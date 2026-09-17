#!/usr/bin/env python3
"""10.4 — secret-rotation drill without mutating any secret.

    python scripts/ops/secret_rotation_drill.py
    python scripts/ops/secret_rotation_drill.py --check-env
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from core.secret_rotation import ROTATION_ORDER, check_required_secrets  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print secret rotation order; never rotates.")
    parser.add_argument("--check-env", action="store_true")
    args = parser.parse_args(argv)
    print("Rotation order (Human performs the live cut):")
    for i, name in enumerate(ROTATION_ORDER, 1):
        print(f"  {i}. {name}")
    if not args.check_env:
        print("Dry-run only. Re-run with --check-env after filling secrets.")
        return 0
    missing = check_required_secrets()
    if missing:
        print("Missing or placeholder: " + ", ".join(missing), file=sys.stderr)
        return 1
    print("All listed secrets are present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
