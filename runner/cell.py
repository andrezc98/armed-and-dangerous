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
import os
import re
import sys
import tempfile
import time
from datetime import datetime
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
NODE_GONE_TIMEOUT = 600  # the cell is billed until the instance actually goes away
SCALE_DOWN_RETRIES = 3
SCALE_DOWN_BACKOFF = 10
JOB_DELETE_TIMEOUT = 60

# The own images are written into the manifests by bare name and a sentinel tag
# (`aad-java:UNSET`), so nothing in git carries the sandbox account id. The
# registry and the tag only exist at render time: the registry comes from
# results/<date>/ecr.json (git-ignored, it has the account id in it) and the tag
# from results/images.json (committed, written by the gated push). Reaching the
# cluster with the sentinel still on costs the fifteen paid minutes an
# ImagePullBackOff takes to become obvious.
UNSET_TAG = "UNSET"
OWN_IMAGES = ("aad-java", "aad-go", "aad-iperf3", "aad-ycsb")
IMAGES = {}  # {"registry": ..., "tag": ...}, filled once per run by load_images()
_UNSET_IMAGE = re.compile(rf"({'|'.join(OWN_IMAGES)}):{UNSET_TAG}")

# The throwaway kustomization the runner renders every overlay through: the
# overlays name their images bare, this is what puts the registry back.
# `resources` is a RELATIVE path on purpose - kustomize refuses an absolute one
# ("new root ... cannot be absolute", kustomize v5.6.0 in kubectl 1.33.9).
OVERLAY_KUSTOMIZATION = """resources:
  - {overlay}
images:
{images}
"""

# The Job templates the runner renders itself, per workload: they are not part of
# any kustomization, so `kubectl kustomize` does not see their image tags.
JOB_TEMPLATES = {
    "mongo": ("workloads/mongo/base/ycsb-load-job.yaml",
              "workloads/mongo/base/ycsb-run-job.yaml"),
    "net": ("workloads/net/base/iperf3-client-job.yaml",
            "workloads/net/base/iperf3-client-reverse-job.yaml"),
}

# What to try when the loader, and not the silicon, is what the knee measured.
KNEE_REMEDY = ("raise the VU budget (--env PREALLOC_VUS=... --env MAX_VUS=...) or "
               "give the loader node group a bigger instance, then run the cell again")

# Rendered per run: a Job's pod template is immutable, so the name carries the
# repetition. The k6 scripts arrive through a ConfigMap built from runner/k6/.
# The aad/cell label on the Job (not only on the pod) is what lets the cell drop
# every Job it created when it ends.
K6_JOB = """apiVersion: batch/v1
kind: Job
metadata:
  name: {name}
  namespace: {ns}
  labels:
    aad/cell: {cell}
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
    # millisecond, and not after a node group has been paid for. safe_load_all
    # and not safe_load, because a rendered overlay is a multi-document stream;
    # it is a generator, so the list() is what actually parses.
    list(yaml.safe_load_all(yaml_text))
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

CLUSTER_JSON_HELP = (
    "The runner never runs terraform. A human writes this file once per lab day, "
    "right after the apply (infra/README.md):\n"
    "    terraform -chdir=infra output -json > results/<date>/cluster.json"
)
ECR_JSON_HELP = (
    "The runner never runs terraform. A human writes this file once per lab day, "
    "right after the apply (infra/ecr/README.md):\n"
    "    terraform -chdir=infra/ecr output -json > results/<date>/ecr.json"
)
IMAGES_JSON_HELP = (
    "results/images.json is written by the gated push and committed:\n"
    "    AWS_PROFILE=<sandbox> PUSH=1 apps/build-multiarch.sh\n"
    "Pass --image-tag <tag> to point this cell at another tag that is in ECR."
)
FIXTURE_CLUSTER = config.RUNNER / "tests" / "fixtures" / "cluster.json"
FIXTURE_ECR = config.RUNNER / "tests" / "fixtures" / "ecr.json"
FIXTURE_IMAGES = config.RUNNER / "tests" / "fixtures" / "images.json"


def read_json(path, fixture, help_text):
    """One of the files a human leaves for the runner. Missing is fatal, except
    under --dry-run, where the fixture stands in so the plan is readable without
    a cluster (and says so)."""
    if not path.exists() and config.DRY_RUN:
        print(f"# {path} not found; --dry-run reads the fixture {fixture}")
        path = fixture
    if not path.exists():
        raise SystemExit(f"{path} is missing.\n{help_text}")
    return json.loads(path.read_text())


def unwrap(raw):
    """`terraform output -json` wraps every value in {"value": ..., "type": ...}."""
    return {k: (v["value"] if isinstance(v, dict) and "value" in v else v) for k, v in raw.items()}


def cluster_info(day_dir):
    """Cluster and node group names, read from results/<date>/cluster.json.

    That file is `terraform output -json` redirected by the person who ran the
    apply, so its values arrive wrapped in {"value": ...} and are unwrapped here.
    Nothing in this runner shells out to terraform: an orchestrator that can
    apply infrastructure is an orchestrator that can apply it by accident.
    """
    path = day_dir / "cluster.json"
    info = unwrap(read_json(path, FIXTURE_CLUSTER, CLUSTER_JSON_HELP))
    missing = [k for k in ("cluster_name", "nodegroup_names") if not info.get(k)]
    if missing:
        raise SystemExit(f"{path} has no {', '.join(missing)}.\n{CLUSTER_JSON_HELP}")
    return info


def load_images(day_dir, override_tag=None):
    """Where the own images live today: registry from ECR, tag from the push.

    Two files because they have two lifetimes and two secrecy levels. The
    registry is `<account>.dkr.ecr.<region>.amazonaws.com`, so it carries the
    sandbox account id and its file is git-ignored; it is written once per lab
    day from `terraform -chdir=infra/ecr output -json`. The tag is whatever the
    last gated push produced, it is the same for every lab day until the next
    push, and results/images.json has no account data in it, so that one IS
    committed.
    """
    path = day_dir / "ecr.json"
    registry = unwrap(read_json(path, FIXTURE_ECR, ECR_JSON_HELP)).get("registry")
    if not registry:
        raise SystemExit(f"{path} has no registry.\n{ECR_JSON_HELP}")

    tag = override_tag
    if not tag:
        images_path = config.RESULTS / "images.json"
        tag = read_json(images_path, FIXTURE_IMAGES, IMAGES_JSON_HELP).get("tag")
        if not tag:
            raise SystemExit(f"{images_path} has no tag.\n{IMAGES_JSON_HELP}")

    IMAGES.update(registry=registry, tag=tag)
    print(f"# own images: {registry}/<name>:{tag}")
    return IMAGES


def image_ref(name):
    if not IMAGES:
        raise RuntimeError(
            f"{name} has no registry yet: load_images() has to run before anything renders"
        )
    return f"{IMAGES['registry']}/{name}:{IMAGES['tag']}"


def rewrite_images(text):
    """Put the registry and the tag back on the own images of a manifest.

    The manifests name them bare with a sentinel tag so that git never carries an
    account id; this is the one place that undoes that, for the Job templates the
    runner renders itself. Overlays go through kustomize_overlay() instead.
    """
    return _UNSET_IMAGE.sub(lambda m: image_ref(m.group(1)), text)


def scale(info, mng, size):
    sh([
        "aws", "eks", "update-nodegroup-config",
        "--cluster-name", info["cluster_name"],
        "--nodegroup-name", info["nodegroup_names"][mng],
        "--scaling-config", f"desiredSize={size}",
    ])


def scale_to_zero(info, mng, label):
    """The one step that must happen even when everything else failed.

    Retried, because a transient API error here leaves a 4xlarge running until
    somebody notices; then waited out, because the cell is billed until the node
    is actually gone and the ledger's minutes have to say so.
    """
    for attempt in range(1, SCALE_DOWN_RETRIES + 1):
        try:
            scale(info, mng, 0)
            break
        except Exception as exc:
            print(f"# scale to 0 failed ({exc}); attempt {attempt}/{SCALE_DOWN_RETRIES}")
            if attempt == SCALE_DOWN_RETRIES:
                print(f"# WARNING: {mng} may still be running. Check it by hand:\n"
                      f"#   aws eks describe-nodegroup --cluster-name {info['cluster_name']} "
                      f"--nodegroup-name {info['nodegroup_names'][mng]}")
                return
            time.sleep(SCALE_DOWN_BACKOFF)
    try:
        wait_until(lambda: not labelled_nodes(label), NODE_GONE_TIMEOUT, f"no node with {label}")
    except RuntimeError as exc:
        print(f"# WARNING: {exc}; check `aws ec2 describe-instances` by hand")


def labelled_nodes(label):
    out = kubectl("get", "nodes", "-l", label, "--no-headers", capture=True, quiet=True, check=False)
    return [line.split() for line in out.splitlines() if line.split()]


def ready_nodes(label):
    return [fields[0] for fields in labelled_nodes(label) if fields[1:2] == ["Ready"]]


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


def kustomize_overlay(workload, cell):
    """The overlay rendered with the own images pointed at the sandbox ECR.

    The overlays name their images bare (`aad-java:UNSET`) so that nothing in git
    carries the account id. kustomize's images transformer is what puts the
    registry and the tag back: "newName - Override the image name for images
    whose image name matches name", "newTag - Override the image tag or digest"
    (https://kubectl.docs.kubernetes.io/references/kustomize/kustomization/images/).
    It runs from a throwaway kustomization in a temp dir, so the repo stays free
    of the account id even while a cell is running.

    An entry the overlay does not use costs nothing: an images entry that matches
    no image is simply not applied, which is why all four go in every time.
    """
    images = "\n".join(
        f"  - name: {name}\n"
        f"    newName: {IMAGES['registry']}/{name}\n"
        f"    newTag: {IMAGES['tag']}"
        for name in OWN_IMAGES
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()  # /var -> /private/var on macOS; relpath is lexical
        rel = os.path.relpath(Path(overlay(workload, cell)).resolve(), root)
        (root / "kustomization.yaml").write_text(
            OVERLAY_KUSTOMIZATION.format(overlay=rel, images=images)
        )
        print(f"# kustomize overlay {workload}/{cell} with the own images of the day")
        return kubectl("kustomize", str(root), capture=True, quiet=True)


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

    Two ways to read it, because one of the images has no shell:

    - `cat /sys/fs/cgroup/cpuset.cpus.effective` through `kubectl exec`, for
      every workload whose image can run a `cat`;
    - for the distroless Go server, its own /healthz through the API server
      service proxy: `runtime.NumCPU()` "returns the number of logical CPUs
      usable by the current process", i.e. it honours the affinity mask
      (https://pkg.go.dev/runtime#NumCPU). The proxy URL form is the documented
      one - `.../services/<name>:<port>/proxy` "proxies to the specified port
      name or port number using http"
      (https://kubernetes.io/docs/tasks/access-application-cluster/access-cluster-services/).

    Either way, silence is not a pass. An empty answer used to leave the control
    unevaluated and the cell went on to measure something incomparable.
    """
    expected = config.exclusive_cpus(cell)
    if spec.get("cpus_proxy"):
        where = f"/api/v1/namespaces/{config.NAMESPACE}/services/{spec['cpus_proxy']}/proxy/healthz"
        body = kubectl("get", "--raw", where, capture=True, check=False).strip()
        meta["cpuset"] = body or "<dry-run>"
        if not body:
            return [] if config.DRY_RUN else [f"cpuset_unreadable: GET {where} answered nothing"]
        count = json.loads(body)["cpus"]
    else:
        where = f"{spec['resource']} cpuset.cpus.effective"
        cpuset = kn("exec", spec["resource"], "--", "cat", "/sys/fs/cgroup/cpuset.cpus.effective",
                    capture=True, check=False).strip()
        meta["cpuset"] = cpuset or "<dry-run>"
        if not cpuset:
            return [] if config.DRY_RUN else [f"cpuset_unreadable: {where} answered nothing"]
        count = cpuset_size(cpuset)
    meta["cpuset_count"] = count
    if count != expected:
        return [f"{where} is {count} vCPUs, expected {expected} exclusive"]
    return []


# --- jobs --------------------------------------------------------------------

_PLACEHOLDER = re.compile(r"__[A-Z][A-Z_]*__")


def render(template_path, **subs):
    """Fill a manifests/ Job template. Every __PLACEHOLDER__ must be known here:
    a template that grows one the runner does not pass would otherwise be applied
    with the literal text in it.

    The own image of the template gets its registry and tag in the same pass:
    these templates are not part of any kustomization, so no images transformer
    ever sees them.
    """
    text = Path(template_path).read_text()
    for key, value in subs.items():
        text = text.replace(f"__{key}__", str(value))
    text = rewrite_images(text)
    left = set(_PLACEHOLDER.findall(text))
    if left:
        raise RuntimeError(f"{Path(template_path).name} still has {sorted(left)}")
    return text


def k6_job_yaml(name, cell, script, env):
    # json.dumps and not an f-string quote: a value with a quote, a backslash or
    # a leading '*' in it would otherwise render YAML that either fails to parse
    # or, worse, parses into something else. JSON scalars are valid YAML scalars.
    body = "\n".join(
        f'            - name: {k}\n              value: {json.dumps(str(v))}' for k, v in env.items()
    )
    return K6_JOB.format(
        name=name, ns=config.NAMESPACE, cell=cell, image=K6_IMAGE, script=script,
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
    # `delete` returns before the object is gone, and a Job's pod template is
    # immutable, so re-applying the same name races the old one's finalizer.
    # `--for=delete` is the documented way to wait for that
    # (https://kubernetes.io/docs/reference/kubectl/generated/kubectl_wait/:
    # "Wait for the pod "busybox1" to be deleted, with a timeout of 60s, after
    # having issued the "delete" command"). It errors when the Job never
    # existed, which is the common case, hence check=False.
    kn("wait", "--for=delete", f"job/{name}", f"--timeout={JOB_DELETE_TIMEOUT}s", check=False)
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


def job_failure(name):
    """Everything a human needs to see about a Job that produced no output.

    A Job with no logs is an ImagePullBackOff, an unschedulable pod or an OOM
    kill, and every one of those is invisible in the summary the runner was
    waiting for. `kubectl logs` writes the reason to stderr, so that is captured
    too instead of coming back as an empty string.
    """
    errors = []
    kn("logs", f"job/{name}", capture=True, check=False, stderr=errors)
    parts = [
        kn("describe", "job", name, capture=True, check=False),
        kn("describe", "pod", "-l", f"job-name={name}", capture=True, check=False),
        "".join(errors).strip(),
    ]
    return "\n".join(p for p in parts if p.strip())


def k6_summary(logs):
    """The summary JSON out of the Job logs, split on the marker.

    None for "there is no summary here", which includes a marker with nothing
    after it: k6 died before handleSummary wrote the file, `cat` printed
    nothing, and the caller's job_failure() path is the one that explains it.
    Parsing an empty string would raise a JSONDecodeError instead.
    """
    if SUMMARY_MARKER not in logs:
        return None
    body = logs.split(SUMMARY_MARKER, 1)[1].strip()
    return json.loads(body) if body else None


# --- workload steps ----------------------------------------------------------

def k6_env(spec, mode, extra):
    env = {"TARGET_URL": spec["target_url"], "MODE": mode, "SLO_MS": spec["slo_ms"]}
    env.update(extra)
    return env


LADDER_REMEDY = ("raise the top of the ladder (--rate-max, or --threads for mongo) "
                 "and run the cell again")


def uncrossed(found, last, unit):
    """The reason a ladder that never broke the SLO is not a knee.

    The top step passing means the ladder stopped before the system did: 80 % of
    it is 80 % of a rate the silicon was still comfortable at, and the cells get
    compared on the ceiling of the generator's script instead of on their own.
    """
    if found is None or found != last:
        return []
    return [f"ladder_never_crossed: the top step ({found} {unit}) still met the SLO; "
            f"{LADDER_REMEDY}"]


def k6_knee(spec, workload, cell, cell_dir, env_extra):
    ladder = spec["ladder"]
    name = f"k6-{workload}-{cell}-knee"
    # --env reaches the ladder too: a knee run that ignores the VU budget the
    # human just raised is the run that made them raise it. The merged dict is
    # also what the summary is judged against, so an overridden STAGE_SECONDS
    # moves the runner's expectation and not only k6's.
    env = {**ladder, **env_extra}
    stage_seconds, ramp_seconds = int(env["STAGE_SECONDS"]), int(env.get("RAMP_SECONDS", 5))
    rates = knee.ladder_rates({k: int(env[k]) for k in ("RATE_START", "RATE_STEP", "RATE_MAX")})
    logs = run_job(
        name,
        k6_job_yaml(name, cell, spec["script"], k6_env(spec, "knee", env)),
        stage_seconds * len(rates) + 300,
    )
    summary = k6_summary(logs)
    if summary is None:
        # Only a dry run gets to invent a knee. On the cluster, a ladder that
        # printed no summary is a failure, and assuming RATE_START would put a
        # made-up number on the slide.
        if not config.DRY_RUN:
            raise RuntimeError(
                f"job/{name} produced no {SUMMARY_MARKER} block:\n{job_failure(name)}"
            )
        print(f"# (dry-run) assuming knee = RATE_START = {rates[0]}")
        return {"unit": "rps", "knee": rates[0], "slo_ms": spec["slo_ms"],
                "series": [], "invalid": []}
    series = knee.series_from_summary(summary)
    steps = knee.step_reasons(summary, stage_seconds, ramp_seconds)
    found = knee.find(series, spec["slo_ms"], steps)
    invalid = uncrossed(found, rates[-1], "rps")
    if found is None and series and series[0][0] in steps:
        invalid.append(f"ladder_first_step_invalid: {series[0][0]} rps {steps[series[0][0]]}")
    result = {
        "unit": "rps",
        "knee": found,
        "slo_ms": spec["slo_ms"],
        "series": series,
        # Only the steps at or below the knee matter; past it the ladder is
        # supposed to break (runner/knee.py).
        "invalid_steps": {r: why for r, why in sorted(steps.items())
                          if found is None or r <= found},
        "invalid": invalid,
    }
    if not config.DRY_RUN:
        (cell_dir / "knee-raw.json").write_text(json.dumps(summary, indent=1))
    return result


def check_knee(result, slo_ms):
    """A knee the cell may not measure at is a knee the cell must not measure at.

    Three ways a ladder fails to produce one: the generator was the bottleneck
    (the loader guard, or a step that never delivered the load it offered), the
    first step already broke the SLO, or no step ever did and the knee is just
    the top of the ladder.
    """
    if result.get("invalid"):
        raise RuntimeError(f"knee not usable: {'; '.join(result['invalid'])}. {KNEE_REMEDY}")
    if result["knee"] is None:
        raise RuntimeError(
            f"no knee: the first step already broke p99 < {slo_ms} ms. {KNEE_REMEDY}"
        )


def ycsb_job_yaml(name, cell, spec, threads, target, operationcount, load=False):
    template = config.MANIFESTS / "workloads" / "mongo" / "base" / (
        "ycsb-load-job.yaml" if load else "ycsb-run-job.yaml"
    )
    if load:
        # The load is the day's, not the cell's: it runs once, when the
        # collection is empty, and every later cell of the day reuses it.
        text = render(template, NAME=name)
    else:
        text = render(
            template, NAME=name, CELL=cell, WORKLOAD=spec["workload_file"], THREADS=threads,
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
            ycsb_job_yaml(name, cell, spec, threads, 0, spec["knee_operationcount"]),
            spec["fixed_seconds"] + 900,
        )
        if config.DRY_RUN:
            continue
        # One broken step invalidates the ladder: the steps after it are measured
        # against a cache and a client the failed step already disturbed. Both
        # lines are needed: READ carries the p99 the SLO is about, TOTAL the
        # throughput the fixed runs are throttled to.
        parsed = knee.parse_ycsb(logs) if logs else {}
        missing = [line for line in ("READ", "TOTAL") if line not in parsed]
        if missing:
            raise RuntimeError(
                f"job/{name} printed no {'/'.join(missing)} line:\n{job_failure(name)}"
            )
        (cell_dir / f"knee-t{threads}.txt").write_text(logs)
        runs.append((threads, logs))
    if not runs:
        print(f"# (dry-run) assuming knee = {spec['threads'][0]} threads")
        return {"unit": "threads", "knee": spec["threads"][0], "ops": 0,
                "slo_ms": spec["slo_ms"], "series": [], "invalid": []}
    series = knee.series_from_ycsb(runs)
    found = knee.find(series, spec["slo_ms"])
    ops = 0
    for threads, logs in runs:
        if threads == found:
            # TOTAL and not READ: `--target` throttles every operation, and
            # workloadb is 95/5, so pinning the run to the READ rate would ask
            # for 5 % less load than the knee actually carried.
            ops = knee.parse_ycsb(logs)["TOTAL"]["OPS"]
    return {"unit": "threads", "knee": found, "ops": ops, "slo_ms": spec["slo_ms"],
            "series": series, "invalid": uncrossed(found, spec["threads"][-1], "threads")}


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


MONGO_DROP = 'db.getSiblingDB("ycsb").usertable.drop()'
MONGO_COUNT = 'db.getSiblingDB("ycsb").usertable.estimatedDocumentCount()'


def mongo_prepare(spec, cell, meta, date, reload=False):
    """Load once per lab day, then warm the cache in every cell.

    The dataset survives between cells on purpose (the PVC reattaches), so the
    20M-record load runs only when the collection is empty; what every cell still
    has to pay is the warm-up, until 'pages read into cache' stops moving.

    Empty or complete, nothing in between. A load that was killed halfway leaves
    a collection that answers every read and is a different benchmark from the
    one the other cells ran, and the warm-up control would look perfectly flat
    while it happened. (estimatedDocumentCount reads the collection metadata, so
    it is exact except after an unclean shutdown - which is itself a reason to
    reload rather than to measure.)
    """
    count = mongo_int(MONGO_COUNT)
    meta["mongo_documents"] = count
    if count is None and not config.DRY_RUN:
        raise RuntimeError("could not read the ycsb collection count from mongosh")
    if reload and not config.DRY_RUN:
        print(f"# --reload: dropping the {count} document(s) already in ycsb.usertable")
        mongo_eval(MONGO_DROP)
        count = 0
    if config.DRY_RUN or count == 0:
        name = f"ycsb-load-{date}"
        run_job(name, ycsb_job_yaml(name, cell, spec, None, None, None, load=True), 5400)
    elif count != spec["recordcount"]:
        raise RuntimeError(
            f"partial_dataset: ycsb.usertable holds {count} documents, not the "
            f"{spec['recordcount']} both YCSB Jobs are written for. Drop it and let the "
            f"cell load it again:\n"
            f"    kubectl -n {config.NAMESPACE} exec statefulset/mongo -- "
            f"mongosh --quiet --eval '{MONGO_DROP}'\n"
            f"  or pass --reload."
        )

    # Warm until two consecutive samples stop moving, not for a fixed number of
    # passes: a cold 40 GiB WiredTiger cache does not care how many times it was
    # asked. The wall clock is the only bound, and hitting it means the run would
    # measure EBS instead of memory.
    meta["mongo_warmup"] = []
    deadline = now() + spec["warm_max_min"] * 60
    attempt = 0
    while True:
        before = mongo_pages_read()
        name = f"ycsb-run-{cell}-warm{attempt}"
        run_job(
            name,
            ycsb_job_yaml(name, cell, spec, 64, 0, spec["knee_operationcount"]),
            spec["warmup_seconds"] + 900,
        )
        delta = mongo_pages_read() - before
        meta["mongo_warmup"].append(delta)
        if config.DRY_RUN or delta < spec["warm_pages"]:
            return
        attempt += 1
        if now() > deadline:
            raise RuntimeError(
                f"cache_not_warm: 'pages read into cache' still climbing by {delta} per pass "
                f"after {spec['warm_max_min']} min; this cell would measure EBS, not memory"
            )


def iperf_run(cell, index, reverse):
    direction = "rev" if reverse else "fwd"
    name = f"iperf3-client-{cell}-{direction}-r{index}"
    template = config.MANIFESTS / "workloads" / "net" / "base" / (
        "iperf3-client-reverse-job.yaml" if reverse else "iperf3-client-job.yaml"
    )
    return name, run_job(name, render(template, NAME=name, CELL=config.node_cell(cell)), 300)


def server_node(sut_nodes):
    """The node the iperf3 server actually landed on (`.spec.nodeName`).

    Both net pods carry an anti-affinity, so the pair is guaranteed to be split
    across the two cell nodes; which one holds the server is not.
    """
    node = kn("get", "pod", "-l", "app=iperf3-server",
              "-o", "jsonpath={.items[0].spec.nodeName}", capture=True, check=False).strip()
    if node:
        return node
    if not config.DRY_RUN:
        raise RuntimeError("the iperf3-server pod reports no spec.nodeName")
    return sut_nodes[0]


# --- the cell ----------------------------------------------------------------

def budget_gate(day_dir, override, cost_md=cost.COST_MD):
    """No node group goes up before the day's money is on the table.

    A dry run is let through: printing the plan is how a human reads what a cell
    would cost before the rates for the day exist at all.
    """
    if config.DRY_RUN:
        return
    try:
        spent, estimate = cost.day_total(day_dir, cost_md)
    except (RuntimeError, FileNotFoundError, KeyError) as exc:
        raise SystemExit(
            f"budget gate: {exc}\nFill {cost.COST_MD} with the rates of the day before "
            "scaling a node group up."
        ) from None
    if spent > estimate and not override:
        raise SystemExit(
            f"budget gate: {day_dir.name} has already committed USD {spent:.2f} against an "
            f"estimate_per_day_usd of {estimate:.2f}. Read {day_dir}/ledger.md and stop, or "
            "pass --override-budget if this extra cell is deliberate."
        )
    print(f"# budget: USD {spent:.2f} committed today, estimate {estimate:.2f}")


def check_images(workload, cell):
    """No cell starts while anything still says :UNSET.

    The sentinel tag is what the manifests carry in git; load_images() and the
    two renderers are what replace it. One that survives reaches the cluster as
    an ImagePullBackOff, which is fifteen minutes of a paid 4xlarge before anyone
    reads it. Rendering the overlay and the workload's Job templates here costs a
    second.
    """
    texts = {f"overlay {workload}/{cell}": kustomize_overlay(workload, cell)}
    for rel in JOB_TEMPLATES.get(workload, ()):
        texts[rel] = rewrite_images((config.MANIFESTS / rel).read_text())
    left = sorted(what for what, text in texts.items() if f":{UNSET_TAG}" in text)
    if not left:
        return
    message = (f":{UNSET_TAG} is still the image tag in {', '.join(left)}. Every own image is "
               f"one of {', '.join(OWN_IMAGES)} and gets its registry and tag from "
               "results/<date>/ecr.json and results/images.json (runner/README.md); an image "
               "the renderer does not know about has to be added to OWN_IMAGES.")
    if config.DRY_RUN:
        print(f"# (dry-run) this check would stop the cell: {message}")
        return
    raise SystemExit(message)


def run_cell(args):
    workload, cell = args.workload, args.cell
    spec = dict(config.WORKLOADS[workload])
    apply_overrides(spec, args)
    if cell not in spec["cells"]:
        raise SystemExit(f"{workload} has no cell {cell}; cells are {spec['cells']}")

    # The LOCAL date, not UTC: a lab day that runs into the evening in Lima or
    # Buenos Aires would otherwise roll into tomorrow's directory at 19:00 and
    # split one day's ledger, and its budget gate, in two.
    date = args.date or datetime.now().astimezone().date().isoformat()
    day_dir = config.RESULTS / date
    cell_dir = day_dir / workload / cell
    if not config.DRY_RUN:
        cell_dir.mkdir(parents=True, exist_ok=True)

    info = cluster_info(day_dir)
    load_images(day_dir, args.image_tag)
    mng = config.node_cell(cell)
    nodes_wanted = spec.get("nodes", 1)
    label = f"aad/cell={mng}"
    invalid = []

    print(f"\n=== {date}  {workload}/{cell} on node group {info['nodegroup_names'][mng]} "
          f"({config.instance_type(cell)} x{nodes_wanted}) ===\n")
    budget_gate(day_dir, args.override_budget)
    check_images(workload, cell)

    # From here on the money is running, so everything is inside the try: the
    # scale-up included, because a scale-up that half succeeded still bills.
    started = now()
    try:
        scale(info, mng, nodes_wanted)
        sut_nodes = wait_nodes(label, nodes_wanted, f"{mng}-node")
        sut = sut_nodes[0]
        loader = wait_nodes("aad/role=loader", 1, "loader-node")[0]

        if workload == "net":
            # The net knob is this workload's knob and nobody else's; in
            # manifests/base it would also retune the Java, Mongo and inference
            # tuned cells (manifests/base/README.md).
            kubectl("apply", "-f", str(config.MANIFESTS / "base" / "net-tuned-daemonset.yaml"))
            kn("rollout", "status", "daemonset/net-tuned", "--timeout=300s")

        # Not `apply -k`: the overlay only becomes appliable once the images
        # transformer has run over it (kustomize_overlay).
        apply_stdin(kustomize_overlay(workload, cell), f"overlay {workload}/{cell}")
        kn("rollout", "status", spec["resource"], "--timeout=900s")

        if workload == "net":
            # Which of the two cell nodes carries the server is the scheduler's
            # decision, and the server is the SUT: APerf and the CPU medians have
            # to follow it rather than whichever node came up first.
            sut = server_node(sut_nodes)

        meta = {}
        invalid += check_cpuset(spec, cell, meta)
        if invalid:
            raise RuntimeError(f"cell not comparable: {invalid}")

        if spec["loader"] == "k6":
            sync_k6_scripts()

        # --- warmup: the same shape as the measurement, so what gets warm is
        # what gets measured. Inference has no ladder, so it warms closed-loop on
        # the server's slots exactly as it will be measured; the others hold the
        # first rate of their ladder.
        if workload == "mongo":
            mongo_prepare(spec, cell, meta, date, reload=args.reload)
        elif spec["loader"] == "k6" and spec["warmup_seconds"]:
            duration = f"{spec['warmup_seconds']}s"
            if spec.get("ladder") is None:
                mode, load = "saturate", {"VUS": spec["saturate_vus"], "DURATION": duration}
            else:
                mode, load = "fixed", {"RATE": spec["ladder"]["RATE_START"], "DURATION": duration}
            name = f"k6-{workload}-{cell}-warmup"
            run_job(
                name,
                k6_job_yaml(name, cell, spec["script"],
                            k6_env(spec, mode, {**load, **args.env})),
                spec["warmup_seconds"] + 300,
            )

        # --- knee, with the loader guard around it in both loaders: a knee found
        # while the generator is saturated is the generator's knee, not the
        # silicon's, and go-ycsb saturates a client as happily as k6 does.
        if workload == "mongo" or spec.get("ladder"):
            with capture.TopSampler(sut_nodes, loader, sut=sut) as top:
                knee_result = (
                    ycsb_knee(spec, cell, cell_dir) if workload == "mongo"
                    else k6_knee(spec, workload, cell, cell_dir, args.env)
                )
            knee_result["loader_peak_percent"] = top.peak_loader_percent
            if top.peak_loader_percent > config.LOADER_CPU_GUARD_PERCENT:
                knee_result["invalid"].append(
                    f"loader node CPU {top.peak_loader_percent}% > "
                    f"{config.LOADER_CPU_GUARD_PERCENT}% during the knee"
                )
            if not config.DRY_RUN:
                (cell_dir / "knee.json").write_text(json.dumps(knee_result, indent=1))
            check_knee(knee_result, spec["slo_ms"])  # after the file: the record survives

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
            try:
                with capture.TopSampler(sut_nodes, loader, sut=sut) as top:
                    measure(spec, workload, cell, i, run_dir, run_meta, args)
                run_meta["loader_peak_percent"] = top.peak_loader_percent
                if not config.DRY_RUN:
                    top.write(run_dir / "top.json")
                # For net the generator is the second SUT node, not the loader, so
                # the guard has nothing to say about this run.
                if workload != "net" and top.peak_loader_percent > config.LOADER_CPU_GUARD_PERCENT:
                    run_meta.setdefault("invalid", []).append(
                        f"loader node CPU {top.peak_loader_percent}% > "
                        f"{config.LOADER_CPU_GUARD_PERCENT}%"
                    )
            finally:
                # The recorder outlives the load Job. If the run blew up it is
                # still holding a privileged pod on the SUT, and the next cell
                # would measure with it running.
                run_meta["aperf"] = capture.aperf_finish(aperf, timeout=aperf_seconds + 600)
            run_meta["flamegraph"] = capture.flamegraph(
                spec["service_name"], begin, now(), run_dir / "flamegraph.json"
            )
            if not config.DRY_RUN:
                (run_dir / "meta.json").write_text(json.dumps(run_meta, indent=1))
    except Exception as exc:
        # An aborted cell still burned node minutes; the ledger has to see them.
        invalid.append(str(exc))
        raise
    finally:
        scale_to_zero(info, mng, label)
        # The Jobs this cell created. They are Complete or Failed by now and
        # their logs are already on disk; what they still do is keep their pods
        # in `kubectl get pods` and their names taken for the next cell.
        kn("delete", "jobs", "-l", f"aad/cell={cell}", "--ignore-not-found")
        if workload == "net":
            kubectl("delete", "-f", str(config.MANIFESTS / "base" / "net-tuned-daemonset.yaml"),
                    "--ignore-not-found")
        if workload != "mongo":
            kubectl("delete", "-k", overlay(workload, cell), "--ignore-not-found")
        else:
            # The Mongo overlay stays up. Its StatefulSet has
            # persistentVolumeClaimRetentionPolicy.whenDeleted: Delete, so
            # deleting it here would take the PVC and the 20M record dataset with
            # it, and the next mongo cell of the day would reload for an hour.
            # The pod goes Pending when this node group hits zero and reschedules
            # on the next cell's node; --teardown-day is the only place that
            # drops the StatefulSet and the PVCs.
            print("# mongo overlay kept: --teardown-day is what drops the sts and its PVC")

        minutes = (now() - started) / 60
        if not config.DRY_RUN:
            (cell_dir / "cell.json").write_text(json.dumps({
                "date": date, "workload": workload, "cell": cell,
                "instance_type": config.instance_type(cell), "nodes": nodes_wanted,
                "minutes": round(minutes, 1), "runs": args.runs, "invalid": invalid,
            }, indent=1))
        print(f"\n# {workload}/{cell}: {minutes:.1f} min")
        write_ledger(day_dir)


def no_summary(run_meta, name):
    """A measured run whose Job printed nothing is not a fast run, it is no run.

    It stays on disk and it stays in the ledger; what it does not do is quietly
    disappear from the medians, which is what an unrecorded empty run would.
    """
    if config.DRY_RUN:
        return
    print(f"# job/{name}: no output\n{job_failure(name)}")
    run_meta.setdefault("invalid", []).append(f"no_summary: job/{name}")


def measure(spec, workload, cell, i, run_dir, run_meta, args):
    """One measured run at 80 % of the knee."""
    if workload == "net":
        for reverse, out_name in ((False, "iperf.json"), (True, "iperf-reverse.json")):
            name, logs = iperf_run(cell, i, reverse)
            if not logs:
                no_summary(run_meta, name)
            elif not config.DRY_RUN:
                (run_dir / out_name).write_text(logs)
        return

    kneefile = run_dir.parent / "knee.json"
    kneed = json.loads(kneefile.read_text()) if kneefile.exists() else None

    if workload == "mongo":
        threads = kneed["knee"] if kneed else spec["threads"][0]
        target = int(0.8 * (kneed["ops"] if kneed else 0)) or 1
        name = f"ycsb-run-{cell}-t{threads}-r{i}"
        logs = run_job(
            name,
            ycsb_job_yaml(name, cell, spec, threads, target,
                          int(target * spec["fixed_seconds"])),
            spec["fixed_seconds"] + 900,
        )
        run_meta["threads"], run_meta["target_ops"] = threads, target
        if not logs:
            no_summary(run_meta, name)
        elif not config.DRY_RUN:
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
    logs = run_job(name, k6_job_yaml(name, cell, spec["script"], env),
                   spec["fixed_seconds"] + 300)
    summary = k6_summary(logs)
    if summary is None:
        no_summary(run_meta, name)
    elif not config.DRY_RUN:
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


# Two filters, both of which must come back []. The Project tag is the provider's
# default_tags and only reaches what Terraform created; a CSI volume is created by
# the driver's own CreateVolume call and carries it only because the add-on is
# configured with controller.extraVolumeTags (infra/main.tf). The second filter is
# the tag the driver writes on its own, so the check still holds if that
# configuration is ever lost.
VOLUME_LEAK_FILTERS = (
    "Name=tag:Project,Values=armed-and-dangerous",
    f"Name=tag:kubernetes.io/created-for/pvc/namespace,Values={config.NAMESPACE}",
)


def describe_volumes():
    for tag_filter in VOLUME_LEAK_FILTERS:
        sh(["aws", "ec2", "describe-volumes", "--filters", tag_filter,
            "--query", "Volumes[].VolumeId"])


def teardown_day():
    """End of the lab day, before the human runs `terraform destroy`.

    Everything here is outside the Terraform state, which is exactly why it is
    here: the EBS volume behind the Mongo PVC was provisioned by the CSI driver
    and the Karpenter nodes were provisioned by Karpenter, so `terraform destroy`
    sees neither (infra/README.md). This is also the only place the Mongo
    StatefulSet is deleted: a cell leaves it running so the next cell of the day
    reuses the dataset. `delete pvc --all` takes Pyroscope's 20Gi volume with it,
    which is the intention - it is a profile store for one lab day, not a
    database.

    The canonical order for the whole teardown is in the root README
    ("Reproducir"); this command is its middle step.
    """
    # Only the arc and the clip days have NodePools at all, and their CRD only
    # exists after `kubectl apply -f infra/karpenter/`.
    if kubectl("get", "crd", "nodepools.karpenter.sh", capture=True, quiet=True,
               check=False).strip() or config.DRY_RUN:
        kubectl("delete", "nodepool", "--all", "--ignore-not-found")
    kn("delete", "jobs", "--all", "--ignore-not-found")
    kubectl("delete", "-f", str(config.MANIFESTS / "base" / "net-tuned-daemonset.yaml"),
            "--ignore-not-found")
    kn("delete", "sts", "mongo", "--ignore-not-found")
    kn("delete", "pvc", "--all")
    describe_volumes()
    print("\n# both lists above must be [] BEFORE `terraform destroy`, which a human runs.")
    print("# The full order is in the root README, section 'Reproducir':")
    print("#   cd infra && terraform destroy")
    print("#   aws ec2 describe-instances --filters Name=tag:Project,Values=armed-and-dangerous "
          "Name=instance-state-name,Values=running --query 'Reservations[].Instances[].InstanceId'")


# --- cli ---------------------------------------------------------------------

def apply_overrides(spec, args):
    for key in ("slo_ms", "fixed_seconds", "warmup_seconds", "warm_pages", "warm_max_min"):
        if getattr(args, key) is not None:
            spec[key] = getattr(args, key)
    if args.threads:
        spec["threads"] = args.threads
    if spec.get("ladder"):
        spec["ladder"] = dict(spec["ladder"])
        for flag, key in (("rate_start", "RATE_START"), ("rate_step", "RATE_STEP"),
                          ("rate_max", "RATE_MAX"), ("stage_seconds", "STAGE_SECONDS"),
                          ("ramp_seconds", "RAMP_SECONDS")):
            if getattr(args, flag) is not None:
                spec["ladder"][key] = getattr(args, flag)


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="cell", description=__doc__.splitlines()[0])
    p.add_argument("--workload", choices=sorted(config.WORKLOADS))
    p.add_argument("--cell", choices=sorted(config.CELL_MNG))
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--date", help="results/<date>/ to write into (default: today, local time)")
    p.add_argument("--dry-run", action="store_true", help="print the command plan and touch nothing")
    p.add_argument("--teardown-day", action="store_true",
                   help="drop everything the cluster still holds (NodePools, Jobs, net "
                        "knob, Mongo sts, PVCs) and print the leak checks, before "
                        "terraform destroy")
    p.add_argument("--override-budget", action="store_true",
                   help="run even though the day already exceeds estimate_per_day_usd")
    p.add_argument("--image-tag", dest="image_tag",
                   help="tag of the own images in ECR (default: the tag in results/images.json)")
    p.add_argument("--slo-ms", type=float, dest="slo_ms")
    p.add_argument("--fixed-seconds", type=int, dest="fixed_seconds")
    p.add_argument("--warmup-seconds", type=int, dest="warmup_seconds")
    p.add_argument("--rate-start", type=int, dest="rate_start")
    p.add_argument("--rate-step", type=int, dest="rate_step")
    p.add_argument("--rate-max", type=int, dest="rate_max")
    p.add_argument("--stage-seconds", type=int, dest="stage_seconds")
    p.add_argument("--ramp-seconds", type=int, dest="ramp_seconds")
    p.add_argument("--threads", type=int, nargs="+", help="YCSB thread ladder")
    p.add_argument("--warm-pages", type=int, dest="warm_pages",
                   help="mongo: 'pages read into cache' delta per pass that counts as flat")
    p.add_argument("--warm-max-min", type=int, dest="warm_max_min",
                   help="mongo: give up warming the cache after this many minutes")
    p.add_argument("--reload", action="store_true",
                   help="mongo: drop the YCSB collection and load it again before this cell")
    p.add_argument("--env", action="append", default=[], metavar="K=V",
                   help="extra env for the k6 Job (repeatable)")
    args = p.parse_args(argv)
    args.env = dict(kv.split("=", 1) for kv in args.env)
    if not args.teardown_day and not (args.workload and args.cell):
        p.error("--workload and --cell are required (or --teardown-day)")
    return args


def main(argv=None):
    args = parse_args(argv)
    config.require_sandbox()  # first thing that runs, dry run included
    config.DRY_RUN = args.dry_run
    if args.teardown_day:
        teardown_day()
        return 0
    run_cell(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
