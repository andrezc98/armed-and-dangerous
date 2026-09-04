"""One cell of the lab, start to finish: scale up, deploy, warm, find the knee,
measure n times at 80 % of it, scale back to zero, write the ledger.

The whole thing is a straight line of shell-outs through config.sh(), so
`--dry-run` prints the exact command plan and touches nothing. There is no
framework here on purpose: the interesting part of this runner is the order of
the steps and the checks between them, and both are easier to audit as a script
than as a plugin system.

    uv run cell --workload java --cell arm-tuned --runs 3
    uv run cell --workload java --cell arm-tuned --dry-run
    uv run cell --teardown-day
"""

import argparse
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

import capture
import config
import cost
import knee
from config import sh

K6_IMAGE = "grafana/k6:2.2.0"  # /bin/sh present, verified with docker run 2026-09-04
SUMMARY_MARKER = "---AAD-SUMMARY---"
POLL_SECONDS = 10
NODE_READY_TIMEOUT = 900
MONGO_WARM_PAGES = 1000  # 'pages read into cache' delta that counts as flat

# Rendered per run: a Job's pod template is immutable, so the name carries the
# repetition. The k6 scripts arrive through a ConfigMap built from runner/k6/.
K6_JOB = """apiVersion: batch/v1
kind: Job
metadata:
  name: {name}
  namespace: {ns}
spec:
  backoffLimit: 0
  template:
    metadata:
      labels:
        app: k6
    spec:
      restartPolicy: Never
      nodeSelector:
        aad/role: loader
      containers:
        - name: k6
          image: {image}
          command:
            - sh
            - -c
            - "k6 run --quiet -e SUMMARY_PATH=/tmp/summary.json /scripts/{script}; rc=$?; echo {marker}; cat /tmp/summary.json; exit $rc"
          env:
{env}
          resources:
            requests:
              cpu: "8"
              memory: 4Gi
          volumeMounts:
            - name: scripts
              mountPath: /scripts
      volumes:
        - name: scripts
          configMap:
            name: k6-scripts
"""


# --- plumbing ----------------------------------------------------------------

def now():
    return time.time()


def kubectl(*args, **kw):
    return sh(["kubectl", *args], **kw)


def kn(*args, **kw):
    return kubectl("-n", config.NAMESPACE, *args, **kw)


def apply_stdin(yaml_text, what):
    # Parse before applying: a broken template render should fail here, in a
    # millisecond, and not after a node group has been paid for.
    yaml.safe_load(yaml_text)
    print(f"# apply {what}")
    kubectl("apply", "-f", "-", stdin=yaml_text)


def wait_until(predicate, timeout, what):
    """One poll loop for the whole runner. Under --dry-run it evaluates once."""
    print(f"# wait for {what} (timeout {timeout}s, poll {POLL_SECONDS}s)")
    deadline = now() + timeout
    while True:
        value = predicate()
        if value or config.DRY_RUN:
            return value
        if now() > deadline:
            raise RuntimeError(f"timed out waiting for {what}")
        time.sleep(POLL_SECONDS)


# --- cluster -----------------------------------------------------------------

def cluster_info(day_dir):
    """`terraform output -json`, cached once per lab day.

    Terraform is never applied from here; this only reads the state that a human
    already created (infra/README.md).
    """
    cached = day_dir / "cluster.json"
    if cached.exists():
        return json.loads(cached.read_text())
    raw = sh(
        ["terraform", f"-chdir={config.REPO / 'infra'}", "output", "-json"], capture=True
    )
    if not raw:  # --dry-run
        return {
            "cluster_name": "aws-aad-eks-lab",
            "nodegroup_names": {c: f"aws-aad-mng-{c}" for c in config.INSTANCE},
        }
    out = json.loads(raw)
    info = {k: v["value"] for k, v in out.items()}
    day_dir.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(info, indent=1))
    return info


def scale(info, mng, size):
    sh([
        "aws", "eks", "update-nodegroup-config",
        "--cluster-name", info["cluster_name"],
        "--nodegroup-name", info["nodegroup_names"][mng],
        "--scaling-config", f"desiredSize={size}",
    ])


def ready_nodes(label):
    out = kubectl("get", "nodes", "-l", label, "--no-headers", capture=True, quiet=True, check=False)
    return [line.split()[0] for line in out.splitlines() if line.split()[1:2] == ["Ready"]]


def wait_nodes(label, count, placeholder):
    nodes = wait_until(
        lambda: (lambda n: n if len(n) >= count else None)(ready_nodes(label)),
        NODE_READY_TIMEOUT,
        f"{count} Ready node(s) with {label}",
    )
    return nodes or [f"<{placeholder}-{i + 1}>" for i in range(count)]


# --- workload ----------------------------------------------------------------

def overlay(workload, cell):
    return str(config.MANIFESTS / "workloads" / workload / "overlays" / cell)


def sync_k6_scripts():
    yaml_text = kubectl(
        "create", "configmap", "k6-scripts", "-n", config.NAMESPACE,
        f"--from-file={config.RUNNER / 'k6'}", "--dry-run=client", "-o", "yaml",
        capture=True,
    )
    apply_stdin(yaml_text, "configmap/k6-scripts")


def cpuset_size(cpuset):
    """How many vCPUs a cpuset list like '1-7,9' names."""
    total = 0
    for part in cpuset.split(","):
        if "-" in part:
            lo, hi = part.split("-")
            total += int(hi) - int(lo) + 1
        elif part:
            total += 1
    return total


def check_cpuset(spec, cell, meta):
    """The control that makes cells comparable: the pod must own its vCPUs.

    A cpuset equal to the whole node means the static CPU manager did not take,
    the pod is sharing cores with the DaemonSets and the IRQs, and the cell is
    not comparable with any other (manifests/base/README.md).
    """
    expected = config.exclusive_cpus(cell)
    cpuset = kn("exec", spec["resource"], "--", "cat", "/sys/fs/cgroup/cpuset.cpus.effective",
                capture=True, check=False).strip()
    meta["cpuset"] = cpuset or "<dry-run>"
    if not cpuset:
        return []
    count = cpuset_size(cpuset)
    meta["cpuset_count"] = count
    if count != expected:
        return [f"cpuset {cpuset} is {count} vCPUs, expected {expected} exclusive"]
    return []


# --- jobs --------------------------------------------------------------------

_PLACEHOLDER = re.compile(r"__[A-Z][A-Z_]*__")


def render(template_path, **subs):
    """Fill a manifests/ Job template. Every __PLACEHOLDER__ must be known here:
    a template that grows one the runner does not pass would otherwise be applied
    with the literal text in it."""
    text = Path(template_path).read_text()
    for key, value in subs.items():
        text = text.replace(f"__{key}__", str(value))
    left = set(_PLACEHOLDER.findall(text))
    if left:
        raise RuntimeError(f"{Path(template_path).name} still has {sorted(left)}")
    return text


def k6_job_yaml(name, script, env):
    body = "\n".join(f'            - name: {k}\n              value: "{v}"' for k, v in env.items())
    return K6_JOB.format(
        name=name, ns=config.NAMESPACE, image=K6_IMAGE, script=script,
        marker=SUMMARY_MARKER, env=body,
    )


def run_job(name, yaml_text, timeout):
    """Apply one Job, wait for it to finish either way, return its logs.

    k6 exits 99 when a threshold fails, so the Job ends Failed on a run that
    completed perfectly well (runner/k6/lib.js). Waiting only for
    condition=complete would hang on exactly the runs that carry the knee, hence
    the poll on both conditions.
    """
    kn("delete", "job", name, "--ignore-not-found")
    apply_stdin(yaml_text, f"job/{name}")

    def finished():
        conditions = kn(
            "get", "job", name,
            "-o", r'jsonpath={range .status.conditions[*]}{.type}={.status}{"\n"}{end}',
            capture=True, quiet=True, check=False,
        )
        for line in conditions.splitlines():
            if line.strip() in ("Complete=True", "Failed=True"):
                return line.strip()
        return None

    status = wait_until(finished, timeout, f"job/{name}")
    logs = kn("logs", f"job/{name}", capture=True, check=False)
    print(f"# job/{name} -> {status or 'dry-run'}")
    return logs


def k6_summary(logs):
    """The summary JSON out of the Job logs, split on the marker."""
    if SUMMARY_MARKER not in logs:
        return None
    return json.loads(logs.split(SUMMARY_MARKER, 1)[1])


# --- workload steps ----------------------------------------------------------

def k6_env(spec, mode, extra):
    env = {"TARGET_URL": spec["target_url"], "MODE": mode, "SLO_MS": spec["slo_ms"]}
    env.update(extra)
    return env


def k6_knee(spec, workload, cell, cell_dir):
    ladder = spec["ladder"]
    seconds = ladder["STAGE_SECONDS"] * (
        1 + (ladder["RATE_MAX"] - ladder["RATE_START"]) // ladder["RATE_STEP"]
    )
    logs = run_job(
        f"k6-{workload}-{cell}-knee",
        k6_job_yaml(f"k6-{workload}-{cell}-knee", spec["script"], k6_env(spec, "knee", ladder)),
        seconds + 300,
    )
    summary = k6_summary(logs)
    if summary is None:
        print(f"# (dry-run) assuming knee = RATE_START = {ladder['RATE_START']}")
        return {"unit": "rps", "knee": ladder["RATE_START"], "slo_ms": spec["slo_ms"], "series": []}
    series = knee.series_from_summary(summary)
    found = knee.find(series, spec["slo_ms"])
    result = {
        "unit": "rps",
        "knee": found,
        "slo_ms": spec["slo_ms"],
        "series": series,
        "invalid": knee.invalid_reasons(summary),
    }
    if not config.DRY_RUN:
        (cell_dir / "knee-raw.json").write_text(json.dumps(summary, indent=1))
    return result


def ycsb_job_yaml(name, spec, threads, target, operationcount, load=False):
    template = config.MANIFESTS / "workloads" / "mongo" / "base" / (
        "ycsb-load-job.yaml" if load else "ycsb-run-job.yaml"
    )
    if load:
        text = render(template, NAME=name)
    else:
        text = render(
            template, NAME=name, WORKLOAD=spec["workload_file"], THREADS=threads,
            TARGET=target, OPERATIONCOUNT=operationcount,
        )
    # recordcount is written into both Job templates, not passed in: the load and
    # the run MUST agree or the run reads a hot subset of the loaded collection
    # (manifests/base/README.md). Assert rather than trust.
    if f"recordcount={spec['recordcount']}" not in text:
        raise RuntimeError(
            f"{template.name} does not carry recordcount={spec['recordcount']}; "
            "the load and the run would disagree"
        )
    return text


def ycsb_knee(spec, cell, cell_dir):
    runs = []
    for threads in spec["threads"]:
        name = f"ycsb-run-{cell}-t{threads}-knee"
        logs = run_job(
            name,
            ycsb_job_yaml(name, spec, threads, 0, spec["knee_operationcount"]),
            spec["fixed_seconds"] + 900,
        )
        if logs and not config.DRY_RUN:
            (cell_dir / f"knee-t{threads}.txt").write_text(logs)
        if logs:
            runs.append((threads, logs))
    if not runs:
        print(f"# (dry-run) assuming knee = {spec['threads'][0]} threads")
        return {"unit": "threads", "knee": spec["threads"][0], "ops": 0,
                "slo_ms": spec["slo_ms"], "series": []}
    series = knee.series_from_ycsb(runs)
    found = knee.find(series, spec["slo_ms"])
    ops = 0
    for threads, logs in runs:
        if threads == found:
            ops = knee.parse_ycsb(logs)["READ"]["OPS"]
    return {"unit": "threads", "knee": found, "ops": ops, "slo_ms": spec["slo_ms"], "series": series}


def mongo_eval(js):
    return kn("exec", "statefulset/mongo", "--", "mongosh", "--quiet", "--eval", js,
              capture=True, check=False).strip()


def mongo_int(js):
    """One integer out of mongosh. Not every build prints a bare number for a
    long (some print Long("0")), and reading the count wrong here is the
    difference between measuring a 20M-record collection and an empty one."""
    m = re.search(r"\d+", mongo_eval(js))
    return int(m.group()) if m else None


def mongo_pages_read():
    return mongo_int('db.serverStatus().wiredTiger.cache["pages read into cache"]') or 0


def mongo_prepare(spec, cell, meta, date):
    """Load once per lab day, then warm the cache in every cell.

    The dataset survives between cells on purpose (the PVC reattaches), so the
    20M-record load runs only when the collection is empty; what every cell still
    has to pay is the warm-up, until 'pages read into cache' stops moving.
    """
    count = mongo_int('db.getSiblingDB("ycsb").usertable.estimatedDocumentCount()')
    meta["mongo_documents"] = count
    if count is None and not config.DRY_RUN:
        raise RuntimeError("could not read the ycsb collection count from mongosh")
    if config.DRY_RUN or count == 0:
        name = f"ycsb-load-{date}"
        run_job(name, ycsb_job_yaml(name, spec, None, None, None, load=True), 5400)

    meta["mongo_warmup"] = []
    for attempt in range(3):
        before = mongo_pages_read()
        name = f"ycsb-run-{cell}-warm{attempt}"
        run_job(
            name,
            ycsb_job_yaml(name, spec, 64, 0, spec["knee_operationcount"]),
            spec["warmup_seconds"] + 900,
        )
        delta = mongo_pages_read() - before
        meta["mongo_warmup"].append(delta)
        if config.DRY_RUN or delta < MONGO_WARM_PAGES:
            break


def iperf_run(cell, index, reverse):
    direction = "rev" if reverse else "fwd"
    name = f"iperf3-client-{cell}-{direction}-r{index}"
    template = config.MANIFESTS / "workloads" / "net" / "base" / (
        "iperf3-client-reverse-job.yaml" if reverse else "iperf3-client-job.yaml"
    )
    logs = run_job(name, render(template, NAME=name, CELL=config.node_cell(cell)), 300)
    return logs


# --- the cell ----------------------------------------------------------------

def run_cell(args):
    workload, cell = args.workload, args.cell
    spec = dict(config.WORKLOADS[workload])
    apply_overrides(spec, args)
    if cell not in spec["cells"]:
        raise SystemExit(f"{workload} has no cell {cell}; cells are {spec['cells']}")

    date = args.date or datetime.now(UTC).strftime("%Y-%m-%d")
    day_dir = config.RESULTS / date
    cell_dir = day_dir / workload / cell
    if not config.DRY_RUN:
        cell_dir.mkdir(parents=True, exist_ok=True)

    info = cluster_info(day_dir)
    mng = config.node_cell(cell)
    nodes_wanted = spec.get("nodes", 1)
    label = f"aad/cell={mng}"
    started = now()
    invalid = []

    print(f"\n=== {workload}/{cell} on node group {info['nodegroup_names'][mng]} "
          f"({config.instance_type(cell)} x{nodes_wanted}) ===\n")
    scale(info, mng, nodes_wanted)
    try:
        sut_nodes = wait_nodes(label, nodes_wanted, f"{mng}-node")
        sut = sut_nodes[0]
        loader = wait_nodes("aad/role=loader", 1, "loader-node")[0]

        if workload == "net":
            # The net knob is this workload's knob and nobody else's; in
            # manifests/base it would also retune the Java, Mongo and inference
            # tuned cells (manifests/base/README.md).
            kubectl("apply", "-f", str(config.MANIFESTS / "base" / "net-tuned-daemonset.yaml"))
            kn("rollout", "status", "daemonset/net-tuned", "--timeout=300s")

        kubectl("apply", "-k", overlay(workload, cell))
        kn("rollout", "status", spec["resource"], "--timeout=900s")

        meta = {}
        invalid += check_cpuset(spec, cell, meta)
        if invalid:
            raise RuntimeError(f"cell not comparable: {invalid}")

        if spec["loader"] == "k6":
            sync_k6_scripts()

        # --- warmup
        if workload == "mongo":
            mongo_prepare(spec, cell, meta, date)
        elif spec["loader"] == "k6" and spec["warmup_seconds"]:
            rate = spec.get("warmup_rate", spec.get("ladder", {}).get("RATE_START", 1))
            name = f"k6-{workload}-{cell}-warmup"
            run_job(
                name,
                k6_job_yaml(name, spec["script"], k6_env(spec, "fixed", {
                    "RATE": rate, "DURATION": f"{spec['warmup_seconds']}s", **args.env,
                })),
                spec["warmup_seconds"] + 300,
            )

        # --- knee
        knee_result = None
        if workload == "mongo":
            knee_result = ycsb_knee(spec, cell, cell_dir)
        elif spec.get("ladder"):
            with capture.TopSampler(sut, loader) as top:
                knee_result = k6_knee(spec, workload, cell, cell_dir)
            knee_result["loader_peak_percent"] = top.peak_loader_percent
            if top.peak_loader_percent > config.LOADER_CPU_GUARD_PERCENT:
                # A knee found while the generator itself is saturated is the
                # generator's knee, not the silicon's.
                knee_result["invalid"] = knee_result.get("invalid", []) + [
                    f"loader node CPU {top.peak_loader_percent}% > "
                    f"{config.LOADER_CPU_GUARD_PERCENT}% during the knee"
                ]
                raise RuntimeError(knee_result["invalid"][-1])
        if knee_result:
            if not config.DRY_RUN:
                (cell_dir / "knee.json").write_text(json.dumps(knee_result, indent=1))
            if knee_result["knee"] is None:
                raise RuntimeError(f"no knee: the first step already broke p99 < {spec['slo_ms']} ms")

        # --- measured runs
        for i in range(1, args.runs + 1):
            run_dir = cell_dir / f"run-{i}"
            if not config.DRY_RUN:
                run_dir.mkdir(parents=True, exist_ok=True)
            run_meta = dict(meta)
            print(f"\n--- run {i}/{args.runs} ---")
            # net runs both directions back to back, so the recording is twice as long
            aperf_seconds = spec["fixed_seconds"] * (2 if workload == "net" else 1)
            aperf = capture.aperf_start(sut, aperf_seconds, run_dir / "aperf")
            begin = now()
            with capture.TopSampler(sut, loader) as top:
                measure(spec, workload, cell, i, run_dir, run_meta, args)
            run_meta["loader_peak_percent"] = top.peak_loader_percent
            if not config.DRY_RUN:
                top.write(run_dir / "top.json")
            run_meta["aperf"] = capture.aperf_finish(aperf, timeout=aperf_seconds + 600)
            run_meta["flamegraph"] = capture.flamegraph(
                spec["service_name"], begin, now(), run_dir / "flamegraph.json"
            )
            if top.peak_loader_percent > config.LOADER_CPU_GUARD_PERCENT:
                run_meta.setdefault("invalid", []).append(
                    f"loader node CPU {top.peak_loader_percent}% > {config.LOADER_CPU_GUARD_PERCENT}%"
                )
            if not config.DRY_RUN:
                (run_dir / "meta.json").write_text(json.dumps(run_meta, indent=1))
    except Exception as exc:
        # An aborted cell still burned node minutes; the ledger has to see them.
        invalid.append(str(exc))
        raise
    finally:
        scale(info, mng, 0)
        if workload == "net":
            kubectl("delete", "-f", str(config.MANIFESTS / "base" / "net-tuned-daemonset.yaml"),
                    "--ignore-not-found")
        # The overlay goes, the Mongo volume stays: the dataset is reused by the
        # next cell of the same lab day (manifests/base/README.md).
        kubectl("delete", "-k", overlay(workload, cell), "--ignore-not-found")

        minutes = (now() - started) / 60
        if not config.DRY_RUN:
            (cell_dir / "cell.json").write_text(json.dumps({
                "date": date, "workload": workload, "cell": cell,
                "instance_type": config.instance_type(cell), "nodes": nodes_wanted,
                "minutes": round(minutes, 1), "runs": args.runs, "invalid": invalid,
            }, indent=1))
        print(f"\n# {workload}/{cell}: {minutes:.1f} min")
        write_ledger(day_dir)


def measure(spec, workload, cell, i, run_dir, run_meta, args):
    """One measured run at 80 % of the knee."""
    if workload == "net":
        for reverse, name in ((False, "iperf.json"), (True, "iperf-reverse.json")):
            logs = iperf_run(cell, i, reverse)
            if logs and not config.DRY_RUN:
                (run_dir / name).write_text(logs)
        return

    kneefile = run_dir.parent / "knee.json"
    kneed = json.loads(kneefile.read_text()) if kneefile.exists() else None

    if workload == "mongo":
        threads = kneed["knee"] if kneed else spec["threads"][0]
        target = int(0.8 * (kneed["ops"] if kneed else 0)) or 1
        name = f"ycsb-run-{cell}-t{threads}-r{i}"
        logs = run_job(
            name,
            ycsb_job_yaml(name, spec, threads, target, int(target * spec["fixed_seconds"])),
            spec["fixed_seconds"] + 900,
        )
        run_meta["threads"], run_meta["target_ops"] = threads, target
        if logs and not config.DRY_RUN:
            (run_dir / "ycsb.txt").write_text(logs)
        return

    name = f"k6-{workload}-{cell}-r{i}"
    if spec.get("ladder") is None:
        # Inference: closed loop against the server's own slots.
        env = k6_env(spec, "saturate", {
            "VUS": spec["saturate_vus"], "DURATION": f"{spec['fixed_seconds']}s", **args.env,
        })
        out_name = "llama.json"
    else:
        rate = int(0.8 * kneed["knee"]) if kneed else spec["ladder"]["RATE_START"]
        env = k6_env(spec, "fixed", {
            "RATE": rate, "DURATION": f"{spec['fixed_seconds']}s", **args.env,
        })
        run_meta["rate"] = rate
        out_name = "k6.json"
    logs = run_job(name, k6_job_yaml(name, spec["script"], env), spec["fixed_seconds"] + 300)
    summary = k6_summary(logs)
    if summary and not config.DRY_RUN:
        (run_dir / out_name).write_text(json.dumps(summary, indent=1))
        reasons = knee.invalid_reasons(summary)
        if reasons:
            run_meta.setdefault("invalid", []).extend(reasons)


def write_ledger(day_dir):
    try:
        text = cost.ledger(day_dir)
    except (RuntimeError, FileNotFoundError, KeyError) as exc:
        print(f"# no ledger yet: {exc}")
        return
    print("\n" + text)
    if not config.DRY_RUN:
        (day_dir / "ledger.md").write_text(text)


def teardown_day():
    """End of the lab day, before the human runs `terraform destroy`.

    The EBS volume behind the Mongo PVC was provisioned by the CSI driver, is not
    in Terraform state, and `terraform destroy` never sees it (infra/README.md).
    """
    kn("delete", "sts", "mongo", "--ignore-not-found")
    kn("delete", "pvc", "--all")
    sh(["aws", "ec2", "describe-volumes",
        "--filters", "Name=tag:Project,Values=armed-and-dangerous",
        "--query", "Volumes[].VolumeId"])
    print("\n# the list above must be [] BEFORE `terraform destroy`, which a human runs:")
    print("#   cd infra && terraform destroy")
    print("#   aws ec2 describe-instances --filters Name=tag:Project,Values=armed-and-dangerous "
          "Name=instance-state-name,Values=running --query 'Reservations[].Instances[].InstanceId'")


# --- cli ---------------------------------------------------------------------

def apply_overrides(spec, args):
    for key in ("slo_ms", "fixed_seconds", "warmup_seconds"):
        if getattr(args, key) is not None:
            spec[key] = getattr(args, key)
    if args.threads:
        spec["threads"] = args.threads
    if spec.get("ladder"):
        spec["ladder"] = dict(spec["ladder"])
        for flag, key in (("rate_start", "RATE_START"), ("rate_step", "RATE_STEP"),
                          ("rate_max", "RATE_MAX"), ("stage_seconds", "STAGE_SECONDS")):
            if getattr(args, flag) is not None:
                spec["ladder"][key] = getattr(args, flag)


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="cell", description=__doc__.splitlines()[0])
    p.add_argument("--workload", choices=sorted(config.WORKLOADS))
    p.add_argument("--cell", choices=sorted(config.CELL_MNG))
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--date", help="results/<date>/ to write into (default: today, UTC)")
    p.add_argument("--dry-run", action="store_true", help="print the command plan and touch nothing")
    p.add_argument("--teardown-day", action="store_true", help="drop the Mongo dataset before terraform destroy")
    p.add_argument("--slo-ms", type=float, dest="slo_ms")
    p.add_argument("--fixed-seconds", type=int, dest="fixed_seconds")
    p.add_argument("--warmup-seconds", type=int, dest="warmup_seconds")
    p.add_argument("--rate-start", type=int, dest="rate_start")
    p.add_argument("--rate-step", type=int, dest="rate_step")
    p.add_argument("--rate-max", type=int, dest="rate_max")
    p.add_argument("--stage-seconds", type=int, dest="stage_seconds")
    p.add_argument("--threads", type=int, nargs="+", help="YCSB thread ladder")
    p.add_argument("--env", action="append", default=[], metavar="K=V",
                   help="extra env for the k6 Job (repeatable)")
    args = p.parse_args(argv)
    args.env = dict(kv.split("=", 1) for kv in args.env)
    if not args.teardown_day and not (args.workload and args.cell):
        p.error("--workload and --cell are required (or --teardown-day)")
    return args


def main(argv=None):
    args = parse_args(argv)
    config.DRY_RUN = args.dry_run
    config.require_sandbox()  # first thing that runs, dry run included
    if args.teardown_day:
        teardown_day()
        return 0
    run_cell(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
