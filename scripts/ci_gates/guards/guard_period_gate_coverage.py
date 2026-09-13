"""G-21/G-22 (CROSS_FLOW_IMPACT_MAP.md §6): every money-amend flow — a
document `complete()`/`cancel()` that posts stock, GL, or a payment
allocation — must call ``assert_period_allows_money_amend`` before writing,
so a document dated inside a closed/soft-closed GST or accounting period
can't be created, completed, cancelled, or amended undetected.

That gate had no structural check before 2026-09-13: `PurchaseInvoice.complete`
gated on `invoice_date`, but its direct sibling `GoodsReceiptService.complete`
(posting the same kind of valuation-carrying stock) did not (G-21);
`complete_challan` gated the stock it posted, but `cancel_challan` — reversing
that exact same posting — did not (G-22). Both shipped unnoticed because no
test enumerated "every money-amend complete()/cancel()" and asserted the gate
appears; each flow only had its own black-box behavioural test.

This guard is a REGISTRY, not a blanket scan: it names every call site this
codebase's own audit has verified calls the gate today (2026-09-13,
CROSS_FLOW_IMPACT_MAP.md §6), and fails if any of them stop calling it — a
future refactor that accidentally drops the gate call is caught immediately,
the same way `guard_no_raw_unit_cost_update` catches a raw `unit_cost` write.

Extending the registry: when you verify (by reading the function, not by
grep alone) that another money-amend flow correctly calls the gate, add it
here and to CROSS_FLOW_IMPACT_MAP.md §6's call-site list together — this
guard and that doc are meant to stay in lockstep. Do not add an entry you
haven't personally confirmed; an unverified registry defeats the point.
"""

from __future__ import annotations

import ast
from pathlib import Path

NAME = "period_gate_coverage"
CONSEQUENCE = (
    "A money-amend complete()/cancel() stopped calling assert_period_allows_money_amend "
    "— a document dated inside a closed GST/accounting period could be written undetected, "
    "the same class of gap as G-21 (GoodsReceiptService) and G-22 (cancel_challan)."
)

_GATE_TOKEN = "assert_period_allows_money_amend"

# (relative path from repo root, class name, method name)
_REGISTRY: tuple[tuple[str, str, str], ...] = (
    ("backend/sales/services.py", "SalesService", "complete"),
    ("backend/sales/services.py", "SalesService", "cancel"),
    ("backend/sales/return_service.py", "ReturnService", "complete_return"),
    ("backend/sales/return_service.py", "ReturnService", "cancel_return"),
    ("backend/sales/notes_services.py", "SalesNotesService", "complete_credit_note"),
    ("backend/sales/notes_services.py", "SalesNotesService", "cancel_credit_note"),
    ("backend/sales/notes_services.py", "SalesNotesService", "complete_debit_note"),
    ("backend/sales/notes_services.py", "SalesNotesService", "cancel_debit_note"),
    ("backend/sales/notes_services.py", "SalesNotesService", "complete_challan"),
    ("backend/sales/notes_services.py", "SalesNotesService", "cancel_challan"),
    ("backend/purchases/services.py", "PurchaseService", "complete"),
    ("backend/purchases/services.py", "PurchaseService", "cancel"),
    ("backend/purchases/services.py", "PurchaseService", "complete_return"),
    ("backend/purchases/services.py", "PurchaseService", "cancel_return"),
    ("backend/purchases/notes_services.py", "PurchaseNotesService", "complete_credit_note"),
    ("backend/purchases/notes_services.py", "PurchaseNotesService", "cancel_credit_note"),
    ("backend/purchases/notes_services.py", "PurchaseNotesService", "complete_debit_note"),
    ("backend/purchases/notes_services.py", "PurchaseNotesService", "cancel_debit_note"),
    ("backend/purchases/grn_service.py", "GoodsReceiptService", "complete"),
    ("backend/purchases/grn_service.py", "GoodsReceiptService", "cancel"),
    ("backend/purchases/boe_services.py", "BillOfEntryService", "complete"),
    ("backend/purchases/boe_services.py", "BillOfEntryService", "cancel"),
    ("backend/payments/services.py", "PaymentService", "create_receipt"),
    ("backend/payments/services.py", "PaymentService", "create_supplier_payment"),
    ("backend/payments/services.py", "PaymentService", "allocate_receipt"),
    ("backend/payments/services.py", "PaymentService", "allocate_supplier_payment"),
    ("backend/payments/services.py", "PaymentService", "reverse_allocation"),
    ("backend/payments/services.py", "PaymentService", "void_receipt"),
    ("backend/payments/services.py", "PaymentService", "void_supplier_payment"),
)


def _find_method_source(tree: ast.Module, source: str, class_name: str, method_name: str) -> str | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                    return ast.get_source_segment(source, item)
    return None


def check(root: Path) -> list[str]:
    violations: list[str] = []
    for rel_path, class_name, method_name in _REGISTRY:
        path = root / rel_path
        label = f"{rel_path}::{class_name}.{method_name}"
        if not path.exists():
            violations.append(f"{label}: file not found (registry is stale — fix the path or remove the entry)")
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError) as exc:
            violations.append(f"{label}: could not parse {rel_path}: {exc}")
            continue
        segment = _find_method_source(tree, source, class_name, method_name)
        if segment is None:
            violations.append(
                f"{label}: method not found (renamed/moved? registry is stale — fix or remove the entry)"
            )
            continue
        if _GATE_TOKEN not in segment:
            violations.append(f"{label}: no longer calls {_GATE_TOKEN}")
    return violations


def make_bad_tree(tmp: Path) -> None:
    """Build every registry file with a valid (gate-calling) stub, except
    GoodsReceiptService.cancel — the one entry deliberately left broken, so
    --selftest exercises the real "method exists but dropped the gate call"
    path, not just "file missing" (which the guard also catches, but that's
    not the interesting case)."""
    by_file: dict[str, dict[str, set[str]]] = {}
    for rel_path, class_name, method_name in _REGISTRY:
        by_file.setdefault(rel_path, {}).setdefault(class_name, set()).add(method_name)

    for rel_path, classes in by_file.items():
        path = tmp / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        for class_name, methods in classes.items():
            lines.append(f"class {class_name}:")
            for method_name in sorted(methods):
                lines.append("    @staticmethod")
                lines.append(f"    def {method_name}(doc, user):")
                is_broken = (
                    rel_path == "backend/purchases/grn_service.py"
                    and class_name == "GoodsReceiptService"
                    and method_name == "cancel"
                )
                if is_broken:
                    lines.append("        doc.status = 'CANCELLED'")
                else:
                    lines.append("        from reporting.gst_periods import assert_period_allows_money_amend")
                    lines.append("        assert_period_allows_money_amend(doc.company, doc.some_date)")
                lines.append("        return doc")
                lines.append("")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
