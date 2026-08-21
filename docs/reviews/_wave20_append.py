#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wave 20 append BB-000639+."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from _wave20_issues import ISSUES

TODAY = "2026-08-05"
OUT = Path(__file__).resolve().parent
REGISTER = OUT / "MASTER_ISSUE_REGISTER.md"
STATS = OUT / "_stats.json"
CHANGELOG = OUT / "CHANGELOG.md"
EXEC = OUT / "01_EXECUTIVE_SUMMARY.md"
ROADMAP = OUT / "REMEDIATION_ROADMAP.md"
PROD = OUT / "21_PRODUCTION_READINESS.md"
START_ID = 639


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
| **References** | Wave 20 live-code pass; {TODAY} |

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
## Wave 20 re-audit ({TODAY})

Appended **{len(ISSUES)}** issues `BB-{start:06d}` … `BB-{end:06d}` from continued live-code verification after Wave 19 missed-findings. Prior IDs unchanged.

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
        "production_readiness": 3.4,
        "architecture": 4.5,
        "security": 3.0,
        "performance": 4.5,
        "accounting": 2.5,
        "gst": 3.1,
        "maintainability": 4.2,
        "scalability": 3.2,
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
        "wave20": {
            "date": TODAY,
            "new": len(ISSUES),
            "start": f"BB-{start:06d}",
            "end": f"BB-{end:06d}",
            "severity": dict(sev),
            "scores": scores,
        },
    }
    STATS.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    cl = f"""## {TODAY} — Wave 20 live-code pass

Continued engineering audit after Wave 19 missed-findings (IRP/e-way, files, payments, notes).

- Appended **{len(ISSUES)}** issues `BB-{start:06d}` … `BB-{end:06d}` (Critical {sev.get('Critical', 0)} · High {sev.get('High', 0)} · Medium {sev.get('Medium', 0)} · Low {sev.get('Low', 0)}).
- Register total: **{new_total}**. Open: **{status.get('Open', 0)}**.
- New P0s: IRP/e-way seller GSTIN ignores stamp (BB-000639); FileAsset path escape (BB-000643); no CN IRN (BB-000647); paid invoices cannot be credited (BB-000648).

PR score revised **3.6 → 3.4**. Accounting **2.5**. Security **3.0**. GST **3.1**.

---

"""
    CHANGELOG.write_text(cl + CHANGELOG.read_text(encoding="utf-8"), encoding="utf-8")

    banner = (
        f"**Latest:** Wave 20 re-audit {TODAY} — register **{new_total}** "
        f"(`BB-000550`…`BB-{end:06d}`). **Open: {status.get('Open', 0)}.** "
        f"PR **{scores['production_readiness']} / 10**. "
        f"Waves 19+20 live-code verification.\n"
    )
    et = EXEC.read_text(encoding="utf-8")
    et = re.sub(r"\*\*Latest:\*\*[^\n]*", banner.strip(), et, count=1)
    section = f"""
---

## Wave 20 re-audit ({TODAY})

Continued live-code pass after Wave 19 missed-findings. **+{len(ISSUES)} Open** `BB-{start:06d}`–`BB-{end:06d}`.

### Additional P0 blockers

- **BB-000639** — IRP/e-Way seller GSTIN ignores `company_gstin` stamp
- **BB-000643** — FileAsset `upload_to` cross-tenant path
- **BB-000647** — Credit/debit notes cannot be IRN'd
- **BB-000648** — Paid invoices cannot receive credit notes

### Scores (supersede Wave 19 missed)

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

**CTO:** Still **NO-GO**. Do not enable e-invoice, multi-GSTIN, file uploads to shared disk, or post-payment returns until 639/643/647/648 are fixed. Books-on Complete (BB-000599) remains broken.

---
"""
    if f"Wave 20 re-audit ({TODAY})" not in et:
        et = et.rstrip() + "\n" + section
    EXEC.write_text(et + "\n", encoding="utf-8")

    prod_bit = f"""
# Production readiness (Wave 20 — {TODAY})

**Score: {scores['production_readiness']} / 10.** Open **{status.get('Open', 0)}** (`BB-000550`–`BB-{end:06d}`).

Additional hard stops: BB-000639 (IRP seller GSTIN), BB-000643 (file path), BB-000647 (CN IRN), BB-000648 (paid-invoice CN).

"""
    pb = PROD.read_text(encoding="utf-8")
    if f"Wave 20 — {TODAY}" not in pb:
        PROD.write_text(prod_bit + pb, encoding="utf-8")

    road_bit = f"""## Wave 20 hotfix ({TODAY})

| Focus | IDs |
|-------|-----|
| IRP/e-way seller stamp + CN IRN + challan distance/URP/taxonomy | BB-000639–642, BB-000647 |
| FileAsset path + store_bytes gate | BB-000643, BB-000644 |
| UTR uniqueness + number seq scan | BB-000645, BB-000646 |
| Paid-invoice CN + CN POS freeze | BB-000648, BB-000649 |

"""
    rb = ROADMAP.read_text(encoding="utf-8")
    if f"Wave 20 hotfix ({TODAY})" not in rb:
        ROADMAP.write_text(road_bit + rb, encoding="utf-8")

    blurbs = {
        "06_SECURITY_REVIEW.md": f"## Wave 20 ({TODAY})\n\nBB-000643 FileAsset path escape; BB-000644 store_bytes bypasses validation.\n\n",
        "08_GST_REVIEW.md": f"## Wave 20 ({TODAY})\n\nBB-000639 seller GSTIN stamp ignored on IRP/e-way; BB-000640–642 e-way challan/URP/taxonomy; BB-000647 no CN IRN; BB-000649 CN POS drift.\n\n",
        "09_ACCOUNTING_REVIEW.md": f"## Wave 20 ({TODAY})\n\nBB-000648 paid invoices cannot be credited; BB-000645 UTR 90-day window.\n\n",
        "05_DATABASE_REVIEW.md": f"## Wave 20 ({TODAY})\n\nBB-000646 sequence full-scan; BB-000645 missing unique(company,utr).\n\n",
        "11_API_REVIEW.md": f"## Wave 20 ({TODAY})\n\nNo CN/DN einvoice/eway actions on note viewsets (BB-000647).\n\n",
        "07_PERFORMANCE_REVIEW.md": f"## Wave 20 ({TODAY})\n\nBB-000646 `_max_existing_seq` O(n) on every document number.\n\n",
        "10_BUSINESS_LOGIC_REVIEW.md": f"## Wave 20 ({TODAY})\n\nBB-000648 outstanding-capped CNs; BB-000649 live-master POS on notes.\n\n",
        "03_BACKEND_REVIEW.md": f"## Wave 20 ({TODAY})\n\nFile ingest split-brain (BB-000643/644); document number scan (BB-000646); notes IRP gap (BB-000647).\n\n",
        "17_INTEGRATION_REVIEW.md": f"## Wave 20 ({TODAY})\n\nIRP/e-way still HO-GSTIN only (BB-000639); CN IRN absent (BB-000647).\n\n",
        "02_ARCHITECTURE_REVIEW.md": f"## Wave 20 ({TODAY})\n\nFiling identity not an aggregate — stamp unused by statutory payloads (BB-000639). Notes are not amendments of a frozen supply (BB-000649).\n\n",
        "04_FRONTEND_REVIEW.md": f"## Wave 20 ({TODAY})\n\nNo UI for e-way subSupplyType/transMode (BB-000642); no CN IRN actions.\n\n",
        "12_DEVOPS_REVIEW.md": f"## Wave 20 ({TODAY})\n\nShared MEDIA_ROOT tenant keys unsafe (BB-000643) — object storage required before multi-tenant prod.\n\n",
        "13_TESTING_REVIEW.md": f"## Wave 20 ({TODAY})\n\nMissing: paid-invoice CN, secondary-GSTIN IRP payload, challan e-way distance, path-traversal upload.\n\n",
        "14_UI_UX_REVIEW.md": f"## Wave 20 ({TODAY})\n\nReturn/refund on prepaid invoices has no successful path (BB-000648).\n\n",
        "16_MOBILE_REVIEW.md": f"## Wave 20 ({TODAY})\n\nPOS/mobile prepaid return blocked by BB-000648.\n\n",
        "19_TECHNICAL_DEBT.md": f"## Wave 20 ({TODAY})\n\nNumber allocator still defensive full-scan (BB-000646). Dual file ingest (BB-000644).\n\n",
        "20_REFACTORING_PLAN.md": f"## Wave 20 ({TODAY})\n\nInsert: (0e) seller identity helper for IRP/e-way/GSTR; (0f) note amendment engine + IRN; (0g) UUID file keys.\n\n",
        "KNOWN_LIMITATIONS_AND_TECH_DEBT.md": f"## Wave 20 limitations ({TODAY})\n\n| Area | Limitation |\n|------|------------|\n| Multi-GSTIN IRP | Stamp unused — HO GSTIN only |\n| e-Way challan | Distance hardcoded 0; taxonomy road/supply only |\n| Credit notes | No IRN; blocked when invoice paid |\n| File storage | Raw filename keys; store_bytes unvalidated |\n\n",
        "ARCHITECTURAL_DECISIONS.md": f"## Wave 20 ADR notes ({TODAY})\n\n**ADR-A25:** Filing identity = CompanyGstin row, not Company.gstin. **ADR-A26:** Credit notes amend frozen supplies (POS/tax/GSTIN snapshot). **ADR-A27:** Object keys are server-generated UUIDs; client filenames are metadata only.\n\n",
        "18_COMPETITOR_ANALYSIS.md": f"## Wave 20 ({TODAY})\n\nTallyPrime / Zoho Books / ERPNext all IRN credit notes and allow CN after receipt. BizBoard cannot (BB-000647/648). Multi-GSTIN e-way is table stakes vs Zoho/TallyPrime — BB-000639 fails that bar.\n\n",
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

    print(f"WAVE20 OK: BB-{start:06d}..BB-{end:06d} n={len(ISSUES)} open={status.get('Open')} total={new_total}")


if __name__ == "__main__":
    main()
