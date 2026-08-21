#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wave 22 closure hygiene — stats, changelog, exec, roadmap."""
from __future__ import annotations

import json
import re
from pathlib import Path

TODAY = "2026-08-06"
OUT = Path(__file__).resolve().parent
STATS = OUT / "_stats.json"
CHANGELOG = OUT / "CHANGELOG.md"
EXEC = OUT / "01_EXECUTIVE_SUMMARY.md"
ROADMAP = OUT / "REMEDIATION_ROADMAP.md"
PROD = OUT / "21_PRODUCTION_READINESS.md"

scores = {
    "production_readiness": 7.8,
    "architecture": 5.8,
    "security": 6.5,
    "performance": 5.0,
    "accounting": 8.5,
    "gst": 8.2,
    "maintainability": 5.2,
    "scalability": 4.2,
    "testing": 6.5,
}


def main() -> None:
    prior = json.loads(STATS.read_text(encoding="utf-8"))
    status = dict(prior.get("status") or {})
    open_before = status.get("Open", 0)
    # Wave 22 had 64 Open; all Resolved
    status["Open"] = max(0, open_before - 64)
    status["Resolved"] = status.get("Resolved", 0) + 64
    # Flip issue meta
    for issue in prior.get("issues") or []:
        try:
            n = int(issue["id"].split("-")[1])
        except Exception:
            continue
        if 695 <= n <= 758:
            issue["status"] = "Resolved"
    prior["status"] = status
    prior["open_count"] = status["Open"]
    prior["wave22_closure"] = {
        "date": TODAY,
        "resolved": 64,
        "start": "BB-000695",
        "end": "BB-000758",
        "scores": scores,
        "tests": [
            "test_wave22_f0_gst_accounting_payroll.py",
            "test_wave22_f1_period_money_series.py",
            "test_wave22_f2_fifo_serial_mfg.py",
            "test_wave22_f3_billing_idempotency.py",
            "test_wave22_f4_pwa_flags.py",
            "test_wave22_f5_platform.py",
        ],
    }
    prior["audit_date"] = TODAY
    STATS.write_text(json.dumps(prior, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    cl = f"""## {TODAY} — Wave 22 Full Remediation (F0–F5)

Closed all **64** Wave 22 Open issues `BB-000695`–`BB-000758`.

### Sprints
- **F0:** Sales RCM GL (no Output GST), GSTR-1 RCM/SUPECOM liability, GSTR-3B stamp reuse, GSTR-9 GSTIN, payroll employer+ESI ceiling, TCS ungated, BooksHealth coverage, 2B PARTIAL no sticky FK, multi-GSTIN fail-closed stamp, FY closes GstReturnPeriod.
- **F1:** Period gate no swallow; money service period gates; unallocate reverse dating; opening stock atomic; WO business dates; series GSTIN+FY; CN number after period assert.
- **F2:** Challan/PI/transfer/return/WO FIFO peel restore; PR serial; H9 qty forbid on tracked SKUs; CRM convert idempotent; price_role; SO convert lot/serial; rebuild WH; GRN honesty.
- **F3:** SaaS PENDING + REQUIRE_SUBSCRIPTION; PAST_DUE grace; seat_limit; idempotency begin_record; GSTIN sandbox trust.
- **F4:** PWA offline.html + no /api cache + logout purge; GSTR export GSTIN; runtime feature flags; filing 404 without GSP_CERTIFIED; WA/OCR/AI/company switch.
- **F5:** Celery doc keys; compose RLS/migrate; feature_flags read; Android allowBackup; Dependabot/CI/CD; OpenAPI drift; NewInvoice split; Sentry ErrorBoundary; /metrics; recon GET read-only; nginx no-cache; inventory apps.get_model.

### Scores (post Wave 22 remediation)
PR **{scores['production_readiness']}**, Accounting **{scores['accounting']}**, GST **{scores['gst']}**, Security **{scores['security']}**.

Tests: `test_wave22_f0_*.py` … `test_wave22_f5_*.py`.

---

"""
    CHANGELOG.write_text(cl + CHANGELOG.read_text(encoding="utf-8"), encoding="utf-8")

    banner = (
        f"**Latest:** Wave 22 Full Remediation {TODAY} — register **{prior['total']}**; "
        f"Wave 22 Open **0** (`BB-000695`–`BB-000758` Resolved). "
        f"PR **{scores['production_readiness']} / 10**. "
        f"Final Gates + signed Deferred (BB-000624 live NIC) still block 10/10.\n"
    )
    et = EXEC.read_text(encoding="utf-8")
    et = re.sub(r"\*\*Latest:\*\*[^\n]*", banner.strip(), et, count=1)
    section = f"""
---

## Wave 22 Full Remediation ({TODAY})

All **64** Wave 22 issues `BB-000695`–`BB-000758` **Resolved** via sprints F0–F5.

### Scores (supersede Wave 22 Open residual scores)

| Dimension | Score |
|-----------|------:|
| Production Readiness | **{scores['production_readiness']}** |
| Architecture | **{scores['architecture']}** |
| Security | **{scores['security']}** |
| Performance | **{scores['performance']}** |
| Accounting Correctness | **{scores['accounting']}** |
| GST Compliance | **{scores['gst']}** |
| Maintainability | **{scores['maintainability']}** |
| Scalability | **{scores['scalability']}** |
| Testing Coverage | **{scores['testing']}** |

**CTO:** Dogfood **Yes**. Paid pilot **Conditional** after Final Gates (TLS, GO_NO_GO, backups). GA still blocked by live NIC (BB-000624 Deferred) and unsigned ops gates. Do not claim live GSTN filing.

---
"""
    if f"Wave 22 Full Remediation ({TODAY})" not in et:
        et = et.rstrip() + "\n" + section
    EXEC.write_text(et + "\n", encoding="utf-8")

    road = f"""## Wave 22 closure ({TODAY})

| Sprint | Status |
|--------|--------|
| F0 Money/GST/Payroll | **Done** |
| F1 Period/Money/Series | **Done** |
| F2 FIFO/Serial/Mfg | **Done** |
| F3 SaaS/Idempotency | **Done** |
| F4 PWA/FE | **Done** |
| F5 Platform | **Done** |

Open in 695–758: **0**.

"""
    rb = ROADMAP.read_text(encoding="utf-8")
    if f"Wave 22 closure ({TODAY})" not in rb:
        ROADMAP.write_text(road + rb, encoding="utf-8")

    prod_bit = f"""# Production readiness (Wave 22 closure — {TODAY})

**Score: {scores['production_readiness']} / 10.** Wave 22 Open **0** (`BB-000695`–`BB-000758` Resolved).

Remaining hard stops for GA: Final Gates (signed GO_NO_GO, TLS, backup restore drill) + BB-000624 live NIC Deferred.

"""
    pb = PROD.read_text(encoding="utf-8")
    if f"Wave 22 closure — {TODAY}" not in pb:
        PROD.write_text(prod_bit + pb, encoding="utf-8")

    print(f"WAVE22 CLOSE OK open={status['Open']} resolved+={64} scores={scores}")


if __name__ == "__main__":
    main()
