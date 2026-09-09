"""CR-144: StockMovement unit_cost may only be written through
``StockMovement.stamp_cost`` in backend/inventory/models.py.

A raw ``.update(unit_cost=...)`` QuerySet write bypasses cost-layer
recomputation, so running weighted cost silently diverges from the movement
history and every downstream COGS / valuation / GL figure is wrong with no
error. This is the one behavioural guard kept verbatim from the retired wave
scripts (see ../GATE_INVENTORY.md).
"""

from __future__ import annotations

import re
from pathlib import Path

NAME = "no_raw_unit_cost_update"
CONSEQUENCE = (
    "A raw StockMovement.update(unit_cost=) bypasses stamp_cost; running cost "
    "diverges from movements and all COGS/valuation/GL figures go wrong silently."
)

_PATTERN = re.compile(r"\.update\s*\([^)]*unit_cost\s*=")
_ALLOWED = {"backend/inventory/models.py"}


def check(root: Path) -> list[str]:
    backend = root / "backend"
    violations: list[str] = []
    if not backend.exists():
        return [f"{NAME}: backend/ not found under {root}"]
    for py in backend.rglob("*.py"):
        parts = set(py.parts)
        if ".venv" in parts or "migrations" in parts or "tests" in parts:
            continue
        rel = py.relative_to(root).as_posix()
        if rel in _ALLOWED:
            continue
        try:
            content = py.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in _PATTERN.finditer(content):
            line = content[: m.start()].count("\n") + 1
            violations.append(f"{rel}:{line}: {m.group(0).strip()}")
    return violations


def make_bad_tree(tmp: Path) -> None:
    d = tmp / "backend" / "somewhere"
    d.mkdir(parents=True, exist_ok=True)
    (d / "bad.py").write_text(
        "def oops(qs):\n"
        "    StockMovement.objects.filter(id=1).update(unit_cost=Decimal('1'))\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    import sys

    root = Path(__file__).resolve().parents[3]
    out = check(root)
    if out:
        print(f"GUARD FAIL {NAME}:")
        for v in out:
            print("  ", v)
        sys.exit(1)
    print(f"GUARD OK {NAME}")
