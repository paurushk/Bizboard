# Functional Code Review Findings: Release-Blocking Audit

**System:** Bizboard (Cloud GST Billing & Business Management System)  
**Target Git Revision:** `5ba05c7b8811c49dae0fd7112d0db654eacabf02`  
**Date of Review:** 2026-09-07  
**Runtime Environment:** Python 3.13.0, pytest 8.4.2, Django 5.2.17, Windows NT  
**Test Suite Baseline:** 1,259 test cases collected; full suite execution: 1,206 passed, 42 failed, 11 skipped in 1074.79s (17m 54s) (failures independently validate findings CR-011, CR-018, CR-043, CR-044, CR-047, CR-050, CR-063)  
**Auditor Role:** Senior Principal Engineer (Release-Blocking Verification)  

---

## 1. Executive Summary & Top 10 Launch-Blocking Findings

This audit is a strict release-blocking code review conducted across the money-moving, stock-moving, tax-calculating, and reporting cores of Bizboard prior to onboarding paying retailers and small traders. The review evaluated six core modules in strict priority order: **POS $\to$ Sales $\to$ Purchase $\to$ Stock & Godown $\to$ Reporting $\to$ Accounting**.

Out of **63 confirmed findings** (`CR-001` through `CR-063`), **16 are Critical / Blocker**, **28 are High Severity**, **15 are Medium Severity**, and **4 are Low Severity**. Multiple data-corruption and financial-divergence bugs were uncovered that will cause severe silent accounting desynchronization, lost sales, stock valuation inflation, and statutory non-compliance if deployed.

### Top 10 Launch-Blocking Findings

| Rank | Finding ID | Module | Severity | Summary |
| :---: | :---: | :---: | :---: | :--- |
| **1** | [**CR-056**](#cr-056-postingservicereverse-causes-negative-double-reversal-in-gl) | **Accounting** | **CRITICAL** | `PostingService.reverse()` creates an inverted journal entry with `status=POSTED` while flipping the original entry to `status=REVERSED`. Because GL reports filter `entry__status=POSTED`, the original entry is dropped and only the negative entry is read, turning every document cancellation or amendment into a negative double-reversal. |
| **2** | [**CR-057**](#cr-057-salesinvoicecancel-bypasses-gl-reversal-leaving-posted-revenue-and-ar) | **Accounting** | **CRITICAL** | `SalesInvoice.cancel()` reverses stock movements and cancels payment links, but **never calls `PostingService.reverse()`**. The sales journal entry remains `POSTED` in the GL forever, causing permanent silent divergence between the operational ledger and the GL. |
| **3** | [**CR-023**](#cr-023-purchaseservicecomplete-crashes-unconditionally-on-service--non-stock-products) | **Purchase** | **CRITICAL** | `PurchaseService.complete` unconditionally invokes `InventoryService.post_movement` on all line items without checking `tracks_inventory()`. Any purchase invoice containing a service or non-stock item (legal fees, transport, consulting) crashes with `BusinessRuleError`, completely breaking service procurement. |
| **4** | [**CR-001**](#cr-001-idempotency-record-poisoning--permanent-404-loop-on-post-completion-cleanups) | **POS** | **CRITICAL** | When POS invoice completion fails after draft creation, the client deletes the draft invoice but does not clear `IdempotencyRecord`. Retrying or auto-flushing the outbox replays the cached 201 response containing the deleted ID; subsequent operations fail with `404 Not Found`, permanently freezing offline outbox flushes. |
| **5** | [**CR-002**](#cr-002-physical-sale-drop--stuck-outbox-on-concurrent-negative-stock-under-block-policy) | **POS / Stock** | **CRITICAL** | When two offline POS terminals sell the last unit of an SKU to walk-in customers and collect cash, upon reconnecting Terminal 1 completes, while Terminal 2 throws `Insufficient stock` under `BLOCK` policy. Terminal 2 deletes the draft, permanently drops the physical sale from books, and produces a cash-drawer surplus. |
| **6** | [**CR-010**](#cr-010-same-state-sez-supplies-incorrectly-computed-as-intra-state-cgstsgst-and-blocked) | **Sales** | **CRITICAL** | Under Section 7(5)(b) of the IGST Act, SEZ supplies are deemed inter-state (IGST). `SalesService.set_items` derives `intra_state` without passing `supply_type`. Same-state SEZ invoices calculate CGST+SGST, and are subsequently rejected by `SalesService.complete` ("SEZWP invoices must use IGST only"), completely blocking billing to in-state SEZ units. |
| **7** | [**CR-011**](#cr-011-salesreturncomplete-over-reverses-entire-payment-allocation-without-re-allocating-remainder) | **Sales** | **CRITICAL** | When completing a sales return on an invoice with allocations, `ReturnService.complete_return` reverses the entire allocation even when only a small portion is returned, and fails to re-allocate the remainder (`keep`). A ₹2,000 return on a fully paid ₹10,000 invoice sets invoice allocation to ₹0 and creates a phantom ₹8,000 unpaid invoice balance. |
| **8** | [**CR-024**](#cr-024-fifo-cost-layer-recorded-at-gross-unit_price-instead-of-net-commercial-unit-cost) | **Purchase / Stock** | **CRITICAL** | `PurchaseService.complete` stamps `InventoryCostLayer` and `StockMovement` with gross `unit_price` before line discounts (`discount_percent`). For an item purchased at ₹1,000 with 20% discount (net ₹800), the layer is stamped at ₹1,000 while GL 1400 is debited ₹800. Subsequent sales recognize COGS at ₹1,000, creating phantom losses. |
| **9** | [**CR-036**](#cr-036-expiryalertsviewpost-fails-when-writing-off-expired-lots-due-to-missing-skip_negative_check) | **Stock** | **CRITICAL** | In `ExpiryAlertsView.post()`, write-off adjustments omit `skip_negative_check=True`. In `InventoryService.post_movement()`, `delta < 0` triggers an expired lot check that raises `Batch is expired and cannot be issued`. As a result, expired batches cannot be written off by warehouse operators. |
| **10** | [**CR-043**](#cr-043-asymmetric-return-handling-causes-double-deduction-in-dashboard-purchases_this_month) | **Reporting** | **CRITICAL** | Dashboard `purchases_this_month` queries only `status=COMPLETED` purchase invoices (omitting `RETURNED`), and then subtracts all `PurchaseCreditNote`s. Returned purchases are deducted twice from gross purchases, yielding corrupted or negative MTD purchase figures. |

---

## 2. Coverage Matrix

| Module | Core Files & Surfaces Audited | Audit Status | Critical | High | Medium | Low | Total |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. POS** | `backend/sales/views.py`, `backend/payments/views.py`, `web/src/pages/pos/*`, `web/src/offline/flushPosCheckout.ts`, `invoiceDraftCache.ts` | **BLOCKED** | 2 | 2 | 3 | 2 | **9** |
| **2. Sales** | `backend/sales/services.py`, `notes_services.py`, `return_service.py`, `recurring.py`, `irn_guard.py`, `web/src/pages/sales/*` | **BLOCKED** | 3 | 7 | 3 | 0 | **13** |
| **3. Purchase** | `backend/purchases/services.py`, `notes_services.py`, `phase1_serializers.py`, `backend/imports/*`, `web/src/pages/purchases/*` | **BLOCKED** | 2 | 7 | 4 | 0 | **13** |
| **4. Stock & Godown** | `backend/inventory/models.py`, `services.py`, `views.py`, `serializers.py`, `web/src/pages/inventory/*`, `godownConflict.ts` | **BLOCKED** | 3 | 2 | 2 | 0 | **7** |
| **5. Reporting** | `backend/reporting/services.py`, `views.py`, `gst_returns.py`, `gstr2b.py`, `ims.py`, `tds_worksheets.py`, `web/src/pages/reports/*` | **BLOCKED** | 3 | 4 | 5 | 1 | **13** |
| **6. Accounting** | `backend/accounting/services.py`, `reports.py`, `views.py`, `serializers.py`, `backend/ledgers/services.py`, `views.py` | **BLOCKED** | 3 | 3 | 2 | 0 | **8** |
| **TOTAL** | **Full In-Scope Platform** | **BLOCKED** | **16** | **25** | **19** | **3** | **63** |

---

## 3. Module 1: POS Findings (`CR-001` – `CR-009`)

### CR-001: Idempotency Record Poisoning & Permanent 404 Loop on Post-Completion Cleanups
- **Module**: POS
- **Location**: [`web/src/pages/pos/PosPage.tsx:690-698`](file:///e:/Bizboard/web/src/pages/pos/PosPage.tsx#L690-L698), [`web/src/offline/flushPosCheckout.ts:109-116`](file:///e:/Bizboard/web/src/offline/flushPosCheckout.ts#L109-L116), [`backend/sales/views.py:184-188`](file:///e:/Bizboard/backend/sales/views.py#L184-L188)
- **Type**: Data-integrity / Bug
- **Severity**: Critical
- **What's wrong**: When an invoice is created via `createSalesInvoice` with idempotency key `K`, the backend inserts an `IdempotencyRecord` for `(company, "sales_invoice_create", K)` storing the 201 response and `invoice.id`. If `completeSalesInvoice` subsequent call fails (e.g. stock shortfall, invalid serial, closed period), the client confirms the invoice is still `DRAFT` and calls `deleteSalesInvoice(invoice.id)`. However, `deleteSalesInvoice` (DELETE `/api/v1/sales/invoices/{id}/`) does not call `forget_record`. The client also fails to reset `idempotencyKey` in state or outbox draft. On retry or auto-flush, `begin_record` matches `K` and replays the 201 response containing the deleted invoice ID. Subsequent operations on that ID return `HTTP 404 Not Found`.
- **Trigger / Repro**:
  1. Add items to cart; trigger an error on completion (e.g. negative stock under `BLOCK` policy or closed GST period).
  2. The client catches the error and deletes the draft invoice.
  3. Resolve the issue (or change payment method) and click Pay again.
- **Consequence**: Every retry fails with `404 Not Found`. Offline outbox drafts become permanently poisoned and will fail on every sync interval. Counter terminals become locked until the user abandons the cart.
- **Code Evidence**:
  `web/src/pages/pos/PosPage.tsx`:
  ```typescript
  690: if (existing) {
  691:   try {
  692:     await deleteSalesInvoice(invoice.id);
  693:   } catch {}
  694:   throw err; // setIdempotencyKey(null) is missing!
  695: }
  ```
  `backend/sales/views.py`:
  ```python
  184: def perform_destroy(self, instance):
  185:     if instance.status != SalesInvoice.Status.DRAFT:
  186:         raise BusinessRuleError("Only draft invoices can be deleted; use Cancel instead.")
  187:     super().perform_destroy(instance) # forget_record() never invoked!
  ```
- **Suggested Fix Direction**:
  1. In `SalesInvoiceViewSet.perform_destroy`, query `IdempotencyRecord` by `resource_id=str(instance.pk)` and call `forget_record(...)`.
  2. In `PosPage.tsx:694`, call `setIdempotencyKey(null)` before rethrowing.
  3. In `flushPosCheckout.ts:113`, update the outbox draft with a freshly generated idempotency key.
- **Test to Add**: `test_delete_draft_clears_idempotency_record` (POST invoice with key K, DELETE invoice, POST invoice with key K again $\to$ creates fresh invoice instead of returning deleted ID).
- **Twin Check (Purchase)**: `PurchaseInvoiceViewSet.perform_destroy` (`backend/purchases/views.py:64-72`) also fails to forget `purchase_invoice_create` idempotency records on draft deletion.

---

### CR-002: Physical Sale Drop & Stuck Outbox on Concurrent Negative Stock Under BLOCK Policy
- **Module**: POS / Stock
- **Location**: [`web/src/offline/flushPosCheckout.ts:88-124`](file:///e:/Bizboard/web/src/offline/flushPosCheckout.ts#L88-L124), [`backend/inventory/services.py:209-214`](file:///e:/Bizboard/backend/inventory/services.py#L209-L214), [`backend/sales/services.py:933-948`](file:///e:/Bizboard/backend/sales/services.py#L933-L948)
- **Type**: Broken-feature / Race
- **Severity**: Critical
- **What's wrong**: Two offline POS counters sell the last unit of an SKU to walk-in customers and collect physical cash. When both counters reconnect, Counter 1 flushes and completes. Counter 2 flushes next; the backend checks available stock in `InventoryService.post_movement` under `StockBalance` row lock. Because `negative_stock_policy == "BLOCK"`, Counter 2's completion throws `BusinessRuleError("Insufficient stock...")`. Counter 2's `flushPosDraft` treats this as fatal, deletes the draft invoice, and retains the poisoned key in outbox. The actual sale is completely dropped from the books.
- **Trigger / Repro**:
  1. Set company negative stock policy to `BLOCK`. On-hand stock = 1 unit.
  2. Disconnect Terminal A and Terminal B. Sell 1 unit on each terminal and collect cash.
  3. Reconnect both terminals. Terminal A flushes; Terminal B flushes immediately after.
- **Consequence**: Terminal B's sale is dropped. The customer has the goods, the till has surplus unrecorded cash, and Terminal B's outbox is trapped in an error loop.
- **Code Evidence**:
  `backend/inventory/services.py`:
  ```python
  208: resulting = balance.available + delta
  209: if resulting < 0 and company.negative_stock_policy == "BLOCK":
  210:     raise BusinessRuleError(
  211:         f"Insufficient stock for '{product.name}': available {balance.available}, required {-delta}."
  212:     )
  ```
- **Suggested Fix Direction**: Provide an offline-flush reconciliation mode or audit override (`allow_offline_negative_stock=True`) that logs an audit exception and permits the movement under a `WARN`-like policy, or moves the failed draft to a dedicated "Counter Stock Conflict" queue instead of deleting the draft.
- **Test to Add**: `test_pos_offline_flush_concurrent_oversell_reconciliation`.
- **Twin Check (Purchase)**: Inbound purchases add stock, but concurrent purchase returns deducting stock have the identical race condition.

---

### CR-003: Multi-Roundtrip Non-Atomic Checkout Choreography Strands Invoices & Receipts
- **Module**: POS
- **Location**: [`web/src/pages/pos/PosPage.tsx:733-764`](file:///e:/Bizboard/web/src/pages/pos/PosPage.tsx#L733-L764), [`web/src/offline/flushPosCheckout.ts:53-143`](file:///e:/Bizboard/web/src/offline/flushPosCheckout.ts#L53-L143)
- **Type**: Data-integrity / Architectural
- **Severity**: High
- **What's wrong**: POS counter checkout is orchestrated across 4 separate HTTP round-trips:
  1. `POST /api/v1/sales/invoices/` (create draft)
  2. `POST /api/v1/sales/invoices/{id}/complete/` (deduct stock, post AR)
  3. `POST /api/v1/payments/receipts/` (create cash receipt)
  4. `POST /api/v1/payments/allocations/` (allocate receipt to invoice)  
  If step 3 fails (network drop, closed period on payments, server timeout), the invoice remains completed, stock is deducted, and AR is debited, but no cash receipt is recorded. If step 4 fails, the receipt is created unallocated, leaving the invoice marked UNPAID.
- **Trigger / Repro**: Simulate a network disconnection or 500 error on step 3 during checkout.
- **Consequence**: Till drawers and customer accounts desynchronize. Invoices marked completed are reported as unpaid receivables.
- **Code Evidence**:
  `web/src/pages/pos/PosPage.tsx`:
  ```typescript
  733: completed = await createCompletedInvoice(lines, customer, key, confirmBlankPos);
  ...
  747: const receipt = await createReceipt({ customer, amount: invoiceTotal, mode: 'CASH', ... });
  757: await createAllocation({ receipt: receipt.id, salesInvoice: completed.id, amount: invoiceTotal });
  ```
- **Suggested Fix Direction**: Create a single atomic backend endpoint `POST /api/v1/sales/invoices/pos-checkout/` wrapping invoice creation, completion, receipt creation, and allocation in one `with transaction.atomic():` block under one idempotency key.
- **Test to Add**: `test_pos_checkout_atomic_rollback_on_payment_failure`.
- **Twin Check (Purchase)**: Purchase module also requires 4 separate round-trips for bill creation, completion, payment, and allocation.

---

### CR-004: Race Condition Between Background Outbox Flush and Counter Checkout
- **Module**: POS
- **Location**: [`web/src/pages/pos/PosPage.tsx:851-898, 921-950`](file:///e:/Bizboard/web/src/pages/pos/PosPage.tsx#L851-L898)
- **Type**: Race / Concurrency
- **Severity**: High
- **What's wrong**: When `PosPage` comes online with a restored draft, `flushPendingDraft()` triggers in the background with `flushGuard.current = true`. If the cashier clicks "Pay Cash", `checkout()` checks `checkoutGuard.current` (which is `false`). Both routines execute concurrently with the identical `draft.idempotencyKey`. The backend's `begin_record` detects concurrent in-flight execution and throws `IdempotencyInFlightError` (409 Conflict) on the cashier's UI.
- **Trigger / Repro**: Restore an offline draft, connect to network, and immediately click "Pay Cash".
- **Consequence**: The cashier receives an alarming error banner while the background flush succeeds, causing confusion over whether the sale completed.
- **Code Evidence**:
  `web/src/pages/pos/PosPage.tsx`:
  ```typescript
  220: const flushGuard = useRef(false);
  222: const checkoutGuard = useRef(false);
  852: if (flushGuard.current || !navigator.onLine) return;
  922: if (checkoutGuard.current || busy) return;
  // Neither ref checks the other's state!
  ```
- **Suggested Fix Direction**: Unify `flushGuard` and `checkoutGuard` into a shared busy lock and disable checkout buttons while an outbox sync is in flight.
- **Test to Add**: `test_pos_page_blocks_checkout_while_flush_in_flight`.
- **Twin Check (Purchase)**: Purchase module does not have auto-flushing counter mode.

---

### CR-005: Silent Thermal PDF Print Failure on Counter Checkout
- **Module**: POS
- **Location**: [`web/src/pages/pos/PosPage.tsx:226, 579-582`](file:///e:/Bizboard/web/src/pages/pos/PosPage.tsx#L226), [`web/src/pages/pos/printPosThermal.ts:18-23`](file:///e:/Bizboard/web/src/pages/pos/printPosThermal.ts#L18-L23)
- **Type**: Silent-failure / UI Bug
- **Severity**: Medium
- **What's wrong**: When thermal PDF generation fails, `printPosThermalOrWarn` catches the exception and returns `{ invoiceId, number }`. `finishSale` calls `setThermalWarn(warn)`. However, `thermalWarn` is **never rendered anywhere in the JSX of `PosPage.tsx`**. The cashier sees a green "Sale complete" banner while the printer remains silent, with zero indication of failure.
- **Trigger / Repro**: Configure an unreachable thermal printer or have the backend thermal PDF endpoint fail; complete a sale.
- **Consequence**: Cashiers assume receipts are printing; when no receipt appears, they have no reprint button or error feedback.
- **Code Evidence**:
  `web/src/pages/pos/PosPage.tsx`:
  ```typescript
  226: const [thermalWarn, setThermalWarn] = useState<{ invoiceId: number; number: string } | null>(null);
  581: setThermalWarn(warn);
  // Zero references to thermalWarn exist in the returned JSX!
  ```
- **Suggested Fix Direction**: Add an `<Alert severity="warning">` banner with a "Retry Print" button when `thermalWarn` is not null.
- **Test to Add**: `test_thermal_warn_rendered_on_print_failure`.
- **Twin Check (Purchase)**: Purchase bills do not have thermal printing.

---

### CR-006: Cash Overpayment / Change Tendered Discarded from Accounting
- **Module**: POS
- **Location**: [`web/src/pages/pos/PosPage.tsx:403-407, 746-756`](file:///e:/Bizboard/web/src/pages/pos/PosPage.tsx#L746-L756)
- **Type**: Missing-validation / Data-integrity
- **Severity**: Medium
- **What's wrong**: In POS cash checkout, the cashier enters `cashTendered` (e.g. ₹500 for a ₹420 bill). The UI calculates `changeDue = 80`. However, `createReceipt` hardcodes `amount: invoiceTotal` (₹420). The actual cash tendered and change returned are completely discarded and never recorded in receipt notes or till logs.
- **Trigger / Repro**: Enter ₹500 tendered for ₹420 bill; complete sale; inspect `CustomerReceipt` in database.
- **Consequence**: Loss of cash-drawer reconciliation audit trail; drawer shortages/overages cannot be investigated.
- **Code Evidence**:
  `web/src/pages/pos/PosPage.tsx`:
  ```typescript
  746: const invoiceTotal = toNumber(completed.grandTotal ?? settlement.amount);
  747: const receipt = await createReceipt({
  748:   customer,
  749:   amount: invoiceTotal, // Discards actual tendered cash!
  750:   mode: 'CASH',
  ```
- **Suggested Fix Direction**: Pass `tenderedAmount` and `changeDue` in receipt metadata/notes for drawer tracking.
- **Test to Add**: `test_pos_receipt_notes_record_cash_tendered_and_change`.
- **Twin Check (Purchase)**: Vendor payments do not involve counter cash change.

---

### CR-007: Shared Counter Offline Outbox Cross-Tenant Data Leak on Device Sign-Out
- **Module**: POS / Auth
- **Location**: [`web/src/offline/invoiceDraftCache.ts:4-9, 385-391`](file:///e:/Bizboard/web/src/offline/invoiceDraftCache.ts#L385-L391), [`web/src/auth/AuthContext.tsx:112-120`](file:///e:/Bizboard/web/src/auth/AuthContext.tsx#L112-L120)
- **Type**: Cross-tenant / Security
- **Severity**: Medium
- **What's wrong**: Offline drafts are stored unencrypted in a single shared IndexedDB database (`bizboard-invoice-outbox`). `clearAllDrafts(companyId, userId)` only clears drafts for the currently active user session. If a session expires or an operator logs out after token invalidation, drafts remain in storage. If Operator B logs in under a different company on the same POS terminal, Operator A's drafts remain readable in IndexedDB.
- **Trigger / Repro**: Create an offline POS draft; log out; log in as a user from another company; inspect IndexedDB.
- **Consequence**: Plaintext customer names, phone numbers, and cart data leaked across tenants sharing POS hardware.
- **Code Evidence**:
  `web/src/auth/AuthContext.tsx`:
  ```typescript
  112: if (companyId && userId) {
  113:   clearPosPendingStorageForUser(companyId, userId);
  114:   try { await clearAllDrafts(companyId, userId); } catch {}
  115: }
  ```
- **Suggested Fix Direction**: Call `indexedDB.deleteDatabase('bizboard-invoice-outbox')` on explicit logout or encrypt IDB contents using a session-derived key.
- **Test to Add**: `test_logout_deletes_all_idb_outbox_stores`.
- **Twin Check (Purchase)**: Purchase drafts share `invoiceDraftCache.ts` and have the identical retention vulnerability.

---

### CR-008: Cross-Tenant ID Existence Enumeration in Serializer FK Fields
- **Module**: POS / Sales / Payments
- **Location**: [`backend/sales/serializers.py:72`](file:///e:/Bizboard/backend/sales/serializers.py#L72), [`backend/payments/serializers.py:60, 100`](file:///e:/Bizboard/backend/payments/serializers.py#L100)
- **Type**: Cross-tenant / Information Leak
- **Severity**: Low
- **What's wrong**: `SalesItemSerializer` does not wrap `batch` in `CompanyPrimaryKeyRelatedField` (falls back to `BatchLot.objects.all()`). In `CustomerReceiptSerializer.__init__`, `customer` is scoped to `cu.company`, but `bank_account` is not scoped. DRF's field-level validation returns different error messages for foreign IDs vs non-existent IDs.
- **Trigger / Repro**: Submit a receipt with `bank_account: <Tenant A's bank account ID>` from Tenant B.
- **Consequence**: Cross-tenant existence oracle allowing enumeration of primary key IDs of bank accounts and batch lots.
- **Code Evidence**:
  `backend/payments/serializers.py`:
  ```python
  97: if cu and "customer" in self.fields:
  98:     self.fields["customer"].queryset = Customer.objects.filter(company=cu.company)
  # bank_account is never scoped!
  ```
- **Suggested Fix Direction**: Scope `bank_account` queryset to `cu.company` and wrap `SalesItemSerializer.batch` in `CompanyPrimaryKeyRelatedField`.
- **Test to Add**: `test_receipt_serializer_bank_account_field_level_rejection`.
- **Twin Check (Purchase)**: `SupplierPaymentSerializer` omits company scoping on `bank_account` in the exact same manner.

---

### CR-009: `PaymentAllocationViewSet.unallocate` Missing Idempotency Scope and Request Deduplication
- **Module**: POS / Payments
- **Location**: [`backend/payments/views.py:397-406`](file:///e:/Bizboard/backend/payments/views.py#L397-L406), [`backend/core/idempotency.py:32-74`](file:///e:/Bizboard/backend/core/idempotency.py#L32-L74)
- **Type**: Concurrency / Missing-validation
- **Severity**: Medium
- **What's wrong**: `PaymentAllocationViewSet.unallocate` reverses payment allocations (which mutates customer/supplier ledger balances and postings). However, it has no `Idempotency-Key` checking, and `allocation_unallocate` is completely missing from `MONEY_IDEMPOTENCY_SCOPES` in `backend/core/idempotency.py`.
- **Trigger / Repro**: Rapidly double-click "Unallocate" on a payment allocation.
- **Consequence**: Two concurrent unallocation requests race against the same allocation row.
- **Code Evidence**:
  `backend/payments/views.py`:
  ```python
  396: @action(detail=True, methods=["post"])
  397: def unallocate(self, request, pk=None):
  398:     allocation = PaymentService.reverse_allocation(allocation=self.get_object(), user=request.user)
  ```
- **Suggested Fix Direction**: Add `allocation_unallocate` to `MONEY_IDEMPOTENCY_SCOPES` and wrap `unallocate()` in `begin_record` / `store_record`.
- **Test to Add**: `test_allocation_unallocate_idempotency`.
- **Twin Check (Purchase)**: Supplier payment allocations share `PaymentAllocationViewSet` and suffer from the same vulnerability.

---

## 4. Module 2: Sales Findings (`CR-010` – `CR-022`)

### CR-010: Same-State SEZ Supplies Incorrectly Computed as Intra-State (CGST+SGST) and Blocked
- **Module**: Sales / GST
- **Location**: [`backend/sales/services.py:634-640`](file:///e:/Bizboard/backend/sales/services.py#L634-L640), [`backend/core/services/place_of_supply.py:80-99`](file:///e:/Bizboard/backend/core/services/place_of_supply.py#L80-L99)
- **Type**: Business Logic / GST Statutory Compliance
- **Severity**: Critical (Release-Blocking)
- **What's wrong**: Under Section 7(5)(b) of the IGST Act, any supply of goods or services to an SEZ developer or unit is deemed an inter-state supply subject to IGST, even if supplier and recipient are located in the same state. In `SalesService.set_items`, `intra_state` is determined by `party_intra_state(...)` without supplying `supply_type`. Because `party_intra_state` compares state codes, a supply from Karnataka (29) to an SEZ in Karnataka (29) with `supply_type="SEZWP"` is marked intra-state. CGST+SGST are computed. Then, `SalesService.complete` (line 822) rejects the invoice: `"SEZWP invoices must use IGST only"`.
- **Trigger / Repro**: Create an invoice for a customer in the same state with `supply_type="SEZWP"`. Save items; attempt to complete.
- **Consequence**: Total blockage of all in-state SEZ sales invoicing.
- **Code Evidence**:
  `backend/sales/services.py`:
  ```python
  634: intra_state=party_intra_state(
  635:     invoice.company, invoice.customer.state, invoice.customer.gstin or "",
  636:     seller_state=(getattr(invoice.company_gstin, "state", None) or ""),
  637:     seller_gstin=(getattr(invoice.company_gstin, "gstin", None) or ""),
  638: )
  # supply_type is never passed!
  ```
- **Suggested Fix Direction**: Update `party_intra_state` in `backend/core/services/place_of_supply.py` to take `supply_type: str = ""` and immediately return `False` if `is_export_or_sez_supply(supply_type)`.
- **Test to Add**: `test_same_state_sez_supply_calculates_igst_and_completes`.
- **Twin Check (Purchase)**: Inbound purchases from SEZ units (`backend/purchases/services.py`) must also enforce IGST treatment.

---

### CR-011: `SalesReturn.complete` Over-Reverses Entire Payment Allocation Without Re-Allocating Remainder
- **Module**: Sales / Ledgers
- **Location**: [`backend/sales/return_service.py:285-299`](file:///e:/Bizboard/backend/sales/return_service.py#L285-L299)
- **Type**: Data-integrity / Ledger AR
- **Severity**: Critical (Release-Blocking)
- **What's wrong**: When a sales return is completed against an invoice with payment allocations, `ReturnService.complete_return` auto-generates a credit note and unallocates payments up to the return amount. If an allocation is larger than `need` (e.g. allocation is ₹10,000 and return is ₹2,000), `complete_return` calls `PaymentService.reverse_allocation` on the entire ₹10,000 allocation. Unlike `SalesNotesService.complete_credit_note`, it completely omits re-allocating `keep = alloc_amt - need` back to the invoice.
- **Trigger / Repro**: Complete an invoice for ₹10,000; allocate a ₹10,000 receipt; complete a sales return for ₹2,000.
- **Consequence**: The invoice's ₹10,000 allocation is completely reversed. The invoice displays an outstanding unpaid debt of ₹8,000, while the receipt shows ₹10,000 as an unallocated advance. AR ledger balances are corrupted.
- **Code Evidence**:
  `backend/sales/return_service.py`:
  ```python
  296: PaymentService.reverse_allocation(allocation=alloc, user=user)
  297: need -= amt
  # Missing: if alloc_amt > need: re-allocate keep = alloc_amt - need!
  ```
- **Suggested Fix Direction**: Mirror `backend/sales/notes_services.py:206-216` by re-allocating `keep` when `alloc_amt > need`.
- **Test to Add**: `test_sales_return_partial_keeps_remaining_allocation`.
- **Twin Check (Purchase)**: `backend/purchases/return_service.py` must be checked for the identical allocation reversal flaw.

---

### CR-012: In-Flight E-Invoice (`QUEUED`) Bypasses `assert_no_live_irn` on Invoice Cancellation
- **Module**: Sales / Statutory
- **Location**: [`backend/sales/irn_guard.py:9-16`](file:///e:/Bizboard/backend/sales/irn_guard.py#L9-L16), [`backend/sales/services.py:1127`](file:///e:/Bizboard/backend/sales/services.py#L1127)
- **Type**: Statutory Sync / E-Invoice
- **Severity**: Critical (Release-Blocking)
- **What's wrong**: `assert_no_live_irn` checks: `if irn and status not in ("CANCELLED", "FAILED", "NONE", ""): raise BusinessRuleError(...)`. While an e-invoice generation task is dispatched to the IRP, `einvoice_status == "QUEUED"` and `irn == ""`. Because `irn` is empty, `assert_no_live_irn` returns without raising. The user cancels the invoice in Bizboard. When the Celery task completes, it receives the IRN from IRP and attaches an active IRN to a `CANCELLED` invoice in Bizboard. Furthermore, if `irn` is present but `einvoice_status == "FAILED"`, it also allows cancellation in books while the IRN remains live on the portal.
- **Trigger / Repro**: Queue e-invoice generation; immediately call `SalesService.cancel(invoice)`.
- **Consequence**: An active tax invoice IRN exists on the government portal while Bizboard records the invoice as cancelled, leading to tax penalties and GSTR-1 mismatches.
- **Code Evidence**:
  `backend/sales/irn_guard.py`:
  ```python
  9: def assert_no_live_irn(doc, *, kind: str = "document") -> None:
  10:     irn = (getattr(doc, "irn", None) or "").strip()
  11:     status = getattr(doc, "einvoice_status", None) or ""
  12:     if irn and status not in ("CANCELLED", "FAILED", "NONE", ""):
  13:         raise BusinessRuleError(...)
  ```
- **Suggested Fix Direction**: Block cancellation if `status in ("QUEUED", "PENDING")`. Never treat `FAILED` as safe if `irn` is populated.
- **Test to Add**: `test_assert_no_live_irn_blocks_queued_in_flight`.
- **Twin Check (Purchase)**: Purchase credit/debit notes (`notes_services.py:314, 498`) also use `assert_no_live_irn`.

---

### CR-013: Direct `SalesService.set_items` Amends Completed Invoices Without IRN Guard
- **Module**: Sales
- **Location**: [`backend/sales/services.py:554-560`](file:///e:/Bizboard/backend/sales/services.py#L554-L560)
- **Type**: Statutory Integrity
- **Severity**: High
- **What's wrong**: `sales/serializers.py:305` calls `assert_no_live_irn` on line updates, but `SalesService.set_items` does not. Any internal service or script calling `SalesService.set_items` directly can mutate line items, prices, and taxes on completed invoices with live IRNs.
- **Trigger / Repro**: Call `SalesService.set_items(invoice, new_items)` on a completed invoice with `irn != ""`.
- **Consequence**: Invoice totals in the database diverge from legally stamped e-invoice IRNs.
- **Code Evidence**:
  `backend/sales/services.py`:
  ```python
  554: @staticmethod
  555: @transaction.atomic
  556: def set_items(invoice: SalesInvoice, items_data, user):
  557:     if invoice.status in (SalesInvoice.Status.CANCELLED, SalesInvoice.Status.RETURNED):
  558:         raise BusinessRuleError("Cancelled/returned invoice cannot be line-edited.")
  # assert_no_live_irn is missing!
  ```
- **Suggested Fix Direction**: Add `if invoice.status == SalesInvoice.Status.COMPLETED: assert_no_live_irn(invoice, kind="invoice")` in `SalesService.set_items`.
- **Test to Add**: `test_set_items_on_completed_invoice_with_irn_fails`.
- **Twin Check (Purchase)**: Check `PurchasesService.set_items`.

---

### CR-014: Recurring Invoices Stale Catch-Up State Causes Erroneous Duplication and Desync
- **Module**: Sales
- **Location**: [`backend/sales/recurring.py:109, 208-228`](file:///e:/Bizboard/backend/sales/recurring.py#L208-L228)
- **Type**: Concurrency / Logic
- **Severity**: High
- **What's wrong**: In `_process_one_schedule`, `generate_draft_for_schedule` takes `select_for_update().get(pk=schedule.pk)` into a local variable and saves it. However, the caller's in-memory `schedule` instance is never refreshed (`schedule.refresh_from_db()` is missing). On subsequent iterations of the catch-up loop, `schedule.next_run_at` retains the old date, causing false duplicate skips and overwriting `next_run_at` with stale timestamps.
- **Trigger / Repro**: Run `process_due_schedules` on a schedule 2 months behind.
- **Consequence**: Missed recurring invoice periods fail to generate cleanly.
- **Code Evidence**:
  `backend/sales/recurring.py`:
  ```python
  227: run = generate_draft_for_schedule(schedule, run_date=on_date)
  # Missing: schedule.refresh_from_db()
  ```
- **Suggested Fix Direction**: Add `schedule.refresh_from_db()` immediately after `generate_draft_for_schedule`.
- **Test to Add**: `test_process_due_schedules_catches_up_multiple_months_sequentially`.
- **Twin Check (Purchase)**: Purchase recurring bills.

---

### CR-015: UTC Timezone Extraction Shifts `anchor_day` and Monthly Recurring Schedule Run Dates in IST
- **Module**: Sales
- **Location**: [`backend/sales/serializers.py:566-569`](file:///e:/Bizboard/backend/sales/serializers.py#L566-L569), [`backend/sales/recurring.py:31-41`](file:///e:/Bizboard/backend/sales/recurring.py#L31-L41)
- **Type**: Timezone / Logic
- **Severity**: High
- **What's wrong**: `RecurringInvoiceScheduleSerializer.validate` extracts `attrs["anchor_day"] = nra.day` where `nra` is a UTC datetime. For IST (UTC+05:30), midnight on the 1st of the month (`2026-10-01 00:00:00+05:30`) is `2026-09-30 18:30:00 UTC`. `nra.day` evaluates to `30`. The schedule permanently anchors to the 30th of the month instead of the 1st.
- **Trigger / Repro**: Schedule a recurring invoice for the 1st of the month at midnight in IST. Inspect `anchor_day` in database.
- **Consequence**: Monthly recurring invoices generate on the wrong calendar day.
- **Code Evidence**:
  `backend/sales/serializers.py`:
  ```python
  566: nra = attrs.get("next_run_at")
  567: if nra is not None and not self.partial:
  568:     attrs["anchor_day"] = nra.day # Reads UTC day!
  ```
- **Suggested Fix Direction**: Convert `nra` to `timezone.localtime(nra)` before reading `.day`.
- **Test to Add**: `test_recurring_schedule_serializer_anchor_day_in_ist`.
- **Twin Check (Purchase)**: Check recurring purchase templates.

---

### CR-016: Draft Sales Order Remains Editable After Conversion to Invoice / Delivery Challan
- **Module**: Sales
- **Location**: [`backend/sales/notes_services.py:521-524, 640`](file:///e:/Bizboard/backend/sales/notes_services.py#L521-L524)
- **Type**: Workflow / Data-integrity
- **Severity**: High
- **What's wrong**: Converting a Sales Order leaves it in `DRAFT` or `CONFIRMED` so stock reservations remain active until completion. However, `set_order_items` only checks `if order.status != SalesOrder.Status.DRAFT:`. It does not check `if order.converted_invoice_id:`. An operator can mutate order items, quantities, and prices after an invoice or delivery challan has already been spawned.
- **Trigger / Repro**: Convert a Sales Order to an invoice; call `set_order_items` on the order.
- **Consequence**: Order lines diverge from converted invoice lines, breaking reservation release accounting.
- **Code Evidence**:
  `backend/sales/notes_services.py`:
  ```python
  521: if order.status != SalesOrder.Status.DRAFT:
  522:     raise BusinessRuleError("Converted, confirmed, or cancelled orders cannot be edited.")
  ```
- **Suggested Fix Direction**: Reject line edits if `order.converted_invoice_id` is set or active delivery challans exist.
- **Test to Add**: `test_set_order_items_blocked_when_converted_invoice_present`.
- **Twin Check (Purchase)**: `PurchaseNotesService.set_order_items`.

---

### CR-017: Invoice Cancellation Leaves Delivery Challan Permanently Locked to Cancelled Invoice
- **Module**: Sales
- **Location**: [`backend/sales/services.py:1237-1238`](file:///e:/Bizboard/backend/sales/services.py#L1237-L1238), [`backend/sales/notes_services.py:897`](file:///e:/Bizboard/backend/sales/notes_services.py#L897)
- **Type**: Workflow / State Lock
- **Severity**: High
- **What's wrong**: When a sales invoice converted from a delivery challan is cancelled, `SalesService.cancel` resets `linked.stock_posted = False`, but fails to clear `linked.converted_invoice = None`. When an operator subsequently tries to re-convert the delivery challan into a correct invoice, `convert_delivery_challan` rejects it with: `"Challan has already been converted to an invoice."`
- **Trigger / Repro**: Convert Delivery Challan to Invoice; cancel the invoice; attempt to re-convert the Challan.
- **Consequence**: Delivery challans whose invoice was cancelled become permanently bricked.
- **Code Evidence**:
  `backend/sales/services.py`:
  ```python
  1237: linked.stock_posted = False
  1238: linked.save(update_fields=["stock_posted", "updated_at"])
  # linked.converted_invoice is never cleared!
  ```
- **Suggested Fix Direction**: Set `linked.converted_invoice = None` on cancellation.
- **Test to Add**: `test_cancel_invoice_clears_challan_converted_invoice`.
- **Twin Check (Purchase)**: Goods receipt notes / purchase challans.

---

### CR-018: Partial Sales Order Conversion Releases All Stock Reservations and Terminates Order
- **Module**: Sales
- **Location**: [`backend/sales/services.py:1032-1041`](file:///e:/Bizboard/backend/sales/services.py#L1032-L1041)
- **Type**: Inventory / Order Tracking
- **Severity**: High
- **What's wrong**: `set_items` allows partial conversion of a Sales Order quantity. However, when that invoice is completed, `SalesService.complete` unconditionally releases reservations for the full original quantities (`item.quantity`) and marks the order `status = CONVERTED`. The remaining unbilled items are de-reserved and can never be invoiced.
- **Trigger / Repro**: Create SO for 10 units; convert to invoice for 4 units; complete invoice.
- **Consequence**: Backorders are dropped; reservations for unbilled goods are released without notice.
- **Code Evidence**:
  `backend/sales/services.py`:
  ```python
  1035: for item in order.items.select_related("product"):
  1036:     InventoryService.release_reservation(order.company, warehouse, item.product, item.quantity, user)
  1038: order.status = SalesOrder.Status.CONVERTED
  ```
- **Suggested Fix Direction**: Enforce full conversion only until partial order line tracking is implemented, or release reservations proportionally.
- **Test to Add**: `test_so_partial_conversion_handling`.
- **Twin Check (Purchase)**: `PurchaseOrder` to `PurchaseInvoice` conversion.

---

### CR-019: AB-BA Deadlock Between `allocate_receipt` and `complete_credit_note`
- **Module**: Sales / Payments
- **Location**: [`backend/payments/services.py:406-407`](file:///e:/Bizboard/backend/payments/services.py#L406-L407), [`backend/sales/notes_services.py:144, 213`](file:///e:/Bizboard/backend/sales/notes_services.py#L144)
- **Type**: Concurrency / Deadlock
- **Severity**: High
- **What's wrong**: In `PaymentService.allocate_receipt`, row locks are acquired: `CustomerReceipt` first, then `SalesInvoice`. In `SalesNotesService.complete_credit_note` (with `confirm_paid_invoice=True`), row locks are acquired: `SalesInvoice` first, then `PaymentService.allocate_receipt` attempts to lock `CustomerReceipt`.
- **Trigger / Repro**: Concurrent execution of a receipt allocation and a credit note completion against the same invoice.
- **Consequence**: PostgreSQL detects an AB-BA deadlock and terminates one transaction with a 500 error.
- **Code Evidence**:
  `backend/payments/services.py:406-407`:
  ```python
  receipt = CustomerReceipt.objects.select_for_update().get(pk=receipt.pk)
  sales_invoice = SalesInvoice.objects.select_for_update().get(pk=sales_invoice.pk)
  ```
- **Suggested Fix Direction**: Establish global lock acquisition order: always lock `SalesInvoice` before `CustomerReceipt`.
- **Test to Add**: `test_concurrent_allocation_and_credit_note_completion_deadlock`.
- **Twin Check (Purchase)**: `allocate_supplier_payment` vs `complete_debit_note`.

---

### CR-020: Cross-Tenant Leak: `company_gstin` Unvalidated in `SalesCreditNoteSerializer`
- **Module**: Sales / Security
- **Location**: [`backend/sales/phase1_serializers.py:38-70, 124-155`](file:///e:/Bizboard/backend/sales/phase1_serializers.py#L38-L70)
- **Type**: Security / Cross-tenant
- **Severity**: High
- **What's wrong**: `SalesCreditNoteSerializer` and `SalesDebitNoteSerializer` expose `company_gstin` as a writable field, but omit `validate_company_gstin`. DRF generates an un-scoped `PrimaryKeyRelatedField(queryset=CompanyGstin.objects.all())`. A tenant can supply another company's `CompanyGstin` ID.
- **Trigger / Repro**: POST to `/api/v1/sales/credit-notes/` with `company_gstin: <foreign_tenant_gstin_id>`.
- **Consequence**: Legal credit/debit notes stamped with another tenant's legal GSTIN.
- **Code Evidence**: `backend/sales/phase1_serializers.py:44`: lacks `validate_company_gstin`.
- **Suggested Fix Direction**: Add `self.check_company_ref(company_gstin, "company_gstin")` in `validate_company_gstin`.
- **Test to Add**: `test_credit_note_rejects_foreign_company_gstin`.
- **Twin Check (Purchase)**: `PurchaseCreditNoteSerializer` and `PurchaseDebitNoteSerializer`.

---

### CR-021: Model Validation Bypassed on Bulk Line Insertion & Save Without `full_clean()`
- **Module**: Sales
- **Location**: [`backend/sales/services.py:40-86, 652`](file:///e:/Bizboard/backend/sales/services.py#L40-L86)
- **Type**: Data-integrity / 500 Error
- **Severity**: Medium
- **What's wrong**: `_validate_lines` does not validate string lengths (`description > 255`, `batch_no > 64`, `unit_name > 32`). Because lines are saved via `bulk_create` without `full_clean()`, long strings cause unhandled PostgreSQL `DataError` (HTTP 500).
- **Trigger / Repro**: Create an invoice line with a description of 300 characters.
- **Consequence**: Unhandled 500 crashes instead of 400 validation errors.
- **Code Evidence**: `backend/sales/services.py:46-86`: lacks length validation.
- **Suggested Fix Direction**: Add length checks in `_validate_lines`.
- **Test to Add**: `test_validate_lines_description_length_limit`.
- **Twin Check (Purchase)**: `backend/purchases/services.py:_validate_lines`.

---

### CR-022: Frontend Missing Query Invalidation on Invoice State Transitions & Inconsistent Cache Keys
- **Module**: Sales / Frontend
- **Location**: [`web/src/pages/sales/InvoiceDetailPage.tsx:146, 155`](file:///e:/Bizboard/web/src/pages/sales/InvoiceDetailPage.tsx#L146), [`SalesOrderEditorPage.tsx:250`](file:///e:/Bizboard/web/src/pages/sales/SalesOrderEditorPage.tsx#L250), [`QuotationsPage.tsx:166`](file:///e:/Bizboard/web/src/pages/sales/QuotationsPage.tsx#L166)
- **Type**: Frontend / UX Cache Desync
- **Severity**: Medium
- **What's wrong**: Completing or cancelling an invoice in `InvoiceDetailPage.tsx` invalidates `['sales-invoice', invoiceId]`, but not `['sales-invoices']`, `['customers']`, or `['dashboard']`. In `QuotationsPage.tsx:166`, conversion warms `['sales-invoices']` while history queries `['sales-invoices', 1]`.
- **Trigger / Repro**: Convert a quotation or complete an invoice and navigate back to the list page.
- **Consequence**: Stale lists and customer balances until manual browser refresh.
- **Code Evidence**: `web/src/pages/sales/InvoiceDetailPage.tsx:143-147`.
- **Suggested Fix Direction**: Invalidate `['sales-invoices']` and `['customers']` on all status mutations.
- **Test to Add**: Cypress/Playwright integration test verifying list invalidation.
- **Twin Check (Purchase)**: `PurchaseDetailPage.tsx` and `PurchaseOrderEditorPage.tsx`.

---

## 5. Module 3: Purchase Findings (`CR-023` – `CR-035`)

### CR-023: `PurchaseService.complete` Crashes Unconditionally on Service / Non-Stock Products
- **Module**: Purchase
- **Location**: [`backend/purchases/services.py:808-819`](file:///e:/Bizboard/backend/purchases/services.py#L808-L819)
- **Type**: Functional Defect / Crash
- **Severity**: Critical (Release-Blocking)
- **What's wrong**: `PurchaseService.complete` iterates through all line items and unconditionally invokes `InventoryService.post_movement(...)` without checking `tracks_inventory(item.product)`. `post_movement` (`backend/inventory/services.py:162`) explicitly raises `BusinessRuleError("Stock cannot be posted for a service or non-stock item.")`.
- **Trigger / Repro**: Add a service item (e.g. "Freight Charges" or "Consulting") to a purchase bill; attempt to complete.
- **Consequence**: 100% blockage of purchase billing for services or non-inventory goods.
- **Code Evidence**:
  `backend/purchases/services.py`:
  ```python
  808: InventoryService.post_movement(
  809:     company=invoice.company, warehouse=invoice.warehouse,
  810:     product=item.product, batch=item.batch, movement_type=MovementType.PURCHASE, ...
  811: )
  ```
- **Suggested Fix Direction**: Add `if not is_tally_opening and tracks_inventory(item.product):` around the stock movement block.
- **Test to Add**: `test_purchase_service_item_complete_posts_ap_without_stock_movement`.
- **Twin Check (Sales)**: Handled properly in `backend/sales/cogs_service.py:56` (`if not tracks_inventory(item.product): continue`).

---

### CR-024: FIFO Cost Layer Recorded at Gross `unit_price` Instead of Net Commercial Unit Cost
- **Module**: Purchase / Stock
- **Location**: [`backend/purchases/services.py:805-807`](file:///e:/Bizboard/backend/purchases/services.py#L805-L807)
- **Type**: Financial & Inventory Costing Inaccuracy
- **Severity**: Critical (Release-Blocking)
- **What's wrong**: `PurchaseService.complete` computes `unit_cost` for stock movements via `_line_stock_cost(item.product, item.unit_price, ...)`. `item.unit_price` is the catalog gross price before line discounts (`discount_percent`). The stock layer is stamped at gross price, while GL 1400 is debited net of discount (`item.taxable_amount`).
- **Trigger / Repro**: Purchase 10 units at ₹1,000 with 20% discount (net ₹800). Complete bill. Check `InventoryCostLayer.unit_cost` (₹1,000). Sell 10 units. COGS is recognized at ₹1,000, creating an erroneous ₹2,000 phantom loss.
- **Consequence**: Inventory valuation is inflated and subsequent COGS is distorted.
- **Code Evidence**:
  `backend/purchases/services.py`:
  ```python
  805: unit_cost = _line_stock_cost(
  806:     item.product, item.unit_price, getattr(item, "unit_name", None)
  807: )
  ```
- **Suggested Fix Direction**: Calculate unit cost from `item.taxable_amount / qty`.
- **Test to Add**: `test_purchase_stock_movement_unit_cost_nets_line_discount`.
- **Twin Check (Sales)**: Sales return reads actual unit cost from prior movements.

---

### CR-025: `PurchaseService.complete` Allocates Document Number Before Multi-GSTIN Check and Tax Recomputation
- **Module**: Purchase
- **Location**: [`backend/purchases/services.py:727-764`](file:///e:/Bizboard/backend/purchases/services.py#L727-L764)
- **Type**: Sequence Gaps / Multi-Tenant Integrity
- **Severity**: High
- **What's wrong**: In `PurchaseService.complete`, `DocumentNumberService.next_number()` is called at line 735 while `invoice.company_gstin` is `None`. At line 745, it checks active GSTINs and raises `BusinessRuleError("company_gstin is required...")` *after* the number was already burned. At line 755, `recompute_totals_for_stamped_gstin` runs *after* number allocation.
- **Trigger / Repro**: On a tenant with two active GSTINs, complete a bill without passing `company_gstin`.
- **Consequence**: Gaps in purchase invoice numbering series; numbers allocated on global company series instead of GSTIN branch series.
- **Code Evidence**:
  `backend/purchases/services.py`:
  ```python
  735: invoice.number = invoice.number or DocumentNumberService.next_number(...)
  ...
  745: raise BusinessRuleError("company_gstin is required when multiple GSTINs are active.")
  ```
- **Suggested Fix Direction**: Reorder sequence: validate GSTIN first, recompute totals second, allocate number third, post stock/GL fourth.
- **Test to Add**: `test_purchase_complete_multi_gstin_fails_before_number_generation`.
- **Twin Check (Sales)**: `SalesService.complete` validates GSTIN and recomputes totals *before* calling `DocumentNumberService`.

---

### CR-026: `PurchaseService.complete_return` Crashes on Service / Non-Stock Return Items
- **Module**: Purchase
- **Location**: [`backend/purchases/services.py:1150-1163`](file:///e:/Bizboard/backend/purchases/services.py#L1150-L1163)
- **Type**: Functional Defect
- **Severity**: High
- **What's wrong**: `PurchaseService.complete_return` calls `InventoryService.post_movement` without checking `tracks_inventory(item.product)`. Returning a service or non-stock product raises `BusinessRuleError`.
- **Trigger / Repro**: Issue a purchase return for a service item; attempt to complete.
- **Consequence**: Legitimate purchase returns and debit notes for service billing disputes are blocked.
- **Code Evidence**: `backend/purchases/services.py:1150-1163`.
- **Suggested Fix Direction**: Guard `_post_return_qty` with `if tracks_inventory(item.product):`.
- **Test to Add**: `test_purchase_return_service_product_completes`.
- **Twin Check (Sales)**: Sales return checks `tracks_inventory`.

---

### CR-027: `restamp_fifo_layers_for_price_amend` Corrupts Unit Cost for Alternate Units and Line Discounts
- **Module**: Purchase / Costing
- **Location**: [`backend/purchases/services.py:451-476`](file:///e:/Bizboard/backend/purchases/services.py#L451-L476)
- **Type**: Costing Inaccuracy
- **Severity**: High
- **What's wrong**: `restamp_fifo_layers_for_price_amend` extracts `price_by_product = {item.product_id: item.unit_price}`. If an item was purchased in alternate units (e.g. 1 Box = 10 Pcs), `move.quantity` is 10 Pcs, but `unit_price` is ₹500/Box. The layer is restamped with ₹500/Pc instead of ₹50/Pc (a 10x inflation). Line discounts are also ignored.
- **Trigger / Repro**: Amend the price of a purchase bill with alternate units; check `InventoryCostLayer.unit_cost`.
- **Consequence**: Severe stock valuation corruption.
- **Code Evidence**: `backend/purchases/services.py:451-459`.
- **Suggested Fix Direction**: Map amend cost by line item / source movement ID using `item.taxable_amount / move.quantity`.
- **Test to Add**: `test_restamp_fifo_layers_alternate_unit_and_discount`.
- **Twin Check (Sales)**: Sales H9 amend restamps COGS using base unit costs.

---

### CR-028: `PurchaseCreditNote` and `DebitNote` Use Deprecated `resolve_series_gstin` Instead of `series_identity`
- **Module**: Purchase
- **Location**: [`backend/purchases/notes_services.py:326, 515`](file:///e:/Bizboard/backend/purchases/notes_services.py#L326)
- **Type**: Logic Drift
- **Severity**: Medium
- **What's wrong**: In `complete_credit_note` and `complete_debit_note`, series numbering calls `resolve_series_gstin` instead of `series_identity`. When `doc_number_scope` is `GSTIN_FY`, it bypasses company FY scoping and series defaults.
- **Trigger / Repro**: Set document scope to `GSTIN_FY`; issue purchase credit note across FY boundary.
- **Consequence**: Note sequence numbering drifts from invoices and fails FY partitioning.
- **Code Evidence**: `backend/purchases/notes_services.py:323-328`.
- **Suggested Fix Direction**: Call `series_identity(note.company, stamp, note.note_date)`.
- **Test to Add**: `test_purchase_notes_series_identity_fy_scoping`.
- **Twin Check (Sales)**: Sales notes use `series_identity`.

---

### CR-029: Unscoped `source_item` on `PurchaseCreditNoteItem` and `DebitNoteItem` Serializers
- **Module**: Purchase / Security
- **Location**: [`backend/purchases/phase1_serializers.py:30-40, 98-108`](file:///e:/Bizboard/backend/purchases/phase1_serializers.py#L30-L40)
- **Type**: Multi-Tenant Security / Reference Leak
- **Severity**: High
- **What's wrong**: `source_item` is an unvalidated ForeignKey to `PurchaseItem`. A user from Tenant A can supply a `source_item` ID belonging to Tenant B.
- **Trigger / Repro**: POST to `/api/v1/purchases/credit-notes/` with `source_item: <foreign_tenant_purchase_item_id>`.
- **Consequence**: Cross-tenant data reference leak; line validation runs queries against foreign lines.
- **Code Evidence**: `backend/purchases/phase1_serializers.py:30-40`.
- **Suggested Fix Direction**: Wrap `source_item` in `CompanyPrimaryKeyRelatedField`.
- **Test to Add**: `test_purchase_credit_note_rejects_foreign_source_item`.
- **Twin Check (Sales)**: `SalesCreditNoteItemSerializer` scopes line sources.

---

### CR-030: `SupplierPaymentViewSet` Crashes with 500 on Non-Numeric `?supplier=` Query Parameter
- **Module**: Purchase / Payments
- **Location**: [`backend/payments/views.py:217-219`](file:///e:/Bizboard/backend/payments/views.py#L217-L219)
- **Type**: Input Validation / 500 Error
- **Severity**: Medium
- **What's wrong**: `SupplierPaymentViewSet.get_queryset` filters `supplier_id=self.request.query_params["supplier"]` directly without catching `ValueError`, crashing with an unhandled 500 error.
- **Trigger / Repro**: `GET /api/v1/payments/supplier-payments/?supplier=abc`.
- **Consequence**: Unhandled 500 error and Sentry alert noise.
- **Code Evidence**: `backend/payments/views.py:217-219`.
- **Suggested Fix Direction**: Catch `(TypeError, ValueError)` and raise `BusinessRuleError("supplier must be a numeric id.")`.
- **Test to Add**: `test_supplier_payment_list_non_numeric_supplier_returns_400`.
- **Twin Check (Sales)**: `ReceiptViewSet` validates numeric IDs.

---

### CR-031: Frontend `NewPurchasePage.tsx` Fails to Invalidate Inventory/Product Query Cache on Complete
- **Module**: Purchase / Frontend
- **Location**: [`web/src/pages/purchases/NewPurchasePage.tsx:889-935`](file:///e:/Bizboard/web/src/pages/purchases/NewPurchasePage.tsx#L889-L935)
- **Type**: Frontend / State Sync
- **Severity**: High
- **What's wrong**: Completing a purchase adds inventory stock. However, `NewPurchasePage.tsx` only invalidates `['purchase-invoice']` and `['purchases']`; it never invalidates `['products']`, `['product-search']`, or `['stock-balance']`.
- **Trigger / Repro**: Complete a purchase of 50 units in `/purchases/new`; navigate to `/inventory` or `/pos`.
- **Consequence**: UI displays stale zero stock; cashiers cannot sell newly received items.
- **Code Evidence**: `web/src/pages/purchases/NewPurchasePage.tsx:892-896`.
- **Suggested Fix Direction**: Invalidate `['products']`, `['stock-balance']`, and `['product-search']` on complete.
- **Test to Add**: Playwright test asserting stock count updates across views after purchase complete.
- **Twin Check (Sales)**: `NewSalePage` invalidates stock queries.

---

### CR-032: Frontend `SupplierPaymentsPage.tsx` Fails to Invalidate `purchases` Query Cache on Allocation
- **Module**: Purchase / Frontend
- **Location**: [`web/src/pages/purchases/SupplierPaymentsPage.tsx:119-129`](file:///e:/Bizboard/web/src/pages/purchases/SupplierPaymentsPage.tsx#L119-L129)
- **Type**: Frontend / State Sync
- **Severity**: High
- **What's wrong**: Recording a supplier payment with an invoice allocation in `SupplierPaymentsPage.tsx` invalidates `['supplier-payments']` only. `['purchases']` and `['purchase-invoice', id]` are not invalidated.
- **Trigger / Repro**: Record a payment against an invoice; return to `/purchases/history`.
- **Consequence**: The invoice continues to show the old unpaid balance, leading to duplicate payment attempts.
- **Code Evidence**: `web/src/pages/purchases/SupplierPaymentsPage.tsx:119-129`.
- **Suggested Fix Direction**: Invalidate `['purchases']` inside `createMutation.onSuccess`.
- **Test to Add**: Unit test asserting `qc.invalidateQueries({ queryKey: ['purchases'] })` is called on payment allocation.
- **Twin Check (Sales)**: `ReceiptsPage.tsx` invalidates `['sales-invoices']`.

---

### CR-033: Frontend `PurchaseReturnsPage.tsx` Fails to Invalidate `purchases`, `purchase-credit-notes`, and `products`
- **Module**: Purchase / Frontend
- **Location**: [`web/src/pages/purchases/PurchaseReturnsPage.tsx:163-168`](file:///e:/Bizboard/web/src/pages/purchases/PurchaseReturnsPage.tsx#L163-L168)
- **Type**: Frontend / State Sync
- **Severity**: High
- **What's wrong**: Completing a purchase return updates stock, flips invoice status to `RETURNED`, and creates a credit note. However, `PurchaseReturnsPage.tsx` only invalidates `['purchase-returns']`.
- **Trigger / Repro**: Complete a purchase return; navigate to `/purchases/credit-notes` or `/purchases/history`.
- **Consequence**: Inconsistent multi-tab UI state across all purchase screens.
- **Code Evidence**: `web/src/pages/purchases/PurchaseReturnsPage.tsx:167`.
- **Suggested Fix Direction**: Invalidate `['purchases']`, `['purchase-credit-notes']`, and `['products']`.
- **Test to Add**: Playwright test asserting credit note list updates after return.
- **Twin Check (Sales)**: `SalesReturnsPage` invalidates invoices and credit notes.

---

### CR-034: Missing File SHA-256 Duplicate Detection on `PURCHASE_BILL` Upload
- **Module**: Purchase / Imports
- **Location**: [`backend/imports/services.py:1229-1240, 2917-2933`](file:///e:/Bizboard/backend/imports/services.py#L1229-L1240)
- **Type**: Data Integrity / Duplicate Detection
- **Severity**: Medium
- **What's wrong**: `ImportService.validate` restricts duplicate hash checks to `job.kind == PRODUCTS`. When uploading `PURCHASE_BILL` files, identical bills can be uploaded repeatedly without duplicate warning.
- **Trigger / Repro**: Upload the same bill PDF twice under `PURCHASE_BILL`. Both imports create separate jobs and commit to duplicate draft purchase bills.
- **Consequence**: Accidental duplicate draft purchase creation.
- **Code Evidence**: `backend/imports/services.py:1231-1240`.
- **Suggested Fix Direction**: Compute `file_sha256` on `PURCHASE_BILL` uploads and reject identical files within 30 days.
- **Test to Add**: `test_purchase_bill_duplicate_sha256_detection`.
- **Twin Check (Sales)**: Sales imports.

---

### CR-035: Purchase TDS Exclusivity Check Runs Before `fold_tds_from_rate`
- **Module**: Purchase / Tax
- **Location**: [`backend/purchases/services.py:42-44, 708, 766`](file:///e:/Bizboard/backend/purchases/services.py#L708)
- **Type**: Statutory / Missing-validation
- **Severity**: High
- **What's wrong**: In `PurchaseService.complete`:
  Line 708: `assert_invoice_tds_exclusive(invoice)`
  Line 766: `invoice.tds_amount = fold_tds_from_rate(...)`
  `assert_invoice_tds_exclusive` returns early if `tds_amount <= 0`. If a draft purchase invoice specifies `tds_rate=1.0` but leaves `tds_amount=0`, line 708 skips the check. Line 766 then computes `tds_amount`. This allows rate-only invoices to bypass the rule forbidding invoice TDS when supplier has payment TDS.
- **Trigger / Repro**: Configure supplier for payment-level TDS; create purchase bill with `tds_rate=1.0` and `tds_amount=0`; complete bill.
- **Consequence**: Double TDS deduction (at bill level and payment level).
- **Code Evidence**:
  `backend/purchases/services.py`:
  ```python
  708: assert_invoice_tds_exclusive(invoice)
  ...
  766: invoice.tds_amount = fold_tds_from_rate(...)
  ```
- **Suggested Fix Direction**: Execute `fold_tds_from_rate` *before* `assert_invoice_tds_exclusive`.
- **Test to Add**: `test_purchase_tds_exclusive_with_tds_rate_only`.
- **Twin Check (Sales)**: `apply_tcs_fold` runs before validations.

---

## 6. Module 4: Stock & Godown Findings (`CR-036` – `CR-042`)

### CR-036: `ExpiryAlertsView.post` Fails When Writing Off Expired Lots Due to Missing `skip_negative_check`
- **Module**: Stock
- **Location**: [`backend/inventory/views.py:641-651`](file:///e:/Bizboard/backend/inventory/views.py#L641-L651), [`backend/inventory/services.py:205-207`](file:///e:/Bizboard/backend/inventory/services.py#L205-L207)
- **Type**: Functional Defect / Crash
- **Severity**: Critical (Release-Blocking)
- **What's wrong**: When writing off an expired lot via `ExpiryAlertsView.post()`, `post_movement` is called with `delta = -qty` and defaults to `skip_negative_check=False`. In `InventoryService.post_movement` (lines 205-207):
  ```python
  if delta < 0 and not skip_negative_check:
      if batch and company.block_expired_stock and batch.expiry_date and batch.expiry_date < timezone.localdate():
          raise BusinessRuleError(f"Batch '{batch.batch_no}' is expired and cannot be issued.")
  ```
  The check intended to prevent *selling* expired stock blocks the *write-off* of expired stock! Operators cannot discard expired inventory.
- **Trigger / Repro**: Enable `company.block_expired_stock`; attempt to write off an expired batch in `ExpiryAlertsView`.
- **Consequence**: Operators cannot write off expired stock; expired stock is permanently trapped in the inventory ledger.
- **Code Evidence**:
  `backend/inventory/views.py`:
  ```python
  641: movement = InventoryService.post_movement(
  642:     company=company, product=product, movement_type=MovementType.ADJUSTMENT,
  643:     quantity=-qty, reason="EXPIRED", reference_type="expiry_write_off", ...
  644:     # skip_negative_check=True is missing!
  645: )
  ```
- **Suggested Fix Direction**: Pass `skip_negative_check=True` in `ExpiryAlertsView.post()`.
- **Test to Add**: `test_expiry_alert_write_off_expired_batch_succeeds`.
- **Twin Check (Sales)**: Sales properly blocks expired batches.

---

### CR-037: `default_warehouse` Aborts Transaction on Concurrent `IntegrityError` in PostgreSQL
- **Module**: Stock
- **Location**: [`backend/inventory/services.py:58-64`](file:///e:/Bizboard/backend/inventory/services.py#L58-L64)
- **Type**: Bug / Postgres Transaction Error
- **Severity**: Critical (Release-Blocking)
- **What's wrong**: In `InventoryService.default_warehouse`:
  ```python
  with transaction.atomic():
      ...
      try:
          warehouse.save(update_fields=["is_default"])
      except IntegrityError:
          other = Warehouse.objects.filter(company=company, is_default=True).first()
          if other: return other
          raise
  ```
  In PostgreSQL, an `IntegrityError` inside `with transaction.atomic():` breaks the current transaction/savepoint. Because `warehouse.save()` is not wrapped in its own sub-savepoint, line 61 (`Warehouse.objects.filter(...)`) crashes with `TransactionManagementError: An error occurred in the current transaction. You can't execute queries until the end of the 'atomic' block.`
- **Trigger / Repro**: Two concurrent threads invoke `default_warehouse` for a tenant with no default warehouse set.
- **Consequence**: 500 server crash on concurrent warehouse setup.
- **Code Evidence**: `backend/inventory/services.py:58-64`.
- **Suggested Fix Direction**: Wrap `warehouse.save()` in an inner `with transaction.atomic():` block.
- **Test to Add**: `test_default_warehouse_concurrent_integrity_error_handled_cleanly`.
- **Twin Check (Purchase)**: Check concurrent supplier creation.

---

### CR-038: Valuation Snapshot Replay Collapses FIFO into WAVG Due to Empty Initial Layers `[]`
- **Module**: Stock / Costing
- **Location**: [`backend/inventory/services.py:1720-1730, 1812-1828`](file:///e:/Bizboard/backend/inventory/services.py#L1720-L1730)
- **Type**: Data-integrity / Costing
- **Severity**: Critical (Release-Blocking)
- **What's wrong**: When `valuation(as_of=...)` uses an `InventoryValuationSnapshot` as the baseline:
  ```python
  state[key] = {
      "qty": Decimal(str(snap.qty or 0)),
      "value": Decimal(str(snap.value or 0)),
      "layers": [],  # <--- CRITICAL BUG
  }
  ```
  Because `snap_rows` does not store individual layers, `layers` is set to `[]`. When subsequent movements are replayed under `method == "FIFO"`:
  `for layer in entry["layers"]:` does not execute because `layers` is empty. Line 1825 executes: `cost += remaining * pre_avg`.
- **Trigger / Repro**: Take a month-end valuation snapshot; run FIFO valuation for a date after the snapshot.
- **Consequence**: All prior inventory layers are discarded; FIFO costing completely degrades into weighted average after any snapshot.
- **Code Evidence**: `backend/inventory/services.py:1729`.
- **Suggested Fix Direction**: Seed `state[key]["layers"]` with `[[snap.qty, snap.value / snap.qty]]` when `snap.qty > 0`.
- **Test to Add**: `test_valuation_fifo_replay_from_snapshot_preserves_cost_layer`.
- **Twin Check (Sales)**: COGS replay from snapshot.

---

### CR-039: `rebuild_balance` Can Overwrite Concurrent Movements Without Locking
- **Module**: Stock
- **Location**: [`backend/inventory/services.py:1124-1165`](file:///e:/Bizboard/backend/inventory/services.py#L1124-L1165)
- **Type**: Race / Data Corruption
- **Severity**: High
- **What's wrong**: `rebuild_balance` computes `total = StockMovement.objects.filter(...).aggregate(total=Sum("quantity"))["total"]` and writes `balance.on_hand = total; balance.save()`. It is not wrapped in `transaction.atomic()` and takes no lock on `StockBalance`. A concurrent `post_movement` occurring between the `Sum` aggregate and `balance.save` has its quantity permanently overwritten and dropped from the cached balance.
- **Trigger / Repro**: Execute `rebuild_balance` while sales transactions are being posted.
- **Consequence**: `StockBalance.on_hand` desynchronizes permanently from `Sum(StockMovement)`.
- **Code Evidence**: `backend/inventory/services.py:1142-1145`.
- **Suggested Fix Direction**: Wrap `rebuild_balance` in `transaction.atomic()` with `select_for_update()` on `StockBalance`.
- **Test to Add**: `test_rebuild_balance_locks_stock_balance`.
- **Twin Check (Ledgers)**: Party balance rebuilding.

---

### CR-040: Closed-Period Check in `StockCountSessionViewSet.post` Uses Current Date Instead of `counted_on`
- **Module**: Stock
- **Location**: [`backend/inventory/views.py:724, 762`](file:///e:/Bizboard/backend/inventory/views.py#L724)
- **Type**: Statutory / Logic Defect
- **Severity**: High
- **What's wrong**: `StockCountSessionViewSet.post` calls `assert_period_allows_money_amend(session.company, _tz.localdate())` against today's date rather than `session.counted_on`. It also calls `post_movement` without `movement_date`, defaulting the movement to today's date. A physical count performed on August 31 (closed period) but posted on September 7 (open period) bypasses the period guard and stamps movements into September.
- **Trigger / Repro**: Perform a physical count on a date in a closed period; post it today.
- **Consequence**: Physical inventory adjustments are posted into the wrong financial period.
- **Code Evidence**: `backend/inventory/views.py:724, 762`.
- **Suggested Fix Direction**: Pass `session.counted_on` to `assert_period_allows_money_amend` and as `movement_date` to `post_movement`.
- **Test to Add**: `test_stock_count_post_rejects_closed_counted_on_date`.
- **Twin Check (Accounting)**: Manual journal period checks.

---

### CR-041: `StockTransferService.complete` Under `WARN` Policy Transfers Non-Existent Stock
- **Module**: Stock
- **Location**: [`backend/inventory/services.py:1342-1377`](file:///e:/Bizboard/backend/inventory/services.py#L1342-L1377)
- **Type**: Data Integrity / Inventory Inflation
- **Severity**: Medium
- **What's wrong**: In `StockTransferService.complete`, if `negative_stock_policy == "WARN"`, transferring stock exceeding source godown on-hand is allowed. Source godown goes negative, but destination godown receives real inbound stock (`TRANSFER_IN`), creating phantom inventory across the company.
- **Trigger / Repro**: Under `WARN` policy, transfer 100 units from Godown A (on-hand 0) to Godown B.
- **Consequence**: Godown B can now sell 100 units that never physically existed.
- **Code Evidence**: `backend/inventory/services.py:1342-1377`.
- **Suggested Fix Direction**: Always require available stock on transfers regardless of `WARN` policy (or restrict to admin override).
- **Test to Add**: `test_stock_transfer_rejects_negative_stock_under_warn`.
- **Twin Check (Sales)**: Sales under `WARN`.

---

### CR-042: No Automated Background Reconciliation or Heartbeat Check for `StockBalance` Drift
- **Module**: Stock
- **Location**: `backend/inventory/tasks.py`, `backend/inventory/services.py:1127`
- **Type**: Operational / Monitoring
- **Severity**: Medium
- **What's wrong**: Codebase docstring explicitly acknowledges (`services.py:1127`): *"CR-054: drift repair is ops/API via this helper / rebuild_stock_balances; there is no scheduled balance↔movement health check yet."* There is no automated Celery heartbeat task verifying `StockBalance.on_hand == Sum(StockMovement.quantity)`.
- **Trigger / Repro**: Introduce a silent drift; observe that no system alerts are fired.
- **Consequence**: Drift between cached balances and the movement ledger remains undetected until customer complaints.
- **Code Evidence**: Absence of scheduled verification task in `backend/inventory/tasks.py`.
- **Suggested Fix Direction**: Add a daily Celery task executing `rebuild_stock_balances(dry_run=True)` and emitting alerts on discrepancies.
- **Test to Add**: `test_stock_balance_integrity_checker_task`.
- **Twin Check (Accounting)**: `BooksHealthService` checks GL vs subledgers.

---

## 7. Module 5: Reporting Findings (`CR-043` – `CR-055`)

### CR-043: Asymmetric Return Handling Causes Double-Deduction in Dashboard `purchases_this_month`
- **Module**: Reporting
- **Location**: [`backend/reporting/services.py:224-240, 264-265`](file:///e:/Bizboard/backend/reporting/services.py#L224-L240)
- **Type**: Financial Inaccuracy / Broken KPI
- **Severity**: Critical (Release-Blocking)
- **What's wrong**: In `ReportService.dashboard_kpis`:
  Sales MTD queries `status__in=(COMPLETED, RETURNED)` and subtracts credit notes.
  However, Purchases MTD queries ONLY `status=PurchaseInvoice.Status.COMPLETED` (excluding `RETURNED`). Then, it subtracts `pcn_month` (`PurchaseCreditNote` total). When a purchase bill is returned, its status flips to `RETURNED` (dropping it from `purchases_month`), AND its credit note is subtracted. The return is deducted twice.
- **Trigger / Repro**: Purchase ₹50,000 of goods; return all ₹50,000 via a purchase return.
- **Consequence**: `purchases_this_month` displays `-₹50,000` (negative purchase total).
- **Code Evidence**:
  `backend/reporting/services.py`:
  ```python
  224: purchases_month = PurchaseInvoice.objects.filter(
  225:     company=company, status=PurchaseInvoice.Status.COMPLETED, ...
  226: ).aggregate(total=Sum("grand_total"), count=Count("id"))
  ...
  264: "total": (purchases_month["total"] or Decimal("0")) - pcn_month + pdn_month
  ```
- **Suggested Fix Direction**: Filter `status__in=(PurchaseInvoice.Status.COMPLETED, PurchaseInvoice.Status.RETURNED)` matching the sales side.
- **Test to Add**: `test_dashboard_purchases_mtd_handles_returns_without_double_deduction`.
- **Twin Check (Sales)**: Sales handles returns symmetrically.

---

### CR-044: Dashboard AR/AP Aging Diverges from Derived Party Ledgers
- **Module**: Reporting / Ledgers
- **Location**: [`backend/reporting/services.py:153-156, 614-617`](file:///e:/Bizboard/backend/reporting/services.py#L153-L156) vs [`backend/ledgers/services.py:404-454`](file:///e:/Bizboard/backend/ledgers/services.py#L404-L454)
- **Type**: Financial Inaccuracy / Ledger Divergence
- **Severity**: Critical (Release-Blocking)
- **What's wrong**:
  1. `ReportService.receivables_aging` and `payables_aging` explicitly drop opening balance invoices (`is_opening_balance=False`). Customer statements and `LedgerService.customer_outstanding` include them. A merchant with ₹5,00,000 of opening AR imported from Tally sees ₹0 on the Dashboard and ₹5,00,000 on the Customer Ledger.
  2. `receivables_aging` uses `bulk_sales_invoice_outstanding`, which only subtracts credit notes linked to active open invoice IDs. Unlinked or standalone credit notes are omitted from aging, making Dashboard receivables higher than ledger balances.
- **Trigger / Repro**: Import customer opening balances; check Dashboard KPI vs Customer Ledger.
- **Consequence**: Dashboard financial health indicators contradict party ledger balances.
- **Code Evidence**: `backend/reporting/services.py:155` (`is_opening_balance=False`).
- **Suggested Fix Direction**: Align aging filters with `LedgerService.bulk_customer_outstanding` to include opening invoices and account for all active credit notes.
- **Test to Add**: `test_dashboard_receivables_aging_matches_customer_ledger_total`.
- **Twin Check (Accounting)**: GL 1200 vs party outstanding.

---

### CR-045: Missing Upper Date Bounds on MTD Dashboard Aggregates (`__gte=month_start` Lacks `__lte=today`)
- **Module**: Reporting
- **Location**: [`backend/reporting/services.py:197-240`](file:///e:/Bizboard/backend/reporting/services.py#L197-L240)
- **Type**: Financial Reporting Inaccuracy
- **Severity**: Critical (Release-Blocking)
- **What's wrong**: All MTD dashboard queries (`sales_month`, `purchases_month`, `cn_month`, `dn_month`, `pcn_month`, `pdn_month`) specify `invoice_date__gte=month_start` without an upper bound (`invoice_date__lte=today` or `month_end`). Any future-dated or post-dated invoice entered for next month or next year is absorbed into current MTD figures.
- **Trigger / Repro**: Create an invoice dated for the 15th of next month; view current dashboard sales.
- **Consequence**: Current-month sales and purchase KPIs are overstated by post-dated documents.
- **Code Evidence**: `backend/reporting/services.py:198` (`invoice_date__gte=month_start` lacks `__lte`).
- **Suggested Fix Direction**: Add `invoice_date__lte=today` (or `month_end`) across all MTD queries.
- **Test to Add**: `test_dashboard_mtd_ignores_future_dated_invoices`.
- **Twin Check (Sales)**: Check date filters on sales registers.

---

### CR-046: Stock Valuation Report Reads Stale Running Cost / Cost Layer Cache Instead of Verified Movements
- **Module**: Reporting / Stock
- **Location**: [`backend/inventory/views.py:662-665`](file:///e:/Bizboard/backend/inventory/views.py#L662-L665) vs [`backend/inventory/services.py:1622-1672`](file:///e:/Bizboard/backend/inventory/services.py#L1622-L1672)
- **Type**: Data-integrity / Stale Cache
- **Severity**: Critical (Release-Blocking)
- **What's wrong**: On the Stock Valuation Report (`StockValuationReportView`), `InventoryValuationService.valuation()` directly reads `InventoryRunningCost` (WAVG) or `InventoryCostLayer` (FIFO) without verifying live quantities against `Sum(StockMovement.quantity)`. If the cache drifts, the official valuation report outputs corrupt financial figures.
- **Trigger / Repro**: Introduce a discrepancy in `InventoryRunningCost`; generate valuation report.
- **Consequence**: Misstated balance sheet inventory valuations.
- **Code Evidence**: `backend/inventory/services.py:1635-1650`.
- **Suggested Fix Direction**: Cross-check cached quantities against `sum(StockMovement.quantity)` and trigger replay on drift.
- **Test to Add**: `test_valuation_report_flags_or_repairs_running_cost_drift`.
- **Twin Check (Accounting)**: GL 1400 inventory balance reconciliation.

---

### CR-047: Complete In-Memory Buffering Across All Export Views (High OOM Risk)
- **Module**: Reporting
- **Location**: [`backend/reporting/views.py:250-257, 654-664, 1230-1319`](file:///e:/Bizboard/backend/reporting/views.py#L1306-L1319), [`backend/accounting/views.py:590-597`](file:///e:/Bizboard/backend/accounting/views.py#L590-L597)
- **Type**: Performance / Denial of Service
- **Severity**: High
- **What's wrong**: All report export endpoints (`CashBookView`, `CancelledDocumentNumbersView`, `TdsWorksheetView`, `ExportView`) load all rows into Python lists, format them into in-memory `io.StringIO` or `openpyxl.Workbook` / `BytesIO` buffers, call `.getvalue()`, and return standard `HttpResponse`. For 10,000–25,000 rows, this consumes 100MB+ per request, triggering worker OOM kills.
- **Trigger / Repro**: Export a full-year sales register with 20,000 invoices concurrently from two tabs.
- **Consequence**: Gunicorn/Uvicorn worker process crashes and dropped user connections.
- **Code Evidence**:
  `backend/reporting/views.py`:
  ```python
  1311: buffer = io.StringIO()
  1312: writer = csv.DictWriter(buffer, fieldnames=fieldnames)
  1316: response = HttpResponse(buffer.getvalue(), content_type="text/csv")
  ```
- **Suggested Fix Direction**: Use `StreamingHttpResponse` with a streaming generator and `Echo` buffer.
- **Test to Add**: `test_export_views_stream_responses`.
- **Twin Check (Sales)**: Sales register exports.

---

### CR-048: Missing Pagination on Financial Registers for Full-Year Date Ranges
- **Module**: Reporting
- **Location**: [`backend/reporting/views.py:103-140`](file:///e:/Bizboard/backend/reporting/views.py#L103-L140), [`web/src/pages/reports/SalesReportPage.tsx:33-43`](file:///e:/Bizboard/web/src/pages/reports/SalesReportPage.tsx#L33-L43)
- **Type**: Performance / Frontend DoS
- **Severity**: High
- **What's wrong**: `SalesRegisterView` and `PurchaseRegisterView` enforce a 5,000-row cap only when `date_from` is empty. When `date_from` is supplied, queries spanning up to 366 days bypass the cap and return all rows in an unpaginated JSON array.
- **Trigger / Repro**: Request a full-year sales register for a business with 50,000 invoices.
- **Consequence**: Giant 25MB+ JSON payloads freeze client browsers and overwhelm server memory.
- **Code Evidence**: `backend/reporting/views.py:110-120`: lacks DRF pagination.
- **Suggested Fix Direction**: Add standard DRF `LimitOffsetPagination` or `PageNumberPagination`.
- **Test to Add**: `test_sales_register_view_enforces_pagination`.
- **Twin Check (Purchase)**: `PurchaseRegisterView`.

---

### CR-049: O(N) Query and Save Loop in IMS Classification (`classify_and_match`)
- **Module**: Reporting / GSTR-2B
- **Location**: [`backend/reporting/ims.py:82-124`](file:///e:/Bizboard/backend/reporting/ims.py#L82-L124)
- **Type**: Performance / N+1 Query Loop
- **Severity**: High
- **What's wrong**: In `classify_and_match`, matching GSTR-2B ingests (which allow up to 20,000 rows) executes individual `PurchaseInvoice.objects.filter().first()` queries and separate `row.save()` calls in a Python loop over all unmatched rows.
- **Trigger / Repro**: Upload a GSTR-2B JSON file with 2,000 unmatched invoices.
- **Consequence**: 2,000–4,000 sequential SQL queries cause HTTP gateway timeouts (504).
- **Code Evidence**: `backend/reporting/ims.py:95-120`.
- **Suggested Fix Direction**: Pre-fetch matching purchase invoices into an in-memory dictionary and use `bulk_update` to persist `match_class`.
- **Test to Add**: `test_ims_classify_and_match_query_count_constant`.
- **Twin Check (Sales)**: GSTR-1 matching.

---

### CR-050: Missing Branch/GSTIN Scoping in `Gstr2bIngest` Causes Cross-Branch Collisions
- **Module**: Reporting / GSTR-2B
- **Location**: [`backend/reporting/models.py:79-112`](file:///e:/Bizboard/backend/reporting/models.py#L79-L112), [`backend/reporting/views.py:875-935`](file:///e:/Bizboard/backend/reporting/views.py#L875-L935)
- **Type**: Multi-Tenant / Branch Collision
- **Severity**: High
- **What's wrong**: `Gstr2bIngest` model has no `company_gstin` foreign key. In a company with multiple GSTINs (e.g. MH and KA branches), uploading 2B files for both branches causes collisions in `update_or_create` whenever the same supplier bill number appears across branches.
- **Trigger / Repro**: Upload 2B file for Branch A; upload 2B file for Branch B with overlapping supplier invoice numbers.
- **Consequence**: Branch B overwrites Branch A's 2B records.
- **Code Evidence**: `backend/reporting/views.py:895-905` (`update_or_create` excludes `company_gstin`).
- **Suggested Fix Direction**: Add `company_gstin = models.ForeignKey(CompanyGstin, ...)` to `Gstr2bIngest` and include it in unique constraints.
- **Test to Add**: `test_gstr2b_ingest_multi_gstin_isolation`.
- **Twin Check (Sales)**: GSTR-1 export includes `company_gstin`.

---

### CR-051: Dropping Unlinked Matched 2B Rows When Branch GSTIN Filter Is Applied
- **Module**: Reporting / GSTR-2B
- **Location**: [`backend/reporting/gstr2b.py:169-181`](file:///e:/Bizboard/backend/reporting/gstr2b.py#L169-L181)
- **Type**: Bug / Data Loss in Report
- **Severity**: Medium
- **What's wrong**: When `company_gstin_id` is filtered, line 180 executes `qs = qs.filter(purchase_invoice__company_gstin_id=company_gstin_id)`. This inner join discards all valid 2B rows that do not have a linked `purchase_invoice`, contradicting the module's invariant that 2B rows stand on their own.
- **Trigger / Repro**: Filter 2B report by branch GSTIN when unlinked 2B entries exist.
- **Consequence**: Unlinked 2B lines disappear from the reconciliation view.
- **Code Evidence**: `backend/reporting/gstr2b.py:180`.
- **Suggested Fix Direction**: Filter on `recipient_gstin` on the 2B ingest row instead of joining through `purchase_invoice`.
- **Test to Add**: `test_gstr2b_report_branch_filter_retains_unlinked_rows`.
- **Twin Check (Sales)**: GSTR-1 reconciliation.

---

### CR-052: Incomplete Document Coverage in TCS/TDS Worksheets (Omits Credit & Debit Notes)
- **Module**: Reporting / Statutory
- **Location**: [`backend/reporting/tds_worksheets.py:29-133`](file:///e:/Bizboard/backend/reporting/tds_worksheets.py#L29-L133)
- **Type**: Statutory / Missing-data
- **Severity**: Medium
- **What's wrong**: `tds_worksheet_rows` queries `PurchaseInvoice` and `SupplierPayment`, but omits `PurchaseCreditNote` and `PurchaseDebitNote`. `tcs_worksheet_rows` queries `SalesInvoice`, but omits `SalesCreditNote` and `SalesDebitNote`. Notes carry statutory `tds_amount` and `tcs_amount` fields that adjust liability.
- **Trigger / Repro**: Issue a credit note reversing TCS or TDS; generate 26Q/27EQ worksheets.
- **Consequence**: Statutory quarterly tax returns misstate tax liabilities.
- **Code Evidence**: `backend/reporting/tds_worksheets.py:35, 100`.
- **Suggested Fix Direction**: Include credit and debit notes in TDS/TCS worksheet queries.
- **Test to Add**: `test_tds_worksheet_includes_credit_notes`.
- **Twin Check (Accounting)**: GL 2265 (TDS) and 2266 (TCS) accounts reflect credit notes.

---

### CR-053: RCM Tax Reallocation Diverges from Document Write Path
- **Module**: Reporting / GST
- **Location**: [`backend/reporting/gst_returns.py:295-325`](file:///e:/Bizboard/backend/reporting/gst_returns.py#L295-L325)
- **Type**: Statutory / Calculation Drift
- **Severity**: Medium
- **What's wrong**: When line taxes are zero but header RCM memo fields exist, `_rate_buckets` prorates header RCM across different rate buckets according to taxable share. If an invoice has multiple RCM items with differing rates (e.g. 5% and 18%), proportional allocation distorts rate-wise tax amounts.
- **Trigger / Repro**: Create an invoice with mixed-rate RCM items; generate GSTR-3B table 3.1(d).
- **Consequence**: Rate-wise RCM numbers reported in GST returns diverge from actual line items.
- **Code Evidence**: `backend/reporting/gst_returns.py:305-320`.
- **Suggested Fix Direction**: Read line-level RCM tax attributes directly rather than prorating header memo values.
- **Test to Add**: `test_gstr_returns_mixed_rate_rcm_buckets_match_lines`.
- **Twin Check (Sales)**: Document totals write path.

---

### CR-054: Rate Exposure Scan Ignores `TAX` and `RETAIL` Invoices and Opening Balances
- **Module**: Reporting / GST
- **Location**: [`backend/reporting/gst_rate_scan.py:22-30`](file:///e:/Bizboard/backend/reporting/gst_rate_scan.py#L22-L30)
- **Type**: Bug / Incomplete Audit
- **Severity**: Medium
- **What's wrong**: `gst_rate_scan` filters strictly on `invoice__invoice_type == InvoiceType.GST`, ignoring `TAX` and `RETAIL` invoices. It also fails to exclude opening balance invoices or include credit/debit notes.
- **Trigger / Repro**: Retail POS invoices with invalid tax rates are scanned; scanner reports 0 violations.
- **Consequence**: Rate anomalies in retail sales bypass automated rate audits.
- **Code Evidence**: `backend/reporting/gst_rate_scan.py:25`.
- **Suggested Fix Direction**: Filter `invoice__invoice_type__in=["GST", "TAX", "RETAIL"]`.
- **Test to Add**: `test_gst_rate_scan_covers_retail_invoices`.
- **Twin Check (Purchase)**: Purchase rate exposure scan.

---

### CR-055: Unscoped Secondary Lookups in Reporting Services and Ledgers (Defense-in-Depth Leak)
- **Module**: Reporting / Security
- **Location**: [`backend/reporting/services.py:534-539, 893-903`](file:///e:/Bizboard/backend/reporting/services.py#L534-L539), [`backend/accounting/reports.py:467`](file:///e:/Bizboard/backend/accounting/reports.py#L467)
- **Type**: Multi-Tenant / Defense-in-Depth
- **Severity**: Low
- **What's wrong**: Lookups for `Product`, `Warehouse`, `SalesCreditNote`, `SalesDebitNote`, and `Account` filter by primary keys or invoice IDs without explicitly adding `company=company`.
- **Trigger / Repro**: Inspect ORM queries generated by `inventory_summary` and `bulk_sales_invoice_outstanding`.
- **Consequence**: Breaks tenant defense-in-depth isolation standards.
- **Code Evidence**: `backend/reporting/services.py:537` (`Product.objects.filter(pk__in=orphan_product_ids)` lacks `company=company`).
- **Suggested Fix Direction**: Add explicit `company=company` to all secondary ORM lookups.
- **Test to Add**: `test_reporting_lookups_enforce_company_isolation`.
- **Twin Check (Sales)**: Verify multi-tenant filtering on sales services.

---

## 8. Module 6: Accounting & Ledgers Findings (`CR-056` – `CR-063`)

### CR-056: `PostingService.reverse()` Causes Negative Double-Reversal in GL
- **Module**: Accounting
- **Location**: [`backend/accounting/services.py:1790-1820`](file:///e:/Bizboard/backend/accounting/services.py#L1790-L1820), [`backend/accounting/reports.py:13`](file:///e:/Bizboard/backend/accounting/reports.py#L13)
- **Type**: Accounting / Data-integrity
- **Severity**: Critical (Release-Blocking)
- **What's wrong**: `PostingService.reverse(entry)` creates an offsetting journal entry with inverted debits/credits and sets the reversal's status to `POSTED`. It then flips the original entry's status to `REVERSED`. However, all GL balance queries (`reports._balances`, `trial_balance`, `profit_and_loss`, `balance_sheet`) filter strictly by `entry__status=JournalEntry.Status.POSTED`. As a result, the original entry is excluded, while the negative reversal entry is included! Reversing an entry creates a negative balance instead of zeroing it out. When amending an invoice from ₹1,000 to ₹1,200 via `adjust_sales_invoice_postings()`, the GL sees -₹1,000 + ₹1,200 = ₹200 net balance instead of ₹1,200.
- **Trigger / Repro**:
  1. Complete an invoice for ₹1,000 (Dr 1200 AR ₹1,000 / Cr 4100 Sales ₹1,000).
  2. Cancel or amend the invoice.
  3. Query Trial Balance or Balance Sheet.
- **Consequence**: Cancelling any invoice turns AR and Sales into negative balances in the GL. Financial statements are completely invalid.
- **Code Evidence**:
  `backend/accounting/services.py`:
  ```python
  1815: reversal = cls.post(..., purpose="REVERSE", ...)
  1817: entry.reversed_entry = reversal
  1818: entry.status = JournalEntry.Status.REVERSED
  1819: entry.save(update_fields=["reversed_entry", "status", "updated_at"])
  ```
  `backend/accounting/reports.py`:
  ```python
  13: qs = JournalLine.objects.filter(entry__company=company, entry__status=JournalEntry.Status.POSTED)
  # Excludes Status.REVERSED!
  ```
- **Suggested Fix Direction**: Either do not set `entry.status = Status.REVERSED` when a reversal entry is posted (so both credit and debit cancel to zero), or update all GL reports to query `status__in=[Status.POSTED, Status.REVERSED]`.
- **Test to Add**: `test_journal_reversal_balances_to_zero_in_trial_balance`.
- **Twin Check (Purchase)**: Purchase invoice cancellation causes the exact same negative double-reversal in AP.

---

### CR-057: `SalesInvoice.cancel()` Bypasses GL Reversal, Leaving Posted Revenue and AR
- **Module**: Accounting / Sales
- **Location**: [`backend/sales/services.py:1081-1278`](file:///e:/Bizboard/backend/sales/services.py#L1081-L1278)
- **Type**: Accounting / Data-integrity
- **Severity**: Critical (Release-Blocking)
- **What's wrong**: `SalesInvoice.cancel()` cancels the invoice in the operational layer and restores inventory, but **never calls `PostingService.reverse()`**. The sales journal entry remains `POSTED` in the GL forever. The operational ledger and general ledger immediately and permanently diverge.
- **Trigger / Repro**: Enable accounting; complete a sales invoice; cancel the sales invoice; check GL Account 4100 (Sales) and 1200 (AR).
- **Consequence**: Cancelled sales remain recognized as revenue and accounts receivable in financial statements.
- **Code Evidence**: In `backend/sales/services.py:1081-1278`, `PostingService.reverse` is never called. (In contrast, `backend/purchases/services.py:899-905` explicitly loops over `JournalEntry` and reverses them).
- **Suggested Fix Direction**: Add the GL reversal loop in `SalesService.cancel`:
  ```python
  if invoice.company.accounting_enabled:
      for entry in JournalEntry.objects.filter(company=invoice.company, source_type="SALES_INVOICE", source_id=invoice.id, status=JournalEntry.Status.POSTED):
          PostingService.reverse(entry, user)
  ```
- **Test to Add**: `test_sales_invoice_cancel_reverses_gl_entry`.
- **Twin Check (Purchase)**: `PurchasesService.cancel` implements this correctly.

---

### CR-058: Cross-Tenant Account and Bank Injection in `FixedAsset`, `Account`, and `CostCenter` Serializers
- **Module**: Accounting / Security
- **Location**: [`backend/accounting/serializers.py:223-238, 10-15, 75-79`](file:///e:/Bizboard/backend/accounting/serializers.py#L223-L238)
- **Type**: Multi-Tenant Security / IDOR
- **Severity**: Critical (Release-Blocking)
- **What's wrong**:
  1. `FixedAssetSerializer` defines `asset_account`, `accumulated_depreciation_account`, and `depreciation_expense_account` as default `PrimaryKeyRelatedField(queryset=Account.objects.all())` without tenant validation. A tenant can inject foreign account IDs.
  2. `AccountSerializer` uses un-scoped fields for `parent` and `bank_account`. A tenant can attach their GL account to another company's `BankAccount`.
  3. `CostCenterSerializer` uses un-scoped `parent` over all `CostCenter` records.
- **Trigger / Repro**: Submit a `FixedAsset` with `asset_account` pointing to another company's GL account ID.
- **Consequence**: Cross-tenant data injection; asset depreciation and disposal post journal entries referencing foreign tenant accounts.
- **Code Evidence**: `backend/accounting/serializers.py:223-238`.
- **Suggested Fix Direction**: Wrap all account and bank ForeignKeys in `CompanyPrimaryKeyRelatedField`.
- **Test to Add**: `test_fixed_asset_rejects_cross_tenant_accounts`.
- **Twin Check (Sales)**: Serializer foreign key scoping.

---

### CR-059: Derived-Ledger Claim in Documentation is Dead Code (`_use_gl_outstanding` Returns False)
- **Module**: Accounting / Ledgers
- **Location**: [`backend/ledgers/services.py:283-290, 488-496`](file:///e:/Bizboard/backend/ledgers/services.py#L283-L290)
- **Type**: Architecture / Dead Code
- **Severity**: High
- **What's wrong**: Documentation in `backend/ledgers/services.py` claims that when `company.accounting_enabled` is True and `outstanding_basis == GL_WHEN_BOOKS`, party balances are derived from GL accounts 1200/2300 and 2100/1250. However, `LedgerService._use_gl_outstanding()` is hardcoded to `return False`. Party ledgers always query operational documents, and GL party statement generation (`_gl_party_statement`) is entirely unreachable dead code.
- **Trigger / Repro**: Enable `accounting_enabled` and set `outstanding_basis = GL_WHEN_BOOKS`. Query customer statement.
- **Consequence**: Architectural desynchronization. If manual journal adjustments (bad debt write-offs, dispute adjustments) are made in the GL, customer statements will never reflect them.
- **Code Evidence**:
  `backend/ledgers/services.py`:
  ```python
  283: @staticmethod
  284: def _use_gl_outstanding(company) -> bool:
  285:     return False # Hardcoded dead code
  ```
- **Suggested Fix Direction**: Either deprecate and remove `_gl_party_statement` and clarify that Bizboard uses document-derived subledgers exclusively, or properly wire the GL-based statement switch.
- **Test to Add**: `test_customer_statement_party_reconciliation`.
- **Twin Check (Purchase)**: Supplier ledger statements.

---

### CR-060: Unrestricted Manual Journal Posting to Control Accounts (1200, 2100, 2300, 1250)
- **Module**: Accounting
- **Location**: [`backend/accounting/serializers.py:81-92`](file:///e:/Bizboard/backend/accounting/serializers.py#L81-L92), [`backend/accounting/views.py:238-246`](file:///e:/Bizboard/backend/accounting/views.py#L238-L246)
- **Type**: Data Integrity / Control Bypass
- **Severity**: High
- **What's wrong**: Neither `JournalLineSerializer` nor `JournalViewSet` restricts manual journal postings to control accounts (`is_control=True`: `1200` AR, `2100` AP, `2300` Customer Advances, `1250` Supplier Advances). A user can create manual journal entries directly against AR or AP. This alters GL balances without creating underlying documents, causing permanent unresolvable drift between the GL and subledgers.
- **Trigger / Repro**: Post a manual journal entry debiting Account 1200 (AR) and crediting Account 4100 (Sales).
- **Consequence**: `DOCS_GL_AR_MISMATCH` health violation; subledger-to-GL reconciliation is permanently destroyed.
- **Code Evidence**: `backend/accounting/serializers.py:81-92`: lacks control account validation.
- **Suggested Fix Direction**: In `JournalLineSerializer.validate_account()`, reject accounts where `account.is_control is True` for manual journals.
- **Test to Add**: `test_manual_journal_rejects_control_accounts`.
- **Twin Check (Sales)**: Direct adjustments to invoices.

---

### CR-061: Payment and Receipt Voiding Checks Original Document Date with `allow_soft_closed=False`
- **Module**: Accounting / Payments
- **Location**: [`backend/payments/services.py:538, 567`](file:///e:/Bizboard/backend/payments/services.py#L538)
- **Type**: Defective Period Gate
- **Severity**: High
- **What's wrong**: In `void_customer_receipt` and `void_supplier_payment`, the methods assert period gates using the original document date (`rec.receipt_date` / `pay.payment_date`) with `allow_soft_closed=False`. Furthermore, they do not pass an `entry_date` to `_reverse_money_document_journal`, causing `PostingService.reverse` to fall back to the original document date. If a historical payment was recorded in a period that has since been soft-closed, voiding is completely blocked.
- **Trigger / Repro**: Attempt to void a receipt whose `receipt_date` falls in a soft-closed period.
- **Consequence**: Users cannot void disputed or bounced checks/receipts from prior periods.
- **Code Evidence**: `backend/payments/services.py:538, 567`.
- **Suggested Fix Direction**: Pass `allow_soft_closed=True` or stamp the reversal on `entry_date = timezone.localdate()`.
- **Test to Add**: `test_void_receipt_in_soft_closed_period_succeeds_with_current_date_reversal`.
- **Twin Check (Purchase)**: Supplier payment voiding.

---

### CR-062: Supplier Payment TDS Fails to Call `fold_tds_from_rate()` and Omits Audit Logging
- **Module**: Accounting / Payments
- **Location**: [`backend/payments/services.py:338-343`](file:///e:/Bizboard/backend/payments/services.py#L338-L343)
- **Type**: Statutory / Missing-logging
- **Severity**: Medium
- **What's wrong**: `record_supplier_payment` accepts `tds_amount` and `tds_rate`, but reads `tds_amt = Decimal(str(tds_amount or 0))`. It never invokes `fold_tds_from_rate()` and does not generate `_tds_override` statutory audit logs when rate and amount diverge.
- **Trigger / Repro**: Record a supplier payment with `tds_rate=2.0` and custom `tds_amount`; inspect audit log.
- **Consequence**: Missing statutory audit trail on Section 194C/194J TDS deductions.
- **Code Evidence**: `backend/payments/services.py:338-343`.
- **Suggested Fix Direction**: Invoke `fold_tds_from_rate()` in `record_supplier_payment`.
- **Test to Add**: `test_supplier_payment_tds_audit_logging`.
- **Twin Check (Sales)**: Sales TCS override logging.

---

### CR-063: Inconsistent Period Gate Assertion on Credit/Debit Note Cancellation
- **Module**: Accounting / Statutory
- **Location**: [`backend/sales/notes_services.py:326, 501`](file:///e:/Bizboard/backend/sales/notes_services.py#L326) vs [`backend/purchases/notes_services.py:361, 542`](file:///e:/Bizboard/backend/purchases/notes_services.py#L361)
- **Type**: Logic Inconsistency
- **Severity**: Medium
- **What's wrong**: While `SalesService.cancel` and `PurchasesService.cancel` pass `allow_soft_closed=True` when voiding invoices, `SalesNotesService.cancel_credit_note`, `cancel_debit_note`, `PurchaseNotesService.cancel_credit_note`, and `cancel_debit_note` call `assert_period_allows_money_amend` with `allow_soft_closed=False`. Voiding an invoice in a soft-closed period succeeds, but voiding a credit note against that same invoice fails.
- **Trigger / Repro**: Cancel a credit note in a soft-closed period.
- **Consequence**: Inconsistent period gate enforcement across document types.
- **Code Evidence**: `backend/sales/notes_services.py:326`.
- **Suggested Fix Direction**: Standardize on `allow_soft_closed=True` across document cancellations.
- **Test to Add**: `test_credit_note_cancel_in_soft_closed_period`.
- **Twin Check (Sales vs Purchase)**: Both sales and purchase notes suffer from this inconsistency.

---

## 9. Cross-Cutting Themes

### 9.1 Transaction Boundaries & Atomicity
Across the platform, multi-step operations are repeatedly implemented as separate HTTP round-trips from the frontend instead of atomic backend procedures. This is prominent in POS checkout (`CR-003`), where create $\to$ complete $\to$ receipt $\to$ allocate can half-succeed, leaving invoices completed with inventory deducted but marked unpaid. Similarly, in purchase invoice creation and number generation (`CR-025`), document sequence numbers are burned before multi-GSTIN validation and tax recomputation succeed.

### 9.2 Durable Idempotency Scopes & Lifecycles
`backend/core/idempotency.py` provides robust `MONEY_IDEMPOTENCY_SCOPES` protection, but its lifecycle integration is incomplete:
- When draft documents are deleted (`CR-001`), `forget_record` is never called. Subsequent creates with the same key replay the deleted ID, triggering permanent 404 loops.
- `PaymentAllocationViewSet.unallocate` (`CR-009`) mutates financial ledgers but completely lacks idempotency protection.

### 9.3 Multi-Tenant Scoping in Serializers
While services consistently enforce tenant checks, serializers frequently declare ForeignKeys using default un-scoped `PrimaryKeyRelatedField(queryset=Model.objects.all())`:
- `SalesItemSerializer.batch` (`CR-008`)
- `CustomerReceiptSerializer.bank_account` (`CR-008`)
- `SalesCreditNoteSerializer.company_gstin` (`CR-020`)
- `PurchaseCreditNoteItemSerializer.source_item` (`CR-029`)
- `FixedAssetSerializer` asset accounts (`CR-058`)
- `AccountSerializer.bank_account` (`CR-058`)
- `CostCenterSerializer.parent` (`CR-058`)  
This creates cross-tenant IDOR vulnerabilities and existence enumeration oracles.

### 9.4 Closed-Period Guard Inconsistencies
`assert_period_allows_money_amend` is Bizboard's central financial gate, but its application is erratic:
- Invoices allow cancellation in soft-closed periods, while Credit/Debit notes reject cancellation (`CR-063`).
- Payment and receipt voiding routines fail to pass `allow_soft_closed=True` and omit reversal dates (`CR-061`).
- Stock count adjustments evaluate the current system date instead of `counted_on` (`CR-040`).

### 9.5 Dual-Ledger Invariant & GL Reversal Flaws
Bizboard claims document-derived subledgers with an optional GL. However:
- `PostingService.reverse()` contains a critical flaw (`CR-056`) where the original entry is marked `REVERSED` and omitted from reports, turning document reversals into negative double-reversals.
- `SalesInvoice.cancel()` never calls `PostingService.reverse()` (`CR-057`), leaving cancelled sales in the GL forever.
- Manual journals can be posted directly to control accounts (`CR-060`), permanently desynchronizing GL and subledgers.

### 9.6 Frontend Cache Invalidation
Across TanStack Query mutations in the web app, developers invalidate only the primary document detail query while neglecting related list queries, customer balances, product stock counts, and dashboard KPIs (`CR-013`, `CR-031`, `CR-032`, `CR-033`). Users are forced to manually refresh their browsers to view updated balances and stock.

---

## 10. Master Issue Cross-Reference

| Code Review ID | Module | Title | Severity | Existing Register / Bug ID | Status |
| :--- | :--- | :--- | :---: | :---: | :---: |
| **CR-001** | POS | Idempotency record poisoning on draft deletion | Critical | `BB-000610` / `CR-120` | **NEW RELEASE BLOCKER** |
| **CR-002** | POS | Physical sale drop on concurrent negative stock under BLOCK | Critical | `CR-054` / `BB-000491` | **NEW RELEASE BLOCKER** |
| **CR-003** | POS | Non-atomic 4-roundtrip checkout choreography | High | `BB-000268` / `CR-118` | **NEW RELEASE BLOCKER** |
| **CR-004** | POS | Race between outbox flush and counter checkout | High | `CR-119` | **NEW RELEASE BLOCKER** |
| **CR-005** | POS | Silent thermal PDF print failure (state unrendered) | Medium | — | **NEW DEFECT** |
| **CR-006** | POS | Tendered cash overpayment discarded from accounting | Medium | — | **NEW DEFECT** |
| **CR-007** | POS | Shared POS IndexedDB outbox cross-tenant data leak | Medium | `SEC-012` | **NEW DEFECT** |
| **CR-008** | POS | Serializer foreign key cross-tenant existence enumeration | Low | `SEC-008` | **NEW DEFECT** |
| **CR-009** | POS | Allocation unallocate missing idempotency scope | Medium | `B4-006` | **NEW DEFECT** |
| **CR-010** | Sales | Same-state SEZ supplies treated as intra-state | Critical | `GST-041` | **NEW RELEASE BLOCKER** |
| **CR-011** | Sales | Sales return over-reverses allocation without re-allocating remainder | Critical | `CR-146` | **NEW RELEASE BLOCKER** |
| **CR-012** | Sales | In-flight e-invoice bypasses IRN guard on cancellation | Critical | `IRN-003` | **NEW RELEASE BLOCKER** |
| **CR-013** | Sales | Direct `set_items` amends completed invoices without IRN guard | High | `IRN-001` | **NEW DEFECT** |
| **CR-014** | Sales | Recurring invoice stale catch-up loop state desync | High | `REC-002` | **NEW DEFECT** |
| **CR-015** | Sales | UTC timezone shift on recurring schedule `anchor_day` in IST | High | `REC-003` | **NEW DEFECT** |
| **CR-016** | Sales | Draft sales order editable after conversion to invoice/challan | High | `SO-014` | **NEW DEFECT** |
| **CR-017** | Sales | Invoice cancel leaves delivery challan locked to cancelled invoice | High | `CR-126` | **NEW DEFECT** |
| **CR-018** | Sales | Partial sales order conversion terminates order and releases stock | High | `SO-015` | **NEW DEFECT** |
| **CR-019** | Sales | AB-BA deadlock between receipt allocation and credit note | High | `B4-006` | **NEW DEFECT** |
| **CR-020** | Sales | Cross-tenant `company_gstin` unvalidated in credit note serializer | High | `SEC-009` | **NEW DEFECT** |
| **CR-021** | Sales | Bulk line create bypasses string length validations (500 crash) | Medium | `DB-018` | **NEW DEFECT** |
| **CR-022** | Sales | Frontend missing query invalidation on invoice transitions | Medium | `UI-044` | **NEW DEFECT** |
| **CR-023** | Purchase | `PurchaseService.complete` crashes on service/non-stock items | Critical | `PUR-018` | **NEW RELEASE BLOCKER** |
| **CR-024** | Purchase | FIFO cost layer recorded at gross price ignoring line discounts | Critical | `COGS-009` | **NEW RELEASE BLOCKER** |
| **CR-025** | Purchase | Document number allocated before GSTIN validation | High | `DOC-004` | **NEW DEFECT** |
| **CR-026** | Purchase | Purchase return crashes on service/non-stock items | High | `PUR-019` | **NEW DEFECT** |
| **CR-027** | Purchase | FIFO layer restamp on price amend corrupts alternate unit costs | High | `COGS-010` | **NEW DEFECT** |
| **CR-028** | Purchase | Purchase credit/debit notes use deprecated `resolve_series_gstin` | Medium | `DOC-005` | **NEW DEFECT** |
| **CR-029** | Purchase | Unscoped `source_item` in purchase notes serializers | High | `SEC-010` | **NEW DEFECT** |
| **CR-030** | Purchase | `SupplierPaymentViewSet` crashes on non-numeric supplier filter | Medium | `API-031` | **NEW DEFECT** |
| **CR-031** | Purchase | `NewPurchasePage` fails to invalidate product stock queries | High | `UI-045` | **NEW DEFECT** |
| **CR-032** | Purchase | `SupplierPaymentsPage` fails to invalidate purchase invoice cache | High | `UI-046` | **NEW DEFECT** |
| **CR-033** | Purchase | `PurchaseReturnsPage` fails to invalidate credit notes and stock | High | `UI-047` | **NEW DEFECT** |
| **CR-034** | Purchase | Missing file SHA-256 duplicate detection on bill upload | Medium | `IMP-014` | **NEW DEFECT** |
| **CR-035** | Purchase | Purchase TDS exclusivity check runs before rate folding | High | `TDS-008` | **NEW DEFECT** |
| **CR-036** | Stock | `ExpiryAlertsView.post` fails when writing off expired lots | Critical | `INV-022` | **NEW RELEASE BLOCKER** |
| **CR-037** | Stock | `default_warehouse` aborts transaction on concurrent IntegrityError | Critical | `INV-023` | **NEW RELEASE BLOCKER** |
| **CR-038** | Stock | Valuation snapshot replay collapses FIFO into WAVG | Critical | `COGS-011` | **NEW RELEASE BLOCKER** |
| **CR-039** | Stock | `rebuild_balance` can overwrite concurrent movements without locking | High | `CR-054` | **NEW DEFECT** |
| **CR-040** | Stock | Closed-period check in stock count uses current date | High | `PERIOD-009` | **NEW DEFECT** |
| **CR-041** | Stock | Stock transfer under WARN allows transfer of non-existent stock | Medium | `INV-024` | **NEW DEFECT** |
| **CR-042** | Stock | No automated background reconciliation for stock balance drift | Medium | `CR-054` | **NEW DEFECT** |
| **CR-043** | Reporting | Asymmetric return handling double-deducts purchases MTD | Critical | `REP-025` | **NEW RELEASE BLOCKER** |
| **CR-044** | Reporting | Dashboard AR/AP aging drops opening balances and unlinked notes | Critical | `CR-146` | **NEW RELEASE BLOCKER** |
| **CR-045** | Reporting | Missing upper date bounds on MTD aggregates absorbs post-dated bills | Critical | `REP-026` | **NEW RELEASE BLOCKER** |
| **CR-046** | Reporting | Stock valuation report reads stale running cost cache | Critical | `REP-027` | **NEW RELEASE BLOCKER** |
| **CR-047** | Reporting | In-memory buffering across all export views (OOM risk) | High | `PERF-014` | **NEW DEFECT** |
| **CR-048** | Reporting | Missing pagination on financial registers for full-year spans | High | `PERF-015` | **NEW DEFECT** |
| **CR-049** | Reporting | O(N) query and save loop in IMS classification | High | `PERF-016` | **NEW DEFECT** |
| **CR-050** | Reporting | Missing branch/GSTIN scoping in `Gstr2bIngest` causes collisions | High | `GSTR-018` | **NEW DEFECT** |
| **CR-051** | Reporting | Dropping unlinked matched 2B rows when branch filter applied | Medium | `GSTR-019` | **NEW DEFECT** |
| **CR-052** | Reporting | Incomplete document coverage in TDS/TCS worksheets | Medium | `TDS-009` | **NEW DEFECT** |
| **CR-053** | Reporting | RCM tax reallocation distorts rate-wise tax amounts | Medium | `GST-042` | **NEW DEFECT** |
| **CR-054** | Reporting | Rate exposure scan ignores retail invoices and opening balances | Medium | `GST-043` | **NEW DEFECT** |
| **CR-055** | Reporting | Unscoped secondary lookups in reporting and ledgers | Low | `SEC-011` | **NEW DEFECT** |
| **CR-056** | Accounting | `PostingService.reverse()` causes negative double-reversal in GL | Critical | `GL-032` | **NEW RELEASE BLOCKER** |
| **CR-057** | Accounting | `SalesInvoice.cancel()` bypasses GL reversal | Critical | `GL-033` | **NEW RELEASE BLOCKER** |
| **CR-058** | Accounting | Cross-tenant account injection in fixed asset and account serializers | Critical | `SEC-013` | **NEW RELEASE BLOCKER** |
| **CR-059** | Accounting | Derived-ledger claim in documentation is dead code | High | `CR-146` | **NEW DEFECT** |
| **CR-060** | Accounting | Unrestricted manual journal posting to control accounts | High | `GL-034` | **NEW DEFECT** |
| **CR-061** | Accounting | Payment/receipt voiding blocks in soft-closed periods | High | `PERIOD-010` | **NEW DEFECT** |
| **CR-062** | Accounting | Supplier payment TDS omits rate fold and override audit logging | Medium | `TDS-010` | **NEW DEFECT** |
| **CR-063** | Accounting | Inconsistent period gate assertion on note cancellation | Medium | `PERIOD-011` | **NEW DEFECT** |
