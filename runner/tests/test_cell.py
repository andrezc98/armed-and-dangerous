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
| c7i.4xlarge | 0.50 | 2026-09-11, aws pricing |
| m7g.large | 0.10 | 2026-09-11, aws pricing |
| eks-control-plane | 0.10 | 2026-09-11, aws pricing |

- estimate_per_day_usd: {estimate}
- fixed_hours_per_day: 4.0
"""


@pytest.fixture
def plan(monkeypatch, capsys):
    """The --dry-run command plan of one cell, as printed."""
    monkeypatch.setenv("AWS_PROFILE", "aad-sandbox-test")

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


def test_every_other_workload_still_deletes_its_overlay(plan):
    assert "kubectl delete -k" in plan("--workload", "java", "--cell", "arm-tuned")


# --- C5: the scale-down is retried and awaited -------------------------------

def test_the_plan_waits_for_the_cell_nodes_to_disappear(plan):
    out = plan("--workload", "java", "--cell", "arm-tuned")
    assert "--scaling-config desiredSize=0" in out
    assert "wait for no node with aad/cell=arm-tuned" in out


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
