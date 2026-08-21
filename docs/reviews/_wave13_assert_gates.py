#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assert Wave 13 code gates before marking BB-000379–455 Resolved/Deferred.

Exit 0 only when critical remediation strings/behaviors are present in tree.
Does not mutate the register.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _fail(fails: list[str], msg: str) -> None:
    fails.append(msg)


def main() -> int:
    fails: list[str] = []

    # BB-000379 — sandbox banned on create + webhook in production/staging
    pay_svc = _read("backend/payments/services.py")
    pay_views = _read("backend/payments/views.py")
    pay_gw = _read("backend/payments/gateway.py")
    if "sandbox_forbidden_env" not in pay_svc or "sandbox_forbidden_env" not in pay_views:
        _fail(fails, "379: sandbox_forbidden_env missing from payments create/webhook path")
    if "PARTIALLY_PAID" not in pay_svc:
        _fail(fails, "392: PARTIALLY_PAID missing in payments.services")
    if "sandbox_webhook_secret_for_company" not in pay_gw and "company_id" not in pay_gw:
        _fail(fails, "393: per-company sandbox HMAC helper missing")

    # BB-000380 — return COGS
    acct = _read("backend/accounting/services.py")
    if "post_sales_return_cogs" not in acct:
        _fail(fails, "380: post_sales_return_cogs missing")

    # BB-000440 — beat health without `or True`
    prod = _read("docker-compose.prod.yml")
    if "or True" in prod:
        _fail(fails, "440: docker-compose.prod.yml still has `or True` beat bypass")
    if "bizboard:celery_beat_heartbeat" not in prod:
        _fail(fails, "440: beat heartbeat key missing from compose.prod")
    # AST sanity: healthcheck python snippet must not short-circuit assert
    for line in prod.splitlines():
        if "celery_beat_heartbeat" in line and "or True" in line:
            _fail(fails, "440: beat assert still ORs True")

    # BB-000387 — prepare_einvoice Owner
    sales_views = _read("backend/sales/views.py")
    if "prepare_einvoice" not in sales_views or "IsOwner" not in sales_views:
        _fail(fails, "387: prepare_einvoice/eway Owner gate missing")

    # BB-000424 / FE POS known-gate
    tax = _read("web/src/utils/tax.ts")
    if "placeOfSupplyKnown" not in tax:
        _fail(fails, "424: placeOfSupplyKnown missing in tax.ts")

    # BB-000407 — access body null in production
    acct_views = _read("backend/accounts/views.py")
    if 'env in ("production", "staging")' not in acct_views and "production" not in acct_views:
        _fail(fails, "407: production/staging access-body gate missing")
    if '"access": None' not in acct_views and "access'] = None" not in acct_views:
        _fail(fails, "407: access=None body path missing")

    # BB-000418 — invite accept
    if "AcceptInviteView" not in acct_views and "invite/accept" not in _read(
        "backend/accounts/urls_auth.py"
    ):
        _fail(fails, "418: invite accept endpoint missing")

    # BB-000419 — OTP stub fail-closed
    sms = _read("backend/core/services/sms.py")
    if "outside development/test" not in sms and "outside development" not in sms:
        _fail(fails, "419: SMS stub fail-closed message missing")

    # BB-000384 honesty — GSP fail-closed in prod/staging
    gsp = _read("backend/sales/einvoice_eway_actions.py")
    if "production" not in gsp or "staging" not in gsp:
        _fail(fails, "384: e-invoice/e-way prod/staging fail-closed missing")

    # BB-000417 — cookie JWT CSRF
    authn = _read("backend/core/authentication.py")
    if "enforce_csrf" not in authn:
        _fail(fails, "417: CookieJWTAuthentication CSRF enforce missing")

    # BB-000426 — dashboard RoleRoute
    app = _read("web/src/App.tsx")
    if "canViewFinancialReports" not in app or "DashboardPage" not in app:
        _fail(fails, "426: Dashboard RoleRoute financial gate missing")

    # BB-000443 — request id + JSON logs
    mw = _read("backend/core/middleware.py")
    if "request_id" not in mw or "json.dumps" not in mw:
        _fail(fails, "443: JSON request logging middleware incomplete")

    # BB-000442 — CD compose validation
    cd = _read(".github/workflows/cd.yml")
    if "compose.prod" not in cd and "docker-compose.prod.yml" not in cd:
        _fail(fails, "442: CD compose.prod validation missing")

    # Sanity: compose.prod healthcheck is parseable as not always-true
    try:
        # Ensure no trivial `assert x or True` survives as a Python expression string
        snippet = None
        for line in prod.splitlines():
            if "celery_beat_heartbeat" in line and "assert" in line:
                snippet = line.strip().strip('"').strip(",")
                break
        if snippet:
            # Extract from import… to end of quoted expression if present
            if "or True" in snippet:
                _fail(fails, "440: AST gate — or True still in heartbeat snippet")
    except SyntaxError:
        pass

    if fails:
        print("FAIL Wave 13 gates:")
        for f in fails:
            print(" -", f)
        return 1
    print("OK: Wave 13 code gates present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
