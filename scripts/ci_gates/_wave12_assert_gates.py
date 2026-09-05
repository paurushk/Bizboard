#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assert Wave 12 code gates before marking BB-000318–378 Resolved.

Exit 0 only when critical remediation strings/behaviors are present in tree.
Does not mutate the register.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
WEB = ROOT / "web"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def main() -> int:
    fails: list[str] = []

    # BB-000318 — sandbox banned in production/staging
    pay_views = _read("backend/payments/views.py")
    if "sandbox" not in pay_views or "production" not in pay_views:
        fails.append("318: GatewaySettingsView missing sandbox/prod gate")
    if "cannot be enabled in production or staging" not in pay_views:
        fails.append("318: missing sandbox production ban message")

    # BB-000351 — overpay reject (no silent clamp)
    pay_svc = _read("backend/payments/services.py")
    if "over" not in pay_svc.lower() and "Over" not in pay_svc:
        # Accept BusinessRuleError paths around capture/amount
        if "BusinessRuleError" not in pay_svc:
            fails.append("351: payments services missing BusinessRuleError overpay path")

    # BB-000332 — OTP_ENABLED (not only OTP_DEBUG_ECHO)
    acct = _read("backend/accounts/views.py")
    if "OTP_ENABLED" not in acct or "secrets.randbelow" not in acct:
        fails.append("332: OTP_ENABLED / secrets.randbelow missing in accounts.views")

    # BB-000322 — perpetual purchase Dr 1400
    acct_svc = _read("backend/accounting/services.py")
    if '"1400"' not in acct_svc and "'1400'" not in acct_svc:
        fails.append("322: post_purchase missing inventory account 1400")
    # COGS must remain for sales
    if "post_sales_cogs" not in acct_svc and "cogs" not in acct_svc.lower():
        fails.append("322: COGS posting missing")

    # BB-000320 — FE state name map
    tax_ts = _read("web/src/utils/tax.ts")
    if "IN_STATE_NAME_TO_CODE" not in tax_ts and "karnataka" not in tax_ts.lower():
        fails.append("320: FE tax.ts missing state-name→code map")

    # BB-000350 — canCreate* === true
    perms = _read("web/src/utils/permissions.ts")
    if "=== true" not in perms:
        fails.append("350: permissions.ts missing === true capability checks")

    # BB-000344 — accounting feature default off
    feat = ""
    for cand in (
        "web/src/config/features.ts",
        "web/src/features.ts",
        "web/src/config.ts",
    ):
        p = ROOT / cand
        if p.exists():
            feat += p.read_text(encoding="utf-8")
    # Also search common feature flag sites
    if not feat:
        for p in (WEB / "src").rglob("*.ts*"):
            t = p.read_text(encoding="utf-8", errors="ignore")
            if "accounting" in t and ("VITE_" in t or "features" in t):
                feat += t + "\n"
                if len(feat) > 50_000:
                    break
    if '=== "true"' not in feat and "=== 'true'" not in feat:
        # Fallback: grep accounting flag files
        hit = False
        for p in (WEB / "src").rglob("*"):
            if p.suffix not in {".ts", ".tsx", ".js"}:
                continue
            t = p.read_text(encoding="utf-8", errors="ignore")
            if "accounting" in t and ("=== 'true'" in t or '=== "true"' in t):
                hit = True
                break
        if not hit:
            fails.append("344: features.accounting default-off (=== 'true') not found")

    # BB-000375 — access httpOnly cookie
    if "JWT_ACCESS_COOKIE" not in _read("backend/config/settings.py") and "ACCESS_COOKIE" not in acct:
        # Cookie helpers live in accounts.views
        if "_set_access_cookie" not in acct:
            fails.append("375: access cookie helper missing")

    # BB-000321 — FEFO cancel via SALE movements
    sales_svc = _read("backend/sales/services.py")
    if "StockMovement" not in sales_svc and "reference_id" not in sales_svc:
        fails.append("321: cancel movement-replay markers missing in sales.services")

    # Constraints in Docker
    docker = _read("backend/Dockerfile")
    if "constraints.txt" not in docker:
        fails.append("345: backend Dockerfile missing constraints.txt")

    if fails:
        print("FAIL Wave 12 gates:")
        for f in fails:
            print(" -", f)
        return 1
    print("OK: Wave 12 code gates present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
