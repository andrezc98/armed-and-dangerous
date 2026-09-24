"""The knee: the highest offered load whose p99 still fits the SLO.

A knee is the FIRST crossing of the SLO, not the last step that happens to look
good: past the crossing the queue is already the thing being measured, so a
later step reading low means the load generator stopped keeping up, not that the
system recovered. `find` therefore walks the ladder in order and stops.

This module also owns the two parsers that build a series, because both the knee
search and `analysis.stats` read the same raw files (one-way import: stats -> knee).
"""

import re

# k6 tags each held step of the ladder (runner/k6/lib.js reqTags); the samples
# taken during the linear ramp into a step are tagged rate:ramp and are not a
# rate anyone offered.
_RATE_SUBMETRIC = re.compile(r"^http_req_duration\{rate:(\d+)\}$")

# The three sub-metrics runner/k6/lib.js gives a threshold per held step, which
# is what makes k6 report them per step at all.
_STEP_SUBMETRIC = re.compile(r"^(http_reqs|http_req_failed|http_req_duration)\{rate:(\d+)\}$")

# A step counts when it delivered nearly all the requests it offered and almost
# all of them answered. 0.95 leaves room for the first and last second of the
# hold landing outside the window k6 attributed to the step.
STEP_MIN_DELIVERED = 0.95
STEP_MAX_FAILED = 0.01

# A fixed run of 8 min at ~30k rps dropped 0.05 % of its iterations at the smoke
# gate, with 2000 VUs preallocated and 664 in use at peak: stragglers, not a
# generator that fell behind. Above this share the generator set the number.
FIXED_MAX_DROPPED = 0.001

# go-ycsb prints one line per operation kind plus TOTAL:
#   READ   - Takes(s): 20.0, Count: 19024, OPS: 951.2, Avg(us): 402, ... 99th(us): 1300, ...
_YCSB_LINE = re.compile(r"^(\w+)\s+-\s+(.*)$")
_YCSB_FIELD = re.compile(r"([A-Za-z0-9.]+\([a-z]+\)|[A-Za-z]+):\s*([0-9.]+)")


def find(series, slo_ms, invalid_steps=None):
    """Last rate whose p99 <= slo_ms with every preceding step also usable.

    `series` is [(offered_rate, p99_ms)]; it is sorted here so callers do not
    have to. `invalid_steps` is {rate: why} from `step_reasons`: a step the
    generator did not actually deliver cannot carry the knee either, and it ends
    the walk exactly like a crossing does. Returns None when the first step is
    already unusable.

    Steps past the crossing are never looked at. Past it the ladder is measuring
    a queue, so timeouts and dropped iterations up there are the expected shape
    of an overloaded system, not a reason to throw the whole ladder away.
    """
    invalid_steps = invalid_steps or {}
    knee = None
    for rate, p99 in sorted(series, key=lambda pair: pair[0]):
        if rate in invalid_steps or p99 is None or p99 > slo_ms:
            break
        knee = rate
    return knee


def ladder_rates(ladder):
    """The rates lib.js `stageRates()` will hold, from the same ladder spec."""
    rates, rate = [], ladder["RATE_START"]
    while rate <= ladder["RATE_MAX"]:
        rates.append(rate)
        rate += ladder["RATE_STEP"]
    return rates


def step_reasons(summary, stage_seconds, ramp_seconds):
    """Why each ladder step does not count, as {rate: why}. Empty = all usable.

    Judged per step, not over the whole run: a knee ladder is SUPPOSED to break
    at the top, so `invalid_reasons` (which is the rule for the FIXED runs)
    would reject every ladder that actually found a knee.

    A step is usable when the generator delivered the load it promised
    (`http_reqs{rate:R}` close to R x the held seconds, so a step starved by the
    VU budget is caught) and the answers were answers (`http_req_failed{rate:R}`
    under 1 %).
    """
    held = max(stage_seconds - ramp_seconds, 0)
    steps = {}
    for name, metric in summary.get("metrics", {}).items():
        m = _STEP_SUBMETRIC.match(name)
        if m:
            steps.setdefault(int(m.group(2)), {})[m.group(1)] = metric.get("values", {})

    reasons = {}
    for rate, metrics in steps.items():
        why = []
        wanted = STEP_MIN_DELIVERED * rate * held
        delivered = metrics.get("http_reqs", {}).get("count", 0)
        if delivered < wanted:
            why.append(f"delivered {delivered:.0f} requests, expected >= {wanted:.0f}")
        failed = metrics.get("http_req_failed", {}).get("rate", 0)
        if failed >= STEP_MAX_FAILED:
            why.append(f"http_req_failed rate {failed:.3f} >= {STEP_MAX_FAILED}")
        if why:
            reasons[rate] = "; ".join(why)
    return reasons


def _p99(values):
    """p99 of one step, or None when the step held no samples.

    k6 materialises a tagged sub-metric for every threshold it was given, so a
    step where nothing answered is still in the summary with every trend stat at
    zero (the ladder's summaryTrendStats carries no `count`, runner/k6/lib.js),
    and `max` is the one of those that no real response can leave at zero. A p99
    of 0 ms is not a step that met the SLO, it is a step that never ran.
    """
    if values.get("count") == 0 or values.get("max", 1) == 0:
        return None
    return values.get("p(99)")


def series_from_summary(summary):
    """(rate, p99_ms) out of a k6 MODE=knee summary; p99 is None for an empty step."""
    series = []
    for name, metric in summary.get("metrics", {}).items():
        m = _RATE_SUBMETRIC.match(name)
        if m:
            series.append((int(m.group(1)), _p99(metric["values"])))
    return sorted(series, key=lambda pair: pair[0])


def invalid_reasons(summary):
    """Why this FIXED k6 run does not count. Empty list means it is usable.

    Failed requests and dropped iterations both mean the number on the page is
    not the number the system produced: the first is errors answering fast, the
    second is the generator itself running out of VUs.

    Whole-run, so it belongs to the runs held at one rate and NOT to a knee
    ladder, whose top steps are overloaded on purpose (`step_reasons`).
    """
    metrics = summary.get("metrics", {})
    reasons = []
    failed = metrics.get("http_req_failed", {}).get("values", {}).get("rate", 0)
    if failed > 0.01:
        reasons.append(f"http_req_failed rate {failed:.3f} > 0.01")
    dropped = metrics.get("dropped_iterations", {}).get("values", {}).get("count", 0)
    done = metrics.get("iterations", {}).get("values", {}).get("count", 0)
    share = dropped / (dropped + done) if dropped else 0
    if share > FIXED_MAX_DROPPED:
        reasons.append(f"dropped_iterations {dropped:.0f} = {share:.4f} of the offered "
                       f"iterations > {FIXED_MAX_DROPPED}")
    return reasons


def parse_ycsb(text):
    """go-ycsb's final report as {"READ": {"OPS": .., "99th(us)": ..}, "TOTAL": {...}}."""
    out = {}
    for line in text.splitlines():
        m = _YCSB_LINE.match(line.strip())
        if not m:
            continue
        fields = {k: float(v) for k, v in _YCSB_FIELD.findall(m.group(2))}
        if fields:
            out[m.group(1)] = fields
    return out


def series_from_ycsb(runs):
    """(threads, READ p99 in ms) out of [(threads, ycsb stdout)].

    The Mongo ladder is threads, not an offered rate: go-ycsb is a closed loop,
    so concurrency is the only knob that raises the offered load.
    """
    return sorted(
        (threads, parse_ycsb(text)["READ"]["99th(us)"] / 1000.0) for threads, text in runs
    )
