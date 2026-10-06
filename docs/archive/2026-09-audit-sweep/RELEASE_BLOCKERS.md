# Release Blockers

**Date:** 28 September 2026  
**Decision:** **HOLD** — do not grant `ENABLE_INSURANCE`, `ENABLE_PROJECTS`, or `ENABLE_CONTRACTS` to a paying tenant, and do not set `POSTGRES_RLS_ENABLED=1`, until the P1 rows below are fixed and covered by the tests in `TEST_GAP_ANALYSIS.md`.

Production examples still have RLS off. Core sales, purchases, and accounting are not blocked by this pass **as they run today**. Recurring billing is blocked **only** for the RLS flip (DR-001). The growth modules are blocked regardless of RLS.

The 27 September sign-off in this file (“all P1s remediated, release unblocked”) is withdrawn.

## Blockers

| ID | Severity | Blocked capability | Why it blocks | Fix gate |
| --- | --- | --- | --- | --- |
| DR-001 | P1 | Enabling Postgres RLS; contract expiry; recurring drafts under RLS | Beat tasks scan tenant tables with an empty company GUC. Success returns zero rows. Documented incident response is “turn RLS on”, which would stop recurring drafts. | Per-company `set_rls_company` (same pattern as AR dunning). Postgres test with RLS on. |
| DR-002 | P1 | `ENABLE_INSURANCE` | Second option on the same set issues a second in-force policy. | Reject when the option set already has a live policy. Test the switch-and-issue sequence. |
| DR-003 | P1 | Insurance renewal diary | Check-then-insert on name and message prefix duplicates or suppresses renewal leads. | Unique link from the generated lead to the policy. Parallel-post test. |
| DR-004 | P1 | Insurance cover dates | `tenure_months * 30` shortens a 12-month policy by about five days. | Calendar-month (or explicit) end date. Anniversary test. |
| DR-005 | P1 | `ENABLE_PROJECTS` | Milestone sticks to a draft or cancelled invoice and can never be billed again. Close treats that as done. | Mark invoiced only after `COMPLETED`, or release the FK on cancel. Close refuses non-completed invoices. |
| DR-006 | P1 | Projects UI | Invoice click opens the first invoiced milestone, not the one just posted. | Navigate to the posted milestone’s `salesInvoice`. Component test with two milestones. |

## Ship-with-follow-ups (P2, not a hold on core ERP)

| ID | Notes |
| --- | --- |
| DR-007 | Resolved complaints can point at draft credit notes. |
| DR-008 | Referral rewards rounded to the rupee. |
| DR-009 | SLA looks breached during `WAITING`. |
| DR-010 | Bad ids and dates on project and policy actions return 500. |
| DR-011 | Unsigned Razorpay webhooks accepted whenever `DJANGO_ENV=test` and the secret is empty. The header check is dead code. |
| DR-012 | Negative or duplicate policy commission. |
| DR-013 | Shared milestone form state; no project close; insurance screen hides `end_date`. |
| DR-015 | Contract list trusts a status column the beat is supposed to maintain. Fold into the DR-001 fix. |

## Explicitly not blockers

- Cross-tenant reads on the new viewsets were not found. Isolation remains app-layer `company_id` while RLS is off, which matches `docs/FREEZE_SCOPE.md`.
- GST Guard owner/manager override on invoice and note completion.
- POD photo drain and the Celery document-id key list. Those earlier fixes are present. They do not cover DR-001, because these beats pass no document id.

## Exit criteria

1. DR-001 through DR-006 have code fixes and the tests listed in `TEST_GAP_ANALYSIS.md`.
2. A Postgres run with `POSTGRES_RLS_ENABLED=1` shows recurring draft creation and contract status movement.
3. Insurance and project persona tests include the negative cases, not only the happy path.
4. This file is updated from HOLD only after those runs, not after a static reread.
