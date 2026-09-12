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
| [`TESTING_STRATEGY.md`](TESTING_STRATEGY.md) | Persona-centric testing method: the 7-layer confidence model, per-journey question set, quality-dimension coverage map, ranked gap register, weak assumptions, regression discipline, evidence/sign-off model | **Active** — authority for method, priorities, gaps (line-item status stays in `FREEZE_SCOPE_COVERAGE.md`) |
| [`Q-OS_QUALITY_PIPELINE_PLAN.md`](Q-OS_QUALITY_PIPELINE_PLAN.md) | Design + phased plan for the Q-OS pipeline that turns testing evidence into an actionable Product Quality Backlog (10 categories, calibrated scoring, evidence-strength cap, lifecycle enforcement, sequenced frontier, observation layer) | **Plan — for build** · reference implementation is Bizboard; generated output is `PRODUCT_QUALITY_BACKLOG.md` |
| [`Q-OS_IMPLEMENTATION_RUNBOOK.md`](Q-OS_IMPLEMENTATION_RUNBOOK.md) | Executable task-by-task build plan for the above — Phases 0–5, each task with goal / steps / files / acceptance check / deps / effort; appendices carry the JSON Schema, lint checks, CI jobs, frontier scoring, and a sample item | **Runbook** — Phase 0 + Phase 1 built; Phase 2 partial |
| [`PRODUCT_QUALITY_BACKLOG.md`](PRODUCT_QUALITY_BACKLOG.md) | **GENERATED** by `qos/tools/build_backlog.py` — the ranked backlog itself: dashboard, sequenced top-12 frontier, 10 categories, Accepted/won't-fix. Edit `qos/backlog/*.yaml`, not this file | **Live** — gated by the `qos-lint` CI job; see [`../qos/README.md`](../qos/README.md) |
| [`archive/`](archive/) | Superseded historical reports kept for reference (security/test/bug/perf snapshots, old code-review dumps, UX audits, old Phase 1 plan) | **Frozen** — do not update |

### Notes

- **`reviews/`** mixes the current issue register (`MASTER_ISSUE_REGISTER.md`,
  `CHANGELOG.md`, `KNOWN_LIMITATIONS_AND_TECH_DEBT.md`) with point-in-time wave
  audits and reusable master prompts. Live remediation currently also tracked in
  the repo-root `DEEP_CODE_REVIEW_2026-09-03.md` / `FIX_PLAN_2026-09-03.md`.
  Consolidating these into one register is planned but not yet done.
- **`archive/`** contents are frozen snapshots. Each points at its live
  replacement in its header; don't cite them as current.
- The repo root holds only `README.md`, `MVP_IMPLEMENTATION_PLAN.md`,
  `REPOSITORY_AUDIT.md`, and the current `DEEP_CODE_REVIEW` / `FIX_PLAN`.
