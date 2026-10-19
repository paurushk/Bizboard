# Customer care + Jobs & contracts — plan to reach 10/10 on every dimension

Source: the review of Complaints, Supplier complaints, Support tickets, Shared tickets, Job cards, Projects and Contracts (2026-10-18). Every work package (WP) below traces to a finding in that review. Findings marked **[V]** are *needs verification*: WP-00 proves or disproves them before any code is written.

Conventions: backend in `backend/<app>/`, web in `web/src/pages/...`. IDs: `CCJ-xx` setup/shared, `CMP` complaints, `SCM` supplier complaints, `TKT` tickets, `SHR` shared tickets, `JOB` job cards, `PRJ` projects, `CON` contracts, `XLK` cross-links, `QA` quality gates. Effort: S ≤ 0.5 d, M ≈ 1–2 d, L ≈ 3–5 d.

### Revision 2 (2026-10-18) — changes after plan review

Each review comment was checked against the code. Accepted, rejected and adjusted items:

- **Accepted, verified in code:** `ContractViewSet.get_permissions` skips `SubscriptionWritesAllowed` (CCJ-00e); the three `[V]` items are real bugs from reading the code, so they become regression tests inside the fix WPs instead of investigations; `cancel_job` blocks a job whose invoice is CANCELLED (JOB-11); `close_project` accepts an empty project (PRJ-02); no `ServiceBay` endpoint exists (JOB-12); audit is missing in workshop/projects services and ticket comments (FND-10); terminal-state attachment/comment mutations are unguarded (FND-14).
- **Accepted as design improvements:** list vs detail serializers (FND-03b); denormalised `expiring_from_date` instead of cross-DB `Case/When` (CON-07); SLA recompute that cannot be gamed (TKT-02); explicit RLS ownership for vendor replies (SHR-03); coverage query covers `Contract.product` *and* `covered_products` (XLK-02); billing cadence selector (CON-04); idempotency on complaint document actions (CMP-06); URL state in `MasterDetail` (FND-02); concurrency rules for POST actions (FND-12); print/PDF slips (JOB-14, CON-12); warehouse on job cards (JOB-13, decision D10); Sales-side lock for invoices linked to jobs/milestones (JOB-02, PRJ-06); FK migrations moved to Phase 1 (FND-13).
- **Rejected:** the claim that milestone invoices should pass `invoice_type=GST` explicitly. `SalesInvoice.invoice_type` already defaults to `GST` (`sales/models.py:55`), so there is no gap.
- **Clarified, not changed:** supplier complaints have exactly one document type (`PurchaseDebitNote`); SCM work packages say so explicitly and no new purchase-return link is added unless a decision (D12) asks for it.

---

## 0. What "10" means (the exit criteria per dimension)

A dimension scores 10 only when **every** listed criterion is true and tested. Scores are re-assessed per screen at the end (section 9).

| Dimension | 10 means | Delivered by |
|---|---|---|
| Purpose clarity | Page title + one-line subtitle states the job; customer, status, owner and next action visible without opening anything; no control belongs to another screen | FND-02, FND-03, per-module list/detail rebuilds |
| UX | Master–detail with deep-linkable detail route; tables not stacked text; every action gives visible success/failure beside the control; consistent dialogs | FND-02/05/06 + module rebuilds |
| Cognitive load | No typed database IDs; pickers search by number/name; smart defaults (assignee, price, dates); ≤ 1 primary action per state; progressive disclosure for rare fields | FND-04, JOB-05, CON-02, TKT-03 |
| Flow | No dead end: every state has a forward or recovery path; every entity links to its neighbours; back/cancel/refresh safe | PRJ-01/02, CMP-05, CON-03, XLK-* |
| Functionality | Create, view, edit (where legal), search, filter, paginate, export, attach, audit on every screen; backend capabilities all reachable | module WPs |
| Business logic | Rules in service layer, one source of truth shared by UI; decisions D1–D9 closed and encoded in tests | section 7 + per-module rules |
| Data/state handling | Locked transitions, optimistic-concurrency on edits, no silent divergence (invoice vs job, schedule vs contract, share vs ticket), idempotent actions | JOB-02, CON-01/02, TKT-07, SHR-02 |
| Error handling | Every failure shows what, why, how to fix; no silent drops; empty/loading/error states on every query; inline field errors | FND-05, JOB-06, QA-03 |
| Cross-product integration | Ticket↔invoice↔contract↔job↔complaint↔project linkable both ways; warranty lookup; search, reports, notifications cover all seven | XLK-*, FND-11 |
| Consistency | One layout, one status chip, one confirm dialog, one money/date formatter, one i18n pass (EN + HI) | FND-02/06/08 |
| Accessibility | axe clean; keyboard-operable board and tables; labelled controls; 44 px targets; mobile card layout; contrast AA | FND-09, QA-04 |

---

## 1. Delivery phases and order

```
Phase 0  Fix confirmed bugs, each with a regression test  ~4 d
Phase 1  Shared foundation + all schema migrations      ~10 d  ← unblocks everything
         (search, layout, pickers, audit, FK columns FND-13)
Phase 2  Module rebuilds (can run in parallel by module)
           Job cards   ~12 d   (largest gap)
           Contracts   ~9 d
           Tickets+Shared ~9 d
           Complaints+Supplier ~8 d
           Projects    ~6 d
Phase 3  Cross-links + warranty + notifications          ~6 d
Phase 4  Quality gates, sign-offs, docs                   ~5 d
```

Parallelism: after Phase 1, modules touch disjoint files except the shared components and `i18n/en.ts` / `hi.ts` (merge-conflict hotspot — add keys in a per-module namespace block). Job cards and contracts share only the coverage API (XLK-02): build Contracts first or stub it.

Release strategy: no new feature flags (existing `ENABLE_*` stay). API changes are additive; renamed UI routes keep redirects from the old paths. Each phase ends green on: `ruff`, `tsc -b`, eslint (0-error gate), vitest, backend pytest (private-DB recipe from memory), and the Postgres concurrency subset.

---

## 2. Phase 0 — Fix confirmed bugs (test first, then fix)

Code reading confirmed the three bugs earlier marked "needs verification". Each now starts with a failing regression test that stays in the suite, then the fix.

| ID | Work | Files | Done when | Size |
|---|---|---|---|---|
| CCJ-00a **(confirmed)** | Failing test, then fix: deleting a contract leaves its `RecurringInvoiceSchedule` active (`pause_ended_contract_schedules` filters `contracts__isnull=False`, so an orphan is ignored). Fix is CON-01a below | `tests/test_contract_delete_schedule.py` | Test red before, green after | S |
| CCJ-00b **(confirmed)** | Failing test, then fix: convert job → add line → complete invoice; the new line is reserved but never billed, then released without a stock movement. Fix is JOB-02a below | `tests/test_jobcard_line_after_convert.py` | Invoice lines == job lines; stock moves match | S |
| CCJ-00c **(confirmed)** | Failing test, then fix: complaint whose linked return is CANCELLED can neither resolve nor link a new return (`_assert_posted` + `existing: True`). Fix is CMP-05 (pulled into Phase 0 as a minimal `unlink-document`) | `tests/test_complaint_cancelled_doc.py` | Recoverable path exists | S |
| CCJ-00d | Check payroll/GL consumers of `labour_commission_amount` (grep + test) — still a real investigation | `workshop/services.py`, `payroll/` | Decision D5 can be made | S |
| CCJ-00e | **Subscription write-lock bypass**: `ContractViewSet.get_permissions` returns hard-coded lists and never appends `SubscriptionWritesAllowed()`. Change to `[*super().get_permissions()]` plus `IsOwner()` for `create_schedule` (and audit the other seven viewsets for the same override) | `contracts/views.py` | Expired-subscription company gets 402/403 on contract writes; test per viewset | S |
| JOB-11a | `cancel_job` must allow cancelling a job whose linked invoice is CANCELLED (unlink first, as `convert_to_invoice` already does) | `workshop/services.py` | Test: invoice cancelled → job cancellable, reservations released | S |
| JOB-01 | Allow `unit_price >= 0` in `JobCardLineSerializer.validate_unit_price` (warranty/goodwill lines) | `workshop/serializers.py` | Zero-price part + labour accepted; negative rejected | S |
| JOB-02a | Block `add_line` when `job.sales_invoice_id` is set (interim; full fix in JOB-02) | `workshop/services.py` | Clear message "Invoice draft exists — revert to editing first" | S |
| CMP-01 | `DOC_OK` = `{'APPROVED'}` in UI to match backend; disabled-button tooltip explains why | `ComplaintsPage.tsx`, `SupplierComplaintsPage.tsx` | No server error possible from button state | S |
| CON-01a | Interim: `ContractViewSet.destroy` refuses when schedule/service events exist; otherwise pauses schedule | `contracts/views.py` | Test from CCJ-00a passes | S |
| TKT-01a | `slaChipModel`: RESOLVED/CLOSED → `met`/`breached-at-resolve`, never a live countdown | `cognitive/loadHelpers.ts` | Unit tests for 6 status×time combos | S |

---

## 3. Phase 1 — Shared foundation

| ID | Work | Detail | Size |
|---|---|---|---|
| FND-01 | **Server-side search**: `SearchableMixin` on `CompanyScopedViewSet` (`search_fields`, `q`, `search` alias, 100-char cap, `icontains`, number prefix fast path). Apply to Complaint (number, customer name, description), SupplierComplaint, Ticket (number, subject, customer), Contract (number, customer, notes, product), JobCard (number, registration_no, customer, vehicle_model), Project (number, name, customer) | Tests per viewset incl. cross-company isolation. Fixes dead search boxes | M |
| FND-02 | **Master–detail layout**: `<MasterDetail>` component; detail on its own route (`/complaints/:id`, `/support/tickets/:id`, `/workshop/jobs/:id`, `/projects/:id`, `/contracts/:id`, `/support/shared/:id`); desktop = list left + detail right, mobile = separate screens; `?status=&q=&page=` in URL. **Acceptance:** opening a row, switching rows, and Back all preserve the list's query string (`?status=OPEN&q=pump&page=2`) | Retire "detail pasted under the list" | L |
| FND-03 | **Names on rows**: serializers add `customer_name`, `assignee_name`, `invoice_number`, `product_name`; `select_related` in `get_queryset`; `<CustomerLink>` component | N+1 test (query-count assertion) | M |
| FND-03b | **List vs detail serializers**: `JobCardListSerializer` (no `serial_history`, no nested lines; line count + total) and `ProjectListSerializer` (milestone count, invoiced/remaining totals instead of the full milestone array); detail serializers unchanged. Same for tickets/contracts if their lists embed children | Query-count test on a 50-row list (`serial_history` currently runs per row) | M |
| FND-04 | **Pickers**: `TicketPicker`, `JobCardPicker`, `SalesInvoicePicker`, `ContractPicker`, `ServiceBayPicker`, `TechnicianPicker` — async search by number/name, scoped to customer when given. Remove every "type the ID" field | M |
| FND-05 | **Action feedback**: `useActionFeedback()` → snackbar for success, inline `role="alert"` next to the action for failure, field-level errors mapped from DRF `{field: [..]}`; remove page-top shared `error` state | M |
| FND-06 | **Presentation primitives**: `<StatusChip>` (enumLabel + colour + icon, not colour alone), `formatMoney`, `formatDate` (timezone-safe — parse `YYYY-MM-DD` as local date, fixing the `new Date()` day-shift), `formatDateTime`, `<MoneyText>`; replace `String(status)` / raw amounts | S |
| FND-07 | **Standard dialogs**: replace every `window.confirm` with `ConfirmDialog`; destructive/terminal actions (reject, cancel project, cancel contract, resolve, delete) use it, with typed confirmation only for money-bearing cancels | S |
| FND-08 | **i18n**: new namespaces `care.*`, `jobs.*`, `projects.*`, `contracts.*`; EN + HI complete; remove raw enum leaks (`row.priority`); Hindi review via QOS item | M |
| FND-09 | **Accessibility base**: kanban cards become `<a>`/`<button>`; `aria-live` regions for status moves; focus moves to detail on open and returns on close; table `scope` headers; 44 px targets; responsive card layout < 600 px | M |
| FND-10 | **Audit timeline**: backend `GET /api/audit/?entity=Ticket&id=` (company-scoped, paginated) + `<ActivityTimeline>`; used on all detail pages. **First close the audit gaps, or the timelines are empty:** add `AuditService.log` to `workshop/services.py` (`create_job`, `add_line`, `start_job`, `schedule_job`, `cancel_job`, `convert_to_invoice`) and `projects/services.py` (`create_project`, `add_milestone`, `update/delete_milestone`, `mark_ready`, `invoice_milestone`, `close_project`); audit ticket comments and attachments; route `share_ticket` through `AuditService.log` (it writes `AuditEvent` directly) and add the missing audit on `revoke_share`; audit complaint document links and contract service events | Test per action: one audit row with entity type/id and actor | L |
| FND-11 | **Global search & nav**: extend `search/views.py` to job cards, projects, supplier complaints, shared tickets (vendor only); results link to detail routes; `menu.ts` hides *Shared tickets* unless company is the vendor (expose `is_vendor_company` on `/me` or features payload) | M |
| FND-12 | **Concurrency rules, two kinds.** (a) Field edits via `PATCH` (tickets, complaints, contracts, projects, jobs): `updated_at` precondition (`If-Unmodified-Since` or `version`) → 409 "changed by X — reload". (b) State changes via custom `POST` actions (`transition`, `ready`, `invoice`, `schedule`, `lines`, `create-return` …): no timestamp; they rely on `select_for_update` plus a server-side status precondition, return 409 with the current status, and the UI refetches. Every POST action must lock its row (tickets' `transition_status` does not yet) | M |
| FND-13 | **All schema migrations up front** (moved from XLK-01): nullable FKs `Ticket.{source_invoice, contract, job_card, complaint}`, `JobCard.{contract, ticket, source_complaint, warehouse}`, `Complaint.ticket`, `Project.contract`; plus the other new columns/tables in section 8. Expand-only, with RLS policies for new tables. Done once so each module is touched a single time | Migrations apply forward on SQLite + Postgres; model/serializer fields exposed read-only until their WP lands | M |
| FND-14 | **Terminal-state locks**: block comment, attachment upload **and delete** on CLOSED tickets, RESOLVED/REJECTED complaints and supplier complaints, and CANCELLED/EXPIRED contracts (renew/uncancel first). One helper `assert_mutable(entity)` used by all four attachment actions and ticket comments | Tests: POST and DELETE refused with a clear message in each terminal state | S |

---

## 4. Phase 2 — Module work packages

### 4.1 Job cards (`backend/workshop`, `web/src/pages/workshop`)

| ID | Work | Acceptance |
|---|---|---|
| JOB-02 | **Lines locked after convert; explicit "Revert to editing"**: `POST /jobs/:id/reopen` — only when linked invoice is DRAFT: unlink + cancel the draft (via `SalesService`), job → IN_PROGRESS, audit. Re-convert rebuilds invoice. Never leave reservations without a billable line. **Interplay with Sales:** when `SalesService` cancels a draft it already calls `sync_job_card(completed=False)` (unlinks, status IN_PROGRESS); `reopen` must call the same path rather than unlink twice, and be a no-op if already unlinked. **Divergence guard:** a draft `SalesInvoice` linked to a job card (or project milestone) is read-only for line edits in the Sales UI/API (message: "Edit the job card, then re-create the draft") — otherwise the job and invoice drift apart | Test: convert→reopen→add line→convert→complete: invoice lines == job lines; stock moves == part lines; reservations 0; editing a linked draft in Sales is refused |
| JOB-03 | **Edit/remove lines** (`PATCH/DELETE /jobs/:id/lines/:line_id`) with reservation delta (release old, reserve new) in one transaction; allowed only DRAFT/IN_PROGRESS without invoice | Reservation balance tests; concurrent edit test |
| JOB-04 | **Edit job header** (technician, complaint text, vehicle fields, odometer, customer only while no lines) `PATCH /jobs/:id` | Status-guarded; audit event |
| JOB-05 | **UI rebuild**: list table (number, customer, vehicle/reg no, technician, bay, status chip, total, age) + filters (status, technician, bay, date) + search + pagination; detail route with line table; **kind toggle PART/LABOUR**; product picker; **serial & batch pickers** (only in-stock, expiry shown); price default from product, editable, `0` allowed with "No charge" chip; GST + totals preview; primary action by state: DRAFT→Start, IN_PROGRESS→Create draft invoice, INVOICED→Open invoice; Schedule and Cancel (ConfirmDialog) | Golden e2e: create → add part (serial) + labour → convert → complete |
| JOB-06 | **Booking correctness**: inside the existing `@transaction.atomic` of `create_job`/`schedule_job`, `ServiceBay.objects.select_for_update().get(pk=…)` *before* the clash query (assert the function is only called in a transaction); technician overlap check (warn-with-override, lock the `CompanyUser` row too; the override flag is part of the idempotency key of `create`); reject unknown `service_bay`/`technician` ids with 400 instead of silently dropping (`_bay_for`, view create); bay day-board view (columns = bays, rows = time) | Postgres concurrency test: two simultaneous bookings → one 400 |
| JOB-07 | **Totals + labour**: `JobCard.subtotal/gst/total` computed in serializer; labour minutes shown; hours-vs-estimate field optional | Matches invoice total to the paisa |
| JOB-08 | **Commission** per decision D5: either (a) post accrual to payroll/commission ledger at invoice completion, or (b) hide the fields and remove `technician_commission_percent` from UI | Chosen path tested; no dangling field |
| JOB-09 | **Warranty/AMC coverage**: `JobCard.contract` FK (nullable); on create, UI shows active covering contracts (XLK-02); covered part/labour lines default to ₹0 with `covered_by_contract` flag; job report "free vs paid" | Test: expired contract not offered; covered line billed at 0 |
| JOB-10 | **Origin links**: `JobCard.ticket` and `.source_complaint` FKs; "Create job card" button on ticket/complaint pre-fills customer + description | XLK-01 |
| JOB-11 | Invoice cancel/complete regression tests for `sync_job_card` + `release_reservations_for_invoice` including returned and **cancelled** invoices (JOB-11a lets a job with a cancelled invoice be cancelled) | Added to `test_jobcard_*` |
| JOB-12 | **Service bay management** (nothing exists today): `ServiceBayViewSet` (`GET/POST/PATCH/DELETE /api/workshop/bays/`, company-scoped, unique name, delete blocked while future bookings exist, `is_active` flag so bays can be retired), "Manage bays" drawer on the job list, `ServiceBayPicker` fed from it | Bay can be created, renamed, deactivated; picker lists only active bays; test for delete with bookings |
| JOB-13 | **Warehouse consistency**: `add_line` and `_release_job_reservations` use `default_warehouse`; add optional `JobCard.warehouse` (defaults to the default warehouse) and use it for reservations *and* the draft invoice's stock source so reserve and deduct hit the same warehouse (decision D10) | Multi-warehouse test: reserve, convert, complete → one warehouse moves |
| JOB-14 | **Printable job card / estimate slip** (customer drop-off copy): PDF endpoint or `@media print` view with customer, vehicle, complaint, lines, totals, terms | Prints on A4; shows no internal commission data |

### 4.2 Contracts (`backend/contracts`, `web/src/pages/contracts`)

| ID | Work | Acceptance |
|---|---|---|
| CON-00 | `get_permissions` keeps `SubscriptionWritesAllowed` (CCJ-00e) — listed here so the contract acceptance suite covers it | |
| CON-01 | **Safe delete**: block delete when schedule, service events or invoices exist (message names them) → offer Cancel; if deletable, pause schedule. `pause_ended_contract_schedules` also catches schedules whose contract set is empty | CCJ-00a test green |
| CON-02 | **Edit UI + dialog** (type, dates, value, reminder days, products, notes) via existing PATCH; on value/product change with a schedule, show "Update the monthly billing line?" → `POST /contracts/:id/sync-schedule` updates `line_template` for future runs, audited | No silent schedule/contract divergence |
| CON-03 | **Renew**: `POST /contracts/:id/renew {new_end_date, value?, note}` extends in place, writes `ContractRenewal` row (previous_end, new_end, value, user, at), resumes schedule via `resume_renewed_contract_schedules`; works from EXPIRED/EXPIRING (not CANCELLED) | Renewal history on detail; schedule resumes without back-dated invoices |
| CON-04 | **Billing schedule UX**: rename "Renew invoice" → "Start billing" with a **cadence selector** (`RecurringInvoiceSchedule.Cadence` already supports WEEKLY/MONTHLY/QUARTERLY/HALF_YEARLY/ANNUALLY; default MONTHLY; `create_contract_schedule` takes it; CON-02 "update billing line" copy follows the chosen cadence); show schedule state (active / paused: contract ended / next run date / last invoice); pause/resume; owner-only controls hidden for others with explanatory text | No 403 reachable by a visible button |
| CON-05 | **Validation**: overlap/duplicate warning (same customer+product+type overlapping dates → 409 `overlap` that UI can confirm-override); value ≥ 0; reminder days 0–365; reject `status=CANCELLED` on create; `validate_status` compares against effective status | Serializer tests |
| CON-06 | **Service events**: accept `occurred_at`; ticket picker restricted to same customer (server check); required note; edit/delete by creator within 24 h; render local date-time | Test: other-customer ticket → 400 |
| CON-07 | **List**: table with customer, type, products, end date, *days to expiry*, value, status chip; status select (replaces free text); quick filters "Expiring ≤ 30 d"; search `q`; sort; server pagination. **Perf**: replace the Python-side `filter_by_effective_status` scan with a stored, indexed `Contract.expiring_from_date` (= `end_date − renewal_reminder_days`, set in `Contract.save()`, backfilled by migration), so ACTIVE/EXPIRING/EXPIRED are plain date comparisons that behave the same on SQLite and Postgres (no cross-DB date-plus-integer SQL); index `(company, end_date)` and `(company, expiring_from_date)` | Query-count + 10 k-row test under budget |
| CON-08 | **Report**: exclude cancelled by default, toggle; expiring-by-month; monthly recurring value; CSV export | Totals tie to list filters |
| CON-09 | **Reminders**: Celery task at `renewal_reminder_days` → in-app notification (+ WhatsApp when planned); de-duplicated per contract per cycle | Notification test; idempotent re-run |
| CON-10 | **Detail page**: customer link, covered products, value, schedule card, renewal history, service timeline, documents, linked tickets/jobs (XLK); label by type ("Warranty period" only for WARRANTY) | |
| CON-12 | **Printable contract / AMC certificate**: PDF or print view with customer, covered products, term, value, terms text | Prints on A4 |
| CON-11 | INSURANCE type: apply decision D8 (keep + link to Insurance module, or remove from picker) | |

### 4.3 Support tickets (`backend/support`, `web/src/pages/support`)

| ID | Work | Acceptance |
|---|---|---|
| TKT-01 | **SLA correctness (server)**: serializer exposes `sla_state` ∈ `running | paused | met | breached | breached_resolved` and `sla_remaining_seconds`; resolved tickets freeze at `resolved_at`; UI chip only renders server state | Tests across WAITING/RESOLVED/reopened |
| TKT-02 | **Priority change without SLA gaming**: track `Ticket.waiting_total_seconds` (accumulated on leaving WAITING). New due = `created_at + waiting_total + SLA_OFFSETS[new_priority]`, i.e. active time already spent still counts. Raising priority can therefore bring the due time forward (possibly already breached, which is honest); lowering never pushes it later than `created_at + waiting_total + new offset`. Changing priority while WAITING is applied on exit. Audited with old/new due | Test: HIGH→MEDIUM→HIGH leaves the deadline unchanged; 5-day-old ticket raised to URGENT shows breached, not reset |
| TKT-03 | **Create/edit**: description in create dialog; optional links (invoice, contract, job); detail edit for subject, description, priority, assignee; show customer, created, SLA, links | |
| TKT-04 | **Board & list**: list view default + board toggle; status filter; "hide closed older than 7 d"; per-column counts from server (`report` endpoint) not from the 20-row page; paging per view | Counts correct with > 20 tickets |
| TKT-05 | **Comments**: show author + time, multiline, reject empty (400), audited, refused on CLOSED tickets (FND-14); `is_internal` toggle kept but customer-visible channel deferred (D4) | |
| TKT-06 | **Delete rule**: only OPEN, no comments/attachments/links; otherwise "Close" guidance; ConfirmDialog; share rows removed | |
| TKT-07 | **Concurrency**: `select_for_update` in `transition_status`; FND-12 version check on edits | Postgres race test |
| TKT-08 | **Sharing state**: serializer returns `shared`, `shared_at`, `include_description`; UI toggles Share/Stop sharing; PII warning text; `stop-sharing` idempotent (200 even if not shared); edits to subject/description re-sync the share copy (respecting `include_description`); revoke audited | Vendor view never stale |
| TKT-09 | **Assignment & workload**: unassigned queue, reassign audit, "mine" default for non-owners | |

### 4.4 Shared tickets

| ID | Work | Acceptance |
|---|---|---|
| SHR-01 | Nav visible only to the vendor company (FND-11); non-vendors get 404 route | No empty page for ordinary companies |
| SHR-02 | Detail route; "Open" opens the *shared* ticket; remove stray "Next" button; pagination + status filter + search | |
| SHR-03 | **Vendor response** per D6, with an explicit RLS model. A reply is **dual-written inside one `rls_bypass()` block**: a `VendorTicketShareComment` row owned by the vendor company (`company_id = vendor`, so the vendor reads its own sent replies) and a `TicketComment` row owned by the source company (`company_id = source`, `is_internal=False`, author label "Vendor", so the source reads it on its ticket). The write helper asserts `share.vendor_company_id == acting company` and that the share is not revoked; the source company never gets write access to the vendor rows. Source assignee is notified; vendor can acknowledge / set a vendor-side state | RLS tests both ways: vendor cannot read other vendors' shares; source cannot read vendor-internal rows; revoked share refuses replies |
| SHR-04 | Revoked shares show a clear "no longer shared" state to the vendor rather than disappearing | |

### 4.5 Complaints and supplier complaints

Customer (`CMP`) first; `SCM` mirrors each with the purchase equivalents (`PurchaseInvoice`, `PurchaseDebitNote`) — implement shared logic once in `complaints/services.py` parameterised by model.

| ID | Work | Acceptance |
|---|---|---|
| CMP-02 | **Lock links**: customer & source invoice immutable once any document is linked or status ≥ APPROVED (serializer `validate`) | Test: change invoice after credit note → 400 |
| CMP-03 | **Reason + confirm**: REJECTED requires `inspection_notes`; terminal moves (Reject, Resolve) use ConfirmDialog | |
| CMP-04 | **Resolution rule** (D2): resolving without any document requires `resolution_note` (new field); report distinguishes | Migration + tests |
| CMP-05 | **Document recovery**: `POST unlink-document` allowed when the linked document is CANCELLED/unposted; audited; `_assert_posted` message names the blocking document | CCJ-00c scenario recoverable |
| CMP-06 | **Multi-line documents**: line table with checkboxes + qty ≤ *returnable quantity* (reuse the sales-returns returnable-lines endpoint), server re-validates. Wrap `create-return`, `create-credit-note`, `create-replacement-order` (and `create-debit-note`) in `wrap_idempotent` like job convert / milestone invoice | Over-return → 400; replayed request returns the same document |
| CMP-07 | **List**: table (number, customer, category, status chip, invoice, assignee, age, created); search; filters (status, category, assignee, customer, date); pagination | |
| CMP-08 | **Detail route**: header with customer/invoice links; edit description/category/assignee while OPEN/INSPECTING; explicit *Save notes* (`PATCH inspection_notes`, no transition); activity timeline | Notes never lost |
| CMP-09 | **Document links go to the document** (return detail, not list); drop the stray "Issue credit note" shortcut or route it through the complaint so it's linked | |
| CMP-10 | **Source-invoice picker**: searchable by number (FND-04), no 20-item cap | |
| CMP-11 | **Attachments**: blocked on closed complaints; image thumbnails; size/type error text | |
| CMP-12 | **Report**: date range, by assignee, ageing buckets, SLA target (D3) | |
| CMP-13 | "Create ticket / job card from complaint" (XLK-01) | |
| SCM-01…13 | Mirror CMP-01…13 for supplier complaints. **Parity note:** a supplier complaint has a single remedy document, `PurchaseDebitNote` (no purchase return, no replacement purchase order). So SCM-05 unlinks only the debit note, SCM-06 line selection feeds the debit note only, SCM-09 has one document link, and the "return vs credit note" exclusivity rule does not apply. Adding a purchase-return link is out of scope unless decision D12 asks for it | |

### 4.6 Projects (`backend/projects`, `web/src/pages/projects`)

| ID | Work | Acceptance |
|---|---|---|
| PRJ-01 | **Unstick READY**: `milestones/:id/unready` (READY, no invoice → PLANNED); allow delete of READY without invoice | Project with abandoned READY milestone can close |
| PRJ-02 | **Cancel project**: allowed when no COMPLETED milestone invoice; cancels/unlinks drafts, marks CANCELLED, audit; `close` message lists blocking milestones. **`close` requires at least one INVOICED milestone** — today an empty project (zero milestones) can be closed; direct it to Cancel instead | Test: empty project → close refused, cancel works |
| PRJ-03 | **Edit project**: name, notes, start/end date, optional `contract_value`; migration; `http_method_names` adds PATCH | |
| PRJ-04 | **Ordering**: sequence editable in UI + drag reorder; invoicing out of order shows a warning (not block) | |
| PRJ-05 | **Money summary** on list/detail: total, invoiced, ready, remaining, % complete (progress bar); label "Amount excludes GST" with computed incl-GST preview; warn if sum > `contract_value` | |
| PRJ-06 | **Invoice traceability**: invoice line description `PRJ-0001 · <milestone>`; project columns in sales reports via `project_milestones` relation; project link on invoice detail; a draft invoice linked to a milestone is read-only for line edits in Sales (same guard as JOB-02) | |
| PRJ-07 | **UI rebuild**: create via `CreateDialog` with success feedback; table list + filters + search + pagination; detail route with milestone table (add via dialog, not always-open row form); `enumLabel`/`formatMoney`; ConfirmDialog everywhere | |
| PRJ-08 | Links: `Project.contract` FK (nullable), tickets/jobs referencing the project (XLK) | |
| PRJ-09 | Milestone due reminders (target date passed & not invoiced) via the same notification task as CON-09 | |

---

## 5. Phase 3 — Cross-module integration

| ID | Work | Detail |
|---|---|---|
| XLK-01 | **Origin links**: nullable FKs — `Ticket.source_invoice`, `Ticket.contract`, `Ticket.job_card`, `Ticket.complaint`; `JobCard.ticket/.source_complaint/.contract`; `Complaint.ticket`; `Project.contract`. Single "Create … from this" action menu on each detail page | **Columns/migrations now live in FND-13 (Phase 1).** This WP only wires the UI actions and serializers, so no model is migrated twice |
| XLK-02 | **Coverage lookup**: `GET /api/contracts/coverage/?customer=&product=&date=` → covering active contracts (type, end date, schedule). **Query must match both product representations:** `Q(product_id=p) | Q(covered_products__product_id=p)` with `distinct()`, otherwise the 2nd+ product of a multi-product contract is missed. Effective status computed from dates (not the cached `status`). Consumed by job card create, ticket create, complaint detail ("under warranty?") | Expired/cancelled excluded; date-boundary tests |
| XLK-03 | **Linked-records panel + endpoint** `GET /api/links/?entity=&id=` returns neighbours (tickets, jobs, complaints, contracts, projects, invoices, documents) with number/status/href; rendered via one `<LinkedRecordsPanel>` | One query set per entity, bounded |
| XLK-04 | **Customer 360 / customer detail** shows open tickets, complaints, jobs, active contracts, projects (count + link) | Uses XLK-03 |
| XLK-05 | **Dashboards/notifications**: tickets past SLA, expiring contracts, overdue milestones, jobs ready to invoice appear on the owner dashboard / action centre | Reuse `tickets_past_sla_q`, effective contract status |
| XLK-06 | **Reports**: add care & job KPIs (resolution time, SLA met %, repeat complaints per product/supplier, warranty cost, free-vs-paid jobs, project billed vs planned) to the reports hub | Respect report access rules (`reportAccess.ts`) |
| XLK-07 | **Permissions** (D1): keep `CanCreateSales` as base; add read-only access for VIEWER role to care lists; restrict delete/share/cancel to owner or a new `can_manage_care` flag; supplier complaints keep purchases right | Role matrix test (OWNER/SALES/PURCHASE/VIEWER) per endpoint |

---

## 6. Phase 4 — Quality gates (needed for the 10s)

| ID | Gate | Detail |
|---|---|---|
| QA-01 | Backend tests | New files per module (`test_care_*`, `test_jobs_*`, `test_contracts_*`, `test_projects_*`); cross-company isolation on every new endpoint; idempotency replays; query-count ceilings on lists |
| QA-02 | Postgres concurrency | Bay double-booking, ticket double-transition, complaint doc double-link, milestone double-invoice, contract renew double-click |
| QA-03 | Failure-state tests (vitest) | For each page: loading, empty, error+retry, validation error mapped to field, 409 reload, offline retry; no console errors |
| QA-04 | Accessibility | `vitest-axe` on each page + Playwright keyboard run (board move, dialog focus trap, table nav); mobile viewport 375 px snapshot; contrast check on chips |
| QA-05 | E2E golden journeys | (1) complaint→approve→credit note→complete→resolve; (2) ticket→job card→invoice→resolve; (3) contract create→billing→expire→renew; (4) project milestones→close; (5) share ticket→vendor reply |
| QA-06 | Regression sweep | Sales invoice cancel/complete hooks, recurring schedule beat, RLS suite, global search, existing `test_pj_*` persona tests, openapi snapshot + `openapi-types.ts` regeneration (CI drift check) |
| QA-07 | Docs & backlog | Update `docs/FREEZE_SCOPE_COVERAGE.md`, `docs/TESTING_STRATEGY.md` gaps, add QOS items for Hindi review and CA/ops sign-offs (commission, warranty accounting) |
| QA-08 | Re-score | Repeat the review rubric per screen (section 9); anything < 10 becomes a tracked defect |

---

## 7. Decisions needed from the founder (recommended default first)

| # | Decision | Recommended |
|---|---|---|
| D1 | Who may use care screens? | Keep sales right; add read-only for VIEWER; delete/share/cancel owner-only or `can_manage_care` |
| D2 | May a complaint resolve with no document? | Yes, but only with a written `resolution_note` |
| D3 | Complaint SLA target? | Same four-tier model as tickets; default 7 days, report only (no auto-escalation yet) |
| D4 | Customer-visible ticket replies? | Not now; keep internal; revisit with WhatsApp (Growth OS) |
| D5 | Technician commission | Post to payroll at invoice completion **if** payroll already consumes it (WP CCJ-00d decides); otherwise hide the fields |
| D6 | Vendor replies on shared tickets? | Yes — vendor→source comment only; no source→vendor writes |
| D7 | Contract renewal model | Extend in place + renewal history (not successor contracts) |
| D8 | INSURANCE contract type | Remove from the picker; use the Insurance module (keep existing rows readable) |
| D9 | Job card bay/vehicle fields | Keep (workshop archetype) but show only when the Workshop/auto archetype pack is on |
| D10 | Warehouse for job card parts | Optional `JobCard.warehouse`, defaulting to the default warehouse; reserve and deduct from the same one |
| D11 | Contract billing cadence | Selector at "Start billing" (monthly default); existing monthly schedules unaffected |
| D12 | Supplier complaint remedies | Debit note only for now; purchase-return / replacement PO link deferred |

---

## 8. Data and API changes (summary)

New columns (all nullable/defaulted, expand-only): `Complaint.resolution_note`, `SupplierComplaint.resolution_note`, `Ticket.{source_invoice, contract, job_card, complaint}`, `JobCard.{contract, ticket, source_complaint}`, `JobCardLine.covered_by_contract`, `Project.{notes, start_date, end_date, contract_value, contract}`, `Complaint.ticket`.
Also: `Contract.expiring_from_date` (+ indexes), `Ticket.waiting_total_seconds`, `JobCard.warehouse`, `ServiceBay.is_active`. All of these ship in FND-13, not per module.
New tables: `ContractRenewal`, `VendorTicketShareComment` (RLS policies required — follow `core/migrations/0039_rls_supplier_complaint.py`).
New endpoints: `workshop/bays/` (CRUD), `complaints/:id/unlink-document` (minimal version in Phase 0), `jobs/:id/reopen`, `jobs/:id/lines/:id` (PATCH/DELETE), `jobs/:id` (PATCH), `contracts/:id/renew`, `contracts/:id/sync-schedule`, `contracts/coverage/`, `complaints/:id/unlink-document`, `projects/:id/milestones/:mid/unready`, `projects/:id/cancel`, `audit/`, `links/`.
All list endpoints gain `q`, `page`, ordering, and `*_name` display fields. Regenerate `docs/openapi-snapshot.json` and `web/src/api/openapi-types.ts` (never read them whole; grep).

---

## 9. Dimension → work package traceability (final check)

| Dimension | Must all be true at sign-off | WPs |
|---|---|---|
| Purpose clarity | Subtitle + customer + next action on every row/detail; Shared tickets hidden for non-vendors | FND-03, FND-11, SHR-01 |
| UX | Master–detail routes, tables, feedback beside action | FND-02/05/06, all rebuilds |
| Cognitive load | Zero typed IDs; defaults; progressive disclosure | FND-04, JOB-05, TKT-03 |
| Flow | No dead ends (stuck READY, expired contract, cancelled return, unshared Stop) | PRJ-01/02, CON-03, CMP-05, TKT-08 |
| Functionality | Edit/search/filter/page/export/delete rules on all seven | per module |
| Business logic | D1–D9 closed; line/invoice/reservation integrity | JOB-02/03, CON-05, CMP-04 |
| Data/state | Locks, versioning, idempotency, sync of dependants | FND-12, TKT-07, JOB-06, CON-02 |
| Error handling | Field-mapped errors, 409 reload, no silent drops | FND-05, JOB-06, QA-03 |
| Cross-product | Links both ways, coverage lookup, search, reports, notifications | XLK-01…07, FND-11 |
| Consistency | One chip/dialog/format/i18n pass | FND-06/07/08 |
| Accessibility | axe clean, keyboard, mobile | FND-09, QA-04 |

## 10. Risks and mitigations

- **Largest rewrite is Job cards** — ship JOB-01/02a immediately (Phase 0), then rebuild behind the same route; keep old API shapes stable.
- **i18n/locale file conflicts** between parallel modules — per-module key namespaces; one owner merges `hi.ts`.
- **Shared-component churn** (`MasterDetail`, pickers) can regress other pages — introduce under new names, migrate the seven screens only, leave other pages alone.
- **Uncommitted tree**: the working tree already holds many uncommitted features (reports work, prior plans). Branch from a clean commit or use an isolated worktree for this programme; do not `git stash` (a past stash wipe is recorded in memory).
- **Postgres-only races** need the Postgres run (RAM DB recipe in `a7761e0`); SQLite passes will not prove QA-02.
- **Accounting-adjacent items** (commission, warranty cost, free-of-charge lines) need CA sign-off — track as QOS items, don't gate engineering.

## 11. Suggested first sprint (5 days)

Phase 0 is realistically 4 days, because three of the items are confirmed bugs that each need a failing test, a fix and a regression run. Day 1: CCJ-00e (subscription lock), JOB-01, TKT-01a, CMP-01 (quick wins), plus the failing tests for CCJ-00a/b/c. Day 2: fix CON-01a and JOB-02a/JOB-11a. Day 3: minimal `unlink-document` (CCJ-00c) and CCJ-00d. Day 4: Phase 0 regression run on SQLite and Postgres. Then Phase 1 in this order: FND-13 (migrations), FND-01 (search), FND-03/03b, FND-10 (audit gaps), FND-05/06/07/14, then FND-02. Then module rebuilds in the order Job cards → Contracts → Tickets/Shared → Complaints → Projects.

---

## Completion record (2026-10-19)

All phases were built with the recommended defaults for D1 to D12. Nothing is committed.

**Verified:** ruff clean; `tsc -b` and eslint clean; web suite 2627 of 2628 passed, the one failure (`inventory/ItemFormDialog`) passed on its own re-run; OpenAPI snapshot and `openapi-types.ts` regenerated; Q-OS lint green. Postgres concurrency and phase 0 tests (15) passed on a throwaway container before the last few edits.

**Not done, by design:**
- PRJ-06, a project/job column on the sales register: dropped because it altered the accountant's CSV. The invoice page shows the link.

**Needs a person:** Hindi review (QOS-0135), CA sign-off (QOS-0136), the CI Postgres lane and a live run of the golden journeys (QOS-0134), a browser and device pass.
