#!/usr/bin/env python
"""Write pytest, Vitest and Playwright results into the Task Register workbook.

    python qos/tools/register_sync.py --junit qos/evidence/pytest-junit.xml \
        [--junit web/junit-vitest.xml] [--junit web/junit-playwright.xml] \
        [--register Bizboard_Product_Task_Universe_Master.xlsx] [--by "CI run 123"] [--dry-run]

For every Task Register row whose ``Test case ID`` names one or more test files
(``tests/test_x.py``, ``web/src/__tests__/ux_0596.test.tsx``) or test ids
(``tests/test_x.py::test_name``), the matching JUnit testcases decide
``Verification result``:

* any failure or error                 -> ``Fail``
* every matched test passed            -> ``Pass`` (a row already marked ``Partial`` stays ``Partial``)
* nothing matched / all skipped        -> row left untouched, reported as ``unmatched``

Pytest classnames (``tests.edge.test_x.TestClass``) and Vitest / Playwright
file paths (``src/__tests__/ux_0596.test.tsx``, ``e2e/login.spec.ts``) are both
recognised. A ``web/`` prefix on the register path matches a report emitted
from the ``web/`` directory.

``Last verified`` and ``Verified by`` are set only for rows that were scored.
The register's formulas have no cached values after an openpyxl save; open it in
Excel (or run ``qos/tools/recalc_xlsx.ps1``) before reading the Founder view.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import openpyxl

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTER = REPO_ROOT / "Bizboard_Product_Task_Universe_Master.xlsx"

# Vitest uses *.test.ts(x); Playwright uses *.spec.ts(x). Either may appear as
# a path inside classname, or as the whole classname.
_WEB_FILE = re.compile(r"([\w./-]+\.(?:test|spec)\.[cm]?[jt]sx?)", re.IGNORECASE)


def _outcome(case: ET.Element) -> str:
    if case.find("failure") is not None or case.find("error") is not None:
        return "fail"
    if case.find("skipped") is not None:
        return "skip"
    return "pass"


def _pytest_file(classname: str) -> str | None:
    parts = classname.split(".")
    # tests.edge.test_x.TestClass -> tests/edge/test_x.py
    while parts and not parts[-1].startswith("test_"):
        parts.pop()
    if not parts:
        return None
    return "/".join(parts) + ".py"


def case_file(classname: str) -> str | None:
    """Map a JUnit classname to a repo-relative test file, or None."""
    text = (classname or "").replace("\\", "/")
    web = _WEB_FILE.search(text)
    if web:
        return web.group(1).lstrip("./")
    return _pytest_file(text)


def _index_keys(file: str) -> list[str]:
    keys = [file]
    if file.startswith("web/"):
        keys.append(file[len("web/"):])
    elif file.startswith("src/") or file.startswith("e2e/"):
        keys.append("web/" + file)
    return keys


def load_junit(path: Path) -> dict[str, list[tuple[str, str]]]:
    """file -> [(test name, outcome)] with outcome in pass|fail|skip.

    Each case is stored under the path from the report and under the ``web/``
    alias, so a register row can use either form.
    """
    by_file: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for case in ET.parse(path).getroot().iter("testcase"):
        file = case_file(case.get("classname", ""))
        if not file:
            continue
        row = (case.get("name", ""), _outcome(case))
        for key in _index_keys(file):
            by_file[key].append(row)
    return by_file


def merge_junit(paths: list[Path]) -> dict[str, list[tuple[str, str]]]:
    merged: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for path in paths:
        for file, rows in load_junit(path).items():
            merged[file].extend(rows)
    return merged


def _lookup(file: str, by_file: dict[str, list[tuple[str, str]]]) -> list[tuple[str, str]]:
    if file in by_file:
        return by_file[file]
    if file.startswith("web/") and file[len("web/"):] in by_file:
        return by_file[file[len("web/"):]]
    alias = "web/" + file
    if alias in by_file:
        return by_file[alias]
    return []


def score(test_ref: str, by_file: dict[str, list[tuple[str, str]]]) -> str | None:
    outcomes: list[str] = []
    for ref in (r.strip() for r in test_ref.split(";") if r.strip()):
        ref = ref.replace("backend/", "", 1) if ref.startswith("backend/") else ref
        file, _, test = ref.partition("::")
        for name, outcome in _lookup(file, by_file):
            if not test or name == test or name.startswith(test + "["):
                outcomes.append(outcome)
    if "fail" in outcomes:
        return "Fail"
    if "pass" in outcomes:
        return "Pass"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--junit", required=True, type=Path, action="append",
                    help="JUnit XML from pytest, Vitest or Playwright. Repeat for each suite.")
    ap.add_argument("--register", type=Path, default=DEFAULT_REGISTER)
    ap.add_argument("--by", default="pytest (JUnit sync)")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    by_file = merge_junit(a.junit)
    wb = openpyxl.load_workbook(a.register)
    ws = wb["Task Register"]
    head = {c.value: c.column for c in ws[1]}
    need = ["Task ID", "Test case ID", "Verification result", "Last verified", "Verified by"]
    missing = [h for h in need if h not in head]
    if missing:
        print(f"register is missing columns: {missing}", file=sys.stderr)
        return 2

    changed = unmatched = 0
    for r in range(2, ws.max_row + 1):
        ref = ws.cell(r, head["Test case ID"]).value
        if not ref:
            continue
        result = score(str(ref), by_file)
        if result is None:
            unmatched += 1
            print(f"unmatched  {ws.cell(r, 1).value}: {ref}")
            continue
        cur = ws.cell(r, head["Verification result"]).value
        new = "Partial" if (result == "Pass" and cur == "Partial") else result
        print(f"{ws.cell(r, 1).value}: {cur} -> {new}")
        ws.cell(r, head["Verification result"]).value = new
        ws.cell(r, head["Last verified"]).value = a.date
        ws.cell(r, head["Verified by"]).value = a.by
        changed += 1
    print(f"scored {changed}, unmatched {unmatched}")
    if not a.dry_run and changed:
        wb.calculation.fullCalcOnLoad = True
        wb.save(a.register)
        print(f"saved {a.register} (recalculate in Excel before reading the dashboards)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
