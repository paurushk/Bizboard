#!/usr/bin/env python3
"""WP-EN1: keep pull requests small enough to review.

    python scripts/ci_gates/check_merge_size.py <base-ref> [--labels "a,b"]

Counts added + deleted lines between <base-ref> and HEAD, leaving out generated and lock files.
Above WARN_LINES it prints a warning; above FAIL_LINES it fails unless the PR carries the
``large-change-approved`` label. See docs/ops/RELEASE_HYGIENE.md.

Switched on as a merge blocker only after the WP-A1 commit chunks are on main: those chunks are
deliberately large and would trip it.
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys

WARN_LINES = 1500
FAIL_LINES = 4000
APPROVAL_LABEL = "large-change-approved"
GENERATED = (
    "docs/openapi-snapshot.json",
    "web/src/api/openapi-types.ts",
    "*package-lock.json",
    "docs/accounting/LEDGER_COVERAGE_MAP.md",
    "docs/PRODUCT_QUALITY_BACKLOG.md",
    "docs/reviews/MASTER_ISSUE_REGISTER.md",
    "*/migrations/*.py",
)


def counted_lines(numstat: str) -> tuple[int, list[str]]:
    total = 0
    skipped: list[str] = []
    for row in numstat.splitlines():
        parts = row.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        if any(fnmatch.fnmatch(path, pat) for pat in GENERATED):
            skipped.append(path)
            continue
        if added == "-" or deleted == "-":  # binary
            continue
        total += int(added) + int(deleted)
    return total, skipped


def verdict(total: int, labels: set[str]) -> tuple[int, str]:
    if total > FAIL_LINES and APPROVAL_LABEL not in labels:
        return 1, (
            f"FAIL: {total} changed lines (limit {FAIL_LINES}). Split the change, or add the "
            f"'{APPROVAL_LABEL}' label with a reviewer's agreement."
        )
    if total > WARN_LINES:
        return 0, f"WARN: {total} changed lines; over {WARN_LINES} is hard to review well."
    return 0, f"OK: {total} changed lines."


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--labels", default="")
    args = ap.parse_args()
    numstat = subprocess.run(
        ["git", "diff", "--numstat", f"{args.base}...HEAD"], check=True, capture_output=True, text=True,
    ).stdout
    total, skipped = counted_lines(numstat)
    code, message = verdict(total, {x.strip() for x in args.labels.split(",") if x.strip()})
    print(message)
    if skipped:
        print(f"(not counted: {len(skipped)} generated/lock/migration file(s))")
    return code


if __name__ == "__main__":
    sys.exit(main())
