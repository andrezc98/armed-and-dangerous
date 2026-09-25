"""Every cell a workload lists can actually run: it has an overlay to apply, a
node group to scale, an instance behind it and a rate in results/cost.md."""

import re

import pytest

import config
import cost

NODEGROUPS_TF = config.REPO / "infra" / "nodegroups.tf"
CELLS = [(w, c) for w, spec in config.WORKLOADS.items() for c in spec["cells"]]


def _sut_node_groups():
    """Keys of node_group_defs built on local.sut_common, with their instance."""
    tf = NODEGROUPS_TF.read_text()
    out = {}
    for m in re.finditer(r'^\s*"([\w-]+)" = merge\(local\.sut_common, \{(.*?)^\s*\}\)',
                         tf, re.M | re.S):
        out[m.group(1)] = re.search(r'instance_types\s*=\s*\["([\w.]+)"\]', m.group(2)).group(1)
    return out


@pytest.mark.parametrize("workload, cell", CELLS)
def test_every_cell_has_an_overlay_and_a_node_group(workload, cell):
    overlay = config.MANIFESTS / "workloads" / workload / "overlays" / cell
    assert (overlay / "kustomization.yaml").is_file(), overlay
    groups = _sut_node_groups()
    assert config.node_cell(cell) in groups
    assert config.instance_type(cell) == groups[config.node_cell(cell)]
    assert config.instance_type(cell) in cost.rates()


def test_the_amd_column_is_in_every_workload():
    for workload, spec in config.WORKLOADS.items():
        assert "amd-stock" in spec["cells"], workload
        if workload != "go":  # go has stock cells only, on every silicon
            assert "amd-tuned" in spec["cells"], workload
    assert "amd-tuned-vthreads" in config.WORKLOADS["java"]["cells"]


def test_the_amd_cells_are_m8a_with_15_exclusive_cores():
    for c in ("amd-stock", "amd-tuned", "amd-tuned-vthreads"):
        assert config.instance_type(c) == "m8a.4xlarge"
        assert config.exclusive_cpus(c) == 15


def test_the_amd_node_groups_mirror_the_x86_ones():
    tf = NODEGROUPS_TF.read_text()

    def block(name):
        return re.search(rf'^\s*"{name}" = merge\(local\.sut_common, \{{(.*?)^\s*\}}\)',
                         tf, re.M | re.S).group(1)

    for kind in ("stock", "tuned"):
        amd, x86 = block(f"amd-{kind}"), block(f"x86-{kind}")
        assert amd.replace("amd-", "x86-").replace("m8a.", "m8i.") == x86


def test_the_az_gate_checks_every_sut_instance():
    main = (config.REPO / "infra" / "main.tf").read_text()
    required = re.search(r"required_instance_types = \[(.*?)\]", main).group(1)
    for instance in set(_sut_node_groups().values()):
        assert f'"{instance}"' in required, instance


def test_the_dry_run_fixture_knows_every_node_group():
    """--dry-run reads tests/fixtures/cluster.json in place of terraform output;
    a node group missing there is a KeyError before the plan prints."""
    import json

    import cell

    names = json.loads(cell.FIXTURE_CLUSTER.read_text())["nodegroup_names"]["value"]
    assert set(_sut_node_groups()) <= set(names)
