"""The four figures of the talk, straight from results/<date>/.

Nothing is drawn that a slide does not use: the knee per cell, tok/s against
$/Mtok, CPU per Gbps, and the generational arc. Bars carry the min/max of the
runs as error bars, because a median without its spread is a claim without a
measurement behind it.

    uv run python -m analysis.charts results/2026-09-11
    uv run python -m analysis.charts results/2026-09-11 --out /tmp/figs
"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no display on the lab machine, and none is wanted
import matplotlib.pyplot as plt  # noqa: E402

import config  # noqa: E402
import cost  # noqa: E402
from analysis import stats  # noqa: E402

SLIDES = config.REPO / "slides" / "assets"
# One colour per silicon, so a reader tells the two families apart before
# reading a single label.
ARM = "#1b6ca8"
X86 = "#b8562f"


def _colors(cells):
    return [ARM if c.startswith("arm") else X86 for c in cells]


def _errbars(spreads):
    """matplotlib wants [[below], [above]] distances, not absolute bounds."""
    return [
        [s["median"] - s["min"] for s in spreads],
        [s["max"] - s["median"] for s in spreads],
    ]


def _save(fig, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def _bars(cells, values, ylabel, title, out, spreads=None):
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(cells, values, color=_colors(cells),
           yerr=_errbars(spreads) if spreads else None, capsize=4)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3)
    fig.autofmt_xdate(rotation=30)
    return _save(fig, out)


def knee_chart(summaries, out):
    """Highest offered load that still met the SLO, cell by cell."""
    cells = [c for c, s in summaries.items() if s.get("knee", {}).get("knee")]
    if not cells:
        return None
    values = [summaries[c]["knee"]["knee"] for c in cells]
    unit = summaries[cells[0]]["knee"].get("unit", "rps")
    slo = summaries[cells[0]]["knee"].get("slo_ms")
    return _bars(cells, values, unit, f"Knee (p99 < {slo} ms)", out)


def inference_chart(summaries, out):
    """tok/s on the left axis, $/Mtok on the right: throughput is only half the story."""
    cells = [c for c, s in summaries.items() if "tok_s" in s]
    if not cells:
        return None
    tok = [summaries[c]["tok_s"] for c in cells]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(cells, [t["median"] for t in tok], color=_colors(cells),
           yerr=_errbars(tok), capsize=4)
    ax.set_ylabel("tok/s (agregado)")
    ax.grid(axis="y", alpha=0.3)
    costs = [summaries[c].get("usd_per_mtok") for c in cells]
    if any(c is not None for c in costs):
        right = ax.twinx()
        right.plot(cells, costs, marker="o", color="black", linestyle="--")
        right.set_ylabel("USD / Mtok")
    ax.set_title("Inferencia: rendimiento y costo")
    fig.autofmt_xdate(rotation=30)
    return _save(fig, out)


def net_chart(summaries, out):
    """CPU per Gbps: on a pair of identical instances, Gbps alone reports the ENA."""
    cells = [c for c, s in summaries.items() if "cpu_per_gbps" in s]
    if not cells:
        return None
    return _bars(cells, [summaries[c]["cpu_per_gbps"] for c in cells],
                 "vCPU / Gbps", "Red: CPU por Gbps", out)


def arc_chart(points, out, ylabel="rps en el knee"):
    """The generational arc: one line per silicon family across generations."""
    fig, ax = plt.subplots(figsize=(7, 4))
    for family, series in points.items():
        ax.plot([p[0] for p in series], [p[1] for p in series], marker="o",
                label=family, color=ARM if family.startswith("arm") else X86)
    ax.set_ylabel(ylabel)
    ax.set_title("Arco generacional")
    ax.grid(alpha=0.3)
    ax.legend()
    return _save(fig, out)


def render_all(day_dir, out_dir=SLIDES):
    """Every figure the day's results can support. Missing data draws nothing."""
    day_dir, out_dir = Path(day_dir), Path(out_dir)
    try:
        rates = {c: cost.rates()[config.instance_type(c)] for c in config.CELL_MNG}
    except (RuntimeError, FileNotFoundError, KeyError):
        rates = {}  # cost.md not captured yet: the figures that need it are skipped
    written = []
    for workload_dir in sorted(p for p in day_dir.iterdir() if p.is_dir()):
        summaries = stats.summarize_all(workload_dir, rates)
        name = workload_dir.name
        for chart, suffix in (
            (knee_chart, "knee"),
            (inference_chart, "tok-s"),
            (net_chart, "cpu-per-gbps"),
        ):
            path = chart(summaries, out_dir / f"{name}-{suffix}.png")
            if path:
                written.append(path)
    arc = day_dir / "arc.json"
    if arc.exists():
        written.append(arc_chart(json.loads(arc.read_text()), out_dir / "arc.png"))
    return written


def main(argv=None):
    p = argparse.ArgumentParser(prog="charts", description=__doc__.splitlines()[0])
    p.add_argument("results_day", help="results/<date>/")
    p.add_argument("--out", default=str(SLIDES))
    args = p.parse_args(argv)
    for path in render_all(args.results_day, args.out):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
