"""Task 7 statistics: averages, baselines, bootstrap intervals, counters -> analysis/stats.md.

    python3 analysis/stats.py

Reads analysis/data/{cells,runs,telemetry}.csv (built by collect.py) and never
touches results/. Scope: day_class task7-d1/d2/d3, set_aside empty.
Reuses runner/analysis/stats.py (MIN_RUNS, _spread) and runner/cost.py (rates).
Also writes analysis/data/stats-comparisons.csv (one row per comparison).
"""
import csv
import math
import random
import statistics
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "analysis" / "data"
sys.path.insert(0, str(ROOT / "runner"))
# ponytail: runner/capture.py imports httpx for live metrics-API calls we never make;
# an empty stand-in lets system python3 import the runner's own stats module.
sys.modules.setdefault("httpx", types.ModuleType("httpx"))
import config  # noqa: E402
import cost  # noqa: E402
from analysis import stats as rstats  # noqa: E402

CHIPS = ("arm", "amd", "x86")
NAME = {"arm": "arm (m9g)", "amd": "amd (m8a)", "x86": "x86 (m8i)"}
PRICE = {c: cost.rates()[config.instance_type(f"{c}-stock")] for c in CHIPS}
KNEE_WL = ("postgres", "mongo")  # headline = knee_throughput, one ladder per day
UNIT = {"go": "rps", "java": "rps", "inference": "tok/s", "postgres": "tps", "mongo": "ops/s"}
SEED, B = 20261003, 10000
PMU = ("ipc", "branch-mpki", "inst-l1-mpki", "stall-frontend-pkc")


def load():
    # set_aside lives in cells.csv only; runs/telemetry inherit it through the workload dir name.
    aside = {r["workload"] for r in csv.DictReader(open(DATA / "cells.csv")) if r["set_aside"]}
    rows = lambda f: [r for r in csv.DictReader(open(DATA / f))
                      if r["day_class"].startswith("task7") and r["workload"] not in aside]
    return rows("cells.csv"), rows("runs.csv"), rows("telemetry.csv")


cells, runs, tele = load()
valid_runs = {}  # (workload, cell, day) -> [headline_value of valid runs]
valid_keys = set()
for r in runs:
    if r["valid"] == "True" and r["headline_value"]:
        valid_runs.setdefault((r["workload"], r["cell"], r["day_class"][-2:]), []).append(
            float(r["headline_value"]))
        valid_keys.add((r["results_dir"], r["workload"], r["cell"], r["run"]))

# D[(workload, variant)][chip] = [{"day", "value", "runs"}]; runs = what the bootstrap
# resamples inside a day. PG/Mongo: the knee is one number per day, nothing to resample;
# their fixed runs (held at 80 % of the knee) are kept apart as "fixed".
D = {}
for r in cells:
    w, day = r["workload"], r["day_class"][-2:]
    if w == "net":
        continue
    rv = valid_runs.get((w, r["cell"], day), [])
    if w in KNEE_WL:
        if not r["knee_throughput"]:
            continue
        d = {"day": day, "value": float(r["knee_throughput"]), "runs": [], "fixed": rv}
    else:
        if not rv:
            continue
        assert len(rv) >= rstats.MIN_RUNS, (w, r["cell"], day)
        d = {"day": day, "value": statistics.median(rv), "runs": rv, "fixed": rv}
        assert abs(d["value"] - float(r["headline_median"])) < 1e-6
    D.setdefault((w, r["variant"]), {}).setdefault(r["chip"], []).append(d)
for v in D.values():
    for days in v.values():
        days.sort(key=lambda d: d["day"])


def mean(days):
    return statistics.mean(d["value"] for d in days)


def boot(days, rng):
    """One bootstrap draw of the chip mean: resample days, then runs inside each day."""
    out = []
    for d in (rng.choice(days) for _ in days):
        out.append(statistics.median(rng.choices(d["runs"], k=len(d["runs"])))
                   if d["runs"] else d["value"])
    return statistics.mean(out)


def envelope(days):
    """Min-max of the day values; with one day, of that day's runs."""
    vals = [d["value"] for d in days] if len(days) > 1 else (days[0]["runs"] or [days[0]["value"]])
    return min(vals), max(vals)


def compare(a, b, scale=1.0):
    """Ratio mean(a)/mean(b) * scale, 95 % percentile bootstrap, envelopes, label."""
    rng = random.Random(SEED)  # same seed per comparison: reproducible, order-independent
    draws = sorted(boot(a, rng) / boot(b, rng) * scale for _ in range(B))
    lo, hi = draws[int(0.025 * B)], draws[int(0.975 * B) - 1]
    ea, eb = envelope(a), envelope(b)
    env = (ea[0] / eb[1] * scale, ea[1] / eb[0] * scale)
    # The (scaled) day ranges overlap exactly when the envelope ratio straddles 1.
    label = "within noise" if env[0] <= 1 <= env[1] else ("clear" if lo > 1 or hi < 1 else "lean")
    return {"ratio": mean(a) / mean(b) * scale, "lo": lo, "hi": hi, "env_ratio": env, "label": label}


def fmt(x):
    return f"{x/1000:.1f}k" if x >= 1000 else f"{x:.1f}"


def pct(x):
    return f"{x:+.1f} %"


def cv(vals):
    return statistics.stdev(vals) / statistics.mean(vals) * 100 if len(vals) > 1 else float("nan")


def days_str(days):
    return " / ".join(f"{d['day']} {fmt(d['value'])}" for d in days)


def cmp_cells(c):
    return (f"{c['ratio']:.2f}x | {c['lo']:.2f}–{c['hi']:.2f} | "
            f"{c['env_ratio'][0]:.2f}–{c['env_ratio'][1]:.2f} | {c['label']}")


out, comparisons = [], []  # comparisons -> csv + the label list


def record(section, w, var, what, c, note=""):
    comparisons.append(dict(section=section, workload=w, variant=var, comparison=what,
                            ratio=round(c["ratio"], 4), ci_lo=round(c["lo"], 4), ci_hi=round(c["hi"], 4),
                            env_lo=round(c["env_ratio"][0], 4), env_hi=round(c["env_ratio"][1], 4),
                            label=c["label"], note=note))


# ---------------------------------------------------------------- Method
out += [
    "# Task 7 statistics (generated by analysis/stats.py — do not edit by hand)", "",
    "Scope: Task 7 only (`day_class` task7-d1/d2/d3, set-aside dirs excluded). Every headline cell "
    "ran on two independent instances: day d1 (Go, Java) or d2 (inference, PostgreSQL, MongoDB, net), "
    "and day d3. Each day has 3 fixed runs.", "",
    "## Method", "",
    "- **Day value.** Go/Java: median of the 3 valid runs' fine-ladder knees (rps). Inference: median "
    "of the 3 runs' tok/s. PostgreSQL/MongoDB: the knee throughput of that day's ladder (one number per "
    "day); their 3 fixed runs are held at 80 % of the knee, so they measure stability, not capacity. "
    "These are the same numbers as `headline.md`.",
    "- **Mean.** Average of the two day values. This is the number on the slide.",
    "- **Run min–max.** Lowest and highest single run across both days (for PostgreSQL/MongoDB: the "
    "fixed runs at 80 %).",
    "- **CV within a day.** Standard deviation of a day's 3 runs divided by their mean: how much "
    "the runs on one machine disagree. Shown as the worse of the two days.",
    "- **Drift between days.** Second day minus first day, as % of the first: how much a different "
    "machine of the same type, on a different day, moved the result.",
    "- **Ratios.** Chip A mean / chip B mean. `vs x86` puts the Xeon at 1.00. `per $` divides each "
    f"mean by its on-demand price first (results/cost.md: arm {PRICE['arm']}, amd {PRICE['amd']}, "
    f"x86 {PRICE['x86']} $/h), so per-$ ratio = raw ratio × price B / price A.",
    "- **Tuning gain.** tuned mean / stock mean on the same chip (and vthreads / tuned for Java).",
    f"- **Bootstrap 95 % interval.** {B} times: pick 2 days with replacement for each chip, and inside "
    "each picked day pick 3 runs with replacement and take their median; compute the ratio of the two "
    "means. The interval is the middle 95 % of those ratios. Days are the independent unit (different "
    "machine); runs on one machine are not independent machines, so they only add within-day noise. "
    "PostgreSQL/MongoDB have one knee per day, so only days are resampled. "
    f"Fixed seed {SEED}.",
    "- **Why the bootstrap is weak here.** With 2 days per chip, resampling days can only produce 3 "
    "day combinations (d1+d1, d1+d3, d3+d3). The interval cannot see machine-to-machine variation "
    "that 2 machines did not show. Read it as \"how far apart could these two days pull the ratio\", "
    "not as a population interval. That is why the min–max envelope is reported next to it.",
    "- **Envelope.** Worst case to best case of the ratio using the day values: (A lowest day / B "
    "highest day) to (A highest day / B lowest day). For 1-day comparisons the runs are used instead.",
    "- **Labels.** `clear`: the bootstrap interval excludes 1.00 and the two chips' day ranges do not "
    "overlap. `within noise`: the day ranges overlap (the two chips cannot be separated with this data). "
    "`lean`: ranges do not overlap but the interval still reaches 1.00. Per-$ labels use the "
    "per-$ day values, so a raw tie can be a per-$ win.",
    "- **Ladder steps.** Go/Java knees come from a stepped ladder (1–2k rps steps), and "
    "PostgreSQL/MongoDB knees are the throughput at a client/thread step. A CV of 0 % means every run "
    "landed on the same step, not that there was no noise below the step size. MongoDB amd-stock and "
    "x86-stock landed on the exact same step both days (identical knees): Mongo is not CPU-bound at the "
    "knee, so that tie says little about the chips.",
    "- **Geometric mean.** The n-th root of the product of n ratios: the fair average of ratios (a 2x "
    "and a 0.5x average to 1.0x, not 1.25x).",
    "- **Hardware counters.** APerf p50 (median of 1-second samples over the run window) per run, "
    "then the median over the valid runs of both days.", "",
]

# ---------------------------------------------------------------- 1. Averages
out += ["## 1. Averages per cell", "",
        "| workload | variant | chip | per day | mean | run min–max | CV within day (worst) | drift d→d |",
        "|---|---|---|---|---|---|---|---|"]
for (w, var), chips in sorted(D.items()):
    for c in CHIPS:
        if c not in chips:
            continue
        days = chips[c]
        allr = [x for d in days for x in d["fixed"]]
        rng = f"{fmt(min(allr))}–{fmt(max(allr))}" + (" (fixed@80 %)" if w in KNEE_WL else "")
        cvw = max(cv(d["fixed"]) for d in days)
        drift = pct((days[-1]["value"] / days[0]["value"] - 1) * 100) if len(days) > 1 else "1 day only"
        out.append(f"| {w} | {var} | {NAME[c]} | {days_str(days)} | {fmt(mean(days))} {UNIT[w]} | "
                   f"{rng} | {cvw:.2f} % | {drift} |")
out += ["", "PostgreSQL/MongoDB run CV is the fixed runs at a set target, so near 0 by construction; "
        "their day-to-day drift is the knee's.", ""]

# ---------------------------------------------------------------- 2+3. Chip ratios
PAIRS = (("arm", "x86"), ("amd", "x86"), ("arm", "amd"))
out += ["## 2–3. Chip ratios with uncertainty", "",
        "Raw and per $. Interval = bootstrap 95 %; envelope = day min–max (see Method).", "",
        "| workload | variant | pair | basis | ratio | bootstrap 95 % | envelope | label |",
        "|---|---|---|---|---|---|---|---|"]
chip_cmp = {}
for (w, var), chips in sorted(D.items()):
    for a, b in PAIRS:
        if a not in chips or b not in chips:
            continue
        for basis, scale in (("raw", 1.0), ("per $", PRICE[b] / PRICE[a])):
            c = compare(chips[a], chips[b], scale)
            chip_cmp[(w, var, a, b, basis)] = c
            record("chip", w, var, f"{a}/{b} {basis}", c)
            out.append(f"| {w} | {var} | {a}/{b} | {basis} | {cmp_cells(c)} |")
out.append("")

# ---------------------------------------------------------------- 2c. Tuning gains
out += ["## 2c. Tuning gain per chip", "",
        "| workload | comparison | chip | ratio | bootstrap 95 % | envelope | label |",
        "|---|---|---|---|---|---|---|"]
TUNES = [(w, "tuned", "stock") for w in ("java", "inference", "postgres", "mongo")] + \
        [("java", "tuned-vthreads", "tuned")]
for w, num, den in TUNES:
    for c in CHIPS:
        a, b = D.get((w, num), {}).get(c), D.get((w, den), {}).get(c)
        if a and b:
            r = compare(a, b)
            record("tuning", w, f"{num}/{den}", c, r)
            out.append(f"| {w} | {num} / {den} | {NAME[c]} | {cmp_cells(r)} |")
# 1-day x86 extras: compare against the same day only (same run-to-run conditions).
for w, num, den in (("java", "smtoff", "stock"), ("inference", "t8", "tuned")):
    a = D[(w, num)]["x86"]
    b = [d for d in D[(w, den)]["x86"] if d["day"] == a[0]["day"]]
    r = compare(a, b)
    record("tuning", w, f"{num}/{den}", "x86", r, note=f"1 day only ({a[0]['day']}), runs resampled")
    out.append(f"| {w} | x86-{num} / x86-{den} ({a[0]['day']} only) | {NAME['x86']} | {cmp_cells(r)} |")
out += ["", "The two x86 extras ran on one day only: their interval resamples 3 runs on one machine "
        "and says nothing about machine-to-machine variation; the envelope uses run min–max. "
        "x86-smtoff also carries the full JIT bundle that x86-tuned does not "
        "(facts-setup.md open question 1), so it is not a single-variable comparison.", ""]

# ---------------------------------------------------------------- 4. Cross-workload
BEST = [("go", "stock"), ("java", "tuned"), ("java", "tuned-vthreads"), ("inference", "tuned"),
        ("postgres", "tuned"), ("mongo", "tuned")]
GEO = {"best (go stock, java tuned, inference/postgres/mongo tuned)":
       [k for k in BEST if k != ("java", "tuned-vthreads")],
       "same with java vthreads": [k for k in BEST if k != ("java", "tuned")],
       "stock only (go, java, inference, postgres, mongo)":
       [(w, "stock") for w in ("go", "java", "inference", "postgres", "mongo")]}
hdr = "| workload | variant | arm/x86 per $ | amd/x86 per $ | arm/amd per $ | arm/x86 raw | amd/x86 raw | arm/amd raw |"
out += ["## 4. Cross-workload summary (per $, x86 = 1.00)", "",
        "Best variant per chip = tuned where it was measured (Go has only stock). Java vthreads shown "
        "as its own row. Label after each ratio.", "", hdr, "|---|---|---|---|---|---|---|---|"]


def cell(w, var, a, b, basis):
    c = chip_cmp[(w, var, a, b, basis)]
    return f"{c['ratio']:.2f}x {c['label']}"


for w, var in BEST:
    out.append(f"| {w} | {var} | " + " | ".join(
        cell(w, var, a, b, basis) for basis in ("per $", "raw") for a, b in PAIRS) + " |")
out += ["", "Geometric mean across workloads (net excluded: its throughput is the instance network cap):", "",
        "| set | arm/x86 per $ | amd/x86 per $ | arm/amd per $ | arm/x86 raw | amd/x86 raw | arm/amd raw |",
        "|---|---|---|---|---|---|---|"]
geo_rows = {}
for name, keys in GEO.items():
    vals = [math.exp(statistics.mean(math.log(chip_cmp[(w, v, a, b, basis)]["ratio"]) for w, v in keys))
            for basis in ("per $", "raw") for a, b in PAIRS]
    geo_rows[name] = vals
    out.append(f"| {name} | " + " | ".join(f"{x:.2f}x" for x in vals) + " |")
out.append("")

# ---------------------------------------------------------------- 5. Net
out += ["## 5. Network (iperf3, d2 only)", "",
        "Net ran on day d2 only, so there is no second instance and no interval. Throughput is the "
        "instance's network cap, not a chip property; the chip shows up in CPU cores spent per Gbps "
        "(SUT node CPU minus its idle baseline, per direction, median of 3 runs).", "",
        "| chip | variant | Gbps fwd | Gbps rev | cores/Gbps fwd | cores/Gbps rev |",
        "|---|---|---|---|---|---|"]
net = {(r["chip"], r["variant"]): r for r in cells if r["workload"] == "net"}
assert {r["day_class"] for r in cells if r["workload"] == "net"} == {"task7-d2"}
for c in CHIPS:
    for var in ("stock", "tuned"):
        r = net[(c, var)]
        f = lambda k: float(r[k])
        out.append(f"| {NAME[c]} | {var} | {f('headline_median'):.2f} | {f('gbps_rev_median'):.2f} | "
                   f"{f('cpu_cores_per_gbps_fwd_median'):.3f} | {f('cpu_cores_per_gbps_rev_median'):.3f} |")
    s, t = (float(net[(c, v)]["cpu_cores_per_gbps_fwd_median"]) for v in ("stock", "tuned"))
    out.append(f"| {NAME[c]} | tuned/stock | | | {t/s:.2f}x | |")
out += ["", "The \"tuned\" net profile is a latency knob (IRQ pinning, adaptive-rx off): it buys no "
        "Gbps (already at the cap) and costs CPU per Gbps.", ""]

# ---------------------------------------------------------------- 6. Counters
out += ["## 6. Hardware counters (APerf, p50)", "",
        "Only IPC, branch-MPKI, L1i-MPKI and frontend stalls (per 1000 cycles) exist on all three chips. "
        "m8i (x86) exposes nothing beyond these plus L1d; m8a (amd) has no L1d/L3/backend stall; m9g (arm) "
        "has everything but L3 (data/README.md). Each vendor maps these names to its own PMU events, so "
        "cross-vendor stall and MPKI numbers are indicative, not exact. Net: APerf covers idle baseline + "
        "forward only.", "",
        "| workload | variant | chip | runs | IPC | branch MPKI | L1i MPKI | frontend stall /kc |",
        "|---|---|---|---|---|---|---|---|"]
T = {}
for r in tele:
    if (r["results_dir"], r["workload"], r["cell"], r["run"]) in valid_keys:
        T.setdefault((r["workload"], r["variant"], r["chip"]), []).append(r)
for (w, var, c) in sorted(T, key=lambda k: (k[0], k[1], CHIPS.index(k[2]))):
    rs = T[(w, var, c)]
    med = []
    for m in PMU:
        xs = [float(r[f"pmu_{m}_p50"]) for r in rs if r[f"pmu_{m}_p50"]]
        med.append(f"{statistics.median(xs):.2f}" if xs else "–")
    out.append(f"| {w} | {var} | {NAME[c]} | {len(rs)} | " + " | ".join(med) + " |")
out.append("")

# ---------------------------------------------------------------- Labels list
out += ["## Label list (every comparison above: chip pairs raw and per $, then tuning gains)", ""]
for lab in ("clear", "lean", "within noise"):
    items = [f"{x['workload']} {x['variant']} {x['comparison']} {x['ratio']:.2f}x"
             for x in comparisons if x["label"] == lab]
    out.append(f"- **{lab}** ({len(items)}): " + "; ".join(items))
out.append("")

# ---------------------------------------------------------------- sanity vs headline.md
for (w, var, a, want) in (("go", "stock", "arm", 1.97), ("go", "stock", "amd", 1.26),
                          ("postgres", "tuned", "amd", 1.52), ("java", "tuned-vthreads", "arm", 2.11),
                          ("inference", "stock", "arm", 2.36), ("mongo", "tuned", "arm", 1.36)):
    got = chip_cmp[(w, var, a, "x86", "per $")]["ratio"]
    assert round(got, 2) == want, (w, var, a, got, want)

(ROOT / "analysis/stats.md").write_text("\n".join(out))
with open(DATA / "stats-comparisons.csv", "w", newline="") as f:
    wr = csv.DictWriter(f, fieldnames=list(comparisons[0]))
    wr.writeheader()
    wr.writerows(comparisons)
print("\n".join(out))
print("sanity check vs headline.md per-$ ratios: OK")
