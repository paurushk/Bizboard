#!/usr/bin/env python3
"""Append Wave 8 sections to review docs + rewrite executive summary scores."""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
STATS = json.loads((OUT / "_stats.json").read_text(encoding="utf-8"))
TODAY = "2026-08-03"

SEV = STATS["severity"]
PRI = STATS["priority"]
STATUS = STATS["status"]
TOTAL = STATS["total"]
CAT = STATS["category"]
MOD = STATS["module"]

WAVE8_OPEN_CRITICAL = [
    "BB-000196 Empty gateway creds → SandboxAdapter forgery",
    "BB-000197 PayU missing signature accepted",
    "BB-000198 Razorpay stub payment links on error",
    "BB-000199 Purchase H9 missing period/GL",
    "BB-000200 Any member can post journals",
]


def append_once(path: Path, marker: str, section: str) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else f"# {path.name}\n"
    if marker in text:
        return
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text + "\n" + section, encoding="utf-8")


def write_executive_summary() -> None:
    path = OUT / "01_EXECUTIVE_SUMMARY.md"
    # Prepend Wave 8 update block after title — rewrite key sections by replacing file carefully
    text = path.read_text(encoding="utf-8")
    wave_block = f"""
---

## Wave 8 re-audit ({TODAY}) — SUPERSEDES Scope C “zero Open” claim

Independent code re-verification **invalidated Wave 7 register closure**. Scope C fixed many items (OTP hash, ValDtls, composition gates, RCM GL, media off, beat in compose, blocking pip-audit), but **payment webhook authenticity, purchase H9 GL, accounting RBAC, and observability** remain defective. **62 new issues** logged as `BB-000196` … `BB-000257`. Four prior IDs reopened: `BB-000004`, `BB-000011`, `BB-000018`, `BB-000047`.

### Updated verdict

BizBoard remains a **strong billing + inventory foundation** and is **not commercially launchable** as a full Cloud ERP. After Wave 8, even a **paid billing pilot is blocked** until payment-forgery P0s close.

| Audience | Deploy? |
|----------|---------|
| Internal dogfood (no public pay webhooks) | **Conditional** |
| Paid pilot with live payment links | **No — until BB-000196–198 closed** |
| GA / full ERP claims | **No** |

### Scores (0–10) — Wave 8

| Dimension | Score | Delta vs Wave7 | Notes |
|-----------|------:|:--------------:|-------|
| Production Readiness | **4.5** | −2.3 | Payment forgery + unsigned Go gates |
| Architecture | **6.0** | −0.5 | Dual ledger + shared-DB tenancy unchanged |
| Security | **3.5** | −3.0 | Sandbox webhook / PayU / stub links / journal RBAC |
| Performance | **5.0** | −0.5 | fetchAllPages residual; invoice loads all customers |
| Accounting Correctness | **5.0** | −1.0 | Purchase H9 / journal RBAC / expense-vs-inventory |
| GST Compliance | **4.5** | −0.5 | 3B ITC hint; manual IRN; no 2B; sandbox GSP |
| Maintainability | **5.0** | −0.5 | God modules unchanged |
| Scalability | **4.0** | −0.5 | Client fetch-all; no load proof |
| Testing Coverage | **5.5** | −0.5 | Light e2e without API; adversarial pay tests missing |

### Register totals (cumulative)

| Metric | Count |
|--------|------:|
| **Total issues** | **{TOTAL}** |
| Critical | {SEV.get('Critical', 0)} |
| High | {SEV.get('High', 0)} |
| Medium | {SEV.get('Medium', 0)} |
| Low | {SEV.get('Low', 0)} |

| Priority | Count |
|----------|------:|
| P0 | {PRI.get('P0', 0)} |
| P1 | {PRI.get('P1', 0)} |
| P2 | {PRI.get('P2', 0)} |
| P3 | {PRI.get('P3', 0)} |

### Status histogram (Wave 8)

| Status | Count |
|--------|------:|
| Open | {STATUS.get('Open', 0)} |
| Resolved | {STATUS.get('Resolved', 0)} |
| Deferred — roadmap | {STATUS.get('Deferred — roadmap', STATUS.get('Deferred - roadmap', 53))} |
| Deferred — ops owner | {STATUS.get('Deferred — ops owner', STATUS.get('Deferred - ops owner', 7))} |
| Accepted (positive) | {STATUS.get('Accepted (positive)', 4)} |

### Wave 8 P0 blockers (must close before any paid pilot with payments)

1. **BB-000196** — Empty gateway credentials → SandboxAdapter (`X-Sandbox-Signature: ok`)
2. **BB-000197** — PayU accepts missing signature
3. **BB-000198** — Razorpay stubs fake collect URLs on failure
4. **BB-000199** — Purchase H9 without period/GL
5. **BB-000200** — Any company member can post journals

### Estimated remediation effort (additive to prior roadmap)

| Band | Eng-days |
|------|--------:|
| Wave 8 P0 payment + H9 + journal RBAC | **8–12** |
| Wave 8 P1 (IDOR, FE RoleRoutes, fetch-all pickers, Dockerfile, Redis lockout) | **25–40** |
| Remaining Deferred ops/roadmap (unchanged order of magnitude) | **400+ to GA** |
| **Honest paid pilot (billing, payments hardened, no ERP claims)** | **~40–60 from today** |

### Final CTO Verdict (Wave 8)

**Do not enable public payment webhooks or Cashfree/PayU in any environment until BB-000196–198 are fixed and adversarially tested.**

**Do not treat Wave 7 “zero Open” as a quality gate** — closure was process-failed (BB-000251). Require failing-then-passing tests for every Critical Resolved claim.

Core tax Decimal math, tenant isolation tests, stock `select_for_update`, OTP hashing, composition invoice gates, and RCM GL splits remain **worth keeping**. The launch-blocking failure mode is again **payment integrity + over-claimed compliance/books**, compounded by **false remediation closure**.

"""
    if f"Wave 8 re-audit ({TODAY})" not in text:
        # Insert after first Verdict section header area — after line with Production Readiness Score
        anchor = "## Verdict\n"
        if anchor in text:
            # Keep original verdict historically, add wave8 after History or at top after title
            text = text.replace(
                "# BizBoard — Executive Summary (Engineering Audit)\n",
                "# BizBoard — Executive Summary (Engineering Audit)\n\n"
                f"**Latest:** Wave 8 re-audit {TODAY} — register **{TOTAL}** issues "
                f"(`BB-000001`…`BB-000257`). **Open: {STATUS.get('Open', 0)}.** "
                f"Production Readiness Score **4.5 / 10**.\n",
                1,
            )
            # Append wave block before Artifact index
            text = text.replace("## Artifact index\n", wave_block + "\n## Artifact index\n", 1)
        hist = f"| {TODAY} | Wave 8 re-audit — +62 issues BB-000196…257; reopened BB-000004/011/018/047; PR score 4.5 |\n"
        if hist.strip() not in text:
            text = text.rstrip() + "\n" + hist
        path.write_text(text, encoding="utf-8")


def update_changelog() -> None:
    path = OUT / "CHANGELOG.md"
    entry = f"""
## {TODAY} — Wave 8 independent re-audit

Re-ran complete engineering audit against live `backend/` + `web/` + compose/CI (not worktrees).

### Outcomes

- Appended **62** issues `BB-000196` … `BB-000257` (Critical 5 · High 24 · Medium 25 · Low 8).
- Reopened residual parents: **BB-000004**, **BB-000011**, **BB-000018**, **BB-000047**.
- Register total: **{TOTAL}**.
- Status: Open **{STATUS.get('Open', 0)}** · Resolved **{STATUS.get('Resolved', 0)}** · Deferred roadmap/ops retained for untouched IDs.
- Invalidated Wave 7 “zero Open / Scope C complete” as a launch gate (see BB-000251).
- Production Readiness Score revised **6.8 → 4.5**.
- Script: `_wave8_reaudit_append.py` (append-only; IDs permanent).

### Highest new Criticals

{chr(10).join('- ' + x for x in WAVE8_OPEN_CRITICAL)}

### Passes re-executed

Repository structure, architecture, backend, frontend, database, authn/z, accounting, GST, inventory, sales/purchase, manufacturing/payroll/CRM (absent), banking/payments, OCR/AI, WhatsApp, mobile, reports, GST portal, Tally, API, performance, security, caching, concurrency, logging, observability, DevOps, testing, a11y, docs, config, dependencies, scalability, maintainability, cross-module, production readiness, missed-findings (Wave 8).

"""
    append_once(path, f"## {TODAY} — Wave 8", entry)


def update_roadmap() -> None:
    path = OUT / "REMEDIATION_ROADMAP.md"
    section = f"""
---

## Wave 8 — Immediate hotfix track ({TODAY}) · P0

Supersedes “Scope C completed / zero Open” narrative for launch decisions.

| Focus | Issue IDs | Outcome |
|-------|-----------|---------|
| Payment webhook fail-closed | BB-000196, BB-000197, BB-000213 | No sandbox settle without explicit sandbox provider |
| No stub collect URLs | BB-000198, BB-000211 | Real Razorpay or hard error; disable Cashfree/PayU |
| Purchase H9 parity | BB-000199 | Period + GL reverse/repost |
| Accounting RBAC | BB-000200, BB-000201 | Journals/reports capability-gated |
| Process | BB-000251 | Resolved requires adversarial test evidence |

**Exit:** Safe to expose payment webhooks in pilot.

### Wave 8 P1 (week 2–4)

- IDOR: logo/signature, bank recon (BB-000202, BB-000203)
- FE RoleRoutes + payment URL allowlist (BB-000209, BB-000210)
- Dockerfile non-root, `requests` dep, Redis required, ADMIN default off
- Invoice pickers stop fetch-all (BB-000246)
- GSTR-3B remove net_payable_hint ITC subtract (BB-000212)

"""
    append_once(path, f"## Wave 8 — Immediate hotfix", section)
    # Update header date note
    text = path.read_text(encoding="utf-8")
    if "Wave 8 re-opened" not in text:
        text = text.replace(
            "**Date:** 2026-08-02",
            f"**Date:** 2026-08-02 (updated {TODAY} Wave 8)\n\n> **Wave 8:** Scope C “zero Open” is **not** a launch gate. See hotfix track below.",
            1,
        )
        path.write_text(text, encoding="utf-8")


REVIEW_SECTIONS = {
    "03_BACKEND_REVIEW.md": f"""
## Wave 8 ({TODAY})

New backend findings BB-000196–BB-000257 focus on **payment gateway authenticity**, **purchase H9 GL gap**, **journal RBAC**, **FileAsset/bank-line IDOR**, **OTP verify race**, **missing `requests` dependency**, **ADMIN_ENABLED default**, and **celery false-positive health**. Scope C OTP hash / ValDtls / RCM GL / composition gates verified still present.
""",
    "04_FRONTEND_REVIEW.md": f"""
## Wave 8 ({TODAY})

Confirmed: VITE_USE_MOCKS prod hard-stop, `/auth/me` boot refresh, RoleRoute→Forbidden. Still open/new: localStorage JWT (BB-000257), RoleRoute gaps on quotations/returns/payments/inventory (BB-000209), payment href allowlist (BB-000210), fetchAllPages silent cap + invoice loads all customers (BB-000245/246), Zod absent (BB-000256), e-Way submit ungated (BB-000224), mobile drawer/a11y (BB-000242/243).
""",
    "06_SECURITY_REVIEW.md": f"""
## Wave 8 ({TODAY})

**Security score revised to 3.5/10.** Critical: sandbox webhook forgery (BB-000196), PayU unsigned accept (BB-000197), Razorpay stub links (BB-000198), journal posting by any member (BB-000200). High: IDOR logo/bank line, FE route gaps, open payment URLs, Fernet residual outside prod, DEBUG-on-public-host residual, Redis lockout bypass.
""",
    "08_GST_REVIEW.md": f"""
## Wave 8 ({TODAY})

New/residual: GSTR-3B `net_payable_hint` still subtracts provisional ITC (BB-000212); manual mark-IRN (BB-000214); client-writable einvoice/AATO (BB-000215); Null GSTIN provider (BB-000225); e-Way FE submit ungated (BB-000224); blank company POS→intra in FE (BB-000233). Live GSP still Deferred (BB-000005).
""",
    "09_ACCOUNTING_REVIEW.md": f"""
## Wave 8 ({TODAY})

Critical: purchase H9 missing period/GL (BB-000199); journals HasCompany-only (BB-000200). Medium: `accounting_enabled` via Company PATCH (BB-000216). Prior dual-ledger / purchases→5100 / FIFO gaps remain Deferred/Open as applicable.
""",
    "12_DEVOPS_REVIEW.md": f"""
## Wave 8 ({TODAY}) — refresh

**Corrected prior stale claims:** Celery beat **is** in compose; pip-audit **is** blocking. Still open: TLS (BB-000015), backups (BB-000045), no CD (BB-000219), Redis unauthenticated + default PG password (BB-000217), celery health false-positive (BB-000218), Dockerfile root (BB-000207), no Dependabot/CodeQL/Trivy (BB-000220), RUNBOOKS omits beat on restore (BB-000238).
""",
    "07_PERFORMANCE_REVIEW.md": f"""
## Wave 8 ({TODAY})

Invoice editor fetch-all customers (BB-000246); silent 50-page truncation (BB-000245); no virtualization residual; load unproven. Score ~5.0.
""",
    "11_API_REVIEW.md": f"""
## Wave 8 ({TODAY})

Payment webhook probe uses sandbox parser (BB-000205); public pay metadata disclosure (BB-000237); idempotency still roadmap (BB-000189).
""",
    "13_TESTING_REVIEW.md": f"""
## Wave 8 ({TODAY})

Light e2e job without API (BB-000221); missing adversarial payment webhook suite for BB-000196–198; process failure BB-000251 (Resolved without re-verify).
""",
    "14_UI_UX_REVIEW.md": f"""
## Wave 8 ({TODAY})

Mobile drawer stays open (BB-000242); menu aria-label missing (BB-000243); skip-link missing (BB-000244); RoleRoute gaps confuse VIEWER UX.
""",
    "15_AI_REVIEW.md": f"""
## Wave 8 ({TODAY})

Tool JSON truncated to 800 chars then re-fed (BB-000236). PILOT_ADVANCED can over-enable AI in prod builds (BB-000223).
""",
    "16_MOBILE_REVIEW.md": f"""
## Wave 8 ({TODAY})

Still responsive-web only (BB-000179). Drawer UX bug BB-000242. No PWA.
""",
    "17_INTEGRATION_REVIEW.md": f"""
## Wave 8 ({TODAY})

Cashfree/PayU stub links (BB-000211); Razorpay stub-on-error (BB-000198); WhatsApp/GSP/SMS still Deferred; GSTIN Null provider (BB-000225).
""",
    "21_PRODUCTION_READINESS.md": f"""
## Wave 8 ({TODAY}) — GO / NO-GO

**NO-GO for paid pilot with payments.** Score **4.5/10**.

Must be green before pilot:
- [ ] BB-000196 / 197 / 198 payment authenticity
- [ ] BB-000199 purchase H9
- [ ] BB-000200 / 201 accounting RBAC
- [ ] BB-000015 TLS (ops)
- [ ] BB-000045 backups (ops)
- [ ] GO_NO_GO.md signed (BB-000014)

BB-000047 Observability reopened — do not treat prior Resolved as APM complete.
""",
    "19_TECHNICAL_DEBT.md": f"""
## Wave 8 ({TODAY})

Process debt: false Resolved closure (BB-000251). Doc drift: 12_DEVOPS_REVIEW stale claims (BB-000239); root MVP/PERF/UX stale (BB-000240). God modules unchanged.
""",
    "20_REFACTORING_PLAN.md": f"""
## Wave 8 ({TODAY}) priority refactors

1. Payment adapter fail-closed module + adversarial tests
2. Shared H9 amend service (sales+purchase)
3. Accounting permission mixin
4. Split resources.ts / invoice-purchase editors
5. Server-driven party/product pickers (kill fetchAll for docs)
""",
    "02_ARCHITECTURE_REVIEW.md": f"""
## Wave 8 ({TODAY})

No architecture change. Confirmed risks: shared-DB tenancy without RLS, dual AR/AP vs GL, payment adapter sandbox escape hatch as architectural footgun. Score ~6.0.
""",
    "05_DATABASE_REVIEW.md": f"""
## Wave 8 ({TODAY})

No new schema Criticals. Residual concurrency: StockBalance get_or_create race (BB-000235); document number sync_next unlocked (BB-000234).
""",
    "10_BUSINESS_LOGIC_REVIEW.md": f"""
## Wave 8 ({TODAY})

Purchase amend / journal RBAC / payment settle paths are business-integrity defects — see BB-000196–200.
""",
    "18_COMPETITOR_ANALYSIS.md": f"""
## Wave 8 ({TODAY})

No change to competitor gaps (Tally/Zoho/ERPNext). Payment integrity bugs make BizBoard weaker than Zoho Books on collections reliability until P0s close.
""",
    "KNOWN_LIMITATIONS_AND_TECH_DEBT.md": f"""
## Wave 8 ({TODAY})

Added known limitations: payment adapters may stub/sandbox; purchase H9 incomplete; journals not SoD-gated; celery health ≠ worker liveness.
""",
    "ARCHITECTURAL_DECISIONS.md": f"""
## Wave 8 ({TODAY}) ADR notes

- **ADR-W8-1:** Payment sandbox adapter must never activate for named providers without credentials in non-test env.
- **ADR-W8-2:** “Resolved” in register requires linked adversarial test; process gate BB-000251.
""",
}


def main():
    write_executive_summary()
    update_changelog()
    update_roadmap()
    for name, section in REVIEW_SECTIONS.items():
        append_once(OUT / name, f"## Wave 8 ({TODAY})", section)
    print("Updated executive summary, changelog, roadmap, and review appendices.")


if __name__ == "__main__":
    main()
