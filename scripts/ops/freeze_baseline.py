#!/usr/bin/env python3
"""1.2 — SHA-256 of docs/FREEZE_SCOPE.md (A1–A26 / Table B baseline).

    python scripts/ops/freeze_baseline.py
Paste the digest into docs/pilot/GO_NO_GO.md when Human signs G1. This script
does not sign the freeze.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCOPE = ROOT / "docs" / "FREEZE_SCOPE.md"


def digest() -> str:
    return hashlib.sha256(SCOPE.read_bytes()).hexdigest()


def main() -> int:
    if not SCOPE.is_file():
        print("docs/FREEZE_SCOPE.md missing", file=sys.stderr)
        return 1
    print(f"{digest()}  {SCOPE.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
