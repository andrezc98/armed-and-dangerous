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

_TOP_CPU = re.compile(r"^(\S+)\s+(\d+)m\s+(\d+)%")


def aperf_start(node, seconds, out_dir):
    """Start the APerf recording that should cover the measured run."""
    if not config.DRY_RUN:
        out_dir.mkdir(parents=True, exist_ok=True)
    return config.popen(
        [
            "kubectl", "aperf",
            f"--node={node}",
            f"--aperf_options=-i 1 -p {seconds}",
            f"--namespace={APERF_NAMESPACE}",
        ],
        cwd=out_dir,
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


def _top(node, loader):
    """One sample: SUT node CPU, loader node CPU, and the measured pod's CPU."""
    nodes = config.sh(
        ["kubectl", "top", "node", node, loader, "--no-headers"], capture=True, quiet=True, check=False
    )
    pods = config.sh(
        ["kubectl", "top", "pod", "-n", config.NAMESPACE, "--no-headers"],
        capture=True, quiet=True, check=False,
    )
    sample = {"ts": datetime.now(UTC).isoformat()}
    for line in nodes.splitlines():
        m = _TOP_CPU.match(line.strip())
        if not m:
            continue
        which = "node" if m.group(1) == node else "loader"
        sample[f"{which}_cpu_millicores"] = int(m.group(2))
        sample[f"{which}_cpu_percent"] = int(m.group(3))
    pod_m = 0
    for line in pods.splitlines():
        m = _TOP_CPU.match(line.strip())
        if m and not m.group(1).startswith(("k6-", "ycsb-", "iperf3-client")):
            pod_m = max(pod_m, int(m.group(2)))
    sample["pod_cpu_millicores"] = pod_m
    return sample


class TopSampler:
    """`kubectl top` every ten seconds into run-<i>/top.json.

    Also the loader guard: `peak_loader_percent` is what says whether the number
    on the slide is the SUT's limit or the generator's.
    """

    def __init__(self, node, loader, interval=10):
        self.node, self.loader, self.interval = node, loader, interval
        self.samples = []
        self._stop = threading.Event()
        self._thread = None

    def __enter__(self):
        if config.DRY_RUN:
            _top(self.node, self.loader)  # prints the command plan once
            return self
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.samples.append(_top(self.node, self.loader))
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
