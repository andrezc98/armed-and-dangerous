"""The C-states knob script, run for real against a synthetic cpuidle tree.

A regular file stands in for /dev/cpu_dma_latency, so the read-back check fails
on purpose (it rereads ASCII, not the kernel's s32); what is asserted is the
value the script chose and wrote, which is the part that differs per driver."""

import subprocess

import pytest
import yaml

import config

DAEMONSET = config.MANIFESTS / "base" / "cstates-daemonset.yaml"


def _container():
    return yaml.safe_load(DAEMONSET.read_text())["spec"]["template"]["spec"]["containers"][0]


def _run(tmp_path, states):
    cpuidle = tmp_path / "cpuidle"
    for i, (name, latency) in enumerate(states):
        d = cpuidle / f"state{i}"
        d.mkdir(parents=True)
        (d / "name").write_text(f"{name}\n")
        (d / "latency").write_text(f"{latency}\n")
    dev, limit = tmp_path / "dev", tmp_path / "limit"
    dev.write_text("")
    env = {"PATH": "/usr/bin:/bin", "PMQOS_DEV": str(dev),
           "CPUIDLE_DIR": str(cpuidle), "LIMIT_FILE": str(limit)}
    proc = subprocess.run(["sh", "-c", _container()["command"][-1]], env=env,
                          capture_output=True, text=True, timeout=10)
    return proc, dev, limit


@pytest.mark.parametrize("states, want", [
    # intel_idle on m8i: C1 happens to be state1.
    ([("POLL", 0), ("C1", 2), ("C1E", 10), ("C6", 170)], 2),
    # C1 found by name wherever the driver numbers it.
    ([("POLL", 0), ("C2", 100), ("C1", 1)], 1),
    # No state spelled C1 (acpi_idle fallback names): the shallowest non-POLL.
    ([("POLL", 0), ("C2_ACPI", 50), ("C1_ACPI", 1)], 1),
])
def test_the_cstates_knob_caps_at_c1_whatever_the_driver_calls_it(tmp_path, states, want):
    proc, dev, limit = _run(tmp_path, states)
    assert dev.read_text() == f"0x{want:08x}", proc.stdout + proc.stderr
    assert limit.read_text() == str(want)
    assert f"wanted {want}" in proc.stdout  # the read-back against a plain file


def test_the_cstates_knob_refuses_a_node_with_only_poll(tmp_path):
    proc, dev, _ = _run(tmp_path, [("POLL", 0)])
    assert proc.returncode == 1
    assert "no non-POLL idle state" in proc.stdout
    assert dev.read_text() == ""


def test_the_probe_compares_against_the_limit_the_script_chose():
    probe = _container()["readinessProbe"]["exec"]["command"][-1]
    assert "LIMIT_FILE" in probe


def test_both_knob_daemonsets_reach_the_amd_tuned_cell():
    for name in ("cstates-daemonset.yaml", "net-tuned-daemonset.yaml"):
        spec = yaml.safe_load((config.MANIFESTS / "base" / name).read_text())["spec"]
        terms = spec["template"]["spec"]["affinity"]["nodeAffinity"][
            "requiredDuringSchedulingIgnoredDuringExecution"]["nodeSelectorTerms"]
        assert "amd-tuned" in terms[0]["matchExpressions"][0]["values"], name
