# Q-OS — Product Quality Pipeline: Implementation & Execution Plan

**Status:** Plan — for build · **Created:** 2026-09-10 · **Owner:** QA + founder
**Purpose:** Turn testing evidence into an **actionable Product Quality Backlog** —
"find everything preventing the product from being correct, usable, satisfying,
successful and delightful, then say exactly what to fix or build next" — with the
rigor additions that keep it a *plan* and not a prettier list.

**Reference implementation:** Bizboard. The pipeline is product-agnostic; Bizboard
is where it is first stood up and proven.

**Relationship to existing docs:**

| Doc | Role in Q-OS |
|---|---|
| [`TESTING_STRATEGY.md`](TESTING_STRATEGY.md) | The analysis layer Q-OS consumes — **L1–L10** method, per-journey question set, gap register. Philosophy: `HOLISTIC_VALIDATION_REVIEW.md` |
| [`HOLISTIC_VALIDATION_REVIEW.md`](HOLISTIC_VALIDATION_REVIEW.md) | Quality model Q-OS must not duplicate — Flow / Impact / Truth graphs. Q-OS is **output**, not a second layer system |
| [`BUSINESS_ARCHETYPES_AND_PERSONAS.md`](BUSINESS_ARCHETYPES_AND_PERSONAS.md) | Persona / archetype / journey vocabulary; validation hypotheses H-01…H-05 = delight/outcome thresholds |
| [`FREEZE_SCOPE.md`](FREEZE_SCOPE.md) / [`FREEZE_SCOPE_COVERAGE.md`](FREEZE_SCOPE_COVERAGE.md) | Scope boundary + per-item gated/GAP status → seeds the backlog and the "accepted / won't-fix" set |
| [`reviews/MASTER_ISSUE_REGISTER.md`](reviews/MASTER_ISSUE_REGISTER.md), [`reviews/UX_AUDIT_FINDINGS.md`](reviews/UX_AUDIT_FINDINGS.md) | Historical findings mined into the backlog (with the multi-scheme dedup problem this plan explicitly fixes) |
| [`pilot/GO_NO_GO.md`](pilot/GO_NO_GO.md), [`pilot/UAT_CHECKLIST.md`](pilot/UAT_CHECKLIST.md) | Consume the Q-OS dashboard trend as a gate input |

---

## Part A — The method (design)

### A1. Pipeline stages

```
Product → Understand → Generate Tests → Execute → Observe → Reason
        → Identify Problems → Prioritize → Recommend → Re-test → (loop)
```

| Stage | Input | Output | Runner | Bizboard substrate |
|---|---|---|---|---|
| **Understand** | Codebase, docs, personas | Journey inventory + risk surface (every persona × journey, marked "has evidence / none") | Human + `TESTING_STRATEGY.md` | §2–§5 of the strategy doc |
| **Generate tests** | Journey inventory | L1–L6 tests per journey (invariants, contracts, WF chains, PJ journeys, matrices, e2e) | Dev | `core/invariants/`, `tests/workflows/`, `tests/personas/`, `web/e2e/` |
| **Execute** | Test suite | Pass/fail + coverage + snapshots + query counts | CI | `.github/workflows/ci.yml` (11 jobs) |
| **Observe** | Journeys, real + synthetic use | Friction metrics: step count, wall-clock, backtracks, dead-ends, abandonment point, error-shown rate | **Q-OS observation layer (Phase 3 — new)** + pilot telemetry | none yet — this is the build decision |
| **Reason** | Execute + Observe outputs | Candidate findings, each with a hypothesis about user impact | Human + Q-OS synthesis | strategy §7 gap register is a worked example |
| **Identify** | Candidate findings | Backlog items in the A2 schema, one stable ID each, deduped | Q-OS generator + human curation | replaces the 3-scheme register |
| **Prioritize** | Backlog items | Scored items + a **sequenced frontier** (top-N with deps/effort/risk-retired) | Q-OS `frontier` tool + review | new |
| **Recommend** | Frontier | Concrete fix / feature per item + the regression guard it needs | Human | — |
| **Re-test** | Landed fix | Guard exists, has failed-then-passed, item → `guarded` | CI gate | red-then-green rule, `guard_regression_corpus_grows` pattern |

### A2. The backlog-item schema (the heart of the fix)

One stable ID scheme (`QOS-NNNN`), never reused. One file per item under
`qos/backlog/` (source of truth); `docs/PRODUCT_QUALITY_BACKLOG.md` is a generated
view.

```yaml
id: QOS-0007
category: DISSATISFACTION        # one of the 10 (A4)
title: "Onboarding requires 9 steps for a first-time user"
persona: [P1]                    # BUSINESS_ARCHETYPES personas
archetype: [ARCH-03, ARCH-01]    # optional
journey: "First-run onboarding"  # a named journey/loop

problem: >
  A first-time owner must re-enter information the system could infer (GSTIN →
  legal name / state; PIN → state). Optional configuration is not deferrable, so
  the shortest path to a first invoice is 9 screens.

evidence:
  strength: hypothesis           # measured | simulated | single-run | heuristic | hypothesis
  source:
    - "web/e2e-golden/personas-golden.spec.ts (registration path length)"
    - "UX_AUDIT_FINDINGS.md Module 1"
  detail: >
    Not yet observed with users. Would be confirmed by a synthetic P1-owner
    onboarding agent run (target: abandonment rate, median step count).

scoring:
  reach: 5          # every new tenant hits it
  severity: 3       # frustrates, does not block or corrupt
  frequency: 1      # once per tenant lifetime
  impact_band: Medium         # = f(reach, severity, frequency) per RUBRIC.md
business_metric: activation    # activation | time_to_first_invoice | support_ticket_rate | renewal | none

priority: P1-investigate       # derived, then capped by evidence.strength (A3)
priority_rationale: "High reach, but hypothesis-grade evidence caps it at investigate."

effort: M                      # S <1d | M <1wk | L <1mo | XL epic
recommendation: >
  Collapse to 3 steps: (1) GSTIN + verify → auto-fill name/state/PIN;
  (2) first product OR skip; (3) done → land on New Invoice. Move price lists,
  godowns, users, branding to a dismissible "finish setup" checklist.
test_required: "PJ-NEWUSER asserts <=3 screens to first invoice; onboarding agent abandonment < 10%"
guard_ref: null                # filled when the guard lands: path::test_name

lifecycle: open                # open | investigating | accepted_wontfix | in_progress | fixed | verified | guarded
supersedes: []
duplicates: []
owner: web
opened: 2026-09-10
closed: null
```

**Required for every item:** `persona`, `journey`, `evidence.strength`,
`scoring`, `recommendation`, `test_required`. `qos-lint` rejects an item missing
any of these.

### A3. Scoring rubric (calibrated, fixed up front — `qos/RUBRIC.md`)

**Impact = f(reach, severity, frequency)**, each a defined 1–5 band. No free-text
"High".

| Axis | 5 | 4 | 3 | 2 | 1 |
|---|---|---|---|---|---|
| **Reach** — of the affected persona population | ~all | majority | ~half | minority | edge |
| **Severity** | data loss / money wrong / security breach | blocks the task, no workaround | blocks with a workaround / clear frustration | mild friction | cosmetic |
| **Frequency** | every session | daily | weekly | monthly | rare |

`impact_band`: `High` if `reach*severity*frequency ≥ 45` **or** any `severity = 5`;
`Medium` 18–44; `Low` < 18.

**Priority** = impact_band mapped to `P0/P1/P2/P3`, **then capped by evidence
strength** — the rule that stops P0s being minted from hunches:

| evidence.strength | max priority allowed |
|---|---|
| `measured` (real telemetry) or `simulated` (agent, n ≥ 5) | P0 |
| `single-run` (one agent/manual pass) | P0 **only with** `-confirm` suffix and a scheduled confirmation run |
| `heuristic` (static analysis, expert read) | P1 |
| `hypothesis` (inferred, not observed) | **P1-investigate** — never a fix priority, only an investigation priority |

`security` findings with `severity = 5` are exempt from the cap (assume-true until
disproven).

### A4. The 10 categories — each with an exit bar

The backlog is done for a category when its exit bar is met. Exit bars tie to a
business or pilot-hypothesis outcome, not to "list is empty".

| # | Category | Exit bar (target state) | Outcome link |
|---|---|---|---|
| 1 | **Critical bugs** | 0 open; every past critical has a `guarded` regression test | — (hard gate) |
| 2 | **Dissatisfaction** | Every SUPPORTED journey observed (agent or telemetry); no open item with `severity ≥ 3` and `reach ≥ 4` | support_ticket_rate, renewal |
| 3 | **Usability improvements** | Top-20 routes: 1 smoke + axe each; every primary journey ≤ its step budget | activation, time_to_first_invoice |
| 4 | **Persona gaps** | Every SUPPORTED archetype has a green `PJ-*` for every staffed persona; CONDITIONAL archetypes have a documented boundary + its guard | archetype fit / expansion |
| 5 | **Business gaps** | Every rule in `FREEZE_SCOPE.md` §A/§G marked SUP has a chain or invariant; missing-report list empty or accepted | compliance, CA acceptance (H-05) |
| 6 | **Reliability & trust** | Every failure path has a "visible state, no data loss" test; `H-01`/`H-03` PASS | renewal, support_ticket_rate |
| 7 | **Performance** | Executed load smoke green (p95 budget, 0 5xx); large-tenant fixture report/export within budget | activation at scale, churn |
| 8 | **Security & privacy** | Every inbound webhook has a forgery test; tenant-isolation sweep green; pen-test findings triaged | trust, contractual |
| 9 | **Delight opportunities** | `H-02` PASS (not INCONCLUSIVE); ≥ N shipped friction removals per pilot stage with before/after metric | NPS, referral, retention |
| 10 | **Innovation opportunities** | Each carries a "why now / why us" test and an expected-value rationale; reviewed, not auto-scheduled | expansion revenue |

### A5. Lifecycle & loop enforcement

```
open → investigating → (accepted_wontfix | in_progress) → fixed → verified → guarded
```

- **`accepted_wontfix`** requires a rationale and moves the item into the backlog
  doc's **"Accepted / won't-fix"** section (seeded from `FREEZE_SCOPE.md` §B NOT
  SUPPORTED + C1–C8 KNOWN LIMITATIONS). Stakeholders stop re-raising these.
- **`fixed` → `verified`** requires the `test_required` guard to exist and be in
  the running suite.
- **`verified` → `guarded`** requires **red-then-green attestation**:
  `guard_ref` links a commit/CI run where the guard *failed* before the fix.
  This is Bizboard's proven rule (`test_invariants_smoke.py`,
  `guard_regression_corpus_grows`), reused.
- CI job **`guard_qos_backlog`** fails the build if: any item in `fixed`+ has no
  resolvable `guard_ref`; any `P0` violates the evidence cap; any duplicate ID;
  any illegal lifecycle transition; the generated `PRODUCT_QUALITY_BACKLOG.md` is
  out of sync with `qos/backlog/`.

### A6. Prioritization output — the sequenced frontier

Per-item `P0/P1` tags are not a plan. `qos/tools/frontier.py` emits an **ordered
top-N** for the current milestone:

- sort by `priority`, then `risk_retired / effort` (risk_retired = impact_band
  weight × evidence confidence);
- carry **dependency edges** (item B needs A first);
- annotate each with effort band and the metric it moves;
- output to the backlog doc header as "Do these next, in this order — retires X%
  of open High-impact risk before pilot Stage N".

### A7. Dashboard — snapshot **and** derivative

```
🔴 Critical bugs         : 0        (Δ30d  0)   guarded: 63/63
🟠 Dissatisfaction       : 9        (Δ30d +3)   observed: 2/9 journeys
🟡 Usability             : 21       (Δ30d -4)
🟣 Persona gaps          : 8        (Δ30d  0)
🔵 Business gaps          : 5        (Δ30d -2)
🟤 Reliability & trust    : 6        (Δ30d -1)
🟢 Performance            : 4        (Δ30d  0)   load smoke: NOT RUN
🟠 Security & privacy     : 5        (Δ30d -1)
✨ Delight                : 12       shipped this stage: 3 (before/after logged)
💡 Innovation             : 9        (review-only)

Leading indicator — risk surface with ZERO evidence of any kind: 14 / 62 journeys (23%)
New findings vs closed (30d): +11 / -13   → net closing
```

`qos/history/*.jsonl` stores daily counts; the derivative and the
zero-evidence indicator are the real signal.

### A8. The observation layer — the build-or-don't decision, made explicit

Categories 2, 3, 9 cannot be `measured`/`simulated` without this. Two options,
decided in a written ADR at Phase 3 start:

**Option A — build it (recommended).**
- **Synthetic persona agents** (`qos/agents/`): scripted journeys on top of
  Playwright + the existing `PJ-*` / `web/e2e/personas/` seeds. Each run emits
  `qos/observations/<journey>.<persona>.json`: step count, wall-clock, backtracks,
  dead-ends hit (403 / empty state / disabled control), modal interruptions,
  abandonment point, error-shown count.
- **Thresholds** from the validation hypotheses (H-02 ≤ 35 s no-mouse; onboarding
  ≤ 3 steps; H-03 zero dup/loss) and new budgets.
- **Auto-promotion:** when an agent run produces evidence matching an open
  `hypothesis` item, the generator promotes it to `simulated (n=k)` and lifts the
  priority cap.
- **Pilot telemetry** (parallel, higher grade): event schema for activation, step
  funnels, `error-shown`, task-complete time; a nightly query feeds `measured`
  evidence for the same items during pilot stages.

**Option B — defer.** Keep 2/3/9 as `hypothesis`, do not let them drive fix
priority, and revisit after pilot Stage 1 produces real telemetry. Choose this
only if agent-build cost can't be funded this cycle.

---

## Part B — Execution plan (phased)

Durations are indicative for a 1–2 person effort; they compress with more hands.
"Today" = 2026-09-10.

### Phase 0 — Foundations · effort M · ~1 week

| Task | Deliverable | Acceptance |
|---|---|---|
| Commit the item schema | `qos/schema/item.schema.json` | validates the A2 example |
| Write the rubric | `qos/RUBRIC.md` (A3 tables) | founder + QA sign-off |
| Pick the ID scheme + layout | `qos/README.md`, `qos/backlog/` (one YAML/item), `qos/history/` | documented; no second scheme allowed |
| Scaffold `qos-lint` | CI job: schema-valid, unique IDs, required fields, evidence cap, doc-in-sync | green on a 3-item seed |
| Generator skeleton | `qos/tools/build_backlog.py` → `docs/PRODUCT_QUALITY_BACKLOG.md` | round-trips the seed |

### Phase 1 — Backfill the backlog from existing evidence · effort M–L · ~1–2 weeks

Mine, dedupe, and normalise everything already known.

| Source | Feeds category | Notes |
|---|---|---|
| `TESTING_STRATEGY.md` §7 (G-1…G-16, determinism, mutation) | 4,5,6,7,8 + 2,3,9 (as hypothesis) | each already has impact/priority/owner/test — near-direct map |
| `reviews/UX_AUDIT_FINDINGS.md` + `_WAVE2_` (UX-001…) | 2,3 | most are "Fixed & Verified" → open a `guarded`-candidate item only where no regression test exists |
| `reviews/MASTER_ISSUE_REGISTER.md` — open CR / R / BB | 1,5,6,8 | **dedupe across the 3 schemes** (the register itself warns not to sum them); one QOS id per real defect, `duplicates:` links the twins |
| `FREEZE_SCOPE.md` §B NOT SUPPORTED + §C C1–C8 | **Accepted / won't-fix section** | rationale carried verbatim |
| `FREEZE_SCOPE.md` §G/§H marked SUP but 🟡/⛔/🚫 in coverage | 4,5 | 1:1 with the coverage doc's Open GAPs |
| `BUSINESS_ARCHETYPES` §8 CONDITIONAL/OUT, §9 readiness dims 4/7/8/9 "UNTESTED" | 4,9 | ARCH-05 drug forms, ARCH-07 milestone billing, etc. |
| `18_COMPETITOR_ANALYSIS.md` + persona veto triggers | 10 | speculative annex, review-only |

**Deliverables:** `qos/backlog/*.yaml` (~60–90 items), generated
`docs/PRODUCT_QUALITY_BACKLOG.md` with dashboard v1 + the sequenced top-12
frontier + the Accepted/won't-fix section.

**Acceptance:**
- every open GAP in `FREEZE_SCOPE_COVERAGE.md` maps to exactly one QOS item;
- no item missing persona / journey / evidence.strength / test_required;
- categories 2, 3, 9 contain **only** `hypothesis` items, each naming the agent or
  telemetry that would confirm it;
- founder signs the top-12 frontier.

### Phase 2 — Loop enforcement + prioritization output · effort M · ~1 week

| Task | Deliverable | Acceptance |
|---|---|---|
| Lifecycle state machine in `qos-lint` | legal-transition table enforced | illegal transition → red |
| `guard_qos_backlog` CI job | (A5) — resolvable `guard_ref`, evidence cap, dedup, doc sync | a planted "fixed, no guard" item → red in a dry run |
| Red-then-green attestation | `guard_ref` schema requires a `failed_at` commit/run ref | missing ref blocks `verified → guarded` |
| `frontier.py` | ordered top-N with dependency edges + effort + metric | reproduces the Phase-1 manual top-12 (±2) |
| Dashboard trend | `qos/history/` daily snapshot + `Δ30d` + zero-evidence indicator + new-vs-closed | rendered in the backlog doc header |
| Wire into governance | `pilot/GO_NO_GO.md` gains a "Q-OS dashboard trend" input row | referenced |

### Phase 3 — Observation layer · effort L · ~2–4 weeks

| Task | Deliverable | Acceptance |
|---|---|---|
| **ADR: build vs defer** (A8) | `qos/adr/0001-observation-layer.md` | decided, signed |
| *(if build)* persona agents | `qos/agents/` — onboarding (P1), POS checkout (P2), B2B invoice loop (P3/P5), month-end + GSTR (P5/P6) | each emits the friction JSON on a CI cadence |
| Thresholds | encoded from H-02/H-03 + new step budgets | agent fails when budget exceeded |
| Auto-promotion hook | generator lifts `hypothesis → simulated(n=k)` + re-scores | ≥ 3 Phase-1 hypotheses promoted or refuted with data |
| Pilot telemetry schema | `qos/telemetry/EVENTS.md` + nightly query stub | events defined; query returns for a seeded tenant |

### Phase 4 — Work the frontier / close the loop · ongoing, per pilot stage

Each pilot stage (per `BUSINESS_ARCHETYPES` §12 sequence):

1. Fix the current top-N; land each guard **red-then-green**.
2. Re-run agents + pull telemetry; promote/refute hypotheses.
3. Re-score, regenerate the frontier, snapshot the dashboard.
4. Record H-0x results (INCONCLUSIVE extends the experiment — it is not a pass).
5. Dashboard trend → Go/No-Go input.

**Stage-aligned targets:**

| Pilot stage | Q-OS focus |
|---|---|
| Stage 1 (ARCH-01 POS) | category 9 (H-02), category 2 counter-clerk friction, category 7 POS latency |
| Stage 2 (ARCH-03 loop) | category 5/6 (H-01), category 4 trader personas, category 3 back-office UX |
| Stage 3 (CA) | category 5 (H-05), category 8 audit trail, category 1 tax correctness |
| Stage 4 (ARCH-04/05/06) | category 4 specialised persona gaps, category 6 inventory trust |

### Phase 5 — Continuous operation

- **Regeneration cadence:** re-mine sources at every pilot-stage boundary and
  every release.
- **Human-edit survival:** `recommendation`, `owner`, `priority_rationale`,
  `lifecycle`, `test_required`, `guard_ref` are human-owned and never overwritten
  by the generator; `scoring` math, `impact_band`, dashboard, frontier are
  recomputed. Generator refuses to touch any item in `in_progress`+ except
  `evidence` and `scoring`.
- **Rubric recalibration:** quarterly — sample 10 closed items, check the score
  predicted the pain; adjust bands.
- **Anti-theatre check:** if `new − closed > 0` for two consecutive stages, stop
  adding and burn down.

---

## Part C — Concrete wiring

### C1. Repository layout

```
qos/
  README.md                  # pipeline stages, ownership, cadence
  RUBRIC.md                  # A3 scoring + priority cap
  schema/item.schema.json
  backlog/QOS-0001.yaml ...  # source of truth, one file per item
  history/2026-09.jsonl      # daily dashboard snapshots
  tools/
    build_backlog.py         # backlog/*.yaml -> docs/PRODUCT_QUALITY_BACKLOG.md
    frontier.py              # sequenced top-N
    lint.py                  # invoked by CI (qos-lint / guard_qos_backlog)
  agents/                    # Phase 3 — synthetic persona journeys
  observations/              # Phase 3 — agent output
  telemetry/EVENTS.md        # Phase 3 — pilot event schema
  adr/0001-observation-layer.md
docs/
  PRODUCT_QUALITY_BACKLOG.md # GENERATED — do not hand-edit
```

### C2. CI jobs to add (`.github/workflows/ci.yml`)

| Job | Blocking? | Does |
|---|---|---|
| `qos-lint` | yes | schema, unique IDs, required fields, evidence cap, doc-in-sync |
| `guard_qos_backlog` | yes | lifecycle legality, resolvable `guard_ref` for `fixed`+ items, red-then-green ref present |
| `qos-dashboard` | no (advisory) | append today's snapshot to `qos/history/`, render trend |
| `qos-agents` | no (advisory, Phase 3) | run persona agents, emit friction JSON, auto-promote hypotheses |

Reuse the existing `scripts/ci_gates/run_guards.py` + `--selftest` convention so
each Q-OS guard proves it can fail.

### C3. Mapping to Bizboard's existing gates

| Existing | Q-OS use |
|---|---|
| `INVARIANTS_STRICT=1` sweep | evidence source for categories 1, 6 (`measured`) |
| `guard_regression_corpus_grows` + `.corpus_count` | prior art for `guard_qos_backlog`'s guard-must-exist rule |
| `guard_ca_tax_parity` (F1–F8) | evidence for category 5 (H-05 proxy) |
| `PJ-*` journeys + `web/e2e/personas/` | agent seeds for Phase 3 |
| `pilot/UAT_CHECKLIST.md`, `GO_NO_GO.md` | consume the dashboard trend |
| `FREEZE_SCOPE_COVERAGE.md` Open GAPs | 1:1 seed for categories 4/5 |

### C4. Worked examples (from the strategy doc's gap register)

| G-id | → QOS item | Category | evidence.strength | priority |
|---|---|---|---|---|
| G-4 (FE SALES/ACCT role-hiding `test.fixme`) | "UI may render dead controls that 403 for SALES/ACCOUNTANT" | DISSATISFACTION | heuristic | P1 |
| G-7 (no executed load test) | "Pilot scale unvalidated — no load/soak/large-tenant test" | PERFORMANCE | heuristic | P1 |
| G-8 (per-webhook forgery not enumerated) | "Not every inbound webhook has a signature-forgery test" | SECURITY_PRIVACY | heuristic | P1 (sev-5 exempt from cap) |
| G-1 (no Godown-Keeper journey) | "Missing PJ journey for P4 at a departmental firm" | PERSONA_GAP | heuristic | P2 |
| G-14 (no CA has filed from worksheets) | "CA acceptance (H-05) unproven" | BUSINESS_GAP | hypothesis | P1-investigate |
| WF-11 skipped (recurring invoices) | "Recurring invoices re-typed every cycle" | DELIGHT | hypothesis | P2 |
| — (from competitor analysis) | "One-click GSTR filing via GSP" | INNOVATION | hypothesis | review-only |

---

## Part D — Risks & anti-goals for Q-OS itself

| Risk | Mitigation |
|---|---|
| **Backlog theatre** — many items, few closes | `new − closed` trend gate (Phase 5); frontier forces a burn-down order |
| **Rubric drift** — everyone scores "High" | fixed bands (A3), quarterly recalibration against closed items |
| **Hunch-driven P0s** | evidence-strength cap (A3) — hard rule in `qos-lint` |
| **Generator vs human edit conflict** | human-owned fields never regenerated (Phase 5); generator locks `in_progress`+ |
| **Observation layer becomes a cost sink** | Phase-3 ADR scopes it to 4 journeys; advisory lane; Option B exit |
| **Dashboard vanity metrics** | the load-bearing numbers are the derivative and the zero-evidence indicator, not the raw counts |
| **Delight/innovation crowd out correctness** | categories 9/10 can never exceed P2 without `measured` evidence; category 1 exit bar is a hard gate |
| **Second ID scheme creeps in** | `qos/README.md` forbids it; `qos-lint` rejects non-`QOS-` ids; historical schemes are *sources*, not *stores* |

---

## Immediate next step

Execute **Phase 1** against Bizboard now: mine `TESTING_STRATEGY.md` §7 +
`UX_AUDIT_FINDINGS.md` + the open CR/R/BB register + `FREEZE_SCOPE` limitations
into `qos/backlog/*.yaml` and generate `docs/PRODUCT_QUALITY_BACKLOG.md` v1 with
the dashboard and the sequenced top-12. Phase 0 scaffolding (schema, rubric,
lint) lands alongside it.
