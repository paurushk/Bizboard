#!/usr/bin/env python3
"""Wave 0: Mark deferred ops/roadmap issues in MASTER_ISSUE_REGISTER.md."""
from __future__ import annotations

import re
from pathlib import Path

REGISTER = Path(__file__).resolve().parent / "MASTER_ISSUE_REGISTER.md"

# Issue IDs that are ops/human — Deferred — ops owner
OPS = {
    "BB-000015",  # TLS termination (certs) — code half separate
    "BB-000186",  # chaos/failover drill
}

# Titles/patterns that imply ops or process (matched by ID from full list)
OPS_EXTRA = set()  # filled from title scan below

# Issue IDs that are roadmap / vendor / ERP scope
ROADMAP = {
    "BB-000005",  # live GSP — code half is sandbox gate; mark roadmap for live NIC, resolve code later as partial
    "BB-000006",  # real SMS vendor — code fail-closed; vendor onboarding deferred
    "BB-000009",  # full 2B matching — provisional labels are code; engine deferred
    "BB-000036",  # missing Manufacturing/Payroll/CRM/multi-company — product claim
    "BB-000045",  # no GSTR-2A/2B module
    "BB-000049",  # GSTR-9 full annual
    "BB-000050",  # CMP-08
    "BB-000177",  # no mobile native
    "BB-000178",  # no offline
    "BB-000179",  # no POS mode — can be deferred
    "BB-000180",  # competitor Tally
    "BB-000181",  # competitor Zoho bank feeds
    "BB-000182",  # competitor ERPNext manufacturing
    "BB-000183",  # pen-test
    "BB-000184",  # chaos already in OPS
    "BB-000190",  # OpenAPI generate FE client — large, defer if needed
    "BB-000039",  # no cess
    "BB-000040",  # no SEZ/export
}

# BB-000014: split — signatures deferred; code flags stay open until Wave 1
# We'll add a note on BB-000014 rather than full Deferred

DEFERRED_NOTE_OPS = (
    "\n\n### Resolution (2026-08-02 Scope C Wave 0)\n"
    "**Status → Deferred — ops owner.** Not code-closable in this cycle "
    "(infra/human gate). Engineering backlog treats as decided-deferred.\n"
)

DEFERRED_NOTE_ROADMAP = (
    "\n\n### Resolution (2026-08-02 Scope C Wave 0)\n"
    "**Status → Deferred — roadmap.** Out of Scope C code program "
    "(vendor contract, multi-quarter product, or GA-only work). "
    "Code honesty gates / stubs may still land in later waves.\n"
)


def set_status(block: str, new_status: str) -> str:
    return re.sub(
        r"(\| \*\*Status\*\* \| )Open( \|)",
        rf"\1{new_status}\2",
        block,
        count=1,
    )


def main() -> None:
    text = REGISTER.read_text(encoding="utf-8")

    # Split into header + issues
    parts = re.split(r"(?=^## BB-\d+)", text, flags=re.M)
    header, *issue_blocks = parts

    # Title-based classification for remaining
    title_ops_keywords = (
        "tls termination",
        "go/no-go",
        "ca letter",
        "backup",
        "pen-test",
        "dpdp",
        "restore drill",
        "chaos",
        "failover drill",
        "unsigned while ui",
    )
    title_roadmap_keywords = (
        "manufacturing",
        "payroll",
        "crm",
        "multi-company",
        "multi-branch",
        "whatsapp business",
        "native mobile",
        "gstr-2a",
        "gstr-2b",
        "cmp-08",
        "live gsp",
        "sandbox-only (fake",
        "no cess",
        "sez / export",
        "no pos",
        "offline-first",
        "erpnext",
        "zoho books bank",
        "tallyprime local",
        "pen-test",
        "openapi not used to generate",
        "sms provider is console",  # vendor half
        "itc = all purchase",  # 2b engine half - keep open for provisional label wave
    )

    # For BB-000005, 006, 009: Wave 0 marks roadmap for the non-code half;
    # Wave 1+ will resolve code halves and may change status to Resolved for gate work.
    # Per plan: "Keep code halves Open until fixed". So BB-000005/006/009 stay Open for now.
    # Only fully non-code items get Deferred now.

    stay_open_for_code = {
        "BB-000005",  # sandbox gate in W1
        "BB-000006",  # fail-closed + hash in W1
        "BB-000009",  # provisional labels in W3
        "BB-000014",  # feature flags in W1
        "BB-000015",  # USE_TLS settings in W1; certs deferred — split note
    }

    pure_ops = {
        "BB-000183",  # pen-test
        "BB-000186",  # chaos
    }
    pure_roadmap = {
        "BB-000036",
        "BB-000039",
        "BB-000040",
        "BB-000045",
        "BB-000049",
        "BB-000050",
        "BB-000177",
        "BB-000178",
        "BB-000179",
        "BB-000180",
        "BB-000181",
        "BB-000182",
        "BB-000190",
    }

    # Scan all issues for title matches
    for block in issue_blocks:
        m = re.match(r"## (BB-\d+) — (.+)", block)
        if not m:
            continue
        iid, title = m.group(1), m.group(2).lower()
        if iid in stay_open_for_code:
            continue
        if any(k in title for k in title_ops_keywords) or iid in pure_ops:
            pure_ops.add(iid)
        if any(k in title for k in title_roadmap_keywords) or iid in pure_roadmap:
            # Don't double-count if also in stay_open
            if iid not in stay_open_for_code:
                pure_roadmap.add(iid)

    # BB-000015: add deferred note for certs but keep status for USE_TLS code — actually plan says
    # Deferred ops for TLS certs. Mark Deferred — ops owner and Wave 1 still does USE_TLS settings.
    pure_ops.add("BB-000015")

    # Remove overlaps: prefer ops over roadmap
    pure_roadmap -= pure_ops
    pure_roadmap -= stay_open_for_code
    pure_ops -= stay_open_for_code

    new_blocks = []
    counts = {"ops": 0, "roadmap": 0, "open": 0}
    for block in issue_blocks:
        m = re.match(r"## (BB-\d+)", block)
        if not m:
            new_blocks.append(block)
            continue
        iid = m.group(1)
        if "Resolution (2026-08-02 Scope C Wave 0)" in block:
            new_blocks.append(block)
            continue
        if iid in pure_ops:
            b = set_status(block, "Deferred — ops owner")
            if not b.rstrip().endswith(DEFERRED_NOTE_OPS.strip()[:40]):
                b = b.rstrip() + DEFERRED_NOTE_OPS
            new_blocks.append(b + "\n")
            counts["ops"] += 1
        elif iid in pure_roadmap:
            b = set_status(block, "Deferred — roadmap")
            b = b.rstrip() + DEFERRED_NOTE_ROADMAP
            new_blocks.append(b + "\n")
            counts["roadmap"] += 1
        else:
            counts["open"] += 1
            new_blocks.append(block)

    # Add Wave 0 banner to header
    banner = (
        "\n## Scope C Wave 0 triage (2026-08-02)\n\n"
        "Non-code issues marked `Deferred — ops owner` or `Deferred — roadmap`. "
        "Remaining `Open` items are in the code remediation waves.\n\n"
        f"- Deferred ops: {counts['ops']}\n"
        f"- Deferred roadmap: {counts['roadmap']}\n"
        f"- Still Open (code program): {counts['open']}\n"
    )
    if "Scope C Wave 0 triage" not in header:
        # Insert after How to use section totals — after first --- or at end of header
        header = header.rstrip() + "\n" + banner + "\n"

    REGISTER.write_text(header + "".join(new_blocks), encoding="utf-8")
    print(f"Wave 0 done: ops={counts['ops']} roadmap={counts['roadmap']} open={counts['open']}")
    print("OPS:", sorted(pure_ops))
    print("ROADMAP:", sorted(pure_roadmap))


if __name__ == "__main__":
    main()
