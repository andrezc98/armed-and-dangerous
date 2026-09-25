"""The knee: the highest offered load whose p99 still fits the SLO.

A knee is the FIRST crossing of the SLO, not the last step that happens to look
good: past the crossing the queue is already the thing being measured, so a
later step reading low means the load generator stopped keeping up, not that the
system recovered. `walk` therefore walks the ladder in order and stops, and says
WHY it stopped: a step over the SLO is a knee, a step the generator could not
deliver while latency was still fine is only the generator's ceiling.

This module also owns the two parsers that build a series, because both the knee
search and `analysis.stats` read the same raw files (one-way import: stats -> knee).
"""

import math
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

# A fixed run is held at 80 % of the knee, so it has to deliver that rate and
# stay inside the SLO, or the number on the slide is not the one it claims to
# be. The gate's arm-tuned fixed run at 80 % of a 2.5 ms knee read p99 5.26 ms
# and was not flagged (results/profiler-gate.md). Same 0.95 as a ladder step.
FIXED_MIN_DELIVERED = STEP_MIN_DELIVERED

# go-ycsb prints one line per operation kind plus TOTAL:
#   READ   - Takes(s): 20.0, Count: 19024, OPS: 951.2, Avg(us): 402, ... 99th(us): 1300, ...
_YCSB_LINE = re.compile(r"^(\w+)\s+-\s+(.*)$")
_YCSB_FIELD = re.compile(r"([A-Za-z0-9.]+\([a-z]+\)|[A-Za-z]+):\s*([0-9.]+)")


def walk(series, slo_ms, invalid_steps=None):
    """Walk the ladder in order; return (knee, ended_by).

    `series` is [(step, p99_ms)] (step = offered rate, or YCSB threads); it is
    sorted here so callers do not have to. `invalid_steps` is {step: why} from
    `step_reasons`. `knee` is the last step before the walk ended, None when the
    very first step ended it.

    The walk ends at the first step that is either
    - a crossing, p99 > SLO. It counts as a crossing even when the step is also
      under-delivered or failing: a slow SUT is what starves the arrival-rate
      VUs, so that shortfall is the SUT's;
    - unresolved: the step is invalid (or empty) while its p99 is still inside
      the SLO. The system was keeping up and the generator or the network was
      not, so this ladder found the loader's ceiling, not the SUT's knee.

    `ended_by` is {"step", "p99_ms", "kind": "crossing"|"unresolved", "reason"},
    or None when no step ended the walk (the ladder never crossed).

    Steps past the end are never looked at. Past a crossing the ladder is
    measuring a queue, so timeouts and dropped iterations up there are the
    expected shape of an overloaded system, not a reason to throw the ladder away.
    """
    invalid_steps = invalid_steps or {}
    knee = None
    for step, p99 in sorted(series, key=lambda pair: pair[0]):
        why = invalid_steps.get(step)
        if p99 is not None and p99 > slo_ms:
            reason = "; ".join(r for r in (f"p99 {p99:.2f} ms > SLO {slo_ms} ms", why) if r)
            return knee, {"step": step, "p99_ms": p99, "kind": "crossing", "reason": reason}
        if p99 is None or why:
            return knee, {"step": step, "p99_ms": p99, "kind": "unresolved",
                          "reason": why or "no samples in the step"}
        knee = step
    return knee, None


def find(series, slo_ms, invalid_steps=None):
    """The knee alone, for callers that do not need to know how the walk ended."""
    return walk(series, slo_ms, invalid_steps)[0]


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


# Any sub-metric tagged with a ladder step, whatever the metric.
_RATE_TAG = re.compile(r"^(.*)\{rate:(\d+)\}$")
_SUMMED = ("http_reqs", "iterations", "dropped_iterations")


def merge_summaries(summaries):
    """N k6 summaries of generators that each offered 1/N of the load, as the
    ONE summary a single generator would have written, same schema, so the knee
    walk, step_reasons, invalid_reasons and analysis.stats read it unchanged.

    Conservative where it cannot be exact (the percentiles of the union are not
    recoverable from the parts):
    - http_req_duration (whole run and per step): every stat is the MAX across
      generators, `min` the min. avg and med are the max too, not a mean: the
      number on the slide may only err towards slower;
    - http_reqs, iterations, dropped_iterations: count and rate are summed;
    - http_req_failed: request-weighted, by passes + fails (what k6 v2.2.0 writes
      for a Rate, results/2026-09-04/java/arm-tuned/run-1/k6.json) or, missing
      those, by the step's own http_reqs count;
    - a step tag is the per-generator rate lib.js held, so {rate:R} becomes
      {rate:R x N}: the aggregate rate the step offered;
    - everything else (thresholds, gauges, other trends, state, options) is
      generator 1's. Nothing the runner judges reads them.
    """
    if len(summaries) == 1:
        return summaries[0]
    n = len(summaries)
    merged = {**summaries[0], "metrics": {}}
    names = dict.fromkeys(name for s in summaries for name in s.get("metrics", {}))
    for name in names:
        present = [s for s in summaries if name in s.get("metrics", {})]
        metric = dict(present[0]["metrics"][name])
        values = [s["metrics"][name].get("values", {}) for s in present]
        tagged = _RATE_TAG.match(name)
        base = tagged.group(1) if tagged else name
        keys = dict.fromkeys(k for v in values for k in v)
        if base == "http_req_duration":
            metric["values"] = {
                k: (sum if k == "count" else min if k == "min" else max)(v[k] for v in values if k in v)
                for k in keys}
        elif base in _SUMMED:
            metric["values"] = {k: sum(v.get(k, 0) for v in values) for k in keys}
        elif base == "http_req_failed":
            reqs = "http_reqs" + name[len(base):]
            weights = [v["passes"] + v["fails"] if "passes" in v and "fails" in v
                       else s["metrics"].get(reqs, {}).get("values", {}).get("count", 0)
                       for s, v in zip(present, values)]
            total = sum(weights)
            out = {k: sum(v.get(k, 0) for v in values) for k in ("passes", "fails") if k in keys}
            out["rate"] = (sum(w * v.get("rate", 0) for w, v in zip(weights, values)) / total
                           if total else max(v.get("rate", 0) for v in values))
            metric["values"] = out
        if tagged:
            name = f"{base}{{rate:{int(tagged.group(2)) * n}}}"
        merged["metrics"][name] = metric
    return merged


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


def invalid_reasons(summary, slo_ms=None, target_rate=None):
    """Why this FIXED k6 run does not count. Empty list means it is usable.

    Failed requests and dropped iterations both mean the number on the page is
    not the number the system produced: the first is errors answering fast, the
    second is the generator itself running out of VUs. With `slo_ms` (> 0) the
    run must also hold the SLO, and with `target_rate` it must deliver at least
    FIXED_MIN_DELIVERED of it: a run at "80 % of the knee" that misses either is
    not a run at 80 % of the knee.

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
    if slo_ms and slo_ms > 0:
        p99 = metrics.get("http_req_duration", {}).get("values", {}).get("p(99)")
        if p99 is not None and p99 > slo_ms:
            reasons.append(f"fixed_over_slo: p99 {p99:.2f} ms > SLO {slo_ms} ms")
    if target_rate:
        rate = metrics.get("http_reqs", {}).get("values", {}).get("rate", 0)
        if rate < FIXED_MIN_DELIVERED * target_rate:
            reasons.append(f"fixed_underdelivered: {rate:.0f} rps < "
                           f"{FIXED_MIN_DELIVERED} x {target_rate} rps offered")
    return reasons


def ycsb_invalid_reasons(parsed, slo_ms=None, target_ops=None):
    """The fixed-run rule of `invalid_reasons` for a go-ycsb report: READ p99
    inside the SLO, and TOTAL OPS at least FIXED_MIN_DELIVERED of the --target
    the run was throttled to (TOTAL, because --target throttles every operation)."""
    reasons = []
    # No p99 at all is a pgbench report with no sampled transaction; its own
    # reason (pgbench_reasons, no_latency_samples) says so. go-ycsb always has one.
    p99 = parsed["READ"].get("99th(us)", 0) / 1000.0
    if slo_ms and slo_ms > 0 and p99 > slo_ms:
        reasons.append(f"fixed_over_slo: READ p99 {p99:.2f} ms > SLO {slo_ms} ms")
    ops = parsed["TOTAL"]["OPS"]
    if target_ops and ops < FIXED_MIN_DELIVERED * target_ops:
        reasons.append(f"fixed_underdelivered: TOTAL {ops:.0f} ops/s < "
                       f"{FIXED_MIN_DELIVERED} x {target_ops} ops/s target")
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


def _ycsb_number(value):
    return str(int(value)) if value == int(value) else f"{value:.1f}"


_YCSB_FINISHED = "Run finished"


def merge_ycsb(texts):
    """N go-ycsb reports of clients that ran concurrently, each with 1/N of the
    threads and operations, as ONE report in go-ycsb's own line format, so
    parse_ycsb, series_from_ycsb and analysis.stats read it unchanged.

    Per operation line (READ, UPDATE, TOTAL ...): OPS and Count summed, Takes(s)
    and every percentile and Max the MAX across clients, Min the min, Avg(us)
    count-weighted (exact, unlike the percentiles of the union, which the parts
    cannot give back: the max errs only towards slower). A line one client did
    not print is left out, so a client with no report makes a step with no
    report. go-ycsb v1.0.3 splits --target across its own threads
    (pkg/client/client.go, targetPerThread), so N processes offer N x target/N.
    """
    if len(texts) == 1:
        return texts[0]
    # Only what follows go-ycsb's "Run finished" line is a final report: the
    # periodic reports before it use the same line format, so a client killed
    # at 30 s would otherwise pass its 30 s interim numbers off as a finished
    # step (review of 8dd4b8f). No such line = no report from that client.
    finals = [text.rsplit(_YCSB_FINISHED, 1)[1] if _YCSB_FINISHED in text else ""
              for text in texts]
    parsed = [parse_ycsb(text) for text in finals]
    kinds = [k for k in parsed[0] if all(k in p for p in parsed)]
    lines = [f"# merged from {len(texts)} go-ycsb clients (runner/knee.py merge_ycsb)"]
    for kind in kinds:
        rows = [p[kind] for p in parsed]
        merged = {}
        for field in rows[0]:
            values = [r[field] for r in rows if field in r]
            if field in ("OPS", "Count"):
                merged[field] = sum(values)
            elif field == "Min(us)":
                merged[field] = min(values)
            elif field == "Avg(us)" and all("Count" in r for r in rows):
                counts = sum(r["Count"] for r in rows)
                merged[field] = round(sum(r["Avg(us)"] * r["Count"] for r in rows) / counts
                                      if counts else 0, 1)
            else:  # Takes(s), Max(us), every NNth(us)
                merged[field] = max(values)
        # The clients start and finish seconds apart; while one runs alone it
        # runs faster, so the sum of their own OPS overstates what the SUT gave
        # the step. Total operations over the longest client's time is what was
        # actually delivered across the step.
        if "Count" in merged and merged.get("Takes(s)"):
            merged["OPS"] = round(merged["Count"] / merged["Takes(s)"], 1)
        body = ", ".join(f"{field}: {_ycsb_number(v)}" for field, v in merged.items())
        lines.append(f"{kind:<6} - {body}")
    return "\n".join(lines) + "\n"


# --- pgbench (PostgreSQL 18.6) -------------------------------------------------
# pgbench's summary has no percentiles (printResults in pgbench.c, REL_18_6), so
# the run Job (manifests/workloads/postgres/base/pgbench-run-job.yaml) logs a
# sample of its transactions (-l --sampling-rate) and, after pgbench exits,
# prints:
#   PGBENCH_MARKER
#   rc=<pgbench exit code>
#   samples=<logged transactions that did not fail>
#   "<count> <us>" lines: histogram of the SERVICE latency
#   PGBENCH_LAG_MARKER
#   "<count> <us>" lines: histogram of the schedule lag (only with -R)
# The log's `time` is "transaction's elapsed time, in microseconds"
# (https://www.postgresql.org/docs/18/pgbench.html); in the source it is
# now - txn_scheduled, so under -R it includes the schedule lag, "the
# difference between the transaction's scheduled start time and the time it
# actually started" (field 7, present only with --rate). The Job logs time -
# lag as the service latency, and the lag on its own: the SLO judges the
# server, the lag budget judges the generator.
PGBENCH_MARKER = "---AAD-PGBENCH-LATENCY-US---"
PGBENCH_LAG_MARKER = "---AAD-PGBENCH-LAG-US---"

# The summary lines pgbench 18.6 prints (printResults), e.g.
#   duration: 60 s
#   number of transactions actually processed: 1889218
#   number of failed transactions: 0 (0.000%)
#   tps = 188999.384247 (without initial connection time)
_PGBENCH_FIELDS = {
    "seconds": re.compile(r"^duration: (\d+) s$", re.M),
    "count": re.compile(r"^number of transactions actually processed: (\d+)", re.M),
    "failed": re.compile(r"^number of failed transactions: (\d+)", re.M),
    "tps": re.compile(r"^tps = ([0-9.]+) ", re.M),
}
_PGBENCH_RC = re.compile(r"^rc=(\d+)$", re.M)
_PGBENCH_SAMPLES = re.compile(r"^samples=(\d+)$", re.M)
# pgbench 18.6 prints this when a client aborted (a lost connection, an error
# outside --max-tries), and still prints a tps line after it: a plausible
# number over a run that stopped part way (tests/fixtures/pgbench-aborted.txt).
PGBENCH_ABORTED = "Run was aborted"
_PERCENTILES = (("50th(us)", 0.50), ("90th(us)", 0.90), ("95th(us)", 0.95),
                ("99th(us)", 0.99), ("99.9th(us)", 0.999))


def _uniq_c(text):
    """`uniq -c` lines, "<count> <value>", as {value: count}; other lines skipped
    (stderr can land between them in `kubectl logs`)."""
    hist = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            hist[int(parts[1])] = hist.get(int(parts[1]), 0) + int(parts[0])
    return hist


def parse_pgbench(text):
    """One pgbench Job's stdout as {"seconds", "count", "failed", "tps",
    "samples", "hist", "lag"}; hist and lag are {us: sampled transactions}.

    None when there is no report:
    - no marker: the Job never got past pgbench;
    - no tps or count line: pgbench died before its summary;
    - rc missing or not 0, or "Run was aborted": pgbench says itself that the
      summary it printed is incomplete (I1, review of 5b1896e);
    - samples missing or not the histogram's own total: lines were lost on
      the way (a cut `kubectl logs`, a killed sort) and the p99 would be
      computed over part of the sample (M4).
    """
    if not text or PGBENCH_MARKER not in text:
        return None
    summary, tail = text.split(PGBENCH_MARKER, 1)
    found = {k: rx.search(summary) for k, rx in _PGBENCH_FIELDS.items()}
    rc, samples = _PGBENCH_RC.search(tail), _PGBENCH_SAMPLES.search(tail)
    if (not (found["tps"] and found["count"]) or PGBENCH_ABORTED in text
            or rc is None or rc.group(1) != "0" or samples is None):
        return None
    service, _, lag = tail.partition(PGBENCH_LAG_MARKER)
    hist = _uniq_c(service)
    if sum(hist.values()) != int(samples.group(1)):
        return None
    return {"seconds": int(found["seconds"].group(1)) if found["seconds"] else 0,
            "count": int(found["count"].group(1)),
            "failed": int(found["failed"].group(1)) if found["failed"] else 0,
            "tps": float(found["tps"].group(1)), "samples": int(samples.group(1)),
            "hist": hist, "lag": _uniq_c(lag)}


def _hist_percentile(hist, q, total):
    """Nearest-rank percentile of a {value: count} histogram."""
    rank, seen = max(math.ceil(q * total), 1), 0
    for value in sorted(hist):
        seen += hist[value]
        if seen >= rank:
            return value
    return None


def _add(hists):
    out = {}
    for hist in hists:
        for us, n in hist.items():
            out[us] = out.get(us, 0) + n
    return out


def merge_pgbench(texts):
    """N pgbench processes that ran one step together, each with 1/N of the
    clients and of -R, as ONE report in go-ycsb's line format, so parse_ycsb,
    series_from_ycsb, ycsb_invalid_reasons and analysis.stats read it unchanged.

    Unlike merge_ycsb, the percentiles here are exact for the union of the
    samples: the histograms add up. The latency fields are the SERVICE latency;
    LagP99(us) and LagMax(us), when the run was throttled, are the schedule
    lag's. Count, failed and tps are summed (every process ran the same -T).
    Samples is the total, MinProcSamples the smallest process's, Procs N. READ
    and TOTAL are the same line: select-only is one read per transaction.

    "" when any process has no report (parse_pgbench): a step with part of its
    load unaccounted for has no report. Zero samples over processes that all
    reported is a report without latency fields (knee.pgbench_reasons says
    no_latency_samples), not an empty one.
    """
    parsed = [parse_pgbench(text) for text in texts]
    if not parsed or None in parsed:
        return ""
    hist, lag = _add(p["hist"] for p in parsed), _add(p["lag"] for p in parsed)
    samples, lags = sum(hist.values()), sum(lag.values())
    fields = {
        "Takes(s)": max(p["seconds"] for p in parsed),
        "Count": sum(p["count"] for p in parsed),
        "OPS": round(sum(p["tps"] for p in parsed), 1),
    }
    if samples:
        fields.update({
            "Avg(us)": round(sum(us * n for us, n in hist.items()) / samples, 1),
            "Min(us)": min(hist),
            "Max(us)": max(hist),
            **{name: _hist_percentile(hist, q, samples) for name, q in _PERCENTILES},
        })
    fields.update({"Samples": samples, "MinProcSamples": min(p["samples"] for p in parsed),
                   "Procs": len(parsed), "Failed": sum(p["failed"] for p in parsed)})
    if lags:
        fields.update({"LagP99(us)": _hist_percentile(lag, 0.99, lags), "LagMax(us)": max(lag)})
    body = ", ".join(f"{field}: {_ycsb_number(v)}" for field, v in fields.items())
    return (f"# merged from {len(texts)} pgbench clients (runner/knee.py merge_pgbench)\n"
            f"READ   - {body}\nTOTAL  - {body}\n")


def pgbench_reasons(line, min_samples):
    """Why a merged pgbench line (a knee step or a fixed run) does not count:
    no sampled transaction at all, too few to put a p99 on (in total, or in any
    one process: its share of the load would be judged on too little, M3), or
    any failed transaction."""
    why = []
    samples, procs = line.get("Samples", 0), line.get("Procs", 1)
    if not samples:
        why.append("no_latency_samples: no transaction was logged in any process")
    else:
        if samples < min_samples:
            why.append(f"{samples:.0f} sampled transactions < {min_samples}: p99 not resolved")
        low = line.get("MinProcSamples", samples)
        if procs > 1 and low < min_samples / procs:
            why.append(f"a pgbench process logged {low:.0f} sampled transactions < "
                       f"{min_samples}/{procs:.0f}: p99 not resolved")
    if line.get("Failed", 0):
        why.append(f"{line['Failed']:.0f} failed transactions")
    return why


def pgbench_fixed_reasons(parsed, slo_ms, target_ops, min_samples, max_lag_p99_ms):
    """The fixed-run rule for a merged pgbench report: ycsb_invalid_reasons on
    the service latency and the delivered tps, pgbench_reasons, and the lag
    budget. The lag is the generator's, not the server's: a run whose p99 lag
    is over max_lag_p99_ms did not offer the load it claims on the schedule it
    claims, whatever the service latency says (C1)."""
    reasons = ycsb_invalid_reasons(parsed, slo_ms, target_ops) + pgbench_reasons(
        parsed["READ"], min_samples)
    lag_ms = parsed["READ"].get("LagP99(us)", 0) / 1000.0
    if max_lag_p99_ms is not None and lag_ms > max_lag_p99_ms:
        reasons.append(f"fixed_generator_lagging: schedule lag p99 {lag_ms:.2f} ms > "
                       f"{max_lag_p99_ms} ms")
    return reasons


def series_from_ycsb(runs):
    """(threads, READ p99 in ms) out of [(threads, ycsb stdout)].

    The Mongo ladder is threads, not an offered rate: go-ycsb is a closed loop,
    so concurrency is the only knob that raises the offered load.
    """
    return sorted(
        (threads, parse_ycsb(text)["READ"]["99th(us)"] / 1000.0) for threads, text in runs
    )
