# Recurring Invoices Module: Implementation Plan (rev 2)

**Document:** `RECURRING_INVOICES_IMPLEMENTATION_PLAN.md`
**Status:** 🟢 **IMPLEMENTED 2026-10-15** (all phases; see §10)
**Target:** `backend/sales/recurring.py`, `backend/sales/models.py`, `backend/sales/serializers.py`, `backend/sales/views.py` (`RecurringInvoiceScheduleViewSet`), `web/src/pages/sales/RecurringInvoicesPage.tsx`
**Tracking:** BB-000669, B2-009, B2-026, CR-015, CR-121

> **Rev 2 changes:** every claim below was checked against the code on 2026-10-14. Corrections to rev 1 are listed in §9. The frontend page itself was **not** re-read for this revision; Phase 3/4 items must be validated against it before work starts.

---

## 0. Pre-flight

- `backend/sales/models.py`, `views.py`, `services.py`, `serializers.py` already carry **uncommitted changes from other work** (Returns, Routes, etc.). Land or isolate those first, or work on a separate branch, to avoid tangled diffs.
- Every phase that changes the API must regenerate `docs/openapi-snapshot.json` and `web/src/api/openapi-types.ts` (CI drift check), run `makemigrations`, and update `docs/FREEZE_SCOPE_COVERAGE.md`.
- Existing tests: `backend/tests/test_sprint_c_recurring.py` and `backend/tests/test_sprint_c_recurring_tds.py` — extend both as needed; the TDS file must stay green.

---

## 1. Executive Summary (corrected)

Core monthly anchoring (`anchor_day`) is sound. Verified problems:

1. **Misreported failure on `auto_complete` (P1).** [recurring.py:308](backend/sales/recurring.py:308) raises `AssertionError` when the invoice is `COMPLETED`. This is **not** a stuck scheduler: `generate_draft_for_schedule` is `@transaction.atomic` and has already committed the invoice, the run and the `next_run_at` advance. The real effects: a false `last_error` is written on a successful run, the owner email is skipped, the `created` count is wrong, and the catch-up loop stops after one tick.
2. **Permission mismatch (P0/UX).** UI offers "Run now" to `CanCreateSales`; backend enforces `IsOwner()` ([views.py:2356](backend/sales/views.py:2356)) → 403 for non-owners.
3. **Silent auto-complete failure (P1).** A failed `complete()` is swallowed and only logged ([recurring.py:184-191](backend/sales/recurring.py:184)); the user never learns why an invoice stayed DRAFT. Locked periods also stall a schedule with no visible reason.
4. **Truncated pickers (P1)** — first 100 customers / 50 products *(UI, to verify)*.
5. **Missing lifecycle (P1)** — no edit, resume, history, `last_error` display; `last_error` is not in the serializer.
6. **Contradictory copy (P1)** — email says "BizBoard never auto-completes" even when `auto_complete` is on; module/function docstrings are stale ("draft-only", "Never completes").

---

## 2. Decision Register

| ID | Decision | Rationale |
|---|---|---|
| **D1** | In `_process_one_schedule`, accept `DRAFT` or `COMPLETED` when `auto_complete`; otherwise `DRAFT` only. Raise `BusinessRuleError` (not `AssertionError`) otherwise. | Removes false failure; keeps invariant. |
| **D2** | `run_now` permission → `CanCreateSales`. **Audit every manual run** via the viewset's existing `_audit("RUN_NOW", schedule)` (`core/viewsets.py` → `AuditService.log`). Do not branch on `request.user.role` (role lives on `CompanyUser`). | Matches UI; consistent audit. |
| **D3** | Async server-search Autocomplete for customer/product (Phase 3). | Removes caps. |
| **D4** | Edit / pause / resume first inside the **existing** page; drawer rebuild is a later, separate phase. | Smaller, safer increments. |
| **D5** | **Gated on product confirmation:** new cadences (`QUARTERLY`, `HALF_YEARLY`, `ANNUALLY`), `end_date`, `max_occurrences`. This is new scope, not bug-fix; ship last. | Avoid mixing features into bug-fix release. |
| **D6** | Auto-complete failure is stored **on the run**, not the schedule: add `RecurringInvoiceRun.completion_error` (TextField, blank). Schedule `last_error` continues to mean "generation failed". Emit the owner email/notification stating the invoice was left in DRAFT and why. | `last_error` is cleared on the next success ([recurring.py:300-302](backend/sales/recurring.py:300)), so it can't carry this. Inventory is not "silently bypassed" today — the gap is visibility. |
| **D7** | E-invoicing: show a UI warning only when `auto_complete` is on for an e-invoice-applicable company. **Out of scope:** automatic IRN push (separate feature; needs its own plan). Verify the real e-invoice status field before referencing it. | Rev 1 contradicted itself and used an unverified field. |
| **D8** | One copy set: "Draft by default. With Auto-complete on, invoices are finalized on creation (stock deducted, customer balance updated); if a check fails the invoice stays in Draft and you are notified." Apply to banner, confirm modal, email, and fix stale docstrings. | Single source of truth. |
| **D9** | Resume/reactivate must **not** replay history: on resume, if `next_run_at` is in the past, require the user to pick a new next run date (default: next future occurrence per cadence/anchor). | Otherwise catch-up creates up to `MAX_CATCHUP_TICKS`=12 back-dated invoices (all completed if `auto_complete`). |
| **D10** | Delete is blocked when runs exist (return 409 with message "Pause instead"). | `RecurringInvoiceRun.schedule` is `CASCADE`: deleting loses history and duplicate-guard records. |
| **D11** | "Run now" counts toward `max_occurrences` (documented), respects `end_date`, and refuses for non-ACTIVE customers. | Consistent with the beat; avoids bypass. |

---

## 3. Backend Specification

### 3.1 Phase 1 fixes (no schema change except D6)

**a) Replace the assertion** at [recurring.py:303-312](backend/sales/recurring.py:303):
```python
if run.invoice_id:
    inv = run.invoice
    allowed = {SalesInvoice.Status.DRAFT}
    if schedule.auto_complete:
        allowed.add(SalesInvoice.Status.COMPLETED)
    if inv.status not in allowed:
        raise BusinessRuleError(
            f"Recurring-generated invoice {inv.pk} has unexpected status {inv.status!r}."
        )
    doc_kind, doc_id = "invoice", inv.pk
```
Because the invoice is already committed when this raises, treat this branch as a true invariant violation only.

**b) Record completion failure (D6).** In `generate_draft_for_schedule`, in the `except Exception` at line 187, capture `str(exc)[:2000]` and pass it to `RecurringInvoiceRun.objects.create(..., completion_error=...)`. Migration: add nullable-safe `completion_error` TextField(blank=True, default="").

**c) Remove dead guards** `hasattr(schedule, "last_error")` (field exists) and update docstrings (module line 1, function docstring) to reflect optional auto-complete.

**d) Record lock reason.** When `period_is_locked` stops a schedule ([recurring.py:293-296](backend/sales/recurring.py:293)), set `last_error = "Accounting/GST period locked for <date>; will retry after unlock"` (without advancing `next_run_at`, per CR-015). Clear on next success (already handled).

**e) Email copy (D8).** Build body from the invoice status and `completion_error`:
- COMPLETED → "Invoice #… was automatically generated and completed from recurring schedule #… for <customer>."
- DRAFT with `completion_error` → "Draft … generated but could not be auto-completed: <error>. Review and complete it."
- DRAFT otherwise → "Draft … generated. Complete it when ready."
Subject: "Recurring document generated". Remove "never auto-completes".

**f) `run_now`** ([views.py:2353-2387](backend/sales/views.py:2353)):
- `get_permissions`: add `run_now` to the `CanCreateSales` group.
- Call `self._audit("RUN_NOW", schedule)`.
- Reject if `schedule.customer.status != "ACTIVE"` with a clear `BusinessRuleError`.
- Distinguish outcomes in the response: add `already_existed: bool` (when `generate_draft_for_schedule` returned a pre-existing run for the period key) instead of reporting a plain success; make the `None` error message specific (inactive / locked period).
- Document the known interaction: a manual run consumes the current period key, so a later scheduled run in the same period is skipped as duplicate (surface this in the confirm dialog).

**g) Serializer** ([serializers.py:1087](backend/sales/serializers.py:1087)): add read-only `last_error`; add `anchor_day` handling fix (see 3.2).

### 3.2 Phase 2: lifecycle (edit / pause / resume)

- **Fix `anchor_day` on edit.** `validate()` currently sets it only for non-partial writes. On any write that changes `next_run_at` (PUT *or* PATCH) recompute `anchor_day` from the new local date; on `cadence` change re-validate `next_run_at`.
- **Resume (D9):** when `is_active` goes `False → True` and `next_run_at <= now`, require `next_run_at` in the payload (validation error otherwise) — the UI pre-fills the next future occurrence.
- **Runs sub-resource** `GET /recurring-schedules/{id}/runs/` (permission: `CanViewSalesSurfaces`):
  - Serializer fields use `allow_null=True` on document-number sources (DRF drops dotted-source fields when the related object is null); verify real field names (`invoice_number`, order number, challan number) against the models before coding.
  - Add `completion_error`; derive `status` from the linked document, `"DELETED"` if all links are null (SET_NULL), not `"UNKNOWN"`.
  - Paginate (limit/offset) instead of a hard `[:50]`; use `select_related`.
- **Delete guard (D10)** in `perform_destroy`/`destroy`.

### 3.3 Phase 5 (gated, D5): cadences and contract limits

Only after product sign-off. Required together, not piecemeal:

1. `Cadence` += `QUARTERLY`, `HALF_YEARLY`, `ANNUALLY` (max_length 12 is sufficient). Migration.
2. `advance_next_run`: generalize with `month_step` (3/6/12). Rev 1's arithmetic is correct; keep the anchor-day clamp.
3. **`period_key_for` must change** (rev 1 missed this). Today every non-weekly cadence returns `YYYY-MM`, so a manual run in a different month from the scheduled one would produce a second invoice for the same quarter/half/year. New keys: `YYYY-Qn`, `YYYY-Hn`, `YYYY`. Add a unit test covering manual-vs-scheduled collisions. Existing monthly keys are unchanged.
4. Fields: `end_date` (Date, null), `max_occurrences` (PositiveInt, null), `total_runs_count` (PositiveInt, default 0).
5. **Enforce inside `generate_draft_for_schedule`** (under the existing `select_for_update`), not only the beat loop, so "Run now" respects it (D11):
   - if `end_date` and `on_date > end_date` → deactivate, return `None`;
   - if `max_occurrences` and `total_runs_count >= max_occurrences` → deactivate, return `None`;
   - **increment `total_runs_count` after the run row is created** (rev 1 never incremented it); reaching the limit deactivates the schedule.
6. Serializer + validation: `end_date >= next_run_at.date()`.

---

## 4. Frontend Specification (validate against current page first)

### Phase 3a — in-place improvements (small)
- Status chip (Active / Paused) and amber `last_error` indicator with tooltip on each row.
- Edit action (reuses existing create form in a dialog), Pause / Resume (resume prompts for new next-run date per D9).
- "Run now": enabled for users with create-sales permission; confirm dialog states the period-key consumption and that auto-complete will finalize the invoice if on.
- Success toast must handle **all stop stages**: link to the invoice, sales order or challan using the matching id from the response, via the SPA router (not a raw `<Link target="_blank">` to a hardcoded path). Wording depends on returned `status`: "Draft generated" vs "Invoice completed"; show `already_existed` case as informational, not success.
- All strings through `t()` (rev 1 snippets used hardcoded English).
- Delete: show the 409 message and offer "Pause instead".

### Phase 3b — scaling & transparency
- `AsyncCustomerAutocomplete` / `AsyncProductAutocomplete` (debounced server search; reuse any existing search endpoints/components in the repo before writing new ones).
- Run History view (drawer tab or modal) from the runs endpoint, with deep links and `completion_error` display.
- Expose header fields already supported by the model: `company_gstin`, `invoice_discount`, `invoice_discount_mode`, `additional_charges`, `price_mode`, `notes`.
- **Totals preview via a server endpoint** (as done for sales-returns preview-totals), not client-side GST math, to avoid duplicating tax logic. Reuse the existing invoice preview logic if present.
- Full drawer/tab redesign (rev 1 §4) only if 3a/3b prove insufficient.

---

## 5. Cross-Module Verification Matrix (corrected)

| Area | Current behaviour | Required |
|---|---|---|
| Inventory | `complete()` failure → invoice stays DRAFT, only logged | Store on run (`completion_error`), notify owner, show in history. Test: stock 0, qty 5, `auto_complete` → DRAFT + error recorded. |
| Blocked/archived customer | Beat already skips (`customer__status="ACTIVE"`); `run_now` does not | Make `run_now` refuse; UI badge optional. |
| Locked period | Beat stalls silently, no error | Write `last_error`; no advance; clears on success. |
| E-invoicing | Unknown field/flow | Verify actual status field; warning copy only (D7). |
| Delete | Cascades runs | Blocked when runs exist (D10). |
| Resume | Replays up to 12 periods | New next-run date required (D9). |

### 5b. Verified cross-module impact (code-checked 2026-10-14)

| # | Module | Finding (file) | Impact on this plan | Action |
|---|---|---|---|---|
| X1 | **Contracts** | `contracts/services.py:27-91` `create_contract_schedule` creates a MONTHLY, `auto_complete=False` schedule, calls `generate_draft_for_schedule(schedule, user=user)` and **raises if the invoice is not DRAFT**. `Contract.recurring_schedule` is `SET_NULL`. Contract has its own `start_date`/`end_date`/`status`. | (a) Edit/pause/delete of a contract-owned schedule from the Recurring page can silently desync the contract (delete → link nulled; edit → differs from `contract.value`). (b) Nothing pauses the schedule when a contract expires/cancels (`refresh_contract_statuses` never touches it), so it keeps billing. (c) `schedule.draft_invoice_id = ...` at line 90 is an unsaved ad-hoc attribute read in `contracts/views.py:76` — fragile; keep behaviour when `generate_draft_for_schedule` changes. (d) `advance_next_run` is imported here — keep its signature backward compatible. (e) D11/`end_date` overlaps contract `end_date`. | Mark contract-linked schedules read-only for cadence/template in the UI (show "Managed by Contract <n>" + link); block delete (D10 already blocks when runs exist; also block when `contracts` reverse relation exists). Add contract-expiry → deactivate schedule (or set `end_date` in Phase 5 from `contract.end_date`). Add tests in contracts suite. |
| X2 | **Customers** | `masters/views.py:582` archive deactivates the customer's active schedules; beat also filters `customer__status="ACTIVE"` (`recurring.py:242`). Test: `test_customers_master.py:632`. | Rev-2 D9 resume and "Resume" button would reactivate a schedule of an INACTIVE customer that then never runs (beat filter) with no explanation. | Resume must refuse (or warn) when customer is not ACTIVE; show "Customer inactive" badge; add test. |
| X3 | **Sales completion engine** (`SalesService.complete`, `sales/services.py:1008+`) | With `auto_complete`, runs the full gate stack under `user=None` (beat): `billing.quotas.assert_complete_allowed` (plan monthly-complete limit), credit limit + chronic/auto-hold dunning, GST guard / place-of-supply, below-cost block (only company owner may override, `user=None` never can), FEFO/negative-stock checks, FY-restart numbering warning, document number consumed, SALE stock movements, GL posting, PDF queue, `on_commit` hooks. | Each gate failure currently = silent DRAFT (swallowed). Auto-completes also **consume the tenant's monthly complete quota** and **document numbers**, and can leave numbering/FY warnings unacknowledged. Plan's D6 covers recording the error but not these specifics. | `completion_error` should store the structured code (e.g. `PLAN_QUOTA_EXCEEDED`, `CREDIT_LIMIT`, `BLOCKED_CUSTOMER`) so UI/email can give a precise reason; add one test per gate class (quota, credit, below-cost, stock, GST guard). Document that `user=None` completions are audited as system. |
| X4 | **Billing / plans** | `assert_complete_allowed` takes `select_for_update` on `Company` when a limit is active; the beat runs hourly across tenants. | Catch-up (up to 12 ticks) with auto_complete can exhaust a tenant's monthly quota in one run, blocking their manual billing for the month. | Cap auto-completes per run for quota-limited tenants or leave extras in DRAFT with `completion_error`; notify owner. |
| X5 | **Accounting / GST periods** | `period_is_locked` checks `GstReturnPeriod` (SOFT_CLOSED/CLOSED) and `AccountingPeriod`; shared with CR-015/`test_a10_period_centralization.py`. | Phase 1.3 (`last_error` on lock) and Phase 5 `period_key_for` change touch tests `test_a10_*` and `test_a13_a14_*` (`MAX_CATCHUP_TICKS`). | Update/extend those tests; keep `YYYY-MM` keys for MONTHLY/WEEKLY unchanged. |
| X6 | **Tenant backup/restore** (`accounts/tenant_backup.py:120,268,766,977`) | Schedules/runs are exported, wiped and restored via generic `_optional_rows`; counts compared at line ~1962. | New columns (`completion_error`, Phase 5 `end_date`, `max_occurrences`, `total_runs_count`) must round-trip; restore ordering (schedules before runs) must be kept. Phase 5 `total_runs_count` restored from backup must stay consistent with run rows. | Add a backup→restore round-trip test with new fields; verify generic row serializer handles them. |
| X7 | **Notifications** | Owner email sent per run via `NotificationService.send` (EMAIL only, first OWNER). | Burst catch-up/auto-complete = up to 12 emails per schedule per tick; failure emails (D6) add more. | Aggregate into one digest per schedule per tick; also create an in-app notification for failures. |
| X8 | **Celery beat** | `settings.py:640` runs `generate_recurring_invoices_task` at **minute 15 of every hour** (not daily); `contracts-refresh-status` runs 01:15 daily. | Plan assumed daily-ish beat; hourly runs mean a "Run now" and a scheduled run can race — only the `select_for_update` + unique `(schedule, period_key)` constraint protect it. | Add a concurrency test (Postgres-only, per existing suite convention) for run_now vs beat. |
| X9 | **Audit** | `CompanyScopedViewSet._audit_raw` → `AuditService.log`. | D2 audit uses this; beat-generated runs have `user=None`. | Log system-generated runs with action `RECURRING_RUN` so history is complete. |
| X10 | **Reporting / GSTR / AR** | Drafts don't post; completed recurring invoices flow into GSTR-1, receivables, dunning like any invoice. No special-casing found in reporting code (only tests reference recurring). | Auto-complete moves revenue/AR/GST liability without a human review. | Surface "Generated from recurring schedule #n" on the invoice (via `recurring_runs` reverse relation, `related_name="recurring_runs"`) in invoice detail/PDF-free list so accountants can trace; check GST-return tests unaffected. |
| X11 | **API clients** | Web uses `api/legacy/sales.ts` + generated `openapi-types.ts`; mobile has no references. | Only web needs updating; OpenAPI regeneration required. | As in §0. |

**Net effect on plan:** add X1/X2 guards to Phase 2 (lifecycle), structured `completion_error` + per-gate tests to Phase 1, quota/digest handling to Phase 1.4/1.5, backup round-trip and contracts tests to the test plan.

---

## 6. Test Plan

**Backend (pytest, extend `test_sprint_c_recurring.py`):**
- `auto_complete` success: no exception, no false `last_error`, email sent, count correct, catch-up continues.
- `auto_complete` gate failure: invoice DRAFT, `completion_error` stored, email says why, schedule `last_error` stays empty.
- Locked period sets `last_error`, no advance; unlock then success clears it.
- `run_now`: allowed for non-owner with create-sales permission; denied without; audit row written; refuses non-ACTIVE customer; `already_existed` flag; works for SALES_ORDER and DELIVERY_CHALLAN stages.
- PATCH `next_run_at` recomputes `anchor_day` (31st → Feb → Mar stays 31).
- Resume with past `next_run_at` and no new date → validation error; with date → no back-dated burst.
- Delete blocked with runs; allowed with none.
- Runs endpoint: pagination, null-document rows, tenant isolation (add to the tenancy matrix).
- Cross-module (§5b): contract-linked schedule cannot be deleted/edited into desync; contract expiry deactivates its schedule; resume refused for INACTIVE customer; tenant backup→restore round-trip with new fields; auto-complete gate matrix (plan quota, credit limit, below-cost, stock, GST guard) each leaving DRAFT + structured `completion_error`; `run_now` vs beat race (Postgres-only); existing `test_a10_period_centralization.py`, `test_a13_a14_reporting_sales.py`, `test_customers_master.py` stay green.
- Phase 5: quarterly/half-yearly/annual advance incl. month-end clamp; period keys; manual-vs-scheduled no double invoice; `end_date`/`max_occurrences` enforced on beat **and** `run_now`; counter increments once per run.

**Frontend (Vitest/RTL):** status chip + error tooltip; edit round-trip; resume date prompt; toast variants per stop stage and status; delete 409 message; autocomplete search (Phase 3b).

**E2E (Playwright):** create → run now → follow toast link; edit persists; pause/resume with date.

Run: `pytest backend/tests/test_sprint_c_recurring.py backend/tests/test_sprint_c_recurring_tds.py` plus tenancy suite; web `tsc -b`, lint (0-error gate) and the page test.

---

## 7. Execution Order

### Phase 1 — Correctness (backend, small)
- [ ] 1.1 Replace assertion (3.1a), remove dead guards/docstrings (3.1c)
- [ ] 1.2 `completion_error` field + migration + capture (3.1b)
- [ ] 1.3 Lock-reason `last_error` (3.1d)
- [ ] 1.4 Email copy (3.1e)
- [ ] 1.5 `run_now`: permission, audit, customer check, `already_existed` (3.1f)
- [ ] 1.6 Serializer `last_error`; regenerate OpenAPI snapshot + TS types; tests

### Phase 2 — Lifecycle (backend)
- [ ] 2.1 `anchor_day` recompute on edit
- [ ] 2.2 Resume rule (D9)
- [ ] 2.3 Delete guard (D10)
- [ ] 2.4 Runs endpoint + tests

### Phase 3 — UI
- [ ] 3a (in-place), then 3b (pickers, history, header fields, server totals preview)

### Phase 4 — Copy harmonization
- [ ] Banner, confirm modal and email aligned to D8 (email done in 1.4; do UI strings with 3a)

### Phase 5 — Gated scope (D5)
- [ ] Only after product confirmation: cadences + `period_key_for` + contract limits (3.3)

---

## 8. Definition of Done

1. Schedules with `auto_complete=True` run without errors, false `last_error`, or missing notifications.
2. Users with create-sales permission can "Run now"; every manual run is audited.
3. A failed auto-complete or locked period is visible to the user (history / row indicator / email).
4. Schedules can be edited, paused, resumed (without back-dated bursts), and deleted only when safe.
5. Customer/product pickers work for catalogs > 1,000 items.
6. OpenAPI snapshot/types regenerated; migrations applied; freeze-scope doc updated; lint/type-check gates green; all listed tests pass.

---

## 9. Corrections from Rev 1

| Rev 1 claim | Finding |
|---|---|
| Assertion "crashes beat and strands schedules" (P0) | Invoice/run/advance already committed; effect is false `last_error`, no email, miscount, loop stop. Downgraded to P1. |
| `request.user.role != "OWNER"`, `core.services.audit.record_audit_event` | Role is on `CompanyUser`; no such helper found. Use `self._audit(...)` from `CompanyScopedViewSet`. |
| D6 "silent inventory bypass"; write to `last_error` | Failure is swallowed but not bypassed; `last_error` is cleared on success → use `RecurringInvoiceRun.completion_error`. |
| New cadences only need date math | `period_key_for` also needs new keys; counters must be incremented; limits must be enforced in `generate_draft_for_schedule` so `run_now` obeys them. |
| Edit/PATCH "just works" | `anchor_day` only set on create/non-partial → stale on edit. |
| Reactivation is a simple toggle | Replays up to 12 back-dated periods → D9. |
| Delete from UI | Cascades run history → D10. |
| Toast links to `/sales/history/{invoice_id}` | `invoice_id` is null for order/challan stages; use router + correct id. |
| Matrix items "new" (customer suspended, locked period) | Beat already skips non-ACTIVE customers; locked period lacks `last_error`. |
| D7 warning + auto IRN push | Contradictory; IRN push out of scope. |
| "100% pass rate" DoD | Replaced with concrete gates. |
| Single large drawer phase | Split into 3a/3b. |

---

## 10. Implementation record (2026-10-15)

| Phase | Result | Where |
|---|---|---|
| 1 Correctness | Done | `backend/sales/recurring.py` (rewritten), `views.py` (`RecurringInvoiceScheduleViewSet`), migration `sales/0076` (`completion_error`, `is_manual`, `end_date`, `max_occurrences`, `total_runs_count`, cadences) |
| 2 Lifecycle | Done | serializer rules (anchor day, resume, contract lock), delete guard, `GET .../runs/` |
| 3 UI | Done | `web/src/pages/sales/RecurringInvoicesPage.tsx`, `pages/sales/recurring/*` (drawer, history, helpers) |
| 4 Copy | Done | one wording in banner, confirm, email, help page, FAQ (en + hi) |
| 5 Cadences and limits | Done | `period_key_for`, `advance_next_run`, term enforcement in `generate_for_schedule` |
| Cross-module (§5b) | Done | contracts pause on end (`contracts/services.py`, `tasks.py`, `views.py`); backup restore ids; digest notice; catch-up completes only the first period |

Decisions taken where the plan was open: "Run now" counts toward the maximum runs; a schedule switches itself off when the next occurrence would pass the end date; contract-owned schedules allow only pause, notes and auto-complete from the Recurring page; the Recurring list uses 200 rows per page.

Evidence: `backend/tests/test_recurring_lifecycle.py` (30), `test_recurring_concurrency_postgres.py` (2, run on Postgres 17), existing recurring/contract/customer/period/backup suites (304 passed), web page and helper tests (13 + helpers), full web suite and lint (0 errors), `e2e-golden/recurring-invoices-golden.spec.ts` (passed against a real backend). Coverage rows: `docs/FREEZE_SCOPE_COVERAGE.md` "Recurring invoices hardening".

Left to people: native-speaker review of the new Hindi strings.

### 10b. Follow-ups closed (2026-10-15)

Added after the first pass: invoice detail shows its recurring origin; a schedule paused by its contract ending is marked (`paused_reason`, migration `sales/0077`) and restarts when the contract is renewed or un-cancelled, while a person's own pause is never undone; the contracts job also pauses for companies with contracts switched off; a completed B2B invoice is handed to the e-invoice portal automatically when the company uses e-invoicing, with its state in the run history; the beat keeps a tenth of a plan's monthly completions free for manual billing; restore keeps run links to orders and challans; run-now links open the document itself; the product picker has its custom-field filter back; the list filters and pages on the server (50 per page); on phones the table becomes cards with an actions menu.

Verification: full backend suite 4306 passed, 57 skipped (one timing test, `test_i4_catalog_import_of_5000_skus`, failed while the machine was busy and passed alone in 12 s); recurring, contract and race tests also passed on Postgres 17 (55); full web suite 1966 passed (one invoice-screen test failed under load and passed alone, 37/37); lint 0 errors; typecheck clean; golden e2e passed in Chrome against a real backend; axe found no violations in the page or the edit panel at desktop width, and the page has no horizontal overflow at 390 px; OpenAPI snapshot is identical under test and dev settings.

Still outside the code: native-speaker review of the new Hindi strings; deploying migrations `0076` and `0077`; committing (nothing is committed).
