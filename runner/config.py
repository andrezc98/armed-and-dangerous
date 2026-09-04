"""Constants of the lab and the one place a subprocess is spawned.

Everything the runner knows about a cell lives here: which managed node group it
runs on, which instance is under it, how many exclusive vCPUs its pod should own,
and the load parameters of each workload. `cell.py` and `capture.py` only combine
these; they do not invent values.
"""

import os
import shlex
import subprocess
from pathlib import Path

RUNNER = Path(__file__).resolve().parent
REPO = RUNNER.parent
RESULTS = REPO / "results"
MANIFESTS = REPO / "manifests"
NAMESPACE = "aad"
# The lab lives in us-east-1 and the sandbox profile does not default to it, so
# every `aws` call the runner renders passes --region explicitly. A call that
# resolves to another region either fails or - worse - answers "nothing here"
# to a leak check.
REGION = "us-east-1"

# Set by cell.py --dry-run. sh() prints and returns "" while it is on.
DRY_RUN = False


def require_sandbox() -> None:
    """Refuse to touch AWS unless the personal sandbox profile or CI OIDC is in use."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return
    profile = os.environ.get("AWS_PROFILE", "")
    if "sandbox" not in profile:
        raise RuntimeError(
            "AWS_PROFILE must be the personal sandbox profile (name contains 'sandbox'); "
            "refusing to use default credentials"
        )


def sh(cmd, *, capture=False, check=True, cwd=None, stdin=None, quiet=False, stderr=None):
    """The only place this runner spawns a process.

    One funnel so --dry-run can print the exact command plan, and so the AWS CLI
    keeps inheriting AWS_PROFILE instead of a second credential path existing in
    Python (that is also why there is no boto3 in pyproject.toml).

    `stderr` is an optional list the child's stderr is appended to, for the
    callers that have to put it in an error message (capture=True only; without
    capture the child writes straight to the terminal).
    """
    line = "$ " + shlex.join(cmd)
    if stdin is not None:
        line = f"$ <stdin> | {shlex.join(cmd)}"
    if cwd:
        line += f"    # cwd={cwd}"
    # quiet is for the polling and sampling loops, which would otherwise bury the
    # plan under one line every ten seconds. --dry-run still prints them, because
    # in a dry run each of those loops executes exactly once.
    if DRY_RUN or not quiet:
        print(line, flush=True)
    if DRY_RUN:
        return ""
    out = subprocess.run(
        cmd,
        cwd=cwd,
        input=stdin,
        text=True,
        capture_output=capture,
        check=False,
    )
    if stderr is not None and out.stderr:
        stderr.append(out.stderr)
    if check and out.returncode:
        # CalledProcessError prints the command and the exit code and swallows
        # the captured stderr, which is the only part that says what went wrong.
        raise RuntimeError(
            f"{shlex.join(cmd)} exited {out.returncode}"
            + (f"\n{out.stderr.strip()}" if out.stderr else "")
        )
    return (out.stdout or "") if capture else ""


# --- cells -------------------------------------------------------------------
# Overlay name -> managed node group key in `terraform output -json nodegroup_names`.
# The three that are not 1:1 are cells of a workload, not node groups: x86-t15 is
# llama.cpp with -t 15 on the x86-tuned node group, and the two -vthreads cells
# are the same tuned nodes with a different JVM flag.
CELL_MNG = {
    "x86-stock": "x86-stock",
    "x86-tuned": "x86-tuned",
    "x86-smtoff": "x86-smtoff",
    "arm-stock": "arm-stock",
    "arm-tuned": "arm-tuned",
    "x86-t15": "x86-tuned",
    "x86-tuned-vthreads": "x86-tuned",
    "arm-tuned-vthreads": "arm-tuned",
}

INSTANCE = {
    "x86-stock": "m8i.4xlarge",
    "x86-tuned": "m8i.4xlarge",
    "x86-smtoff": "m8i.4xlarge",
    "arm-stock": "m9g.4xlarge",
    "arm-tuned": "m9g.4xlarge",
}

# Exclusive vCPUs the measured pod must own (static CPU manager + 1 reserved
# vCPU, infra/userdata/base.toml). x86-smtoff is 8 vCPUs, so 7.
EXCLUSIVE_CPUS = {"x86-smtoff": 7}
DEFAULT_EXCLUSIVE_CPUS = 15

LOADER_CPU_GUARD_PERCENT = 70  # above this the loader is the bottleneck, not the SUT

# --- workloads ---------------------------------------------------------------
# Every number here is a default the smoke gate (plan Task 6.5) is allowed to
# move; all of them are overridable from the CLI.
WORKLOADS = {
    "java": {
        "loader": "k6",
        "script": "java.js",
        "target_url": "http://java.aad.svc:9966",
        "resource": "deploy/java",
        # Pyroscope labels a profile by process.executable.name (the chart's
        # ingestion_relabeling_rules in manifests/base/pyroscope-values.yaml).
        "service_name": "java",
        "slo_ms": 100,  # CMP333 acceptance rule
        # RAMP_SECONDS is in the ladder and not only a lib.js default because the
        # runner needs the held seconds of a step to judge whether the generator
        # delivered it (knee.step_reasons); k6 gets the same number as env.
        "ladder": {"RATE_START": 200, "RATE_STEP": 400, "RATE_MAX": 6000,
                   "STAGE_SECONDS": 60, "RAMP_SECONDS": 5},
        "fixed_seconds": 480,
        "warmup_seconds": 180,
        "cells": ["x86-stock", "x86-tuned", "x86-smtoff", "arm-stock", "arm-tuned",
                  "x86-tuned-vthreads", "arm-tuned-vthreads"],
    },
    "go": {
        "loader": "k6",
        "script": "go.js",
        "target_url": "http://go.aad.svc:8080",
        "resource": "deploy/go",
        "service_name": "aad-go",
        # distroless: no shell to `kubectl exec` a `cat` into, so the cpuset
        # control reads /healthz through the API server service proxy instead
        # (<service>:<port> of the k8s apiserver proxy URL form).
        "cpus_proxy": "go:8080",
        "slo_ms": 20,
        "ladder": {"RATE_START": 1000, "RATE_STEP": 1000, "RATE_MAX": 20000,
                   "STAGE_SECONDS": 60, "RAMP_SECONDS": 5},
        "fixed_seconds": 480,
        "warmup_seconds": 60,
        "cells": ["x86-stock", "arm-stock"],
    },
    "inference": {
        "loader": "k6",
        "script": "inference.js",
        "target_url": "http://llama.aad.svc:8080",
        "resource": "deploy/llama",
        "service_name": "llama-server",
        # 0 = no latency SLO. A closed loop on 4 slots is measured in tok/s,
        # and a p99 threshold here only made every Job end Failed
        # (runner/k6/lib.js omits the threshold when SLO_MS <= 0).
        "slo_ms": 0,
        # No ladder: with --parallel 4 slots an open arrival rate either idles
        # slots or queues inside the server, so the measured run is closed-loop
        # (MODE=saturate, VUS = slots) and there is no knee to find.
        "ladder": None,
        "saturate_vus": 4,
        "fixed_seconds": 360,
        "warmup_seconds": 60,
        "cells": ["x86-stock", "x86-tuned", "x86-t15", "arm-stock", "arm-tuned"],
    },
    "mongo": {
        "loader": "ycsb",
        "resource": "statefulset/mongo",
        "service_name": "mongod",
        "slo_ms": 5,  # READ p99
        "threads": [16, 32, 64, 128],
        "recordcount": 20000000,  # same value as ycsb-load-job.yaml, on purpose
        "workload_file": "workloadb",  # 95/5 read heavy; the load itself is workloada
        # The knee jobs run unthrottled (--target 0), so their length is
        # operationcount / achieved OPS. Sized for roughly a minute per step at
        # the throughput the gate measures; the gate tunes it.
        "knee_operationcount": 2000000,
        "fixed_seconds": 480,
        "warmup_seconds": 300,
        "warm_pages": 1000,  # 'pages read into cache' delta per pass that counts as flat
        "warm_max_min": 20,  # give up warming after this and refuse to measure EBS
        "cells": ["x86-stock", "x86-tuned", "arm-stock", "arm-tuned"],
    },
    "net": {
        "loader": "iperf3",
        "resource": "deploy/iperf3-server",
        "service_name": "iperf3",
        # -P 8 -t 60 are baked into the client Job templates; repeated here only
        # so the runner knows how long to record APerf for.
        "fixed_seconds": 60,
        "warmup_seconds": 0,
        "nodes": 2,  # client and server on two nodes of the same node group
        "cells": ["x86-stock", "x86-tuned", "arm-stock", "arm-tuned"],
    },
}


def node_cell(cell):
    """The aad/cell label value of the node group a cell runs on."""
    return CELL_MNG[cell]


def instance_type(cell):
    return INSTANCE[node_cell(cell)]


def exclusive_cpus(cell):
    return EXCLUSIVE_CPUS.get(node_cell(cell), DEFAULT_EXCLUSIVE_CPUS)


def popen(cmd, *, cwd=None, log=None):
    """Same funnel for the two commands that must outlive the call: the APerf
    recording and the Pyroscope port-forward. Returns None under --dry-run.

    `log` is a path that receives the child's stdout and stderr; without it the
    child writes to this terminal. What it must never be again is a pipe nobody
    reads: a child that fills the 64 KiB pipe buffer blocks forever, and the one
    child here that talks (APerf, a line per sampling interval) is also the one
    the runner waits on, so that deadlock lands in the middle of a paid run.
    """
    print("$ " + shlex.join(cmd) + " &" + (f"    # cwd={cwd}" if cwd else ""), flush=True)
    if DRY_RUN:
        return None
    if log is None:
        return subprocess.Popen(cmd, cwd=cwd, text=True)
    # Popen dups the descriptor, so the parent's handle can close right away.
    with open(log, "w") as handle:
        return subprocess.Popen(cmd, cwd=cwd, text=True, stdout=handle,
                                stderr=subprocess.STDOUT)
