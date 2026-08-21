#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wave 19 missed-findings append BB-000599+ (subagent residual pass)."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from _wave19_missed_issues import ISSUES

TODAY = "2026-08-05"
OUT = Path(__file__).resolve().parent
REGISTER = OUT / "MASTER_ISSUE_REGISTER.md"
STATS = OUT / "_stats.json"
CHANGELOG = OUT / "CHANGELOG.md"
EXEC = OUT / "01_EXECUTIVE_SUMMARY.md"
ROADMAP = OUT / "REMEDIATION_ROADMAP.md"
PROD = OUT / "21_PRODUCTION_READINESS.md"
START_ID = 599


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
| **References** | Wave 19 missed-findings; live code {TODAY} |

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
## Wave 19 missed-findings ({TODAY})

Appended **{len(ISSUES)}** issues `BB-{start:06d}` … `BB-{end:06d}` from independent GST/accounting/inventory, FE/DevOps/API, and auth/RBAC residual passes after Wave 19 primary append. Prior IDs unchanged.

"""
    sev, pri, cat, mod = (
        Counter(x["severity"] for x in meta),
        Counter(x["priority"] for x in meta),
        Counter(x["category"] for x in meta),
        Counter(x["module"] for x in meta),
    )
    new_total = prior["total"] + len(ISSUES)
    status = dict(prior.get("status") or {})
    for k in list(status):
        if "roadmap" in k:
            status["Deferred — roadmap"] = status.pop(k)
            break
    for k in list(status):
        if "ops" in k:
            status["Deferred — ops owner"] = status.pop(k)
            break
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
        "production_readiness": 3.6,
        "architecture": 4.6,
        "security": 3.2,
        "performance": 4.8,
        "accounting": 2.8,
        "gst": 3.4,
        "maintainability": 4.3,
        "scalability": 3.4,
        "testing": 4.8,
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
        "wave19_missed": {
            "date": TODAY,
            "new": len(ISSUES),
            "start": f"BB-{start:06d}",
            "end": f"BB-{end:06d}",
            "severity": dict(sev),
            "scores": scores,
        },
    }
    STATS.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    cl = f"""## {TODAY} — Wave 19 missed-findings (subagent residuals)

Independent GST/accounting, FE/DevOps/API, and auth/RBAC passes after Wave 19 primary.

- Appended **{len(ISSUES)}** issues `BB-{start:06d}` … `BB-{end:06d}` (Critical {sev.get('Critical', 0)} · High {sev.get('High', 0)} · Medium {sev.get('Medium', 0)} · Low {sev.get('Low', 0)}).
- Register total: **{new_total}**. Open: **{status.get('Open', 0)}**.
- New P0s include: sales GL `cgst_amount` mismatch, cess not in GL, FIFO cancel/transfer/COGS peel, prod cookie+CSRF/SPA break, CSP vs MUI, AA mock ingest, `is_gst_registered` on wrong model, SOFT_CLOSED no-op, journal reverse drops party FKs, idempotency TOCTOU, RLS middleware-before-JWT.

PR score revised **4.2 → 3.6**. Accounting **2.8**. Security **3.2**. GST **3.4**.

---

"""
    CHANGELOG.write_text(cl + CHANGELOG.read_text(encoding="utf-8"), encoding="utf-8")

    banner = (
        f"**Latest:** Wave 19 missed-findings {TODAY} — register **{new_total}** "
        f"(`BB-000550`…`BB-{end:06d}`). **Open: {status.get('Open', 0)}.** "
        f"PR **{scores['production_readiness']} / 10**. "
        f"Primary Wave 19 + residual GST/auth/FE passes.\n"
    )
    et = EXEC.read_text(encoding="utf-8")
    et = re.sub(r"\*\*Latest:\*\*[^\n]*", banner.strip(), et, count=1)
    section = f"""
---

## Wave 19 missed-findings ({TODAY})

Residual passes ([GST/accounting/inventory](2c83fedd-22a1-4c00-bd37-63ab48d115eb), [FE/DevOps/API](0dfd11e9-f1ea-4a2f-8e0e-460cba23f845), [auth/RBAC](3d330ff7-b3bb-422c-b983-8b660178d793)) after primary Wave 19. **+{len(ISSUES)} Open** `{f'BB-{start:06d}'}`–`{f'BB-{end:06d}'}`.

### Additional P0 blockers

- **BB-000599** — Sales GL reads `cgst_amount` (Complete fails when books on)
- **BB-000600** — Cess never in GL / IRP lines
- **BB-000601** — FIFO cancel/transfer/COGS peel broken
- **BB-000602 / 603** — Prod cookie JWT + CSRF/SPA + Bearer still live
- **BB-000604** — RLS middleware before JWT auth
- **BB-000605** — nginx CSP breaks MUI + Google Fonts
- **BB-000606** — AA ingest auto-mocks bank txns
- **BB-000607** — `is_gst_registered` on wrong model
- **BB-000608** — SOFT_CLOSED is a no-op
- **BB-000609** — Journal reverse drops party FKs
- **BB-000610** — Idempotency-Key TOCTOU duplicates
- **BB-000611–614** — Inclusive cess, flag refresh, money-list truncate, ITC default CLAIMABLE

### Scores (supersede Wave 19 primary)

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

**CTO:** Still **NO-GO**. Books-on billing is broken (599). Production auth cookie mode is unshippable (602). Do not enable FIFO, AA, cess-heavy SKUs, or RLS.

---
"""
    if f"Wave 19 missed-findings ({TODAY})" not in et:
        et = et.rstrip() + "\n" + section
    EXEC.write_text(et + "\n", encoding="utf-8")

    prod_bit = f"""
# Production readiness (Wave 19 missed — {TODAY})

**Score: {scores['production_readiness']} / 10.** Open **{status.get('Open', 0)}** (`BB-000550`–`BB-{end:06d}`).

Additional hard stops: BB-000599 (books-on Complete), BB-000602 (prod SPA auth), BB-000605 (CSP), BB-000606 (AA mocks), BB-000601 (FIFO).

"""
    pb = PROD.read_text(encoding="utf-8")
    if f"Wave 19 missed — {TODAY}" not in pb:
        PROD.write_text(prod_bit + pb, encoding="utf-8")

    road_bit = f"""## Wave 19 missed-findings hotfix ({TODAY})

| Focus | IDs |
|-------|-----|
| Books-on Complete + cess GL + reverse FKs | BB-000599, BB-000600, BB-000609 |
| FIFO cancel/transfer/COGS | BB-000601 |
| Prod cookie+CSRF+Bearer | BB-000602, BB-000603 |
| RLS middleware-after-auth | BB-000604 |
| CSP / AA mocks / is_gst_registered / SOFT_CLOSED | BB-000605–608 |
| Idempotency durable | BB-000610 |
| ITC / inclusive cess / money lists / flags | BB-000611–614 |

"""
    rb = ROADMAP.read_text(encoding="utf-8")
    if f"Wave 19 missed-findings hotfix ({TODAY})" not in rb:
        ROADMAP.write_text(road_bit + rb, encoding="utf-8")

    # Touch key review docs
    blurbs = {
        "06_SECURITY_REVIEW.md": f"## Wave 19 missed ({TODAY})\n\nBB-000602/603 prod cookie+CSRF/Bearer; BB-000604 RLS order; BB-000616/617 invite+login tokens; BB-000618 read ACL; BB-000625 CORS; BB-000626 health; BB-000631/632 ClamAV/Cashfree.\n\n",
        "08_GST_REVIEW.md": f"## Wave 19 missed ({TODAY})\n\nBB-000607 is_gst_registered; BB-000608 SOFT_CLOSED; BB-000611 inclusive cess; BB-000614 ITC; BB-000619–624 returns/RCM/GSTR-1/SEZ/CMP/IRP; BB-000637 2B match; BB-000638 POS fallback.\n\n",
        "09_ACCOUNTING_REVIEW.md": f"## Wave 19 missed ({TODAY})\n\nBB-000599 cgst_amount; BB-000600 cess GL; BB-000609 reverse FKs; BB-000606 AA mocks.\n\n",
        "05_DATABASE_REVIEW.md": f"## Wave 19 missed ({TODAY})\n\nBB-000601 FIFO layer cancel/transfer; BB-000604 RLS auth order.\n\n",
        "04_FRONTEND_REVIEW.md": f"## Wave 19 missed ({TODAY})\n\nBB-000605 CSP; BB-000612 flags; BB-000613 money truncate; BB-000630 PhasePages; BB-000635 virtualization theater.\n\n",
        "11_API_REVIEW.md": f"## Wave 19 missed ({TODAY})\n\nBB-000610 durable idempotency required.\n\n",
        "12_DEVOPS_REVIEW.md": f"## Wave 19 missed ({TODAY})\n\nBB-000605 CSP; BB-000626 health disclosure; BB-000636 beat duplicate snapshots.\n\n",
        "15_AI_REVIEW.md": f"## Wave 19 missed ({TODAY})\n\nBB-000627 tax regex; BB-000629 OCR confidence dropped.\n\n",
        "17_INTEGRATION_REVIEW.md": f"## Wave 19 missed ({TODAY})\n\nBB-000606 AA mocks; BB-000624 Live IRP stub; BB-000628 Tally dump.\n\n",
        "03_BACKEND_REVIEW.md": f"## Wave 19 missed ({TODAY})\n\nBB-000599–601, BB-000607–610 posting/FIFO/model/idempotency residuals.\n\n",
        "07_PERFORMANCE_REVIEW.md": f"## Wave 19 missed ({TODAY})\n\nBB-000613 silent first-page money lists; BB-000635 virtualization theater.\n\n",
        "10_BUSINESS_LOGIC_REVIEW.md": f"## Wave 19 missed ({TODAY})\n\nBB-000608 period close; BB-000615 serial SM; BB-000619 return CN cess.\n\n",
        "13_TESTING_REVIEW.md": f"## Wave 19 missed ({TODAY})\n\nProd DEBUG=0 auth e2e missing (BB-000602); books-on complete untested (BB-000599); FIFO cancel untested (BB-000601).\n\n",
        "16_MOBILE_REVIEW.md": f"## Wave 19 missed ({TODAY})\n\nNo new mobile IDs; CSP (BB-000605) also breaks installed PWA/WebView.\n\n",
        "14_UI_UX_REVIEW.md": f"## Wave 19 missed ({TODAY})\n\nBB-000605 unstyled MUI; BB-000612 flags invisible until reload; BB-000629 OCR confidence UX.\n\n",
        "02_ARCHITECTURE_REVIEW.md": f"## Wave 19 missed ({TODAY})\n\nAuth dual-stack + RLS wrong layer (BB-000602–604). Dual ledger reverse FK gap (BB-000609). FIFO not actually perpetual (BB-000601).\n\n",
        "19_TECHNICAL_DEBT.md": f"## Wave 19 missed ({TODAY})\n\nPhasePages still the accounting app (BB-000630). Idempotency cache (BB-000610). Dead CORS env (BB-000625).\n\n",
        "20_REFACTORING_PLAN.md": f"## Wave 19 missed ({TODAY})\n\nInsert before ERP work: (0) prod auth+CSRF, (0b) post_sales_invoice field names+cess CoA, (0c) FIFO cancel/COGS peel, (0d) durable idempotency.\n\n",
        "21_PRODUCTION_READINESS.md": "",
        "KNOWN_LIMITATIONS_AND_TECH_DEBT.md": f"## Wave 19 missed limitations ({TODAY})\n\n| Area | Limitation |\n|------|------------|\n| accounting_enabled | GST Complete broken (BB-000599) until field-name fix |\n| Cess | Documents only — not GL/IRP lines/inclusive/RCM |\n| FIFO | Cancel/transfer/COGS peel unsafe |\n| Prod auth | Cookie mode unshippable without CSRF+SPA change |\n| AA | Empty ingest injects mock bank data |\n| SOFT_CLOSED | Does not block or warn on Complete |\n\n",
        "ARCHITECTURAL_DECISIONS.md": f"## Wave 19 missed ADR notes ({TODAY})\n\n**ADR-A22 (recommended):** Durable idempotency table, not cache. **ADR-A23:** CSRF bootstrap is part of cookie-auth or cookie-auth is forbidden. **ADR-A24:** `accounting_enabled` must not break Complete — posting guards tested with real lines.\n\n",
    }
    for name, section in blurbs.items():
        if not section:
            continue
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

    print(f"WAVE19 MISSED OK: BB-{start:06d}..BB-{end:06d} n={len(ISSUES)} open={status.get('Open')} total={new_total}")


if __name__ == "__main__":
    main()
