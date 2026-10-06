"""Make the workbook the single source of truth for 2026-10-05.

usage: python qos/evidence/apply_truth.py <workbook.xlsx> <junit.xml>

Reads qos/evidence/plan_status/out_*.json (what the code actually implements, per plan item, with real test ids),
scores those test ids against the JUnit file, and writes the result into:
  * Implementation plan (stage cells, evidence, blocked reason, PR column)
  * Task Register (Work status, Verification result, Last verified, Verified by, Test case ID, Code pointer, Notes)
  * MVP scope after review / P0 gap decisions (current status columns)
  * Code review 2026-10-05 (findings and their outcome)
  * Truth snapshot (what is built, tested, signed off and open)
Nothing is marked Done unless a human has signed Review; agent review is recorded as In progress.
"""
import glob
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from review_findings_2026_10_05 import F as FINDINGS  # noqa: E402

TODAY = date(2026, 10, 5)
BY = "pytest full suite on SQLite (agent run 2026-10-05); human review pending"
wb = openpyxl.load_workbook(sys.argv[1])
junit = sys.argv[2]

# ---------------- test results
results = {}  # "tests/x.py::[Class::]name" -> pass|fail|skip|xfail
for case in ET.parse(junit).getroot().iter("testcase"):
    parts = case.get("classname", "").split(".")
    i = max((k for k, p in enumerate(parts) if p.startswith("test_")), default=None)
    if i is None:
        continue
    key = "::".join(["/".join(parts[: i + 1]) + ".py", *parts[i + 1:], case.get("name", "").split("[")[0]])
    sk = case.find("skipped")
    if case.find("failure") is not None or case.find("error") is not None:
        o = "fail"
    elif sk is not None:
        o = "xfail" if sk.get("type") == "pytest.xfail" else "skip"
    else:
        o = "pass"
    prev = results.get(key)
    results[key] = "fail" if "fail" in (o, prev) else (prev if prev == o else (o if prev is None else "pass" if "pass" in (o, prev) else o))
by_tail = defaultdict(list)
for k in results:
    by_tail[(k.split("::")[0], k.split("::")[-1])].append(k)


def norm(tid):
    import re
    return re.sub(r"\s*::\s*", "::", tid.strip())


def score(tid):
    tid = norm(tid)
    t = tid.replace("backend/", "", 1) if tid.startswith("backend/") else tid
    if t in results:
        return results[t]
    parts = t.split("::")
    if len(parts) >= 2 and (parts[0], parts[-1]) in by_tail:
        outs = {results[k] for k in by_tail[(parts[0], parts[-1])]}
        return "fail" if "fail" in outs else "pass" if "pass" in outs else sorted(outs)[0]
    if len(parts) == 1 and t.endswith(".py"):  # whole file
        outs = {v for k, v in results.items() if k.startswith(t + "::")}
        if outs:
            return "fail" if "fail" in outs else "pass" if "pass" in outs else sorted(outs)[0]
    return None


status = []
for f in sorted(glob.glob(str(HERE / "plan_status" / "out_*.json"))):
    status.extend(json.load(open(f, encoding="utf-8")))
st = {s["wi_id"]: s for s in status}

hdr_font, hdr_fill = Font(name="Calibri", size=11, bold=True, color="FFFFFFFF"), PatternFill("solid", fgColor="FF1F497D")
body = Font(name="Calibri", size=10)
thin = Side(style="thin", color="FFBFBFBF")
box = Border(left=thin, right=thin, top=thin, bottom=thin)
wrap = Alignment(wrap_text=True, vertical="top")

# ---------------- Implementation plan
plan = wb["Implementation plan"]
ph = {c.value: c.column for c in plan[4]}
tr = wb["Task Register"]
th = {c.value: c.column for c in tr[1]}
rows_by_task = {tr.cell(r, 1).value: r for r in range(2, tr.max_row + 1)}
counts = Counter()
plan_result = {}
for r in range(5, plan.max_row + 1):
    wid = plan.cell(r, 1).value
    if not wid or wid not in st:
        continue
    s = st[wid]
    kind = plan.cell(r, ph["Kind"]).value
    tests = [norm(x) for x in (s.get("test_ids") or [])]
    scored = [(t, score(t)) for t in tests]
    ran = [o for _, o in scored if o]
    all_pass = bool(ran) and all(o == "pass" for o in ran) and len(ran) == len(scored)
    any_fail = any(o == "fail" for o in ran)
    impl = s["implementation"]
    counts[impl] += 1
    cells = {k: plan.cell(r, ph[k]) for k in ("Design", "Build", "Tests", "Review", "Register sync")}
    def put(k, v):
        if cells[k].value != "N/A":
            cells[k].value = v
    if impl == "Built":
        put("Design", "Done"); put("Build", "Done")
        put("Tests", "Done" if (all_pass or kind in ("decision", "external", "gate")) else ("Blocked" if any_fail else "In progress"))
        put("Review", "In progress")  # agent review done twice; a human has not signed
        reg = plan.cell(r, ph["Register task"]).value
        put("Register sync", "Done" if (reg and all_pass) else "Not started")
    elif impl == "Partial":
        put("Design", "Done"); put("Build", "In progress")
        put("Tests", "In progress" if tests else "Not started")
        put("Review", "Not started"); put("Register sync", "Not started")
    else:
        for k in cells:
            put(k, "Not started")
    ev = []
    if tests:
        ev.append("Tests: " + "; ".join(f"{t.replace('backend/', '')} [{o or 'not in run'}]" for t, o in scored))
    if s.get("code_refs"):
        ev.append("Code: " + "; ".join(s["code_refs"]))
    ev.append("Run: pytest on SQLite 2026-10-05 (Postgres-only tests skipped)")
    plan.cell(r, ph["Evidence (test ids, run id)"]).value = " | ".join(ev)
    plan.cell(r, ph["PR / branch"]).value = "uncommitted working tree"
    plan.cell(r, ph["Blocked reason"]).value = (
        ("Gap: " + s["gaps"]) if impl != "Built" and s.get("gaps")
        else ("Any failing test must be fixed first" if any_fail else
              ("Agent review done; human sign-off pending" if impl == "Built" and kind not in ("decision", "external") else
               ("Needs a person's decision or sign-off" if impl != "Built" else "")))
    )
    for k in ("Evidence (test ids, run id)", "PR / branch", "Blocked reason"):
        plan.cell(r, ph[k]).alignment = wrap
    plan_result[wid] = (impl, all_pass, any_fail, scored, s)

# ---------------- Task Register
changed = Counter()
for wid, (impl, all_pass, any_fail, scored, s) in plan_result.items():
    task = s.get("register_task")
    r = rows_by_task.get(task)
    if not r:
        continue
    cur = tr.cell(r, th["Work status"]).value
    note = f"Truth 2026-10-05 ({wid}): {impl}. " + (s.get("gaps") or "") + " " + (s.get("note") or "")
    if impl == "Built" and scored:
        if any_fail:
            tr.cell(r, th["Verification result"]).value = "Fail"
        elif all_pass:
            tr.cell(r, th["Verification result"]).value = "Pass"
            if cur in (None, "", "Gap", "Claimed - unverified", "Built - unverified", "Built - partial"):
                tr.cell(r, th["Work status"]).value = "Built - tested"
        else:
            if cur in (None, "", "Gap", "Claimed - unverified"):
                tr.cell(r, th["Work status"]).value = "Built - unverified"
    elif impl == "Partial":
        if cur in (None, "", "Gap", "Claimed - unverified", "Built - unverified"):
            tr.cell(r, th["Work status"]).value = "Built - partial"
        if scored and not any_fail:
            tr.cell(r, th["Verification result"]).value = "Partial"
        elif any_fail:
            tr.cell(r, th["Verification result"]).value = "Fail"
    elif impl == "Not built":
        if cur in (None, ""):
            tr.cell(r, th["Work status"]).value = "Gap"
    if scored:
        tr.cell(r, th["Last verified"]).value = TODAY
        tr.cell(r, th["Verified by"]).value = BY
        existing = [x.strip() for x in str(tr.cell(r, th["Test case ID"]).value or "").split(";") if x.strip()]
        for t, _ in scored:
            if t not in existing:
                existing.append(t)
        tr.cell(r, th["Test case ID"]).value = "; ".join(existing)
    if s.get("code_refs"):
        ptr = str(tr.cell(r, th["Code pointer"]).value or "")
        add = "; ".join(c for c in s["code_refs"] if c not in ptr)
        if add:
            tr.cell(r, th["Code pointer"]).value = (ptr + "; " if ptr else "") + add
    old = tr.cell(r, th["Notes"]).value
    tr.cell(r, th["Notes"]).value = (str(old) + " | " if old else "") + note.strip()
    changed[impl] += 1

# ---------------- MVP scope sheet and P0 sheet: current status
def current(task):
    for wid, (impl, ap, af, sc, s) in plan_result.items():
        if s.get("register_task") == task:
            return wid, impl, ap, af, s
    return None


for name, task_col, anchor_col in (("MVP scope after review", 1, 11), ("P0 gap decisions", 1, 11)):
    ws = wb[name]
    hrow = 3 if name == "MVP scope after review" else 4
    col = ws.max_column + 1
    c = ws.cell(hrow, col, "Status now (2026-10-05)")
    c.font, c.fill, c.alignment, c.border = hdr_font, hdr_fill, Alignment(wrap_text=True, vertical="center"), box
    ws.column_dimensions[L(col)].width = 60
    for r in range(hrow + 1, ws.max_row + 1):
        task = ws.cell(r, task_col).value
        if not task:
            continue
        cur = current(task)
        if cur:
            wid, impl, ap, af, s = cur
            txt = f"{wid}: {impl}" + (" and tests pass" if impl == "Built" and ap else "") + (" - TESTS FAILING" if af else "") \
                  + (f". Missing: {s['gaps']}" if s.get("gaps") else "") + ". Human review pending."
        else:
            txt = "No plan item maps to this task."
        cell = ws.cell(r, col, txt)
        cell.font, cell.alignment, cell.border = body, wrap, box

# ---------------- Code review sheet
name = "Code review 2026-10-05"
if name in wb.sheetnames:
    del wb[name]
cr = wb.create_sheet(name, wb.sheetnames.index("Plan change log") + 1)
cr.sheet_view.showGridLines = False
cr["A1"] = "Code review 2026-10-05"
cr["A1"].font = Font(name="Calibri", size=16, bold=True)
cr["A2"] = ("Two read-only review rounds (eight reviewers each) over the uncommitted tree, then fixes. Fixed = changed and verified; "
            "Reverted = tried, an existing pinned test showed the product wants the opposite; Open = not changed, reason given.")
cr["A2"].font = Font(name="Calibri", size=10, italic=True)
cr["A2"].alignment = wrap
cr.merge_cells("A2:F2")
cr.row_dimensions[2].height = 30
for c, (h, w) in enumerate([("#", 5), ("Area", 12), ("Severity", 10), ("Finding", 70), ("Outcome", 16), ("How or why", 70)], 1):
    cell = cr.cell(4, c, h)
    cell.font, cell.fill, cell.border, cell.alignment = hdr_font, hdr_fill, box, Alignment(wrap_text=True, vertical="center")
    cr.column_dimensions[L(c)].width = w
for n, (area, sev, finding, outcome, how) in enumerate(FINDINGS, 1):
    for c, v in enumerate([n, area, sev, finding, outcome, how], 1):
        cell = cr.cell(4 + n, c, v)
        cell.font, cell.alignment, cell.border = body, wrap, box
    cr.row_dimensions[4 + n].height = 44
last = 4 + len(FINDINGS)
cr.freeze_panes = "A5"
cr.auto_filter.ref = f"A4:F{last}"
from openpyxl.formatting.rule import CellIsRule
for txt, color in (("Open", "FFFFE0B2"), ("Reverted", "FFD9D9D9"), ("Fixed", "FFC6EFCE")):
    cr.conditional_formatting.add(f"E5:E{last}", CellIsRule(operator="equal", formula=[f'"{txt}"'], fill=PatternFill("solid", bgColor=color, fgColor=color)))
cr.cell(last + 2, 4, "Fixed (no test) means changed and exercised by the existing suites only; it has no dedicated regression test.").font = Font(name="Calibri", size=9, italic=True)

# ---------------- Truth snapshot
name = "Truth snapshot"
if name in wb.sheetnames:
    del wb[name]
ts = wb.create_sheet(name, 0)
ts.sheet_view.showGridLines = False
tot = Counter()  # real testcase counts (parametrised cases counted individually)
for case in ET.parse(junit).getroot().iter("testcase"):
    sk = case.find("skipped")
    tot["fail" if (case.find("failure") is not None or case.find("error") is not None) else ("skip" if sk is not None else "pass")] += 1
fixed = Counter(("Fixed" if o.startswith("Fixed") else o) for _, _, _, o, _ in FINDINGS)
lines = [
    ("As of", TODAY.strftime("%d %b %Y"), None),
    ("What this workbook is", "The single source of truth for plan status, task status and test evidence. Anything not recorded here is not claimed.", None),
    ("Code state", "All implementation is in the uncommitted working tree. Nothing is committed, merged or deployed.", None),
    ("Test run", f"Backend full suite on SQLite: {tot['pass']} passed, {tot['fail']} failed, {tot['skip'] + tot['xfail']} skipped. Postgres-only concurrency tests are skipped on SQLite and have not been run since the changes. Web: vitest, tsc -b and ESLint are clean at the last full run.", None),
    ("Plan items", f"{len(plan_result)} items: {counts['Built']} Built, {counts['Partial']} Partial, {counts['Not built']} Not built (judged against each item's own scope, from code and tests).", None),
    ("Sign-off", "No item is Done. Review is In progress on every Built item: agent review has run, a human has not signed. Decision and external items (host, CA, pharmacist, gateway, devices) are not recorded.", None),
    ("Code review", f"{len(FINDINGS)} findings across two rounds: {fixed['Fixed']} fixed, {fixed['Open']} open, {fixed['Reverted']} reverted. See the Code review 2026-10-05 sheet.", None),
    ("Freeze", "Live NIC e-way, GSTR-2B API, Tally and WhatsApp Cloud stay off. Built items for those are stubs or stored fields only.", None),
    ("Before any deploy", "Set PLANWAVE_DATA_KEY and MFA_ENCRYPTION_KEY; run manage.py seal_bank_accounts once; start workers with -Q celery,high_priority,media_heavy,reports; apply migrations (planwave 0004, masters 0030, inventory 0026-0027, core 0051, sales 0063).", None),
    ("Known open items", "COD cash receipts on routes, 206AB rates for company vendors, AA consent verification, WhatsApp opt-in source, wall-clock SLA tests, lower-severity web items, Postgres re-run of concurrency tests.", None),
]
ts["A1"] = "Truth snapshot"
ts["A1"].font = Font(name="Calibri", size=18, bold=True)
ts.column_dimensions["A"].width = 24
ts.column_dimensions["B"].width = 130
for n, (k, v, _) in enumerate(lines, 3):
    a = ts.cell(n, 1, k)
    a.font, a.alignment = Font(name="Calibri", size=10, bold=True), wrap
    b = ts.cell(n, 2, v)
    b.font, b.alignment = body, wrap
    ts.row_dimensions[n].height = max(18, 15 * (len(str(v)) // 125 + 1))

# ---------------- change log
log = wb["Plan change log"]
n = log.max_row + 1
for c, v in enumerate([TODAY, "Truth update: plan stages, evidence and Task Register rows set from code and the latest full test run; review findings recorded.",
                       "All", f"{counts['Built']} Built, {counts['Partial']} Partial, {counts['Not built']} Not built; none Done (human sign-off pending).", "Claude (delegated)"], 1):
    cell = log.cell(n, c, v)
    cell.font, cell.border, cell.alignment = body, box, wrap
log.cell(n, 1).number_format = "dd-mmm-yy"
log.row_dimensions[n].height = 60

wb.save(sys.argv[1])
print("plan", dict(counts), "register rows touched", dict(changed), "tests", dict(tot))
