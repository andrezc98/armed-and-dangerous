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
from statistics import median
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
# Idle node CPU sampled before the first iperf3 direction of a net run. 60 s so
# that two or three whole metrics-API windows (15-20 s each) lie inside it; 30 s
# could hold a single one and leave the baseline missing on most runs.
NET_BASELINE_SECONDS = 60

# The own images are written into the manifests by bare name and a sentinel tag
# (`aad-java:UNSET`), so nothing in git carries the sandbox account id. The
# registry and the tag only exist at render time: the registry comes from
# results/<date>/ecr.json (git-ignored, it has the account id in it) and the tag
# from results/images.json (committed, written by the gated push). Reaching the
# cluster with the sentinel still on costs the fifteen paid minutes an
# ImagePullBackOff takes to become obvious.
UNSET_TAG = "UNSET"
# aad-llama (arm64 only, KleidiAI build) since calibration day 2026-09-24; its tag
# is set by apps/llama/build-kleidiai.sh, not by the multi-arch build.
OWN_IMAGES = ("aad-java", "aad-go", "aad-iperf3", "aad-ycsb", "aad-llama")
# {"registry": ..., "tags": {"aad-java": ..., ...}}, filled once per run by
# load_images(). One tag PER image, not one shared by all four: a partial
# PUSH=1 (one image rebuilt) only ever moves that image's own tag, so a schema
# with a single top-level tag used to repoint every own image at a tag only
# one of them had - an ImagePullBackOff on a billing node group.
IMAGES = {}
_UNSET_IMAGE = re.compile(rf"({'|'.join(OWN_IMAGES)}):{UNSET_TAG}")

# The throwaway kustomization the runner renders every overlay through: the
# overlays name their images bare, this is what puts the registry back.
# `resources` is a RELATIVE path on purpose - kustomize refuses an absolute one
# ("new root ... cannot be absolute", kustomize v5.6.0 in kubectl 1.33.9).
# apiVersion/kind are the ones every kustomization.yaml in this repo already
# carries (https://kubectl.docs.kubernetes.io/references/kustomize/kustomization/:
# "apiVersion: kustomize.config.k8s.io/v1beta1" / "kind: Kustomization") - a
# throwaway file is still a Kustomization and kustomize documents both fields
# as part of the object, not as decoration.
OVERLAY_KUSTOMIZATION = """apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - {overlay}
images:
{images}
"""

# The Job templates the runner renders itself, per workload: they are not part of
# any kustomization, so `kubectl kustomize` does not see their image tags.
JOB_TEMPLATES = {
    "mongo": ("workloads/mongo/base/ycsb-load-job.yaml",
              "workloads/mongo/base/ycsb-run-job.yaml"),
    "postgres": ("workloads/postgres/base/pgbench-init-job.yaml",
                 "workloads/postgres/base/pgbench-run-job.yaml"),
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


def cluster_info(day_dir, mng=None):
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
    # A cluster applied before a node group existed (the AMD column, 2026-09-25)
    # has no name for it; say so instead of a KeyError further down.
    if mng is not None and mng not in info["nodegroup_names"]:
        raise SystemExit(
            f"{path} has no node group {mng}: that cluster was applied before "
            f"infra/nodegroups.tf had it. Apply (gated) and write the file again.\n{CLUSTER_JSON_HELP}"
        )
    return info


def load_images(day_dir, override_tag=None):
    """Where the own images live today: registry from ECR, tag per image from
    the push.

    Two files because they have two lifetimes and two secrecy levels. The
    registry is `<account>.dkr.ecr.<region>.amazonaws.com`, so it carries the
    sandbox account id and its file is git-ignored; it is written once per lab
    day from `terraform -chdir=infra/ecr output -json`. The tags are whatever
    the last gated push produced FOR EACH image (apps/build-multiarch.sh merges
    into results/images.json rather than overwriting it, so a partial PUSH=1
    only moves the tag of the image(s) it actually rebuilt); results/images.json
    has no account data in it, so that one IS committed. `--image-tag` is a
    single override applied to all four - a one-off for pointing a cell at a tag
    that is not what the file currently says for any of them.
    """
    path = day_dir / "ecr.json"
    registry = unwrap(read_json(path, FIXTURE_ECR, ECR_JSON_HELP)).get("registry")
    if not registry:
        raise SystemExit(f"{path} has no registry.\n{ECR_JSON_HELP}")

    if override_tag:
        tags = {name: override_tag for name in OWN_IMAGES}
    else:
        images_path = config.RESULTS / "images.json"
        images = read_json(images_path, FIXTURE_IMAGES, IMAGES_JSON_HELP).get("images", {})
        missing = [name for name in OWN_IMAGES if not images.get(name, {}).get("tag")]
        if missing:
            raise SystemExit(
                f"{images_path} has no tag for {', '.join(missing)}.\n{IMAGES_JSON_HELP}"
            )
        tags = {name: images[name]["tag"] for name in OWN_IMAGES}

    IMAGES.update(registry=registry, tags=tags)
    if len(set(tags.values())) == 1:
        print(f"# own images: {registry}/<name>:{next(iter(tags.values()))}")
    else:
        detail = ", ".join(f"{name}={tag}" for name, tag in sorted(tags.items()))
        print(f"# own images: {registry}/<name>:<tag> ({detail})")
    return IMAGES


def image_ref(name):
    if not IMAGES:
        raise RuntimeError(
            f"{name} has no registry yet: load_images() has to run before anything renders"
        )
    return f"{IMAGES['registry']}/{name}:{IMAGES['tags'][name]}"


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
        "--region", config.REGION,
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
                      f"#   aws eks describe-nodegroup --region {config.REGION} "
                      f"--cluster-name {info['cluster_name']} "
                      f"--nodegroup-name {info['nodegroup_names'][mng]}")
                return
            time.sleep(SCALE_DOWN_BACKOFF)
    try:
        wait_until(lambda: not labelled_nodes(label), NODE_GONE_TIMEOUT, f"no node with {label}")
    except RuntimeError as exc:
        print(f"# WARNING: {exc}; check `aws ec2 describe-instances --region "
              f"{config.REGION}` by hand")


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


# kind of the `kind/name` in config.WORKLOADS[...]["resource"], for --app-env.
KINDS = {"deploy": "Deployment", "statefulset": "StatefulSet"}


def app_env_patch(workload, app_env):
    """The `patches:` block that sets --app-env K=V on the SUT container.

    A strategic merge patch, the same form the overlays already use for
    JAVA_TOOL_OPTIONS: env is merged by name, so K=V replaces a value the base
    or the overlay set and adds one they did not. Built as data and dumped, not
    templated, so a value with a quote or a colon in it stays a value.
    """
    spec = config.WORKLOADS[workload]
    short, name = spec["resource"].split("/", 1)
    patch = {
        "apiVersion": "apps/v1",
        "kind": KINDS[short],
        "metadata": {"name": name, "namespace": config.NAMESPACE},
        "spec": {"template": {"spec": {"containers": [{
            "name": spec.get("container", name),
            "env": [{"name": k, "value": str(v)} for k, v in app_env.items()],
        }]}}},
    }
    return yaml.safe_dump({"patches": [{"patch": yaml.safe_dump(patch, sort_keys=False)}]},
                          sort_keys=False)


def kustomize_overlay(workload, cell, app_env=None):
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

    Goes through image_ref() (guarded: raises if load_images() has not run) for
    each name rather than reading IMAGES directly, so there is exactly one place
    that knows how a registry/tag pair is put together.

    `app_env` ({K: V} from --app-env) is patched onto the SUT container in the
    same throwaway kustomization (app_env_patch): the calibration day sweeps
    pool sizes and JVM flags without editing an overlay.
    """
    entries = []
    for name in OWN_IMAGES:
        new_name, new_tag = image_ref(name).rsplit(":", 1)
        entries.append(f"  - name: {name}\n    newName: {new_name}\n    newTag: {new_tag}")
    images = "\n".join(entries)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()  # /var -> /private/var on macOS; relpath is lexical
        rel = os.path.relpath(Path(overlay(workload, cell)).resolve(), root)
        (root / "kustomization.yaml").write_text(
            OVERLAY_KUSTOMIZATION.format(overlay=rel, images=images)
            + (app_env_patch(workload, app_env) if app_env else "")
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


# Node groups whose cells promise the C-states knob (manifests/base/
# cstates-daemonset.yaml, its nodeAffinity list): a tuned cell measured with the
# knob pod crash-looping is a stock cell with a "tuned" label on the slide.
CSTATES_NODE_CELLS = ("x86-tuned", "x86-smtoff", "amd-tuned")


def check_cstates(cell, sut, meta, timeout=300):
    """The C-states knob pod on THIS SUT node is Ready, or the cell is not
    comparable. Review of the AMD column (2026-09-25): nothing checked it, and
    on a node whose cpuidle list the script cannot use the pod exits 1 and
    restarts forever while the cell runs untuned."""
    if config.node_cell(cell) not in CSTATES_NODE_CELLS:
        return []

    def ready():
        out = kn("get", "pods", "-l", "app=cstates", "--field-selector",
                 f"spec.nodeName={sut}", "-o",
                 r'jsonpath={range .items[*]}{.status.containerStatuses[0].ready}{"\n"}{end}',
                 capture=True, quiet=True, check=False)
        return "true" in out.split() or None

    try:
        wait_until(ready, timeout, f"cstates knob Ready on {sut}")
    except RuntimeError:
        return [f"cstates knob not Ready on {sut} after {timeout}s"]
    meta["cstates_ready"] = True
    return []


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
    """Apply one Job, wait for it to finish either way, return its logs."""
    return run_jobs([(name, yaml_text)], timeout)[0]


def run_jobs(jobs, timeout):
    """Apply every (name, yaml) Job, THEN wait for each; logs in the same order.

    All applied before any is waited on, so the k6 generators of one run
    (run_k6) load the SUT at the same time instead of one after the other.

    k6 exits 99 when a threshold fails, so the Job ends Failed on a run that
    completed perfectly well (runner/k6/lib.js). Waiting only for
    condition=complete would hang on exactly the runs that carry the knee, hence
    the poll on both conditions.
    """
    for name, _ in jobs:
        clear_job(name)
    # Only the applies sit back to back: a leftover Job's delete wait would
    # otherwise hold generator 2 back while generator 1 already runs.
    for name, yaml_text in jobs:
        apply_stdin(yaml_text, f"job/{name}")
    return [finish_job(name, timeout) for name, _ in jobs]


def clear_job(name):
    kn("delete", "job", name, "--ignore-not-found")
    # `delete` returns before the object is gone, and a Job's pod template is
    # immutable, so re-applying the same name races the old one's finalizer.
    # `--for=delete` is the documented way to wait for that
    # (https://kubernetes.io/docs/reference/kubectl/generated/kubectl_wait/:
    # "Wait for the pod "busybox1" to be deleted, with a timeout of 60s, after
    # having issued the "delete" command"). It errors when the Job never
    # existed, which is the common case, hence check=False.
    kn("wait", "--for=delete", f"job/{name}", f"--timeout={JOB_DELETE_TIMEOUT}s", check=False)


def finish_job(name, timeout):
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

def vu_budget(spec):
    """The ladder's VU budget, for the warmup and fixed runs as well: a fixed run
    at 80 % of a 90k knee on the lib.js defaults (200 preallocated) drops
    iterations while k6 grows VUs and lands over knee.FIXED_MAX_DROPPED."""
    ladder = spec.get("ladder") or {}
    return {k: ladder[k] for k in ("PREALLOC_VUS", "MAX_VUS") if k in ladder}


def k6_env(spec, mode, extra):
    env = {"TARGET_URL": spec["target_url"], "MODE": mode, "SLO_MS": spec["slo_ms"]}
    env.update(extra)
    return env


# What run_k6 divides among the generators. lib.js reads each as one process's
# own load, so every generator gets its 1/N: the rates exactly (check_generators
# refuses a split that is not whole), the VU budget rounded up.
SPLIT_RATES = ("RATE", "RATE_START", "RATE_STEP", "RATE_MAX")
SPLIT_VUS = ("PREALLOC_VUS", "MAX_VUS")


def generators(spec):
    """How many k6 Jobs share one load (config.WORKLOADS k6_generators)."""
    return spec.get("k6_generators", 1)


def split_load(env, n):
    """One generator's share of a k6 env."""
    if n == 1:
        return env
    out = dict(env)
    for key in SPLIT_RATES:
        if key in out:
            out[key] = int(out[key]) // n
    for key in SPLIT_VUS:
        if key in out:
            out[key] = -(-int(out[key]) // n)
    return out


def run_k6(spec, name, cell, mode, env, timeout):
    """One k6 load, as generators(spec) Jobs started together, each at 1/N of
    `env`. Returns (Job names, their summaries: None where a Job printed none).

    Two since calibration day 2026-09-24 (config.WORKLOADS, java): one k6
    process at 70k rps added ~0.8 ms to the p99 two processes measured. Names
    get -g1..-gN only when there is more than one, so inference keeps its names.
    knee.merge_summaries turns the summaries back into one.
    """
    n = generators(spec)
    names = [name] if n == 1 else [f"{name}-g{g}" for g in range(1, n + 1)]
    share = split_load(k6_env(spec, mode, env), n)
    if n > 1:
        print(f"# {n} k6 generators, each at 1/{n} of the load: {', '.join(names)}")
    logs = run_jobs([(job, k6_job_yaml(job, cell, spec["script"], share)) for job in names],
                    timeout)
    return names, [k6_summary(text) for text in logs]


def write_summaries(out_dir, out_name, summaries, merged):
    """The merged summary under the name everything reads, and next to it each
    generator's own (k6-g1.json, knee-raw-g2.json ...), untouched. merged=None
    (a generator printed nothing) still keeps the generators that did, for the
    post-mortem."""
    if merged is not None:
        (out_dir / out_name).write_text(json.dumps(merged, indent=1))
    if len(summaries) > 1:
        stem = out_name.removesuffix(".json")
        for g, summary in enumerate(summaries, 1):
            if summary is not None:
                (out_dir / f"{stem}-g{g}.json").write_text(json.dumps(summary, indent=1))


LADDER_REMEDY = ("raise the top of the ladder (--rate-max, --threads for mongo, "
                 "--clients for postgres) "
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


def job_times(name):
    """(started, finished) epochs of the Job's container, None for what cannot
    be read.

    The container's own startedAt and not the Job's .status.startTime: between
    the two sit the scheduling and the image pull, and the ladder's clock
    (lib.js, exec.scenario.startTime) only starts with the process. Read after
    the Job finished, so the container is in state.terminated. Both are the
    node's clock, as the metrics API's windows are the kubelet's: the loader
    guard compares cluster time with cluster time, never with this laptop's.
    """
    state = "{.items[0].status.containerStatuses[0].state.terminated"
    out = kn("get", "pod", "-l", f"job-name={name}", "-o",
             f"jsonpath={state}.startedAt}} {state}.finishedAt}}",
             capture=True, quiet=True, check=False).split()
    epochs = [datetime.fromisoformat(t).timestamp() for t in out[:2]]
    return tuple(epochs + [None] * (2 - len(epochs)))


def job_started(name):
    return job_times(name)[0]


def check_fine_ladder(spec, env_extra):
    """The fine ladder's grid, checked before anything is paid for: S/fine_steps
    must be a whole number of rps, or the steps drift off K + S (and a step of 0
    never reaches it)."""
    if not spec.get("ladder"):
        return
    coarse_step, steps = int({**spec["ladder"], **env_extra}["RATE_STEP"]), spec["fine_steps"]
    if coarse_step < steps or coarse_step % steps:
        raise SystemExit(f"RATE_STEP {coarse_step} cannot be split into fine_steps={steps} "
                         f"whole steps; pick a RATE_STEP that is a multiple of {steps}")


def check_generators(spec, env_extra):
    """Every rate the cell will offer splits into whole rps per generator,
    checked before anything is paid for. The coarse ladder's rates are
    RATE_START + i x RATE_STEP, the fine ladders' K + j x RATE_STEP/fine_steps,
    so those three (and RATE_MAX, --env RATE) cover them all. The fixed run's
    80 % is rounded down to a multiple of N in measure()."""
    n = generators(spec)
    if n == 1 or not spec.get("ladder"):
        return
    ladder = {**spec["ladder"], **env_extra}
    rates = {key: int(ladder[key]) for key in SPLIT_RATES if key in ladder}
    if spec.get("fine_steps"):
        rates["the fine step RATE_STEP/fine_steps"] = int(ladder["RATE_STEP"]) // spec["fine_steps"]
    bad = [f"{key} {rate}" for key, rate in rates.items() if rate % n]
    if bad:
        raise SystemExit(f"{', '.join(bad)} cannot be split across k6_generators={n} whole rps "
                         f"per generator; pick rates that are multiples of {n}")


def k6_knee(spec, workload, cell, out_dir, env_extra, ladder=None, name=None,
            raw_name="knee-raw.json"):
    """Run one k6 ladder and read it. `ladder` overrides the spec's (the fine
    ladder of each run); the verdict on the coarse ladder is in `invalid`."""
    name = name or f"k6-{workload}-{cell}-knee"
    # --env reaches the ladder too: a knee run that ignores the VU budget the
    # human just raised is the run that made them raise it. The merged dict is
    # also what the summary is judged against, so an overridden STAGE_SECONDS
    # moves the runner's expectation and not only k6's.
    env = {**spec["ladder"], **env_extra, **(ladder or {})}
    stage_seconds, ramp_seconds = int(env["STAGE_SECONDS"]), int(env.get("RAMP_SECONDS", 5))
    rates = knee.ladder_rates({k: int(env[k]) for k in ("RATE_START", "RATE_STEP", "RATE_MAX")})
    names, summaries = run_k6(spec, name, cell, "knee", env, stage_seconds * len(rates) + 300)
    missing = [job for job, summary in zip(names, summaries) if summary is None]
    if missing:
        # Only a dry run gets to invent a knee. On the cluster, a ladder that
        # printed no summary is a failure, and assuming RATE_START would put a
        # made-up number on the slide. One generator's summary is not the load
        # either: it saw 1/N of it.
        if not config.DRY_RUN:
            if out_dir is not None:
                write_summaries(out_dir, raw_name, summaries, None)
            raise RuntimeError("\n".join(
                f"job/{job} produced no {SUMMARY_MARKER} block:\n{job_failure(job)}"
                for job in missing))
        print(f"# (dry-run) assuming knee = RATE_START = {rates[0]}")
        return {"unit": "rps", "knee": rates[0], "slo_ms": spec["slo_ms"],
                "series": [], "ended_by": None, "windows": {}, "invalid": []}
    summary = knee.merge_summaries(summaries)
    series = knee.series_from_summary(summary)
    steps = knee.step_reasons(summary, stage_seconds, ramp_seconds)
    found, ended_by = knee.walk(series, spec["slo_ms"], steps)
    invalid = uncrossed(found, rates[-1], "rps")
    if found is None and series and series[0][0] in steps:
        invalid.append(f"ladder_first_step_invalid: {series[0][0]} rps {steps[series[0][0]]}")
    elif ended_by and ended_by["kind"] == "unresolved":
        invalid.append(f"capacity_unresolved: step {ended_by['step']} rps {ended_by['reason']}")
    # The earliest generator's clock: they are applied back to back, a second
    # or two apart, well inside capture.K6_START_SLACK_SECONDS.
    started = min((t for t in map(job_started, names) if t is not None), default=None)
    result = {
        "unit": "rps",
        "knee": found,
        "slo_ms": spec["slo_ms"],
        "series": series,
        # The step that ended the walk and why, reason included: a crossing is a
        # knee, an unresolved step is the loader's ceiling (knee.walk).
        "ended_by": ended_by,
        # Only the steps up to the one that ended the walk matter; past it the
        # ladder is supposed to break (runner/knee.py).
        "invalid_steps": {r: why for r, why in sorted(steps.items())
                          if ended_by is None or r <= ended_by["step"]},
        # Where each step sits on the clock, for the per-step loader guard.
        "windows": (capture.ladder_windows(started, stage_seconds, rates)
                    if started is not None else {}),
        "invalid": invalid,
    }
    if not config.DRY_RUN:
        write_summaries(out_dir, raw_name, summaries, summary)
    return result


def loader_guard(result, samples, sut_cpus=None):
    """The loader guard of a ladder, judged per step and only through the step
    that ended the walk. Returns the reasons it fails; records the peaks.

    The ladder runs past the knee on purpose (Java to 120k rps), so the top
    steps push the loader over the line even when the knee sat at a third of
    it; a peak over the whole ladder rejected every cell that way. What has to
    hold is that the loader was not the bottleneck up to the step that decided
    the knee. A sample counts for every step its metrics interval overlaps
    (capture.by_overlap), so the tail of the crossing step is always guarded.

    Fail closed: a guarded step no loader sample covers is a step nobody can
    say the loader kept up with (capacity_unresolved). Without step times (a
    pod already gone) the whole ladder is guarded, which can only be stricter.

    One exception, on evidence: the crossing step itself is not held against
    the loader when the SUT node shows its exclusive CPUs saturated in that same
    step (>= SUT_SATURATED of `sut_cpus`). Calibration day 2026-09-24, Java
    x86-tuned: at the crossing p99 went to 198 ms, k6 grew thousands of VUs
    waiting on the SUT and the loader read 98 % - a consequence of the SUT
    collapsing (15.1 cores busy), not a loader that capped the load. Steps up
    to the knee keep the strict guard; an unsaturated SUT keeps it too.
    """
    windows, ended_by = result.get("windows") or {}, result.get("ended_by")
    observed = capture.loader_observed(samples)
    if windows:
        split = capture.by_overlap(observed, windows, "loader")
        peaks = {step: (capture.loader_peak(in_step) if in_step else None)
                 for step, in_step in split.items()}
        result["loader_peak_by_step"] = peaks
        if any("actuator" in sample for sample in samples):  # Java's pools, per step
            result["actuator_by_step"] = {
                step: capture.actuator_stats(in_step)
                for step, in_step in capture.by_overlap(samples, windows).items()}
        # The SUT node's CPU per step, on the same metrics windows: what says
        # whether the knee is the CPU running out or something queueing before
        # it (calibration day 2026-09-24: the pools never filled).
        sut = [s for s in samples if s.get("node_cpu_millicores") is not None]
        result["sut_cpu_cores_by_step"] = {
            step: ({"max": max(v) / 1000, "median": median(v) / 1000, "samples": len(v)}
                   if (v := [s["node_cpu_millicores"] for s in in_step]) else "missing")
            for step, in_step in capture.by_overlap(sut, windows, "node").items()}
        guarded = [step for step in windows if ended_by is None or step <= ended_by["step"]]
        unobserved = [step for step in guarded if not split[step]]
        judged = guarded
        crossing = ended_by["step"] if ended_by and ended_by.get("kind") == "crossing" else None
        cores = result["sut_cpu_cores_by_step"].get(crossing)
        if sut_cpus and isinstance(cores, dict) and cores["max"] >= SUT_SATURATED * sut_cpus:
            judged = [step for step in guarded if step != crossing]
            result["loader_guard_waived"] = {
                "step": crossing, "sut_cores_max": cores["max"], "sut_cpus": sut_cpus,
                "why": "SUT CPU saturated at the crossing: the loader reacted to it"}
        peak = max((peaks[step] for step in judged if peaks[step] is not None), default=None)
        where = (f"through step {ended_by['step']}" if ended_by else "over the whole ladder")
    else:
        unobserved = [] if observed else ["the whole ladder"]
        peak, where = capture.loader_peak(observed), "over the whole ladder (no step times)"
    result["loader_peak_percent"] = peak
    reasons = [] if config.DRY_RUN else [
        f"capacity_unresolved: no loader telemetry for step {step}" for step in unobserved]
    if peak is not None and peak > config.LOADER_CPU_GUARD_PERCENT:
        reasons.append(f"loader node CPU {peak}% > {config.LOADER_CPU_GUARD_PERCENT}% "
                       f"during the knee, {where}")
    return reasons


SUT_SATURATED = 0.95  # share of the exclusive CPUs that counts as the SUT out of CPU


def fixed_loader_guard(workload, samples):
    """The whole-run loader guard of a fixed run. For net the generator is the
    second SUT node, not the loader, so the guard has nothing to say there.
    Fail closed: a run nobody watched the loader through is not a run the loader
    is known to have kept up with."""
    if workload == "net" or config.DRY_RUN:
        return []
    observed = capture.loader_observed(samples)
    if not observed:
        return ["loader_unobserved: no loader CPU sample during the run"]
    peak = capture.loader_peak(observed)
    if peak is not None and peak > config.LOADER_CPU_GUARD_PERCENT:
        return [f"loader node CPU {peak}% > {config.LOADER_CPU_GUARD_PERCENT}%"]
    return []


def fine_knee(spec, workload, cell, run_dir, env_extra, coarse_knee, i, sampler):
    """The knee of THIS run: a fine ladder right above the coarse knee.

    The coarse ladder's step (10k rps for Java) is the resolution of the knee,
    and three fixed runs used to inherit that one rounded number. Each run now
    climbs from K + S/5 to K + S in five steps (K the coarse knee, S its step),
    judged by the same rules as the coarse ladder (knee.walk, loader_guard):
    - the first fine step already crosses -> the run knee is K;
    - otherwise it is the last fine step before the crossing;
    - nothing crosses -> K + S, noted as fine_never_crossed. Not invalid: the
      coarse ladder did cross at K + S, so this run just sits at the top of
      its resolution.
    An unresolved fine step or a saturated loader invalidates the run.
    """
    check_fine_ladder(spec, env_extra)
    coarse_step = int({**spec["ladder"], **env_extra}["RATE_STEP"])
    fine_step = coarse_step // spec["fine_steps"]  # exact: the last step is K + S
    ladder = {"RATE_START": coarse_knee + fine_step, "RATE_STEP": fine_step,
              "RATE_MAX": coarse_knee + coarse_step,
              "STAGE_SECONDS": spec["fine_stage_seconds"]}
    print(f"# fine ladder {ladder['RATE_START']}..{ladder['RATE_MAX']} rps, step {fine_step}")
    with sampler() as top:
        result = k6_knee(spec, workload, cell, run_dir, env_extra, ladder=ladder,
                         name=f"k6-{workload}-{cell}-fine-r{i}", raw_name="knee-fine-raw.json")
    result.update(coarse_knee=coarse_knee, ladder=ladder, notes=[])
    ended_by = result.get("ended_by")
    result["invalid"] = loader_guard(result, top.samples, config.exclusive_cpus(cell))
    if ended_by is None:
        result["run_knee"] = coarse_knee + coarse_step
        result["notes"].append(f"fine_never_crossed: {ladder['RATE_MAX']} rps still met the SLO")
    else:
        result["run_knee"] = result["knee"] if result["knee"] is not None else coarse_knee
        if ended_by["kind"] == "unresolved":
            result["invalid"].append(
                f"capacity_unresolved: fine step {ended_by['step']} rps {ended_by['reason']}")
    if not config.DRY_RUN:
        (run_dir / "knee-fine.json").write_text(json.dumps(result, indent=1))
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


YCSB_WARM_THREADS = 64  # the warm-up passes' thread count, split like any other


def ycsb_clients(spec):
    """How many go-ycsb Jobs share one load (config.WORKLOADS mongo ycsb_clients)."""
    return spec.get("ycsb_clients", 1)


def check_ycsb_clients(spec):
    """Every thread count and operationcount the cell will ask for splits into
    whole parts per client, checked before anything is paid for. The fixed
    run's --target is rounded down to a multiple of N in measure(), which makes
    its operationcount (target x fixed_seconds) divide too."""
    n = ycsb_clients(spec)
    if n == 1 or "threads" not in spec:
        return
    counts = {f"threads {t}": t for t in spec["threads"]}
    counts[f"warm-up threads {YCSB_WARM_THREADS}"] = YCSB_WARM_THREADS
    for key in ("knee_operationcount", "warm_operationcount"):
        counts[f"{key} {spec[key]}"] = spec[key]
    bad = [what for what, count in counts.items() if count % n or count < n]
    if bad:
        raise SystemExit(f"{', '.join(bad)} cannot be split across ycsb_clients={n} "
                         f"whole parts per client; pick multiples of {n}")


def run_ycsb(spec, name, cell, threads, target, operationcount, timeout):
    """One YCSB load, as ycsb_clients(spec) Jobs started together (run_jobs),
    each with 1/N of the threads, the --target and the operations. Returns
    (Job names, their stdouts). Names get -c1..-cN only when there is more than
    one; knee.merge_ycsb turns the reports back into one."""
    n = ycsb_clients(spec)
    names = [name] if n == 1 else [f"{name}-c{c}" for c in range(1, n + 1)]
    if n > 1:
        print(f"# {n} go-ycsb clients, each with 1/{n} of the threads and ops: "
              f"{', '.join(names)}")
    jobs = [(job, ycsb_job_yaml(job, cell, spec, threads // n, target // n, operationcount // n))
            for job in names]
    return names, run_jobs(jobs, timeout)


def ycsb_window(names, begin):
    """The step's window: the earliest client's start to the latest client's
    finish (cluster clock, job_times). A client whose time cannot be read gives
    way to this laptop's clock for that end, which can only widen the window."""
    times = [job_times(job) for job in names]
    starts, ends = [t[0] for t in times], [t[1] for t in times]
    return (min(starts) if None not in starts else begin,
            max(ends) if None not in ends else now())


def write_ycsb(out_dir, out_name, logs, merged):
    """The merged report under the name everything reads (knee-t128.txt,
    ycsb.txt) and, with more than one client, each client's raw stdout next to
    it (knee-t128-c1.txt ...). merged=None still keeps the raw ones."""
    if merged is not None:
        (out_dir / out_name).write_text(merged)
    if len(logs) > 1:
        stem = out_name.removesuffix(".txt")
        for c, text in enumerate(logs, 1):
            if text:
                (out_dir / f"{stem}-c{c}.txt").write_text(text)


def ycsb_knee(spec, cell, cell_dir):
    """The thread ladder, walked as it runs.

    A step with no READ/TOTAL report breaks the ladder only while the walk is
    still open: the steps after it would be measured against a cache and a
    client the failed step already disturbed. Once a step has crossed, the ones
    above it are overloaded on purpose, and one of them dying without a report
    is that overload, not a reason to throw away the crossing below it.
    """
    runs, series, windows, ignored, ended_by = [], [], {}, {}, None
    for threads in spec["threads"]:
        name = f"ycsb-run-{cell}-t{threads}-knee"
        begin = now()
        names, client_logs = run_ycsb(spec, name, cell, threads, 0,
                                      spec["knee_operationcount"], spec["fixed_seconds"] + 900)
        # One set of Jobs per step, so the step's window is their own containers
        # (cluster clock): earliest start to latest finish.
        windows[threads] = ycsb_window(names, begin)
        if config.DRY_RUN:
            continue
        # Both lines are needed: READ carries the p99 the SLO is about, TOTAL
        # the throughput the fixed runs are throttled to. A client without them
        # leaves them out of the merge: the step has no report.
        logs = knee.merge_ycsb(client_logs)
        parsed = knee.parse_ycsb(logs) if logs else {}
        missing = [line for line in ("READ", "TOTAL") if line not in parsed]
        if missing:
            write_ycsb(cell_dir, f"knee-t{threads}.txt", client_logs, None)
            if ended_by is None:
                raise RuntimeError("\n".join(
                    f"job/{job} printed no {'/'.join(missing)} line:\n{job_failure(job)}"
                    for job, text in zip(names, client_logs)
                    if not {"READ", "TOTAL"} <= knee.parse_ycsb(text).keys()))
            ignored[threads] = f"no {'/'.join(missing)} line, past the end of the walk"
            continue
        write_ycsb(cell_dir, f"knee-t{threads}.txt", client_logs, logs)
        runs.append((threads, logs))
        series = knee.series_from_ycsb(runs)
        ended_by = knee.walk(series, spec["slo_ms"])[1]
    if not runs:
        print(f"# (dry-run) assuming knee = {spec['threads'][0]} threads")
        return {"unit": "threads", "knee": spec["threads"][0], "ops": 0,
                "slo_ms": spec["slo_ms"], "series": [], "ended_by": None, "windows": {},
                "invalid": []}
    found, ended_by = knee.walk(series, spec["slo_ms"])
    ops = 0
    for threads, logs in runs:
        if threads == found:
            # TOTAL and not READ: `--target` throttles every operation, and
            # workloadb is 95/5, so pinning the run to the READ rate would ask
            # for 5 % less load than the knee actually carried.
            ops = knee.parse_ycsb(logs)["TOTAL"]["OPS"]
    return {"unit": "threads", "knee": found, "ops": ops, "slo_ms": spec["slo_ms"],
            "series": series, "ended_by": ended_by, "windows": windows,
            "ignored_after_end": ignored,
            "invalid": uncrossed(found, spec["threads"][-1], "threads")}


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
    """WiredTiger's 'pages read into cache' counter. Unreadable fails the cell:
    read as 0, two unreadable samples are a delta of 0, which is exactly what a
    warm cache looks like, and the cell would go on to measure EBS."""
    value = mongo_int('db.serverStatus().wiredTiger.cache["pages read into cache"]')
    if value is None and not config.DRY_RUN:
        raise RuntimeError("cache_unreadable: mongosh returned no 'pages read into cache'; "
                           "the warm-up control cannot pass by saying nothing")
    return value or 0


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
        run_ycsb(spec, name, cell, YCSB_WARM_THREADS, 0, spec["warm_operationcount"],
                 spec["warmup_seconds"] + 900)
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


# --- postgres (pgbench) --------------------------------------------------------

PGBENCH_WARM_CLIENTS = 64  # the warm-up passes' -c, split like any other step
POSTGRES_STATEFULSET = config.MANIFESTS / "workloads" / "postgres" / "base" / "statefulset.yaml"


def pgbench_clients(spec):
    """How many pgbench Jobs share one load (config.WORKLOADS postgres pgbench_clients)."""
    return spec.get("pgbench_clients", 1)


def _max_connections(app_env):
    """The server's max_connections as the cell will start it: --app-env, else
    the base StatefulSet (the overlays do not touch it)."""
    if "PG_MAX_CONNECTIONS" in (app_env or {}):
        return int(app_env["PG_MAX_CONNECTIONS"])
    container = yaml.safe_load(POSTGRES_STATEFULSET.read_text())["spec"]["template"]["spec"][
        "containers"][0]
    return int(next(e["value"] for e in container["env"] if e["name"] == "PG_MAX_CONNECTIONS"))


# Connections left free under max_connections: the runner's own psql, the
# superuser-reserved slots. The ladder's top step and the fixed run's doubled
# client count both stay under max_connections - this.
PG_RESERVED_CONNECTIONS = 10


def check_pgbench_clients(spec, app_env=None):
    """Every client count splits into whole sessions per pgbench process, and the
    top step fits under max_connections - PG_RESERVED_CONNECTIONS, checked
    before anything is paid for. The fixed run's -R is rounded down to a
    multiple of N, and its clients capped under the same line, in measure()."""
    n = pgbench_clients(spec)
    counts = {f"clients {c}": c for c in spec["clients"]}
    counts[f"warm-up clients {PGBENCH_WARM_CLIENTS}"] = PGBENCH_WARM_CLIENTS
    bad = [what for what, count in counts.items() if count % n or count < n]
    if bad:
        raise SystemExit(f"{', '.join(bad)} cannot be split across pgbench_clients={n} "
                         f"whole sessions per process; pick multiples of {n}")
    limit = _max_connections(app_env)
    if max(spec["clients"]) > limit - PG_RESERVED_CONNECTIONS:
        raise SystemExit(f"the ladder's top step opens {max(spec['clients'])} sessions and the "
                         f"server's max_connections is {limit} ({PG_RESERVED_CONNECTIONS} kept "
                         "free); raise PG_MAX_CONNECTIONS (statefulset or --app-env) or lower "
                         "--clients")


def pgbench_job_yaml(name, cell, spec, clients, rate, seconds, init=False):
    base = config.MANIFESTS / "workloads" / "postgres" / "base"
    if init:
        return render(base / "pgbench-init-job.yaml", NAME=name, CELL=cell, SCALE=spec["scale"])
    return render(base / "pgbench-run-job.yaml", NAME=name, CELL=cell, CLIENTS=clients,
                  THREADS=pgbench_threads(spec, clients), SECONDS=seconds,
                  RATE_ARGS=f"-R {rate}" if rate else "", SAMPLING_RATE=spec["sampling_rate"])


def pgbench_threads(spec, clients):
    """-j of one process with `clients` sessions, and the vCPUs its Job asks for:
    pgbench_threads, never more than the sessions (pgbench caps it there too)."""
    return min(spec["pgbench_threads"], clients)


def run_pgbench(spec, name, cell, clients, rate, seconds):
    """One pgbench load, as pgbench_clients(spec) Jobs started together
    (run_jobs), each with 1/N of the clients and of -R (0 = unthrottled).
    Returns (Job names, their stdouts); knee.merge_pgbench makes them one."""
    n = pgbench_clients(spec)
    names = [name] if n == 1 else [f"{name}-c{c}" for c in range(1, n + 1)]
    if n > 1:
        print(f"# {n} pgbench clients, each with 1/{n} of the sessions and of -R: "
              f"{', '.join(names)}")
    jobs = [(job, pgbench_job_yaml(job, cell, spec, clients // n, rate // n, seconds))
            for job in names]
    return names, run_jobs(jobs, seconds + 900)


def pgbench_knee(spec, cell, cell_dir):
    """The client ladder, walked as it runs, with ycsb_knee's rules (knee.walk,
    uncrossed, the loader guard in run_cell) plus a per-step verdict: a step
    with too few sampled transactions or any failure is not usable
    (knee.pgbench_reasons), which the walk reads as unresolved, not as a knee.

    Unlike Mongo's ladder it stops at the step that ended the walk: past it the
    walk never looks (knee.walk), so those steps are minutes paid for nothing.
    A step with no report while the walk is open breaks the ladder, as in Mongo.
    """
    runs, series, windows, steps, ended_by = [], [], {}, {}, None
    # Per step, for pgbench_knee_guard: which Jobs ran it and how many threads each had.
    jobs, threads = {}, {}
    n = pgbench_clients(spec)
    for clients in spec["clients"]:
        name = f"pgbench-run-{cell}-c{clients}-knee"
        begin = now()
        names, client_logs = run_pgbench(spec, name, cell, clients, 0, spec["step_seconds"])
        windows[clients] = ycsb_window(names, begin)
        jobs[clients], threads[clients] = names, pgbench_threads(spec, clients // n)
        if config.DRY_RUN:
            continue
        merged = knee.merge_pgbench(client_logs)
        write_ycsb(cell_dir, f"knee-c{clients}.txt", client_logs, merged or None)
        if not merged:
            raise RuntimeError("\n".join(
                f"job/{job} printed no pgbench report:\n{job_failure(job)}"
                for job, text in zip(names, client_logs) if knee.parse_pgbench(text) is None))
        runs.append((clients, merged))
        line = knee.parse_ycsb(merged)["READ"]
        why = knee.pgbench_reasons(line, spec["min_samples"])
        if why:
            steps[clients] = "; ".join(why)
        # A step with no sampled transaction has no p99: None, which knee.walk
        # reads as unresolved (its reason says no_latency_samples).
        series.append((clients, line["99th(us)"] / 1000.0 if "99th(us)" in line else None))
        ended_by = knee.walk(series, spec["slo_ms"], steps)[1]
        if ended_by:
            break
    if not runs:
        print(f"# (dry-run) assuming knee = {spec['clients'][0]} clients")
        return {"unit": "clients", "knee": spec["clients"][0], "ops": 0,
                "slo_ms": spec["slo_ms"], "series": [], "ended_by": None, "windows": windows,
                "jobs": jobs, "threads": threads, "invalid": []}
    found, ended_by = knee.walk(series, spec["slo_ms"], steps)
    # TOTAL tps at the knee: what the fixed runs are throttled to 80 % of.
    ops = next((knee.parse_ycsb(text)["TOTAL"]["OPS"] for c, text in runs if c == found), 0)
    invalid = uncrossed(found, spec["clients"][-1], "clients")
    if ended_by and ended_by["kind"] == "unresolved":
        invalid.append(f"capacity_unresolved: step {ended_by['step']} clients "
                       f"{ended_by['reason']}")
    return {"unit": "clients", "knee": found, "ops": ops, "slo_ms": spec["slo_ms"],
            "series": series, "ended_by": ended_by, "windows": windows,
            "jobs": jobs, "threads": threads, "invalid_steps": steps, "invalid": invalid}


PGBENCH_POD_SATURATED = 0.9  # share of its own -j threads that counts as a saturated pgbench


def pgbench_pod_guard(samples, windows, jobs, threads, skip=()):
    """Per window, the peak CPU (cores) of every pgbench pod of that window's
    Jobs, and the reasons: a pod at >= PGBENCH_POD_SATURATED of its -j threads
    is a generator that could not go faster, so what the window measured is the
    generator's ceiling (I2, review of 5b1896e). The node-level loader guard
    cannot see that: two 16-thread pods at 100 % are 32 of 64 vCPUs, 50 %.

    Samples are TopSampler's metrics-API pod samples (capture.parse_pod_metrics,
    loader_pods / loader_pods_window), attributed by overlap like the node
    guard's; a pod belongs to a Job when its name is the Job's plus "-". Keys
    in `skip` are not judged for saturation.

    Fail closed (N1, review round 2): this guard is the only one that can see a
    saturated pgbench, so a Job of a window with no pod sample at all is a
    window nobody can say the generator kept up in. Returns (saturation
    reasons, {key: {pod: peak cores}}, {key: [Jobs never sampled]}); the
    callers word the unobserved ones like loader_guard / fixed_loader_guard.
    A skipped key still needs its observation: the waiver excuses saturation
    at the crossing, not a missing sample. Nothing is unobserved under
    --dry-run, where no sampler runs."""
    split = capture.by_overlap([s for s in samples if s.get("loader_pods")], windows,
                               "loader_pods")
    peaks, reasons, unobserved = {}, [], {}
    for key, in_window in split.items():
        per = {}
        for sample in in_window:
            for pod, millicores in sample["loader_pods"].items():
                if any(pod.startswith(f"{job}-") for job in jobs.get(key, ())):
                    per[pod] = max(per.get(pod, 0), millicores / 1000)
        peaks[key] = per
        missing = [job for job in jobs.get(key, ())
                   if not any(pod.startswith(f"{job}-") for pod in per)]
        if missing and not config.DRY_RUN:
            unobserved[key] = missing
        if key in skip:
            continue
        limit = PGBENCH_POD_SATURATED * threads[key]
        over = [f"{pod} {cores:.2f} cores >= {PGBENCH_POD_SATURATED} x {threads[key]} threads"
                for pod, cores in sorted(per.items()) if cores >= limit]
        if over:
            where = f"step {key}" if isinstance(key, int) else key
            reasons.append(f"loader_pgbench_saturated: {where}: {'; '.join(over)}")
    return reasons, peaks, unobserved


def pgbench_knee_guard(result, samples):
    """pgbench_pod_guard over a knee ladder: the steps through the one that
    ended the walk, as loader_guard judges them, and the same waiver: the
    crossing step is not held against the generator when loader_guard found
    the SUT's CPUs saturated there (loader_guard_waived)."""
    ended_by = result.get("ended_by")
    windows = {step: w for step, w in (result.get("windows") or {}).items()
               if ended_by is None or step <= ended_by["step"]}
    waived = (result.get("loader_guard_waived") or {}).get("step")
    reasons, peaks, unobserved = pgbench_pod_guard(samples, windows, result.get("jobs", {}),
                                                   result.get("threads", {}), skip={waived})
    reasons = [f"capacity_unresolved: no pgbench pod sample for step {step} "
               f"({', '.join(f'job/{job}' for job in missing)})"
               for step, missing in sorted(unobserved.items())] + reasons
    result["pgbench_pod_cores_by_step"] = peaks
    result["invalid"] += reasons
    return reasons


def pgbench_run_guard(run_meta, samples, begin, end):
    """pgbench_pod_guard over one fixed run (its Jobs, the whole run)."""
    reasons, peaks, unobserved = pgbench_pod_guard(
        samples, {"run": (begin, end)}, {"run": run_meta.get("pgbench_jobs", [])},
        {"run": run_meta.get("pgbench_threads", 1)})
    run_meta["pgbench_pod_cores"] = peaks["run"]
    if unobserved.get("run"):
        reasons.insert(0, "loader_unobserved: no pgbench pod sample for "
                          + ", ".join(f"job/{job}" for job in unobserved["run"]))
    return reasons


def psql(sql):
    """One query on the server, tuples only, unaligned ('|' between columns)."""
    return kn("exec", "statefulset/postgres", "--", "psql", "-U", "postgres", "-tAX",
              "-c", sql, capture=True, check=False).strip()


def postgres_read_pages():
    """8 KiB pages the postgres container has read from its block devices: the
    rbytes of its cgroup's io.stat ("rbytes Bytes read", Documentation/admin-
    guide/cgroup-v2.rst), summed over devices. Page-cache hits never reach it,
    so unlike pg_stat_database.blks_read (which counts reads served by the
    kernel's cache as well: blks_hit "only includes hits in the PostgreSQL
    buffer cache, not the operating system's file system cache",
    https://www.postgresql.org/docs/18/monitoring-stats.html) it goes flat for
    the stock cell too, whose 128MB shared_buffers never hold the dataset.

    Unreadable fails the cell, as in Mongo: two unreadable samples are a delta
    of 0, which is exactly what a warm cache looks like. Returns (pages, the raw
    io.stat), the raw text for the cell's record (M2)."""
    out = kn("exec", "statefulset/postgres", "--", "sh", "-c",
             "cat /sys/fs/cgroup/io.stat && echo end", capture=True, check=False)
    if "end" not in out and not config.DRY_RUN:
        raise RuntimeError("cache_unreadable: /sys/fs/cgroup/io.stat of the postgres "
                           "container answered nothing; the warm-up control cannot pass by "
                           "saying nothing")
    raw = out.rsplit("end", 1)[0].strip()
    return sum(int(b) for b in re.findall(r"rbytes=(\d+)", raw)) // 8192, raw


PG_INITIALISED = "SELECT to_regclass('pgbench_accounts_pkey') IS NOT NULL"
PG_KNOBS = ("shared_buffers", "effective_cache_size", "max_connections", "huge_pages",
            "huge_pages_status")


def postgres_prepare(spec, cell, meta, date, reload=False):
    """Init once per lab day, then prewarm and warm in every cell (mongo_prepare's
    shape).

    The dataset survives between cells (the PVC reattaches). It counts as there
    when pgbench_accounts_pkey exists, the init's last step, and
    pgbench_branches holds `scale` rows (one per scale unit). Anything else is
    re-initialised: the init starts by dropping the tables, so a half-done one
    never gets measured.

    Every cell then pays the warm-up: the node is new, its page cache empty. A
    sequential pg_prewarm(..., 'read') of the table and its index pulls ~17 GB
    into the kernel cache at EBS throughput instead of 8 KiB random reads
    ("read - reads the requested range of blocks", https://www.postgresql.org/
    docs/18/pgprewarm.html), then pgbench passes run until the container stops
    reading from its disk (postgres_read_pages)."""
    initialised = psql(PG_INITIALISED)
    if initialised not in ("t", "f") and not config.DRY_RUN:
        raise RuntimeError(f"could not read the pgbench tables' state from psql: {initialised!r}")
    if initialised == "t" and not reload:
        branches = psql("SELECT count(*) FROM pgbench_branches")
        if branches != str(spec["scale"]):
            raise RuntimeError(
                f"scale_mismatch: pgbench_branches holds {branches} rows, this cell is written "
                f"for scale {spec['scale']}. Pass --reload to run the init again.")
    initialised_here = config.DRY_RUN or initialised != "t" or reload
    if initialised_here:
        name = f"pgbench-init-{date}"
        run_job(name, pgbench_job_yaml(name, cell, spec, None, None, None, init=True), 5400)
        done = psql(PG_INITIALISED)
        if done != "t" and not config.DRY_RUN:
            raise RuntimeError(f"init_incomplete: job/{name} ended without "
                               f"pgbench_accounts_pkey:\n{job_failure(name)}")

    pg = meta["postgres"] = {}
    psql("CREATE EXTENSION IF NOT EXISTS pg_prewarm")
    # pg_prewarm returns "the number of blocks prewarmed" as int8; anything else
    # (an error, nothing) is a prewarm that did not happen (M1).
    blocks = psql("SELECT pg_prewarm('pgbench_accounts', 'read') + "
                  "pg_prewarm('pgbench_accounts_pkey', 'read')")
    if not blocks.isdigit() and not config.DRY_RUN:
        raise RuntimeError(f"prewarm_failed: pg_prewarm returned {blocks!r}, not a block count")
    pg["prewarm_blocks"] = int(blocks) if blocks.isdigit() else None
    row = psql("SELECT pg_database_size(current_database()), "
               + ", ".join(f"current_setting('{k}')" for k in PG_KNOBS)).split("|")
    pg.update(zip(PG_KNOBS, row[1:]))
    pg["database_bytes"] = int(row[0]) if row[0].isdigit() else None
    print(f"# postgres: {pg}")

    pg["warmup_read_pages"] = []
    deadline = now() + spec["warm_max_min"] * 60
    attempt = 0
    before, raw = postgres_read_pages()
    pg["io_stat_first"] = raw
    # The prewarm just read the dataset from EBS, so a container whose io.stat
    # still says 0 bytes read is one whose reads io.stat does not count (the io
    # controller not enabled for it), and every delta below would read 0 = warm
    # (M2). Not after this cell's own init: the dataset was written through
    # this node's page cache and the prewarm read nothing from disk.
    if not before and not config.DRY_RUN:
        if not initialised_here:
            raise RuntimeError("cache_unreadable: io.stat reports 0 rbytes right after "
                               "pg_prewarm read the dataset; it is not counting this "
                               f"container's reads:\n{raw or '<empty>'}")
        pg["io_stat_unverified"] = ("0 rbytes after this cell's own init: the dataset was "
                                    "written through the page cache, nothing to read yet")
    while True:
        run_pgbench(spec, f"pgbench-run-{cell}-warm{attempt}", cell, PGBENCH_WARM_CLIENTS, 0,
                    spec["warmup_seconds"])
        after, raw = postgres_read_pages()
        pg["io_stat_last"] = raw
        delta = after - before
        before = after
        pg["warmup_read_pages"].append(delta)
        if config.DRY_RUN or delta < spec["warm_pages"]:
            return
        attempt += 1
        if now() > deadline:
            raise RuntimeError(
                f"cache_not_warm: the postgres container still read {delta} pages from disk "
                f"per pass after {spec['warm_max_min']} min; this cell would measure EBS")


def system_info_lines(text):
    """The `system_info:` line(s) llama.cpp prints: the CPU features its ggml CPU
    backend was built for and detected (NEON, SVE, KLEIDIAI, AVX512, AMX...)."""
    return [line[line.index("system_info:"):].strip()
            for line in text.splitlines() if "system_info:" in line]


def llama_system_info(spec):
    """Which kernels llama.cpp dispatched on this node, into the cell's meta.

    First the server's own log. At the pinned server-b10775 that line is logged
    at TRACE (common_params_print_info, COM_TRC), under the default verbosity 3,
    so it is normally not there; checked 2026-09-24 with `docker run
    ghcr.io/ggml-org/llama.cpp:server-b10775 -m /nonexistent.gguf -lv 4`, which
    prints it and exits on the missing model. Raising the measured server's
    verbosity would also log every TRACE line during the run, so the same binary
    is run that way once, inside the same pod (same cpuset, same image), before
    the warm-up. It fails on the model in milliseconds; its n_threads is the
    probe's own, the CPU feature list is the server's.
    """
    resource = spec["resource"]
    lines = system_info_lines(kn("logs", resource, "-c", "llama", capture=True, quiet=True,
                                 check=False))
    if not lines:
        errors = []
        # `timeout` is GNU coreutils 9.4 in the image (Ubuntu 24.04, checked
        # 2026-09-24 with docker run --entrypoint sh); --request-timeout bounds
        # the kubectl side. A probe that hangs is recorded as missing.
        out = kn("--request-timeout=45s", "exec", resource, "-c", "llama", "--",
                 "timeout", "30", "/app/llama-server",
                 "-m", "/nonexistent.gguf", "--port", "18080", "-lv", "4",
                 capture=True, check=False, stderr=errors)
        lines = system_info_lines(out + "".join(errors))
    info = lines or "missing"
    print(f"# llama.cpp system_info: {info}")
    return info


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

    Under --dry-run, config.sh() never actually runs `kubectl kustomize` (it
    short-circuits and returns "" while config.DRY_RUN is set), so rendering the
    overlay here would always come back empty and therefore always look clean -
    not a check, just the appearance of one. The overlay render is skipped and
    said out loud instead of pretending it happened; the Job templates below are
    plain Python string substitution (rewrite_images), so they involve no
    subprocess and ARE genuinely checked even in a dry run.
    """
    texts = {}
    if config.DRY_RUN:
        print("# (dry-run) overlay render skipped: kubectl does not run under --dry-run "
              "(config.sh), so only the Job templates below are actually checked here")
    else:
        texts[f"overlay {workload}/{cell}"] = kustomize_overlay(workload, cell)
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

    mng = config.node_cell(cell)
    info = cluster_info(day_dir, mng)
    load_images(day_dir, args.image_tag)
    nodes_wanted = spec.get("nodes", 1)
    label = f"aad/cell={mng}"
    invalid = []

    print(f"\n=== {date}  {workload}/{cell} on node group {info['nodegroup_names'][mng]} "
          f"({config.instance_type(cell)} x{nodes_wanted}) ===\n")
    budget_gate(day_dir, args.override_budget)
    check_images(workload, cell)
    check_fine_ladder(spec, args.env)
    check_generators(spec, args.env)
    if workload == "mongo":
        check_ycsb_clients(spec)
    if workload == "postgres":
        check_pgbench_clients(spec, args.app_env)

    # From here on the money is running, so everything is inside the try: the
    # scale-up included, because a scale-up that half succeeded still bills.
    started = now()
    meta = {}  # before the try: the finally below reads it even when the scale-up failed
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

        # The two databases' StatefulSets both tolerate the SUT taint and keep
        # their last cell's nodeSelector; when that matches this cell, the
        # other database would come up next to the one being measured. Scaled
        # to 0 (its PVC and dataset stay); its own next cell's apply brings it
        # back to 1. Missing is fine, hence check=False (I3).
        other = {"mongo": "postgres", "postgres": "mongo"}.get(workload)
        if other:
            kn("scale", f"statefulset/{other}", "--replicas=0", check=False)

        # Not `apply -k`: the overlay only becomes appliable once the images
        # transformer has run over it (kustomize_overlay).
        apply_stdin(kustomize_overlay(workload, cell, args.app_env), f"overlay {workload}/{cell}")
        kn("rollout", "status", spec["resource"], "--timeout=900s")

        if workload == "net":
            # Which of the two cell nodes carries the server is the scheduler's
            # decision, and the server is the SUT: APerf and the CPU medians have
            # to follow it rather than whichever node came up first.
            sut = server_node(sut_nodes)

        if args.app_env:
            meta["app_env"] = args.app_env
        if workload == "inference":
            meta["llama_system_info"] = llama_system_info(spec)
        invalid += check_cpuset(spec, cell, meta)
        invalid += check_cstates(cell, sut, meta)
        if invalid:
            raise RuntimeError(f"cell not comparable: {invalid}")

        if spec["loader"] == "k6":
            sync_k6_scripts()

        def sampler():
            return capture.TopSampler(sut_nodes, loader, sut=sut, actuator=spec.get("actuator"),
                                      pod_prefix="pgbench-" if workload == "postgres" else None)

        # --- warmup: the same shape as the measurement, so what gets warm is
        # what gets measured. Inference has no ladder, so it warms closed-loop on
        # the server's slots exactly as it will be measured; the others hold the
        # first rate of their ladder.
        if workload == "mongo":
            mongo_prepare(spec, cell, meta, date, reload=args.reload)
        elif workload == "postgres":
            postgres_prepare(spec, cell, meta, date, reload=args.reload)
        elif spec["loader"] == "k6" and spec["warmup_seconds"]:
            duration = f"{spec['warmup_seconds']}s"
            if spec.get("ladder") is None:
                mode, load = "saturate", {"VUS": spec["saturate_vus"], "DURATION": duration}
            else:
                mode, load = "fixed", {"RATE": spec["ladder"]["RATE_START"], "DURATION": duration}
            run_k6(spec, f"k6-{workload}-{cell}-warmup", cell, mode,
                   {**vu_budget(spec), **load, **args.env}, spec["warmup_seconds"] + 300)

        # --- knee, with the loader guard around it in both loaders: a knee found
        # while the generator is saturated is the generator's knee, not the
        # silicon's, and go-ycsb saturates a client as happily as k6 does.
        if workload in ("mongo", "postgres") or spec.get("ladder"):
            with sampler() as top:
                knee_result = (
                    ycsb_knee(spec, cell, cell_dir) if workload == "mongo"
                    else pgbench_knee(spec, cell, cell_dir) if workload == "postgres"
                    else k6_knee(spec, workload, cell, cell_dir, args.env)
                )
            knee_result["invalid"] += loader_guard(knee_result, top.samples,
                                                   config.exclusive_cpus(cell))
            if workload == "postgres":
                pgbench_knee_guard(knee_result, top.samples)
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
            if spec.get("ladder"):
                # Before APerf and the flame graph window: those cover the fixed
                # run only (~4 min per run, config.WORKLOADS fine_stage_seconds).
                fine = fine_knee(spec, workload, cell, run_dir, args.env, knee_result["knee"], i,
                                 sampler)
                run_meta["run_knee"] = fine["run_knee"]
                if fine["invalid"]:
                    # Rule 1 and 2 again: no run at 80 % of a knee nobody found.
                    run_meta["invalid"] = list(fine["invalid"])
                    print(f"# run {i} not measured: {'; '.join(fine['invalid'])}")
                    if not config.DRY_RUN:
                        (run_dir / "meta.json").write_text(json.dumps(run_meta, indent=1))
                    continue
            # net runs both directions back to back, so the recording is twice as long
            aperf_seconds = spec["fixed_seconds"] * (2 if workload == "net" else 1)
            aperf = capture.aperf_start(sut, aperf_seconds, run_dir / "aperf")
            begin = now()
            try:
                with sampler() as top:
                    measure(spec, workload, cell, i, run_dir, run_meta, args)
                run_meta["loader_peak_percent"] = top.peak_loader_percent
                if run_meta.get("net_windows"):
                    run_meta["net_cpu_cores"] = capture.window_cores(top.samples,
                                                                     run_meta["net_windows"])
                    run_meta["net_cpu_notes"] = capture.net_coverage(run_meta["net_cpu_cores"])
                if spec.get("actuator"):
                    run_meta["actuator"] = capture.actuator_stats(top.samples)
                if not config.DRY_RUN:
                    top.write(run_dir / "top.json")
                reasons = fixed_loader_guard(workload, top.samples)
                if workload == "postgres":
                    reasons += pgbench_run_guard(run_meta, top.samples, begin, now())
                if reasons:
                    run_meta.setdefault("invalid", []).extend(reasons)
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
        if workload not in ("mongo", "postgres"):
            kubectl("delete", "-k", overlay(workload, cell), "--ignore-not-found")
        else:
            # The Mongo (and PostgreSQL) overlay stays up. Its StatefulSet has
            # persistentVolumeClaimRetentionPolicy.whenDeleted: Delete, so
            # deleting it here would take the PVC and the 20M record dataset with
            # it, and the next mongo cell of the day would reload for an hour.
            # The pod goes Pending when this node group hits zero and reschedules
            # on the next cell's node; --teardown-day is the only place that
            # drops the StatefulSet and the PVCs.
            print(f"# {workload} overlay kept: --teardown-day is what drops the sts and its PVC")

        minutes = (now() - started) / 60
        if not config.DRY_RUN:
            (cell_dir / "cell.json").write_text(json.dumps({
                "date": date, "workload": workload, "cell": cell,
                "instance_type": config.instance_type(cell), "nodes": nodes_wanted,
                "minutes": round(minutes, 1), "runs": args.runs, "invalid": invalid,
                "app_env": args.app_env,
                "llama_system_info": meta.get("llama_system_info"),
                # pg_database_size, the server knobs as SHOW reads them
                # (huge_pages_status included) and the warm-up's EBS reads.
                "postgres": meta.get("postgres"),
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
        # CPU per Gbps is per direction: the node CPU of each direction's own
        # window, minus what the node burns idle (aperf and the DaemonSets
        # included) in the NET_BASELINE_SECONDS before the first one. The
        # TopSampler around this call provides the samples; stats and meta read
        # them per window (capture.window_cores).
        # The baseline's bounds are this laptop's clock and the directions' are
        # the node's (job_started); both NTP-synced, and a metrics window has to
        # lie wholly inside either (capture.window_cores), so a second of skew
        # costs at most a sample, never borrows one from the neighbour.
        begin = now()
        if not config.DRY_RUN:
            time.sleep(NET_BASELINE_SECONDS)
        windows = {"baseline": [begin, now()]}
        for reverse, out_name in ((False, "iperf.json"), (True, "iperf-reverse.json")):
            begin = now()
            name, logs = iperf_run(cell, i, reverse)
            # The client's own start and -t, not the Job's apply-to-done span,
            # which also holds the pod's scheduling and teardown.
            started = job_started(name)
            windows["rev" if reverse else "fwd"] = (
                [started, started + spec["fixed_seconds"]] if started is not None else [begin, now()]
            )
            if not logs:
                no_summary(run_meta, name)
            elif not config.DRY_RUN:
                (run_dir / out_name).write_text(logs)
        run_meta["net_windows"] = windows
        return

    kneefile = run_dir.parent / "knee.json"
    kneed = json.loads(kneefile.read_text()) if kneefile.exists() else None

    if workload == "mongo":
        threads = kneed["knee"] if kneed else spec["threads"][0]
        n = ycsb_clients(spec)
        target = int(0.8 * (kneed["ops"] if kneed else 0))
        # ponytail: whole ops/s per client by rounding down (< N ops/s off the 80 %).
        target = (target - target % n) or n
        name = f"ycsb-run-{cell}-t{threads}-r{i}"
        names, client_logs = run_ycsb(spec, name, cell, threads, target,
                                      target * spec["fixed_seconds"], spec["fixed_seconds"] + 900)
        # The aggregate target: the merged TOTAL OPS is judged against it.
        run_meta["threads"], run_meta["target_ops"] = threads, target
        if not all(client_logs):
            for job, text in zip(names, client_logs):
                if not text:
                    no_summary(run_meta, job)
            if not config.DRY_RUN:
                write_ycsb(run_dir, "ycsb.txt", client_logs, None)
        elif not config.DRY_RUN:
            logs = knee.merge_ycsb(client_logs)
            write_ycsb(run_dir, "ycsb.txt", client_logs, logs)
            parsed = knee.parse_ycsb(logs)
            if "READ" in parsed and "TOTAL" in parsed:  # a truncated report: stats says so
                reasons = knee.ycsb_invalid_reasons(parsed, spec["slo_ms"], target)
                if reasons:
                    run_meta.setdefault("invalid", []).extend(reasons)
        return

    if workload == "postgres":
        knee_clients = kneed["knee"] if kneed else spec["clients"][0]
        n = pgbench_clients(spec)
        # Under -R, -c only caps how many transactions can be in flight: at the
        # knee's own count, 80 % of its tps keeps every session 80 % busy and a
        # Poisson schedule then queues behind them (schedule lag). Twice the
        # knee's sessions leave the schedule room; capped under max_connections
        # (C1, review of 5b1896e).
        cap = _max_connections(getattr(args, "app_env", None)) - PG_RESERVED_CONNECTIONS
        clients = min(spec["fixed_clients_factor"] * knee_clients, cap)
        clients -= clients % n
        target = int(0.8 * (kneed["ops"] if kneed else 0))
        # ponytail: whole tps per client by rounding down (< N tps off the 80 %).
        target = (target - target % n) or n
        names, client_logs = run_pgbench(spec, f"pgbench-run-{cell}-c{clients}-r{i}", cell,
                                         clients, target, spec["fixed_seconds"])
        run_meta.update(clients=clients, knee_clients=knee_clients, target_ops=target,
                        pgbench_jobs=names, pgbench_threads=pgbench_threads(spec, clients // n))
        merged = knee.merge_pgbench(client_logs)
        if not merged:
            for job, text in zip(names, client_logs):
                if knee.parse_pgbench(text) is None:
                    no_summary(run_meta, job)
            if not config.DRY_RUN:
                write_ycsb(run_dir, "pgbench.txt", client_logs, None)
        elif not config.DRY_RUN:
            write_ycsb(run_dir, "pgbench.txt", client_logs, merged)
            reasons = knee.pgbench_fixed_reasons(knee.parse_ycsb(merged), spec["slo_ms"], target,
                                                 spec["min_samples"], spec["pg_max_lag_p99_ms"])
            if reasons:
                run_meta.setdefault("invalid", []).extend(reasons)
        return

    name = f"k6-{workload}-{cell}-r{i}"
    if spec.get("ladder") is None:
        # Inference: closed loop against the server's own slots.
        mode, env = "saturate", {
            "VUS": spec["saturate_vus"], "DURATION": f"{spec['fixed_seconds']}s", **args.env,
        }
        out_name = "llama.json"
    else:
        # The run's own knee (fine_knee) when it has one; the coarse one otherwise.
        run_knee = run_meta.get("run_knee") or (kneed["knee"] if kneed else None)
        rate = int(0.8 * run_knee) if run_knee else spec["ladder"]["RATE_START"]
        # ponytail: whole rps per generator by rounding down (< N rps); exact
        # already for every default ladder, where 80 % of a knee is a multiple of 800.
        rate -= rate % generators(spec)
        mode, env = "fixed", {
            **vu_budget(spec), "RATE": rate, "DURATION": f"{spec['fixed_seconds']}s", **args.env,
        }
        # What k6 is actually asked for: --env RATE=... wins over the 80 %, and
        # the validity rule has to judge the run against that.
        run_meta["rate"] = int(env["RATE"])
        out_name = "k6.json"
    names, summaries = run_k6(spec, name, cell, mode, env, spec["fixed_seconds"] + 300)
    if None in summaries:
        for job, summary in zip(names, summaries):
            if summary is None:
                no_summary(run_meta, job)
        if not config.DRY_RUN:
            write_summaries(run_dir, out_name, summaries, None)
    elif not config.DRY_RUN:
        # Merged: http_reqs rate summed, so fixed_underdelivered compares the
        # aggregate delivered against the aggregate RATE in run_meta.
        summary = knee.merge_summaries(summaries)
        write_summaries(run_dir, out_name, summaries, summary)
        reasons = knee.invalid_reasons(summary, spec["slo_ms"], run_meta.get("rate"))
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
        sh(["aws", "ec2", "describe-volumes", "--region", config.REGION,
            # status=available: the nodes' root disks carry the Project tag
            # and vanish with the instances; a leak is a detached volume.
            "--filters", tag_filter, "Name=status,Values=available",
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
    kn("delete", "sts", "mongo", "postgres", "--ignore-not-found")
    # Pyroscope before its PVC: while its pod mounts the volume, the
    # pvc-protection finalizer holds `delete pvc` forever (smoke gate 2026-09-04).
    config.sh(["helm", "uninstall", "pyroscope", "-n", config.NAMESPACE, "--ignore-not-found",
        "--wait"])
    kn("delete", "pvc", "--all")
    describe_volumes()
    print("\n# both lists above must be [] BEFORE `terraform destroy`, which a human runs.")
    print("# The full order is in the root README, section 'Reproducir':")
    print("#   cd infra && terraform destroy")
    print(f"#   aws ec2 describe-instances --region {config.REGION} "
          "--filters Name=tag:Project,Values=armed-and-dangerous "
          "Name=instance-state-name,Values=running --query 'Reservations[].Instances[].InstanceId'")


# --- cli ---------------------------------------------------------------------

def apply_overrides(spec, args):
    for key in ("slo_ms", "fixed_seconds", "warmup_seconds", "warm_pages", "warm_max_min"):
        if getattr(args, key) is not None:
            spec[key] = getattr(args, key)
    if args.threads:
        spec["threads"] = args.threads
    if args.clients:
        spec["clients"] = args.clients
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
                        "knob, Mongo and PostgreSQL sts, PVCs) and print the leak checks, before "
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
    p.add_argument("--clients", type=int, nargs="+", help="pgbench client ladder (postgres)")
    p.add_argument("--warm-pages", type=int, dest="warm_pages",
                   help="mongo: 'pages read into cache' delta per pass that counts as flat; "
                        "postgres: 8 KiB pages read from disk (cgroup io.stat) per pass")
    p.add_argument("--warm-max-min", type=int, dest="warm_max_min",
                   help="mongo: give up warming the cache after this many minutes")
    p.add_argument("--reload", action="store_true",
                   help="mongo: drop the YCSB collection and load it again before this cell; "
                        "postgres: run the pgbench init again (it drops the tables first)")
    p.add_argument("--env", action="append", default=[], metavar="K=V",
                   help="extra env for the k6 Job (repeatable)")
    p.add_argument("--app-env", action="append", default=[], metavar="K=V", dest="app_env",
                   help="env for the SUT container, patched through the overlay render "
                        "(repeatable; recorded in the cell's meta)")
    args = p.parse_args(argv)
    args.env = dict(kv.split("=", 1) for kv in args.env)
    args.app_env = dict(kv.split("=", 1) for kv in args.app_env)
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
