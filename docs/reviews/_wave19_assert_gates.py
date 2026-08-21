#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assert Wave 19 semantic gates. Exit 0 when W19A-G deliverables are present."""
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

    so = _read("web/src/pages/sales/SalesOrderEditorPage.tsx")
    dc = _read("web/src/pages/sales/DeliveryChallanEditorPage.tsx")
    po = _read("web/src/pages/purchases/PurchaseOrderEditorPage.tsx")
    if "cessRate" not in so:
        fails.append("W19A: SO editor missing cessRate")
    if "cessRate" not in dc:
        fails.append("W19A: delivery challan editor missing cessRate")
    if "cessRate" not in po:
        fails.append("W19A: PO editor missing cessRate")

    outbox = _read("web/src/offline/invoiceDraftCache.ts")
    if "enqueueDraft" not in outbox or "flushOutbox" not in outbox:
        fails.append("W19B: outbox APIs missing")
    if "indexedDB" not in outbox and "IDB" not in outbox:
        fails.append("W19B: IndexedDB path missing")
    inv = _read("web/src/pages/sales/NewInvoicePage.tsx")
    if "enqueueDraft" not in inv or "flushOutbox" not in inv:
        fails.append("W19B: NewInvoicePage not wired to outbox")
    pos = _read("web/src/pages/pos/PosPage.tsx")
    if "flushOutbox" not in pos and "enqueueDraft" not in pos:
        fails.append("W19B: POS not on shared outbox helpers")

    if not _exists("web/src/api/statutory.ts"):
        fails.append("W19C: statutory API client missing")
    if not _exists("web/src/pages/reports/StatutoryEventsPage.tsx"):
        fails.append("W19C: statutory events page missing")
    if "statutory-events" not in _read("web/src/navigation/menu.ts"):
        fails.append("W19C: statutory nav missing")
    if "statutory-events" not in _read("web/src/App.tsx"):
        fails.append("W19C: statutory route missing")

    if not _exists("web/src/api/typedClient.ts"):
        fails.append("W19D: typedClient missing")
    if "export interface paths" not in _read("web/src/api/openapi-types.ts"):
        fails.append("W19D: openapi-types.ts missing paths export")
    if "typedClient" not in _read("web/src/api/manufacturing.ts"):
        fails.append("W19D: manufacturing not pointed at typedClient")

    if not _exists("backend/core/rls.py"):
        fails.append("W19E: core/rls.py missing")
    rls_mig = next((ROOT / "backend/core/migrations").glob("*wave19_rls*"), None)
    if rls_mig is None:
        fails.append("W19E: wave19 RLS migration missing")
    else:
        sql = rls_mig.read_text(encoding="utf-8")
        if "sales_salescreditnote" not in sql or "inventory_stockmovement" not in sql:
            fails.append("W19E: RLS migration missing expected tenant tables")
    if "set_rls_company" not in _read("backend/config/celery.py"):
        fails.append("W19E: Celery RLS prerun missing")
    if 'POSTGRES_RLS_ENABLED", "0"' not in _read("backend/config/settings.py") and (
        'POSTGRES_RLS_ENABLED", "0")' not in _read("backend/config/settings.py")
    ):
        if 'os.environ.get("POSTGRES_RLS_ENABLED", "0")' not in _read("backend/config/settings.py"):
            fails.append("W19E: RLS default enablement changed unexpectedly")

    if not _exists("web/src/api/legacy/sales.ts"):
        fails.append("W19F: legacy/sales.ts missing")
    if "export * from './legacy/sales'" not in _read("web/src/api/resources.ts"):
        fails.append("W19F: resources.ts is not a re-export barrel")
    if not _exists("web/src/components/billing/DraftLineTable.tsx"):
        fails.append("W19F: DraftLineTable missing")
    if "useVirtualizer" not in _read("web/src/components/VirtualizedTable.tsx"):
        fails.append("W19F: VirtualizedTable not using tanstack virtual")
    if "@tanstack/react-virtual" not in _read("web/package.json"):
        fails.append("W19F: @tanstack/react-virtual dependency missing")

    gst = _read("backend/reporting/gst_returns.py")
    if 'aid_kind": "hsn_inward"' not in gst and "aid_kind\": \"hsn_inward\"" not in gst:
        if 'hsn_inward' not in gst:
            fails.append("W19G: GSTR-9 table 18 inward HSN missing")
    if "tax_status" not in gst or "rate_unknown" not in gst:
        fails.append("W19G: GSTR-1 AT rate/POS depth missing")

    if fails:
        print("WAVE19 ASSERT FAIL")
        for item in fails:
            print(" -", item)
        return 1
    print("WAVE19 ASSERT OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
