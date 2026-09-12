# Q-OS — Product Quality pipeline

Turns testing + observation evidence into an **actionable Product Quality
Backlog**: find everything preventing the product from being correct, usable,
satisfying, successful and delightful — then say exactly what to fix or build
next, in what order.

- **Design / rationale:** [`../docs/Q-OS_QUALITY_PIPELINE_PLAN.md`](../docs/Q-OS_QUALITY_PIPELINE_PLAN.md)
- **Build plan (task-by-task):** [`../docs/Q-OS_IMPLEMENTATION_RUNBOOK.md`](../docs/Q-OS_IMPLEMENTATION_RUNBOOK.md)
- **Analysis this consumes:** [`../docs/TESTING_STRATEGY.md`](../docs/TESTING_STRATEGY.md)
- **Generated output:** [`../docs/PRODUCT_QUALITY_BACKLOG.md`](../docs/PRODUCT_QUALITY_BACKLOG.md) — do not hand-edit

## Locked decisions (2026-09-10)

Adopted as the working model; formal founder confirmation tracked as **QOS-0052**.

| Decision | Value |
|---|---|
| ID scheme | `QOS-NNNN`, zero-padded to 4, never reused. Historical `CR-`/`R-`/`BB-`/`G-`/`UX-` ids are **sources, not stores** — traced in `backlog/_SOURCE_MAP.md`, never a second backlog. |
| Source of truth | `qos/backlog/<id>.yaml`, one file per item. `docs/PRODUCT_QUALITY_BACKLOG.md` is generated. `qos/backlog/_generated_manifest.json` records which files `_backfill_phase1.py` owns — it refuses to overwrite one that has been hand-edited since. |
| Frontier size | top 12 |
| `qos-lint` blocking | yes, from day 1 (`.github/workflows/ci.yml` + `scripts/ci_gates/REQUIRED_CHECKS.txt`) |
| Observation layer (Phase 3) | see `adr/0001-observation-layer.md` — **deferred (Accepted provisional)**; categories 2/3/9 stay hypothesis-grade until it lands. Mandatory revisit at pilot Stage 1. |

## Layout

```
qos/
  README.md                 this file
  RUBRIC.md                 scoring bands + evidence->priority cap (linter-enforced)
  journeys.yaml             risk-surface inventory (drives the zero-evidence indicator)
  schema/item.schema.json   backlog item schema (JSON Schema 2020-12)
  backlog/
    _SOURCE_MAP.md          every source finding -> QOS id (makes re-mining idempotent)
    QOS-0001.yaml ...        the items
  history/                  daily dashboard snapshots (JSONL), for the trend
  adr/                      decision records
  tools/
    _common.py              shared loaders + the scoring model
    lint.py                 the merge gate — checks L1-L12; `--selftest` proves each can fail
    build_backlog.py        backlog/*.yaml -> docs/PRODUCT_QUALITY_BACKLOG.md (deterministic)
    frontier.py             the sequenced top-N
    dashboard.py            per-category snapshot + trend + zero-evidence indicator
    _selftest/              deliberately-broken fixtures, one per check
```

## Commands

```bash
pip install -r qos/tools/requirements.txt

python qos/tools/lint.py                 # gate the backlog (run before commit)
python qos/tools/lint.py --selftest      # prove every check can fail (fixtures + global L7/L8)
python qos/tools/build_backlog.py        # regenerate docs/PRODUCT_QUALITY_BACKLOG.md
python qos/tools/frontier.py --n 12      # print the sequenced frontier
python qos/tools/dashboard.py            # print the dashboard block (reads qos/history/ if present)
python qos/tools/dashboard.py --append qos/history/$(date +%Y-%m).jsonl   # snapshot the trend
python qos/tools/_backfill_phase1.py     # re-mine (merges over hand edits — see merge.py)
```

`cd` anywhere — the tools resolve the repo root from their own path.

### Trend history

`qos/history/*.jsonl` (one snapshot per line) is **not committed to `main`**. The
`qos-dashboard` CI job appends a daily snapshot and pushes it to the dedicated
**`qos-history`** branch (and uploads it as a workflow artifact). To see the
trend locally, hydrate that branch first:

```bash
git fetch origin qos-history
git show origin/qos-history:qos/history/$(date +%Y-%m).jsonl > qos/history/$(date +%Y-%m).jsonl
python qos/tools/dashboard.py            # now the d7/d30 columns are populated
```

`build_backlog.py` never reads history — the generated doc is deterministic
regardless of what is in `qos/history/`.

## Lifecycle

```
open -> investigating -> (accepted_wontfix | in_progress) -> fixed -> verified -> guarded
```

- `fixed`/`verified`/`guarded` require a real `guard_ref.test` that resolves to a
  file in the repo (check L10).
- `guarded` requires `guard_ref.failed_at` — a commit SHA or CI run URL from a run
  where the guard **failed** before the fix (red-then-green, check L11).
- `accepted_wontfix` requires a `wontfix_rationale` and moves the item into the
  backlog doc's "Accepted / won't-fix" section (check L12).

## Ownership & cadence

| Cadence | Action | Owner |
|---|---|---|
| every PR | `qos-lint` (blocking) | author |
| every merge to `main` | `qos-dashboard` appends a snapshot (advisory) | CI |
| each pilot-stage boundary + each release | re-mine sources into `backlog/`; regenerate; re-review the frontier | QA + founder |
| quarterly | recalibrate `RUBRIC.md` against 10 closed items | QA |
| if `new - closed > 0` for two stages | freeze intake, burn down | QA |

**Generator vs human edit:** `recommendation`, `owner`, `priority_rationale`,
`lifecycle`, `test_required`, `guard_ref`, `depends_on`, `wontfix_rationale` are
human-owned and never overwritten. `scoring` math, `impact_band`, dashboard and
frontier are recomputed.
