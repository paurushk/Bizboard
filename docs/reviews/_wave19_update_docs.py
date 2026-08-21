#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prepend Wave 19 living-doc sections. Do not overwrite history."""
from __future__ import annotations

import json
from pathlib import Path

TODAY = "2026-08-05"
OUT = Path(__file__).resolve().parent
STATS = json.loads((OUT / "_stats.json").read_text(encoding="utf-8"))
W19 = STATS["wave19"]
SCORES = W19["scores"]
START, END = W19["start"], W19["end"]
NEW = W19["new"]
OPEN = STATS["open_count"]
TOTAL = STATS["total"]

SEV = STATS["severity"]
PRI = STATS["priority"]
CAT = STATS["category"]
MOD = STATS["module"]
STATUS = STATS["status"]


def prepend_after_title(path: Path, section: str, marker: str) -> None:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return
    lines = text.splitlines(keepends=True)
    if not lines:
        path.write_text(section + text, encoding="utf-8")
        return
    # insert after first heading line
    out = [lines[0]]
    if len(lines) > 1 and lines[1].strip() == "":
        out.append(lines[1])
        rest = lines[2:]
    else:
        rest = lines[1:]
    path.write_text("".join(out) + section + "".join(rest), encoding="utf-8")


def main() -> None:
    exec_banner = (
        f"**Latest:** Wave 19 independent re-audit {TODAY} — register **{TOTAL}** issues "
        f"(`{START}`…`{END}`, +{NEW} Open). **Open: {OPEN}.** "
        f"Production Readiness **{SCORES['production_readiness']} / 10**. "
        f"Wave 18 Open==0 / PR~9.0 **invalidated**.\n\n"
    )
    exec_section = f"""
---

## Wave 19 re-audit ({TODAY}) — SUPERSEDES Wave 18 “Open == 0” / PR~9.0

Independent code re-verification of live `backend/`, `web/`, `mobile/`, compose, nginx, and CI after Wave 18 closed Deferred MVPs. **{NEW} new issues** logged as `{START}` … `{END}`.

### Updated verdict

| Audience | Deploy? |
|----------|---------|
| Internal dogfood (ERP flags off, accounting off, Owner-only, RLS off, no OCR commit without rate review) | **Conditional** |
| Paid pilot claiming Manufacturing / Payroll / multi-GSTIN / RLS / mobile app | **No** |
| GA / unsupervised Cloud ERP for Indian MSMEs | **No** |

### Scores (0–10) — Wave 19

| Dimension | Score | Notes |
|-----------|------:|-------|
| Production Readiness | **{SCORES['production_readiness']}** | Open P0s; Final Gates still unsigned |
| Architecture | **{SCORES['architecture']}** | ERP bolt-ons without stock/GSTIN bounded contexts |
| Security | **{SCORES['security']}** | RLS theater; host `*` bypass; VIEWER ERP; WhatsApp global token |
| Performance | **{SCORES['performance']}** | Master fetch-all remains; FIFO unproven under WO+POS |
| Accounting Correctness | **{SCORES['accounting']}** | WO silent GL; payroll 2100/net-only; AA amount match |
| GST Compliance | **{SCORES['gst']}** | Multi-GSTIN blended GSTR; OCR rate=18; GSTR-9 stubs |
| Maintainability | **{SCORES['maintainability']}** | Flag/doc/client dual stacks |
| Scalability | **{SCORES['scalability']}** | RLS unsafe; superuser DB role; no load proof |
| Testing Coverage | **{SCORES['testing']}** | Wave19 gates are string checks; residual P0s untested |

### Register totals (cumulative)

| Metric | Count |
|--------|------:|
| **Total issues** | **{TOTAL}** |
| Critical | {SEV.get('Critical', 0)} |
| High | {SEV.get('High', 0)} |
| Medium | {SEV.get('Medium', 0)} |
| Low | {SEV.get('Low', 0)} |
| **Open** | **{OPEN}** |
| Resolved | {STATUS.get('Resolved', 0)} |
| Deferred — roadmap | {STATUS.get('Deferred — roadmap', 0)} |
| Deferred — ops owner | {STATUS.get('Deferred — ops owner', 0)} |
| Accepted (positive) | {STATUS.get('Accepted (positive)', 0)} |

### Wave 19 P0 blockers

1. **BB-000550** — `ALLOWED_HOSTS='*'` classified local
2. **BB-000551 / BB-000552** — RLS non-functional (SET LOCAL + superuser)
3. **BB-000553** — VIEWER mutates manufacturing/payroll/CRM
4. **BB-000554 / BB-000555** — WO SALE/PURCHASE + list-price FG
5. **BB-000556** — GSTR ignores `company_gstin` stamp
6. **BB-000557** — OCR defaults GST rate 18%
7. **BB-000558** — Wave 18 process invalidation

### Final CTO Verdict (Wave 19)

**Do not commercially launch BizBoard as a Cloud ERP.** Wave 17–18 module checkboxes (Manufacturing, Payroll, CRM, RLS, Mobile, multi-GSTIN) are **preview scaffolds** with P0 correctness and isolation defects.

**Do** continue a **controlled GST billing + inventory + optional books dogfood** with:

- ERP / POS / OCR / WhatsApp-cloud / AA / FIFO / RLS flags **off** unless explicitly waived.
- All Wave 19 P0s closed or signed-risk waived.
- `docs/pilot/GO_NO_GO.md` and `FINAL_GATES_10.md` actually signed.
- Product copy matching a single honesty matrix (README + OpenAPI + UI + this register).

Core billing Decimal math, tenant-scoped viewsets, and append-only stock remain the valuable core. The launch failure mode is still **over-claiming incomplete ERP/GST/isolation**, now worse because half-built modules can corrupt stock and books when flags are flipped on.

---

"""

    exec_path = OUT / "01_EXECUTIVE_SUMMARY.md"
    text = exec_path.read_text(encoding="utf-8")
    text = re_sub_latest = __import__("re").sub(
        r"\*\*Latest:\*\*[^\n]*",
        exec_banner.strip(),
        text,
        count=1,
    )
    if f"## Wave 19 re-audit ({TODAY})" not in text:
        # append section at end to preserve history
        text = text.rstrip() + "\n" + exec_section
    exec_path.write_text(text + "\n", encoding="utf-8")

    prod_section = f"""
# Production readiness (Wave 19 — {TODAY})

**Score: {SCORES['production_readiness']} / 10.** Open **{OPEN}** after Wave 19 re-audit (`{START}`–`{END}`).

Wave 18 engineering ceiling ~9.0 is **withdrawn**. RLS, multi-GSTIN GSTR, manufacturing valuation, payroll statutory, mobile app, and VIEWER ACL are not launch-ready.

Dogfood: Conditional (ERP flags off). Paid multi-role / ERP-claimed pilot: **No**. GA: **No**.

Must before any paid pilot that enables new Wave 17–18 flags:

- [ ] Close BB-000550–BB-000558 (or signed waiver)
- [ ] Residual pytest red→green for RLS runtime, WO movement types, VIEWER 403, GSTR-per-GSTIN, OCR no default rate
- [ ] Final Gates in `docs/pilot/FINAL_GATES_10.md` still required for any 10/10 language

"""
    prod = OUT / "21_PRODUCTION_READINESS.md"
    body = prod.read_text(encoding="utf-8")
    if f"Wave 19 — {TODAY}" not in body:
        prod.write_text(prod_section + body, encoding="utf-8")

    road = f"""## Wave 19 hotfix track ({TODAY}) — P0 before any ERP-flagged pilot

> Wave 18 Open==0 is **not** a launch gate. Open count now **{OPEN}** (`{START}`–`{END}`).

| Focus | Issue IDs | Outcome |
|-------|-----------|---------|
| Host/DEBUG bypass | BB-000550, BB-000559 | Wildcard/IP hosts cannot look local |
| RLS actually works or stays off | BB-000551, BB-000552, BB-000560, BB-000561, BB-000562 | Non-superuser + session GUC + child company_id |
| ERP RBAC | BB-000553, BB-000563 | VIEWER cannot move stock/cash |
| Manufacturing stock/GL | BB-000554, BB-000555, BB-000564, BB-000565, BB-000583, BB-000593 | Real movement types + cancel + postings |
| GST multi-GSTIN + OCR | BB-000556, BB-000557, BB-000568, BB-000569 | Per-GSTIN returns/series; no invented rates |
| Payroll honesty or statutory | BB-000566, BB-000567 | No fake payroll product |
| Secrets / WhatsApp / outbox | BB-000571, BB-000572, BB-000573 | No global token; no secret sprawl |
| Docs/mobile honesty | BB-000574, BB-000575, BB-000558 | One module matrix; unclaim store app |
| Tests | BB-000576 | Residual suite required in CI |

**Exit:** Dogfood billing+inventory only; ERP flags off until P0s green.

"""
    roadmap = OUT / "REMEDIATION_ROADMAP.md"
    rb = roadmap.read_text(encoding="utf-8")
    if f"Wave 19 hotfix track ({TODAY})" not in rb:
        roadmap.write_text(road + rb, encoding="utf-8")

    review_blurbs = {
        "02_ARCHITECTURE_REVIEW.md": f"""## Wave 19 ({TODAY})

ERP apps bolted onto `CompanyScopedViewSet` without inventory event taxonomy, filing-GSTIN aggregate root, or GL participation. RLS middleware is not an isolation architecture (BB-000551/552). ADRs missing for these designs (BB-000598). Issues: BB-000551–556, BB-000564, BB-000583, BB-000593, BB-000598.

""",
        "03_BACKEND_REVIEW.md": f"""## Wave 19 ({TODAY})

New P0/P1 in manufacturing/payroll/crm services, feature-flag asserts, idempotency shadowing, Celery RLS bootstrap. Issues: BB-000553–555, BB-000561, BB-000563–567, BB-000586.

""",
        "04_FRONTEND_REVIEW.md": f"""## Wave 19 ({TODAY})

No invoice GSTIN picker; outbox schema incomplete; fetch-all masters remain; typedClient only on manufacturing; ERP a11y/i18n gaps. Issues: BB-000556, BB-000572, BB-000577–580, BB-000588–589, BB-000597.

""",
        "05_DATABASE_REVIEW.md": f"""## Wave 19 ({TODAY})

Child tables without `company_id` (BomLine, PaySlip, StockTransferLine) omitted from Wave 19 RLS list. Superuser runtime role. Document series uniqueness ignores GSTIN. Issues: BB-000552, BB-000562, BB-000569.

""",
        "06_SECURITY_REVIEW.md": f"""## Wave 19 ({TODAY})

Critical: ALLOWED_HOSTS `*` local bypass (BB-000550); RLS theater (BB-000551/552); VIEWER ERP ACL (BB-000553); WhatsApp global token (BB-000571); plaintext outbox (BB-000572); GSP creds on company PATCH (BB-000573); nginx IP Host rewrite (BB-000559).

""",
        "07_PERFORMANCE_REVIEW.md": f"""## Wave 19 ({TODAY})

`fetchAllPagesMasters` still used for customers/products/COA (BB-000578). FIFO layer locking unproven under concurrent WO+invoice (BB-000592).

""",
        "08_GST_REVIEW.md": f"""## Wave 19 ({TODAY})

P0: multi-GSTIN blended GSTR + interstate from primary GSTIN (BB-000556); OCR rate default 18 (BB-000557); series not per GSTIN (BB-000569); GSTR-9 tables 6/7 stubs (BB-000568); outbox drops cess (BB-000577); SUPECOM still unguarded (BB-000596).

""",
        "09_ACCOUNTING_REVIEW.md": f"""## Wave 19 ({TODAY})

Manufacturing silent GL (BB-000564); FG list-price receipts (BB-000555); payroll net-to-2100/1100 (BB-000567); AA amount-only match (BB-000570). Dual-ledger ADR-A02 violated by new modules.

""",
        "10_BUSINESS_LOGIC_REVIEW.md": f"""## Wave 19 ({TODAY})

WO state machine has no cancel (BB-000565); BOM not snapshotted (BB-000583); CRM is status CRUD (BB-000582); SALE enum overload (BB-000593).

""",
        "11_API_REVIEW.md": f"""## Wave 19 ({TODAY})

OpenAPI description denies installed apps (BB-000584); typedClient not on money APIs (BB-000579); feature_flags JSON not in Company API (BB-000563).

""",
        "12_DEVOPS_REVIEW.md": f"""## Wave 19 ({TODAY})

Compose DB superuser (BB-000552); nginx Host rewrite (BB-000559); base compose still migrates on api start (BB-000585). Final Gates ops IDs remain Deferred.

""",
        "13_TESTING_REVIEW.md": f"""## Wave 19 ({TODAY})

`test_wave19.py` and `_wave19_assert_gates.py` are presence checks, not residual P0 probes (BB-000576, BB-000558). Mock flags hide ERP routes (BB-000597).

""",
        "14_UI_UX_REVIEW.md": f"""## Wave 19 ({TODAY})

Missing GSTIN picker on invoice UI; Hindi gaps on ERP/POS (BB-000588); a11y on new dialogs (BB-000589); module banners vs README conflict (BB-000574).

""",
        "15_AI_REVIEW.md": f"""## Wave 19 ({TODAY})

OCR prompt invents 18% GST (BB-000557). `ai_features_enabled` Owner-writable without gated consent (BB-000581).

""",
        "16_MOBILE_REVIEW.md": f"""## Wave 19 ({TODAY})

Capacitor tree is config-only (BB-000575). PWA manifest without service worker (BB-000580). Do not claim Mobile App.

""",
        "17_INTEGRATION_REVIEW.md": f"""## Wave 19 ({TODAY})

WhatsApp env token fallback (BB-000571). AA amount-only recon (BB-000570). GSP secrets via company PATCH (BB-000573).

""",
        "18_COMPETITOR_ANALYSIS.md": f"""## Wave 19 ({TODAY})

Checkbox ERP modules do not create Zoho/TallyPrime/ERPNext parity (BB-000591). Positioning must stay “GST billing + inventory (+ preview modules)”.

""",
        "19_TECHNICAL_DEBT.md": f"""## Wave 19 ({TODAY})

New debt: dual flag systems, SALE enum overload, untyped money clients, stale honesty docs, RLS design that cannot be enabled. See `{START}`–`{END}`.

""",
        "20_REFACTORING_PLAN.md": f"""## Wave 19 ({TODAY})

Priority refactors: (1) inventory business-event types, (2) filing GSTIN aggregate + series, (3) RLS session GUC + app role, (4) ERP capability matrix, (5) kill legacy fetch-all + typed money client. Do not add more ERP surface until P0s close.

""",
        "KNOWN_LIMITATIONS_AND_TECH_DEBT.md": f"""## Wave 19 living limitations ({TODAY})

| Limitation | Honest status now |
|------------|-------------------|
| Manufacturing | **Preview CRUD** — WO uses SALE/PURCHASE; no cancel; no GL; no BOM snapshot |
| Payroll | **Salary voucher only** — no PF/ESI/PT/TDS; wrong COA |
| CRM | **Lead notebook** — no convert/activities |
| Multi-GSTIN | **Stamp field only** — GSTR/series/UI not GSTIN-scoped |
| RLS | **Unsafe to enable** — SET LOCAL no-op; superuser bypass |
| Mobile | **Capacitor config + manifest** — no store binary, no SW |
| WhatsApp Cloud | **Optional** — global token fallback unsafe |
| OCR | **Assistive** — unknown rate currently defaults to 18% (P0) |
| GSTR-9 | **Partial worksheet** — tables 6/7 stubs |
| FIFO | **Code path exists** — load-unproven with WO+POS |
| Final Gates | **Ops/CA unsigned** — blocks any 10/10 claim |

""",
        "ARCHITECTURAL_DECISIONS.md": f"""## Wave 19 recommended ADRs ({TODAY}) — not yet adopted

### ADR-A19 — Do not enable Postgres RLS until session GUC + NOSUPERUSER app role land

**Decision (recommended):** `POSTGRES_RLS_ENABLED` remains 0 in all deployed envs until BB-000551/552/560/561/562 close.  
**Rationale:** Current SET LOCAL + superuser design is theater or outage.

### ADR-A20 — Inventory movements are business events, not SALE/PURCHASE overloads

**Decision (recommended):** Manufacturing, transfers, challans, and invoices must not share `MovementType.SALE`/`PURCHASE`.  
**Rationale:** BB-000554/555/593.

### ADR-A21 — Filing GSTIN is an aggregate root for series, tax split, and returns

**Decision (recommended):** Either one active filing GSTIN per tenant or full per-GSTIN series+GSTR. Stamps without scoping are forbidden.  
**Rationale:** BB-000556/569.

""",
    }

    for name, section in review_blurbs.items():
        path = OUT / name
        if not path.exists():
            continue
        marker = f"Wave 19 ({TODAY})"
        if "living limitations" in section:
            marker = f"Wave 19 living limitations ({TODAY})"
        elif "recommended ADRs" in section:
            marker = f"Wave 19 recommended ADRs ({TODAY})"
        prepend_after_title(path, section + "\n", marker)

    print("WAVE19 DOCS UPDATED")


if __name__ == "__main__":
    main()
