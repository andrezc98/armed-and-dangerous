"""summarize() reads run-*/ and turns raw outputs into the numbers a slide shows."""

import json
import shutil
from pathlib import Path

from analysis import stats

FIXTURES = Path(__file__).parent / "fixtures"


def _k6_cell(tmp_path):
    """Three java runs: p99 x0.9 / x1.0 / x1.1 and rps 190 / 200 / 210."""
    base = json.loads((FIXTURES / "java-fixed.json").read_text())
    cell = tmp_path / "java" / "arm-tuned"
    for i, (scale, rps) in enumerate([(0.9, 190.0), (1.0, 200.0), (1.1, 210.0)], start=1):
        run = json.loads(json.dumps(base))
        values = run["metrics"]["http_req_duration"]["values"]
        run["metrics"]["http_req_duration"]["values"] = {k: v * scale for k, v in values.items()}
        run["metrics"]["http_reqs"]["values"]["rate"] = rps
        d = cell / f"run-{i}"
        d.mkdir(parents=True)
        (d / "k6.json").write_text(json.dumps(run))
    return cell


def test_summarize_gives_median_and_spread_over_the_runs(tmp_path):
    s = stats.summarize(_k6_cell(tmp_path))
    assert s["workload"] == "java"
    assert s["cell"] == "arm-tuned"
    assert s["runs"] == 3
    assert s["excluded"] == []
    assert "insufficient_runs" not in s
    assert s["rps"] == {"median": 200.0, "min": 190.0, "max": 210.0}
    assert round(s["p99_ms"]["median"], 6) == 4.573517
    assert round(s["p99_ms"]["min"], 6) == round(4.573517 * 0.9, 6)
    assert round(s["p99_ms"]["max"], 6) == round(4.573517 * 1.1, 6)


def test_usd_per_kop_is_the_hourly_rate_over_kilo_ops_per_hour(tmp_path):
    s = stats.summarize(_k6_cell(tmp_path), usd_per_hour=1.0)
    # 200 rps -> 720 kop/h -> 1 USD / 720 kop
    assert round(s["usd_per_kop"], 8) == round(1.0 / 720.0, 8)


def test_without_a_rate_there_is_no_derived_cost(tmp_path):
    s = stats.summarize(_k6_cell(tmp_path))
    assert "usd_per_kop" not in s


def test_summarize_reads_the_knee_file_when_the_cell_has_one(tmp_path):
    cell = _k6_cell(tmp_path)
    (cell / "knee.json").write_text(json.dumps({"knee": 2600, "slo_ms": 100, "unit": "rps"}))
    assert stats.summarize(cell)["knee"]["knee"] == 2600


def test_a_run_with_failures_is_reported_invalid_and_left_out_of_the_medians(tmp_path):
    cell = _k6_cell(tmp_path)
    bad = json.loads((cell / "run-3" / "k6.json").read_text())
    bad["metrics"]["http_req_failed"]["values"]["rate"] = 0.2
    (cell / "run-3" / "k6.json").write_text(json.dumps(bad))
    s = stats.summarize(cell)
    assert s["excluded"] == [{"run": "run-3", "reasons": ["http_req_failed rate 0.200 > 0.01"]}]
    assert s["runs"] == 2
    assert s["rps"]["max"] == 200.0
    assert s["insufficient_runs"] is True


def test_usd_per_mtok_from_the_llama_token_counter(tmp_path):
    cell = tmp_path / "inference" / "arm-tuned"
    (cell / "run-1").mkdir(parents=True)
    shutil.copy(FIXTURES / "llama-fixed.json", cell / "run-1" / "llama.json")
    s = stats.summarize(cell, usd_per_hour=0.72)
    # 36000 predicted tokens / 360 s = 100 tok/s; 0.72 USD/h / (100*3600 tok/h) * 1e6
    assert s["tok_s"]["median"] == 100.0
    assert round(s["usd_per_mtok"], 6) == 2.0


def test_cpu_per_gbps_from_iperf_plus_top(tmp_path):
    cell = tmp_path / "net" / "arm-tuned"
    (cell / "run-1").mkdir(parents=True)
    shutil.copy(FIXTURES / "iperf3-forward.json", cell / "run-1" / "iperf.json")
    shutil.copy(FIXTURES / "top-net.json", cell / "run-1" / "top.json")
    s = stats.summarize(cell)
    assert round(s["gbps"]["median"], 3) == 170.774
    assert s["node_cpu_cores"]["median"] == 8.0
    # 8 cores / 170.774255733856 Gbps
    assert round(s["cpu_per_gbps"], 4) == 0.0468


def test_mongo_latency_is_read_p99_and_throughput_is_total_ops(tmp_path):
    """--target throttles every operation and workloadb is 95/5, so READ OPS
    under-reported what the server carried by the 5 % of updates."""
    cell = tmp_path / "mongo" / "x86-tuned"
    (cell / "run-1").mkdir(parents=True)
    shutil.copy(FIXTURES / "ycsb-t64.txt", cell / "run-1" / "ycsb.txt")
    s = stats.summarize(cell, usd_per_hour=1.0)
    assert s["rps"]["median"] == 1001.1
    assert s["p99_ms"]["median"] == 1.3
    assert round(s["usd_per_kop"], 8) == round(1.0 / (1001.1 * 3.6), 8)


def test_an_empty_cell_directory_summarizes_to_zero_runs(tmp_path):
    cell = tmp_path / "java" / "x86-stock"
    cell.mkdir(parents=True)
    s = stats.summarize(cell)
    assert s["runs"] == 0
    assert "p99_ms" not in s


def test_a_run_the_runner_marked_invalid_is_excluded_from_the_medians(tmp_path):
    """meta.json is authoritative: a saturated loader or a Job that printed
    nothing is not visible in the output files the analysis reads."""
    cell = _k6_cell(tmp_path)
    (cell / "run-3" / "meta.json").write_text(
        json.dumps({"invalid": ["loader node CPU 88% > 70%"]})
    )
    s = stats.summarize(cell)
    assert s["excluded"] == [{"run": "run-3", "reasons": ["loader node CPU 88% > 70%"]}]
    assert s["runs"] == 2
    assert s["rps"]["max"] == 200.0


def test_a_meta_json_without_invalidations_keeps_the_run(tmp_path):
    cell = _k6_cell(tmp_path)
    for i in (1, 2, 3):
        (cell / f"run-{i}" / "meta.json").write_text(json.dumps({"aperf": "ok", "invalid": []}))
    s = stats.summarize(cell)
    assert s["runs"] == 3
    assert s["excluded"] == []


def test_fewer_than_three_valid_runs_flags_the_cell_without_raising(tmp_path):
    cell = _k6_cell(tmp_path)
    for i in (2, 3):
        (cell / f"run-{i}" / "meta.json").write_text(json.dumps({"invalid": ["no_summary"]}))
    s = stats.summarize(cell)
    assert s["runs"] == 1
    assert s["insufficient_runs"] is True
    assert s["rps"]["median"] == 190.0  # still summarised, just flagged


def test_a_truncated_ycsb_run_is_excluded_instead_of_crashing_the_analysis(tmp_path):
    """go-ycsb prints its report only if it finished. A killed run leaves a file
    with no READ line, and that used to be a KeyError over the whole cell."""
    cell = tmp_path / "mongo" / "x86-tuned"
    (cell / "run-1").mkdir(parents=True)
    (cell / "run-1" / "ycsb.txt").write_text("Run finished, takes 1m2s\n")
    s = stats.summarize(cell)
    assert s["runs"] == 0
    assert s["excluded"] == [{"run": "run-1", "reasons": ["ycsb.txt has no READ/TOTAL line"]}]


# --- fixed runs are judged against the SLO and the rate they were held at ----

def test_a_fixed_run_over_the_knee_slo_is_excluded(tmp_path):
    """java-fixed.json reads p99 4.57 ms; against a 2.5 ms knee SLO it is the
    gate's 5.26 ms case, which nothing flagged."""
    cell = _k6_cell(tmp_path)
    (cell / "knee.json").write_text(json.dumps({"knee": 40000, "slo_ms": 2.5, "unit": "rps"}))
    s = stats.summarize(cell)
    assert s["runs"] == 0
    assert s["excluded"][0]["reasons"][0].startswith("fixed_over_slo: p99 4.1")


def test_a_fixed_run_below_its_target_rate_is_excluded(tmp_path):
    cell = _k6_cell(tmp_path)  # 190 / 200 / 210 rps delivered
    for i in (1, 2, 3):
        (cell / f"run-{i}" / "meta.json").write_text(json.dumps({"rate": 210}))
    s = stats.summarize(cell)
    assert [e["run"] for e in s["excluded"]] == ["run-1"]  # 190 < 0.95 x 210
    assert "fixed_underdelivered" in s["excluded"][0]["reasons"][0]


def test_a_throttled_ycsb_run_that_missed_its_target_is_excluded(tmp_path):
    cell = tmp_path / "mongo" / "x86-tuned"
    (cell / "run-1").mkdir(parents=True)
    shutil.copy(FIXTURES / "ycsb-t64.txt", cell / "run-1" / "ycsb.txt")  # TOTAL 1001.1 ops/s
    (cell / "run-1" / "meta.json").write_text(json.dumps({"target_ops": 1200}))
    s = stats.summarize(cell)
    assert s["runs"] == 0
    assert s["excluded"][0]["reasons"][0].startswith("fixed_underdelivered: TOTAL 1001")


# --- the capacity of a cell is the spread of its runs' own knees -------------

def test_capacity_is_the_spread_of_the_run_knees(tmp_path):
    cell = _k6_cell(tmp_path)
    (cell / "knee.json").write_text(json.dumps({"knee": 30000, "slo_ms": 10, "unit": "rps"}))
    for i, k in enumerate((32000, 36000, 34000), start=1):
        (cell / f"run-{i}" / "meta.json").write_text(json.dumps({"run_knee": k}))
    assert stats.summarize(cell)["capacity"] == {"median": 34000, "min": 32000, "max": 36000}


def test_old_results_without_run_knees_fall_back_to_the_coarse_knee(tmp_path):
    cell = _k6_cell(tmp_path)
    (cell / "knee.json").write_text(json.dumps({"knee": 30000, "slo_ms": 10, "unit": "rps"}))
    assert stats.summarize(cell)["capacity"] == {"median": 30000, "min": 30000, "max": 30000}


# --- net: CPU per Gbps per direction, over the idle node ---------------------

def test_cpu_per_gbps_is_per_direction_over_an_idle_baseline(tmp_path):
    from datetime import UTC, datetime
    cell = tmp_path / "net" / "arm-tuned"
    run = cell / "run-1"
    run.mkdir(parents=True)
    shutil.copy(FIXTURES / "iperf3-forward.json", run / "iperf.json")
    shutil.copy(FIXTURES / "iperf3-forward.json", run / "iperf-reverse.json")
    t0 = 1_800_000_000

    def sample(sec, millicores):
        return {"ts": datetime.fromtimestamp(t0 + sec, UTC).isoformat(),
                "node_cpu_millicores": millicores}

    # idle 500m; forward 2500m; reverse 4500m (plus one stray idle sample)
    (run / "top.json").write_text(json.dumps(
        [sample(1, 500)] + [sample(15 + 10 * k, 2500) for k in range(6)]
        + [sample(85 + 10 * k, 4500) for k in range(6)] + [sample(140, 500)]))
    (run / "meta.json").write_text(json.dumps({"net_windows": {
        "baseline": [t0, t0 + 10], "fwd": [t0 + 12, t0 + 72], "rev": [t0 + 80, t0 + 140]}}))
    s = stats.summarize(cell)
    assert s["node_cpu_baseline_cores"]["median"] == 0.5
    assert s["node_cpu_cores_forward"]["median"] == 2.0
    assert s["node_cpu_cores_reverse"]["median"] == 4.0
    assert round(s["cpu_per_gbps"], 5) == round(2.0 / 170.774255733856, 5)
    assert round(s["cpu_per_gbps_reverse"], 5) == round(4.0 / 170.774255733856, 5)
