# CI gate scripts

Semantic regression guards that assert wave deliverables remain present in
the codebase. Run by `.github/workflows/ci.yml` (waves 16–19) and available
for manual checks:

```sh
python scripts/ci_gates/_wave19_assert_gates.py
```

- `_wave{12..19}_assert_gates.py`, `_wave10_assert_open_zero.py`,
  `_wave11_assert_deferred_targets.py` — assertion gates for their wave.
- `_wave{17,18}_close_deferred.py` — deferred-issue register closers
  (existence-checked by the matching `_assert_gates.py`).
- `_close_open_550_694.py` — issue-register closer; thin wrapper at
  `backend/scripts/close_open_550_694.py`.
- `_stats.json` — shared counters read/written by the closers.

Relocated from `docs/reviews/` (2026-09-05) — they are executable CI
tooling, not documentation. `_wave16` / `_wave19` currently report
pre-existing failures also present on `main`.
