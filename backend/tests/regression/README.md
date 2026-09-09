# backend/tests/regression/ — the anti-regression corpus

**Rule: every bug fixed from the freeze onward lands exactly one permanent test
here, and it must be shown red on the parent commit before the fix.**

Why a dedicated folder:

- An LLM (or a human) maintaining this codebase has no memory of past bugs. This
  folder *is* that memory. It is never merged into the general suite, never
  reorganised into "wave" files, never deleted wholesale.
- `scripts/ci_gates/guards/guard_regression_corpus_grows.py` counts the
  `def test_*` functions here and fails CI if the count drops below
  [`.corpus_count`](.corpus_count). Removing a test requires lowering that number
  in the same commit with a written reason.

## How to add one

1. Reproduce the bug. Write the test here so it **fails on the current commit**.
   File name: `test_<issueid>_<slug>.py` (e.g. `test_bb000361_cn_reconcile.py`,
   or `test_freeze001_...` for bugs found during the freeze itself).
2. Paste the failing output into the PR, or let CI verify red-then-green
   (stash the fix, run just this test, expect failure).
3. Apply the fix. The test goes green.
4. Bump `.corpus_count` by the number of `test_*` functions you added.

## Conventions

- One bug per file. Keep the docstring: the symptom, the root cause, the fix.
- Prefer the narrowest assertion that would have caught the bug. No broad
  "exercise the module" tests — those belong in `tests/` or `tests/workflows/`.
- Every test here carries the `regression` marker automatically (see
  `conftest.py` in this folder).
- Do not import from sibling regression files.

## Migrating historical regression tests

Existing `BB-####` / `CR-###` assertions scattered through `tests/test_wave*.py`
etc. are migrated **opportunistically** — when Phase 2 work touches that area,
lift the focused assertion into a named file here and bump `.corpus_count`. No
big-bang move.
