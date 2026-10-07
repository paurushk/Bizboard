# POS fix plan

**Document version:** 1.6
**Revised:** 2026-10-07
**Screen verdict:** Waves 0–5 are in the product, including the leftovers that were still partial. POS-009 and POS-010 stay closed as things we will not build. Scores were not measured with cashiers.

This file is the remediation plan: what is wrong, what to change, what not to build, and how to roll it out. Scores and later product work are in [POS_Roadmap.md](POS_Roadmap.md). They are estimates, not measurements, and they are not part of Waves 0–5.

## Version history

| Version | Date | What changed |
|---|---|---|
| 1.0 | 2026-10-06 | First blueprint. Several proposed fixes contradicted code that already existed. |
| 1.1 | 2026-10-06 | Re-checked the original eleven issues. Closed POS-009 and POS-010. |
| 1.2 | 2026-10-07 | Added POS-012 through POS-027 from the product review. |
| 1.3 | 2026-10-07 | Added unmeasured scores and a “path to 10”. That mixed a roadmap into this plan and left every issue Open while the header implied the waves had been scored as if done. |
| 1.4 | 2026-10-07 | Document review. One verdict per issue. Wave 0. Fix interactions written out. Data remediation and rollout added. Scores moved to `POS_Roadmap.md`. |
| 1.5 | 2026-10-07 | Waves 0–5 implemented. Status column is Shipped. Historical cash mispost is a read-only report; it does not post corrections. |
| 1.6 | 2026-10-07 | Leftovers closed: recovery collections, native receipt bytes, till variance, server holds, last bills, below-cost PIN, drawer confirm, discount audit, exchange, closed period, and the GST split assertion. Scores stay unmeasured. |
| 1.7 | 2026-10-07 | Code review pass. Fixed: PIN lockout counted one wrong try up to three times and locked the whole company; PIN hash exposed in the company payload; PIN left in the page after one approval; refund replay keyed by company only; cash refund allowed with no open till; refund counted on every same-day shift; collect not idempotent; salesperson and counter-event shift not checked against the company; walk-in move did not lock; inactive products sent to the offline catalogue; catalogue and scale read used the wrong key names or partial lines; receipt image printed after the cut; bulk sync parked every failure as a permanent conflict and skipped customerless drafts; checkout callbacks missed dependencies (customer GSTIN, till, prescription file). |

## What this revision checked in code

The 1.4 review of the document was not a full re-audit. These four claims were read in the working tree on 2026-10-07. `main` HEAD at that read was `b84350eb6e28b041c18e9c4c69600b34aac8ddef`. The POS files are modified in the working tree, so that hash is the branch tip, not a commit that contains this plan.

| Claim | Result |
|---|---|
| Atomic checkout | On for every new counter sale. `isAtomicPosCheckoutEnabled` always returns true. Recovery of a bill that is already completed uses `POST /sales/pos/collect/`, which applies the mapped bank. It does not create a second invoice. |
| `flushPosDraft` | Cash by default, through atomic checkout, with batch and serials. The draft date is pinned. A non-cash draft is not converted to cash. Named credit flushes only when `pos_offline_credit` is on and the draft was accepted as credit. |
| Walk-in flag | `Customer.is_pos_walk_in`. The counter looks up that flag. A typed name is a separate customer. |
| Service / non-stock | Lines with type SERVICE or `track_inventory` false skip the stock gate. The server check is warehouse-scoped. |

## How to read the matrix

**Verdict**

| Verdict | Meaning |
|---|---|
| Confirmed | The gap is real and the fix in the log is the one to build. |
| Partial | The gap is real. An earlier proposed fix was too wide or wrong. Build only the narrowed fix. |
| Conditional | The gap exists only when a company setting or party data matches. |
| Do not build | Building it would be wrong. Status is Closed. |

**Status:** `Shipped` means the behaviour is in this working tree. POS-009 and POS-010 stay `Closed` because they must not be built. Scores are still unmeasured.

**Size** is a planning label (S/M/L), not an estimate from a team. **Owner** is unassigned until someone takes the issue.

**Priority versus wave.** P0 and P1 are Waves 0–2. A P2 sits in Wave 5 only when it does not change money, stock, or whether Pay starts a sale. POS-017, POS-018, POS-020, and POS-022 change Pay, so they are not “only if still needed”.

## Fix interactions

These three are specified here so the issue logs cannot be implemented in isolation.

### 1. Tender-to-account mapping (POS-012, POS-005, POS-030)

`post_receipt` debits a bank ledger only when `receipt.bank_account_id` is set. Otherwise it debits cash **1100**. POS sends no `bank_account`. Companies can have more than one bank account. “Use the company’s bank account” is not implementable until each non-cash mode has a chosen account.

- Add a company setting: one `BankAccount` id for each of UPI, CARD, BANK, and CHEQUE.
- Do not default to the first bank account.
- Until that mode has a saved account, its Pay button stays disabled and says which setting is missing.
- Cash always posts to 1100 and needs no bank.
- Credit (POS-012, POS-030) creates no receipt and needs no bank.
- **Offline:** queue **cash only**. Do not queue UPI, card, bank, cheque, or credit. The cashier cannot know, offline, whether the mapping will accept the tender at sync. Blocking at tender time is the rule. The 1.2 instruction to pass CARD and BANK through the outbox is withdrawn.

### 2. Discount mode and the on-screen total (POS-015, POS-020)

Sending a GSTIN bill discount as before-tax changes the tax. The tender still calculates after-tax (`calculateInvoiceTotals` with `AFTER_TAX`). Pay would then open the totals-mismatch dialog on a correct sale.

- The mode sent to the server and the mode used on the tender must be the same value, computed before the server preview.
- POS-020 (row amount omitting cess and inclusive extraction) is the same family. Fix it in the same change, not in a later layout pass.

### 3. Credit limit and a short tender (POS-013)

“The payment covers the invoice” is only the full-pay case. A short tender is a part payment. The check is exposure **after** the receipt this request will post:

- Full pay: this invoice does not increase exposure.
- Short pay: exposure increases by `grand_total - receipt_amount`.
- Credit (no receipt): exposure increases by `grand_total`.

The collection hold (`stop_credit` / `overdue_severe` when `auto_credit_hold_on_severe_overdue` is on) is **not** bypassed by cash. A customer on hold cannot be billed on this screen until the hold is lifted. Say that in the error. Do not hide it inside the “covered by payment” branch.

## Summary matrix

| ID | Pri | Title | Verdict | Wave | Status | Size | Owner |
|---|---|---|---|---|---|---|---|
| POS-037 | P0 | Atomic checkout may be off, so two pay paths exist | Confirmed | 0 | Shipped | S | Unassigned |
| POS-036 | P1 | Walk-in is a name regex, not a flag | Confirmed | 0 | Shipped | S | Unassigned |
| POS-001 | P0 | Stock gate sums every godown | Confirmed | 1 | Shipped | M | Unassigned |
| POS-012 | P0 | Non-cash tenders debit cash 1100 | Confirmed | 1 | Shipped | L | Unassigned |
| POS-030 | P1 | Credit to the walk-in party is uncollectable | Confirmed | 1 | Shipped | S | Unassigned |
| POS-018 | P1 | F5 starts a UPI sale | Confirmed | 1 | Shipped | S | Unassigned |
| POS-031 | P1 | Offline flush is not atomic | Confirmed | 1 | Shipped | M | Unassigned |
| POS-003 | P1 | Offline flush drops the chosen batch | Confirmed | 1 | Shipped | S | Unassigned |
| POS-005 | P1 | Offline queue accepts tenders that cannot sync | Confirmed | 1 | Shipped | M | Unassigned |
| POS-032 | P1 | Two terminals and the last unit | Needs a Postgres test | 1 | Shipped | S | Unassigned |
| POS-013 | P1 | Credit limit ignores the receipt about to be posted | Confirmed | 2 | Shipped | M | Unassigned |
| POS-014 | P1 | Same SKU always merges onto one line | Confirmed | 2 | Shipped | S | Unassigned |
| POS-015 | P1 | GSTIN bill discount fails, or disagrees with the tender | Confirmed | 2 | Shipped | M | Unassigned |
| POS-020 | P2 | Row amount can disagree with the tender | Confirmed | 2 | Shipped | S | Unassigned |
| POS-016 | P1 | Customer list is the first 100, with no search | Confirmed | 2 | Shipped | M | Unassigned |
| POS-023 | P1 | Required UTR is never asked | Conditional | 2 | Shipped | S | Unassigned |
| POS-028 | P1 | Credit sale is due today | Confirmed | 2 | Shipped | S | Unassigned |
| POS-017 | P2 | Cheque submits before its fields are usable | Confirmed | 2 | Shipped | S | Unassigned |
| POS-022 | P2 | Below-cost override requires the owner’s session | Confirmed | 2 | Shipped | M | Unassigned |
| POS-002 | P1 | Till exists; the counter does not use it | Partial | 3 | Shipped | L | Unassigned |
| POS-008 | P2 | Several lots are not pre-selected | Partial | 4 | Shipped | S | Unassigned |
| POS-004 | P2 | Unnamed offline sales should share one walk-in | Partial | 4 | Shipped | S | Unassigned |
| POS-007 | P2 | Two hold mechanisms | Confirmed | 4 | Shipped | M | Unassigned |
| POS-021 | P2 | Blank place of supply stops ordinary walk-in sales | Conditional | 4 | Shipped | S | Unassigned |
| POS-029 | P2 | Expired lots can still be sold | Confirmed | 4 | Shipped | M | Unassigned |
| POS-033 | P2 | Offline sale has no customer slip and must not invent an invoice number | Confirmed | 4 | Shipped | S | Unassigned |
| POS-035 | P2 | Any cashier can discount a line to zero | Confirmed | 4 | Shipped | M | Unassigned |
| POS-006 | P2 | Native thermal print is a stub | Partial | 5 | Shipped | M | Unassigned |
| POS-009 | — | Poll the UPI QR | Do not build | — | Closed | — | — |
| POS-010 | — | Add a cashier role | Do not build | — | Closed | — | — |
| POS-011 | P3 | Tender height, tax rows, repeated SKU | Confirmed | 5 | Shipped | S | Unassigned |
| POS-019 | P2 | Scale weight is discarded | Confirmed | 5 | Shipped | S | Unassigned |
| POS-024 | P3 | Offline split uses the UPI message | Confirmed | 5 | Shipped | S | Unassigned |
| POS-025 | P3 | Every customer phone is on the counter | Confirmed | 5 | Shipped | S | Unassigned |
| POS-026 | P3 | Drawer opens with no extra confirm | Confirmed | 5 | Shipped | S | Unassigned |
| POS-027 | P3 | Custom-field filter sits on the scan row | Confirmed | 5 | Shipped | S | Unassigned |
| POS-034 | P2 | Discounts, drawer opens, and UPI “received” are not audited | Confirmed | 5 | Shipped | M | Unassigned |

The first three to build, in order: **POS-037** (one pay path), **POS-001** (stock the godown will issue), **POS-012 with POS-030, POS-005, POS-031, and POS-003** (tender and lot match the books, including after reconnect). POS-016 is P1 and stays in Wave 2. It is not bundled with the P2 speed items.

## Data remediation (POS-012 already happened)

The code change stops new non-cash receipts from debiting 1100. It does not repair receipts already posted.

**Detect, read-only, before any correcting entry.** Receipts whose mode is not `CASH`, whose `bank_account_id` is null, and whose `CUSTOMER_RECEIPT` / `CREATE` journal debits account 1100. Separately, receipts whose mode is `CREDIT` and which are allocated to a sales invoice created from POS: those customers’ ageing is too low if the sale was meant to stay unpaid.

**Correct only with an accountant, after POS-012 is live** so the same error is not posted again.

- Non-cash that debited 1100: a reclass journal, debit the mapped bank ledger, credit 1100, memo pointing at the receipt. Do not edit the posted receipt journal in place.
- CREDIT that should have stayed unpaid: reverse that receipt and its allocation so the invoice is outstanding again. Do this per customer, not as a silent bulk update. Some CREDIT rows may have been intentional settlement instruments; the accountant decides.

**Rollback of a correction** is a reversing journal, not a restore of the 1100 debit as the new normal.

There is no detection query committed in this repo yet. The first task under POS-012 is to add that read-only report and have finance review a sample before any journal is posted.

## Rollout

POS-012 changes live books. Ship in this order.

1. **Wave 0.** Confirm atomic checkout is on in the target build (POS-037). Add the walk-in flag (POS-036). No change to posting.
2. **Export** the detection set above. No correcting journals yet.
3. **POS-001 and POS-018.** Stock and the F5 key. No ledger change. Safe to ship on their own.
4. **Mapping required.** Company setting for UPI, card, bank, and cheque accounts. While a mode has no account, that Pay button is off. Cash keeps working. Do not add a flag whose “off” position posts non-cash to 1100 again.
5. **POS-012, POS-030, POS-005, POS-031, POS-003** together. One pay path, cash-only offline queue, atomic flush, batch kept.
6. **Correcting journals** from the export, accountant-signed.
7. Waves 2–5.

**Rollback.** Disable the non-cash buttons (mapping setting empty). Do not roll the posting code back to “no bank account means 1100”. Open offline cash drafts can still flush. Queued non-cash drafts must not exist after step 5; if any remain from older builds, fail them in the outbox with an explicit error and do not convert them to cash.

## Test plan

Each issue log has a Check. This is where those checks live. Owner of the suite is unassigned.

| Area | File | Run |
|---|---|---|
| Checkout payload, discount mode, batch on the online body | `web/src/pages/pos/posCheckoutPayload.test.ts` | Unit, with the frontend suite |
| Offline flush mode, batch, no second receipt on retry | `web/src/offline/flushPosCheckout.test.ts` | Unit |
| F5 does not call checkout | `web/src/pages/pos/PosPage.hotkeys.test.tsx` | Unit |
| Totals mismatch and short collect | `backend/tests/workflows/test_wf_pos_totals_mismatch.py` | Django |
| Shift expected cash excludes the other cashier | `backend/tests/personas/test_pj_pos_shift_and_cash_reconciliation.py` | Django |
| Two checkouts of the last unit | **New** `backend/tests/test_pos_checkout_concurrency.py` | `pytest.mark.postgres` only, same marker as `backend/tests/test_concurrency_races.py`. Not part of the sqlite default run. |
| Pay blocked for stock, batch, serial | `web/e2e/pos/pos-complete-gates.spec.ts` | Playwright |
| GL debit account for each tender | **New** cases beside `backend/tests/snapshots/test_gl_posting_sets.py` or a POS posting test | Django |
| Godown scope on the client | **New** case beside `web/src/pages/pos/` stock helpers | Unit |

Wave 1 is not done until the Postgres concurrency test and the posting test exist and pass. A green default sqlite run does not cover POS-032.

## Wave 0 — one path, one walk-in

### POS-037: Atomic checkout may be off

- **Priority:** P0. **Verdict:** Confirmed. **Status:** Shipped.
- **Where:** `isAtomicPosCheckoutEnabled` in `web/src/config/features.ts`. `performCashCheckout` in `PosPage.tsx` uses `posCheckout` only when that returns true. Otherwise it uses create, complete, and a separate receipt.
- **Do:** On the build that will take Waves 1–2, set `VITE_ENABLE_ATOMIC_POS_CHECKOUT` and the runtime flag true, and add a test that the POS pay path calls `posCheckout`. Then delete the legacy branch in the same change as POS-031 so there is nothing left to patch twice.
- **Do not:** Implement Wave 1 on both paths and hope the flag is on. Do not leave this as a footnote.
- **Check:** A production build without `VITE_PILOT_ADVANCED` still uses `posCheckout` for cash, UPI, card, cheque, and credit.

### POS-036: Walk-in is a name regex

- **Priority:** P1. **Verdict:** Confirmed. **Status:** Shipped.
- **Where:** `walkInCustomer` in `PosPage.tsx` uses `/walk[\s-]?in/i`. `Customer` has no such field.
- **Do:** Add a boolean on the customer, one true row per company. Backfill a single existing party whose name matches the regex only when exactly one such party exists. If zero or several match, do not guess; the setup screen asks. POS, offline flush, and POS-021 read the flag.
- **Do not:** Keep the regex as a fallback. “Walkin Traders” must not become the walk-in account.
- **Check:** A party named “Walkin Traders” is not auto-selected. The flagged party is.

## Wave 1 — stock, tender, offline

Do not block POS-001 on the flush, or the flush on the till.

### POS-001: Stock gate sums every godown

- **Priority:** P0. **Verdict:** Confirmed. **Status:** Shipped.
- **Where:** `availableByProduct` and `posStockBlocked` in `PosPage.tsx`. The caption `pos.warehouseQtyBlock` says “In this godown: {n}” and uses that summed total. `listStock()` uses `staleTime: 60_000`.
- **What is wrong:** Every warehouse is added together. Policy `BLOCK`: Pay stays enabled, then the server rejects godown A. Policy `WARN`: the sale can complete and drive godown A negative. A `SERVICE`, or any product with `track_inventory` false, is still compared to on-hand and can block Pay at zero.
- **Do:**
  1. Filter balances by `warehouseId` before the map, the search label, the caption, and `posStockBlocked`. No godown selected: available is 0.
  2. Skip the gate for `product_type === SERVICE` and for `track_inventory === false`.
  3. Refetch this godown’s stock when a sale completes and when the window regains focus. The server stays the authority.
- **Do not:** Change the server negative-stock check. It is already warehouse-scoped. Do not hide expired lots here (POS-029).
- **Check:** Stock only in the other godown: this godown shows 0 and Pay is blocked under `BLOCK`. A service line does not block Pay. After a sale, the next scan sees the new on-hand without waiting 60 seconds.

### POS-012: Non-cash tenders debit cash 1100

- **Priority:** P0. **Verdict:** Confirmed. **Status:** Shipped.
- **Where:** Credit calls `checkout('CREDIT')`. Hindi `pos.creditPay` is “उधार”. `pos_checkout` allocates a receipt for any positive amount. `PostingService.post_receipt` debits 1100 when `bank_account_id` is null. The screen never sends `bank_account`. Cheque posts immediately while status is `PENDING_CLEARANCE`.
- **Do:** Follow [Fix interaction 1](#1-tender-to-account-mapping-pos-012-pos-005-pos-030). Credit completes the invoice with no receipt and no allocation (see POS-028 for the due date and POS-030 for who may take credit). Cash stays on 1100. UPI, card, bank, and cheque post to the mapped bank ledger.
- **Do not:** Invent GL 1000 or 1050. Do not pick the first bank account. Do not change the cash-shift formula here; it already counts `PaymentMode.CASH` only, which is correct once non-cash stops hitting 1100.
- **Check:** Credit: no receipt, exposure up, 1100 unchanged. UPI with a mapped bank: debit is that bank. UPI with no mapping: Pay disabled, no invoice left behind. Cash: 1100, and it is in that cashier’s expected cash.

### POS-030: Credit to the walk-in party

- **Priority:** P1. **Verdict:** Confirmed. **Status:** Shipped.
- **Where:** Walk-in can be the selected customer when Credit is pressed. After POS-012 that creates an unpaid invoice on a party with no real name.
- **Do:** Credit requires a named customer who is not the flagged walk-in (POS-036). The Credit button stays disabled until then, with that reason.
- **Do not:** Create a collectable balance on the walk-in party.
- **Check:** Credit with walk-in selected does not call checkout. Credit with a named customer does, and the invoice is unpaid.

### POS-018: F5 starts a UPI sale

- **Priority:** P1. **Verdict:** Confirmed. **Status:** Shipped. Moved out of Wave 5. An ordinary refresh key starts a payment, and the change is small.
- **Where:** The key handler treats F5 and F6 as UPI and calls `preventDefault`.
- **Do:** F5 does not pay and does not call `preventDefault`. Keep a single UPI shortcut that is not a browser chrome key, and show it on the button.
- **Check:** F5 does not call checkout. The remaining shortcut still pays when the cart is valid. Covered by `PosPage.hotkeys.test.tsx`.

### POS-031: Offline flush is not atomic

- **Priority:** P1. **Verdict:** Confirmed. **Status:** Shipped.
- **Where:** `flushPosDraft` in `web/src/offline/flushPosCheckout.ts` completes the invoice, then creates the receipt, then allocates. Those are separate calls. Idempotency keys exist per step. A crash after complete and before receipt leaves an unpaid invoice; a naive retry can create a second sale if the create key is rotated.
- **Do:** Flush cash drafts through `pos_checkout` (one transaction: invoice, complete, receipt, allocation) under the draft’s idempotency key. Requires POS-037. If the key is replayed, return the existing invoice and do not create another receipt.
- **Do not:** Keep the three-step flush and defer atomicity to the roadmap.
- **Check:** Kill the client after the server has committed the checkout. Retry uses the same key and yields one invoice and one cash receipt. A failed checkout leaves no completed invoice.

### POS-003: Offline flush drops the chosen batch

- **Priority:** P1. **Verdict:** Confirmed. **Status:** Shipped.
- **Where:** Online payloads send `batchNo`. `flushPosDraft` omits it. Blank batch number on a tracked item makes `SalesService._sale_batches` allocate first-expired-first-out.
- **Checked with this:** the flush **does** send `serialNumbers`. Do not add a serial-drop issue.
- **Do:** Send `batchNo` on the atomic flush body the same way `buildAtomicPosInvoicePayload` does.
- **Do not:** Treat a missing batch as a client error for items that are not batch-tracked.
- **Check:** A queued line whose lot is not the earliest syncs as that lot. A serialised line still syncs with its serials.

### POS-005: Offline queue accepts tenders that cannot sync

- **Priority:** P1. **Verdict:** Confirmed. **Status:** Shipped. The 1.2 fix (pass CARD and BANK through) is withdrawn. See interaction 1.
- **Where:** The outbox stores `paymentMode`. `flushPosDraft` then forces `mode: 'CASH'`. The banner (`pos.offlineBanner`) says cash sales will queue. UPI is already refused in the flush, which is too late if the draft was queued.
- **Do:** While offline, Pay accepts cash only. UPI, card, bank, cheque, and credit are disabled with a connection message that names the mode. Do not enqueue them. Banner text matches that rule. Cash flush uses the atomic path (POS-031) and mode `CASH`.
- **Do not:** Invent GL accounts in this change. Do not convert an old queued card draft into cash. Fail that draft with an error (see Rollout).
- **Check:** Offline card press does not enqueue. Offline cash enqueue flushes as cash. A cheque draft already in an old outbox does not become a cash receipt.

### POS-032: Two terminals and the last unit

- **Priority:** P1. **Verdict:** Needs a Postgres test. Not yet shown as a product bug. **Status:** Shipped.
- **Where:** Each terminal has its own idempotency key. The client gate can be 60 seconds stale (POS-001 refetch reduces that). The server must still reject the second sale under `BLOCK`.
- **Do:** Add `backend/tests/test_pos_checkout_concurrency.py` with `pytest.mark.postgres`. Two concurrent checkouts of the last unit: one succeeds, one fails, on-hand is not negative. If the test fails, fix the lock in the sale movement before calling Wave 1 done.
- **Do not:** Add a client-side lock and call that the fix.
- **Check:** The Postgres job fails if both checkouts commit.

## Wave 2 — rules at pay

### POS-013: Credit limit ignores the receipt about to be posted

- **Priority:** P1. **Verdict:** Confirmed. **Status:** Shipped.
- **Where:** `SalesService.complete` adds the full grand total to exposure before `pos_checkout` creates the receipt. The screen has no override.
- **Do:** Follow [Fix interaction 3](#3-credit-limit-and-a-short-tender-pos-013). Apply it only inside `pos_checkout`, where the receipt amount is known in the same transaction. Collection hold still blocks every tender.
- **Do not:** Turn off credit limit for all invoices. Do not let cash skip a collection hold.
- **Check:** At the limit, full cash completes and exposure does not keep the bill. Short cash completes only for the unpaid part that still fits. Credit at the limit does not complete. A `stop_credit` customer cannot pay cash until the hold is lifted.

### POS-014: Same SKU always merges onto one line

- **Priority:** P1. **Verdict:** Confirmed. **Status:** Shipped.
- **Where:** `addProduct` finds a line by `product.id` only.
- **Do:** If the existing line’s batch differs from the batch being added, append a line. Merge when the product and the batch are the same. Non-batch scans still merge.
- **Check:** Two lots of one SKU become two lines and both issue.

### POS-015: GSTIN bill discount

- **Priority:** P1. **Verdict:** Confirmed. **Status:** Shipped.
- **Where:** Tender uses `AFTER_TAX`. The payload omits `invoice_discount_mode`. The model default is `AFTER_TAX`. `SalesService.complete` rejects that mode on a GST invoice when the customer has a GSTIN.
- **Do:** Follow [Fix interaction 2](#2-discount-mode-and-the-on-screen-total-pos-015-pos-020). GSTIN customers use before-tax on both the tender and the payload. Customers without a GSTIN may keep after-tax. Include POS-020 in this change.
- **Do not:** Remove the server rule.
- **Check:** GSTIN customer, bill discount greater than zero: Pay completes, the mismatch dialog does not open, stored mode is before-tax, and the row sum matches the tender before round-off.

### POS-020: Row amount can disagree with the tender

- **Priority:** P2. **Verdict:** Confirmed. **Status:** Shipped. Wave 2, with POS-015.
- **Where:** The row calls `calculateLineTax` without cess and without inclusive extraction. The tender memo does both.
- **Do:** Render price and line total from the same line-tax result the tender uses.
- **Do not:** Fork tax math inside POS.
- **Check:** Inclusive price plus cess: row amounts foot to the tender before bill discount, charges, and round-off.

### POS-016: Customer list is the first 100

- **Priority:** P1. **Verdict:** Confirmed. **Status:** Shipped.
- **Where:** `listCustomersPage({ pageSize: 100 })` into a select, no name or phone query.
- **Do:** Search by name and phone without a 100-row cap. Pin the flagged walk-in (POS-036) at the top.
- **Do not:** Load every customer. Do not merge typed names (POS-004).
- **Check:** A customer outside the first 100 is found by phone and gets their price list.

### POS-023: Required UTR is never asked

- **Priority:** P1. **Verdict:** Conditional. **Status:** Shipped.
- **Where:** `PaymentService.create_receipt` requires a UTR when `require_payment_reference` is set and mode is UPI or BANK. POS does not ask.
- **Do:** When the flag is on, require the reference before Pay and send it. When the flag is off, show no field.
- **Do not:** Invent a UTR. Do not poll the QR (POS-009).
- **Check:** Flag on, empty UPI: Pay stays disabled. Flag off: no field.

### POS-028: Credit sale is due today

- **Priority:** P1. **Verdict:** Confirmed. **Status:** Shipped. Promoted out of the roadmap so it has an owner and a wave.
- **Where:** Atomic and flush payloads set `due_date` to the invoice date and `payment_terms_days` to 0. After POS-012 a credit sale is unpaid and immediately overdue.
- **Do:** For credit only, set terms from the customer’s payment terms and due date from the invoice date plus those days. Cash and other settled tenders stay due on the invoice date because they are paid now.
- **Check:** A credit sale for a customer with 15-day terms is due 15 days out and is not overdue today. A cash sale is due today and paid.

### POS-017: Cheque submits before its fields are usable

- **Priority:** P2. **Verdict:** Confirmed. **Status:** Shipped. Wave 2, not optional.
- **Where:** Fields render only when `lastMethod === 'CHEQUE'`. The button calls `rememberMethod` and `checkout` in one click.
- **Do:** The first click only selects cheque and shows the fields. Checkout runs when number and bank are filled, and the mapped bank account exists (POS-012).
- **Check:** The first click does not call `pos_checkout`. The second creates one cheque receipt in `PENDING_CLEARANCE` against the mapped bank, not 1100.

### POS-022: Below-cost override requires the owner’s session

- **Priority:** P2. **Verdict:** Confirmed. **Status:** Shipped. Wave 2.
- **Where:** `assert_below_cost_blocked` accepts `below_cost_override_reason` from an owner. POS never sends it. The owner is often not the person at the counter.
- **Do:** Ask for a one-time owner PIN or approval code. The server checks that secret, stores the reason, and writes the existing audit event. Sales staff cannot type a reason alone.
- **Do not:** Treat “the logged-in user is the owner” as the only path. Do not send a blank reason.
- **Check:** A valid PIN completes one invoice and the audit text includes the reason. A wrong PIN does not. No second invoice is created.

## Wave 3 — till

Ship after POS-012. Closing a shift while non-cash still debits 1100 records the wrong variance.

### POS-002: Till exists; the counter does not use it

- **Priority:** P1. **Verdict:** Partial. Do not create a new model. **Status:** Shipped.
- **What exists:** `CashShiftRegister`, one row per company, cashier, and business date. `cash_shifts.py` expected cash = opening float + that cashier’s cash receipts − that cashier’s cash supplier payments. `POST /api/v1/accounting/cash-shifts/` and `POST .../close/`.
- **What is missing:** No open or close on POS. Close stores variance and does not post a journal. The view set needs accounting enabled. List needs financial-report permission, so sales staff cannot read their own shift.
- **Do:** A cashier-readable “my open shift today” that does not need financial reports. If accounting is on and no shift is open, ask for the opening float. End shift uses the existing denomination map, then `close`, and shows expected, counted, and variance.
- **Do not:** A second register, `AUDITED`, `terminal_id`, or a stored cash-sales total. Cash drop and a variance journal stay in the roadmap (R-14), not this wave.
- **Check:** Open, cash sale, close once, second close rejected. The other cashier’s cash is excluded. A UPI sale is not in expected cash.

## Wave 4 — counter speed

### POS-008: Pre-select the earliest lot

- **Priority:** P2. **Verdict:** Partial. **Status:** Shipped.
- **Do:** When the line has no batch and the list is non-empty, set `batchNo` to `lots[0]` (soonest expiry). Keep the dropdown. Do not replace a batch the cashier already chose. Expired lots stay visible until POS-029.
- **Do not:** Return to a free-text batch field.
- **Check:** Two lots: the earliest is selected. An override sticks.

### POS-004: Unnamed offline sales and the walk-in

- **Priority:** P2. **Verdict:** Partial. **Status:** Shipped.
- **What the code does:** A draft with no customer and a typed name creates one customer per draft. Retry of the same draft does not create a second. Two drafts with the same typed name stay two customers. That split is deliberate.
- **Do:** No typed name: bind to the flagged walk-in (POS-036), creating that party once if needed. A typed name stays its own customer.
- **Do not:** Look up by exact name. Do not use an idempotency key derived only from the name.
- **Check:** Two offline drafts typed “Ravi” are two customers. Two with no name share the flagged walk-in.

### POS-007: Two ways to hold a bill

- **Priority:** P2. **Verdict:** Confirmed. **Status:** Shipped.
- **Where:** Bill tabs use the device draft. Hold cart uses `sessionStorage` key `bb_pos_holds:{company}:{user}`.
- **Do:** Hold carts are server-side. F8 parks the bill on the server and F9 recalls it. The same user can open that hold on another terminal. The bill still on screen keeps a device draft.
- **Do not:** Keep a second device-only hold list beside the server holds.
- **Check:** An old hold chip reappears as a tab. New holds do not write `bb_pos_holds`.

### POS-021: Blank place of supply

- **Priority:** P2. **Verdict:** Conditional. **Status:** Shipped.
- **Where:** Tax on and no state and no GSTIN opens the intra-state confirm. The tender already assumes local tax. The server can store `pos_assumed_local`.
- **Do:** If the customer is the flagged walk-in and the company already assumes local supply for a blank party, skip the dialog and keep the tax note on the tender. A named customer with a blank state still confirms. Interstate is never inferred for a named customer. Assuming local for the flagged walk-in is the company rule, not a guess that the walk-in is in another state.
- **Do not:** Skip the dialog for a named party. Do not use the name regex.
- **Check:** Flagged walk-in, assume-local on: no dialog, invoice is intra-state. Named customer, no state: dialog still appears.

### POS-029: Expired lots can still be sold

- **Priority:** P2. **Verdict:** Confirmed. **Status:** Shipped. Promoted out of the roadmap.
- **Where:** `availablePosBatches` keeps a lot with quantity even when `expiryDate` is in the past.
- **Do:** Company setting: block, or allow with a reason. `regulated_category` DRUG defaults to block. FOOD and GOODS default to allow-with-reason until the company chooses. The reason is an audit event (POS-034).
- **Do not:** Silently drop expired lots with no setting.
- **Check:** DRUG lot expired yesterday cannot be selected. A GOODS lot expired yesterday asks for a reason before Pay.

### POS-033: Offline sale has no customer slip

- **Priority:** P2. **Verdict:** Confirmed. **Status:** Shipped.
- **Where:** Offline enqueue does not print. The invoice number is assigned at sync. Nothing on screen gives the customer a reference, and nothing must look like a tax invoice number.
- **Do:** Show a local queue reference that is visibly not an invoice number. Do not print a tax invoice until sync returns the real number.
- **Check:** Offline cash shows a queue id. No PDF titled as a tax invoice is generated offline.

### POS-035: Any cashier can discount a line to zero

- **Priority:** P2. **Verdict:** Confirmed. **Status:** Shipped.
- **Where:** `updateDiscount` clamps to 0–100 and has no role or company cap.
- **Do:** A company max line-discount percent. Above it, Pay needs the same owner PIN as POS-022. At or under the cap, Pay does not ask.
- **Check:** A discount under the cap completes. A discount over the cap without a PIN does not.

## Wave 5 — print, layout, audit

Not optional for a shop that uses a Bluetooth printer or needs an audit trail. Optional relative to taking a correct cash payment.

### POS-006: Native thermal print is a stub

- **Priority:** P2. **Verdict:** Partial. **Status:** Shipped.
- **Where:** `printPosThermalOrWarn` sends `BizBoard`, the number, and a drawer kick when `printEscPos` returns `native`. Otherwise it downloads `thermal_pdf`, which already has the full bill (`backend/sales/pdf/thermal_receipt.py`).
- **Do:** Real ESC/POS bytes only on the native path. Desktop stays on the PDF.
- **Do not:** Add WebUSB or raw TCP in the page.

### POS-009: Do not poll the UPI QR

- **Verdict:** Do not build. **Status:** Closed.
- **Why:** `upi://pay` has no payment id and no status URL. A second confirm that names the amount is roadmap R-06, not a poller.

### POS-010: Do not add a cashier role

- **Verdict:** Do not build. **Status:** Closed.
- **Why:** `pos_checkout` already requires create-sales and create-payments. Sales staff have both by default. A 403 means `can_create_payments` was turned off.

### POS-011: Tender panel height

- **Priority:** P3. **Verdict:** Confirmed. **Status:** Shipped.
- **Do:** One tax row. Keep Change and the primary Pay control on a 768px-tall screen. Drop the repeated SKU. On a narrow screen, Pay is currently below the cart.
- **Do not:** Start the fix list here.

### POS-019: Scale weight is discarded

- **Priority:** P2. **Verdict:** Confirmed. **Status:** Shipped.
- **Where:** The button calls `readScaleWeight()` and ignores the number.
- **Do:** A finite weight sets the selected line’s quantity, in that product’s unit. No selected line: show the weight and do not add a line. No serial port: leave the cart unchanged.
- **Check:** A port that returns `1.25` sets quantity to 1.25.

### POS-024: Offline split message

- **Priority:** P3. **Verdict:** Confirmed. **Status:** Shipped.
- **Do:** After POS-005, split is disabled offline because it includes UPI. The message names split, not “UPI needs a connection”, when the cashier pressed split.
- **Do not:** Queue a split offline.

### POS-025: Phones on the counter

- **Priority:** P3. **Verdict:** Confirmed. **Status:** Shipped.
- **Do:** POS-016’s search may show a phone on the row being matched. Do not render every party’s phone in a standing list.

### POS-026: Drawer opens with no extra confirm

- **Priority:** P3. **Verdict:** Confirmed. **Status:** Shipped.
- **Do:** Leave the button for anyone who can use POS. Audit the open (POS-034). Do not add a cashier role to hide it.

### POS-027: Custom-field filter on the scan row

- **Priority:** P3. **Verdict:** Confirmed. **Status:** Shipped.
- **Do:** Show the filter only when the company has active product custom fields and the cashier opens it.

### POS-034: Missing audit events

- **Priority:** P2. **Verdict:** Confirmed. **Status:** Shipped.
- **Do:** Audit a line discount, a price change (when R-13 exists), a drawer kick, a below-cost PIN (POS-022), an expired-lot reason (POS-029), and UPI “Payment received” (who, when, amount). Use the existing audit log. Do not invent a second log.
- **Check:** Each of those actions has one audit row tied to the invoice or the shift.

## Explicitly out of Waves 0–5

- A second cash-shift model, an `AUDITED` status, or a variance journal. Cash drop is roadmap R-14.
- In-browser raw TCP or WebUSB.
- Polling `upi://pay` (POS-009).
- A cashier role or `CanOperatePosTerminal` (POS-010).
- Merging customers by typed name (POS-004).
- New GL codes for card or UPI (POS-012).
- Filing an e-invoice IRN from this screen (roadmap R-18).
- Held bills on the server (roadmap R-12) until POS-007’s device list is the only hold list.
- Returns on this screen (roadmap R-09).

## Final verdict

**Not ready. Nothing in this plan has shipped.**

Wave 0 comes first, because the atomic flag defaults off and the walk-in party is a name match. Wave 1 then makes stock, credit, and offline sync match what the cashier did. Later waves do not start a second pay path or a second hold list.

Scores are not in this file. [POS_Roadmap.md](POS_Roadmap.md) holds the unmeasured estimates and the later work. Shipping Waves 0–5 does not, by itself, make any dimension a 10.
