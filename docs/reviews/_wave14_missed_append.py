#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wave 14 missed-findings pass: append BB-000544+ after primary Wave 14 append."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

TODAY = "2026-08-04"
OUT = Path(__file__).resolve().parent
REGISTER = OUT / "MASTER_ISSUE_REGISTER.md"
STATS = OUT / "_stats.json"
CHANGELOG = OUT / "CHANGELOG.md"
EXEC = OUT / "01_EXECUTIVE_SUMMARY.md"
ROADMAP = OUT / "REMEDIATION_ROADMAP.md"

ISSUES: list[dict] = []


def add(**kwargs):
    ISSUES.append(kwargs)


add(
    title="Production/staging can boot on SQLite when DATABASE_URL unset — no fail-fast",
    category="Configuration",
    subcategory="Database",
    severity="Critical",
    priority="P0",
    module="Config",
    feature="Boot",
    files="backend/config/settings.py DATABASES",
    problem="dj_database_url defaults to sqlite:///db.sqlite3. Fail-fast secret checks run for production/staging but nothing refuses SQLite engine. A misconfigured prod process without DATABASE_URL silently uses SQLite — data loss, no concurrency, pg_dump backups useless.",
    evidence="settings.py L150-156 default sqlite; no ImproperlyConfigured when ENGINE is sqlite and DJANGO_ENV in production/staging",
    root_cause="Local-dev convenience without production engine gate (BB-000543 Medium understated).",
    business="Catastrophic data durability failure.",
    technical="Wrong database in prod.",
    customer="Total data loss risk.",
    security="SQLite file perms weaker for multi-tenant media adjacency.",
    performance="SQLite locks under concurrent writes.",
    scalability="Cannot scale.",
    compliance="Backup script targets Postgres only.",
    risk="First bad bare-metal deploy stores pilot books in a disposable file.",
    fix_immediate="If DJANGO_ENV in (production, staging): require postgres DATABASE_URL; refuse sqlite.",
    fix_short="CI boot test: DJANGO_ENV=production without DATABASE_URL must exit non-zero.",
    fix_long="Separate settings_prod.py without sqlite import path.",
    effort="0.5d",
    tests="production env + no DATABASE_URL → ImproperlyConfigured",
    acceptance="Prod never opens SQLite.",
    status="Open",
    refs="BB-000543 escalate; Wave14 missed",
)
add(
    title="Purchase return cancel restores stock via ADJUSTMENT without batch/lot replay",
    category="Inventory",
    subcategory="Returns",
    severity="High",
    priority="P1",
    module="Purchases",
    feature="Purchase return cancel",
    files="backend/purchases/services.py cancel_return",
    problem="cancel_return posts ADJUSTMENT +qty without replaying PURCHASE_RETURN movement lots/batches (sales cancel_return was fixed to replay lots in Wave 13). Purchase cancel can restore to wrong/unbatched balances.",
    evidence="purchases/services.py cancel_return ~L578-588 ADJUSTMENT quantity=item.quantity no batch; sales cancel_return replays movements",
    root_cause="Asymmetric sales vs purchase cancel remediation.",
    business="Batch/FEFO stock wrong after cancel.",
    technical="Lot integrity break.",
    customer="Expiry/serial mismatches.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Inventory audit fail.",
    risk="Track-batch companies corrupt stock on cancel.",
    fix_immediate="Replay PURCHASE_RETURN movements like sales cancel_return.",
    fix_short="Shared ReturnCancelService.",
    fix_long="Movement reverse API.",
    effort="1d",
    tests="Batched purchase return cancel restores same lots.",
    acceptance="Cancel preserves lot identity.",
    status="Open",
    refs="BB-000394 asymmetry; Wave14 missed",
)
add(
    title="No DB statement_timeout / idle_in_transaction_session_timeout in Django OPTIONS",
    category="Database",
    subcategory="Safety",
    severity="High",
    priority="P1",
    module="Database",
    feature="Postgres",
    files="backend/config/settings.py DATABASES",
    problem="Long queries or leaked transactions can exhaust pool; no statement_timeout in OPTIONS.",
    evidence="DATABASES config only dj_database_url + conn_max_age",
    root_cause="Default Django PG options.",
    business="Outage from one heavy report.",
    technical="Pool starvation.",
    customer="API timeouts cascading.",
    security="N/A",
    performance="High impact under abuse.",
    scalability="Poor.",
    compliance="N/A",
    risk="Festival GSTR export kills API workers.",
    fix_immediate="Set statement_timeout and idle_in_transaction_session_timeout via OPTIONS.",
    fix_short="Per-route timeouts for heavy_reports.",
    fix_long="PgBouncer + kill switches.",
    effort="0.5d",
    tests="SHOW statement_timeout on connection in prod settings test.",
    acceptance="Prod has statement_timeout.",
    status="Open",
    refs="Wave14 missed",
)
add(
    title="CookieJWTAuthentication + Authorization JWT dual stack increases confusion and test gaps",
    category="Security",
    subcategory="Auth",
    severity="Medium",
    priority="P2",
    module="Accounts",
    feature="JWT",
    files="backend/config/settings.py REST_FRAMEWORK DEFAULT_AUTHENTICATION_CLASSES",
    problem="Both CookieJWTAuthentication and JWTAuthentication enabled — clients may still send Bearer tokens; XSS exfil of Bearer remains viable if any client stores tokens.",
    evidence="DEFAULT_AUTHENTICATION_CLASSES Cookie + JWTAuthentication",
    root_cause="Migration dual-run.",
    business="Inconsistent session security posture.",
    technical="Two auth paths.",
    customer="Odd 401s across clients.",
    security="Bearer still valid if stolen from non-cookie clients.",
    performance="N/A",
    scalability="N/A",
    compliance="N/A",
    risk="Docs/SDKs encourage Bearer forever.",
    fix_immediate="Disable JWTAuthentication header path when DJANGO_ENV in production/staging.",
    fix_short="Deprecation warning on Bearer.",
    fix_long="Cookie-only everywhere except service accounts.",
    effort="1d",
    tests="Prod rejects Authorization Bearer access tokens.",
    acceptance="Cookie-only access auth in prod.",
    status="Open",
    refs="Wave14 missed",
)
add(
    title="Audit Open==0 gate scripts do not execute beat float/ISO roundtrip or refund ledger invariant",
    category="Process",
    subcategory="Gates",
    severity="High",
    priority="P1",
    module="Docs",
    feature="Assert gates",
    files="docs/reviews/_wave13_assert_gates.py",
    problem="String presence gates missed BB-000456/457 class failures (ISO vs float heartbeat; phantom refund advances). Need property/semantic gates.",
    evidence="_wave13_assert_gates.py checks or True absence, not ISO parse compatibility with task writer",
    root_cause="Syntactic not semantic gates.",
    business="False green releases.",
    technical="Process bug.",
    customer="Bad money paths ship.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="N/A",
    risk="Wave 15 repeats false Open==0.",
    fix_immediate="Add semantic probes to assert_gates for heartbeat + refund ledger.",
    fix_short="pytest -m residual_launch required in CI.",
    fix_long="Separate launch_approved flag from checklist_closed.",
    effort="1d",
    tests="Gate fails on current tree for beat mismatch.",
    acceptance="Gates catch BB-000456 class bugs before Open==0.",
    status="Open",
    refs="BB-000461; Wave14 missed",
)
add(
    title="Purchase return cancel does not reverse inventory GL from auto purchase CN path on stock-only adjust",
    category="Accounting",
    subcategory="Purchase returns",
    severity="Medium",
    priority="P2",
    module="Purchases",
    feature="Return cancel books",
    files="backend/purchases/services.py cancel_return; accounting post_note",
    problem="Cancel cancels linked CN (GL reverse via note cancel) but stock restore uses ADJUSTMENT without unit_cost — valuation/GL inventory layers can drift vs CN taxable base after cancel cycles.",
    evidence="cancel_return ADJUSTMENT without unit_cost; CN cancel reverses note journal",
    root_cause="Stock cancel path not costed.",
    business="Inventory value drift after cancel.",
    technical="Movement cost missing.",
    customer="Stock valuation jumps.",
    security="N/A",
    performance="N/A",
    scalability="N/A",
    compliance="Books vs stock.",
    risk="Repeated return/cancel cycles widen variance.",
    fix_immediate="Cost ADJUSTMENT from original PURCHASE_RETURN unit_cost; assert BooksHealth.",
    fix_short="Forbid cancel after period close.",
    fix_long="Reversible movement pairs.",
    effort="1d",
    tests="Return+cancel → inventory GL and qty match baseline.",
    acceptance="Cancel is value-neutral.",
    status="Open",
    refs="Wave14 missed",
)


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
| **Affected APIs** | See related endpoints |
| **Affected Database Tables** | See models |
| **Status** | {data['status']} |
| **Owner** | Unassigned |
| **Review Date** | {TODAY} |
| **Estimated Effort** | {data['effort']} |
| **Breaking Change** | Possibly |
| **Regression Risk** | Medium |
| **Dependencies** | See Cross References |
| **Cross References** | {data['refs']} |
| **References** | Wave 14 missed-findings pass |

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
2. Execute related flow.
3. Observe vs acceptance criteria.

### Recommended Fix
{data['fix_immediate']}

### Immediate Fix
{data['fix_immediate']}

### Short-term Fix
{data['fix_short']}

### Long-term Refactor
{data['fix_long']}

### Alternative Solutions
Signed GO_NO_GO waiver only if non-P0.

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


def main():
    prior = json.loads(STATS.read_text(encoding="utf-8"))
    start = prior["total"] + 1
    end = start + len(ISSUES) - 1

    reg = REGISTER.read_text(encoding="utf-8")
    if f"BB-{start:06d}" in reg:
        raise SystemExit(f"BB-{start:06d} already present")

    blocks = []
    meta = []
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
                "status": data["status"],
            }
        )

    sev = Counter(m["severity"] for m in meta)
    pri = Counter(m["priority"] for m in meta)
    cat = Counter(m["category"] for m in meta)
    mod = Counter(m["module"] for m in meta)

    status = dict(prior.get("status") or {})
    # normalize deferred key
    for k in list(status.keys()):
        if "Deferred" in k and "roadmap" in k.replace("\u2014", "—"):
            val = status.pop(k)
            status["Deferred — roadmap"] = val
            break
    status["Open"] = status.get("Open", 0) + len(ISSUES)
    severity = merge_count(prior.get("severity"), sev)
    priority = merge_count(prior.get("priority"), pri)
    category = merge_count(prior.get("category"), cat)
    module = merge_count(prior.get("module"), mod)
    new_total = prior["total"] + len(ISSUES)

    note = f"""
## Wave 14 missed-findings ({TODAY})

Appended **{len(ISSUES)}** issues `BB-{start:06d}` … `BB-{end:06d}` (SQLite prod gate, purchase return cancel lots, statement_timeout, dual JWT auth, semantic gates, cancel valuation).

"""
    if "Wave 14 missed-findings" not in reg:
        reg = reg.replace("## Wave 14 re-audit", note + "## Wave 14 re-audit", 1)

    reg = re.sub(
        r"(\| \*\*Total issues\*\* \| )\d+( \|)",
        rf"\g<1>{new_total}\2",
        reg,
        count=1,
    )
    for label in ("Critical", "High", "Medium", "Low"):
        reg = re.sub(
            rf"(\| {label} \| )\d+( \|)",
            rf"\g<1>{severity.get(label, 0)}\2",
            reg,
            count=1,
        )
    for label in ("P0", "P1", "P2", "P3"):
        reg = re.sub(
            rf"(\| {label} \| )\d+( \|)",
            rf"\g<1>{priority.get(label, 0)}\2",
            reg,
            count=1,
        )
    if re.search(r"\| Open \| \d+ \|", reg):
        reg = re.sub(
            r"(\| Open \| )\d+( \|)",
            rf"\g<1>{status['Open']}\2",
            reg,
            count=1,
        )
    else:
        reg = reg.replace(
            "### By Status\n\n| Status | Count |\n|--------|------:|\n",
            "### By Status\n\n| Status | Count |\n|--------|------:|\n| Open | "
            + str(status["Open"])
            + " |\n",
            1,
        )

    REGISTER.write_text(reg.rstrip() + "\n\n" + "".join(blocks), encoding="utf-8")

    stats = {
        **prior,
        "total": new_total,
        "open_count": status["Open"],
        "severity": severity,
        "priority": priority,
        "category": category,
        "module": module,
        "status": status,
        "wave14_missed_new": len(ISSUES),
        "wave14_missed_start": f"BB-{start:06d}",
        "wave14_missed_end": f"BB-{end:06d}",
        "issues": (prior.get("issues") or []) + meta,
    }
    STATS.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    cl_block = f"""## {TODAY} — Wave 14 missed-findings pass

Appended **{len(ISSUES)}** issues `BB-{start:06d}` … `BB-{end:06d}` after Wave 14 primary append.

Highlights: SQLite production fail-open (Critical), purchase return cancel lot asymmetry, missing statement_timeout, dual JWT auth stack, semantic gate gap, cancel valuation drift.

Register total: **{new_total}**. Open: **{status['Open']}**. Production Readiness **3.3 / 10**.

---

"""
    cl = CHANGELOG.read_text(encoding="utf-8")
    if "Wave 14 missed-findings pass" not in cl:
        if cl.startswith("# docs/reviews"):
            parts = cl.split("\n", 2)
            CHANGELOG.write_text(
                parts[0] + "\n\n" + cl_block + (parts[2] if len(parts) > 2 else ""),
                encoding="utf-8",
            )
        else:
            CHANGELOG.write_text(cl_block + cl, encoding="utf-8")

    if EXEC.exists():
        et = EXEC.read_text(encoding="utf-8")
        et = re.sub(
            r"\*\*Latest:\*\*[^\n]*",
            f"**Latest:** Wave 14 missed-findings {TODAY} — register **{new_total}** issues. "
            f"**Open: {status['Open']}.** "
            f"Resolved {status.get('Resolved', 0)}. "
            f"Production Readiness Score **3.3 / 10**.",
            et,
            count=1,
        )
        if f"## Wave 14 missed-findings ({TODAY})" not in et:
            et = et.rstrip() + f"""

---

## Wave 14 missed-findings ({TODAY})

Additional residuals after Wave 14 primary: **BB-{start:06d}** SQLite prod fail-open; purchase return cancel lots; PG statement_timeout; dual JWT; semantic gates. Open now **{status['Open']}**. Score **3.3 / 10**.

"""
        EXEC.write_text(et, encoding="utf-8")

    if ROADMAP.exists():
        rt = ROADMAP.read_text(encoding="utf-8")
        if "Wave 14 missed" not in rt:
            ROADMAP.write_text(
                rt.rstrip()
                + f"""

---

## Wave 14 missed-findings hotfix ({TODAY})

| Focus | IDs |
|-------|-----|
| SQLite prod refuse | BB-{start:06d} |
| Purchase cancel lots | BB-{start+1:06d} |
| statement_timeout | BB-{start+2:06d} |
| Cookie-only prod auth | BB-{start+3:06d} |
| Semantic assert gates | BB-{start+4:06d} |

""",
                encoding="utf-8",
            )

    banner = (
        f"\n\n---\n\n## Wave 14 missed-findings ({TODAY})\n\n"
        f"Appended `BB-{start:06d}`…`BB-{end:06d}` ({len(ISSUES)}). "
        f"Open **{status['Open']}**. See MASTER_ISSUE_REGISTER.md.\n"
    )
    for name in [
        "09_ACCOUNTING_REVIEW.md",
        "05_DATABASE_REVIEW.md",
        "06_SECURITY_REVIEW.md",
        "12_DEVOPS_REVIEW.md",
        "21_PRODUCTION_READINESS.md",
        "KNOWN_LIMITATIONS_AND_TECH_DEBT.md",
    ]:
        path = OUT / name
        if path.exists() and f"Wave 14 missed-findings ({TODAY})" not in path.read_text(encoding="utf-8"):
            path.write_text(path.read_text(encoding="utf-8").rstrip() + banner, encoding="utf-8")

    print(f"Appended {len(ISSUES)} issues BB-{start:06d}..BB-{end:06d}")
    print(f"Total {new_total}; Open {status['Open']}; sev+ {dict(sev)}")


if __name__ == "__main__":
    main()
