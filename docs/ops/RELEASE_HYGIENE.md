# Per-release hygiene (C.4)

For every prod deploy:

1. Git SHA and image digest (`pin_image_digests.sh`)
2. `python scripts/ops/freeze_baseline.py` digest (confirm freeze file unchanged or Human accepted)
3. `showmigrations` heads per app
4. Release notes: `python scripts/ops/release_notes.py <prev> <sha>` — money/tax/stock first; Human edits before customers see them
5. Expand-only? Else `EXPAND_CONTRACT_OK` already shipped
6. After up: `/api/v1/health/?ready=1`, one Complete → PDF, `check_invariants --company <pilot>`


## Pull request size (WP-EN1)

CI job `merge-size` counts changed lines on every pull request, leaving out generated files,
lock files and migrations (`scripts/ci_gates/check_merge_size.py`). Over 1,500 lines it warns; over
4,000 it fails unless the PR has the `large-change-approved` label, which a reviewer adds after
agreeing the change can't be split. Merge small changes to `main` often; a working tree that
collects weeks of work across programmes is the largest single release risk this repo has had.

The job is advisory until the WP-A1 commit chunks (the uncommitted tree as of 2026-10-22) are on
`main`; those chunks are deliberately large. After that, remove `continue-on-error` from the job
and mark it a blocker in `scripts/ci_gates/REQUIRED_CHECKS.txt` and branch protection.
