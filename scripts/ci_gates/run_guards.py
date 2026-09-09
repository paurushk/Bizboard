#!/usr/bin/env python3
"""Run all Freeze Gate guards (Phase 1).

    python scripts/ci_gates/run_guards.py             # run every guard against the repo
    python scripts/ci_gates/run_guards.py --selftest  # prove every guard can fail

--selftest is the gate-integrity check: for each guard it builds the guard's own
``make_bad_tree`` fixture in a temp dir and asserts ``check()`` reports at least
one violation. A guard that cannot fail is worthless and fails the selftest.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import tempfile
from pathlib import Path

CI_GATES_DIR = Path(__file__).resolve().parent
GUARDS_DIR = CI_GATES_DIR / "guards"
REPO_ROOT = CI_GATES_DIR.parents[1]


def _load_guards() -> list[object]:
    mods = []
    for path in sorted(GUARDS_DIR.glob("guard_*.py")):
        spec = importlib.util.spec_from_file_location(f"_guard_{path.stem}", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for attr in ("NAME", "CONSEQUENCE", "check", "make_bad_tree"):
            if not hasattr(mod, attr):
                raise SystemExit(f"guard {path.name} is missing required attribute '{attr}'")
        mods.append(mod)
    return mods


def _run(guards: list[object]) -> int:
    failed = False
    for g in guards:
        violations = g.check(REPO_ROOT)
        if violations:
            failed = True
            print(f"FAIL  {g.NAME}")
            print(f"      why: {g.CONSEQUENCE}")
            for v in violations:
                print(f"      - {v}")
        else:
            print(f"ok    {g.NAME}")
    return 1 if failed else 0


def _selftest(guards: list[object]) -> int:
    failed = False
    for g in guards:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            g.make_bad_tree(tmp)
            violations = g.check(tmp)
            if violations:
                print(f"ok    {g.NAME} (fires on bad input)")
            else:
                failed = True
                print(f"FAIL  {g.NAME}: make_bad_tree did not trigger check() — guard cannot fail")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true", help="prove each guard can fail")
    args = ap.parse_args()
    guards = _load_guards()
    if not guards:
        print("no guards found under scripts/ci_gates/guards/", file=sys.stderr)
        return 1
    return _selftest(guards) if args.selftest else _run(guards)


if __name__ == "__main__":
    raise SystemExit(main())
