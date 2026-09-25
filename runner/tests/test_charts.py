"""Smoke test: the four figures render from fixtures without a display."""

import json
import shutil
from pathlib import Path

from analysis import charts

FIXTURES = Path(__file__).parent / "fixtures"


# stats.MIN_RUNS: a cell with fewer valid runs is flagged and the charts skip it,
# so the fixture day has the three repetitions a real cell has.
RUNS = (1, 2, 3)


def _day(tmp_path):
    """A results/<date>/ with one java cell, one inference cell and one net cell."""
    day = tmp_path / "2026-09-11"
    for cell, rps in (("arm-tuned", 200.0), ("x86-tuned", 190.0)):
        for i in RUNS:
            d = day / "java" / cell / f"run-{i}"
            d.mkdir(parents=True)
            shutil.copy(FIXTURES / "java-fixed.json", d / "k6.json")
        (day / "java" / cell / "knee.json").write_text(
            json.dumps({"unit": "rps", "knee": int(rps * 10), "slo_ms": 100})
        )
    for cell in ("arm-tuned", "x86-t8"):
        for i in RUNS:
            d = day / "inference" / cell / f"run-{i}"
            d.mkdir(parents=True)
            shutil.copy(FIXTURES / "llama-fixed.json", d / "llama.json")
    for cell in ("arm-tuned", "x86-tuned"):
        for i in RUNS:
            d = day / "net" / cell / f"run-{i}"
            d.mkdir(parents=True)
            shutil.copy(FIXTURES / "iperf3-forward.json", d / "iperf.json")
            shutil.copy(FIXTURES / "top-net.json", d / "top.json")
    (day / "arc.json").write_text(
        json.dumps({"arm": [["m6g", 900], ["m7g", 1200], ["m9g", 2100]],
                    "x86": [["m5", 700], ["m6i", 950], ["m8i", 1500]]})
    )
    return day


def test_render_all_writes_pngs(tmp_path):
    out = tmp_path / "figs"
    written = charts.render_all(_day(tmp_path), out)
    names = sorted(p.name for p in written)
    assert names == ["arc.png", "inference-tok-s.png", "java-knee.png", "net-cpu-per-gbps.png"]
    for path in written:
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_a_day_with_nothing_to_plot_writes_nothing(tmp_path):
    day = tmp_path / "2026-09-11"
    (day / "java" / "arm-tuned").mkdir(parents=True)
    assert charts.render_all(day, tmp_path / "figs") == []


def test_a_cell_with_too_few_valid_runs_is_not_drawn(tmp_path):
    """A bar over one run is a median with no spread behind it."""
    day = _day(tmp_path)
    for i in (2, 3):
        (day / "net" / "arm-tuned" / f"run-{i}" / "meta.json").write_text(
            json.dumps({"invalid": ["no_summary: job/iperf3-client-arm-tuned-fwd-r%d" % i]})
        )
        (day / "net" / "x86-tuned" / f"run-{i}" / "meta.json").write_text(
            json.dumps({"invalid": ["no_summary"]})
        )
    written = sorted(p.name for p in charts.render_all(day, tmp_path / "figs"))
    assert "net-cpu-per-gbps.png" not in written
    assert "java-knee.png" in written
