# ADR 0001 — Observation layer for categories 2 / 3 / 9

**Status:** Accepted (provisional) — decision recorded 2026-09-10; formal founder
ratification tracked as **QOS-0052**. Mandatory revisit trigger: the start of
pilot Stage 1 (see "Decision" below).
**Date raised:** 2026-09-10
**Context runbook task:** P3-T0

## Context

Q-OS categories `DISSATISFACTION`, `USABILITY`, and `DELIGHT` describe things that
are technically correct but frustrating, hard to discover, or a missed chance to
remove friction. Bizboard has strong evidence for correctness / reliability /
security (invariants, workflow chains, tenancy sweeps, CI) but **no observation
layer** for how a real or simulated persona actually experiences a journey:
step count, wall-clock, backtracks, dead-ends hit, abandonment point.

Without it, every item in categories 2/3/9 is `evidence.strength: hypothesis` and
the rubric caps it at `P1-investigate` — it can never become a fix priority.
`docs/BUSINESS_ARCHETYPES_AND_PERSONAS.md` §9 readiness dimensions 4/7/8/9 are all
"UNTESTED IN PILOT" for the same reason.

## Options

### Option A — build it

1. **Synthetic persona agents** (`qos/agents/`) on top of Playwright + the
   existing `web/e2e/personas/` and `web/e2e-golden` seeds. One agent per priority
   journey (onboarding P1, POS checkout P2, B2B invoice loop P3/P5, month-end
   GSTR P5/P6). Each run emits `qos/observations/<journey>.<persona>.json` with
   step count, wall-clock, backtracks, dead-ends, modal interruptions,
   errors-shown, abandonment point, and a pass/fail against a budget.
2. **Budgets** from the validation hypotheses (H-02 <= 35 s no-mouse; onboarding
   <= 3 steps; H-03 zero dup/loss).
3. **Auto-promotion** (`qos/tools/promote.py`): an open `hypothesis` item whose
   journey an agent run shows `BUDGET_EXCEEDED` is promoted to
   `simulated (n=k)`, lifting the priority cap. A journey observed within budget
   across >= 5 runs moves the item to `accepted_wontfix`.
4. **Pilot telemetry** (parallel, higher grade): an event schema
   (`qos/telemetry/EVENTS.md`) feeding `measured` evidence during pilot stages.

**Cost:** ~10-15 person-days for the 4 agents + promotion + telemetry schema.
**Benefit:** categories 2/3/9 become regression-guarded; Q-OS delivers the signal
no test report does.

### Option B — defer

Keep categories 2/3/9 as `hypothesis`, do not let them drive fix priority, and
revisit after pilot Stage 1 produces the first real telemetry.

**Cost:** the backlog under-serves the "satisfying / delightful" half of the
promise until Stage 1.
**Benefit:** zero build cost now; Stage 1 telemetry may make bespoke agents
redundant for some journeys.

## Decision

**Deferred (Option B) for now.** Rationale: the frozen pilot's lead archetype
(ARCH-03, desktop, low operational friction) makes the correctness / reliability
/ compliance categories the near-term risk, and pilot Stage 1 (ARCH-01 POS) will
produce real usage telemetry within weeks — cheaper and higher-grade than
synthetic agents for the POS journey specifically. Revisit this ADR at the
**start of pilot Stage 1**: if Stage 1 telemetry cannot be stood up in time, or
if Stage 2 (ARCH-03) needs friction evidence before its fieldwork, build Option A
for the onboarding + B2B-loop journeys at that point.

Until then: `qos-lint` keeps categories 2/3/9 capped at `P1-investigate`, and
each such item names the agent or telemetry query that would confirm it.

Superseded-by: _none yet_

## Consequences

- `qos/agents/`, `qos/observations/`, `qos/telemetry/`, `qos/tools/promote.py` are
  **not built** in this cycle.
- The dashboard's zero-evidence indicator will stay high (~14/30 journeys) — that
  is the correct signal, not a defect.
- Phase 4 fixes draw from categories 1 and 4-8; categories 2/3/9 contribute
  investigation tasks only.
