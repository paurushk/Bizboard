# Release-Blocking Code Review: Accounting & Ledgers Module

**Review Scope:**
- `backend/accounting/` (`models.py`, `services.py`, `views.py`, `serializers.py`, `reports.py`, `tasks.py`, management commands)
- `backend/ledgers/` (`services.py`, `views.py`, `urls.py`)
- `backend/reporting/tds_worksheets.py` & caller flows (`sales/services.py`, `purchases/services.py`, `core/services/billing.py`, `payments/services.py`)
- `web/src/pages/phase/` (`JournalsPage.tsx`, `PeriodsPage.tsx`, `FixedAssetsPage.tsx`, `AccountingReportsPages.tsx`) & `web/src/pages/accounting/`

---

## Executive Summary & Review Dashboard

### Counts by Severity

| Severity | Count | Issue Identifiers |
|---|:---:|---|
| **Critical** | 1 | ACC-001 |
| **High** | 6 | ACC-002, ACC-003, ACC-004, ACC-005, ACC-006, ACC-010 |
| **Medium** | 4 | ACC-007, ACC-008, ACC-009, ACC-011 |
| **Low** | 1 | ACC-012 |
| **Total** | **12** | |

---

### Flow Coverage Matrix

| Subflow / Write Path | Reversal / Unwind Path | Concurrency & Atomicity | Tests Present | Status / Findings |
|---|---|---|---|---|
| **Sales Invoices → GL** (`post_sales_invoice`) | Cancel calls `PostingService.reverse()` in atomic block; Amend reverses original entry date + reposts | `uniq_accounting_source_posting` unique constraint prevents double-post; period rows locked with `select_for_update` | `test_phase5_accounting.py`, `test_sprint_a_accounting_p1.py`, `test_sprint_c_recurring_tds.py` | **ACC-001** (lines outside savepoint in base), **ACC-005** (dual-ledger drift) |
| **Sales Returns & COGS** (`post_sales_return`, `post_sales_return_cogs`) | Cancel reverses entries via `reverse()` | Source-scoped idempotency on `SALES_RETURN` / `SALES_RETURN_COGS` | `test_sprint_a_accounting_p1.py`, `test_pr5_returns_serials_fefo.py` | **ACC-001** (header-only failure mode) |
| **Sales Notes (CN/DN)** (`post_note`) | Cancel reverses journal entry | Source-scoped idempotency on `SALES_CREDIT_NOTE` / `SALES_DEBIT_NOTE` | `test_phase1_notes_ledger.py`, `test_sprint_a_accounting_p1.py` | **ACC-001**, **ACC-005** |
| **Purchase Invoices → GL** (`post_purchase`) | Cancel reverses entry via `reverse()` | Source-scoped idempotency on `PURCHASE_INVOICE` | `test_phase5_accounting.py`, `test_sprint_c_recurring_tds.py` | **ACC-001**, **ACC-007** (silent TDS override), **ACC-008** (purchase tax drift absorbed) |
| **Purchase Notes (PCN/PDN)** (`post_note`) | Cancel reverses entry via `reverse()` | Source-scoped idempotency on `PURCHASE_CREDIT_NOTE` / `PURCHASE_DEBIT_NOTE` | `test_phase1_notes_ledger.py`, `test_sprint_a_accounting_p1.py` | **ACC-006** (PCN/PDN ignores TDS 2265, polluting 1250 Advances) |
| **Bill of Entry → GL** (`post_bill_of_entry`) | Cancel reverses BoE entry | Source-scoped idempotency on `BILL_OF_ENTRY` | `test_gst08_bill_of_entry.py` | **ACC-001**, **ACC-003** (bypassed GST locks in base) |
| **Receipts & Payments** (`post_receipt`, `post_supplier_payment`) | Void/cancel reverses entry | Source-scoped idempotency on `CUSTOMER_RECEIPT` / `SUPPLIER_PAYMENT` | `test_phase5_accounting.py`, `test_sprint_a_accounting_p1.py` | **ACC-001**, **ACC-005** |
| **Payment Allocations** (`post_receipt_allocation`, `post_supplier_payment_allocation`) | Unallocate reverses allocation entry | Source-scoped idempotency on `PAYMENT_ALLOCATION` | `test_phase5_accounting.py`, `test_partial_closures.py` | **ACC-001**, **ACC-005** |
| **Stock Adjustments / Opening Stock** (`post_stock_adjustment`, `post_opening_stock`) | Cancel reverses adjustment entry | Source-scoped idempotency on `STOCK_ADJUSTMENT` / `OPENING_STOCK` | `test_phase5_accounting.py` | **ACC-001**, **ACC-003** (opening stock / adjustment vs locked periods) |
| **Fixed Assets Depreciation & Disposal** (`post_depreciation`, `post_asset_disposal`) | Manual journal reversal only; no direct un-depreciate | Background Celery task (`accounting/tasks.py`) checks last posted month; disposal runs in `@transaction.atomic` | `test_phase5_accounting.py` | **ACC-001**, **ACC-003** (catch-up task bypasses GST locks) |
| **Manual Journal Vouchers** (`JournalViewSet` create, post, reverse) | Reverse action creates mirror reversal entry and flips status to `REVERSED` | Create is atomic; reverse lacked atomic wrapper in base; period TOCTOU race | `test_phase5_accounting.py` | **ACC-002** (un-atomic reverse), **ACC-004** (TOCTOU race), **ACC-009** (cutover bypassed) |
| **Financial Year Close** (`close_financial_year`) | Irreversible in UI (requires database/admin intervention) | Atomic block wrapping `FY_CLOSE` entry and all period status updates | `test_phase5_accounting.py`, `test_pr6_period_gl.py` | **ACC-003** (checks health & draft docs before close) |
| **Bank Reconciliation** (`BankReconSessionViewSet`) | Unmatch clears statement line FK and timestamp | Excludes already matched lines; scoped to company and session statement | `test_phase5_accounting.py`, `test_wave17_comms_bank_tenancy.py` | Validated (IDOR secured) |
| **Derived Ledgers & Statements** (`LedgerService`) | Dynamic query; no stored state to reverse | Branching based on `outstanding_basis`: `GL_WHEN_BOOKS` (GL 1200/2300/2100/1250) vs `DOCUMENTS_ALWAYS` | `test_ledger.py`, `test_phase5_accounting.py` | **ACC-005** (Document AR/AP vs GL party AR/AP divergence) |
| **Management Backfills** (`backfill_accounting_postings`, `backfill_missing_postings`) | Rerunning relies on idempotent `POSTED` checks | No outer transaction per document in older command; inherits line atomicity holes | `test_phase5_accounting.py` | **ACC-001**, **ACC-003**, **ACC-010** (safety & scope discrepancies) |

---

## Core Checklist Verification

### 1. Derived-Ledger Claim vs Live Accounting GL
- **Verdict:** Verified with Architectural Nuance.
- **Evidence:** The codebase contains **no** `CustomerLedger` or `SupplierLedger` tables. Balances and statements are generated on the fly by `LedgerService`. When `company.accounting_enabled` is False or `outstanding_basis` is `DOCUMENTS_ALWAYS`, party balances are derived strictly from documents (`SalesInvoice`, `PurchaseInvoice`, `PaymentAllocation`, `SalesCreditNote`, `PurchaseCreditNote`). When `accounting_enabled` is True and `outstanding_basis` is `GL_WHEN_BOOKS` (default), party balances foot to GL control accounts (`1200` net of `2300` for AR; `2100` net of `1250` for AP) using `JournalLine.customer` and `JournalLine.supplier` tags.
- **Risk Identified:** Individual invoice outstanding (`sales_invoice_outstanding`) is *always* computed from documents, whereas party totals use GL lines. If any posting is missed or an untagged journal is posted, party ledger balances disagree with open invoice totals (**ACC-005**).

### 2. Period Gates Across All Posting Paths
- **Verdict:** Broken in Base / Repaired in Current WIP.
- **Evidence:** Document completion endpoints in Sales, Purchases, Payments, and Notes call `assert_period_allows_money_amend(company, date)` in `reporting/gst_periods.py` (which checks both `AccountingPeriod` and `GstReturnPeriod`). However, `PostingService.post` in base code checked only `AccountingPeriod`, completely bypassing `GstReturnPeriod` locks (**ACC-003**). Direct callers like background depreciation (`accounting/tasks.py`), ITC reclassification, and management backfill commands could write journals into GST-locked periods. Furthermore, manual journals posted via `JournalViewSet.post` bypassed `company.books_start_date` (**ACC-009**), and period closure suffered from a concurrent TOCTOU race condition (**ACC-004**).

### 3. Cess GL & TCS/TDS Explicit Amount Overrides
- **Verdict:** Partially Implemented; Discrepancy Found.
- **Evidence:**
  - **Cess GL:** Fully mapped in Chart of Accounts: `2270` Output Cess (Liability), `1370` Input Cess (Asset), `2280` RCM Cess Payable (Liability). Sales enforces hard-stop tax validation (drift > ₹0.05 fails), but purchase posting absorbs drift into charges/inventory (**ACC-008**).
  - **TCS (206C):** `apply_tcs_fold` in `sales/services.py` prioritizes explicit `tcs_amount` over calculated rate. When divergent, both values are recorded in `invoice._tcs_override` and written to the `COMPLETE` `StatutoryDocumentEvent` (verified by `test_tcs_sales_gl_206c`).
  - **TDS (194C/J/Q):** `fold_tds_from_rate` in `core/services/billing.py` allows positive amount to override rate, but in base code, this override was completely silent and omitted from statutory audit logging (**ACC-007**).
  - **Purchase Notes:** Purchase credit and debit notes did not reverse TDS Payable (account `2265`), polluting Supplier Advances (`1250`) on full credit notes (**ACC-006**).

### 4. Contra & Voucher Entries
- **Verdict:** Enforced via Manual Journals; UI Gaps.
- **Evidence:** Bizboard has no separate "Contra" document type; bank-to-cash, cash-to-bank, and bank-to-bank transfers are booked as manual `JournalEntry` records. Double-entry integrity is enforced on create and post via `assert_balanced()` (sum of debits == sum of credits). However, the frontend (`JournalsPage.tsx`) lacks fields for `customer`, `supplier`, and `cost_center`, preventing users from attaching party sub-ledger tags to manual journal lines.

### 5. Dual-Ledger Divergence
- **Verdict:** Vulnerability Confirmed.
- **Evidence:** `BooksHealthService.control_balances` originally compared total GL `1200` against customer-tagged GL `1200` (verifying zero untagged lines), but did **not** compare document AR (`sum(bulk_customer_outstanding)`) against party-tagged GL AR. As a result, drifting document allocations or missed invoice postings caused party ledger views to show one number while open invoices showed another, without triggering a health error or blocking period close (**ACC-005**).

### 6. Tenancy & Permissions
- **Verdict:** Robust Backend Enforcement.
- **Evidence:** All models inherit `CompanyScopedModel` (`Account`, `AccountingPeriod`, `CostCenter`, `JournalEntry`, `BankReconSession`, `FixedAsset`). `JournalLine` maintains a denormalized `company` ForeignKey with index. All viewsets inherit `CompanyScopedViewSet` and `AccountingEnabledMixin`. Mutating actions require `CanPostJournals`, reading requires `CanViewFinancialReports`, and period close/soft-close is strictly restricted to `IsOwner`. Bank reconciliation session matches verify that statement lines belong to the session statement and matching company (preventing IDOR).

### 7. Atomicity & Transaction Boundaries
- **Verdict:** Critical Defect in Base Posting Engine.
- **Evidence:** In base code, `PostingService.post` created the `JournalEntry` header inside a `transaction.atomic()` savepoint, but executed `JournalLine.objects.bulk_create` *after* the block exited (**ACC-001**). Failure during line creation left an empty `POSTED` header that permanently blocked reposting. `PostingService.reverse` also lacked an atomic boundary with the status flip (**ACC-002**).

---

## Detailed Review Findings

### ACC-001 — Journal lines created outside entry savepoint
- **Module:** Accounting -> `PostingService.post` atomicity
- **Location:** `backend/accounting/services.py:548-574`
- **Type:** Data-integrity
- **Severity:** Critical
- **What's wrong:** In `PostingService.post`, `JournalEntry.objects.create(...)` was placed inside a `transaction.atomic()` block, but `JournalLine.objects.bulk_create(...)` executed *after* that atomic block exited. Any database exception, network drop, timeout, or constraint failure during line creation leaves a committed `POSTED` `JournalEntry` header with zero lines in the database. Furthermore, the idempotent fast-path at the start of `post()`:
  ```python
  existing = JournalEntry.objects.filter(
      company=company, source_type=source_type, source_id=source_id, purpose=purpose,
      status=JournalEntry.Status.POSTED,
  ).first()
  if existing:
      return existing
  ```
  returns the existing header immediately without checking whether lines exist. Subsequent retries from document completion, Celery retry loops, or backfill scripts treat the journal as already posted and never write the lines.
- **Trigger / repro:** Enable accounting on a company. Trigger a posting (e.g. invoice completion or backfill). Induce an error or interrupt the worker process immediately after `JournalEntry.objects.create` before `bulk_create` completes. Observe a `POSTED` entry with `lines.count() == 0`. Re-invoke `PostingService.post`: the empty header is returned and lines are permanently missing.
- **Consequence:** The General Ledger silently loses debits and credits for completed documents. Trial balance, balance sheet, and party sub-ledgers become permanently corrupted. Period close health checks may not flag a missing posting because the `JournalEntry` record exists.
- **Code evidence:** `backend/accounting/services.py`:
  ```python
  with transaction.atomic():
      number = DocumentNumberService.next_number(company, "JOURNAL_ENTRY")
      entry = JournalEntry.objects.create(...)
  # CRITICAL FLAW: bulk_create executes outside the atomic savepoint above:
  JournalLine.objects.bulk_create([
      JournalLine(entry=entry, account=line["account"], ...) for line in lines
  ])
  ```
- **Suggested fix direction:** Enclose both `JournalEntry.objects.create` and `JournalLine.objects.bulk_create` inside the identical `transaction.atomic()` savepoint. In the deduplication lookup, verify `existing.lines.exists()`, deleting and recreating any orphaned empty headers.
- **Test to add:** `test_posting_service_atomic_rollback_on_line_failure`: Mock `JournalLine.objects.bulk_create` to raise `DatabaseError`; assert that no `JournalEntry` is committed and a subsequent retry succeeds with all lines.
- **Twin check:** `JournalViewSet.create` (`views.py:192-229`) correctly decorates the entire method with `@transaction.atomic`.

---

### ACC-002 — `PostingService.reverse` not atomic with status flip
- **Module:** Accounting -> Reversal & Void integrity
- **Location:** `backend/accounting/services.py:1776-1800` & `backend/accounting/views.py:258-263`
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** `PostingService.reverse()` creates a compensating reversal journal entry via `post()`, and then updates the original journal entry's status to `REVERSED` with `reversed_entry=reversal`. In the base code, `reverse()` was not wrapped in `@transaction.atomic`, and the HTTP API action `JournalViewSet.reverse` had no `@transaction.atomic` decorator. If an interruption, database disconnection, or error occurs after the reversal entry is posted but before the original entry's status update is committed, both the original entry and the reversal entry remain in `POSTED` status (with `reversed_entry_id = None`).
- **Trigger / repro:** Post a manual journal entry. Invoke `POST /api/v1/accounting/journals/<id>/reverse/` under an induced failure during `entry.save(update_fields=["status", "reversed_entry", "updated_at"])`. Observe that the reversal entry exists as `POSTED`, while the original entry also remains `POSTED`. Triggering `/reverse/` a second time posts another reversal entry.
- **Consequence:** Both original and reversal entries remain active in the General Ledger. Subsequent retries post duplicate reversal entries, doubling the debit and credit impact on nominal accounts and party ledgers.
- **Code evidence:** In `services.py`:
  ```python
  reversal = cls.post(...) # Reversal posted and committed
  # If execution fails here:
  entry.status = JournalEntry.Status.REVERSED
  entry.reversed_entry = reversal
  entry.save(update_fields=["status", "reversed_entry", "updated_at"])
  ```
  `JournalViewSet.reverse` in `views.py` merely called `PostingService.reverse` without an atomic transaction wrapper.
- **Suggested fix direction:** Decorate `PostingService.reverse` with `@transaction.atomic` and ensure `JournalViewSet.reverse` is annotated with `@transaction.atomic` so the reversal posting and status flip commit or roll back as an indivisible unit.
- **Test to add:** `test_journal_reverse_atomic_rollback`: Induce an error during `entry.save` in `PostingService.reverse`; assert that the reversal `JournalEntry` is rolled back and the original entry remains `POSTED` without orphaned reversal records.
- **Twin check:** Operational document cancel paths (`cancel_invoice`, `cancel_purchase`) wrap document status updates and `reverse()` in outer transactions, but the manual journal reversal API did not.

---

### ACC-003 — `PostingService.post` ignores GST period locks
- **Module:** Accounting -> Period gates
- **Location:** `backend/accounting/services.py:532-537`
- **Type:** Missing-validation
- **Severity:** High
- **What's wrong:** `PostingService.post` checked only `AccountingPeriod` (`status=CLOSED` or `status=SOFT_CLOSED`). It failed to check `GstReturnPeriod` locks (`reporting/models.py:GstReturnPeriod`). The centralized period gate across Bizboard is `assert_period_allows_money_amend(company, date)` in `reporting/gst_periods.py`, which enforces both accounting period and GST return period locks. Operational document completion endpoints (sales invoices, purchases, payments, notes) called the shared assertion, but internal callers hitting `PostingService.post` directly bypassed GST return period gates entirely. Direct callers include:
  - Background asset depreciation catch-up task (`accounting/tasks.py:123`)
  - `management/commands/backfill_accounting_postings.py`
  - `management/commands/backfill_missing_postings.py`
  - ITC reclassification helpers (`reclass_unreviewed_itc`, `reclass_rejected_itc`)
  - Financial year-end close (`close_financial_year`)
- **Trigger / repro:** Soft-close or close a GST month (e.g. `2026-07` in `GstReturnPeriod`) while keeping `AccountingPeriod` open or unconfigured. Run `python manage.py backfill_accounting_postings` or trigger monthly depreciation catch-up for that month. The journal entry posts successfully.
- **Consequence:** General ledger postings land in statutory tax periods for which GSTR-1 and GSTR-3B returns have already been finalized and filed, creating irreconcilable discrepancies between filed GST returns and accounting records.
- **Code evidence:** In `backend/accounting/services.py:513-535`:
  ```python
  if AccountingPeriod.objects.filter(
      company=company, start_date__lte=entry_date, end_date__gte=entry_date, status=AccountingPeriod.Status.CLOSED
  ).exists():
      raise BusinessRuleError("Cannot post into a closed accounting period.")
  ```
  No call to `assert_period_allows_money_amend` or check against `GstReturnPeriod` existed.
- **Suggested fix direction:** Call `assert_period_allows_money_amend(company, entry_date, allow_soft_closed=allow_soft_closed)` inside `PostingService.post` prior to allocating voucher numbers or writing entries.
- **Test to add:** `test_posting_service_rejects_post_in_gst_closed_period`: Create a closed `GstReturnPeriod`; invoke `PostingService.post` with an `entry_date` in that month; assert `BusinessRuleError` is raised.
- **Twin check:** `JournalViewSet.post` (`views.py:244`) invoked `assert_period_allows_money_amend`, proving that the omission in `PostingService.post` was an oversight.

---

### ACC-004 — Period close vs concurrent post (TOCTOU race)
- **Module:** Accounting -> Period close races
- **Location:** `backend/accounting/views.py:93-149` & `backend/accounting/services.py:524-531`
- **Type:** Race
- **Severity:** High
- **What's wrong:** In `PeriodViewSet.soft_close` and `PeriodViewSet.close`, the target `AccountingPeriod` was retrieved via `self.get_object()` without `select_for_update()`, and neither action method was wrapped in `@transaction.atomic`. Concurrently, `PostingService.post` queried `AccountingPeriod.objects.filter(...)` using an unlocked read. If an Owner closed a period while another session was completing an invoice or voucher dated into that period, the posting thread read the period status as `OPEN` before the close transaction committed, and proceeded to insert a journal entry into the newly closed period.
- **Trigger / repro:** Concurrently run two requests: (1) Owner executes `POST /api/v1/accounting/periods/<id>/close/`; (2) Operator completes a sales invoice or posts a journal dated inside that period. The unlocked read in `post()` sees `OPEN` status before the status change commits, and inserts the journal entry after the period is marked `CLOSED`.
- **Consequence:** Invoices, payments, or vouchers land in officially closed periods, invalidating frozen financial statements and audited closing balances.
- **Code evidence:** In `views.py:95, 118`:
  ```python
  def close(self, request, pk=None):
      period = self.get_object() # Unlocked read without transaction.atomic
      ...
      period.status = AccountingPeriod.Status.CLOSED
      period.save(update_fields=["status", "updated_by", "updated_at"])
  ```
  `services.py:524` checked period status with a plain `filter(...).exists()` without row locking.
- **Suggested fix direction:** Annotate `PeriodViewSet.soft_close` and `PeriodViewSet.close` with `@transaction.atomic` and retrieve the period via `get_object_or_404(self.get_queryset().select_for_update(), pk=pk)`. In `PostingService.post`, evaluate overlapping periods using `select_for_update()` to serialize with concurrent close requests.
- **Test to add:** `test_concurrent_period_close_blocks_posting`: Under PostgreSQL, verify that a concurrent transaction closing a period blocks or serializes with `PostingService.post`, preventing backdated entries into the closed period.
- **Twin check:** A parallel TOCTOU vulnerability existed in `GstReturnPeriod` close actions.

---

### ACC-005 — Dual ledger can diverge; health check does not compare documents↔GL
- **Module:** Accounting -> Derived ledgers vs live GL
- **Location:** `backend/ledgers/services.py:1-120` & `backend/accounting/services.py:2064-2200`
- **Type:** Data-integrity / Silent-failure
- **Severity:** High
- **What's wrong:** Bizboard uses two distinct ledger calculation mechanisms:
  1. Document-derived ledger: `LedgerService.sales_invoice_outstanding` / `purchase_invoice_outstanding` calculates open balances directly from document `grand_total` minus `PaymentAllocation` records minus credit/debit notes.
  2. GL party sub-ledger: When `company.accounting_enabled` is True and `outstanding_basis` is `GL_WHEN_BOOKS` (default), party balances in `customer_outstanding` / `supplier_outstanding` and party statements are computed from GL accounts `1200` net of `2300` (AR) and `2100` net of `1250` (AP) via `JournalLine.customer` and `JournalLine.supplier` tags.
  However, individual invoice views ALWAYS use document math, while party ledgers use GL math. If an invoice posting was missed, if an allocation posting failed, or if an untagged manual journal adjusted account `1200`/`2100`, party ledger balances diverged from the sum of open invoices. Furthermore, `BooksHealthService.control_balances` originally verified only that total GL 1200 equaled customer-tagged GL 1200 (checking for untagged lines); it never verified that total GL AR equaled total document AR (`sum(bulk_customer_outstanding)`).
- **Trigger / repro:** Enable accounting. Complete a sales invoice. Simulate a missed posting or inject an untagged manual credit to `1200`. Inspect `/api/v1/ledgers/customers/<id>/` vs `/api/v1/sales/invoices/?customer=<id>`: customer statement shows ₹0 balance, while invoices list shows open unpaid invoices. Check `BooksHealthService.control_balances`: reports healthy if untagged balance is zero.
- **Consequence:** Operators see conflicting balances across the application. Cash allocation dialogs enforce document balances while customer aging and statements display GL balances. Period close is not blocked by this discrepancy.
- **Code evidence:** In `ledgers/services.py`: party balances foot to GL when books are enabled, but per-invoice outstanding strictly uses document tables. In `accounting/services.py`: `BooksHealthService.control_balances` only compared GL control accounts against tagged lines within `JournalLine`, ignoring `LedgerService.bulk_customer_outstanding(company)`.
- **Suggested fix direction:** Add a document-to-GL party reconciliation check in `BooksHealthService.control_balances` (`_docs_gl_party_alerts`) that compares total document AR/AP against tagged GL party AR/AP and generates `DOCS_GL_AR_MISMATCH` / `DOCS_GL_AP_MISMATCH` alerts when drift exceeds ₹1.00.
- **Test to add:** `test_books_health_detects_document_gl_party_divergence`: Create a document-to-GL discrepancy; assert `BooksHealthService.control_balances` returns a `DOCS_GL_AR_MISMATCH` warning alert.
- **Twin check:** Affects both Customer AR (1200 vs 2300) and Supplier AP (2100 vs 1250).

---

### ACC-006 — Purchase credit/debit notes do not reverse TDS payable (2265)
- **Module:** Accounting -> TDS / Note GL posting
- **Location:** `backend/accounting/services.py:1550-1695`
- **Type:** Data-integrity / Sales/Purchase-inconsistency
- **Severity:** High
- **What's wrong:** When a purchase invoice with TDS is posted (`post_purchase`), `PostingService` credits `2100` (AP) net of TDS and credits `2265` (TDS Payable). When a Purchase Credit Note is issued against that invoice, `PostingService.post_note` failed to reverse account `2265`. Instead, `post_note` debited `2100` (AP) up to the bill's open balance, routing any excess to `1250` (Supplier Advances). For a full Credit Note on a bill with TDS, the TDS portion was debited to Supplier Advances instead of reversing TDS Payable. Similarly, a Purchase Debit Note that enlarged a TDS bill credited only `2100` and `1400` without crediting `2265` TDS Payable.
- **Trigger / repro:** 
  1. Complete a Purchase Invoice: Taxable ₹10,000 + 18% GST (₹1,800) = ₹11,800. TDS at 10% on ₹10,000 = ₹1,000. GL posts: Dr 1400 (₹10,000), Dr 1310/1320 (₹1,800), Cr 2100 (₹10,800), Cr 2265 (₹1,000).
  2. Complete a full Purchase Credit Note of ₹11,800.
  3. Inspect GL: Dr 2100 (₹10,800), Dr 1250 (₹1,000), Cr 1400 (₹10,000), Cr 1310/1320 (₹1,800). Account `2265` retains an unreversed ₹1,000 credit, while account `1250` reflects a phantom ₹1,000 debit.
- **Consequence:** TDS Payable (2265) is permanently overstated, creating false tax liabilities. Supplier Advances (1250) is polluted with fictitious advance debits.
- **Code evidence:** In `PostingService.post_note` (`PURCHASE_CREDIT_NOTE`):
  ```python
  ap_out = LedgerService.purchase_invoice_outstanding(note.purchase_invoice)
  ap_debit = min(note.grand_total, ap_out)
  advance_debit = note.grand_total - ap_debit
  lines.append({"account": cls._account(note.company, "2100"), "debit": ap_debit, "supplier": note.supplier})
  if advance_debit > 0:
      lines.append({"account": cls._account(note.company, "1250"), "debit": advance_debit, "supplier": note.supplier})
  ```
  There was no handling for account `2265` anywhere in `post_note`.
- **Suggested fix direction:** In `post_note`, compute the proportional TDS reduction based on the parent bill's `tds_amount` and `grand_total`. Debit account `2265` TDS Payable for that slice, and reduce the `2100` AP debit and `1250` advance debit accordingly.
- **Test to add:** `test_purchase_credit_note_reverses_tds_gl`: Complete a purchase bill with TDS; complete a full credit note; assert account `2265` is debited and has a net balance of ₹0.
- **Twin check:** Sales notes with TCS (2266) add TCS to gross consideration rather than netting from receivables, avoiding the advance overflow bug, but purchase notes lacked TDS integration.

---

### ACC-007 — TDS amount-vs-rate override is silent (unlike TCS 206C)
- **Module:** Accounting -> TCS/TDS overrides
- **Location:** `backend/core/services/billing.py:121-142` & `backend/purchases/services.py:760, 831`
- **Type:** Missing-validation
- **Severity:** Medium
- **What's wrong:** Per repository product decisions, when an operator enters an explicit statutory amount (`tcs_amount` or `tds_amount`) that conflicts with the standard calculated rate, the explicit amount overrides the rate. On the sales side (`apply_tcs_fold` in `sales/services.py`), when an explicit `tcs_amount` overrides the calculated rate amount, the override and calculated rate amounts are recorded on `invoice._tcs_override` and written into `StatutoryDocumentEvent` with `payload["tcs_override"] = {"provided_amount": ..., "calculated_rate_amount": ...}`. However, for purchase TDS (`fold_tds_from_rate` in `core/services/billing.py`), the function accepted `q2(amount)` when positive without stashing override metadata or logging any statutory audit event.
- **Trigger / repro:** Create a Purchase Invoice with `tds_rate = 10.0` and `tds_amount = 500.00` on a ₹10,000 taxable purchase (expected deduction: ₹1,000). Complete the invoice. Query `StatutoryDocumentEvent` for the purchase invoice: no `tds_override` event or payload exists.
- **Consequence:** Tax auditors and CAs reviewing Form 26Q worksheets cannot determine whether a discrepancy between the bill's rate and deduction was an intentional override or an input error, failing statutory auditability requirements.
- **Code evidence:** In `core/services/billing.py:121-131`:
  ```python
  def fold_tds_from_rate(*, tds_rate, tds_amount, taxable_total, document=None) -> Decimal:
      rate = Decimal(str(tds_rate or 0))
      amount = Decimal(str(tds_amount if tds_amount not in (None, "") else 0))
      if rate > 0 and amount == 0:
          return q2(Decimal(str(taxable_total or 0)) * rate / Decimal("100"))
      return q2(amount)
  ```
  Neither divergence calculation nor audit metadata stashing existed in the base implementation.
- **Suggested fix direction:** In `fold_tds_from_rate`, when both `rate > 0` and `amount > 0` diverge, attach a `_tds_override` dictionary to `document` recording both supplied amount and calculated rate amount, and record it in `StatutoryDocumentEvent` upon purchase completion.
- **Test to add:** `test_tds_override_audit_logged`: Create purchase invoice with conflicting `tds_rate` and `tds_amount`; complete invoice; assert `StatutoryDocumentEvent` contains `payload["tds_override"]` with both values.
- **Twin check:** Parity with TCS sales implementation in `sales/services.py:apply_tcs_fold` and `backend/tests/test_sprint_c_recurring_tds.py::test_tcs_sales_gl_206c`.

---

### ACC-008 — Cess GL present; purchase tax drift weaker than sales
- **Module:** Accounting -> Tax GL integrity
- **Location:** `backend/accounting/services.py:592-612, 1020-1045`
- **Type:** Sales/Purchase-inconsistency
- **Severity:** Medium
- **What's wrong:** The chart of accounts provides dedicated accounts for Cess: `2270` Output Cess, `1370` Input Cess, and `2280` RCM Cess Payable. In `PostingService.post_sales_invoice` (lines 593-612), strict validation enforces that line tax totals match header tax fields within a ₹0.05 tolerance, aborting with `BusinessRuleError` if they drift. In `PostingService.post_purchase`, however, if header taxes or additional charges drift from line totals, the residual is absorbed into `5110` (Purchase Charges) or `1400` (Inventory) with only an audit log, rather than rejecting the document.
- **Trigger / repro:** Submit a Purchase Invoice with ₹500 line tax but ₹600 header tax or mismatched charges. The purchase completes and posts GL, silently dumping the ₹100 discrepancy into account `5110`.
- **Consequence:** Distorts expense and inventory accounts; purchases lack the hard double-entry discipline enforced on sales invoices.
- **Code evidence:** `services.py:609` enforces `if drift > Decimal("0.05"): raise BusinessRuleError(...)` on sales, whereas purchase posting lines handle residual differences via soft absorption into account `5110` (`lines.append({"account": accounts["5110"], "debit": residual})`).
- **Suggested fix direction:** Apply the same ₹0.05 drift threshold to `post_purchase`, refusing to post GL when header taxes and line totals do not reconcile.
- **Test to add:** `test_purchase_gl_rejects_tax_drift`: Attempt to post a purchase invoice with header/line tax discrepancy > ₹0.05; assert `BusinessRuleError` is raised.
- **Twin check:** Direct inconsistency between Sales and Purchase posting engines in `PostingService`.

---

### ACC-009 — Manual vouchers: balance OK; `books_start_date` bypassed
- **Module:** Accounting -> Contra & Manual Journals
- **Location:** `backend/accounting/views.py:231-256`
- **Type:** Missing-validation
- **Severity:** Medium
- **What's wrong:** Bizboard uses Manual Journals as its voucher mechanism for contra, adjustments, and opening balances. While double-entry balance is strictly validated on create and post, `JournalViewSet.post` bypassed `company.books_start_date`. Operational documents posted via `PostingService.post` reject any document dated prior to `books_start_date` (B1-032). Because `JournalViewSet.post` did not call `PostingService.post` and instead updated the entry status directly, an accountant could post a manual journal dated prior to the books cutover date. Additionally, the frontend (`JournalsPage.tsx`) does not provide inputs for customer/supplier party tags, meaning manual adjustments touching control accounts (1200/2100) are posted without party tags, triggering control balance warnings.
- **Trigger / repro:** Configure `company.books_start_date = 2026-04-01`. Create a manual journal dated `2025-12-31`. Invoke `POST /api/v1/accounting/journals/<id>/post/`. In base code, the posting succeeds without error.
- **Consequence:** Pre-cutover financial data is modified by manual journals, distorting historical opening balances and retained earnings.
- **Code evidence:** In `backend/accounting/views.py:231-256`:
  ```python
  assert_period_allows_money_amend(self.company, entry.entry_date)
  # Missing check for company.books_start_date
  entry.status = JournalEntry.Status.POSTED
  entry.save(...)
  ```
  `books_start_date` was not checked on this posting path.
- **Suggested fix direction:** In `JournalViewSet.post`, check `cutover = getattr(self.company, "books_start_date", None)` and raise `BusinessRuleError` if `entry.entry_date < cutover`.
- **Test to add:** `test_manual_journal_post_before_books_start_date_rejected`: Set `books_start_date`; attempt to post manual journal dated before that date; assert `BusinessRuleError`.
- **Twin check:** `PostingService.post` checks `books_start_date`, but `JournalViewSet.post` implemented its own posting logic and omitted the check.

---

### ACC-010 — `backfill_missing_postings` / `backfill_accounting_postings` safety gaps
- **Module:** Accounting -> Management commands
- **Location:** `backend/accounting/management/commands/backfill_accounting_postings.py` & `backfill_missing_postings.py`
- **Type:** Data-integrity / Silent-failure
- **Severity:** High
- **What's wrong:** Two separate management commands exist for backfilling GL postings with conflicting scopes and safety mechanisms. `backfill_missing_postings.py` requires `--company` and supports `--dry-run`, but only backfills notes, sales return cogs, and bills of entry—omitting core sales invoices, purchase invoices, and payments. `backfill_accounting_postings.py` attempts to backfill all entities, but originally lacked a `--dry-run` flag and operated across all companies in the database without tenant isolation. Furthermore, both commands inherited the ACC-001 defect (creating empty headers if interrupted) and the ACC-003 defect (posting into GST-locked periods without restriction).
- **Trigger / repro:** Run `python manage.py backfill_accounting_postings` in production when GST return periods have been closed. Postings are written into closed periods across all companies, and any process termination leaves unrepairable empty `JournalEntry` headers.
- **Consequence:** Running backfills can violate statutory GST locks across multiple tenants and permanently break GL idempotency for interrupted records.
- **Code evidence:** `backfill_accounting_postings.py` iterated `Company.objects.filter(accounting_enabled=True)` with no default dry-run and no per-document transaction isolation.
- **Suggested fix direction:** Deprecate `backfill_missing_postings.py` or merge into a single authoritative command requiring `--company`, defaulting to `--dry-run`, wrapping each document post in a savepoint, and respecting all period gates.
- **Test to add:** `test_backfill_command_respects_period_gates_and_dry_run`: Execute backfill command with `--dry-run` and verify zero database modifications; run against closed period and verify documents are skipped with warnings.
- **Twin check:** Inconsistency between two parallel backfill commands in the same management package.

---

### ACC-011 — Balance check does not quantize lines to 2 dp before commit
- **Module:** Accounting -> Double-entry integrity
- **Location:** `backend/accounting/services.py:512-523`
- **Type:** Data-integrity
- **Severity:** Medium
- **What's wrong:** `PostingService.post` checked double-entry balance by summing raw Decimal values provided in the `lines` list (`debit = sum(...)`, `credit = sum(...)`). However, the database columns `JournalLine.debit` and `JournalLine.credit` are defined with `decimal_places=2`. If lines contained amounts with 3 or more decimal places (e.g. from cost layer allocations, proportional TDS calculations, or FX conversions), the raw sums could be equal in Python (`10.004 == 10.004`), but upon insertion into the database, individual lines were truncated or rounded differently by the DB driver, creating an unbalanced posted journal entry.
- **Trigger / repro:** Call `PostingService.post` with lines: Dr Account A: 5.004, Dr Account B: 5.004 (total 10.008); Cr Account C: 10.008. Python equality passes. When stored in SQLite/PostgreSQL, lines become 5.00, 5.00, and 10.01. Sum of stored debits (10.00) != sum of credits (10.01).
- **Consequence:** An unbalanced journal entry is committed to the database, causing the Trial Balance and Balance Sheet equation (`assets == liabilities + equity + pl`) to fail.
- **Code evidence:** In `backend/accounting/services.py:520-523`:
  ```python
  debit = sum((Decimal(str(line.get("debit", 0) or 0)) for line in lines), Decimal("0"))
  credit = sum((Decimal(str(line.get("credit", 0) or 0)) for line in lines), Decimal("0"))
  if not lines or debit != credit:
      raise BusinessRuleError(...)
  ```
  Lines were not quantized to 2 decimal places before the sum and check.
- **Suggested fix direction:** Quantize each line's debit and credit to 2 decimal places (`Decimal("0.01")`) before calculating totals, validating balance, and executing `bulk_create`.
- **Test to add:** `test_post_rejects_or_quantizes_sub_paisa_unbalanced_lines`: Submit journal lines with sub-paisa amounts that unbalance after 2dp rounding; assert rejection or proper quantization.
- **Twin check:** Model-level `assert_balanced()` aggregates database columns with 2dp, which would catch this post-commit, but `post()` failed to guard before commit.

---

### ACC-012 — Feature-flag gating: UI dual-key vs API `accounting_enabled`
- **Module:** Accounting -> Feature gating
- **Location:** `web/src/App.tsx`, `web/src/navigation/menu.ts`, `backend/core/services/feature_flags.py`, `backend/accounting/views.py:34-40`
- **Type:** Improvement
- **Severity:** Low
- **What's wrong:** Access to the Accounting module in the frontend is gated by two checks: `isAccountingFeatureEnabled()` (evaluating `VITE_ENABLE_ACCOUNTING`) and `company.accountingEnabled`. In the backend, `ENABLE_ACCOUNTING` is derived directly from `company.accounting_enabled`, and viewsets enforce `AccountingEnabledMixin`. When a tenant operates with accounting disabled and subsequently enables it in Settings, historical completed documents have no GL postings. The Books Health page immediately surfaces numerous `DOCUMENT_MISSING_POSTING` errors without offering a self-service resolution mechanism in the UI.
- **Trigger / repro:** Create invoices with accounting disabled. Enable accounting via `POST /api/v1/accounting/settings/` (`accounting_enabled: true`). Navigate to Books Health: system reports unhealthy books due to missing historical postings.
- **Consequence:** Tenant is alerted to unhealthy books immediately upon turning on the feature, with no UI button or automated background process to generate catch-up postings.
- **Code evidence:** `AccountingSettingsView.post` seeds the chart of accounts (`seed_chart_of_accounts`) when enabled, but does not trigger an asynchronous backfill task or provide guidance on historical document postings.
- **Suggested fix direction:** When `accounting_enabled` is switched from False to True, enqueue a background task to backfill missing postings, or expose a clear banner and button in the UI directing the user to run a books initialization backfill.
- **Test to add:** `test_enable_accounting_seeds_coa_and_health_surfaces_backfill_need`: Verify that enabling accounting seeds the CoA and accurately reports missing posting count in health check.
- **Twin check:** Similar pattern to GST reporting enablement (`gstr_reports_enabled`).