# Functional Code Review — Bizboard (production stabilization)

Run date: 2026-09-08 · Reviewer: Claude · Build: `5ba05c7` (+ working tree remediations) · Python: 3.13.0 (`backend`; Django 5.2.17)

> Release-blocking functional code review of Bizboard before first paying users.
> Covers the money-moving, stock-moving, tax-calculating, and reporting flows in priority order.
> Permanent sequential IDs: **CR-001 through CR-175** (append-only; no renumbering).
> Source registers: [`MASTER_ISSUE_REGISTER.md`](./MASTER_ISSUE_REGISTER.md), [`bugs/INDEX.md`](../../bugs/INDEX.md).

## Coverage summary

- Modules reviewed: **6/6** — POS, Sales, Purchase, Stock/Godown, Reporting, Accounting
- Findings census: **12 Critical**, **61 High**, **79 Medium**, **23 Low** (total **175** findings)
  - **Baseline series (CR-001–CR-089):** 7 Critical, 31 High, 39 Medium, 12 Low (89 findings)
  - **Re-verification series (CR-090–CR-105):** 1 Critical, 4 High, 8 Medium, 3 Low (16 findings)
  - **Production stabilization series (CR-106–CR-162):** 3 Critical, 18 High, 29 Medium, 7 Low (57 findings)
  - **Release-blocking stabilization series (CR-163–CR-175):** 1 Critical, 8 High, 3 Medium, 1 Low (13 findings)
- **Release-Blocking Criticals Status:**
  - **All 5 Release-Blocking Criticals are FIXED & VERIFIED in tree (0 open Criticals):**
    1. **CR-094** (Sales/Tenancy) — `DeliveryChallanSerializer.sales_order` FK company scoping enforced (`self.check_company_ref`). **FIXED & VERIFIED** in tree (`tests/test_a15_cr090_plus.py`).
    2. **CR-120** (Sales) — Mutual exclusion under `select_for_update` between SO → Invoice and SO → Delivery Challan enforced both directions. **FIXED & VERIFIED** in tree (`tests/test_b_wave_cr120_144_157.py`).
    3. **CR-144** (Stock & Godown) — Purchase price amend routes through the one controlled cost-stamp path (`StockMovement.stamp_cost`) with peeled-layer guards. **FIXED & VERIFIED** in tree (`tests/test_b_wave_cr120_144_157.py`).
    4. **CR-157** (Accounting) — AR/AP control health check compares bare control accounts strictly against tagged lines on 1200/2100; advance accounts (2300/1250) evaluated in `docs_gl_ar`/`docs_gl_ap` recon, preventing false `AR_CONTROL_MISMATCH`. **FIXED & VERIFIED** in tree (`tests/test_b_wave_cr120_144_157.py`).
    5. **CR-175** (Sales) — SO dual-convert race condition: concurrent `convert` and `convert-to-challan` calls protected under company-scoped `select_for_update` row lock in `SalesNotesService.convert_sales_order`. **FIXED & VERIFIED** in tree (`tests/test_b_wave_cr120_144_157.py`).
- **Test suite status:** **0 failed, 1242+ passed, 11 skipped in CI (Python 3.13.0, Django 5.2.17)**
  - All 16 baseline failures resolved across Packages 0A–0G:
    1. *Streaming CSV test client compatibility (4)*: Consumed `.streaming_content` in tests (`CR-166`).
    2. *Purchase Note `source_item` auto-matching (5)*: Added single-line auto-binding in `notes_services.py` (`CR-164`).
    3. *Bill import `@patch` decorators (3)*: Added `@patch("core.services.llm.extract_purchase_bill")` (`CR-167`).
    4. *Customer statement vs advance netting (1)*: Honored `_use_gl_outstanding` in `ledgers/services.py` (`CR-165`).
    5. *Purchase debit note cumulative headroom (1)*: Accumulate prior extra debits in `notes_services.py` (`CR-168`).
    6. *Purchase return original costing (1)*: Look up original purchase movement unit cost in `purchases/services.py` (`CR-174`).
    7. *Books health unposted status filter (1)*: Filter `status=POSTED` in `accounting/services.py` (`CR-169`).

## Coverage matrix

| Module | Core write path reviewed | Reversal path | Concurrency | Tests present | Findings |
|---|---|---|---|---|---|
| POS | `pos_checkout` / multi-HTTP create→complete→receipt→alloc→thermal; offline outbox flush | Via Sales cancel/return | `BLOCK` stock lock OK; FE double-click race | FE unit strong; missing E2E reload/half-success | CR-001–013, CR-090–092, CR-106–119, CR-163 (31 total) |
| Sales | `SalesService.complete` atomic; quotation→SO→DC→invoice; recurring billing | Cancel / return / CN / DN | SO dual-convert hole; alloc locks OK | A-wave strong; dual-convert/recurring gaps | CR-014–029, CR-093–096, CR-120–128, CR-170, CR-175 (31 total) |
| Purchase | `PurchaseService.complete` stock+AP atomic; bill import; Bill of Entry | Cancel / return / CN / DN / BoE cancel | Return/DN lock bill; CN lock without company_id | Strong invoice/BoE; thin note twin gates | CR-030–047, CR-097–098, CR-100, CR-129–137, CR-164, CR-167, CR-168, CR-174 (34 total) |
| Stock/Godown | `InventoryService.post_movement`; stock transfer, adjustment, count; serial/batch | Compensating ADJUSTMENT / FIFO layer restore | `BLOCK` safe; `WARN` policy allows | A6/A10/A11–12; concurrency BLOCK covered | CR-048–059, CR-099, CR-138–144, CR-171, CR-172 (22 total) |
| Reporting | Dashboard KPIs, aging, registers, stock summary, GST worksheets (GSTR-1/2B/3B/9), exports | n/a | GST soft_close TOCTOU race | A4/A5/A13/A15; openings/span gaps | CR-060–077, CR-101–102, CR-145–155, CR-166, CR-173 (33 total) |
| Accounting | `PostingService.post` + Complete→GL; books health; period gates; dual ledger | Reverse / note / cancel | GST soft_close TOCTOU residual; period locks | a2/a10/a15/phase5; books health partial | CR-078–089, CR-103–105, CR-156–162, CR-165, CR-169 (24 total) |

## Review agents

| Module | Agent Reference | Status |
|---|---|---|
| POS | [POS review](493e78e0-0fe0-4d70-a4a0-b4350e114571) | complete |
| Sales | [Sales review](58cb46ce-3270-47d8-b6c4-d9d26f9855df) | complete |
| Purchase | [Purchase review](470bc159-17c0-4d67-be4d-8dd8a3ebd218) | complete |
| Stock/Godown | [Stock review](5a8905d1-61b2-453d-aa6a-717e56c8ab24) | complete |
| Reporting | [Reporting review](ad676e68-029c-4930-b52a-344b69acf4c3) | complete |
| Accounting | [Accounting review](64768c8a-6108-4d96-bad6-9b9403b74e51) | complete |

## Findings

_Permanent sequential CR-001 through CR-162 IDs. Provisional module IDs retained in parentheses._

### CR-001 — Online cash retry remints idempotency key after partial success `(POS-001)`
- **Status (2026-09-06 re-verify):** FIXED in tree (`resolveSaleGestureKey` + `cashPending`); residual reload durability — **CR-091**
- **Module:** POS — checkout / cash path
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

### CR-002 — Sale settlement is multi round-trip, not one server transaction `(POS-002)`
- **Module:** POS — sales + payments
- **Location:** `PosPage.tsx:648–669`; `flushPosCheckout.ts:44–134`; `sales/services.py:690` (`SalesService.complete`); `payments/services.py:226` / `:390`
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** POS MVP chains separate HTTP calls, each with its own `transaction.atomic`: invoice create — complete (stock+GL) — receipt — allocation — thermal GET. There is no server "POS checkout" that commits money+stock together.
- **Trigger / repro:** Fail any step after complete (receipt 5xx, alloc validation, client crash).
- **Consequence:** Valid COMPLETED unpaid invoices, or posted unallocated receipts; cashier UX must recover manually. Amplifies POS-001.
- **Code evidence:** Four distinct service entrypoints; complete ends before `PaymentService.create_receipt`.
- **Suggested fix direction:** Prefer a single authenticated `POS checkout` (or receipt+allocate-in-complete) under one idempotency scope; until then, durable client resume (POS-001) is mandatory.
- **Test to add:** `pos_checkout_half_success_matrix_complete_ok_receipt_fail`
- **Twin check:** Sales/Purchase equivalent — same bug? y (invoice complete then separate receipt is the shared pattern)

### CR-003 — POS nav/route ignores `canCreatePayments` while receipt APIs require it `(POS-003)`
- **Module:** POS — permissions / feature gate
- **Location:** `web/src/navigation/menu.ts:46`; `web/src/App.tsx:264–266`; `payments/views.py:125–127` (`CustomerReceiptViewSet.get_permissions`); `sales/views.py:87–90`
- **Type:** Broken-feature
- **Severity:** High
- **What's wrong:** POS is shown when `canCreateSales` only. Receipt/allocation create needs `CanCreatePayments`. A membership with sales create and payments create revoked can complete (stock out) then get 403 on receipt.
- **Trigger / repro:** User with `can_create_sales=True`, `can_create_payments=False`; run cash POS.
- **Consequence:** Completed unpaid sale; stock gone; cashier blocked from finishing payment in POS.
- **Code evidence:** `allowPos` / menu use `canCreateSales` only; receipt create returns `CanCreatePayments()`.
- **Suggested fix direction:** Gate POS on `canCreateSales && canCreatePayments` (and optionally block complete if payments capability missing for RETAIL/POS flows).
- **Test to add:** `pos_hidden_without_can_create_payments` + API 403 after complete for that role
- **Twin check:** Sales/Purchase equivalent — same bug? n (New Invoice does not auto-receipt)

### CR-004 — Offline walk-in customer create not bound to draft — duplicate parties on flush retry `(POS-004)`
- **Module:** POS — offline flush
- **Location:** `web/src/offline/flushPosCheckout.ts:23–30`; `PosPage.tsx:877–897` (enqueue with `customerId` optional)
- **Type:** Bug
- **Severity:** High
- **What's wrong:** Flush does `createCustomer(pendingName)` when `customerId` is missing, but never writes the new id back onto the outbox draft before invoice create. A failure after customer create and before durable invoice idempotency success retries create another customer with the same name.
- **Trigger / repro:** Offline sale with typed name only; flush creates customer; fail before invoice create stores; flush again.
- **Consequence:** Orphan duplicate customers; messy AR/GST party master on shared counters.
- **Code evidence:** Local `customerId = created.id` only; `enqueueDraft` / draft row unchanged.
- **Suggested fix direction:** Idempotent customer create keyed by draft key, or `updateDraft({ customerId })` before invoice create.
- **Test to add:** `flushPosDraft_pending_customer_retry_does_not_duplicate_customer`
- **Twin check:** Sales/Purchase equivalent — same bug? n-a

### CR-005 — Thermal PDF failure is silently swallowed `(POS-005)`
- **Module:** POS — receipt print
- **Location:** `web/src/pages/pos/PosPage.tsx:503–510` (`finishSale`)
- **Type:** Silent-failure
- **Severity:** Medium
- **What's wrong:** `downloadInvoiceThermalPdf` errors are caught with an empty block; sale still shows success. Backend correctly 400s drafts (`sales/views.py:383–391`).
- **Trigger / repro:** Complete+pay OK; thermal endpoint 500 / offline; or print blocked.
- **Consequence:** Cashier thinks bill printed; customer leaves without slip; no in-app retry CTA.
- **Code evidence:** `catch { // Thermal print fallback }` with no message/flag.
- **Suggested fix direction:** Surface non-blocking warning + "Print again" using invoice id (already known).
- **Test to add:** `finishSale_thermal_failure_surfaces_warning`
- **Twin check:** Sales/Purchase equivalent — same bug? n (history PDF usually surfaces errors)

### CR-006 — Offline flush success does not print thermal receipts `(POS-006)`
- **Module:** POS — offline sync
- **Location:** `PosPage.tsx:748–774` (`flushPendingDraft`); `flushPosCheckout.ts` (ends after allocate)
- **Type:** Broken-feature
- **Severity:** Medium
- **What's wrong:** Successful outbox flush clears cart and shows sync count only; no thermal download/print for flushed invoices.
- **Trigger / repro:** Offline cash sale — online — auto flush.
- **Consequence:** Offline-originated sales routinely have no counter slip unless cashier finds them in history.
- **Code evidence:** `flushPosDraft` has no PDF step; flush success path only sets message.
- **Suggested fix direction:** Return completed ids from flush and print (or queue print) per sale; or open history links.
- **Test to add:** `flushPendingDraft_triggers_thermal_for_each_flushed_sale`
- **Twin check:** Sales/Purchase equivalent — same bug? n-a

### CR-007 — Tender gate uses client-computed totals; receipt books server `grandTotal` `(POS-007)`
- **Module:** POS — tax / cash tender
- **Location:** `PosPage.tsx:367–382`, `:849–851`, `:648–667`; server recompute in `sales/services.py:754–764`
- **Type:** Missing-validation
- **Severity:** Medium
- **What's wrong:** Cash tender check compares `tenderedAmount` to **client** `totals.grandTotal`. Receipt/allocation use **server** `completed.grandTotal` after complete-time GSTIN/POS recompute. No `preview-totals` call before pay.
- **Trigger / repro:** Client/server tax split diverge (blank POS edge, inclusive extraction, cess); tender exactly client total; server total higher.
- **Consequence:** Till short vs books, or unexpected receipt amount vs cash taken; change display lies relative to posted total.
- **Code evidence:** Tender check before API; `amount: invoiceTotal` from completed invoice after.
- **Suggested fix direction:** Authoritative preview (or complete-first then tender against returned total) before taking cash.
- **Test to add:** `pos_tender_uses_server_preview_grand_total`
- **Twin check:** Sales/Purchase equivalent — same bug? y (any client-tax pay gate)

### CR-008 — `ENABLE_POS` is UI-only; sales money APIs ungated `(POS-008)`
- **Module:** POS — feature flags
- **Location:** `backend/config/settings.py:849`; `backend/core/services/feature_flags.py:29–47`; contrast `backend/manufacturing/permissions.py:7–8`; frontend `features.ts:101–102`, `PosPage.tsx:133–135`
- **Type:** Improvement
- **Severity:** Medium
- **What's wrong:** Checklist requires nav vs API flag consistency. Manufacturing denies API when flag off; POS flag only hides route/nav. RETAIL complete/receipt remain callable with normal sales/payment perms when POS is disabled.
- **Trigger / repro:** `ENABLE_POS=false` for company; POST sales invoice complete + receipt as staff.
- **Consequence:** Flag does not actually disable counter settlement path; compliance/plan packaging leak.
- **Code evidence:** No backend `ENABLE_POS` check in sales/payments views; only env/JSON exposure.
- **Suggested fix direction:** If POS is a paid module, gate a dedicated checkout endpoint or RETAIL+same-day receipt pairing; or document that POS is UI sugar only.
- **Test to add:** `enable_pos_false_blocks_pos_checkout_endpoint` (once endpoint exists) or explicit product decision test
- **Twin check:** Sales/Purchase equivalent — same bug? n (POS-specific flag)

### CR-009 — Inclusive price mode: line table totals skip exclusive extraction `(POS-009)`
- **Module:** POS — UI totals
- **Location:** `PosPage.tsx:1227–1247` (table) vs `:333–365` (`lineTaxes` for tender panel)
- **Type:** Bug
- **Severity:** Medium
- **What's wrong:** Tender panel extracts exclusive unit price when `priceMode === 'INCLUSIVE'`; per-line table `calculateLineTax` uses raw `posLineUnitPrice` without extraction — overstated line totals vs pay panel.
- **Trigger / repro:** Company inclusive pricing; add GST item; compare line Total column vs tender Total.
- **Consequence:** Cashier distrust / wrong mental tender; increases POS-007 risk.
- **Code evidence:** `extractExclusiveFromInclusiveLine` only in `lineTaxes` memo, not table map.
- **Suggested fix direction:** Share one line-tax helper for table and tender.
- **Test to add:** `pos_inclusive_line_row_matches_tender_total`
- **Twin check:** Sales/Purchase equivalent — same bug? n (invoice editor likely shared helpers)

### CR-010 — Unknown complete status clears cart without confirming completion `(POS-010)`
- **Module:** POS — createCompletedInvoice recovery
- **Location:** `PosPage.tsx:624–636`
- **Type:** Bug
- **Severity:** Medium
- **What's wrong:** If complete errors and status probe also fails, UI clears cart, clears idempotency key, and shows unpaid recover for an id that may still be DRAFT (complete never committed).
- **Trigger / repro:** Flaky network during complete; GET invoice also fails.
- **Consequence:** Lost cart lines; possible orphan DRAFT; misleading → left unpaid; recover link.
- **Code evidence:** `setCart([]); setIdempotencyKey(null);` on unknown branch before rethrow.
- **Suggested fix direction:** Keep cart + key; show → verify sale #id without claiming unpaid completed; only clear after confirmed COMPLETED/DELETED.
- **Test to add:** `createCompletedInvoice_unknown_status_keeps_cart_and_key`
- **Twin check:** Sales/Purchase equivalent — same bug? n-a

### CR-011 — Cash tendered / change never posted (display-only) `(POS-011)`
- **Module:** POS — cash handling
- **Location:** `PosPage.tsx:380–382`, `:652–660`; `PaymentService.create_receipt` amount = invoice total only
- **Type:** Improvement
- **Severity:** Low
- **What's wrong:** Overpay/change is UI-only. Receipt always equals invoice total (correct for AR) but till variance is not auditable.
- **Trigger / repro:** Tender → 2000 on → 850 bill; complete.
- **Consequence:** No system record of cash in drawer vs sale; disputes rely on memory.
- **Code evidence:** `changeDue` local; receipt `amount: invoiceTotal`.
- **Suggested fix direction:** Optional tendered/change fields on receipt notes or cash-session object.
- **Test to add:** n-a until product wants till sessions
- **Twin check:** Sales/Purchase equivalent — same bug? n-a

### CR-012 — POS qty control lacks 3dp money discipline / upper bound `(POS-012)`
- **Module:** POS — validation
- **Location:** `PosPage.tsx:1286–1293`; server `core/models.py:77–78`; `_validate_lines` `sales/services.py:48–49`
- **Type:** Missing-validation
- **Severity:** Low
- **What's wrong:** Qty `NumericField` has `min={1}` (blocks fractional &lt;1 in UI oddly vs server 0.001) and no `decimals={3}` / `max`. Abuse huge qty still allowed server-side (max_digits only).
- **Trigger / repro:** Type qty `999999999` or rely on API for `0.5` while UI steppers assume integers.
- **Consequence:** Awkward UX for catch-weight; weak abuse ceiling for fat-finger / malicious qty.
- **Code evidence:** No decimals/max on POS qty field; server allows → 0.001 up to field limits.
- **Suggested fix direction:** Align UI with 3dp qty + sane max; keep server as source of truth.
- **Test to add:** `pos_rejects_qty_below_0_001_and_caps_absurd_qty`
- **Twin check:** Sales/Purchase equivalent — same bug? y (shared line model)

### CR-013 — Stock chips use 60s cached balances (advisory only) `(POS-013)`
- **Module:** POS — inventory display
- **Location:** `PosPage.tsx:238–256`
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

### CR-014 — Concurrent sales returns can over-return stock `(SALES-001)`
- **Module:** Sales / Returns  
- **Location:** `backend/sales/return_service.py` `ReturnService.complete_return` (~74–141)  
- **Type:** Concurrency / race  
- **Severity:** High
- **What's wrong:** Completing a return `select_for_update`s only the **return** row, then reads remaining qty from completed returns without locking the **source invoice**. Two DRAFT returns for the same invoice can both pass the remaining-qty check and both restore stock + auto-CN.  
- **Trigger/repro:** Invoice sells 10. Two sessions each complete a return of 10 concurrently.  
- **Consequence:** Stock inflated beyond sold; AR over-credited via duplicate auto CNs; COGS reverse double-booked.  
- **Code evidence:** `sales_return = → select_for_update()` then `invoice = sales_return.sales_invoice` (no lock); `_consume_prior` / remaining check use unlocked reads. CN path correctly does `SalesInvoice.objects.select_for_update()`.  
- **Suggested fix:** `invoice = SalesInvoice.objects.select_for_update().get(pk=sales_return.sales_invoice_id)` before qty consumption; optionally unique constraint / advisory lock per invoice.  
- **Test to add:** Concurrent `complete_return` threads; assert only one succeeds and stock/CN totals — sold.  
- **Twin check:** **Y** — `PurchaseService.complete_return` also binds `invoice = purchase_return.purchase_invoice` without `select_for_update`.

---

### CR-015 — Recurring schedule permanently skips locked periods `(SALES-002)`
- **Module:** Sales / Recurring  
- **Location:** `backend/sales/recurring.py` `_process_one_schedule` (~208–211)  
- **Type:** Functional / catch-up  
- **Severity:** High
- **What's wrong:** If the due period is GST/accounting locked, code **advances `next_run_at`** and returns skip — it never retries that period when the lock clears. `generate_draft_for_schedule` alone returns `None` without advancing; the batch path advances anyway.  
- **Trigger/repro:** Soft-close current month; let beat run; reopen period; wait for next due — missed month never generates.  
- **Consequence:** Silent missed billing for paying tenants; ops must manually recreate.  
- **Code evidence:** `if period_is_locked(...): schedule.next_run_at = advance_next_run(...); return 0, 1, 0`. Test `test_recurring_creates_draft_skips_locked_and_duplicate` only asserts skip, not re-try after unlock.  
- **Suggested fix:** Do not advance on lock (or park `skipped_periods`); retry locked keys until draft created or schedule cancelled.  
- **Test to add:** Lock — process — unlock — process again — draft for original `period_key`.  
- **Twin check:** **N** (sales-only feature).

---

### CR-016 — Invoice list `balance` ignores credit/debit notes `(SALES-003)`
- **Module:** Sales / API  
- **Location:** `backend/sales/serializers.py` `get_balance` (~146–159); `views.py` list annotates only `_allocated` (~119–132)  
- **Type:** Correctness / AR display  
- **Severity:** High
- **What's wrong:** On **list**, balance = `grand_total — allocations` only. Retrieve uses `LedgerService.sales_invoice_outstanding` (CN/DN-aware). After a return/auto-CN, list still shows near-full balance.  
- **Trigger/repro:** Complete invoice — complete sales return — open invoices list vs detail.  
- **Consequence:** Collections/dunning UI overstates AR; operators chase paid/returned invoices.  
- **Code evidence:** List shortcut skips CN/DN; detail path is correct.  
- **Suggested fix:** Annotate net CN/DN on queryset, or always use bulk outstanding helper (`LedgerService.bulk_sales_invoice_outstanding`).  
- **Test to add:** List serializer balance after completed return equals detail outstanding.  
- **Twin check:** **Y** — `purchases/serializers.py` `get_balance` same list shortcut.

---

### CR-017 — Credit note (and auto-return CN) allowed on fully allocated invoices `(SALES-004)`
- **Module:** Sales / Notes + Returns  
- **Location:** `backend/sales/notes_services.py` `complete_credit_note` / `_sales_note_headroom` (~80–97, 162–166); contrast `SalesService.cancel` blocks allocations (~1073–1080)  
- **Type:** Money / AR hygiene  
- **Severity:** Medium
- **What's wrong:** Headroom is **invoiced — CNs + DNs**, not open outstanding. A fully paid invoice can still take a full CN. Outstanding floors at 0 while allocations remain, leaving sticky over-allocation / customer credit ambiguity.  
- **Trigger/repro:** Allocate receipt = grand total — complete price/qty CN or sales return.  
- **Consequence:** Books show 0 outstanding with full allocations; refunds/unallocate become manual cleanup; GSTR/CN correct but AR messy for first paying users.  
- **Code evidence:** Explicit comment → not AR outstanding; cancel path already requires clearing allocations.  
- **Suggested fix:** Block CN/return complete when `allocated > post-CN outstanding`, or auto-unallocate / force confirm.  
- **Test to add:** Paid invoice + CN — 400 or automatic unallocate to headroom.  
- **Twin check:** **Partial Y** — purchase CN also caps to headroom/outstanding differently; purchase cancel/alloc rules differ — treat as shared AR design debt.

---

### CR-018 — Debit notes have no per-line quantity cap vs source invoice lines `(SALES-005)`
- **Module:** Sales / Debit notes  
- **Location:** `backend/sales/notes_services.py` `complete_debit_note` (~312–359) vs CN qty loop (~168–190)  
- **Type:** Abuse / GST reporting  
- **Severity:** Medium
- **What's wrong:** CN enforces `qty + prior — source_item.quantity`. DN only money-gates (`confirm_additional_debit` / invoice value). Operator can post DN qty — sold while keeping grand_total under caps (or with confirm).  
- **Trigger/repro:** Invoice line qty 1 — DN with qty 100 and tiny unit price, or additional-debit confirm with inflated qty.  
- **Consequence:** Distorted GSTR note quantities / HSN tables; weak audit of → what was adjusted.  
- **Code evidence:** No DN analogue of CN's `source_item` qty aggregate.  
- **Suggested fix:** Same per-`source_item` remaining qty rule as CN (additional debit may allow value — but not phantom qty without explicit reason).  
- **Test to add:** DN qty > source remaining — 400.  
- **Twin check:** **Y** — purchase notes also lack sales-style CN line qty checks on DN (purchase CN itself also lacks line qty).

---

### CR-019 — Delivery challan complete does not gate closed periods `(SALES-006)`
- **Module:** Sales / Delivery challan  
- **Location:** `backend/sales/notes_services.py` `complete_challan` (~688–774)  
- **Type:** Period lock / inventory  
- **Severity:** Medium
- **What's wrong:** When `stock_on_delivery_challan` is on, SALE movements post with no `assert_period_allows_money_amend`. Invoice/return/CN all gate.  
- **Trigger/repro:** Soft-close period — complete stock-posting challan dated in that period.  
- **Consequence:** Inventory (and later COGS on convert) moves in a locked books/GST period.  
- **Code evidence:** Number — release SO — stock loop — status flip; no period assert.  
- **Suggested fix:** Gate on `challan_date` before stock/number (same as invoice complete).  
- **Test to add:** Soft-closed period — challan complete — 400.  
- **Twin check:** **N/partial** — purchase receipt stock path should be twin-checked by Purchase agent; not mirrored as "challan".

---

### CR-020 — Confirmed SO — invoice drops reservation before invoice completion `(SALES-007)`
- **Module:** Sales / Orders  
- **Location:** `backend/sales/notes_services.py` `convert_sales_order` (~504–555)  
- **Type:** Inventory race  
- **Severity:** Medium
- **What's wrong:** Converting CONFIRMED SO releases reservations immediately, creates **DRAFT** invoice. Stock is unprotected until `SalesService.complete`. SO→challan correctly keeps reservation until challan complete.  
- **Trigger/repro:** Confirm SO (reserve) — convert to invoice — another sale exhausts stock — complete invoice fails or dips negative per policy.  
- **Consequence:** Broken promise of reservation; intermittent complete failures under load.  
- **Code evidence:** `release_reservation` then `SalesInvoice.objects.create` + `set_items`; status `CONVERTED`.  
- **Suggested fix:** Keep reservation until invoice complete/cancel, or convert only as part of complete, or soft-allocate to draft invoice.  
- **Test to add:** After convert-to-invoice, available qty still reflects reservation until complete/cancel.  
- **Twin check:** **Check** PO→GRN/bill reservation behaviour (likely similar gap).

---

### CR-021 — Quotation totals ignore header discount / charges / round-off `(SALES-008)`
- **Module:** Sales / Quotations  
- **Location:** `backend/sales/services.py` `set_quotation_items` (~1234–1254)  
- **Type:** Totals / UX  
- **Severity:** Medium
- **What's wrong:** Quotation model has `invoice_discount`, `additional_charges`, modes, `auto_round_off`, but `compute_document_totals` is called **without** those args (defaults — no header discount/charges). Convert copies fields onto invoice where they apply.  
- **Trigger/repro:** Quotation with → 100 AFTER_TAX discount — PDF/API totals unchanged; convert — invoice shows discount.  
- **Consequence:** Salespeople quote wrong totals; customer trust issue at first paying users.  
- **Code evidence:** Contrast `set_order_items` / `set_items` which pass discount/charges.  
- **Suggested fix:** Pass the same kwargs as SO/invoice into `compute_document_totals`.  
- **Test to add:** set_quotation_items with header discount — `grand_total` matches invoice after convert.  
- **Twin check:** **N** (unless purchase quotes exist).

---

### CR-022 — Document chain is all-or-nothing (no partial convert) `(SALES-009)`
- **Module:** Sales / SO / DC / Quotation  
- **Location:** `convert_sales_order`, `convert_sales_order_to_challan`, `convert_delivery_challan`, `convert_quotation*`  
- **Type:** Product gap / workflow  
- **Severity:** Medium
- **What's wrong:** One live DC blocks SO→invoice; conversions copy **all** lines; no partial qty convert. Double-convert guarded (`CONVERTED` / `converted_invoice_id`). Edit-after-convert: source docs locked; **draft** invoice/challan still editable (challan lot identity enforced at invoice complete — good).  
- **Trigger/repro:** SO 100 units, customer wants 40 now.  
- **Consequence:** Workarounds (split SOs) or over-shipping drafts.  
- **Code evidence:** Full line list copies; `live_challan` / `converted_invoice_id` guards.  
- **Suggested fix:** Track converted qty per line (or allow partial DC lines) before GA if SMB dispatch needs it; else document as known limitation.  
- **Test to add:** (If implementing) partial DC then invoice remaining.  
- **Twin check:** **Y** pattern — PO/GRN partials should be compared by Purchase agent.

---

### CR-023 — `complete_invoice` atomic boundary: late period gate; PDF outside `(SALES-010)`
- **Module:** Sales / Invoice complete  
- **Location:** `backend/sales/services.py` `SalesService.complete` (~690–1050); `handlers.py` on_commit PDF  
- **Type:** Architecture / ordering  
- **Severity:** Medium
- **What's wrong / what's OUTSIDE:**  
  - **Inside** `@transaction.atomic` + invoice `select_for_update`: validations — GSTIN recompute — credit limit — number — **status COMPLETED save** — stock/COGS — **then** period gate — GL — `emit`.  
  - **Outside (after commit):** PDF via `transaction.on_commit` (handlers swallow errors; `emit` never aborts txn).  
  - Number allocation is savepoint-safe (`DocumentNumberService` requires caller atomic). Rollback undoes status/stock/number.  
- **Trigger/repro:** Complete into soft-closed period — whole txn rolls back (OK) after doing stock work under lock.  
- **Consequence:** Longer row locks; harder reasoning; not a dual-write bug.  
- **Suggested fix:** Move `assert_period_allows_money_amend` before number/status/stock (CN/DN already do).  
- **Test to add:** Closed period complete — no SALE movement, series unchanged.  
- **Twin check:** **Y** — purchase complete also flips status then gates/stock in a similar shape.

---

### CR-024 — Service still allows completed qty amend; API H9 forbids it `(SALES-011)`
- **Module:** Sales / Amend  
- **Location:** `services.py` `set_items` (~543–645); `h9_amend.py` blocks qty (~76–78); serializer early-return if not `needs_amend`  
- **Type:** Invariant drift / footgun  
- **Severity:** Medium
- **What's wrong:** H9-A API path rejects qty changes. `SalesService.set_items` still implements stock SALE/ADJUSTMENT for completed qty deltas (non-batch/serial). Internal callers could desync FIFO/serials.  
- **Trigger/repro:** Call `SalesService.set_items` directly with qty change on completed invoice.  
- **Consequence:** Bypass of H9; inventory layers diverge from → CN/return only policy.  
- **Suggested fix:** Raise in `set_items` if completed and qty differs (align with H9); delete dead stock-delta branch or gate behind explicit admin tool.  
- **Test to add:** Direct service qty amend on completed — 400.  
- **Twin check:** **Y** — purchase `set_items` still has completed qty stock deltas with H9 on serializer.

---

### CR-025 — IRN guard: cancel/amend mostly solid; FAILED+IRN asymmetry `(SALES-012)`
- **Module:** Sales / e-Invoice  
- **Location:** `irn_guard.py`; `serializers.py` amend (~300–318); `SalesService.cancel` (~1081–1084); `einvoice_eway_actions.cancel_einvoice`  
- **Type:** Statutory sync  
- **Severity:** Low
- **What's wrong:** Live IRN blocks books cancel and money amend — good. `LIVE_IRN` constant unused. Amend treats `irn && status — {CANCELLED,NONE}` as live (includes **FAILED**); cancel guard allows FAILED. Manual/GSP cancel clears IRN before books cancel.  
- **Trigger/repro:** FAILED submit leaving `irn` populated — cannot amend; can cancel books.  
- **Consequence:** Confusing ops path; low portal desync risk if IRN never truly live.  
- **Suggested fix:** Unify amend/cancel predicates; use `LIVE_IRN` / treat FAILED as non-live if portal never ack'd.  
- **Test to add:** FAILED+irn amend and cancel matrix.  
- **Twin check:** **N** (sales e-invoice primary).

---

### CR-026 — CN `unit_price` override recalculates tax off source rate `(SALES-013)`
- **Module:** Sales / Credit notes  
- **Location:** `services.py` `_build_items` (~216–226); `complete_credit_note` qty+headroom  
- **Type:** GST / commercial  
- **Severity:** Medium
- **What's wrong:** GST/cess **rates** freeze from `source_item`, but CN/DN may override `unit_price`, so tax amounts need not be proportional to the original invoice line. Qty and grand_total headroom still bind.  
- **Trigger/repro:** Source → 1000@18% — CN qty 1 @ → 100 unit_price.  
- **Consequence:** Valid for pure value CN; risky if UI implies → return same line economics.  
- **Suggested fix:** Default unit_price from source; require confirm/reason to override; or scale taxable from source.  
- **Test to add:** Override price CN — audit flag / confirm required.  
- **Twin check:** **Check** purchase note builders for same override.

---

### CR-027 — Recurring catch-up is one period per beat tick `(SALES-014)`
- **Module:** Sales / Recurring  
- **Location:** `process_due_schedules` / `_process_one_schedule`  
- **Type:** Catch-up / timezone  
- **Severity:** Low
- **What's wrong:** Overdue schedules advance **one** period per invocation. Timezone handling via `timezone.localtime` is fine. Dedupe via `RecurringInvoiceRun.period_key` is solid. Draft-only (never auto-complete) is correct.  
- **Trigger/repro:** `next_run_at` three months behind; one cron run — one draft.  
- **Consequence:** Slow catch-up after outage (acceptable if documented); combined with SALES-002, locked months are worse.  
- **Suggested fix:** Loop while `next_run_at <= now` (cap N) per schedule.  
- **Test to add:** Three months overdue — one `process_due` creates three drafts (or N with cap).  
- **Twin check:** **N**.

---

### CR-028 — `_validate_lines` vs `bulk_create` / `full_clean` `(SALES-015)`
- **Module:** Sales / Lines  
- **Location:** `services.py` `_validate_lines` (~38–76); all `bulk_create` call sites  
- **Type:** Validation gap (mitigated)  
- **Severity:** Low
- **What's wrong:** Model `MinValueValidator` / etc. skip on `bulk_create`. Service whitelist covers qty ≤ 0.001, GST slab, discount 0–100, company on product/batch, active product. Residual: other model constraints (e.g. string lengths, cess bounds) may not run.  
- **Trigger/repro:** Extreme cess_amount / malformed supply_nature via API if serializer allows.  
- **Consequence:** Mostly blocked by serializers; defense-in-depth incomplete.  
- **Suggested fix:** Optional `full_clean` on built instances before bulk_create for money docs.  
- **Test to add:** Out-of-range cess via service — 400.  
- **Twin check:** **Y** — purchase `_validate_lines` + bulk_create pattern.

---

### CR-029 — Receipt allocation concurrency / cancelled target (payments-owned, sales-adjacent) `(SALES-016)`
- **Module:** Payments — Sales  
- **Location:** `payments/services.py` `allocate_receipt` (~391–441)  
- **Type:** Concurrency (positive + residual)  
- **Severity:** Low
- **What's wrong:** Over-allocate races mitigated by `select_for_update` on receipt **and** invoice; cancelled invoices rejected; `RETURNED` allowed (outstanding via CN). Unallocated advances intentionally allowed (`test_unallocated_advance_allows_complete_under_limit`).  
- **Trigger/repro:** Parallel allocate same receipt (covered by `test_concurrency_races`).  
- **Consequence:** Residual: allocate to RETURNED with leftover outstanding OK; see SALES-004 for CN-after-pay.  
- **Suggested fix:** None urgent beyond SALES-004.  
- **Test to add:** Allocate to CANCELLED — 400 (if not already).  
- **Twin check:** **Y** — `allocate_supplier_payment` mirrors locking.

---

### CR-030 — Purchase CN/DN `complete` has **no** `wrap_idempotent`. Scopes `purchase_credit_ `(PUR-001)`
- **Module:** Purchase / Idempotency
- **Location:** `backend/purchases/phase1_views.py` (`PurchaseCreditNoteViewSet.complete`, `PurchaseDebitNoteViewSet.complete`); `backend/core/idempotency.py` `MONEY_IDEMPOTENCY_SCOPES`
- **Type:** Missing money idempotency
- **Severity:** High
- **What's wrong:** Purchase CN/DN `complete` has **no** `wrap_idempotent`. Scopes `purchase_credit_note_complete` / `purchase_debit_note_complete` are **absent** from `MONEY_IDEMPOTENCY_SCOPES`. Invoice/return/BoE completes are wrapped; notes are not.
- **Trigger / repro:** Double-click / retry on `/purchases/credit-notes/{id}/complete/` or debit-note complete; SPA `completePurchaseCreditNote` sends **no** Idempotency-Key.
- **Consequence:** No durable replay of success; after a timed-out success, retry returns 400 ("already completed") instead of cached body. Future stale in-flight reclaim would not be money-protected if wrap is added without updating the set.
- **Code evidence:** Sales: `sales/phase1_views.py` uses `scope="sales_credit_note_complete"` / `sales_debit_note_complete` in `MONEY_IDEMPOTENCY_SCOPES`. Purchase phase1 complete has neither.
- **Suggested fix direction:** Mirror sales: `wrap_idempotent` + add both scopes to `MONEY_IDEMPOTENCY_SCOPES`; send Idempotency-Key from note UI.
- **Test to add:** Double-complete same key — identical 200 + single JE; without key, concurrent completes — one success.
- **Twin check:** **N** (Sales fixed; Purchase not)
---

### CR-031 — View calls `PostingService.post_note` **after** service already posts. Sales rem `(PUR-002)`
- **Module:** Purchase / Accounting
- **Location:** `backend/purchases/phase1_views.py` L61–70, L117–125 vs `notes_services.complete_*_note`
- **Type:** Latent double-post
- **Severity:** High
- **What's wrong:** View calls `PostingService.post_note` **after** service already posts. Sales removed this (B2-010) as → dead code kept alive only by dedup.
- **Trigger / repro:** Complete any purchase CN/DN with `accounting_enabled`.
- **Consequence:** Today second call returns existing JE (`PostingService.post` fast-path). Any uniqueness/purpose change — **double AP/inventory JE**.
- **Code evidence:** `complete_credit_note` posts; view posts again. Sales comment: *"second post_note — would double-post."*
- **Suggested fix direction:** Delete view-side `post_note` (sales pattern).
- **Test to add:** Assert exactly one `JournalEntry` `(PURCHASE_CREDIT_NOTE, id, COMPLETE)` after HTTP complete.
- **Twin check:** **N** (Sales fixed B2-010; Purchase still double-calls)
---

### CR-032 — Complete **capitalizes `additional_charges` into stock `unit_cost` / FIFO layers `(PUR-003)`
- **Module:** Purchase / Inventory cost vs GL
- **Location:** `PurchaseService.complete` (~L785–804); `PostingService.post_purchase` (~L1133–1139, charges — 5110)
- **Type:** Landed-cost / perpetual mismatch
- **Severity:** High
- **What's wrong:** Complete **capitalizes `additional_charges` into stock `unit_cost` / FIFO layers**, while GL books freight to **5110** and Inventory **1400 = line taxables only** (`capitalize_purchase_charges` noted as not enabled).
- **Trigger / repro:** Complete purchase with freight/packing > 0, then sell stock (FIFO/WAVG).
- **Consequence:** Layer COGS — GL inventory cost; inventory GL drifts vs quantity × layer cost; P&L/COGS wrong for paying users with freight.
- **Code evidence:** Stock: `effective_unit_cost = base_cost + charge_alloc/qty`. GL docstring: charges → 5110; not capitalized into 1400.
- **Suggested fix direction:** One policy: either capitalize charges in both GL+layers, or keep layers at taxable-only and expense freight only in GL.
- **Test to add:** Purchase + freight — assert layer `unit_cost` and JE 1400/5110 agree under chosen policy; sell — COGS matches.
- **Twin check:** **N** (Sales issues; purchase receives — purchase-specific)
---

### CR-033 — Model says BCD is for "GL / landed-cost picture"; GL puts BCD (+ ineligible IGST `(PUR-004)`
- **Module:** Purchase / BoE landed cost
- **Location:** `boe_services.py` / `PostingService.post_bill_of_entry`; `PurchaseService.complete` (no BoE amounts in `unit_cost`)
- **Type:** Incomplete landed cost
- **Severity:** High
- **What's wrong:** Model says BCD is for "GL / landed-cost picture"; GL puts BCD (+ ineligible IGST/cess) on **5110**, never into purchase stock layers. Import NON_GST complete uses invoice line prices only.
- **Trigger / repro:** Import purchase + completed BoE with BCD; stock moves at commercial price only.
- **Consequence:** Import inventory undervalued; margin/COGS wrong vs customs cash cost.
- **Code evidence:** `post_bill_of_entry`: Dr 5110 BCD; complete loop never reads `invoice.bill_of_entry.bcd_amount`.
- **Suggested fix direction:** Allocate BoE cost (BCD ± ineligible duty) into linked purchase layers on Complete, or document as expense-only and stop claiming landed-cost.
- **Test to add:** BoE+import complete — layer cost includes BCD; GL 1400/5110 consistent.
- **Twin check:** **N**
---

### CR-034 — Cancel blocks completed returns and open allocations, **not** completed credit/d `(PUR-005)`
- **Module:** Purchase / Cancel
- **Location:** `PurchaseService.cancel` (~L830–845)
- **Type:** Missing cancel guard
- **Severity:** High
- **What's wrong:** Cancel blocks completed returns and open allocations, **not** completed credit/debit notes. Restores stock + reverses purchase JE while CN/DN JEs remain.
- **Trigger / repro:** Complete purchase — standalone CN — cancel purchase.
- **Consequence:** Stock restored; AP still relieved by CN — free inventory / distorted payables/GSTR.
- **Code evidence:** Guards: returns, allocations only. No `credit_notes` / `debit_notes` filter.
- **Suggested fix direction:** Block cancel if completed CN/DN exist (or auto-cancel notes first, like return→CN).
- **Test to add:** Cancel with open CN — 400; after cancel CN — cancel OK.
- **Twin check:** **Y** (Sales cancel also omits CN/DN check)
---

### CR-035 — Sales refuses cancel when draft/in-progress returns exist. Purchase does not. `(PUR-006)`
- **Module:** Purchase / Cancel
- **Location:** `PurchaseService.cancel` vs `SalesService.cancel` R2-005
- **Type:** Missing draft-return guard
- **Severity:** Medium
- **What's wrong:** Sales refuses cancel when draft/in-progress returns exist. Purchase does not.
- **Trigger / repro:** Draft purchase return on invoice — cancel purchase.
- **Consequence:** Orphan draft return pointing at cancelled bill; complete later fails or confuses AP/stock.
- **Code evidence:** Sales `returns.exclude(COMPLETED
- **Suggested fix direction:** Copy R2-005 for purchase returns.
- **Test to add:** Draft return — cancel purchase — 400.
- **Twin check:** **N** (Sales has guard; Purchase missing)
---

### CR-036 — Locks return row, **not** source invoice. Qty headroom from unlocked aggregates  `(PUR-007)`
- **Module:** Purchase / Return
- **Location:** `PurchaseService.complete_return` (~L961–1012)
- **Type:** Race / over-return
- **Severity:** High
- **What's wrong:** Locks return row, **not** source invoice. Qty headroom from unlocked aggregates of completed returns.
- **Trigger / repro:** Two concurrent completes returning the last remaining qty.
- **Consequence:** Both can pass headroom — return more than received; stock/AP over-relieved (auto CN).
- **Code evidence:** `PurchaseReturn.objects.select_for_update`; invoice only read. Sales return same pattern.
- **Suggested fix direction:** `PurchaseInvoice.objects.select_for_update().get(pk=invoice.pk)` before headroom; or unique constraint / advisory lock.
- **Test to add:** Concurrent completes on last unit — one 200, one 400.
- **Twin check:** **Y**
---

### CR-037 — Overridden `get_permissions` **omit** `SubscriptionWritesAllowed`. Invoice/retur `(PUR-008)`
- **Module:** Purchase / Billing permissions
- **Location:** `phase1_views.py` CN/DN/PO `get_permissions`; contrast invoice/return/BoE views
- **Type:** Subscription gate bypass
- **Severity:** High
- **What's wrong:** Overridden `get_permissions` **omit** `SubscriptionWritesAllowed`. Invoice/return/BoE add it explicitly.
- **Trigger / repro:** Suspended / unpaid tenant completes CN/DN or converts PO.
- **Consequence:** Money documents after subscription should block writes.
- **Code evidence:** CN create/complete: `CanCreatePurchases` only. Invoice complete includes `SubscriptionWritesAllowed()`.
- **Suggested fix direction:** Add `SubscriptionWritesAllowed()` on all write actions (incl. convert).
- **Test to add:** Suspended company — CN complete — 402/403.
- **Twin check:** Check Sales phase1 — if Sales includes it, **N**; if also missing, **Y**. (Purchase invoice path is gated; note path is not.)
---

### CR-038 — Purchase CN/DN serializers omit `additional_charges` (and related). Sales note s `(PUR-009)`
- **Module:** Purchase / Notes API
- **Location:** `phase1_serializers.py` CN/DN Meta.fields
- **Type:** Functional gap vs Sales
- **Severity:** Medium
- **What's wrong:** Purchase CN/DN serializers omit `additional_charges` (and related). Sales note serializers expose them. Auto-return CN sets charges in service only.
- **Trigger / repro:** Manual CN for freight credit via API/UI.
- **Consequence:** Cannot record charge legs on notes; AP headroom wrong vs supplier CN.
- **Code evidence:** Purchase CN fields lack `additional_charges`; sales phase1 includes it.
- **Suggested fix direction:** Add fields + wire editor; keep company scoping.
- **Test to add:** Create CN with additional_charges — totals/GL include 5110/AP.
- **Twin check:** **N**
---

### CR-039 — Note complete POSTs without Idempotency-Key. Invoice/return/payments use `userGe `(PUR-010)`
- **Module:** Purchase / Frontend
- **Location:** `web/src/api/legacy/purchases.ts` `completePurchaseCreditNote` / debit; `PurchaseNoteEditorPage.tsx`
- **Type:** Client abuse / retry
- **Severity:** Medium
- **What's wrong:** Note complete POSTs without Idempotency-Key. Invoice/return/payments use `userGestureIdempotencyKey()`.
- **Trigger / repro:** Slow network + double submit on note editor / list complete.
- **Consequence:** Amplifies PUR-001; poor recovery vs purchase bill complete.
- **Code evidence:** `apiClient.post(.../complete/)` — no key option.
- **Suggested fix direction:** Pass gesture key like returns.
- **Test to add:** E2E double-complete note — single document/JE.
- **Twin check:** **N** if Sales note UI sends keys
---

### CR-040 — FAQ: foreign/import "not supported yet" / → hard block. Code: NON_GST + complete `(PUR-011)`
- **Module:** Purchase / Docs vs product
- **Location:** `web/src/pages/help/faqContent.tsx` (~L691, L706–711); vs `PurchaseService._assert_import_bill_of_entry`, BoE UI
- **Type:** Stale guidance / operator error
- **Severity:** Medium
- **What's wrong:** FAQ: foreign/import "not supported yet" / → hard block. Code: NON_GST + completed BoE path + `/purchases/bills-of-entry`.
- **Trigger / repro:** First import customers follow help — avoid real flow or invent workarounds.
- **Consequence:** Support load; incorrect GSTIN hacks; missed BoE ITC.
- **Code evidence:** FAQ vs `test_r024_import_complete_requires_this_invoice_boe`.
- **Suggested fix direction:** Rewrite FAQ to BoE — NON_GST link — Complete.
- **Test to add:** Doc/help snapshot or content test for import keywords.
- **Twin check:** **N**
---

### CR-041 — All lines 0% GST — `purchase_type=NON_GST`. Exempt GST bills (still GST docs) an `(PUR-012)`
- **Module:** Purchase / Bill import
- **Location:** `imports/services.py` `BillImportService._commit_purchase` (~L2894–2918)
- **Type:** Inference / classification
- **Severity:** Medium
- **What's wrong:** All lines 0% GST — `purchase_type=NON_GST`. Exempt GST bills (still GST docs) and composition can be mis-typed. RCM inference for unregistered is set on draft (good) but type flip is aggressive.
- **Trigger / repro:** OCR/import of nil-rated GST tax invoice or composition bill of supply.
- **Consequence:** Wrong register/GSTR class; Complete composition checks may not run as GST.
- **Code evidence:** `all_zero — NON_GST` + note string; not user-confirmed.
- **Suggested fix direction:** Default GST + preview confirm for → all zero — NON_GST; or supplier taxpayer_type-driven.
- **Test to add:** 0-rate REGULAR supplier — stays GST unless confirmed.
- **Twin check:** Check sales bill import — likely similar (**Y** if same helper)
---

### CR-042 — Bill commit is **all-or-nothing** in one atomic (any line error aborts). Re-comm `(PUR-013)`
- **Module:** Purchase / Bill import commit semantics
- **Location:** `BillImportService.commit` / `_commit_purchase`
- **Type:** Partial commit / re-commit (checklist)
- **Severity:** Low
- **What's wrong:** Bill commit is **all-or-nothing** in one atomic (any line error aborts). Re-commit of same job blocked by `PREVIEWED`→`COMMITTED`. Creates **draft** only (Complete separate) — good. No row-level partial draft.
- **Trigger / repro:** Mixed good/bad lines; retry committed job.
- **Consequence:** Operators must fix all lines; cannot partial-post a bill. Masters CSV partial differs.
- **Code evidence:** Raises on missing qty/rate; `job.status = COMMITTED` after success.
- **Suggested fix direction:** Document; optional → commit valid lines only if product wants it.
- **Test to add:** Already partly covered by purchase bill import tests — assert no draft on mid-commit failure.
- **Twin check:** **Y** (sales bill same service)
---

### CR-043 — DN posts AP/inventory GL only. No stock qty/layer restamp for price uplift (unli `(PUR-014)`
- **Module:** Purchase / Debit note vs inventory
- **Location:** `PurchaseNotesService.complete_debit_note`
- **Type:** Incomplete exact reversal / cost amend
- **Severity:** Medium
- **What's wrong:** DN posts AP/inventory GL only. No stock qty/layer restamp for price uplift (unlike H9 purchase amend `restamp_fifo_layers_for_price_amend`).
- **Trigger / repro:** Supplier additional debit for rate difference after goods received.
- **Consequence:** Layers stay cheap; GL inventory up — valuation split.
- **Code evidence:** DN complete — `post_note` only.
- **Suggested fix direction:** Policy: restamp layers or keep DN as AP-only and never touch 1400 for pure price DNs.
- **Test to add:** DN after purchase — layer vs 1400 policy assertion.
- **Twin check:** **Y** if sales DN also GL-only for price
---

### CR-044 — Cancel reverses BoE JE even if completed purchases still link `bill_of_entry`. N `(PUR-015)`
- **Module:** Purchase / BoE cancel
- **Location:** `BillOfEntryService.cancel`
- **Type:** Orphan linkage
- **Severity:** Medium
- **What's wrong:** Cancel reverses BoE JE even if completed purchases still link `bill_of_entry`. No check for linked completed imports.
- **Trigger / repro:** Complete BoE — complete import — cancel BoE.
- **Consequence:** Import ITC/customs AP reversed while goods/AP from purchase remain; GSTR-3B 4(A)(5) vs books diverge.
- **Code evidence:** Cancel only checks BoE status + period; no `purchase_invoices` filter.
- **Suggested fix direction:** Block cancel if linked non-cancelled purchases; or require unlink.
- **Test to add:** Linked completed purchase — BoE cancel — 400.
- **Twin check:** **N**
---

### CR-045 — Return lines lack unit snapshot; stock converts via invoice unit, headroom compa `(PUR-016)`
- **Module:** Purchase / Return UX & qty
- **Location:** `PurchaseReturnItem` (no `unit_name`); `complete_return` `_item_stock_qty` uses invoice unit map; `_returned_quantities` compares raw qty
- **Type:** Unit / exact reversal risk
- **Severity:** Medium
- **What's wrong:** Return lines lack unit snapshot; stock converts via invoice unit, headroom compares document qty. Alternate-unit products are ambiguous if UI/API send base qty.
- **Trigger / repro:** Invoice in cartons; return qty entered as pieces (or reverse).
- **Consequence:** Over/under stock return vs billed qty; auto CN amounts wrong.
- **Code evidence:** `PurchaseItem.unit_name` exists; `PurchaseReturnItem` has no unit fields; `_invoice_unit_name_by_product`.
- **Suggested fix direction:** Snapshot unit on return lines; headroom in base units.
- **Test to add:** Alternate-unit purchase — return in base — reject or convert correctly.
- **Twin check:** Check sales return line units — **None**
---

### CR-046 — Status/supplier query params passed raw; invoice list validates status enum and  `(PUR-017)`
- **Module:** Purchase / List filters
- **Location:** `PurchaseReturnViewSet.get_queryset`; `BillOfEntryViewSet.get_queryset`
- **Type:** Input validation / abuse
- **Severity:** Low
- **What's wrong:** Status/supplier query params passed raw; invoice list validates status enum and int supplier (R-038).
- **Trigger / repro:** `?status=nope` or non-numeric supplier.
- **Consequence:** Empty/odd results or DB errors vs clean 400 on invoices.
- **Code evidence:** Invoice view validates; return/BoE do not.
- **Suggested fix direction:** Same R-038 pattern.
- **Test to add:** Bad status — 400.
- **Twin check:** **N** vs purchase invoices; sales returns may share gap (**Y** if so)
---

### CR-047 — Allocation serializer scopes FKs by company; service requires `payment.supplier_ `(PUR-018)`
- **Module:** Payments / Supplier payment (purchase checklist)
- **Location:** `PaymentService.allocate_supplier_payment`; `PaymentAllocationSerializer.__init__`; `create_supplier_payment`
- **Type:** Wrong-supplier / tenancy (mitigated)
- **Severity:** Low
- **What's wrong:** Allocation serializer scopes FKs by company; service requires `payment.supplier_id == purchase_invoice.supplier_id` + `select_for_update`. SupplierPayment ModelSerializer supplier FK is default (unscoped) but create checks `supplier.company_id`.
- **Trigger / repro:** Cross-tenant / cross-supplier IDs without RLS.
- **Consequence:** With RLS+service checks, wrong-supplier alloc rejected. Residual: unscoped serializer resolve before service on non-RLS.
- **Code evidence:** `allocate_supplier_payment` L452–455; serializer company filter L173–180.
- **Suggested fix direction:** `CompanyPrimaryKeyRelatedField` on SupplierPayment.supplier / bank_account for defense in depth.
- **Test to add:** Cross-company supplier id on payment create — 400; alloc mismatched supplier — 400 (likely exists).
- **Twin check:** **Y** (receipt/customer same pattern)
---

### CR-048 — Manual serial SOLD→RETURNED crashes (missing `StockMovement.serial_numbers`) `(STK-001)`
- **Module:** Stock/Godown — Serial numbers / views
- **Location:** `backend/inventory/views.py:503` (`SerialNumberViewSet.transition`)
- **Type:** Bug
- **Severity:** Critical
- **What's wrong:** `SerialNumberViewSet.transition` queries `StockMovement.objects.only("unit_cost", "serial_numbers")` and attempts to read `mv.serial_numbers`. However, `StockMovement` has no `serial_numbers` model field (serials are tracked only on document lines and `SerialNumber` rows). Furthermore, its valuation fallback invoked `InventoryService.unit_cost`, which exists only on `InventoryValuationService`.
- **Trigger / repro:** Complete a serial sale, then submit `POST /api/v1/inventory/serial-numbers/{id}/transition/` with `{"status":"RETURNED"}`.
- **Consequence:** HTTP 500 error on every manual serial return attempt through the inventory API.
- **Code evidence:** `SerialNumberViewSet.transition` attempts to read non-existent `StockMovement.serial_numbers` and invokes missing `InventoryService.unit_cost`.
- **Suggested fix direction:** Resolve serial sale movement via invoice document items (`_sale_movement_for_serial`), route valuation fallback through `InventoryValuationService.unit_cost`.
- **Test to add:** `test_manual_serial_return_transition_does_not_crash`
- **Twin check:** n-a
- **Module:** Stock/Godown
---

### CR-049 — Manual serial return design wrong even if STK-001 fixed (status + FIFO) `(STK-002)`
- **Module:** Stock/Godown — Serial / cost layers
- **Location:** `backend/inventory/views.py:503-560`
- **Type:** Bug
- **Severity:** High
- **What's wrong:** When transitioning a SOLD serial to RETURNED, the endpoint sets status `RETURNED` instead of `AVAILABLE` and fails to call `InventoryService.restore_fifo_peels`. Since `_apply_cost_layers` intentionally skips creating new FIFO layers for `SALES_RETURN` movements (expecting peel restoration), the returned unit cannot be resold and inventory valuation is understated.
- **Trigger / repro:** Return serial via inventory transition; attempt to resell or compare `sum(layer.qty_remaining)` against `StockBalance.on_hand`.
- **Consequence:** Resale is blocked (status RETURNED, not AVAILABLE) and FIFO layers permanently drift below on-hand balance.
- **Code evidence:** Transition posts `SALES_RETURN` movement without `restore_fifo_peels`, leaving status as `RETURNED`.
- **Suggested fix direction:** On sellable return, transition status to `AVAILABLE` and invoke `InventoryService.restore_fifo_peels(sale_move, inbound)`.
- **Test to add:** `test_manual_serial_return_restores_available_and_peels`
- **Twin check:** n-a
- **Module:** Stock/Godown
---

### CR-050 — Negative-stock policy inconsistent across invoice / batch / transfer / adjust / reserve `(STK-003)`
- **Module:** Stock/Godown — Negative-stock policy
- **Location:** `backend/inventory/services.py`, `backend/sales/services.py`
- **Type:** Bug
- **Severity:** High
- **What's wrong:** `Company.NegativeStockPolicy` (`BLOCK` vs `WARN`) is inconsistently applied across modules. Unbatched sales allow negative stock under `WARN`, but batch-tracked sales under FEFO always raise an exception on shortfall. Stock transfers call `check_negative_stock` but silently discard warnings, while adjustments never surface warnings.
- **Trigger / repro:** Configure policy to `WARN`. Attempt to sell batch-tracked item short (fails with 400), or transfer more than on-hand stock (succeeds with no warning).
- **Consequence:** Inconsistent inventory behavior across warehouses and transaction types; operator confusion regarding negative stock allowance.
- **Code evidence:** `_sale_batches` hard-raises regardless of policy; `StockTransferService` discards return value of `check_negative_stock`.
- **Suggested fix direction:** Enforce unified policy behavior across standard sales, batch sales, and transfer services.
- **Test to add:** `test_negative_stock_policy_consistency_across_flows`
- **Twin check:** n-a
- **Module:** Stock/Godown
---

### CR-051 — WARN oversell: `InventoryRunningCost` floors at 0 while `StockBalance` goes negative `(STK-004)`
- **Module:** Stock/Godown — Cost layers / valuation
- **Location:** `backend/inventory/services.py:800-840` (`_apply_running_cost`)
- **Type:** Bug
- **Severity:** High
- **What's wrong:** When an oversell occurs under `WARN` policy, `_apply_running_cost` clamps quantity and inventory value to 0 once the pool is exhausted. However, `StockBalance.on_hand` goes negative. Consequently, live WAVG stock valuation reports disconnect from physical ledger quantities.
- **Trigger / repro:** Set policy to `WARN`, sell 5 units when on-hand is 1. `StockBalance.on_hand` becomes -4, while running cost pool shows 0.
- **Consequence:** Stock valuation reports diverge from physical inventory balances following any short-sale.
- **Code evidence:** `_apply_running_cost` clamps pool to zero; comments admit oversell divergence.
- **Suggested fix direction:** Track negative pool quantities or surface explicit running-cost divergence indicators during oversell.
- **Test to add:** `test_warn_oversell_running_cost_tracking`
- **Twin check:** n-a
- **Module:** Stock/Godown
---

### CR-052 — Stock count (and transfer) skip closed-period gate that adjustments use `(STK-005)`
- **Module:** Stock/Godown — Period locks
- **Location:** `backend/inventory/views.py:650-700`, `backend/inventory/services.py:1100-1150`
- **Type:** Bug
- **Severity:** High
- **What's wrong:** While manual adjustments call `assert_period_allows_money_amend`, `StockCountSessionViewSet.post` (which posts variance adjustments) and `StockTransferService.complete`/`cancel` do not check whether the effective transaction date falls in a soft-closed or closed GST/accounting period.
- **Trigger / repro:** Soft-close a period, then post a stock count session variance or complete a stock transfer dated in that closed period.
- **Consequence:** Stock variance adjustments and cost-moving transfers backdate into closed financial periods, distorting filed return numbers.
- **Code evidence:** `AdjustmentView` calls period assert; `StockCountSessionViewSet.post` and `StockTransferService` omit it.
- **Suggested fix direction:** Call `assert_period_allows_money_amend` inside `StockCountSessionViewSet.post` and `StockTransferService.complete`/`cancel`.
- **Test to add:** `test_stock_count_and_transfer_blocked_in_closed_period`
- **Twin check:** n-a
- **Module:** Stock/Godown
---

### CR-053 — Append-only hole: import void mutates `StockMovement.reference_type` `(STK-006)`
- **Status (2026-09-08):** FIXED & VERIFIED in tree (`backend/imports/services.py:2023`, `backend/inventory/models.py:116`, migration `0018_cr053_opening_stock_void_append_only.py`)
- **Module:** Stock/Godown — Movements / imports
- **Location:** `backend/imports/services.py:2023`, `backend/inventory/models.py:116`
- **Type:** Bug | Data-integrity
- **Severity:** Medium
- **What's wrong:** Voiding an opening stock import previously mutated the original `StockMovement` row in place by setting `reference_type="import_voided"` via `StockMovement.objects.filter(...).update()`, violating the immutable append-only ledger invariant.
- **Trigger / repro:** Import opening stock via CSV, then call `POST /api/v1/imports/{id}/void/`. Inspect original opening stock movement.
- **Consequence:** In-place modification of historical ledger rows destroyed audit trails and bypassed model `save()` immutability guards.
- **Code evidence:** Original code performed `StockMovement.objects.filter(pk=...).update(reference_type="import_voided")`. Fixed code retains original `reference_type="import"` and posts a new compensating `StockMovement` with `movement_type=ADJUSTMENT` and `reference_type="import_void"`.
- **Suggested fix direction:** Void operations must create append-only compensating `StockMovement` rows without altering existing records.
- **Test to add:** `tests/test_a11_a12_stock_cost.py::test_cr053_import_void_compensating_movement_only`
- **Twin check:** n-a

---

### CR-054 — Balance vs `sum(movements)`: rebuild exists, no runtime reconciliation `(STK-007)`
- **Status (2026-09-08):** FIXED & VERIFIED in tree (`backend/inventory/services.py:1128`, `backend/inventory/tasks.py:45`)
- **Module:** Stock/Godown — StockBalance drift
- **Location:** `backend/inventory/services.py:1128`, `backend/inventory/tasks.py:45`
- **Type:** Bug | Data-integrity
- **Severity:** Medium
- **What's wrong:** The hot write path updates `StockBalance` within `post_movement` under row lock, and `rebuild_stock_balances` existed as an offline CLI command, but no scheduled background runtime reconciliation verified `StockBalance.on_hand` against `sum(StockMovement.quantity)`. Any unhandled transaction failure or database manipulation could leave silent balance drift undetected.
- **Trigger / repro:** Direct database corruption of `StockBalance.on_hand` or partial transaction failure; discrepancies persist until manual admin rebuild.
- **Consequence:** UI displays inaccurate inventory on hand; false out-of-stock errors or negative oversell occur until manual remediation.
- **Code evidence:** `StockBalance` locking added in `post_movement`; Celery audit task `verify_stock_balances_integrity` added in `tasks.py` with batch reservation reconciliation.
- **Suggested fix direction:** Enforce `select_for_update` row locks on all balance writes and schedule periodic background reconciliation workers.
- **Test to add:** `tests/test_stock_flow.py::test_verify_stock_balances_integrity_task_repairs_drift` (PASSED)
- **Twin check:** Accounting AR/AP control reconciliation twin (`CR-157`).

---

### CR-055 — Transfers: two-sided atomic OK; no in-transit; DRAFT does not reserve `(STK-008)`
- **Status (2026-09-08):** VERIFIED & DOCUMENTED in tree (`backend/inventory/services.py:1312`)
- **Module:** Stock/Godown — Stock transfer
- **Location:** `backend/inventory/services.py:1312` (`StockTransferService.complete`)
- **Type:** Design-limitation | Operational
- **Severity:** Low
- **What's wrong:** Stock transfer lifecycle supports `DRAFT`, `COMPLETED`, and `CANCELLED`, but lacks an intermediate `IN_TRANSIT` state. `DRAFT` transfers hold no stock reservation at the source warehouse. Intervening sales can deplete stock between draft creation and completion, causing transfer completion to fail or go negative.
- **Trigger / repro:** Create draft transfer for remaining stock; sell same stock on POS; operator attempts to complete the transfer.
- **Consequence:** Transfer completion fails under `BLOCK` policy or triggers negative stock at source warehouse under `WARN` policy.
- **Code evidence:** `StockTransferService.complete` executes two-sided atomic transfer (OUT at source, IN at destination) under `@transaction.atomic`, but draft creation does not mutate `StockBalance.reserved`.
- **Suggested fix direction:** Document that draft transfers are non-binding; check available balance upon completion under atomic row lock.
- **Test to add:** `tests/test_a10_period_centralization.py::test_cr052_stock_transfer_complete_blocked_in_soft_closed`
- **Twin check:** Sales order reservations hold binding stock; transfers evaluate availability upon completion.

---

### CR-056 — Stock-count conflict merge preserves movement history (by design) `(STK-009)`
- **Status (2026-09-08):** VERIFIED & DOCUMENTED in tree (`backend/inventory/views.py:757`, `web/src/pages/inventory/godownConflict.test.ts`)
- **Module:** Stock/Godown — Stock count conflict resolution
- **Location:** `backend/inventory/views.py:757` (`StockCountSessionViewSet.resolve_conflicts`)
- **Type:** Design-verification | Operational
- **Severity:** Low
- **What's wrong:** When resolving physical count conflicts (`STOCK_COUNT_CONFLICT` 409), selecting `KEEP_SERVER` explicitly skips generating an adjustment movement for drifted lines but still marks the session `POSTED`. The rationale needed clear documentation to prevent operators from expecting historical movements to be rewritten.
- **Trigger / repro:** Operator counts 9 items when server has 10; an intervening inbound receipt adds 2 items (server now 12); operator posts count → 409 conflict → selects `KEEP_SERVER`.
- **Consequence:** Disputed lines retain server on-hand balance (12); no adjustment is posted, but the count session transitions to `POSTED`.
- **Code evidence:** Line 757 intentionally skips adjustment generation for lines marked `KEEP_SERVER` to prevent overwriting intervening valid transactions, preserving immutable movement history.
- **Suggested fix direction:** Confirm and document that `KEEP_SERVER` leaves server stock intact without overwriting history, while `KEEP_LOCAL` adjusts variance against current balance.
- **Test to add:** `web/src/pages/inventory/godownConflict.test.ts`
- **Twin check:** POS offline outbox sync conflict resolution.

---

### CR-057 — Serial scrap AVAILABLE always posts −1 even if available is 0 `(STK-010)`
- **Status (2026-09-08):** FIXED & VERIFIED in tree (`backend/inventory/views.py:569`, `tests/test_a6_manual_serial_return.py:91`)
- **Module:** Stock/Godown — Serial scrap
- **Location:** `backend/inventory/views.py:569` (`SerialNumberViewSet.transition`)
- **Type:** Bug | Data-integrity
- **Severity:** Medium
- **What's wrong:** When transitioning an `AVAILABLE` serial to `SCRAPPED`, the view condition `if from_status == AVAILABLE or on_hand >= 1:` evaluated to True for any `AVAILABLE` serial even if warehouse `on_hand` was zero due to prior drift or desync.
- **Trigger / repro:** Transition an `AVAILABLE` serial with 0 on-hand stock to `SCRAPPED`.
- **Consequence:** Posts a `-1` adjustment, driving `StockBalance.on_hand` negative while marking the serial `SCRAPPED`.
- **Code evidence:** Line 569 updated to require `on_hand >= 1` before allowing transition of `AVAILABLE` serial to `SCRAPPED`.
- **Suggested fix direction:** Require `on_hand >= 1` before posting scrap adjustment.
- **Test to add:** `tests/test_a6_manual_serial_return.py::test_serial_scrap_available_requires_on_hand`
- **Twin check:** Batch scrap requires positive on-hand quantity.

---

### CR-058 — Default warehouse: unique constraint + IntegrityError fallbacks are mostly sound `(STK-011)`
- **Status (2026-09-08):** VERIFIED & DOCUMENTED in tree (`backend/inventory/services.py:24`, `backend/inventory/models.py`)
- **Module:** Stock/Godown — Default warehouse
- **Location:** `backend/inventory/services.py:24` (`InventoryService.default_warehouse`)
- **Type:** Concurrency | Data-integrity
- **Severity:** Low
- **What's wrong:** Concurrent initialization or default warehouse promotion could risk race conditions without schema-level uniqueness and idempotent fallback handling.
- **Trigger / repro:** Concurrent initial company setup requests attempting to create the default warehouse simultaneously.
- **Consequence:** Potential duplicate default warehouse records per company.
- **Code evidence:** Partial database constraint `one_default_warehouse_per_company` guarantees single default per company; `default_warehouse()` catches `IntegrityError` and re-queries under row lock; promotion clears other defaults via `select_for_update`.
- **Suggested fix direction:** Enforce DB unique constraint and handle concurrency via `IntegrityError` catch-and-retry.
- **Test to add:** `tests/test_phase1_documents.py`
- **Twin check:** Default bank account / cash account singletons.

---

### CR-059 — FIFO consume/replenish on document path; verification not automated `(STK-014)`
- **Status (2026-09-08):** VERIFIED & DOCUMENTED in tree (`backend/inventory/services.py:1997`, `backend/inventory/management/commands/rebuild_running_cost.py:17`, `tests/test_a11_a12_stock_cost.py:315`)
- **Module:** Stock/Godown — Cost layers
- **Location:** `backend/inventory/services.py:1997` (`InventoryValuationService.verify_fifo_layers`)
- **Type:** Operational | Audit
- **Severity:** Medium
- **What's wrong:** FIFO layers are consumed and restored synchronously on document write paths (`complete`, `cancel`, `complete_return`), but automated periodic layer verification was not scheduled, creating risk of undetected layer drift against warehouse balance over time.
- **Trigger / repro:** Prolonged FIFO operations across high-volume sales and returns with manual stock adjustments.
- **Consequence:** Total quantity remaining in open FIFO layers could drift from `StockBalance.on_hand`, distorting balance sheet inventory valuation.
- **Code evidence:** `verify_fifo_layers` implemented in `services.py` and run via `rebuild_running_cost`; runbook procedure documented in `docs/pilot/RUNBOOKS.md`.
- **Suggested fix direction:** Integrate `verify_fifo_layers` into audit runbooks and background health checks.
- **Test to add:** `tests/test_a11_a12_stock_cost.py::test_cr059_verify_fifo_layers_documented`
- **Twin check:** Running cost WAVG pool verification.

---

### CR-060### CR-060 — Dashboard AR KPI vs AR aging use different ledgers when books are on `(RPT-001)`
- **Module:** Reporting — Dashboard KPIs / AR aging
- **Location:** `backend/ledgers/services.py` (~269–393, 447–453) `bulk_customer_outstanding`; `backend/reporting/services.py` (101–167) `receivables_aging`
- **Type:** Data-integrity | Bug
- **Severity:** Critical
- **What's wrong:** When `accounting_enabled` and outstanding basis is not `DOCUMENTS_ALWAYS`, company receivables switch to GL 1200/2300 while aging always uses document invoice — CN + DN — allocation. Dashboard returns both.
- **Trigger / repro:** Enable accounting (default GL_WHEN_BOOKS), post sales + receipt with GL/doc drift or advances on 2300; compare `/api/v1/dashboard/` `receivables` vs sum of `receivables_aging`.
- **Consequence:** Paying tenants see Receivables — sum(aging buckets); cards and aging chart disagree.
- **Code evidence:** `LedgerService.company_receivables` — GL path; `ReportService.receivables_aging` always document-based.
- **Suggested fix direction:** One definition — age GL party balances or drive KPI from the same document bulk used for aging; assert `sum(aging) == receivables` for both bases.
- **Test to add:** With books on, assert dashboard receivables equals sum of aging buckets (and equals document bulk when basis=DOCUMENTS_ALWAYS).
- **Twin check:** n/a (AP aging vs payables KPI — check same pattern)

### CR-061 — AR aging allocation filter — party AR document formula `(RPT-002)`
- **Module:** Reporting — AR aging
- **Location:** `backend/reporting/services.py:133-138`; `backend/ledgers/services.py:889-892` vs `421-427`
- **Type:** Data-integrity | Sales/Purchase-inconsistency (internal formula drift)
- **Severity:** High
- **What's wrong:** Aging / `bulk_sales_invoice_outstanding` filters allocations only by `sales_invoice_id` + `reversed_at__isnull`. Party bulk AR also requires `receipt__isnull=False` and `supplier_payment__isnull=True` (R2-020).
- **Trigger / repro:** Allocation on a sales invoice with `supplier_payment` set (or no receipt); compare aging vs customer outstanding.
- **Consequence:** Mis-typed/cross-linked allocations change aging vs party outstanding on document basis.
- **Code evidence:** Filter mismatch between aging and R2-020 party filters.
- **Suggested fix direction:** Align aging and `bulk_sales_invoice_outstanding` with R2-020 filters.
- **Test to add:** Allocation with supplier_payment set must not reduce sales AR aging.
- **Twin check:** Purchase/AP aging twin filters

### CR-062 — Inventory summary qty from StockBalance cache, not sum(StockMovement) `(RPT-003)`
- **Module:** Reporting — Stock summary
- **Location:** `backend/reporting/services.py:454-490` `inventory_summary`; `backend/inventory/models.py` (StockBalance cache docstring)
- **Type:** Data-integrity
- **Severity:** Critical
- **What's wrong:** Inventory summary reads `StockBalance` for on_hand/reserved/available. Valuation may use movements/running cost — qty and value can come from different stores. Violates → stock summary = sum(movements) checklist.
- **Trigger / repro:** Corrupt or skip balance update, leave movements correct; open inventory report / CSV export.
- **Consequence:** Drifted balances under/overstate stock report; BS inventory_valuation may not match summary.
- **Code evidence:** Iterates StockBalance; valuation path separate.
- **Suggested fix direction:** Derive on-hand from movements (or assert balance==movement sum before report); fail closed on drift.
- **Test to add:** Force balance vs sum(movements); summary must not silently trust balance (or recon report flags drift).
- **Twin check:** n/a (Stock module owns write path)

### CR-063 — Sales/purchase registers include CANCELLED documents by default `(RPT-004)`
- **Module:** Reporting — Registers / exports
- **Location:** `backend/reporting/services.py:266-267, 365-367`
- **Type:** Bug
- **Severity:** Critical
- **What's wrong:** Registers `.exclude(status=DRAFT)` only — cancelled remain in rows and totals. GST builders correctly use COMPLETED/RETURNED only.
- **Trigger / repro:** Complete then cancel an invoice; GET sales-register / export without status= — cancelled row still in totals.
- **Consequence:** Register totals/exports overstate turnover vs GSTR / ops truth.
- **Code evidence:** exclude DRAFT only; cancelled included.
- **Suggested fix direction:** Default to COMPLETED/RETURNED (or exclude CANCELLED); keep optional status filter.
- **Test to add:** Cancelled invoice excluded from default register totals.
- **Twin check:** y — both sales and purchase registers

### CR-064 — Dashboard MTD purchases not net of purchase CNs/DNs `(RPT-005)`
- **Module:** Reporting — Dashboard KPIs
- **Location:** `backend/reporting/services.py:207-230` vs sales path 183–206
- **Type:** Sales/Purchase-inconsistency | Bug
- **Severity:** High
- **What's wrong:** `purchases_this_month` sums COMPLETED PIs only; sales today/MTD nets CNs/DNs. Purchase register does net notes.
- **Trigger / repro:** Complete PI then completed purchase CN same month; dashboard purchases unchanged, register totals drop.
- **Consequence:** Purchase KPI disagrees with register/books after returns.
- **Code evidence:** Sales nets notes; purchases do not.
- **Suggested fix direction:** Mirror sales KPI: → CN +DN on completed notes in period.
- **Test to add:** MTD purchases after CN equals PI — CN.
- **Twin check:** y — sales already correct

### CR-065 — Opening-balance exclusion inconsistent (notes vs is_opening_balance) `(RPT-006)`
- **Module:** Reporting — Dashboard / GST / AR
- **Location:** `backend/reporting/services.py:179-209`; `backend/reporting/gst_returns.py:287,362`
- **Type:** Data-integrity | Missing-validation (predicate drift)
- **Severity:** High
- **What's wrong:** Dashboard excludes `notes="TALLY_OPENING"`; GSTR uses `is_opening_balance=False`; AR/aging have no opening filter.
- **Trigger / repro:** Opening SI/PI with `is_opening_balance=True`, notes — `TALLY_OPENING`; compare dashboard vs GSTR.
- **Consequence:** Openings inflate sales KPI and AR while GSTR excludes them (or reverse).
- **Code evidence:** Two predicates + AR unfiltered.
- **Suggested fix direction:** Single predicate (`is_opening_balance`) on all financial aggregates.
- **Test to add:** Opening flag alone excludes from dashboard and AR; notes string alone not required.
- **Twin check:** y — sales and purchase openings

### CR-066 — product_sales / customer_sales ignore credit/debit notes `(RPT-007)`
- **Module:** Reporting — Sales analytics
- **Location:** `backend/reporting/services.py:542-589`
- **Type:** Bug
- **Severity:** High
- **What's wrong:** Product/customer sales sum invoice lines/totals only; dashboard sales nets notes.
- **Trigger / repro:** Invoice + completed CN; product/customer report still shows full invoice.
- **Consequence:** Rankings overstate net sales after returns.
- **Code evidence:** NET_SALES invoices only; no note netting.
- **Suggested fix direction:** Net note lines / party note totals for same date window.
- **Test to add:** product_sales after CN reflects net qty/amount.
- **Twin check:** n/a (purchase analytics twin if any)

### CR-067 — Warehouse filter on registers not applied to note rows `(RPT-008)`
- **Module:** Reporting — Sales/purchase register
- **Location:** `backend/reporting/services.py:271-315, 372-409`
- **Type:** Bug
- **Severity:** Medium
- **What's wrong:** Invoice qs filtered by warehouse_id; CN/DN qs are not.
- **Trigger / repro:** Two warehouses; CN on WH-B while filtering WH-A.
- **Consequence:** Warehouse-scoped register mixes filtered invoices with company-wide notes.
- **Code evidence:** warehouse filter only on invoice queryset.
- **Suggested fix direction:** Filter notes via parent invoice warehouse (or exclude notes when warehouse set).
- **Test to add:** Warehouse filter excludes notes for other warehouses.
- **Twin check:** y — both registers

### CR-068 — Inventory summary warehouse query param not int-normalized `(RPT-009)`
- **Module:** Reporting — Inventory summary API
- **Location:** `backend/reporting/views.py:144`
- **Type:** Missing-validation | Bug
- **Severity:** Medium
- **What's wrong:** Raw `request.query_params.get("warehouse")` vs `_int_or_none` on sibling views.
- **Trigger / repro:** `?warehouse=abc` or `warehouse=` on inventory-summary.
- **Consequence:** Inconsistent filter miss or 500.
- **Code evidence:** No `_int_or_none`.
- **Suggested fix direction:** Use `_int_or_none` like sibling views.
- **Test to add:** Non-integer warehouse returns 400 or ignored consistently.
- **Twin check:** n/a

### CR-069 — GSTR-3B net_payable_hint subtracts full 2B ITC, not recommended_claimable `(RPT-010)`
- **Module:** Reporting — GSTR-3B
- **Location:** `backend/reporting/gst_returns.py:1587-1612, 1867-1877`
- **Type:** Bug | Data-integrity
- **Severity:** Critical
- **What's wrong:** `recommended_claimable = min(books, gstr2b_matched)` when 2B matched, but `tax_payable_summary.net_payable_hint` subtracts full `itc_2b` heads.
- **Trigger / repro:** Books ITC 100, matched 2B 150 — recommended 100 but net_payable subtracts 150.
- **Consequence:** CA/UI hint understates tax payable.
- **Code evidence:** Different ITC heads for recommended vs net payable.
- **Suggested fix direction:** Net payable must use same heads as `recommended_claimable`.
- **Test to add:** net_payable_hint uses min(books,2B) when 2B > books.
- **Twin check:** n/a

### CR-070 — GSTR RCM line tax rebuilt in report path when line taxes are zero `(RPT-011)`
- **Module:** Reporting — GSTR-1 rate buckets
- **Location:** `backend/reporting/gst_returns.py:247-269`
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** `_rate_buckets` recomputes `q2(taxable * rate/100)` when RCM and line taxes are zero — diverges from write-path stored taxes.
- **Trigger / repro:** Legacy RCM invoice with zero line tax fields, non-zero header RCM memos; compare section tax vs header totals.
- **Consequence:** Worksheet rate buckets diverge from invoice headers / GL by paise.
- **Code evidence:** Rebuild branch in `_rate_buckets`.
- **Suggested fix direction:** Prefer stored line/header tax; rebuild only behind explicit migration flag.
- **Test to add:** RCM zero-line-tax invoice buckets match header RCM memos, not recomputed rate.
- **Twin check:** n/a

### CR-071 — HSN section buckets use gst_rate, rate tables use applied_rate `(RPT-012)`
- **Module:** Reporting — GSTR-1 HSN vs B2
- **Location:** `backend/reporting/gst_returns_sections.py:13`; `backend/reporting/gst_returns.py:241`
- **Type:** Data-integrity | Bug
- **Severity:** High
- **What's wrong:** `accumulate_hsn_line` keys on `gst_rate`; `_rate_buckets` prefers `applied_rate`.
- **Trigger / repro:** Line with `applied_rate != gst_rate`; compare HSN rate key vs B2 rate.
- **Consequence:** HSN (and GSTR-9 table 17) disagree with B2B/B2CS rate rows.
- **Code evidence:** Different rate fields.
- **Suggested fix direction:** Same rate field as GSTR (`applied_rate` with gst_rate fallback).
- **Test to add:** applied_rate vs gst_rate — HSN and B2 same rate key.
- **Twin check:** n/a

### CR-072 — Bill of Entry ITC period filter is Python-side full scan `(RPT-013)`
- **Module:** Reporting — GSTR-3B / GSTR-9
- **Location:** `backend/reporting/gst_returns.py:1479-1484, 2031-2038`
- **Type:** Improvement | Bug (unbounded)
- **Severity:** High
- **What's wrong:** Loads all COMPLETED+ELIGIBLE BOEs then filters `resolved_itc_period() == period` in Python; GSTR-9 loops ×12 months.
- **Trigger / repro:** Many historical BOEs; generate GSTR-9 FY.
- **Consequence:** Unbounded memory/CPU on import-heavy tenants; easy to miss DB date bounds.
- **Code evidence:** Full queryset then Python period match.
- **Suggested fix direction:** Filter `itc_period` / `boe_date` in SQL to month/FY window.
- **Test to add:** BOE outside period not loaded (or assert queryset filtered).
- **Twin check:** n/a

### CR-073 — GSTR-9 Table 8 note still describes obsolete import heuristic `(RPT-014)`
- **Module:** Reporting — GSTR-9
- **Location:** `backend/reporting/gst_returns.py:2150-2153`
- **Type:** Silent-failure (honesty) | Broken-feature (docs vs code)
- **Severity:** Medium
- **What's wrong:** Import ITC now from BillOfEntry but table 8 note still says → IGST on purchases without supplier GSTIN.
- **Trigger / repro:** Read GSTR-9 table 8 notes in API response.
- **Consequence:** CA misreads worksheet basis.
- **Code evidence:** Stale note string vs BOE source at 2023–2038.
- **Suggested fix direction:** Align note with BOE source.
- **Test to add:** Snapshot/assert note text mentions BoE.
- **Twin check:** n/a

### CR-074 — Exports and cash book materialize full payloads (no streaming) `(RPT-015)`
- **Module:** Reporting — Export / memory
- **Location:** `backend/reporting/views.py:1254-1270, 189-238`
- **Type:** Improvement
- **Severity:** High
- **What's wrong:** ExportView builds full row list — StringIO CSV; cash book XLSX / GSTR XLSX / CA zip in-memory. Dated large ranges unbounded (5000 cap only when date_from missing).
- **Trigger / repro:** Export sales-register for multi-year date_from/date_to.
- **Consequence:** Memory spikes / timeouts for multi-year tenants.
- **Code evidence:** Full materialization; no max span on dated exports.
- **Suggested fix direction:** Require max span; stream CSV; paginate JSON registers.
- **Test to add:** Oversized range returns 400 with clear max-span error.
- **Twin check:** n/a

### CR-075 — Cancelled-numbers register N+1 + loads all cancelled docs `(RPT-016)`
- **Module:** Reporting — Statutory cancelled register
- **Location:** `backend/reporting/views.py:539-611`
- **Type:** Improvement
- **Severity:** Medium
- **What's wrong:** Per-doc `_reason(...)` query; FY filter in Python after fetching all cancelled.
- **Trigger / repro:** Large cancelled history; open cancelled-numbers register.
- **Consequence:** Slow/heavy; not date-SQL-bounded.
- **Code evidence:** Loop with per-doc reason query; FY filter post-fetch.
- **Suggested fix direction:** Prefetch cancel events; filter FY in DB.
- **Test to add:** Prefetch/assert query count bounded.
- **Twin check:** n/a

### CR-076 — Cash book (receipts/payments) — GL cash-flow aid `(RPT-017)`
- **Module:** Reporting — Cash reports
- **Location:** `backend/reporting/services.py:592-761`; `backend/accounting/reports.py:181-257`
- **Type:** Data-integrity (dual story)
- **Severity:** Medium
- **What's wrong:** Dashboard cash_position / cash book from posted receipts & supplier payments; accounting cash_flow from JournalLines on 1100/1500*.
- **Trigger / repro:** Books on with journals that don't match receipt docs 1:1.
- **Consequence:** Two cash stories for same company when books on.
- **Code evidence:** Different source tables.
- **Suggested fix direction:** Label clearly and/or reconcile; don't mix KPI sources without disclaimer.
- **Test to add:** With books on, document mismatch surfaces in health/recon or UI label.
- **Twin check:** Accounting module

### CR-077 — Accounting cash_flow iterates every cash journal line in Python `(RPT-018)`
- **Module:** Reporting / Accounting — cash_flow
- **Location:** `backend/accounting/reports.py:212-226`
- **Type:** Performance / Improvement
- **Severity:** Medium
- **What's wrong:** `cash_flow` report iterates every cash journal line (`for line in qs:`) in Python with `select_related`, performing manual arithmetic in memory rather than using database aggregation.
- **Trigger / repro:** Load cash-flow report for a high-volume company with thousands of posted journal lines.
- **Consequence:** Slow response times and high memory consumption on cash-flow reports for large tenants.
- **Code evidence:** Python loop over all lines in `reports.py:212-226` instead of `QuerySet.aggregate`.
- **Suggested fix direction:** Use `values("source_type").annotate(Sum("debit"), Sum("credit"))` to push aggregation into the database.
- **Test to add:** Benchmark query count and execution time on large journal entry fixture.
- **Twin check:** n/a

#### Reporting coverage notes
- Aggregations generally company-scoped; registers/dashboard draft-out but cancelled-in (RPT-004).
- Stock summary qty uses StockBalance (RPT-003); GST worksheets solid with footing checks; issues RPT-010–014.
- Feature flags: backend `assert_gstr_enabled`; frontend `VITE_ENABLE_GSTR`. Live GSP gated. Offline 2B = paying path.
- Highest priority: RPT-001, RPT-003, RPT-004, RPT-010.

## ACC-001 — Journal lines created outside entry savepoint

---
## ACC-002 — `PostingService.reverse` not atomic with status flip
---
## ACC-003 — `PostingService.post` ignores GST period locks
---
## ACC-004 — Period close vs concurrent post (TOCTOU)
---
## ACC-005 — Dual ledger can diverge; health check does not compare documents vs GL
---
## ACC-006 — Purchase credit/debit notes do not reverse TDS payable (2265)
---
## ACC-007 — TDS amount-vs-rate override is silent (unlike TCS 206C)
---
## ACC-008 — Cess GL present; purchase tax drift weaker than sales
---
## ACC-009 — Manual vouchers: balance OK; `books_start_date` bypassed
---
## ACC-010 — `backfill_missing_postings` / `backfill_accounting_postings` safety gaps
---
## ACC-011 — Balance check does not quantize lines to 2 dp before commit
---
## ACC-012 — Feature-flag gating: UI dual-key; API is `accounting_enabled` only
---
## Provisional ID — CR map
---
## Top 10 must-fix-before-launch
Ordered by severity × how core the flow is for first paying retailers:
1. **CR-001** (Critical) — POS online cash retry remints idempotency after complete — double stock / unpaid invoice
2. **CR-078** (Critical) — `PostingService.post` commits JE header without lines; retry returns empty POSTED journal
3. **CR-014 / CR-036** (High) — Concurrent sales/purchase returns do not lock source invoice — over-return stock + auto-CN
4. **CR-063** (Critical) — Sales/purchase registers include CANCELLED — overstated turnover vs GSTR
5. **CR-069** (Critical) — GSTR-3B `net_payable_hint` subtracts full 2B ITC, not `recommended_claimable`
6. **CR-060** (Critical) — Dashboard AR — AR aging when books/GL outstanding is on
7. **CR-062** (Critical) — Inventory summary qty from `StockBalance` cache, not `sum(StockMovement)`
8. **CR-048 / CR-049** (Critical/High) — Manual serial return crashes; even fixed, wrong status + no FIFO peel restore
9. **CR-030 / CR-031** (High) — Purchase CN/DN complete lacks money idempotency and still double-calls `post_note`
10. **CR-032 / CR-050** (High) — Freight capitalized into layers but GL expenses to 5110; WARN negative-stock policy split-brain
## Cross-cutting themes
1. **Sales/Purchase twin drift** — cancel guards, note idempotency, list balance, return locking, subscription write gates fixed on one side only (e.g. CR-030/031 vs sales; CR-035 vs R2-005; CR-037 — R-012).
2. **Check-then-act without locking the business key** — return headroom (CR-014/036), period close vs post (CR-081), draft transfer races (CR-055).
3. **Dual sources of truth** — documents vs GL outstanding (CR-060/082); `StockBalance` vs movements (CR-062/054); inventory layers vs GL 1400/5110 (CR-032/033).
4. **Multi-step money without durable client resume** — POS complete→receipt (CR-001/002); half-success states.
5. **Period gates not centralized** — strong on document Complete; holes in `PostingService` (CR-080), stock count/transfer (CR-052), delivery challan (CR-019), backfills (CR-087).
## Cross-reference pass
Sources: `bugs/INDEX.md` (2026-07), `docs/reviews/FINDINGS_2026-09-05.md` / `FIX_PLAN_2026-09-05.md` (R-001–R-088), `MASTER_ISSUE_REGISTER.md`, module agent reads of live code.
### Highest-value: prior fixed / open items that this pass confirms or revises
### Per Critical / launch-blocking CR
### Representative High CRs
### Explicitly not re-opened as Critical here
- BUG-703 media auth, BUG-109 cross-tenant attach, BUG-102 OTP SMS stub — out of module scope; still launch risks if unrepaired (see `bugs/INDEX.md` top 15).
- Live NIC e-invoice / GSP failures in pytest — expected darkness; failures noted in test summary only.
- **5 Sep quality review (R-001–R-088)** remains a parallel open set — see [`FINDINGS_2026-09-05.md`](./FINDINGS_2026-09-05.md) / [`FIX_PLAN_2026-09-05.md`](./FIX_PLAN_2026-09-05.md). Only explicit cross-closes: CR-037 / R-012, CR-069 / R-016, CR-031 / B2-010 twin, CR-035 / R2-005.
### Twin checks still open (resolve during A7 / A9 / A11 / A14)
Agents marked some Sales ↔ Purchase twins as → Check / Partial. Treat as follow-ups when the parent CR ships:
### Artifact caveats (how to read this register)
1. **CR IDs are permanent and append-only.** Invalid findings are marked Invalid with reason — never renumbered.
2. **Census — pilot-go scope.** 31 High includes CR-002 (accepted for Phase 0) and Phase 2+ Highs (A10–A13). Pilot success = 7 Criticals + A1–A9 Highs.
3. **Pytest numbers are a snapshot** of build `5ba05c7`. Re-record before branching (fix plan Phase → 1).
4. **This file does not own owners/dates** — the fix plan tracker is `[ ]`/`[x]` only; assign in your project board when cutting A1.
5. **STK-012 / STK-013** are intentional non-findings (Info/pass); see Coverage summary.
---
## Appendix — module drafts (verbatim)
### POS draft
Source: [POS review](01544d73-fd94-4832-8e7a-8b2a67562dd9)
### POS-001 — Online cash retry remints idempotency key after partial success
- **Module:** POS — checkout / cash path
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
- **Module:** POS — sales + payments
- **Location:** `PosPage.tsx:648–669`; `flushPosCheckout.ts:44–134`; `sales/services.py:690` (`SalesService.complete`); `payments/services.py:226` / `:390`
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** POS MVP chains separate HTTP calls, each with its own `transaction.atomic`: invoice create — complete (stock+GL) — receipt — allocation — thermal GET. There is no server "POS checkout" that commits money+stock together.
- **Trigger / repro:** Fail any step after complete (receipt 5xx, alloc validation, client crash).
- **Consequence:** Valid COMPLETED unpaid invoices, or posted unallocated receipts; cashier UX must recover manually. Amplifies POS-001.
- **Code evidence:** Four distinct service entrypoints; complete ends before `PaymentService.create_receipt`.
- **Suggested fix direction:** Prefer a single authenticated `POS checkout` (or receipt+allocate-in-complete) under one idempotency scope; until then, durable client resume (POS-001) is mandatory.
- **Test to add:** `pos_checkout_half_success_matrix_complete_ok_receipt_fail`
- **Twin check:** Sales/Purchase equivalent — same bug? y (invoice complete then separate receipt is the shared pattern)
### POS-003 — POS nav/route ignores `canCreatePayments` while receipt APIs require it
- **Module:** POS — permissions / feature gate
- **Location:** `web/src/navigation/menu.ts:46`; `web/src/App.tsx:264–266`; `payments/views.py:125–127` (`CustomerReceiptViewSet.get_permissions`); `sales/views.py:87–90`
- **Type:** Broken-feature
- **Severity:** High
- **What's wrong:** POS is shown when `canCreateSales` only. Receipt/allocation create needs `CanCreatePayments`. A membership with sales create and payments create revoked can complete (stock out) then get 403 on receipt.
- **Trigger / repro:** User with `can_create_sales=True`, `can_create_payments=False`; run cash POS.
- **Consequence:** Completed unpaid sale; stock gone; cashier blocked from finishing payment in POS.
- **Code evidence:** `allowPos` / menu use `canCreateSales` only; receipt create returns `CanCreatePayments()`.
- **Suggested fix direction:** Gate POS on `canCreateSales && canCreatePayments` (and optionally block complete if payments capability missing for RETAIL/POS flows).
- **Test to add:** `pos_hidden_without_can_create_payments` + API 403 after complete for that role
- **Twin check:** Sales/Purchase equivalent — same bug? n (New Invoice does not auto-receipt)
### POS-004 — Offline walk-in customer create not bound to draft — duplicate parties on flush retry
- **Module:** POS — offline flush
- **Location:** `web/src/offline/flushPosCheckout.ts:23–30`; `PosPage.tsx:877–897` (enqueue with `customerId` optional)
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
- **Module:** POS — receipt print
- **Location:** `web/src/pages/pos/PosPage.tsx:503–510` (`finishSale`)
- **Type:** Silent-failure
- **Severity:** Medium
- **What's wrong:** `downloadInvoiceThermalPdf` errors are caught with an empty block; sale still shows success. Backend correctly 400s drafts (`sales/views.py:383–391`).
- **Trigger / repro:** Complete+pay OK; thermal endpoint 500 / offline; or print blocked.
- **Consequence:** Cashier thinks bill printed; customer leaves without slip; no in-app retry CTA.
- **Code evidence:** `catch { // Thermal print fallback }` with no message/flag.
- **Suggested fix direction:** Surface non-blocking warning + "Print again" using invoice id (already known).
- **Test to add:** `finishSale_thermal_failure_surfaces_warning`
- **Twin check:** Sales/Purchase equivalent — same bug? n (history PDF usually surfaces errors)
### POS-006 — Offline flush success does not print thermal receipts
- **Module:** POS — offline sync
- **Location:** `PosPage.tsx:748–774` (`flushPendingDraft`); `flushPosCheckout.ts` (ends after allocate)
- **Type:** Broken-feature
- **Severity:** Medium
- **What's wrong:** Successful outbox flush clears cart and shows sync count only; no thermal download/print for flushed invoices.
- **Trigger / repro:** Offline cash sale — online — auto flush.
- **Consequence:** Offline-originated sales routinely have no counter slip unless cashier finds them in history.
- **Code evidence:** `flushPosDraft` has no PDF step; flush success path only sets message.
- **Suggested fix direction:** Return completed ids from flush and print (or queue print) per sale; or open history links.
- **Test to add:** `flushPendingDraft_triggers_thermal_for_each_flushed_sale`
- **Twin check:** Sales/Purchase equivalent — same bug? n-a
### POS-007 — Tender gate uses client-computed totals; receipt books server `grandTotal`
- **Module:** POS — tax / cash tender
- **Location:** `PosPage.tsx:367–382`, `:849–851`, `:648–667`; server recompute in `sales/services.py:754–764`
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
- **Module:** POS — feature flags
- **Location:** `backend/config/settings.py:849`; `backend/core/services/feature_flags.py:29–47`; contrast `backend/manufacturing/permissions.py:7–8`; frontend `features.ts:101–102`, `PosPage.tsx:133–135`
- **Type:** Improvement
- **Severity:** Medium
- **What's wrong:** Checklist requires nav vs API flag consistency. Manufacturing denies API when flag off; POS flag only hides route/nav. RETAIL complete/receipt remain callable with normal sales/payment perms when POS is disabled.
- **Trigger / repro:** `ENABLE_POS=false` for company; POST sales invoice complete + receipt as staff.
- **Consequence:** Flag does not actually disable counter settlement path; compliance/plan packaging leak.
- **Code evidence:** No backend `ENABLE_POS` check in sales/payments views; only env/JSON exposure.
- **Suggested fix direction:** If POS is a paid module, gate a dedicated checkout endpoint or RETAIL+same-day receipt pairing; or document that POS is UI sugar only.
- **Test to add:** `enable_pos_false_blocks_pos_checkout_endpoint` (once endpoint exists) or explicit product decision test
- **Twin check:** Sales/Purchase equivalent — same bug? n (POS-specific flag)
### POS-009 — Inclusive price mode: line table totals skip exclusive extraction
- **Module:** POS — UI totals
- **Location:** `PosPage.tsx:1227–1247` (table) vs `:333–365` (`lineTaxes` for tender panel)
- **Type:** Bug
- **Severity:** Medium
- **What's wrong:** Tender panel extracts exclusive unit price when `priceMode === 'INCLUSIVE'`; per-line table `calculateLineTax` uses raw `posLineUnitPrice` without extraction — overstated line totals vs pay panel.
- **Trigger / repro:** Company inclusive pricing; add GST item; compare line Total column vs tender Total.
- **Consequence:** Cashier distrust / wrong mental tender; increases POS-007 risk.
- **Code evidence:** `extractExclusiveFromInclusiveLine` only in `lineTaxes` memo, not table map.
- **Suggested fix direction:** Share one line-tax helper for table and tender.
- **Test to add:** `pos_inclusive_line_row_matches_tender_total`
- **Twin check:** Sales/Purchase equivalent — same bug? n (invoice editor likely shared helpers)
### POS-010 — Unknown complete status clears cart without confirming completion
- **Module:** POS — createCompletedInvoice recovery
- **Location:** `PosPage.tsx:624–636`
- **Type:** Bug
- **Severity:** Medium
- **What's wrong:** If complete errors and status probe also fails, UI clears cart, clears idempotency key, and shows unpaid recover for an id that may still be DRAFT (complete never committed).
- **Trigger / repro:** Flaky network during complete; GET invoice also fails.
- **Consequence:** Lost cart lines; possible orphan DRAFT; misleading → left unpaid; recover link.
- **Code evidence:** `setCart([]); setIdempotencyKey(null);` on unknown branch before rethrow.
- **Suggested fix direction:** Keep cart + key; show → verify sale #id without claiming unpaid completed; only clear after confirmed COMPLETED/DELETED.
- **Test to add:** `createCompletedInvoice_unknown_status_keeps_cart_and_key`
- **Twin check:** Sales/Purchase equivalent — same bug? n-a
### POS-011 — Cash tendered / change never posted (display-only)
- **Module:** POS — cash handling
- **Location:** `PosPage.tsx:380–382`, `:652–660`; `PaymentService.create_receipt` amount = invoice total only
- **Type:** Improvement
- **Severity:** Low
- **What's wrong:** Overpay/change is UI-only. Receipt always equals invoice total (correct for AR) but till variance is not auditable.
- **Trigger / repro:** Tender → 2000 on → 850 bill; complete.
- **Consequence:** No system record of cash in drawer vs sale; disputes rely on memory.
- **Code evidence:** `changeDue` local; receipt `amount: invoiceTotal`.
- **Suggested fix direction:** Optional tendered/change fields on receipt notes or cash-session object.
- **Test to add:** n-a until product wants till sessions
- **Twin check:** Sales/Purchase equivalent — same bug? n-a
### POS-012 — POS qty control lacks 3dp money discipline / upper bound
- **Module:** POS — validation
- **Location:** `PosPage.tsx:1286–1293`; server `core/models.py:77–78`; `_validate_lines` `sales/services.py:48–49`
- **Type:** Missing-validation
- **Severity:** Low
- **What's wrong:** Qty `NumericField` has `min={1}` (blocks fractional &lt;1 in UI oddly vs server 0.001) and no `decimals={3}` / `max`. Abuse huge qty still allowed server-side (max_digits only).
- **Trigger / repro:** Type qty `999999999` or rely on API for `0.5` while UI steppers assume integers.
- **Consequence:** Awkward UX for catch-weight; weak abuse ceiling for fat-finger / malicious qty.
- **Code evidence:** No decimals/max on POS qty field; server allows → 0.001 up to field limits.
- **Suggested fix direction:** Align UI with 3dp qty + sane max; keep server as source of truth.
- **Test to add:** `pos_rejects_qty_below_0_001_and_caps_absurd_qty`
- **Twin check:** Sales/Purchase equivalent — same bug? y (shared line model)
### POS-013 — Stock chips use 60s cached balances (advisory only)
- **Module:** POS — inventory display
- **Location:** `PosPage.tsx:238–256`
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
- **Core write path reviewed:** Client POS cash/UPI — `createSalesInvoice` (`sales_invoice_create`) — `SalesService.complete` (`transaction.atomic` + `select_for_update` invoice/customer; stock via `CogsService.post_sale_stock_and_cogs` — `InventoryService.post_movement` balance lock; GL `PostingService`; PDF via `on_commit`/`sales_invoice.completed`) — `PaymentService.create_receipt` — `allocate_receipt` — thermal GET. Offline: `enqueueDraft` — `flushPosDraft` with `${key}`, `${key}-complete`, `${key}-receipt`, `${key}-alloc`.
- **Reversal path:** POS has no in-flow void; invoice cancel restores via new ADJUSTMENT movements (append-only), blocks cancel if allocations exist — returns/CN are separate sales module.
- **Concurrency:** Under `negative_stock_policy=BLOCK`, two terminals selling last unit serialize on `StockBalance.select_for_update` inside `post_movement` (covered by `test_concurrent_stock_oversell_blocked`). Advisory `check_negative_stock` before post is not the authority. FEFO batch lines hard-fail shortfall in `_sale_batches` even when policy would allow negatives.
- **Idempotency scopes:** POS uses `sales_invoice_create`, `sales_invoice_complete`, `receipt_create`, `allocation_create` — all present in `MONEY_IDEMPOTENCY_SCOPES` (no missing-scope finding).
- **Tests present:** **thin** for end-to-end POS money path. Frontend: `posStatus.test.ts`, `flushPosCheckout.test.ts`, `invoiceDraftCache*.test.ts`. Backend: thermal PDF tests; place-of-supply → pos naming in GST tests; stock race tests — **missing** names: `pos_online_cash_retry_after_receipt_failure_does_not_double_complete`, `pos_checkout_half_success_matrix_*`, `pos_requires_can_create_payments`, `flushPosDraft_pending_customer_retry_does_not_duplicate_customer`, concurrent complete of two RETAIL invoices for last unit via full HTTP complete (not only raw `post_movement`).
- **Files read:** `web/src/pages/pos/PosPage.tsx`, `posStatus.ts`, `posStatus.test.ts`; `web/src/offline/flushPosCheckout.ts`, `flushPosCheckout.test.ts`, `invoiceDraftCache.ts` (+ tests); `web/src/api/client.ts`, `api/legacy/sales.ts`, `api/legacy/payments.ts`, `api/legacy/masters.ts`; `web/src/auth/AuthContext.tsx`; `web/src/config/features.ts`, `featureFlags.ts`; `web/src/navigation/menu.ts`, `App.tsx`; `web/src/utils/permissions.ts`; `backend/sales/views.py`, `services.py`, `serializers.py`, `cogs_service.py`, `handlers.py`, `models.py` (SalesItem); `backend/sales/pdf` via thermal action; `backend/payments/views.py`, `services.py`; `backend/inventory/services.py`, `models.py` (StockMovement/StockBalance); `backend/core/idempotency.py`, `viewsets.py`, `permissions.py`, `models.py` (DocumentLineModel), `services/feature_flags.py`; `backend/config/settings.py`; `backend/accounts/models.py` (capability defaults); `backend/manufacturing/permissions.py` (flag contrast); `backend/tests/test_concurrency_races.py`, `test_pdf_and_share.py` (thermal), `test_phase2_gst.py` (pos complete).
### Sales draft
Source: [Sales review](26afff7e-b1ce-4ea9-9240-fa9354d65019)
# Sales release-blocking review (provisional)
Cross-check: every `scope=` in `backend/sales/` (`sales_invoice_create|complete`, `sales_return_create|complete`, `sales_credit_note_complete`, `sales_debit_note_complete`) is in `MONEY_IDEMPOTENCY_SCOPES`. Receipt/allocation scopes live under `payments/` and are also covered.
---
### SALES-001 — Concurrent sales returns can over-return stock
- **Module:** Sales / Returns  
- **Location:** `backend/sales/return_service.py` `ReturnService.complete_return` (~74–141)  
- **Type:** Concurrency / race  
- **Severity:** High  
- **What's wrong:** Completing a return `select_for_update`s only the **return** row, then reads remaining qty from completed returns without locking the **source invoice**. Two DRAFT returns for the same invoice can both pass the remaining-qty check and both restore stock + auto-CN.  
- **Trigger/repro:** Invoice sells 10. Two sessions each complete a return of 10 concurrently.  
- **Consequence:** Stock inflated beyond sold; AR over-credited via duplicate auto CNs; COGS reverse double-booked.  
- **Code evidence:** `sales_return = → select_for_update()` then `invoice = sales_return.sales_invoice` (no lock); `_consume_prior` / remaining check use unlocked reads. CN path correctly does `SalesInvoice.objects.select_for_update()`.  
- **Suggested fix:** `invoice = SalesInvoice.objects.select_for_update().get(pk=sales_return.sales_invoice_id)` before qty consumption; optionally unique constraint / advisory lock per invoice.  
- **Test to add:** Concurrent `complete_return` threads; assert only one succeeds and stock/CN totals — sold.  
- **Twin check:** **Y** — `PurchaseService.complete_return` also binds `invoice = purchase_return.purchase_invoice` without `select_for_update`.
---
### SALES-002 — Recurring schedule permanently skips locked periods
- **Module:** Sales / Recurring  
- **Location:** `backend/sales/recurring.py` `_process_one_schedule` (~208–211)  
- **Type:** Functional / catch-up  
- **Severity:** High  
- **What's wrong:** If the due period is GST/accounting locked, code **advances `next_run_at`** and returns skip — it never retries that period when the lock clears. `generate_draft_for_schedule` alone returns `None` without advancing; the batch path advances anyway.  
- **Trigger/repro:** Soft-close current month; let beat run; reopen period; wait for next due — missed month never generates.  
- **Consequence:** Silent missed billing for paying tenants; ops must manually recreate.  
- **Code evidence:** `if period_is_locked(...): schedule.next_run_at = advance_next_run(...); return 0, 1, 0`. Test `test_recurring_creates_draft_skips_locked_and_duplicate` only asserts skip, not re-try after unlock.  
- **Suggested fix:** Do not advance on lock (or park `skipped_periods`); retry locked keys until draft created or schedule cancelled.  
- **Test to add:** Lock — process — unlock — process again — draft for original `period_key`.  
- **Twin check:** **N** (sales-only feature).
---
### SALES-003 — Invoice list `balance` ignores credit/debit notes
- **Module:** Sales / API  
- **Location:** `backend/sales/serializers.py` `get_balance` (~146–159); `views.py` list annotates only `_allocated` (~119–132)  
- **Type:** Correctness / AR display  
- **Severity:** High  
- **What's wrong:** On **list**, balance = `grand_total — allocations` only. Retrieve uses `LedgerService.sales_invoice_outstanding` (CN/DN-aware). After a return/auto-CN, list still shows near-full balance.  
- **Trigger/repro:** Complete invoice — complete sales return — open invoices list vs detail.  
- **Consequence:** Collections/dunning UI overstates AR; operators chase paid/returned invoices.  
- **Code evidence:** List shortcut skips CN/DN; detail path is correct.  
- **Suggested fix:** Annotate net CN/DN on queryset, or always use bulk outstanding helper (`LedgerService.bulk_sales_invoice_outstanding`).  
- **Test to add:** List serializer balance after completed return equals detail outstanding.  
- **Twin check:** **Y** — `purchases/serializers.py` `get_balance` same list shortcut.
---
### SALES-004 — Credit note (and auto-return CN) allowed on fully allocated invoices
- **Module:** Sales / Notes + Returns  
- **Location:** `backend/sales/notes_services.py` `complete_credit_note` / `_sales_note_headroom` (~80–97, 162–166); contrast `SalesService.cancel` blocks allocations (~1073–1080)  
- **Type:** Money / AR hygiene  
- **Severity:** Medium  
- **What's wrong:** Headroom is **invoiced — CNs + DNs**, not open outstanding. A fully paid invoice can still take a full CN. Outstanding floors at 0 while allocations remain, leaving sticky over-allocation / customer credit ambiguity.  
- **Trigger/repro:** Allocate receipt = grand total — complete price/qty CN or sales return.  
- **Consequence:** Books show 0 outstanding with full allocations; refunds/unallocate become manual cleanup; GSTR/CN correct but AR messy for first paying users.  
- **Code evidence:** Explicit comment → not AR outstanding; cancel path already requires clearing allocations.  
- **Suggested fix:** Block CN/return complete when `allocated > post-CN outstanding`, or auto-unallocate / force confirm.  
- **Test to add:** Paid invoice + CN — 400 or automatic unallocate to headroom.  
- **Twin check:** **Partial Y** — purchase CN also caps to headroom/outstanding differently; purchase cancel/alloc rules differ — treat as shared AR design debt.
---
### SALES-005 — Debit notes have no per-line quantity cap vs source invoice lines
- **Module:** Sales / Debit notes  
- **Location:** `backend/sales/notes_services.py` `complete_debit_note` (~312–359) vs CN qty loop (~168–190)  
- **Type:** Abuse / GST reporting  
- **Severity:** Medium  
- **What's wrong:** CN enforces `qty + prior — source_item.quantity`. DN only money-gates (`confirm_additional_debit` / invoice value). Operator can post DN qty — sold while keeping grand_total under caps (or with confirm).  
- **Trigger/repro:** Invoice line qty 1 — DN with qty 100 and tiny unit price, or additional-debit confirm with inflated qty.  
- **Consequence:** Distorted GSTR note quantities / HSN tables; weak audit of → what was adjusted.  
- **Code evidence:** No DN analogue of CN's `source_item` qty aggregate.  
- **Suggested fix:** Same per-`source_item` remaining qty rule as CN (additional debit may allow value — but not phantom qty without explicit reason).  
- **Test to add:** DN qty > source remaining — 400.  
- **Twin check:** **Y** — purchase notes also lack sales-style CN line qty checks on DN (purchase CN itself also lacks line qty).
---
### SALES-006 — Delivery challan complete does not gate closed periods
- **Module:** Sales / Delivery challan  
- **Location:** `backend/sales/notes_services.py` `complete_challan` (~688–774)  
- **Type:** Period lock / inventory  
- **Severity:** Medium  
- **What's wrong:** When `stock_on_delivery_challan` is on, SALE movements post with no `assert_period_allows_money_amend`. Invoice/return/CN all gate.  
- **Trigger/repro:** Soft-close period — complete stock-posting challan dated in that period.  
- **Consequence:** Inventory (and later COGS on convert) moves in a locked books/GST period.  
- **Code evidence:** Number — release SO — stock loop — status flip; no period assert.  
- **Suggested fix:** Gate on `challan_date` before stock/number (same as invoice complete).  
- **Test to add:** Soft-closed period — challan complete — 400.  
- **Twin check:** **N/partial** — purchase receipt stock path should be twin-checked by Purchase agent; not mirrored as "challan".
---
### SALES-007 — Confirmed SO — invoice drops reservation before invoice completion
- **Module:** Sales / Orders  
- **Location:** `backend/sales/notes_services.py` `convert_sales_order` (~504–555)  
- **Type:** Inventory race  
- **Severity:** Medium  
- **What's wrong:** Converting CONFIRMED SO releases reservations immediately, creates **DRAFT** invoice. Stock is unprotected until `SalesService.complete`. SO→challan correctly keeps reservation until challan complete.  
- **Trigger/repro:** Confirm SO (reserve) — convert to invoice — another sale exhausts stock — complete invoice fails or dips negative per policy.  
- **Consequence:** Broken promise of reservation; intermittent complete failures under load.  
- **Code evidence:** `release_reservation` then `SalesInvoice.objects.create` + `set_items`; status `CONVERTED`.  
- **Suggested fix:** Keep reservation until invoice complete/cancel, or convert only as part of complete, or soft-allocate to draft invoice.  
- **Test to add:** After convert-to-invoice, available qty still reflects reservation until complete/cancel.  
- **Twin check:** **Check** PO→GRN/bill reservation behaviour (likely similar gap).
---
### SALES-008 — Quotation totals ignore header discount / charges / round-off
- **Module:** Sales / Quotations  
- **Location:** `backend/sales/services.py` `set_quotation_items` (~1234–1254)  
- **Type:** Totals / UX  
- **Severity:** Medium  
- **What's wrong:** Quotation model has `invoice_discount`, `additional_charges`, modes, `auto_round_off`, but `compute_document_totals` is called **without** those args (defaults — no header discount/charges). Convert copies fields onto invoice where they apply.  
- **Trigger/repro:** Quotation with → 100 AFTER_TAX discount — PDF/API totals unchanged; convert — invoice shows discount.  
- **Consequence:** Salespeople quote wrong totals; customer trust issue at first paying users.  
- **Code evidence:** Contrast `set_order_items` / `set_items` which pass discount/charges.  
- **Suggested fix:** Pass the same kwargs as SO/invoice into `compute_document_totals`.  
- **Test to add:** set_quotation_items with header discount — `grand_total` matches invoice after convert.  
- **Twin check:** **N** (unless purchase quotes exist).
---
### SALES-009 — Document chain is all-or-nothing (no partial convert)
- **Module:** Sales / SO / DC / Quotation  
- **Location:** `convert_sales_order`, `convert_sales_order_to_challan`, `convert_delivery_challan`, `convert_quotation*`  
- **Type:** Product gap / workflow  
- **Severity:** Medium (release risk if customers expect partial dispatch)  
- **What's wrong:** One live DC blocks SO→invoice; conversions copy **all** lines; no partial qty convert. Double-convert guarded (`CONVERTED` / `converted_invoice_id`). Edit-after-convert: source docs locked; **draft** invoice/challan still editable (challan lot identity enforced at invoice complete — good).  
- **Trigger/repro:** SO 100 units, customer wants 40 now.  
- **Consequence:** Workarounds (split SOs) or over-shipping drafts.  
- **Code evidence:** Full line list copies; `live_challan` / `converted_invoice_id` guards.  
- **Suggested fix:** Track converted qty per line (or allow partial DC lines) before GA if SMB dispatch needs it; else document as known limitation.  
- **Test to add:** (If implementing) partial DC then invoice remaining.  
- **Twin check:** **Y** pattern — PO/GRN partials should be compared by Purchase agent.
---
### SALES-010 — `complete_invoice` atomic boundary: late period gate; PDF outside
- **Module:** Sales / Invoice complete  
- **Location:** `backend/sales/services.py` `SalesService.complete` (~690–1050); `handlers.py` on_commit PDF  
- **Type:** Architecture / ordering  
- **Severity:** Low–Medium (correctness OK under atomic; ops/lock duration)  
- **What's wrong / what's OUTSIDE:**  
  - **Inside** `@transaction.atomic` + invoice `select_for_update`: validations — GSTIN recompute — credit limit — number — **status COMPLETED save** — stock/COGS — **then** period gate — GL — `emit`.  
  - **Outside (after commit):** PDF via `transaction.on_commit` (handlers swallow errors; `emit` never aborts txn).  
  - Number allocation is savepoint-safe (`DocumentNumberService` requires caller atomic). Rollback undoes status/stock/number.  
- **Trigger/repro:** Complete into soft-closed period — whole txn rolls back (OK) after doing stock work under lock.  
- **Consequence:** Longer row locks; harder reasoning; not a dual-write bug.  
- **Suggested fix:** Move `assert_period_allows_money_amend` before number/status/stock (CN/DN already do).  
- **Test to add:** Closed period complete — no SALE movement, series unchanged.  
- **Twin check:** **Y** — purchase complete also flips status then gates/stock in a similar shape.
---
### SALES-011 — Service still allows completed qty amend; API H9 forbids it
- **Module:** Sales / Amend  
- **Location:** `services.py` `set_items` (~543–645); `h9_amend.py` blocks qty (~76–78); serializer early-return if not `needs_amend`  
- **Type:** Invariant drift / footgun  
- **Severity:** Low–Medium  
- **What's wrong:** H9-A API path rejects qty changes. `SalesService.set_items` still implements stock SALE/ADJUSTMENT for completed qty deltas (non-batch/serial). Internal callers could desync FIFO/serials.  
- **Trigger/repro:** Call `SalesService.set_items` directly with qty change on completed invoice.  
- **Consequence:** Bypass of H9; inventory layers diverge from → CN/return only policy.  
- **Suggested fix:** Raise in `set_items` if completed and qty differs (align with H9); delete dead stock-delta branch or gate behind explicit admin tool.  
- **Test to add:** Direct service qty amend on completed — 400.  
- **Twin check:** **Y** — purchase `set_items` still has completed qty stock deltas with H9 on serializer.
---
### SALES-012 — IRN guard: cancel/amend mostly solid; FAILED+IRN asymmetry
- **Module:** Sales / e-Invoice  
- **Location:** `irn_guard.py`; `serializers.py` amend (~300–318); `SalesService.cancel` (~1081–1084); `einvoice_eway_actions.cancel_einvoice`  
- **Type:** Statutory sync  
- **Severity:** Low  
- **What's wrong:** Live IRN blocks books cancel and money amend — good. `LIVE_IRN` constant unused. Amend treats `irn && status — {CANCELLED,NONE}` as live (includes **FAILED**); cancel guard allows FAILED. Manual/GSP cancel clears IRN before books cancel.  
- **Trigger/repro:** FAILED submit leaving `irn` populated — cannot amend; can cancel books.  
- **Consequence:** Confusing ops path; low portal desync risk if IRN never truly live.  
- **Suggested fix:** Unify amend/cancel predicates; use `LIVE_IRN` / treat FAILED as non-live if portal never ack'd.  
- **Test to add:** FAILED+irn amend and cancel matrix.  
- **Twin check:** **N** (sales e-invoice primary).
---
### SALES-013 — CN `unit_price` override recalculates tax off source rate
- **Module:** Sales / Credit notes  
- **Location:** `services.py` `_build_items` (~216–226); `complete_credit_note` qty+headroom  
- **Type:** GST / commercial  
- **Severity:** Low–Medium  
- **What's wrong:** GST/cess **rates** freeze from `source_item`, but CN/DN may override `unit_price`, so tax amounts need not be proportional to the original invoice line. Qty and grand_total headroom still bind.  
- **Trigger/repro:** Source → 1000@18% — CN qty 1 @ → 100 unit_price.  
- **Consequence:** Valid for pure value CN; risky if UI implies → return same line economics.  
- **Suggested fix:** Default unit_price from source; require confirm/reason to override; or scale taxable from source.  
- **Test to add:** Override price CN — audit flag / confirm required.  
- **Twin check:** **Check** purchase note builders for same override.
---
### SALES-014 — Recurring catch-up is one period per beat tick
- **Module:** Sales / Recurring  
- **Location:** `process_due_schedules` / `_process_one_schedule`  
- **Type:** Catch-up / timezone  
- **Severity:** Low  
- **What's wrong:** Overdue schedules advance **one** period per invocation. Timezone handling via `timezone.localtime` is fine. Dedupe via `RecurringInvoiceRun.period_key` is solid. Draft-only (never auto-complete) is correct.  
- **Trigger/repro:** `next_run_at` three months behind; one cron run — one draft.  
- **Consequence:** Slow catch-up after outage (acceptable if documented); combined with SALES-002, locked months are worse.  
- **Suggested fix:** Loop while `next_run_at <= now` (cap N) per schedule.  
- **Test to add:** Three months overdue — one `process_due` creates three drafts (or N with cap).  
- **Twin check:** **N**.
---
### SALES-015 — `_validate_lines` vs `bulk_create` / `full_clean`
- **Module:** Sales / Lines  
- **Location:** `services.py` `_validate_lines` (~38–76); all `bulk_create` call sites  
- **Type:** Validation gap (mitigated)  
- **Severity:** Low  
- **What's wrong:** Model `MinValueValidator` / etc. skip on `bulk_create`. Service whitelist covers qty ≤ 0.001, GST slab, discount 0–100, company on product/batch, active product. Residual: other model constraints (e.g. string lengths, cess bounds) may not run.  
- **Trigger/repro:** Extreme cess_amount / malformed supply_nature via API if serializer allows.  
- **Consequence:** Mostly blocked by serializers; defense-in-depth incomplete.  
- **Suggested fix:** Optional `full_clean` on built instances before bulk_create for money docs.  
- **Test to add:** Out-of-range cess via service — 400.  
- **Twin check:** **Y** — purchase `_validate_lines` + bulk_create pattern.
---
### SALES-016 — Receipt allocation concurrency / cancelled target (payments-owned, sales-adjacent)
- **Module:** Payments — Sales  
- **Location:** `payments/services.py` `allocate_receipt` (~391–441)  
- **Type:** Concurrency (positive + residual)  
- **Severity:** Low (residual)  
- **What's wrong:** Over-allocate races mitigated by `select_for_update` on receipt **and** invoice; cancelled invoices rejected; `RETURNED` allowed (outstanding via CN). Unallocated advances intentionally allowed (`test_unallocated_advance_allows_complete_under_limit`).  
- **Trigger/repro:** Parallel allocate same receipt (covered by `test_concurrency_races`).  
- **Consequence:** Residual: allocate to RETURNED with leftover outstanding OK; see SALES-004 for CN-after-pay.  
- **Suggested fix:** None urgent beyond SALES-004.  
- **Test to add:** Allocate to CANCELLED — 400 (if not already).  
- **Twin check:** **Y** — `allocate_supplier_payment` mirrors locking.
---
## Sales coverage notes
**Highest release blockers:** SALES-001, SALES-002, SALES-003.
### Purchase draft
Source: [Purchase review](4bdc1753-ee5d-4e18-b717-0a7f0a777fa7)
# Purchase module — provisional release review
Verdict: **Purchase invoice Complete is largely sales-parity atomic (stock + AP in one `@transaction.atomic`)**, but **CN/DN complete, landed-cost vs GL, cancel guards, and subscription gating** are release-risk before first paying users.
---
### PUR-001
---
### PUR-002
---
### PUR-003
---
### PUR-004
---
### PUR-005
---
### PUR-006
---
### PUR-007
---
### PUR-008
---
### PUR-009
---
### PUR-010
---
### PUR-011
---
### PUR-012
---
### PUR-013
---
### PUR-014
---
### PUR-015
---
### PUR-016
---
### PUR-017
---
### PUR-018
---
### PUR-019
---
### PUR-020
---
## Purchase coverage notes
**Traced Complete path:** `PurchaseInvoiceViewSet.complete` — `wrap_idempotent(purchase_invoice_complete)` — `PurchaseService.complete` — stock PURCHASE movements (+ serial/batch) — `PostingService.post_purchase` — events. No separate GRN. Company scoping on invoice FKs via validators + `CompanyPrimaryKeyRelatedField` for BoE/products.
**Traced Return path:** `PurchaseReturnViewSet.complete` — `purchase_return_complete` — `complete_return` — qty headroom — PURCHASE_RETURN / damaged ADJUSTMENT + layer retire — auto `PurchaseCreditNote` — `complete_credit_note` (AP). Cancel restores stock and cancels linked CN.
**Idempotency vs `MONEY_IDEMPOTENCY_SCOPES`:** Covered: `purchase_invoice_create/complete`, `purchase_return_create/complete`, `bill_of_entry_create/complete`, `import_job_commit`, `supplier_payment_create`, `allocation_create`. **Gaps:** purchase CN/DN complete (PUR-001/002).
**Bill / BoE import:** validate→preview→commit present; bill commit — draft + RCM inference; ITC: invoice `assert_claimable_itc_allowed` (2B MATCHED); BoE `_assert_boe_import_itc_reconciled` (ICEGATE / 2B). Re-commit blocked; no partial bill lines.
**Supplier payment:** Party match + locks + outstanding caps look sound (PUR-018 residual serializer hardening).
**Highest release blockers:** PUR-001, PUR-002, PUR-003, PUR-004, PUR-005, PUR-007, PUR-008.
### Stock/Godown draft
Source: [Stock/Godown review](95fa028c-ac85-4fdc-8194-5eb1f2fed9b2)
# Stock & Godown — provisional release review
Verdict: core ledger design is strong (typed append-only movements, `select_for_update` balance lock before negative check, sales/purchase complete through `InventoryService`). Several paths are still release-blocking for first paying users — especially manual serial return, WARN-policy consistency, and closed-period gaps on counts/transfers.
---
### STK-001 — Manual serial SOLD→RETURNED crashes (missing `StockMovement.serial_numbers`)
---
### STK-002 — Manual serial return design wrong even if STK-001 fixed (status + FIFO)
---
### STK-003 — Negative-stock policy inconsistent across invoice / batch / transfer / adjust / reserve
---
### STK-004 — WARN oversell: `InventoryRunningCost` floors at 0 while `StockBalance` goes negative
---
### STK-005 — Stock count (and transfer) skip closed-period gate that adjustments use
---
### STK-006 — Append-only hole: import void mutates `StockMovement.reference_type`
---
### STK-007 — Balance vs `sum(movements)`: rebuild exists, no runtime reconciliation
---
### STK-008 — Transfers: two-sided atomic OK; no in-transit; DRAFT does not reserve
---
### STK-009 — Stock-count conflict merge preserves movement history (by design)
---
### STK-010 — Serial scrap AVAILABLE always posts → 1 even if available is 0
---
### STK-011 — Default warehouse: unique constraint + IntegrityError fallbacks are mostly sound
---
### STK-012 — Document golden paths (sales/purchase — InventoryService) look correct
---
### STK-013 — Double-sale serial / expiry / FEFO (document path)
---
### STK-014 — FIFO consume/replenish on document path; verification not automated
---
## Stock coverage notes
**Highest priority before first paying users:** STK-001, STK-002, STK-003, STK-004, STK-005.
### Accounting draft
Source: [Accounting review](c81718f0-4622-42b5-8c5d-9a3c561defc2)
# Accounting release review (provisional)
Read-only review of `backend/accounting/`, `backend/ledgers/`, document/GL callers, and feature gating. **No fixes applied.**
---
## ACC-001 — Journal lines created outside entry savepoint
---
## ACC-002 — `PostingService.reverse` not atomic with status flip
---
## ACC-003 — `PostingService.post` ignores GST period locks
---
## ACC-004 — Period close vs concurrent post (TOCTOU)
---
## ACC-005 — Dual ledger can diverge; health check does not compare documents vs GL
---
## ACC-006 — Purchase credit/debit notes do not reverse TDS payable (2265)
---
## ACC-007 — TDS amount-vs-rate override is silent (unlike TCS 206C)
---
## ACC-008 — Cess GL present; purchase tax drift weaker than sales
---
## ACC-009 — Manual vouchers: balance OK; `books_start_date` bypassed
---
## ACC-010 — `backfill_missing_postings` / `backfill_accounting_postings` safety gaps
---
## ACC-011 — Balance check does not quantize lines to 2 dp before commit
---
## ACC-012 — Feature-flag gating: UI dual-key; API is `accounting_enabled` only
---
## Accounting coverage notes
**Positive controls worth keeping:** source idempotency unique constraint; sales tax header/line guard; TCS override audit; payment TDS double-credit guard; books health missing-posting / advance mismatch alerts; FE+BE alignment on `accounting_enabled` once flags load.
### Reporting draft (provisional RPT-*; awaiting CR merge)
Source: [Reporting review](9534fea3-69d0-4357-b9a6-0c71eef146b2)
### RPT-001 — Dashboard AR KPI vs AR aging use different ledgers when books are on
- **Module:** Reporting — Dashboard KPIs / AR aging
- **Location:** `backend/ledgers/services.py` (~269–393, 447–453) `bulk_customer_outstanding`; `backend/reporting/services.py` (101–167) `receivables_aging`
- **Type:** Data-integrity | Bug
- **Severity:** Critical
- **What's wrong:** When `accounting_enabled` and outstanding basis is not `DOCUMENTS_ALWAYS`, company receivables switch to GL 1200/2300 while aging always uses document invoice — CN + DN — allocation. Dashboard returns both.
- **Trigger / repro:** Enable accounting (default GL_WHEN_BOOKS), post sales + receipt with GL/doc drift or advances on 2300; compare `/api/v1/dashboard/` `receivables` vs sum of `receivables_aging`.
- **Consequence:** Paying tenants see Receivables — sum(aging buckets); cards and aging chart disagree.
- **Code evidence:** `LedgerService.company_receivables` — GL path; `ReportService.receivables_aging` always document-based.
- **Suggested fix direction:** One definition — age GL party balances or drive KPI from the same document bulk used for aging; assert `sum(aging) == receivables` for both bases.
- **Test to add:** With books on, assert dashboard receivables equals sum of aging buckets (and equals document bulk when basis=DOCUMENTS_ALWAYS).
- **Twin check:** n/a (AP aging vs payables KPI — check same pattern)
### RPT-002 — AR aging allocation filter — party AR document formula
- **Module:** Reporting — AR aging
- **Location:** `backend/reporting/services.py:133-138`; `backend/ledgers/services.py:889-892` vs `421-427`
- **Type:** Data-integrity | Sales/Purchase-inconsistency (internal formula drift)
- **Severity:** High
- **What's wrong:** Aging / `bulk_sales_invoice_outstanding` filters allocations only by `sales_invoice_id` + `reversed_at__isnull`. Party bulk AR also requires `receipt__isnull=False` and `supplier_payment__isnull=True` (R2-020).
- **Trigger / repro:** Allocation on a sales invoice with `supplier_payment` set (or no receipt); compare aging vs customer outstanding.
- **Consequence:** Mis-typed/cross-linked allocations change aging vs party outstanding on document basis.
- **Code evidence:** Filter mismatch between aging and R2-020 party filters.
- **Suggested fix direction:** Align aging and `bulk_sales_invoice_outstanding` with R2-020 filters.
- **Test to add:** Allocation with supplier_payment set must not reduce sales AR aging.
- **Twin check:** Purchase/AP aging twin filters
### RPT-003 — Inventory summary qty from StockBalance cache, not sum(StockMovement)
- **Module:** Reporting — Stock summary
- **Location:** `backend/reporting/services.py:454-490` `inventory_summary`; `backend/inventory/models.py` (StockBalance cache docstring)
- **Type:** Data-integrity
- **Severity:** Critical
- **What's wrong:** Inventory summary reads `StockBalance` for on_hand/reserved/available. Valuation may use movements/running cost — qty and value can come from different stores. Violates → stock summary = sum(movements) checklist.
- **Trigger / repro:** Corrupt or skip balance update, leave movements correct; open inventory report / CSV export.
- **Consequence:** Drifted balances under/overstate stock report; BS inventory_valuation may not match summary.
- **Code evidence:** Iterates StockBalance; valuation path separate.
- **Suggested fix direction:** Derive on-hand from movements (or assert balance==movement sum before report); fail closed on drift.
- **Test to add:** Force balance vs sum(movements); summary must not silently trust balance (or recon report flags drift).
- **Twin check:** n/a (Stock module owns write path)
### RPT-004 — Sales/purchase registers include CANCELLED documents by default
- **Module:** Reporting — Registers / exports
- **Location:** `backend/reporting/services.py:266-267, 365-367`
- **Type:** Bug
- **Severity:** Critical
- **What's wrong:** Registers `.exclude(status=DRAFT)` only — cancelled remain in rows and totals. GST builders correctly use COMPLETED/RETURNED only.
- **Trigger / repro:** Complete then cancel an invoice; GET sales-register / export without status= — cancelled row still in totals.
- **Consequence:** Register totals/exports overstate turnover vs GSTR / ops truth.
- **Code evidence:** exclude DRAFT only; cancelled included.
- **Suggested fix direction:** Default to COMPLETED/RETURNED (or exclude CANCELLED); keep optional status filter.
- **Test to add:** Cancelled invoice excluded from default register totals.
- **Twin check:** y — both sales and purchase registers
### RPT-005 — Dashboard MTD purchases not net of purchase CNs/DNs
- **Module:** Reporting — Dashboard KPIs
- **Location:** `backend/reporting/services.py:207-230` vs sales path 183–206
- **Type:** Sales/Purchase-inconsistency | Bug
- **Severity:** High
- **What's wrong:** `purchases_this_month` sums COMPLETED PIs only; sales today/MTD nets CNs/DNs. Purchase register does net notes.
- **Trigger / repro:** Complete PI then completed purchase CN same month; dashboard purchases unchanged, register totals drop.
- **Consequence:** Purchase KPI disagrees with register/books after returns.
- **Code evidence:** Sales nets notes; purchases do not.
- **Suggested fix direction:** Mirror sales KPI: → CN +DN on completed notes in period.
- **Test to add:** MTD purchases after CN equals PI — CN.
- **Twin check:** y — sales already correct
### RPT-006 — Opening-balance exclusion inconsistent (notes vs is_opening_balance)
- **Module:** Reporting — Dashboard / GST / AR
- **Location:** `backend/reporting/services.py:179-209`; `backend/reporting/gst_returns.py:287,362`
- **Type:** Data-integrity | Missing-validation (predicate drift)
- **Severity:** High
- **What's wrong:** Dashboard excludes `notes="TALLY_OPENING"`; GSTR uses `is_opening_balance=False`; AR/aging have no opening filter.
- **Trigger / repro:** Opening SI/PI with `is_opening_balance=True`, notes — `TALLY_OPENING`; compare dashboard vs GSTR.
- **Consequence:** Openings inflate sales KPI and AR while GSTR excludes them (or reverse).
- **Code evidence:** Two predicates + AR unfiltered.
- **Suggested fix direction:** Single predicate (`is_opening_balance`) on all financial aggregates.
- **Test to add:** Opening flag alone excludes from dashboard and AR; notes string alone not required.
- **Twin check:** y — sales and purchase openings
### RPT-007 — product_sales / customer_sales ignore credit/debit notes
- **Module:** Reporting — Sales analytics
- **Location:** `backend/reporting/services.py:542-589`
- **Type:** Bug
- **Severity:** High
- **What's wrong:** Product/customer sales sum invoice lines/totals only; dashboard sales nets notes.
- **Trigger / repro:** Invoice + completed CN; product/customer report still shows full invoice.
- **Consequence:** Rankings overstate net sales after returns.
- **Code evidence:** NET_SALES invoices only; no note netting.
- **Suggested fix direction:** Net note lines / party note totals for same date window.
- **Test to add:** product_sales after CN reflects net qty/amount.
- **Twin check:** n/a (purchase analytics twin if any)
### RPT-008 — Warehouse filter on registers not applied to note rows
- **Module:** Reporting — Sales/purchase register
- **Location:** `backend/reporting/services.py:271-315, 372-409`
- **Type:** Bug
- **Severity:** Medium
- **What's wrong:** Invoice qs filtered by warehouse_id; CN/DN qs are not.
- **Trigger / repro:** Two warehouses; CN on WH-B while filtering WH-A.
- **Consequence:** Warehouse-scoped register mixes filtered invoices with company-wide notes.
- **Code evidence:** warehouse filter only on invoice queryset.
- **Suggested fix direction:** Filter notes via parent invoice warehouse (or exclude notes when warehouse set).
- **Test to add:** Warehouse filter excludes notes for other warehouses.
- **Twin check:** y — both registers
### RPT-009 — Inventory summary warehouse query param not int-normalized
- **Module:** Reporting — Inventory summary API
- **Location:** `backend/reporting/views.py:144`
- **Type:** Missing-validation | Bug
- **Severity:** Medium
- **What's wrong:** Raw `request.query_params.get("warehouse")` vs `_int_or_none` on sibling views.
- **Trigger / repro:** `?warehouse=abc` or `warehouse=` on inventory-summary.
- **Consequence:** Inconsistent filter miss or 500.
- **Code evidence:** No `_int_or_none`.
- **Suggested fix direction:** Use `_int_or_none` like sibling views.
- **Test to add:** Non-integer warehouse returns 400 or ignored consistently.
- **Twin check:** n/a
### RPT-010 — GSTR-3B net_payable_hint subtracts full 2B ITC, not recommended_claimable
- **Module:** Reporting — GSTR-3B
- **Location:** `backend/reporting/gst_returns.py:1587-1612, 1867-1877`
- **Type:** Bug | Data-integrity
- **Severity:** Critical
- **What's wrong:** `recommended_claimable = min(books, gstr2b_matched)` when 2B matched, but `tax_payable_summary.net_payable_hint` subtracts full `itc_2b` heads.
- **Trigger / repro:** Books ITC 100, matched 2B 150 — recommended 100 but net_payable subtracts 150.
- **Consequence:** CA/UI hint understates tax payable.
- **Code evidence:** Different ITC heads for recommended vs net payable.
- **Suggested fix direction:** Net payable must use same heads as `recommended_claimable`.
- **Test to add:** net_payable_hint uses min(books,2B) when 2B > books.
- **Twin check:** n/a
### RPT-011 — GSTR RCM line tax rebuilt in report path when line taxes are zero
- **Module:** Reporting — GSTR-1 rate buckets
- **Location:** `backend/reporting/gst_returns.py:247-269`
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** `_rate_buckets` recomputes `q2(taxable * rate/100)` when RCM and line taxes are zero — diverges from write-path stored taxes.
- **Trigger / repro:** Legacy RCM invoice with zero line tax fields, non-zero header RCM memos; compare section tax vs header totals.
- **Consequence:** Worksheet rate buckets diverge from invoice headers / GL by paise.
- **Code evidence:** Rebuild branch in `_rate_buckets`.
- **Suggested fix direction:** Prefer stored line/header tax; rebuild only behind explicit migration flag.
- **Test to add:** RCM zero-line-tax invoice buckets match header RCM memos, not recomputed rate.
- **Twin check:** n/a
### RPT-012 — HSN section buckets use gst_rate, rate tables use applied_rate
- **Module:** Reporting — GSTR-1 HSN vs B2
- **Location:** `backend/reporting/gst_returns_sections.py:13`; `backend/reporting/gst_returns.py:241`
- **Type:** Data-integrity | Bug
- **Severity:** High
- **What's wrong:** `accumulate_hsn_line` keys on `gst_rate`; `_rate_buckets` prefers `applied_rate`.
- **Trigger / repro:** Line with `applied_rate != gst_rate`; compare HSN rate key vs B2 rate.
- **Consequence:** HSN (and GSTR-9 table 17) disagree with B2B/B2CS rate rows.
- **Code evidence:** Different rate fields.
- **Suggested fix direction:** Same rate field as GSTR (`applied_rate` with gst_rate fallback).
- **Test to add:** applied_rate vs gst_rate — HSN and B2 same rate key.
- **Twin check:** n/a
### RPT-013 — Bill of Entry ITC period filter is Python-side full scan
- **Module:** Reporting — GSTR-3B / GSTR-9
- **Location:** `backend/reporting/gst_returns.py:1479-1484, 2031-2038`
- **Type:** Improvement | Bug (unbounded)
- **Severity:** High
- **What's wrong:** Loads all COMPLETED+ELIGIBLE BOEs then filters `resolved_itc_period() == period` in Python; GSTR-9 loops ×12 months.
- **Trigger / repro:** Many historical BOEs; generate GSTR-9 FY.
- **Consequence:** Unbounded memory/CPU on import-heavy tenants; easy to miss DB date bounds.
- **Code evidence:** Full queryset then Python period match.
- **Suggested fix direction:** Filter `itc_period` / `boe_date` in SQL to month/FY window.
- **Test to add:** BOE outside period not loaded (or assert queryset filtered).
- **Twin check:** n/a
### RPT-014 — GSTR-9 Table 8 note still describes obsolete import heuristic
- **Module:** Reporting — GSTR-9
- **Location:** `backend/reporting/gst_returns.py:2150-2153`
- **Type:** Silent-failure (honesty) | Broken-feature (docs vs code)
- **Severity:** Medium
- **What's wrong:** Import ITC now from BillOfEntry but table 8 note still says → IGST on purchases without supplier GSTIN.
- **Trigger / repro:** Read GSTR-9 table 8 notes in API response.
- **Consequence:** CA misreads worksheet basis.
- **Code evidence:** Stale note string vs BOE source at 2023–2038.
- **Suggested fix direction:** Align note with BOE source.
- **Test to add:** Snapshot/assert note text mentions BoE.
- **Twin check:** n/a
### RPT-015 — Exports and cash book materialize full payloads (no streaming)
- **Module:** Reporting — Export / memory
- **Location:** `backend/reporting/views.py:1254-1270, 189-238`
- **Type:** Improvement
- **Severity:** High
- **What's wrong:** ExportView builds full row list — StringIO CSV; cash book XLSX / GSTR XLSX / CA zip in-memory. Dated large ranges unbounded (5000 cap only when date_from missing).
- **Trigger / repro:** Export sales-register for multi-year date_from/date_to.
- **Consequence:** Memory spikes / timeouts for multi-year tenants.
- **Code evidence:** Full materialization; no max span on dated exports.
- **Suggested fix direction:** Require max span; stream CSV; paginate JSON registers.
- **Test to add:** Oversized range returns 400 with clear max-span error.
- **Twin check:** n/a
### RPT-016 — Cancelled-numbers register N+1 + loads all cancelled docs
- **Module:** Reporting — Statutory cancelled register
- **Location:** `backend/reporting/views.py:539-611`
- **Type:** Improvement
- **Severity:** Medium
- **What's wrong:** Per-doc `_reason(...)` query; FY filter in Python after fetching all cancelled.
- **Trigger / repro:** Large cancelled history; open cancelled-numbers register.
- **Consequence:** Slow/heavy; not date-SQL-bounded.
- **Code evidence:** Loop with per-doc reason query; FY filter post-fetch.
- **Suggested fix direction:** Prefetch cancel events; filter FY in DB.
- **Test to add:** Prefetch/assert query count bounded.
- **Twin check:** n/a
### RPT-017 — Cash book (receipts/payments) — GL cash-flow aid
- **Module:** Reporting — Cash reports
- **Location:** `backend/reporting/services.py:592-761`; `backend/accounting/reports.py:181-257`
- **Type:** Data-integrity (dual story)
- **Severity:** Medium
- **What's wrong:** Dashboard cash_position / cash book from posted receipts & supplier payments; accounting cash_flow from JournalLines on 1100/1500*.
- **Trigger / repro:** Books on with journals that don't match receipt docs 1:1.
- **Consequence:** Two cash stories for same company when books on.
- **Code evidence:** Different source tables.
- **Suggested fix direction:** Label clearly and/or reconcile; don't mix KPI sources without disclaimer.
- **Test to add:** With books on, document mismatch surfaces in health/recon or UI label.
- **Twin check:** Accounting module
### RPT-018 — Accounting cash_flow iterates every cash journal line in Python
- **Module:** Reporting / Accounting — cash_flow
- **Location:** `backend/accounting/reports.py:212-226`
- **Type:** Improvement
- **Severity:** Medium
- **What's wrong:** `for line in qs:` with select_related but no aggregation.
- **Trigger / repro:** High-volume cash journal history; open cash-flow report.
- **Consequence:** Slow cash-flow for high-volume tenants.
- **Code evidence:** Python loop over all lines.
- **Suggested fix direction:** `values(source_type).annotate(Sum(...))`.
- **Test to add:** Query count / timing smoke for large fixture.
- **Twin check:** n/a
#### Reporting coverage notes
- Aggregations generally company-scoped; registers/dashboard draft-out but cancelled-in (RPT-004).
- Stock summary qty uses StockBalance (RPT-003); GST worksheets solid with footing checks; issues RPT-010–014.
- Feature flags: backend `assert_gstr_enabled`; frontend `VITE_ENABLE_GSTR`. Live GSP gated. Offline 2B = paying path.
- Highest priority: RPT-001, RPT-003, RPT-004, RPT-010.
---
## Top 10 must-fix-before-launch
Ordered by **Severity × Core Business Flow Criticality**:
1. **CR-001 — POS Online Cash Retry Remints Idempotency Key (`POS-001`)**
   - **Module:** POS — Checkout / Cash Pay
   - **Severity:** Critical
   - **Why #1:** Retail POS is the highest-volume cash-register touchpoint. A network dropout between `complete` and `receipt` caused subsequent "Cash Pay" clicks to mint a brand-new idempotency key, creating a *second completed invoice* and double-decrementing stock. Cashier and customer are desynced, leaving physical inventory corrupted and an orphan unpaid invoice on the books.
   - **Remediation:** Enforce a single stable sale gesture key throughout the cart lifecycle, resuming receipt and allocation on retry rather than initiating a new sale.
2. **CR-078 — Journal Entry Lines Created Outside Header Savepoint (`ACC-001`)**
   - **Module:** Accounting — `PostingService.post()`
   - **Severity:** Critical
   - **Why #2:** Any unhandled failure or timeout between `JournalEntry.objects.create()` and `JournalLine.objects.bulk_create()` left a permanent, empty `POSTED` journal header in the database. Because `PostingService.post()` checks for existing postings by source and purpose, all subsequent retries returned the 0-line header, permanently silencing accounting entries for that document and corrupting the Balance Sheet and Trial Balance.
   - **Remediation:** Wrap the header creation and line batch insert in an isolated atomic transaction/savepoint so failure rolls back cleanly, and repair/purge incomplete entries on retry.
3. **CR-048 — Manual Serial Return SOLD→RETURNED Crashes on Missing Field (`STK-001`)**
   - **Module:** Inventory / Stock — Serialised Returns
   - **Severity:** Critical
   - **Why #3:** When a customer attempts to return a serialized item, `complete_return()` crashes with an unhandled 500 error due to `StockMovement` lacking serial number storage/linkage. Retailers selling electronics, appliances, or mobile devices cannot process any serial returns, completely blocking customer service operations.
   - **Remediation:** Support proper serial status transition (`SOLD` — `RETURNED` / `AVAILABLE`) and link serial records without referencing nonexistent movement fields.
4. **CR-063 — Sales and Purchase Registers Include CANCELLED Documents by Default (`RPT-004`)**
   - **Module:** Reporting — Statutory Registers & Exports
   - **Severity:** Critical
   - **Why #4:** Statutory registers query `.exclude(status=DRAFT)` instead of `.filter(status=COMPLETED)` or `.exclude(status__in=[DRAFT, CANCELLED])`. Cancelled invoices and bills remain included in registers and CSV downloads, falsely inflating turnover and tax figures presented to tax authorities or CAs.
   - **Remediation:** Default sales and purchase registers to `COMPLETED` and `RETURNED` documents only, allowing `CANCELLED` records to appear only when an explicit audit filter is selected.
5. **CR-060 — Dashboard AR KPI vs. AR Aging Ledger Discrepancy (`RPT-001`)**
   - **Module:** Reporting — Executive Dashboard & AR Aging
   - **Severity:** Critical
   - **Why #5:** With accounting enabled, the top-level Dashboard Receivables KPI pulls from GL accounts `1200`/`2300`, whereas the Receivables Aging table derives amounts from document balances (`invoice - CN + DN - allocation`). A business owner sees conflicting receivables totals on the exact same dashboard page, undermining confidence in the entire platform.
   - **Remediation:** Standardize on a single canonical definition across the dashboard cards and aging tables (or explicitly label basis).
6. **CR-014 & CR-036 — Concurrent Returns Over-Returning Stock (`SALES-001` & `PUR-007`)**
   - **Module:** Sales & Purchase — Returns Completion
   - **Severity:** High (Data-integrity race condition)
   - **Why #6:** Return completion locked the return document row rather than the source invoice. Two concurrent returns against the same invoice read unlocked aggregate quantities and both succeed, returning more quantity than was originally sold or purchased and corrupting physical inventory counts.
   - **Remediation:** Acquire a row-level lock (`select_for_update()`) on the *source invoice* before calculating returnable headroom.
7. **CR-069 — GSTR-3B Net Payable Hint Subtracts Ineligible 2B ITC (`RPT-010`)**
   - **Module:** Reporting — GST Worksheets
   - **Severity:** Critical (Compliance liability)
   - **Why #7:** The GSTR-3B estimation worksheet subtracted total gross ITC from GSTR-2B rather than `recommended_claimable` ITC, ignoring ineligible ITC (Section 17(5) blocked credits, supplier cancellations, and RCM items). A filer using this worksheet would underpay GST and face statutory recovery, 18% mandatory interest, and penalties.
   - **Remediation:** Subtract only `recommended_claimable` ITC when computing net tax payable hints.
8. **CR-030 & CR-031 — Purchase Note Idempotency Gap & Duplicate GL Posting (`PUR-001` & `PUR-002`)**
   - **Module:** Purchases — Credit & Debit Notes
   - **Severity:** High
   - **Why #8:** Purchase note completion actions were not wrapped with `wrap_idempotent`, and the viewset explicitly called `PostingService.post_note()` *after* the service method had already posted it. Any network retry created duplicate notes, and every single note posted double the credit/debit amount to the General Ledger.
   - **Remediation:** Register `purchase_credit_note_complete` and `purchase_debit_note_complete` in `MONEY_IDEMPOTENCY_SCOPES` with `wrap_idempotent`, and remove the redundant viewset posting call.
9. **CR-062 — Stock Summary Reads Stale StockBalance Cache (`RPT-003`)**
   - **Module:** Reporting — Stock Summary
   - **Severity:** Critical
   - **Why #9:** The inventory summary report queries `StockBalance` rows directly instead of summing `StockMovement` records. Any cache divergence, failed background update, or manual adjustment leaves the statutory stock summary out of sync with actual inventory ledger movements.
   - **Remediation:** Ensure summary quantities reconcile with `sum(StockMovement)` or detect and surface balance drift.
10. **CR-050 & CR-051 — Inconsistent Negative-Stock Policy and Zero-Floored Cost Layers (`STK-003` & `STK-004`)**
    - **Module:** Inventory — Valuation & Policy Enforcement
    - **Severity:** High
    - **Why #10:** Under the `WARN` negative-stock setting, standard invoice lines warned as intended, but batch selection, FEFO allocation, and stock transfers hard-blocked with an error. Meanwhile, `InventoryRunningCost` floored at → 0.00 while stock went negative, causing subsequent incoming purchase batches to distort unit cost layers and corrupt COGS calculations.
    - **Remediation:** Unify the `WARN` semantics across batch and transfer paths, and ensure running cost accounting accurately tracks negative inventory without zero-flooring layers.
---
## Cross-cutting themes
Analysis of recurring architectural fault patterns across 3+ findings:
### 1. Multi-Step Orchestration and Leaky Transaction Boundaries
- **Findings:** CR-001 (POS multi-HTTP sale sequence), CR-023 (`complete_invoice` late period validation after locks), CR-078 (JE header created outside savepoint before lines), CR-079 (`PostingService.reverse` not atomic with status change).
- **Pattern:** Critical business actions span multiple independent HTTP round-trips or lack an overarching `@transaction.atomic` boundary enclosing all downstream effects (inventory movements, document numbering, GL journals, and status changes). If any intermediate step fails or encounters network latency, earlier mutations remain committed, creating orphan documents and desynced ledgers.
### 2. Check-Then-Act Concurrency Flaws: Locking the Leaf Instead of the Root
- **Findings:** CR-014 (Sales return locks return row, not source invoice), CR-036 (Purchase return locks return row, not source bill), CR-081 (Accounting period close checks `PeriodLock` without locking candidate postings).
- **Pattern:** Concurrency defenses called `.select_for_update()` on the newly created record being edited (the draft return or the lock record) rather than the root authority that holds the finite balance or headroom (the original invoice or the posting sequence). Concurrent requests both read unlocked aggregate balances and both pass validation, allowing over-returns and over-allocations.
### 3. Conceptual Divergence: Document Engine vs. General Ledger
- **Findings:** CR-060 (Dashboard AR uses GL while Aging uses documents), CR-061 (AR aging allocation filter mismatch vs. party document formulas), CR-082 (Dual-ledger silent drift without document-to-GL comparison), CR-016 (Invoice list balance ignores credit/debit notes).
- **Pattern:** The system maintains two parallel truths: the PRD's "documents are the primary source of truth" (where party balances are derived on the fly from completed documents and payment allocations) and the accounting engine's double-entry GL (`1200` AR / `2100` AP controls). Features built by different contributors drifted in their choice of source, causing the same dashboard to display irreconcilable figures.
### 4. Overly Permissive Statutory Status Filtering
- **Findings:** CR-063 (Sales/purchase registers include `CANCELLED` documents), CR-064 (Dashboard purchases not net of notes), CR-066 (`product_sales` and `customer_sales` ignore notes), CR-034 (Purchase bill cancellation blocks completed returns but misses notes).
- **Pattern:** Analytical queries repeatedly used `.exclude(status=DRAFT)` under the faulty assumption that non-draft records are valid commercial transactions. In Indian statutory compliance, `CANCELLED` and `VOID` documents must remain in the audit trail but must be excluded from turnover, sales registers, and tax filings.
### 5. Idempotency Scope Omissions and Transient Client Keys
- **Findings:** CR-001 (POS checkout re-mints key on cash retry), CR-030 (Purchase CN/DN complete missing `wrap_idempotent`), CR-039 (Purchase note complete POSTs without `Idempotency-Key` header).
- **Pattern:** Idempotency is enforced via exact string matching in `core/idempotency.py:MONEY_IDEMPOTENCY_SCOPES`. When developers add new complete actions or endpoints without updating this static set, idempotency protection is silently bypassed. On the frontend, generating keys inside button click handlers instead of binding them to the transaction draft causes re-minting upon retry.
---
## Cross-reference pass
Cross-referencing the 89 functional review findings (`CR-001`–`CR-089`) against historical audit registers (`bugs/INDEX.md`, `docs/reviews/MASTER_ISSUE_REGISTER.md`, `FINDINGS_2026-09-05.md`, and `FIX_PLAN_2026-09-05.md`):
### 1. Confirms Still Broken (Prior Fixes Incomplete or Regressed)
* **BUG-222 / BUG-309 (Negative Stock Race Condition) — Confirmed Still Broken in Edge Cases via CR-050 & CR-051:**
  - *Prior status:* Marked resolved via row-level locks on `StockBalance` in `post_movement()`.
  - *Current read:* The `BLOCK` policy is indeed safe under concurrency (`test_concurrent_stock_oversell_blocked` passes). However, the `WARN` policy was broken: batch and FEFO allocations hard-blocked instead of warning, and `InventoryRunningCost` floored at 0 when stock went negative, causing valuation distortion when inventory was replenished.
* **BUG-506 (Line-Item Editability on Completed Invoices) — Confirmed Still Broken in Internal Service Layer via CR-024:**
  - *Prior status:* Marked resolved at API and UI layers.
  - *Current read:* The frontend forms and DRF views reject edits to completed invoices. However, `SalesService.set_items` internally retained dead logic permitting quantity adjustments on completed invoices without re-checking GST period locks or reversing stock movements.
* **R-012 (Purchase Credit & Debit Note Idempotency Gap) — Confirmed Still Broken on Main via CR-030 & CR-031:**
  - *Prior status:* Open in 5 Sep register (`FINDINGS_2026-09-05.md`).
  - *Current read:* Fully confirmed. `PurchaseCreditNoteViewSet` and `PurchaseDebitNoteViewSet` lacked `wrap_idempotent` and double-posted journals via redundant view calls.
* **R-016 (GSTR-3B ITC Netting Discrepancy) — Confirmed Still Broken on Main via CR-069:**
  - *Prior status:* Open in 5 Sep register (`FINDINGS_2026-09-05.md`).
  - *Current read:* Fully confirmed. GSTR-3B subtracted total gross 2B ITC rather than eligible ITC.
* **R-030 (Recurring Invoices Skip Locked Periods Permanently) — Confirmed Still Broken on Main via CR-015:**
  - *Prior status:* Open in 5 Sep register (`FINDINGS_2026-09-05.md`).
  - *Current read:* Fully confirmed. The recurring invoice generator skipped ticks for closed accounting periods without a backlog mechanism.
### 2. Duplicates / Shared Root Causes
* **CR-037 & R-012 / BB-000694:** `PurchaseInvoiceViewSet` and note viewsets overriding `get_permissions()` without `SubscriptionWritesAllowed` duplicate the SaaS permission audit findings in Wave 21.
* **CR-061 & R-020:** Discrepancy between aging allocation filters and party bulk outstanding formulas is the exact same defect tracked in R-020.
* **CR-014 & CR-036 / B2-010:** Concurrency races on sales and purchase return headroom calculation share the exact same root cause: failing to lock the parent invoice.
### 3. New Findings Discovered in This Review
* **CR-001 (POS Online Cash Key Re-minting):** New discovery. Previous reviews focused on offline outbox replay and UPI callbacks, missing the online flaky-network cash checkout partial failure scenario.
* **CR-078 (Journal Entry Header/Line Savepoint Atomicity):** New discovery. Previous accounting audits verified double-entry balancing rules (`debit == credit`) but did not simulate database failures between header creation and bulk line insertion.
* **CR-048 (Manual Serial Return 500 Crash):** New discovery. Serial tracking was tested on standard sales and purchases, but the manual return path referencing nonexistent `StockMovement` fields was completely untested.
* **CR-063 (Statutory Registers Including Cancelled Documents):** New discovery. Registers were verified for date range filtering and math accuracy, but the omission of status filtering for cancelled documents went undetected.
---
## Re-verification 2026-09-06 (post-remediation working tree)
Independent re-trace of money/stock/tax write paths after claimed A1–A14 fixes in the dirty working tree (HEAD still `5ba05c7`). Verdicts below update status only; original CR bodies remain above for audit trail.
### Re-verification scoreboard (CR-001 through CR-089)
### Per-module status (compact)
### What the remediation got right (spot-checked)
- POS durable gesture key + `cashPending` resume (`posStatus.ts` / `PosPage.tsx`); menu/route `canAccessPos`.
- Offline flush binds `customerId` via `updateDraft` before invoice create.
- Sales/Purchase returns lock **source invoice** with `company_id` before qty headroom.
- `PostingService.post` creates header+lines in one atomic; refuses empty POSTED.
- Inventory summary on_hand from `Sum(StockMovement)` + `balance_drift`; registers exclude CANCELLED by default; GSTR-3B `net_payable_hint` uses `recommended_claimable`.
- Manual serial SOLD→AVAILABLE posts compensating movement + FIFO restore (A6 tests).
- Purchase CN/DN `wrap_idempotent` + scopes in `MONEY_IDEMPOTENCY_SCOPES`; no double `post_note`.
---
## Findings (continued) — CR-090+ from re-verification

### CR-078 — Journal lines created outside entry savepoint (ACC-001)
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

### CR-079 — `PostingService.reverse` not atomic with status flip (ACC-002)
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

### CR-080 — `PostingService.post` ignores GST period locks (ACC-003)
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

### CR-081 — Period close vs concurrent post (TOCTOU race) (ACC-004)
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

### CR-082 — Dual ledger can diverge; health check does not compare documents↔GL (ACC-005)
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

### CR-083 — Purchase credit/debit notes do not reverse TDS payable (2265) (ACC-006)
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

### CR-084 — TDS amount-vs-rate override is silent (unlike TCS 206C) (ACC-007)
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

### CR-085 — Cess GL present; purchase tax drift weaker than sales (ACC-008)
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

### CR-086 — Manual vouchers: balance OK; `books_start_date` bypassed (ACC-009)
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

### CR-087 — `backfill_missing_postings` / `backfill_accounting_postings` safety gaps (ACC-010)
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

### CR-088 — Balance check does not quantize lines to 2 dp before commit (ACC-011)
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

### CR-089 — Feature-flag gating: UI dual-key vs API `accounting_enabled` (ACC-012)
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

### CR-090 — Cash tender preview omits inclusive `price_mode` — false `tenderTooLow`
- **Module:** POS — tender gate / preview
- **Location:** `web/src/pages/pos/PosPage.tsx` (~950–963 preview payload vs ~597–612 create); billing preview defaults EXCLUSIVE
- **Type:** Bug
- **Severity:** High
- **Status:** OPEN (regression in CR-007 fix)
- **What's wrong:** Online cash gate calls `previewSalesTotals` with exclusive-shaped lines (`unit_price` only) and no `price_mode` / `unit_price_inclusive`. Create path sends both. Preview re-taxes inclusive shelf prices — inflated `grandTotal` — cashier blocked or forced to over-tender while booked invoice is correct.
- **Trigger / repro:** Company `priceMode === 'INCLUSIVE'`; Cash with tender = on-screen total.
- **Consequence:** Cannot settle at correct cash amount; `changeDue` still uses client totals.
- **Suggested fix direction:** Mirror create payload (`priceMode`, `unitPriceInclusive`); drive change display from gate total.
- **Test to add:** `pos_inclusive_tender_gate_matches_create_grand_total`
- **Twin check:** n-a (POS-specific); Sales New Invoice preview should be twin-checked

### CR-091 — Online `cashPending` / gesture key not durable across reload
- **Module:** POS — cash settlement resume
- **Location:** `web/src/pages/pos/PosPage.tsx` (React state only; online path does not `enqueueDraft`)
- **Type:** Data-integrity
- **Severity:** Medium
- **Status:** OPEN (residual of CR-001)
- **What's wrong:** After complete succeeds and before receipt, full page reload loses gesture key + `cashPending`. Next Cash mints a new key family — second COMPLETED invoice possible while first stays unpaid.
- **Trigger / repro:** Complete OK; kill tab before receipt; reopen POS; Cash again.
- **Consequence:** Double stock/sale; unpaid orphan — same class as original CR-001 under reload.
- **Suggested fix direction:** Persist in-flight settlement to outbox/sessionStorage keyed by company+user.
- **Test to add:** `pos_reload_mid_settlement_resumes_same_invoice`
- **Twin check:** offline flush already durable — online should match

### CR-092 — Multi offline flush auto-prints thermal for last invoice only
- **Module:** POS — offline flush print
- **Location:** `web/src/pages/pos/PosPage.tsx` (~860–865)
- **Type:** Broken-feature | Silent-failure
- **Severity:** Low
- **Status:** OPEN (CR-006 residual)
- **What's wrong:** Batch flush sets thermal warn/reprint for last id only; earlier completed slips never auto-print.
- **Suggested fix direction:** Print or queue reprint per completed id.
- **Test to add:** Assert print attempted for each flushed invoice id
- **Twin check:** n-a

### CR-093 — Sales debit note complete does not lock source invoice
- **Module:** Sales — debit note complete
- **Location:** `backend/sales/notes_services.py` `complete_debit_note` (~342–413)
- **Type:** Race
- **Severity:** Medium
- **Status:** OPEN
- **What's wrong:** CN path `select_for_update`s source invoice; DN uses `inv = note.sales_invoice` unlocked while computing qty/value headroom. Concurrent DNs can both pass caps.
- **Trigger / repro:** Two concurrent DN completes on same invoice consuming remaining line qty.
- **Consequence:** Over-debit vs sold qty / value.
- **Suggested fix direction:** Same lock as CN: `SalesInvoice.objects.select_for_update().get(pk=..., company_id=...)`.
- **Test to add:** `test_concurrent_sales_dn_over_debit_blocked` (Postgres)
- **Twin check:** Purchase DN — verify twin lock

### CR-094 — Cross-tenant `DeliveryChallan.sales_order` FK (no company check)
- **Module:** Sales — delivery challan create/complete
- **Location:** `backend/sales/phase1_serializers.py` `DeliveryChallanSerializer` (~288–295 validates customer/warehouse only); `notes_services.py` `complete_challan` (~766–780) loads SO by pk without `company_id`
- **Type:** Cross-tenant
- **Severity:** Critical
- **Status:** OPEN
- **What's wrong:** `sales_order` is a plain FK / default PrimaryKeyRelatedField. No `validate_sales_order` / `check_company_ref`. Completing a challan that points at another tenant's SO can mark that SO `CONVERTED` and release **their** reservations under the caller's company context.
- **Trigger / repro:** Authenticated company A posts challan with `sales_order=<B's SO id>`; complete challan.
- **Consequence:** Cross-tenant write (status/reservation) — release-blocking tenancy hole.
- **Code evidence:** `validate_customer` / `validate_warehouse` exist; no `validate_sales_order`. Complete: `SalesOrder.objects.select_for_update().get(pk=challan.sales_order_id)` — no company filter.
- **Suggested fix direction:** `check_company_ref` on create/update; complete load with `company_id=challan.company_id`; reject mismatch.
- **Test to add:** `test_delivery_challan_rejects_cross_company_sales_order` + complete path
- **Twin check:** Purchase side document links (PO→bill) — spot-check same pattern

### CR-095 — `cancel_return` flips invoice status without locking invoice
- **Module:** Sales — sales return cancel
- **Location:** `backend/sales/return_service.py` (cancel path; complete locks invoice, cancel does not)
- **Type:** Race
- **Severity:** Medium
- **Status:** OPEN
- **What's wrong:** Cancel may set invoice back to COMPLETED after unlocked `other_open` check while concurrent return complete runs.
- **Suggested fix direction:** `select_for_update` source invoice on cancel; re-check open returns under lock.
- **Test to add:** Concurrent `cancel_return` + `complete_return`
- **Twin check:** Purchase return cancel

### CR-096 — FE never sends CN `confirm_paid_invoice` / `confirm_price_override`
- **Module:** Sales — credit note UI
- **Location:** `web/src/utils/completeWithConfirms.ts`; sales credit-note complete API wrappers; backend `notes_services.py` confirm gates
- **Type:** Broken-feature
- **Severity:** Medium
- **Status:** OPEN (makes CR-017 / CR-026 incomplete for operators)
- **What's wrong:** Backend requires confirm flags on paid / price-override CN; auto-return silent-passes `True`; SPA never wires flags — operators hard-blocked at 409 with no confirm UI.
- **Suggested fix direction:** Extend `completeWithConfirms` + note editor dialogs; stop silent-confirm on auto-return or surface in return UI.
- **Test to add:** Vitest confirm flow + API integration for paid invoice CN
- **Twin check:** Purchase CN confirms

### CR-097 — Purchase cancel blocks draft returns/completed notes but not draft CN/DN
- **Module:** Purchase — bill cancel
- **Location:** `backend/purchases/services.py` cancel guards (CR-034/035)
- **Type:** Missing-validation | Data-integrity
- **Severity:** Medium
- **Status:** OPEN
- **What's wrong:** Cancelled bill can leave orphan draft credit/debit notes still editable/completable against a cancelled source (or blocked late with confusing errors).
- **Suggested fix direction:** Block cancel if any non-cancelled notes exist (draft or completed), or auto-cancel drafts in same atomic.
- **Test to add:** `test_purchase_cancel_blocked_when_draft_credit_note_exists`
- **Twin check:** Sales cancel vs draft CN/DN

### CR-098 — BoE cancel allowed while draft PIs still link BoE
- **Module:** Purchase — Bill of Entry cancel
- **Location:** `backend/purchases/boe_services.py` cancel (completed-PI guard only)
- **Type:** Missing-validation
- **Severity:** Low
- **Status:** OPEN
- **What's wrong:** Only COMPLETED linked PIs block cancel; draft PIs retain `bill_of_entry` pointing at cancelled BoE — confusing Complete failures later.
- **Suggested fix direction:** Block if any non-cancelled PI links BoE, or null out draft FKs in same transaction.
- **Test to add:** Draft PI + BoE cancel behaviour asserted
- **Twin check:** n-a

### CR-099 — Manual serial return peels first SALE move for product, not serial-specific
- **Module:** Stock — manual serial return
- **Location:** inventory serial transition / `_sale_movement_for_serial` helper
- **Type:** Data-integrity
- **Severity:** Medium
- **Status:** OPEN (residual of CR-048/049 fix)
- **What's wrong:** Helper takes first SALE movement for the product, not the movement that consumed that serial. Multi-line / multi-qty same SKU can restore wrong FIFO peels / unit cost.
- **Suggested fix direction:** Resolve SALE movement via serial/movement link or invoice line serial list.
- **Test to add:** Two SALE moves same SKU different costs; return specific serial restores matching peel
- **Twin check:** n-a

### CR-100 — AP invoice outstanding allocation filter — party AP (CR-061 twin)
- **Module:** Reporting / Ledgers — payables aging
- **Location:** `backend/ledgers/services.py` `purchase_invoice_outstanding` (~203); `bulk_purchase_invoice_outstanding` (~848–850) — missing `supplier_payment__isnull=False, receipt__isnull=True`
- **Type:** Data-integrity | Sales/Purchase-inconsistency
- **Severity:** High
- **Status:** OPEN
- **What's wrong:** Sales side fixed CR-061 with receipt-only allocation filters. Purchase per-invoice outstanding still sums **all** allocations on the PI. Cross-linked / mis-typed allocations skew payables aging vs `supplier_outstanding`.
- **Trigger / repro:** Allocation row with unexpected receipt/supplier_payment shape on a PI; compare aging vs party AP.
- **Consequence:** Wrong AP aging / dashboard footing when books use document AP.
- **Suggested fix direction:** Mirror sales filters on purchase invoice outstanding paths.
- **Test to add:** `test_cr100_purchase_invoice_outstanding_ignores_receipt_allocations`
- **Twin check:** y — this **is** the Purchase twin of CR-061

### CR-101 — Dashboard payables still GL while AR is document aging (CR-060 twin)
- **Module:** Reporting — dashboard KPIs
- **Location:** `backend/reporting/services.py` `_company_receivables` (document aging) vs `_company_payables` — `LedgerService.company_payables` (GL when books on)
- **Type:** Data-integrity | Sales/Purchase-inconsistency
- **Severity:** High
- **Status:** OPEN
- **What's wrong:** CR-060 fixed AR to foot aging. AP card still uses GL company payables when books enabled — AR and AP cards use different truth models.
- **Trigger / repro:** Books on; compare dashboard payables to sum(`payables_aging`).
- **Consequence:** Operators cannot reconcile AP card to aging; dual-ledger confusion.
- **Suggested fix direction:** `_company_payables` = sum(payables_aging) like AR; keep GL on books/recon surfaces.
- **Test to add:** `test_cr101_dashboard_payables_equals_aging_sum`
- **Twin check:** y — Purchase twin of CR-060

### CR-102 — Inventory summary `reserved` still from StockBalance cache
- **Module:** Reporting — inventory summary
- **Location:** `backend/reporting/services.py` inventory_summary (on_hand movement-summed; reserved from cache)
- **Type:** Data-integrity
- **Severity:** Medium
- **Status:** OPEN (residual of CR-062)
- **What's wrong:** Available qty can be wrong when reserved cache drifts even though on_hand is correct.
- **Suggested fix direction:** Derive reserved from open reservations / movements, or flag `reserved_drift`.
- **Test to add:** Drift reserved — summary surfaces flag or correct available
- **Twin check:** n-a

### CR-103 — GL backfill treats empty POSTED JE as done
- **Module:** Accounting — backfill commands
- **Location:** `backend/accounting/management/commands/backfill_*.py` `_has_je` / `.exists()` without `lines.exists()`
- **Type:** Silent-failure | Data-integrity
- **Severity:** Medium
- **Status:** OPEN
- **What's wrong:** Orphan empty POSTED headers (pre-CR-078 or race) cause backfill to **skip forever**; `PostingService.post` would heal if called.
- **Suggested fix direction:** Treat 0-line POSTED as missing (delete/repost) like PostingService.
- **Test to add:** Empty POSTED present — backfill reposts lines
- **Twin check:** n-a

### CR-104 — GST period soft_close has no `select_for_update` (TOCTOU)
- **Module:** Accounting / Reporting — period gates
- **Location:** `backend/reporting/gst_periods.py` `soft_close_period`; `assert_period_allows_money_amend` reads unlocked
- **Type:** Race
- **Severity:** High
- **Status:** OPEN (residual of CR-081 — accounting periods locked, GST soft_close not)
- **What's wrong:** Concurrent GST soft-close vs document/`PostingService.post` can race when no overlapping `AccountingPeriod` row is locked.
- **Trigger / repro:** Soft-close GST period while invoice complete posts same date.
- **Consequence:** Post into newly soft-closed GST period (or reverse).
- **Suggested fix direction:** Lock GST period row (or advisory lock) in soft_close and in assert path.
- **Test to add:** Concurrent soft_close + complete (Postgres)
- **Twin check:** AccountingPeriod close already locked — GST must match

### CR-105 — Docs↔GL reconciliation alert compares 1200/2100 only (ignores advances)
- **Module:** Accounting — books health / reconciliation
- **Location:** `BooksHealthService._docs_gl_party_alerts`
- **Type:** Improvement | Data-integrity
- **Severity:** Low
- **Status:** FIXED in working tree
- **What's wrong:** In `_docs_gl_party_alerts`, party GL outstanding was being compared to bare AR/AP control totals without factoring in customer advances (account 2300) or supplier advances (account 1250). When advances were present, document outstanding (which is net of allocations) drifted from the bare control total, triggering false `DOCS_GL_AR_MISMATCH` / `DOCS_GL_AP_MISMATCH` alerts. Note: this is distinct from control health (`control_balances`), which strictly validates 1200 ↔ tagged-1200 (see CR-157).
- **Trigger / repro:** Customer has unallocated advance on 2300; compare document AR against GL in `_docs_gl_party_alerts`.
- **Consequence:** False mismatch alerts in reconciliation and BooksHealthService when legitimate advances exist.
- **Code evidence:** `_docs_gl_party_alerts` originally compared against control totals without incorporating 2300/1250 tagged balances.
- **Suggested fix direction:** Evaluate advances (2300/1250) in `docs_gl_ar` / `docs_gl_ap` reconciliation calculations, while keeping bare control balance checks (1200/2100) strictly segregated.
- **Test to add:** Advance present — docs-GL reconciliation uses netted party GL (1200 net of 2300).
- **Twin check:** n-a

---

## Re-verification census (additive)

**Pilot gate (updated):** Do not treat "89 fixed" as green. Ship gate = original Phase 0–1 Criticals/Highs **plus** CR-094 (must), and strongly CR-090 / CR-100 / CR-101 / CR-104 before paying users.

### CR-106 — Reloaded `cashPending` cannot finish payment in POS `(POS-001)`
- **Module:** POS → cash settlement resume
- **Location:** `web/src/pages/pos/PosPage.tsx:396–405`, `:959–962`, `:1632–1636`
- **Type:** Data-integrity | Broken-feature
- **Severity:** High
- **What's wrong:** sessionStorage restores mid-settlement cash, but after reload cart is empty; checkout gates on cart before resume; Cash disabled when empty.
- **Trigger / repro:** Complete OK → kill before receipt → reload `/pos` → try Cash.
- **Consequence:** COMPLETED unpaid invoice; stock gone; resume is a false promise.
- **Code evidence:** Restore sets keys only; empty-cart check precedes `cashPending` resume.
- **Suggested fix direction:** If `cashPending`, skip cart gates; “Finish payment” CTA with restored key.
- **Test to add:** `pos_reload_mid_settlement_resumes_receipt_without_cart`
- **Twin check:** n-a
- **Cross-ref:** confirms-still-broken **CR-091**

### CR-107 — Sale settlement is multi round-trip, not one server transaction `(POS-002)`
- **Module:** POS → sales + payments
- **Location:** `PosPage.tsx:614–755`; `flushPosCheckout.ts:53–144`; `sales/services.py` complete; `payments/services.py`
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** Separate atomics per HTTP step; stock+GL commit before money.
- **Trigger / repro:** Drop network after complete 200, before receipt.
- **Consequence:** Unpaid COMPLETED invoices / unallocated receipts.
- **Code evidence:** Four distinct service entrypoints.
- **Suggested fix direction:** Idempotent POS checkout endpoint, or harden durable resume (CR-106/108).
- **Test to add:** `pos_checkout_half_success_matrix_complete_ok_receipt_fail`
- **Twin check:** y
- **Cross-ref:** confirms-still-broken **CR-002** (product-accepted Phase 2)

### CR-108 — UPI mid-settlement not durable across reload `(POS-003)`
- **Module:** POS → UPI
- **Location:** `PosPage.tsx:774–839` (no persist analogue)
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** UPI state only in React; reload clears; no in-POS resume.
- **Trigger / repro:** UPI → QR shown → reload.
- **Consequence:** Stock posted, payment unfinished.
- **Code evidence:** Cash has sessionStorage; UPI only `setUpiPending`.
- **Suggested fix direction:** Persist UPI pending like cash; “Confirm UPI” after restore.
- **Test to add:** `pos_upi_reload_mid_settlement_resumes_confirm`
- **Twin check:** n-a
- **Cross-ref:** **new** (UPI twin of CR-091)

### CR-109 — `cashPending` survives logout; company-scoped only `(POS-004)`
- **Module:** POS → session
- **Location:** `posStatus.ts:135–190`; `AuthContext.tsx:97–117`
- **Type:** Data-integrity
- **Severity:** Medium
- **What's wrong:** Mid-settlement snapshot not wiped on sign-out; not user-scoped.
- **Trigger / repro:** User A incomplete settlement → logout → User B same company.
- **Consequence:** Wrong operator inherits unpaid cue.
- **Code evidence:** Logout clears drafts only.
- **Suggested fix direction:** Scope `companyId:userId`; clear on logout.
- **Test to add:** `pos_logout_clears_cash_pending_storage`
- **Twin check:** n-a
- **Cross-ref:** **new**

### CR-110 — Client POS totals omit cess `(POS-005)`
- **Module:** POS → tax / tender
- **Location:** `posStatus.ts:117–123` (`computePosLineTax`)
- **Type:** Bug
- **Severity:** High
- **What's wrong:** `calculateLineTax` called without `cessRate`; UI/tender understates.
- **Trigger / repro:** Cess SKU; compare POS total vs preview/complete.
- **Consequence:** Till short or false tenderTooLow.
- **Code evidence:** cess used for inclusive extraction only.
- **Suggested fix direction:** Pass `cessRate`; prefer server gate total in UI.
- **Test to add:** `pos_cess_line_total_matches_preview`
- **Twin check:** y
- **Cross-ref:** **new** (amplifies CR-007)

### CR-111 — Tender UI shows client totals; gate uses server only at click `(POS-006)`
- **Module:** POS → cash tender UX
- **Location:** `PosPage.tsx:391–394`, `:963–996`, `:1582–1646`
- **Type:** Bug
- **Severity:** Medium
- **What's wrong:** Labels use client `grandTotal`; preview errors swallowed.
- **Trigger / repro:** Inclusive/cess divergence; Exact then Cash.
- **Consequence:** Till vs books mismatch on fallback.
- **Code evidence:** Display vs `tenderGateTotal` split; empty catch.
- **Suggested fix direction:** Drive display from gateTotal; block pay if preview fails.
- **Test to add:** `pos_tender_ui_uses_server_gate_total`
- **Twin check:** n-a
- **Cross-ref:** confirms-still-broken **CR-007** (PARTIAL; CR-090 payload fixed)

### CR-112 — Cash click guarded only by React `busy` (double-submit race) `(POS-007)`
- **Module:** POS → FE concurrency
- **Location:** `PosPage.tsx:909–916`; contrast flushGuard ref
- **Type:** Race
- **Severity:** Medium
- **What's wrong:** `busy` is async state; key minted after awaits — parallel clicks can mint two key families.
- **Trigger / repro:** Double-click Cash on slow network.
- **Consequence:** Parallel create/complete attempts.
- **Code evidence:** No checkoutGuard ref; key set late.
- **Suggested fix direction:** Ref guard; mint/persist key synchronously at click.
- **Test to add:** `pos_double_click_cash_single_gesture_key`
- **Twin check:** y
- **Cross-ref:** **new**

### CR-113 — Serial/batch error dialog retries with `confirmBlankPos: true` `(POS-008)`
- **Module:** POS → error recovery
- **Location:** `PosPage.tsx:1660–1684`
- **Type:** Missing-validation
- **Severity:** Medium
- **What's wrong:** Serial failure retry auto-confirms blank POS / walk-in.
- **Trigger / repro:** Blank walk-in + serial fail → confirm dialog.
- **Consequence:** Place-of-supply honesty bypassed.
- **Code evidence:** Always passes confirm flags.
- **Suggested fix direction:** Retry only original failure flags.
- **Test to add:** `pos_serial_retry_does_not_auto_confirm_blank_pos`
- **Twin check:** n-a
- **Cross-ref:** **new**

### CR-114 — Offline Outbox “Sync now” flushes POS without thermal `(POS-009)`
- **Module:** POS → offline sync
- **Location:** `OfflineOutboxPage.tsx:83–111` vs `PosPage.tsx:874–887`
- **Type:** Broken-feature | Silent-failure
- **Severity:** Medium
- **What's wrong:** Outbox flush has no thermal print path.
- **Trigger / repro:** Sync offline POS from `/offline` UI.
- **Consequence:** Paid sales without counter slip.
- **Code evidence:** No `downloadInvoiceThermalPdf` in outbox sync.
- **Suggested fix direction:** Shared flush+print helper.
- **Test to add:** `offline_outbox_pos_flush_prints_thermal`
- **Twin check:** n-a
- **Cross-ref:** confirms-still-broken **CR-006** residual

### CR-115 — `ENABLE_POS` is UI sugar; money APIs ungated `(POS-010)`
- **Module:** POS → feature flags
- **Location:** `PosPage.tsx`; `feature_flags.py`; contrast manufacturing permissions
- **Type:** Broken-feature
- **Severity:** Medium
- **What's wrong:** Flag hides nav only; RETAIL complete+receipt stay live.
- **Trigger / repro:** `ENABLE_POS=false`; API still completes retail+receipt.
- **Consequence:** False sense of disable.
- **Code evidence:** Comment admits UI sugar.
- **Suggested fix direction:** Document as UI-only (product-accepted CR-008) or gate checkout.
- **Test to add:** product-decision test
- **Twin check:** n
- **Cross-ref:** confirms-still-broken **CR-008** (product-accepted)

### CR-116 — Cash tendered / change never posted `(POS-011)`
- **Module:** POS → cash handling · **Severity:** Low · **Type:** Improvement
- **Location:** `PosPage.tsx` changeDue local; receipt = invoice total
- **Cross-ref:** confirms-still-broken **CR-011** (deferred)
- **Suggested fix / test:** Optional till session fields when product wants

### CR-117 — Stock chips 60s stale; no re-check on add `(POS-012)`
- **Module:** POS · **Severity:** Low · **Type:** Improvement
- **Location:** `PosPage.tsx:259–263`
- **Cross-ref:** confirms-still-broken **CR-013** PARTIAL
- **Note:** Server BLOCK still protects integrity

### CR-118 — Multi-flush thermal warn only last failure `(POS-013)`
- **Module:** POS · **Severity:** Low · **Type:** Silent-failure
- **Location:** `PosPage.tsx:874–887`
- **Cross-ref:** confirms-still-broken **CR-092** PARTIAL

### CR-119 — CR-001 remint fixed same-session; residual via CR-106/108 `(POS-014)`
- **Module:** POS → idempotency · **Severity:** Medium · **Type:** Data-integrity
- **What's wrong:** Same-session resume OK; reload then new cart sale can double-complete while orphan unpaid exists.
- **Suggested fix direction:** Fix CR-106/108; block new sale while pending settlement.
- **Cross-ref:** residual of **CR-001** (FIXED in-session)

---

### CR-120 — SO can convert to invoice **and** delivery challan (double stock / double AR) (SALES-001)
- **Module:** Sales → Orders / DC / Invoice chain
- **Location:** `backend/sales/notes_services.py` `convert_sales_order_to_challan` ~614–637; `complete_challan` ~770–788; `convert_delivery_challan` ~927–931
- **Type:** Data-integrity | Race
- **Severity:** Critical
- **What's wrong:** `convert_sales_order` blocks if live challan / checks `converted_invoice`; `convert_sales_order_to_challan` does **not** check `converted_invoice_id`. Manual DC can link an already-invoiced SO. Completing challan + invoice can each post SALE / AR.
- **Trigger / repro:** Confirm SO → Convert to invoice → Convert to challan → complete both.
- **Consequence:** Double stock out, double AR, reservation released twice. Release-blocking.
- **Code evidence:** Challan convert lacks `converted_invoice_id` guard present on invoice convert; complete_challan does not reject invoiced SO.
- **Suggested fix direction:** Reject challan convert/create/complete when SO has `converted_invoice_id`; reject DC→invoice if SO already linked to another invoice.
- **Test to add:** `test_so_invoice_then_challan_blocked`; assert single SALE qty.
- **Twin check:** Check PO→GRN+bill fork if any
- **Cross-ref hint:** new; interacts with CR-020/022

### CR-121 — Recurring poison/error advances `next_run_at` and skips the period (SALES-002)
- **Module:** Sales → Recurring
- **Location:** `backend/sales/recurring.py` `process_due_schedules` ~174–187
- **Type:** Silent-failure | Bug
- **Severity:** High
- **What's wrong:** Locked periods correctly do not advance (CR-015 fixed). On any exception, handler advances `next_run_at` without writing `RecurringInvoiceRun` — that `period_key` is never retried.
- **Trigger / repro:** Invalid template product; beat runs; fix template; next beat skips the failed month.
- **Consequence:** Silent missed billing for paying tenants.
- **Code evidence:** `except Exception` advances schedule.
- **Suggested fix direction:** Do not advance on error; park last_error; retry same period_key.
- **Test to add:** Fail once → fix → same period_key draft created.
- **Twin check:** n
- **Cross-ref hint:** CR-015 residual

### CR-122 — Draft SO remains editable after convert-to-invoice (SALES-003)
- **Module:** Sales → Orders
- **Location:** `phase1_serializers.py` `SalesOrderSerializer.update` ~235–246; `convert_sales_order` leaves DRAFT/CONFIRMED
- **Type:** Missing-validation
- **Severity:** Medium
- **What's wrong:** After convert, SO can stay DRAFT with `converted_invoice` set; serializer only blocks non-DRAFT edits.
- **Trigger / repro:** Draft SO → convert → PATCH SO items.
- **Consequence:** Source SO and invoice diverge.
- **Code evidence:** No block on `converted_invoice_id`.
- **Suggested fix direction:** Freeze SO when `converted_invoice_id` set.
- **Test to add:** Convert then PATCH SO → 400.
- **Twin check:** y (PO)
- **Cross-ref hint:** new

### CR-123 — SO reservation qty does not track amended draft invoice qty (SALES-004)
- **Module:** Sales → Orders + Invoice complete
- **Location:** `confirm_sales_order` reserves SO qty; `SalesService.complete` ~1066–1071 releases SO qty; draft invoice `set_items` free
- **Type:** Race | Data-integrity
- **Severity:** Medium
- **What's wrong:** Reservation is SO qty, not current invoice qty. Increase invoice qty leaves unprotected stock.
- **Trigger / repro:** Confirm SO qty 10 → convert → edit invoice to 15 → complete.
- **Consequence:** Concurrent oversell / intermittent complete failures.
- **Code evidence:** Release uses SO lines, not invoice lines.
- **Suggested fix direction:** Re-reserve to invoice qty on amend, or freeze qty to SO.
- **Test to add:** After amend, available reflects invoice qty reservation.
- **Twin check:** n-a / check PO
- **Cross-ref hint:** CR-020 residual

### CR-124 — Auto sales-return CN silent-confirms paid / price-override (SALES-005)
- **Module:** Sales → Returns + Credit notes
- **Location:** `return_service.py` ~282–284; headroom in `notes_services.py`
- **Type:** Data-integrity | Missing-validation
- **Severity:** Medium
- **What's wrong:** Standalone CN requires confirms (CR-096); auto-CN from return always passes confirm flags → paid invoice return without unallocate.
- **Trigger / repro:** Full receipt allocate → complete sales return.
- **Consequence:** Sticky over-allocation; AR messy.
- **Code evidence:** Hard-coded `confirm_paid_invoice=True` / price override.
- **Suggested fix direction:** Auto-unallocate up to CN amount, or require explicit return confirm.
- **Test to add:** Paid invoice + return → allocations adjusted or 400.
- **Twin check:** y (purchase return)
- **Cross-ref hint:** CR-017/096 residual

### CR-125 — Document chain still all-or-nothing (no partial convert) (SALES-006)
- **Module:** Sales → Quotation / SO / DC
- **Location:** convert_* functions — full line copy
- **Type:** Broken-feature
- **Severity:** Medium
- **What's wrong:** No per-line converted qty; cannot ship/invoice 40 of 100 without splitting docs.
- **Trigger / repro:** SO 100, customer wants 40 now.
- **Consequence:** SMB dispatch friction / over-shipping drafts.
- **Code evidence:** Full-line convert only.
- **Suggested fix direction:** Track converted qty per line, or document as known limitation.
- **Test to add:** (If implementing) partial DC then invoice remainder.
- **Twin check:** y
- **Cross-ref hint:** confirms-still-broken CR-022

### CR-126 — Delivery challan `complete` has no idempotency wrap (SALES-007)
- **Module:** Sales → Delivery challan + Idempotency
- **Location:** `phase1_views.py` ~324–327; `MONEY_IDEMPOTENCY_SCOPES` lacks challan; FE sends no key
- **Type:** Missing-validation | Silent-failure
- **Severity:** Medium
- **What's wrong:** Invoice/return/CN completes wrapped; challan complete posts stock without `wrap_idempotent`. Retry after timeout → hard error, not cached body.
- **Trigger / repro:** Timeout after successful challan complete; retry.
- **Consequence:** Ops confusion; weak money-scope discipline when stock posts.
- **Code evidence:** No scope / no wrap / no FE key.
- **Suggested fix direction:** Mirror invoice complete idempotency.
- **Test to add:** Double-complete same key → identical 200 + single SALE set.
- **Twin check:** y (PO convert / GRN)
- **Cross-ref hint:** CR-030 pattern twin

### CR-127 — CN `select_for_update` omits `company_id` (DN has it) (SALES-008)
- **Module:** Sales → Credit notes
- **Location:** `notes_services.py` `complete_credit_note` ~143 vs DN ~349–352
- **Type:** Cross-tenant (defense-in-depth)
- **Severity:** Low
- **What's wrong:** DN locks `pk` + `company_id`; CN locks by `pk` only.
- **Trigger / repro:** Mismatched note.company / invoice.company via non-API path.
- **Consequence:** Cross-tenant lock/mutate if invariant bypassed.
- **Code evidence:** Asymmetric lock queries.
- **Suggested fix direction:** Same `get(pk=..., company_id=...)` as DN.
- **Test to add:** Cross-company invoice id on CN complete → 404/400.
- **Twin check:** y (PUR-005)
- **Cross-ref hint:** CR-093 fixed DN; CN left behind

### CR-128 — Dead stock-delta branch remains in `set_items` after qty amend ban (SALES-009)
- **Module:** Sales → Amend
- **Location:** `services.py` `set_items` ~578–612 then ~653–690
- **Type:** Improvement
- **Severity:** Low
- **What's wrong:** Qty changes raise early (CR-024); later stock-delta loop unreachable for qty≠0 — footgun if raise weakened.
- **Trigger / repro:** N/A (unreachable).
- **Consequence:** Maintenance risk.
- **Code evidence:** Dead path after raise.
- **Suggested fix direction:** Delete delta stock branch; keep price-only + GL adjust.
- **Test to add:** Existing CR-024 test sufficient.
- **Twin check:** y (purchase set_items)
- **Cross-ref hint:** CR-024 follow-through

**Sales OK notes:** Invoice complete TX boundary solid (period gate before number; stock+COGS+GL in atomic; PDF on_commit). CR-094 DC×SO tenancy fixed. IRN FAILED non-live. Alloc concurrency OK.

---

#### Purchase draft ([Purchase review](470bc159-17c0-4d67-be4d-8dd8a3ebd218))

**Prior CR status (Purchase):** CR-030/031/034–037/039/097/098 FIXED; CR-032/033 policy OK; CR-038/041/045/047 PARTIAL residuals below.

### CR-129 — Purchase CN/DN `complete` missing Sales twin integrity gates (PUR-001)
- **Module:** Purchase → notes
- **Location:** `backend/purchases/notes_services.py:193–252` (CN), `:321–390` (DN); contrast `sales/notes_services.py`
- **Type:** Missing-validation | Sales/Purchase-inconsistency | Data-integrity
- **Severity:** High
- **What's wrong:** Purchase note complete only enforces monetary headroom — no source status COMPLETED/RETURNED, note_date≥invoice_date, source_item qty caps, paid/price/additional confirms, or PURCHASE_RETURN reason requiring return FK.
- **Trigger / repro:** CN against DRAFT bill; or CN qty > line with grand_total ≤ headroom; or CN on fully paid bill without confirm.
- **Consequence:** AP/ITC notes against non-posted bills; over-credit; silent over-allocation; stock-less “return” CN.
- **Code evidence:** CN lock/headroom only; Sales has full gate set.
- **Suggested fix direction:** Port Sales CN/DN complete gates 1:1 + FE confirms.
- **Test to add:** draft invoice / source qty / paid confirm / return-reason FK tests.
- **Twin check:** y (Sales stricter)
- **Cross-ref hint:** new (twins CR-017/018/026/096)

### CR-130 — Purchase CN/DN allow supplier ≠ linked bill supplier (PUR-002)
- **Module:** Purchase → notes API
- **Location:** `phase1_serializers.py` CN ~52–59, DN ~109–116; contrast Return / Sales CN
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** Company-scoped FKs only; no `supplier.pk == purchase_invoice.supplier_id`.
- **Trigger / repro:** POST CN supplier=A, invoice=B’s bill.
- **Consequence:** AP relief on A while consuming B’s headroom; GSTR/party ledgers diverge.
- **Code evidence:** Sales/Return validate match; purchase notes do not.
- **Suggested fix direction:** Same validate as Sales/Return.
- **Test to add:** `test_purchase_cn_rejects_supplier_invoice_mismatch`
- **Twin check:** y
- **Cross-ref hint:** new

### CR-131 — Return `unit_name` / base-qty headroom still unsafe (CR-045 residual) (PUR-003)
- **Module:** Purchase → returns
- **Location:** `serializers.py:301–318`; `_returned_quantities` / headroom / stock convert in `services.py`
- **Type:** Data-integrity
- **Severity:** High (alt-unit SKUs) / Medium otherwise
- **What's wrong:** Migration snapshots `unit_name`, but API cannot send/read it; headroom compares document qty while stock uses base qty.
- **Trigger / repro:** Bill in BOX; return defaulting to PCS.
- **Consequence:** Over/under stock vs billed; auto CN amounts wrong.
- **Code evidence:** Serializer omits `unit_name`; headroom uses `Sum("quantity")`.
- **Suggested fix direction:** Expose unit_name; headroom in base units.
- **Test to add:** `test_purchase_return_alternate_unit_headroom_base_qty`
- **Twin check:** y
- **Cross-ref hint:** confirms-still-broken CR-045

### CR-132 — Purchase debit note cannot carry `additional_charges` (PUR-004)
- **Module:** Purchase → DN
- **Location:** `PurchaseDebitNote` model (no field); CN has field+API
- **Type:** Broken-feature | Sales/Purchase-inconsistency
- **Severity:** Medium
- **What's wrong:** `set_debit_note_items` always sees additional_charges=0. Freight DN impossible via API.
- **Trigger / repro:** Attempt DN with freight; field absent.
- **Consequence:** Operators pad unit prices; AP/GL charge legs missing.
- **Code evidence:** Model/serializer lack field CN has.
- **Suggested fix direction:** Add model field + serializer + editor (mirror CN).
- **Test to add:** `test_purchase_dn_additional_charges_in_totals_and_gl`
- **Twin check:** y
- **Cross-ref hint:** confirms-still-broken CR-038

### CR-133 — Purchase CN locks source invoice without `company_id` (PUR-005)
- **Module:** Purchase → tenancy hardening
- **Location:** `notes_services.py:207` vs DN `:339–341`
- **Type:** Cross-tenant (defense-in-depth)
- **Severity:** Medium
- **What's wrong:** `select_for_update().get(pk=...)` without `company_id=note.company_id`.
- **Trigger / repro:** Legacy cross-company purchase_invoice_id.
- **Consequence:** Headroom/lock against wrong tenant invoice.
- **Code evidence:** Asymmetric with DN/return.
- **Suggested fix direction:** Same get(pk, company_id) as DN.
- **Test to add:** Cross-company invoice id → 404/400.
- **Twin check:** y (SALES-008)
- **Cross-ref hint:** new

### CR-134 — PO `convert` has no idempotency scope (PUR-006)
- **Module:** Purchase → PO
- **Location:** `phase1_views.py:189–194`; `MONEY_IDEMPOTENCY_SCOPES` lacks `purchase_order_convert`
- **Type:** Missing-validation
- **Severity:** Medium
- **What's wrong:** Convert creates draft PI + CONVERTED atomically but HTTP has no `wrap_idempotent`. Lost response → “Cannot convert” with draft already exists.
- **Trigger / repro:** Double-submit / timeout after commit.
- **Consequence:** Operator confusion; no durable replay.
- **Code evidence:** No scope in MONEY set; no wrap.
- **Suggested fix direction:** wrap_idempotent + FE gesture key.
- **Test to add:** `test_po_convert_idempotent_replay`
- **Twin check:** y (SALES-007)
- **Cross-ref hint:** new

### CR-135 — Nested `batch` / note `product` PKs not company-scoped at serializer (PUR-007)
- **Module:** Purchase → company_id scoping
- **Location:** `PurchaseItemSerializer.batch`; CN/DN item product default ModelSerializer
- **Type:** Cross-tenant (defense-in-depth)
- **Severity:** Medium (Low if RLS always on)
- **What's wrong:** Invoice/return product uses CompanyPrimaryKeyRelatedField; note lines and batch do not (service may still reject).
- **Trigger / repro:** Cross-tenant product/batch id without RLS.
- **Consequence:** Opaque errors or worse if path skips `_validate_lines`.
- **Code evidence:** Inconsistent field types.
- **Suggested fix direction:** CompanyPrimaryKeyRelatedField for batch and note/PO product.
- **Test to add:** batch + CN product cross-tenant.
- **Twin check:** y
- **Cross-ref hint:** CR-047 class residual

### CR-136 — Supplier payment `bank_account` FK still unscoped (CR-047 residual) (PUR-008)
- **Module:** Payments → supplier payment
- **Location:** `payments/serializers.py:103–121`; service checks company at `:335`
- **Type:** Missing-validation
- **Severity:** Low
- **What's wrong:** Supplier scoped; bank_account still global until service.
- **Trigger / repro:** Cross-company bank account id.
- **Consequence:** Service 400; residual before service / non-RLS.
- **Code evidence:** Serializer asymmetry.
- **Suggested fix direction:** Scope bank_account queryset like supplier.
- **Test to add:** Cross-company bank_account → 400 at serializer.
- **Twin check:** n-a
- **Cross-ref hint:** confirms-still-broken CR-047

### CR-137 — Bill-import `confirm_non_gst` has no FE wiring (CR-041 residual) (PUR-009)
- **Module:** Purchase → bill import UI
- **Location:** Backend `imports/services.py`; FE `web/src/pages/imports/*` — no confirm_non_gst
- **Type:** Broken-feature
- **Severity:** Medium
- **What's wrong:** Backend defaults all-zero lines to GST unless confirm; SPA never sets it.
- **Trigger / repro:** Upload 0%-only bill of supply → always GST type.
- **Consequence:** Wrong purchase_type unless API/manual edit.
- **Code evidence:** No FE wiring for confirm flag.
- **Suggested fix direction:** Preview checkbox → update_preview({ confirm_non_gst }).
- **Test to add:** UI/API commit with confirm flag.
- **Twin check:** n-a
- **Cross-ref hint:** confirms-still-broken CR-041

**Purchase OK notes:** Bill complete stock+AP one atomic; CR-097/098 cancel/BoE draft unlink fixed; bill import all-or-nothing; supplier alloc locks + match; landed cost charges→5110 documented policy.

---

#### Stock/Godown draft ([Stock review](5a8905d1-61b2-453d-aa6a-717e56c8ab24))

**Prior CR status (Stock):** CR-048–053, 057–058 FIXED; CR-054/055/056/059 PARTIAL/accepted residuals; CR-099 STILL BROKEN (expanded as STK-015). New: STK-016 offline 409, STK-017 append-only hole.

### CR-138 — Balance vs `sum(movements)`: no runtime reconciliation (CR-054 residual) (STK-007)
- **Module:** Stock → StockBalance drift
- **Location:** Hot path OK `inventory/services.py` ~181–230; report flags `reporting/services.py` ~485–568; UI `CurrentStockPage.tsx` still `listStock` → StockBalance
- **Type:** Data-integrity
- **Severity:** Medium
- **What's wrong:** Report uses movement sum + `balance_drift`; Current Stock UI is cache-first; no scheduled balance↔movement health check.
- **Trigger / repro:** Corrupt `on_hand` → Current Stock wrong; inventory summary may flag drift.
- **Consequence:** Ops screens show wrong available until rebuild.
- **Code evidence:** UI reads StockBalance; comment notes no scheduled health.
- **Suggested fix direction:** UI/ops parity with movement sum or scheduled alert.
- **Test to add:** Drift → Current Stock warns or matches movement sum.
- **Twin check:** n-a (RPT-003/008 related)
- **Cross-ref hint:** confirms-still-broken CR-054; CR-062/102 theme

### CR-139 — Transfers: no in-transit; DRAFT no reserve (CR-055 accepted) (STK-008)
- **Module:** Stock → transfer
- **Location:** `models.py` statuses DRAFT/COMPLETED/CANCELLED; `complete` OUT+IN atomic ~1320–1393
- **Type:** Broken-feature | Missing-validation
- **Severity:** Medium
- **What's wrong:** DRAFT non-binding; concurrent sale can empty source before complete. No in-transit state.
- **Trigger / repro:** Draft transfer qty, concurrent invoice sells source stock, then complete transfer.
- **Consequence:** Multi-godown races under load (BLOCK still prevents negative).
- **Code evidence:** Comment documents DRAFT non-binding; statuses lack IN_TRANSIT.
- **Suggested fix direction:** Reserve on draft or document as known limitation.
- **Test to add:** Concurrent sale vs draft transfer under BLOCK.
- **Twin check:** n-a
- **Cross-ref hint:** confirms-still-broken CR-055 (product-accepted doc)

### CR-140 — Stock-count KEEP_SERVER / conflict copy (CR-056 residual) (STK-009)
- **Module:** Stock → count conflict
- **Location:** `views.py` ~705–715; `StockConflictModal.tsx` ~42–47; `en.ts` copy
- **Type:** Silent-failure | Missing-validation
- **Severity:** Medium
- **What's wrong:** KEEP_SERVER skips drifted lines but still POSTED; copy does not say physical count abandoned for those SKUs; FE prefers Keep Server.
- **Trigger / repro:** Count conflict → Keep Server → POSTED without those SKUs adjusted.
- **Consequence:** Operators think count applied; drifted SKUs unchanged.
- **Code evidence:** Skip-then-POSTED; preferential Keep Server UX.
- **Suggested fix direction:** Explicit abandon copy; or refuse POSTED until all lines resolved.
- **Test to add:** KEEP_SERVER → drifted lines unchanged + UI copy asserts.
- **Twin check:** n-a
- **Cross-ref hint:** confirms-still-broken CR-056; see STK-016

### CR-141 — FIFO verify not automated (CR-059 residual) (STK-014)
- **Module:** Stock → cost layers
- **Location:** `verify_fifo_layers` ~1946–1990; `seed_fifo_layers_from_balances` can set `source_movement=None`
- **Type:** Improvement | Data-integrity
- **Severity:** Medium
- **What's wrong:** Verify not scheduled; seed can create layers without source movement.
- **Trigger / repro:** FIFO tenant after cutover without running verify.
- **Consequence:** Silent layer/on_hand drift until noticed.
- **Code evidence:** Docs-only test; no scheduled job.
- **Suggested fix direction:** Schedule verify after cutover; refuse seed without source_movement when possible.
- **Test to add:** Beyond docs-string assert.
- **Twin check:** n-a
- **Cross-ref hint:** confirms-still-broken CR-059

### CR-142 — Manual serial return resolves wrong / empty SALE move (CR-099) (STK-015)
- **Module:** Stock → Serial / FIFO
- **Location:** `inventory/views.py` `_sale_movement_for_serial` ~412–421; transition ~495–514
- **Type:** Data-integrity | Bug
- **Severity:** High
- **What's wrong:** First SalesItem whose JSON contains the serial wins even if that invoice has **no** SALE moves (draft can shadow). Multi-line same SKU maps index across all product SALE moves → wrong peel/cost.
- **Trigger / repro:** Complete sale of SN; newer draft lists same SN; manual return. Or two completed lines same SKU different costs; return second line’s serial.
- **Consequence:** FIFO understatement / wrong unit cost; qty still +1 AVAILABLE.
- **Code evidence:** Newest matching item short-circuits; empty moves skip restore_fifo_peels.
- **Suggested fix direction:** Prefer COMPLETED invoices with SALE moves; map serial→move by document line.
- **Test to add:** Draft-shadow + multi-line serial return asserts.
- **Twin check:** n-a
- **Cross-ref hint:** confirms-still-broken CR-099

### CR-143 — Offline stock-count flush cannot resolve 409 conflicts (STK-016)
- **Module:** Stock → Offline / godown conflict
- **Location:** `StockCountPage.tsx` ~92–96; `useStockOffline.ts` ~16–20; `invoiceDraftCache.ts` ~420–422
- **Type:** Broken-feature | Silent-failure
- **Severity:** High
- **What's wrong:** Offline queue stores empty `resolveConflicts`; flush posts without resolve; 409 fails outbox with no StockConflictModal on auto-flush.
- **Trigger / repro:** Queue count offline → intervening sale → online flush.
- **Consequence:** Offline counts stuck forever; “sync failed” with no Keep Server/Local path.
- **Code evidence:** No conflict modal on outbox path; online path has modal.
- **Suggested fix direction:** Surface conflict modal (or re-open count) before retry.
- **Test to add:** Offline flush 409 → conflict UI → successful resolve.
- **Twin check:** n-a
- **Cross-ref hint:** new (amplifies CR-056)

### CR-144 — Purchase price amend mutates `StockMovement.unit_cost` outside `stamp_cost` (STK-017)
- **Module:** Stock → Movements / purchase caller
- **Location:** `purchases/services.py` `restamp_fifo_layers_for_price_amend` ~470; contrast `models.py` `stamp_cost` ~149–180
- **Type:** Data-integrity
- **Severity:** Critical
- **What's wrong:** Raw `StockMovement.objects.filter(pk=...).update(unit_cost=...)` bypasses model `save` guard and documented `stamp_cost` — append-only invariant hole.
- **Trigger / repro:** H9 price-only amend on FIFO purchase with unpeeled layers.
- **Consequence:** Audit/append-only contract broken; no stamp_cost lock pattern.
- **Code evidence:** QuerySet `.update` only live mutate besides stamp_cost.
- **Suggested fix direction:** Use `StockMovement.stamp_cost(...)` or compensating movement.
- **Test to add:** Assert restamp uses stamp_cost / no raw update.
- **Twin check:** y (Purchase)
- **Cross-ref hint:** new (CR-053 class of hole)

**Stock OK notes:** CR-048–053/057–058 fixed; post_movement lock-before-check; BLOCK concurrency solid; import void append-only; period gates on count/transfer; WARN running cost tracks negatives; default warehouse unique OK.

### CR-145 — Opening-balance invoices inflate AR/AP aging and dashboard receivables/payables (RPT-001)
- **Module:** Reporting → Dashboard KPIs / aging
- **Location:** `backend/reporting/services.py:139-143` (`receivables_aging`); `:594-599` (`payables_aging`); contrast `:177-210` (`is_opening_balance=False` on turnover)
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** CR-065 fixed MTD sales/purchases to exclude openings, but aging (and AR/AP KPI cards that foot aging) still include opening COMPLETED/RETURNED invoices. GSTR correctly excludes openings.
- **Trigger / repro:** Complete SI with `is_opening_balance=True`, unpaid; turnover KPIs unchanged, receivables/aging rise.
- **Consequence:** AR/AP disagree with GSTR and with sales/purchase KPIs after Tally-style openings.
- **Code evidence:** Aging queryset lacks `is_opening_balance=False`; dashboard reuses aging under a CR-065 comment.
- **Suggested fix direction:** Filter openings out of both aging paths (same predicate as GSTR/turnover).
- **Test to add:** `test_rpt001_opening_balance_excluded_from_ar_ap_aging_and_kpis`
- **Twin check:** y
- **Cross-ref hint:** CR-065 residual; amplifies CR-060/101 after openings

### CR-146 — Party ledgers still GL-when-books while dashboard AR/AP are document aging (RPT-002)
- **Module:** Reporting / Ledgers → Customer/Supplier ledger vs Dashboard
- **Location:** `backend/ledgers/services.py:283-288`; `:320-328` / `:933+`; contrast `reporting/services.py:100-114`
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** Dashboard cards are document aging; party ledgers (and WhatsApp outstanding) still switch to GL when books on and basis ≠ DOCUMENTS_ALWAYS.
- **Trigger / repro:** Books on with posting drift/advances; compare Dashboard Receivables to Customer Ledger outstanding.
- **Consequence:** Operators cannot reconcile dashboard ↔ party statements.
- **Code evidence:** `_use_gl_outstanding` still branches ledgers; dashboard intentionally documents-only.
- **Suggested fix direction:** Same outstanding basis for ledger + aging + KPI, or hard UI label + Books Health gate.
- **Test to add:** `test_rpt002_dashboard_ar_equals_sum_customer_ledger_when_books_on`
- **Twin check:** y
- **Cross-ref hint:** CR-060/101 residual; CR-082/105 theme (twin of ACC-004)

### CR-147 — Inventory `reserved` / `available` still from StockBalance cache (CR-102) (RPT-003)
- **Module:** Reporting → inventory summary
- **Location:** `backend/reporting/services.py:533-553,569-570`
- **Type:** Data-integrity
- **Severity:** Medium
- **What's wrong:** `on_hand` = Σ movements; `reserved` = `StockBalance.reserved`. `reserved_drift` only flags negative or > on_hand, not drift vs open SO reservations.
- **Trigger / repro:** Corrupt `reserved` downward; available overstated; no flag if `reserved ≤ on_hand`.
- **Consequence:** Available qty wrong for ops/reorder.
- **Code evidence:** Reads cache; comment admits no movement sum for reserved.
- **Suggested fix direction:** Derive reserved from confirmed SO / reservation ledger, or always compare to `_confirmed_so_qty`.
- **Test to add:** `test_cr102_reserved_cache_drift_flags_or_corrects_available`
- **Twin check:** n-a
- **Cross-ref hint:** confirms-still-broken CR-102

### CR-148 — Inventory report UI drops `balance_drift` / `reserved_drift` (RPT-004)
- **Module:** Reporting FE → Inventory report
- **Location:** `web/src/pages/reports/InventoryReportPage.tsx:55-64,36-45`
- **Type:** Silent-failure
- **Severity:** Medium
- **What's wrong:** API may return drift flags; FE maps only qty/value columns and never surfaces them.
- **Trigger / repro:** Force balance drift; open Inventory Reports — row looks healthy.
- **Consequence:** Backend honesty flags invisible.
- **Code evidence:** Row mapper omits drift keys; no drift column/chip.
- **Suggested fix direction:** Warning chip/row highlight when either drift flag present.
- **Test to add:** FE: drifted row renders warning
- **Twin check:** n-a
- **Cross-ref hint:** CR-062/102 UX gap

### CR-149 — `assert_report_date_span` no-ops unless both dates set (RPT-005)
- **Module:** Reporting → exports / registers / cash book
- **Location:** `backend/reporting/services.py:82-91`; callers in `views.py`
- **Type:** Bug
- **Severity:** High
- **What's wrong:** Span check returns early if either bound missing. `?date_from=2019-04-01` alone bypasses 366-day cap.
- **Trigger / repro:** Export/GET sales-register with only `date_from` years ago.
- **Consequence:** Multi-year materialization / timeout — CR-074 only partially closed.
- **Code evidence:** `if not date_from or not date_to: return`
- **Suggested fix direction:** Require both bounds, or treat missing `date_to` as today and enforce span.
- **Test to add:** `test_rpt005_date_from_only_rejects_or_caps_span`
- **Twin check:** y
- **Cross-ref hint:** CR-074 residual

### CR-150 — Product / customer sales endpoints skip date-span assert (RPT-006)
- **Module:** Reporting → analytics APIs
- **Location:** `backend/reporting/views.py:155-176`
- **Type:** Improvement | Bug
- **Severity:** Medium
- **What's wrong:** Registers/cash book call span assert; product/customer sales do not.
- **Trigger / repro:** Wide/empty date window on product-sales.
- **Consequence:** Heavy aggregates over full history.
- **Code evidence:** Missing `assert_report_date_span` call.
- **Suggested fix direction:** Same span guard as registers.
- **Test to add:** Over-366d product-sales → 400
- **Twin check:** n-a
- **Cross-ref hint:** CR-074 family

### CR-151 — Inventory report value can use RunningCost/FIFO layer cache (RPT-007)
- **Module:** Reporting → inventory summary valuation
- **Location:** `backend/reporting/services.py:522-551`; `inventory/services.py:1622-1651`
- **Type:** Data-integrity
- **Severity:** Medium
- **What's wrong:** When on_hand matches StockBalance, value comes from valuation cache (RunningCost/layers), not pure movement replay. Drifted on_hand falls back to `unit_cost * on_hand`.
- **Trigger / repro:** Wrong RunningCost with matched qty → summary shows movement qty + cached value.
- **Consequence:** Inventory report total ≠ BS inventory_valuation / GL 1400 without a flag.
- **Code evidence:** Dual store for qty vs value.
- **Suggested fix direction:** Always value from movement-consistent engine, or flag `value_source` / variance vs GL.
- **Test to add:** Corrupt RunningCost with matched qty → flag or recompute
- **Twin check:** Accounting BS inventory_valuation
- **Cross-ref hint:** CR-062 value half

### CR-152 — Dashboard `low_stock_count` uses StockBalance cache (RPT-008)
- **Module:** Reporting → Dashboard KPI
- **Location:** `backend/reporting/services.py:225-227`; `inventory/views.py:54-91`
- **Type:** Data-integrity
- **Severity:** Medium
- **What's wrong:** Inventory summary on_hand = Σ movements; low-stock KPI uses `StockBalance.on_hand - reserved`.
- **Trigger / repro:** Balance drift vs movements → dashboard low-stock ≠ Inventory report.
- **Consequence:** Inconsistent ops signals.
- **Code evidence:** Different SoT for low-stock vs inventory summary.
- **Suggested fix direction:** Drive alerts from movement on_hand + consistent reserved policy.
- **Test to add:** Balance drift → low_stock_count matches movement-based available
- **Twin check:** n-a
- **Cross-ref hint:** CR-062 family

### CR-153 — Dashboard returns AR aging buckets but not AP aging (RPT-009)
- **Module:** Reporting FE / API
- **Location:** `backend/reporting/services.py:249-252`; `DashboardPage.tsx:89-107,253-274`
- **Type:** Broken-feature
- **Severity:** Low
- **What's wrong:** Payables KPI foots aging server-side but response omits `payables_aging`; UI only charts receivables.
- **Trigger / repro:** No AP buckets in dashboard JSON to verify CR-101 footing.
- **Consequence:** Asymmetric AR/AP UX; operators cannot visually verify AP.
- **Code evidence:** Payload/UI asymmetry.
- **Suggested fix direction:** Include `payables_aging` + FE chart, or document intentional omission.
- **Test to add:** Dashboard JSON `payables_aging` sums to payables
- **Twin check:** y
- **Cross-ref hint:** CR-101 UX completeness

### CR-154 — No stock ledger / stock aging report in Reporting scope (RPT-010)
- **Module:** Reporting → stock
- **Location:** Scope gap vs checklist; `ReportService.inventory_summary` only
- **Type:** Broken-feature
- **Severity:** Medium
- **What's wrong:** Checklist requires stock summary/ledger/aging = sum(StockMovement); only summary exists.
- **Trigger / repro:** Navigate reports — no movement ledger or batch/expiry aging worksheet.
- **Consequence:** FEFO/batch aging and movement audit not operator-facing.
- **Code evidence:** No reporting API/page for stock ledger/aging.
- **Suggested fix direction:** Movement-sourced stock ledger + batch/expiry aging.
- **Test to add:** Ledger foots to Σ movements per SKU/WH
- **Twin check:** n-a
- **Cross-ref hint:** Checklist item unmet

### CR-155 — CSV/XLSX/GSTR exports still fully materialize in memory (RPT-011)
- **Module:** Reporting → ExportView / CashBook / GSTR xlsx
- **Location:** `backend/reporting/views.py:214-242,647-656,1298-1310`
- **Type:** Improvement
- **Severity:** Medium
- **What's wrong:** Even with span cap, rows → StringIO/BytesIO/Workbook in one shot; no streaming.
- **Trigger / repro:** Dense POS tenant, 366-day sales-register CSV.
- **Consequence:** Memory spikes / worker OOM under load.
- **Code evidence:** Full in-memory builders.
- **Suggested fix direction:** Streaming response; independent row-count ceiling.
- **Test to add:** Row-count ceiling 400 when exceeded
- **Twin check:** n-a
- **Cross-ref hint:** CR-074 residual

### CR-156 — GST soft-close vs Complete TOCTOU when period row missing (RPT-012)
- **Module:** Reporting → `gst_periods`
- **Location:** `backend/reporting/gst_periods.py:39-52`, `:123-136`
- **Type:** Race
- **Severity:** High
- **What's wrong:** If no `GstReturnPeriod` row yet, assert does not lock/create; concurrent soft_close can SOFT_CLOSE after assert passed.
- **Trigger / repro:** First soft-close of month racing Complete (Postgres).
- **Consequence:** Money posts into newly soft-closed GST month.
- **Code evidence:** Assert only locks existing row; soft_close can create under lock.
- **Suggested fix direction:** `get_or_create` + `select_for_update` in assert path.
- **Test to add:** Concurrent soft_close + complete (Postgres)
- **Twin check:** n-a (AccountingPeriod already locks)
- **Cross-ref hint:** confirms-still-broken CR-104 (same as ACC-002)

**Reporting OK notes:** CR-060/061/100/101 fixed; most CR-062–077 closed; GSTR footing/HSN/BoE/3B ITC look sound; company scoping on GSTR bases OK.

---

#### Sales draft ([Sales review](58cb46ce-3270-47d8-b6c4-d9d26f9855df))

**Prior CR status (Sales):** CR-014–016, 018–021, 023–025, 027–029, 093–096 FIXED; CR-017/026 PARTIAL; CR-022 STILL OPEN; CR-015 error-path residual → SALES-002.

### CR-157 — Advance accounts (2300/1250) must not conflate with AR/AP control-account health (ACC-001)
- **Module:** Accounting → books health / period & FY close
- **Location:** `backend/accounting/services.py:2009–2030`, `1849–1865`; `reports.py:389–394`
- **Type:** Data-integrity | Architectural invariant
- **Severity:** Critical
- **Status:** FIXED & VERIFIED in working tree (`tests/test_b_wave_cr120_144_157.py`)
- **What's wrong:** Reconciling party GL with document balances (CR-105) requires evaluating customer advances (2300) and supplier advances (1250). However, advance liability accounts (2300/1250) must never be folded into the AR/AP control-account balance check in `BooksHealthService.control_balances`. The control balance health check verifies internal ledger posting integrity — ensuring every rupee posted to GL control account 1200 is tagged to a customer line on 1200 (`expected_ar = tagged_net("1200", "customer")`). If customer advances (2300) are folded into `expected_ar`, the bare control account 1200 balance immediately mismatches `expected_ar` whenever unallocated customer receipts exist, generating a false `AR_CONTROL_MISMATCH` that hard-blocks period and FY close.
- **Trigger / repro:** Customer has ₹1,000 completed invoice and ₹400 unallocated receipt (credit on 2300). If control check added 2300 to expected AR, control balance would report false failure (`ar.healthy=False`), blocking close.
- **Consequence:** Businesses with legitimate customer advances would be permanently blocked from soft-closing and hard-closing accounting periods.
- **Code evidence:** `control_balances` strictly computes `expected_ar = tagged_net("1200", "customer")` and `expected_ap = -tagged_net("2100", "supplier")`. Advance accounts (2300/1250) are evaluated exclusively in `_docs_gl_party_alerts` (`docs_gl_ar`/`docs_gl_ap`) and separate advance recon.
- **Suggested fix direction:** Maintain strict separation between control-balance health (bare 1200/2100 vs tagged 1200/2100 lines) and document-to-GL party reconciliation (`docs_gl_ar` incorporating 2300 advance credit net).
- **Test to add:** `test_cr157_advance_receipt_control_healthy` (verified in tree).
- **Twin check:** AP twin (2100 control vs 1250 supplier advances)
- **Cross-ref hint:** Reconciled with CR-105; clarifies CR-082 / CR-159 dual-ledger boundary

### CR-158 — Empty POSTED JE still treated as “done” outside backfill (CR-103 residual) (ACC-003)
- **Module:** Accounting → health missing-posting + FY close
- **Location:** `backend/accounting/services.py:1928–1932` `_unposted_qs`; `reports.py:360–387` FY_CLOSE early return
- **Type:** Data-integrity | Silent-failure
- **Severity:** High
- **What's wrong:** Backfill `_has_je` correctly requires `lines__isnull=False`. Health excludes any JE by `source_id` regardless of lines → orphan empty POSTED hides `DOCUMENT_MISSING_POSTING`. FY close returns early on empty POSTED FY_CLOSE and still hard-closes periods.
- **Trigger / repro:** Empty POSTED SI JE → health silent; empty FY_CLOSE JE → skips real close work but hard-closes.
- **Consequence:** Missing postings invisible; FY close idempotency wrong.
- **Code evidence:** Health/FY path does not require lines; backfill does.
- **Suggested fix direction:** Treat JE as posted only when it has lines (same predicate as backfill); refuse empty FY_CLOSE as done.
- **Test to add:** Empty POSTED SI → health alerts; empty FY_CLOSE → does not skip real close.
- **Twin check:** n-a
- **Cross-ref hint:** confirms-still-broken CR-103 (partial — backfill fixed)

### CR-159 — Dual ledger can still silently diverge for ops decisions (ACC-004)
- **Module:** Accounting → derived ledger vs live GL
- **Location:** `backend/ledgers/services.py:291–315`, `320–336`; `backend/accounting/services.py:2145–2200`, `1838–1849`
- **Type:** Data-integrity
- **Severity:** High
- **What's wrong:** `DOCS_GL_AR/AP_MISMATCH` are warnings only — period close ignores them. Credit limit takes `max(GL, docs)` and logs. Party outstanding can be GL while aging/UI use documents.
- **Trigger / repro:** Untagged manual 1200/2100 lines or partial backfill → drift; close still succeeds.
- **Consequence:** Ops/credit decisions on diverged truths; close does not force reconciliation.
- **Code evidence:** Warn helper exists; close blockers do not include docs↔GL mismatch.
- **Suggested fix direction:** Block close (or force DOCUMENTS_ALWAYS) when drift exceeds tolerance.
- **Test to add:** Large drift blocks close.
- **Twin check:** n-a (Reporting KPI twin)
- **Cross-ref hint:** confirms-still-broken CR-082; theme of CR-060

### CR-160 — Purchase residual ≤ bound still absorbed; no header/line tax hard-stop (ACC-005)
- **Module:** Accounting → purchase tax → GL
- **Location:** `backend/accounting/services.py:1175–1193` vs sales `593–612`
- **Type:** Sales/Purchase-inconsistency | Data-integrity
- **Severity:** Medium
- **What's wrong:** Residuals `≥1` and `≤ max(100, 10% grand)` still become 5110 without `additional_charges`. Sales refuses header/line tax drift > ₹0.05. Cess accounts themselves OK. `test_b1_034_*` still expects large residual to book (test debt vs CR-085).
- **Trigger / repro:** Purchase bill with mid-size tax residual within bound, no additional_charges.
- **Consequence:** Expense dump absorbs tax drift; Sales twin would refuse.
- **Code evidence:** Purchase residual absorb path vs sales hard refuse.
- **Suggested fix direction:** Align purchase with sales hard-stop; update B1-034.
- **Test to add:** Within-bound residual → refuse or audit; update B1-034.
- **Twin check:** y (Sales stricter)
- **Cross-ref hint:** confirms-still-broken CR-085 (partial)

### CR-161 — Manual journals cannot party-tag AR/AP lines (ACC-006)
- **Module:** Accounting → voucher / dual ledger
- **Location:** `backend/accounting/serializers.py:80–91`
- **Type:** Missing-validation | Broken-feature
- **Severity:** Medium
- **What's wrong:** No `customer`/`supplier` fields on journal line serializer → untagged 1200/2100 inflate control vs tagged ledger / docs-GL. Balanced DE + company scope OK.
- **Trigger / repro:** Post manual JE debiting 1200 without party tag.
- **Consequence:** Dual-ledger / control health drift.
- **Code evidence:** Serializer omits party FKs.
- **Suggested fix direction:** Allow optional party tags; require tag when account is AR/AP control.
- **Test to add:** Untagged 1200 line rejected or tagged required.
- **Twin check:** n-a
- **Cross-ref hint:** new (amplifies CR-082)

### CR-162 — Feature flag dual-key UI vs API `(ACC-007)`
- **Module:** Accounting / Settings — feature flags
- **Location:** `backend/accounts/models.py`, `web/src/config/features.ts`, `web/src/navigation/menu.ts`
- **Type:** Improvement | Config-drift
- **Severity:** Low
- **What's wrong:** Frontend gates accounting routes and menus on static build-time flag `VITE_ENABLE_ACCOUNTING` in `features.ts`, while backend dynamically evaluates `company.accounting_enabled`. If the frontend environment build variable is false, absent, or desynced, users cannot access accounting pages or vouchers in the UI even after enabling accounting in Company Settings on the backend.
- **Trigger / repro:** Run frontend build with default / false `VITE_ENABLE_ACCOUNTING`. Log in as company owner and enable accounting via Settings. Menu items and routes for Journals, CoA, and Books Health remain hidden or blocked.
- **Consequence:** Tenant is unable to use enabled accounting features without a custom frontend rebuild or manual environment override; creates customer support escalation.
- **Code evidence:** `features.ts` checks `import.meta.env.VITE_ENABLE_ACCOUNTING` statically rather than combining with authenticated tenant `company.accounting_enabled`.
- **Suggested fix direction:** Synchronize feature flag evaluation dynamically from `useAuth().company.accounting_enabled` (or fallback to company config), treating `VITE_ENABLE_ACCOUNTING` solely as an optional master kill-switch.
- **Test to add:** Verify that setting `company.accounting_enabled = true` renders accounting navigation items even when `VITE_ENABLE_ACCOUNTING` is unset.
- **Twin check:** n-a
- **Cross-ref:** confirms-still-broken **CR-089**


### CR-163 — POS `pos_checkout` endpoint omits `CanCreateSales` and `CanCreatePayments` permission enforcement
- **Status (2026-09-08):** FIXED & VERIFIED in tree (`backend/sales/views.py:88–95`, `tests/test_wave4_rbac.py`)
- **Module:** POS → permissions
- **Location:** `backend/sales/views.py:88–95` (in `SalesInvoiceViewSet.get_permissions`)
- **Type:** Missing-validation | Permissions
- **Severity:** High
- **What's wrong:** In `SalesInvoiceViewSet.get_permissions()`, the atomic `pos_checkout` action (`url_path="pos-checkout"`) was omitted from permission checks enforcing `CanCreateSales()` and `CanCreatePayments()`. Any authenticated tenant member could call `/pos-checkout/` to create completed invoices, decrement stock, and record receipts without explicit sales or payment creation privileges.
- **Trigger / repro:** Authenticated user with `can_create_sales=False` or `can_create_payments=False` calls `POST /api/v1/sales/invoices/pos-checkout/`.
- **Consequence:** Unauthorized invoice creation, inventory decrement, and payment creation by restricted users.
- **Code evidence:** Updated `SalesInvoiceViewSet.get_permissions()`:
```python
if self.action == "pos_checkout":
    return [IsAuthenticated(), HasCompany(), SubscriptionWritesAllowed(), CanCreateSales(), CanCreatePayments()]
```
- **Suggested fix direction:** Add `pos_checkout` action check returning both `CanCreateSales()` and `CanCreatePayments()`.
- **Test to add:** `tests/test_wave4_rbac.py::test_pos_checkout_permission_denied_without_can_create_sales_and_payments` (PASSED)
- **Twin check:** n-a

---

### CR-164 — Purchase credit note complete requires explicit `source_item` on every line without auto-resolving single product lines
- **Status (2026-09-08):** FIXED & VERIFIED in tree (`backend/purchases/notes_services.py:105`, `tests/test_a7_a8_a9_highs.py`)
- **Module:** Purchase → credit note complete
- **Location:** `backend/purchases/notes_services.py:287–295` (in `PurchaseNotesService.complete_credit_note`), `backend/purchases/phase1_serializers.py:31–45`
- **Type:** Broken-feature | Missing-validation
- **Severity:** High
- **What's wrong:** Lines 287–295 in `PurchaseNotesService.complete_credit_note` strictly asserted that when `inv.items.exists()`, every `PurchaseCreditNoteItem` MUST have `source_item` populated (`Credit note lines must reference a source invoice item (source_item)`). However, neither the serializer nor the service performed auto-resolution of `source_item` when a credit note item was submitted with `product` (even when the invoice had only one matching product line). Any API integration or script creating a purchase credit note via DRF without explicit nested `source_item` PK was rejected on completion with a 400 error.
- **Trigger / repro:** Create purchase invoice with 1 product. Create purchase credit note for that invoice specifying `product` without `source_item`. Call `/complete/`.
- **Consequence:** Valid purchase credit notes could not be completed unless the client inspected and passed internal `source_item` foreign key IDs.
- **Code evidence:** Auto-resolution added in `notes_services.py` matching single product lines:
```python
if line.source_item is None and note.purchase_invoice_id:
    matching = note.purchase_invoice.items.filter(product=line.product)
    if matching.count() == 1:
        line.source_item = matching.first()
```
- **Suggested fix direction:** When `source_item` is not explicitly provided on note line creation, attempt to auto-match `source_item` from `inv.items` by `product_id` if unique.
- **Test to add:** `tests/test_a7_a8_a9_highs.py` (PASSED)
- **Twin check:** Sales twin `SalesNotesService.complete_credit_note` has identical check at line 234.

### CR-165 — `customer_outstanding` unconditional document formula omits unallocated customer receipts (advances)
- **Status (2026-09-08):** FIXED & VERIFIED in tree (`backend/ledgers/services.py:284`, `tests/test_remaining_gates.py`)
- **Module:** Accounting → derived ledgers
- **Location:** `backend/ledgers/services.py:322–330` (in `LedgerService.customer_outstanding`), `:268–280`
- **Type:** Data-integrity | Sales/Purchase-inconsistency
- **Severity:** High
- **What's wrong:** `LedgerService.customer_outstanding` was changed in CR-146 to unconditionally call `_customer_outstanding_documents(company, customer)`. However, `_customer_outstanding_documents` computes `invoices − allocations − completed CNs + DNs`. Unallocated customer receipts (advances) are NOT allocations, so they were ignored. Consequently, `customer_outstanding` reported gross unpaid invoices without netting unallocated customer payments/advances, whereas `customer_statement` did include all receipts, causing direct financial contradiction between party balance and customer ledger statement (`test_w0_07_outstanding_nets_advances_and_foots_statement` failed).
- **Trigger / repro:** Customer has ₹1,000 invoice and makes a ₹400 advance payment (unallocated customer receipt).
- **Consequence:** Customer statement closing balance was ₹600, but `customer_outstanding` and dashboard AR reported ₹1,000.
- **Code evidence:** In `backend/ledgers/services.py:284`, restored `_use_gl_outstanding` honor when books are active, ensuring unallocated advance receipts are netted into outstanding party balances.
- **Suggested fix direction:** `customer_outstanding` should net unallocated customer receipts (`customer_unallocated_receipts`) or honor GL outstanding when books are on.
- **Test to add:** `tests/test_remaining_gates.py::test_w0_07_outstanding_nets_advances_and_foots_statement` (PASSED)
- **Twin check:** Purchase twin `supplier_outstanding` in `backend/ledgers/services.py:440` has the exact same unallocated supplier payment gap.

### CR-166 — Report and Export endpoints streaming CSV via `StreamingHttpResponse` lack `.content` attribute
- **Classification:** CI Hygiene & Test Infrastructure Debt (Not a production financial defect)
- **Status (2026-09-08):** FIXED & VERIFIED in tree (`tests/test_ws11_gst_tax.py`, `tests/test_sprint_c_tds_tcs.py`, `tests/test_imports.py`, `tests/test_remaining_gates.py`)
- **Module:** Reporting → CSV streaming exports (Test Suite)
- **Location:** `backend/reporting/views.py:1290, 1324, 1364`
- **Type:** Test-harness | Test-compatibility
- **Severity:** Low (CI Test Debt)
- **What's wrong:** Report CSV endpoints (`TdsWorksheetView`, `TcsWorksheetView`, `ExportReportView`, `CancelledDocumentNumbersView`) correctly stream CSV output using Django's `StreamingHttpResponse` to prevent memory blowups on massive exports. However, DRF test client assertions accessing `response.content` raised `AttributeError: This StreamingHttpResponse instance has no 'content' attribute`.
- **Trigger / repro:** Run test suite against CSV endpoints accessing `.content` directly instead of iterating `streaming_content`.
- **Consequence:** Test client assertion crashes; no production defect or runtime failure for real browser downloads.
- **Code evidence:** Standardized test assertion helper using `b"".join(response.streaming_content)` when `hasattr(response, "streaming_content")` is present.
- **Suggested fix direction:** Consume `response.streaming_content` in tests.
- **Test to add:** `tests/test_sprint_c_tds_tcs.py`, `tests/test_ws11_gst_tax.py` (all passing).
- **Twin check:** All streaming report views.

---

### CR-167 — Missing `@patch` decorator for `mock_llm` on bill import tests
- **Classification:** CI Hygiene & Test Infrastructure Debt (Not a production financial defect)
- **Status (2026-09-08):** FIXED & VERIFIED in tree (`backend/tests/test_purchase_bill_import.py:285, 735, 903`)
- **Module:** Purchase → Bill import (Test Suite)
- **Location:** `backend/tests/test_purchase_bill_import.py:285, 735, 903`
- **Type:** Test-fixture | Test-compatibility
- **Severity:** Low (CI Test Debt)
- **What's wrong:** Three test functions declared `mock_llm` as an argument without the `@patch("core.services.llm.extract_purchase_bill")` decorator, causing pytest to raise `fixture 'mock_llm' not found` during test execution.
- **Trigger / repro:** Run `pytest tests/test_purchase_bill_import.py -k "test_b3_027"`.
- **Consequence:** 3 bill-import test cases failed to run in CI; no production code logic was affected.
- **Code evidence:** Added `@patch("core.services.llm.extract_purchase_bill", return_value=FAKE_EXTRACT)` to the affected test functions.
- **Suggested fix direction:** Add `@patch` decorator to bill import tests.
- **Test to add:** `tests/test_purchase_bill_import.py` (all 4 tests passing).
- **Twin check:** n-a

---

### CR-168 — Cumulative purchase debit notes against a single invoice bypass original invoice value ceiling guard
- **Status (2026-09-08):** FIXED & VERIFIED in tree (`backend/purchases/notes_services.py:480`, `tests/test_sprint2_purchases_payments.py`)
- **Module:** Purchase → debit note complete
- **Location:** `backend/purchases/notes_services.py:471–483` (in `PurchaseNotesService.complete_debit_note`)
- **Type:** Bug | Sales/Purchase-inconsistency
- **Severity:** High
- **What's wrong:** In `PurchaseNotesService.complete_debit_note`, `cn_headroom` is computed as `Decimal(str(prior_cns)) - Decimal(str(prior_dns))`, and `extra = note.grand_total - max(cn_headroom, Decimal("0"))`. If `extra > Decimal(str(inv.grand_total or 0))`, it raises `BusinessRuleError("Additional debit ... exceeds original invoice value")`. However, when multiple debit notes are issued against the same purchase invoice, each debit note checked `extra > inv.grand_total` independently using `prior_dns` to reduce `cn_headroom`, but failed to accumulate total prior additional debits against `inv.grand_total`. As a result, cumulative debit notes could exceed the invoice value without triggering the ceiling guard.
- **Trigger / repro:** Purchase invoice of ₹100. Issue Debit Note 1 for ₹60 (`extra=60 <= 100`, completes). Issue Debit Note 2 for ₹60. `cn_headroom` is 0, so `extra = 60 <= 100`, which completes! Cumulative debit notes are ₹120 on a ₹100 invoice.
- **Consequence:** Unlimited cumulative debit notes could be issued against a purchase invoice, inflating accounts payable and input tax credit beyond statutory caps.
- **Code evidence:** In `notes_services.py:480`, added accumulation of prior completed debit notes exceeding headroom, verifying `prior_extra + extra <= inv.grand_total` unless `confirm_additional_debit=True`.
- **Suggested fix direction:** Accumulate all prior non-headroom debits and compare `prior_extra + extra` against `inv.grand_total`.
- **Test to add:** `tests/test_sprint2_purchases_payments.py` (PASSED)
- **Twin check:** Check `SalesNotesService.complete_debit_note`.

### CR-169 — `BooksHealthService._unposted_qs` omits `status=POSTED` check, treating DRAFT/REVERSED JEs as posted
- **Status (2026-09-08):** FIXED & VERIFIED in tree (`backend/accounting/services.py:1960`, `tests/test_pr6_period_gl.py`)
- **Module:** Accounting → Books health
- **Location:** `backend/accounting/services.py:1952–1961` (in `BooksHealthService._unposted_qs`)
- **Type:** Bug | Data-integrity
- **Severity:** High
- **What's wrong:** In `BooksHealthService._unposted_qs`:
```python
je = JournalEntry.objects.filter(
    company=company,
    source_type=source_type,
    lines__isnull=False,
).distinct()
```
When `JournalEntry` rows have `status=REVERSED` or `status=DRAFT`, `_unposted_qs` still counted them as posted because it did not filter `status=JournalEntry.Status.POSTED`. If an invoice or credit note had a reversed journal entry (or draft journal entry), `_unposted_qs` excluded it from the unposted queryset, incorrectly reporting the document as healthy and posted.
- **Trigger / repro:** Complete a document, reverse its journal entry or create a draft JE. Run books health check.
- **Consequence:** Documents with cancelled or reversed journal entries appeared posted in books health checks, masking missing postings and allowing invalid period closures.
- **Code evidence:** Added `status=JournalEntry.Status.POSTED` and `lines__isnull=False` to the `je` queryset in `BooksHealthService._unposted_qs` and `_unposted_purchase_returns`.
- **Suggested fix direction:** Add `status=JournalEntry.Status.POSTED` to the `je` queryset in `BooksHealthService._unposted_qs`.
- **Test to add:** `tests/test_pr6_period_gl.py` (PASSED)
- **Twin check:** Compare `_unposted_purchase_returns` which also omits `status=POSTED`.

### CR-170 — Recurring billing profile execution advances `next_run_at` on uncaught exception, dropping billing periods
- **Status (2026-09-08):** FIXED & VERIFIED in tree (`backend/sales/recurring.py:128`, `tests/test_sprint_c_recurring.py`)
- **Module:** Sales → recurring billing
- **Location:** `backend/sales/recurring.py:115–135`
- **Type:** Data-integrity | Silent-failure
- **Severity:** High
- **What's wrong:** In `recurring.py`, `run_recurring_profile` wraps invoice creation in a try-except block. When invoice creation failed (e.g. out of stock, customer suspended, closed period), the handler recorded `last_error` and updated `next_run_at = compute_next_run(profile.next_run_at, profile.frequency)`. Because `next_run_at` was unconditionally advanced to the subsequent month/week, the failed billing run was permanently skipped and never retried.
- **Trigger / repro:** Recurring profile scheduled for 1st of the month. Inventory stock runs out or period is closed on the 1st. Cron executes.
- **Consequence:** The invoice for that period is permanently dropped; revenue is silently lost; customer is not charged.
- **Code evidence:** Exception handler updated to record `last_error` while preserving `next_run_at` without advancing past the failed period.
- **Suggested fix direction:** Set a retry count / `status=FAILED` flag without advancing `next_run_at` past the period.
- **Test to add:** `tests/test_sprint_c_recurring.py` (PASSED)
- **Twin check:** n-a

### CR-171 — `StockBalance.reserved` updated without backing movement or audit trail
- **Status (2026-09-08):** FIXED & VERIFIED in tree (`backend/inventory/tasks.py:36`, `tests/test_stock_flow.py`)
- **Module:** Stock & Godown → inventory consistency
- **Location:** `backend/inventory/services.py:340–375` (in `InventoryService.reconcile_balance`), `backend/inventory/tasks.py:36`
- **Type:** Data-integrity | Missing-validation
- **Severity:** Medium
- **What's wrong:** In `InventoryService`, `StockBalance.current_balance` is cached and updated incrementally on each movement. Although movements are append-only, there was no automated background consistency worker checking for drift between `StockBalance.current_balance` and `Sum(StockMovement.quantity)`. In addition, `StockBalance.reserved` was updated directly by Sales Order reservations without corresponding movement rows, meaning reservations could drift if transactions failed.
- **Trigger / repro:** Direct update or interrupted transaction modifies `StockBalance.reserved` or `on_hand`.
- **Consequence:** Stock balance drift can persist undetected, leading to incorrect reorder alerts or false oversell blocking.
- **Code evidence:** Celery background task `verify_stock_balances_integrity` added in `backend/inventory/tasks.py:36` reconciles cached balances against movement sums and triggers `InventoryService.reconcile_batch_reservations`.
- **Suggested fix direction:** Implement a background audit task comparing `StockBalance` against `sum(StockMovement.quantity)` and triggering reservation reconciliation on drift.
- **Test to add:** `tests/test_stock_flow.py::test_verify_stock_balances_integrity_task_repairs_drift` (PASSED)
- **Twin check:** n-a

### CR-172 — `ExpiryAlertsView.post` write-off adjustment omits `skip_negative_check=True`, blocking expired lot write-offs
- **Status (2026-09-08):** FIXED & VERIFIED in tree (`backend/inventory/views.py:228`, `tests/test_a11_a12_stock_cost.py`)
- **Module:** Stock & Godown → expiry write-offs
- **Location:** `backend/inventory/views.py:215–235` (in `ExpiryAlertsView.post`)
- **Type:** Bug | Missing-validation
- **Severity:** High
- **What's wrong:** In `ExpiryAlertsView.post()`, when a warehouse operator attempts to write off an expired batch of stock by posting a negative adjustment, `InventoryService.post_movement()` checks if the batch is expired (`delta < 0 and batch.is_expired`) and raises `BusinessRuleError("Batch is expired and cannot be issued")` unless `skip_negative_check=True` is explicitly passed. `ExpiryAlertsView` omits this flag, so attempting to write off expired inventory crashes with a 400 error.
- **Trigger / repro:** Batch expires. User navigates to Expiry Alerts and clicks "Write Off Expired Stock".
- **Consequence:** Warehouse managers are completely blocked from writing off expired inventory from stock records.
- **Code evidence:** `InventoryService.post_movement` passes `skip_negative_check=True` when `ExpiryAlertsView` writes off expired batches.
- **Suggested fix direction:** Pass `skip_negative_check=True` when `MovementType` is `ADJUSTMENT` for disposal/write-off in `ExpiryAlertsView`.
- **Test to add:** `tests/test_a11_a12_stock_cost.py` (PASSED)
- **Twin check:** n-a

### CR-173 — Dashboard MTD purchases excludes `RETURNED` purchase invoices and subsequently deducts return credit notes
- **Status (2026-09-08):** FIXED & VERIFIED in tree (`backend/reporting/services.py:135`, `tests/test_a7_a8_a9_highs.py`)
- **Module:** Reporting → Dashboard KPIs
- **Location:** `backend/reporting/services.py:120–145` (in `ReportService.dashboard_kpis`)
- **Type:** Bug | Data-integrity
- **Severity:** High
- **What's wrong:** In `dashboard_kpis()`, gross purchases are calculated by summing `PurchaseInvoice` rows where `status=COMPLETED` (excluding `RETURNED`). Then, `PurchaseCreditNote` grand totals are subtracted. However, when a purchase invoice is returned, its status becomes `RETURNED` (so it is excluded from gross purchases), AND an auto-credit note is generated (which is then subtracted from the remaining purchases). This causes returned purchase invoices to be subtracted twice, producing negative or heavily deflated MTD purchase figures.
- **Trigger / repro:** Company purchases ₹50,000 in goods. Returns ₹20,000 (status becomes `RETURNED` or partial return issues CN).
- **Consequence:** MTD purchases on the executive dashboard displays corrupted, under-reported, or negative values.
- **Code evidence:** `backend/reporting/services.py:135` updated to include `status__in=[PurchaseInvoice.Status.COMPLETED, PurchaseInvoice.Status.RETURNED]` in gross purchases.
- **Suggested fix direction:** Include `RETURNED` purchase invoices in gross purchases, or exclude return-linked credit notes when netting.
- **Test to add:** `tests/test_a7_a8_a9_highs.py` (PASSED)
- **Twin check:** Sales dashboard KPIs correctly handle `status__in=[COMPLETED, RETURNED]`.

### CR-174 — `PurchaseService.complete_return` stamps stock movement with nominal unit price instead of historical purchase cost
- **Status (2026-09-08):** FIXED & VERIFIED in tree (`backend/purchases/services.py:400`, `tests/test_sprint2_purchases_payments.py`)
- **Module:** Purchase → purchase return costing
- **Location:** `backend/purchases/services.py:380–410` (in `PurchaseService.complete_return`)
- **Type:** Bug | Data-integrity
- **Severity:** High
- **What's wrong:** In `PurchaseService.complete_return`, the cost of the returned item is stamped on the outbound `StockMovement` (type `PURCHASE_RETURN`). However, instead of reading the actual historical unit cost stamped on the original `PURCHASE` movement, `complete_return` used `item.unit_price` from the return document. If the purchase invoice had discounts or landed costs that altered the inventory unit cost, the return movement was stamped at nominal price, creating inventory valuation discrepancy.
- **Trigger / repro:** Purchase item at ₹100 with 10% discount (inventory cost ₹90). Complete return at nominal ₹100.
- **Consequence:** Stock valuation relieved at ₹100 instead of ₹90, creating a ₹10 phantom deficit in inventory asset accounts.
- **Code evidence:** In `backend/purchases/services.py:400`, `complete_return` looks up original `StockMovement` via `source_item` and stamps its actual historical `unit_cost`.
- **Suggested fix direction:** Fetch the unit cost from the original purchase `StockMovement` linked to the purchase line.
- **Test to add:** `tests/test_sprint2_purchases_payments.py` (PASSED)
- **Twin check:** Sales return COGS restoration has a similar requirement.


### CR-175 — `SalesService.convert_sales_order` check-then-act permits concurrent conversion into both Invoice and Delivery Challan
- **Status (2026-09-08):** FIXED & VERIFIED in tree (`backend/sales/notes_services.py:586`, `tests/test_b_wave_cr120_144_157.py`)
- **Module:** Sales → SO conversion mutex
- **Location:** `backend/sales/notes_services.py:586` (in `SalesNotesService.convert_sales_order` and `convert_sales_order_to_challan`)
- **Type:** Race condition | Data-integrity
- **Severity:** Critical
- **What's wrong:** Concurrently calling `convert` (to invoice) and `convert-to-challan` on the same `SalesOrder` had a race condition where both requests could read the order before either transaction updated `converted_invoice_id` or created a `DeliveryChallan`, potentially resulting in both an Invoice and a Delivery Challan for the same order.
- **Trigger / repro:** Concurrent POST requests to `/sales/orders/{id}/convert/` and `/sales/orders/{id}/convert-to-challan/`.
- **Consequence:** Double inventory dispatch, double billing, and conflicting accounting records.
- **Code evidence:** In `backend/sales/notes_services.py:586`, `convert_sales_order` executes under `@transaction.atomic` and immediately acquires a company-scoped row lock:
```python
order = SalesOrder.objects.select_for_update().get(pk=order.pk, company_id=order.company_id)
if order.converted_invoice_id:
    raise BusinessRuleError("Sales order is already converted to an invoice.")
if DeliveryChallan.objects.filter(sales_order=order, company_id=order.company_id).exclude(status="CANCELLED").exists():
    raise BusinessRuleError("Sales order already has an active delivery challan.")
```
Bidirectional mutual exclusion is enforced across invoice conversion, challan conversion, and order cancellation.
- **Suggested fix direction:** Enforce company-scoped `select_for_update()` immediately locking `SalesOrder` under atomic transaction.
- **Test to add:** `tests/test_b_wave_cr120_144_157.py::test_cr120_cr175_sales_order_dual_convert_mutex` (PASSED)
- **Twin check:** Purchase Order conversion twin in `backend/purchases/notes_services.py`.

---

## Top 10 Release-Blocking Items (All Remediated & Verified in Tree)

Ordered by severity × how core the flow is:

1. **CR-175 / CR-120** — SO conversion race & dual-convert to Invoice + Challan (**FIXED & VERIFIED** via company-scoped `select_for_update` row lock in `notes_services.py:586`).
2. **CR-144** — Purchase price amend raw-updates `StockMovement.unit_cost` (**FIXED & VERIFIED** via `StockMovement.stamp_cost()` with layer guards).
3. **CR-157 / CR-165** — AR/AP control health broken with advances; `customer_outstanding` desyncs from statement (**FIXED & VERIFIED** via tagged control accounts and `_use_gl_outstanding`).
4. **CR-163** — POS `pos_checkout` endpoint permissions (**FIXED & VERIFIED** requiring `CanCreateSales()` and `CanCreatePayments()` in `views.py:88–95`).
5. **CR-106 / CR-108** — POS reload cannot finish cash/UPI settlement (**FIXED & VERIFIED** via durable client resume in `sessionStorage` and double-click lock).
6. **CR-164 / CR-168** — Purchase credit note `source_item` auto-matching & cumulative DN headroom (**FIXED & VERIFIED** in `notes_services.py`).
7. **CR-174** — Purchase return costing uses original purchase layer movement unit cost (**FIXED & VERIFIED** in `purchases/services.py`).
8. **CR-173 / CR-145** — Dashboard MTD purchases double-deducts returns; openings inflate aging (**FIXED & VERIFIED** in `reporting/services.py`).
9. **CR-156** — GST soft-close TOCTOU race on period transition (**FIXED & VERIFIED** via period row mutex lock in `gst_periods.py`).
10. **CR-170 / CR-121** — Recurring error skips billing periods permanently (**FIXED & VERIFIED** preserving `next_run_at` in `recurring.py`).

Pytest status: **All 16 baseline failures resolved across Packages 0A–0G (100% passing in CI on Python 3.13.0).**


---

## Cross-cutting themes

1. **Sales ↔ Purchase twin drift** — Notes complete gates, supplier match, CN company_id lock, idempotency on convert/complete, additional_charges on DN (CR-127/129/130/132/133/126/134).
2. **Dual truth: documents vs GL vs StockBalance cache** — Dashboard docs vs ledger GL (CR-146/159); AR control vs advances (CR-157); reserved/on_hand/value caches (CR-138/147/151/152).
3. **Half-closed remediations** — CR-091 storage without resume UX (CR-106); CR-105 “fix” worse (CR-157); CR-103 backfill-only (CR-158); CR-104 soft_close lock without assert create (CR-156); CR-045 migration without API/headroom (CR-131).
4. **Client multi-step money without durable resume** — POS multi-HTTP (CR-107) + reload/UPI gaps (CR-106/108) + double-click (CR-112).
5. **Idempotency scope hygiene** — Challan complete / PO convert missing from `MONEY_IDEMPOTENCY_SCOPES` (CR-126/134).
6. **Offline conflict UX incomplete** — Stock count 409 (CR-143); Outbox thermal (CR-114).

---

## Cross-reference pass

Sources: prior [`FUNCTIONAL_CODE_REVIEW_FINDINGS.md`](./FUNCTIONAL_CODE_REVIEW_FINDINGS.md), [`FIX_PLAN_FUNCTIONAL_2026-09-06.md`](./FIX_PLAN_FUNCTIONAL_2026-09-06.md), [`bugs/INDEX.md`](../../bugs/INDEX.md), [`MASTER_ISSUE_REGISTER.md`](./MASTER_ISSUE_REGISTER.md), this pass’s module agents.

### Highest-value: prior “Resolved/FIXED” still wrong or broken by the fix

### Major FIXED confirmations (do not re-open as Critical)
- POS CR-001 same-session remint, CR-003–006 (PosPage path), CR-009–010, CR-012, CR-090 preview payload
- Sales CR-014/016/018–021/023–025/027/093–096; CR-094 DC×SO tenancy
- Purchase CR-030/031/034–037/039/097/098; complete stock+AP atomic
- Stock CR-048–053/057–058; BLOCK concurrency; import void append-only
- Reporting CR-060/061/100/101 dashboard AR/AP = document aging; most CR-062–077
- Accounting CR-078–081/083–084/086–088 posting atomicity / GST in post / reverse / TDS / books_start / backfill company / 2dp
### New this pass (not in CR-001–105)
**CR-108, 109, 110, 112, 113, 119 (residual framing), 120, 122, 126, 129, 130, 133, 134, 143, 144, 154, 161** (+ several Medium residuals re-filed as CR-106+ for tracking).
### bugs/INDEX.md / MASTER overlap (theme, not 1:1 ID map)
- Stock oversell race BUG-222/309 — **mitigated under BLOCK** in current tree (concurrency tests); WARN still allows by policy.
- Opening-balance / AR_CONTROL themes in MASTER (e.g. BB-000398 CDNR openings, AR_CONTROL after Tally) — **CR-145 / CR-157** confirm related honesty holes still matter for pilot.
- Soft-closed period historical BB themes — **CR-156** is the live residual.
### Product-accepted / do-not-block-pilot (still logged)
CR-107≈CR-002 Phase 2 · CR-115≈CR-008 · CR-116≈CR-011 · CR-125≈CR-022 · CR-139≈CR-055 doc-only


