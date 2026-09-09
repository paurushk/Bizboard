# Retired CI gate scripts

Removed from `.github/workflows/ci.yml` on 2026-09-08 (Phase 1 — see
`GATE_INVENTORY.md`). They are **presence checks** — `_read(path)` + substring
`in` / `not in`, `_exists(path)` — and cannot detect a behavioural regression.
A green result from any of them was false confidence.

Left on disk so the change is reviewable. Safe to `git rm` once reviewed:

```
git rm scripts/ci_gates/_wave16_assert_gates.py \
       scripts/ci_gates/_wave17_assert_gates.py \
       scripts/ci_gates/_wave18_assert_gates.py \
       scripts/ci_gates/_wave19_assert_gates.py \
       scripts/ci_gates/_cr144_cr120_assert_guards.py
```

`_cr144_cr120_assert_guards.py` is retired **only because its real check moved**
to `guards/guard_no_raw_unit_cost_update.py` (behaviourally identical, now
self-tested). Remove the original with the others.

The older `_wave10`…`_wave15`, `_wave17_close_deferred`, `_wave18_close_deferred`,
`_close_open_550_694` scripts were never in CI; keep or remove at will.
