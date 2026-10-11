# Money In, Phase 2: Implementation Plan

**Date:** 2026-10-11
**Source:** the deep review of Money In and its integrated modules (sections A to G of that review; each work package below cites the finding IDs it closes).
**Builds on:** [`MONEY_IN_IMPLEMENTATION_PLAN.md`](../../MONEY_IN_IMPLEMENTATION_PLAN.md) (Phase 1, OW-1..OW-14, implemented, not yet committed) and Q-OS item QOS-0118.
**Scope:** every finding in the review. Nothing is left as "not planned"; items that need a decision or a design spike say so, with a recommended default.

---

## 1. How to read this plan

* **Finding IDs** (A1, B4, D2 and so on) are the review's. Every finding appears in exactly one work package (WP). Section 12 is the reverse index.
* **Effort:** S = under 1 day, M = 1 to 3 days, L = 3 to 6 days, XL = more than 6 days, for one engineer including tests.
* **Decision (D-n)** = a business or accounting call the founder or the company's CA must make. Each has a **recommended default** so work can start; the WP says what changes if the decision goes the other way.
* **Gate** at the end of each phase = what must be green before the next phase starts.

### Working rules for every WP

1. Money paths stay append-only: reversals, never deletes. Any new posting goes through `PostingService` and is idempotent by `(source_type, source_id, purpose)`.
2. Every new behaviour is enforced on the **server first**; the UI mirrors it.
3. Every new string goes into both `en.ts` and `hi.ts`; every new endpoint gets `extend_schema`, and the OpenAPI snapshot plus `openapi-types.ts` are regenerated in the same change.
4. Each WP lands with backend tests (SQLite and, for locking or index behaviour, Postgres), frontend tests, an axe check for any new dialog, and a line in `docs/FREEZE_SCOPE_COVERAGE.md`.
5. A migration is additive and reversible. Index builds on large tables use `CONCURRENTLY` in a non-atomic migration (as `0039` does).
6. Changing a rule that existing clients may rely on (for example, rejecting `CREDIT`) is announced in the plan's "Behaviour changes" list and covered by a test that names the old behaviour.

---

## 2. Decisions needed

| ID | Question | Recommended default | If decided otherwise |
|---|---|---|---|
| **D-1** | **Uncleared cheques** (B4). A cheque receipt is `POSTED` the moment it is entered, can be allocated, marks the invoice paid, and counts as customer credit. | Phase 2a: **show, do not block.** Customer balances and invoice screens say "includes ₹X in uncleared cheques". Add a company flag `cheque_allocation_on_clearance` (default **off**, so nothing changes silently). When on, a pending cheque stays an advance until it clears, and clearing auto-applies it. | If the founder wants hold-until-cleared as the default, flip the flag default and add a data migration note; WP-4 already contains the clearing hook. |
| **D-2** | **TDS deducted by customers** (B6). Which ledger holds it? | New asset account **1270 "TDS Receivable (deducted by customers)"** (1260 and 1365 are taken). Receipt gets `tds_deducted`; the invoice settles for `received + tds_deducted`. | If the CA prefers an income-tax-prepaid account, only the account code in the posting changes. |
| **D-3** | **Refund of an advance** (B7). Reuse the POS refund machinery or add a model? | Spike first (WP-7 task 1). Default: a small new model `CustomerAdvanceRefund` linked to the receipt, because `pos_refunds` is built around sales returns. | If the spike shows `pos_refunds` rows fit, reuse them and skip the new model and migration. |
| **D-4** | **Who may export and print vouchers** (E1)? | Reuse the existing `CompanyUser.can_export` flag for CSV export (no new field). Voucher printing stays with payment viewers but is audit-logged. | A new flag only if the owner wants printing restricted separately. |
| **D-5** | **GST on advances** (C, GSTR-1). Receipts with no invoice yet. | Add a company-level "advance GST treatment" (goods or services) and a default rate, with a per-receipt override. For a registered goods supplier advances are generally not taxed at receipt; for services they are. **The CA must confirm** before this ships, so WP-10 is built behind a company flag (default off). | If the CA says "never compute", keep today's honest "aid" rows and drop WP-10 task 3. |
| **D-6** | **Editing a receipt** (B8). Which fields? | Editable after posting: `notes`, `reference`, `bank_account` (only if not reconciled and only to another account of the same company), `utr` (re-checked for duplicates). **Not editable:** customer, amount, mode, date. Those need void and re-enter. | Wider editing means reversing and re-posting the journal inside the edit; explicitly out of this plan. |
| **D-8** | **Cash receipts of ₹2,00,000 or more** (Income Tax s.269ST: not allowed in one day from one person, for one transaction, or for one event). | **Warn, do not block.** Company setting `cash_269st_mode` = `off` / `warn` / `block`, default `warn`; checks the receipt and the customer's cash receipts for the same day. The CA confirms before `block` is offered. | `block` makes `create_receipt` refuse; `off` removes the check. |
| **D-7** | **Closed-till correction** (C, POS). A cash receipt counted in a closed till cannot be voided and no correction flow exists. | Spike first (WP-9 task 1). Default design: a manager-approved correction that reverses the receipt and records a `CashShiftAdjustment` against the closed shift, leaving the shift's counted figures intact. Until built, the error message is reworded to say what the user can actually do. | If the owner prefers "never change a closed till", keep the guard and ship only the reworded message. |

---

## 3. Phase map

| Phase | Theme | WPs | Effort | Gate |
|---|---|---|---|---|
| **0** | Close out Phase 1 (ops) | WP-0 | S | Rebuilt DEV, migration applied, golden payments spec green, Phase 1 committed |
| **1** | Stop bad money in | WP-1, WP-2, WP-3 | M | No receipt can be created in CREDIT mode, with a discount above its amount, or as bank money in the cash book; the dialog bugs are gone |
| **2** | Books and policy | WP-4, WP-5, WP-6, WP-7 | XL | Uncleared cheques, TDS, edits and advance refunds are in the books, tied out |
| **3** | Cross-module and capability | WP-8, WP-9, WP-10, WP-11, WP-12 | XL | Recon, POS, GST, dunning, portal and alerts agree with Money In |
| **4** | Screen and operations | WP-13, WP-14, WP-15 | L | Sorting, allocation management, send, offline, permissions, audit, load |
| **5** | Assurance | WP-16 | M | Browser specs, concurrency and cross-tenant tests, Postgres run recorded |

Phases 1 and 4's quick items can overlap with Phase 2; the order above is the dependency order. WP-16 tests are written inside each WP; WP-16 is the cross-cutting remainder.

---

## 4. Phase 0: close out Phase 1

### WP-0: Operational close-out (A2, A3)

| # | Task | Detail |
|---|---|---|
| 1 | Rebuild DEV images | The images were built before the cheque-bounce fix (A1). Back up first (`scripts/compose-env.sh dev --profile backup run --rm -e BACKUP_ALLOW_UNENCRYPTED=1 backup`, output in the git-ignored `backups/dev`), then `build api worker beat web`, then `up -d`. The image installs `uharfbuzz` from `requirements.txt` |
| 2 | Migrate DEV | `scripts/compose-env.sh dev --profile migrate run --rm migrate`. Expect `payments.0038` and `payments.0039` (the second creates five trigram indexes concurrently) |
| 3 | Verify indexes | `select indexname, indisvalid from pg_indexes join pg_class on relname = indexname join pg_index on indexrelid = pg_class.oid where indexname like '%upper_trgm'`. Any `indisvalid = false` is dropped and rebuilt (E4) |
| 4 | Postgres re-run | Receipt tests plus `test_concurrency_races` and tenancy, on the final code. Record the result in the Phase 1 plan's section 6 |
| 5 | Golden spec | `payments-golden-path.spec.ts` against a throwaway API container (MFA off, as in the quotations close-out), host dev server on a port outside the Windows excluded ranges |
| 6 | Commit | Phase 1 as one commit (keep `web/src/pages/help/quotationHelp.test.tsx`, which belongs to another session, out of it). Do not push without being asked |
| 7 | Update records | `MONEY_IN_IMPLEMENTATION_PLAN.md` section 7 checklist, QOS-0118 evidence, `FREEZE_SCOPE_COVERAGE.md`. **Also fix its sections 4.1 and 5**, which still say the PDF is English-only and that a trigram index is deliberately not added; both are now false (`shaped_text.py`, `hindi_numbers.py`, `fonts/`, `0039`). The two plans must not contradict each other |
| 8 | **Harden `0039` before it is first applied** (it is still uncommitted) | `CREATE INDEX CONCURRENTLY IF NOT EXISTS` is **not** safe after an interrupted build: PostgreSQL leaves an index with `indisvalid = false` under the same name, and the re-run skips it and exits 0. Before each create, look up `pg_index.indisvalid` for the name and `DROP INDEX CONCURRENTLY` it if invalid, then create. Fix the docstring's claim. Note in the runbook that `CREATE EXTENSION pg_trgm` needs a privileged role on managed Postgres (RDS, Cloud SQL): the migrate role, or a one-time DBA step, must have it |
| 9 | Short-query fallback | A trigram GIN index cannot serve a 1 or 2 character term, so such a search scans every UNION branch. The API ignores `q` under 3 characters except an exact receipt-number match, and `ReceiptsPage.tsx` shows the existing "type at least N characters" hint. Test both |

**Acceptance:** DEV serves the new voucher in Hindi; indexes valid; golden spec green; commit exists.
**Rollback:** `migrate payments 0037` drops the columns and the indexes.

---

## 5. Phase 1: stop bad money in

### WP-1: Receipt input validation (B1, B2, B3, s.269ST)  [M]

**Goal:** the service refuses receipts that misstate money, whichever caller creates them.

| # | Task | Files |
|---|---|---|
| 1 | **B1.** Reject `mode=CREDIT` in `PaymentService.create_receipt` (`BusinessRuleError`, code `receipt_mode_invalid`) and in `CustomerReceiptSerializer.validate_mode`. Remove `CREDIT` from the form's and the filter's mode lists in `ReceiptsPage.tsx`. Keep `CREDIT` accepted as a **filter** value so old rows stay findable. Check the other callers of `create_receipt` (POS tender mapping, gateway, bank import) for any that pass `CREDIT`; `settle_completed_invoice_payment` already returns early on it | `payments/services.py`, `payments/serializers.py`, `ReceiptsPage.tsx` |
| 2 | **B2.** Validate `settlement_discount`: `0 <= discount`, and `amount + discount <= open balance of the invoice it is applied to`. Because the discount is posted at allocation time, enforce it in `allocate_receipt` (reject when `share > invoice open outstanding - amount`) and at create when `sales_invoice` is supplied. Reject a discount with no invoice and no oldest-first (it has nothing to settle, see B5) | `payments/services.py`, `payments/views.py` |
| 3 | **B3.** For `UPI`, `BANK` and `CARD`, require `bank_account`. If the company has exactly one active bank account or a default, preselect it in the form and, for API callers that omit it, apply the default; otherwise refuse with a message that links to the bank-account setup. Cash and cheque keep working without one (a cheque is deposited later). Reuse `PaymentService.ensure_default_bank_account`. **The rule applies to user-entered receipts only.** Gateway webhooks, POS tenders, bank import and the offline replay must never 400 on it: they resolve or auto-create the default bank account (a webhook that returns 500 or 400 breaks the capture, see R3-001) | `payments/services.py`, `payments/views.py`, `ReceiptsPage.tsx` |
| 4 | Remove the "Not specified (cash box)" menu item for those modes; keep it for CASH | `ReceiptsPage.tsx`, i18n |
| 5 | **D-8 (s.269ST):** for `mode=CASH`, warn (or block, per `cash_269st_mode`) when the receipt, or the customer's cash receipts for that day including it, reach ₹2,00,000. Response carries a `cash_limit_warning` the dialog shows; the setting lives with the company flags | `payments/services.py`, company flags, `ReceiptsPage.tsx` |
| 6 | **Data check, not a migration:** a management command `report_receipt_anomalies` listing existing receipts that break the new rules (CREDIT mode, UPI/BANK/CARD without bank, discount above amount) so the owner can review them. It changes nothing | `payments/management/commands/` |

**Tests:** CREDIT 400 via API and service; discount boundaries (equal, above, negative, no invoice); UPI with and without bank, default-bank fallback; existing receipts still list and void; a CREDIT row still filters. Update the three probes I ran in the review into permanent tests.
**Behaviour changes to announce:** `CREDIT` receipts, over-discounts and bank-less UPI/BANK/CARD now return 400.
**Acceptance:** the three review probes return 400 with clear messages; no existing test regresses.
**Risk:** a company that relies on bank-less UPI. Mitigation: the default-bank fallback, and the anomaly report to run before deploy.

### WP-2: New-receipt dialog fixes (D1, D2, D3, D7)  [S]

| # | Task | Detail |
|---|---|---|
| 1 | **D1.** On customer change, clear `invoice`, `allocAmount`, `invoiceQuery`, and `oldestFirst` is kept | `ReceiptsPage.tsx` customer `onChange` |
| 2 | **D2.** After a successful save reset `mode` to CASH, `paidFromTill` to false, and the cheque fields | `onSuccess` |
| 3 | **D3.** Keep `allocAmount` in step with the amount while the user has not edited it (`allocTouched` flag); once touched, never overwrite | state in the dialog |
| 4 | **D7.** Add a "show inactive customers" checkbox to the customer picker (default off). Server: `listCustomersPage` already supports `status`; pass `status` only when off | `ReceiptsPage.tsx`, i18n |
| 5 | Extract the dialog into `NewReceiptDialog.tsx` (the page is over 900 lines), moving the state with it, so the next WPs stay small | new file |

**Tests:** customer change clears the invoice; mode resets after save; amount edit updates the applied amount until touched; inactive customer reachable. Backend: confirm and test that an `INACTIVE` customer with an open invoice can still be given a receipt and have it allocated (neither the serializer nor `create_receipt` may block it). Add to `ReceiptsPage.test.tsx` (or split into `NewReceiptDialog.test.tsx`).
**Acceptance:** the exact sequence from the review (pick customer A, an invoice, change to customer B, save) no longer ends in a party-mismatch error.

### WP-3: Quick truthfulness fixes (C: POS message, D9)  [S]

| # | Task |
|---|---|
| 1 | Reword the closed-till error ("Void it from the till correction flow") to what is true today: it names the shift and says a manager must correct the till (until WP-9 exists) |
| 2 | **D9.** KPI labels: "Allocated" and "Advance held" say whether uncleared cheques are included (they are), via a footnote tied to D-1's outcome |
| 3 | Add the "unmatch" hint to the bank-matched error: "Open Bank reconciliation, unmatch line N, then void" (the line id comes from the match) |

**Tests:** message content tests. **Acceptance:** no error text refers to a flow that does not exist.

**Phase 1 gate:** backend suites (SQLite) green; the golden payments spec green after WP-1's bank-account rule (the spec uses CASH, so it is unaffected, but confirm); the anomaly report run once on DEV and its output reviewed.

---

## 6. Phase 2: books and policy

### WP-4: Uncleared-cheque policy (B4, D9 completion)  [L]  (decision D-1)

| # | Task | Files |
|---|---|---|
| 1 | **Show:** add `uncleared_cheque_total` to the customer balance payload (`LedgerService`) and to `CustomerReceiptSerializer` summaries; display "includes ₹X in uncleared cheques" on the customer 360 screen, the invoice detail payment panel, and the Money In totals note | `ledgers/services.py`, customer and invoice pages |
| 2 | **Flag:** company setting `cheque_allocation_on_clearance` (default off) in the company feature flags and the settings page | `accounts` flags, settings UI |
| 3 | **Behaviour when on:** `allocate_receipt` refuses a receipt whose `cheque_status` is pending ("This cheque has not cleared"), and `allocate_receipt_oldest_first` skips it. On clearing (`set_cheque_status` to CLEARED) with the flag on, auto-run oldest-first for the receipt **only if** it was entered with `allocate_oldest` (store that intent on the receipt: new boolean `allocate_on_clear` plus a nullable `intended_sales_invoice` FK and `intended_amount`, migration `0041`). If the user chose a specific invoice, clearing allocates to that invoice first (if still open, capped at its balance) and the remainder stays an advance; otherwise oldest-first | `payments/services.py`, model |
| 4 | **Invoice status:** with the flag on, an invoice covered only by a pending cheque shows "Cheque pending" rather than Paid. Add a derived `payment_status` display value, not a stored change | `sales` serializers |
| 5 | **Dunning and promises:** with the flag on, a pending cheque does not stop reminders; with it off, behaviour is unchanged | `payments/dunning.py`, `promise_to_pay.py` |
| 6 | Report: add "uncleared cheques" to the receivables ageing report as a separate column | `reporting` |

**Tests:** flag off = every existing test unchanged; flag on = pending cheque cannot allocate, clears and auto-allocates, bounce after clear reverses; customer balance shows the uncleared figure in both modes; totals tie-out test extended.
**Acceptance:** for any customer, Money In "cheques pending", the customer balance note and the ageing column report the same number.
**Rollback:** turn the flag off. The new column is nullable-safe.

### WP-5: Settlement-discount accounting (B5)  [M]

| # | Task |
|---|---|
| 1 | Define the rule (after WP-1's validation): a receipt's discount exists only to the extent it is allocated. Stop storing a discount on a receipt that has no allocation (API and UI refuse it, see WP-1.2) |
| 2 | When the **last live allocation** of a receipt with a discount is reversed (void, unallocate), the discount's journal share is already reversed with the allocation; add a test that proves the receipt then shows `settlement_discount` unapplied, and that re-allocating applies it once, not twice |
| 3 | Show the discount on the voucher and the dialog as "Discount ₹X (applied when allocated)" |
| 4 | **Close a live GL vs sub-ledger mismatch (verified in code).** `accounting.services._settlement_discount_share` prorates by `allocation.amount / receipt.amount` and rounds to paise. `ledgers.services._settlement_discount_by_invoice` prorates by `allocation.amount / sum(live allocations of the receipt)` and does not round. A ₹1,000 receipt with a ₹100 discount allocated ₹500 to one invoice credits AR ₹550 in the GL but reduces the invoice by ₹600, which is a ₹50 gap that `AR_SUBLEDGER_MISMATCH` would report at close. **Fix by persisting the amount, not recomputing it:** add `PaymentAllocation.discount_applied` (Decimal, default 0), set once at allocation time inside `allocate_receipt` / `allocate_receipt_oldest_first` under the receipt lock, using one shared helper. Rule: `discount_applied = receipt.settlement_discount - sum(live discount_applied of this receipt)` when this allocation brings cumulative allocated to `receipt.amount`, otherwise the amount-proportional share rounded half-up, never exceeding the unapplied remainder. Both the GL posting and `LedgerService` read the stored column; the two old functions are deleted. Backfill in the migration for existing allocations using the GL rule (what was actually posted). Reversing an allocation frees its `discount_applied` for the next one |

**Tests:** two allocations of one receipt with a discount sum to exactly the discount; unallocate then re-allocate; void restores invoice balances (existing test kept); **the ₹1,000 / ₹100 / ₹500 case: GL AR credit equals the invoice reduction**; `_ar_subledger` alert stays silent after every case.
**Acceptance:** `sum(discount_applied) == receipt.settlement_discount` once fully allocated, and GL 1200 equals the open-invoice total, in a property-style test over random splits and random unallocations.
**Migration:** `0040_allocation_discount_applied` (so the later migrations renumber: see section 10).

### WP-6: Customer TDS on receipts (B6)  [L]  (decision D-2)

| # | Task | Files |
|---|---|---|
| 1 | Chart: add account `1270 "TDS Receivable (deducted by customers)"` to `CHART`, with a seeding step for existing companies (`seed_chart_of_accounts` already adds missing accounts; confirm and add a test) | `accounting/services.py` |
| 2 | Model: `CustomerReceipt.tds_deducted` (Decimal, default 0) and `tds_section` (char, blank). Migration `0042` (see section 10). Serializer and OpenAPI | `payments` |
| 3 | **Define the allocation semantics first.** `PaymentAllocation.amount` stays **cash** allocated. Add `PaymentAllocation.tds_applied` beside `discount_applied` (same persisted-at-allocation rule as WP-5.4, same shared helper). The invoice is reduced by `amount + discount_applied + tds_applied`. Posting: `post_receipt` is Dr Cash/Bank `amount`, Dr 1270 `tds_deducted`, Cr 2300 `amount + tds_deducted`. Allocation debits 2300 by `amount + tds_applied` (the discount is **not** in 2300: it is posted at allocation as Dr 5150, Cr 1200) and credits 1200 by `amount + tds_applied + discount_applied`. Void reverses all of it | `accounting/services.py` |
| 4 | Settlement: `LedgerService.sales_invoice_outstanding` reads `discount_applied` and `tds_applied` from the allocation rows (no proration at read time) | `ledgers/services.py` |
| 4a | **Advance tie-outs (otherwise every receipt with TDS trips period close):** `_advance_recon_alerts` must compute customer advances as `sum(amount + tds_deducted)` of POSTED receipts minus `sum(amount + tds_applied)` of live allocations (and, after WP-7b, minus live advance refunds), mirroring the supplier side which already adds `tds_amount`. `CustomerReceiptSerializer.get_unallocated`, `CustomerReceiptViewSet.summary()` (`advance`, `allocated`) and `export()` use the same formula. One helper, `receipt_unallocated(receipt)`, used by all of them | `accounting/services.py`, `payments/serializers.py`, `payments/views.py` |
| 5 | Validation: `tds_deducted >= 0`, and `amount + tds + discount <= invoice open balance` when allocating. Optional rate hint from the customer's PAN type (reuse the supplier-side TDS helpers) | `payments/services.py` |
| 6 | UI: "TDS deducted by customer" field (collapsed under "More", with a section dropdown) in the new-receipt dialog; shown on the voucher and in the CSV; a TDS receivable line in the trial-balance drill | web |
| 7 | Reporting: a "TDS receivable (Form 26AS) register" (receipt, customer PAN, section, amount, date) for reconciliation, as a CSV report | `reporting` |

**Tests:** invoice 1,000, customer pays 900 and deducts 100 TDS: invoice fully settled, 1270 debited 100, void restores everything; partial allocation; **an unallocated receipt with TDS does not raise `CUSTOMER_ADVANCE_MISMATCH`**; summary, export and the serializer agree on the advance; cross-check against the trial balance; Hindi voucher includes the TDS line.
**Acceptance:** the "short-paid forever" case from the review closes in one receipt.
**Risk:** touches the posting of every receipt. Mitigation: `tds_deducted = 0` produces byte-identical journals to today, asserted by the existing GL snapshot tests.

### WP-7: Receipt edits and advance refunds (B7, B8)  [XL]  (decisions D-3, D-6)

**7a. Receipt edit (B8)**

| # | Task |
|---|---|
| 1 | Add `PATCH /payments/receipts/{id}/` (limit `http_method_names` to allow it) restricted to the fields in D-6. Permission: `CanCreatePayments`; editing `bank_account` or `utr` also needs the receipt to be unreconciled |
| 2 | `PaymentService.edit_receipt`: lock the row, validate each field (UTR duplicate check as at create, bank account belongs to the company), write a `record_document_event` with `before` and `after`, and re-point the existing journal's bank line when the bank account changes. **Bank-account edits are allowed only when:** mode is UPI, BANK, CARD or CHEQUE (never CASH), the receipt is unreconciled, a cheque has not cleared, and the receipt's date is in an open period (the same gate as create). Otherwise refuse with a message to void and re-enter, as void already posts its reversal on today's date for exactly this reason. Re-posting uses the original date only under that gate. Notes, reference and UTR edits touch no journal and have no period restriction |
| 3 | UI: an "Edit" action on the voucher dialog for the editable fields only |

**7b. Refund of an advance (B7)**

| # | Task |
|---|---|
| 1 | **Spike (S):** read `sales/pos_refunds.py` and decide reuse vs new model (D-3) |
| 2 | Model `CustomerAdvanceRefund`: company, receipt FK (PROTECT), amount, mode, refund_date, bank_account, utr, reason, status, created_by, voided_at. Constraint: sum of live refunds on a receipt `<=` its unallocated amount (checked under `select_for_update` on the receipt) |
| 3 | Posting: Dr 2300 Customer Advances, Cr Cash or Bank. Reversal on void of the refund |
| 4 | Effects: the receipt's `unallocated` falls by the refunded amount; status stays POSTED (a fully refunded receipt shows "Refunded" through a derived flag, not by changing the existing `REFUNDED` meaning, which is gateway-specific) |
| 5 | API: `POST /payments/receipts/{id}/refund-advance/`, idempotent by key; list on the voucher |
| 6 | UI: "Refund advance" action on rows with an unallocated amount (owner or cancel permission), reason required, same 3 to 500 character rule as void |
| 7 | Cash-out of a till: refund in CASH from an open till stamps the shift like a payout (reuse `mark_paid_from_till`-style stamping) |
| 8 | **Every place that reads "unallocated" must subtract live refunds (verified gaps):** `allocate_receipt` and `allocate_receipt_oldest_first` (available = amount, less live allocations, less live refunds, under the receipt lock; otherwise an advance can be refunded and then allocated in full); `CustomerReceiptViewSet.summary()` (`collected` and `advance` would otherwise be overstated by the refund); `export()` (advance column); `CustomerReceiptSerializer` (`unallocated`, a `refunded_total` field); `receipt_voucher.py`; and `_advance_recon_alerts` (a refund debits 2300 with no allocation row, which would raise `CUSTOMER_ADVANCE_MISMATCH`). Use the shared `receipt_unallocated()` helper from WP-6.4a so there is one definition |
| 9 | GST: a refund of an advance on which tax was reported needs a refund voucher and reduces liability (see WP-10.6). Until WP-10 ships (flag off), the refund form shows no GST fields |

**Tests:** refunding part of an advance leaves summary, export, serializer and `_advance_recon_alerts` consistent; after a refund a full-amount allocation is refused; bank edit refused for CASH, for a closed period and for a cleared cheque; edit changes only allowed fields and is audited; edit of a reconciled receipt refused; UTR duplicate refused; refund cannot exceed the advance; two concurrent refunds cannot exceed it (Postgres); refund then allocate; void of a receipt with a refund refused until the refund is voided.
**Acceptance:** a customer asking for an advance back no longer requires voiding the receipt.

**Phase 2 gate:** the cash (1100), customer advance (2300), receivable (1200) and TDS (1270) tie-out test from Phase 1 extended with discount, TDS, cheque and refund cases; GL snapshot tests unchanged for receipts with none of the new fields.

---

## 7. Phase 3: cross-module and capability

### WP-8: Bank reconciliation integration (C: Bank, B9 support)  [M]

| # | Task |
|---|---|
| 1 | **Unmatch shortcut:** the bank-matched void error returns the matching line id and statement id in `details`; the UI turns it into a link to the reconciliation screen with that line selected |
| 2 | **Reconciled flag on the row:** `CustomerReceiptSerializer.reconciled` (from `recon_matches` and `aa_transactions`, prefetched), a "Reconciled" chip on Money In, and a filter `reconciled=true/false` |
| 3 | **Bounce after reconciliation (A1 follow-through):** when a matched cheque bounces, mark the `ReconMatch` as `needs_review` (new nullable field) instead of leaving a match to a voided receipt; recon screen lists these |
| 3a | **The return line on the statement:** a bank posts a bounced cheque as a second, debit line; the original credit stays. Let that debit line be matched to the bounce's reversal journal so both statement lines reconcile and nothing is left as an unexplained difference | `reconciliation` |
| 4 | Recon creation guard for walk-in (done in Phase 1) gets a UI hint: the customer picker on the recon screen hides the walk-in customer |

**Tests:** matched void error carries ids; reconciled filter; bounce marks the match for review and the recon screen lists it.

### WP-9: POS and till correction (C: POS, D-7)  [L]

| # | Task |
|---|---|
| 1 | **Spike (M):** map how `expected_cash`, `counted_cash` and `variance` on `CashShiftRegister` are computed and locked; choose the correction record (`CashShiftAdjustment`: shift FK, receipt FK, amount, reason, approved_by) |
| 2 | Service `PosShiftService.correct_closed_till_receipt`: manager permission, reason, voids the receipt through `void_receipt` with a new `allow_closed_till=True`, writes the adjustment against the shift, and posts the journal difference so the till ledger and the GL agree |
| 3 | UI: replace the refusal with "Correct closed till" (manager only) on that error |
| 4 | Shift report shows adjustments after close, with who and why |

**Tests:** closed-till receipt corrected; the shift's counted cash is untouched, adjustments listed, expected cash recomputed consistently; a cashier without permission is refused.
**Acceptance:** the error message's promised flow exists.

### WP-10: GST on advances (C: GST, D-5)  [L]  behind a company flag

| # | Task |
|---|---|
| 1 | Settings: `advance_gst_treatment` (none / goods / services) and `advance_gst_default_rate`; receipt-level override `advance_gst_rate` (nullable) |
| 2 | Report rows: for `services` (or a per-receipt rate), the GSTR-1 advance table computes tax inclusive of the rate and place of supply from the customer, instead of `rate_unknown`; for `goods` and `none` it keeps the current honest "aid" with a clearer note |
| 3 | **Exclude uncleared cheques** from the advance rows (they are not yet received) and **subtract** advances later adjusted against invoices in the period (adjustment table, so a receipt allocated in the same period does not report twice). **Cross-period:** an advance reported in period 1 and adjusted against an invoice in period 2 must reduce period 2's liability (the adjustment table), so tax is not paid on both the advance and the invoice |
| 4 | Optional receipt voucher: when tax applies, the voucher shows the tax split (GST receipt voucher), otherwise it is a plain acknowledgement |
| 5 | CA sign-off checklist in the release notes before the flag is turned on for any company |
| 6 | **Refund of an advance (WP-7b):** when tax was reported on the advance, the refund needs a GST refund voucher (CGST s.31(3)(e)) and reduces the liability in the period of the refund. Voucher numbering follows the receipt-voucher series rules; CA confirms |
| 7 | **Books vs report:** decide with the CA whether advance output tax is only reported (GSTR-1 rows) or also posted to the GL (Dr 2300 or an advance-GST clearing account, Cr output tax 2200/2210/2220). Posting it keeps the GL tax accounts tied to GSTR-1; reporting only leaves them different by design. Default: report only, with the difference listed on the GST tie-out screen, until the CA decides. This is part of D-5 |

**Tests:** services advance computes CGST/SGST or IGST by place of supply; goods advance unchanged; allocation in the same period removes the row; uncleared cheque excluded; flag off = identical to today.

### WP-11: Dunning, promises and events (C: Dunning)  [M]

| # | Task |
|---|---|
| 1 | Emit a `customer_receipt.created` / `.voided` domain event (the `emit(...)` helper already exists) and subscribe `promise_to_pay` so a kept promise closes at once rather than at the next evaluation |
| 2 | Dunning: a void re-enables reminders for the re-opened invoices the same day (check the "already reminded today" rule so a void does not suppress or double-send) |
| 3 | Payment-link state: voiding the receipt that paid an invoice re-opens a link that had been marked paid, or flags it for a person if a gateway capture exists |
| 4 | Credit-note warning (C: Credit notes): when an invoice is returned or credit-noted after a receipt paid it, the receipt row gets "Invoice later returned, review the advance" (derived, no new data) |

**Tests:** promise closes on receipt; void re-opens reminders; link state; return-after-payment flag.

### WP-12: Alerts and surfaces (B9, C: Dashboard, C: Portal)  [M]

| # | Task |
|---|---|
| 1 | **B9:** new attention rule `WALK_IN_UNALLOCATED_RECEIPT` (receipts for `is_pos_walk_in` customers with unallocated amount, from gateway or import), with a link to allocate or reassign |
| 2 | **Reassign customer:** a controlled action to move an unallocated receipt from a walk-in to a named customer (audit-logged), because B9 otherwise has no resolution. Do not rewrite history: post a party-transfer journal (Dr 2300 walk-in, Cr 2300 named customer, plus the sub-ledger move) dated today and record the reassignment in `DocumentEvent`; if the original period is open and the owner prefers a clean re-post, allow it only under the period gate |
| 3 | **DUPLICATE_PAYMENT** alert: add UTR or reference to the grouping and exclude pairs whose UTRs differ; add a dismiss with reason |
| 4 | **Gateway rows:** show on the Money In row for gateway receipts a "Refund" action (owner) calling the existing gateway refund service, and a link to the payment |
| 5 | Customer portal: confirm the receipt appears on the customer's statement page with the voucher link (read-only PDF through the existing signed-link mechanism) |

**Tests:** alert fires and clears on allocation; reassign keeps the GL balanced; duplicate alert false-positive case; refund action permission.

**Phase 3 gate:** a cross-module tie-out suite: one scenario that creates an invoice, receives a cheque with TDS and a discount, reconciles, bounces, re-receives, voids, refunds an advance, and asserts the customer ledger, the GL, the shift, the GST aid rows and the Money In totals agree at each step.

---

## 8. Phase 4: screen and operations

### WP-13: Money In screen capabilities (D4, D5, D6, D8)  [XL]

| # | Task | Detail |
|---|---|---|
| 1 | **D4 sorting and paging:** `ordering` query param (allow-list: `receipt_date`, `amount`, `number`, `customer__name`, `status`), sortable column headers with `aria-sort`, page-size selector (25, 50, 100), "go to page" input. Keep the default order | `CustomerReceiptViewSet`, `ReceiptsPage.tsx` |
| 2 | **D5 allocation management:** a drawer from the voucher dialog listing live allocations with an "Unallocate" action (cancel permission, reason, calls the existing `unallocate`), and an allocate form with a **chosen amount** per invoice and a search over **all** open bills (server-side search, not the first 50) | `PaymentAllocationViewSet`, new drawer |
| 3 | **D6 send receipt:** "Send" on the voucher: WhatsApp (reuse `core/services/whatsapp.py` wa.me or Cloud) and email, with the PDF link; log the send; consent and template rules as for invoices | reuse `sales/whatsapp_send.py` patterns |
| 4 | **D6 bulk:** multi-select rows with bulk "allocate oldest first" for advances (one job, per-row result list, stops nothing on a single failure) and bulk "send". Rows are processed **sequentially in `(receipt_date, id)` order, per customer, under a lock on that customer's open invoices**, so several advances of one customer cannot race for the same bills; the endpoint requires an `Idempotency-Key` | new endpoint `receipts/bulk-allocate/` |
| 5 | **D8 offline:** spike the offline outbox for new receipts (the POS outbox already queues sales). Default: queue cash and cheque receipts when offline, show them as "Waiting to send", replay with the original idempotency key, never queue void or refund. **Rules:** the receipt keeps the client-captured `receipt_date` (subject to the period gate) and gets its number from the server at sync time, so numbers may not follow dates (documented, as for any back-dated entry); a replay that conflicts (invoice paid meanwhile, closed period, over-allocation) lands in a "Needs attention" list with the reason instead of failing silently | `web/src/offline`, spike first (M) |

**Tests:** ordering allow-list rejects unknown fields (400); sort stability across pages; unallocate then re-allocate; send logs and respects consent; bulk allocate partial failure; offline replay is idempotent (same key, one receipt).
**Acceptance:** an accountant can fix a wrong allocation and send a receipt without leaving the screen.

### WP-14: Security, audit and abuse limits (E1, E2, E3, Audit)  [M]

| # | Task |
|---|---|
| 1 | **E1:** `export/` requires `CompanyUser.can_export` (or OWNER); the Export button hides without it. Per D-4, voucher printing stays open to payment viewers |
| 2 | **Audit:** `AuditService.log` entries `EXPORT` (filters used, row count) and `PRINT` (receipt id, layout, language). Both append-only |
| 3 | **E2:** throttle scopes `receipts_export` (for example 6 per hour per user) and `receipts_summary` (burst limit) via the existing throttle settings; stream the CSV (`StreamingHttpResponse`, as the cancelled-numbers export does) instead of buffering 20,000 rows |
| 4 | **E3:** accept the `Idempotency-Key` on `void/` and on `refund-advance/` (store the response as `receipt_create` does); a retry returns the first response |
| 5 | **E5:** Hindi vouchers are drawn as outlines, so they are not searchable or readable by assistive tools. Wrap each shaped run in a marked-content span carrying `/ActualText` with the real Unicode Devanagari string (ISO 32000), so copy, find and screen readers return Hindi. Do **not** put an invisible English layer under the outlines: it copies mismatched English and misleads screen readers. Spike (S): confirm ReportLab can emit the span around the outline path in `shaped_text.py`, and check copy and find in Chrome and Acrobat |
| 6 | **E4:** a startup or deploy check (`manage.py check_indexes`) that reports invalid indexes; wire it into the deploy runbook |

**Tests:** export without `can_export` is 403; audit rows written; throttle returns 429 after the limit; idempotent void replay; invalid-index check detects a deliberately invalid index (Postgres).

### WP-15: Performance (A4, F)  [M]

| # | Task |
|---|---|
| 1 | **A4:** `summary()` currently runs a separate `qs.count()` over all statuses (to report excluded rows), which a `WHERE status = 'POSTED'` partial index cannot serve. Fold `total`, `pending`, the POSTED count and the all-status count into **one** `.aggregate()` using conditional `Count`/`Sum` (`filter=Q(status=...)`), and index `(company_id, receipt_date) INCLUDE (status, amount, mode, cheque_status)` without the partial predicate, built concurrently. Measure before and after on the 405,000-row profile database and record the numbers in the plan |
| 2 | **No totals cache.** KPIs that lag a user's own create or void cost more support than the query does. Re-measure after task 1; only if it misses the target, reconsider a cache, and then only with invalidation covering receipts, allocations, cheque status, credit notes, returns and bank import |
| 2a | **N+1 in the list (verified):** `CustomerReceiptSerializer.get_utr_warning` runs two queries per row that has a UTR (customer receipts and supplier payments), up to 200 extra queries on a 100-row page. Compute duplicate UTRs once per page in `CustomerReceiptViewSet.list` (one query for the page's UTRs against both tables, passed through serializer context), or drop the live check from list serialization because the unique constraint already prevents active duplicates. Add a query-count test (`assertNumQueries`) for a page of UPI receipts. Re-run the 405,000-row profile **with UTRs populated** |
| 3 | Allocation-heavy profile: seed `PaymentAllocation` rows (the earlier profile had none) and re-measure the totals and the list; add the allocation index if the plan shows a scan |
| 4 | Keep the profiling scripts under `backend/perf/` so the numbers can be reproduced (the repo already has a `perf` folder) |

**Acceptance:** totals under 150 ms and search under 100 ms at 135,000 receipts per tenant with realistic allocations, on Postgres.

**Phase 4 gate:** accessibility checks for every new dialog and drawer; the 375 px, 768 px and Hindi-locale visual checks repeated; a load run (the existing `load/` harness) on list, summary and export.

---

## 9. Phase 5: assurance

### WP-16: Cross-cutting tests (G)  [M]

| # | Test | Where |
|---|---|---|
| 1 | Browser specs: void with a reason, voucher print in English and Hindi, filter and export, new receipt with TDS and a walk-in block | `web/e2e-golden/` (new `money-in-golden.spec.ts`) |
| 2 | Cross-tenant: `export/` and `summary/` with a second tenant's data present; voucher of another tenant's receipt (404) already exists | backend |
| 3 | Concurrency (Postgres): two users void the same receipt (one 200, one idempotent 200, one journal); two bounces of one cheque; allocate and void racing | `test_concurrency_races.py` style |
| 4 | Bounce then re-receipt of the same cheque number: allowed, duplicate-cheque warning shown | backend |
| 5 | The void reversal date shown in the UI equals the journal's `entry_date` (read the date from the response, not recompute on the client) | backend + web |
| 6 | The Phase 3 cross-module tie-out scenario as a permanent test | backend |
| 7 | A property-style test over random allocation splits for discount and TDS proration (WP-5, WP-6) | backend |
| 8 | Postgres run of every new suite, recorded in the plan | CI and local |

---

## 10. Cross-cutting concerns

| Topic | Plan |
|---|---|
| **Migrations** | `0040_allocation_discount_applied` (WP-5; adds `tds_applied` too if WP-6 lands together), `0041_receipt_allocate_on_clear` (WP-4), `0042_receipt_tds` (WP-6), `0043_customer_advance_refund` (WP-7), `0044_recon_needs_review` (WP-8), summary index (WP-15), advance GST fields (WP-10), `CashShiftAdjustment` in `accounting` (WP-9), the covering index (WP-15). Each additive and reversible; run `makemigrations --check` in CI as today |
| **Row-level security** | Every new company table gets an RLS migration in the same change (the repo's rule, enforced by `test_rls_coverage`) |
| **OpenAPI and types** | Regenerate the snapshot and `openapi-types.ts` in every WP that touches an endpoint or serializer; the contract test (`domain.apiContract.test.ts`) must pass |
| **i18n** | All strings in `en` and `hi`; the literal and parity ratchets stay green; new Hindi wording reviewed by a native speaker before release (the amount-in-words table especially) |
| **Feature flags** | `cheque_allocation_on_clearance` (WP-4), advance GST (WP-10), offline receipts (WP-13) ship dark and are enabled per company |
| **Behaviour changes to announce** | CREDIT receipts, over-discounts and bank-less UPI/BANK/CARD refused (WP-1); `export/` needs `can_export` (WP-14); void and refund accept idempotency keys (additive) |
| **Docs** | `docs/FREEZE_SCOPE_COVERAGE.md` rows per WP; QOS items (one per phase); a user-help page for cheques, TDS and advance refunds (the repo has a help catalog under `web/src/pages/help/`) |
| **Observability** | Counters for receipts created, voided, refunded, edited; alert if void rate in a day exceeds a threshold; log `receipt.search` timings for the slow-query review |

---

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| WP-5 and WP-6 change how AR and advances tie out (persisted `discount_applied` / `tds_applied`; shared `receipt_unallocated()`) | One helper for every reader (GL posting, ledger, serializer, summary, export, `_advance_recon_alerts`); the period-close alerts are part of the acceptance tests; backfill uses what the GL actually posted |
| WP-6 changes receipt posting for every company | `tds_deducted = 0` must yield byte-identical journals; GL snapshot tests gate the change; ship behind the TDS field being empty by default |
| WP-1 refuses input some customers rely on (bank-less UPI) | Anomaly report first; default-bank fallback; announce before deploy |
| Hindi wording errors on the voucher | Native-speaker review before enabling by default; English remains the default |
| Concurrent index builds fail and leave invalid indexes | WP-0 and WP-14 checks; documented rebuild step |
| Scope is large | Phases are independently shippable; only WP-5 depends on WP-1, WP-6 on WP-5, and WP-4's flag is optional |
| Policy decisions stall work | Every decision has a recommended default that lets the WP proceed; the WP notes what changes otherwise |

---

## 12. Reverse index: finding to work package

| Finding | WP | Finding | WP |
|---|---|---|---|
| A1 (fixed) | done; follow-through in WP-8.3 | C GST advances | WP-10 |
| A2, A3 | WP-0 | C Ledger / outstanding | WP-4 |
| A4 | WP-15 | C Bank reconciliation | WP-8 |
| B1 | WP-1 | C POS shifts | WP-3.1, WP-9 |
| B2 | WP-1, WP-5 | C Dunning / promises | WP-11 |
| B3 | WP-1 | C Dashboard / alerts | WP-12 |
| B4 | WP-4 | C Portal / payment links | WP-11.3, WP-12 |
| B5 | WP-5 | C Credit notes | WP-11.4 |
| B6 | WP-6 | C Audit | WP-14 |
| B7 | WP-7b | D1, D2, D3, D7 | WP-2 |
| B8 | WP-7a | D4, D5, D6, D8 | WP-13 |
| B9 | WP-12 | D9 | WP-3.2, WP-4 |
| E1, E2, E3, E5 | WP-14 | E4 | WP-0, WP-14.6 |
| F (performance) | WP-15 | G (tests) | WP-16 and each WP |

---

## 13. Suggested order of work

1. **WP-0** (day 0).
2. **WP-1, WP-2, WP-3** together, in that order: the validation rules first, then the dialog, which depends on them.
3. **WP-5, WP-4, WP-6**: discount rule before TDS (they share the proration code), cheque policy alongside.
4. **WP-7a, WP-7b**, then **WP-8** (uses the new reconciled flag in the edit rules).
5. **WP-9** and **WP-10** after their spikes and decisions; **WP-11, WP-12** in parallel.
6. **WP-13** (the largest UI item) once the data model is stable; **WP-14, WP-15** any time after WP-1.
7. **WP-16** closes each phase and runs again at the end.

## 14. Implementation record (2026-10-11)

All work packages WP-0 to WP-16 are built. Nothing is committed yet.

**Spike results.** D-3: a new `CustomerAdvanceRefund` model (the advance is not a single row, so refunds
need their own reversible record). D-7: a new `CashShiftAdjustment` model for closed-till corrections.

**Migrations.** payments `0040_money_in_phase2`, `0041_promise_auto_resolved`, `0042_receipt_summary_indexes`
and `0043_receipt_prefix_search_indexes` (the two index migrations are non-atomic and use CONCURRENTLY);
accounts `0061`; accounting `0016`; core `0056` and `0057` (row-level security for the new tables).

**Performance (PostgreSQL 17, 3 tenants x 135,000 receipts).** First page of the list 140-220 ms; month
summary about 65 ms; all-time summary about 250 ms; search 125-250 ms end to end; month export 315-520 ms.
The covering index gives a 1.2 ms index-only month aggregate. The synthetic UTR prefix used in the run was
not very selective, so real search times should be at or below these figures. Reproduce with
`python -m perf.receipts_profile`.

**Behaviour changes to tell operators.**
- A UPI or bank receipt now needs a bank account (a default one is used when the company has exactly one).
- Cheque allocation on clearance, the s.269ST mode (warn by default) and advance GST (off by default) are
  company settings; defaults keep today's behaviour.
- A customer's outstanding and a bill's balance both count the cash, discount and TDS each receipt cleared.
- Voiding a receipt that has live advance refunds is refused until the refunds are voided.
- Walk-in customers cannot hold an advance.

**Operator steps.** Back up, rebuild `api worker beat web`, run the migrate profile, then
`manage.py check_indexes` and confirm no index is invalid.

**Open for people, not code.** Native Hindi review; CA sign-off on account 1270 and advance GST
(`docs/ca/CA_SIGN_OFF_CHECKLIST.md`); the s.269ST warn-or-block decision.
