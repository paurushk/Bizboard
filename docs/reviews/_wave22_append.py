#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wave 22 append BB-000695+."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from _wave22_issues import ISSUES

TODAY = "2026-08-06"
OUT = Path(__file__).resolve().parent
REGISTER = OUT / "MASTER_ISSUE_REGISTER.md"
STATS = OUT / "_stats.json"
CHANGELOG = OUT / "CHANGELOG.md"
EXEC = OUT / "01_EXECUTIVE_SUMMARY.md"
ROADMAP = OUT / "REMEDIATION_ROADMAP.md"
PROD = OUT / "21_PRODUCTION_READINESS.md"
START_ID = 695


def render_issue(n: int, data: dict) -> str:
    iid = f"BB-{n:06d}"
    return f"""
## {iid} — {data['title']}

| Field | Value |
|-------|-------|
| **Issue ID** | {iid} |
| **Title** | {data['title']} |
| **Category** | {data['category']} |
| **Subcategory** | {data['subcategory']} |
| **Severity** | {data['severity']} |
| **Priority** | {data['priority']} |
| **Module** | {data['module']} |
| **Feature** | {data['feature']} |
| **Affected Files** | {data['files']} |
| **Affected Classes** | See files |
| **Affected Functions** | See files |
| **Affected APIs** | See files / related endpoints |
| **Affected Database Tables** | See models in files |
| **Status** | Open |
| **Owner** | Unassigned |
| **Review Date** | {TODAY} |
| **Estimated Effort** | {data['effort']} |
| **Breaking Change** | Possibly — assess per fix |
| **Regression Risk** | Medium unless tests added |
| **Dependencies** | See Cross References |
| **Cross References** | {data['refs']} |
| **References** | Wave 22 independent re-audit; {TODAY} |

### Problem Description
{data['problem']}

### Evidence
{data['evidence']}

### Code Snippet
See affected files at `{TODAY}` tree.

### Root Cause
{data['root_cause']}

### Business Impact
{data['business']}

### Technical Impact
{data['technical']}

### Customer Impact
{data['customer']}

### Security Impact
{data['security']}

### Performance Impact
{data['performance']}

### Scalability Impact
{data['scalability']}

### Compliance Impact
{data['compliance']}

### Risk if ignored
{data['risk']}

### Steps to reproduce
1. Follow evidence paths in current tree.
2. Execute related API/UI flow.
3. Observe failure vs acceptance criteria.

### Recommended Fix
{data['fix_immediate']}

### Immediate Fix
{data['fix_immediate']}

### Short-term Fix
{data['fix_short']}

### Long-term Refactor
{data['fix_long']}

### Alternative Solutions
Waive with signed risk in GO_NO_GO only if non-P0.

### Required Tests
{data['tests']}

### Acceptance Criteria
{data['acceptance']}
"""


def merge_count(old: dict, add: Counter) -> dict:
    out = dict(old or {})
    for k, v in add.items():
        out[k] = out.get(k, 0) + v
    return out


def main() -> None:
    prior = json.loads(STATS.read_text(encoding="utf-8"))
    assert prior["total"] == START_ID - 1, f"Expected prior total {START_ID-1}, got {prior['total']}"
    assert len(ISSUES) == 64, len(ISSUES)

    start, end = START_ID, START_ID + len(ISSUES) - 1
    blocks, meta = [], []
    for i, data in enumerate(ISSUES):
        n = start + i
        blocks.append(render_issue(n, data))
        meta.append(
            {
                "id": f"BB-{n:06d}",
                "title": data["title"],
                "severity": data["severity"],
                "priority": data["priority"],
                "category": data["category"],
                "module": data["module"],
                "status": "Open",
            }
        )

    reg = REGISTER.read_text(encoding="utf-8")
    if f"BB-{start:06d}" in reg:
        raise SystemExit(f"BB-{start:06d} already present")

    note = f"""
## Wave 22 independent re-audit ({TODAY})

Appended **{len(ISSUES)}** issues `BB-{start:06d}` … `BB-{end:06d}` from residual live-code verification after Sprint A–E / Wave 21 closures. Prior IDs unchanged. Invalidates post-sprint “engineering ceiling 9.x” as a commercial launch gate until Wave 22 P0s close.

"""
    sev, pri, cat, mod = (
        Counter(x["severity"] for x in meta),
        Counter(x["priority"] for x in meta),
        Counter(x["category"] for x in meta),
        Counter(x["module"] for x in meta),
    )
    new_total = prior["total"] + len(ISSUES)
    status = dict(prior.get("status") or {})
    # Normalize deferred keys that may have encoding issues
    status["Open"] = status.get("Open", 0) + len(ISSUES)
    severity = merge_count(prior.get("severity"), sev)
    priority = merge_count(prior.get("priority"), pri)
    category = merge_count(prior.get("category"), cat)
    module = merge_count(prior.get("module"), mod)

    if reg.startswith("#"):
        nl = reg.find("\n")
        reg2 = reg[: nl + 1] + note + reg[nl + 1 :]
    else:
        reg2 = note + reg
    reg2 = re.sub(r"(\| \*\*Total issues\*\* \| )(\d+)( \|)", rf"\g<1>{new_total}\3", reg2, count=1)
    for label in ("Critical", "High", "Medium", "Low"):
        reg2 = re.sub(rf"(\| {label} \| )(\d+)( \|)", rf"\g<1>{severity.get(label, 0)}\3", reg2, count=1)
    for label in ("P0", "P1", "P2", "P3"):
        reg2 = re.sub(rf"(\| {label} \| )(\d+)( \|)", rf"\g<1>{priority.get(label, 0)}\3", reg2, count=1)
    for label, key in [
        ("Resolved", "Resolved"),
        ("Open", "Open"),
        ("Deferred — roadmap", "Deferred — roadmap"),
        ("Deferred — ops owner", "Deferred — ops owner"),
        ("Accepted (positive)", "Accepted (positive)"),
    ]:
        # Also try mojibake key for deferred
        val = status.get(key)
        if val is None and "Deferred" in key:
            for sk, sv in status.items():
                if "Deferred" in sk and ("roadmap" in key) == ("roadmap" in sk or "roadmap" in sk.encode("utf-8", "replace").decode("utf-8", "replace")):
                    if "roadmap" in key and "roadmap" in sk:
                        val = sv
                    elif "ops" in key and "ops" in sk:
                        val = sv
        if val is not None:
            reg2 = re.sub(rf"(\| {re.escape(label)} \| )(\d+)( \|)", rf"\g<1>{val}\3", reg2, count=1)

    REGISTER.write_text(reg2 + "\n".join(blocks) + "\n", encoding="utf-8")

    scores = {
        "production_readiness": 4.2,
        "architecture": 4.8,
        "security": 3.5,
        "performance": 4.5,
        "accounting": 5.5,
        "gst": 5.0,
        "maintainability": 4.2,
        "scalability": 3.5,
        "testing": 4.6,
    }
    stats = {
        **prior,
        "total": new_total,
        "open_count": status.get("Open", 0),
        "severity": severity,
        "priority": priority,
        "category": category,
        "module": module,
        "status": status,
        "audit_date": TODAY,
        "issues": (prior.get("issues") or []) + meta,
        "wave22": {
            "date": TODAY,
            "new": len(ISSUES),
            "start": f"BB-{start:06d}",
            "end": f"BB-{end:06d}",
            "severity": dict(sev),
            "priority": dict(pri),
            "scores": scores,
        },
    }
    STATS.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    cl = f"""## {TODAY} — Wave 22 independent re-audit

Live-code residual pass after Sprint A–E / Wave 21 (register previously Open=0 for 550–694).

- Appended **{len(ISSUES)}** issues `BB-{start:06d}` … `BB-{end:06d}` (Critical {sev.get('Critical', 0)} · High {sev.get('High', 0)} · Medium {sev.get('Medium', 0)} · Low {sev.get('Low', 0)}).
- Register total: **{new_total}**. Wave 22 Open: **{len(ISSUES)}**.
- Invalidates engineering-ceiling PR/Accounting/GST 9.x as commercial launch gate until Wave 22 P0s close.
- Top P0s: sales RCM GL (695); GSTR-3B empty-stamp (697); period swallow (699); bank/gateway period bypass (700); payroll employer GL (703); challan/PI cancel FIFO (717/718); PR serial drop (722); SaaS ACTIVE/no-sub (725); idempotency TOCTOU (730); PWA API cache (738).

Scores revised (honest residual): PR **{scores['production_readiness']}**, Accounting **{scores['accounting']}**, GST **{scores['gst']}**, Security **{scores['security']}**.

Agents: [Audit accounting GST security](7496f099-6068-4cbc-a47d-f351ed153039), [Audit inventory sales payroll](3148440a-3c08-4abb-a850-3a4b1597348d), [Audit frontend mobile DevOps](b9c6c334-890f-4d03-951e-3d1c44190ddf).

---

"""
    CHANGELOG.write_text(cl + CHANGELOG.read_text(encoding="utf-8"), encoding="utf-8")

    banner = (
        f"**Latest:** Wave 22 independent re-audit {TODAY} — register **{new_total}** "
        f"(`BB-000695`…`BB-{end:06d}`). **Wave 22 Open: {len(ISSUES)}.** "
        f"PR **{scores['production_readiness']} / 10** (supersedes Sprint A–E engineering ceiling for launch gate). "
        f"P0 residuals: sales RCM GL, GSTR-3B stamp, PWA API cache, FIFO cancel, SaaS gate, payroll employer.\n"
    )
    et = EXEC.read_text(encoding="utf-8")
    et = re.sub(r"\*\*Latest:\*\*[^\n]*", banner.strip(), et, count=1)
    section = f"""
---

## Wave 22 independent re-audit ({TODAY})

Post Sprint A–E live-code residual pass. **+{len(ISSUES)} Open** `BB-{start:06d}`–`BB-{end:06d}`. Prior closures retained; incomplete remediations logged as new IDs.

### Additional P0 blockers

- **BB-000695** — Sales RCM still posts Output GST / full-tax AR
- **BB-000697** — GSTR-3B re-resolves stamp from empty invoice list
- **BB-000699 / 700** — Period gate swallow + bank/gateway bypass
- **BB-000703** — Payroll employer PF/ESI never posted
- **BB-000717 / 718 / 722** — Challan/PI cancel FIFO; purchase-return serial drop
- **BB-000725** — SaaS ACTIVE without payment; no-sub never blocked
- **BB-000730** — Idempotency-Key TOCTOU residual
- **BB-000738** — PWA caches `/api` (status 0); logout does not purge

### Scores (supersede Sprint A–E engineering ceiling for launch gate)

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

**CTO:** Still **NO-GO** for commercial “full Cloud ERP” launch. Dogfood conditional. Paid pilot blocked until Wave 22 P0s closed or signed waived. Do not claim multi-GSTIN 3B, sales RCM books, SaaS entitlements, or offline PWA privacy until 697/695/725/738 fixed.

---
"""
    if f"Wave 22 independent re-audit ({TODAY})" not in et:
        et = et.rstrip() + "\n" + section
    EXEC.write_text(et + "\n", encoding="utf-8")

    prod_bit = f"""# Production readiness (Wave 22 — {TODAY})

**Score: {scores['production_readiness']} / 10.** Wave 22 Open **{len(ISSUES)}** (`BB-{start:06d}`–`BB-{end:06d}`). Register total **{new_total}**.

Hard stops beyond Final Gates: BB-000695 (sales RCM GL), BB-000697 (GSTR-3B stamp), BB-000699/700 (period bypass), BB-000703 (payroll employer), BB-000717/718/722 (FIFO/serial), BB-000725 (SaaS gate), BB-000730 (idempotency), BB-000738 (PWA API cache).

"""
    pb = PROD.read_text(encoding="utf-8")
    if f"Wave 22 — {TODAY}" not in pb:
        PROD.write_text(prod_bit + pb, encoding="utf-8")

    road_bit = f"""## Wave 22 hotfix ({TODAY})

| Focus | IDs |
|-------|-----|
| Sales RCM GL + GSTR RCM note liability + 3B stamp + GSTR-9 GSTIN | BB-000695, BB-000696, BB-000697, BB-000698 |
| Period gate swallow + bank/gateway/unallocate dating | BB-000699, BB-000700, BB-000701 |
| Payroll employer GL + ESI ceiling | BB-000703, BB-000704 |
| FIFO cancel/return/transfer/H9 + PR serial + WO lot/serial | BB-000717–BB-000724 |
| SaaS ACTIVE/PAST_DUE/seats + idempotency TOCTOU | BB-000725–BB-000727, BB-000730 |
| PWA API cache + navigateFallback + AI settings fail-open | BB-000737, BB-000738, BB-000756 |
| GSTR export GSTIN + company switch persist + feature-flag asymmetry | BB-000740, BB-000741, BB-000745 |
| OpenAPI/Android CI + recon GET + nginx SW headers | BB-000748–BB-000750, BB-000754, BB-000755 |

"""
    rb = ROADMAP.read_text(encoding="utf-8")
    if f"Wave 22 hotfix ({TODAY})" not in rb:
        ROADMAP.write_text(road_bit + rb, encoding="utf-8")

    blurbs = {
        "02_ARCHITECTURE_REVIEW.md": f"## Wave 22 ({TODAY})\n\nBB-000757 inventory↔sales coupling; BB-000725 SaaS entitlement theater; dual-ledger residuals 695/703/713.\n\n",
        "03_BACKEND_REVIEW.md": f"## Wave 22 ({TODAY})\n\nSales RCM GL missing (695); period except-pass (699); service-layer period bypass (700); idempotency TOCTOU (730); recon GET mutates (754).\n\n",
        "04_FRONTEND_REVIEW.md": f"## Wave 22 ({TODAY})\n\nPWA API cache (738); navigateFallback lie (737); feature-flag asymmetry (741); AI settings ON (756); NewInvoicePage god module (751); company switch persist (745).\n\n",
        "05_DATABASE_REVIEW.md": f"## Wave 22 ({TODAY})\n\nFIFO layer identity on cancel paths (717–720, 724); opening stock non-atomic with GL (705).\n\n",
        "06_SECURITY_REVIEW.md": f"## Wave 22 ({TODAY})\n\nPWA `/api` cache + status 0 (738); compose RLS forced off (710); Celery RLS prerun residual (709); company switch header race (745); Android allowBackup (746); GSTIN sandbox trust (734).\n\n",
        "07_PERFORMANCE_REVIEW.md": f"## Wave 22 ({TODAY})\n\nNo RED metrics/SLO path (753); recon GET write amplification (754); nginx immutable over-broad (755).\n\n",
        "08_GST_REVIEW.md": f"## Wave 22 ({TODAY})\n\nGSTR-3B empty stamp (697); GSTR-9 unscoped (698); RCM note liability (696); SUPECOM totals (707); silent primary stamp (708); export ignores GSTIN (740); 2B first-match (716); GSTR live filing stub (742).\n\n",
        "09_ACCOUNTING_REVIEW.md": f"## Wave 22 ({TODAY})\n\nSales RCM Output GST (695); RCM purchase discount (702); payroll employer (703); opening stock atomicity (705); WO dating (706); TCS under ENABLE_TDS (711); FY vs GST lock (712); BooksHealth coverage (713); unallocate reverse dating (701).\n\n",
        "10_BUSINESS_LOGIC_REVIEW.md": f"## Wave 22 ({TODAY})\n\nFIFO cancel/return/transfer/H9 (717–721); PR serial drop (722); WO lot/serial (723–724); SO convert drops serial (732); price_role dead (728); CRM re-entrant convert (731); no GRN (735).\n\n",
        "11_API_REVIEW.md": f"## Wave 22 ({TODAY})\n\nIdempotency TOCTOU (730); recon GET side effects (754); OpenAPI drift ungated (750); feature_flags no Owner API (715).\n\n",
        "12_DEVOPS_REVIEW.md": f"## Wave 22 ({TODAY})\n\nCompose RLS=0 pin (710); migrate-on-start base (714); CD .env fixture missing (749); Dependabot skips mobile (747); nginx SW cache headers (755).\n\n",
        "13_TESTING_REVIEW.md": f"## Wave 22 ({TODAY})\n\nBB-000580 presence-only theater (758); no Android CI (748); OpenAPI types ungated (750).\n\n",
        "14_UI_UX_REVIEW.md": f"## Wave 22 ({TODAY})\n\nGSTR export vs preview GSTIN (740); WhatsApp copy honesty (743); OCR PII disclaimer missing (744); offline.html unused (737).\n\n",
        "15_AI_REVIEW.md": f"## Wave 22 ({TODAY})\n\nAI settings default ON residual (756); OCR no LLM/PII consent (744); ErrorBoundary skips Sentry (752).\n\n",
        "16_MOBILE_REVIEW.md": f"## Wave 22 ({TODAY})\n\nallowBackup true (746); no CI Android assemble (748); PWA API cache affects WebView (738).\n\n",
        "17_INTEGRATION_REVIEW.md": f"## Wave 22 ({TODAY})\n\nGSTR filing adapter never Live (742); WhatsApp mode/error honesty (743); GSTIN HTTP sandbox trust (734).\n\n",
        "18_COMPETITOR_ANALYSIS.md": f"## Wave 22 ({TODAY})\n\nNo GRN vs Zoho/Tally (735); SaaS seat/entitlement non-enforcing vs Zoho Billing (725–727); multi-GSTIN 3B bug vs Tally multi-firm (697).\n\n",
        "19_TECHNICAL_DEBT.md": f"## Wave 22 ({TODAY})\n\nNewInvoicePage 1680LOC (751); inventory↔sales import (757); OpenAPI theater (750); weak PWA gate test (758).\n\n",
        "20_REFACTORING_PLAN.md": f"## Wave 22 ({TODAY})\n\nInsert: (0l) sales RCM posting branch; (0m) period gate in money services; (0n) FIFO reverse-by-layer; (0o) PWA NetworkOnly /api; (0p) SaaS fail-closed writes.\n\n",
        "KNOWN_LIMITATIONS_AND_TECH_DEBT.md": f"## Wave 22 limitations ({TODAY})\n\n| Area | Limitation |\n|------|------------|\n| Sales RCM | GSTR excludes; GL still posts Output GST |\n| Multi-GSTIN 3B | Stamp resolved from empty list |\n| FIFO cancels | Challan/PI/transfer/return peel wrong layers |\n| SaaS billing | ACTIVE without pay; no-sub never blocked |\n| PWA | Caches authenticated /api |\n| Payroll | Employer PF/ESI not in GL |\n| GRN | Not implemented |\n\n",
        "ARCHITECTURAL_DECISIONS.md": f"## Wave 22 ADR notes ({TODAY})\n\n**ADR-A32:** Money create/allocate must period-gate in the service layer, not only HTTP views. **ADR-A33:** Authenticated `/api` must never be SW-cached. **ADR-A34:** FIFO reverse restores peels / retires source layers — never invent zero-cost layers. **ADR-A35:** SaaS writes fail closed when subscription required. **ADR-A36:** Sales RCM posting must not credit Output GST.\n\n",
    }
    for name, section in blurbs.items():
        path = OUT / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        marker = section.split("\n", 1)[0]
        if marker in text:
            continue
        lines = text.splitlines(keepends=True)
        if not lines:
            continue
        rest = lines[1:]
        if rest and rest[0].strip() == "":
            path.write_text(lines[0] + rest[0] + section + "".join(rest[1:]), encoding="utf-8")
        else:
            path.write_text(lines[0] + "\n" + section + "".join(rest), encoding="utf-8")

    # Fix a few ID refs in roadmap that assumed wrong numbering for AI settings
    # BB-000756 = 695+61 = index 61 (0-based) → 695+61=756 yes if 65 issues (695..759)
    # 737 = 695+42, 738=695+43, 740=695+45, 741=695+46, 745=695+50, 756=695+61
    print(
        f"WAVE22 OK: BB-{start:06d}..BB-{end:06d} n={len(ISSUES)} "
        f"open={status.get('Open')} total={new_total} "
        f"sev={dict(sev)} pri={dict(pri)}"
    )


if __name__ == "__main__":
    main()
