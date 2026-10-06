# -*- coding: utf-8 -*-
"""Write passing or failing pytest results into scripts/task_evidence.csv.

Uses scripts/task_test_map.csv. A task with no mapping is left untouched.
This does not mark a task OS ready, and it does not invent a result.
"""
import csv
import datetime
import os
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MAP_CSV = os.path.join(ROOT, "scripts", "task_test_map.csv")
EVIDENCE_CSV = os.path.join(ROOT, "scripts", "task_evidence.csv")
FIELDS = [
    "Task ID",
    "Owner",
    "Target date",
    "Estimate days",
    "Depends on",
    "Blocked by",
    "Test case ID",
    "Last verified",
    "Verified by",
    "Verification result",
]


def load_map():
    if not os.path.exists(MAP_CSV):
        return {}
    with open(MAP_CSV, encoding="utf-8", newline="") as handle:
        return {
            (item.get("Test case ID") or "").strip(): item["Task ID"].strip()
            for item in csv.DictReader(handle)
            if (item.get("Task ID") or "").strip() and (item.get("Test case ID") or "").strip()
        }


def junit_results(path):
    tree = ET.parse(path)
    results = {}
    for case in tree.iter("testcase"):
        name = case.get("name") or ""
        classname = case.get("classname") or ""
        node = f"{classname}::{name}" if classname else name
        failed = case.find("failure") is not None or case.find("error") is not None
        skipped = case.find("skipped") is not None
        if skipped:
            result = "Skipped"
        elif failed:
            result = "Fail"
        else:
            result = "Pass"
        results[node] = result
        results[name] = result
    return results


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/apply_pytest_evidence.py path/to/junit.xml")
    mapping = load_map()
    if not mapping:
        print("No task-to-test map. Nothing updated.")
        return 0
    results = junit_results(sys.argv[1])
    existing = {}
    if os.path.exists(EVIDENCE_CSV):
        with open(EVIDENCE_CSV, encoding="utf-8", newline="") as handle:
            for item in csv.DictReader(handle):
                if item.get("Task ID"):
                    existing[item["Task ID"]] = item
    today = datetime.date.today().isoformat()
    updated = 0
    for test_id, task_id in mapping.items():
        if test_id not in results:
            continue
        row = existing.get(task_id, {field: "" for field in FIELDS})
        row["Task ID"] = task_id
        row["Test case ID"] = test_id
        row["Last verified"] = today
        row["Verified by"] = "CI"
        row["Verification result"] = results[test_id]
        existing[task_id] = row
        updated += 1
    with open(EVIDENCE_CSV, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for task_id in sorted(existing):
            writer.writerow({field: existing[task_id].get(field, "") for field in FIELDS})
    print(f"Updated {updated} task evidence row(s). Unmapped tests were ignored.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
