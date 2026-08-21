#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assert Wave 17 semantic gates. Exit 0 when W17A–G deliverables are present."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _exists(rel: str) -> bool:
    return (ROOT / rel).exists()


def main() -> int:
    fails: list[str] = []

    # W17A
    if "submit_einvoice_async" not in _read("backend/sales/tasks.py"):
        fails.append("W17A: Celery submit_einvoice_async missing")
    if "submit-einvoice-async" not in _read("backend/sales/einvoice_eway_actions.py"):
        fails.append("W17A: async e-invoice enqueue action missing")
    if "Gstr2bIngestViewSet" not in _read("backend/reporting/views.py"):
        fails.append("W17A: GSTR-2B API viewset missing")
    if "GSTR2B_UNMATCHED" not in _read("backend/reporting/gst_health.py"):
        fails.append("W17A: GstHealth GSTR2B_UNMATCHED missing")
    sections = _read("backend/reporting/gst_returns_sections.py")
    if "append_exp_sez_rows" not in sections:
        fails.append("W17A: GSTR-1 EXP/SEZ routing missing")
    gstr = _read("backend/reporting/gst_returns.py")
    if '"exp"' not in gstr or '"sez"' not in gstr:
        fails.append("W17A: GSTR-1 exp/sez payload keys missing")
    if "gstr9_worksheet_mvp" not in gstr or '"tables"' not in gstr:
        fails.append("W17A: GSTR-9 tables aid missing")
    if "cmp08" not in gstr.lower() and "Use /api/v1/reports/cmp08/" not in gstr:
        fails.append("W17A: composition routing message missing")
    if "taxpayer_type" not in _read("backend/masters/models.py"):
        fails.append("W17A: Customer/Supplier taxpayer_type missing")
    if "company_gstin" not in _read("backend/sales/models.py"):
        fails.append("W17A: SalesInvoice.company_gstin missing")
    if "_clamav_scan" not in _read("backend/core/services/files.py"):
        fails.append("W17A: ClamAV scan hook missing")
    ledgers = _read("backend/ledgers/services.py")
    if "_gl_party_statement" not in ledgers:
        fails.append("W17A: GL-first statements missing")
    if "_advance_recon_alerts" not in _read("backend/accounting/services.py"):
        fails.append("W17A: advance recon BooksHealth missing")
    if "party tags" not in _read("backend/accounting/management/commands/backfill_accounting_postings.py").lower():
        fails.append("W17A: backfill party tags missing")
    if "log_money_change" not in _read("backend/sales/serializers.py"):
        fails.append("W17A: money audit hooks on sales missing")
    if "create-draft" not in _read("load/k6_smoke.js") and "create_draft" not in _read("load/k6_smoke.js"):
        if "sales/invoices/" not in _read("load/k6_smoke.js") or "POST" not in _read("load/k6_smoke.js"):
            fails.append("W17A: k6 create-draft scenario missing")
    if "postgres-rls" not in _read(".github/workflows/ci.yml") and "POSTGRES_RLS_ENABLED" not in _read(
        ".github/workflows/ci.yml"
    ):
        fails.append("W17A: RLS CI job missing")

    # W17B
    if "amendments" not in gstr:
        fails.append("W17B: GSTR-1 amendments missing")
    if "gstr2b-match" not in gstr:
        fails.append("W17B: CA pack 2B summary missing")
    if "GstFilingSandboxView" not in _read("backend/reporting/views.py"):
        fails.append("W17B: sandbox filing view missing")

    # W17C
    if not _exists("backend/tests/test_wave17_gst_books.py"):
        fails.append("W17C: golden/books pytest missing")

    # W17D
    if not _exists("backend/manufacturing/models.py"):
        fails.append("W17D: manufacturing app missing")
    if not _exists("backend/payroll/models.py"):
        fails.append("W17D: payroll app missing")
    if not _exists("backend/crm/models.py"):
        fails.append("W17D: crm app missing")
    if "push_masters_http" not in _read("backend/integrations/tally/adapter.py"):
        fails.append("W17D: Tally HTTP push missing")

    # W17E
    if not _exists("backend/core/services/whatsapp.py"):
        fails.append("W17E: WhatsApp Cloud client missing")
    if not _exists("mobile/capacitor.config.ts"):
        fails.append("W17E: Capacitor shell missing")

    # W17F
    if not _exists("backend/banking/models.py"):
        fails.append("W17F: AA banking app missing")
    gw = _read("backend/payments/gateway.py")
    if "CashfreeGateway" not in gw or "PayUGateway" not in gw:
        fails.append("W17F: Cashfree/PayU adapters missing")

    # W17G
    if "switch-company" not in _read("backend/accounts/urls_auth.py"):
        fails.append("W17G: switch-company endpoint missing")
    if not _exists("web/src/i18n/hi.ts"):
        fails.append("W17G: Hindi i18n missing")
    if "FeatureFlagsView" not in _read("backend/core/views.py") and "feature-flags" not in _read(
        "backend/core/urls.py"
    ):
        fails.append("W17G: feature-flags API missing")

    # W17H
    if not _exists("docs/reviews/_wave17_close_deferred.py"):
        fails.append("W17H: close deferred script missing")

    if fails:
        print("WAVE17 ASSERT GATES FAILED:")
        for f in fails:
            print(" -", f)
        return 1
    print("WAVE17 ASSERT GATES OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
