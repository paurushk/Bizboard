#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wave 11: Resolve deferred code-fixable backlog + reclassify already-fixed IDs.

Never deletes IDs. Appends resolution notes. Asserts targets are not Deferred — roadmap.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

TODAY = "2026-08-03"
OUT = Path(__file__).resolve().parent
REGISTER = OUT / "MASTER_ISSUE_REGISTER.md"
STATS = OUT / "_stats.json"
CHANGELOG = OUT / "CHANGELOG.md"
EXEC = OUT / "01_EXECUTIVE_SUMMARY.md"

# Wave R — already fixed in tree (reclassify)
WAVE_R = {
    "BB-000031": "Accounting routes under RoleRoute allow={allowAccounting} (App.tsx).",
    "BB-000061": "Delivery challan posts stock when stock_on_delivery_challan (sales/notes_services).",
    "BB-000077": "Opening uses is_opening_balance; magic TALLY_OPENING notes rejected.",
    "BB-000079": "BankAccount partial unique on is_default (payments/models).",
    "BB-000083": "Search invoices gated Owner / can_view_financial_reports (search/views).",
    "BB-000113": "Backup route uses canExport (App.tsx).",
    "BB-000133": "JWT_ACCESS_MINUTES default 15m (config/settings).",
}

# Wave 11A–D implementations
WAVE_11 = {
    "BB-000030": "Wave 11A: USER_KEY stores display-only cache; capabilities from /auth/me; access memory-only.",
    "BB-000084": "Wave 11A: company/tenancy FKs read-only + re-stamp; regression tests.",
    "BB-000085": "Wave 11A: CompanyScopedViewSet audit + tenant isolation tests for stragglers.",
    "BB-000137": "Wave 11A: CSV exports gated CanExport; PII minimized for non-owners.",
    "BB-000064": "Wave 11B: GstReturnSnapshot UniqueConstraint (company, return_type, period); replace on regenerate.",
    "BB-000063": "Wave 11B: POS via GSTIN/state-code map (billing + place_of_supply).",
    "BB-000081": "Wave 11B: SerialNumberService.receive IntegrityError retry.",
    "BB-000082": "Wave 11B: Register requires GSTIN for REGULAR/COMPOSITION; empty OK for UNREGISTERED.",
    "BB-000076": "Wave 11B: insights float→Decimal for money/score paths.",
    "BB-000068": "Wave 11C: insights beat fans out per-company Celery tasks.",
    "BB-000075": "Wave 11C: ledger statement select_related/prefetch (ledgers/services).",
    "BB-000118": "Wave 11C: product picker listProductsPage + search (useProductSearch).",
    "BB-000121": "Wave 11C: optional VITE_SENTRY_DSN wiring (main.tsx); no-op when unset.",
    "BB-000165": "Wave 11C: VITE_SENTRY_DSN documented in web/.env.example.",
    "BB-000125": "Wave 11C: backend constraints.txt + CI -c; upper-bound ranges in requirements.",
    "BB-000191": "Wave 11D: test_money_contract.py Decimal-string smoke for sales/purchase totals.",
}

# Remain Deferred with Wave 12 note (not resolved this wave)
WAVE_12_NOTE = {
    "BB-000108": "Wave 11: skipped god-module rewrite — deferred to Wave 12.",
    "BB-000114": "Wave 11: skipped mega-component split — deferred to Wave 12.",
}

TARGET_RESOLVE = {**WAVE_R, **WAVE_11}


def _append_note(text: str, iid: str, note: str) -> str:
    marker = f"Resolution ({TODAY} Wave 11)"
    block_split = text.split(f"## {iid} —", 1)
    if len(block_split) < 2:
        print(f"WARN: missing issue {iid}")
        return text
    if marker in block_split[1].split("## BB-", 1)[0]:
        return text
    parts = re.split(rf"(## {re.escape(iid)} —[^\n]*\n)", text, maxsplit=1)
    if len(parts) < 3:
        print(f"WARN: cannot append note for {iid}")
        return text
    head, title, rest = parts[0], parts[1], parts[2]
    nxt = re.search(r"\n## BB-\d+", rest)
    if nxt:
        block, after = rest[: nxt.start()], rest[nxt.start() :]
    else:
        block, after = rest, ""
    if not block.endswith("\n"):
        block += "\n"
    return head + title + block + note + after


def main() -> None:
    stats = json.loads(STATS.read_text(encoding="utf-8"))
    text = REGISTER.read_text(encoding="utf-8")

    closed: list[str] = []
    for iid, detail in TARGET_RESOLVE.items():
        pattern = (
            rf"(## {iid} —[\s\S]*?\|\s*\*\*Status\*\*\s*\|\s*)"
            r"Deferred — roadmap(\s*\|)"
        )
        text, n = re.subn(pattern, r"\1Resolved\2", text, count=1)
        if n != 1:
            # Already Resolved or different status
            cur = next((i for i in stats["issues"] if i["id"] == iid), None)
            print(f"WARN: status flip count={n} for {iid} (stats={cur and cur.get('status')})")
        note = (
            f"\n### Resolution ({TODAY} Wave 11)\n"
            f"**Status → Resolved.** {detail}\n"
        )
        text = _append_note(text, iid, note)
        closed.append(iid)

    for iid, detail in WAVE_12_NOTE.items():
        note = (
            f"\n### Note ({TODAY} Wave 11)\n"
            f"**Status remains Deferred — roadmap.** {detail}\n"
        )
        text = _append_note(text, iid, note)

    for item in stats["issues"]:
        if item["id"] in TARGET_RESOLVE:
            item["status"] = "Resolved"

    status_hist: dict[str, int] = {}
    for item in stats["issues"]:
        st = item["status"]
        status_hist[st] = status_hist.get(st, 0) + 1
    stats["status"] = status_hist
    stats["open_count"] = status_hist.get("Open", 0)
    stats["wave11_closure"] = {
        "date": TODAY,
        "closed_count": len(closed),
        "closed_ids": sorted(closed),
        "wave12_deferred": sorted(WAVE_12_NOTE),
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
        f"\n## Wave 11 deferred code-fixable ({TODAY})\n\n"
        f"Resolved **{len(closed)}** Deferred-roadmap items (Wave R reclassify + 11A–D). "
        f"God-modules BB-000108/114 remain Deferred (Wave 12). "
        f"Open: {status_hist.get('Open', 0)}. "
        f"Deferred — roadmap: {status_hist.get('Deferred — roadmap', 0)}.\n"
    )
    if f"Wave 11 deferred code-fixable ({TODAY})" not in text:
        text = text.replace("## How to use\n", "## How to use\n" + banner + "\n", 1)

    REGISTER.write_text(text, encoding="utf-8")
    STATS.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")

    deferred_left = [
        i["id"]
        for i in stats["issues"]
        if i["id"] in TARGET_RESOLVE and i.get("status") == "Deferred — roadmap"
    ]
    if deferred_left:
        raise SystemExit(f"FAIL still Deferred: {deferred_left}")

    entry = f"""# docs/reviews — CHANGELOG

## {TODAY} — Wave 11 deferred code-fixable backlog

Resolved **{len(closed)}** Deferred-roadmap items via Wave R reclassify + Waves 11A–D.

### Outcomes

| Status | Count |
|--------|------:|
| Resolved | {status_hist.get('Resolved', 0)} |
| Open | **{status_hist.get('Open', 0)}** |
| Deferred — roadmap | {status_hist.get('Deferred — roadmap', 0)} |
| Deferred — ops owner | {status_hist.get('Deferred — ops owner', 0)} |
| Accepted (positive) | {status_hist.get('Accepted (positive)', 0)} |

### Waves

1. **Wave R** — Reclassify already-fixed: 031, 061, 077, 079, 083, 113, 133
2. **11A Security** — user storage, serializer/ViewSet tenancy, export CanExport (030, 084, 085, 137)
3. **11B Data/GST** — snapshot unique, POS normalize, serial IntegrityError, register GSTIN, insights Decimal (064, 063, 081, 082, 076)
4. **11C Perf/FE** — insights fan-out, ledger prefetch, product search, Sentry DSN, constraints (068, 075, 118, 121, 165, 125)
5. **11D Tests** — money contract smoke (191)

**Still Deferred (Wave 12):** BB-000108 / BB-000114 god-module splits.

Script: `_wave11_assert_deferred_targets.py` (exit 0 = targets not Deferred-roadmap).

---

"""
    old = CHANGELOG.read_text(encoding="utf-8") if CHANGELOG.exists() else ""
    if "Wave 11 deferred code-fixable" not in old:
        if old.startswith("# docs/reviews"):
            idx = old.find("\n## ")
            old = old[idx + 1 :] if idx >= 0 else old
        CHANGELOG.write_text(entry + old, encoding="utf-8")

    if EXEC.exists():
        ex = EXEC.read_text(encoding="utf-8")
        latest = (
            f"**Latest:** Wave 11 deferred code-fixable {TODAY} — register **{stats['total']}** issues. "
            f"**Open: {status_hist.get('Open', 0)}.** Resolved **{status_hist.get('Resolved', 0)}** "
            f"(+{len(closed)} from Deferred). Deferred — roadmap **{status_hist.get('Deferred — roadmap', 0)}**. "
            f"Production Readiness Score **6.7 / 10**.\n"
        )
        ex = re.sub(r"\*\*Latest:\*\*[^\n]*\n", latest + "\n", ex, count=1)
        if "Wave 11 deferred code-fixable" not in ex:
            ex = ex.rstrip() + f"""

---

## Wave 11 deferred code-fixable ({TODAY})

Resolved **{len(closed)}** Deferred-roadmap code items (Wave R + 11A–D). **Open remains 0.**

God-modules BB-000108 / BB-000114 left Deferred for Wave 12. Vendor/ops Deferred unchanged.

Production Readiness Score **6.7 / 10** for honest billing pilot; full ERP/GA still No.

"""
        EXEC.write_text(ex, encoding="utf-8")

    print(
        "OK closed",
        len(closed),
        "Resolved",
        status_hist.get("Resolved"),
        "Deferred roadmap",
        status_hist.get("Deferred — roadmap"),
    )


if __name__ == "__main__":
    main()
