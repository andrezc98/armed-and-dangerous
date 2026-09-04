"""What the lab day cost, from rates captured that same day.

Nothing here hardcodes a price. `results/cost.md` is filled by hand on lab day
with the rates read off the AWS pricing page for the region actually used, and
this module refuses to produce a ledger while any of them still says TODO: a
stale price on a $/kop slide is a wrong number, not an approximate one.
"""

import json
import re
from pathlib import Path

COST_MD = Path(__file__).resolve().parent.parent / "results" / "cost.md"

# Charged for the whole lab day rather than per cell: the loader and tools node
# groups sit at desired=1 from apply to destroy, and so does the control plane.
FIXED_PER_DAY = ("c7i.4xlarge", "m7g.large", "eks-control-plane")

# Instance names start with a letter, so the |---|---| separator row never matches.
_ROW = re.compile(r"^\|\s*([A-Za-z][\w.-]*)\s*\|\s*([^|\s]+)\s*\|")
_SCALAR = re.compile(r"^-\s*(\w+):\s*(\S+)\s*$")


def _number(name, raw):
    try:
        return float(raw)
    except ValueError:
        raise RuntimeError(
            f"{name} is {raw!r} in {COST_MD.name}: capture the real value on lab day before running the ledger"
        ) from None


def read(path=COST_MD):
    """{'rates': {instance: usd_per_hour}, 'estimate_per_day_usd': f, 'fixed_hours_per_day': f}."""
    out = {"rates": {}}
    for line in Path(path).read_text().splitlines():
        row = _ROW.match(line)
        if row and row.group(2) not in ("---", "usd_per_hour"):
            out["rates"][row.group(1)] = _number(row.group(1), row.group(2))
            continue
        scalar = _SCALAR.match(line.strip())
        if scalar:
            out[scalar.group(1)] = _number(scalar.group(1), scalar.group(2))
    return out


def rates(path=COST_MD):
    return read(path)["rates"]


def _cells(day, rate):
    """[(cell.json, usd)] for one lab day.

    Each cell writes a cell.json with the minutes its node group actually spent
    above desired=0; that is the only thing being billed per cell.
    """
    out = []
    for cellfile in sorted(Path(day).glob("*/*/cell.json")):
        c = json.loads(cellfile.read_text())
        out.append((c, c["minutes"] * rate[c["instance_type"]] / 60 * c["nodes"]))
    return out


def day_total(results_dir, cost_md=COST_MD):
    """(USD already committed today, the day's declared estimate).

    What the budget gate in cell.py asks before it scales a node group up: the
    cells already recorded plus the fixed line, which is running whether or not
    another cell is measured.
    """
    book = read(cost_md)
    total = sum(usd for _, usd in _cells(results_dir, book["rates"]))
    total += book["fixed_hours_per_day"] * sum(book["rates"][i] for i in FIXED_PER_DAY)
    return total, book["estimate_per_day_usd"]


def ledger(results_dir, cost_md=COST_MD):
    """Markdown ledger for one lab day (results/<date>/), cell by cell."""
    day = Path(results_dir)
    book = read(cost_md)
    rate = book["rates"]

    lines = [
        f"# Ledger {day.name}",
        "",
        "| workload | cell | instancia | nodos | minutos | USD |",
        "|---|---|---|---|---|---|",
    ]
    total = 0.0
    for c, usd in _cells(day, rate):
        total += usd
        lines.append(
            f"| {c['workload']} | {c['cell']} | {c['instance_type']} | "
            f"{c['nodes']} | {c['minutes']:.1f} | {usd:.2f} |"
        )

    hours = book["fixed_hours_per_day"]
    fixed = hours * sum(rate[i] for i in FIXED_PER_DAY)
    total += fixed
    lines += [
        f"| (fijo) | loader + tools + control plane | {', '.join(FIXED_PER_DAY)} | "
        f"1 | {hours * 60:.1f} | {fixed:.2f} |",
        f"| **total** | | | | | **{total:.2f}** |",
        "",
        f"estimate_per_day_usd: {book['estimate_per_day_usd']:.2f} - "
        + ("**OVER_ESTIMATE**" if total > book["estimate_per_day_usd"] else "OK"),
    ]
    return "\n".join(lines) + "\n"
