"""The generational arc (plan Task 8): java stock on one Karpenter .4xlarge per
family. Dry runs and a local `kubectl kustomize` only; nothing here reaches a
cluster (conftest.no_live_commands)."""

import json

import pytest
import yaml

import cell
import config
import cost


@pytest.fixture
def plan(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AWS_PROFILE", "aad-sandbox-test")
    monkeypatch.setattr(config, "RESULTS", tmp_path)

    def run(*argv):
        try:
            cell.main([*argv, "--dry-run"])
        finally:
            config.DRY_RUN = False
        return capsys.readouterr().out

    return run


# --- the option ----------------------------------------------------------------

def test_arc_names_the_cell_and_defaults_to_one_run():
    args = cell.parse_args(["--workload", "java", "--arc", "m7g"])
    assert (args.cell, args.runs) == ("arc-m7g", 1)
    assert cell.parse_args(["--workload", "java", "--arc", "m5", "--runs", "2"]).runs == 2
    assert cell.parse_args(["--workload", "java", "--cell", "arm-stock"]).runs == 3


@pytest.mark.parametrize("argv", [
    ["--workload", "go", "--arc", "m7g"],                        # java only
    ["--workload", "java", "--arc", "m4"],                       # not a family of the arc
    ["--workload", "java", "--arc", "m7g", "--cell", "arm-stock"],
])
def test_arc_refuses_what_it_does_not_measure(argv):
    with pytest.raises(SystemExit):
        cell.parse_args(argv)


def test_arc_cells_map_to_their_instance_type():
    assert config.instance_type("arc-m6i") == "m6i.4xlarge"
    assert config.node_cell("arc-m6i") == "arc"
    assert config.exclusive_cpus("arc-m6i") == config.DEFAULT_EXCLUSIVE_CPUS


# --- the NodePool patch --------------------------------------------------------

@pytest.mark.parametrize("family,pool,arch", [("m7g", "aad-arc-arm64", "arm64"),
                                              ("m5", "aad-arc-amd64", "amd64")])
def test_the_nodepool_patch_changes_only_the_family(family, pool, arch):
    name, body = cell.arc_nodepool_patch(family)
    assert name == pool
    assert body == {"spec": {"template": {"spec": {"requirements": [
        {"key": "karpenter.k8s.aws/instance-family", "operator": "In", "values": [family]},
        {"key": "karpenter.k8s.aws/instance-size", "operator": "In", "values": ["4xlarge"]},
        {"key": "kubernetes.io/arch", "operator": "In", "values": [arch]},
        {"key": "karpenter.sh/capacity-type", "operator": "In", "values": ["on-demand"]},
    ]}}}}


# --- placement ------------------------------------------------------------------

def _java(rendered):
    return next(d for d in yaml.safe_load_all(rendered) if d and d["kind"] == "Deployment")


@pytest.mark.parametrize("family,stock", [("m7g", "arm-stock"), ("m6i", "x86-stock")])
def test_the_arc_overlay_is_stock_on_the_arc_node_only(family, stock):
    assert cell.overlay("java", f"arc-{family}").endswith(f"/java/overlays/{stock}")
    pod = _java(cell.kustomize_overlay("java", f"arc-{family}", {"A": "1"}))["spec"]["template"]["spec"]
    assert pod["nodeSelector"] == {"aad/role": "arc",
                                   "node.kubernetes.io/instance-type": f"{family}.4xlarge"}
    assert "tolerations" not in pod
    env = {e["name"]: e["value"] for e in pod["containers"][0]["env"]}
    assert env["JAVA_TOOL_OPTIONS"] == "-Xms24g -Xmx24g"  # the stock overlay's
    assert env["A"] == "1"  # --app-env still lands next to the arc patch


def test_a_task7_overlay_keeps_its_node_group():
    pod = _java(cell.kustomize_overlay("java", "arm-stock"))["spec"]["template"]["spec"]
    assert pod["nodeSelector"] == {"aad/cell": "arm-stock"}


# --- the plan -------------------------------------------------------------------

def test_the_arc_plan_patches_the_pool_and_runs_five_minutes(plan, monkeypatch):
    applied = {}
    real = cell.apply_stdin
    monkeypatch.setattr(cell, "apply_stdin",
                        lambda text, what: (applied.__setitem__(what, text), real(text, what)))
    out = plan("--workload", "java", "--arc", "m8g")
    assert "kubectl patch nodepool aad-arc-arm64 --type merge" in out
    assert "update-nodegroup-config" not in out
    # the node is waited for after the apply: Karpenter needs the Pending pod
    assert out.index("apply overlay java/arc-m8g") < out.index(
        "-l aad/role=arc,node.kubernetes.io/instance-type=m8g.4xlarge")
    job = yaml.safe_load(applied["job/k6-java-arc-m8g-r1-g1"])
    env = {e["name"]: e["value"] for e in job["spec"]["template"]["spec"]["containers"][0]["env"]}
    assert env["DURATION"] == f"{config.ARC_FIXED_SECONDS}s"
    assert "--- run 2/" not in out


def test_the_arc_does_not_abort_on_a_shared_cpuset(plan, monkeypatch):
    monkeypatch.setattr(cell, "check_cpuset", lambda *a: ["cpuset is 16 vCPUs, expected 15"])
    assert "--- run 1/1 ---" in plan("--workload", "java", "--arc", "m9g")


@pytest.mark.parametrize("exc", [RuntimeError("boom"), KeyboardInterrupt()])
def test_the_arc_node_is_released_when_the_cell_dies(plan, monkeypatch, capsys, exc):
    def die(*a):
        raise exc

    monkeypatch.setattr(cell, "check_cpuset", die)
    with pytest.raises(type(exc)):
        plan("--workload", "java", "--arc", "m6g")
    out = capsys.readouterr().out
    assert "kubectl delete -k" in out and "overlays/arm-stock" in out
    assert "# wait for no node with aad/role=arc" in out
    assert out.index("kubectl delete -k") < out.index("# wait for no node with aad/role=arc")


# --- the ledger ---------------------------------------------------------------------

def test_an_arc_type_without_a_rate_is_todo_not_a_crash(tmp_path):
    md = tmp_path / "cost.md"
    md.write_text("| instance | usd_per_hour |\n|---|---|\n| m9g.4xlarge | 2.00 |\n"
                  "| c8i.16xlarge | 0.5 |\n| m7g.large | 0.1 |\n| eks-control-plane | 0.1 |\n\n"
                  "- estimate_per_day_usd: 10\n- fixed_hours_per_day: 1\n")
    for name, itype in (("arc-m9g", "m9g.4xlarge"), ("arc-m7g", "m7g.4xlarge")):
        d = tmp_path / "day" / "java" / name
        d.mkdir(parents=True)
        (d / "cell.json").write_text(json.dumps(
            {"workload": "java", "cell": name, "instance_type": itype, "nodes": 1, "minutes": 30.0}))
    text = cost.ledger(tmp_path / "day", md)
    assert "| java | arc-m7g | m7g.4xlarge | 1 | 30.0 | TODO |" in text
    assert "| java | arc-m9g | m9g.4xlarge | 1 | 30.0 | 1.00 |" in text
    assert "TODO: no rate in cost.md for m7g.4xlarge" in text
    assert cost.day_total(tmp_path / "day", md) == (pytest.approx(1.0 + 0.7), 10.0)
