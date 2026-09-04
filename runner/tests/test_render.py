"""The Job templates render into valid YAML with nothing left unfilled."""

import shutil

import pytest
import yaml

import cell
import config

ECR = "123456789012.dkr.ecr.us-east-1.amazonaws.com"


def test_the_k6_job_is_valid_yaml_and_carries_the_env():
    doc = yaml.safe_load(cell.k6_job_yaml("k6-java-arm-tuned-r1", "arm-tuned", "java.js",
                                          {"MODE": "fixed", "RATE": 2000}))
    container = doc["spec"]["template"]["spec"]["containers"][0]
    assert doc["metadata"]["name"] == "k6-java-arm-tuned-r1"
    assert doc["spec"]["backoffLimit"] == 0
    assert doc["spec"]["template"]["spec"]["nodeSelector"] == {"aad/role": "loader"}
    assert container["env"] == [{"name": "MODE", "value": "fixed"},
                                {"name": "RATE", "value": "2000"}]
    assert cell.SUMMARY_MARKER in container["command"][-1]
    assert "/scripts/java.js" in container["command"][-1]


def test_every_job_the_runner_renders_is_labelled_with_its_cell():
    """The label the cell deletes its own Jobs by at the end of the cell."""
    k6 = yaml.safe_load(cell.k6_job_yaml("k6-java-x86-t15-r1", "x86-t15", "java.js", {}))
    ycsb = yaml.safe_load(
        cell.ycsb_job_yaml("ycsb-run-arm-tuned-t64-r1", "arm-tuned",
                           config.WORKLOADS["mongo"], 64, 900, 432000)
    )
    iperf = yaml.safe_load(
        cell.render(config.MANIFESTS / "workloads" / "net" / "base" / "iperf3-client-job.yaml",
                    NAME="iperf3-client-arm-tuned-fwd-r1", CELL="arm-tuned")
    )
    assert k6["metadata"]["labels"] == {"aad/cell": "x86-t15"}
    assert ycsb["metadata"]["labels"] == {"aad/cell": "arm-tuned"}
    assert iperf["metadata"]["labels"] == {"aad/cell": "arm-tuned"}


def test_an_env_value_yaml_would_swallow_survives_the_render():
    """A bare "value: {v}" turned any quote, backslash or leading '*' in an
    --env into either a parse error or a different value. JSON scalars are
    valid YAML scalars, so json.dumps is the whole fix."""
    hostile = {"PROMPT": 'say "hi": *now*', "PATHS": "C:\\tmp", "EMPTY": ""}
    doc = yaml.safe_load(cell.k6_job_yaml("k6-x", "arm-tuned", "inference.js", hostile))
    env = doc["spec"]["template"]["spec"]["containers"][0]["env"]
    assert {e["name"]: e["value"] for e in env} == hostile


def test_the_ycsb_run_template_fills_every_placeholder():
    spec = config.WORKLOADS["mongo"]
    doc = yaml.safe_load(
        cell.ycsb_job_yaml("ycsb-run-arm-tuned-t64-r1", "arm-tuned", spec, 64, 900, 432000)
    )
    args = doc["spec"]["template"]["spec"]["containers"][0]["args"]
    assert doc["metadata"]["name"] == "ycsb-run-arm-tuned-t64-r1"
    assert "operationcount=432000" in args
    assert f"recordcount={spec['recordcount']}" in args
    assert args[args.index("--threads") + 1] == "64"
    assert args[args.index("--target") + 1] == "900"


def test_a_template_with_an_unknown_placeholder_is_refused(tmp_path):
    t = tmp_path / "job.yaml"
    t.write_text("name: __NAME__\ncell: __CELL__\n")
    with pytest.raises(RuntimeError, match="__CELL__"):
        cell.render(t, NAME="x")


def test_cpuset_size_counts_ranges_and_singletons():
    assert cell.cpuset_size("1-15") == 15
    assert cell.cpuset_size("0-15") == 16
    assert cell.cpuset_size("1-7") == 7
    assert cell.cpuset_size("2,4,6-8") == 5


# --- the own images get their registry back at render time -------------------

def test_a_job_template_renders_with_the_registry_and_tag_of_the_day():
    """The templates say `aad-iperf3:UNSET` in git; nothing but the runner knows
    which account they are pulled from."""
    doc = yaml.safe_load(
        cell.render(config.MANIFESTS / "workloads" / "net" / "base" / "iperf3-client-job.yaml",
                    NAME="iperf3-client-arm-tuned-fwd-r1", CELL="arm-tuned")
    )
    image = doc["spec"]["template"]["spec"]["containers"][0]["image"]
    assert image == f"{ECR}/aad-iperf3:2026-09-19"


def test_rendering_without_a_registry_is_refused(monkeypatch):
    """An empty cell.IMAGES used to render `None/aad-ycsb:None` and only fail in
    the cluster, on a node that is already billing."""
    monkeypatch.setattr(cell, "IMAGES", {})
    with pytest.raises(RuntimeError, match="load_images"):
        cell.render(config.MANIFESTS / "workloads" / "mongo" / "base" / "ycsb-load-job.yaml",
                    NAME="ycsb-load-2026-09-19")


@pytest.mark.skipif(shutil.which("kubectl") is None, reason="kubectl is not installed")
@pytest.mark.parametrize("workload, cell_name, own_image", [
    ("java", "arm-tuned", "aad-java"),
    ("go", "x86-stock", "aad-go"),
    # mongo's overlay carries the upstream mongo:8.0.29 image, not an own one -
    # aad-ycsb only shows up in the Job templates outside this kustomization
    # (cell.JOB_TEMPLATES). Rendered here to prove a workload with no own image
    # in its overlay still goes through the throwaway kustomization cleanly.
    ("mongo", "x86-stock", None),
    # inference is entirely third-party images (curlimages/curl, llama.cpp);
    # same reasoning as mongo.
    ("inference", "x86-t15", None),
    ("net", "arm-tuned", "aad-iperf3"),
])
def test_an_overlay_renders_through_the_throwaway_kustomization(workload, cell_name, own_image):
    """The images transformer runs from a temp dir outside the repo, so the
    resources entry has to be a relative path: kustomize refuses an absolute one
    with "new root ... cannot be absolute", and the cell would die after the node
    group is already up. One overlay (go/x86-stock) used to be the only one ever
    exercised through kustomize_overlay(); every workload's kustomization.yaml is
    shaped differently (mongo and net drop resources that are not listed at all,
    inference has no own image), so each is rendered here."""
    rendered = cell.kustomize_overlay(workload, cell_name)
    assert cell.UNSET_TAG not in rendered
    if own_image:
        assert f"{ECR}/{own_image}:2026-09-19" in rendered
