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

# go-ycsb prints one line per operation kind plus TOTAL:
#   READ   - Takes(s): 20.0, Count: 19024, OPS: 951.2, Avg(us): 402, ... 99th(us): 1300, ...
_YCSB_LINE = re.compile(r"^(\w+)\s+-\s+(.*)$")
_YCSB_FIELD = re.compile(r"([A-Za-z0-9.]+\([a-z]+\)|[A-Za-z]+):\s*([0-9.]+)")


def find(series, slo_ms):
    """Last rate whose p99 <= slo_ms with every preceding step also under it.

    `series` is [(offered_rate, p99_ms)]; it is sorted here so callers do not
    have to. Returns None when the first step already breaks the SLO.
    """
    knee = None
    for rate, p99 in sorted(series):
        if p99 is None or p99 > slo_ms:
            break
        knee = rate
    return knee


def series_from_summary(summary):
    """(rate, p99_ms) out of a k6 MODE=knee summary."""
    series = []
    for name, metric in summary.get("metrics", {}).items():
        m = _RATE_SUBMETRIC.match(name)
        if m:
            series.append((int(m.group(1)), metric["values"]["p(99)"]))
    return sorted(series)


def invalid_reasons(summary):
    """Why this k6 run does not count. Empty list means the run is usable.

    Failed requests and dropped iterations both mean the number on the page is
    not the number the system produced: the first is errors answering fast, the
    second is the generator itself running out of VUs.
    """
    metrics = summary.get("metrics", {})
    reasons = []
    failed = metrics.get("http_req_failed", {}).get("values", {}).get("rate", 0)
    if failed > 0.01:
        reasons.append(f"http_req_failed rate {failed:.3f} > 0.01")
    dropped = metrics.get("dropped_iterations", {}).get("values", {}).get("count", 0)
    if dropped > 0:
        reasons.append(f"dropped_iterations count {dropped:.0f} > 0")
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
