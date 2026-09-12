"""Sequenced frontier: the ordered top-N of open items to work next.

value = priority_weight * impact_weight * evidence_confidence / effort_cost
Ordering respects `depends_on` - an item never ranks above an unresolved blocker.
"""

from __future__ import annotations

import argparse

from _common import (
    IMPACT_W,
    EV_CONF,
    OPEN_STATES,
    enable_utf8_stdout,
    frontier_value,
    load_items,
    open_items,
)

DEFAULT_N = 12


def _resolved(dep_id: str, items: dict) -> bool:
    dep = items.get(dep_id)
    return dep is None or dep.get("lifecycle") not in OPEN_STATES


def compute(items: dict[str, dict], n: int = DEFAULT_N) -> dict:
    opens = open_items(items)
    ranked = sorted(
        opens,
        key=lambda it: (-frontier_value(it), it["priority"], it["id"]),
    )

    picked: list[dict] = []
    picked_ids: set[str] = set()
    # Iterate repeatedly so an item whose blocker was just picked can follow it.
    progressed = True
    while progressed and len(picked) < n:
        progressed = False
        for it in ranked:
            if it["id"] in picked_ids:
                continue
            deps = it.get("depends_on") or []
            if all(_resolved(d, items) or d in picked_ids for d in deps):
                picked.append(it)
                picked_ids.add(it["id"])
                progressed = True
                if len(picked) >= n:
                    break

    def risk(it: dict) -> float:
        return IMPACT_W[it["scoring"]["impact_band"]] * EV_CONF[it["evidence"]["strength"]]

    denom_pool = [it for it in opens if it["scoring"]["impact_band"] in ("High", "Medium")]
    denom = sum(risk(it) for it in denom_pool) or 1.0
    retired = sum(risk(it) for it in picked if it["scoring"]["impact_band"] in ("High", "Medium"))

    rows = []
    for rank, it in enumerate(picked, 1):
        blockers = [
            d for d in (it.get("depends_on") or [])
            if not _resolved(d, items) and d not in picked_ids
        ]
        rows.append({
            "rank": rank,
            "id": it["id"],
            "title": it["title"],
            "category": it["category"],
            "priority": it["priority"],
            "effort": it["effort"],
            "value": frontier_value(it),
            "moves": it.get("business_metric", "none"),
            "blocked_by": ",".join(blockers) or "-",
        })
    return {
        "rows": rows,
        "n": n,
        "open_total": len(opens),
        "risk_retired_pct": round(100 * retired / denom, 1),
    }


def render_md(result: dict) -> str:
    out = [f"## Do next - sequenced frontier (top {len(result['rows'])} of {result['open_total']} open)", ""]
    out.append("| # | id | title | category | priority | effort | value | moves | blocked by |")
    out.append("|--:|---|---|---|---|---|--:|---|---|")
    for r in result["rows"]:
        out.append(
            f"| {r['rank']} | {r['id']} | {r['title']} | {r['category']} | "
            f"{r['priority']} | {r['effort']} | {r['value']} | {r['moves']} | {r['blocked_by']} |"
        )
    out.append("")
    out.append(
        f"Risk retired by this frontier: **{result['risk_retired_pct']}%** of open "
        f"High/Medium-impact risk."
    )
    return "\n".join(out)


def main() -> int:
    enable_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=DEFAULT_N)
    args = ap.parse_args()
    items, _ = load_items()
    print(render_md(compute(items, args.n)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
