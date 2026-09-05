#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assert Wave 11 target IDs are not Deferred — roadmap."""
from __future__ import annotations

import json
import sys
from pathlib import Path

STATS = Path(__file__).resolve().parent / "_stats.json"

MUST_NOT_BE_DEFERRED = [
    # Wave R
    "BB-000031",
    "BB-000061",
    "BB-000077",
    "BB-000079",
    "BB-000083",
    "BB-000113",
    "BB-000133",
    # Wave 11A
    "BB-000030",
    "BB-000084",
    "BB-000085",
    "BB-000137",
    # Wave 11B
    "BB-000064",
    "BB-000063",
    "BB-000081",
    "BB-000082",
    "BB-000076",
    # Wave 11C
    "BB-000068",
    "BB-000075",
    "BB-000118",
    "BB-000121",
    "BB-000165",
    "BB-000125",
    # Wave 11D
    "BB-000191",
]


def main() -> int:
    stats = json.loads(STATS.read_text(encoding="utf-8"))
    by_id = {i["id"]: i for i in stats["issues"]}
    bad: list[str] = []
    missing: list[str] = []
    for iid in MUST_NOT_BE_DEFERRED:
        item = by_id.get(iid)
        if item is None:
            missing.append(iid)
            continue
        if item.get("status") == "Deferred — roadmap":
            bad.append(f"{iid}={item.get('status')}")
        elif item.get("status") != "Resolved":
            # Allow Resolved only for this assert; warn otherwise
            bad.append(f"{iid}={item.get('status')} (expected Resolved)")
    if missing:
        print("MISSING", missing)
        return 1
    if bad:
        print("FAIL still Deferred/not Resolved:", bad)
        return 1
    print("OK", len(MUST_NOT_BE_DEFERRED), "targets Resolved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
