# POS Module Audit, Issue Log & Remediation Blueprint

**Document Version:** 1.1  
**Scope:** `web/src/pages/pos/*`, `web/src/offline/flushPosCheckout.ts`, `backend/sales/views.py` (`pos_checkout`), `backend/accounting/cash_shifts.py`, `backend/sales/pdf/thermal_receipt.py`  
**Generated On:** 2026-10-06  
**Revised On:** 2026-10-06  
**Revision:** Checked each issue against the current code. Version 1.0 marked all 11 open and proposed fixes that duplicate or contradict what is already built.

---

## Executive Summary

Four issues are confirmed as written. Four are real gaps whose version 1.0 fix is the wrong change. Three blueprints should not be built.

| Verdict | Issues |
|---|---|
| Confirmed | POS-001, POS-003, POS-005, POS-007 |
| Real gap, wrong fix | POS-002, POS-004, POS-006, POS-008 |
| Do not build | POS-009, POS-010, and the version 1.0 model for POS-002 |

POS-011 stays a later layout pass. It was not measured.

### Issue Summary Matrix

| Issue ID | Priority | Title | Verdict | Status |
|---|---|---|---|---|
| **ISSUE-POS-001** | **P0** | Stock gate sums every godown | Confirmed | Open |
| **ISSUE-POS-002** | **P1** | Till exists; POS does not use it | Wrong fix in v1.0 | Open (UI only) |
| **ISSUE-POS-003** | **P1** | Offline flush drops the chosen batch | Confirmed | Open |
| **ISSUE-POS-004** | **P2** | Typed names create separate customers | Partial | Open, narrowed |
| **ISSUE-POS-005** | **P1** | Offline receipt is always cash | Confirmed | Open |
| **ISSUE-POS-006** | **P2** | ESC/POS bytes are a stub; PDF receipt is not | Partial | Open, narrowed |
| **ISSUE-POS-007** | **P2** | Two hold mechanisms | Confirmed | Open |
| **ISSUE-POS-008** | **P2** | Several lots are not pre-selected | Partial | Open, narrowed |
| **ISSUE-POS-009** | — | Poll a UPI intent | Do not build | Closed as specified |
| **ISSUE-POS-010** | — | Sales staff cannot check out | Do not build | Closed as specified |
| **ISSUE-POS-011** | **P3** | Tender panel height | Unmeasured | Later |

Version 1.0 linked warehouse scoping to the offline batch fix, and the till to a new cashier role. Those links are dropped. Wave 1 is three independent correctness fixes.

---

## Detailed Issue Logs

### ISSUE-POS-001: Stock gate sums every godown

- **Priority:** P0
- **Verdict:** Confirmed
- **Where:** `availableByProduct` and `posStockBlocked` in `web/src/pages/pos/PosPage.tsx`. The cart caption uses `pos.warehouseQtyBlock` (“In this godown: {n}”) with that same total.
- **What is wrong:** Balances are added across every warehouse. The selected godown is ignored. A product with 0 in godown A and 25 in godown B shows 25, Pay stays enabled, and the server then rejects the sale against godown A.
- **Related fact:** `availablePosBatches` already filters by `warehouseId`. The batch dropdown and the stock gate do not use the same scope.
- **Do:** Filter `stockBalances` by `warehouseId` before the map, the search label, the caption, and `posStockBlocked`. If no godown is selected yet, treat available as 0 rather than the company total.
- **Do not:** Change the server negative-stock check. It is already warehouse-scoped.
- **Check:** Two godowns, stock only in the other one. This godown shows 0 and Pay is blocked while the company policy is `BLOCK`.

### ISSUE-POS-002: Till exists; the counter does not use it

- **Priority:** P1 (was P0 “absence”)
- **Verdict:** Version 1.0 is wrong. Do not create a new model.
- **What already exists:**
  - `CashShiftRegister` in `backend/accounting/models.py`: cashier, business date, opening float, denominations, expected cash, counted cash, variance, `OPEN` / `CLOSED`, `locked_at`.
  - One row per company, cashier, and business date (`uniq_cash_shift_per_cashier_day`).
  - `backend/accounting/cash_shifts.py`: Indian note and coin counts, expected cash = opening float + that cashier’s cash receipts − that cashier’s cash supplier payments.
  - API: `POST /api/v1/accounting/cash-shifts/`, `POST .../close/`. Covered by `test_bug_acc_001_cash_shift_close_is_per_cashier`.
- **What is actually missing:**
  - No POS screen to open or close the till.
  - No cash-drop movement.
  - Close stores variance. It does not post a journal.
  - `CashShiftRegisterViewSet` uses `AccountingEnabledMixin`, so a company with accounting off cannot use it.
  - Create and close need `CanCreatePayments`. List needs `CanViewFinancialReports`. Sales staff have payments on and financial reports off, so they cannot list their own shift.
- **Do:**
  1. Add a cashier-readable “my open shift for today” read that does not require financial-report permission.
  2. On POS, if accounting is on and no shift is open, ask for the opening float.
  3. Add End shift: the existing denomination map, then `close`. Show expected, counted, and variance. Print the thermal PDF of that summary only after the PDF path is the one in use (see POS-006).
- **Do not:** Add a second `CashShiftRegister`, an `AUDITED` status, `terminal_id`, or a stored `cash_sales_total`. Expected cash is computed at close. Cash drops and a variance journal are a later slice, not this one.
- **Check:** Cashier opens a float, rings a cash sale, closes with a note count, and cannot close again. A second cashier’s cash receipts are not in the first cashier’s expected total (already asserted by `BUG-ACC-001`).

### ISSUE-POS-003: Offline flush drops the chosen batch

- **Priority:** P1
- **Verdict:** Confirmed. The failure mode in version 1.0 is wrong.
- **Where:** `draftLinesFromCart` in `PosPage.tsx` stores `batchNo`. `createCompletedInvoice` sends it. `flushPosDraft` in `web/src/offline/flushPosCheckout.ts` maps items and omits `batchNo`.
- **What actually happens:** `SalesService._sale_batches` does not raise “batch_no is required” when the number is blank. It allocates first-expired-first-out. A cashier who picked a later lot loses that choice on sync.
- **Do:** Include `batchNo` on each flush item the same way the online create does (`batchNo: line.batchNo` when present).
- **Do not:** Treat a missing batch as a hard error in the client. The server already has a FEFO fallback for lines that were never batch-tracked.
- **Check:** Queue a batch-tracked line whose chosen lot is not the earliest. After flush, the invoice line is that lot, not the earliest one.

### ISSUE-POS-004: Typed names and the walk-in customer

- **Priority:** P2 (was P1)
- **Verdict:** Partial. The version 1.0 search-by-name fix must not be built.
- **What the code does:** If a draft has no `customerId` and has `pendingCustomerName`, flush calls `createCustomer`, then `updateDraft` with that id before the invoice. A retry of the same draft does not create a second customer. A different draft with the same typed name does. The comment in `flushPosCheckout.ts` says that is deliberate: sharing an id across drafts that only share a name would merge different people into one ledger.
- **Do:** When the cashier did not type a name, bind the sale to the company’s single walk-in customer (create that party once if it is missing). Leave a typed name as its own customer.
- **Do not:** `listCustomers` by exact name, and do not use an idempotency key derived only from the name. That key is not company-scoped and would merge strangers.
- **Check:** Two offline drafts both typed “Ravi” become two customers. Two offline drafts with no typed name share the walk-in customer. Retrying one failed draft does not add a third party.

### ISSUE-POS-005: Offline receipt is always cash

- **Priority:** P1
- **Verdict:** Confirmed. The GL account numbers in version 1.0 are not this code’s posting map.
- **Where:** `flushPosDraft` sets `mode: 'CASH'` on `createReceipt`. `draft.paymentMode` is already on the outbox. UPI is refused before that (`UPI POS drafts must be finished on the POS screen while online`).
- **Impact:** Card, bank, cheque, and credit can be queued while offline and then posted as cash. Cheque number, bank, and date are not on the flush payload.
- **Do:** Pass `draft.paymentMode` for `CASH`, `CARD`, and `BANK`. If the mode is `CHEQUE` or `CREDIT`, leave the draft failed with a clear error until those fields are stored and sent. Keep the UPI refusal.
- **Do not:** Invent GL 1000 / GL 1050 in this change. Receipt posting already follows `PaymentMode`.
- **Check:** A queued card sale creates a card receipt. A queued cheque sale stays in the outbox and does not create a cash receipt.

### ISSUE-POS-006: ESC/POS stub versus the thermal PDF

- **Priority:** P2 (was P1)
- **Verdict:** Partial.
- **What is stubbed:** `printPosThermalOrWarn` in `web/src/pages/pos/printPosThermal.ts` builds `BizBoard\n{number}\n\n\n` plus a drawer kick and sends it to `printEscPos`.
- **What is not stubbed:** If native print does not return `native`, the same function downloads `thermal_pdf`. `backend/sales/pdf/thermal_receipt.py` already renders store name, GSTIN, phone, invoice, date, customer, item, SKU, HSN, MRP, discount, tax, and total for 58mm and 80mm.
- **Do not:** Add WebUSB or raw TCP inside the page. The counter already states that network print needs the desktop bridge. A browser cannot open a raw socket.
- **Do, if print quality on a Bluetooth printer is still required:** Format ESC/POS bytes only on the path where `printEscPos` returns `native`. Desktop Chrome keeps the thermal PDF.

### ISSUE-POS-007: Two ways to hold a bill

- **Priority:** P2
- **Verdict:** Confirmed
- **Where:** Bill tabs use in-memory `sessionStore` (`F8` / `F9`). Hold cart writes `sessionStorage` key `bb_pos_holds:{company}:{user}` and renders recall chips. The two stores do not see each other.
- **Do:** Keep the tabs. On load, move any `bb_pos_holds` rows into tabs, then stop writing that key. Allow a tab label. `F8` holds into a new tab. `F9` and Ctrl+1..9 switch tabs.
- **Do not:** Leave the Hold cart button in place “for a while” without a migration. Cashiers would still have two lists.

### ISSUE-POS-008: Pre-select the earliest lot

- **Priority:** P2
- **Verdict:** Partial. The dropdown stays.
- **What exists:** `availablePosBatches` in `web/src/pages/pos/posBatchExpiry.ts` returns in-stock lots for the selected godown, soonest expiry first. The line control is a dropdown of those lots. Auto-fill runs only when the list length is 1 (`addProduct` and the stock effect in `PosPage.tsx`).
- **Gap:** Two or more lots leave the line blank and block Pay until the cashier opens the list.
- **Do:** When the line has no batch yet and the list is non-empty, set `batchNo` to `lots[0]`. Keep the dropdown so the cashier can override.
- **Do not:** Go back to a free-text batch field. Do not auto-replace a batch the cashier already chose.

### ISSUE-POS-009: Do not poll the UPI QR

- **Verdict:** Do not build
- **Why:** `backend/payments/upi.py` builds an amount-locked `upi://pay` link from the company VPA. POS shows that QR and waits for “Payment received”. There is no gateway order id and no status endpoint for that link. Polling every 2.5 seconds cannot see the customer’s UPI app.
- **If this is revisited:** Integrate a collect API (Cashfree or PayU) that has a payment id and a webhook. Until then, keep the manual button. A confirm step before it posts the receipt is enough. Offline UPI is already refused.

### ISSUE-POS-010: Do not add a cashier role

- **Verdict:** Do not build
- **Why:** `pos_checkout` requires `CanCreateSales` and `CanCreatePayments`. `CompanyUser.capability_defaults_for_role` sets both true for `SALES_STAFF`. There is no `CASHIER` role and no `can_operate_pos` field. `CanCreatePayments` allows `OWNER` or `can_create_payments`.
- **If a user sees 403:** That user’s `can_create_payments` was turned off. Turn it back on. Do not add `CanOperatePosTerminal`.

### ISSUE-POS-011: Tender panel height

- **Priority:** P3
- **Verdict:** Unmeasured. Do this after wave 1.
- **Do:** Collapse CGST / SGST / IGST into one tax row. Keep Change and the primary Pay control visible without scrolling the pay buttons off a 768px-tall screen.
- **Do not:** Start the POS fix list here.

---

## Implementation order

Wave 1, 2, and 3 are independent. Do not block the batch flush on the godown filter, and do not block the till screen on POS-010.

### Wave 1 — correctness

| Issue | Change | Test |
|---|---|---|
| POS-001 | Scope on-hand and `posStockBlocked` to `warehouseId` | Other godown’s stock does not enable Pay |
| POS-003 | Send `batchNo` from `flushPosDraft` | Chosen later lot survives flush |
| POS-005 | Use `draft.paymentMode` for cash, card, and bank. Fail cheque and credit in the outbox | Card receipt is not cash. Cheque creates no receipt |

### Wave 2 — till on the counter

| Issue | Change | Test |
|---|---|---|
| POS-002 | Cashier can read today’s open shift. POS opens and closes the existing register | Second close is rejected. Other cashier’s cash is excluded. No new model |

### Wave 3 — counter speed

| Issue | Change | Test |
|---|---|---|
| POS-008 | Default `lots[0]`, dropdown remains | Two lots: earliest is selected; override sticks |
| POS-004 | Unnamed offline sales share the walk-in customer | Two typed “Ravi” drafts stay two customers |
| POS-007 | Tabs only; migrate `bb_pos_holds` | A held cart from the old strip appears as a tab |

### Wave 4 — only if still needed

| Issue | Change |
|---|---|
| POS-006 | ESC/POS body only when native print is connected. Desktop stays on the thermal PDF |
| POS-009 | Confirm before “Payment received”. No poll |
| POS-011 | Pin Pay and Change |
| POS-010 | No code |

### Explicitly out of this document

- A second cash-shift model, cash drops, and a variance journal.
- In-browser raw TCP or WebUSB.
- A gateway poll of `upi://pay`.
- A `CASHIER` role or `CanOperatePosTerminal`.
- Merging customers by typed name.
