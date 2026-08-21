#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wave 19 independent re-audit (2026-08-05): append BB-000550+ after Wave 18 Open==0.

Never regenerates prior IDs. Append-only. IDs permanent.
Invalidates Wave 18 “Open == 0” / PR~9.0 as a commercial launch gate.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from _wave19_issues import ISSUES

TODAY = "2026-08-05"
OUT = Path(__file__).resolve().parent
REGISTER = OUT / "MASTER_ISSUE_REGISTER.md"
STATS = OUT / "_stats.json"
CHANGELOG = OUT / "CHANGELOG.md"
EXEC = OUT / "01_EXECUTIVE_SUMMARY.md"
ROADMAP = OUT / "REMEDIATION_ROADMAP.md"
PROD = OUT / "21_PRODUCTION_READINESS.md"
START_ID = 550


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
| **Status** | {data.get('status', 'Open')} |
| **Owner** | Unassigned |
| **Review Date** | {TODAY} |
| **Estimated Effort** | {data['effort']} |
| **Breaking Change** | Possibly — assess per fix |
| **Regression Risk** | Medium unless tests added |
| **Dependencies** | See Cross References |
| **Cross References** | {data['refs']} |
| **References** | Wave 19 independent re-audit; live code {TODAY} |

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
    assert ISSUES, "No issues loaded"

    start = START_ID
    end = START_ID + len(ISSUES) - 1
    blocks = []
    new_issues_meta = []
    for i, data in enumerate(ISSUES):
        n = start + i
        iid = f"BB-{n:06d}"
        data.setdefault("status", "Open")
        blocks.append(render_issue(n, data))
        new_issues_meta.append(
            {
                "id": iid,
                "title": data["title"],
                "severity": data["severity"],
                "priority": data["priority"],
                "category": data["category"],
                "module": data["module"],
                "status": data["status"],
            }
        )

    reg = REGISTER.read_text(encoding="utf-8")
    if f"BB-{start:06d}" in reg:
        raise SystemExit(f"BB-{start:06d} already present — refuse double append")

    header_note = f"""
## Wave 19 re-audit ({TODAY})

Appended **{len(ISSUES)}** new issues `BB-{start:06d}` … `BB-{end:06d}` from independent code re-verification after Wave 18 open-closure / Deferred MVP claims. Prior IDs unchanged. **Invalidates Wave 18 Open==0 and PR~9.0 as a launch gate.**

"""
    sev = Counter(x["severity"] for x in new_issues_meta)
    pri = Counter(x["priority"] for x in new_issues_meta)
    cat = Counter(x["category"] for x in new_issues_meta)
    mod = Counter(x["module"] for x in new_issues_meta)

    new_total = prior["total"] + len(ISSUES)
    status = dict(prior.get("status") or {})
    # normalize dash keys
    for k in list(status.keys()):
        if "Deferred" in k and "roadmap" in k:
            status["Deferred — roadmap"] = status.pop(k)
            break
    for k in list(status.keys()):
        if "Deferred" in k and "ops" in k:
            status["Deferred — ops owner"] = status.pop(k)
            break
    status["Open"] = status.get("Open", 0) + len(ISSUES)

    severity = merge_count(prior.get("severity"), sev)
    priority = merge_count(prior.get("priority"), pri)
    category = merge_count(prior.get("category"), cat)
    module = merge_count(prior.get("module"), mod)

    # Insert wave note after H1; patch first totals table in the existing register body.
    if reg.startswith("#"):
        nl = reg.find("\n")
        reg2 = reg[: nl + 1] + header_note + reg[nl + 1 :]
    else:
        reg2 = header_note + reg
    reg2 = re.sub(
        r"(\| \*\*Total issues\*\* \| )(\d+)( \|)",
        rf"\g<1>{new_total}\3",
        reg2,
        count=1,
    )
    for label in ("Critical", "High", "Medium", "Low"):
        reg2 = re.sub(
            rf"(\| {label} \| )(\d+)( \|)",
            rf"\g<1>{severity.get(label, 0)}\3",
            reg2,
            count=1,
        )
    for label in ("P0", "P1", "P2", "P3"):
        reg2 = re.sub(
            rf"(\| {label} \| )(\d+)( \|)",
            rf"\g<1>{priority.get(label, 0)}\3",
            reg2,
            count=1,
        )
    # Status histogram in register (By Status table)
    for label, key in [
        ("Resolved", "Resolved"),
        ("Open", "Open"),
        ("Deferred — roadmap", "Deferred — roadmap"),
        ("Deferred — ops owner", "Deferred — ops owner"),
        ("Accepted (positive)", "Accepted (positive)"),
    ]:
        if key in status:
            reg2 = re.sub(
                rf"(\| {re.escape(label)} \| )(\d+)( \|)",
                rf"\g<1>{status[key]}\3",
                reg2,
                count=1,
            )

    REGISTER.write_text(reg2 + "\n".join(blocks) + "\n", encoding="utf-8")

    stats = {
        **prior,
        "total": new_total,
        "open_count": status.get("Open", 0),
        "severity": severity,
        "priority": priority,
        "category": category,
        "module": module,
        "status": status,
        "wave19_new": len(ISSUES),
        "wave19_start": f"BB-{start:06d}",
        "wave19_end": f"BB-{end:06d}",
        "audit_date": TODAY,
        "issues": (prior.get("issues") or []) + new_issues_meta,
        "wave19": {
            "date": TODAY,
            "new": len(ISSUES),
            "start": f"BB-{start:06d}",
            "end": f"BB-{end:06d}",
            "severity": dict(sev),
            "priority": dict(pri),
            "scores": {
                "production_readiness": 4.2,
                "architecture": 4.8,
                "security": 3.8,
                "performance": 5.0,
                "accounting": 3.5,
                "gst": 4.0,
                "maintainability": 4.5,
                "scalability": 3.5,
                "testing": 5.2,
            },
        },
    }
    STATS.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    cl_block = f"""## {TODAY} — Wave 19 independent re-audit

Re-ran complete engineering audit against live `backend/` + `web/` + `mobile/` + compose/CI/nginx **after** Wave 18 claimed Open==0 and engineering scores ~9.0.

### Outcomes

- Appended **{len(ISSUES)}** issues `BB-{start:06d}` … `BB-{end:06d}` (
  Critical {sev.get('Critical', 0)} ·
  High {sev.get('High', 0)} ·
  Medium {sev.get('Medium', 0)} ·
  Low {sev.get('Low', 0)}).
- Register total: **{new_total}**.
- Status: Open **{status.get('Open', 0)}** · prior Resolved/Deferred/Accepted retained.
- Invalidated Wave 18 “Open == 0” / PR~9.0 as a commercial launch gate (see BB-000558).
- Production Readiness Score revised **~9.0 → 4.2**.

### Highest new Criticals

- BB-000550 ALLOWED_HOSTS `*` treated as local (DEBUG/ENV bypass)
- BB-000551 / 552 RLS SET LOCAL no-op + superuser bypass (RLS theater)
- BB-000553 VIEWER can mutate manufacturing/payroll/CRM (cash+stock)
- BB-000554 / 555 WO uses SALE/PURCHASE movements + list-price FG costing
- BB-000556 Multi-GSTIN stamps dumped into one GSTR keyed off primary GSTIN
- BB-000557 OCR/LLM defaults unknown gst_rate to 18%
- BB-000558 Wave 18 Open==0 / score process invalidation

### Passes re-executed

Repository structure through missed-findings (Wave 19). Scripts: `_wave19_issues.py` + `_wave19_reaudit_append.py` + `_wave19_update_docs.py`.

---

"""
    cl = CHANGELOG.read_text(encoding="utf-8") if CHANGELOG.exists() else ""
    if "Wave 19 independent re-audit" not in cl:
        CHANGELOG.write_text(cl_block + cl, encoding="utf-8")

    print(f"WAVE19 APPEND OK: BB-{start:06d}..BB-{end:06d} ({len(ISSUES)} issues)")
    print("severity", dict(sev))
    print("open", status.get("Open"))
    print("total", new_total)


if __name__ == "__main__":
    main()
