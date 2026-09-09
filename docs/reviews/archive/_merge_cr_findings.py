"""Merge module drafts into permanent CR-NNN findings document."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parent


def sev_norm(s: str) -> str:
    s = (s or "").strip().lower()
    if "blocker" in s or "critical" in s:
        return "Critical"
    if "high" in s:
        return "High"
    if "medium" in s or "low–medium" in s or "low-medium" in s:
        return "Medium"
    if "low" in s:
        return "Low"
    if "info" in s or "pass" in s:
        return "Info"
    return "Medium"


def parse_dash_findings(text: str, prefix: str):
    pat = re.compile(
        rf"(### {prefix}-\d{{3}} — .+?)(?=\n### {prefix}-\d{{3}} — |\n## |\Z)",
        re.S,
    )
    out = []
    for m in pat.finditer(text):
        block = m.group(1).strip()
        title_m = re.match(rf"### ({prefix}-\d{{3}}) — (.+)", block)
        if not title_m:
            continue
        pid, title = title_m.group(1), title_m.group(2).strip()
        sev_m = re.search(r"\*\*Severity:\*\*\s*(.+)", block)
        sev = sev_norm(sev_m.group(1) if sev_m else "")
        if sev == "Info" or re.search(r"Info / pass|mostly pass", block, re.I):
            continue
        out.append((pid, title, sev, block))
    return out


def parse_table_findings(text: str, prefix: str):
    # ACC drafts use ##; PUR/STK use ###. Escape braces for f-string → regex quantifier.
    pat = re.compile(
        rf"(#{{2,3}} {prefix}-\d{{3}}(?:\s|$|[^\n]*).+?)(?=\n#{{2,3}} {prefix}-\d{{3}}|\n## [A-Za-z]|\n# |\Z)",
        re.S,
    )
    out = []
    for m in pat.finditer(text):
        block = m.group(1).strip()
        title_m = re.match(rf"#{{2,3}} ({prefix}-\d{{3}})(?:\s*[—\-]\s*(.+))?", block)
        if not title_m:
            continue
        pid = title_m.group(1)
        title = (title_m.group(2) or "").strip()
        if not title:
            tm = re.search(r"\|\s*\*\*Area\*\*\s*\|\s*(.+?)\s*\|", block)
            title = tm.group(1).strip() if tm else pid
        if title == pid or not title:
            first = re.search(r"\*\*What's wrong\*\*\s*\|\s*(.+?)\s*\|", block)
            if first:
                title = first.group(1).strip()[:80]
            else:
                im = re.search(r"\|\s*\*\*Impact\*\*\s*\|\s*(.+?)\s*\|", block)
                if im:
                    title = im.group(1).strip()[:80]
        sev_m = re.search(r"\|\s*\*\*Severity\*\*\s*\|\s*(.+?)\s*\|", block)
        sev = sev_norm(sev_m.group(1) if sev_m else "")
        if sev == "Info" or re.search(r"Info / pass|mostly pass", block, re.I):
            continue
        out.append((pid, title, sev, block))
    return out


def main() -> None:
    rpt_path = root / "_draft_Reporting.md"
    rpt_body = rpt_path.read_text(encoding="utf-8") if rpt_path.exists() else ""

    all_findings = []
    all_findings += [
        ("POS",) + x
        for x in parse_dash_findings(
            (root / "_draft_POS.md").read_text(encoding="utf-8"), "POS"
        )
    ]
    all_findings += [
        ("Sales",) + x
        for x in parse_dash_findings(
            (root / "_draft_Sales.md").read_text(encoding="utf-8"), "SALES"
        )
    ]
    all_findings += [
        ("Purchase",) + x
        for x in parse_table_findings(
            (root / "_draft_Purchase.md").read_text(encoding="utf-8"), "PUR"
        )
    ]
    all_findings += [
        ("Stock/Godown",) + x
        for x in parse_table_findings(
            (root / "_draft_Stock.md").read_text(encoding="utf-8"), "STK"
        )
    ]
    all_findings += [("Reporting",) + x for x in parse_dash_findings(rpt_body, "RPT")]
    all_findings += [
        ("Accounting",) + x
        for x in parse_table_findings(
            (root / "_draft_Accounting.md").read_text(encoding="utf-8"), "ACC"
        )
    ]

    seen = set()
    uniq = []
    for f in all_findings:
        if f[1] in seen:
            continue
        seen.add(f[1])
        uniq.append(f)
    all_findings = uniq

    counts = Counter(f[3] for f in all_findings)
    by_mod = Counter(f[0] for f in all_findings)
    print("Total", len(all_findings), dict(counts), dict(by_mod))

    lines = [
        "## Findings",
        "",
        "_Permanent CR-NNN IDs. Provisional module IDs retained in parentheses._",
        "",
    ]
    mapping = []
    for i, (mod, pid, title, sev, block) in enumerate(all_findings, 1):
        cr = f"CR-{i:03d}"
        mapping.append((cr, pid, sev, mod, title))
        body = re.sub(
            rf"^### {re.escape(pid)}[^\n]*",
            f"### {cr} — {title} `({pid})`",
            block,
            count=1,
        )
        if "**Severity:**" in body:
            body = re.sub(r"\*\*Severity:\*\*\s*.+", f"**Severity:** {sev}", body, count=1)
        elif "| **Severity** |" in body:
            body = re.sub(
                r"\|\s*\*\*Severity\*\*\s*\|\s*.+?\s*\|",
                f"| **Severity** | {sev} |",
                body,
                count=1,
            )
        # Ensure Module field for dash forms
        if "**Module:**" not in body and "| **Module** |" not in body:
            body = body.replace(
                f"### {cr} — {title} `({pid})`\n",
                f"### {cr} — {title} `({pid})`\n- **Module:** {mod}\n",
                1,
            )
        lines.append(body)
        lines.append("")

    cr_section = "\n".join(lines)

    matrix = {
        "POS": (
            "create→complete→receipt→thermal (multi-HTTP); offline flush",
            "n/a (cancel via sales)",
            "stock lock on complete; cash key remint",
            "e2e/flush tests; thin cash-retry",
        ),
        "Sales": (
            "SalesService.complete + notes/returns/receipts",
            "cancel / return / CN",
            "return unlock invoice; alloc locked",
            "strong; missing concurrent return",
        ),
        "Purchase": (
            "PurchaseService.complete stock+AP atomic",
            "return / CN / BoE cancel",
            "return unlock invoice",
            "present; CN idempotency thin",
        ),
        "Stock/Godown": (
            "InventoryService.post_movement",
            "transfer cancel / return peels",
            "BLOCK safe; WARN fragmented",
            "concurrency BLOCK covered",
        ),
        "Reporting": (
            "KPIs, registers, GSTR, exports",
            "n/a",
            "n/a",
            "GST footing strong; KPI edges thin",
        ),
        "Accounting": (
            "PostingService.post / document→GL",
            "reverse / note / cancel",
            "period close TOCTOU",
            "books health partial",
        ),
    }
    cr_by_mod: dict[str, list[str]] = {}
    for cr, pid, sev, mod, title in mapping:
        cr_by_mod.setdefault(mod, []).append(cr)

    matrix_md = [
        "## Coverage matrix",
        "",
        "| Module | Core write path reviewed | Reversal path | Concurrency | Tests present | Findings |",
        "|---|---|---|---|---|---|",
    ]
    for mod in ["POS", "Sales", "Purchase", "Stock/Godown", "Reporting", "Accounting"]:
        c, r, co, t = matrix[mod]
        ids = cr_by_mod.get(mod, [])
        id_s = ", ".join(ids[:4])
        if len(ids) > 4:
            id_s += f", … ({len(ids)} total)"
        matrix_md.append(f"| {mod} | {c} | {r} | {co} | {t} | {id_s} |")

    summary = f"""# Functional Code Review — Bizboard (production stabilization)

Run date: 2026-09-06 · Reviewer: Claude · Build: `5ba05c7`

> Permanent **CR-NNN** IDs assigned. Provisional POS-/SALES-/PUR-/STK-/RPT-/ACC-* kept in parentheses.

## Coverage summary

- Modules reviewed: **6/6** — POS, Sales, Purchase, Stock/Godown, Reporting, Accounting
- Findings: **{counts['Critical']} Critical**, **{counts['High']} High**, **{counts['Medium']} Medium**, **{counts['Low']} Low** (total **{len(all_findings)}**; Info/pass notes excluded)
- Test suite: running (Python 3.12.11) → `docs/reviews/_pytest_functional_review_2026-09-06.txt`
"""

    agent_table = """
## Review agents

| Module | Agent | Status |
|---|---|---|
| POS | [POS review](01544d73-fd94-4832-8e7a-8b2a67562dd9) | draft complete |
| Sales | [Sales review](26afff7e-b1ce-4ea9-9240-fa9354d65019) | draft complete |
| Purchase | [Purchase review](4bdc1753-ee5d-4e18-b717-0a7f0a777fa7) | draft complete |
| Stock/Godown | [Stock review](95fa028c-ac85-4fdc-8194-5eb1f2fed9b2) | draft complete |
| Reporting | [Reporting review](9534fea3-69d0-4357-b9a6-0c71eef146b2) | draft complete |
| Accounting | [Accounting review](c81718f0-4622-42b5-8c5d-9a3c561defc2) | draft complete |
"""

    map_lines = [
        "## Provisional ID → CR map",
        "",
        "| Provisional | CR | Severity | Module | Title |",
        "|---|---|---|---|---|",
    ]
    for cr, pid, sev, mod, title in mapping:
        safe = title.replace("|", "/")[:70]
        map_lines.append(f"| {pid} | {cr} | {sev} | {mod} | {safe} |")

    pending = """
---

## Top 10 must-fix-before-launch

_(Draft from Critical/High on core money/stock flows; finalize after pytest + cross-ref)_

1. POS cash retry remints idempotency after complete (`POS-001`)
2. Concurrent sales/purchase returns over-return (`SALES-001` / `PUR-007`)
3. Journal lines outside `PostingService.post` savepoint (`ACC-001`)
4. Sales/purchase registers include CANCELLED (`RPT-004`)
5. Inventory summary trusts `StockBalance` cache (`RPT-003`)
6. GSTR-3B `net_payable_hint` uses full 2B not `recommended_claimable` (`RPT-010`)
7. Dashboard AR ≠ aging when books on (`RPT-001`)
8. Manual serial return crashes (`STK-001`)
9. Purchase CN/DN lack money idempotency + double `post_note` (`PUR-001`/`PUR-002`)
10. WARN negative-stock / freight layer≠GL split (`STK-003`, `PUR-003`)

## Cross-cutting themes

1. **Sales/Purchase twin drift** — cancel guards, note idempotency, list balance, return locking fixed on one side only.
2. **Check-then-act without locking the business key** — return headroom, period close vs post.
3. **Dual sources of truth** — documents vs GL outstanding; StockBalance vs movements; inventory layers vs GL 1400/5110.
4. **Multi-step money without durable client resume** — POS complete→receipt half-success.
5. **Period gates not centralized** — `PostingService`, stock count/transfer, delivery challan gaps.

## Cross-reference pass

_Status: queued — mark each CR new / duplicate-of / confirms-still-broken against `bugs/INDEX.md`, `MASTER_ISSUE_REGISTER.md` (R-001…R-088), `FINDINGS_2026-09-05.md`, prior DEEP_* reviews after pytest lands._
"""

    appendix_parts = ["\n---\n\n## Appendix — module drafts (verbatim)\n"]
    for title, fname, agent in [
        ("POS", "_draft_POS.md", "01544d73-fd94-4832-8e7a-8b2a67562dd9"),
        ("Sales", "_draft_Sales.md", "26afff7e-b1ce-4ea9-9240-fa9354d65019"),
        ("Purchase", "_draft_Purchase.md", "4bdc1753-ee5d-4e18-b717-0a7f0a777fa7"),
        ("Stock/Godown", "_draft_Stock.md", "95fa028c-ac85-4fdc-8194-5eb1f2fed9b2"),
        ("Accounting", "_draft_Accounting.md", "c81718f0-4622-42b5-8c5d-9a3c561defc2"),
    ]:
        body = (root / fname).read_text(encoding="utf-8").strip()
        appendix_parts.append(
            f"\n### {title} draft\n\nSource: [{title} review]({agent})\n\n{body}\n"
        )
    if rpt_body:
        appendix_parts.append("\n" + rpt_body + "\n")

    out = "\n".join(
        [
            summary,
            "\n".join(matrix_md),
            agent_table,
            cr_section,
            "\n".join(map_lines),
            pending,
            "".join(appendix_parts),
        ]
    )
    out_path = root / "FUNCTIONAL_CODE_REVIEW_FINDINGS.md"
    out_path.write_text(out, encoding="utf-8")
    (root / "_cr_map.txt").write_text(
        "\n".join(f"{a}\t{b}\t{c}\t{d}\t{e}" for a, b, c, d, e in mapping),
        encoding="utf-8",
    )
    print(f"Wrote {out_path} size={out_path.stat().st_size}")


if __name__ == "__main__":
    main()
