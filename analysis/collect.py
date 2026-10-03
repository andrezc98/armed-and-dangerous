"""Walk every results/<dir>/ and flatten it into analysis/data/{cells,runs,telemetry}.csv.

Read-only over results/. Stdlib only, plus runner/knee.py (itself stdlib only)
so validity is judged by the exact rules runner/analysis/stats.py uses.

    python3 analysis/collect.py
"""

import csv
import json
import re
import sys
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
OUT = ROOT / "analysis" / "data"
sys.path.insert(0, str(ROOT / "runner"))
import knee  # noqa: E402  parse_ycsb, invalid_reasons, ycsb_invalid_reasons

# Fallback only: every cell.json carries instance_type (runner/config.py INSTANCE).
INSTANCE = {"arm": "m9g.4xlarge", "amd": "m8a.4xlarge", "x86": "m8i.4xlarge"}
HEADLINE = {  # workload -> (metric name, unit)
    "go": ("run_knee", "rps"), "java": ("run_knee", "rps"),
    "inference": ("tok_s", "tok/s"),
    "postgres": ("fixed_ops", "tps"), "mongo": ("fixed_ops", "ops/s"),
    "net": ("gbps_fwd", "Gbps"),
}
KNEE_UNIT = {"go": "rps", "java": "rps", "postgres": "tps", "mongo": "ops/s"}
# Workload dirs the lab set aside (progress.md): postgres at fixed_clients_factor 2,
# mongo on an EBS-throughput-bound volume. Same parser as the base workload.
SET_ASIDE = {"postgres-2x": "fixed_clients_factor=2 rerun set aside (progress.md, commit 960d17a)",
             "mongo-ebs125": "EBS-bound mongo run set aside (progress.md, T7 D2)"}

skipped = []  # (path, reason) -> README


def rel(p):
    return str(Path(p).relative_to(RESULTS))


def read_json(p):
    p = Path(p)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception as e:
        skipped.append((rel(p), f"unparseable JSON: {e}"))
        return None


def base_workload(w):
    return w.split("-")[0]


def day_class(name):
    m = re.search(r"task7-d\d", name)
    if m:
        return m.group(0)
    if "-cal-" in name:
        return "calibration"
    if "-ab-" in name:
        return "ab-test"
    return "early-lab"


def spread(vals):
    vals = [v for v in vals if v is not None]
    return (median(vals), min(vals), max(vals)) if vals else (None, None, None)


def js(v):
    return json.dumps(v, sort_keys=True) if v not in (None, [], {}) else ""


def us_ms(line, key):
    v = (line or {}).get(key)
    return v / 1000.0 if v is not None else None


# ---------------------------------------------------------------- one run
def parse_run(run, wl, slo_ms):
    """Every per-run field on disk, plus the stats.py validity verdict."""
    meta = read_json(run / "meta.json")
    r = {"run": run.name, "has_meta": meta is not None}
    meta = meta or {}
    for k in ("run_knee", "rate", "target_ops", "clients", "knee_clients", "threads",
              "loader_peak_percent", "cpuset", "cpuset_count", "cstates_ready",
              "lag_p99_ms", "lag_max_ms", "pgbench_threads", "mongo_documents",
              "aperf", "flamegraph"):
        r[k] = meta.get(k)
    r["mongo_warmup"] = js(meta.get("mongo_warmup"))
    r["pgbench_pod_cores_max"] = max(meta["pgbench_pod_cores"].values()) if meta.get("pgbench_pod_cores") else None
    r["actuator"] = js(meta.get("actuator"))
    r["meta_invalid"] = "; ".join(meta.get("invalid") or [])
    r["invalid_before_rejudge"] = "; ".join(meta.get("invalid_before_rejudge") or [])
    r["rejudged"] = meta.get("rejudged") or ""
    si = (meta.get("llama_system_info") or [""])[0]
    m = re.search(r"n_threads = (\d+)", si)
    r["llama_n_threads"] = int(m.group(1)) if m else None

    fine = read_json(run / "knee-fine.json")
    if fine:
        eb = fine.get("ended_by") or {}
        r.update(fine_coarse_knee=fine.get("coarse_knee"), fine_ended_by_kind=eb.get("kind"),
                 fine_ended_by_step=eb.get("step"), fine_invalid="; ".join(fine.get("invalid") or []),
                 fine_loader_guard_waived=bool(fine.get("loader_guard_waived")))

    reasons = list(meta.get("invalid") or [])
    measured = False
    head = None
    summary = read_json(run / "k6.json") or read_json(run / "llama.json")
    report = next((run / n for n in ("ycsb.txt", "pgbench.txt") if (run / n).exists()), None)
    if summary:
        measured = True
        mt = summary.get("metrics", {})
        d = mt.get("http_req_duration", {}).get("values", {})
        r.update(p50_ms=d.get("med"), p90_ms=d.get("p(90)"), p95_ms=d.get("p(95)"),
                 p99_ms=d.get("p(99)"), p999_ms=d.get("p(99.9)"), max_ms=d.get("max"),
                 avg_ms=d.get("avg"),
                 delivered_rps=mt.get("http_reqs", {}).get("values", {}).get("rate"),
                 requests=mt.get("http_reqs", {}).get("values", {}).get("count"),
                 http_req_failed_rate=mt.get("http_req_failed", {}).get("values", {}).get("rate"),
                 dropped_iterations=mt.get("dropped_iterations", {}).get("values", {}).get("count", 0),
                 iterations=mt.get("iterations", {}).get("values", {}).get("count"),
                 duration_s=summary.get("state", {}).get("testRunDurationMs", 0) / 1000.0 or None)
        tok = mt.get("llama_predicted_tokens")
        if tok and r["duration_s"]:
            r["llama_predicted_tokens"] = tok["values"]["count"]
            r["tok_s"] = tok["values"]["count"] / r["duration_s"]  # stats.py formula
            r["llama_slot_tok_s_med"] = mt.get("llama_predicted_per_second", {}).get("values", {}).get("med")
            r["llama_prompt_ms_med"] = mt.get("llama_prompt_ms", {}).get("values", {}).get("med")
            r["llama_predicted_ms_med"] = mt.get("llama_predicted_ms", {}).get("values", {}).get("med")
        if not meta.get("invalid"):
            reasons += knee.invalid_reasons(summary, slo_ms, meta.get("rate"))
        head = r.get("tok_s") if wl == "inference" else r.get("run_knee")
    elif report:
        measured = True
        r["report_file"] = report.name
        parsed = knee.parse_ycsb(report.read_text())
        rd, tot = parsed.get("READ"), parsed.get("TOTAL")
        r.update(fixed_ops=(tot or {}).get("OPS"), read_ops=(rd or {}).get("OPS"),
                 update_ops=parsed.get("UPDATE", {}).get("OPS"),
                 p50_ms=us_ms(rd, "50th(us)"), p90_ms=us_ms(rd, "90th(us)"),
                 p95_ms=us_ms(rd, "95th(us)"), p99_ms=us_ms(rd, "99th(us)"),
                 p999_ms=us_ms(rd, "99.9th(us)"), max_ms=us_ms(rd, "Max(us)"),
                 avg_ms=us_ms(rd, "Avg(us)"), update_p99_ms=us_ms(parsed.get("UPDATE"), "99th(us)"),
                 duration_s=(tot or {}).get("Takes(s)"), requests=(tot or {}).get("Count"),
                 pgbench_failed=(rd or {}).get("Failed"), pgbench_samples=(rd or {}).get("Samples"))
        missing = [x for x in ("READ", "TOTAL") if x not in parsed]
        if missing:
            reasons.append(f"{report.name} has no {'/'.join(missing)} line")
        elif "99th(us)" not in rd:
            reasons.append(f"no_latency_samples: {report.name}")
        elif not meta.get("invalid"):
            reasons += knee.ycsb_invalid_reasons(parsed, slo_ms, meta.get("target_ops"))
        head = r["fixed_ops"]
    elif (run / "iperf.json").exists():
        measured = True
        for tag, name in (("fwd", "iperf.json"), ("rev", "iperf-reverse.json")):
            e = (read_json(run / name) or {}).get("end")
            if not e:
                continue
            r[f"gbps_{tag}"] = e["sum_received"]["bits_per_second"] / 1e9
            r[f"gbps_sent_{tag}"] = e["sum_sent"]["bits_per_second"] / 1e9
            r[f"retransmits_{tag}"] = e["sum_sent"].get("retransmits")
            cpu = e.get("cpu_utilization_percent") or {}
            r[f"iperf_client_cpu_pct_{tag}"] = cpu.get("host_total")
            r[f"iperf_server_sut_cpu_pct_{tag}"] = cpu.get("remote_total")
        cores = meta.get("net_cpu_cores") or {}
        r.update(net_cpu_baseline_cores=cores.get("baseline"), net_cpu_fwd_cores=cores.get("fwd"),
                 net_cpu_rev_cores=cores.get("rev"), net_cpu_notes="; ".join(meta.get("net_cpu_notes") or []))
        base = cores.get("baseline")
        for tag in ("fwd", "rev"):
            if base is not None and cores.get(tag) is not None and r.get(f"gbps_{tag}"):
                r[f"cpu_cores_per_gbps_{tag}"] = (cores[tag] - base) / r[f"gbps_{tag}"]
        head = r.get("gbps_fwd")
    r["measured"] = measured
    r["invalid_reasons"] = "; ".join(dict.fromkeys(reasons))
    r["valid"] = measured and not reasons
    r["headline_value"] = head
    return r


# ---------------------------------------------------------------- telemetry
def aperf_js(path):
    """aperf report data/js/*.js: `name = {json}` per line; first line is the data."""
    line = path.read_text().split("\n", 1)[0]
    return json.loads(line.split("=", 1)[1])


def telemetry(run):
    t = {"run": run.name}
    samples = read_json(run / "top.json")
    if isinstance(samples, list) and samples:
        def col(k, scale=1.0):
            return [s[k] / scale for s in samples if s.get(k) is not None]
        t["top_samples"] = len(samples)
        t["top_source"] = ",".join(sorted({s.get("source", "kubectl-top") for s in samples}))
        for name, key, scale in (("node_cpu_cores", "node_cpu_millicores", 1000.0),
                                 ("node_cpu_pct", "node_cpu_percent", 1.0),
                                 ("pod_cpu_cores", "pod_cpu_millicores", 1000.0),
                                 ("loader_cpu_pct", "loader_cpu_percent", 1.0)):
            v = col(key, scale)
            t[f"top_{name}_median"], _, t[f"top_{name}_max"] = spread(v)
    fg = read_json(run / "flamegraph.json")
    t["flamegraph_exists"] = (run / "flamegraph.json").exists()
    if fg:
        fb, md = fg.get("flamebearer") or {}, fg.get("metadata") or {}
        # ponytail: raw numTicks (ns) omitted: 12 digits, reads as an account id to a sanitize grep; flame_cpu_seconds carries it.
        t["flame_sample_rate"] = md.get("sampleRate")
        t["flame_units"] = md.get("units")
        t["flame_cpu_seconds"] = fb["numTicks"] / md["sampleRate"] if fb.get("numTicks") and md.get("sampleRate") else None
        t["flame_distinct_frames"] = len(fb.get("names") or [])
    reports = sorted((run / "aperf").glob("aperf_record_*/aperf_record_report/data/js"))
    t["aperf_report"] = bool(reports)
    if not reports:
        if (run / "aperf").exists():
            skipped.append((rel(run / "aperf"), "no extracted aperf_record_report/data/js"))
        return t
    d = reports[-1]
    try:
        raw = json.loads((d / "runs.js").read_text().split("=", 1)[1])
        t["aperf_seconds"] = (raw[0]["collection_end_ms"] - raw[0]["collection_start_ms"]) / 1000.0
        kv = aperf_js(d / "systeminfo.js")["runs"]["aperf_record"]["key_value_groups"][""]["key_values"]
        t["aperf_instance_type"], t["aperf_cpus"], t["aperf_kernel"] = (
            kv.get("Instance Type"), kv.get("CPUs"), kv.get("Kernel Version"))
        for m, v in aperf_js(d / "cpu_utilization.js")["runs"]["aperf_record"]["metrics"].items():
            t[f"cpu_{m}_avg"] = v["stats"]["avg"]
            t[f"cpu_{m}_p50"] = v["stats"]["p50"]
        for m, v in aperf_js(d / "perf_stat.js")["runs"]["aperf_record"]["metrics"].items():
            agg = next((s for s in v["series"] if s.get("is_aggregate")), v["series"][0])
            # ponytail: a 2-point all-zero series is aperf's placeholder for a
            # PMU event this CPU does not expose; NA, not a measured 0.
            ok = len(agg["values"]) > 2
            t[f"pmu_{m}_avg"] = v["stats"]["avg"] if ok else None
            t[f"pmu_{m}_p50"] = v["stats"]["p50"] if ok else None
    except Exception as e:
        skipped.append((rel(d), f"aperf report parse error: {e!r}"))
    return t


# ---------------------------------------------------------------- one cell
def parse_cell(cdir, day):
    wl, cellname = cdir.parent.name, cdir.name
    bw = base_workload(wl)
    chip, _, variant = cellname.partition("-")
    cell_json = read_json(cdir / "cell.json") or {}
    kj = read_json(cdir / "knee.json") or {}
    slo = kj.get("slo_ms")
    c = {"results_dir": day, "day_class": day_class(day), "date": day[:10], "workload": wl,
         "cell": cellname, "chip": chip, "variant": variant,
         "set_aside": SET_ASIDE.get(wl, ""),
         "instance_type": cell_json.get("instance_type") or INSTANCE.get(chip),
         "cell_json_workload": cell_json.get("workload"), "cell_json_cell": cell_json.get("cell"),
         "nodes": cell_json.get("nodes"), "minutes": cell_json.get("minutes"),
         "runs_requested": cell_json.get("runs"), "has_cell_json": bool(cell_json),
         "has_knee_json": bool(kj)}
    eb = kj.get("ended_by") or {}
    if kj:
        closed = kj.get("unit") in ("clients", "threads")
        c.update(knee_unit_raw=kj.get("unit"),
                 knee_throughput=kj.get("ops") if closed else kj.get("knee"),
                 knee_throughput_unit=KNEE_UNIT.get(bw),
                 knee_step=kj.get("knee"), slo_ms=slo,
                 ended_by_kind=eb.get("kind"), ended_by_step=eb.get("step"),
                 ended_by_p99_ms=eb.get("p99_ms"), ended_by_reason=eb.get("reason"),
                 knee_invalid="; ".join(kj.get("invalid") or []),
                 knee_invalid_steps=js(kj.get("invalid_steps")),
                 knee_loader_peak_percent=kj.get("loader_peak_percent"),
                 loader_guard_waived=(kj.get("loader_guard_waived") or {}).get("why", ""),
                 knee_series=js(kj.get("series")))
    c["cell_invalid"] = "; ".join(cell_json.get("invalid") or [])
    before = cell_json.get("invalid_before_rejudge") or kj.get("invalid_before_rejudge") or []
    c["invalid_before_rejudge"] = "; ".join(before)
    c["rejudged"] = cell_json.get("rejudged") or kj.get("rejudged") or ""
    c["app_env"] = js(cell_json.get("app_env"))
    si = (cell_json.get("llama_system_info") or [""])[0]
    m = re.search(r"n_threads = (\d+)", si)
    c["llama_n_threads"] = int(m.group(1)) if m else None
    c["llama_system_info"] = si
    pg = cell_json.get("postgres") or {}
    if pg:
        aw = pg.get("after_warmup") or {}
        al = pg.get("after_ladder") or {}
        c.update(pg_shared_buffers=pg.get("shared_buffers"), pg_effective_cache_size=pg.get("effective_cache_size"),
                 pg_max_connections=pg.get("max_connections"), pg_huge_pages=pg.get("huge_pages"),
                 pg_huge_pages_status=pg.get("huge_pages_status"), pg_database_bytes=pg.get("database_bytes"),
                 pg_shmem_thp=pg.get("shmem_thp"), pg_shmem_enabled_after_warmup=aw.get("shmem_enabled"),
                 pg_shmem_huge_share_after_warmup=aw.get("shmem_huge_share"),
                 pg_shmem_huge_share_after_ladder=al.get("shmem_huge_share"))

    runs = [parse_run(r, bw, slo) for r in sorted(cdir.glob("run-*"), key=lambda p: int(p.name[4:]))
            if r.is_dir()]
    tel = [telemetry(r) for r in sorted(cdir.glob("run-*"), key=lambda p: int(p.name[4:])) if r.is_dir()]
    ident = {k: c[k] for k in ("results_dir", "day_class", "workload", "cell", "chip", "variant")}
    runs = [{**ident, **r} for r in runs]
    tel = [{**ident, **t} for t in tel]

    metric, unit = HEADLINE[bw]
    valid = [r for r in runs if r["valid"]]
    c.update(n_run_dirs=len(runs), n_runs_measured=sum(r["measured"] for r in runs),
             n_runs_valid=len(valid), headline_metric=metric, headline_unit=unit)
    c["headline_median"], c["headline_min"], c["headline_max"] = spread([r["headline_value"] for r in valid])
    c["headline_median_all_runs"] = spread([r["headline_value"] for r in runs])[0]
    c["headline_source"] = "valid runs" if c["headline_median"] is not None else ""
    if (c["headline_median"] is None and bw in ("go", "java") and kj.get("unit") == "rps"
            and kj.get("knee") and not kj.get("invalid")):  # stricter than stats.py: no invalid knee
        # stats.py: results from before the fine ladder have only the coarse knee.
        c["headline_median"] = c["headline_min"] = c["headline_max"] = kj["knee"]
        c["headline_source"] = "coarse knee.json (no valid run_knee)"
    for k in ("p99_ms", "delivered_rps", "fixed_ops", "gbps_rev", "cpu_cores_per_gbps_fwd",
              "cpu_cores_per_gbps_rev", "lag_p99_ms"):
        c[f"{k}_median"] = spread([r.get(k) for r in valid])[0]
    c["run_loader_peak_percent_max"] = max((r["loader_peak_percent"] for r in runs
                                            if r["loader_peak_percent"] is not None), default=None)
    c["runs_invalid_before_rejudge"] = sum(bool(r["invalid_before_rejudge"]) for r in runs)
    c["run_invalid_reasons"] = " | ".join(f"{r['run']}: {r['invalid_reasons']}" for r in runs if r["invalid_reasons"])
    return c, runs, tel


def cell_dirs(day_dir):
    for wdir in sorted(p for p in day_dir.iterdir() if p.is_dir()):
        if base_workload(wdir.name) not in HEADLINE:
            skipped.append((rel(wdir), "not a workload dir (inventory/logs/flamegraphs)"))
            continue
        for cdir in sorted(p for p in wdir.iterdir() if p.is_dir()):
            yield cdir
        for f in sorted(p for p in wdir.iterdir() if p.is_file()):
            skipped.append((rel(f), "runner log beside the cell dirs"))


def write_csv(path, rows):
    cols = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return len(rows), len(cols)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cells, runs, tel = [], [], []
    for day in sorted(p for p in RESULTS.iterdir() if p.is_dir()):
        for f in sorted(p for p in day.iterdir() if p.is_file()):
            why = {"cluster.json": "terraform output: account IDs/ARNs, deliberately not read",
                   "ecr.json": "ECR repo URIs: account ID, deliberately not read",
                   "ledger.md": "human ledger (minutes/USD per cell), duplicated by cell.json minutes"}.get(
                f.name, "day-level artefact, not a cell (calibration side-output or log)")
            skipped.append((rel(f), why))
        for cdir in cell_dirs(day):
            c, r, t = parse_cell(cdir, day.name)
            cells.append(c)
            runs += r
            tel += t
            for f in sorted(cdir.iterdir()):
                if f.is_file() and f.name.startswith(("knee-attempt", "knee-raw-attempt")):
                    skipped.append((rel(f), "superseded knee attempt kept by hand (early lab)"))
    stats = {name: write_csv(OUT / f"{name}.csv", rows)
             for name, rows in (("cells", cells), ("runs", runs), ("telemetry", tel))}
    with open(OUT / "skipped.txt", "w") as fh:
        for p, why in skipped:
            fh.write(f"{p}\t{why}\n")
    for k, (n, ncol) in stats.items():
        print(f"{k}.csv: {n} rows x {ncol} cols")
    print(f"skipped.txt: {len(skipped)} entries")
    check(cells)


# Known Task 7 medians (speaker's notes): d1-or-d2 / d3. Fails loudly if the
# parsing drifts. Go/Java/inference = headline_median, PG/Mongo = knee ops.
EXPECTED = {("go", "arm-stock"): (36000, 37000), ("go", "amd-stock"): (28000, 30000),
            ("go", "x86-stock"): (20000, 20000), ("java", "arm-tuned"): (86000, 90000),
            ("java", "amd-tuned"): (90000, 90000), ("inference", "arm-tuned"): (100.0, 108.0),
            ("postgres", "arm-tuned"): (338.4e3, 331.9e3), ("postgres", "amd-tuned"): (604.7e3, 583.9e3),
            ("postgres", "x86-tuned"): (336.0e3, 344.9e3), ("mongo", "arm-stock"): (239.8e3, 237.5e3)}


def check(cells):
    for (wl, cell), want in EXPECTED.items():
        got = [c["knee_throughput"] if wl in ("postgres", "mongo") else c["headline_median"]
               for c in cells if c["workload"] == wl and c["cell"] == cell
               and c["day_class"].startswith("task7") and c["day_class"] != "task7-d2" * (wl in ("go", "java"))]
        assert len(got) == 2 and all(abs(g - w) <= 0.0015 * w for g, w in zip(got, want)), (wl, cell, got, want)
    print("sanity check vs Task 7 medians: OK")


if __name__ == "__main__":
    main()
