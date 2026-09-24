"""Per-run artefacts that are not the load generator's own output.

Three things, all best-effort except the last: an APerf recording on the SUT
node, `kubectl top` samples every ten seconds, and the Pyroscope flame graph of
the measured process. If APerf or Pyroscope fail the run still counts - the
argument of the talk stands on the knee and the flame graphs, and the smoke gate
(plan Task 6.5) is what decides whether APerf records on Bottlerocket at all.

There is no CLI here on purpose: cell.py is the only entrypoint, and it is the
one that calls require_sandbox().
"""

import json
import re
import threading
import time
from datetime import UTC, datetime
from statistics import median

import httpx

import config

# `kubectl aperf` (aws/aperf docs/README-EKS.md, verified 2026-09-04) has no
# `record` subcommand: it drives record + report + copy + cleanup itself, and the
# classic aperf flags travel inside --aperf_options. The tarball
# aperf_record_YYYYMMDD-HHMMSS.tar.gz lands in the CURRENT directory, so the run's
# aperf/ directory is passed as cwd rather than as a flag.
APERF_NAMESPACE = config.NAMESPACE  # the aad namespace is already PSS privileged

PYROSCOPE_PORT = 4040
# Profile type and label selector per the Pyroscope server API reference; the
# service_name label is what the chart's ingestion_relabeling_rules map
# process.executable.name onto (manifests/base/pyroscope-values.yaml).
PYROSCOPE_QUERY = 'process_cpu:cpu:nanoseconds:cpu:nanoseconds{{service_name="{service}"}}'

# `kubectl top` prints different columns for nodes and for pods, and the pod form
# has no percentage at all. From the printer that produces them (kubectl 1.33,
# staging/src/k8s.io/kubectl/pkg/metricsutil/metrics_printer.go):
#   NodeColumns = {"NAME", "CPU(cores)", "CPU(%)", "MEMORY(bytes)", "MEMORY(%)"}
#   PodColumns  = {"NAME", "CPU(cores)", "MEMORY(bytes)"}
# with CPU printed as "%vm" and memory as "%vMi". One regex for both would have
# to make the percentage optional, and then every pod line would read its memory
# as a CPU percentage; two regexes are the honest version.
_TOP_NODE = re.compile(r"^(\S+)\s+(\d+)m\s+(\d+)%")
_TOP_POD = re.compile(r"^(\S+)\s+(\d+)m\s+(\d+)Mi")

# Pods of the load generators, which run on the loader node and are not the SUT.
_LOADER_PODS = ("k6-", "ycsb-", "iperf3-client")


APERF_LOG = "aperf.log"


def aperf_start(node, seconds, out_dir):
    """Start the APerf recording that should cover the measured run.

    Its output lands in run-<i>/aperf/aperf.log, next to the tarball, and that
    file is the only diagnostic when `aperf_finish` reports "failed: exit 1":
    the plugin says there why (no PMU in the guest, no /boot, a pod that would
    not schedule) and the runner deliberately does not fail the run over it.
    Before, that output went to a pipe nobody read (config.popen).
    """
    if not config.DRY_RUN:
        out_dir.mkdir(parents=True, exist_ok=True)
    return config.popen(
        [
            "kubectl", "aperf",
            f"--node={node}",
            f"--aperf_options=-i 1 -p {seconds}",
            f"--namespace={APERF_NAMESPACE}",
            # Pinned image (public.ecr.aws tag v1.2.3 verified 2026-09-04) and no
            # browser: the plugin defaults to :latest and --open-report=true.
            "--aperf_image=public.ecr.aws/aperf/aperf:v1.2.3",
            "--open-report=false",
        ],
        cwd=out_dir,
        log=None if config.DRY_RUN else out_dir / APERF_LOG,
    )


def aperf_finish(proc, timeout):
    """'ok' or the reason it is not. Never raises: APerf is not the measurement."""
    if proc is None:
        return "dry-run"
    try:
        rc = proc.wait(timeout=timeout)
    except Exception as exc:  # includes TimeoutExpired
        proc.kill()
        return f"failed: {exc}"
    return "ok" if rc == 0 else f"failed: exit {rc}"


def flamegraph(service, start, end, out_path):
    """Pyroscope render JSON for one process, through a temporary port-forward.

    The API serves json (flamebearer) or dot and no PNG, so this saves the JSON;
    the slide images are screenshots of the Pyroscope UI.
    """
    forward = config.popen(
        ["kubectl", "port-forward", "-n", config.NAMESPACE,
         "svc/pyroscope", f"{PYROSCOPE_PORT}:{PYROSCOPE_PORT}"]
    )
    params = {
        "query": PYROSCOPE_QUERY.format(service=service),
        "from": str(int(start)),
        "until": str(int(end)),
        "format": "json",
    }
    if config.DRY_RUN:
        print(f"# GET http://127.0.0.1:{PYROSCOPE_PORT}/pyroscope/render {params} -> {out_path}")
        return "dry-run"
    try:
        time.sleep(2)  # let the forward come up
        r = httpx.get(
            f"http://127.0.0.1:{PYROSCOPE_PORT}/pyroscope/render", params=params, timeout=60
        )
        r.raise_for_status()
        out_path.write_text(r.text)
        return "ok"
    except Exception as exc:
        return f"failed: {exc}"
    finally:
        if forward:
            forward.terminate()


def parse_top(node_text, pod_text, sut, loader, keep=None):
    """One sample out of the two `kubectl top` outputs. Pure, so it is testable.

    Every cell node lands in `nodes`, because the net cell runs on two of them
    and only sampling the first would report the client's CPU as the server's
    half the time. `node_cpu_*` stays the SUT's, which is what the medians and
    cpu_per_gbps read.
    """
    sample = {"ts": datetime.now(UTC).isoformat(), "nodes": {}}
    for line in node_text.splitlines():
        m = _TOP_NODE.match(line.strip())
        if not m:
            continue  # '<unknown>' when metrics-server has no sample for the node yet
        name, millicores, percent = m.group(1), int(m.group(2)), int(m.group(3))
        if keep is not None and name not in keep:
            continue  # tools node, other cells: not this cell's business
        if name == loader:
            sample["loader_cpu_millicores"], sample["loader_cpu_percent"] = millicores, percent
            continue
        sample["nodes"][name] = millicores
        if name == sut:
            sample["node_cpu_millicores"], sample["node_cpu_percent"] = millicores, percent
    pod_m = 0
    for line in pod_text.splitlines():
        m = _TOP_POD.match(line.strip())
        if m and not m.group(1).startswith(_LOADER_PODS):
            pod_m = max(pod_m, int(m.group(2)))
    sample["pod_cpu_millicores"] = pod_m
    return sample


# How far a `kubectl top` value can trail the load it reports: metrics-server
# serves the CPU rate of the kubelet's last window, 15-60 s old. Only the
# fallback path needs it; the metrics API says its own window.
METRICS_LAG_SECONDS = 20

_DURATION = re.compile(r"(\d+(?:\.\d+)?)(h|ms|us|µs|ns|m|s)")
_DURATION_UNIT = {"h": 3600, "m": 60, "s": 1, "ms": 1e-3, "us": 1e-6, "µs": 1e-6, "ns": 1e-9}
_CPU_UNIT = {"n": 1e-6, "u": 1e-3, "m": 1, "": 1000}  # to millicores


def _seconds(duration):
    """A Go duration string ("20.035s", "1m0.5s") in seconds."""
    return sum(float(v) * _DURATION_UNIT[u] for v, u in _DURATION.findall(duration))


def _millicores(quantity):
    """A CPU quantity ("123456789n", "250m", "2") in millicores."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([num]?)", quantity)
    return float(m.group(1)) * _CPU_UNIT[m.group(2)]


def parse_node_metrics(body, allocatable, sut, loader, keep=None):
    """One sample out of GET /apis/metrics.k8s.io/v1beta1/nodes; None when the
    answer is not a NodeMetricsList (API not served, error, dry run).

    Unlike `kubectl top`, every item carries the interval its value covers,
    [timestamp - window, timestamp], on the cluster's clock (kubelet stamps it,
    metrics-server passes it through): that interval, not the moment the laptop
    received the answer, is what gets attributed to a ladder step. Percent is
    over the node's allocatable CPU, as `kubectl top node` computes it.
    """
    try:
        items = json.loads(body)["items"]
    except (ValueError, KeyError, TypeError):
        return None
    sample = {"ts": datetime.now(UTC).isoformat(), "source": "metrics-api", "nodes": {}}
    for item in items:
        name = item["metadata"]["name"]
        if keep is not None and name not in keep:
            continue
        end = _epoch(item["timestamp"])
        window = [end - _seconds(item["window"]), end]
        millicores = round(_millicores(item["usage"]["cpu"]))
        percent = round(100 * millicores / allocatable[name]) if allocatable.get(name) else None
        if name == loader:
            sample.update(loader_cpu_millicores=millicores, loader_cpu_percent=percent,
                          loader_window=window)
            continue
        sample["nodes"][name] = millicores
        if name == sut:
            sample.update(node_cpu_millicores=millicores, node_cpu_percent=percent,
                          node_window=window)
    return sample


def _allocatable():
    """{node: allocatable millicores}, read once per sampler."""
    out = config.sh(["kubectl", "get", "nodes", "-o",
                     'jsonpath={range .items[*]}{.metadata.name}={.status.allocatable.cpu}{"\\n"}{end}'],
                    capture=True, quiet=True, check=False)
    return {name: _millicores(cpu) for name, cpu in
            (line.split("=", 1) for line in out.splitlines() if "=" in line)}


def _top(nodes, sut, loader, allocatable):
    """One sample: every cell node's CPU, the loader's, and the measured pod's.

    Nodes from the metrics API (parse_node_metrics). Only when that is not served
    does it fall back to `kubectl top node`, whose samples carry no window of
    their own; the guard then stretches each step by METRICS_LAG_SECONDS.
    """
    keep = set(nodes) | {loader}
    body = config.sh(["kubectl", "get", "--raw", "/apis/metrics.k8s.io/v1beta1/nodes",
                      "--request-timeout=5s"], capture=True, quiet=True, check=False)
    pod_text = config.sh(
        ["kubectl", "top", "pod", "-n", config.NAMESPACE, "--no-headers"],
        capture=True, quiet=True, check=False,
    )
    sample = parse_node_metrics(body, allocatable, sut, loader, keep)
    if sample is None:
        # `kubectl top node` takes ONE name (or -l); with several it errors out
        # and the guard sampled nothing (2026-09-04 gate). List all, keep ours.
        node_text = config.sh(["kubectl", "top", "node", "--no-headers"],
                              capture=True, quiet=True, check=False)
        sample = parse_top(node_text, "", sut, loader, keep=keep)
        sample["source"] = "kubectl-top"
    sample["pod_cpu_millicores"] = parse_top("", pod_text, sut, loader)["pod_cpu_millicores"]
    return sample


def parse_actuator(body):
    """The VALUE of one /actuator/metrics/<name> answer; None when there is none.

    None and not 0: a pool gauge that reads 0 and a meter that is not there
    (actuator not exposed, MBean registry off, a 404 through the proxy) are
    opposite findings.
    """
    try:
        for measurement in json.loads(body)["measurements"]:
            if measurement["statistic"] == "VALUE":
                return measurement["value"]
    except (ValueError, KeyError, TypeError):
        pass
    return None


def _actuator(spec):
    """One reading of every meter in config.WORKLOADS[...]["actuator"]."""
    base = f"/api/v1/namespaces/{config.NAMESPACE}/services/{spec['proxy']}/proxy{spec['path']}"
    # 2 s each: a JVM stalled under overload must not hold up the CPU samples
    # (TopSampler takes those first anyway); a timeout reads as missing.
    return {
        name: parse_actuator(config.sh(["kubectl", "get", "--raw", f"{base}/{name}",
                                        "--request-timeout=2s"],
                                       capture=True, quiet=True, check=False))
        for name in spec["metrics"]
    }


def actuator_stats(samples):
    """{meter: {"max", "median", "samples"}} over the samples that carry a
    reading, or "missing" for a meter that never answered. Not fatal: the pools
    explain a knee, they do not decide it."""
    values = {}
    for sample in samples:
        for name, value in (sample.get("actuator") or {}).items():
            values.setdefault(name, [])
            if value is not None:
                values[name].append(value)
    return {name: ({"max": max(v), "median": median(v), "samples": len(v)} if v else "missing")
            for name, v in values.items()}


def _epoch(ts):
    return datetime.fromisoformat(ts).timestamp()


def ladder_windows(start, stage_seconds, steps):
    """{step: (begin, end)} in epoch seconds for a k6 ladder whose container
    started at `start` (its startedAt, node clock): lib.js holds step i from
    start + i x STAGE_SECONDS for STAGE_SECONDS, ramp included. The scenario
    itself starts a few seconds after the container; attributing a metrics
    interval to every step it overlaps (by_overlap) absorbs that."""
    return {step: (start + i * stage_seconds, start + (i + 1) * stage_seconds)
            for i, step in enumerate(steps)}


def interval(sample, who=None):
    """The time a sample's value covers. `who` = "loader" or "node": the metrics
    API window of that node; without one (the `kubectl top` fallback) the value
    may trail the load by METRICS_LAG_SECONDS. who=None: the receipt instant."""
    w = sample.get(f"{who}_window") if who else None
    if w:
        return w
    t = _epoch(sample["ts"])
    return [t - METRICS_LAG_SECONDS, t] if who else [t, t]


def by_overlap(samples, windows, who=None):
    """{key: [samples whose interval overlaps (begin, end)]}. A sample lands in
    EVERY step it overlaps: a 20 s metrics window across a step boundary says
    something about both, and dropping it from the second is how overload at
    the tail of a crossing step used to fall into the next, unguarded step."""
    out = {key: [] for key in windows}
    for sample in samples:
        b, e = interval(sample, who)
        for key, (begin, end) in windows.items():
            if b < end and e >= begin:
                out[key].append(sample)
    return out


def window_cores(samples, windows):
    """{key: median SUT node CPU in cores over the distinct metrics windows that
    lie WHOLLY inside (begin, end), or None when none does}. Wholly inside, so
    an idle baseline never borrows a lagged value of the run before it, and a
    direction never borrows the other's. Needs the metrics API's windows: a
    `kubectl top` sample covers nothing it can prove."""
    out = {}
    for key, (begin, end) in windows.items():
        seen = {}
        for s in samples:
            w = s.get("node_window")
            if w and "node_cpu_millicores" in s and begin <= w[0] and w[1] <= end:
                seen[tuple(w)] = s["node_cpu_millicores"]  # a repeated poll is one sample
        out[key] = median(seen.values()) / 1000.0 if seen else None
    return out


def net_coverage(per):
    """What a net run's per-window CPU is missing: [] when cpu_per_gbps holds."""
    notes = [] if per.get("baseline") is not None else ["baseline_missing"]
    return notes + [f"direction_uncovered: {d}" for d in ("fwd", "rev") if per.get(d) is None]


def loader_peak(samples):
    return max((s.get("loader_cpu_percent") or 0 for s in samples), default=0)


def loader_observed(samples):
    return [s for s in samples if s.get("loader_cpu_percent") is not None]


class TopSampler:
    """`kubectl top` every ten seconds into run-<i>/top.json.

    Also the loader guard: `peak_loader_percent` is what says whether the number
    on the slide is the SUT's limit or the generator's. With `actuator` (Java)
    every sample also carries the pool gauges, see `actuator_stats`.
    """

    def __init__(self, nodes, loader, sut=None, interval=10, actuator=None):
        self.nodes = list(nodes)
        self.sut = sut or self.nodes[0]
        self.loader, self.interval, self.actuator = loader, interval, actuator
        self.samples = []
        self._allocatable = None
        self._stop = threading.Event()
        self._thread = None

    def __enter__(self):
        if config.DRY_RUN:
            self._sample()  # prints the command plan once
            return self
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def _sample(self):
        """CPU first, into the list, THEN the pool gauges onto the same sample:
        a stalled actuator must never cost the guard its CPU sample."""
        if not self._allocatable:  # retried until it answers: without it no percent
            self._allocatable = _allocatable()
        sample = _top(self.nodes, self.sut, self.loader, self._allocatable)
        self.samples.append(sample)
        if self.actuator:
            sample["actuator"] = _actuator(self.actuator)
        return sample

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._sample()
            except Exception as exc:  # a missing metrics-server must not kill a run
                self.samples.append({"ts": datetime.now(UTC).isoformat(), "error": str(exc)})
            self._stop.wait(self.interval)

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval + 5)
        return False

    @property
    def peak_loader_percent(self):
        return loader_peak(self.samples)

    def write(self, path):
        path.write_text(json.dumps(self.samples, indent=1))
