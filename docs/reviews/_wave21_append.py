#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wave 21 append BB-000650+."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from _wave21_issues import ISSUES

TODAY = "2026-08-05"
OUT = Path(__file__).resolve().parent
REGISTER = OUT / "MASTER_ISSUE_REGISTER.md"
STATS = OUT / "_stats.json"
CHANGELOG = OUT / "CHANGELOG.md"
EXEC = OUT / "01_EXECUTIVE_SUMMARY.md"
ROADMAP = OUT / "REMEDIATION_ROADMAP.md"
PROD = OUT / "21_PRODUCTION_READINESS.md"
START_ID = 650


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
| **References** | Wave 21 residual passes; {TODAY} |

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
## Wave 21 residual passes ({TODAY})

Appended **{len(ISSUES)}** issues `BB-{start:06d}` … `BB-{end:06d}` from [Find more audit issues](b068e323-842d-410f-9ea4-ce7d7be094e9) and [Audit payroll mfg CRM](9d174bcc-11c0-45d7-b87c-03d9f1810cd1). Duplicates of BB-000639/643/648/649/640–642 skipped. Prior IDs unchanged.

"""
    sev, pri, cat, mod = (
        Counter(x["severity"] for x in meta),
        Counter(x["priority"] for x in meta),
        Counter(x["category"] for x in meta),
        Counter(x["module"] for x in meta),
    )
    new_total = prior["total"] + len(ISSUES)
    status = dict(prior.get("status") or {})
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
        if key in status:
            reg2 = re.sub(rf"(\| {re.escape(label)} \| )(\d+)( \|)", rf"\g<1>{status[key]}\3", reg2, count=1)

    REGISTER.write_text(reg2 + "\n".join(blocks) + "\n", encoding="utf-8")

    scores = {
        "production_readiness": 3.1,
        "architecture": 4.3,
        "security": 2.7,
        "performance": 4.5,
        "accounting": 2.2,
        "gst": 2.9,
        "maintainability": 4.0,
        "scalability": 3.0,
        "testing": 4.4,
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
        "wave21": {
            "date": TODAY,
            "new": len(ISSUES),
            "start": f"BB-{start:06d}",
            "end": f"BB-{end:06d}",
            "severity": dict(sev),
            "scores": scores,
        },
    }
    STATS.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    cl = f"""## {TODAY} — Wave 21 residual passes

Logged non-duplicate findings from [Find more audit issues](b068e323-842d-410f-9ea4-ce7d7be094e9) and [Audit payroll mfg CRM](9d174bcc-11c0-45d7-b87c-03d9f1810cd1).

- Appended **{len(ISSUES)}** issues `BB-{start:06d}` … `BB-{end:06d}` (Critical {sev.get('Critical', 0)} · High {sev.get('High', 0)} · Medium {sev.get('Medium', 0)} · Low {sev.get('Low', 0)}).
- Register total: **{new_total}**. Open: **{status.get('Open', 0)}**.
- Skipped duplicates: paid-CN (648), IRP stamp (639), e-way payload (640–642), file path (643), CN charges/POS (649).
- New P0s: receipt/alloc DELETE orphans GL; GSTR-1 CDNUR vs B2CS; mfg/CRM cross-tenant FKs; invite/prod password deadlock; multi-company join blocked; CompanyGstin no API; VIEWER payments ACL; AA flag ignored.

PR score revised **3.4 → 3.1**. Accounting **2.2**. Security **2.7**. GST **2.9**.

---

"""
    CHANGELOG.write_text(cl + CHANGELOG.read_text(encoding="utf-8"), encoding="utf-8")

    banner = (
        f"**Latest:** Wave 21 residual passes {TODAY} — register **{new_total}** "
        f"(`BB-000550`…`BB-{end:06d}`). **Open: {status.get('Open', 0)}.** "
        f"PR **{scores['production_readiness']} / 10**. "
        f"Waves 19–21 live-code verification.\n"
    )
    et = EXEC.read_text(encoding="utf-8")
    et = re.sub(r"\*\*Latest:\*\*[^\n]*", banner.strip(), et, count=1)
    section = f"""
---

## Wave 21 residual passes ({TODAY})

[Find more audit issues](b068e323-842d-410f-9ea4-ce7d7be094e9) + [Audit payroll mfg CRM](9d174bcc-11c0-45d7-b87c-03d9f1810cd1). **+{len(ISSUES)} Open** `BB-{start:06d}`–`BB-{end:06d}`. Duplicates of 639/643/648/649/640–642 not re-IDed.

### Additional P0 blockers

- **BB-000650 / 651** — Receipt/allocation DELETE orphans GL
- **BB-000652** — GSTR-1 CDNUR vs B2CS
- **BB-000672** — Mfg/CRM cross-tenant FKs
- **BB-000673 / 674** — Multi-company join + CompanyGstin CRUD missing
- **BB-000675 / 676 / 677** — Invite UI caps/password/reports defaults
- **BB-000680 / 691** — AA kill-switch off; VIEWER can list payments
- **BB-000688 / 689 / 686** — Sales/stock/AI KPIs wrong

### Scores (supersede Wave 20)

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

**CTO:** Still **NO-GO**. Production multi-user invite is broken. Tenant FK isolation fails on ERP modules. Cash DELETE corrupts books. Do not claim multi-company or multi-branch.

---
"""
    if f"Wave 21 residual passes ({TODAY})" not in et:
        et = et.rstrip() + "\n" + section
    EXEC.write_text(et + "\n", encoding="utf-8")

    prod_bit = f"""
# Production readiness (Wave 21 — {TODAY})

**Score: {scores['production_readiness']} / 10.** Open **{status.get('Open', 0)}** (`BB-000550`–`BB-{end:06d}`).

Additional hard stops: BB-000650/651 (GL orphans on DELETE), BB-000652 (GSTR-1 CDNUR), BB-000672 (cross-tenant FKs), BB-000676 (prod invite), BB-000673 (multi-company).

"""
    pb = PROD.read_text(encoding="utf-8")
    if f"Wave 21 — {TODAY}" not in pb:
        PROD.write_text(prod_bit + pb, encoding="utf-8")

    road_bit = f"""## Wave 21 hotfix ({TODAY})

| Focus | IDs |
|-------|-----|
| Money-doc DELETE + alloc reverse + period gate | BB-000650, BB-000651, BB-000654, BB-000655 |
| GSTR-1 CDNUR/B2CS + e-way cancel clear | BB-000652, BB-000653 |
| Tenant FKs + invite/prod + RBAC UI + VIEWER payments | BB-000672, BB-000675–677, BB-000691, BB-000694 |
| Multi-company join + CompanyGstin CRUD | BB-000673, BB-000674 |
| AA/WA flags + BOM ACTIVE + pay run immutability | BB-000678–685 |
| KPI/OCR/AI settings | BB-000686–693 |

"""
    rb = ROADMAP.read_text(encoding="utf-8")
    if f"Wave 21 hotfix ({TODAY})" not in rb:
        ROADMAP.write_text(road_bit + rb, encoding="utf-8")

    blurbs = {
        "06_SECURITY_REVIEW.md": f"## Wave 21 ({TODAY})\n\nBB-000672 cross-tenant ERP FKs; BB-000658 company-switch race; BB-000675–677 invite RBAC; BB-000691 VIEWER payments; BB-000680 AA flag; BB-000693 AI settings fail-open.\n\n",
        "08_GST_REVIEW.md": f"## Wave 21 ({TODAY})\n\nBB-000652 CDNUR vs B2CS; BB-000653 e-way cancel leaves bill no; BB-000663 auto-CN discount; BB-000674 CompanyGstin no CRUD.\n\n",
        "09_ACCOUNTING_REVIEW.md": f"## Wave 21 ({TODAY})\n\nBB-000650/651 DELETE orphans GL; BB-000654 period bypass; BB-000655 alloc date; BB-000664 FY close plug; BB-000682 pay run delete.\n\n",
        "05_DATABASE_REVIEW.md": f"## Wave 21 ({TODAY})\n\nBB-000667 serial unique too wide; BB-000660 opening stock ignores batch.\n\n",
        "11_API_REVIEW.md": f"## Wave 21 ({TODAY})\n\nNo CompanyGstin API (BB-000674); no WA connection API (BB-000678); AA unguarded (BB-000680).\n\n",
        "10_BUSINESS_LOGIC_REVIEW.md": f"## Wave 21 ({TODAY})\n\nBB-000657 price lists FE-only; BB-000659 SO/challan WH; BB-000681 BOM status ignored.\n\n",
        "03_BACKEND_REVIEW.md": f"## Wave 21 ({TODAY})\n\nMoney-doc destroy (BB-000650/651); ERP serializer tenant gap (BB-000672); payroll races (BB-000685).\n\n",
        "17_INTEGRATION_REVIEW.md": f"## Wave 21 ({TODAY})\n\nWA connection+template (BB-000678/679); AA kill-switch (BB-000680).\n\n",
        "02_ARCHITECTURE_REVIEW.md": f"## Wave 21 ({TODAY})\n\nMulti-company invite gap (BB-000673). No SaaS entitlement layer (BB-000671). No tenant DR (BB-000668).\n\n",
        "04_FRONTEND_REVIEW.md": f"## Wave 21 ({TODAY})\n\nInvite UI broken for prod (BB-000676/675/677/694). AI settings !== false (BB-000693).\n\n",
        "12_DEVOPS_REVIEW.md": f"## Wave 21 ({TODAY})\n\nNo tenant backup/restore product path (BB-000668). date.today() on UTC hosts (BB-000666).\n\n",
        "13_TESTING_REVIEW.md": f"## Wave 21 ({TODAY})\n\nMissing: DELETE receipt GL, CDNUR split, cross-tenant BOM PK, prod invite without password, concurrent pay-run complete.\n\n",
        "14_UI_UX_REVIEW.md": f"## Wave 21 ({TODAY})\n\nInvite password required vs optional helper text (BB-000676). OWNER option dead (BB-000694).\n\n",
        "15_AI_REVIEW.md": f"## Wave 21 ({TODAY})\n\nBB-000686 AP aging grand_total; BB-000687 health uses receipts; BB-000688 sales KPIs include RETURNED; BB-000692 OCR qty=1; BB-000693 AI settings ON.\n\n",
        "16_MOBILE_REVIEW.md": f"## Wave 21 ({TODAY})\n\nPrice lists bypassed on non-web clients (BB-000657). Company header race affects mobile (BB-000658).\n\n",
        "19_TECHNICAL_DEBT.md": f"## Wave 21 ({TODAY})\n\nFY close placeholder (BB-000664). Recurring/TDS/SaaS billing absent (BB-000669–671).\n\n",
        "20_REFACTORING_PLAN.md": f"## Wave 21 ({TODAY})\n\nInsert: (0h) money-doc void not delete; (0i) CompanyPrimaryKeyRelatedField on all ERP; (0j) invite consent + token UX; (0k) GSTR note classifier.\n\n",
        "KNOWN_LIMITATIONS_AND_TECH_DEBT.md": f"## Wave 21 limitations ({TODAY})\n\n| Area | Limitation |\n|------|------------|\n| Multi-company | Existing users cannot join second company |\n| Multi-branch | CompanyGstin no product CRUD |\n| Invite | Prod UI requires rejected password |\n| TDS/TCS / recurring / SaaS billing | Absent |\n| FY close | Unsafe plug JE, unwired |\n\n",
        "ARCHITECTURAL_DECISIONS.md": f"## Wave 21 ADR notes ({TODAY})\n\n**ADR-A28:** Money documents are voided, never hard-deleted. **ADR-A29:** All company-scoped FKs use CompanyPrimaryKeyRelatedField. **ADR-A30:** Invite is token+consent; passwords forbidden in prod. **ADR-A31:** GSTR note section follows original supply class (B2B/B2CL/B2CS), not party GSTIN alone.\n\n",
        "18_COMPETITOR_ANALYSIS.md": f"## Wave 21 ({TODAY})\n\nZoho/Tally allow multi-firm login and branch GSTIN CRUD in-product. BizBoard invite hard-fails existing emails (BB-000673) and has no CompanyGstin UI (BB-000674). No TDS vs Tally/Zoho.\n\n",
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

    print(f"WAVE21 OK: BB-{start:06d}..BB-{end:06d} n={len(ISSUES)} open={status.get('Open')} total={new_total}")


if __name__ == "__main__":
    main()
