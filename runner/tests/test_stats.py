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
    assert s["invalid_runs"] == []
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
    assert s["invalid_runs"] == [{"run": "run-3", "reasons": ["http_req_failed rate 0.200 > 0.01"]}]
    assert s["runs"] == 2
    assert s["rps"]["max"] == 200.0


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


def test_mongo_uses_the_read_line_of_ycsb(tmp_path):
    cell = tmp_path / "mongo" / "x86-tuned"
    (cell / "run-1").mkdir(parents=True)
    shutil.copy(FIXTURES / "ycsb-t64.txt", cell / "run-1" / "ycsb.txt")
    s = stats.summarize(cell, usd_per_hour=1.0)
    assert s["rps"]["median"] == 951.2
    assert s["p99_ms"]["median"] == 1.3
    assert round(s["usd_per_kop"], 8) == round(1.0 / (951.2 * 3.6), 8)


def test_an_empty_cell_directory_summarizes_to_zero_runs(tmp_path):
    cell = tmp_path / "java" / "x86-stock"
    cell.mkdir(parents=True)
    s = stats.summarize(cell)
    assert s["runs"] == 0
    assert "p99_ms" not in s
