# Contributing to Bizboard

## Verification before you push

| Scope | Command | When |
|---|---|---|
| Backend fast lane | `cd backend && pytest` | every change |
| Backend Phase-2 gate | `cd backend && INVARIANTS_STRICT=1 pytest tests/workflows tests/tenancy tests/gst tests/snapshots tests/edge tests/errors tests/matrices tests/personas tests/test_invariants_smoke.py tests/regression` | before push |
| Frontend | `cd web && npm run lint && npm test -- --run && npm run build` | FE change |
| **Concurrency / row-lock lane** | `scripts/test_concurrency_local.sh` | **any change to allocation, stock movement, document numbering, or period close** |
| Q-OS backlog | `python qos/tools/lint.py` | any `qos/` change |

## The concurrency lane — do not skip it (QOS-0006)

Tests marked `@pytest.mark.postgres` exercise `SELECT ... FOR UPDATE` row locks:
payment allocation, stock oversell, concurrent document numbering, period-close
races. **SQLite does not enforce those locks**, so on a normal `pytest` run these
tests *skip* — a real race bug passes locally and only fails in CI (or worse, in
production).

`scripts/test_concurrency_local.sh` spins a throwaway `postgres:17-alpine`
container, points the suite at it (`DATABASE_URL` + `PYTEST_KEEP_DATABASE_URL=1`,
which `config.settings_test` needs to honour a local Postgres), runs the
`postgres` marker lane, and tears the container down afterwards.

```bash
scripts/test_concurrency_local.sh                      # whole lane
scripts/test_concurrency_local.sh tests/test_concurrency_races.py
scripts/test_concurrency_local.sh -k "numbering or allocation"
```

Requires Docker. If you cannot run Docker locally, say so in the PR so a reviewer
runs the lane, and rely on the CI `backend` / `invariant-sweep` jobs (both run on
real Postgres).

## Regression tests

- One permanent test per fixed bug, under `backend/tests/regression/`.
  `scripts/ci_gates/guards/guard_regression_corpus_grows.py` blocks a delete
  without lowering `.corpus_count`.
- **Red-then-green:** a regression test must have failed against the unfixed code
  at least once. Link the failing run / commit in the PR.

## Feature flags

Every product `_env_bool("X")` / `VITE_ENABLE_X` must be classified in
`docs/FREEZE_SCOPE.md` §E — `guard_config_consistency` enforces it.

## Commits

Branch off `main`; do not push directly. End commit messages with the
`Co-Authored-By` trailer the tooling injects.
