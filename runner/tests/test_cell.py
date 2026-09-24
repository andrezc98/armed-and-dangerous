"""The decisions cell.py makes before, during and after a cell.

Nothing here reaches a cluster or AWS: the dry-run plan is a string, and the
three guards (cluster.json, budget, knee) are pure functions over files.
"""

import json

import pytest
import yaml

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
    ("inference", "x86-t15"),
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
    assert "wait --for=delete job/k6-java-arm-tuned-knee --timeout=60s" in out


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

    def fake_run_job(name, yaml_text, timeout):
        captured["y"] = yaml_text
        return ""  # a dry run has no logs

    monkeypatch.setattr(config, "DRY_RUN", True)
    monkeypatch.setattr(cell, "run_job", fake_run_job)
    cell.k6_knee(dict(config.WORKLOADS["java"]), "java", "arm-tuned", None, {"MAX_VUS": "8000"})
    env = yaml.safe_load(captured["y"])["spec"]["template"]["spec"]["containers"][0]["env"]
    assert {"name": "MAX_VUS", "value": "8000"} in env
    assert {"name": "MODE", "value": "knee"} in env


# --- C2/C4: a knee is used or the cell stops ---------------------------------

def test_a_knee_run_with_no_summary_fails_instead_of_assuming_rate_start(monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(cell, "run_job", lambda *a, **k: "")
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
