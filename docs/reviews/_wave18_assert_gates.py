#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assert Wave 18 semantic gates. Exit 0 when W18A–G deliverables are present."""
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

    if "warehouses are stock locations" not in _read("backend/accounts/models.py"):
        fails.append("W18A: Company warehouse docstring not updated")

    if "cess_total" not in _read("backend/core/models.py"):
        fails.append("W18B: cess_total missing")
    if "cess_rate" not in _read("backend/core/models.py"):
        fails.append("W18B: cess_rate missing")
    if "itc_eligibility" not in _read("backend/purchases/models.py"):
        fails.append("W18B: purchase ITC eligibility missing")
    if '"doc"' not in _read("backend/reporting/gst_returns.py"):
        fails.append("W18B: GSTR-1 DOC missing")
    if '"at"' not in _read("backend/reporting/gst_returns.py"):
        fails.append("W18B: GSTR-1 AT missing")
    if "hsn_outward" not in _read("backend/reporting/gst_returns.py"):
        fails.append("W18B: GSTR-9 table 17 missing")

    if not _exists("web/src/api/manufacturing.ts"):
        fails.append("W18C: manufacturing API client missing")
    if not _exists("web/src/pages/manufacturing/BomsPage.tsx"):
        fails.append("W18C: BOMs page missing")
    if "nav.manufacturing" not in _read("web/src/navigation/menu.ts") and "manufacturing" not in _read(
        "web/src/navigation/menu.ts"
    ):
        fails.append("W18C: manufacturing nav missing")

    if not _exists("web/src/pages/pos/PosPage.tsx"):
        fails.append("W18D: POS page missing")
    if not _exists("web/src/offline/invoiceDraftCache.ts"):
        fails.append("W18D: offline draft cache missing")
    if "Ctrl" not in _read("web/src/pages/sales/NewInvoicePage.tsx") and "metaKey" not in _read(
        "web/src/pages/sales/NewInvoicePage.tsx"
    ):
        fails.append("W18D: invoice keyboard shortcuts missing")

    if "X-Company-Id" not in _read("web/src/api/client.ts"):
        fails.append("W18E: X-Company-Id header missing")
    if "bizboard:locale" not in _read("web/src/i18n/index.ts"):
        fails.append("W18E: locale persistence missing")
    if "IntegrationConnection" not in _read("backend/core/services/whatsapp.py"):
        fails.append("W18E: WhatsApp IntegrationConnection missing")

    if not _exists("web/src/components/VirtualizedTable.tsx"):
        fails.append("W18F: VirtualizedTable missing")
    if "gen:api-types" not in _read("web/package.json"):
        fails.append("W18F: openapi-typescript script missing")
    openapi_types = _read("web/src/api/openapi-types.ts")
    if "export interface paths" not in openapi_types and "export type paths = {" not in openapi_types:
        fails.append("W18F: openapi-types.ts still a placeholder stub")

    if "class StatutoryDocumentEvent" not in _read("backend/core/models.py"):
        fails.append("W18G: StatutoryDocumentEvent missing")
    if "scaffold" in _read("backend/payments/gateway.py") and "Cashfree refund is not implemented" in _read(
        "backend/payments/gateway.py"
    ):
        fails.append("W18G: Cashfree refund still scaffold")
    if not _exists("web/public/manifest.webmanifest"):
        fails.append("W18G: PWA manifest missing")
    if not _exists("load/README.md"):
        fails.append("W18G: load README missing")

    if not _exists("docs/reviews/_wave18_close_deferred.py"):
        fails.append("W18H: close deferred script missing")

    if fails:
        print("WAVE18 ASSERT GATES FAILED:")
        for f in fails:
            print(" -", f)
        return 1
    print("WAVE18 ASSERT GATES OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
