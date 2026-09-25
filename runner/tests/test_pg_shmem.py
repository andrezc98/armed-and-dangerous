"""PostgreSQL tuned, two additions of 2026-09-25: THP for its shared memory
(the pg-shmem-thp DaemonSet, --pg-shmem-thp) and wait-event sampling.

The DaemonSet script runs for real against a regular file standing in for
/sys/kernel/mm/transparent_hugepage/shmem_enabled, in the kernel's format (the
active value in brackets)."""

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


def test_the_probe_reads_the_bracketed_value_back():
    probe = _spec()["containers"][0]["readinessProbe"]["exec"]["command"][-1]
    assert "SHMEM_FILE" in probe and "MODE" in probe


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


def test_parse_shmem_reads_the_active_values_and_the_counters():
    assert cell.parse_shmem(MEMINFO) == {
        "shmem_enabled": "never", "shmem_enabled_2048kB": "inherit",
        "Shmem_kB": 17123456, "ShmemHugePages_kB": 16777216, "ShmemPmdMapped_kB": 16252928}
    assert cell.parse_shmem("") == {}


def test_thp_on_but_no_shmem_huge_pages_is_noted_not_fatal():
    pg = {"shmem_thp": True}
    cell.record_shmem(pg, "after_warmup", MEMINFO.replace("16777216", "0"))
    assert pg["after_warmup"]["ShmemHugePages_kB"] == 0
    assert pg["notes"] == ["shmem_thp_unused: after_warmup ShmemHugePages 0 kB"]
    cell.record_shmem(pg, "after_ladder", MEMINFO)
    assert len(pg["notes"]) == 1


def test_without_the_option_zero_shmem_huge_pages_is_just_recorded():
    pg = {"shmem_thp": False}
    cell.record_shmem(pg, "after_warmup", MEMINFO.replace("16777216", "0"))
    assert "notes" not in pg


# --- wait events ---------------------------------------------------------------------

def test_wait_events_add_up_per_sample_and_null_is_cpu():
    samples = ["#|sample|0\n||12\nLWLock|BufferMapping|3\nClient|ClientRead|1\n",
               "#|sample|0\n||10\nLWLock|BufferMapping|5\n",
               "",  # an exec that answered nothing: an error, not an idle sample
               "#|sample|0\n"]  # nobody connected
    got = cell.aggregate_wait_events(samples)
    assert got == {"samples": 3, "errors": 1,
                   "backends": {"CPU": 22, "LWLock:BufferMapping": 8, "Client:ClientRead": 1}}


def test_the_sampler_query_skips_itself_and_counts_only_client_backends():
    q = cell.PG_WAIT_EVENTS_SQL
    assert "backend_type = 'client backend'" in q and "pg_backend_pid()" in q
    assert "wait_event_type" in q and "GROUP BY" in q


def test_the_sampler_takes_at_least_one_sample(monkeypatch):
    calls = []
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(cell, "kn", lambda *a, **k: calls.append(a) or "#|sample|0\n||4\n")
    with cell.PgWaitSampler(interval=60) as w:
        pass
    assert w.summary()["backends"] == {"CPU": 4}
    assert calls[0][:3] == ("exec", "statefulset/postgres", "--")


def _psql(answer):
    """kn as the ladder sees it: the sampler's psql answers, job_times reads nothing."""
    return lambda *a, **k: answer if "psql" in a else ""


def test_the_knee_records_wait_events_per_step(monkeypatch, tmp_path):
    from test_postgres import SPEC, _ladder, _step
    _ladder(monkeypatch, {16: _step(900), 32: _step(9000)})
    monkeypatch.setattr(cell, "kn", _psql("#|sample|0\n||7\n"))
    result = cell.pgbench_knee(dict(SPEC, clients=[16, 32]), "arm-stock", tmp_path)
    assert set(result["wait_events_by_step"]) == {16, 32}
    assert result["wait_events_by_step"][32]["backends"]["CPU"] >= 7


def test_a_fixed_run_records_its_wait_events(monkeypatch, tmp_path):
    from test_postgres import _fixed, _step
    monkeypatch.setattr(cell, "kn", _psql("#|sample|0\n||3\n"))
    _, _, meta = _fixed(monkeypatch, tmp_path, [_step(900)] * 2, {"knee": 16, "ops": 5000.0})
    assert meta["wait_events_by_step"]["run"]["backends"]["CPU"] >= 3


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
    ready = "$ kubectl -n aad rollout status daemonset/pg-shmem-thp --timeout=300s"
    delete = f"$ kubectl delete -f {DAEMONSET} --ignore-not-found"
    assert out.index(apply) < out.index(ready) < out.index("# apply overlay postgres/arm-tuned")
    # Deleted while the node is still there, so the pod can put the old value back.
    assert out.index(delete) < out.index("--scaling-config desiredSize=0")
    assert "/proc/meminfo" in out and "pg_stat_activity" in out


def test_without_the_option_there_is_no_knob_but_the_evidence_is_still_read(plan):
    out = plan("--workload", "postgres", "--cell", "arm-tuned", "--runs", "1")
    assert "pg-shmem-thp" not in out
    assert "/proc/meminfo" in out and "pg_stat_activity" in out


@pytest.mark.parametrize("argv", [
    ("--workload", "postgres", "--cell", "arm-stock"),
    ("--workload", "mongo", "--cell", "arm-tuned"),
])
def test_the_option_is_refused_where_it_means_nothing(plan, argv):
    with pytest.raises(SystemExit, match="pg-shmem-thp"):
        plan(*argv, "--runs", "1", "--pg-shmem-thp")


def test_teardown_drops_the_knob(plan):
    assert f"delete -f {DAEMONSET} --ignore-not-found" in plan("--teardown-day")
