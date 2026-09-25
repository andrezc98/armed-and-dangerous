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
            "iterations": {"values": {"count": 988}},
        }
    }
    assert knee.invalid_reasons(bad) == [
        "http_req_failed rate 0.050 > 0.01",
        "dropped_iterations 12 = 0.0120 of the offered iterations > 0.001",
    ]


def test_a_fixed_run_survives_the_drops_of_vu_spin_up():
    """The smoke gate's fixed runs dropped 7547 of 15.35M (0.05 %)."""
    gate = {"metrics": {"dropped_iterations": {"values": {"count": 7547}},
                        "iterations": {"values": {"count": 15350000}}}}
    assert knee.invalid_reasons(gate) == []


# --- the ladder is judged per step, not as a whole -----------------------------
# A knee ladder is SUPPOSED to break at the top. Judged with the whole-run rule
# (invalid_reasons, which is the rule for the FIXED runs) every ladder that
# actually found a knee was thrown away.

OVERLOADED = "go-knee-overloaded.json"  # 200..1800 rps; 1400 and 1800 time out
STAGE, RAMP = 60, 5


def _laddered(steps):
    """A k6 knee summary out of {rate: (p99_ms, delivered_fraction, failed_rate)}."""
    metrics = {}
    for rate, (p99, delivered, failed) in steps.items():
        metrics[f"http_req_duration{{rate:{rate}}}"] = {"values": {"p(99)": p99, "max": p99 * 3}}
        metrics[f"http_reqs{{rate:{rate}}}"] = {
            "values": {"count": round(rate * (STAGE - RAMP) * delivered)}
        }
        metrics[f"http_req_failed{{rate:{rate}}}"] = {"values": {"rate": failed}}
    return {"metrics": metrics}


def test_the_old_whole_run_rule_would_have_rejected_a_ladder_that_found_its_knee():
    assert knee.invalid_reasons(_summary(OVERLOADED)) != []


def test_a_crossing_with_an_overloaded_tail_still_yields_the_knee():
    summary = _summary(OVERLOADED)
    steps = knee.step_reasons(summary, STAGE, RAMP)
    # Only the two steps past the crossing are unusable, and only they.
    assert sorted(steps) == [1400, 1800]
    assert knee.find(knee.series_from_summary(summary), 100, steps) == 1000


def test_a_crossing_without_an_overloaded_tail_yields_the_same_knee():
    """The server keeps answering past the SLO: nothing is invalid, and the knee
    is still the last step under it."""
    summary = _laddered({200: (5.0, 1.0, 0.0), 600: (40.0, 1.0, 0.0), 1000: (410.0, 1.0, 0.0)})
    steps = knee.step_reasons(summary, STAGE, RAMP)
    assert steps == {}
    assert knee.find(knee.series_from_summary(summary), 100, steps) == 600


def test_a_first_step_the_generator_never_delivered_is_not_a_knee():
    """Half the offered requests placed at the very first rate: that ladder
    measured the VU budget, and its 5 ms is the generator's latency."""
    summary = _laddered({200: (5.0, 0.5, 0.0), 600: (9.0, 1.0, 0.0)})
    steps = knee.step_reasons(summary, STAGE, RAMP)
    assert 200 in steps and "delivered" in steps[200]
    assert knee.find(knee.series_from_summary(summary), 100, steps) is None


def test_a_step_that_answered_with_errors_is_not_a_knee_either():
    summary = _laddered({200: (5.0, 1.0, 0.0), 600: (6.0, 1.0, 0.05)})
    assert sorted(knee.step_reasons(summary, STAGE, RAMP)) == [600]
    assert knee.find(knee.series_from_summary(summary), 100,
                     knee.step_reasons(summary, STAGE, RAMP)) == 200


def test_ladder_rates_are_the_rates_lib_js_holds():
    assert knee.ladder_rates({"RATE_START": 200, "RATE_STEP": 400, "RATE_MAX": 1800}) == [
        200, 600, 1000, 1400, 1800
    ]
    # A RATE_MAX that is not on the grid: the top step is the last one that fits.
    assert knee.ladder_rates({"RATE_START": 200, "RATE_STEP": 400, "RATE_MAX": 1500})[-1] == 1400


def test_parse_ycsb_reads_the_read_and_total_lines():
    parsed = knee.parse_ycsb((FIXTURES / "ycsb-t64.txt").read_text())
    assert parsed["READ"]["OPS"] == 951.2
    assert parsed["READ"]["99th(us)"] == 1300.0
    assert parsed["READ"]["Count"] == 19024.0
    assert parsed["TOTAL"]["OPS"] == 1001.1


def test_series_from_ycsb_is_threads_to_read_p99_in_ms():
    text = (FIXTURES / "ycsb-t64.txt").read_text()
    assert knee.series_from_ycsb([(64, text)]) == [(64, 1.3)]


def test_a_step_with_no_samples_is_missing_not_passing():
    # k6 materialises a sub-metric for every threshold, so a step where nothing
    # answered comes back with every trend stat at zero. Reading that 0.0 as a
    # p99 would report the empty step as the fastest one on the ladder.
    summary = {
        "metrics": {
            "http_req_duration{rate:100}": {"values": {"p(99)": 5.0, "max": 30.0}},
            "http_req_duration{rate:200}": {
                "values": {"avg": 0, "min": 0, "med": 0, "p(90)": 0, "p(95)": 0,
                           "p(99)": 0, "p(99.9)": 0, "max": 0}
            },
        }
    }
    assert knee.series_from_summary(summary) == [(100, 5.0), (200, None)]
    assert knee.find(knee.series_from_summary(summary), 100) == 100


def test_an_explicit_zero_count_is_also_a_missing_step():
    values = {"count": 0, "max": 12.0, "p(99)": 0.0}
    assert knee.series_from_summary({"metrics": {"http_req_duration{rate:400}": {"values": values}}}) == [
        (400, None)
    ]


# --- a knee is a real crossing, not the loader's ceiling ---------------------
# 2026-09-24 review: the walk used to stop at the first INVALID step as if it
# were a crossing, so a ladder the generator could not deliver published the
# loader's ceiling as the SUT's knee.

def test_an_underdelivered_step_inside_the_slo_leaves_the_capacity_unresolved():
    summary = _laddered({200: (5.0, 1.0, 0.0), 600: (6.0, 0.5, 0.0), 1000: (410.0, 1.0, 0.0)})
    steps = knee.step_reasons(summary, STAGE, RAMP)
    found, ended = knee.walk(knee.series_from_summary(summary), 100, steps)
    assert found == 200
    assert ended["step"] == 600 and ended["kind"] == "unresolved"
    assert "delivered" in ended["reason"]


def test_an_underdelivered_step_over_the_slo_is_still_a_crossing():
    """A slow SUT starves the arrival-rate VUs: that shortfall is the SUT's."""
    summary = _laddered({200: (5.0, 1.0, 0.0), 600: (140.0, 0.5, 0.0)})
    steps = knee.step_reasons(summary, STAGE, RAMP)
    found, ended = knee.walk(knee.series_from_summary(summary), 100, steps)
    assert found == 200
    assert ended["kind"] == "crossing"
    assert "p99 140.00 ms > SLO 100 ms" in ended["reason"] and "delivered" in ended["reason"]


def test_a_ladder_that_never_ended_has_no_end():
    assert knee.walk([(100, 1.0), (200, 2.0)], 100) == (200, None)


# --- fixed runs hold the SLO and deliver the rate ---------------------------

def _fixed(p99, rate):
    return {"metrics": {"http_req_duration": {"values": {"p(99)": p99}},
                        "http_reqs": {"values": {"rate": rate}}}}


def test_a_fixed_run_over_the_slo_is_invalid():
    """The gate's arm-tuned run at 80 % of a 2.5 ms knee read 5.26 ms."""
    assert knee.invalid_reasons(_fixed(5.26, 32000), 2.5, 32000) == [
        "fixed_over_slo: p99 5.26 ms > SLO 2.5 ms"
    ]


def test_a_fixed_run_that_did_not_deliver_its_rate_is_invalid():
    reasons = knee.invalid_reasons(_fixed(1.0, 28000), 10, 32000)
    assert reasons == ["fixed_underdelivered: 28000 rps < 0.95 x 32000 rps offered"]


def test_a_fixed_run_inside_the_slo_at_its_rate_is_valid():
    assert knee.invalid_reasons(_fixed(1.0, 31900), 10, 32000) == []
    # No SLO (inference) and no target: neither rule applies.
    assert knee.invalid_reasons(_fixed(900.0, 1), 0, None) == []


def test_a_fixed_ycsb_run_is_judged_on_read_p99_and_total_ops():
    parsed = knee.parse_ycsb((FIXTURES / "ycsb-t64.txt").read_text())  # READ p99 1.3 ms, TOTAL 1001.1
    assert knee.ycsb_invalid_reasons(parsed, 5, 1000) == []
    assert knee.ycsb_invalid_reasons(parsed, 1, 1200) == [
        "fixed_over_slo: READ p99 1.30 ms > SLO 1 ms",
        "fixed_underdelivered: TOTAL 1001 ops/s < 0.95 x 1200 ops/s target",
    ]


# --- two k6 generators, one summary (2026-09-25) ------------------------------

def _gen(p99, count, failed, *, rate_tag=5000, avg=1.0, min_ms=0.2, dropped=0, iters=None,
         threshold_ok=True):
    """One generator's k6 summary: one held step plus the whole-run metrics."""
    iters = count if iters is None else iters
    return {"state": {"testRunDurationMs": 60000}, "metrics": {
        f"http_req_duration{{rate:{rate_tag}}}": {
            "type": "trend", "values": {"p(99)": p99, "avg": avg, "med": avg, "min": min_ms,
                                        "max": p99 * 3},
            "thresholds": {"p(99)<10": {"ok": threshold_ok}}},
        f"http_reqs{{rate:{rate_tag}}}": {"type": "counter",
                                          "values": {"count": count, "rate": count / 60}},
        f"http_req_failed{{rate:{rate_tag}}}": {"type": "rate", "values": {"rate": failed}},
        "http_req_duration": {"type": "trend", "values": {"p(99)": p99, "avg": avg, "med": avg,
                                                          "min": min_ms, "max": p99 * 3}},
        "http_reqs": {"type": "counter", "values": {"count": count, "rate": count / 60}},
        "http_req_failed": {"type": "rate", "values": {
            "rate": failed, "passes": round(count * failed), "fails": count - round(count * failed)}},
        "iterations": {"type": "counter", "values": {"count": iters, "rate": iters / 60}},
        "dropped_iterations": {"type": "counter", "values": {"count": dropped, "rate": dropped / 60}},
        "vus_max": {"type": "gauge", "values": {"value": 1000}},
    }}


def test_two_generator_summaries_merge_conservatively():
    g1 = _gen(4.0, 300_000, 0.0, avg=1.0, min_ms=0.2, dropped=10)
    g2 = _gen(6.0, 100_000, 0.04, avg=2.0, min_ms=0.1, dropped=5, threshold_ok=False)
    m = knee.merge_summaries([g1, g2])["metrics"]
    # The step tag each generator wrote is ITS rate: the merged step is 2 x 5000.
    assert not any("{rate:5000}" in name for name in m)
    step = m["http_req_duration{rate:10000}"]["values"]
    assert step["p(99)"] == 6.0 and step["max"] == 18.0  # the slower generator
    assert step["avg"] == 2.0 and step["med"] == 2.0      # max, not a mean
    assert step["min"] == 0.1
    assert m["http_reqs{rate:10000}"]["values"]["count"] == 400_000
    # 1 % failed overall: 4 % of the 100k, 0 % of the 300k, weighted by requests.
    assert m["http_req_failed{rate:10000}"]["values"]["rate"] == 0.01
    assert m["http_req_failed"]["values"] == {"passes": 4000, "fails": 396_000, "rate": 0.01}
    assert m["http_req_duration"]["values"]["p(99)"] == 6.0
    assert m["http_reqs"]["values"]["rate"] == 400_000 / 60
    assert m["dropped_iterations"]["values"]["count"] == 15
    assert m["iterations"]["values"]["count"] == 400_000
    # Everything else is generator 1's, thresholds included.
    assert m["http_req_duration{rate:10000}"]["thresholds"] == {"p(99)<10": {"ok": True}}
    assert m["vus_max"]["values"] == {"value": 1000}


def test_one_summary_is_its_own_merge():
    g1 = _gen(4.0, 300_000, 0.0)
    assert knee.merge_summaries([g1]) is g1


def test_a_merged_step_is_judged_against_the_aggregate_rate():
    """Each generator held 5000 rps for 55 s (60 s stage, 5 s ramp). The step
    is 10000 rps: 550k requests wanted, and one generator falling short is the
    step falling short."""
    full = knee.merge_summaries([_gen(4.0, 275_000, 0.0), _gen(4.0, 275_000, 0.0)])
    assert knee.step_reasons(full, 60, 5) == {}
    short = knee.merge_summaries([_gen(4.0, 275_000, 0.0), _gen(4.0, 165_000, 0.0)])
    assert knee.step_reasons(short, 60, 5) == {
        10000: "delivered 440000 requests, expected >= 522500"}
    assert knee.series_from_summary(short) == [(10000, 4.0)]


def test_a_merged_fixed_run_is_judged_against_the_aggregate_rate():
    """Two generators at 13600 rps each are a 27200 rps run."""
    ok = knee.merge_summaries([_gen(4.0, 13600 * 60, 0.0), _gen(4.0, 13600 * 60, 0.0)])
    assert knee.invalid_reasons(ok, 10, 27200) == []
    short = knee.merge_summaries([_gen(4.0, 13600 * 60, 0.0), _gen(4.0, 10400 * 60, 0.0)])
    assert knee.invalid_reasons(short, 10, 27200) == [
        "fixed_underdelivered: 24000 rps < 0.95 x 27200 rps offered"]
