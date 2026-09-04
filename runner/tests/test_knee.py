"""Knee = the first crossing of the SLO, not a lucky later step."""

import json
from pathlib import Path

import knee

FIXTURES = Path(__file__).parent / "fixtures"


def _summary(name):
    return json.loads((FIXTURES / name).read_text())


def test_find_returns_last_rate_below_slo():
    series = [(100, 5.0), (200, 20.0), (300, 60.0)]
    assert knee.find(series, 100) == 300
    assert knee.find(series, 30) == 200
    assert knee.find(series, 10) == 100


def test_find_returns_none_when_the_first_step_already_fails():
    assert knee.find([(100, 120.0), (200, 5.0)], 100) is None


def test_find_stops_at_the_first_crossing_not_at_a_lucky_later_step():
    # 200 breaks the SLO; 300 being fast again does not undo the knee.
    assert knee.find([(100, 10.0), (200, 50.0), (300, 20.0)], 30) == 100


def test_find_on_an_empty_series():
    assert knee.find([], 100) is None


def test_series_from_summary_reads_the_tagged_submetrics():
    series = knee.series_from_summary(_summary("java-knee.json"))
    rates = [r for r, _ in series]
    assert rates == [100, 200, 300]  # sorted, and rate:ramp is not a rate
    assert round(series[0][1], 2) == 5.66


def test_the_java_knee_fixture_has_no_knee_at_its_forced_2ms_slo():
    series = knee.series_from_summary(_summary("java-knee.json"))
    assert knee.find(series, 2) is None
    assert knee.find(series, 6) == 300


def test_series_from_summary_ignores_untagged_and_response_tagged_metrics():
    summary = {
        "metrics": {
            "http_req_duration": {"values": {"p(99)": 9.0}},
            "http_req_duration{expected_response:true}": {"values": {"p(99)": 9.0}},
            "http_req_duration{rate:ramp}": {"values": {"p(99)": 9.0}},
            "http_req_duration{rate:400}": {"values": {"p(99)": 4.0}},
        }
    }
    assert knee.series_from_summary(summary) == [(400, 4.0)]


def test_invalid_reasons_flags_failures_and_dropped_iterations():
    assert knee.invalid_reasons(_summary("java-fixed.json")) == []
    bad = {
        "metrics": {
            "http_req_failed": {"values": {"rate": 0.05}},
            "dropped_iterations": {"values": {"count": 12}},
        }
    }
    assert knee.invalid_reasons(bad) == [
        "http_req_failed rate 0.050 > 0.01",
        "dropped_iterations count 12 > 0",
    ]


def test_parse_ycsb_reads_the_read_and_total_lines():
    parsed = knee.parse_ycsb((FIXTURES / "ycsb-t64.txt").read_text())
    assert parsed["READ"]["OPS"] == 951.2
    assert parsed["READ"]["99th(us)"] == 1300.0
    assert parsed["READ"]["Count"] == 19024.0
    assert parsed["TOTAL"]["OPS"] == 1001.1


def test_series_from_ycsb_is_threads_to_read_p99_in_ms():
    text = (FIXTURES / "ycsb-t64.txt").read_text()
    assert knee.series_from_ycsb([(64, text)]) == [(64, 1.3)]
