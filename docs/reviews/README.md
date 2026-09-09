# reviews/ — history, not scope

**As of the freeze (2026-09-08), everything in this directory is historical.**

These are point-in-time engineering audits, wave findings, fix plans, and
master prompts accumulated during open-ended development. They record how the
codebase got here. They are **not** the specification of what BizBoard does and
**not** a to-do list for the freeze.

## Where scope and quality now live

| Question | Authoritative source |
|---|---|
| What does BizBoard support / not support? | [`../FREEZE_SCOPE.md`](../FREEZE_SCOPE.md) |
| What must be green before freeze? | The Freeze Gate (Phase 0–3 of the quality plan) |
| What is protected, and by which test? | `backend/core/invariants/`, `backend/tests/workflows/`, `backend/tests/regression/` (Phase 2) |
| Architecture invariants | [`../architecture.md`](../architecture.md), [`ARCHITECTURAL_DECISIONS.md`](ARCHITECTURAL_DECISIONS.md) |
| Current limitations to state to a pilot user | [`../FREEZE_SCOPE.md`](../FREEZE_SCOPE.md) section C, [`KNOWN_LIMITATIONS_AND_TECH_DEBT.md`](KNOWN_LIMITATIONS_AND_TECH_DEBT.md) |
## Active Review Artifacts & Registers

- [`MASTER_ISSUE_REGISTER.md`](MASTER_ISSUE_REGISTER.md) / [`CHANGELOG.md`](CHANGELOG.md) —
  consult during the Phase 3 P0/P1 sweep, then each remaining P0/P1 is either
  fixed with a permanent test in `backend/tests/regression/` or reclassified in
  writing.
- [`BUGS_AND_GAPS_WITH_SCREENSHOTS.md`](BUGS_AND_GAPS_WITH_SCREENSHOTS.md) —
  Comprehensive Playwright E2E GUI bug and usability gap register with full screenshot evidence.
- [`UX_AUDIT_FINDINGS.md`](UX_AUDIT_FINDINGS.md) —
  Top 10 Fix-First usability and responsive mobile review report.
- [`KNOWN_LIMITATIONS_AND_TECH_DEBT.md`](KNOWN_LIMITATIONS_AND_TECH_DEBT.md) —
  folded into `FREEZE_SCOPE.md` section C during ratification.

Everything else here is read-only context. Do not drive new work from it.
