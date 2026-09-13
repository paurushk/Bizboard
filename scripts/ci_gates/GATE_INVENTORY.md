# CI gate inventory & triage (Phase 1)

Every script under `scripts/ci_gates/` triaged as part of "Phase 1 — Remove False
Confidence". Verdicts:

- **KEEP** — enforces a real invariant (behaviour or static analysis). Lives in
  `guards/`, is run by `run_guards.py`, and is self-tested by `run_guards.py --selftest`.
- **RETIRE** — a *presence check*: asserts a file exists or a substring appears in
  a source file. It cannot detect a behavioural regression, and a green result
  gives false confidence. Removed from CI. Files left on disk for the founder to
  `git rm` (see `RETIRED.md`).
- **ARCHIVE** — a one-shot historical script (wave close-out bookkeeping), never
  in CI. Left as-is.

## Triage table

| Script | In CI? (before) | Verdict | Notes |
|---|---|---|---|
| `_cr144_cr120_assert_guards.py` | yes (backend job) | **KEEP** → `guards/guard_no_raw_unit_cost_update.py` | Genuine static guard: forbids raw `StockMovement.update(unit_cost=)` outside `stamp_cost`. Ported verbatim; CR-120 half was not implemented in the original and is folded into Phase 2 GST invariants. |
| `_wave16_assert_gates.py` | yes (backend job) | **RETIRE** | 100% `_read(...)` substring / `_exists(...)` checks: restore.sh present, "profiles: [restore]" string, `CeleryIntegration` string, `class InventoryCostLayer` string, etc. No behaviour asserted. |
| `_wave17_assert_gates.py` | yes (backend + postgres-rls jobs) | **RETIRE** | Same. Also asserts presence of `backend/payroll/models.py`, `crm/models.py`, Cashfree/PayU adapters — all **NOT SUPPORTED** in the freeze (see `docs/FREEZE_SCOPE.md` §B). |
| `_wave18_assert_gates.py` | yes (backend + postgres-rls jobs) | **RETIRE** | Same. Includes asserting a **docstring string** ("warehouses are stock locations") in `accounts/models.py`. |
| `_wave19_assert_gates.py` | yes (backend + postgres-rls jobs) | **RETIRE** | Same. `"cessRate" in <tsx source>`, `_exists("web/src/api/typedClient.ts")`, RLS migration string checks. |
| `_wave10_assert_open_zero.py` | no | ARCHIVE | Wave close-out bookkeeping. |
| `_wave11_assert_deferred_targets.py` | no | ARCHIVE | " |
| `_wave12_assert_gates.py` … `_wave15_assert_gates.py` | no | ARCHIVE | Presence checks, but never wired to CI. |
| `_wave17_close_deferred.py`, `_wave18_close_deferred.py` | no | ARCHIVE | One-shot wave close scripts. |
| `_close_open_550_694.py` | no | ARCHIVE | One-shot issue-register close script. |
| `_stats.json`, `_cr_map.txt` | n/a | ARCHIVE | Data files for the above. |

## What replaces the retired gates

The behaviours the wave scripts *gestured* at are covered — properly — by:

1. **The main `pytest` run** (already in CI) for anything that is real behaviour
   in supported scope.
2. **Phase 2** — `backend/core/invariants/`, `backend/tests/workflows/`, the
   place-of-supply matrix, the URL-conf tenant-isolation suite. Cess, GSTR
   sections, period locks, GL balance, stock==movements become *executed
   assertions*, not string greps.
3. **Out-of-scope items** (Manufacturing, Payroll, CRM, RLS, Cashfree/PayU,
   Tally, live GSP) are **NOT SUPPORTED** for the freeze — a Phase 2 test asserts
   they are inaccessible under the pilot flag profile, which is the opposite of
   asserting their code is present.

## Active guards (Phase 1)

`run_guards.py` runs these; CI runs `run_guards.py` then `run_guards.py --selftest`.

| Guard | Consequence if it fails |
|---|---|
| `guard_no_raw_unit_cost_update` | Raw `unit_cost` write bypasses `stamp_cost`; running cost diverges from movements, all COGS/valuation/GL wrong silently. |
| `guard_period_gate_coverage` (G-21/G-22) | A money-amend `complete()`/`cancel()` in the registry stops calling `assert_period_allows_money_amend`; a document dated inside a closed GST/accounting period could be written undetected. See `docs/CROSS_FLOW_IMPACT_MAP.md` §6. |
| `guard_config_consistency` (FG-1) | A feature flag exists in code but is unclassified in `docs/FREEZE_SCOPE.md`; frozen surface undefined for it. |
| `guard_regression_corpus_grows` | A regression test was deleted without lowering `backend/tests/regression/.corpus_count`; a fixed bug is unprotected again. |
| `guard_required_checks_match` | `ci.yml` jobs and `REQUIRED_CHECKS.txt` drifted; a merge gate may not be enforced. |
| `guard_ca_tax_parity` | A CA-signed GST scenario (F1–F8 in `docs/ca/CA_SIGN_OFF_CHECKLIST.md`) lost its automated parity case in `backend/tests/fixtures/tax_parity_cases.json`, or the checklist stopped referencing the fixture — the sign-off no longer maps to the computed tax. |

## Known findings for the founder

- **Python version — RESOLVED 2026-09-08 to 3.13.** `ci.yml` (all 4 jobs) and
  `backend/.python-version` set to `3.13`; the local `.venv` already runs it.
  Still to align: rebuild the local venv cleanly on 3.13 if needed, and confirm
  `constraints.txt` upper pins hold (they were built for 3.12). `requirements-dev.txt`
  still says `pytest>=9.1.1` while 8.4.2 is installed locally — reconcile on the
  next `pip install -c constraints.txt -r requirements-dev.txt`.
- **`pytest-randomly` is now active.** The first CI run may surface inter-test
  order dependence. Fix the offending tests (usually a module-level cache or a
  missing `db` rollback), don't disable the plugin. Escape hatch for a single
  local run: `pytest -p no:randomly`.
- **Opt-in determinism.** `TESTS_FREEZE_CLOCK=1` and `TESTS_NO_SOCKET=1` enable
  the frozen clock and network ban. Run the suite green with each, then wire them
  on by default and delete the env guards.
  **Status 2026-09-10 (updated):** the `fake_time() takes 0 positional arguments`
  crash — freezegun's sweep rebinding DRF's `SimpleRateThrottle.timer` (bare
  `time.time` class attr) into a bound method — is **FIXED** in
  `backend/tests/conftest.py` (`_freeze_clock_opt_in` wraps the real timer in
  `staticmethod()` so the identity check skips it). Full probe was
  **1472 passed / 5 failed / 23 skip**; the 5 were clock-brittle *test*
  assertions — fixtures with hard-coded Aug/Sep-2026 dates that read as "in the
  future" relative to the frozen `2026-06-15`, or a `PERIOD` module constant
  captured at import time (before the freeze fixture applies) drifting from a
  `timezone.localdate()` call made at test time.
  **Status 2026-09-11 (QOS-0018 — fixed):** all 5 re-anchored to the real/frozen
  clock instead of a hardcoded literal — `test_a07_dunning::test_collection_risk_api`,
  `test_b03_ims::test_supplier_scorecard_aggregates_purchase_value_and_mismatches`,
  `test_item_godown_expiry::test_xlsx_excel_dates_and_misfilled_serials_do_not_500`,
  `test_pr6_period_gl::test_completed_pcn_without_je_blocks_after_cutoff`,
  `test_sprint_a_prod_gst_p1::test_sales_rcm_complete_requires_confirm`. Full
  `TESTS_FREEZE_CLOCK=1` probe is now **1488 passed / 0 failed / 23 skip**.
  `determinism-probe` stays advisory in `ci.yml` until it has run green on
  `main` for 3 consecutive runs (a CI-history fact, not something this fix
  can itself produce) — then flip it to blocking and drop the env guards.

## Phase 1 close-out status (2026-09-10)

- **Strict invariant sweep — BLOCKING.** `.github/workflows/ci.yml` job
  `invariant-sweep` runs the Phase 2 gate AND the full-suite strict sweep
  (`INVARIANTS_STRICT=1 pytest`) with no `continue-on-error`; green in fixed and
  randomised order (1455 passed / 0 invariant failures).
- **Diff-coverage — BLOCKING.** The `backend` job's "Diff coverage vs base" step
  is `--fail-under=80` (was `--fail-under=0` + `continue-on-error`). Changed
  lines on a branch must be ≥80% covered. An absolute `--cov-fail-under` floor is
  the last open item here.
- **Red-then-green evidence.** `tests/test_invariants_smoke.py` carries
  `test_the_sweep_actually_catches_a_broken_journal` (hand-crafts an unbalanced
  POSTED entry, asserts `assert_all_invariants` raises) and
  `test_sequences_intact_flags_a_gap` — the sweep provably can fail.
- **Coverage map.** `docs/FREEZE_SCOPE_COVERAGE.md` maps every SUPPORTED /
  SUP item to its concrete test or an explicit GAP line.
