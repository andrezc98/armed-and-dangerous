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


def _top(nodes, sut, loader):
    """One sample: every cell node's CPU, the loader's, and the measured pod's."""
    # `kubectl top node` takes ONE name (or -l); with several it errors out and
    # the guard sampled nothing (found on the 2026-09-04 gate: loader_peak 0
    # during a 40k rps ladder). List every node and keep the ones we want.
    node_text = config.sh(
        ["kubectl", "top", "node", "--no-headers"],
        capture=True, quiet=True, check=False,
    )
    pod_text = config.sh(
        ["kubectl", "top", "pod", "-n", config.NAMESPACE, "--no-headers"],
        capture=True, quiet=True, check=False,
    )
    return parse_top(node_text, pod_text, sut, loader, keep=set(nodes) | {loader})


class TopSampler:
    """`kubectl top` every ten seconds into run-<i>/top.json.

    Also the loader guard: `peak_loader_percent` is what says whether the number
    on the slide is the SUT's limit or the generator's.
    """

    def __init__(self, nodes, loader, sut=None, interval=10):
        self.nodes = list(nodes)
        self.sut = sut or self.nodes[0]
        self.loader, self.interval = loader, interval
        self.samples = []
        self._stop = threading.Event()
        self._thread = None

    def __enter__(self):
        if config.DRY_RUN:
            _top(self.nodes, self.sut, self.loader)  # prints the command plan once
            return self
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.samples.append(_top(self.nodes, self.sut, self.loader))
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
        return max((s.get("loader_cpu_percent", 0) for s in self.samples), default=0)

    def write(self, path):
        path.write_text(json.dumps(self.samples, indent=1))
