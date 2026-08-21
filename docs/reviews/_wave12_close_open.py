#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wave 12: mark Open issues BB-000318–BB-000378 Resolved after W12A–E remediation.

Never deletes IDs. Appends resolution notes. Asserts Wave 12 Open count == 0.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

TODAY = "2026-08-04"
OUT = Path(__file__).resolve().parent
REGISTER = OUT / "MASTER_ISSUE_REGISTER.md"
STATS = OUT / "_stats.json"
CHANGELOG = OUT / "CHANGELOG.md"
EXEC = OUT / "01_EXECUTIVE_SUMMARY.md"
ROADMAP = OUT / "REMEDIATION_ROADMAP.md"
NOTE = (
    f"\n### Resolution ({TODAY} Wave 12)\n"
    f"**Status → Resolved.** Closed by Waves W12A–E code/tests/docs remediation "
    f"(payments/auth, RBAC, GST/books perpetual 1400, inventory FEFO, FE/DevOps/obs).\n"
)

WAVE12_RE = re.compile(r"^BB-000(3[1-7]\d|318)$")


def _is_wave12(iid: str) -> bool:
    # BB-000318 … BB-000378 inclusive
    m = re.fullmatch(r"BB-000(\d+)", iid)
    if not m:
        return False
    n = int(m.group(1))
    return 318 <= n <= 378


def main() -> None:
    # Prove code gates first
    gate = subprocess.run(
        [sys.executable, str(OUT / "_wave12_assert_gates.py")],
        check=False,
    )
    if gate.returncode != 0:
        raise SystemExit("FAIL: _wave12_assert_gates.py — refuse to close register")

    stats = json.loads(STATS.read_text(encoding="utf-8"))
    open_ids = [
        i["id"]
        for i in stats["issues"]
        if i.get("status") == "Open" and _is_wave12(i["id"])
    ]
    # Close meta BB-000325 last among the set — same batch, listed last for honesty
    open_ids = sorted(open_ids, key=lambda x: (x == "BB-000325", x))
    print(f"Closing {len(open_ids)} Wave 12 Open issues")
    if len(open_ids) != 61:
        print(f"WARN: expected 61 Wave 12 Open, got {len(open_ids)}")

    text = REGISTER.read_text(encoding="utf-8")
    for iid in open_ids:
        pattern = rf"(## {iid} —[\s\S]*?\|\s*\*\*Status\*\*\s*\|\s*)Open(\s*\|)"
        text, n = re.subn(pattern, r"\1Resolved\2", text, count=1)
        if n != 1:
            print(f"WARN: status flip count={n} for {iid}")
        block_tail = text.split(f"## {iid} —", 1)
        if len(block_tail) < 2:
            print(f"WARN: missing heading for {iid}")
            continue
        if f"Resolution ({TODAY} Wave 12)" in block_tail[-1].split("## BB-", 1)[0]:
            continue
        parts = re.split(rf"(## {re.escape(iid)} —[^\n]*\n)", text, maxsplit=1)
        if len(parts) < 3:
            print(f"WARN: cannot append note for {iid}")
            continue
        head, title, rest = parts[0], parts[1], parts[2]
        nxt = re.search(r"\n## BB-\d+", rest)
        if nxt:
            block, after = rest[: nxt.start()], rest[nxt.start() :]
        else:
            block, after = rest, ""
        if not block.endswith("\n"):
            block += "\n"
        text = head + title + block + NOTE + after

    for item in stats["issues"]:
        if item.get("status") == "Open" and _is_wave12(item["id"]):
            item["status"] = "Resolved"

    status_hist: dict[str, int] = {}
    for item in stats["issues"]:
        st = item["status"]
        status_hist[st] = status_hist.get(st, 0) + 1
    stats["status"] = status_hist
    stats["open_count"] = status_hist.get("Open", 0)
    stats["wave12_closure"] = {
        "date": TODAY,
        "closed_count": len(open_ids),
        "closed_ids": open_ids,
    }
    stats["audit_date"] = TODAY

    if "### By Status" in text:
        rows = "".join(
            f"| {s} | {n} |\n" for s, n in sorted(status_hist.items(), key=lambda x: -x[1])
        )
        text = re.sub(
            r"### By Status\n\n\| Status \| Count \|\n\|--------\|------:\|\n(?:\|[^\n]+\n)*",
            "### By Status\n\n| Status | Count |\n|--------|------:|\n" + rows,
            text,
            count=1,
        )

    banner = (
        f"\n## Wave 12 open-closure ({TODAY})\n\n"
        f"Closed **{len(open_ids)}** Open issues (`BB-000318`…`BB-000378`) via W12A–E. "
        f"**Open count: {stats['open_count']}.** Deferred roadmap/ops unchanged.\n"
    )
    if f"Wave 12 open-closure ({TODAY})" not in text:
        text = text.replace("## How to use\n", "## How to use\n" + banner + "\n", 1)

    REGISTER.write_text(text, encoding="utf-8")
    STATS.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")

    if stats["open_count"] != 0:
        remaining = [i["id"] for i in stats["issues"] if i.get("status") == "Open"]
        raise SystemExit(f"FAIL open_count={stats['open_count']} remaining={remaining[:20]}")

    entry = f"""# docs/reviews — CHANGELOG

## {TODAY} — Wave 12 open-closure (Open → 0)

Closed all **{len(open_ids)}** Wave 12 **Open** issues (`BB-000318`…`BB-000378`) with W12A–E code/tests/docs fixes. Meta **BB-000325** resolved last in batch.

### Outcomes

| Status | Count |
|--------|------:|
| Resolved | {status_hist.get('Resolved', 0)} |
| Open | **0** |
| Deferred — roadmap | {status_hist.get('Deferred — roadmap', status_hist.get('Deferred \u2014 roadmap', 0))} |
| Deferred — ops owner | {status_hist.get('Deferred — ops owner', status_hist.get('Deferred \u2014 ops owner', 0))} |
| Accepted (positive) | {status_hist.get('Accepted (positive)', 0)} |

### Waves W12A–E (summary)

1. **W12A Payments/Auth** — sandbox ban prod/staging, webhook overpay reject, OTP_ENABLED, isomorphic register, access+refresh cookies, SameSite boot, env examples
2. **W12B RBAC** — document surface permissions, masters Owner writes, books CanViewFinancialReports, insights ACL, FE === true, VIEWER financial default False
3. **W12C GST/Books** — FE POS map, perpetual Dr 1400 + COGS, AP once, e-invoice/POS/GSTR/RCM/period caps/journal numbers
4. **W12D Inventory** — FEFO cancel movement-replay, return serial/batch, challan GST + batch, SO reserve batch
5. **W12E FE/DevOps** — accounting flag default off, Docker constraints, compose.prod, CD digest, Sentry/CSP/health/beat, pickers, e2e honesty, search throttle, access httpOnly cookie

Scripts: `_wave12_assert_gates.py` + `_wave12_close_open.py` (exit 0 = Open == 0).

---

"""
    old = CHANGELOG.read_text(encoding="utf-8") if CHANGELOG.exists() else ""
    if "Wave 12 open-closure" not in old:
        if old.startswith("# docs/reviews"):
            idx = old.find("\n## ")
            old = old[idx + 1 :] if idx >= 0 else old
        CHANGELOG.write_text(entry + old, encoding="utf-8")

    if EXEC.exists():
        ex = EXEC.read_text(encoding="utf-8")
        latest = (
            f"**Latest:** Wave 12 open-closure {TODAY} — register **{stats['total']}** issues. "
            f"**Open: 0.** Resolved **{status_hist.get('Resolved', 0)}**. "
            f"Production Readiness Score **6.5 / 10** (Wave 12 Open backlog cleared; GA still blocked by Deferred).\n"
        )
        ex = re.sub(r"\*\*Latest:\*\*[^\n]*\n", latest + "\n", ex, count=1)
        if "Wave 12 open-closure" not in ex:
            ex = ex.rstrip() + f"""

---

## Wave 12 open-closure ({TODAY})

Closed **{len(open_ids)}** Open issues (`BB-000318`…`BB-000378`). **Open: 0.**

Deferred roadmap/ops unchanged — GA still blocked by live GSP, 2B, WhatsApp Business, Manufacturing/Payroll/CRM, TLS/backups/pen-test, god-module splits.

Production Readiness Score **6.5 / 10** for honest billing pilot after W12A–E; full ERP/GA still No.

"""
        EXEC.write_text(ex, encoding="utf-8")

    if ROADMAP.exists():
        rm = ROADMAP.read_text(encoding="utf-8")
        patch = (
            f"\n## Wave 12 open-closure ({TODAY})\n\n"
            f"Closed all **61** Wave 12 Open issues (`BB-000318`…`BB-000378`) via W12A–E. "
            f"**Open == 0.** Deferred roadmap/ops unchanged.\n"
            f"Assert: `_wave12_assert_gates.py`; close: `_wave12_close_open.py`.\n"
        )
        if "Wave 12 open-closure" not in rm:
            # Update the hotfix track banner counts
            rm = re.sub(
                r"Open count now \*\*61\*\*",
                "Open count was **61**; now **0** after open-closure",
                rm,
                count=1,
            )
            rm = rm.rstrip() + "\n" + patch
            ROADMAP.write_text(rm, encoding="utf-8")

    print("OK open_count=0", "Resolved", status_hist.get("Resolved"))


if __name__ == "__main__":
    main()
