#!/usr/bin/env python3
"""Assert Master Issue Register has zero Open issues."""
from __future__ import annotations

import json
import sys
from pathlib import Path

STATS = Path(__file__).resolve().parent / "_stats.json"


def main() -> int:
    data = json.loads(STATS.read_text(encoding="utf-8"))
    open_count = sum(1 for i in data.get("issues", []) if i.get("status") == "Open")
    reported = data.get("open_count", open_count)
    print(f"open_count={open_count} reported={reported} total={data.get('total')}")
    if open_count != 0 or reported != 0:
        opens = [i["id"] for i in data["issues"] if i.get("status") == "Open"]
        print("OPEN:", ", ".join(opens[:30]), ("..." if len(opens) > 30 else ""))
        return 1
    print("OK: Open == 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
