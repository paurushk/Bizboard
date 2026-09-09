# CI gate scripts

**Freeze Gate guards (Phase 1).** Real invariant checks — behavioural or static
analysis — run by `.github/workflows/ci.yml`:

```sh
python scripts/ci_gates/run_guards.py             # run every guard
python scripts/ci_gates/run_guards.py --selftest  # prove every guard can fail
```

- `guards/guard_*.py` — one invariant each. Every module exposes `NAME`,
  `CONSEQUENCE`, `check(root) -> list[str]`, and `make_bad_tree(tmp)` so the
  selftest can verify it actually fires.
- `run_guards.py` — orchestrator + gate-integrity `--selftest`.
- `REQUIRED_CHECKS.txt` — intended CI job set; `guard_required_checks_match`
  asserts it equals the jobs in `ci.yml`.
- `GATE_INVENTORY.md` — triage of every script here, and findings for the founder.
- `RETIRED.md` — the presence-check "assert gates" removed from CI on 2026-09-08
  and why. Files kept on disk pending `git rm`.

The old `_wave*_assert_gates.py` scripts were substring/existence checks that
could not detect a regression (and `_wave16`/`_wave19` were already red on
`main`). Their intent is now covered by `pytest` and the Phase 2 invariant /
workflow suites. See `GATE_INVENTORY.md`.
