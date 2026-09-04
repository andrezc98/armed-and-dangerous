"""The ledger: what the lab day actually cost, from rates captured that same day."""

import json

import pytest

import cost

COST_MD = """# Tarifas

| instance | usd_per_hour | captured (date, source) |
|---|---|---|
| m8i.4xlarge | 1.00 | 2026-09-11, aws pricing |
| m9g.4xlarge | 2.00 | 2026-09-11, aws pricing |
| c7i.4xlarge | 0.50 | 2026-09-11, aws pricing |
| m7g.large | 0.10 | 2026-09-11, aws pricing |
| eks-control-plane | 0.10 | 2026-09-11, aws pricing |

- estimate_per_day_usd: 10.00
- fixed_hours_per_day: 4.0
"""


def _cost_md(tmp_path, text=COST_MD):
    p = tmp_path / "cost.md"
    p.write_text(text)
    return p


def _day(tmp_path):
    day = tmp_path / "2026-09-11"
    for workload, cell, instance, nodes, minutes in [
        ("java", "arm-tuned", "m9g.4xlarge", 1, 30.0),
        ("net", "x86-tuned", "m8i.4xlarge", 2, 60.0),
    ]:
        d = day / workload / cell
        d.mkdir(parents=True)
        (d / "cell.json").write_text(
            json.dumps(
                {
                    "workload": workload,
                    "cell": cell,
                    "instance_type": instance,
                    "nodes": nodes,
                    "minutes": minutes,
                }
            )
        )
    return day


def test_rates_are_read_from_the_markdown_table(tmp_path):
    assert cost.rates(_cost_md(tmp_path))["m9g.4xlarge"] == 2.00


def test_a_todo_rate_refuses_to_run(tmp_path):
    md = COST_MD.replace("| m9g.4xlarge | 2.00 |", "| m9g.4xlarge | TODO |")
    with pytest.raises(RuntimeError, match="m9g.4xlarge"):
        cost.rates(_cost_md(tmp_path, md))


def test_a_todo_scalar_refuses_to_run(tmp_path):
    md = COST_MD.replace("estimate_per_day_usd: 10.00", "estimate_per_day_usd: TODO")
    with pytest.raises(RuntimeError, match="estimate_per_day_usd"):
        cost.read(_cost_md(tmp_path, md))


def test_ledger_charges_minutes_times_rate_over_sixty_per_cell(tmp_path):
    md = _cost_md(tmp_path)
    out = cost.ledger(_day(tmp_path), cost_md=md)
    # java/arm-tuned: 30 min x 2.00/h x 1 node = 1.00
    assert "| java | arm-tuned | m9g.4xlarge | 1 | 30.0 | 1.00 |" in out
    # net/x86-tuned: 60 min x 1.00/h x 2 nodes = 2.00
    assert "| net | x86-tuned | m8i.4xlarge | 2 | 60.0 | 2.00 |" in out
    # fixed line: 4 h x (0.50 loader + 0.10 tools + 0.10 control plane) = 2.80
    assert "2.80" in out
    assert "5.80" in out  # total


def test_ledger_flags_over_estimate(tmp_path):
    md = _cost_md(tmp_path, COST_MD.replace("estimate_per_day_usd: 10.00", "estimate_per_day_usd: 5.00"))
    assert "OVER_ESTIMATE" in cost.ledger(_day(tmp_path), cost_md=md)


def test_ledger_under_the_estimate_says_so_without_the_flag(tmp_path):
    out = cost.ledger(_day(tmp_path), cost_md=_cost_md(tmp_path))
    assert "OVER_ESTIMATE" not in out
    assert "OK" in out


def test_ledger_of_a_day_with_no_cells_is_still_the_fixed_line(tmp_path):
    day = tmp_path / "2026-09-11"
    day.mkdir()
    out = cost.ledger(day, cost_md=_cost_md(tmp_path))
    assert "2.80" in out
