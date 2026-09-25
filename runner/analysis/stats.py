"""Turn one cell's run-*/ directory into the handful of numbers a slide shows.

Reads only. The raw files under results/<date>/ are the record of the lab day and
nothing here rewrites them.

A cell directory looks like results/<date>/<workload>/<cell>/ and holds
knee.json plus run-1/, run-2/, ... Each run holds whichever of these the workload
produces: k6.json (java, go), llama.json (inference), ycsb.txt (mongo),
pgbench.txt (postgres),
iperf.json / iperf-reverse.json (net), and top.json for the CPU samples.
"""

import json
from pathlib import Path
from statistics import median

import capture  # window_cores: the same per-window CPU the runner writes into meta.json
import knee  # one-way: the parsers live next to the knee search that first needs them

# Below this many valid runs a median is one number with no spread behind it, so
# the cell is flagged and the charts leave it out. Not an exception: the cell
# still burned node minutes and the ledger still has to count them.
MIN_RUNS = 3


def _spread(values):
    return {"median": median(values), "min": min(values), "max": max(values)}


def _read_json(path):
    return json.loads(path.read_text()) if path.exists() else None


def _node_cores(run):
    """Median SUT node CPU in cores over the run's top.json samples."""
    samples = _read_json(run / "top.json")
    if not samples:
        return None
    return median(s["node_cpu_millicores"] for s in samples) / 1000.0


def summarize(cell_dir, usd_per_hour=None):
    """Medians and min/max over the valid runs of one cell.

    `usd_per_hour` is the SUT's on-demand rate for the lab day (cost.rates());
    without it the derived cost fields are simply absent, because a made-up rate
    on a slide is worse than no rate at all.
    """
    cell_dir = Path(cell_dir)
    out = {
        "workload": cell_dir.parent.name,
        "cell": cell_dir.name,
        "runs": 0,
        "excluded": [],
    }
    kneefile = _read_json(cell_dir / "knee.json")
    if kneefile:
        out["knee"] = kneefile
    # The fixed-run rule (knee.invalid_reasons) needs the SLO the knee was found
    # against and the rate each run was held at; both are on disk.
    slo_ms = (kneefile or {}).get("slo_ms")
    if usd_per_hour is not None:
        out["usd_per_hour"] = usd_per_hour

    p99, rps, tok_s, gbps, gbps_rev, cores, run_knees = [], [], [], [], [], [], []
    net_fwd, net_rev, net_idle, ratio_fwd, ratio_rev, new_net = [], [], [], [], [], False
    for run in sorted(p for p in cell_dir.glob("run-*") if p.is_dir()):
        # The runner already judged this run while it had the cluster in front of
        # it: a saturated loader, a cpuset that was not exclusive, a Job that
        # printed no summary. Re-deciding that from the output files alone is not
        # possible, so meta.json is authoritative and the run is dropped here.
        meta = _read_json(run / "meta.json") or {}
        if meta.get("invalid"):
            out["excluded"].append({"run": run.name, "reasons": meta["invalid"]})
            continue
        summary = _read_json(run / "k6.json") or _read_json(run / "llama.json")
        if summary:
            reasons = knee.invalid_reasons(summary, slo_ms, meta.get("rate"))
            if reasons:
                out["excluded"].append({"run": run.name, "reasons": reasons})
                continue
            p99.append(summary["metrics"]["http_req_duration"]["values"]["p(99)"])
            rps.append(summary["metrics"]["http_reqs"]["values"]["rate"])
            tokens = summary["metrics"].get("llama_predicted_tokens")
            if tokens:
                tok_s.append(tokens["values"]["count"] / (summary["state"]["testRunDurationMs"] / 1000.0))
        elif report := next((run / name for name in ("ycsb.txt", "pgbench.txt")
                             if (run / name).exists()), None):
            # go-ycsb prints its report only if it finished. A run killed part
            # way through leaves a file with no READ line, and reading that as a
            # KeyError would take the whole analysis down with it; it is one
            # invalid run, exactly like a k6 Job that printed no summary.
            # pgbench.txt (postgres) is knee.merge_pgbench's output, the same
            # line format on purpose.
            parsed = knee.parse_ycsb(report.read_text())
            missing = [line for line in ("READ", "TOTAL") if line not in parsed]
            if missing:
                out["excluded"].append(
                    {"run": run.name, "reasons": [f"{report.name} has no {'/'.join(missing)} line"]}
                )
                continue
            reasons = knee.ycsb_invalid_reasons(parsed, slo_ms, meta.get("target_ops"))
            if reasons:
                out["excluded"].append({"run": run.name, "reasons": reasons})
                continue
            # READ p99 is the latency the SLO is about; the throughput (and the
            # cost per kop) is TOTAL, because --target throttles every operation
            # and workloadb's 5 % updates are load the server carried too.
            p99.append(parsed["READ"]["99th(us)"] / 1000.0)
            rps.append(parsed["TOTAL"]["OPS"])
        elif (run / "iperf.json").exists():
            gbps.append(_read_json(run / "iperf.json")["end"]["sum_received"]["bits_per_second"] / 1e9)
            reverse = _read_json(run / "iperf-reverse.json")
            if reverse:
                gbps_rev.append(reverse["end"]["sum_received"]["bits_per_second"] / 1e9)
            # Per direction, idle baseline subtracted (cell.measure); runs from
            # before the windows existed fall back to the whole-run median below.
            # A run with windows and a hole in them gets no cpu_per_gbps at all:
            # no falling back to the whole-run formula for a new-format run.
            windows = meta.get("net_windows")
            if windows:
                new_net = True
                per = capture.window_cores(_read_json(run / "top.json") or [], windows)
                notes = capture.net_coverage(per)
                if notes:
                    out.setdefault("net_uncovered", []).append({"run": run.name, "reasons": notes})
                base = per.get("baseline")
                if base is not None:
                    net_idle.append(base)
                    if per.get("fwd") is not None:
                        net_fwd.append(per["fwd"] - base)
                        ratio_fwd.append(net_fwd[-1] / gbps[-1])
                    if per.get("rev") is not None and reverse:
                        net_rev.append(per["rev"] - base)
                        ratio_rev.append(net_rev[-1] / gbps_rev[-1])
        else:
            continue
        out["runs"] += 1
        if meta.get("run_knee") is not None:
            run_knees.append(meta["run_knee"])
        node = _node_cores(run)
        if node is not None:
            cores.append(node)

    # The capacity of the cell is the spread of its runs' own knees (the fine
    # ladder before each fixed run, cell.fine_knee). Results from before that
    # ladder existed have one coarse knee, which is then all there is.
    if run_knees:
        out["capacity"] = _spread(run_knees)
    elif kneefile and kneefile.get("unit") == "rps" and kneefile.get("knee") is not None:
        out["capacity"] = _spread([kneefile["knee"]])
    if p99:
        out["p99_ms"] = _spread(p99)
    if rps:
        out["rps"] = _spread(rps)
        if usd_per_hour is not None:
            # kilo-operations per hour at the median throughput
            out["usd_per_kop"] = usd_per_hour / (out["rps"]["median"] * 3600 / 1000)
    if tok_s:
        out["tok_s"] = _spread(tok_s)
        if usd_per_hour is not None:
            out["usd_per_mtok"] = usd_per_hour / (out["tok_s"]["median"] * 3600) * 1e6
    if gbps:
        out["gbps"] = _spread(gbps)
    if gbps_rev:
        out["gbps_reverse"] = _spread(gbps_rev)
    if cores:
        out["node_cpu_cores"] = _spread(cores)
        if gbps and not new_net:
            # Old results: whole-run CPU (both directions) over forward Gbps.
            out["cpu_per_gbps"] = out["node_cpu_cores"]["median"] / out["gbps"]["median"]
    # The number that means something on a 4xlarge pair: both sides are the same
    # instance type, so Gbps alone only reports the ENA. Each direction's CPU is
    # read in its own window, over the idle node.
    if net_idle:
        out["node_cpu_baseline_cores"] = _spread(net_idle)
    # Per run, then the median over the runs that were fully covered.
    if net_fwd:
        out["node_cpu_cores_forward"] = _spread(net_fwd)
        out["cpu_per_gbps"] = median(ratio_fwd)
    if net_rev:
        out["node_cpu_cores_reverse"] = _spread(net_rev)
        out["cpu_per_gbps_reverse"] = median(ratio_rev)
    if out["runs"] < MIN_RUNS:
        out["insufficient_runs"] = True
    return out


def summarize_all(workload_dir, rates=None):
    """{cell: summarize(cell)} for every cell directory under one workload."""
    workload_dir = Path(workload_dir)
    rates = rates or {}
    return {
        d.name: summarize(d, rates.get(d.name))
        for d in sorted(workload_dir.iterdir())
        if d.is_dir()
    }
