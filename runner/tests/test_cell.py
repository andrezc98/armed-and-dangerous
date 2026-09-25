"""The decisions cell.py makes before, during and after a cell.

Nothing here reaches a cluster or AWS: the dry-run plan is a string, and the
three guards (cluster.json, budget, knee) are pure functions over files.
"""

import json
import re
from datetime import UTC, datetime

import pytest
import yaml

import capture
import cell
import config

COST_MD = """| instance | usd_per_hour | captured (date, source) |
|---|---|---|
| m8i.4xlarge | 1.00 | 2026-09-11, aws pricing |
| m9g.4xlarge | 2.00 | 2026-09-11, aws pricing |
| c7i.8xlarge | 0.50 | 2026-09-11, aws pricing |
| m7g.large | 0.10 | 2026-09-11, aws pricing |
| eks-control-plane | 0.10 | 2026-09-11, aws pricing |

- estimate_per_day_usd: {estimate}
- fixed_hours_per_day: 4.0
"""


@pytest.fixture
def plan(tmp_path, monkeypatch, capsys):
    """The --dry-run command plan of one cell, as printed."""
    monkeypatch.setenv("AWS_PROFILE", "aad-sandbox-test")
    # A real results/<today>/ on this machine must not leak into the plan: the
    # fixture fallback this test suite exercises has to hold on any machine,
    # any day, not just one where results/<today>/ happens to be empty.
    monkeypatch.setattr(config, "RESULTS", tmp_path)

    def run(*argv):
        try:
            cell.main([*argv, "--dry-run"])
        finally:
            config.DRY_RUN = False
        return capsys.readouterr().out

    return run


def _day(tmp_path, estimate="3.00"):
    """A lab day with one 30 min cell already recorded, plus its rates."""
    md = tmp_path / "cost.md"
    md.write_text(COST_MD.format(estimate=estimate))
    day = tmp_path / "2026-09-11"
    d = day / "java" / "arm-tuned"
    d.mkdir(parents=True)
    (d / "cell.json").write_text(json.dumps({
        "workload": "java", "cell": "arm-tuned", "instance_type": "m9g.4xlarge",
        "nodes": 1, "minutes": 30.0,
    }))
    return day, md


# --- every workload plans end to end -----------------------------------------
# One dry run per workload, inference included: the plan is the only place the
# whole sequence of a cell is exercised, and the inference branch used to crash
# in the warm-up (spec["ladder"] is None, so spec.get("ladder", {}).get(...) is
# .get on None) - after the node group would already have been paid for.

@pytest.mark.parametrize("workload,cell_name", [
    ("java", "arm-tuned"),
    ("go", "x86-stock"),
    ("mongo", "x86-stock"),
    ("inference", "arm-tuned"),
    ("inference", "x86-t8"),
    ("net", "arm-tuned"),
])
def test_every_workload_plans_a_whole_cell(plan, workload, cell_name):
    out = plan("--workload", workload, "--cell", cell_name)
    assert "=== " in out and f"{workload}/{cell_name}" in out
    assert "--scaling-config desiredSize=0" in out  # it always comes back down


def test_the_inference_warmup_saturates_the_slots_it_will_be_measured_on(plan, monkeypatch):
    """Warm the way you measure. The old warm-up asked for MODE=fixed at a
    RATE it read off a ladder inference does not have."""
    applied = {}
    real = cell.apply_stdin

    def spy(yaml_text, what):
        applied[what] = yaml_text
        return real(yaml_text, what)

    monkeypatch.setattr(cell, "apply_stdin", spy)
    plan("--workload", "inference", "--cell", "arm-tuned")
    warmup = yaml.safe_load(applied["job/k6-inference-arm-tuned-warmup"])
    env = {e["name"]: e["value"]
           for e in warmup["spec"]["template"]["spec"]["containers"][0]["env"]}
    assert env["MODE"] == "saturate"
    assert env["VUS"] == str(config.WORKLOADS["inference"]["saturate_vus"])
    assert env["DURATION"] == f"{config.WORKLOADS['inference']['warmup_seconds']}s"
    assert env["SLO_MS"] == "0"  # no p99 threshold, so the Job does not end Failed


# --- C1: the runner never runs terraform -------------------------------------

def test_the_plan_never_shells_out_to_terraform(plan):
    assert "terraform" not in plan("--workload", "java", "--cell", "arm-tuned")


def test_a_dry_run_falls_back_to_the_bundled_cluster_fixture(plan):
    out = plan("--workload", "java", "--cell", "arm-tuned", "--date", "2000-01-01")
    assert "cluster.json not found" in out
    assert "tests/fixtures/cluster.json" in out
    assert "aws-aad-mng-arm-tuned" in out


def test_a_real_run_without_cluster_json_says_how_to_write_it(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", False)
    with pytest.raises(SystemExit, match="terraform -chdir=infra output -json"):
        cell.cluster_info(tmp_path / "2026-09-11")


def test_cluster_json_unwraps_the_terraform_output_envelope(tmp_path):
    day = tmp_path / "2026-09-11"
    day.mkdir()
    (day / "cluster.json").write_text(json.dumps({
        "cluster_name": {"sensitive": False, "type": "string", "value": "aws-aad-eks-lab"},
        "nodegroup_names": {"value": {"arm-tuned": "aws-aad-mng-arm-tuned"}},
    }))
    info = cell.cluster_info(day)
    assert info["cluster_name"] == "aws-aad-eks-lab"
    assert info["nodegroup_names"]["arm-tuned"] == "aws-aad-mng-arm-tuned"


def test_a_cluster_json_without_the_node_groups_is_refused(tmp_path):
    day = tmp_path / "2026-09-11"
    day.mkdir()
    (day / "cluster.json").write_text(json.dumps({"cluster_name": {"value": "x"}}))
    with pytest.raises(SystemExit, match="nodegroup_names"):
        cell.cluster_info(day)


# --- C6: a Job name is reused only after the old Job is gone -----------------

def test_the_plan_waits_for_the_previous_job_to_be_deleted(plan):
    out = plan("--workload", "java", "--cell", "arm-tuned")
    for g in (1, 2):  # Java runs two k6 generators (config k6_generators)
        assert f"wait --for=delete job/k6-java-arm-tuned-knee-g{g} --timeout=60s" in out


# --- S1: the Mongo dataset survives the cell ---------------------------------

def test_the_mongo_teardown_plan_does_not_delete_the_overlay(plan):
    out = plan("--workload", "mongo", "--cell", "x86-stock")
    assert "kubectl delete -k" not in out
    assert "mongo overlay kept" in out


def test_fixed_and_warmup_runs_carry_the_ladder_vu_budget():
    """At the gate the budget came from --env, which reached every run; as a
    ladder default it has to reach the non-ladder runs too."""
    assert cell.vu_budget(config.WORKLOADS["java"]) == {"PREALLOC_VUS": 2000, "MAX_VUS": 16000}
    assert cell.vu_budget(config.WORKLOADS["inference"]) == {}


def test_teardown_removes_pyroscope_before_its_pvc(plan):
    """With the Pyroscope pod still mounting it, `delete pvc` hangs on the
    pvc-protection finalizer (smoke gate 2026-09-04)."""
    out = plan("--teardown-day")
    assert out.index("helm uninstall pyroscope") < out.index("delete pvc --all")


def test_every_other_workload_still_deletes_its_overlay(plan):
    assert "kubectl delete -k" in plan("--workload", "java", "--cell", "arm-tuned")


# --- C5: the scale-down is retried and awaited -------------------------------

def test_the_plan_waits_for_the_cell_nodes_to_disappear(plan):
    out = plan("--workload", "java", "--cell", "arm-tuned")
    assert "--scaling-config desiredSize=0" in out
    assert "wait for no node with aad/cell=arm-tuned" in out


# --- the lab is us-east-1, the sandbox profile is not -------------------------

def _aws_lines(out):
    """Every rendered `aws` command of a plan, as printed by config.sh()."""
    return [line for line in out.splitlines() if line.startswith("$ aws ")]


@pytest.mark.parametrize("argv", [
    ("--workload", "java", "--cell", "arm-tuned"),
    ("--teardown-day",),
])
def test_every_aws_call_pins_the_lab_region(plan, argv):
    """The sandbox profile's own default region is not the lab's. Without an
    explicit --region, `update-nodegroup-config` looks for a node group that
    does not exist there and `describe-volumes` reports an empty region as a
    clean teardown."""
    lines = _aws_lines(plan(*argv))
    assert lines, "the plan made no aws call at all"
    for line in lines:
        assert "--region us-east-1" in line, line


# --- S5: --env reaches the knee, not only the warmup and the fixed runs ------

def test_env_overrides_reach_the_knee_job(monkeypatch):
    captured = {}

    def fake_run_jobs(jobs, timeout):
        captured["y"] = jobs[0][1]
        return ["" for _ in jobs]  # a dry run has no logs

    monkeypatch.setattr(config, "DRY_RUN", True)
    monkeypatch.setattr(cell, "run_jobs", fake_run_jobs)
    cell.k6_knee(dict(config.WORKLOADS["java"]), "java", "arm-tuned", None, {"MAX_VUS": "8000"})
    env = yaml.safe_load(captured["y"])["spec"]["template"]["spec"]["containers"][0]["env"]
    assert {"name": "MAX_VUS", "value": "4000"} in env  # half of it, per generator
    assert {"name": "MODE", "value": "knee"} in env


# --- C2/C4: a knee is used or the cell stops ---------------------------------

def test_a_knee_run_with_no_summary_fails_instead_of_assuming_rate_start(monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(cell, "run_jobs", lambda jobs, timeout: ["" for _ in jobs])
    monkeypatch.setattr(cell, "job_failure", lambda name: "Events: ImagePullBackOff")
    with pytest.raises(RuntimeError, match="ImagePullBackOff"):
        cell.k6_knee(dict(config.WORKLOADS["java"]), "java", "arm-tuned", None, {})


def test_a_knee_with_dropped_iterations_aborts_the_cell():
    result = {"knee": 2600, "invalid": ["dropped_iterations count 812 > 0"]}
    with pytest.raises(RuntimeError, match="MAX_VUS"):
        cell.check_knee(result, 100)


def test_a_ladder_that_never_met_the_slo_aborts_the_cell():
    with pytest.raises(RuntimeError, match="first step already broke"):
        cell.check_knee({"knee": None, "invalid": []}, 100)


def test_a_usable_knee_passes_the_check():
    assert cell.check_knee({"knee": 2600, "invalid": []}, 100) is None


# --- a ladder that never crossed is not a knee -------------------------------

def test_a_knee_at_the_top_of_the_ladder_is_refused():
    """The top step still met the SLO, so the ladder stopped before the system
    did and 80 % of it is 80 % of a rate nothing struggled at."""
    reasons = cell.uncrossed(6000, 6000, "rps")
    assert reasons and "raise the top of the ladder" in reasons[0]
    with pytest.raises(RuntimeError, match="ladder_never_crossed"):
        cell.check_knee({"knee": 6000, "invalid": reasons}, 100)


def test_a_knee_below_the_top_of_the_ladder_is_accepted():
    assert cell.uncrossed(2600, 6000, "rps") == []
    assert cell.uncrossed(None, 6000, "rps") == []


def test_the_ycsb_ladder_is_judged_the_same_way():
    assert "ladder_never_crossed" in cell.uncrossed(128, 128, "threads")[0]


# --- the sentinel tag never reaches the cluster ------------------------------

def test_a_manifest_still_tagged_unset_stops_the_cell(monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(cell, "kustomize_overlay", lambda *a: "image: aad-go:UNSET")
    with pytest.raises(SystemExit, match=":UNSET is still the image tag"):
        cell.check_images("go", "x86-stock")


def test_a_rendered_overlay_passes(monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(
        cell, "kustomize_overlay",
        lambda *a: "image: 123456789012.dkr.ecr.us-east-1.amazonaws.com/aad-go:2026-09-19",
    )
    assert cell.check_images("go", "x86-stock") is None


def test_the_job_templates_of_the_workload_are_checked_too(monkeypatch):
    """The overlay is clean but the Job templates are not part of it, so an own
    image the renderer does not know about has to be caught here."""
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(cell, "kustomize_overlay", lambda *a: "image: registry/aad-iperf3:t")
    monkeypatch.setattr(cell, "rewrite_images", lambda text: text)  # renderer went blind
    with pytest.raises(SystemExit, match="iperf3-client-job.yaml"):
        cell.check_images("net", "x86-stock")


def test_a_dry_run_says_which_fixtures_it_read(plan):
    """No cluster and no push yet, so the plan falls back to the fixtures and
    the first lines of it have to say so."""
    out = plan("--workload", "mongo", "--cell", "x86-stock")
    assert "--dry-run reads the fixture" in out
    assert "# own images: 123456789012.dkr.ecr.us-east-1.amazonaws.com/<name>:2026-09-19" in out


# --- registry and tag ---------------------------------------------------------

ECR = "123456789012.dkr.ecr.us-east-1.amazonaws.com"


def _write_ecr_json(tmp_path):
    (tmp_path / "ecr.json").write_text(json.dumps({"registry": {"value": ECR}}))


def _write_images_json(path, tags):
    """tags: {image_name: tag}. Every image gets a distinct, checkable digest."""
    path.write_text(json.dumps({
        "tag": next(iter(tags.values())),
        "images": {name: {"tag": tag, "digest": f"sha256:{name}"} for name, tag in tags.items()},
    }))


def test_the_registry_comes_from_ecr_json_and_the_tag_from_images_json(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(config, "RESULTS", tmp_path)
    _write_ecr_json(tmp_path)
    _write_images_json(tmp_path / "images.json", {name: "2026-10-03" for name in cell.OWN_IMAGES})
    assert cell.load_images(tmp_path) == {
        "registry": ECR, "tags": {name: "2026-10-03" for name in cell.OWN_IMAGES}}


def test_a_per_image_tag_that_differs_from_the_rest_is_what_image_ref_uses():
    """The bug a partial PUSH=1 used to cause: repointing every own image at a
    tag only one of them has. images.json now carries a tag PER image, and
    image_ref() has to use the one that belongs to the name it is asked for,
    not a single tag shared by all four."""
    tags = {"aad-java": "2026-10-05-r2", "aad-go": "2026-10-03",
             "aad-iperf3": "2026-10-03", "aad-ycsb": "2026-10-03"}
    cell.IMAGES.update(registry=ECR, tags=tags)
    assert cell.image_ref("aad-java") == f"{ECR}/aad-java:2026-10-05-r2"
    assert cell.image_ref("aad-go") == f"{ECR}/aad-go:2026-10-03"


def test_image_tag_overrides_images_json_and_does_not_need_it(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(config, "RESULTS", tmp_path)  # no images.json in it
    _write_ecr_json(tmp_path)
    result = cell.load_images(tmp_path, "2026-10-04")
    assert result["tags"] == {name: "2026-10-04" for name in cell.OWN_IMAGES}


def test_a_missing_per_image_tag_names_the_missing_image(tmp_path, monkeypatch):
    """A file that only ever recorded three images (or a stale schema without
    an `images` map) must not silently pass an image through with no tag."""
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(config, "RESULTS", tmp_path)
    _write_ecr_json(tmp_path)
    tags = {name: "2026-10-03" for name in cell.OWN_IMAGES if name != "aad-ycsb"}
    _write_images_json(tmp_path / "images.json", tags)
    with pytest.raises(SystemExit, match="aad-ycsb"):
        cell.load_images(tmp_path)


def test_a_missing_ecr_json_names_the_terraform_command(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", False)
    with pytest.raises(SystemExit, match="terraform -chdir=infra/ecr output -json"):
        cell.load_images(tmp_path)


# --- the cpuset control cannot pass by saying nothing ------------------------

def test_an_unreadable_cpuset_invalidates_the_cell(monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(cell, "kn", lambda *a, **k: "")
    meta = {}
    assert cell.check_cpuset(config.WORKLOADS["java"], "arm-tuned", meta) == [
        "cpuset_unreadable: deploy/java cpuset.cpus.effective answered nothing"
    ]


def test_the_go_cell_reads_its_cpuset_through_the_service_proxy(monkeypatch):
    """distroless: no shell to exec a `cat` into, so the server reports its own
    affinity mask (runtime.NumCPU) over the API server service proxy."""
    seen = {}
    monkeypatch.setattr(config, "DRY_RUN", False)

    def fake_kubectl(*args, **kw):
        seen["args"] = args
        return '{"cpus":15}'

    monkeypatch.setattr(cell, "kubectl", fake_kubectl)
    meta = {}
    assert cell.check_cpuset(config.WORKLOADS["go"], "x86-stock", meta) == []
    assert seen["args"][:2] == ("get", "--raw")
    assert seen["args"][2] == "/api/v1/namespaces/aad/services/go:8080/proxy/healthz"
    assert meta["cpuset_count"] == 15


def test_a_go_pod_that_did_not_get_its_exclusive_cpus_is_refused(monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(cell, "kubectl", lambda *a, **k: '{"cpus":16}')
    assert cell.check_cpuset(config.WORKLOADS["go"], "x86-stock", {}) == [
        "/api/v1/namespaces/aad/services/go:8080/proxy/healthz is 16 vCPUs, "
        "expected 15 exclusive"
    ]


# --- a half-loaded Mongo collection is a different benchmark ----------------

def test_a_partial_ycsb_collection_refuses_to_be_measured(monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(cell, "mongo_int", lambda js: 3_500_000)
    with pytest.raises(RuntimeError, match="partial_dataset"):
        cell.mongo_prepare(dict(config.WORKLOADS["mongo"]), "x86-stock", {}, "2026-09-20")


def test_an_empty_collection_is_loaded_and_a_complete_one_is_reused(monkeypatch):
    spec = dict(config.WORKLOADS["mongo"])
    jobs = []
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(cell, "run_job", lambda name, *a, **k: jobs.append(name) or "")
    monkeypatch.setattr(cell, "mongo_pages_read", lambda: 0)

    monkeypatch.setattr(cell, "mongo_int", lambda js: 0)
    cell.mongo_prepare(spec, "x86-stock", {}, "2026-09-20")
    assert jobs[0] == "ycsb-load-2026-09-20"

    jobs.clear()
    monkeypatch.setattr(cell, "mongo_int", lambda js: spec["recordcount"])
    cell.mongo_prepare(spec, "x86-stock", {}, "2026-09-20")
    assert not any(j.startswith("ycsb-load") for j in jobs)


# --- a Job that printed a marker and nothing else is still no summary --------

def test_an_empty_body_after_the_marker_is_not_a_summary():
    assert cell.k6_summary(f"boom\n{cell.SUMMARY_MARKER}\n") is None
    assert cell.k6_summary("no marker here") is None
    assert cell.k6_summary(f"{cell.SUMMARY_MARKER}\n{{\"metrics\": {{}}}}") == {"metrics": {}}


# --- the lab day is the local day -------------------------------------------

def test_the_default_date_is_the_local_date_not_utc(plan):
    from datetime import datetime
    today = datetime.now().astimezone().date().isoformat()
    assert f"=== {today}  java/arm-tuned" in plan("--workload", "java", "--cell", "arm-tuned")


# --- S3: a measured run with no output is invalid, not absent ----------------

def test_a_measured_run_without_output_is_marked_invalid(monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(cell, "job_failure", lambda name: "Events: OOMKilled")
    meta = {}
    cell.no_summary(meta, "k6-java-arm-tuned-r2")
    assert meta["invalid"] == ["no_summary: job/k6-java-arm-tuned-r2"]


# --- S8: the cost guard actually gates ---------------------------------------

def test_the_budget_gate_refuses_a_day_already_over_its_estimate(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", False)
    day, md = _day(tmp_path, estimate="3.00")  # 1.00 of cells + 2.80 fixed = 3.80
    with pytest.raises(SystemExit, match="override-budget"):
        cell.budget_gate(day, override=False, cost_md=md)


def test_the_budget_gate_lets_a_deliberate_override_through(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", False)
    day, md = _day(tmp_path, estimate="3.00")
    assert cell.budget_gate(day, override=True, cost_md=md) is None


def test_a_day_under_its_estimate_is_not_gated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", False)
    day, md = _day(tmp_path, estimate="10.00")
    assert cell.budget_gate(day, override=False, cost_md=md) is None


def test_a_todo_rate_refuses_to_scale_anything_up(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", False)
    day, md = _day(tmp_path)
    md.write_text(md.read_text().replace("| m9g.4xlarge | 2.00 |", "| m9g.4xlarge | TODO |"))
    with pytest.raises(SystemExit, match="m9g.4xlarge"):
        cell.budget_gate(day, override=False, cost_md=md)


def test_a_dry_run_is_never_gated_on_a_rate_nobody_captured_yet(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", True)
    assert cell.budget_gate(tmp_path, override=False, cost_md=tmp_path / "missing.md") is None


# --- the knee is the SUT's, not the loader's (2026-09-24 review) -------------

def _ladder_summary(steps, stage=60, ramp=5):
    """k6 knee summary out of {rate: (p99_ms, delivered_fraction)}."""
    metrics = {}
    for rate, (p99, delivered) in steps.items():
        metrics[f"http_req_duration{{rate:{rate}}}"] = {"values": {"p(99)": p99, "max": p99 * 3}}
        metrics[f"http_reqs{{rate:{rate}}}"] = {
            "values": {"count": round(rate * (stage - ramp) * delivered)}}
        metrics[f"http_req_failed{{rate:{rate}}}"] = {"values": {"rate": 0.0}}
    return {"metrics": metrics}


def _per_generator(summary, n):
    """What each of n generators writes for an aggregate `summary`: step tags
    and request counts / n (lib.js tags the rate IT held), latencies as they are."""
    metrics = {}
    for name, metric in summary["metrics"].items():
        m = re.match(r"^(.*)\{rate:(\d+)\}$", name)
        if m:
            name = f"{m.group(1)}{{rate:{int(m.group(2)) // n}}}"
        values = metric["values"]
        if name.startswith("http_reqs"):
            values = {k: v / n for k, v in values.items()}
        metrics[name] = {**metric, "values": values}
    return {**summary, "metrics": metrics}


def _fake_jobs(monkeypatch, summary, seen=None):
    """run_jobs answering every generator its share of `summary`; `seen`
    collects the (name, yaml) of every Job."""
    def fake(jobs, timeout):
        if seen is not None:
            seen.extend(jobs)
        share = json.dumps(_per_generator(summary, len(jobs)))
        return [f"{cell.SUMMARY_MARKER}\n{share}" for _ in jobs]

    monkeypatch.setattr(cell, "run_jobs", fake)


def _fake_ladder(monkeypatch, summary, started="2026-10-01T15:00:00Z"):
    """k6_knee against a canned aggregate summary, split across the
    generators; job_started reads `started`."""
    monkeypatch.setattr(config, "DRY_RUN", False)
    _fake_jobs(monkeypatch, summary)
    monkeypatch.setattr(cell, "kn", lambda *a, **k: started)


def _java(**ladder):
    spec = dict(config.WORKLOADS["java"])
    spec["ladder"] = {**spec["ladder"], **ladder}
    return spec


def test_a_loader_limited_step_is_not_published_as_the_knee(monkeypatch, tmp_path):
    """Step 30k under-delivered with p99 well inside the SLO: the generator's
    ceiling. It used to end the walk like a crossing and its reason vanished
    from knee.json; now the cell refuses to measure and says why."""
    spec = _java(RATE_START=10000, RATE_STEP=10000, RATE_MAX=40000)
    _fake_ladder(monkeypatch, _ladder_summary(
        {10000: (1.0, 1.0), 20000: (2.0, 1.0), 30000: (3.0, 0.6), 40000: (30.0, 1.0)}))
    result = cell.k6_knee(spec, "java", "arm-tuned", tmp_path, {})
    assert result["knee"] == 20000
    assert result["ended_by"]["step"] == 30000 and result["ended_by"]["kind"] == "unresolved"
    assert 30000 in result["invalid_steps"]
    assert result["invalid"][0].startswith("capacity_unresolved: step 30000 rps delivered")
    with pytest.raises(RuntimeError, match="capacity_unresolved"):
        cell.check_knee(result, spec["slo_ms"])


def test_a_crossing_is_a_knee_and_keeps_its_reason(monkeypatch, tmp_path):
    spec = _java(RATE_START=10000, RATE_STEP=10000, RATE_MAX=40000)
    _fake_ladder(monkeypatch, _ladder_summary(
        {10000: (1.0, 1.0), 20000: (2.0, 1.0), 30000: (12.0, 0.6), 40000: (30.0, 0.2)}))
    result = cell.k6_knee(spec, "java", "arm-tuned", tmp_path, {})
    assert result["knee"] == 20000 and result["invalid"] == []
    assert result["ended_by"]["kind"] == "crossing"
    assert "delivered" in result["ended_by"]["reason"]
    assert list(result["invalid_steps"]) == [30000]  # 40000 is past the crossing
    # The ladder's clock, from the container's startedAt: 60 s per step.
    t0 = datetime.fromisoformat("2026-10-01T15:00:00Z").timestamp()
    assert result["windows"][30000] == (t0 + 120, t0 + 180 + capture.K6_START_SLACK_SECONDS)


def _samples(t0, pairs):
    """Metrics-API samples: the loader at `pct` over [t0 + begin, t0 + end]
    (cluster clock), received a second after the window closed."""
    return [{"ts": datetime.fromtimestamp(t0 + end + 1, UTC).isoformat(),
             "loader_cpu_percent": pct, "loader_window": [t0 + begin, t0 + end]}
            for begin, end, pct in pairs]


T0 = 1_800_000_000
WINDOWS = {10000: (T0, T0 + 60), 20000: (T0 + 60, T0 + 120), 30000: (T0 + 120, T0 + 180),
           40000: (T0 + 180, T0 + 240)}


def _cliff(sut_cores_at_crossing):
    """x86 on calibration day: the loader calm up to the knee, then 98 % at the
    crossing step while k6 piles VUs on a collapsing SUT."""
    samples = [{"ts": "x", "loader_cpu_percent": pct, "loader_window": [T0 + b, T0 + e],
                "node_cpu_millicores": m, "node_window": [T0 + b, T0 + e]}
               for b, e, pct, m in ((5, 25, 20, 9000), (65, 85, 26, 12600),
                                    (125, 145, 98, sut_cores_at_crossing * 1000))]
    result = {"windows": {k: WINDOWS[k] for k in (10000, 20000, 30000)},
              "ended_by": {"step": 30000, "kind": "crossing"}}
    return result, samples


def test_a_saturated_sut_at_the_crossing_waives_the_loader_there():
    result, samples = _cliff(15.1)
    assert cell.loader_guard(result, samples, sut_cpus=15) == []
    assert result["loader_guard_waived"]["step"] == 30000


def test_an_unsaturated_sut_keeps_the_loader_guard_at_the_crossing():
    """The loader at 98 % with the SUT at 9 of 15 cores is the loader capping it."""
    result, samples = _cliff(9.0)
    assert cell.loader_guard(result, samples, sut_cpus=15)[0].startswith("loader node CPU 98%")
    assert "loader_guard_waived" not in result


def test_the_waiver_never_reaches_the_steps_up_to_the_knee():
    result, samples = _cliff(15.1)
    samples[1]["loader_cpu_percent"] = 80  # the knee step itself
    assert cell.loader_guard(result, samples, sut_cpus=15)[0].startswith("loader node CPU 80%")


def test_the_knee_records_the_sut_cpu_per_step():
    """Whether a knee is the CPU running out is read off the SUT node's cores
    at each step, on the metrics windows like the loader's."""
    samples = [{"ts": "x", "loader_cpu_percent": 20, "loader_window": [T0 + b, T0 + e],
                "node_cpu_millicores": m, "node_window": [T0 + b, T0 + e]}
               for b, e, m in ((5, 25, 4000), (30, 50, 6000), (125, 145, 14500))]
    result = {"windows": WINDOWS, "ended_by": {"step": 30000, "kind": "crossing"}}
    cell.loader_guard(result, samples)
    by_step = result["sut_cpu_cores_by_step"]
    assert by_step[10000] == {"max": 6.0, "median": 5.0, "samples": 2}
    assert by_step[30000]["max"] == 14.5
    assert by_step[20000] == "missing"


def test_the_loader_guard_stops_at_the_step_that_ended_the_walk():
    """The ladder runs past the knee on purpose; the loader at 95 % on the
    steps above the crossing says nothing about the knee."""
    samples = _samples(T0, [(0, 20, 20), (65, 85, 40), (125, 145, 55), (185, 205, 95),
                            (205, 225, 97)])
    result = {"windows": WINDOWS, "ended_by": {"step": 30000}}
    assert cell.loader_guard(result, samples) == []
    assert result["loader_peak_by_step"] == {10000: 20, 20000: 40, 30000: 55, 40000: 97}
    assert result["loader_peak_percent"] == 55

    result = {"windows": WINDOWS, "ended_by": {"step": 40000}}
    assert cell.loader_guard(result, samples) == [
        "loader node CPU 97% > 70% during the knee, through step 40000"]


def test_overload_at_the_tail_of_the_crossing_step_is_guarded():
    """Review 2026-09-24: a metrics window [170, 190] is the crossing step's
    last 10 s. Stamped at its receipt time (191) it used to land in the next,
    unguarded step; by its own interval it belongs to both."""
    samples = _samples(T0, [(0, 20, 20), (65, 85, 40), (125, 145, 50), (170, 190, 92)])
    result = {"windows": WINDOWS, "ended_by": {"step": 30000}}
    assert cell.loader_guard(result, samples) == [
        "loader node CPU 92% > 70% during the knee, through step 30000"]
    assert result["loader_peak_by_step"][30000] == 92
    assert result["loader_peak_by_step"][40000] == 92


def test_a_kubectl_top_sample_is_stretched_by_the_metrics_lag():
    """Fallback without the metrics API: the value may trail the load by
    METRICS_LAG_SECONDS, so a sample received 15 s into the next step still
    counts for the crossing step."""
    samples = [{"ts": datetime.fromtimestamp(T0 + ts, UTC).isoformat(), "loader_cpu_percent": p}
               for ts, p in ((30, 20), (90, 40), (150, 50), (195, 92))]
    result = {"windows": WINDOWS, "ended_by": {"step": 30000}}
    assert cell.loader_guard(result, samples)[0].startswith("loader node CPU 92%")


def test_a_guarded_step_without_loader_telemetry_is_unresolved(monkeypatch):
    """An unobserved loader used to read as 0 % and pass."""
    monkeypatch.setattr(config, "DRY_RUN", False)
    samples = _samples(T0, [(0, 20, 20), (125, 145, 50)])
    samples.append({"ts": datetime.fromtimestamp(T0 + 90, UTC).isoformat(), "error": "timeout"})
    result = {"windows": WINDOWS, "ended_by": {"step": 30000}}
    assert cell.loader_guard(result, samples) == [
        "capacity_unresolved: no loader telemetry for step 20000"]
    assert result["loader_peak_by_step"][20000] is None
    with pytest.raises(RuntimeError, match="no loader telemetry"):
        cell.check_knee({"knee": 20000, "invalid": cell.loader_guard(result, samples)}, 10)


def test_without_step_times_the_guard_falls_back_to_the_whole_ladder():
    samples = _samples(T0, [(0, 20, 20), (185, 205, 95)])
    reasons = cell.loader_guard({"windows": {}, "ended_by": {"step": 10000}}, samples)
    assert reasons and "no step times" in reasons[0]
    assert cell.loader_guard({"windows": {}, "ended_by": None}, []) == [
        "capacity_unresolved: no loader telemetry for step the whole ladder"]


# --- every fixed run gets its own fine knee ----------------------------------

class _NoTop:
    """A sampler whose one metrics window covers the whole fine ladder, loader idle."""
    samples = [{"ts": "2026-10-01T16:00:00+00:00", "loader_cpu_percent": 20,
                "loader_window": [0, 4e9]}]

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fine(monkeypatch, tmp_path, steps, coarse=30000):
    """fine_knee over a canned fine ladder; the coarse step is Java's 10k."""
    _fake_ladder(monkeypatch, _ladder_summary(steps, stage=45))
    seen = {}
    real = cell.k6_knee

    def spy(*a, **k):
        seen.update(k)
        return real(*a, **k)

    monkeypatch.setattr(cell, "k6_knee", spy)
    result = cell.fine_knee(dict(config.WORKLOADS["java"]), "java", "arm-tuned", tmp_path, {},
                            coarse, 2, _NoTop)
    return result, seen


def test_the_fine_ladder_climbs_from_k_plus_s5_to_k_plus_s(monkeypatch, tmp_path):
    result, seen = _fine(monkeypatch, tmp_path, {32000: (4.0, 1.0), 34000: (6.0, 1.0),
                                                 36000: (11.0, 1.0), 38000: (14.0, 1.0),
                                                 40000: (20.0, 1.0)})
    assert seen["ladder"] == {"RATE_START": 32000, "RATE_STEP": 2000, "RATE_MAX": 40000,
                              "STAGE_SECONDS": 45}
    assert seen["name"] == "k6-java-arm-tuned-fine-r2"
    assert result["run_knee"] == 34000 and result["invalid"] == []
    assert json.loads((tmp_path / "knee-fine.json").read_text())["run_knee"] == 34000


def test_a_first_fine_step_that_crosses_leaves_the_coarse_knee(monkeypatch, tmp_path):
    result, _ = _fine(monkeypatch, tmp_path, {32000: (11.0, 1.0), 34000: (12.0, 1.0)})
    assert result["run_knee"] == 30000 and result["invalid"] == []


def test_a_fine_ladder_that_never_crosses_sits_at_k_plus_s_with_a_note(monkeypatch, tmp_path):
    result, _ = _fine(monkeypatch, tmp_path, {r: (2.0, 1.0) for r in range(32000, 40001, 2000)})
    assert result["run_knee"] == 40000 and result["invalid"] == []
    assert result["notes"][0].startswith("fine_never_crossed")


def test_an_unresolved_fine_step_invalidates_the_run(monkeypatch, tmp_path):
    result, _ = _fine(monkeypatch, tmp_path, {32000: (2.0, 1.0), 34000: (3.0, 0.5)})
    assert result["invalid"][0].startswith("capacity_unresolved: fine step 34000 rps")


def test_the_fixed_run_is_held_at_80_percent_of_its_own_knee(monkeypatch, tmp_path):
    jobs = []
    monkeypatch.setattr(config, "DRY_RUN", False)
    _fake_jobs(monkeypatch, {"metrics": {"http_req_duration": {"values": {"p(99)": 12.0}},
                                         "http_reqs": {"values": {"rate": 27200.0}}}}, jobs)
    (tmp_path / "knee.json").write_text(json.dumps({"knee": 30000}))
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    meta = {"run_knee": 34000}

    class Args:
        env = {}

    cell.measure(dict(config.WORKLOADS["java"]), "java", "arm-tuned", 1, run_dir, meta, Args)
    assert [name for name, _ in jobs] == ["k6-java-arm-tuned-r1-g1", "k6-java-arm-tuned-r1-g2"]
    for _, text in jobs:  # 27200 rps split across the two generators
        env = yaml.safe_load(text)["spec"]["template"]["spec"]["containers"][0]["env"]
        assert {"name": "RATE", "value": "13600"} in env
    assert meta["rate"] == 27200
    # p99 12 ms against Java's 10 ms SLO: measured, recorded, and not counted.
    assert meta["invalid"] == ["fixed_over_slo: p99 12.00 ms > SLO 10 ms"]


# --- the SUT's own knobs and meters (2026-09-24) -----------------------------

def test_app_env_is_patched_onto_the_sut_container_of_the_render(monkeypatch):
    """--app-env reaches the SUT through the same throwaway kustomization that
    puts the registry back, as a strategic merge patch on the right container."""
    seen = {}

    def fake_kubectl(*args, **kw):
        seen["k"] = (__import__("pathlib").Path(args[1]) / "kustomization.yaml").read_text()
        return ""

    monkeypatch.setattr(cell, "kubectl", fake_kubectl)
    cell.kustomize_overlay("java", "arm-tuned",
                           {"SPRING_DATASOURCE_HIKARI_MAXIMUMPOOLSIZE": "40",
                            "JAVA_TOOL_OPTIONS": "-Xmx8g -XX:+UseZGC"})
    kustomization = yaml.safe_load(seen["k"])
    patch = yaml.safe_load(kustomization["patches"][0]["patch"])
    assert (patch["kind"], patch["metadata"]["name"]) == ("Deployment", "java")
    container = patch["spec"]["template"]["spec"]["containers"][0]
    assert container["name"] == "java"
    assert {"name": "JAVA_TOOL_OPTIONS", "value": "-Xmx8g -XX:+UseZGC"} in container["env"]
    assert len(kustomization["images"]) == len(cell.OWN_IMAGES)  # the registry still goes back


def test_app_env_finds_the_container_when_it_is_not_named_like_the_resource():
    patch = yaml.safe_load(yaml.safe_load(cell.app_env_patch("net", {"A": "1"}))["patches"][0]["patch"])
    assert patch["metadata"]["name"] == "iperf3-server"
    assert patch["spec"]["template"]["spec"]["containers"][0]["name"] == "iperf3"
    patch = yaml.safe_load(yaml.safe_load(cell.app_env_patch("mongo", {"A": "1"}))["patches"][0]["patch"])
    assert patch["kind"] == "StatefulSet"


def test_without_app_env_the_render_has_no_patch(monkeypatch):
    seen = {}
    monkeypatch.setattr(cell, "kubectl", lambda *a, **k: seen.setdefault(
        "k", (__import__("pathlib").Path(a[1]) / "kustomization.yaml").read_text()) and "")
    cell.kustomize_overlay("java", "arm-tuned")
    assert "patches" not in yaml.safe_load(seen["k"])


def test_app_env_is_a_repeatable_flag_recorded_as_a_dict():
    args = cell.parse_args(["--workload", "java", "--cell", "arm-tuned",
                            "--app-env", "SERVER_TOMCAT_THREADS_MAX=400",
                            "--app-env", "JAVA_TOOL_OPTIONS=-Xmx8g -Da=b=c"])
    assert args.app_env == {"SERVER_TOMCAT_THREADS_MAX": "400", "JAVA_TOOL_OPTIONS": "-Xmx8g -Da=b=c"}


def test_the_java_pools_are_explicit_controls_in_the_base_deployment():
    base = yaml.safe_load((config.MANIFESTS / "workloads" / "java" / "base" /
                           "deployment.yaml").read_text())
    env = {e["name"]: e["value"] for e in base["spec"]["template"]["spec"]["containers"][0]["env"]}
    assert env == {"SPRING_DATASOURCE_HIKARI_MAXIMUMPOOLSIZE": "10",
                   "SERVER_TOMCAT_THREADS_MAX": "200",
                   "MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE": "health,metrics",
                   "SERVER_TOMCAT_MBEANREGISTRY_ENABLED": "true"}


def test_the_ladder_records_the_java_pools_per_step():
    t0 = 1_800_000_000
    samples = _samples(t0, [(0, 20, 20), (65, 85, 40)])
    samples[0]["actuator"] = {"hikaricp.connections.pending": 0.0, "tomcat.threads.busy": 12.0}
    samples[1]["actuator"] = {"hikaricp.connections.pending": 7.0, "tomcat.threads.busy": None}
    result = {"windows": {10000: (t0, t0 + 60), 20000: (t0 + 60, t0 + 120)}, "ended_by": None}
    cell.loader_guard(result, samples)
    assert result["actuator_by_step"][20000] == {
        "hikaricp.connections.pending": {"max": 7.0, "median": 7.0, "samples": 1},
        "tomcat.threads.busy": "missing"}


# --- which kernels llama.cpp dispatched --------------------------------------

LLAMA_LINE = ("0.00.004.454 I cmn  common_param: system_info: n_threads = 15 "
              "(n_threads_batch = 15) / 15 | CPU : NEON = 1 | ARM_FMA = 1 | SVE = 1 | KLEIDIAI = 1 |")


def test_the_system_info_line_is_read_from_the_server_log(monkeypatch):
    calls = []
    monkeypatch.setattr(cell, "kn", lambda *a, **k: calls.append(a[0]) or f"boot\n{LLAMA_LINE}\n")
    info = cell.llama_system_info(config.WORKLOADS["inference"])
    assert info == [LLAMA_LINE[LLAMA_LINE.index("system_info:"):]]
    assert calls == ["logs"]  # no probe when the log has it


def test_without_it_in_the_log_the_same_binary_is_probed_in_the_pod(monkeypatch):
    """At server-b10775 the line is TRACE, so the default log does not carry it."""
    calls = []

    def fake_kn(*args, **kw):
        calls.append(args)
        if "exec" in args:
            kw["stderr"].append(LLAMA_LINE + "\nerror loading model\n")
        return ""

    monkeypatch.setattr(cell, "kn", fake_kn)
    info = cell.llama_system_info(config.WORKLOADS["inference"])
    assert info[0].startswith("system_info: n_threads = 15") and "KLEIDIAI = 1" in info[0]
    probe = calls[1]
    assert probe[:6] == ("--request-timeout=45s", "exec", "deploy/llama", "-c", "llama", "--")
    assert probe[6:9] == ("timeout", "30", "/app/llama-server")  # a hung probe is bounded
    assert "-lv" in probe


def test_a_system_info_nobody_printed_is_recorded_as_missing(monkeypatch):
    monkeypatch.setattr(cell, "kn", lambda *a, **k: "")
    assert cell.llama_system_info(config.WORKLOADS["inference"]) == "missing"


# --- small correctness fixes (2026-09-24) ------------------------------------

def test_an_unreadable_cache_counter_fails_the_warmup_closed(monkeypatch):
    """Read as 0, two unreadable samples are a delta of 0: a 'warm' cache."""
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(cell, "mongo_int", lambda js: None)
    with pytest.raises(RuntimeError, match="cache_unreadable"):
        cell.mongo_pages_read()


def test_a_net_run_records_an_idle_baseline_and_each_direction_window(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(cell.time, "sleep", lambda s: None)
    monkeypatch.setattr(cell, "iperf_run", lambda c, i, reverse: (f"iperf-{reverse}", "{}"))
    starts = iter(["2026-10-01T15:00:20Z", "2026-10-01T15:01:30Z"])
    monkeypatch.setattr(cell, "kn", lambda *a, **k: next(starts))
    meta = {}
    cell.measure(dict(config.WORKLOADS["net"]), "net", "arm-tuned", 1, tmp_path, meta, None)
    t = datetime.fromisoformat("2026-10-01T15:00:20Z").timestamp()
    windows = meta["net_windows"]
    assert set(windows) == {"baseline", "fwd", "rev"}
    assert windows["fwd"] == [t, t + 60] and windows["rev"] == [t + 70, t + 130]


# --- fix round 1 (2026-09-24) ------------------------------------------------

def _ycsb(p99_us):
    text = (config.RUNNER / "tests" / "fixtures" / "ycsb-t64.txt").read_text()
    return text.replace("99th(us): 1300", f"99th(us): {p99_us}")


def _ycsb_ladder(monkeypatch, logs, times=""):
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(cell, "run_job", lambda name, *a, **k: logs[name.split("-")[-2]])
    monkeypatch.setattr(cell, "kn", lambda *a, **k: times)
    monkeypatch.setattr(cell, "job_failure", lambda name: "Events: OOMKilled")


def test_a_mongo_crossing_survives_an_overloaded_step_above_it(monkeypatch, tmp_path):
    """Codex's reproduction: 32 threads cross the 5 ms SLO, then the 64-thread
    step dies without a report. The crossing below it is still the knee."""
    _ycsb_ladder(monkeypatch, {"t16": _ycsb(1300), "t32": _ycsb(9000), "t64": ""})
    result = cell.ycsb_knee(dict(config.WORKLOADS["mongo"], threads=[16, 32, 64]),
                            "x86-stock", tmp_path)
    assert result["knee"] == 16 and result["ended_by"]["step"] == 32
    assert list(result["ignored_after_end"]) == [64]
    assert result["invalid"] == []


def test_a_mongo_step_without_a_report_before_any_crossing_still_breaks_the_ladder(
        monkeypatch, tmp_path):
    _ycsb_ladder(monkeypatch, {"t16": _ycsb(1300), "t32": "", "t64": _ycsb(9000)})
    with pytest.raises(RuntimeError, match="t32-knee printed no READ/TOTAL"):
        cell.ycsb_knee(dict(config.WORKLOADS["mongo"], threads=[16, 32, 64]),
                       "x86-stock", tmp_path)


def test_mongo_step_windows_are_the_jobs_own_container_times(monkeypatch, tmp_path):
    _ycsb_ladder(monkeypatch, {"t16": _ycsb(1300)},
                 times="2026-10-01T15:00:00Z 2026-10-01T15:01:10Z")
    t = datetime.fromisoformat("2026-10-01T15:00:00Z").timestamp()
    result = cell.ycsb_knee(dict(config.WORKLOADS["mongo"], threads=[16]), "x86-stock", tmp_path)
    assert result["windows"][16] == (t, t + 70)


def test_a_fixed_run_is_judged_at_the_rate_k6_was_actually_given(monkeypatch, tmp_path):
    """--env RATE=... overrides the 80 %; the validity rule must use it."""
    monkeypatch.setattr(config, "DRY_RUN", False)
    _fake_jobs(monkeypatch, {"metrics": {"http_req_duration": {"values": {"p(99)": 2.0}},
                                         "http_reqs": {"values": {"rate": 27000.0}}}})
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    meta = {"run_knee": 34000}  # 80 % = 27200

    class Args:
        env = {"RATE": "40000"}

    cell.measure(dict(config.WORKLOADS["java"]), "java", "arm-tuned", 1, run_dir, meta, Args)
    assert meta["rate"] == 40000
    assert meta["invalid"] == ["fixed_underdelivered: 27000 rps < 0.95 x 40000 rps offered"]


@pytest.mark.parametrize("step", ["10002", "3"])
def test_a_coarse_step_the_fine_ladder_cannot_split_is_refused_up_front(step):
    """10002//5 = 2000 ends at K + 10000, not K + S; 3//5 = 0 never gets there."""
    with pytest.raises(SystemExit, match="multiple of 5"):
        cell.check_fine_ladder(dict(config.WORKLOADS["java"]), {"RATE_STEP": step})


def test_a_coarse_step_the_fine_ladder_can_split_passes():
    assert cell.check_fine_ladder(dict(config.WORKLOADS["java"]), {"RATE_STEP": "15000"}) is None
    assert cell.check_fine_ladder(dict(config.WORKLOADS["mongo"]), {}) is None  # no ladder


def test_the_last_fine_step_is_exactly_k_plus_s(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(cell, "k6_knee", lambda *a, **k: seen.update(k) or {
        "knee": None, "ended_by": None, "windows": {}, "invalid": []})
    cell.fine_knee(dict(config.WORKLOADS["java"]), "java", "arm-tuned", tmp_path,
                   {"RATE_STEP": "15000"}, 30000, 1, _NoTop)
    assert (seen["ladder"]["RATE_STEP"], seen["ladder"]["RATE_MAX"]) == (3000, 45000)
    assert knee_rates(seen["ladder"])[-1] == 45000


def knee_rates(ladder):
    return __import__("knee").ladder_rates(ladder)


def test_a_fixed_run_with_no_loader_sample_is_invalid(monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", False)
    assert cell.fixed_loader_guard("java", [{"ts": "t", "error": "timeout"}]) == [
        "loader_unobserved: no loader CPU sample during the run"]
    assert cell.fixed_loader_guard("java", [{"ts": "t", "loader_cpu_percent": 40}]) == []
    assert cell.fixed_loader_guard("java", [{"ts": "t", "loader_cpu_percent": 88}]) == [
        "loader node CPU 88% > 70%"]
    assert cell.fixed_loader_guard("net", []) == []  # the generator is a SUT node there


# --- two k6 generators per load (2026-09-25) ----------------------------------

def _envs(jobs):
    return {name: {e["name"]: e["value"] for e in
                   yaml.safe_load(text)["spec"]["template"]["spec"]["containers"][0]["env"]}
            for name, text in jobs}


def test_a_ladder_for_two_generators_halves_the_rates_and_the_vu_budget(monkeypatch):
    jobs = []
    monkeypatch.setattr(config, "DRY_RUN", True)
    monkeypatch.setattr(cell, "run_jobs", lambda j, timeout: jobs.extend(j) or ["" for _ in j])
    spec = _java(RATE_START=10000, RATE_STEP=10000, RATE_MAX=120000,
                 PREALLOC_VUS=2000, MAX_VUS=16000)
    cell.k6_knee(spec, "java", "arm-tuned", None, {"MAX_VUS": "16001"})
    envs = _envs(jobs)
    assert list(envs) == ["k6-java-arm-tuned-knee-g1", "k6-java-arm-tuned-knee-g2"]
    for env in envs.values():
        assert (env["RATE_START"], env["RATE_STEP"], env["RATE_MAX"]) == ("5000", "5000", "60000")
        assert (env["PREALLOC_VUS"], env["MAX_VUS"]) == ("1000", "8001")  # rounded up
        assert env["STAGE_SECONDS"] == "60" and env["MODE"] == "knee"


def test_the_generators_are_all_applied_before_any_is_waited_on(monkeypatch):
    order = []
    monkeypatch.setattr(cell, "clear_job", lambda name: order.append(("clear", name)))
    monkeypatch.setattr(cell, "apply_stdin", lambda text, what: order.append(("apply", what)))
    monkeypatch.setattr(cell, "finish_job", lambda name, t: order.append(("wait", name)) or name)
    assert cell.run_jobs([("a", "x"), ("b", "y")], 10) == ["a", "b"]
    assert order == [("clear", "a"), ("clear", "b"), ("apply", "job/a"), ("apply", "job/b"),
                     ("wait", "a"), ("wait", "b")]


def test_the_fixed_run_keeps_each_generator_summary_next_to_the_merged_one(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DRY_RUN", False)
    _fake_jobs(monkeypatch, {"metrics": {"http_req_duration": {"values": {"p(99)": 2.0}},
                                         "http_reqs": {"values": {"rate": 27200.0}}}})
    meta = {"run_knee": 34000}

    class Args:
        env = {}

    cell.measure(dict(config.WORKLOADS["java"]), "java", "arm-tuned", 1, tmp_path, meta, Args)
    assert "invalid" not in meta
    merged = json.loads((tmp_path / "k6.json").read_text())
    assert merged["metrics"]["http_reqs"]["values"]["rate"] == 27200.0
    for g in (1, 2):
        raw = json.loads((tmp_path / f"k6-g{g}.json").read_text())
        assert raw["metrics"]["http_reqs"]["values"]["rate"] == 13600.0


def test_a_fixed_rate_is_rounded_down_to_whole_rps_per_generator(monkeypatch, tmp_path):
    jobs = []
    monkeypatch.setattr(config, "DRY_RUN", True)
    monkeypatch.setattr(cell, "run_jobs", lambda j, timeout: jobs.extend(j) or ["" for _ in j])
    meta = {"run_knee": 33999}  # 80 % = 27199.2

    class Args:
        env = {}

    cell.measure(dict(config.WORKLOADS["java"]), "java", "arm-tuned", 1, tmp_path, meta, Args)
    assert meta["rate"] == 27198
    assert {env["RATE"] for env in _envs(jobs).values()} == {"13599"}


def test_a_generator_without_a_summary_fails_the_knee(monkeypatch):
    """Half a ladder is not the ladder: one generator saw 1/N of the load."""
    monkeypatch.setattr(config, "DRY_RUN", False)
    body = f"{cell.SUMMARY_MARKER}\n" + json.dumps({"metrics": {}})
    monkeypatch.setattr(cell, "run_jobs", lambda j, timeout: [body, ""])
    monkeypatch.setattr(cell, "job_failure", lambda name: f"{name}: OOMKilled")
    with pytest.raises(RuntimeError, match="knee-g2: OOMKilled") as err:
        cell.k6_knee(dict(config.WORKLOADS["java"]), "java", "arm-tuned", None, {})
    assert "knee-g1" not in str(err.value)


def test_default_ladders_split_across_their_generators():
    for workload in ("java", "go", "inference", "mongo"):
        assert cell.check_generators(dict(config.WORKLOADS[workload]), {}) is None


@pytest.mark.parametrize("spec_over,env,what", [
    # 5000 / 8 = 625 rps per fine step, which two generators cannot share.
    ({"fine_steps": 8}, {"RATE_STEP": "5000"}, "the fine step RATE_STEP/fine_steps 625"),
    ({}, {"RATE_START": "5001"}, "RATE_START 5001"),
    ({}, {"RATE": "27001"}, "RATE 27001"),
])
def test_a_rate_two_generators_cannot_split_is_refused_up_front(spec_over, env, what):
    spec = {**config.WORKLOADS["go"], **spec_over}
    with pytest.raises(SystemExit, match="k6_generators=2") as err:
        cell.check_generators(spec, env)
    assert what in str(err.value)


def test_the_plan_checks_the_split_before_scaling_anything(plan, capsys):
    with pytest.raises(SystemExit, match="RATE_START 5001"):
        plan("--workload", "go", "--cell", "x86-stock", "--rate-start", "5001")
    assert "update-nodegroup-config" not in capsys.readouterr().out


def test_inference_stays_at_one_job(plan, monkeypatch):
    applied = []
    monkeypatch.setattr(cell, "apply_stdin", lambda text, what: applied.append(what))
    out = plan("--workload", "inference", "--cell", "arm-tuned", "--runs", "1")
    assert config.WORKLOADS["inference"]["k6_generators"] == 1
    assert [w for w in applied if w.startswith("job/k6-")] == [
        "job/k6-inference-arm-tuned-warmup", "job/k6-inference-arm-tuned-r1"]
    assert "k6 generators" not in out


def test_the_java_plan_shows_both_generators_of_every_k6_load(plan, monkeypatch):
    applied = []
    monkeypatch.setattr(cell, "apply_stdin", lambda text, what: applied.append(what))
    out = plan("--workload", "java", "--cell", "arm-tuned", "--runs", "1")
    jobs = [w for w in applied if w.startswith("job/k6-")]
    assert jobs == [f"job/k6-java-arm-tuned-{what}-g{g}"
                    for what in ("warmup", "knee", "fine-r1", "r1") for g in (1, 2)]
    assert "# 2 k6 generators, each at 1/2 of the load" in out
