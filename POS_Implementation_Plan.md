# POS implementation plan

**Date:** 2026-10-07
**Revised:** 2026-10-07, after the pre-implementation review. The decisions below replace the earlier wording where they conflict.
**Source:** deep code review of the uncommitted POS work on `main` (backend `sales/pos_*.py`, `accounting/cash_shifts.py`, web `pages/pos/*`, `offline/flushPosCheckout.ts`).
**Relates to:** [POS_Fix.md](POS_Fix.md) (defects, Waves 0–5) and [POS_Roadmap.md](POS_Roadmap.md) (R-01 to R-20). This plan covers what those do not: the review findings B1–B12, the gaps against a modern POS, and the engineering debt.
**Estimates** are engineer-days for one engineer who knows the repo. They are planning figures, not commitments. The staffing table is the calendar. It includes review, a pilot week per phase, and waiting on the accountant.

## 0. Ground rules

- Phase 0 ships first. The current POS work is uncommitted, and every later phase builds on it.
- Money-path changes (refunds, credit offline, returns) need a Postgres test run. Concurrency tests are Postgres-only. CI already runs the suite on Postgres 17 and does not exclude the `postgres` marker. A local run uses SQLite unless `DATABASE_URL` is set. CI does not roll migrations backward; Phase 0 does that once by hand.
- Every phase ends with: `ruff`, `pytest` on touched suites, `tsc -b`, `eslint` (0 errors), `vitest` on touched folders. Lint stays at 0 errors.
- New settings live in `company.feature_flags` only if they are not secrets. Secrets get a real column. The owner PIN hash that sits in `feature_flags` today moves out in Phase 2.
- Each new rule gets an automated test before it is called done. A score in `POS_Roadmap.md` changes only after a cashier study. Implementation records the check in the checks log at the bottom of this file.
- Hindi and English strings for every new control (`i18n/en.ts`, `i18n/hi.ts`).

## Decisions (2026-10-07)

These are the answers to the pre-implementation review. Later sections follow them.

| # | Decision |
|---|---|
| 1 | A cash or bank refund is **Dr 2300 / Cr 1100** (or the mapped bank). Cap it at the amount that return peeled into advances, and at the customer's 2300 balance. The credit note stays the only sales and GST reversal. |
| 2 | v1 refund modes are `CASH`, `BANK`, and `ADVANCE`. `ORIGINAL` is dropped. `ADVANCE` leaves the peeled money on 2300. `BANK` is the mapped account for a manual UPI or card receipt. A gateway receipt refunds only through `refund_gateway_payment`. Pro-rata across a split bill waits for Phase 5. |
| 3 | The walk-in party cannot take `ADVANCE`. A walk-in return is cash or bank. |
| 4 | Exchange is a return plus a new bill. Checkout can apply the customer's unallocated advance. If the new bill is smaller, the cashier refunds the rest or keeps it as an advance. R-09 stays **Partial** until that ships. |
| 5 | v1 takes one refund mode per return. The refund row is keyed by an idempotency key. There is no unique constraint on the return, so several rows per return can be added in Phase 5. |
| 6 | Phase 2 moves `pos_owner_pin_hash` into a `PosApproverPin` row for the owner and clears the flag. There is no one-release fallback in `feature_flags`. |
| 7 | Offline credit is opt-in (`pos_offline_credit`, default off). Caps: ₹5,000 per customer per outage, or the cached remaining limit if lower; 20 credit bills per terminal per outage; never for stop-credit or severe overdue. Device and server both check. `POS_Fix.md` records this reversal when the setting ships. |
| 8 | Legacy create-then-receipt is already gone. `collectPosPayment` on an already-completed invoice is recovery, not a second pay path. Phase 0 deletes `VITE_ENABLE_ATOMIC_POS_CHECKOUT` and `isAtomicPosCheckoutEnabled`. |
| 9 | Calendar is 10–12 weeks with two engineers. Effort is the phase table. Phase 0 is 3–4 days. The mis-post report runs in parallel and does not block the merge. |
| 10 | One PR, five commits, merged with a merge commit. CI (Postgres, coverage 83%) is the gate. |
| 11 | Any tender that moves cash needs an open shift: a cash split part, and cash on `PosCollectView`. Accounting off means the shift API is unavailable, so the requirement does not apply. Pilot shops are forced on. Other companies stay off until the pilot closes, then the default flips with notice. The Phase 1 exit applies to pilot companies. |
| 12 | One open shift per terminal. The cashier owns it and may hold shifts on several terminals. A second cashier on the same drawer closes and reopens (handover). |
| 13 | `CustomerReceipt` and the refund row get a nullable `shift` foreign key. Checkout, collect, and refund stamp it. Expected cash sums by shift. Rows with no shift use the old `receipt_date` + `created_by` rule. A manual receipt is excluded unless the user ticks "paid from till". |
| 14 | `opened_at` backfill is `business_date` 00:00 Asia/Kolkata (`Company` has no timezone column). `closed_at` for a closed shift is `locked_at`. If a cashier has more than one open row, the migration aborts and lists them. `report_open_shifts` is the ops command. The migration never picks a row. |
| 15 | Cash drops become lines (`shift`, amount, time, user, note). `cash_dropped` stays a cached sum until nothing reads it. Supplier cash payments get the same nullable shift stamp, set only when paid from the till. The Z-report reads those lines. |
| 16 | Walk-in ships in order: get-or-create endpoint, then POS and offline flush switch to it, then the serializer field becomes read-only. The move action locks, clears the old party, and sets the new one in one transaction. It rejects a target that has a GSTIN or a credit limit. A soft-deleted walk-in is ignored by the existing partial unique constraint; get-or-create makes a new one. |
| 17 | A PIN row is the grant. The owner creates it for a named user. Sales staff have none until granted. An accountant has none until the owner grants one. |
| 18 | Price baseline is `resolveListUnitPrice` when the customer's list has the product, otherwise `selling_price` (what `unitPriceFor` already uses). Order: below-cost block, then `pos_max_price_discount_percent` against that baseline, then the line-discount cap on the discount-percent field only. `pos_min_margin_percent` is not added. |
| 19 | Server audit rows are written in checkout first. For one release `PosCounterEventView` still accepts `discount`, `upi_received`, and `price_change` and ignores them (200). The next release returns 400. A drawer open requires a shift id only when the shift requirement is on. |
| 20 | Batch-tracked and serial-tracked items are blocked offline in v1, with a clear message. |
| 21 | A stock conflict parks the whole draft and marks the line. The bill is not completed without that line. |
| 22 | Catalogue warns at 24 hours and blocks at 72 (configurable). Cached credit blocks offline credit after 4 hours. There is no cross-terminal reservation. Exposure is the per-customer cap times the number of terminals. |
| 23 | Offline price lists: customers used on this device in the last 30 days, plus the default list. A customer whose list is not local cannot be selected offline. |
| 24 | UPI QR uses the company VPA and `build_upi_intent` in `payments/upi.py`. Print it only when a balance is still due. Confirmation stays the manual R-06 step. A gateway QR is a later project. |
| 25 | Omit the e-invoice QR when the invoice has no IRN at print time. Reprint loads the invoice again, so the QR appears once an IRN exists. |
| 26 | Scale v1 is generic ASCII over Web Serial: a configurable pattern, and a stable flag read from a status prefix when the device sends one. Weighted barcodes are a company setting, off by default, with type (weight or price), item digits, value digits, and decimals. There is no hard-coded `2x` prefix. |
| 27 | P5-A is a line picker plus the return window, on top of the refund design. About 3 days once P1-A exists. Split-tender pro-rata is a separate Phase 5 item. |
| 28 | Store credit v1 is the customer advance on 2300 (`ADVANCE`). Gift cards stay deferred until there is a CA view on GST at issue versus redemption, an expiry and breakage policy, and a liability account. |
| 29 | Discount evaluation order, written before any scheme or coupon work: price list, scheme, line discount, coupon, bill discount (before tax for a GSTIN customer), tax on the net taxable value, round-off. Loyalty redemption is a tender and does not change tax. Coupons and schemes wait for a pilot request. |
| 30 | Pharmacy at the counter calls the existing `assert_pharmacy_sale` (`drug_schedule` H/H1/X when `pharmacy_enabled` is on). `regulated_category` stays the statutory DRUG/FOOD flag and is not a second checkout gate. Prescription image is optional, in the company file store. Retention length is unset until a pharmacist confirms it. |
| 31 | Salesperson is a field only. No commission report. One terminal identity: a per-device id and label, copied onto the shift at open, then onto each invoice and receipt at checkout. |
| 32 | A pilot day's close is required for posting, stock, GST, and shifts (Phase 1, P3-B, P4-E, and the Phase 5 money items). Catalogue, receipt layout, accessibility, and refactors use a device test, an `axe` run, or the e2e suite. |
| 33 | Phase 0 still runs one local Postgres pass with `DATABASE_URL`, plus forward and backward of migrations `0014` and `0031`. |
| 34 | Score cells in `POS_Roadmap.md` stay blank. This file's checks log records the check and the result. |

## Verified facts that drive this plan

| Fact | Evidence |
|---|---|
| A counter return creates a credit note and, for a paid bill, peels receipt allocations into Customer Advances (2300). It does not credit cash. | `ReturnService.complete_return` calls `complete_credit_note(..., confirm_paid_invoice=True)`. Peel logic is in `notes_services.py`. |
| The advance-refund journal shape already exists: Dr 2300, Cr the receipt's bank or 1100. | `PostingService.post_receipt_refund` (`accounting/services.py`). Its source key is the receipt and purpose `REFUND`, so a second refund against the same receipt needs its own source. |
| Checkout does not require an open shift. | No shift reference on the POS checkout path. The till strip is display and actions. |
| One till per cashier per day. | `uniq_cash_shift_per_cashier_day`. |
| `is_pos_walk_in` is writable through the customer API. One live walk-in per company is already enforced. | `CustomerSerializer.fields` has no read-only rule. Partial unique constraint on `Customer`. |
| `isAtomicPosCheckoutEnabled()` is hard-coded true. `PosPage.tsx` does not call `createSalesInvoice` or `completeSalesInvoice`. | `web/src/config/features.ts`. Recovery uses `collectPosPayment`. |
| The owner PIN hash lives in `company.feature_flags`. | `pos_policy.set_owner_pin`. |
| No local product catalogue for offline scan. | Search and scan call `searchProducts`. |
| Pharmacy sales are already gated. | `assert_pharmacy_sale` in `planwave/services.py`, recorded on `PharmacyDispense`. |
| UPI intent helper exists. | `payments/upi.py` `build_upi_intent`. |
| `CustomerReceipt` inherits `created_at` from `CompanyScopedModel`. Expected cash today uses `receipt_date` and `created_by`, not `created_at`. | `cash_shifts.expected_system_cash`. |

## Phase map

| Phase | Theme | Ships | Est. | Depends on |
|---|---|---|---|---|
| 0 | Land and stabilise | The current uncommitted POS work, safely | 3–4 d | none |
| 1 | Cash integrity | Refunds, shift enforcement, per-terminal shifts, walk-in lock, exchange advance | 11–13 d | 0 |
| 2 | Approvals and audit | Per-user PIN, price floor, server audit | 6–8 d | 0 |
| 3 | Offline that works | Catalogue, opt-in offline credit, batch sync, stock query | 10–12 d | 0, partly 1 |
| 4 | Receipts and hardware | Receipt content, Hindi, UPI QR, silent print, Z-report, scale | 8–10 d | 1 (Z-report) |
| 5 | Counter features | Partial returns, split pro-rata, pharmacy fields, salesperson | 8 d committed | 1, 2 |
| 6 | Engineering quality | Split `PosPage`, e2e, accessibility | 10–12 d | after 1–3 |

Committed effort is about 56–67 engineer-days. Coupons, schemes, and gift cards sit outside that until a pilot or a CA view exists. Calendar time stays 10–12 weeks with two engineers.

Phases 1 and 2 can run in parallel after Phase 0. Phase 3 can start once Phase 0 is in. Phase 6 should not start until Phases 1–3 stop changing `PosPage.tsx`.

---

## Phase 0: land and stabilise (3–4 d)

The work under review is uncommitted. Nothing below it is safe until this is merged and green.

| Step | Detail |
|---|---|
| 0.1 | Read `git diff --stat` and group the work into 4 to 5 commits: (a) accounting and masters migrations (`0014`, `0031`), (b) `pos_policy`, `pos_views`, `sales` changes, (c) offline flush and API client, (d) `PosPage` and components, (e) tests and docs. One PR. Merge with a merge commit so the grouping survives. |
| 0.2 | Run the full backend suite once, not only the POS subset. Run the full web suite and `npm run build`. Record any failure that is not POS-related and open a ticket. |
| 0.3 | One local Postgres run with `DATABASE_URL` set: `test_concurrency_races.py`, plus migrations `0014` and `0031` forward and backward (`0031` backfill is a `RunPython`). CI already runs the Postgres suite; it does not roll migrations back. |
| 0.4 | Run `report_pos_cash_mispost` against a copy of production data when access exists. Hand the output to the accountant before Phase 1 changes any posting. This does not block the merge. |
| 0.5 | Update `POS_Fix.md` POS-007 to say hold carts are server-side (F8 holds, F9 recalls). |
| 0.6 | Delete the stale comment in `scanInput.ts` that says the page does not use it. |
| 0.7 | Delete `VITE_ENABLE_ATOMIC_POS_CHECKOUT` and `isAtomicPosCheckoutEnabled`. Pay stays on `posCheckout`. `collectPosPayment` remains the recovery path for a bill that is already completed. Mark POS-037 done. |
| 0.8 | Grep every API that returns `feature_flags` (pack views, exports, settings). List any response that includes `pos_owner_pin_hash`. Phase 2 removes the hash; this list is the strip checklist. |

**Done when:** the PR is merged with a merge commit, CI is green on Postgres (coverage gate 83%), the flag and the dead function are gone, and the mis-post report is either delivered or explicitly waiting on a data copy.

---

## Phase 1: cash integrity (11–13 d)

### P1-A. Cash and bank refunds on counter returns (B1) (3–4 d)

**Problem.** `PosReturnView` completes a sales return. The credit note reverses sales and GST. For a paid bill, `confirm_paid_invoice=True` peels receipt money into Customer Advances (2300). Cash handed back is not recorded, so the till's expected cash stays high.

**Journal.** Reuse the line shape of `PostingService.post_receipt_refund`: debit 2300, credit 1100 or the mapped bank. Do not call that method as-is for a second refund against the same receipt. The posted-journal unique key is `(company, source_type, source_id, purpose)`, and `post_receipt_refund` uses the receipt id with purpose `REFUND`. The new journal's source is the refund row, purpose `REFUND`, so two refunds against one receipt both post. The credit note is untouched.

A gateway receipt (one with `gateway_payment`) refunds only through `refund_gateway_payment`. A manual UPI or card receipt is bank-mapped; its refund is a manual bank transfer, mode `BANK`.

| Step | Detail |
|---|---|
| 1 | Refund request mode is `CASH`, `BANK`, or `ADVANCE`. Default `CASH` when the peeled receipts are cash, `BANK` when they are UPI, card, bank, or cheque. `ADVANCE` is an explicit choice. Walk-in cannot choose `ADVANCE` (same rule as `pos_credit_walk_in`). |
| 2 | Add a refund row: company, customer, return, amount, mode, cashier, date, bank account, idempotency key, nullable shift. No unique constraint on the return. v1 the screen submits one row. |
| 3 | Inside the same `transaction.atomic()` as `complete_return`: compute the amount peeled into 2300 for this return. `ADVANCE` posts nothing. `CASH` and `BANK` post Dr 2300 / Cr 1100 or the mapped bank from `resolve_bank`. Cap at the peeled amount and at the customer's 2300 balance. Refuse a refund above that cap. |
| 4 | `expected_system_cash` subtracts this shift's cash refunds (see P1-C for the shift foreign key). Until the shift stamp exists, subtract that cashier's cash refunds on the business date. |
| 5 | Web: after a return, require a mode. Show "Refund ₹X by cash", "Refund ₹X to bank", or "Leave as advance". |
| 6 | Idempotent on the refund row's idempotency key. A replay does not post a second journal. |

**Tests.**

- Cash sale, then cash return: expected cash returns to the opening float; ledger shows 2300 debit and 1100 credit. The credit note is the only sales reversal.
- UPI sale with a mapped bank, then return: refund credits that bank, not 1100.
- Gateway receipt: `refund_gateway_payment` runs; no second 2300 journal from the counter refund poster.
- Credit sale, then return: peeled amount is zero; only `ADVANCE` is accepted; customer balance falls by the credit note.
- Partially paid sale: refund capped at the peeled amount.
- Walk-in: `ADVANCE` is refused.
- Double submit of the same idempotency key: one refund row and one journal.

**Acceptance.** For any mix of sales and returns in a pilot day, expected cash equals opening float plus cash receipts stamped to the shift, minus cash refunds, minus cash supplier payments stamped to the shift, minus drops.

Show the journal (Dr 2300 / Cr 1100 or bank, cap, credit note left alone) to the accountant before coding step 3.

### P1-B. Enforce the open shift (B2) (2 d)

Any tender that moves cash needs an open shift for this terminal: a cash sale, the cash part of a split, and `PosCollectView` when the mode is cash. UPI, card, bank, cheque, and credit do not need a drawer. When accounting is off, shifts are unavailable, and this rule does not apply. Say that in the operator note.

| Step | Detail |
|---|---|
| 1 | Company setting `pos_require_open_shift` in `feature_flags`. Off for existing companies. On for new companies. Pilot companies are forced on for the pilot week. After the pilot closes, the default for everyone else flips with notice. |
| 2 | `pos_checkout` and `PosCollectView`: when the setting is on and the tender moves cash, require an open `CashShiftRegister` for this terminal. Error code `pos_shift_required`. |
| 3 | `PosPage`: when the setting is on and no shift is open, disable cash Pay and show the opening-float form in place. |
| 4 | Offline: a draft saved offline records the shift id that was open. Flush checks it is still open or flags the draft for review. |

**Tests.** Setting on and no shift: cash and a cash split are refused, UPI is allowed. Shift closed mid-day: the next cash sale is refused. Setting off: unchanged. Accounting off: no shift error.

### P1-C. One open shift per terminal (B6) (3–4 d)

The drawer is the terminal. The cashier owns the shift and may have one open shift on each terminal they use. A second cashier on that drawer closes the open shift and opens a new one.

| Step | Detail |
|---|---|
| 1 | Add `terminal_id` (stable, generated once per device) and `terminal_label` (the name printed on receipts). Add `opened_at` and `closed_at`. Drop `uniq_cash_shift_per_cashier_day`. Partial unique constraint: one `OPEN` shift per company per `terminal_id`. |
| 2 | Backfill `opened_at` as `business_date` 00:00 Asia/Kolkata. Backfill `closed_at` from `locked_at`. Backfill `terminal_id` on existing rows to `legacy-{cashier_id}` so the new constraint can be created. |
| 3 | Pre-check: if any cashier has more than one `OPEN` row, abort and list them. Add `report_open_shifts` so ops can close the extras. The migration does not choose a survivor. Run on a copy first. |
| 4 | Nullable `shift` on `CustomerReceipt`, on the refund row, and on supplier cash payments. Checkout, collect, and refund set it from the open shift. Supplier payments get it only when the user marks "paid from till". A payments-screen receipt is excluded from expected cash unless that tick is set. |
| 5 | `expected_system_cash` sums cash receipts, cash refunds, till supplier payments, and drop lines for that shift. Rows with a null shift, for shifts that existed before this migration, fall back to `receipt_date` + `created_by` on that business date. |
| 6 | `CashDrop` lines: shift, amount, time, user, note. `drop_cash` appends a line and refreshes `cash_dropped` as the cached sum. Leave the column until every reader uses the lines. |
| 7 | `today` returns the open shift for this terminal, or the last closed one. Add a shift history list for the cashier. Overnight: `business_date` is the opening date; the window is `opened_at` to `closed_at`. |

**Risk.** Live uniqueness change. Copy-first dry run. Abort when two opens exist.

### P1-D. Lock down the walk-in flag (B3) (1 d)

Ship in this order. Reversing it lets the flush create unflagged duplicates.

| Step | Detail |
|---|---|
| 1 | Dedicated get-or-create endpoint for the walk-in party. Atomic. One row under the existing partial unique constraint. |
| 2 | POS and offline flush call that endpoint. They stop sending `is_pos_walk_in` through `createCustomer`. |
| 3 | `is_pos_walk_in` read-only on `CustomerSerializer`. |
| 4 | Owner-only `POST /customers/set-pos-walk-in/`. Row lock, clear the old party, set the new one, audit. Reject a target that has a GSTIN or a credit limit. A soft-deleted current walk-in is already invisible to the constraint; get-or-create creates a replacement. |

**Tests.** Cashier PATCH with the flag is ignored. Two concurrent get-or-create calls produce one row. Move from party A to party B leaves a single flagged row.

### P1-E. Exchange applies the advance (2 d)

R-09 is Partial until a pilot day is re-checked. Cash, bank, and advance refunds post, and checkout can apply the peeled advance. A split bill can be refunded across the original tenders.

| Step | Detail |
|---|---|
| 1 | Exchange stays "return, then a new bill on the same customer". The return peels paid money into 2300 (P1-A). |
| 2 | Checkout gains "apply customer advance": allocate unallocated 2300 to the new invoice up to its total, before a new tender. |
| 3 | If the new bill is smaller than the advance, the cashier chooses a refund (`CASH` or `BANK`) or leaves the remainder as `ADVANCE`. |
| 4 | When P1-E is merged, the R-09 check can be re-run. Until then the roadmap status stays Partial. |

**Phase 1 exit (pilot companies only):** a full day of mixed sales, returns, drops, and a close ties out to the cash ledger within ₹0.

---

## Phase 2: approvals and audit (6–8 d)

### P2-A. Per-user approvals (B5) (3–4 d)

| Step | Detail |
|---|---|
| 1 | Table `PosApproverPin` (company, user, hash, set_at). A row is the grant. The owner creates or resets a row for a named user. Sales staff and accountants have no row until the owner adds one. |
| 2 | Migration: copy `pos_owner_pin_hash` into a row for the owner, then delete the flag. Use the Phase 0.8 list so no API still returns the hash. |
| 3 | `pin_ok` returns the matching approver (or none). Lockout stays per submitting user (`pos_pin_fail:{company}:{user}`), 5 failures, 15 minutes. |
| 4 | Every approval records approver id, approver name, scope (`discount`, `below_cost`, `return`, `price`, `expired_lot`), invoice id, and reason in the audit log. |
| 5 | Settings: set or reset your own PIN. The owner can reset anyone's row, which is also how a grant is removed. |

**Tests.** Approval writes the right approver. Wrong PIN locks the submitting user only. Deleting the row invalidates that PIN. After migration, `feature_flags` has no `pos_owner_pin_hash`.

### P2-B. Price override floor and reason (B7) (2 d)

Baseline price is the price the counter would have charged: `resolveListUnitPrice` when the customer's price list contains the product, otherwise the product `selling_price`. That is the same pair `unitPriceFor` uses.

Check order:

1. Below-cost block. Hard. An approver can override with a reason.
2. `pos_max_price_discount_percent` against the baseline. A lower price needs an approver.
3. The existing line-discount cap, applied only to the discount-percent field.

Do not add `pos_min_margin_percent`.

| Step | Detail |
|---|---|
| 1 | Company setting `pos_max_price_discount_percent` in `feature_flags`. |
| 2 | Enforce the order above in `apply_pos_invoice_rules`. |
| 3 | The invoice item stores `price_override_reason` and the approver. |
| 4 | The server writes the price-change audit row from the saved item during checkout (see P2-C for the client event). |

### P2-C. Server-authoritative audit events (B8) (1–2 d)

| Step | Detail |
|---|---|
| 1 | Checkout writes discount, UPI received, and price-change audit rows on the server. |
| 2 | Same release: `PosCounterEventView` still accepts `discount`, `upi_received`, and `price_change`, ignores the body, and returns 200. Drawer open still logs. Drawer open requires a shift id only when `pos_require_open_shift` is on. Validate `invoice_id` belongs to the company. Cap detail length and character set. |
| 3 | Following release: those three kinds return 400. The client stops sending them. |

**Phase 2 exit:** every override in a day can be traced to one named approver and one invoice.

---

## Phase 3: offline that works (10–12 d)

### P3-A. Offline catalogue (B4) (4–5 d)

| Step | Detail |
|---|---|
| 1 | Backend: paged `GET /products/pos-catalog/?updated_after=` with POS fields only (id, name, sku, barcode, price, gst, hsn, unit, batch and serial flags, product type). Stable cursor and deleted ids. |
| 2 | Web: IndexedDB store keyed by company. Full sync, then delta on login, on reconnect, and every 15 minutes. |
| 3 | Search and scan use the local store when offline. When online, exact barcode or SKU hits use the local store. Fuzzy text stays on the server. |
| 4 | Show "catalogue last synced". Warn after 24 hours. Block selling from it after 72 hours. Both thresholds are company settings. |
| 5 | Cache price lists for customers used on this device in the last 30 days, plus the default list. If the selected customer's list is not local, refuse that customer offline and say so. |
| 6 | Show offline stock as "last known". Batch-tracked and serial-tracked items cannot be sold offline; the message says the lot is not on the device. |

**Tests.** Offline exact scan adds the item. A deleted product disappears after delta sync. A batch-tracked item is refused offline. A catalogue of 20,000 items syncs and searches within 100 ms on a mid-range phone.

### P3-B. Offline credit for a named customer (3–4 d)

This reverses the cash-only offline rule in `POS_Fix.md`. Write that reversal into `POS_Fix.md` in the same change. Setting `pos_offline_credit`, default off.

When the setting is on:

- `CREDIT` offline only for a named customer, never the walk-in.
- Cap ₹5,000 per customer per outage, or the cached remaining credit if that is lower.
- Cap 20 credit bills per terminal per outage.
- Refuse customers on stop-credit or severe overdue, using the last cached hold flags.
- Refuse when the credit cache is older than 4 hours.
- The server applies the same caps and the normal credit-limit check at sync. A failure parks that draft with a reason and does not block other drafts.
- Card, UPI, bank, and cheque stay disallowed offline.

There is no cross-terminal reservation. Worst case exposure is the per-customer cap times the number of terminals. Say that in the operator note.

### P3-C. Batch sync and conflict handling (2 d)

| Step | Detail |
|---|---|
| 1 | The flush sends up to 50 drafts through `PosBatchSyncView`. Each draft keeps its own idempotency key. |
| 2 | Map per-item errors back to drafts. A stock conflict parks the whole draft and marks the offending line. The bill is not completed without that line. |
| 3 | The parked draft reopens in the POS cart with the server error on that line (R-10). |

### P3-D. Stock query scale (B9) (1 d)

| Step | Detail |
|---|---|
| 1 | Add `warehouse` and `product_ids` filters to the stock endpoint if they are not already there, and use them in `PosPage` for the selected godown only. |
| 2 | Refetch that godown's stock after each completed sale and on window focus. The server stays the authority. |
| 3 | The error for a lost race names the item and the quantity left. |

**Phase 3 exit:** with the network off for an hour, a cashier can scan, bill cash, and (where the setting is on) bill named credit within the caps. Sync produces no duplicates. Batch and serial items stay blocked until the network is back.

---

## Phase 4: receipts and hardware (8–10 d)

| ID | Item | Steps | Est. |
|---|---|---|---|
| P4-A | ESC/POS content | GSTIN, tax breakup by rate, HSN, payment mode, cashier, terminal label, savings line, footer text, copies count. Paper width 58 or 80 mm. Rupee glyph via the printer code page, or `Rs` when the code page has none. | 2 d |
| P4-B | Hindi and Unicode | Raster image (canvas to 1-bit ESC/POS) on the native path so any script prints. Text mode stays the fast fallback. | 3 d |
| P4-C | UPI QR on receipt | `build_upi_intent` / `upi_qr_fields` with the company VPA, only when a balance is still due. Manual confirm stays R-06. No gateway QR and no status poll (POS-009). E-invoice QR only when an IRN is already on the invoice. Reprint reloads the invoice. | 1 d |
| P4-D | Silent print and drawer | Desktop shell: PDF to the default thermal printer without a dialog. Browser: document Chrome `--kiosk-printing`. Drawer pulse with the print job. | 2 d |
| P4-E | Z-report | `ShiftSummaryPdf` from the shift's own lines: opening float, sales by tender, returns and refunds, drop lines, expected, counted, variance, cashier, terminal, `opened_at`, `closed_at`. Print on close. Reprint from shift history. Depends on Phase 1. | 2 d |
| P4-F | Scale and weighted barcodes | Generic ASCII over Web Serial. Configurable parse pattern. Read a stable flag from a status prefix when the device sends one. No vendor protocol until a pilot names the model. Weighted barcodes: company setting, off by default; type weight or price; item digits, value digits, decimals. | 2 d |

**Acceptance.** A 58 mm and an 80 mm receipt both show GSTIN, tax split, total, and tender. A balance-due receipt shows the UPI QR. A Hindi item name prints on the native path. A receipt with no IRN has no e-invoice QR.

---

## Phase 5: counter features (8 d committed)

Do not start until P1-A is in. P5-C, P5-D, and gift cards are listed so they are not redesigned later. They are not in the 8 days.

| ID | Item | Key steps | Est. |
|---|---|---|---|
| P5-A | Partial and line returns | The return screen picks lines and quantities. Reuse the remaining-qty math already in `PosReturnView`. Refund through P1-A. Company return-window setting; past the window needs an approver PIN. | 3 d |
| P5-A2 | Split-tender pro-rata | One return of a split bill can post more than one refund row (the idempotency key allows this). Each row follows P1-A caps. The parts together cannot exceed the peeled amount. | 2 d |
| P5-B | Store credit | v1 is `ADVANCE` / ledger 2300 from P1-A. No new tender and no new account. | — |
| P5-C | Loyalty and coupons | Not started without a pilot request. Evaluation order is fixed below. Loyalty burn is a tender and does not change tax. | 3 d when asked |
| P5-D | Schemes | Not started without a pilot request. Buy-X-get-Y and bundle price run in the totals preview and at checkout, in the order below. | 3 d when asked |
| P5-E | Pharmacy fields on the counter | `SalesService.complete` already calls `assert_pharmacy_sale`. The counter collects patient name, prescriber name, registration, and prescription number (and the optional prescription image) and passes them through. Gate is `drug_schedule` H, H1, or X when `pharmacy_enabled` is on. Schedule X still requires the prescription note. Image goes to the company file store. Register read stays `PharmacyRegisterView` (owner, manager, accountant). Keep these fields out of ordinary invoice exports. Do not set a retention period in code until a pharmacist confirms one. | 2 d |
| P5-F | Salesperson | `salesperson` on the invoice. `terminal_id` and `terminal_label` copy from the open shift onto the invoice and the receipt. No commission report. | 1 d |
| — | Gift cards | Deferred. Needs a CA view on GST at issue versus redemption, an expiry and breakage policy, and a liability account. `STORE_CREDIT` is not a refund mode until then. | — |

**Evaluation order** (write this into `apply_pos_invoice_rules` before P5-C or P5-D):

1. Price list (`resolveListUnitPrice`).
2. Scheme.
3. Line discount.
4. Coupon.
5. Bill discount, before tax when the customer has a GSTIN.
6. Tax on the net taxable value.
7. Round-off.

Loyalty redemption is a tender after tax.

Order inside the phase: P5-A, then P5-A2, then P5-E, then P5-F. P5-C and P5-D wait for a pilot.

---

## Phase 6: engineering quality (10–12 d)

### P6-A. Split `PosPage.tsx` (5–6 d)

Target structure under `web/src/pages/pos/`:

| Module | Owns |
|---|---|
| `useCart` | cart lines, add, merge rule (`samePosLine`), quantities, discounts |
| `useTender` | tender mode, split, cheque, UPI pending, cash pending, apply-advance |
| `useCheckout` | `checkout`, idempotency key, error routing, finish sale |
| `useTill` | shift state, drop lines, close |
| `useHolds` | server holds and bill sessions |
| `CustomerPicker`, `ProductSearch`, `CartTable`, `TenderPanel`, `BillBar` | presentational |

Rules: no behaviour change per PR, one module per PR, tests pass before and after, and remove the `eslint-disable` markers as each effect is replaced by derived state.

### P6-B. End-to-end tests (3 d)

Playwright against a seeded local stack. Flows: cash sale, UPI sale with manual confirm, credit sale and later cash collect, split pay, below-cost with approver, return with cash refund, exchange that applies the advance, offline cash sale then sync, till open, drop, close with variance. Run in CI on every PR that touches `pages/pos`, `sales/pos_*`, or `accounting/cash_shifts.py`.

The skeleton can land in week 2. Flows that need P1-A, P1-E, or Phase 3 are added when those phases merge, not before.

### P6-C. Accessibility (2–3 d)

| Step | Detail |
|---|---|
| 1 | Cart as a labelled table with row headers; quantity, batch, and remove controls reachable in tab order. |
| 2 | One polite live region for total and errors; assertive only for payment failure. |
| 3 | Focus management: after add, focus returns to the scan box; dialogs trap and restore focus. |
| 4 | Measure contrast, 200% zoom, and phone width. Write the numbers into the checks log. Leave the roadmap score cells blank. |
| 5 | Add `axe` to the e2e run. |

---

## Cross-cutting

**Migrations.** `0032` and later are written in the phase that needs them. Each one has a forward and backward test on Postgres and is reviewed for lock time on the large tables (`SalesInvoiceItem`, `CustomerReceipt`). The shift uniqueness migration aborts rather than merging open rows.

**Feature flags and rollout.** New behaviours that change posting or block a sale default off for existing companies and on for new ones: `pos_require_open_shift`, `pos_offline_credit`, the price-floor percent, weighted barcodes. Pilot shops are forced on for `pos_require_open_shift` during Phase 1. One pilot shop per phase for one week, then the wider default flips with notice. `pos_offline_credit` stays opt-in after the pilot unless that shop asks for it as the default.

**Secrets.** `PosApproverPin.hash` is a column. Phase 0.8 lists every `feature_flags` response; Phase 2 clears `pos_owner_pin_hash`.

**Data fix.** The `report_pos_cash_mispost` output feeds a one-off reclass by the accountant. Do not auto-post corrections. Re-run the report weekly until it returns zero rows.

**Observability.** Counters for: PIN failures, lockouts, approvals by scope, offline queue depth and age, sync failures by reason, offline credit parked over the cap, shift variance above a threshold, and checkout latency (p50, p95).

**Documentation.** Update `POS_Fix.md` (status column, POS-007, and the offline-credit reversal when P3-B ships). Leave roadmap score cells blank. Set R-09 to Partial until P1-E ships (done in this revision). Add a counter operator guide: open shift, drop, return, exchange, close, offline behaviour, and the offline-credit caps.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Shift uniqueness migration on live data | Failed migration or two open drawers | Copy-first dry run. Abort and `report_open_shifts` when one cashier has two open rows. Never pick a survivor. |
| Refund journal disagrees with the books | Double reversal of sales, or a second refund swallowed by the receipt's `REFUND` purpose | Dr 2300 / Cr cash or bank, sourced on the refund row. Accountant sees that shape before step 3 of P1-A. |
| Offline credit abuse | Over-limit sales | Opt-in setting. Device caps and the same caps at sync. Document exposure as cap times terminal count. |
| `PosPage` split causes regressions | Counter outage | One module per PR. E2e skeleton before the split; money flows added as each phase merges. |
| PIN migration drops the owner's hash | Overrides blocked | Copy into `PosApproverPin` and only then delete the flag, in one migration. |
| Scope creep in Phase 5 | Delay to returns and pharmacy | Committed work is P5-A, P5-A2, P5-E, and P5-F. Coupons, schemes, and gift cards stay out. |

## Definition of done (every item)

1. Code, migration, and tests merged. The new rule has a failing-before, passing-after test.
2. `ruff`, `tsc -b`, `eslint` (0 errors), `pytest`, and `vitest` pass on the touched areas. Postgres concurrency tests pass in CI.
3. Hindi and English strings added.
4. Audit rows written for any override, naming the approver.
5. A row in the checks log below records the check and its result. Roadmap score cells stay blank.
6. Pilot close, for posting, stock, GST, and shift changes only (Phase 1, P3-B, P4-E, Phase 5 money items): a pilot shop's day ties out for cash, stock, ledger, and GST. Catalogue sync, receipt layout, accessibility, and refactors use a device test, an `axe` run, or the e2e suite instead.

## Suggested sequence and staffing

| Weeks | Backend engineer | Web engineer |
|---|---|---|
| 1 | Phase 0, then P1-A | Phase 0, then P1-B web, P1-D web |
| 2–3 | P1-A, P1-C, P1-D, P1-E | P1-B, P6-B skeleton |
| 3–4 | P2-A, P2-B, P2-C | P2 web, P3-A web store |
| 4–6 | P3-A API, P3-B, P3-C, P3-D | P3-A, P3-B web, P3-C |
| 6–8 | P4-E, P4-A, P4-C | P4-A, P4-B, P4-D, P4-F |
| 8–10 | P5-A, P5-A2, P5-E | P5-A web, P6-C |
| 10–12 | P5-F; P5-C or P5-D only if a pilot has asked | P6-A split, after Phases 1–3 have stopped moving `PosPage.tsx` |

## Checks log

Score cells in `POS_Roadmap.md` are not filled from this table. Only a cashier study writes a score.

| Date | Item | Check | Result |
|---|---|---|---|
| 2026-10-07 | P1 money | `pytest tests/test_pos_plan_cash.py` | 16 passed. Bank refund skips 1100. Gateway refund posts no counter journal. Credit return accepts only advance. Partial pay is capped. Expected cash returns to the float. A pilot-day drop ties expected cash to 90. Split after advance creates no second receipt. |
| 2026-10-07 | P1 till, split, outage | `pytest tests/test_pos_plan_cash.py tests/test_pos_counter_policy.py` | 37 passed. A ₹20 till supplier payment plus a ₹10 drop leaves expected cash at ₹70, matching opening float plus the 1100 net minus drops. A 60/40 cash and UPI bill refunds as CASH 60 and BANK 40. Offline credit of ₹3,000 on two dates in one outage refuses the second bill; a new outage accepts it. |
| 2026-10-07 | Review fixes | `pytest tests/test_pos_plan_cash.py tests/test_pos_counter_policy.py` | 42 passed. A split refund credits the bank for the UPI part. A gateway refund cannot also be paid as cash. A shorter idempotency key does not replay a longer one. Offline UPI is refused. A stale credit-cache time is refused. Till cash is not counted on two open drawers. |
| 2026-10-07 | P2-A | `pytest tests/test_pos_counter_policy.py` | Passed with the cash-plan file (23 passed before the idempotency assertion change). Legacy hash still matches `pin_ok`. |
| 2026-10-07 | P4-C | `pytest tests/test_pdf_and_share.py -k thermal` | Passed. UPI QR stays off a fully paid bill. |
| 2026-10-07 | P3/P4 helpers | `vitest src/pages/pos/posPlan.test.ts` and `posRules.test.ts` | 10 passed. Weighted barcode, scale stable flag, catalogue age, offline credit opt-in, raster bit. |
| 2026-10-07 | Phase 0.3 | Local Postgres forward and back of migrations 0014 and 0031 | Not run. No `DATABASE_URL` in this session. |
| 2026-10-07 | Phase 0.4 | `report_pos_cash_mispost` on a production copy | Not run. Waiting on a data copy. |
| 2026-10-07 | P6-C | Contrast, 200% zoom, phone width, axe | Not measured. Cart table name is `pos.cart`. |
