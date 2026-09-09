"""Freeze Gate guards (Phase 1).

Each ``guard_*.py`` module in this package exposes:

    NAME: str            - short identifier
    CONSEQUENCE: str      - one sentence: what breaks in production if this fails
    def check(root: Path) -> list[str]   - [] means pass; each string is a violation
    def make_bad_tree(tmp: Path) -> None  - write a known-violating fixture under tmp
                                            so run_guards.py --selftest can prove the
                                            guard actually fires (gate-integrity).

Run all guards:      python scripts/ci_gates/run_guards.py
Prove they can fail: python scripts/ci_gates/run_guards.py --selftest
"""
