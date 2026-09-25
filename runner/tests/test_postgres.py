"""PostgreSQL 18.6 + pgbench select-only (speaker ruling R2, 2026-09-25).

The fixtures pgbench-knee-c1/c2.txt and pgbench-fixed-c1/c2.txt are real
pgbench 18.6 output through the Job's own script, captured on a laptop (their
first line says so): the format is real, the numbers are not the lab's.
"""

import json
import math
import re
import shutil
from collections import Counter

import pytest
import yaml

import cell
import config
import knee
from analysis import stats

FIXTURES = config.RUNNER / "tests" / "fixtures"
SPEC = config.WORKLOADS["postgres"]


def _fx(name):
    return (FIXTURES / name).read_text()


def _pgbench(tps, count, hist, failed=0, seconds=60):
    """A pgbench 18.6 stdout in the printResults format, plus the histogram."""
    lines = "\n".join(f"{n:>7} {us}" for us, n in sorted(hist.items()))
    return (f"transaction type: <builtin: select only>\nscaling factor: 1000\n"
            f"query mode: simple\nnumber of clients: 8\nnumber of threads: 8\n"
            f"maximum number of tries: 1\nduration: {seconds} s\n"
            f"number of transactions actually processed: {count}\n"
            f"number of failed transactions: {failed} (0.000%)\n"
            f"latency average = 0.100 ms\ninitial connection time = 3.000 ms\n"
            f"tps = {tps:.6f} (without initial connection time)\n"
            f"{knee.PGBENCH_MARKER}\n{lines}\n")


def _step(p99_us, samples=20000, tps=50000.0):
    """One client's step: `samples` sampled latencies, 2 % of them at p99_us, so
    the nearest-rank p99 is p99_us."""
    slow = samples // 50
    return _pgbench(tps, int(tps * 60), {100: samples - slow, p99_us: slow})


# --- config -------------------------------------------------------------------

def test_the_postgres_workload_has_the_six_db_cells_and_two_pgbench_clients():
    assert SPEC["loader"] == "pgbench"
    assert SPEC["resource"] == "statefulset/postgres"
    assert SPEC["cells"] == config.WORKLOADS["mongo"]["cells"]
    assert SPEC["pgbench_clients"] == 2
    assert cell.check_pgbench_clients(dict(SPEC)) is None


@pytest.mark.parametrize("override, what", [
    ({"clients": [16, 33]}, "clients 33"),
    ({"clients": [1]}, "clients 1"),
])
def test_a_client_count_that_does_not_split_stops_the_cell(override, what):
    with pytest.raises(SystemExit, match=what):
        cell.check_pgbench_clients(dict(SPEC, **override))


def test_a_ladder_above_max_connections_stops_the_cell_before_anything_is_paid():
    with pytest.raises(SystemExit, match="max_connections"):
        cell.check_pgbench_clients(dict(SPEC, clients=[16, 1024]))
    with pytest.raises(SystemExit, match="max_connections"):
        cell.check_pgbench_clients(dict(SPEC), {"PG_MAX_CONNECTIONS": "100"})


# --- Job YAML -----------------------------------------------------------------

def _script(text):
    return yaml.safe_load(text)["spec"]["template"]["spec"]["containers"][0]["args"][-1]


def test_a_knee_step_splits_clients_across_two_unthrottled_pgbench_jobs(monkeypatch):
    seen = []
    monkeypatch.setattr(cell, "run_jobs", lambda jobs, timeout: seen.extend(jobs) or ["", ""])
    names, _ = cell.run_pgbench(dict(SPEC), "pgbench-run-arm-tuned-c64-knee", "arm-tuned",
                                64, 0, 60)
    assert names == ["pgbench-run-arm-tuned-c64-knee-c1", "pgbench-run-arm-tuned-c64-knee-c2"]
    for name, text in seen:
        doc = yaml.safe_load(text)
        pod = doc["spec"]["template"]["spec"]
        script = _script(text)
        assert doc["metadata"]["name"] == name
        assert doc["metadata"]["labels"] == {"aad/cell": "arm-tuned"}
        assert pod["nodeSelector"] == {"aad/role": "loader"}
        assert "pgbench -S -c 32 -j 8 -T 60" in script
        assert " -R " not in script  # -R 0 is fatal in pgbench 18.6
        assert f"--sampling-rate={SPEC['sampling_rate']}" in script
        assert knee.PGBENCH_MARKER in script
        # -j never exceeds the vCPUs the Job asks for
        assert pod["containers"][0]["resources"]["requests"]["cpu"] == "8"


def test_a_fixed_run_splits_the_rate_and_small_steps_cap_threads_at_clients(monkeypatch):
    seen = []
    monkeypatch.setattr(cell, "run_jobs", lambda jobs, timeout: seen.extend(jobs) or ["", ""])
    cell.run_pgbench(dict(SPEC), "x", "x86-stock", 8, 10000, 480)
    for _, text in seen:
        assert "pgbench -S -c 4 -j 4 -T 480 -R 5000 " in _script(text)
        assert yaml.safe_load(text)["spec"]["template"]["spec"]["containers"][0][
            "resources"]["requests"]["cpu"] == "4"


def test_the_init_job_loads_the_configured_scale_server_side():
    doc = yaml.safe_load(cell.pgbench_job_yaml("pgbench-init-2026-09-25", None, dict(SPEC),
                                               None, None, None, init=True))
    args = doc["spec"]["template"]["spec"]["containers"][0]["args"]
    assert args == ["-i", "-s", str(SPEC["scale"]), "-I", "dtGvp"]


# --- parse and merge ------------------------------------------------------------

def test_parse_pgbench_reads_the_summary_and_the_histogram():
    p = knee.parse_pgbench(_fx("pgbench-knee-c1.txt"))
    assert p["count"] == 1889218 and p["failed"] == 0 and p["seconds"] == 10
    assert p["tps"] == pytest.approx(188999.384247)
    assert p["hist"][16] == 13 and p["hist"][1261] == 1


def test_two_clients_merge_into_one_report_parse_ycsb_reads():
    texts = [_fx("pgbench-knee-c1.txt"), _fx("pgbench-knee-c2.txt")]
    parts = [knee.parse_pgbench(t) for t in texts]
    merged = knee.parse_ycsb(knee.merge_pgbench(texts))
    hist = Counter()
    for p in parts:
        hist.update(p["hist"])
    ordered = sorted(hist.elements())
    p99 = ordered[math.ceil(0.99 * len(ordered)) - 1]
    for line in ("READ", "TOTAL"):
        assert merged[line]["Count"] == sum(p["count"] for p in parts)
        assert merged[line]["OPS"] == pytest.approx(sum(p["tps"] for p in parts), abs=0.1)
        assert merged[line]["Samples"] == len(ordered)
        assert merged[line]["99th(us)"] == p99  # exact: the histograms add up
        assert merged[line]["Max(us)"] == ordered[-1]
    assert knee.series_from_ycsb([(16, knee.merge_pgbench(texts))]) == [(16, p99 / 1000.0)]


def test_a_client_without_a_summary_is_no_report():
    died = "pgbench: error: connection to server failed\n" + knee.PGBENCH_MARKER + "\n"
    assert knee.parse_pgbench(died) is None
    assert knee.merge_pgbench([died, _fx("pgbench-knee-c2.txt")]) == ""
    assert knee.merge_pgbench(["", ""]) == ""


def test_too_few_samples_or_any_failure_makes_a_step_unusable():
    line = knee.parse_ycsb(knee.merge_pgbench([_step(900, samples=4000)] * 2))["READ"]
    assert knee.pgbench_reasons(line, 10000) == [
        "8000 sampled transactions < 10000: p99 not resolved"]
    failed = knee.parse_ycsb(knee.merge_pgbench(
        [_pgbench(1000.0, 60000, {100: 20000}, failed=3)]))["READ"]
    assert knee.pgbench_reasons(failed, 10000) == ["3 failed transactions"]


# --- the knee ladder ------------------------------------------------------------

def _ladder(monkeypatch, steps, seen=None):
    def fake(jobs, timeout):
        if seen is not None:
            seen.extend(jobs)
        return [steps[int(re.search(r"-c(\d+)-knee", jobs[0][0]).group(1))] for _ in jobs]

    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(cell, "run_jobs", fake)
    monkeypatch.setattr(cell, "kn", lambda *a, **k: "")
    monkeypatch.setattr(cell, "job_failure", lambda name: "Events: OOMKilled")


def test_the_knee_is_the_last_step_under_the_slo_and_the_ladder_stops_at_the_crossing(
        monkeypatch, tmp_path):
    seen = []
    _ladder(monkeypatch, {16: _step(900, tps=40000.0), 32: _step(3000, tps=70000.0),
                          64: _step(9000, tps=80000.0), 128: ""}, seen)
    result = cell.pgbench_knee(dict(SPEC, clients=[16, 32, 64, 128]), "arm-stock", tmp_path)
    assert result["knee"] == 32 and result["unit"] == "clients"
    assert result["ops"] == pytest.approx(140000.0)  # both clients' tps at the knee
    assert result["ended_by"]["kind"] == "crossing" and result["ended_by"]["step"] == 64
    assert result["invalid"] == []
    assert not any("-c128-" in name for name, _ in seen)  # past the crossing: not paid for
    assert (tmp_path / "knee-c32.txt").exists() and (tmp_path / "knee-c32-c2.txt").exists()


def test_an_under_sampled_step_under_the_slo_is_unresolved_not_a_knee(monkeypatch, tmp_path):
    _ladder(monkeypatch, {16: _step(900), 32: _step(900, samples=2000)})
    result = cell.pgbench_knee(dict(SPEC, clients=[16, 32]), "arm-stock", tmp_path)
    assert result["knee"] == 16
    assert result["ended_by"]["kind"] == "unresolved"
    assert "p99 not resolved" in result["invalid_steps"][32]
    assert result["invalid"][0].startswith("capacity_unresolved: step 32 clients")


def test_a_step_with_no_report_breaks_the_ladder(monkeypatch, tmp_path):
    _ladder(monkeypatch, {16: _step(900), 32: ""})
    with pytest.raises(RuntimeError, match="OOMKilled"):
        cell.pgbench_knee(dict(SPEC, clients=[16, 32]), "arm-stock", tmp_path)


def test_a_ladder_that_never_crosses_is_not_a_knee(monkeypatch, tmp_path):
    _ladder(monkeypatch, {16: _step(900), 32: _step(900)})
    result = cell.pgbench_knee(dict(SPEC, clients=[16, 32]), "arm-stock", tmp_path)
    assert "ladder_never_crossed" in result["invalid"][0]


# --- fixed run --------------------------------------------------------------------

def test_a_fixed_run_is_throttled_to_80_percent_and_judged_on_the_merge(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(cell, "run_jobs", lambda jobs, timeout: seen.extend(jobs) or [
        _fx("pgbench-fixed-c1.txt"), _fx("pgbench-fixed-c2.txt")])
    (tmp_path / "knee.json").write_text(json.dumps({"knee": 16, "ops": 5001.0}))
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    meta = {}
    cell.measure(dict(SPEC, fixed_seconds=10, min_samples=500), "postgres", "arm-stock", 1,
                 run_dir, meta, None)
    assert meta["target_ops"] == 4000 and meta["clients"] == 16  # 0.8 x 5001 -> even
    assert all("-R 2000 " in _script(text) for _, text in seen)
    assert (run_dir / "pgbench-c2.txt").read_text() == _fx("pgbench-fixed-c2.txt")
    parsed = knee.parse_ycsb((run_dir / "pgbench.txt").read_text())
    assert parsed["TOTAL"]["OPS"] == pytest.approx(
        sum(knee.parse_pgbench(_fx(f"pgbench-fixed-c{c}.txt"))["tps"] for c in (1, 2)), abs=0.1)
    # 3982 tps >= 0.95 x 4000, p99 4.48 ms < 5 ms, 1942 samples >= 500: valid.
    assert "invalid" not in meta
    # The same report under a 4 ms SLO: the throttled p99 (it counts from the
    # scheduled start, so the schedule lag is in it) is over it.
    meta = {}
    cell.measure(dict(SPEC, fixed_seconds=10, min_samples=500, slo_ms=4), "postgres",
                 "arm-stock", 1, run_dir, meta, None)
    assert [r.split(":")[0] for r in meta["invalid"]] == ["fixed_over_slo"]


def test_a_fixed_run_below_the_sample_floor_is_invalid(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(cell, "run_jobs", lambda jobs, timeout: [_step(900, samples=100)] * 2)
    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    meta = {}
    cell.measure(dict(SPEC), "postgres", "arm-stock", 1, run_dir, meta, None)
    assert any("p99 not resolved" in r for r in meta["invalid"])


# --- prepare: init once per day, prewarm, warm until EBS stops reading ------------

class _Pod:
    """statefulset/postgres as psql and cat see it."""

    def __init__(self, initialised="t", branches=None, io=("0", "0"), knobs="16GB|48GB|600|try|off"):
        self.initialised, self.branches, self.io = initialised, branches, list(io)
        self.knobs, self.sql = knobs, []

    def __call__(self, *args, **kw):
        cmd = list(args)
        if "psql" in cmd:
            sql = cmd[-1]
            self.sql.append(sql)
            if "to_regclass" in sql:
                return self.initialised
            if "pgbench_branches" in sql:
                return str(self.branches if self.branches is not None else SPEC["scale"])
            if "pg_database_size" in sql:
                return f"16013451264|{self.knobs}"
            return "1"
        if "io.stat" in " ".join(cmd):
            rbytes = self.io.pop(0)
            return "" if rbytes is None else f"259:0 rbytes={rbytes} wbytes=1\nend\n"
        return ""


def _prepare(monkeypatch, pod, reload=False):
    jobs = []
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(cell, "kn", pod)
    monkeypatch.setattr(cell, "run_job", lambda name, text, timeout: jobs.append(name) or "")
    monkeypatch.setattr(cell, "run_jobs", lambda j, timeout: jobs.extend(n for n, _ in j) or [])
    meta = {}
    cell.postgres_prepare(dict(SPEC), "arm-tuned", meta, "2026-09-25", reload=reload)
    return jobs, meta


def test_a_loaded_dataset_is_reused_prewarmed_and_recorded(monkeypatch):
    jobs, meta = _prepare(monkeypatch, _Pod(io=("0", str(8192 * 100))))
    assert not any(j.startswith("pgbench-init") for j in jobs)
    assert jobs == ["pgbench-run-arm-tuned-warm0-c1", "pgbench-run-arm-tuned-warm0-c2"]
    pg = meta["postgres"]
    assert pg["database_bytes"] == 16013451264
    assert pg["huge_pages_status"] == "off" and pg["shared_buffers"] == "16GB"
    assert pg["warmup_read_pages"] == [100]


def test_an_empty_database_is_initialised_and_checked_again(monkeypatch):
    pod = _Pod(initialised="f")
    real = pod.__call__

    def after_init(*args, **kw):  # the init Job ran: the tables are there now
        if "pgbench-init-2026-09-25" in jobs_seen:
            pod.initialised = "t"
        return real(*args, **kw)

    jobs_seen = []
    monkeypatch.setattr(cell, "run_job", lambda name, text, timeout: jobs_seen.append(name))
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(cell, "kn", after_init)
    monkeypatch.setattr(cell, "run_jobs", lambda j, timeout: [])
    cell.postgres_prepare(dict(SPEC), "arm-tuned", {}, "2026-09-25")
    assert jobs_seen == ["pgbench-init-2026-09-25"]


def test_an_init_that_did_not_finish_refuses_to_be_measured(monkeypatch):
    with pytest.raises(RuntimeError, match="init_incomplete"):
        _prepare(monkeypatch, _Pod(initialised="f"))


def test_a_dataset_of_another_scale_refuses_to_be_measured(monkeypatch):
    with pytest.raises(RuntimeError, match="scale_mismatch.*--reload"):
        _prepare(monkeypatch, _Pod(branches=100))


def test_an_unreadable_io_stat_fails_the_warm_up_control(monkeypatch):
    with pytest.raises(RuntimeError, match="cache_unreadable"):
        _prepare(monkeypatch, _Pod(io=(None,)))


def test_the_warm_up_repeats_until_ebs_reads_go_flat(monkeypatch):
    big, flat = str(8192 * 50000), str(8192 * 50000 + 8192 * 10)
    jobs, meta = _prepare(monkeypatch, _Pod(io=("0", big, big, flat)))
    assert meta["postgres"]["warmup_read_pages"] == [50000, 10]
    assert [j for j in jobs if j.endswith("-c1")] == [
        "pgbench-run-arm-tuned-warm0-c1", "pgbench-run-arm-tuned-warm1-c1"]


# --- the whole cell, dry run --------------------------------------------------------

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


def test_a_postgres_cell_plans_end_to_end(plan, monkeypatch):
    applied = []
    real = cell.apply_stdin
    monkeypatch.setattr(cell, "apply_stdin", lambda text, what: applied.append(what) or real(text, what))
    out = plan("--workload", "postgres", "--cell", "arm-tuned", "--runs", "1")
    jobs = [w for w in applied if w.startswith("job/")]
    assert jobs[0] == "job/pgbench-init-" + re.search(r"=== (\S+)", out).group(1)
    assert "job/pgbench-run-arm-tuned-warm0-c1" in jobs
    assert "job/pgbench-run-arm-tuned-c16-knee-c2" in jobs
    assert jobs[-2:] == ["job/pgbench-run-arm-tuned-c16-r1-c1", "job/pgbench-run-arm-tuned-c16-r1-c2"]
    assert "pg_prewarm" in out and "/sys/fs/cgroup/io.stat" in out
    assert "postgres overlay kept" in out  # the dataset survives the cell
    assert "--scaling-config desiredSize=0" in out


def test_teardown_drops_the_postgres_statefulset(plan):
    assert "delete sts mongo postgres --ignore-not-found" in plan("--teardown-day")


# --- stats reads the merged report ----------------------------------------------------

def test_stats_reads_pgbench_txt_like_ycsb_txt(tmp_path):
    run = tmp_path / "postgres" / "arm-stock" / "run-1"
    run.mkdir(parents=True)
    (run.parent / "knee.json").write_text(json.dumps({"slo_ms": 5}))
    (run / "pgbench.txt").write_text(knee.merge_pgbench([_step(900)] * 2))
    (run / "meta.json").write_text(json.dumps({"target_ops": 80000}))
    s = stats.summarize(run.parent)
    assert s["runs"] == 1 and s["p99_ms"]["median"] == 0.9 and s["rps"]["median"] == 100000.0


# --- overlays -----------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("kubectl") is None, reason="kubectl is not installed")
@pytest.mark.parametrize("cell_name", SPEC["cells"])
def test_every_postgres_overlay_renders_on_its_node_group(cell_name):
    docs = [d for d in yaml.safe_load_all(cell.kustomize_overlay("postgres", cell_name)) if d]
    sts = next(d for d in docs if d["kind"] == "StatefulSet")
    pod = sts["spec"]["template"]["spec"]
    c = pod["containers"][0]
    env = {e["name"]: e["value"] for e in c["env"]}
    assert pod["nodeSelector"] == {"aad/cell": cell_name}
    assert c["image"] == "postgres:18.6"
    assert c["resources"]["requests"] == c["resources"]["limits"]  # Guaranteed QoS
    assert env["PG_MAX_CONNECTIONS"] == "600"
    tuned = cell_name.endswith("-tuned")
    assert env["PG_SHARED_BUFFERS"] == ("16GB" if tuned else "128MB")
    assert env["PG_EFFECTIVE_CACHE_SIZE"] == ("48GB" if tuned else "4GB")
    assert "shared_buffers=$(PG_SHARED_BUFFERS)" in c["args"]
