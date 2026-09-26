"""PostgreSQL 18.6 + pgbench select-only (speaker ruling R2, 2026-09-25).

The fixtures pgbench-knee-c1/c2.txt, pgbench-fixed-c1/c2.txt and
pgbench-aborted.txt are real pgbench 18.6 output through the Job's own script,
captured on a laptop (their first line says so): the format is real, the
numbers are not the lab's.
"""

import json
import math
import re
import shutil
from collections import Counter
from types import SimpleNamespace

import pytest
import yaml

import capture
import cell
import config
import knee
from analysis import stats

FIXTURES = config.RUNNER / "tests" / "fixtures"
SPEC = config.WORKLOADS["postgres"]


def _fx(name):
    return (FIXTURES / name).read_text()


def _hist(h):
    return "".join(f"{n:>7} {us}\n" for us, n in sorted(h.items()))


def _pgbench(tps, count, hist, failed=0, seconds=60, lag=None, rc=0, samples=None):
    """A pgbench 18.6 stdout in the printResults format, then what the Job
    script prints after it: rc, samples, the service histogram, the lag one."""
    samples = sum(hist.values()) if samples is None else samples
    return (f"transaction type: <builtin: select only>\nscaling factor: 1000\n"
            f"query mode: simple\nnumber of clients: 8\nnumber of threads: 8\n"
            f"maximum number of tries: 1\nduration: {seconds} s\n"
            f"number of transactions actually processed: {count}\n"
            f"number of failed transactions: {failed} (0.000%)\n"
            f"latency average = 0.100 ms\ninitial connection time = 3.000 ms\n"
            f"tps = {tps:.6f} (without initial connection time)\n"
            f"{knee.PGBENCH_MARKER}\nrc={rc}\nsamples={samples}\n{_hist(hist)}"
            f"{knee.PGBENCH_LAG_MARKER}\n{_hist(lag or {})}")


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
    # 10 connections stay free for the runner's psql and the reserved slots
    with pytest.raises(SystemExit, match="max_connections"):
        cell.check_pgbench_clients(dict(SPEC), {"PG_MAX_CONNECTIONS": "520"})
    assert cell.check_pgbench_clients(dict(SPEC), {"PG_MAX_CONNECTIONS": "522"}) is None


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
        assert "pgbench -S -c 32 -j 16 -T 60" in script
        assert " -R " not in script  # -R 0 is fatal in pgbench 18.6
        assert f"--sampling-rate={SPEC['sampling_rate']}" in script
        assert knee.PGBENCH_MARKER in script
        # -j never exceeds the vCPUs the Job asks for
        assert pod["containers"][0]["resources"]["requests"]["cpu"] == "16"
        assert f"echo {knee.PGBENCH_LAG_MARKER}" in script and "echo rc=$rc" in script


def test_a_fixed_run_splits_the_rate_and_small_steps_cap_threads_at_clients(monkeypatch):
    seen = []
    monkeypatch.setattr(cell, "run_jobs", lambda jobs, timeout: seen.extend(jobs) or ["", ""])
    cell.run_pgbench(dict(SPEC), "x", "x86-stock", 8, 10000, 480)
    for _, text in seen:
        assert "pgbench -S -c 4 -j 4 -T 480 -R 5000 " in _script(text)
        assert yaml.safe_load(text)["spec"]["template"]["spec"]["containers"][0][
            "resources"]["requests"]["cpu"] == "4"


def test_the_init_job_loads_the_configured_scale_server_side_and_is_the_cells():
    doc = yaml.safe_load(cell.pgbench_job_yaml("pgbench-init-2026-09-25", "arm-tuned", dict(SPEC),
                                               None, None, None, init=True))
    args = doc["spec"]["template"]["spec"]["containers"][0]["args"]
    assert args == ["-i", "-s", str(SPEC["scale"]), "-I", "dtGvp"]
    assert doc["metadata"]["labels"] == {"aad/cell": "arm-tuned"}  # M6


def test_sixteen_threads_per_process_and_a_lag_budget_by_default():
    assert SPEC["pgbench_threads"] == 16
    assert SPEC["pg_max_lag_p99_ms"] is None  # lag reported, not judged


# --- parse and merge ------------------------------------------------------------

def test_parse_pgbench_reads_the_summary_and_the_histograms():
    p = knee.parse_pgbench(_fx("pgbench-knee-c1.txt"))
    assert p["count"] == 2465849 and p["failed"] == 0 and p["seconds"] == 10
    assert p["tps"] == pytest.approx(246664.177867)
    assert p["hist"][16] == 6530 and sum(p["hist"].values()) == p["samples"] == 123122
    assert p["lag"] == {}  # no -R, no lag column
    fixed = knee.parse_pgbench(_fx("pgbench-fixed-c1.txt"))
    assert sum(fixed["lag"].values()) == fixed["samples"] == 944


def test_an_aborted_or_failed_pgbench_is_no_report():
    """I1: an aborted run still prints a plausible tps line (419k here); only
    rc=2 and "Run was aborted" say the numbers are incomplete."""
    aborted = _fx("pgbench-aborted.txt")
    assert "tps = 419253" in aborted and "rc=2" in aborted
    assert knee.parse_pgbench(aborted) is None
    assert knee.parse_pgbench(aborted.replace("rc=2", "rc=0")) is None  # the abort line alone
    assert knee.parse_pgbench(_pgbench(1000.0, 60000, {100: 20000}, rc=1)) is None
    assert knee.merge_pgbench([aborted, _fx("pgbench-knee-c2.txt")]) == ""


def test_a_throttled_run_whose_lag_histogram_does_not_add_up_is_no_report():
    """N2: under -R the lag gate reads the lag histogram; an empty or cut one
    would read as no lag at all. pgbench prints "rate limit schedule lag" only
    with -R (printResults), so that line says the lag histogram must be whole."""
    fixed = _fx("pgbench-fixed-c1.txt")
    assert knee.parse_pgbench(fixed) is not None
    head, _, _ = fixed.partition(knee.PGBENCH_LAG_MARKER)
    assert knee.parse_pgbench(head + knee.PGBENCH_LAG_MARKER + "\n") is None  # empty
    lag_lines = fixed.partition(knee.PGBENCH_LAG_MARKER)[2].strip().splitlines()
    cut = head + knee.PGBENCH_LAG_MARKER + "\n" + "\n".join(lag_lines[:-1]) + "\n"
    assert knee.parse_pgbench(cut) is None  # truncated
    # unthrottled: no lag line in the summary, no lag histogram expected
    assert knee.parse_pgbench(_fx("pgbench-knee-c1.txt"))["lag"] == {}


def test_a_histogram_that_does_not_add_up_to_its_samples_is_no_report():
    """M4: a truncated log (kubectl logs cut, a killed sort) loses lines."""
    assert knee.parse_pgbench(_pgbench(1000.0, 60000, {100: 20000}, samples=20001)) is None
    no_count = _pgbench(1000.0, 60000, {100: 20000}).replace("samples=20000\n", "")
    assert knee.parse_pgbench(no_count) is None


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
        assert merged[line]["MinProcSamples"] == min(p["samples"] for p in parts)
        assert merged[line]["Procs"] == 2
        assert merged[line]["99th(us)"] == p99  # exact: the histograms add up
        assert merged[line]["Max(us)"] == ordered[-1]
    assert knee.series_from_ycsb([(16, knee.merge_pgbench(texts))]) == [(16, p99 / 1000.0)]


def test_a_client_without_a_summary_is_no_report():
    died = "pgbench: error: connection to server failed\n" + knee.PGBENCH_MARKER + "\nrc=1\n"
    assert knee.parse_pgbench(died) is None
    assert knee.merge_pgbench([died, _fx("pgbench-knee-c2.txt")]) == ""
    assert knee.merge_pgbench(["", ""]) == ""


def test_too_few_samples_or_any_failure_makes_a_step_unusable():
    line = knee.parse_ycsb(knee.merge_pgbench([_step(900, samples=4000)] * 2))["READ"]
    assert knee.pgbench_reasons(line, 10000) == [
        "8000 sampled transactions < 10000: p99 not resolved",
        "a pgbench process logged 4000 sampled transactions < 10000/2: p99 not resolved"]
    # M3: the sum passes, one process alone does not
    lopsided = knee.parse_ycsb(knee.merge_pgbench(
        [_step(900, samples=12000), _step(900, samples=3000)]))["READ"]
    assert knee.pgbench_reasons(lopsided, 10000) == [
        "a pgbench process logged 3000 sampled transactions < 10000/2: p99 not resolved"]
    failed = knee.parse_ycsb(knee.merge_pgbench(
        [_pgbench(1000.0, 60000, {100: 20000}, failed=3)]))["READ"]
    assert knee.pgbench_reasons(failed, 10000) == ["3 failed transactions"]


def test_zero_samples_is_a_report_with_no_latency_and_its_own_reason():
    """I4: every process answered, none logged a transaction."""
    empty = [_pgbench(0.0, 0, {})] * 2
    line = knee.parse_ycsb(knee.merge_pgbench(empty))["READ"]
    assert line["Samples"] == 0 and "99th(us)" not in line
    assert knee.pgbench_reasons(line, 10000)[0].startswith("no_latency_samples")


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


def test_an_aborted_step_breaks_the_ladder(monkeypatch, tmp_path):
    _ladder(monkeypatch, {16: _step(900), 32: _fx("pgbench-aborted.txt")})
    with pytest.raises(RuntimeError, match="no pgbench report"):
        cell.pgbench_knee(dict(SPEC, clients=[16, 32]), "arm-stock", tmp_path)


def test_a_step_with_no_samples_is_unresolved_not_a_knee(monkeypatch, tmp_path):
    _ladder(monkeypatch, {16: _step(900), 32: _pgbench(0.0, 0, {})})
    result = cell.pgbench_knee(dict(SPEC, clients=[16, 32]), "arm-stock", tmp_path)
    assert result["knee"] == 16 and result["ended_by"]["kind"] == "unresolved"
    assert result["invalid_steps"][32].startswith("no_latency_samples")


def test_the_knee_records_each_steps_jobs_and_threads_for_the_pod_guard(monkeypatch, tmp_path):
    _ladder(monkeypatch, {16: _step(900), 64: _step(9000)})
    result = cell.pgbench_knee(dict(SPEC, clients=[16, 64]), "arm-stock", tmp_path)
    assert result["jobs"][64] == ["pgbench-run-arm-stock-c64-knee-c1",
                                  "pgbench-run-arm-stock-c64-knee-c2"]
    assert result["threads"] == {16: 8, 64: 16}


def test_a_peak_inside_the_ladder_is_a_knee_even_without_an_end(monkeypatch, tmp_path):
    """arm-tuned with THP for shmem, 2026-09-26: 337.2k tps at 256 clients, 321.4k
    at 512 (95.3 %: no drop) with p99 3.2 ms (no crossing). The peak is inside the
    ladder, so the silicon set it, not the ladder's top."""
    _ladder(monkeypatch, {16: _step(900, tps=80000.0), 32: _step(900, tps=160000.0),
                          64: _step(900, tps=153000.0)})
    result = cell.pgbench_knee(dict(SPEC, clients=[16, 32, 64]), "arm-stock", tmp_path)
    assert result["knee"] == 32 and result["ended_by"] is None
    assert result["invalid"] == []


def test_a_ladder_still_rising_at_its_top_is_not_a_knee(monkeypatch, tmp_path):
    _ladder(monkeypatch, {16: _step(900, tps=80000.0), 32: _step(900, tps=160000.0)})
    result = cell.pgbench_knee(dict(SPEC, clients=[16, 32]), "arm-stock", tmp_path)
    assert result["invalid"][0].startswith("ladder_never_crossed: the top step (32 clients)")


# --- fixed run --------------------------------------------------------------------

def _fixed(monkeypatch, tmp_path, logs, knee_json, spec=None, app_env=None):
    seen = []
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(cell, "run_jobs", lambda jobs, timeout: seen.extend(jobs) or list(logs))
    monkeypatch.setattr(cell, "job_failure", lambda name: "Events: OOMKilled")
    (tmp_path / "knee.json").write_text(json.dumps(knee_json))
    run_dir = tmp_path / "run-1"
    run_dir.mkdir(exist_ok=True)
    meta = {}
    cell.measure(dict(SPEC, **(spec or {})), "postgres", "arm-stock", 1, run_dir, meta,
                 SimpleNamespace(app_env=app_env or {}))
    return seen, run_dir, meta


def test_a_fixed_run_doubles_the_knee_clients_and_judges_service_latency_and_lag(
        monkeypatch, tmp_path):
    """C1: under -R, -c only caps what is in flight, so the fixed run gets 2x
    the knee's sessions; the SLO judges the service latency (time - lag) and the
    lag, the generator's own, is judged against pg_max_lag_p99_ms."""
    texts = [_fx("pgbench-fixed-c1.txt"), _fx("pgbench-fixed-c2.txt")]
    seen, run_dir, meta = _fixed(monkeypatch, tmp_path, texts, {"knee": 16, "ops": 5001.0},
                                 {"fixed_seconds": 10, "min_samples": 500,
                                  "fixed_clients_factor": 2})
    assert meta["target_ops"] == 4000 and meta["clients"] == 32 and meta["knee_clients"] == 16
    assert all("pgbench -S -c 16 -j 16 -T 10 -R 2000 " in _script(text) for _, text in seen)
    assert meta["pgbench_jobs"] == [name for name, _ in seen] and meta["pgbench_threads"] == 16
    assert (run_dir / "pgbench-c2.txt").read_text() == texts[1]
    parts = [knee.parse_pgbench(t) for t in texts]
    service, lag = Counter(), Counter()
    for p in parts:
        service.update(p["hist"])
        lag.update(p["lag"])
    service, lag = sorted(service.elements()), sorted(lag.elements())
    parsed = knee.parse_ycsb((run_dir / "pgbench.txt").read_text())["READ"]
    assert parsed["99th(us)"] == service[math.ceil(0.99 * len(service)) - 1]
    assert parsed["LagP99(us)"] == lag[math.ceil(0.99 * len(lag)) - 1]
    assert parsed["LagMax(us)"] == lag[-1]
    assert parsed["OPS"] == pytest.approx(sum(p["tps"] for p in parts), abs=0.1)
    # The service p99 is inside the SLO; the lag (1.59 / 3.37 ms) is recorded,
    # not judged, by default (speaker ruling 2026-09-26)...
    assert parsed["99th(us)"] < 5000 and parsed["LagP99(us)"] > 1000
    assert "invalid" not in meta
    assert meta["lag_p99_ms"] == parsed["LagP99(us)"] / 1000.0
    assert meta["lag_max_ms"] == parsed["LagMax(us)"] / 1000.0
    # ...and a budget re-enables the gate.
    _, _, gated = _fixed(monkeypatch, tmp_path, texts, {"knee": 16, "ops": 5001.0},
                         {"fixed_seconds": 10, "min_samples": 500, "pg_max_lag_p99_ms": 1.0})
    assert [r.split(":")[0] for r in gated["invalid"]] == ["fixed_generator_lagging"]


def test_the_fixed_clients_are_capped_by_max_connections(monkeypatch, tmp_path):
    seen, _, meta = _fixed(monkeypatch, tmp_path, [_step(900)] * 2, {"knee": 512, "ops": 9e4},
                           {"fixed_clients_factor": 2})
    assert meta["clients"] == 590  # min(1024, 600 - 10), even
    assert all("-c 295 " in _script(text) for _, text in seen)
    _, _, meta = _fixed(monkeypatch, tmp_path, [_step(900)] * 2, {"knee": 512, "ops": 9e4},
                        {"fixed_clients_factor": 2}, app_env={"PG_MAX_CONNECTIONS": "700"})
    assert meta["clients"] == 690


def test_a_fixed_run_below_the_sample_floor_is_invalid(monkeypatch, tmp_path):
    _, _, meta = _fixed(monkeypatch, tmp_path, [_step(900, samples=100)] * 2,
                        {"knee": 16, "ops": 1.0})
    assert any("p99 not resolved" in r for r in meta["invalid"])


def test_a_fixed_run_with_no_samples_is_invalid(monkeypatch, tmp_path):
    _, run_dir, meta = _fixed(monkeypatch, tmp_path, [_pgbench(0.0, 0, {})] * 2,
                              {"knee": 16, "ops": 1.0})
    assert any(r.startswith("no_latency_samples") for r in meta["invalid"])
    assert (run_dir / "pgbench.txt").exists()


def test_an_aborted_fixed_run_is_no_summary(monkeypatch, tmp_path):
    _, _, meta = _fixed(monkeypatch, tmp_path, [_fx("pgbench-aborted.txt"), _step(900)],
                        {"knee": 16, "ops": 1.0})
    assert meta["invalid"] == ["no_summary: job/pgbench-run-arm-stock-c16-r1-c1"]


# --- the loader guard per pgbench pod (I2) ---------------------------------------------

def _pods(window, **cores):
    return {"ts": "2026-09-25T10:00:00+00:00", "loader_pods_window": list(window),
            "loader_pods": {pod: round(c * 1000) for pod, c in cores.items()}}


def test_parse_pod_metrics_keeps_the_loader_pods_and_their_window():
    body = json.dumps({"items": [
        {"metadata": {"name": "pgbench-run-x-c64-knee-c1-abcde"},
         "timestamp": "2026-09-25T10:00:20Z", "window": "20s",
         "containers": [{"name": "pgbench", "usage": {"cpu": "15000000000n", "memory": "1Mi"}}]},
        {"metadata": {"name": "postgres-0"}, "timestamp": "2026-09-25T10:00:20Z",
         "window": "20s", "containers": [{"name": "postgres", "usage": {"cpu": "14", "memory": "1Mi"}}]},
    ]})
    pods, window = capture.parse_pod_metrics(body, "pgbench-")
    assert pods == {"pgbench-run-x-c64-knee-c1-abcde": 15000}
    assert window[1] - window[0] == 20
    assert capture.parse_pod_metrics("not json", "pgbench-") is None


def test_a_pgbench_pod_at_its_thread_count_makes_the_step_loader_invalid():
    result = {"windows": {16: (0, 70), 64: (70, 140)}, "ended_by": {"step": 64, "kind": "crossing"},
              "jobs": {16: ["pgbench-run-x-c16-knee-c1", "pgbench-run-x-c16-knee-c2"],
                       64: ["pgbench-run-x-c64-knee-c1", "pgbench-run-x-c64-knee-c2"]},
              "threads": {16: 8, 64: 16}, "invalid": []}
    samples = [_pods((10, 30), **{"pgbench-run-x-c16-knee-c1-aaaaa": 7.3,   # 0.91 x 8
                                  "pgbench-run-x-c16-knee-c2-ccccc": 7.1}),
               _pods((90, 110), **{"pgbench-run-x-c64-knee-c1-ddddd": 9.0,
                                   "pgbench-run-x-c64-knee-c2-bbbbb": 10.0})]
    cell.pgbench_knee_guard(result, samples)
    assert result["invalid"] == [
        "loader_pgbench_saturated: step 16: pgbench-run-x-c16-knee-c1-aaaaa 7.30 cores "
        ">= 0.9 x 8 threads"]
    assert result["pgbench_pod_cores_by_step"][64] == {"pgbench-run-x-c64-knee-c1-ddddd": 9.0,
                                                       "pgbench-run-x-c64-knee-c2-bbbbb": 10.0}


def test_the_crossing_step_is_waived_when_the_sut_was_saturated():
    result = {"windows": {64: (0, 70)}, "ended_by": {"step": 64, "kind": "crossing"},
              "jobs": {64: ["pgbench-run-x-c64-knee-c1"]}, "threads": {64: 16}, "invalid": [],
              "loader_guard_waived": {"step": 64}}
    cell.pgbench_knee_guard(result, [_pods((10, 30), **{"pgbench-run-x-c64-knee-c1-a": 15.5})])
    assert result["invalid"] == []


def test_steps_past_the_end_of_the_walk_are_not_guarded():
    result = {"windows": {16: (0, 70), 32: (70, 140)}, "ended_by": {"step": 16, "kind": "crossing"},
              "jobs": {16: ["j16"], 32: ["j32"]}, "threads": {16: 8, 32: 16}, "invalid": []}
    cell.pgbench_knee_guard(result, [_pods((10, 30), **{"j16-a": 1.0}),
                                     _pods((90, 110), **{"j32-a": 16.0})])
    assert result["invalid"] == []


def test_a_guarded_step_with_a_pgbench_pod_nobody_sampled_is_unresolved():
    """N1: the node guard cannot trip on pgbench (2 x 16 threads is 50 % of the
    loader), so the pod guard is the one that must fail closed: every Job of
    every guarded step needs at least one pod sample."""
    result = {"windows": {16: (0, 70), 32: (70, 140)}, "ended_by": {"step": 32, "kind": "crossing"},
              "jobs": {16: ["j16-c1", "j16-c2"], 32: ["j32-c1", "j32-c2"]},
              "threads": {16: 8, 32: 16}, "invalid": [], "loader_guard_waived": {"step": 32}}
    samples = [_pods((10, 30), **{"j16-c1-a": 1.0, "j16-c2-b": 1.0}),
               _pods((90, 110), **{"j32-c1-a": 1.0}),
               {"ts": "2026-09-25T10:00:00+00:00", "loader_cpu_percent": 20}]  # no loader pods
    cell.pgbench_knee_guard(result, samples)
    # the waiver excuses saturation at the crossing, not the lack of an observation
    assert result["invalid"] == ["capacity_unresolved: no pgbench pod sample for step 32 "
                                 "(job/j32-c2)"]


def test_a_knee_with_no_pod_samples_at_all_is_unresolved():
    result = {"windows": {16: (0, 70)}, "ended_by": None, "jobs": {16: ["j16-c1"]},
              "threads": {16: 8}, "invalid": []}
    cell.pgbench_knee_guard(result, [{"ts": "2026-09-25T10:00:00+00:00"}])
    assert result["invalid"] == ["capacity_unresolved: no pgbench pod sample for step 16 "
                                 "(job/j16-c1)"]


def test_a_fixed_run_with_an_unsampled_pgbench_pod_is_loader_unobserved():
    meta = {"pgbench_jobs": ["r1-c1", "r1-c2"], "pgbench_threads": 16}
    reasons = cell.pgbench_run_guard(meta, [_pods((10, 30), **{"r1-c1-z": 3.0})], 0, 100)
    assert reasons == ["loader_unobserved: no pgbench pod sample for job/r1-c2"]


def test_the_dry_run_plan_has_no_pod_samples_and_that_is_not_a_reason(monkeypatch):
    monkeypatch.setattr(config, "DRY_RUN", True)
    result = {"windows": {16: (0, 70)}, "ended_by": None, "jobs": {16: ["j16-c1"]},
              "threads": {16: 8}, "invalid": []}
    cell.pgbench_knee_guard(result, [])
    assert result["invalid"] == []
    assert cell.pgbench_run_guard({"pgbench_jobs": ["r1-c1"], "pgbench_threads": 16}, [], 0, 1) == []


def test_a_fixed_run_pod_at_its_thread_count_is_loader_invalid():
    meta = {"pgbench_jobs": ["pgbench-run-x-c32-r1-c1"], "pgbench_threads": 16}
    reasons = cell.pgbench_run_guard(meta, [_pods((10, 30), **{"pgbench-run-x-c32-r1-c1-z": 14.5})],
                                     0, 100)
    assert reasons == ["loader_pgbench_saturated: run: pgbench-run-x-c32-r1-c1-z 14.50 cores "
                       ">= 0.9 x 16 threads"]
    assert meta["pgbench_pod_cores"] == {"pgbench-run-x-c32-r1-c1-z": 14.5}


def test_pgbench_pods_are_loader_pods_not_the_sut_pod():
    pods = "postgres-0   3000m   100Mi\npgbench-run-x-c1-abcde   15000m   10Mi\n"
    assert capture.parse_top("", pods, "sut", "loader")["pod_cpu_millicores"] == 3000


# --- prepare: init once per day, prewarm, warm until EBS stops reading ------------

class _Pod:
    """statefulset/postgres as psql and cat see it."""

    def __init__(self, initialised="t", branches=None, io=("8192", "8192"),
                 knobs="16GB|48GB|600|try|off", prewarm="2150000"):
        self.initialised, self.branches, self.io = initialised, branches, list(io)
        self.knobs, self.sql, self.prewarm = knobs, [], prewarm

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
            if "pg_prewarm(" in sql:
                return self.prewarm
            return ""
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
    first, last = str(8192 * 2_000_000), str(8192 * 2_000_100)
    jobs, meta = _prepare(monkeypatch, _Pod(io=(first, last)))
    assert not any(j.startswith("pgbench-init") for j in jobs)
    assert jobs == ["pgbench-run-arm-tuned-warm0-c1", "pgbench-run-arm-tuned-warm0-c2"]
    pg = meta["postgres"]
    assert pg["database_bytes"] == 16013451264
    assert pg["huge_pages_status"] == "off" and pg["shared_buffers"] == "16GB"
    assert pg["warmup_read_pages"] == [100]
    assert pg["prewarm_blocks"] == 2150000  # M1
    assert pg["io_stat_first"] == f"259:0 rbytes={first} wbytes=1"  # M2: raw, both ends
    assert pg["io_stat_last"] == f"259:0 rbytes={last} wbytes=1"


def test_a_prewarm_that_returns_no_block_count_fails_the_cell(monkeypatch):
    with pytest.raises(RuntimeError, match="prewarm_failed"):
        _prepare(monkeypatch, _Pod(prewarm="ERROR:  relation does not exist"))


def test_io_stat_that_never_counted_the_prewarm_is_unreadable(monkeypatch):
    """M2: after reading ~17 GB from EBS, zero rbytes means io.stat is not
    counting this container's reads (io controller not enabled)."""
    with pytest.raises(RuntimeError, match="cache_unreadable.*rbytes"):
        _prepare(monkeypatch, _Pod(io=("0", "0")))


def test_zero_rbytes_right_after_this_cells_init_is_recorded_not_fatal(monkeypatch):
    """The init wrote the dataset through this node's page cache, so the
    prewarm read nothing from disk: zero proves nothing either way."""
    pod = _Pod(initialised="f", io=("0", "0"))
    real = pod.__call__

    def after_init(*args, **kw):
        if jobs_seen:
            pod.initialised = "t"
        return real(*args, **kw)

    jobs_seen = []
    monkeypatch.setattr(cell, "run_job", lambda name, text, timeout: jobs_seen.append(name))
    monkeypatch.setattr(config, "DRY_RUN", False)
    monkeypatch.setattr(cell, "kn", after_init)
    monkeypatch.setattr(cell, "run_jobs", lambda j, timeout: [])
    meta = {}
    cell.postgres_prepare(dict(SPEC), "arm-tuned", meta, "2026-09-25")
    assert "io_stat_unverified" in meta["postgres"]


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
    base = 8192 * 2_000_000
    big, flat = str(base + 8192 * 50000), str(base + 8192 * 50010)
    # one io.stat read per pass: each pass's end is the next one's start
    jobs, meta = _prepare(monkeypatch, _Pod(io=(str(base), big, flat)))
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


@pytest.mark.parametrize("workload, other", [("postgres", "mongo"), ("mongo", "postgres")])
def test_a_db_cell_scales_the_other_db_to_zero_before_its_overlay(plan, workload, other):
    """I3: both StatefulSets tolerate the SUT taint; the other one's pod would
    land on this cell's node whenever its last nodeSelector matches it."""
    out = plan("--workload", workload, "--cell", "arm-tuned", "--runs", "1")
    scale_line = f"$ kubectl -n aad scale statefulset/{other} --replicas=0"
    assert scale_line in out
    assert out.index(scale_line) < out.index(f"# apply overlay {workload}/arm-tuned")


@pytest.mark.parametrize("workload", ["postgres", "mongo"])
def test_a_db_cell_recreates_its_own_pod_from_the_new_template(plan, workload):
    """postgres amd-stock 2026-09-25: after the arm node left, <db>-0 came back
    Pending from the old template and RollingUpdate never replaced it."""
    out = plan("--workload", workload, "--cell", "amd-stock", "--runs", "1")
    own = f"$ kubectl -n aad scale statefulset/{workload} --replicas=0"
    gone = f"$ kubectl -n aad wait --for=delete pod/{workload}-0 --timeout=300s"
    assert own in out and gone in out
    assert out.index(own) < out.index(gone) < out.index(f"# apply overlay {workload}/amd-stock")


@pytest.mark.parametrize("workload", ["java", "go", "inference", "net"])
def test_every_cell_parks_both_dbs_before_its_overlay(plan, workload):
    """java x86-tuned 2026-09-26: postgres-0 kept replicas 1 and the x86-tuned
    selector from the PG calibration, landed on the Java SUT node and took its
    CPU; only DB cells used to park the other DB."""
    cell = "arm-tuned" if workload != "go" else "arm-stock"
    out = plan("--workload", workload, "--cell", cell, "--runs", "1")
    for db in ("mongo", "postgres"):
        line = f"$ kubectl -n aad scale statefulset/{db} --replicas=0"
        assert line in out
        assert out.index(line) < out.index(f"# apply overlay {workload}/{cell}")


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


def test_stats_excludes_a_pgbench_run_with_no_latency_samples(tmp_path):
    run = tmp_path / "postgres" / "arm-stock" / "run-1"
    run.mkdir(parents=True)
    (run / "pgbench.txt").write_text(knee.merge_pgbench([_pgbench(0.0, 0, {})] * 2))
    s = stats.summarize(run.parent)
    assert s["runs"] == 0
    assert s["excluded"] == [{"run": "run-1", "reasons": ["no_latency_samples: pgbench.txt"]}]


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


def test_the_fixed_clients_factor_can_be_set_from_the_cli(plan):
    """A/B of the fixed-run sessions (Task 7 day 2: 2x the knee's clients ran
    arm-stock at 14.2-14.4/15 cores at 80 % of the knee)."""
    out = plan("--workload", "postgres", "--cell", "arm-stock", "--runs", "1",
               "--fixed-clients-factor", "1")
    assert "pgbench-run-arm-stock-c16-r1-c1" in out  # dry-run knee = 16 clients, x1


def test_the_fixed_run_uses_the_knee_clients_by_default(monkeypatch, tmp_path):
    """A/B arm-stock, Task 7 day 2: 2x the knee's sessions was load the knee
    never carried (14.2-14.4 vs 12.8-13.2 cores at the same 230k tps)."""
    assert SPEC["fixed_clients_factor"] == 1
    _, _, meta = _fixed(monkeypatch, tmp_path, [_step(900)] * 2, {"knee": 256, "ops": 9e4})
    assert meta["clients"] == meta["knee_clients"] == 256
