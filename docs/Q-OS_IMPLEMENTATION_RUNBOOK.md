# Q-OS — Implementation Runbook (executable)

**Status:** Build runbook · **Created:** 2026-09-10 · **Owner:** whoever executes
**Companion to:** [`Q-OS_QUALITY_PIPELINE_PLAN.md`](Q-OS_QUALITY_PIPELINE_PLAN.md)
(design + rationale). This doc is the task-by-task build plan — every task has a
goal, concrete steps, the files it touches, an acceptance check you can run, its
dependencies, and an effort estimate. Skeleton file contents are in the
appendices; copy and adapt.

**Tech stack (fixed, to match the repo):** Python 3.13, `PyYAML`, `jsonschema`.
Tools live in `qos/tools/`, are plain scripts (no framework), and follow the
`scripts/ci_gates/run_guards.py --selftest` convention (each checker proves it can
fail). No new language, no service.

**Definition of "executable":** after Phase 0 + Phase 1 you can run
`python qos/tools/lint.py && python qos/tools/build_backlog.py` locally, commit,
and CI will gate the backlog. Everything after that is content + enforcement.

---

## Build status (2026-09-10)

| Phase | State | Notes |
|---|---|---|
| **0 Foundations** | **DONE** | `qos/` tree, `schema/item.schema.json`, `RUBRIC.md`, `README.md`, `journeys.yaml`, and all five tools (`lint`, `build_backlog`, `frontier`, `dashboard`, `_common`) built. `lint.py --selftest` green (9 fixtures, checks L2–L6/L10×2/L11/L12 provably fail). `qos-lint` job in `.github/workflows/ci.yml` + `REQUIRED_CHECKS.txt`; `guard_required_checks_match` green. |
| **1 Backfill** | **DONE** | **79 items** in `qos/backlog/*.yaml` + `_SOURCE_MAP.md` (103 source rows). **P1-T4 reconciled — direct read:** BB (machine-checked `Status` tally 739 Resolved / 6 Accepted-positive / 13 non-resolved, all mapped; 3 net-new QOS-0049/0050/0051). **CR** read first-hand from `FUNCTIONAL_CODE_REVIEW_FINDINGS.md`: 5 release-blocking Criticals FIXED & VERIFIED; the 15 stale-`OPEN` CR-090..104 entries → QOS-0053 (CR-100/101), QOS-0054 (CR-104), QOS-0055 (CR-103), QOS-0056 (CR-091) + QOS-0057 re-status sweep. **R-001..088** source doc is absent from the tree → QOS-0058 (honestly flagged, not hand-waved). |
| **2 Enforcement** | **DONE** | Checks L1–L12 all built and **all self-tested** — 9 per-item fixtures + global L7 (stale doc) + global L8 (empty source map). `guard_ref` resolves the **file and the test name** (L10). Frontier honours `depends_on`; zero-evidence indicator over a **51-cell** `journeys.yaml`. `qos-dashboard` pushes the trend snapshot to the dedicated **`qos-history`** branch (never protected — the push lands) plus an artifact fallback; `main` is never touched. `pilot/GO_NO_GO.md` carries the Q-OS dashboard row. |
| **3 Observation layer** | **DECIDED — deferred** | `qos/adr/0001-observation-layer.md` **Accepted (provisional)** = defer (Option B). Nothing half-built: no `qos/agents/`, no stubs. Categories 2/3/9 stay `hypothesis` / `P1-investigate` by rule. Mandatory revisit at pilot Stage 1; formal ratification tracked as **QOS-0052**. |
| **4 Work the frontier** | not started (ongoing) | Per pilot stage. Nothing to "implement" — it is the recurring fix loop. Current frontier top item: `QOS-0006`. |
| **5 Continuous operation** | **DONE (wired)** | Re-mine = re-run `_backfill_phase1.py` → `qos/tools/merge.py` **regenerates mined fields and preserves human-owned ones** (`lifecycle`, `guard_ref`, `priority`, `owner`, …) on every existing item, logging what it kept. `build_backlog.py` never writes YAML. Trend commit-back is live (`qos-history` branch). Quarterly rubric recalibration is a `qos/README.md` cadence entry. |

**Open governance (tracked, not blocking):** `QOS-0052` — sign `RUBRIC.md`, confirm the `README.md` locked decisions, ratify ADR-0001. These are recorded as adopted; the sign-off is a standing quality-review agenda item.

**Follow-up work items that are tracked in the backlog, not gaps in this build:** `QOS-0057` (re-status the ~10 remaining stale-`OPEN` CR entries against the current tree), `QOS-0058` (locate the missing `FINDINGS_2026-09-05.md` or formally supersede the R scheme). Both are honest, scoped backlog items with owners.

Regenerate everything: `python qos/tools/_backfill_phase1.py && python qos/tools/build_backlog.py && python qos/tools/lint.py`.

---

## 0. Before you start — lock these decisions (30 min)

| Decision | Default | Who signs |
|---|---|---|
| ID scheme | `QOS-NNNN`, zero-padded to 4, never reused | founder |
| Source of truth | `qos/backlog/<id>.yaml`, one file per item; `docs/PRODUCT_QUALITY_BACKLOG.md` is generated | founder |
| Frontier size N | 12 | QA |
| `qos-lint` blocking from day 1 | yes | QA |
| Observation layer (Phase 3) | decide at Phase 3 start via ADR — do **not** pre-commit | founder |
| Where the plan lives if Q-OS outgrows Bizboard | keep in `docs/` now; move to a `qos/` repo later, docs travel | founder |

Record the answers at the top of `qos/README.md` (task P0-T2).

---

## Phase 0 — Foundations

**Goal:** the machinery exists and gates an empty backlog. **Effort:** ~1 week
(1 person). **Exit:** `qos-lint` green in CI on a 3-item seed; rubric signed.

### P0-T1 — Repo skeleton · effort S · deps none

**Steps**
1. Create the tree:
   ```
   qos/
     README.md
     RUBRIC.md
     schema/item.schema.json
     backlog/               # empty for now; _SOURCE_MAP.md added in P1
     history/               # empty; .gitkeep
     tools/
       lint.py
       build_backlog.py
       frontier.py
       _common.py
   docs/PRODUCT_QUALITY_BACKLOG.md   # generated placeholder
   ```
2. Add `qos/tools/requirements.txt`: `PyYAML>=6` , `jsonschema>=4`.
3. Add a `Makefile` target or `qos/tools/README.md` with the three commands
   (`lint`, `build`, `frontier`).

**Acceptance:** `ls qos/tools/*.py` shows 4 files; `pip install -r
qos/tools/requirements.txt` succeeds.

### P0-T2 — `qos/README.md` · effort S · deps P0-T1

Write the pipeline-stage table (from the plan §A1), the locked decisions from §0
above, the ownership + cadence table, and the "one ID scheme only — historical
CR/R/BB are *sources*, not *stores*" rule.

**Acceptance:** a new reader can answer "where do items live, who owns them, when
is the backlog regenerated" from this file alone.

### P0-T3 — `qos/schema/item.schema.json` · effort M · deps P0-T1

Use **Appendix A** verbatim as the starting point. It encodes: required fields,
the 10-category enum, persona/archetype enums, the `evidence.strength` enum, the
1–5 scoring axes, the `lifecycle` enum, and the conditional rules expressible in
JSON Schema (`fixed`+ ⇒ `guard_ref` non-null; `guarded` ⇒ `guard_ref.failed_at`
present; `accepted_wontfix` ⇒ `wontfix_rationale` non-empty; `closed` set iff
lifecycle terminal).

**Acceptance:** `python -c "import json,jsonschema;
jsonschema.Draft202012Validator.check_schema(json.load(open('qos/schema/item.schema.json')))"`
exits 0.

### P0-T4 — `qos/RUBRIC.md` · effort S · deps none

Copy the plan §A3 tables (reach/severity/frequency bands, `impact_band` formula,
the **evidence-strength → priority cap**, the security `severity=5` exemption).
Add 3 worked scoring examples so contributors calibrate the same way.

**Acceptance:** founder + QA sign at the bottom (name + date).

### P0-T5 — `qos/tools/_common.py` + `lint.py` v1 · effort L · deps P0-T3

`_common.py`: load all backlog YAML, the schema, the persona/archetype/category
constants, and helper `impact_band(scoring)`.

`lint.py`: implement checks **L1–L8** from **Appendix B**. Ship `--selftest`:
a `qos/tools/_selftest/` dir with ~6 deliberately-broken fixture items, each of
which must make exactly one check fail.

**Acceptance:**
- `python qos/tools/lint.py` exits 0 on an empty backlog and on the 3-item seed
  (P0-T7);
- `python qos/tools/lint.py --selftest` exits 0 (every planted defect caught).

### P0-T6 — `build_backlog.py` v1 · effort M · deps P0-T5

Render `docs/PRODUCT_QUALITY_BACKLOG.md` deterministically from the YAML
(**Appendix C** contract): generated banner (no volatile timestamp in the body),
dashboard block, frontier table (calls `frontier.py`), one section per category,
an "Accepted / won't-fix" section, an "Innovation (review-only)" annex.

**Acceptance:** run twice → identical output; `git diff --exit-code
docs/PRODUCT_QUALITY_BACKLOG.md` clean after a second run.

### P0-T7 — Seed items + CI job · effort S · deps P0-T6

1. Hand-write 3 real seed items from the strategy §7 register:
   `QOS-0001` (G-4, DISSATISFACTION), `QOS-0002` (G-8, SECURITY_PRIVACY),
   `QOS-0003` (G-1, PERSONA_GAP). Use **Appendix D** as the template.
2. Add the `qos-lint` job to `.github/workflows/ci.yml` (**Appendix E**):
   install deps, `python qos/tools/lint.py`, then
   `python qos/tools/build_backlog.py && git diff --exit-code
   docs/PRODUCT_QUALITY_BACKLOG.md`, then `python qos/tools/lint.py --selftest`.
3. Add `qos-lint` to `scripts/ci_gates/REQUIRED_CHECKS.txt` so
   `guard_required_checks_match` keeps it wired.

**Acceptance:** push a branch; `qos-lint` runs and is green. Break a seed item
(e.g. set `priority: P0` with `evidence.strength: hypothesis`) → job goes red.

**Phase 0 DoD:** P0-T1…T7 acceptance all met; `RUBRIC.md` signed; `qos-lint`
blocking and in `REQUIRED_CHECKS.txt`.

---

## Phase 1 — Backfill the backlog

**Goal:** `docs/PRODUCT_QUALITY_BACKLOG.md` v1 exists, every source finding
traced, dashboard + top-12 frontier rendered. **Effort:** ~1.5–2 weeks.
**Exit:** every open GAP in `FREEZE_SCOPE_COVERAGE.md` maps to exactly one QOS
item; founder signs the frontier.

### P1-T1 — `qos/backlog/_SOURCE_MAP.md` · effort S · deps Phase 0

Create the traceability ledger: a table `source id → QOS id → note`. **Every**
mined finding gets a row, even if it becomes a `duplicates:` of another. This is
what makes re-mining idempotent and stops findings getting lost.

### P1-T2 — Mine `TESTING_STRATEGY.md` §7 · effort M · deps P1-T1

18 rows (G-1…G-16 + G-determinism + G-mutation). Each already carries impact /
likelihood / priority / proposed test / owner — near-direct transcription.

- category: from the `[TAG]` in the strategy demo slice where present, else judge;
- `evidence.strength`: `heuristic` for G-1..G-13, `hypothesis` for G-14/G-15/G-16;
- `test_required`: the "Proposed test" column;
- `journey` / `persona`: from the register row.

**Yield:** ~18 items. **Acceptance:** `_SOURCE_MAP.md` has all 18; `qos-lint`
green.

### P1-T3 — Mine `UX_AUDIT_FINDINGS.md` + `_WAVE2_` · effort M · deps P1-T1

UX-001…010 (+ wave 2). Most are "Fixed & Verified". Rule:

- if a regression test already guards the fix → **no item** (log in `_SOURCE_MAP`
  as "covered, guarded");
- if fixed but **no** guard → open item, category `USABILITY` or
  `RELIABILITY_TRUST`, `title: "No regression guard for <UX-00x> (<summary>)"`,
  `priority: P2`, `test_required: <the guard to add>`, `lifecycle: open`;
- if still open → normal item.

**Yield:** ~4–8 items. **Acceptance:** every UX-00x row in `_SOURCE_MAP`.

### P1-T4 — Mine `MASTER_ISSUE_REGISTER.md` (CR / R / BB) · effort L · deps P1-T1

The largest task. The register has **three parallel schemes that must not be
summed**. Work in tranches, P0/P1 first:

1. **R-001…088** (`FINDINGS_2026-09-05.md`) — 5 P0 · 27 P1 first, then P2/UX/PARTIAL.
2. **CR-001…089** (`FUNCTIONAL_CODE_REVIEW_FINDINGS1.md`) — 63 are remediated +
   verified; open the rest. For remediated-without-a-linked-test, open a
   `RELIABILITY_TRUST` "guard missing" item.
3. **BB open (~64)** — Waves 8–22 residuals.

**Dedup:** before creating an item, `grep -ril "<keyword>" qos/backlog/` on the
journey + persona. If an R cross-closes a CR/BB twin, one QOS id, the others become
`duplicates:` rows in `_SOURCE_MAP` (not separate files).

**Yield:** ~40–70 unique items after dedup. **Time-box** each tranche to a day;
if it overruns, land what's done (frontier still works on a partial backlog) and
continue next day.

**Acceptance:** every open R P0/P1 and every open CR has a `_SOURCE_MAP` row;
`qos-lint` green.

### P1-T5 — Accepted / won't-fix from `FREEZE_SCOPE.md` · effort S · deps P1-T1

§B NOT SUPPORTED rows + §C C1–C8 KNOWN LIMITATIONS → items with
`lifecycle: accepted_wontfix`, `wontfix_rationale` = the "Why out" / caveat text,
`category` = `BUSINESS_GAP` (or `PERSONA_GAP` for archetype exclusions).

**Yield:** ~20 items. **Acceptance:** the backlog doc's "Accepted / won't-fix"
section lists all of them with rationale.

### P1-T6 — Persona / business gaps from coverage + archetypes · effort M · deps P1-T2

- `FREEZE_SCOPE_COVERAGE.md` Open GAPs + every 🟡/🚫 row not already covered by
  P1-T2 → `BUSINESS_GAP` / `PERSONA_GAP`;
- `BUSINESS_ARCHETYPES` §8 CONDITIONAL/OUT + §9 readiness dims 4/7/8/9
  "UNTESTED IN PILOT" → `PERSONA_GAP` + `DELIGHT`/`DISSATISFACTION` **hypotheses**
  (each names the agent/telemetry that would confirm it).

**Yield:** ~15–20. **Acceptance (Phase-1 exit gate):** run a cross-check script or
manual pass — **every** Open GAP line in `FREEZE_SCOPE_COVERAGE.md` resolves to
exactly one QOS id (0 unmapped, 0 double-mapped).

### P1-T7 — Innovation annex · effort S · deps P1-T1

From `reviews/18_COMPETITOR_ANALYSIS.md` + persona veto triggers +
`BUSINESS_ARCHETYPES` §10. `category: INNOVATION`, `priority: P3` or a
`review-only` marker, each with a one-line "why now / why us" and an expected-value
note. **Yield:** ~6–10.

### P1-T8 — Generate + frontier review · effort S · deps P1-T2…T7

1. `python qos/tools/build_backlog.py` → commit `docs/PRODUCT_QUALITY_BACKLOG.md`.
2. Walk the top-12 frontier with founder + QA. Adjust `effort`, `depends_on`,
   `priority_rationale` where the ordering looks wrong; regenerate.
3. Snapshot the dashboard counts into `qos/history/<yyyy-mm>.jsonl` (manual for
   now; automated in Phase 2).

**Phase 1 DoD:** frontier signed; 0 unmapped Open GAPs; categories 2/3/9 contain
**only** `hypothesis`/`heuristic` items (no fix-priority P0/P1 without observed
evidence); `_SOURCE_MAP.md` complete.

---

## Phase 2 — Loop enforcement + prioritization output

**Goal:** an item cannot be marked fixed without a real regression guard; the
frontier and dashboard trend are automated. **Effort:** ~1 week.

### P2-T1 — Lifecycle state invariants in `lint.py` · effort M · deps Phase 1

Add checks **L9–L12** (Appendix B): terminal-state ⇒ `closed` date;
`fixed|verified|guarded` ⇒ `guard_ref.test` resolves to an existing file;
`guarded` ⇒ `guard_ref.failed_at` matches a commit SHA or CI run URL pattern;
`accepted_wontfix` ⇒ non-empty `wontfix_rationale`. Extend `--selftest` fixtures.

**Acceptance:** a planted `lifecycle: fixed, guard_ref: null` item → red.

### P2-T2 — `guard_ref` resolution · effort M · deps P2-T1

For `fixed`+ items, verify the `guard_ref.test` (`path::name`) — Phase 2: the file
exists. Phase 4 upgrade: `pytest --collect-only -q <path>` contains `<name>`.
Cache the collect output; only run when a `fixed`+ item changed.

**Acceptance:** point a seed item's `guard_ref` at a non-existent file → red.

### P2-T3 — `frontier.py` complete · effort M · deps Phase 1

Implement the scoring + topo-sort from **Appendix F**: `value = priority_weight ×
impact_weight × evidence_conf ÷ effort_cost`, honour `depends_on` edges, emit
top-N + a "risk retired vs open High-impact risk" percentage. Add `--n` flag.

**Acceptance:** reproduces the P1-T8 hand-reviewed order within ±2 positions;
an item with an unmet `depends_on` never ranks above its blocker.

### P2-T4 — Dashboard trend · effort M · deps P2-T3

`qos/tools/dashboard.py`: compute counts per category, `Δ7d` / `Δ30d` from
`qos/history/*.jsonl`, `new vs closed (30d)`, and the **zero-evidence
risk-surface indicator** (journeys in the `TESTING_STRATEGY.md` inventory with no
linked test and no observation). `build_backlog.py` calls it for the doc header.

Add advisory CI job `qos-dashboard` (Appendix E): on push to `main`, append a
snapshot line and upload `qos/history/` as an artifact. (Committing history from
CI is Phase 5 — needs a write token.)

**Acceptance:** two snapshots on different dates → `Δ` column renders; deleting a
history file degrades gracefully (no crash, shows `Δ n/a`).

### P2-T5 — Governance wiring · effort S · deps P2-T4

Add a row to `pilot/GO_NO_GO.md`: "Q-OS dashboard — criticals = 0, trend
non-increasing, frontier top-N addressed for this stage". Reference the backlog
doc from `pilot/UAT_CHECKLIST.md`.

**Phase 2 DoD:** `lint.py` blocks fixed-without-guard and guarded-without-red-run;
`frontier.py` + `dashboard.py` wired into `build_backlog.py`; `qos-dashboard`
advisory job live; Go/No-Go references the dashboard.

---

## Phase 3 — Observation layer

**Goal:** categories 2 / 3 / 9 get `simulated` or `measured` evidence.
**Effort:** ~2–4 weeks *if built*. **Gated by an ADR — do not start tasks before
the decision.**

### P3-T0 — ADR: build vs defer · effort S · deps Phase 2

Write `qos/adr/0001-observation-layer.md`. Option A (build agents + telemetry) vs
Option B (defer, keep hypotheses). Decide with founder. If B: skip to Phase 4 and
revisit after pilot Stage 1.

### P3-T1 — Persona agent harness · effort L · deps P3-T0 = A

`qos/agents/` on top of Playwright + existing `web/e2e/personas/` +
`web/e2e-golden` seeds. One agent per priority journey:
`onboarding` (P1), `pos_checkout` (P2), `b2b_invoice_loop` (P3/P5),
`month_end_gstr` (P5/P6). Each run emits
`qos/observations/<journey>.<persona>.json`:

```json
{ "journey":"onboarding","persona":"P1","run_id":"...","ts":"...",
  "steps":9,"wall_clock_s":214,"backtracks":2,"dead_ends":1,
  "modal_interrupts":3,"errors_shown":1,"abandoned_at":"step:6:add-price-list",
  "budget":{"steps":3,"wall_clock_s":120},"result":"BUDGET_EXCEEDED" }
```

**Acceptance:** each of the 4 agents runs headless in CI and writes a valid
observation file; budgets encode H-02 (≤35 s, no-mouse) and the onboarding
≤3-step target.

### P3-T2 — Auto-promotion hook · effort M · deps P3-T1

`qos/tools/promote.py`: for each open `hypothesis` item, if a matching
observation file exists (same `journey` + `persona`) with `result:
BUDGET_EXCEEDED`, set `evidence.strength: simulated`, append the run to
`evidence.source`, put `n=<run count>` in `evidence.detail`, and re-run scoring so
the priority cap lifts. Refutes (`result: OK` across ≥5 runs) → move to
`accepted_wontfix` with rationale "observed within budget".

**Acceptance:** ≥3 Phase-1 hypotheses get promoted or refuted with data on the
first full agent run.

### P3-T3 — Pilot telemetry schema · effort M · deps P3-T0 = A

`qos/telemetry/EVENTS.md`: event names + payloads for `activation`,
`step_funnel`, `error_shown`, `task_complete{name,duration_ms}`. A nightly query
stub (`qos/telemetry/nightly.sql` or a management command) that, for a tenant,
returns the same metrics the agents produce — feeding `measured` evidence during
pilot stages.

**Phase 3 DoD (if A):** 4 agents live; `promote.py` wired; ≥3 hypotheses resolved
with data; telemetry schema defined and returns for a seeded tenant.

---

## Phase 4 — Work the frontier (per pilot stage, ongoing)

Per stage (see `BUSINESS_ARCHETYPES` §12 sequence and the plan §B4 table):

1. **Pick** the current top-N from `frontier.py`.
2. **Fix** each; write the guard **red first** — capture the failing run/SHA into
   `guard_ref.failed_at`, then make it pass.
3. **Move** the item `in_progress → fixed → verified` (guard resolves) `→
   guarded` (`failed_at` present). `lint.py` enforces the gates.
4. **Re-observe** — run agents / pull telemetry; `promote.py` updates evidence.
5. **Re-score + regenerate** — `build_backlog.py`; snapshot the dashboard.
6. **Record** H-0x results — INCONCLUSIVE extends the experiment, it is not a pass.
7. **Report** the dashboard trend into `pilot/GO_NO_GO.md`.

**Per-stage DoD:** frontier top-N all `guarded` or explicitly deferred with
rationale; criticals still 0; `new − closed ≤ 0` for the stage.

---

## Phase 5 — Continuous operation

| Task | Cadence | Note |
|---|---|---|
| Re-mine sources into `qos/backlog/` | each pilot-stage boundary + each release | generator preserves human-owned fields (see below); `_SOURCE_MAP.md` makes it idempotent |
| `qos-dashboard` commits history | nightly | needs a CI write token — configure in Phase 5, not before |
| Rubric recalibration | quarterly | sample 10 closed items, check the score predicted the pain, adjust bands in `RUBRIC.md` |
| Anti-theatre burn-down | if `new − closed > 0` two stages running | freeze new-item intake, clear the frontier |

**Generator vs human-edit rule (implement in `build_backlog.py` / a `merge.py`):**
`recommendation`, `owner`, `priority_rationale`, `lifecycle`, `test_required`,
`guard_ref`, `depends_on`, `wontfix_rationale` are human-owned and never
overwritten. `scoring` math, `impact_band`, `priority` (recomputed from rubric),
dashboard, frontier are regenerated. The generator refuses to modify any item in
`in_progress` or later except `evidence` and `scoring`.

---

## Critical path & parallelism

```
P0-T1 ─► P0-T3 ─► P0-T5 ─► P0-T6 ─► P0-T7 ─► [Phase 0 done]
   └► P0-T2                    ▲
   └► P0-T4 ────────────────────┘ (RUBRIC feeds lint's priority cap)

[Phase 0] ─► P1-T1 ─┬─► P1-T2 ─► P1-T6 ─► P1-T8 ─► [Phase 1 done]
                    ├─► P1-T3
                    ├─► P1-T4  (longest — start early, tranche it)
                    ├─► P1-T5
                    └─► P1-T7

[Phase 1] ─► P2-T1 ─► P2-T2
         └► P2-T3 ─► P2-T4 ─► P2-T5 ─► [Phase 2 done]

[Phase 2] ─► P3-T0 ─(if A)─► P3-T1 ─► P3-T2
                          └► P3-T3
```

Parallelisable: P1-T2/T3/T4/T5/T7 by different people once P1-T1 exists.
P0-T4 (RUBRIC) can be drafted on day 1 independent of code.

**One-person estimate:** Phase 0 ≈ 5 days, Phase 1 ≈ 8–10 days, Phase 2 ≈ 5 days,
Phase 3 (if built) ≈ 10–15 days. ~5–6 weeks to a fully enforcing pipeline with
observation; ~3 weeks to "backlog + gates" (Phases 0–2).

---

## Appendix A — `qos/schema/item.schema.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://bizboard/qos/item.schema.json",
  "type": "object",
  "additionalProperties": false,
  "required": ["id","category","title","persona","journey","problem","evidence",
               "scoring","priority","priority_rationale","effort","recommendation",
               "test_required","lifecycle","owner","opened"],
  "properties": {
    "id":        { "type": "string", "pattern": "^QOS-[0-9]{4,}$" },
    "category":  { "enum": ["CRITICAL_BUG","DISSATISFACTION","USABILITY","PERSONA_GAP",
                            "BUSINESS_GAP","RELIABILITY_TRUST","CROSS_FLOW_CONSISTENCY","PERFORMANCE",
                            "SECURITY_PRIVACY","DELIGHT","INNOVATION"] },
    "title":     { "type": "string", "minLength": 8, "maxLength": 120 },
    "persona":   { "type": "array", "minItems": 1,
                   "items": { "enum": ["P1","P2","P3","P4","P5","P6"] } },
    "archetype": { "type": "array",
                   "items": { "enum": ["ARCH-01","ARCH-02","ARCH-03","ARCH-04",
                                       "ARCH-05","ARCH-06","ARCH-07"] } },
    "journey":   { "type": "string", "minLength": 3 },
    "problem":   { "type": "string", "minLength": 40 },
    "evidence": {
      "type": "object", "additionalProperties": false,
      "required": ["strength","source","detail"],
      "properties": {
        "strength": { "enum": ["measured","simulated","single-run","heuristic","hypothesis"] },
        "source":   { "type": "array", "minItems": 1, "items": { "type": "string" } },
        "detail":   { "type": "string", "minLength": 10 }
      }
    },
    "scoring": {
      "type": "object", "additionalProperties": false,
      "required": ["reach","severity","frequency","impact_band"],
      "properties": {
        "reach":     { "type": "integer", "minimum": 1, "maximum": 5 },
        "severity":  { "type": "integer", "minimum": 1, "maximum": 5 },
        "frequency": { "type": "integer", "minimum": 1, "maximum": 5 },
        "impact_band": { "enum": ["High","Medium","Low"] }
      }
    },
    "business_metric": { "enum": ["activation","time_to_first_invoice",
                                  "support_ticket_rate","renewal","nps","referral","none"] },
    "priority": { "type": "string", "pattern": "^P[0-3](-investigate|-confirm)?$" },
    "priority_rationale": { "type": "string", "minLength": 10 },
    "effort": { "enum": ["S","M","L","XL"] },
    "recommendation": { "type": "string", "minLength": 30 },
    "test_required":  { "type": "string", "minLength": 15 },
    "guard_ref": {
      "oneOf": [
        { "type": "null" },
        { "type": "object", "additionalProperties": false, "required": ["test"],
          "properties": { "test": { "type": "string" },
                          "failed_at": { "type": "string" } } }
      ]
    },
    "lifecycle": { "enum": ["open","investigating","accepted_wontfix",
                            "in_progress","fixed","verified","guarded"] },
    "wontfix_rationale": { "type": "string" },
    "depends_on": { "type": "array", "items": { "type": "string", "pattern": "^QOS-[0-9]{4,}$" } },
    "supersedes": { "type": "array", "items": { "type": "string", "pattern": "^QOS-[0-9]{4,}$" } },
    "duplicates": { "type": "array", "items": { "type": "string", "pattern": "^QOS-[0-9]{4,}$" } },
    "owner": { "type": "string", "minLength": 2 },
    "opened": { "type": "string", "format": "date" },
    "closed": { "oneOf": [ { "type": "null" }, { "type": "string", "format": "date" } ] }
  },
  "allOf": [
    { "if": { "properties": { "lifecycle": { "enum": ["fixed","verified","guarded"] } } },
      "then": { "properties": { "guard_ref": { "type": "object" } } } },
    { "if": { "properties": { "lifecycle": { "const": "guarded" } } },
      "then": { "properties": { "guard_ref": { "required": ["failed_at"] } } } },
    { "if": { "properties": { "lifecycle": { "const": "accepted_wontfix" } } },
      "then": { "required": ["wontfix_rationale"],
                "properties": { "wontfix_rationale": { "minLength": 15 } } } },
    { "if": { "properties": { "lifecycle": { "enum": ["guarded","accepted_wontfix"] } } },
      "then": { "properties": { "closed": { "type": "string" } } } }
  ]
}
```

## Appendix B — `lint.py` check list

| # | Check | Fail message |
|---|---|---|
| L1 | Each `qos/backlog/*.yaml` parses and validates against the schema | `<file>: schema: <err>` |
| L2 | `id` unique across files; filename == `<id>.yaml` | `duplicate id <id>` / `filename != id` |
| L3 | **Priority cap:** `hypothesis` ⇒ priority ∈ {P1-investigate,P2,P3}; `heuristic` ⇒ ∉ {P0,P0-confirm}; `single-run` ⇒ P0 only as `P0-confirm`. Exempt: `category==SECURITY_PRIVACY and scoring.severity==5` | `<id>: <strength> evidence cannot be <priority>` |
| L4 | `simulated` ⇒ `evidence.detail` matches `n=(\d+)` with n≥5, **or** an `evidence.source` entry points at an existing `qos/observations/*.json` | `<id>: simulated needs n>=5 or an observation file` |
| L5 | `impact_band` equals `impact_band(scoring)` recomputed from the rubric | `<id>: impact_band <got> != <expected>` |
| L6 | `depends_on` / `supersedes` / `duplicates` reference existing ids; no self-reference; `depends_on` has no cycle | `<id>: dangling ref <ref>` / `cycle: <path>` |
| L7 | `docs/PRODUCT_QUALITY_BACKLOG.md` == `build_backlog.py` output | `backlog doc is stale — run build_backlog.py` |
| L8 | Every `TESTING_STRATEGY.md` Open GAP id (`G-\d+`) appears in `_SOURCE_MAP.md` | `unmapped gap: <G-id>` (warn in Phase 1, fail from Phase 1 DoD) |
| L9 | terminal lifecycle (`guarded`/`accepted_wontfix`) ⇒ `closed` set; non-terminal ⇒ `closed` null | `<id>: closed inconsistent with lifecycle` |
| L10 | `fixed`/`verified`/`guarded` ⇒ file in `guard_ref.test` (before `::`) exists | `<id>: guard_ref.test file missing` |
| L11 | `guarded` ⇒ `guard_ref.failed_at` matches `^[0-9a-f]{7,40}$` or an `https://` run URL | `<id>: guarded needs red-then-green ref` |
| L12 | `accepted_wontfix` ⇒ `wontfix_rationale` ≥ 15 chars | `<id>: wontfix needs a rationale` |

`--selftest`: `qos/tools/_selftest/*.yaml` — one fixture per L2/L3/L4/L6/L10/L11;
each must trip exactly its check and nothing else.

## Appendix C — `build_backlog.py` output contract

```
# Product Quality Backlog  (GENERATED by qos/tools/build_backlog.py — do not edit)

<dashboard block — from dashboard.py>

## Do next — sequenced frontier (top 12)
<frontier table: rank | id | title | category | priority | effort | value | moves | blocked_by>
Risk retired by the top 12: <pct>% of open High-impact risk.

## 1. Critical bugs        (<n> open)
| id | title | persona | journey | priority | effort | evidence | owner |
...
## 2. Dissatisfaction      (<n> open)
...
(one section per category, items sorted by priority then id, id links to the yaml)

## Accepted / won't-fix     (<n>)
| id | title | why | source |
...

## Innovation (review-only) (<n>)
| id | title | why now / why us | expected value |
```

Deterministic: no timestamps in the body; sort keys fixed; trailing newline.

## Appendix D — sample `qos/backlog/QOS-0001.yaml`

> Historical sample from 2026-09-10. **G-4 is closed** (2026-09-13): `role-boundaries.spec.ts` is live for SALES and ACCOUNTANT; live YAML is `qos/backlog/QOS-0001.yaml` (`lifecycle: verified`). Do not copy the `test.fixme` problem text into new items.

```yaml
id: QOS-0001
category: DISSATISFACTION
title: "UI may render controls that 403 for SALES_STAFF and ACCOUNTANT"
persona: [P2, P5]
archetype: [ARCH-03, ARCH-01]
journey: "Everyday navigation as a non-owner role"
problem: >
  Backend RBAC is fully asserted, but the frontend test that proves the UI HIDES
  what a role cannot do is test.fixme-skipped for SALES_STAFF and ACCOUNTANT.
  A control that renders and then 403s on click is exactly the P2/P5 trust-eroding
  friction the personas veto on.
evidence:
  strength: heuristic
  source:
    - "TESTING_STRATEGY.md#7 G-4"
    - "web/e2e/personas/role-boundaries.spec.ts (test.fixme blocks)"
    - "UX_AUDIT_FINDINGS.md UX-002 (historical 403 spam, fixed, now unguarded)"
  detail: >
    Not observed with users; inferred from the skipped FE coverage and the prior
    UX-002 incident. Confirm with a SALES/ACCT persona agent nav sweep.
scoring:
  reach: 4
  severity: 3
  frequency: 4
  impact_band: High
business_metric: support_ticket_rate
priority: P1
priority_rationale: "High impact (reach 4 x sev 3 x freq 4 = 48); heuristic evidence caps at P1."
effort: M
recommendation: >
  Add loginAsSales / loginAsAccountant seeds to web/e2e/helpers/auth.ts and
  un-fixme the SALES and ACCOUNTANT describe blocks in role-boundaries.spec.ts;
  assert no create/mutate control renders for those roles on journals, users,
  and sales routes.
test_required: "role-boundaries.spec.ts green for all four roles in the e2e CI job"
guard_ref: null
lifecycle: open
depends_on: []
supersedes: []
duplicates: []
owner: web
opened: 2026-09-10
closed: null
```

## Appendix E — CI jobs (`.github/workflows/ci.yml`)

```yaml
  qos-lint:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.13" }
      - run: pip install -r qos/tools/requirements.txt
      - run: python qos/tools/lint.py
      - name: Backlog doc in sync
        run: |
          python qos/tools/build_backlog.py
          git diff --exit-code docs/PRODUCT_QUALITY_BACKLOG.md
      - run: python qos/tools/lint.py --selftest

  qos-dashboard:            # advisory, main only (Phase 2)
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.13" }
      - run: pip install -r qos/tools/requirements.txt
      - run: python qos/tools/dashboard.py --append qos/history/$(date +%Y-%m).jsonl
      - uses: actions/upload-artifact@v4
        with: { name: qos-history, path: qos/history/ }
```

Add `qos-lint` to `scripts/ci_gates/REQUIRED_CHECKS.txt`.

## Appendix F — `frontier.py` scoring

```python
PRIO_W   = {"P0":100, "P0-confirm":80, "P1":40, "P1-investigate":20, "P2":10, "P3":3}
IMPACT_W = {"High":3, "Medium":2, "Low":1}
EV_CONF  = {"measured":1.0, "simulated":0.9, "single-run":0.7, "heuristic":0.5, "hypothesis":0.3}
EFFORT_C = {"S":1, "M":3, "L":8, "XL":20}

def value(item):
    p = PRIO_W[item["priority"]]
    i = IMPACT_W[item["scoring"]["impact_band"]]
    e = EV_CONF[item["evidence"]["strength"]]
    c = EFFORT_C[item["effort"]]
    return round(p * i * e / c, 2)

# open = lifecycle in {open, investigating, in_progress}
# 1. build depends_on DAG over open items
# 2. topological layers; within a layer sort by value() desc, then priority, then id
# 3. take first N respecting: never emit an item before an unresolved depends_on
# 4. risk_retired = sum(IMPACT_W*EV_CONF for top-N) / sum(same for all open High/Med)
```

---

## What to hand your executor

1. This runbook + `Q-OS_QUALITY_PIPELINE_PLAN.md`.
2. Start at **P0-T1**. Do Phase 0 in order (critical path above).
3. Phase 1 is the content grind — parallelise P1-T2…T7, keep `_SOURCE_MAP.md`
   honest, don't block on P1-T4 completeness (tranche it).
4. Gate: don't start Phase 2 until the Phase 1 DoD checklist is fully ticked.
5. Phase 3 only after the ADR (P3-T0) is signed.
