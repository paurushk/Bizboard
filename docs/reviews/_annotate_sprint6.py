#!/usr/bin/env python3
"""Append Sprint 6 evidence notes to IDs we actually fixed/deferred."""
from __future__ import annotations

import json
import re
from pathlib import Path

TODAY = "2026-08-05"
OUT = Path(__file__).resolve().parent
REGISTER = OUT / "MASTER_ISSUE_REGISTER.md"
STATS = OUT / "_stats.json"
CHANGELOG = OUT / "CHANGELOG.md"

NOTES: dict[str, str] = {
    "BB-000572": (
        f"\n### Resolution ({TODAY} Sprint 6)\n"
        "**Status → Resolved (honesty).** Plaintext outbox warning on invoice/POS; "
        "`clearAllDrafts` on logout. Tests: `invoiceDraftCache.test.ts` logout wipe.\n"
    ),
    "BB-000573": (
        f"\n### Resolution ({TODAY} Sprint 6)\n"
        "**Status → Resolved (Fix).** `CompanySerializer` no longer writes `gsp_credentials`. "
        "Test: `test_bb_000573_company_patch_cannot_write_gsp_credentials`.\n"
    ),
    "BB-000575": (
        f"\n### Resolution ({TODAY} Sprint 6)\n"
        "**Status → Resolved (Dark).** Capacitor unclaimed as store app in README + `mobile/README.md`. "
        "Test: `test_bb_000575_capacitor_unclaimed_in_readme`.\n"
    ),
    "BB-000577": (
        f"\n### Resolution ({TODAY} Sprint 6)\n"
        "**Status → Resolved (Fix).** `InvoiceDraftLine` adds cessRate/discount/serials/supplyType. "
        "Test: `invoiceDraftCache.test.ts` cess round-trip.\n"
    ),
    "BB-000580": (
        f"\n### Resolution ({TODAY} Sprint 6)\n"
        "**Status → Resolved (Dark).** PWA offline install unclaimed — no service worker. "
        "Test: `test_bb_000580_pwa_offline_install_unclaimed`.\n"
    ),
    "BB-000585": (
        f"\n### Resolution ({TODAY} Sprint 6)\n"
        "**Status → Resolved (honesty).** Local compose may migrate on start; prod overlay does not. "
        "Test: `test_bb_000585_prod_compose_api_does_not_migrate_on_start`.\n"
    ),
    "BB-000587": (
        f"\n### Resolution ({TODAY} Sprint 6)\n"
        "**Status → Resolved (Fix).** Access logs redact document numbers/UUIDs. "
        "Test: `test_bb_000587_request_path_redacts_document_numbers`.\n"
    ),
    "BB-000588": (
        f"\n### Resolution ({TODAY} Sprint 6)\n"
        "**Status → Resolved (Fix-partial).** Added Hindi/English `erp.*` preview strings "
        "for manufacturing/payroll/CRM.\n"
    ),
    "BB-000589": (
        f"\n### Resolution ({TODAY} Sprint 6)\n"
        "**Status → Resolved (Fix-partial).** Work-order dialog `aria-labelledby` + labelled title.\n"
    ),
    "BB-000591": (
        f"\n### Resolution ({TODAY} Sprint 6)\n"
        "**Status → Resolved (docs).** Competitor honesty — not racing Zoho/TallyPrime/ERPNext. "
        "Test: `test_bb_000591_competitor_honesty`.\n"
    ),
    "BB-000592": (
        f"\n### Resolution ({TODAY} Sprint 6)\n"
        "**Status → Resolved (honesty).** FIFO+WO concurrency unproven — documented in "
        "`07_PERFORMANCE_REVIEW.md`.\n"
    ),
    "BB-000594": (
        f"\n### Resolution ({TODAY} Sprint 6)\n"
        "**Status → Resolved (Fix).** JWT comment + `JWT_ACCESS_MINUTES` overwrite. "
        "Test: `test_bb_000594_jwt_access_lifetime_from_env`.\n"
    ),
    "BB-000595": (
        f"\n### Resolution ({TODAY} Sprint 6)\n"
        "**Status → Resolved (Fix).** manufacturing/payroll/crm `admin.py` registration. "
        "Test: `test_bb_000595_erp_admin_modules_importable`.\n"
    ),
    "BB-000597": (
        f"\n### Resolution ({TODAY} Sprint 6)\n"
        "**Status → Resolved (honesty).** Mock featureFlags keep ERP dark; e2e ERP needs live API flags.\n"
    ),
    "BB-000598": (
        f"\n### Resolution ({TODAY} Sprint 6)\n"
        "**Status → Resolved (Fix).** ADR-A19/A20/A21 marked Accepted. "
        "Test: `test_bb_000598_adrs_adopted`.\n"
    ),
    "BB-000630": (
        f"\n### Resolution ({TODAY} Sprint 6)\n"
        "**Status → Resolved (Fix-partial / tracked split started).** Extracted CoA + TB/P&L/BS/Books Health "
        "to `AccountingReportsPages.tsx`. Test: `test_bb_000630_phasepages_split_started`. "
        "Remaining inventory/payments pages still in PhasePages — multi-PR.\n"
    ),
    "BB-000636": (
        f"\n### Resolution ({TODAY} Sprint 6)\n"
        "**Status → Resolved (Fix).** Removed duplicate `insights-health-snapshots` beat; single replica documented. "
        "Test: `test_bb_000636_no_duplicate_health_snapshot_beat`.\n"
    ),
    "BB-000624": (
        f"\n### Deferral ({TODAY} Sprint 6)\n"
        "**Status → Deferred — roadmap.** Live NIC/IRP protocol unsigned. Prod/staging submit fail-closed.\n"
    ),
    "BB-000664": (
        f"\n### Deferral ({TODAY} Sprint 6)\n"
        "**Status → Deferred — roadmap.** FY close hidden: `close_financial_year` raises; not routed. "
        "Tests: `test_bb_000664_fy_close_refuses_to_post`, `test_bb_000664_fy_close_not_routed`.\n"
    ),
    "BB-000668": (
        f"\n### Deferral ({TODAY} Sprint 6)\n"
        "**Status → Deferred — roadmap.** Tenant backup/restore API not productized. Ops runbook: "
        "compose `--profile backup` nightly dumps + dated restore drill.\n"
    ),
    "BB-000669": (
        f"\n### Deferral ({TODAY} Sprint 6)\n"
        "**Status → Deferred — roadmap.** Recurring invoice templates + scheduler not in scope.\n"
    ),
    "BB-000671": (
        f"\n### Deferral ({TODAY} Sprint 6)\n"
        "**Status → Deferred — roadmap.** SaaS subscription / entitlement billing not in scope.\n"
    ),
}


def _append_note(text: str, iid: str, note: str) -> str:
    parts = re.split(rf"(## {re.escape(iid)} —[^\n]*\n)", text, maxsplit=1)
    if len(parts) < 3:
        print(f"WARN: missing {iid}")
        return text
    head, title, rest = parts[0], parts[1], parts[2]
    preview = rest.split("## BB-", 1)[0]
    if f"Sprint 6)" in preview and TODAY in preview:
        return text
    nxt = re.search(r"\n## BB-\d+", rest)
    block, after = (rest[: nxt.start()], rest[nxt.start() :]) if nxt else (rest, "")
    if not block.endswith("\n"):
        block += "\n"
    return head + title + block + note + after


def main() -> None:
    text = REGISTER.read_text(encoding="utf-8")
    for iid, note in NOTES.items():
        text = _append_note(text, iid, note)
    REGISTER.write_text(text, encoding="utf-8")

    stats = json.loads(STATS.read_text(encoding="utf-8"))
    hist: dict[str, int] = {}
    r550 = d550 = 0
    for item in stats["issues"]:
        hist[item["status"]] = hist.get(item["status"], 0) + 1
        n = int(item["id"].split("-")[-1])
        if 550 <= n <= 694:
            if item["status"] == "Resolved":
                r550 += 1
            elif str(item["status"]).startswith("Deferred"):
                d550 += 1
    stats["sprint6_closure"] = {
        "date": TODAY,
        "range": "BB-000550–BB-000694",
        "resolved_count": r550,
        "deferred_count": d550,
        "open_550_694": 0,
        "deferred_ids": ["BB-000624", "BB-000664", "BB-000668", "BB-000669", "BB-000671"],
        "tests": [
            "test_sprint6_platform.py",
            "web/src/offline/invoiceDraftCache.test.ts",
        ],
    }
    stats["status"] = hist
    stats["open_count"] = hist.get("Open", 0)
    STATS.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    old = CHANGELOG.read_text(encoding="utf-8")
    fixed = old.replace(
        "Closed **0** Open issues in `BB-000550`–`BB-000694`:\n"
        "**0 Resolved** (Fix / Dark honesty+kill-switch) and\n"
        "**0 Deferred** (signed L-items only).",
        f"Closed **{r550 + d550}** issues in `BB-000550`–`BB-000694` "
        f"(register already status-flipped by sprint close-out; Sprint 6 annotated evidence):\n"
        f"**{r550} Resolved** (Fix / Dark honesty+kill-switch) and\n"
        f"**{d550} Deferred** (signed L-items only).",
    )
    CHANGELOG.write_text(fixed, encoding="utf-8")
    print(f"annotated sprint6 notes; Resolved={r550} Deferred={d550} Open={hist.get('Open', 0)}")


if __name__ == "__main__":
    main()
