# Area 03 — Backend Inventory, Payments, Ledgers, Masters, Reporting, Search, Imports

**Scope:** `inventory/*`, `payments/*`, `ledgers/*`, `masters/*`, `reporting/*`, `search/*`, `imports/*` (models/serializers/services/views/urls/apps/migrations).

**Test execution:** After installing a missing dependency (`djangorestframework-camel-case`):
```
python -m pytest tests/test_ledger.py tests/test_payment_allocation.py tests/test_stock_flow.py -q
25 passed in 18.99s
python -m pytest tests/test_search_reports_audit.py tests/test_imports.py tests/test_purchase_bill_import.py -q
21 passed in 26.37s
```
All 46 existing tests pass. Findings below are gaps not covered by these tests, or logic errors the tests don't exercise (mostly concurrency and permission-boundary cases).

---

### BUG-300 — "Dashboard receivables loops all customers" (BUG-013) — claim verification
- **Severity:** N/A (claim verification)
- **Location:** `backend/reporting/services.py:22-43, 100-145`
- **Description:** Inaccurate as stated. `ReportService.dashboard()`'s `_company_receivables`/`_company_payables` are pure SQL `aggregate()` calls, not a per-customer Python loop (docstring: "SQL aggregation — avoids per-customer Python loop").
- **Status vs prior report:** INACCURATE (wrong location — the real N+1 is elsewhere, see BUG-301).

### BUG-301 — Real per-party N+1 in customer/supplier ledger list views
- **Severity:** High
- **Category:** Performance
- **Location:** `backend/ledgers/views.py:23-34, 61-71`; root cause `backend/ledgers/services.py:54-69` (`customer_outstanding`)
- **Description:** `CustomerLedgerListView`/`SupplierLedgerListView` iterate every `Customer`/`Supplier` row and call `LedgerService.customer_outstanding` per row, which itself issues 3 separate `aggregate()` queries. For N customers this is `3N + 1` queries, with **no pagination** on this `APIView` at all (unlike `ModelViewSet`-based masters endpoints).
- **Impact:** A retailer with a few thousand customers turns "view outstanding balances" into thousands of DB round-trips and a multi-MB unpaginated JSON payload.
- **Remediation:** Compute all outstandings in one query via `.values("customer_id").annotate(...)` joined against returns/allocations aggregates; add pagination.
- **Suggested test:** 200 customers with invoices/allocations; assert bounded query count via `CaptureQueriesContext`.
- **Status vs prior report:** CONFIRMED (BUG-013, at the corrected location).

### BUG-302 — `dashboard()`'s `receivables_aging` loops every open invoice with 2 extra queries each
- **Severity:** Medium
- **Category:** Performance
- **Location:** `backend/reporting/services.py:67-98`, called from `dashboard()` line 133
- **Description:** Iterates every open `SalesInvoice` in Python and calls `sales_invoice_outstanding` per invoice (2 more aggregate queries each) — same N+1 shape as BUG-301, scoped to invoices, running on every dashboard load.
- **Remediation:** Precompute returns/allocations per invoice via `.values("id").annotate(...)` joined in one pass; bucket in Python only.
- **Suggested test:** Assert bounded query count for `dashboard()` with 100+ open invoices.
- **Status vs prior report:** NEW (adjacent to BUG-013's intent, different mechanism — likely the more common real-world trigger for slow dashboards).

### BUG-303 — Purchase vs sales outstanding "inconsistency" (BUG-017) — claim verification
- **Severity:** N/A
- **Location:** `backend/ledgers/services.py:27-50`; `backend/purchases/models.py:10-14`; `backend/sales/models.py:10-15`
- **Description:** Inaccurate. `PurchaseInvoice.Status` has no `RETURNED` value (only DRAFT/COMPLETED/CANCELLED); a fully purchase-returned invoice stays COMPLETED. Both outstanding functions still subtract returns unconditionally for their respective "still active" status — the math is symmetric, only the vocabulary differs by design.
- **Status vs prior report:** INACCURATE.

### BUG-304 — Unallocated receipts credited with no "Advance" label (BUG-018) — claim verification
- **Severity:** N/A
- **Location:** `backend/ledgers/services.py:90-98, 152-160`
- **Description:** Inaccurate/already handled. Both `customer_statement` and `supplier_statement` compute `unallocated = receipt.amount - allocated` and set `"is_advance": unallocated > 0` plus an `"unallocated"` field on every entry.
- **Suggested test:** Assert `is_advance is True` for an unallocated receipt in `test_ledger.py` (currently only `balance` is checked) — a narrow but real test gap.
- **Status vs prior report:** ALREADY-FIXED (backend has the data; if the frontend doesn't render it, that's a frontend gap — see BUG-527).

### BUG-305 — `customer_statement`/`supplier_statement` built as Python lists
- **Severity:** Low
- **Category:** Performance
- **Location:** `backend/ledgers/services.py:71-172`
- **Description:** Confirmed present — full queryset fetch, Python-side sort, Python-accumulated running balance. Currently bounded to a single party's document count (not in the N+1 path of BUG-301, which calls `customer_outstanding` instead).
- **Impact:** Fine today; would matter only if a future bulk/combined-statement feature reused this per-party function across the whole customer base.
- **Status vs prior report:** CONFIRMED-STILL-PRESENT (low current impact).

### BUG-306 — LLM bill import: no request timeout, real cost/hang risk
- **Severity:** Medium
- **Category:** Bug
- **Location:** `backend/core/services/llm.py:122-186`; `backend/imports/tasks.py:38`
- **Description:** Neither the OpenAI-compatible nor Claude SDK client is constructed with a `timeout=`, and no `time_limit`/`soft_time_limit` on the Celery task. A hanging provider blocks the worker indefinitely, leaving the `ImportJob` stuck in `EXTRACTING` forever with no automatic recovery.
- **Remediation:** Pass `timeout=` to both SDK clients; add `@shared_task(time_limit=120, soft_time_limit=90)`.
- **Suggested test:** Mock the LLM call to sleep past a configured timeout; assert the job ends `FAILED` not hung.
- **Status vs prior report:** CONFIRMED (PERFORMANCE_REPORT.md).

### BUG-307 — Search/masters `icontains` filtering with no trigram/GIN index; not benchmarked
- **Severity:** Medium
- **Category:** Performance
- **Location:** `backend/search/views.py:25-40`; `backend/masters/views.py:47-49, 60-61, 75-78`
- **Description:** Zero `GinIndex`/`TrigramSimilarity`/`pg_trgm`/`SearchVector` usage anywhere. All text search uses plain `Q(name__icontains=q)`, forcing a sequential scan on Postgres for leading-wildcard patterns regardless of existing btree indexes. No raw SQL anywhere either — no SQL-injection vector (confirmed all-ORM).
- **Remediation:** Add `pg_trgm` extension + `GinIndex(opclasses=["gin_trgm_ops"])`, or switch to Postgres full-text search.
- **Status vs prior report:** CONFIRMED (PERFORMANCE_REPORT.md); no SQL injection found.

### BUG-308 — Payment allocation race condition: no row locking allows over-allocation
- **Severity:** High
- **Category:** Bug
- **Location:** `backend/payments/services.py:63-90` (`allocate_receipt`), `:92-121` (`allocate_supplier_payment`)
- **Description:** Both methods run under `@transaction.atomic` but never `select_for_update()` the receipt/payment or target invoice. Under READ COMMITTED, two concurrent allocation requests against the same receipt can both read the same "unallocated" value before either commits, both pass the `amount > unallocated` check, and produce total allocations exceeding the receipt amount or invoice outstanding.
- **Evidence:** Existing test `test_allocations_cannot_exceed_receipt_across_calls` only exercises sequential calls via the synchronous test client, which cannot expose this race.
- **Impact:** Double-allocation of the same receipt/payment, silently overstating how much of an invoice is paid — directly corrupts the derived-ledger invariant.
- **Remediation:** Lock the payment row and the invoice row inside the atomic block before recomputing `unallocated`/`open_outstanding`.
- **Suggested test:** Two threads/connections firing concurrent `allocate_receipt` calls each requesting more than half the receipt; assert exactly one succeeds.
- **Status vs prior report:** NEW. (Same class of race independently found in area 02 as BUG-222 for stock.)

### BUG-309 — Stock oversell race: negative-stock check is not locked before posting the movement
- **Severity:** High
- **Category:** Bug
- **Location:** `backend/inventory/services.py:55-65, 32-48`; `backend/sales/services.py:213-216`
- **Description:** Same race as BUG-222 (area 02), found independently: `check_negative_stock` reads an unlocked `StockBalance` snapshot before `post_movement`'s own (later) lock. Two invoices for the same product, completed concurrently, can both pass the BLOCK check and both post, driving `on_hand` negative.
- **Remediation:** Acquire the `StockBalance` row lock before computing `available`, re-checking inside the same locked section that performs the update.
- **Suggested test:** Two threads completing different draft invoices for the same product where combined demand exceeds available stock; assert exactly one succeeds under BLOCK policy.
- **Status vs prior report:** NEW — see also BUG-222.

### BUG-310 — `PaymentAllocationViewSet` allows any company member to delete an allocation, unaudited
- **Severity:** High
- **Category:** Bug
- **Location:** `backend/payments/views.py:74-96`
- **Description:** Extends `DestroyModelMixin` directly (not `CompanyScopedViewSet`) with only `[IsAuthenticated, HasCompany]` — no `CanCancelDocuments`, no `perform_destroy` override, no audit log call. Any authenticated company member — including default-privilege `SALES_STAFF` (`can_cancel_documents=False` by default) — can `DELETE` an allocation and silently un-apply a payment, with zero audit trail.
- **Impact:** A low-privilege user can retroactively make a paid invoice appear unpaid with no record of who did it.
- **Remediation:** Require `CanCancelDocuments` (or a new permission) on delete; log via `AuditService.log`.
- **Suggested test:** `staff_client.delete(...)` should return 403; owner delete should produce an `AuditEvent`.
- **Status vs prior report:** NEW.

### BUG-311 — Deleting a CustomerReceipt/SupplierPayment cascades away all its allocations with no guard or detailed audit
- **Severity:** High
- **Category:** Bug
- **Location:** `backend/payments/models.py:50-54` (`on_delete=CASCADE`); `backend/payments/views.py:18-21, 46-49`; `backend/core/viewsets.py:40-43`
- **Description:** `PaymentAllocation.receipt`/`.supplier_payment` FKs are `CASCADE`; deleting a receipt/payment with existing allocations silently deletes those allocations too, instantly making previously-paid invoices look unpaid again. The audit log only records "DELETE CustomerReceipt #N", not which allocations/invoices were affected. No business-rule check blocks this (contrast `Product.destroy()`, which checks `is_referenced()` first).
- **Impact:** Silent, retroactive corruption of the derived ledger — the exact invariant the README calls sacrosanct.
- **Remediation:** Change the FK to `PROTECT` (consistent with `sales_invoice`/`purchase_invoice` on the same model), and/or reject deletion when allocations exist, gated behind `CanCancelDocuments`.
- **Suggested test:** Create+allocate a receipt, delete it, assert rejection or correct resulting invoice outstanding + audit trail (no test exists today).
- **Status vs prior report:** NEW.

### BUG-312 — No idempotency guard on OPENING_STOCK postings (API and CSV import)
- **Severity:** Medium
- **Category:** Bug
- **Location:** `backend/inventory/views.py:77-96`; `backend/imports/services.py:183-191`
- **Description:** No check for "opening stock already recorded for this product" anywhere. Both the manual API and CSV importer will happily post a second `OPENING_STOCK` movement, additively inflating `on_hand` (e.g. re-submitting the same CSV, or double-clicking Save).
- **Remediation:** Enforce at most one `OPENING_STOCK` movement per `(company, product)`, or require explicit confirmation if one already exists.
- **Suggested test:** Call `OpeningStockView` twice for the same product; assert rejection/warning, not silent stacking.
- **Status vs prior report:** NEW.

### BUG-313 — Purchase-bill `update_master` feature is dead code (never reachable via the API)
- **Severity:** Medium
- **Category:** Bug
- **Location:** `backend/imports/services.py:369-383, 234-251, 296-316`
- **Description:** `_match_or_create_product` has logic to overwrite an existing product's price/GST/MRP "if `line.get("update_master")`" — but every place a preview line dict is built uses a fixed key set that never includes `update_master`, so the flag is always falsy in the actual commit path. Confirmed also by `test_purchase_bill_matches_existing_product` (asserts master price is never overwritten — consistent with an unreachable branch, not intentional disabling).
- **Impact:** Either dead code or a silently broken feature if the frontend believes it works.
- **Remediation:** Thread `update_master` through the line-dict construction if wanted, else delete the dead branch.
- **Status vs prior report:** NEW.

### BUG-314 — Auto-created suppliers from OCR text have no fuzzy dedup, risking fragmented ledgers
- **Severity:** Medium
- **Category:** Gap
- **Location:** `backend/imports/services.py:390-414`
- **Description:** When a bill import can't match an existing supplier by exact (case-insensitive) GSTIN/name, it silently creates a new `Supplier` from the LLM's extracted name — with no fuzzy/similarity matching to catch OCR spelling variance between bills from the same real supplier.
- **Impact:** Supplier master fills with near-duplicate entries over time, each fragmenting purchase/payment history; no merge tooling exists.
- **Remediation:** Surface a "possible match" list (trigram/Levenshtein similarity) in preview and require explicit confirmation before auto-creating.
- **Suggested test:** Feed two bills with slightly different but equivalent supplier names; assert only one `Supplier` results (currently would fail).
- **Status vs prior report:** NEW.

### BUG-315 — Products auto-created via purchase-bill import get `selling_price=0` with no surfaced warning
- **Severity:** Medium
- **Category:** Gap
- **Location:** `backend/imports/services.py:354-367`
- **Description:** New products are created with `selling_price=Decimal("0")` and nothing in the commit response flags this.
- **Impact:** If sold before the price is set (no other guard found preventing a zero-price sale), direct revenue loss.
- **Remediation:** Default to a configurable markup over purchase_price, or include a `products_needing_price` list in the commit response.
- **Status vs prior report:** NEW.

### BUG-316 — Raw exception text surfaced verbatim to `failure_reason` (info-disclosure risk)
- **Severity:** Medium
- **Category:** Bug
- **Location:** `backend/imports/tasks.py:62-65`; `backend/imports/services.py:264-269`
- **Description:** Broad `except Exception` calls `mark_failed(job, str(exc))`, truncated to 2000 chars, stored directly in a tenant-visible field. Confirmed via `test_purchase_bill_extraction_failure` that raw SDK exception text passes through unfiltered.
- **Impact:** Could leak internal request details (base URLs, model names, occasionally payload excerpts) to end users.
- **Remediation:** Map known exception types to sanitized user-facing messages; log full detail server-side only.
- **Status vs prior report:** NEW.

### BUG-317 — No duplicate-import prevention for CSV or purchase-bill re-uploads
- **Severity:** Medium
- **Category:** Gap
- **Location:** `backend/imports/services.py:148-204, 437-501`; `backend/imports/models.py`
- **Description:** No content-hash/dedup field on `ImportJob`. Re-uploading the same CSV creates a new job and unconditionally re-creates customers/products/opening-stock rows; re-uploading the same purchase-bill PDF produces a second draft purchase (no uniqueness on `supplier_bill_number`).
- **Impact:** An accidental double-submit (slow connection, anxious double-click) silently doubles customer/product/stock/purchase data.
- **Remediation:** Add a content-hash to `ImportJob`, warn/block on duplicate hash within a window; add uniqueness/duplicate-warning on `(company, supplier, supplier_bill_number)`.
- **Suggested test:** Upload+commit the same CSV twice; assert rejection or duplicate-count warning.
- **Status vs prior report:** NEW.

### BUG-318 — `ImportJob` has no index supporting its own default ordering/list query
- **Severity:** Low
- **Category:** Performance
- **Location:** `backend/imports/models.py:6-49`
- **Description:** No composite `(company, created_at)` index despite `Meta.ordering = ["-created_at"]` and company-filtered listing, unlike `CustomerReceipt`/`SupplierPayment` which have this pattern.
- **Remediation:** Add `models.Index(fields=["company", "-created_at"])`.
- **Status vs prior report:** NEW.

### BUG-319 — `can_view_financial_reports` defaults to `True` for every role
- **Severity:** Medium
- **Category:** Gap
- **Location:** `backend/accounts/models.py:109`; enforced by `CanViewFinancialReports` in `core/permissions.py:68-75`
- **Description:** Every other sensitive `CompanyUser` flag defaults `False` (`can_manage_inventory`, `can_import`, `can_cancel_documents`, `can_export`) but `can_view_financial_reports` defaults `True` — a freshly-added `SALES_STAFF` can view dashboard/receivables/payables/ledgers/registers (including implied margins) without the owner ever granting it.
- **Impact:** Retailers commonly don't want junior/counter staff seeing revenue/margins/who-owes-what; this silently grants that by default.
- **Remediation:** Default `False` like its siblings, or document as an intentional decision.
- **Status vs prior report:** NEW. (Directly relevant to area 06's BUG-624 — the frontend nav doesn't even hide the Reports section for these users.)

### BUG-320 — `Product.barcode` has no uniqueness constraint, causing ambiguous matches
- **Severity:** Medium
- **Category:** Bug
- **Location:** `backend/masters/models.py:94-136`; consumed at `backend/imports/services.py:342-345`, `backend/search/views.py:32-34`
- **Description:** Only `sku` gets a `UniqueConstraint`; `barcode` has none. Two products can share a barcode; `_match_or_create_product`'s `Q(sku__iexact=sku) | Q(barcode__iexact=sku)).first()` then picks an arbitrary one on ties, silently attaching a purchase-bill line or barcode-scan search to the wrong product.
- **Remediation:** Add `UniqueConstraint(fields=["company","barcode"], condition=~Q(barcode=""))`, backfill-cleaning duplicates first.
- **Suggested test:** Create two products with the same non-blank barcode in one company; currently succeeds — should be rejected.
- **Status vs prior report:** NEW.

### BUG-321 — Customer/Supplier masters have no duplicate-prevention (name/phone/GSTIN)
- **Severity:** Low
- **Category:** Gap
- **Location:** `backend/masters/models.py:52-92`
- **Description:** Unlike `Category`/`Brand`/`Unit`/`TaxRate` (all `unique_together`), `Customer`/`Supplier` have no uniqueness guard at all — not even on `gstin`, a legally unique identifier. Combined with BUG-317/314, duplicate party records are easy to accumulate.
- **Remediation:** Conditional unique constraint on `(company, gstin)` where non-blank; consider a soft duplicate-warning on `(company, phone)`.
- **Status vs prior report:** NEW.

### BUG-322 — Manual stock `ADJUSTMENT` bypasses the negative-stock policy entirely
- **Severity:** Medium
- **Category:** Bug
- **Location:** `backend/inventory/views.py:50-74`; `backend/inventory/services.py:22-30`
- **Description:** `check_negative_stock` is invoked before SALE and PURCHASE_RETURN movements but never for ADJUSTMENT — a user with `CanManageInventory` can post an arbitrarily large negative adjustment and drive `on_hand` deeply negative even under `BLOCK` policy.
- **Remediation:** Decide intended semantics — if adjustments should always be allowed, document the exception explicitly; if not, apply the same gate.
- **Status vs prior report:** NEW.

### BUG-323 — CSV export ignores the on-screen register filters; empty result omits CSV header
- **Severity:** Low
- **Category:** UI-Optimization
- **Location:** `backend/reporting/views.py:78-109`
- **Description:** `SalesRegisterView`/`PurchaseRegisterView` accept `customer`/`supplier`/`status` params, but the export lambdas only forward `date_from`/`date_to` — a filtered on-screen view exports unfiltered. Separately, a zero-row filtered export omits the CSV header entirely.
- **Remediation:** Thread all query params through to export; always emit a header row using known field names.
- **Status vs prior report:** NEW. (Directly relevant to area 06's BUG-616, found independently on the frontend side.)

### BUG-324 — Test-coverage gaps (consolidated)
- **Severity:** Medium
- **Category:** Test-Coverage
- **Description:** No concurrency test for payment allocation (BUG-308) or stock oversell (BUG-309); no test blocking a non-owner from deleting a receipt/payment/allocation (BUG-310/311); no cross-tenant test for the allocation endpoint itself; no duplicate-import test (BUG-317); no direct assertion of `is_advance`/`unallocated` correctness (BUG-304).
- **Status vs prior report:** NEW.

---

## Summary of most severe systemic issues

1. **Concurrency is an afterthought around money and stock.** `allocate_receipt`/`allocate_supplier_payment` (BUG-308) and the sales-completion negative-stock check (BUG-309, = BUG-222 in area 02) both make an authorization decision from an unlocked read and only lock (if at all) after the decision is made — classic TOCTOU races. `DocumentNumberService` shows the team knows how to do this correctly; the pattern simply wasn't applied to payments/inventory.
2. **Deletion of money-adjacent records is under-governed.** `PaymentAllocationViewSet` and receipt/payment viewsets expose `DELETE` gated only by `HasCompany` (BUG-310/311), with cascading deletes that silently unwind payment history and no `CanCancelDocuments`-style permission or itemized audit trail.
3. **The purchase-bill LLM import trusts its own output more than it should.** Auto-created suppliers/products have no dedup (BUG-314/315/320), a whole safety-valve feature is unreachable dead code (BUG-313), raw exception text reaches end users (BUG-316), and there's no protection against re-importing the same document (BUG-317).

Of the original claims: **BUG-013 and BUG-017 are inaccurate as stated** (the real N+1 is in `ledgers/views.py`, not `reporting`; the purchase/sales outstanding math is actually consistent), and **BUG-018 is already fixed** on the backend (frontend doesn't surface it — see area 06). The LLM-timeout and search-index performance concerns are confirmed.
