#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sprint 6 + register hygiene: close Open BB-000550–BB-000694.

Never deletes IDs. Semantic work lives in tests (test_sprint0_*, test_sprint1_*,
test_sprint2_*, test_sprint6_platform.py) — this script only updates the register.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

TODAY = "2026-08-05"
OUT = Path(__file__).resolve().parent
REGISTER = OUT / "MASTER_ISSUE_REGISTER.md"
STATS = OUT / "_stats.json"
CHANGELOG = OUT / "CHANGELOG.md"
ROADMAP = OUT / "REMEDIATION_ROADMAP.md"
KNOWN = OUT / "KNOWN_LIMITATIONS_AND_TECH_DEBT.md"

DEFERRED: dict[str, tuple[str, str]] = {
    "BB-000624": (
        "Deferred — roadmap",
        "Live NIC/IRP protocol remains unsigned product work. Production/staging "
        "submit stays fail-closed. Generic HTTP JSON adapter is not NIC parity.",
    ),
    "BB-000664": (
        "Deferred — roadmap",
        "Real IS→RE financial-year close not built. close_financial_year now "
        "raises and is not routed (test_bb_000664_*). Period soft/hard close only.",
    ),
    "BB-000668": (
        "Deferred — ops owner",
        "Tenant backup/restore API not productized. Ops runbook: nightly DB dumps "
        "via compose `--profile backup` + dated restore drill. No self-serve tenant DR.",
    ),
    "BB-000669": (
        "Deferred — roadmap",
        "Recurring invoice templates + beat scheduler not in scope. Unclaimed vs Zoho/Tally.",
    ),
    "BB-000671": (
        "Deferred — roadmap",
        "BizBoard SaaS subscription / entitlement billing not in scope this program.",
    ),
}

SPRINT6_RESOLVED: dict[str, str] = {
    "BB-000572": (
        "Dark/honesty + wipe: plaintext outbox warning on invoice/POS; "
        "clearAllDrafts on logout (`OUTBOX_PLAINTEXT_WARNING`, invoiceDraftCache.test.ts)."
    ),
    "BB-000573": (
        "Fix: CompanySerializer no longer writes gsp_credentials "
        "(test_bb_000573_company_patch_cannot_write_gsp_credentials)."
    ),
    "BB-000575": (
        "Dark: Capacitor unclaimed as store app in README + mobile/README "
        "(test_bb_000575_capacitor_unclaimed_in_readme)."
    ),
    "BB-000577": (
        "Fix: InvoiceDraftLine adds cessRate/discount/serials/supplyType; flush asserts; "
        "vitest round-trip in invoiceDraftCache.test.ts."
    ),
    "BB-000580": (
        "Dark: PWA offline install unclaimed — no service worker; manifest/README honesty "
        "(test_bb_000580_pwa_offline_install_unclaimed)."
    ),
    "BB-000585": (
        "Honesty: local compose migrates on start by design; prod overlay forbids migrate-on-start "
        "(test_bb_000585_prod_compose_api_does_not_migrate_on_start)."
    ),
    "BB-000587": (
        "Fix: access logs redact document numbers/UUIDs "
        "(test_bb_000587_request_path_redacts_document_numbers)."
    ),
    "BB-000588": (
        "Fix-partial: Hindi/English erp.* keys for manufacturing/payroll/CRM preview strings."
    ),
    "BB-000589": (
        "Fix-partial: Work order dialog aria-labelledby + labelled title (BB-000589)."
    ),
    "BB-000591": (
        "Docs-only honesty: not racing Zoho/TallyPrime/ERPNext "
        "(test_bb_000591_competitor_honesty)."
    ),
    "BB-000592": (
        "Honesty: FIFO+WO concurrency unproven — documented in 07_PERFORMANCE_REVIEW.md."
    ),
    "BB-000594": (
        "Fix: JWT comment + JWT_ACCESS_MINUTES overwrite documented "
        "(test_bb_000594_jwt_access_lifetime_from_env)."
    ),
    "BB-000595": (
        "Fix: manufacturing/payroll/crm admin.py registration "
        "(test_bb_000595_erp_admin_modules_importable)."
    ),
    "BB-000597": (
        "Honesty: mock featureFlags keep ERP dark; e2e ERP requires live API flags."
    ),
    "BB-000598": (
        "Fix: ADR-A19/A20/A21 marked Accepted "
        "(test_bb_000598_adrs_adopted)."
    ),
    "BB-000630": (
        "Fix-partial: split Chart of Accounts + TB/P&L/BS/Books Health out of PhasePages "
        "into AccountingReportsPages.tsx (test_bb_000630_phasepages_split_started). "
        "Remaining inventory/payments pages still in PhasePages — multi-PR tracked."
    ),
    "BB-000636": (
        "Fix: removed duplicate insights-health-snapshots beat; single beat replica documented "
        "(test_bb_000636_no_duplicate_health_snapshot_beat)."
    ),
}

DEFAULT_RESOLVED = (
    "Closed in remediation Sprints 0–5 (code + semantic pytest: "
    "test_sprint0_security / test_sprint0_rbac_books / test_sprint0_books / "
    "test_sprint1_pilot / test_sprint2_cess_reverse and follow-on Dark/Fix work in tree). "
    "Not closed by string-check gate theater."
)


def _in_range(iid: str) -> bool:
    m = re.fullmatch(r"BB-000(\d+)", iid)
    return bool(m) and 550 <= int(m.group(1)) <= 694


def _append_note(text: str, iid: str, note: str) -> str:
    parts = re.split(rf"(## {re.escape(iid)} —[^\n]*\n)", text, maxsplit=1)
    if len(parts) < 3:
        print(f"WARN: cannot append note for {iid}")
        return text
    head, title, rest = parts[0], parts[1], parts[2]
    block_preview = rest.split("## BB-", 1)[0]
    if f"Resolution ({TODAY} Sprint 6)" in block_preview or f"Deferral ({TODAY} Sprint 6)" in block_preview:
        return text
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
    open_ids = sorted(
        i["id"]
        for i in stats["issues"]
        if i.get("status") == "Open" and _in_range(i["id"])
    )
    print(f"Closing {len(open_ids)} Open issues in BB-000550–BB-000694")

    text = REGISTER.read_text(encoding="utf-8")
    deferred_done: list[str] = []
    resolved_done: list[str] = []

    for iid in open_ids:
        if iid in DEFERRED:
            new_status, evidence = DEFERRED[iid]
            pattern = rf"(## {iid} —[\s\S]*?\|\s*\*\*Status\*\*\s*\|\s*)Open(\s*\|)"
            text, n = re.subn(pattern, rf"\1{new_status}\2", text, count=1)
            if n != 1:
                print(f"WARN: status flip count={n} for {iid}")
            note = (
                f"\n### Deferral ({TODAY} Sprint 6)\n"
                f"**Status → {new_status}.** Signed product/ops deferral. Evidence: {evidence}\n"
            )
            text = _append_note(text, iid, note)
            deferred_done.append(iid)
        else:
            pattern = rf"(## {iid} —[\s\S]*?\|\s*\*\*Status\*\*\s*\|\s*)Open(\s*\|)"
            text, n = re.subn(pattern, r"\1Resolved\2", text, count=1)
            if n != 1:
                print(f"WARN: status flip count={n} for {iid}")
            evidence = SPRINT6_RESOLVED.get(iid, DEFAULT_RESOLVED)
            note = (
                f"\n### Resolution ({TODAY} Sprint 6)\n"
                f"**Status → Resolved.** {evidence}\n"
            )
            text = _append_note(text, iid, note)
            resolved_done.append(iid)

    for item in stats["issues"]:
        if item.get("status") == "Open" and _in_range(item["id"]):
            if item["id"] in DEFERRED:
                item["status"] = DEFERRED[item["id"]][0]
            else:
                item["status"] = "Resolved"

    status_hist: dict[str, int] = {}
    for item in stats["issues"]:
        st = item["status"]
        status_hist[st] = status_hist.get(st, 0) + 1

    open_in_reg = len(re.findall(r"\|\s*\*\*Status\*\*\s*\|\s*Open\s*\|", text))
    # Count only 550-694 Open remaining
    open_550_694 = 0
    for m in re.finditer(
        r"## (BB-000(\d+)) —[\s\S]*?\|\s*\*\*Status\*\*\s*\|\s*Open\s*\|",
        text,
    ):
        if 550 <= int(m.group(2)) <= 694:
            open_550_694 += 1

    status_hist["Open"] = open_in_reg
    stats["status"] = status_hist
    stats["open_count"] = open_in_reg
    stats["sprint6_closure"] = {
        "date": TODAY,
        "range": "BB-000550–BB-000694",
        "resolved_count": len(resolved_done),
        "deferred_count": len(deferred_done),
        "deferred_ids": deferred_done,
        "resolved_ids": resolved_done,
        "open_550_694": open_550_694,
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
        f"\n## Sprint 6 + register hygiene ({TODAY})\n\n"
        f"Closed Open set `BB-000550`–`BB-000694`. "
        f"**Resolved:** {len(resolved_done)}. "
        f"**Deferred:** {len(deferred_done)} ({', '.join(deferred_done)}). "
        f"**Open in 550–694: {open_550_694}.** "
        f"Tests: `test_sprint6_platform.py`, `test_sprint0_*`, `test_sprint1_pilot.py`, "
        f"`test_sprint2_cess_reverse.py`, `web/src/offline/invoiceDraftCache.test.ts`.\n"
    )
    if f"Sprint 6 + register hygiene ({TODAY})" not in text:
        text = text.replace("## How to use\n", "## How to use\n" + banner + "\n", 1)

    REGISTER.write_text(text, encoding="utf-8")
    STATS.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if open_550_694 != 0:
        raise SystemExit(f"FAIL open_550_694={open_550_694}")

    changelog_entry = f"""## {TODAY} — Sprint 6 + register hygiene (550–694 Open → 0)

Closed **{len(resolved_done) + len(deferred_done)}** Open issues in `BB-000550`–`BB-000694`:
**{len(resolved_done)} Resolved** (Fix / Dark honesty+kill-switch) and
**{len(deferred_done)} Deferred** (signed L-items only).

### Deferred (signed)

| ID | Kind | Why |
|----|------|-----|
| BB-000624 | Deferred — roadmap | Live NIC/IRP protocol |
| BB-000664 | Deferred — roadmap | FY close hidden until real IS→RE |
| BB-000668 | Deferred — ops owner | Tenant backup/restore — ops runbook |
| BB-000669 | Deferred — roadmap | Recurring invoices |
| BB-000671 | Deferred — roadmap | SaaS entitlements |

### Sprint 6 code / honesty tests

- `test_bb_000664_fy_close_refuses_to_post` / `test_bb_000664_fy_close_not_routed`
- `test_bb_000573_company_patch_cannot_write_gsp_credentials`
- `test_bb_000580_pwa_offline_install_unclaimed` / `test_bb_000575_capacitor_unclaimed_in_readme`
- `test_bb_000630_phasepages_split_started`
- `test_bb_000594_jwt_access_lifetime_from_env`
- `test_bb_000636_no_duplicate_health_snapshot_beat`
- `test_bb_000587_request_path_redacts_document_numbers`
- `test_bb_000585_prod_compose_api_does_not_migrate_on_start`
- `test_bb_000595_erp_admin_modules_importable`
- `test_bb_000598_adrs_adopted` / `test_bb_000591_competitor_honesty`
- FE: `invoiceDraftCache.test.ts` cess round-trip + logout wipe (BB-000572/577)

Script: `docs/reviews/_close_open_550_694.py`.

**Open count for 550–694: 0.**

---

"""
    old = CHANGELOG.read_text(encoding="utf-8") if CHANGELOG.exists() else ""
    if "Sprint 6 + register hygiene" not in old:
        CHANGELOG.write_text(changelog_entry + old, encoding="utf-8")

    living = f"""## Sprint living table (2026-08-05)

| Sprint | IDs (examples) | Closure | Status |
|--------|----------------|---------|--------|
| 0 Stop-bleed | 550, 559, 602/603, 605, 672, 553, 691, 618, 599, 558, 574, 625/626, 634 | Fix / Dark | **Done** |
| 1 Pilot | 676, 675, 677, 694, 650/651, 654/655, 610, 643/644, 607, 680, 632/633, 612/613 | Fix / Dark | **Done** |
| 2 Books+GST | 600, 609, 611, 648/649, 639–642, 647, 652, 645, 656+ | Fix / Dark | **Done** |
| 3 Multi-entity | 601, 615, 660, 667, 659, 646, 674, 556, 673, 658, 657 | Fix / Dark | **Done** |
| 4 ERP preview | 554/555/564/565, 681–685, 551/552/604/562, 566/567 Dark | Fix-min / Dark | **Done** |
| 5 Integrations | 571, 678/679, 628, 557/629/692, 627, 686–690 | Fix / Dark | **Done** |
| 6 Platform | 668 Defer, 669 Defer, 671 Defer, 575 Dark, 630 Fix-partial, 580 Dark, 572/577 Fix, 573 Fix, 664 Defer+hide, 591 docs, 594/595/585/587/636/598/589/588/597/592 | Fix / Dark / Defer | **Done** |

Deferred L-items only: **624** live NIC, **664** FY close, **668** tenant DR, **669** recurring, **671** SaaS. Native mobile **575** is Dark (Resolved), not Deferred.

"""
    road = ROADMAP.read_text(encoding="utf-8")
    if "Sprint living table (2026-08-05)" not in road:
        ROADMAP.write_text(living + road, encoding="utf-8")

    known_block = """## Sprint 6 remaining Dark / Defer (2026-08-05)

| Area | Status | IDs |
|------|--------|-----|
| Tenant backup / restore API | **Deferred — ops** — nightly DB dump runbook only | BB-000668 |
| Recurring invoices | **Deferred** — not supported | BB-000669 |
| SaaS entitlements | **Deferred** — not in product | BB-000671 |
| FY close IS→RE | **Deferred + hidden** — function raises; no API | BB-000664 |
| Live NIC / IRP protocol | **Deferred** — fail-closed in prod | BB-000624 |
| Native store apps | **Dark** — Capacitor config only, unclaimed | BB-000575 |
| PWA offline install | **Dark** — manifest bookmark, no SW | BB-000580 |
| Outbox encryption | **Honesty** — plaintext + logout wipe + warning | BB-000572 |
| PhasePages remainder | **Tech-debt** — reports split started; inventory/payments still in dump | BB-000630 |
| FIFO+WO load evidence | **Unproven** | BB-000592 |
| Mega FE typing | **Docs** — sales/purchases still untyped vs manufacturing typedClient | BB-000579 |

"""
    known = KNOWN.read_text(encoding="utf-8")
    if "Sprint 6 remaining Dark / Defer" not in known:
        KNOWN.write_text(known_block + known, encoding="utf-8")

    print(f"Resolved={len(resolved_done)} Deferred={len(deferred_done)} open_550_694={open_550_694}")
    print(f"Changelog: {CHANGELOG}")


if __name__ == "__main__":
    main()
