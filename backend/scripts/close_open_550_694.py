#!/usr/bin/env python3
"""Wrapper — canonical closer lives in scripts/ci_gates/_close_open_550_694.py."""
from __future__ import annotations

import runpy
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci_gates" / "_close_open_550_694.py"

if __name__ == "__main__":
    runpy.run_path(str(SCRIPT), run_name="__main__")
