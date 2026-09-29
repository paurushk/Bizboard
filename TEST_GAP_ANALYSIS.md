# Test Gap Analysis

**Date:** 28 September 2026  
**How this was judged:** Existing tests named in the tree were located, not executed in this session. SQLite is the default test database. `core/rls.py` no-ops unless Postgres and `POSTGRES_RLS_ENABLED`. A green `refresh_contract_statuses` test on SQLite does not prove the beat works in production with RLS on.

## Gaps that match open defects

| ID | Missing test | Proposed case |
| --- | --- | --- |
| DR-001 | No Postgres test that an argument-free beat sees tenant rows when RLS is forced on. `backend/tests/test_growth_os.py` calls `refresh_contract_statuses()` directly and expects `>= 1`. That passes on SQLite. | On Postgres with `POSTGRES_RLS_ENABLED=1` and the RLS migrations: seed a contract with `end_date` yesterday and a due `RecurringInvoiceSchedule`. Invoke both tasks with no kwargs, the way Beat does. Assert the contract is `EXPIRED` or `EXPIRING` and a draft invoice exists. Assert the worker GUC is cleared afterwards. |
| DR-002 | Persona coverage issues one policy per option set. | Choose option A, issue, choose option B, issue. Expect 400 and exactly one `IN_FORCE` policy. |
| DR-003 | Diary tests likely use one customer. | Two parallel diary posts for one in-window policy: one lead. Rename the customer, post again: still one lead. |
| DR-004 | Tenure is not asserted against a calendar anniversary. | `tenure_months=12`, start `2026-01-01`, expect `2027-01-01` (or the product’s documented anniversary rule). Also `2024-01-31` plus one month must not land on an invalid day. |
| DR-005 | Tests that the invoice FK is set, not that the invoice is `COMPLETED` or that cancel releases it. | Invoice a milestone, assert invoice status. Cancel the draft, invoice again, assert a new completed document or a 400 that leaves the milestone `READY`. `close_project` with a draft invoice returns 400. |
| DR-006 | `ProjectsPage.test.tsx` only checks the disabled-module copy and an empty create button. | Render two milestones, one with `salesInvoice: 1`, click Invoice on the other, assert `navigate` received `/sales/invoices/2`. |
| DR-007 | Complaint document tests should assert note status. | `create-credit-note` leaves a DRAFT. Transition to `RESOLVED` is rejected until the note is completed. |
| DR-008 | Reward amount compared to a whole number. | 2.5% of `1000.40` equals `25.01`, not `25`. |
| DR-009 | SLA tests that only check the due timestamp at create. | Move to `WAITING`, set the clock past `sla_due_at`, assert the ticket is not breached. Reopen from `CLOSED`, assert a fresh due time. |
| DR-010 | No 400 contract for garbage sequence, unknown milestone, or bad `start_date`. | Each returns 400 with a field error, not 500. |
| DR-011 | Unsigned webhook tests that only cover “secret set, bad signature”. | `DJANGO_ENV=test`, secret empty, no test header: 403. |
| DR-012 | Commission happy path only. | Negative amount 400. Second post with the same idempotency key does not insert a second row. |
| DR-013 | No UI test for per-project milestone fields. | Two projects, type in one, the other card’s inputs stay empty. |

## Areas with tests that do not lock these bugs

- `backend/tests/test_growth_os.py` and `backend/tests/personas/test_pj_contracts_and_field_service.py` exercise contract refresh **without** RLS.
- `backend/tests/personas/test_pj_insurance_desk.py`, `test_pj_project_milestones.py` cover the happy path that made DR-002 and DR-005 look done.
- `backend/tests/test_gst_guard_v2.py` and persona trader tests cover GST Guard override permissions. This pass did not find a bypass there.
- Idempotency tests know `MONEY_IDEMPOTENCY_SCOPES` for sales documents. They do not include `project_milestone_invoice` or `insurance_policy_create`.

## Not required for this hold

Property-based tests for GST rounding and fuzz tests for webhook bodies would be valuable and are not the reason for the hold. The cases in the table are ordinary unit and API tests. They are enough to stop these regressions.

Concurrency tests worth adding with the fixes, not as a separate program: two diary posts, two `choose_option` calls on one set (expect one winner and no 500 leak of a half-updated set), two milestone invoice posts (one draft).
