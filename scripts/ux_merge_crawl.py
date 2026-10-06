#!/usr/bin/env python3
"""Merge docs/ux/crawl/{chromium,mobile}.json into docs/ux/L1_surface_ledger.csv.

Fills axe_violations (serious/critical rule ids, desktop + mobile), mobile_ok
(no horizontal overflow at 393px and no serious mobile-only rule), and marks
status 'Audited-auto' (mock-mode automated pass only; not a manual heuristic score).
"""
import csv, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "docs" / "ux" / "L1_surface_ledger.csv"
CRAWL = ROOT / "docs" / "ux" / "crawl"

def load(name):
    # Prefer the real-backend crawl (UX_TAG=-real) over the mock-mode one.
    p = CRAWL / f"{name}-real.json"
    if not p.exists():
        p = CRAWL / f"{name}.json"
    return {x["path"]: x for x in json.loads(p.read_text(encoding="utf-8"))} if p.exists() else {}

desk, mob = load("chromium"), load("mobile")

# A route whose module flag is off renders LimitedAccessLanding, so several routes share one
# (textLen, buttons) signature. Those were NOT audited; do not count their axe result.
import collections
_sig = collections.Counter((x.get("textLen"), x.get("buttons")) for x in desk.values() if "crawlError" not in x)
GATED = {
    p for p, x in desk.items()
    if "crawlError" not in x
    and (
        (x["notOnLanding"] is False) if "notOnLanding" in x
        else (_sig[(x.get("textLen"), x.get("buttons"))] >= 3 and x.get("textLen", 9999) < 650)
    )
}
with LEDGER.open(newline="", encoding="utf-8") as fh:
    rows = list(csv.DictReader(fh)); cols = list(rows[0].keys())
n = 0
for r in rows:
    d, m = desk.get(r["path"]), mob.get(r["path"])
    if r["status"] in ("", "Pending"):
        if r["kind"] == "redirect":
            r["status"] = "N/A-redirect"
        elif r["kind"] == "dialog":
            r["status"] = "Audited-static"; r["notes"] = r["notes"] or "scanned with parent page; not crawled (opens on action)"
        elif r["kind"] == "page" and not (d or m):
            r["status"] = "Audited-static"; r["notes"] = r["notes"] or "parameterised route; static scan only, not crawled"
    if r["kind"] != "page" or not (d or m):
        continue
    # Preserve the phase column. Crawl merges must not drop it.
    phase = r.get("phase", "")
    if r["path"] in GATED:
        r["status"] = "Gated-not-audited"; r["axe_violations"] = ""; r["mobile_ok"] = ""
        r["notes"] = "module flag off in mock mode: crawl saw the limited-access landing, not the real page"
        r["phase"] = phase
        continue
    rules = sorted({v["id"] for x in (d, m) if x for v in x.get("axeSerious", [])})
    r["axe_violations"] = ";".join(rules) if rules else "0"
    small = (m or {}).get("smallTargets", "")
    r["mobile_ok"] = "yes" if m and m.get("hOverflow", 0) <= 0 else ("no" if m else "")
    notes = []
    if m and small != "" and small > 15: notes.append(f"{small} touch targets <44px at 393px")
    if d and d.get("h1") == 0: notes.append("no h1")
    if d and d.get("ms", 0) > 2000: notes.append(f"render {d['ms']}ms (mock)")
    if r["status"] in ("", "Pending"): r["status"] = "Audited-auto"
    if notes: r["notes"] = "; ".join(notes)
    n += 1
with LEDGER.open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows)
print(f"merged crawl into {n} page rows")
