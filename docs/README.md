# Bizboard documentation

Entry point for everything under `docs/`. Start with the repo-root
[`README.md`](../README.md) for what Bizboard is, local setup, and the
architecture invariants.

## Core references

| Doc | What |
|---|---|
| [`architecture.md`](architecture.md) | How the system is built — layout, invariants, tenancy, feature flags, async, deployment |
| [`reviews/ARCHITECTURAL_DECISIONS.md`](reviews/ARCHITECTURAL_DECISIONS.md) | ADR-A01…A10 — the reasoning behind the invariants |
| [`../README.md`](../README.md) | Product scope, local dev (Docker + non-Docker), verification commands |
| [`../backend/README.md`](../backend/README.md) | Backend quick start, API surface, environment variables, Celery |
| [`openapi-snapshot.json`](openapi-snapshot.json) | Committed OpenAPI snapshot; drives `web/src/api/openapi-types.ts` |

### Setup / testing / deployment

These are covered in the two READMEs rather than duplicated here:

- **Setup** — [`../README.md` § Local development](../README.md#local-development) (Docker and non-Docker); backend detail in [`../backend/README.md`](../backend/README.md).
- **Testing** — [`../README.md` § Verification](../README.md#verification): `cd backend && pytest`; `cd web && npm run lint && npm test -- --run && npm run build`. Backend tests live in `backend/tests/` (`config.settings_test`, SQLite; the `postgres` marker gates row-lock tests). CI: `.github/workflows/ci.yml`.
- **Deployment** — [`architecture.md` § Deployment](architecture.md#deployment), [`reviews/12_DEVOPS_REVIEW.md`](reviews/12_DEVOPS_REVIEW.md), [`pilot/RUNBOOKS.md`](pilot/RUNBOOKS.md). CI gate scripts: `scripts/ci_gates/`.

## Directory map

| Dir | Purpose | Status |
|---|---|---|
| [`pilot/`](pilot/) | Pilot hardening (Phase 0): Definition of Done, Go/No-Go, runbooks, UAT, DPDP posture, env checklist, SLA | **Active** |
| [`phase1/`](phase1/) … [`phase7/`](phase7/) | Canonical per-phase implementation plans (document completeness → GST returns → payments → inventory → light accounting → AI → ecosystem) | **Active** — execute from these |
| [`roadmap/`](roadmap/) | Cross-phase plan maps and wave plans: `PHASE{1..7}_IMPLEMENTATION_PLAN.md` (plan-map pointers), `ONBOARDING_IMPLEMENTATION_PLAN.md`, `BILL_IMPORT_REDESIGN_PLAN.md`, `WAVES_*_CURSOR_IMPLEMENTATION_PLAN.md`, `FUTURE_ROADMAP_IMPLEMENTATION_PLAN.md`, `charters/`, `ticket-logs/` | **Active** |
| [`requirements/`](requirements/) | Feature requirement specs (item custom fields, stock/godown/expiry) | **Active** |
| [`help/`](help/) | In-app help system: codes, intents, event schema, triage, copy sign-off, contributing | **Active** |
| [`onboarding/`](onboarding/) | New-user product onboarding plan | **Active** |
| [`ca/`](ca/) | Chartered-accountant sign-off checklist (GST calc + invoice layouts) | **Active** |
| [`reviews/`](reviews/) | Engineering audit apparatus: numbered reviews `01`–`21`, `MASTER_ISSUE_REGISTER.md`, `CHANGELOG.md`, `REMEDIATION_ROADMAP.md`, `KNOWN_LIMITATIONS_AND_TECH_DEBT.md`, wave findings, audit master prompts | **History, not scope** — see [`reviews/README.md`](reviews/README.md) |
| [`FREEZE_SCOPE.md`](FREEZE_SCOPE.md) | Authoritative freeze scope: SUPPORTED / NOT SUPPORTED / KNOWN LIMITATIONS, frozen flag profile, founder decisions | **Active** — supersedes the README module table for scope |
| [`FREEZE_SCOPE_COVERAGE.md`](FREEZE_SCOPE_COVERAGE.md) | Every SUPPORTED / SUP item → the concrete test that gates it, or an explicit GAP / blocked line | **Active** — reconcile when chains land |
| [`TESTING_STRATEGY.md`](TESTING_STRATEGY.md) | Persona-centric testing **method**: layers **L1–L10**, per-journey question set, quality-dimension coverage map, ranked gap register, weak assumptions, regression discipline, evidence/sign-off | **Active** — authority for method, priorities, gaps (line-item status stays in `FREEZE_SCOPE_COVERAGE.md`). Philosophy lives in `HOLISTIC_VALIDATION_REVIEW.md` |
| [`HOLISTIC_VALIDATION_REVIEW.md`](HOLISTIC_VALIDATION_REVIEW.md) | **BizBoard Quality Model** + diagnostic: product-truth vs capability, Flow / Impact / Truth graphs, generated-catalog target, flow inventory, P0–P2 | **Active** — operating model (rev 2). Other testing docs are *views*, not competing frameworks |
| [`HOLISTIC_VALIDATION_IMPLEMENTATION_PLAN.md`](HOLISTIC_VALIDATION_IMPLEMENTATION_PLAN.md) | **Executable build plan** for the model above — Phases 0–7, each task with goal/steps/files/acceptance/deps/effort | **Phases 0–7 encoded** (2026-09-13). `flow-catalog` stays advisory until 2 green CI weeks (A3). Decision-quality target remains Medium-high (C6). |
| [`HOLISTIC_VALIDATION_80_PLAN.md`](HOLISTIC_VALIDATION_80_PLAN.md) | LLM-session plan to 80% on each review §0.9 dimension. Rubric + C6-80. Not High. | **Active** — scores live in that file’s table; Cursor canvases are IDE-only |
| [`CROSS_FLOW_IMPACT_MAP.md`](CROSS_FLOW_IMPACT_MAP.md) | **Graph 2 (Impact)** — writers/readers of shared mutable fields; event × projection summary is generated | **Active** — `python validation/tools/build_event_matrix.py` |
| [`FULL_SPECTRUM_PERSONA_VALIDATION_PLAN.md`](FULL_SPECTRUM_PERSONA_VALIDATION_PLAN.md) | **L4 view** — persona × archetype index. T1–T7 maps onto L1–L10 | **Active** — not a second pyramid |
| [`Q-OS_QUALITY_PIPELINE_PLAN.md`](Q-OS_QUALITY_PIPELINE_PLAN.md) | **Quality output** — pipeline that turns testing evidence into a Product Quality Backlog | **Plan — for build**. Does not define test layers |
| [`Q-OS_IMPLEMENTATION_RUNBOOK.md`](Q-OS_IMPLEMENTATION_RUNBOOK.md) | Executable task-by-task build plan for the above — Phases 0–5, each task with goal / steps / files / acceptance check / deps / effort; appendices carry the JSON Schema, lint checks, CI jobs, frontier scoring, and a sample item | **Runbook** — Phase 0 + Phase 1 built; Phase 2 partial |
| [`FLOW_CATALOG.md`](FLOW_CATALOG.md) | **GENERATED** Graph 1 — every `App.tsx` route + in-page money action with a coverage label | **Live** — `python validation/tools/build_flow_catalog.py`; advisory CI job `flow-catalog` |
| [`EVENT_MATRIX.md`](EVENT_MATRIX.md) | **GENERATED** Graph 2 — verb × document × projection cells | **Live** — `python validation/tools/build_event_matrix.py` |
| [`PRODUCT_QUALITY_BACKLOG.md`](PRODUCT_QUALITY_BACKLOG.md) | **GENERATED** by `qos/tools/build_backlog.py` — the ranked backlog itself: dashboard, sequenced top-12 frontier, 11 categories, Accepted/won't-fix. Edit `qos/backlog/*.yaml`, not this file | **Live** — gated by the `qos-lint` CI job; see [`../qos/README.md`](../qos/README.md) |
| [`archive/`](archive/) | Superseded historical reports kept for reference (security/test/bug/perf snapshots, old code-review dumps, UX audits, old Phase 1 plan) | **Frozen** — do not update |

### Notes

- **`reviews/`** is **history, not a live backlog.** [`MASTER_ISSUE_REGISTER.md`](reviews/MASTER_ISSUE_REGISTER.md) has three parallel ID schemes (CR-*, R-*, BB-*) that **must not be summed**. Open work was mined into Q-OS (`QOS-0053`…`0058`; see `qos/backlog/_SOURCE_MAP.md`). Drive new defects from `qos/backlog/`, not by adding the register’s Open counts.
- **`archive/`** contents are frozen snapshots. Each points at its live
  replacement in its header; don't cite them as current.
- The repo root holds only `README.md`, `MVP_IMPLEMENTATION_PLAN.md`,
  `REPOSITORY_AUDIT.md`, and the current `DEEP_CODE_REVIEW` / `FIX_PLAN`.
