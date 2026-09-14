"""AST guard: multi-value SalesInvoice/PurchaseInvoice status filters must
use the named predicate modules (P3-T4 / D11).

Single literal filters (`status=DRAFT`) are exempt by construction. Only
multi-value set constructions of ``Model.Status.*`` must route through
``OPEN_RECEIVABLE_STATUSES`` / ``OPEN_PAYABLE_STATUSES`` (or a reviewed
exception). Maintainer: backend lead, same bar as touching
``status_semantics.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

NAME = "status_semantics_usage"
CONSEQUENCE = (
    "A multi-value status__in filter on SalesInvoice/PurchaseInvoice does not "
    "route through status_semantics.py — the G-17/G-18 class of silent drift."
)

_SCAN_ROOTS = ("backend",)
_SKIP_PARTS = {"migrations", "tests", ".venv", "node_modules"}
_MODELS = {"SalesInvoice", "PurchaseInvoice"}

# Reviewed exceptions — same bar as touching status_semantics.py itself.
# Keyed by posix path. BoE COMPLETED+CANCELLED is not the open-payable set.
_EXCEPTION_PATHS = frozenset({"backend/purchases/boe_services.py"})


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _tuple_status_members(node: ast.AST) -> list[tuple[str, str]] | None:
    if not isinstance(node, (ast.Tuple, ast.List)):
        return None
    members: list[tuple[str, str]] = []
    for elt in node.elts:
        if (
            isinstance(elt, ast.Attribute)
            and isinstance(elt.value, ast.Attribute)
            and elt.value.attr == "Status"
            and isinstance(elt.value.value, ast.Name)
        ):
            members.append((elt.value.value.id, elt.attr))
        else:
            return None
    return members


def check(root: Path) -> list[str]:
    violations: list[str] = []
    for base in _SCAN_ROOTS:
        scan = root / base
        if not scan.exists():
            continue
        for path in scan.rglob("*.py"):
            if any(part in _SKIP_PARTS for part in path.parts):
                continue
            rel = _rel(root, path)
            try:
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=rel)
            except (OSError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if not (isinstance(node, ast.keyword) and node.arg == "status__in"):
                    continue
                members = _tuple_status_members(node.value)
                if not members or len(members) < 2:
                    continue
                models = {m[0] for m in members}
                if not models & _MODELS:
                    continue
                if rel in _EXCEPTION_PATHS:
                    continue
                statuses = "+".join(sorted({m[1] for m in members}))
                violations.append(
                    f"{rel}: inline multi-value status__in=({statuses}) — use "
                    "OPEN_RECEIVABLE_STATUSES / OPEN_PAYABLE_STATUSES "
                    "(or add a reviewed exception in this guard)"
                )
    return violations


def make_bad_tree(tmp: Path) -> None:
    bad = tmp / "backend" / "reporting" / "bad_filter.py"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text(
        """
from sales.models import SalesInvoice

def f(company):
    return SalesInvoice.objects.filter(
        company=company,
        status__in=(SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED),
    )
""",
        encoding="utf-8",
    )
