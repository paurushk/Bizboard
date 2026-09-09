# POS release-blocking code review

## Summary

### Flow Coverage
| Flow | Coverage & Analysis |
|---|---|
| **Write path** | Multi-round-trip HTTP chain: client creates draft invoice (`sales_invoice_create`) → completes invoice (`sales_invoice_complete`, decrementing stock & posting GL) → creates customer receipt (`receipt_create`) → creates payment allocation (`allocation_create`) → downloads thermal PDF (`GET /api/v1/sales/invoices/{id}/thermal-pdf/`). Each mutation runs under an independent server-side `transaction.atomic` boundary; failure during receipt creation or allocation leaves an open, completed, unpaid invoice. Offline POS enqueues to an IndexedDB outbox; `flushPosDraft` sequentially replays create, complete, receipt, and allocation with derived idempotency keys (`${key}`, `${key}-complete`, `${key}-receipt`, `${key}-alloc`). |
| **Reversal path** | POS has no in-flow counter void or cancellation endpoint. Cancelling an invoice must be performed via the back-office sales interface (`SalesService.cancel`), which restores inventory via append-only `MovementType.ADJUSTMENT` entries and strictly blocks cancellation if active payment allocations exist. Counter returns and customer refunds are handled outside POS via the `SalesReturn` and Credit Note module. |
| **Concurrency** | Counter oversell concurrency under `negative_stock_policy=BLOCK` is protected by row-level locking on `StockBalance.objects.select_for_update()` inside `InventoryService.post_movement`. Two counter terminals attempting to sell the final unit concurrently will serialize on the balance lock; the second transaction encounters `balance.available + delta < 0` and raises a `BusinessRuleError`. Under `WARN` policy, both sales succeed and balance is allowed to go negative. |
| **Tests present** | Thermal PDF rendering and synchronous endpoint tests exist (`test_pdf_and_share.py`); stock oversell blocking is verified under concurrent threads (`test_concurrent_stock_oversell_blocked`); frontend outbox and status helpers are unit-tested (`posStatus.test.ts`, `flushPosCheckout.test.ts`, `invoiceDraftCache.test.ts`). Missing end-to-end integration tests: online cash retry after mid-flow receipt failure (`pos_online_cash_retry_after_receipt_failure_does_not_double_complete`), checkout half-success matrix tests, role permission check for cashier without payment rights, and offline walk-in customer retry deduplication. |

### Counts by Severity
| Severity | Count | Findings |
|---|:---:|---|
| **Critical** | 1 | POS-001 |
| **High** | 3 | POS-002, POS-003, POS-004 |
| **Medium** | 6 | POS-005, POS-006, POS-007, POS-008, POS-009, POS-010 |
| **Low** | 3 | POS-011, POS-012, POS-013 |
| **Total** | **13** | |

---

### POS-001 — Online cash retry remints idempotency key after partial success
- **Module:** POS -> checkout / cash path
- **Location:** `web/src/pages/pos/PosPage.tsx:874` (function `checkout`); `:642–676` (`performCashCheckout`); `:556–637` (`createCompletedInvoice`)
- **Type:** Data-integrity
- **Severity:** Critical
- **What's wrong:** Every Cash click calls `userGestureIdempotencyKey()` and never reuses `idempotencyKey` state. If `create`+`complete` succeed and `createReceipt` / `createAllocation` fail (or response is lost), the cart remains and a retry starts a **new** sale. UPI `confirmUpiPayment` correctly reuses `${upiPending.key}-receipt`; offline `flushPosDraft` uses stable derived keys — cash online does not.
- **Trigger / repro:** Complete succeeds; kill network before receipt; click Cash Pay again with same cart.
- **Consequence:** Second COMPLETED invoice + second stock decrement; first invoice often left unpaid (or first has unallocated receipt if alloc failed).
- **Code evidence:** `const key = userGestureIdempotencyKey();` on every checkout; recovery/`unpaidRecover` only on unknown complete status, not on receipt/alloc failure.
- **Suggested fix direction:** Persist one sale gesture key (outbox even when online); on retry reuse create/complete/receipt/alloc keys; if complete already done, skip to receipt/alloc and surface unpaid recover — never mint a new family after stock posted.
- **Test to add:** `pos_online_cash_retry_after_receipt_failure_does_not_double_complete`
- **Twin check:** Sales/Purchase equivalent — same bug? y (any multi-step pay-after-complete UI that remints keys)

### POS-002 — Sale settlement is multi round-trip, not one server transaction
- **Module:** POS -> sales + payments
- **Location:** `web/src/pages/pos/PosPage.tsx:648–669`; `web/src/offline/flushPosCheckout.ts:44–134`; `backend/sales/services.py:690` (`SalesService.complete`); `backend/payments/services.py:226` / `:390`
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** POS MVP chains separate HTTP calls, each with its own `transaction.atomic`: invoice create → complete (stock+GL) → receipt → allocation → thermal GET. There is no server “POS checkout” that commits money+stock together.
- **Trigger / repro:** Fail any step after complete (receipt 5xx, alloc validation, client crash).
- **Consequence:** Valid COMPLETED unpaid invoices, or posted unallocated receipts; cashier UX must recover manually. Amplifies POS-001.
- **Code evidence:** Four distinct service entrypoints; complete ends before `PaymentService.create_receipt`.
- **Suggested fix direction:** Prefer a single authenticated `POS checkout` (or receipt+allocate-in-complete) under one idempotency scope; until then, durable client resume (POS-001) is mandatory.
- **Test to add:** `pos_checkout_half_success_matrix_complete_ok_receipt_fail`
- **Twin check:** Sales/Purchase equivalent — same bug? y (invoice complete then separate receipt is the shared pattern)

### POS-003 — POS nav/route ignores `canCreatePayments` while receipt APIs require it
- **Module:** POS -> permissions / feature gate
- **Location:** `web/src/navigation/menu.ts:46`; `web/src/App.tsx:264–266`; `backend/payments/views.py:125–127` (`CustomerReceiptViewSet.get_permissions`); `backend/sales/views.py:87–90`
- **Type:** Broken-feature
- **Severity:** High
- **What's wrong:** POS is shown when `canCreateSales` only. Receipt/allocation create needs `CanCreatePayments`. A membership with sales create and payments create revoked can complete (stock out) then get 403 on receipt.
- **Trigger / repro:** User with `can_create_sales=True`, `can_create_payments=False`; run cash POS.
- **Consequence:** Completed unpaid sale; stock gone; cashier blocked from finishing payment in POS.
- **Code evidence:** `allowPos` / menu use `canCreateSales` only; receipt create returns `CanCreatePayments()`.
- **Suggested fix direction:** Gate POS on `canCreateSales && canCreatePayments` (and optionally block complete if payments capability missing for RETAIL/POS flows).
- **Test to add:** `pos_hidden_without_can_create_payments` + API 403 after complete for that role
- **Twin check:** Sales/Purchase equivalent — same bug? n (New Invoice does not auto-receipt)

### POS-004 — Offline walk-in customer create not bound to draft → duplicate parties on flush retry
- **Module:** POS -> offline flush
- **Location:** `web/src/offline/flushPosCheckout.ts:23–30`; `web/src/pages/pos/PosPage.tsx:877–897` (enqueue with `customerId` optional)
- **Type:** Bug
- **Severity:** High
- **What's wrong:** Flush does `createCustomer(pendingName)` when `customerId` is missing, but never writes the new id back onto the outbox draft before invoice create. A failure after customer create and before durable invoice idempotency success retries create another customer with the same name.
- **Trigger / repro:** Offline sale with typed name only; flush creates customer; fail before invoice create stores; flush again.
- **Consequence:** Orphan duplicate customers; messy AR/GST party master on shared counters.
- **Code evidence:** Local `customerId = created.id` only; `enqueueDraft` / draft row unchanged.
- **Suggested fix direction:** Idempotent customer create keyed by draft key, or `updateDraft({ customerId })` before invoice create.
- **Test to add:** `flushPosDraft_pending_customer_retry_does_not_duplicate_customer`
- **Twin check:** Sales/Purchase equivalent — same bug? n-a

### POS-005 — Thermal PDF failure is silently swallowed
- **Module:** POS -> receipt print
- **Location:** `web/src/pages/pos/PosPage.tsx:503–510` (`finishSale`)
- **Type:** Silent-failure
- **Severity:** Medium
- **What's wrong:** `downloadInvoiceThermalPdf` errors are caught with an empty block; sale still shows success. Backend correctly 400s drafts (`backend/sales/views.py:411–413`).
- **Trigger / repro:** Complete+pay OK; thermal endpoint 500 / offline; or print blocked.
- **Consequence:** Cashier thinks bill printed; customer leaves without slip; no in-app retry CTA.
- **Code evidence:** `catch { // Thermal print fallback }` with no message/flag.
- **Suggested fix direction:** Surface non-blocking warning + “Print again” using invoice id (already known).
- **Test to add:** `finishSale_thermal_failure_surfaces_warning`
- **Twin check:** Sales/Purchase equivalent — same bug? n (history PDF usually surfaces errors)

### POS-006 — Offline flush success does not print thermal receipts
- **Module:** POS -> offline sync
- **Location:** `web/src/pages/pos/PosPage.tsx:748–774` (`flushPendingDraft`); `web/src/offline/flushPosCheckout.ts` (ends after allocate)
- **Type:** Broken-feature
- **Severity:** Medium
- **What's wrong:** Successful outbox flush clears cart and shows sync count only; no thermal download/print for flushed invoices.
- **Trigger / repro:** Offline cash sale → online → auto flush.
- **Consequence:** Offline-originated sales routinely have no counter slip unless cashier finds them in history.
- **Code evidence:** `flushPosDraft` has no PDF step; flush success path only sets message.
- **Suggested fix direction:** Return completed ids from flush and print (or queue print) per sale; or open history links.
- **Test to add:** `flushPendingDraft_triggers_thermal_for_each_flushed_sale`
- **Twin check:** Sales/Purchase equivalent — same bug? n-a

### POS-007 — Tender gate uses client-computed totals; receipt books server `grandTotal`
- **Module:** POS -> tax / cash tender
- **Location:** `web/src/pages/pos/PosPage.tsx:367–382`, `:849–851`, `:648–667`; server recompute in `backend/sales/services.py:799–809`
- **Type:** Missing-validation
- **Severity:** Medium
- **What's wrong:** Cash tender check compares `tenderedAmount` to **client** `totals.grandTotal`. Receipt/allocation use **server** `completed.grandTotal` after complete-time GSTIN/POS recompute. No `preview-totals` call before pay.
- **Trigger / repro:** Client/server tax split diverge (blank POS edge, inclusive extraction, cess); tender exactly client total; server total higher.
- **Consequence:** Till short vs books, or unexpected receipt amount vs cash taken; change display lies relative to posted total.
- **Code evidence:** Tender check before API; `amount: invoiceTotal` from completed invoice after.
- **Suggested fix direction:** Authoritative preview (or complete-first then tender against returned total) before taking cash.
- **Test to add:** `pos_tender_uses_server_preview_grand_total`
- **Twin check:** Sales/Purchase equivalent — same bug? y (any client-tax pay gate)

### POS-008 — `ENABLE_POS` is UI-only; sales money APIs ungated
- **Module:** POS -> feature flags
- **Location:** `backend/config/settings.py:849`; `backend/core/services/feature_flags.py:29–47`; contrast `backend/manufacturing/permissions.py:7–8`; frontend `web/src/config/features.ts:101–102`, `web/src/pages/pos/PosPage.tsx:133–135`
- **Type:** Improvement
- **Severity:** Medium
- **What's wrong:** Checklist requires nav vs API flag consistency. Manufacturing denies API when flag off; POS flag only hides route/nav. RETAIL complete/receipt remain callable with normal sales/payment perms when POS is “disabled.”
- **Trigger / repro:** `ENABLE_POS=false` for company; POST sales invoice complete + receipt as staff.
- **Consequence:** Flag does not actually disable counter settlement path; compliance/plan packaging leak.
- **Code evidence:** No backend `ENABLE_POS` check in sales/payments views; only env/JSON exposure.
- **Suggested fix direction:** If POS is a paid module, gate a dedicated checkout endpoint or RETAIL+same-day receipt pairing; or document that POS is UI sugar only.
- **Test to add:** `enable_pos_false_blocks_pos_checkout_endpoint` (once endpoint exists) or explicit product decision test
- **Twin check:** Sales/Purchase equivalent — same bug? n (POS-specific flag)

### POS-009 — Inclusive price mode: line table totals skip exclusive extraction
- **Module:** POS -> UI totals
- **Location:** `web/src/pages/pos/PosPage.tsx:1227–1247` (table) vs `:333–365` (`lineTaxes` for tender panel)
- **Type:** Bug
- **Severity:** Medium
- **What's wrong:** Tender panel extracts exclusive unit price when `priceMode === 'INCLUSIVE'`; per-line table `calculateLineTax` uses raw `posLineUnitPrice` without extraction → overstated line totals vs pay panel.
- **Trigger / repro:** Company inclusive pricing; add GST item; compare line Total column vs tender Total.
- **Consequence:** Cashier distrust / wrong mental tender; increases POS-007 risk.
- **Code evidence:** `extractExclusiveFromInclusiveLine` only in `lineTaxes` memo, not table map.
- **Suggested fix direction:** Share one line-tax helper for table and tender.
- **Test to add:** `pos_inclusive_line_row_matches_tender_total`
- **Twin check:** Sales/Purchase equivalent — same bug? n (invoice editor likely shared helpers)

### POS-010 — Unknown complete status clears cart without confirming completion
- **Module:** POS -> createCompletedInvoice recovery
- **Location:** `web/src/pages/pos/PosPage.tsx:624–636`
- **Type:** Bug
- **Severity:** Medium
- **What's wrong:** If complete errors and status probe also fails, UI clears cart, clears idempotency key, and shows unpaid recover for an id that may still be DRAFT (complete never committed).
- **Trigger / repro:** Flaky network during complete; GET invoice also fails.
- **Consequence:** Lost cart lines; possible orphan DRAFT; misleading “left unpaid” recover link.
- **Code evidence:** `setCart([]); setIdempotencyKey(null);` on unknown branch before rethrow.
- **Suggested fix direction:** Keep cart + key; show “verify sale #id” without claiming unpaid completed; only clear after confirmed COMPLETED/DELETED.
- **Test to add:** `createCompletedInvoice_unknown_status_keeps_cart_and_key`
- **Twin check:** Sales/Purchase equivalent — same bug? n-a

### POS-011 — Cash tendered / change never posted (display-only)
- **Module:** POS -> cash handling
- **Location:** `web/src/pages/pos/PosPage.tsx:380–382`, `:652–660`; `backend/payments/services.py:226–245` (`PaymentService.create_receipt` amount = invoice total only)
- **Type:** Improvement
- **Severity:** Low
- **What's wrong:** Overpay/change is UI-only. Receipt always equals invoice total (correct for AR) but till variance is not auditable.
- **Trigger / repro:** Tender ₹2000 on ₹850 bill; complete.
- **Consequence:** No system record of cash in drawer vs sale; disputes rely on memory.
- **Code evidence:** `changeDue` local; receipt `amount: invoiceTotal`.
- **Suggested fix direction:** Optional tendered/change fields on receipt notes or cash-session object.
- **Test to add:** n-a until product wants till sessions
- **Twin check:** Sales/Purchase equivalent — same bug? n-a

### POS-012 — POS qty control lacks 3dp money discipline / upper bound
- **Module:** POS -> validation
- **Location:** `web/src/pages/pos/PosPage.tsx:1286–1293`; server `backend/core/models.py:77–78`; `backend/sales/services.py:48–50` (`_validate_lines`)
- **Type:** Missing-validation
- **Severity:** Low
- **What's wrong:** Qty `NumericField` has `min={1}` (blocks fractional <1 in UI oddly vs server 0.001) and no `decimals={3}` / `max`. Abuse huge qty still allowed server-side (max_digits only).
- **Trigger / repro:** Type qty `999999999` or rely on API for `0.5` while UI steppers assume integers.
- **Consequence:** Awkward UX for catch-weight; weak abuse ceiling for fat-finger / malicious qty.
- **Code evidence:** No decimals/max on POS qty field; server allows ≥0.001 up to field limits.
- **Suggested fix direction:** Align UI with 3dp qty + sane max; keep server as source of truth.
- **Test to add:** `pos_rejects_qty_below_0_001_and_caps_absurd_qty`
- **Twin check:** Sales/Purchase equivalent — same bug? y (shared line model)

### POS-013 — Stock chips use 60s cached balances (advisory only)
- **Module:** POS -> inventory display
- **Location:** `web/src/pages/pos/PosPage.tsx:238–256`
- **Type:** Improvement
- **Severity:** Low
- **What's wrong:** `listStock` `staleTime: 60_000` drives search labels; add-to-cart does not re-check. Server `post_movement` + `select_for_update` is authoritative (OK under BLOCK).
- **Trigger / repro:** Two terminals; UI still shows 1 available after other sold.
- **Consequence:** Misleading UI; not a stock integrity bug if policy BLOCK (see concurrency note).
- **Code evidence:** Client cache only; no client stock gate on checkout.
- **Suggested fix direction:** Invalidate stock on sale complete; optional soft warn.
- **Test to add:** n-a (UX)
- **Twin check:** Sales/Purchase equivalent — same bug? y

---

## POS coverage notes
- **Core write path reviewed:** Client POS cash/UPI → `createSalesInvoice` (`sales_invoice_create`) → `SalesService.complete` (`transaction.atomic` + `select_for_update` invoice/customer; stock via `CogsService.post_sale_stock_and_cogs` → `InventoryService.post_movement` balance lock; GL `PostingService`; PDF via `on_commit`/`sales_invoice.completed`) → `PaymentService.create_receipt` → `allocate_receipt` → thermal GET. Offline: `enqueueDraft` → `flushPosDraft` with `${key}`, `${key}-complete`, `${key}-receipt`, `${key}-alloc`.
- **Reversal path:** POS has no in-flow void; invoice cancel restores via new ADJUSTMENT movements (append-only), blocks cancel if allocations exist — returns/CN are separate sales module.
- **Concurrency:** Under `negative_stock_policy=BLOCK`, two terminals selling last unit serialize on `StockBalance.select_for_update` inside `post_movement` (covered by `test_concurrent_stock_oversell_blocked`). Advisory `check_negative_stock` before post is not the authority. FEFO batch lines hard-fail shortfall in `_sale_batches` even when policy would allow negatives.
- **Idempotency scopes:** POS uses `sales_invoice_create`, `sales_invoice_complete`, `receipt_create`, `allocation_create` — all present in `MONEY_IDEMPOTENCY_SCOPES` (no missing-scope finding).
- **Tenancy:** All sales endpoints inherit `CompanyScopedViewSet` and filter queries by `self.company`. Master entities (`Customer`, `Product`, `StockBalance`, `CompanyGstin`) are strictly tenant-isolated. Payment allocations enforce cross-document company equality.
- **Permissions:** `SalesInvoiceViewSet` enforces `CanCreateSales()` for creation and completion. `CustomerReceiptViewSet` and `PaymentAllocationViewSet` enforce `CanCreatePayments()`. The UI route and menu gate must check both permissions (`canCreateSales && canCreatePayments`) to prevent half-completed orphaned sales.
- **Tests present:** **thin** for end-to-end POS money path. Frontend: `posStatus.test.ts`, `flushPosCheckout.test.ts`, `invoiceDraftCache*.test.ts`. Backend: thermal PDF tests; place-of-supply “pos” naming in GST tests; stock race tests — **missing** names: `pos_online_cash_retry_after_receipt_failure_does_not_double_complete`, `pos_checkout_half_success_matrix_*`, `pos_requires_can_create_payments`, `flushPosDraft_pending_customer_retry_does_not_duplicate_customer`, concurrent complete of two RETAIL invoices for last unit via full HTTP complete (not only raw `post_movement`).
- **Files read:** `web/src/pages/pos/PosPage.tsx`, `posStatus.ts`, `posStatus.test.ts`; `web/src/offline/flushPosCheckout.ts`, `flushPosCheckout.test.ts`, `invoiceDraftCache.ts` (+ tests); `web/src/api/client.ts`, `api/legacy/sales.ts`, `api/legacy/payments.ts`, `api/legacy/masters.ts`; `web/src/auth/AuthContext.tsx`; `web/src/config/features.ts`, `featureFlags.ts`; `web/src/navigation/menu.ts`, `App.tsx`; `web/src/utils/permissions.ts`; `backend/sales/views.py`, `services.py`, `serializers.py`, `cogs_service.py`, `handlers.py`, `models.py` (SalesItem); `backend/sales/pdf` via thermal action; `backend/payments/views.py`, `services.py`; `backend/inventory/services.py`, `models.py` (StockMovement/StockBalance); `backend/core/idempotency.py`, `viewsets.py`, `permissions.py`, `models.py` (DocumentLineModel), `services/feature_flags.py`, `services/billing.py`; `backend/config/settings.py`; `backend/accounts/models.py` (capability defaults); `backend/manufacturing/permissions.py` (flag contrast); `backend/tests/test_concurrency_races.py`, `test_pdf_and_share.py` (thermal), `test_phase2_gst.py` (pos complete).