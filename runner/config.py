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


def sh(cmd, *, capture=False, check=True, cwd=None, stdin=None, quiet=False, stderr=None,
       timeout=None):
    """The only place this runner spawns a process.

    One funnel so --dry-run can print the exact command plan, and so the AWS CLI
    keeps inheriting AWS_PROFILE instead of a second credential path existing in
    Python (that is also why there is no boto3 in pyproject.toml).

    `stderr` is an optional list the child's stderr is appended to, for the
    callers that have to put it in an error message (capture=True only; without
    capture the child writes straight to the terminal).

    `timeout` (seconds) kills the child and raises RuntimeError, for the
    sampling loops that must never hang on one stuck call.
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
    try:
        out = subprocess.run(
            cmd,
            cwd=cwd,
            input=stdin,
            text=True,
            capture_output=capture,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{shlex.join(cmd)} timed out after {timeout}s") from exc
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
# The ones that are not 1:1 are cells of a workload, not node groups: x86-t8 is
# llama.cpp with -t 8 (one thread per physical core) on the x86-tuned node group,
# arm-tuned-kleidiai is another llama image on arm-tuned, and the three -vthreads
# cells are the same tuned nodes with a different JVM flag.
CELL_MNG = {
    "x86-stock": "x86-stock",
    "x86-tuned": "x86-tuned",
    "x86-smtoff": "x86-smtoff",
    "amd-stock": "amd-stock",
    "amd-tuned": "amd-tuned",
    "arm-stock": "arm-stock",
    "arm-tuned": "arm-tuned",
    "x86-t8": "x86-tuned",
    "arm-tuned-kleidiai": "arm-tuned",
    "x86-tuned-vthreads": "x86-tuned",
    "amd-tuned-vthreads": "amd-tuned",
    "arm-tuned-vthreads": "arm-tuned",
}

INSTANCE = {
    "x86-stock": "m8i.4xlarge",
    "x86-tuned": "m8i.4xlarge",
    "x86-smtoff": "m8i.4xlarge",
    # AMD EPYC 9R45 (Turin), 16 vCPU = 16 cores, one thread per core (EC2
    # describe-instance-types, 2026-09-24). Added 2026-09-25, speaker ruling.
    "amd-stock": "m8a.4xlarge",
    "amd-tuned": "m8a.4xlarge",
    "arm-stock": "m9g.4xlarge",
    "arm-tuned": "m9g.4xlarge",
}

# Exclusive vCPUs the measured pod must own (static CPU manager + 1 reserved
# vCPU, infra/userdata/base.toml). x86-smtoff is 8 vCPUs, so 7. The AMD cells
# take the default: m8a.4xlarge is 16 vCPUs, 15 of them exclusive = 15 cores.
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
        # Pool gauges sampled every 10 s during every ladder and fixed run
        # (capture.TopSampler), through the API server service proxy like Go's
        # cpus_proxy. The actuator lives under the servlet context path
        # (server.servlet.context-path=/petclinic/ in the pinned PetClinic's
        # application.properties) and is exposed by the base Deployment's env.
        "actuator": {"proxy": "java:9966", "path": "/petclinic/actuator/metrics",
                     "metrics": ["hikaricp.connections.pending", "hikaricp.connections.active",
                                 "tomcat.threads.busy"]},
        # Pyroscope labels a profile by process.executable.name (the chart's
        # ingestion_relabeling_rules in manifests/base/pyroscope-values.yaml).
        "service_name": "java",
        # Smoke gate 2026-09-04: CMP333's 100 ms was for a heavier Groovy app;
        # PetClinic reads stay under 13 ms at 100k rps on Graviton, so a 100 ms
        # knee sits beyond what one loader can offer.
        "slo_ms": 10,
        # Two k6 Jobs per ladder, warm-up and fixed run, each at half the load
        # (cell.run_k6). Calibration 2026-09-24, Java arm-tuned held at 70k rps
        # for 180 s (results/2026-09-24-cal-loadercheck/loadercheck.json): one k6
        # process delivered 69,845 rps at p99 6.59 ms, two at 35k each delivered
        # 69,846 rps at p99 5.73 / 5.77 ms, loader node 37-41 % CPU either way.
        # One process adds ~0.8 ms (+13 %) to p99 at that rate, which moves
        # knees near the 10 ms SLO.
        "k6_generators": 2,
        # RAMP_SECONDS is in the ladder and not only a lib.js default because the
        # runner needs the held seconds of a step to judge whether the generator
        # delivered it (knee.step_reasons); k6 gets the same number as env.
        # 10k start: x86-smtoff has 7 vCPUs and must not cross on the first step.
        # 10k steps again since 2026-09-24: x86-tuned read 3.9 ms at 30k and
        # 11.5 ms at 40k at the gate, and 10k steps alone would round that knee
        # down by a quarter, but every fixed run now climbs its own fine ladder
        # first (fine_steps below), which gives 2k resolution at a fraction of
        # the 5k coarse ladder's time. The VU budget is the one the gate needed
        # near 100k rps (lib.js defaults starve it).
        "ladder": {"RATE_START": 10000, "RATE_STEP": 10000, "RATE_MAX": 120000,
                   "STAGE_SECONDS": 60, "RAMP_SECONDS": 5,
                   "PREALLOC_VUS": 2000, "MAX_VUS": 16000},
        # Fine ladder before each fixed run (cell.fine_knee): K + S/5 .. K + S in
        # fine_steps steps of fine_stage_seconds, same RAMP_SECONDS and VU budget.
        # Costs 5 x 45 s + the Job's start, ~4 min per run, ~12 min per cell.
        "fine_steps": 5,
        "fine_stage_seconds": 45,
        "fixed_seconds": 480,
        "warmup_seconds": 180,
        "cells": ["x86-stock", "x86-tuned", "x86-smtoff", "amd-stock", "amd-tuned",
                  "arm-stock", "arm-tuned",
                  "x86-tuned-vthreads", "amd-tuned-vthreads", "arm-tuned-vthreads"],
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
        "k6_generators": 2,  # same reason as Java's
        # Sized from an estimate, not a measurement (Go did not run at the gate):
        # since 2026-09-24 a request sorts ECHO_N uint64 (apps/go), and ECHO_N
        # 10000 is ~0.2-0.3 ms of CPU (runner/k6/go.js says how that was
        # estimated), so 15 vCPUs top out near 50k rps. The calibration day
        # confirms it. The aad-go image in ECR still serves the old add loop:
        # rebuild and re-push it (images workflow, PUSH=1) before the lab.
        "ladder": {"RATE_START": 5000, "RATE_STEP": 5000, "RATE_MAX": 100000,
                   "STAGE_SECONDS": 60, "RAMP_SECONDS": 5,
                   "PREALLOC_VUS": 2000, "MAX_VUS": 16000},
        # Fine ladder before each fixed run, 1k resolution: ~4 min per run
        # (5 x 45 s + the Job's start), same rules as Java's.
        "fine_steps": 5,
        "fine_stage_seconds": 45,
        "fixed_seconds": 480,
        "warmup_seconds": 60,
        "cells": ["x86-stock", "amd-stock", "arm-stock"],
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
        # One Job: a closed loop of 4 VUs has nothing to split.
        "k6_generators": 1,
        # No ladder: with --parallel 4 slots an open arrival rate either idles
        # slots or queues inside the server, so the measured run is closed-loop
        # (MODE=saturate, VUS = slots) and there is no knee to find.
        "ladder": None,
        "saturate_vus": 4,
        "fixed_seconds": 360,
        "warmup_seconds": 60,
        "cells": ["x86-stock", "x86-tuned", "x86-t8", "amd-stock", "amd-tuned",
                  "arm-stock", "arm-tuned", "arm-tuned-kleidiai"],
    },
    "mongo": {
        "loader": "ycsb",
        "resource": "statefulset/mongo",
        "service_name": "mongod",
        "slo_ms": 5,  # READ p99
        # arm-stock read 3.2 ms at 128 threads at the gate and never crossed 5 ms.
        "threads": [16, 32, 64, 128, 256, 512],
        # go-ycsb processes per step, each with threads/N, operationcount/N and
        # --target/N (runner/cell.py run_ycsb). Calibration 2026-09-25
        # (results/2026-09-25-cal-mongo2client/mongo2client.json), arm-stock, 128
        # threads, 10M ops: one process 191.1k ops/s, READ p99 2.71 ms, SUT 8.3
        # cores; two (64+64) 242.2k ops/s (+27 %), p99 1.68/1.70 ms, SUT 9.8 cores.
        # One client capped the step, as one k6 process did for Java. Every thread
        # count and operationcount must divide by it (check_ycsb_clients).
        "ycsb_clients": 2,
        "recordcount": 20000000,  # same value as ycsb-load-job.yaml, on purpose
        "workload_file": "workloadb",  # 95/5 read heavy; the load itself is workloada
        # The knee jobs run unthrottled (--target 0), so their length is
        # operationcount / achieved OPS. The gate measured 130-170k ops/s, where
        # 2M lasted 10-15 s per step; 10M is roughly a minute.
        "knee_operationcount": 10000000,
        # A warm-up pass stays at the old 2M: warm_pages is judged per pass, and a
        # cold first pass has to finish inside warmup_seconds + 900.
        "warm_operationcount": 2000000,
        "fixed_seconds": 480,
        "warmup_seconds": 300,
        "warm_pages": 1000,  # 'pages read into cache' delta per pass that counts as flat
        "warm_max_min": 20,  # give up warming after this and refuse to measure EBS
        "cells": ["x86-stock", "x86-tuned", "amd-stock", "amd-tuned", "arm-stock", "arm-tuned"],
    },
    # PostgreSQL 18.6 + pgbench select-only next to Mongo (speaker ruling R2,
    # 2026-09-25): Mongo queues on admission-control tickets before the CPU runs
    # out, so the SQL database is the second DB story. Every value below is a
    # default the calibration day is allowed to move (manifests/workloads/
    # postgres/README.md, "Qué decide la calibración").
    "postgres": {
        "loader": "pgbench",
        "resource": "statefulset/postgres",
        # Pyroscope's service_name is the process.executable.name of the backends.
        "service_name": "postgres",
        "slo_ms": 5,  # p99 of a select-only transaction, same line as Mongo's READ
        # pgbench -c, the total over pgbench_clients processes. The top step has
        # to stay under the server's max_connections (check_pgbench_clients).
        "clients": [16, 32, 64, 128, 256, 512],
        # pgbench processes (Jobs) per step, each with clients/N and -R rate/N
        # (pgbench 18.6 splits -R across its own threads, pgbench.c
        # "throttle_delay *= nthreads", so N processes offer N x rate/N). Two,
        # for the reason k6 and go-ycsb run two: one generator capped the step.
        "pgbench_clients": 2,
        # -j per process, and the vCPUs its Job requests (the template ties
        # them). pgbench caps -j at -c itself (pgbench.c "if (nthreads >
        # nclients) nthreads = nclients"); so does the runner, for the request.
        # 16 x 2 processes = 32 of the loader's 64 vCPUs (review of 5b1896e);
        # each pgbench pod is also guarded against its own 16
        # (cell.pgbench_pod_guard).
        "pgbench_threads": 16,
        # pgbench -i -s: 100,000 pgbench_accounts rows per unit (pgbench docs),
        # 86 MB at scale 5 on 18.6 (pg_database_size, laptop 2026-09-25), so
        # scale 1000 is ~17 GB: inside a 64 GiB node, like Mongo's 20 GB.
        "scale": 1000,
        "step_seconds": 60,  # -T of every knee step, ~Mongo's one-minute steps
        # --sampling-rate of the per-transaction log the p99 is computed from. A
        # step with fewer sampled transactions than min_samples has no p99 worth
        # the name (knee.pgbench_reasons).
        "sampling_rate": 0.02,
        "min_samples": 10000,
        "fixed_seconds": 480,
        # Fixed runs: -c = this x the knee's clients (capped under
        # max_connections), because under -R -c only caps what is in flight.
        "fixed_clients_factor": 2,
        # Fixed runs judge the service latency (time - schedule_lag) against
        # slo_ms. The schedule lag is recorded (run meta lag_p99_ms/lag_max_ms)
        # but no longer judged: Task 7 day 2 arm-stock hit its 230k target with
        # service p99 3.7-4.2 ms and lag p99 0.5-1.0 s, pgbench pods at 2.7/16
        # cores - the lag was the server's stalls (max 146 ms, BufferMapping
        # waits) draining through an anchored schedule, i.e. real open-loop
        # queueing, not the generator. The generator stays guarded by the
        # pgbench pod CPU check and under-delivery. Speaker ruling 2026-09-26.
        # A number here re-enables the gate (fixed_generator_lagging).
        "pg_max_lag_p99_ms": None,
        "warmup_seconds": 60,  # -T of each warm-up pass
        # 8 KiB pages the pod read from its disks (cgroup io.stat rbytes / 8192)
        # per warm-up pass that count as flat, and the wall-clock bound; same
        # flags as Mongo's (--warm-pages, --warm-max-min).
        "warm_pages": 8192,
        "warm_max_min": 20,
        "cells": ["x86-stock", "x86-tuned", "amd-stock", "amd-tuned", "arm-stock", "arm-tuned"],
    },
    "net": {
        "loader": "iperf3",
        "resource": "deploy/iperf3-server",
        "container": "iperf3",  # the SUT container, for --app-env; default: the resource's name
        "service_name": "iperf3",
        # -P 8 -t 60 are baked into the client Job templates; repeated here only
        # so the runner knows how long to record APerf for.
        "fixed_seconds": 60,
        "warmup_seconds": 0,
        "nodes": 2,  # client and server on two nodes of the same node group
        "cells": ["x86-stock", "x86-tuned", "amd-stock", "amd-tuned", "arm-stock", "arm-tuned"],
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
