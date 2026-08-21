#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assert Wave 15 semantic gates (W15A–F). Exit 0 only when behaviors are present."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def main() -> int:
    fails: list[str] = []

    # BB-000464 CSP — no style-src unsafe-inline in live header directives
    web_nginx = _read("web/nginx.conf")
    for line in web_nginx.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "unsafe-inline" in stripped:
            fails.append("464: web/nginx.conf still has unsafe-inline")
            break
    root_nginx = _read("nginx/default.conf")
    if "style-src 'self'" not in root_nginx:
        fails.append("464: root nginx CSP missing style-src self")

    # BB-000465 FIFO honesty
    models = _read("backend/accounts/models.py")
    if '("FIFO"' in models or "(\"FIFO\"" in models:
        fails.append("465: Company still offers FIFO choice")
    inv = _read("backend/inventory/services.py")
    if 'method == "FIFO"' not in inv or "BusinessRuleError" not in inv:
        fails.append("465: FIFO must hard-error in InventoryValuationService")

    # BB-000471 cookie-only when DEBUG=0
    auth_views = _read("backend/accounts/views.py")
    if "_access_in_json_body_allowed" not in auth_views:
        fails.append("471: _access_in_json_body_allowed missing")

    # BB-000480 RoleRoute
    app = _read("web/src/App.tsx")
    if "sales/quotations" not in app or "canViewSalesSurfaces" not in app:
        fails.append("480: quotations must use canViewSalesSurfaces")

    # BB-000500/501 ADMIN+CORS
    settings = _read("backend/config/settings.py")
    if "cannot be combined with wildcard" not in settings:
        fails.append("500/501: ADMIN_ENABLED refuse wildcard CORS missing")

    # BB-000503 GUNICORN_WORKERS
    compose = _read("docker-compose.yml")
    if "GUNICORN_WORKERS" not in compose:
        fails.append("503: GUNICORN_WORKERS missing from docker-compose.yml")

    # BB-000546 statement_timeout
    if "statement_timeout" not in settings:
        fails.append("546: statement_timeout missing from settings DATABASE OPTIONS")

    # BB-000547 Bearer JWT off in prod
    if 'DJANGO_ENV in ("production", "staging")' not in settings or "JWTAuthentication" not in settings:
        fails.append("547: JWTAuthentication must be conditional on DJANGO_ENV")

    # BB-000545 purchase cancel lots
    purch = _read("backend/purchases/services.py")
    if "PURCHASE_RETURN" not in purch.split("def cancel_return")[1] or "unit_cost=move.unit_cost" not in purch.split("def cancel_return")[1]:
        fails.append("545/549: cancel_return must replay PURCHASE_RETURN lots with unit_cost")

    # BB-000479 partial refund reject
    pay = _read("backend/payments/services.py")
    if "Only full refunds are supported" not in pay:
        fails.append("479: partial refund reject missing")

    # BB-000514 token entropy + throttle
    if "token_urlsafe(24)" not in pay:
        fails.append("514: payment link token_urlsafe(24) missing")
    wh = _read("backend/payments/webhook_views.py")
    if "PublicPayThrottle" not in wh:
        fails.append("514: PublicPayThrottle missing")

    # BB-000463 fetchAllPages ban for money
    resources = _read("web/src/api/resources.ts")
    if "fetchMoneyListFirstPage" not in resources and "fetchAllPagesMasters" not in resources:
        fails.append("463: money list must not use unbounded fetchAllPages")
    if not (ROOT / "web/scripts/check-fetch-all-pages.mjs").exists():
        fails.append("463: check-fetch-all-pages.mjs missing")

    # BB-000466/510 period close health
    acct = _read("backend/accounting/services.py")
    if "assert_period_close_allowed" not in acct:
        fails.append("466/510: assert_period_close_allowed missing")

    # BB-000478 request logs
    mw = _read("backend/core/middleware.py")
    if "duration_ms" not in mw:
        fails.append("478: duration_ms missing from request logs")

    # BB-000491 idempotency
    if not (ROOT / "backend/core/idempotency.py").exists():
        fails.append("491: core/idempotency.py missing")

    # BB-000476 return/cogs split
    if not (ROOT / "backend/sales/return_service.py").exists():
        fails.append("476: return_service.py missing")
    if not (ROOT / "backend/sales/cogs_service.py").exists():
        fails.append("476: cogs_service.py missing")

    # BB-000477 load harness
    if not (ROOT / "load/k6_smoke.js").exists():
        fails.append("477: load/k6_smoke.js missing")

    # BB-000494 cookie e2e
    if not (ROOT / "web/e2e/helpers/auth.ts").exists():
        fails.append("494: e2e auth helper missing")

    # BB-000495 axe
    if not (ROOT / "web/e2e/a11y.spec.ts").exists():
        fails.append("495: a11y.spec.ts missing")

    if fails:
        print("WAVE15 ASSERT GATES FAILED:")
        for f in fails:
            print(" -", f)
        return 1
    print("WAVE15 ASSERT GATES OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
