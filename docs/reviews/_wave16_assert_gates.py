#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assert Wave 16 mega-wave semantic gates. Exit 0 when behaviors are present."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def main() -> int:
    fails: list[str] = []

    if not (ROOT / "scripts/restore.sh").exists():
        fails.append("W16A: scripts/restore.sh missing")
    if not (ROOT / "scripts/pin_image_digests.sh").exists():
        fails.append("W16A: pin_image_digests.sh missing")
    if "profiles: [\"restore\"]" not in _read("docker-compose.yml") and "profiles: ['restore']" not in _read(
        "docker-compose.yml"
    ):
        if 'profiles: ["restore"]' not in _read("docker-compose.yml"):
            fails.append("W16A: restore compose profile missing")

    sms = _read("backend/core/services/sms.py")
    if "_send_msg91" not in sms or "_send_twilio" not in sms:
        fails.append("W16A: MSG91/Twilio adapters missing")

    settings = _read("backend/config/settings.py")
    if "CeleryIntegration" not in settings:
        fails.append("W16A: Sentry CeleryIntegration missing")
    if "POSTGRES_RLS_ENABLED" not in settings:
        fails.append("W16A: POSTGRES_RLS_ENABLED missing")

    if "PostgresRlsMiddleware" not in _read("backend/core/middleware.py"):
        fails.append("W16A: PostgresRlsMiddleware missing")

    if "EMAIL" not in _read("load/k6_smoke.js"):
        fails.append("W16A: k6 auth scenario missing")

    jl = _read("backend/accounting/models.py")
    if "customer = models.ForeignKey" not in jl or "supplier = models.ForeignKey" not in jl:
        fails.append("W16B: JournalLine party FKs missing")

    ledgers = _read("backend/ledgers/services.py")
    if "accounting_enabled" not in ledgers or "_party_account_net" not in ledgers:
        fails.append("W16B: LedgerService GL-first path missing")

    inv = _read("backend/inventory/models.py")
    if "class InventoryCostLayer" not in inv:
        fails.append("W16B: InventoryCostLayer missing")

    pay = _read("backend/payments/services.py")
    refund_fn = pay.split("def refund_gateway_payment")[1].split("\n    def ")[0]
    if "ALLOCATE_RECEIPT" not in refund_fn:
        fails.append("W16B: refund must reverse ALLOCATE_RECEIPT journals")

    gsp = _read("backend/core/services/gsp_adapters.py")
    if "class IrpAdapter" not in gsp or "HttpSandboxIrpAdapter" not in gsp:
        fails.append("W16C: GSP Protocols / HttpSandbox missing")
    if "get_gstr_filing_adapter" not in gsp:
        fails.append("W16C: get_gstr_filing_adapter missing")

    if "class Gstr2bIngest" not in _read("backend/reporting/models.py"):
        fails.append("W16D: Gstr2bIngest model missing")
    if "claimable_itc_from_2b" not in _read("backend/reporting/gstr2b.py"):
        fails.append("W16D: claimable_itc_from_2b missing")
    if "build_cmp08" not in _read("backend/reporting/gstr2b.py"):
        fails.append("W16D: build_cmp08 missing")

    if not (ROOT / "docs/pilot/FINAL_GATES_10.md").exists():
        fails.append("Final Gates doc missing")

    if not (ROOT / "backend/core/migrations/0005_wave16_postgres_rls.py").exists():
        fails.append("W16A: RLS migration missing")

    if fails:
        print("WAVE16 ASSERT GATES FAILED:")
        for f in fails:
            print(" -", f)
        return 1
    print("WAVE16 ASSERT GATES OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
