"""4.4 — invite UI capsForRole overlapping keys match capability_defaults_for_role."""

from __future__ import annotations

import re
from pathlib import Path

from accounts.models import CompanyUser

ROOT = Path(__file__).resolve().parents[3]
UI = ROOT / "web" / "src" / "pages" / "settings" / "UsersSettingsPage.tsx"

CAMEL = {
    "canManageInventory": "can_manage_inventory",
    "canImport": "can_import",
    "canCancelDocuments": "can_cancel_documents",
    "canViewFinancialReports": "can_view_financial_reports",
    "canExport": "can_export",
    "canCreateSales": "can_create_sales",
    "canCreatePurchases": "can_create_purchases",
    "canCreatePayments": "can_create_payments",
}


def _bools(block: str) -> dict[str, bool]:
    caps = {snake: False for snake in CAMEL.values()}
    for camel, snake in CAMEL.items():
        m = re.search(rf"{camel}:\s*(true|false)", block)
        if m:
            caps[snake] = m.group(1) == "true"
    return caps


def _parse_caps_for_role(src: str) -> dict[str, dict[str, bool]]:
    fn = src.split("function capsForRole", 1)[1].split("function hasAnyWorkCap", 1)[0]
    out: dict[str, dict[str, bool]] = {}
    for role in ("ACCOUNTANT", "VIEWER", "INVENTORY_STAFF", "AUDITOR", "MANAGER"):
        m = re.search(rf"if \(role === '{role}'\) \{{(.*?)\n  \}}", fn, re.S)
        assert m, f"capsForRole missing branch for {role}"
        out[role] = _bools(m.group(1))
    default = re.search(r"return \{ \.\.\.off,([^}]+)\}", fn)
    assert default, "capsForRole missing SALES_STAFF default return"
    out["SALES_STAFF"] = _bools(default.group(1))
    return out


def test_invite_ui_caps_match_backend_defaults_on_overlapping_keys():
    parsed = _parse_caps_for_role(UI.read_text(encoding="utf-8"))
    failures = []
    for role, ui in parsed.items():
        backend = CompanyUser.capability_defaults_for_role(role) or {}
        for snake, want in ui.items():
            got = bool(backend.get(snake))
            if got is not want:
                failures.append(f"{role}.{snake}: UI={want} backend={got}")
    assert not failures, "FG-2d UI/backend cap drift:\n  " + "\n  ".join(failures)
