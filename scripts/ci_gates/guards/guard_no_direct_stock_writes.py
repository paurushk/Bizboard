"""MFG R-1: Manufacturing, Quality and Job work move stock only through ``InventoryService.post_movement``.

The stock ledger is one place. A quantity changed by writing ``StockBalance``, ``StockMovement`` or
``InventoryCostLayer`` rows directly skips the cost layers, the running cost, the quality-hold check and
the reservation release, so the balance, the ledger and the valuation stop agreeing and nothing
raises. Reading and locking (``select_for_update``) these tables is fine; creating, updating,
deleting or assigning to them is not.
"""

from __future__ import annotations

import re
from pathlib import Path

NAME = "no_direct_stock_writes"
CONSEQUENCE = (
    "Manufacturing, quality or job work code wrote a stock table directly; the balance, ledger and "
    "valuation drift apart with no error. Use InventoryService.post_movement."
)

_APPS = ("manufacturing", "quality", "jobwork")
_TABLES = r"(?:StockBalance|StockMovement|InventoryCostLayer|InventoryRunningCost)"
_PATTERNS = [
    re.compile(rf"{_TABLES}\.objects\b[^\n]*\.(?:update|delete|bulk_create|bulk_update|update_or_create)\s*\("),
    re.compile(rf"{_TABLES}\.objects\.create\s*\("),
    re.compile(rf"\b{_TABLES}\s*\(\s*(?:company|product|warehouse)\s*="),
    re.compile(r"\b(?:balance|bal|sb|stock_balance)\.on_hand\s*(?:[+\-*]?=)(?!=)"),
]


def check(root: Path) -> list[str]:
    backend = root / "backend"
    if not backend.exists():
        return [f"{NAME}: backend/ not found under {root}"]
    out: list[str] = []
    for app in _APPS:
        base = backend / app
        if not base.exists():
            continue
        for py in base.rglob("*.py"):
            if "migrations" in py.parts or "tests" in py.parts:
                continue
            text = py.read_text(encoding="utf-8", errors="ignore")
            for pattern in _PATTERNS:
                for m in pattern.finditer(text):
                    line = text[: m.start()].count("\n") + 1
                    out.append(f"{py.relative_to(root).as_posix()}:{line}: {m.group(0).strip()[:90]}")
    return out


def make_bad_tree(tmp: Path) -> None:
    d = tmp / "backend" / "manufacturing" / "services"
    d.mkdir(parents=True, exist_ok=True)
    (d / "bad.py").write_text(
        "def oops(company, product):\n"
        "    StockBalance.objects.filter(company=company, product=product).update(on_hand=0)\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    import sys

    root = Path(__file__).resolve().parents[3]
    found = check(root)
    if found:
        print(f"GUARD FAIL {NAME}:")
        for v in found:
            print("  ", v)
        sys.exit(1)
    print(f"GUARD OK {NAME}")
