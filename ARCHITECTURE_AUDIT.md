# Architecture Audit

**Date:** 28 September 2026  
**Question:** Do module boundaries and the background-job contract still hold for the new domains?

## Boundary that is sound

Request handlers for contracts, complaints, support, insurance, and projects sit on `CompanyScopedViewSet`. Tenant filters are not reimplemented per action. Cross-tenant vendor copies (`VendorTenantSnapshot`, `VendorTicketShare`) write under `rls_bypass()` and store `company_id` as the vendor company, so a normal company filter can read them back. That pattern matches billing ops.

Domain services own status machines (`complaints/services.py`, `support/tickets.py`, `insurance/services.py`, `projects/services.py`). Views are thin. That split is the right one.

The failure is not a circular import. It is two beat tasks that do not follow the cross-tenant job contract the rest of the worker code already uses.

---

### DR-001

| Field | Description |
| --- | --- |
| ID | DR-001 |
| Severity | P1 |
| Category | Architecture |
| Location | `backend/contracts/tasks.py` `refresh_contract_statuses` lines 10–26; `backend/sales/tasks.py` `generate_recurring_invoices_task` lines 274–279; `backend/sales/recurring.py` `process_due_schedules` lines 210–218; `backend/config/celery.py` `set_rls_company_for_task` lines 147–169 |
| Problem | Both scheduled tasks scan tenant tables and pass no `company_id`. Prerun sets `app.company_id` to empty. With Postgres RLS forced on, those scans match nothing. Contract rows stay at whatever status `save()` last wrote. Recurring schedules never generate drafts. The tasks return success (`changed == 0`, `created == 0`) so the failure is silent. |
| Root Cause | Cross-tenant beats in this repo are supposed to either loop `core.rls.iter_company_ids()` and `set_rls_company`, or open `rls_bypass()` for a sweep. Depreciation, AR dunning, expiry bands, and the refund outbox do that. These two call `Model.objects.filter(...)` on the worker connection as if RLS were off. Tests run on SQLite, where the GUC is a no-op (`core/rls.py` returns immediately unless `POSTGRES_RLS_ENABLED` and Postgres), so the suite stays green. |
| User Impact | The day RLS is enabled — `.env.staging.example` already says `1`, and `docs/ops/INCIDENT_RESPONSE.md` lists enabling it as a response step — AMC/warranty contracts never move to EXPIRING or EXPIRED, and subscription invoices stop being drafted. With RLS off (current production examples) the jobs still see every row. |
| Reproduction | Set `POSTGRES_RLS_ENABLED=1` on Postgres with the RLS migrations applied. Create an active contract whose `end_date` is yesterday, and an active recurring schedule with `next_run_at` in the past. Run `refresh_contract_statuses` and `generate_recurring_invoices_task` the way Beat does (no arguments). Contract status stays ACTIVE. No draft invoice appears. Repeat with the flag off and both jobs move rows. |
| Recommended Fix | Match `payments.dunning.run_dunning_all` / `inventory.tasks.record_expiry_bands_task`: iterate company ids, `set_rls_company(cid)` around each company’s rows, clear the GUC in `finally`. Do not wrap the whole sweep in `rls_bypass()` unless the body truly must see every tenant in one statement. Add a Postgres test that fails if either task returns zero while a due row exists. |
| Regression Risk | A per-company loop changes lock duration and beat runtime. Recurring generation must stay idempotent on `RecurringInvoiceRun.period_key` (it already is). Contract `QuerySet.update` skips `Model.save`; keep computing status in the task so CANCELLED rows are still excluded. |

---

### DR-015

| Field | Description |
| --- | --- |
| ID | DR-015 |
| Severity | P2 |
| Category | Architecture |
| Location | `backend/config/celery.py` `_DOC_ID_KEYS` lines 15–29; `backend/contracts/tasks.py` line 26 |
| Problem | Adding `job_card_id`, `policy_id`, `ticket_id`, and the other document keys to the prerun resolver does not cover argument-free sweeps. `Contract.objects.filter(pk=...).update(...)` also skips `Contract.save`, which is the only other place status is derived. List and report endpoints read the stored column (`ContractSerializer` does not recompute). |
| Root Cause | The RLS fix for tasks was keyed off “the task was given a document id”, which is the shape of user-triggered jobs, not Beat sweeps. Status was then stored instead of derived on read, so a missed sweep is user-visible. |
| User Impact | Even with RLS off, status is stale from midnight until the 01:15 IST beat (`CELERY_BEAT_SCHEDULE["contracts-refresh-status"]`). With RLS on, it is stale forever. Renewal reports and `?status=ACTIVE` filters include contracts that have already ended. |
| Reproduction | Create a contract with `end_date` yesterday. Do not run the beat. `GET /api/v1/contracts/?status=ACTIVE` still returns it. `GET` does not recompute. |
| Recommended Fix | Recompute in `to_representation` (or a queryset annotation) from `end_date` and `renewal_reminder_days`, and keep the beat only as a denormalised cache. If the column stays authoritative, the beat must be RLS-safe (DR-001) and a read path should not trust a stale cache for filtering. |
| Regression Risk | Deriving status on read changes cancelled-vs-expired if the derive function does not preserve CANCELLED. `compute_contract_status` does not know about CANCELLED; the caller must. |

## Layering note (not re-scored)

`core` still imports downstream models from sequence and invariant helpers. That coupling is real and already tracked. It did not produce a defect in this pass. Extracting `core` into a library would need a registry; it is not a release blocker beside DR-001.

## Dependency direction that is fine

`insurance.services` imports `crm.models.Lead` and `support.tickets.create_ticket`. Insurance is a caller of CRM and support, not the reverse, on the issue/claim path. `billing.ops.suspend_for_churn` imports `crm.models.Campaign` to drop a win-back draft into the vendor company under `rls_bypass`. That is an intentional vendor-side effect, gated on `VENDOR_COMPANY_ID`.
