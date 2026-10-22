#!/usr/bin/env python3
"""WP-A2: fail the Postgres CI job when any `postgres`-marked test was skipped.

The Postgres job exists to run the tests SQLite cannot (row locks, RLS policies,
races). A skip there means a test that is supposed to prove a guarantee proved
nothing. tests/conftest.py writes the skips to $PG_SKIP_REPORT; this script reads it.

    PG_SKIP_REPORT=pg_skips.json pytest ...
    python scripts/ci_gates/check_postgres_skips.py backend/pg_skips.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_postgres_skips.py <report.json>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if not path.exists():
        print(f"FAIL  no skip report at {path} (was PG_SKIP_REPORT set for the test run?)")
        return 1
    skips = json.loads(path.read_text(encoding="utf-8"))
    if skips:
        print(f"FAIL  {len(skips)} postgres-marked test(s) skipped on Postgres:")
        for line in skips:
            print(f"      - {line}")
        return 1
    print("ok    no postgres-marked test skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
