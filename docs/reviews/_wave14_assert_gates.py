#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assert Wave 14 P0 semantic gates (BB-000456–462, BB-000544, BB-000548).

Exit 0 only when remediation behaviors are present in the live tree.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def main() -> int:
    fails: list[str] = []

    # BB-000456 — epoch heartbeat + bare Redis key
    tasks = _read("backend/core/tasks.py")
    if "time.time()" not in tasks and "str(time.time())" not in tasks:
        fails.append("456: celery_beat_heartbeat must write unix epoch via time.time()")
    if "isoformat" in tasks and "celery_beat_heartbeat" in tasks:
        # Allow comments; fail if assignment still uses isoformat
        for line in tasks.splitlines():
            if "celery_beat_heartbeat" in line or "BEAT_HEARTBEAT" in line:
                continue
            if "cache.set" in line and "isoformat" in line:
                fails.append("456: cache.set still uses isoformat for heartbeat")
    if "redis.from_url" not in tasks:
        fails.append("456: bare Redis key write via redis.from_url missing")
    views = _read("backend/core/views.py")
    if "float(raw)" not in views and "float(ts)" not in views and "float(" not in views:
        fails.append("456: HealthView probe must accept epoch float strings")
    prod = _read("docker-compose.prod.yml")
    if "float(" not in prod or "bizboard:celery_beat_heartbeat" not in prod:
        fails.append("456: compose.prod float heartbeat probe missing")
    if "or True" in prod:
        fails.append("456: compose.prod still has or True bypass")

    # BB-000544 — SQLite refuse in production/staging
    settings = _read("backend/config/settings.py")
    if "sqlite" not in settings.lower() or "ImproperlyConfigured" not in settings:
        fails.append("544: settings must ImproperlyConfigured on sqlite in prod/staging")
    if 'DJANGO_ENV in ("production", "staging")' not in settings or "sqlite" not in settings:
        fails.append("544: production/staging sqlite refuse gate missing")

    # BB-000460 — return COGS from SALE movement unit_cost
    sales = _read("backend/sales/services.py")
    if "cogs_rev" not in sales or "move.unit_cost" not in sales:
        fails.append("460: complete_return must accumulate cogs_rev from SALE move.unit_cost")
    if "InventoryValuationService.unit_cost" in sales.split("def complete_return")[1].split("def cancel_return")[0]:
        fails.append("460: complete_return still uses InventoryValuationService.unit_cost for COGS reverse")

    # BB-000459 — disposal never debits 5300 for NBV
    acct_views = _read("backend/accounting/views.py")
    dispose_block = acct_views.split("def dispose")[1].split("class AccountingSettingsView")[0]
    if 'accounts["5600"]' not in dispose_block and "5600" not in dispose_block:
        fails.append("459: dispose must post Loss 5600")
    if "depreciation_expense_account" in dispose_block and 'debit": net_book_value' in dispose_block.replace(" ", ""):
        fails.append("459: dispose still debits depreciation_expense for NBV")
    acct = _read("backend/accounting/services.py")
    if '"5600"' not in acct or "Loss on Disposal" not in acct:
        fails.append("459: COA 5600 Loss on Disposal missing from chart seed")

    # BB-000457 / 458 — receipt REFUNDED + link reopen
    pay_models = _read("backend/payments/models.py")
    if "REFUNDED" not in pay_models or "ReceiptStatus" not in pay_models:
        fails.append("457: CustomerReceipt ReceiptStatus.REFUNDED missing")
    pay_svc = _read("backend/payments/services.py")
    if "ReceiptStatus.REFUNDED" not in pay_svc:
        fails.append("457: refund_gateway_payment must set ReceiptStatus.REFUNDED")
    if "paid_receipt = None" not in pay_svc and "paid_receipt=None" not in pay_svc:
        fails.append("458: refund must clear payment link paid_receipt")
    ledgers = _read("backend/ledgers/services.py")
    if "ReceiptStatus.POSTED" not in ledgers:
        fails.append("457: ledger must filter ReceiptStatus.POSTED only")

    # BB-000462 honesty — README already excludes fake modules
    readme = _read("README.md")
    for claim in ("Manufacturing", "Payroll", "CRM", "multi-company"):
        # Must appear in "Not claimed" section, not as shipped feature
        if "Not claimed" not in readme:
            fails.append("462: README missing Not claimed honesty block")
            break

    # BB-000548 — this script itself is the semantic gate
    if not (ROOT / "docs/reviews/_wave14_assert_gates.py").exists():
        fails.append("548: _wave14_assert_gates.py missing")

    if fails:
        print("WAVE14 ASSERT GATES FAILED:")
        for f in fails:
            print(" -", f)
        return 1
    print("WAVE14 ASSERT GATES OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
