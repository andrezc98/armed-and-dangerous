"""PostgreSQL tuned, two additions of 2026-09-25: THP for its shared memory
(the pg-shmem-thp DaemonSet, --pg-shmem-thp) and wait-event sampling.

The DaemonSet script runs for real against a regular file standing in for
/sys/kernel/mm/transparent_hugepage/shmem_enabled, in the kernel's format (the
active value in brackets)."""

import shutil
import signal
import subprocess
import time

import pytest
import yaml

import cell
import config

DAEMONSET = config.MANIFESTS / "base" / "pg-shmem-thp-daemonset.yaml"
SYSFS = "always within_size advise [never] deny force\n"
PMD = "always [inherit] within_size advise never\n"


def _spec():
    return yaml.safe_load(DAEMONSET.read_text())["spec"]["template"]["spec"]


def _start(tmp_path, pmd=PMD):
    knob = tmp_path / "shmem_enabled"
    knob.write_text(SYSFS)
    env = {"PATH": "/usr/bin:/bin", "SHMEM_FILE": str(knob), "MODE": "always",
           "PMD_FILE": str(tmp_path / "hugepages-2048kB-shmem_enabled")}
    if pmd is not None:
        (tmp_path / "hugepages-2048kB-shmem_enabled").write_text(pmd)
    proc = subprocess.Popen(["sh", "-c", _spec()["containers"][0]["command"][-1]], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return proc, knob


def _wait_for(pred, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.05)
    return False


# --- the DaemonSet ------------------------------------------------------------------

def test_the_knob_sets_always_and_restores_the_previous_value_when_deleted(tmp_path):
    """SIGTERM is what the kubelet sends when the runner deletes the DaemonSet."""
    proc, knob = _start(tmp_path)
    try:
        assert _wait_for(lambda: knob.read_text().strip() == "always")
    finally:
        proc.send_signal(signal.SIGTERM)
        out = proc.communicate(timeout=5)[0]
    assert "shmem_enabled before=never after=always" in out
    assert knob.read_text().strip() == "never"  # a regular file keeps what was written
    assert proc.returncode == 0


def test_the_knob_refuses_a_pmd_size_that_overrides_the_global_value(tmp_path):
    """The per-size knob only follows the global one when it says inherit
    (transhuge.rst); a PMD size set to never would make `always` a no-op."""
    proc, knob = _start(tmp_path, pmd="always [never] inherit within_size advise\n")
    out = proc.communicate(timeout=5)[0]
    assert proc.returncode == 1
    assert "hugepages-2048kB" in out
    assert knob.read_text() == SYSFS  # nothing was written


def test_the_knob_runs_without_a_per_size_file(tmp_path):
    """Kernels before per-size shmem THP have no hugepages-2048kB/shmem_enabled."""
    proc, knob = _start(tmp_path, pmd=None)
    try:
        assert _wait_for(lambda: knob.read_text().strip() == "always")
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.communicate(timeout=5)


def _probe(knob, mode="always"):
    probe = _spec()["containers"][0]["readinessProbe"]["exec"]["command"]
    return subprocess.run(probe, env={"PATH": "/usr/bin:/bin", "SHMEM_FILE": str(knob),
                                      "MODE": mode}, capture_output=True, timeout=5).returncode


def test_the_probe_is_ready_only_when_the_kernel_brackets_the_mode(tmp_path):
    knob = tmp_path / "shmem_enabled"
    knob.write_text("[always] within_size advise never deny force\n")
    assert _probe(knob) == 0
    knob.write_text(SYSFS)
    assert _probe(knob) != 0
    knob.write_text("always within_size [advise] never deny force\n")  # "always" unbracketed
    assert _probe(knob) != 0


def test_the_pod_mounts_only_the_thp_directory():
    """M5: not the whole /sys."""
    spec = _spec()
    assert [v["hostPath"] for v in spec["volumes"]] == [
        {"path": "/sys/kernel/mm/transparent_hugepage", "type": "Directory"}]
    env = {e["name"]: e["value"] for e in spec["containers"][0]["env"]}
    mount = spec["containers"][0]["volumeMounts"][0]["mountPath"]
    assert env["SHMEM_FILE"] == f"{mount}/shmem_enabled"
    assert env["PMD_FILE"] == f"{mount}/hugepages-2048kB/shmem_enabled"


def _docker_alpine():
    image = _spec()["containers"][0]["image"]
    if shutil.which("docker") is None:
        return None
    try:
        if subprocess.run(["docker", "image", "inspect", image], capture_output=True,
                          timeout=20).returncode and subprocess.run(
                ["docker", "pull", image], capture_output=True, timeout=120).returncode:
            return None
    except subprocess.TimeoutExpired:
        return None
    return image


def test_the_knob_script_in_the_pinned_alpine_image(tmp_path):
    """M6: the same script under the image's busybox sh/sed/sleep, not macOS's."""
    image = _docker_alpine()
    if image is None:
        pytest.skip("docker (or the pinned alpine image) is not available")
    (tmp_path / "shmem_enabled").write_text(SYSFS)
    (tmp_path / "pmd").write_text(PMD)
    name = f"aad-pg-shmem-thp-test-{int(time.time() * 1000)}"
    proc = subprocess.Popen(
        ["docker", "run", "--rm", "--name", name, "-v", f"{tmp_path}:/t",
         "-e", "MODE=always", "-e", "SHMEM_FILE=/t/shmem_enabled", "-e", "PMD_FILE=/t/pmd",
         image, "/bin/sh", "-c", _spec()["containers"][0]["command"][-1]],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        assert _wait_for(lambda: (tmp_path / "shmem_enabled").read_text().strip() == "always",
                         timeout=60)
    finally:
        subprocess.run(["docker", "kill", "--signal", "TERM", name], capture_output=True)
        out = proc.communicate(timeout=30)[0]
    assert "before=never after=always hugepages-2048kB=inherit" in out
    assert "restored to never" in out
    assert (tmp_path / "shmem_enabled").read_text().strip() == "never"


def test_the_knob_is_not_in_the_base_and_only_reaches_tuned_nodes():
    base = yaml.safe_load((config.MANIFESTS / "base" / "kustomization.yaml").read_text())
    assert DAEMONSET.name not in base["resources"]
    values = cell.pg_shmem_thp_cells()
    assert values == ["x86-tuned", "amd-tuned", "arm-tuned"]


# --- /proc/meminfo and shmem_enabled as the postgres container reads them ------------

MEMINFO = """shmem_enabled: always within_size advise [never] deny force
hugepages-2048kB: always [inherit] within_size advise never
Shmem:          17123456 kB
ShmemHugePages:  16777216 kB
ShmemPmdMapped:  16252928 kB
"""
ON = MEMINFO.replace("always within_size advise [never]", "[always] within_size advise never")


def test_parse_shmem_reads_the_active_values_and_the_counters():
    assert cell.parse_shmem(MEMINFO) == {
        "shmem_enabled": "never", "shmem_enabled_2048kB": "inherit",
        "Shmem_kB": 17123456, "ShmemHugePages_kB": 16777216, "ShmemPmdMapped_kB": 16252928}
    assert cell.parse_shmem("") == {}
    assert cell.parse_shmem(ON)["shmem_enabled"] == "always"


def test_thp_on_but_no_shmem_huge_pages_is_noted_not_fatal():
    pg = {"shmem_thp": True, "shared_buffers": "16GB"}
    assert cell.record_shmem(pg, "after_warmup", ON.replace("16777216", "0")) == []
    assert pg["after_warmup"]["ShmemHugePages_kB"] == 0
    assert pg["after_warmup"]["shmem_huge_share"] == 0
    assert pg["notes"] == ["shmem_thp_unused: after_warmup ShmemHugePages 0 kB"]
    cell.record_shmem(pg, "after_ladder", ON)
    assert len(pg["notes"]) == 1


def test_the_huge_share_is_of_shared_buffers_and_the_raw_text_is_kept():
    pg = {"shmem_thp": True, "shared_buffers": "16GB"}
    cell.record_shmem(pg, "after_ladder", ON)
    assert pg["after_ladder"]["shmem_huge_share"] == 1.0  # 16777216 kB / 16 GB
    assert pg["after_ladder"]["raw"] == ON
    pg = {"shmem_thp": False, "shared_buffers": "128MB"}
    cell.record_shmem(pg, "after_ladder", MEMINFO.replace("16777216", "65536"))
    assert pg["after_ladder"]["shmem_huge_share"] == 0.5


def test_without_the_option_zero_shmem_huge_pages_is_just_recorded():
    pg = {"shmem_thp": False}
    assert cell.record_shmem(pg, "after_warmup", MEMINFO.replace("16777216", "0")) == []
    assert "notes" not in pg


def test_a_node_left_with_shmem_thp_on_is_a_leak_that_invalidates_the_cell():
    """I1: a stock-or-without cell on a node whose shmem_enabled is not the
    default measured with the knob on."""
    reasons = cell.record_shmem({"shmem_thp": False}, "after_warmup", ON)
    assert reasons == ["shmem_thp_leak: after_warmup shmem_enabled is always without --pg-shmem-thp"]


def test_the_option_on_but_the_node_not_at_always_invalidates_the_cell():
    reasons = cell.record_shmem({"shmem_thp": True}, "after_warmup", MEMINFO)
    assert reasons == ["shmem_thp_not_applied: after_warmup shmem_enabled is never, "
                       "--pg-shmem-thp wants always"]


def test_an_unreadable_evidence_read_is_an_explicit_error_and_no_note():
    """I4: no shmem_enabled line = the exec failed; nothing is concluded from it."""
    pg = {"shmem_thp": True}
    assert cell.record_shmem(pg, "after_warmup", "error: unable to upgrade connection") == []
    assert pg["after_warmup"]["error"].startswith("no shmem_enabled")
    assert pg["after_warmup"]["raw"] == "error: unable to upgrade connection"
    assert "notes" not in pg
    # shmem_enabled read, meminfo not: no note either
    cell.record_shmem(pg, "after_ladder", ON.split("Shmem:")[0])
    assert "notes" not in pg


def test_the_before_value_falls_back_to_the_previous_container_and_warns(monkeypatch, capsys):
    logs = {(): "", ("--previous",): "shmem_enabled before=never after=always hugepages-2048kB=inherit"}
    monkeypatch.setattr(cell, "kn", lambda *a, **k: logs[a[2:]])
    pg = {}
    cell.pg_shmem_thp_before(pg)
    assert pg["shmem_enabled_before"] == "never"
    logs[("--previous",)] = ""
    cell.pg_shmem_thp_before(pg)
    assert pg["shmem_enabled_before"] is None
    assert "WARNING" in capsys.readouterr().out


# --- wait events ---------------------------------------------------------------------

def test_wait_events_add_up_per_sample_and_null_is_no_wait():
    samples = ["#|sample|0\n||12\nLWLock|BufferMapping|3\nClient|ClientRead|1\n",
               "#|sample|0\n||10\nLWLock|BufferMapping|5\n",
               "",  # an exec that answered nothing: an error, not an idle sample
               "#|sample|0\n",  # nobody connected: the step had not started
               "#|sample|0\n||4\n"]  # the ramp: 4 of 16 connected
    got = cell.aggregate_wait_events(samples, clients=16)
    assert got == {"samples": 2, "dropped": 2, "errors": 1,
                   "backends": {"NoWait": 22, "LWLock:BufferMapping": 8, "Client:ClientRead": 1}}


def test_the_sampler_query_skips_itself_and_counts_only_client_backends():
    q = cell.PG_WAIT_EVENTS_SQL
    assert "backend_type = 'client backend'" in q and "pg_backend_pid()" in q
    assert "wait_event_type" in q and "GROUP BY" in q


def test_the_sampler_takes_at_least_one_sample_with_a_timeout(monkeypatch):
    calls = []
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(cell, "kn", lambda *a, **k: calls.append((a, k)) or "#|sample|0\n||4\n")
    with cell.PgWaitSampler(4, interval=60) as w:
        pass
    assert w.summary()["backends"] == {"NoWait": 4}
    assert calls[0][0][:3] == ("exec", "statefulset/postgres", "--")
    assert calls[0][1]["timeout"] == cell.PG_WAIT_EXEC_TIMEOUT


def test_the_funnel_turns_a_timeout_into_an_error(monkeypatch):
    import subprocess as sp
    monkeypatch.setattr(config, "subprocess", sp)
    with pytest.raises(RuntimeError, match="timed out"):
        config.sh(["sleep", "5"], capture=True, timeout=0.2)


def _psql(answer):
    """kn as the ladder sees it: the sampler's psql answers, job_times reads nothing."""
    return lambda *a, **k: answer if "psql" in a else ""


def test_the_knee_records_wait_events_per_step(monkeypatch, tmp_path):
    from test_postgres import SPEC, _ladder, _step
    _ladder(monkeypatch, {16: _step(900), 32: _step(9000)})
    monkeypatch.setattr(cell, "kn", _psql("#|sample|0\n||40\n"))
    result = cell.pgbench_knee(dict(SPEC, clients=[16, 32]), "arm-stock", tmp_path)
    assert set(result["wait_events_by_step"]) == {16, 32}
    assert result["wait_events_by_step"][32]["backends"]["NoWait"] >= 40


def test_a_fixed_run_records_its_wait_events(monkeypatch, tmp_path):
    from test_postgres import _fixed, _step
    monkeypatch.setattr(cell, "kn", _psql("#|sample|0\n||40\n"))
    _, _, meta = _fixed(monkeypatch, tmp_path, [_step(900)] * 2, {"knee": 16, "ops": 5000.0})
    assert meta["wait_events_by_step"]["run"]["backends"]["NoWait"] >= 40


# --- the whole cell, dry run ------------------------------------------------------------

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


def test_the_option_applies_the_knob_before_postgres_starts_and_deletes_it_first(plan):
    out = plan("--workload", "postgres", "--cell", "arm-tuned", "--runs", "1", "--pg-shmem-thp")
    apply = f"$ kubectl apply -f {DAEMONSET}"
    ready = "$ kubectl -n aad rollout status daemonset/pg-shmem-thp --timeout=120s"
    delete = f"$ kubectl delete -f {DAEMONSET} --ignore-not-found"
    assert out.index(apply) < out.index(ready) < out.index("# apply overlay postgres/arm-tuned")
    # Deleted while the node is still there, so the pod can put the old value back.
    assert out.index(delete) < out.index("--scaling-config desiredSize=0")
    assert "/proc/meminfo" in out and "pg_stat_activity" in out
    assert f"$ kubectl delete -f {DAEMONSET} --ignore-not-found --wait" not in out


@pytest.mark.parametrize("workload, cell_name", [
    ("postgres", "arm-tuned"), ("postgres", "x86-stock"), ("java", "arm-tuned"),
    ("mongo", "amd-tuned")])
def test_every_other_cell_drops_a_leftover_knob_before_the_node_scales_up(plan, workload,
                                                                         cell_name):
    """I1: a cell that did not ask for the knob must not start next to one a
    crashed runner left behind."""
    out = plan("--workload", workload, "--cell", cell_name, "--runs", "1")
    leftover = f"$ kubectl delete -f {DAEMONSET} --ignore-not-found --wait"
    assert out.index(leftover) < out.index("--scaling-config desiredSize=1")
    assert f"$ kubectl apply -f {DAEMONSET}" not in out
    if workload == "postgres":
        assert "/proc/meminfo" in out and "pg_stat_activity" in out


def test_a_failed_leftover_delete_stops_the_cell_before_anything_is_paid(monkeypatch):
    calls = []

    def kubectl(*a, **k):
        calls.append(a)
        if a[:1] == ("delete",):
            raise RuntimeError("kubectl delete exited 1")
        return ""

    monkeypatch.setattr(cell, "kubectl", kubectl)
    with pytest.raises(RuntimeError, match="exited 1"):
        cell.drop_leftover_pg_shmem_thp()
    assert calls == [("delete", "-f", str(DAEMONSET), "--ignore-not-found", "--wait")]


def test_a_failed_final_delete_warns_and_does_not_raise(monkeypatch, capsys):
    def kubectl(*a, **k):
        raise RuntimeError("kubectl delete exited 1")

    monkeypatch.setattr(cell, "kubectl", kubectl)
    cell.delete_pg_shmem_thp()
    assert "WARNING" in capsys.readouterr().out


def test_a_knob_that_never_gets_ready_fails_with_its_own_log(monkeypatch):
    """M1: the reason the pod refused (a PMD size not at inherit, a write that
    did not stick) is in its log, not in rollout status."""
    def kn(*a, **k):
        if a[0] == "rollout":
            raise RuntimeError("timed out waiting for the condition")
        return "hugepages-2048kB/shmem_enabled is never, not inherit"

    monkeypatch.setattr(cell, "kubectl", lambda *a, **k: "")
    monkeypatch.setattr(cell, "kn", kn)
    with pytest.raises(RuntimeError, match="(?s)timed out.*not inherit"):
        cell.apply_pg_shmem_thp()


@pytest.mark.parametrize("argv", [
    ("--workload", "postgres", "--cell", "arm-stock"),
    ("--workload", "mongo", "--cell", "arm-tuned"),
])
def test_the_option_is_refused_where_it_means_nothing(plan, argv):
    with pytest.raises(SystemExit, match="pg-shmem-thp"):
        plan(*argv, "--runs", "1", "--pg-shmem-thp")


def test_teardown_drops_the_knob(plan):
    assert f"delete -f {DAEMONSET} --ignore-not-found" in plan("--teardown-day")
