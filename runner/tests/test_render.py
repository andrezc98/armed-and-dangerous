"""The Job templates render into valid YAML with nothing left unfilled."""

import pytest
import yaml

import cell
import config


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
