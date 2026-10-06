# -*- coding: utf-8 -*-
"""Fail when a task-register claim disagrees with product code.

A row marked Mechanism not found fails if its named token now exists under
backend/ or web/src. A row marked supported or in product fails if its note
names one of those tokens and the token is still absent.

Partial rows may name the missing piece. scripts/ and docs/ are not product code.
"""
import csv
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REGISTER = os.path.join(ROOT, "Bizboard_Master_Task_Register_Enhanced.csv")
SCAN_ROOTS = ("backend", "web/src")
SKIP_DIRS = {"__pycache__", "node_modules", "migrations", ".venv", "venv"}
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx"}

# Distinctive tokens the register uses for mechanisms that were absent.
TOKENS = (
    "pg_trgm",
    "GinIndex",
    "Shift+P",
    "Privacy Mode",
    "Z-score",
    "django-otp",
    "WebSocket",
    "location_tag",
    "TIME_BARRED",
    "206AB",
    "Ctrl+K",
    "Command Palette",
    "type-to-confirm",
    "hash chaining",
    "CartSession",
    "SimpleHistory",
    "PlanQuotaExceeded",
)

SUPPORTED = {
    "Validated (Supported)",
    "In product",
    "Code Complete & Verified",
}


def tokens_in_product():
    found = set()
    for relative in SCAN_ROOTS:
        base = os.path.join(ROOT, relative)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
            for filename in filenames:
                if os.path.splitext(filename)[1] not in TEXT_SUFFIXES:
                    continue
                path = os.path.join(dirpath, filename)
                try:
                    text = open(path, encoding="utf-8", errors="ignore").read()
                except OSError:
                    continue
                for token in TOKENS:
                    if token in text:
                        found.add(token)
    return found


def main():
    if not os.path.exists(REGISTER):
        raise SystemExit(f"Missing register: {REGISTER}")
    present = tokens_in_product()
    problems = []
    with open(REGISTER, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            status = row.get("Validation Status") or ""
            note = row.get("Notes") or ""
            task_id = row.get("Task ID") or ""
            named = [token for token in TOKENS if token in note]
            if status == "Mechanism not found":
                stale = [token for token in named if token in present]
                if stale:
                    problems.append(
                        f"{task_id} says Mechanism not found, but {', '.join(stale)} is in product code"
                    )
            elif status in SUPPORTED:
                missing = [token for token in named if token not in present]
                if missing:
                    problems.append(
                        f"{task_id} is marked {status}, but {', '.join(missing)} is not in product code"
                    )
    if problems:
        print("\n".join(problems))
        raise SystemExit(1)
    print(f"Register claims agree with product code. Tokens present: {sorted(present) or 'none'}")


if __name__ == "__main__":
    sys.exit(main())
