#!/usr/bin/env python3
"""C.4 — freeze-ordered release notes from git log prev..sha.

    python scripts/ops/release_notes.py <prev> <sha>

Prints four buckets (money, tax, stock, other). Does not publish, tag, or
invent GST opinions. Operators paste the output into the release ticket.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

_MONEY = (
    "money",
    "payment",
    "razorpay",
    "invoice",
    "allocation",
    "dunning",
    "billing",
    "receipt",
    "journal",
    "gl ",
    "ledger",
)
_TAX = ("gst", "gstr", "tax", "hsn", "irn", "einvoice", "e-invoice", "cess", "tds", "tcs")
_STOCK = ("stock", "inventory", "warehouse", "batch", "fefo", "godown", "serial")


def bucket(subject: str) -> str:
    text = subject.lower()
    # Tax before money so "einvoice" / "gstr" are not stolen by the "invoice" token.
    if any(token in text for token in _TAX):
        return "tax"
    if any(token in text for token in _MONEY):
        return "money"
    if any(token in text for token in _STOCK):
        return "stock"
    return "other"


def git_subjects(prev: str, sha: str) -> list[str]:
    proc = subprocess.run(  # noqa: S603 — argv list, repo-local git
        ["git", "log", "--format=%s", f"{prev}..{sha}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or f"git log failed ({proc.returncode})")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def render(subjects: list[str]) -> str:
    groups: dict[str, list[str]] = {"money": [], "tax": [], "stock": [], "other": []}
    for subject in subjects:
        groups[bucket(subject)].append(subject)
    lines = [
        "# Release notes (C.4)",
        "",
        "Money / tax / stock first. Human reviews before sending to customers.",
        "",
    ]
    for name in ("money", "tax", "stock", "other"):
        lines.append(f"## {name}")
        if groups[name]:
            lines.extend(f"- {item}" for item in groups[name])
        else:
            lines.append("- (none)")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze-ordered git log notes")
    parser.add_argument("prev", help="Previous release SHA or tag")
    parser.add_argument("sha", help="This release SHA or tag")
    args = parser.parse_args(argv)
    sys.stdout.write(render(git_subjects(args.prev, args.sha)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
