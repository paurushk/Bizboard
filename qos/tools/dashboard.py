"""Dashboard: per-category snapshot + trend + the zero-evidence risk-surface indicator.

Trend deltas come from qos/history/*.jsonl (one JSON object per line, newest last).
If there is no history the delta columns render as 'n/a'.
"""

from __future__ import annotations

import argparse
import json
from datetime import date

from _common import (
    CATEGORIES,
    CATEGORY_EMOJI,
    CATEGORY_LABEL,
    HISTORY_DIR,
    OPEN_STATES,
    enable_utf8_stdout,
    load_items,
    load_journeys,
)


def snapshot(items: dict[str, dict]) -> dict:
    counts = {c: 0 for c in CATEGORIES}
    guarded = {c: 0 for c in CATEGORIES}
    total = {c: 0 for c in CATEGORIES}
    for it in items.values():
        c = it["category"]
        total[c] += 1
        if it.get("lifecycle") in OPEN_STATES:
            counts[c] += 1
        if it.get("lifecycle") == "guarded":
            guarded[c] += 1
    journeys = load_journeys()
    zero_ev = [j for j in journeys if j.get("evidence", "none") == "none"]
    return {
        "date": date.today().isoformat(),
        "open": counts,
        "guarded": guarded,
        "total": total,
        "journeys_total": len(journeys),
        "journeys_zero_evidence": len(zero_ev),
        "open_all": sum(counts.values()),
    }


def _history() -> list[dict]:
    rows: list[dict] = []
    if HISTORY_DIR.exists():
        for path in sorted(HISTORY_DIR.glob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def _delta(cat: str, current: int, hist: list[dict], days: int) -> str:
    if not hist:
        return "n/a"
    # pick the oldest snapshot within the window (list is chronological)
    from datetime import datetime, timedelta

    cutoff = datetime.today().date() - timedelta(days=days)
    prior = None
    for row in hist:
        try:
            d = datetime.fromisoformat(row["date"]).date()
        except (KeyError, ValueError):
            continue
        if d <= cutoff:
            prior = row
    if prior is None:
        prior = hist[0]
    was = prior.get("open", {}).get(cat)
    if was is None:
        return "n/a"
    diff = current - was
    return f"{diff:+d}"


def render_block(items: dict[str, dict], *, with_trend: bool = True) -> str:
    """Dashboard text block.

    with_trend=False -> a pure snapshot, no dependency on qos/history/. build_backlog.py
    uses that so the generated doc stays deterministic (L7) whatever history exists.
    The CLI and the qos-dashboard artifact use with_trend=True.
    """
    snap = snapshot(items)
    hist = _history() if with_trend else []
    lines = ["```", "PRODUCT QUALITY BACKLOG - dashboard", ""]
    width = max(len(CATEGORY_LABEL[c]) for c in CATEGORIES)
    for c in CATEGORIES:
        emoji = CATEGORY_EMOJI[c]
        label = CATEGORY_LABEL[c].ljust(width)
        openc = snap["open"][c]
        extra = ""
        if c == "CRITICAL_BUG":
            extra = f"   guarded: {snap['guarded'][c]}/{snap['total'][c]}"
        if with_trend:
            lines.append(f"{emoji} {label} : {openc:>3}   (d30 {_delta(c, openc, hist, 30)}){extra}")
        else:
            lines.append(f"{emoji} {label} : {openc:>3}{extra}")
    lines.append("")
    lines.append(
        f"Leading indicator - risk surface with ZERO evidence: "
        f"{snap['journeys_zero_evidence']} / {snap['journeys_total']} journeys"
    )
    if with_trend and hist:
        prev_open = hist[-1].get("open_all")
        if prev_open is not None:
            lines.append(f"Open items (all categories): {snap['open_all']}  (last snapshot {prev_open})")
    lines.append("```")
    return "\n".join(lines)


def main() -> int:
    enable_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--append", metavar="FILE", help="append today's snapshot as a JSONL line")
    args = ap.parse_args()
    items, _ = load_items()
    if args.append:
        from pathlib import Path

        path = Path(args.append)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(snapshot(items), sort_keys=True) + "\n")
        print(f"appended snapshot to {path}")
    else:
        print(render_block(items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
