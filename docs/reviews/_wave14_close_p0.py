#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Close Wave 14 P0 issues in MASTER_ISSUE_REGISTER after gates pass.

Resolves: BB-000456..BB-000462, BB-000544, BB-000548.
Does not touch other Open issues.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

TODAY = "2026-08-04"
OUT = Path(__file__).resolve().parent
REGISTER = OUT / "MASTER_ISSUE_REGISTER.md"
STATS = OUT / "_stats.json"
CHANGELOG = OUT / "CHANGELOG.md"
EXEC = OUT / "01_EXECUTIVE_SUMMARY.md"

RESOLVE_IDS = [
    "BB-000456",
    "BB-000457",
    "BB-000458",
    "BB-000459",
    "BB-000460",
    "BB-000461",
    "BB-000462",
    "BB-000544",
    "BB-000548",
]

RESOLUTION = f"""
**Status → Resolved ({TODAY}).** Closed in Wave 14 P0 remediation (beat epoch+Redis key, refund REFUNDED+link reopen, disposal 5600/5700, return COGS SALE unit_cost, SQLite prod refuse, semantic `_wave14_assert_gates.py`, honesty docs). See CHANGELOG Wave 14 P0 closure.
"""


def main() -> None:
    text = REGISTER.read_text(encoding="utf-8")
    closed = 0
    for iid in RESOLVE_IDS:
        # Replace Status | Open in that issue block only
        pattern = rf"(## {iid} —.*?\n\| \*\*Status\*\* \| )Open( \|)"
        new_text, n = re.subn(pattern, rf"\g<1>Resolved\2", text, count=1, flags=re.S)
        if n:
            text = new_text
            closed += 1
            # Append resolution note before next ## BB- if not already
            if f"Status → Resolved ({TODAY})" not in text.split(f"## {iid} —")[1].split("## BB-")[0]:
                # Insert before next issue header
                parts = text.split(f"## {iid} —", 1)
                head, rest = parts[0], parts[1]
                if "\n## BB-" in rest:
                    body, tail = rest.split("\n## BB-", 1)
                    text = head + f"## {iid} —" + body.rstrip() + "\n" + RESOLUTION + "\n## BB-" + tail
                else:
                    text = head + f"## {iid} —" + rest.rstrip() + "\n" + RESOLUTION + "\n"

    # Update Open count in status table
    stats = json.loads(STATS.read_text(encoding="utf-8"))
    # Recount Open from register
    open_count = len(re.findall(r"\|\s*\*\*Status\*\*\s*\|\s*Open\s*\|", text))
    resolved_count = len(re.findall(r"\|\s*\*\*Status\*\*\s*\|\s*Resolved\s*\|", text))

    status = dict(stats.get("status") or {})
    for k in list(status.keys()):
        if "Deferred" in k and "roadmap" in k:
            status["Deferred — roadmap"] = status.pop(k)
            break
    status["Open"] = open_count
    status["Resolved"] = resolved_count

    # Patch status table Open/Resolved rows
    if re.search(r"\| Open \| \d+ \|", text):
        text = re.sub(r"(\| Open \| )\d+( \|)", rf"\g<1>{open_count}\2", text, count=1)
    if re.search(r"\| Resolved \| \d+ \|", text):
        text = re.sub(r"(\| Resolved \| )\d+( \|)", rf"\g<1>{resolved_count}\2", text, count=1)

    # Wave note
    if "Wave 14 P0 closure" not in text:
        text = text.replace(
            "## Wave 14 missed-findings",
            f"## Wave 14 P0 closure ({TODAY})\n\n"
            f"Resolved {closed} P0/process issues: {', '.join(RESOLVE_IDS)}. "
            f"Open now **{open_count}**. Semantic gates: `_wave14_assert_gates.py`.\n\n"
            "## Wave 14 missed-findings",
            1,
        )

    REGISTER.write_text(text, encoding="utf-8")

    # Update issues meta statuses
    issues = stats.get("issues") or []
    for issue in issues:
        if issue.get("id") in RESOLVE_IDS:
            issue["status"] = "Resolved"
    stats["status"] = status
    stats["open_count"] = open_count
    stats["wave14_p0_closure"] = {
        "date": TODAY,
        "resolved_ids": RESOLVE_IDS,
        "resolved_count": closed,
    }
    stats["issues"] = issues
    STATS.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    cl_block = f"""## {TODAY} — Wave 14 P0 Critical closure

Closed **{closed}** P0/process issues via code + tests + `_wave14_assert_gates.py`:

{', '.join(RESOLVE_IDS)}

### Outcomes
- Beat heartbeat: unix epoch + bare Redis key (compose float() compatible)
- Gateway refund: CustomerReceipt.REFUNDED; PaymentLink reopened
- Fixed asset disposal: 5600/5700; never NBV→5300
- Sales return COGS: SALE movement unit_cost basis
- SQLite refused when DJANGO_ENV production/staging
- Semantic assert gates + honesty pointers updated

Open remaining: **{open_count}** (P1+ residual + Deferred roadmap/ops).

---

"""
    cl = CHANGELOG.read_text(encoding="utf-8")
    if "Wave 14 P0 Critical closure" not in cl:
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
            f"**Latest:** Wave 14 P0 closure {TODAY} — register **{stats['total']}** issues. "
            f"**Open: {open_count}.** Resolved {resolved_count}. "
            f"P0 Criticals BB-000456–462/544/548 closed. Production Readiness Score **5.2 / 10** "
            f"(dogfood Conditional; P1+ and Deferred ops/GSP remain).",
            et,
            count=1,
        )
        if f"## Wave 14 P0 closure ({TODAY})" not in et:
            et = et.rstrip() + f"""

---

## Wave 14 P0 closure ({TODAY})

Resolved {closed} Critical/process IDs ({', '.join(RESOLVE_IDS)}). Remaining Open **{open_count}** are mostly P1–P3 Wave 14 residuals + historical Deferred roadmap/ops. Dogfood Conditional; paid pilot still needs GO_NO_GO + TLS/backups + P1 triage.

"""
        EXEC.write_text(et, encoding="utf-8")

    print(f"Closed {closed}/{len(RESOLVE_IDS)}; Open={open_count}; Resolved={resolved_count}")


if __name__ == "__main__":
    main()
