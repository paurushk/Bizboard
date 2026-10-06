#!/usr/bin/env python3
"""Summarise the real-backend crawl (docs/ux/crawl/*-real.json) for the gated-module audit.

Prints per-phase tables: pages that rendered vs still on the landing page, serious axe
rules, console-error routes, missing h1, overflow, touch targets, render time.
"""
import csv, json, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CRAWL = ROOT / "docs" / "ux" / "crawl"
LEDGER = ROOT / "docs" / "ux" / "L1_surface_ledger.csv"

phase = {}
with LEDGER.open(newline="", encoding="utf-8") as fh:
    for r in csv.DictReader(fh):
        if r["kind"] == "page" and r.get("phase"):
            phase[r["path"]] = r["phase"]

for name in ("chromium-real", "mobile-real"):
    p = CRAWL / f"{name}.json"
    if not p.exists():
        print(f"{name}: missing")
        continue
    data = {x["path"]: x for x in json.loads(p.read_text(encoding="utf-8"))}
    print(f"\n=== {name}: {len(data)} routes")
    landing = [k for k, x in data.items() if x.get("notOnLanding") is False]
    print("still on landing:", len(landing), landing[:20])
    rows = [(phase.get(k, ""), k, x) for k, x in data.items() if k in phase and "crawlError" not in x]
    by = collections.defaultdict(list)
    for ph, k, x in rows:
        by[ph].append((k, x))
    for ph in sorted(by):
        print(f"\n-- {ph}")
        for k, x in by[ph]:
            ax = ",".join(sorted({v["id"] for v in x.get("axeSerious", [])})) or "-"
            print(f"{k:38s} axe={ax:32s} inputs={x['inputs']:3d} btn={x['buttons']:3d} small={x['smallTargets']:3d} h1={x['h1']} ovf={x['hOverflow']} {x['ms']}ms err={len(x['errors'])}")
    ser = collections.Counter()
    for k, x in data.items():
        for v in x.get("axeSerious", []):
            ser[v["id"]] += 1
    print("\nserious axe rules over all routes:", ser.most_common())
    print("console-error routes:", sum(1 for x in data.values() if x.get("errors")))
    errs = collections.Counter(e[:90] for x in data.values() for e in x.get("errors", []))
    print("top console errors:", errs.most_common(5))
