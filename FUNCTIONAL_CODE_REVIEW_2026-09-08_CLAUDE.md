# Functional Code Review — Bizboard (production stabilization)
Run date: 2026-09-08 · Reviewer: Claude · Build: `5ba05c7` (branch `main`, dirty working tree)

## Scope of this pass

One focused session. I traced the **core money- and stock-moving write paths** end to end
(view → serializer → service → inventory service → ledger/COGS service → events → on_commit)
for POS, Sales, Purchase, Stock/Godown, plus the idempotency plumbing, the offline outbox,
and the derived-ledger/outstanding layer. Reporting and Accounting were surveyed at the query
level (company-scoping, status filters, date bounds) rather than reconciled figure-by-figure.

**Headline:** the paths in scope are, with few exceptions, already hardened. The prior-audit
fault patterns (oversell races, idempotency scope typos, non-atomic completion, cross-tenant
querysets, per-line rounding residuals, draft-number burning) were checked and are **held** in
the code I read. `post_movement` locks the `StockBalance` row before the authoritative
negative-stock re-check; every money/stock POST in scope maps to a scope string that is
present in `MONEY_IDEMPOTENCY_SCOPES`; completion is one `transaction.atomic` with side
effects on `transaction.on_commit`; querysets go through `CompanyScopedViewSet` /
`CompanyPrimaryKeyRelatedField`; `LedgerService` is fully document-derived with no cached
balance table.

The findings below are what survived that trace. None is a Critical. Two are latent
data-integrity risks that are currently shielded by an upstream guard; the rest are Low.

## Coverage summary
- Modules reviewed: 4 deep (POS, Sales, Purchase, Stock/Godown) + 2 surveyed (Reporting, Accounting) — 4/6 to the checklist standard
- Findings: 0 Critical, 0 High, 1 Medium, 4 Low
- Test suite: **1292 passed, 57 skipped, 0 failed** (SQLite, Python 3.13, 5m24s). Caveat: the concurrency/race suite is Postgres-only and did not run locally — see "Test suite".

## Fixes applied — 2026-09-09

CR-001, CR-002, CR-003 fixed. CR-004 reviewed and left as-is (working as designed).
Regression tests: `backend/tests/test_review_2026_09_fixes.py` (7 tests, all green; the three
behavioural fixes were each verified to fail against the pre-fix code). Full suite re-run
after the changes: **1303 passed, 57 skipped, 0 failed**.

| # | Outcome | Files |
|---|---|---|
| CR-001 | **Fixed.** `PurchaseService.set_items` now **rejects any quantity change on a `COMPLETED` purchase** (twin of `SalesService.set_items` CR-024/CR-128) — a qty correction must go through a debit/credit note or a purchase return. The unreachable-but-buggy in-place qty-delta path (posted a `purchase_invoice_edit` ADJUSTMENT that `cancel()` never reversed) was removed; the completed-invoice branch now only refreshes GL for price/discount amends. | `backend/purchases/services.py` |
| CR-002 | **Fixed.** The purchase-cancel stock-headroom guard now keys on `company.negative_stock_policy == "BLOCK"` instead of the non-existent `Company.allow_negative_stock` attribute. BLOCK behaviour is unchanged (correct); a WARN-policy company can now cancel a purchase whose stock has since moved, consistent with how WARN is honoured everywhere else. | `backend/purchases/services.py` |
| CR-003 | **Fixed.** `pos_checkout` now **caps the recorded receipt at the invoice total** — any over-tender is change returned in cash, recorded in the receipt note, and is no longer booked as a silent unallocated advance on the walk-in customer (GL 2300). A smaller `amount` is still honoured as a part-payment. | `backend/sales/views.py` |
| CR-004 | **Won't fix — working as designed.** Adding `insufficient_stock` / `credit_limit_exceeded` to `TRANSIENT_4XX_CODES` was tried and reverted: it contradicts the deliberate W0-05 contract ("deterministic 4xx are stored") and its test `test_w0_05_deterministic_4xx_stored`, which pins `CREDIT_LIMIT_EXCEEDED` as the canonical stored-4xx example. A retry after the condition clears must use a **fresh** Idempotency-Key. The one automated retrier that reuses `<key>-complete` (offline `flushPosCheckout.ts`) already does exactly that — it probes the invoice status and rotates the key on a confirmed-`DRAFT` failure. Test `test_cr004_deterministic_4xx_on_complete_is_stored_and_needs_a_fresh_key` documents the contract. Any *future* automated retrier must rotate its key on a non-transient 400. | — (no change) |

## Coverage matrix
| Module | Core write path reviewed | Reversal path | Concurrency | Tests present | Findings |
|---|---|---|---|---|---|
| POS | `POST /sales/invoices/pos-checkout` (create+complete+receipt+allocate, one txn, `pos_checkout` idempotency) + offline `flushPosDraft` | via `SalesInvoice.cancel` | invoice+customer `select_for_update`; `post_movement` row lock | present (`test_wave4_rbac`, `flushPosCheckout.test.ts`) | CR-003 |
| Sales | `SalesService.complete` / `set_items` / `convert_quotation` / SO+DC conversions | `cancel`, `complete_return` / `cancel_return`, CN/DN complete/cancel | `select_for_update` on invoice/customer/SO/challan; number assigned in-txn | broad | CR-004 (obs) |
| Purchase | `PurchaseService.complete` / `set_items` / `cancel` / `complete_return` / BoE + bill import commit | `cancel`, `complete_return`, CN/DN | `select_for_update` on invoice/supplier; twin of sales | broad | CR-001, CR-002 |
| Stock/Godown | `InventoryService.post_movement`, `post_opening*`, `StockTransferService.complete` / `cancel`, reserve/release, FIFO layers | transfer cancel, sales/purchase cancel restore, `restore_fifo_peels` / `retire_source_layers` | balance row `select_for_update` before re-check; sorted-warehouse lock order | present (`test_stock_flow`, `test_concurrency_races`) | — |
| Reporting | GSTR-1/2B/3B builders, `accounting/reports.py` (TB/P&L/BS/cash-flow) — company scope + status/date filters only | n/a | n/a | present | — (survey only) |
| Accounting | `LedgerService` outstanding/exposure (document-derived), period gates called from every complete/cancel/allocate | reversal via `PostingService.reverse` on cancellation date | `select_for_update` on JE in reversal | present | — (survey only) |

---

## Findings

### CR-001 — `PurchaseService.set_items` has a completed-invoice quantity-delta branch with no reversal on cancel and a broken headroom guard
- **Module:** Purchase → completed-invoice amend / cancel
- **Location:** `backend/purchases/services.py:387` (qty-delta branch in `set_items`), `backend/purchases/services.py:418` (`purchase_invoice_edit` ADJUSTMENT), `backend/purchases/services.py:969`–`1008` (`cancel` stock reversal), `backend/purchases/services.py:983` (headroom guard)
- **Type:** Sales/Purchase-inconsistency + latent Data-integrity
- **Severity:** Medium
- **What's wrong:**
  `SalesService.set_items` refuses any quantity change on a `COMPLETED` sales invoice
  (`backend/sales/services.py:617`–`635`, CR-024/CR-128) and tells the user to raise a
  credit note / return. `PurchaseService.set_items` instead **accepts** a quantity change on a
  `COMPLETED` purchase invoice for non-serial / non-batch products, posts a compensating
  `MovementType.ADJUSTMENT` with `reference_type="purchase_invoice_edit"`, and calls
  `retire_source_layers` on the original `PURCHASE` layers.
  `PurchaseService.cancel` then reverses only movements of
  `movement_type=PURCHASE, reference_type="purchase_invoice"` — the full **original**
  quantity — and never reverses the `purchase_invoice_edit` ADJUSTMENT. After an edit-down:
  - `retire_source_layers(move, full_original_qty)` raises `"source FIFO layer … already
    been issued"` for FIFO companies (the layer was already reduced by the edit); and
  - the pre-check at line 983 (`bal.on_hand (reduced) < req_qty (original)`) raises
    `"on-hand stock … is less than the purchase quantity"` — see CR-002 for why the
    `allow_negative_stock` escape hatch is inert — so the completed+amended bill can
    **never be cancelled**; under a hypothetical bypass the balance ends at
    `−(edit-down amount)`.
- **Trigger / repro:** Complete a purchase bill for a plain (non-tracked) product, qty 10.
  Call `PurchaseService.set_items` with qty 6 for that line while status is `COMPLETED`.
  Then call `PurchaseService.cancel`.
- **Consequence:** completed purchase bill stuck (cannot cancel); for FIFO, a hard 400 with
  a confusing message; under any future negative-stock bypass, `StockBalance.on_hand`,
  `InventoryRunningCost`, and the FIFO layer set all drift from `Σ StockMovement`.
- **Code evidence:** the qty-delta loop `backend/purchases/services.py:400`–`443` posts
  `purchase_invoice_edit`; `grep -n "purchase_invoice_edit" backend/` shows it is referenced
  only where it is posted and in `_apply_cost_layers`'s "skip FIFO peel" list — **nothing in
  `cancel` or elsewhere unwinds it.**
- **Mitigating fact:** this branch is **not currently reachable through the REST API** —
  `assert_h9a_line_allowlist` (`backend/core/services/h9_amend.py:76`) makes a quantity
  change on a completed purchase a 400 before `set_items` runs. It *is* reachable from any
  other caller of `set_items` on a `COMPLETED` invoice (a new endpoint, a data migration, a
  bill-import "amend on commit" path) and from a direct service call.
- **Suggested fix direction:** make `PurchaseService.set_items` reject quantity changes on
  `COMPLETED` invoices (mirror the sales twin), or, if the branch must stay, have
  `PurchaseService.cancel` also enumerate and reverse `reference_type="purchase_invoice_edit"`
  / `"purchase_invoice"` movements as a set and net them before the headroom check.
- **Test to add:** `test_completed_purchase_qty_amend_then_cancel_nets_stock_to_zero` —
  complete qty 10, `set_items` qty 6 at service level, `cancel`, assert `on_hand == 0`,
  `Σ StockMovement == 0`, and no FIFO-layer exception. Plus a twin assertion that
  `set_items` rejects the qty change the way sales does.
- **Twin check:** Sales — n/a; the sales side forbids the edit that creates the asymmetric
  movement, which is why it has no equivalent bug.

### CR-002 — `PurchaseService.cancel` headroom guard keys on a `Company.allow_negative_stock` attribute that does not exist
- **Module:** Purchase → cancel; cross-cutting negative-stock policy
- **Location:** `backend/purchases/services.py:983`
- **Type:** Bug (dead code) / policy inconsistency
- **Severity:** Low
- **What's wrong:** `... and not getattr(invoice.company, "allow_negative_stock", False)`.
  `Company` defines only `negative_stock_policy` (`backend/accounts/models.py:122`); there is
  no `allow_negative_stock` field or property anywhere in the repo
  (`grep -rn "allow_negative_stock" backend/` → the single call site). `getattr(..., False)`
  therefore always returns `False`, so the on-hand headroom guard can **never** be bypassed
  and does **not** consult `negative_stock_policy`.
- **Trigger / repro:** Company on `negative_stock_policy="WARN"`. Buy 10, sell 6 (legitimate
  under WARN). Try to cancel the purchase bill — blocked with
  `"on-hand stock (4) is less than the purchase quantity (10)"`, even though this company is
  configured to permit negative stock.
- **Consequence:** WARN-policy companies cannot cancel a completed purchase bill once any of
  its stock has moved, contradicting how WARN is honored in `post_movement`,
  `check_negative_stock`, `reserve_stock`, transfer complete, etc.
- **Code evidence:** the guard is the only reader of `allow_negative_stock` in the codebase;
  every other negative-stock decision reads `company.negative_stock_policy`.
- **Suggested fix direction:** replace with
  `company.negative_stock_policy == "BLOCK"` to match the rest of the codebase (and decide
  deliberately whether a WARN company should be allowed to drive stock negative on a
  purchase-cancel — the message implies "no" but the flag implies a per-company "yes").
- **Test to add:** `test_purchase_cancel_headroom_respects_negative_stock_policy` — WARN
  company, partially-consumed purchase, assert cancel is allowed (or explicitly and
  consistently blocked) and that `getattr` on a real field drives it.
- **Twin check:** Sales `cancel` (`backend/sales/services.py:1157`+) restores stock via
  `ADJUSTMENT` without an equivalent on-hand guard — it relies on `post_movement`'s own
  policy check. So the two sides guard oversell-on-reversal differently; the purchase side's
  guard is the stricter one but is misconfigured. (y — divergence)

### CR-003 — POS overpayment is booked as a silent unallocated customer advance, not change
- **Module:** POS → checkout / offline flush
- **Location:** `backend/sales/views.py:256`–`292` (`pos_checkout`), `web/src/offline/flushPosCheckout.ts:150`–`168` (`flushPosDraft`)
- **Type:** Missing-validation / Bug
- **Severity:** Low
- **What's wrong:** `pos_checkout` computes
  `amount = Decimal(payment.get("amount") or completed.grand_total)` and then
  `PaymentService.allocate_receipt(amount=min(amount, completed.grand_total))`. When the
  client sends `amount` (or `tendered_amount` used as `amount`) **greater** than the invoice
  total, a `CustomerReceipt` for the full `amount` is created, `grand_total` is allocated,
  and `amount − grand_total` remains as an **unallocated advance** on the walk-in customer
  (and, with books on, a credit to advances-liability GL 2300). `tendered_amount` is only
  interpolated into a free-text `notes` string ("Tendered … Change …"); nothing rejects or
  rounds the overpayment, and there is no "change given" path.
- **Trigger / repro:** POS cash sale, bill ₹470, client posts `payment: {mode: CASH,
  amount: 500}` (or `amount: 470, tendered_amount: 500` on a screen that forwards
  `tendered_amount` as the receipt amount). Result: ₹30 phantom advance on the counter
  customer.
- **Consequence:** over time, counter sales accumulate small unallocated advances against a
  shared walk-in customer; customer outstanding / advances reports drift from cash reality;
  reconciliation noise.
- **Code evidence:** `min(amount, completed.grand_total)` caps the allocation but nothing
  caps or rejects `amount`; `create_receipt(amount=amount)` books the full figure.
- **Suggested fix direction:** for POS, reject `amount > grand_total` (require the client to
  send the invoice total as the receipt amount and carry tender/change as display-only), or
  explicitly model change so the receipt equals the allocated amount.
- **Test to add:** `test_pos_checkout_rejects_overpayment` / `…books_receipt_equal_to_total`
  — post `amount = grand_total + 30`, assert 400 or assert receipt.amount == grand_total and
  no unallocated advance is created.
- **Twin check:** Purchase — n/a (no counter-payment equivalent); the online sales
  `receipt` + `allocation` endpoints correctly reject `amount > unallocated` /
  `amount > outstanding` for the *allocation*, but the *receipt* itself has the same
  "overpayment becomes advance" behaviour by design there (acceptable for A/R; questionable
  for a cash counter).

### CR-004 — (Observation) deterministic 4xx on `sales_invoice_complete` permanently burns the Idempotency-Key
- **Resolution (2026-09-09): WON'T FIX — working as designed.** Adding
  `insufficient_stock` / `credit_limit_exceeded` to `TRANSIENT_4XX_CODES` was implemented and
  then **reverted**: it breaks the deliberate W0-05 contract and its test
  `tests/test_remaining_gates.py::test_w0_05_deterministic_4xx_stored`, which pins
  `CREDIT_LIMIT_EXCEEDED` as the canonical *stored* deterministic 4xx. The retry contract is:
  use a fresh Idempotency-Key after the condition clears. The only automated retrier that
  reuses `<key>-complete` (`flushPosCheckout.ts`) already probes invoice status and rotates
  the key. `tests/test_review_2026_09_fixes.py::test_cr004_deterministic_4xx_on_complete_is_stored_and_needs_a_fresh_key`
  documents the contract. Follow-up if a new retrier is added: rotate its key on any
  non-transient 400 (do **not** widen `TRANSIENT_4XX_CODES`).
- **Module:** Sales / Purchase → complete; cross-cutting idempotency
- **Location:** `backend/core/idempotency.py:80`–`113` (`TRANSIENT_4XX_CODES`), `:293`–`353` (`wrap_idempotent`), consumed by `backend/sales/views.py:376` and `backend/purchases/views.py:229`
- **Type:** Silent-failure (by design, flagged for awareness)
- **Severity:** Low
- **What's wrong:** `CREDIT_LIMIT_EXCEEDED`, `INSUFFICIENT_STOCK`, and the R2-007 zero-COGS
  warning path are **not** in `TRANSIENT_4XX_CODES`, so a `complete` call that 400s on them
  stores the 400 against the Idempotency-Key. A retry with the **same** key replays the
  stored 400 forever — even after the customer's balance is paid down or stock is
  replenished. The `wrap_idempotent` docstring explicitly classifies credit-limit as
  "deterministic → store", so this is intentional; the web UI mints a fresh key per
  "Complete" click and is unaffected. It only bites automated / offline retriers that reuse a
  derived key (`${draftKey}-complete`). `flushPosCheckout.ts` works around it by probing
  invoice status and rotating the draft key on a confirmed-`DRAFT` failure, so it self-heals
  at the cost of delete+recreate churn.
- **Consequence:** none for the current UI; a latent foot-gun for any new caller that reuses
  a stable key across a "fix the blocker and retry" cycle.
- **Suggested fix direction:** if any first-party automated retrier is added, either add
  `credit_limit_exceeded` / `insufficient_stock` to `TRANSIENT_4XX_CODES` (they *are*
  condition-clears-then-retry cases, like `closed_period`) or document that such retriers
  must rotate the key.
- **Test to add:** `test_complete_credit_limit_4xx_key_can_retry_after_paydown` — assert the
  chosen contract (replay vs. release).
- **Twin check:** Purchase `purchase_invoice_complete` — same mechanism, same
  `confirm_*` codes are in `TRANSIENT_4XX_CODES` but `credit_limit`/stock are not. (y)

---

## Verified-clean notes (things specifically checked and found sound)

These are recorded so the report is usable as a partial release sign-off, not just a defect list.

- **Stock oversell race (POS / invoice complete / transfer):** `InventoryService.post_movement`
  takes `StockBalance … select_for_update().get(pk=…)` *before* the negative-stock re-check
  and *before* writing the movement (`backend/inventory/services.py:192`–`214`). The
  advisory `check_negative_stock` in `SalesService.complete` / `_sale_batches` /
  `StockTransferService.complete` is explicitly a fast-feedback pre-check; the authoritative
  one is under the row lock. Two concurrent completes on the last unit → the second blocks
  and re-reads the updated balance. `test_concurrency_races` covers this.
- **Idempotency scope strings:** every `scope="…"` literal in
  `sales/`, `purchases/`, `inventory/`, `payments/`, `imports/`, `accounts/export_views.py`
  (`grep` cross-checked against `MONEY_IDEMPOTENCY_SCOPES`) is present in the set. The
  historical `"invoice_create"` / `"purchase_create"` typos are gone; `import_job_create`
  is intentionally absent (creates an upload job, not money).
- **Completion atomicity:** `SalesService.complete`, `PurchaseService.complete`,
  `ReturnService.complete_return`, `StockTransferService.complete`,
  `SalesNotesService.complete_challan`, CN/DN completes — all `@transaction.atomic`, all
  re-`select_for_update` the header, assign the document number *inside* the transaction and
  only when `number` is unset (drafts don't burn a slot — BUG-208), post stock + ledger + GL
  before status flip, and defer PDF/email via `transaction.on_commit` (`sales/handlers.py`,
  `core/handlers.py` — the only synchronous subscriber is an audit-log DB insert).
- **Cross-tenant:** in-scope viewsets extend `CompanyScopedViewSet`; line/party/warehouse
  FKs on the serializers are `CompanyPrimaryKeyRelatedField` (scopes `get_queryset` to
  `request.company`); the sensitive re-fetches in services pass `company_id=…`
  (`ReturnService.complete_return`, `PurchaseService.cancel`, `cancel_return`). Grep for
  unscoped `objects.get(pk=…)` / `get_object_or_404` in the in-scope apps turned up only
  self-FK follows and management commands. `allocate_receipt` / `allocate_supplier_payment`
  assert `company_id` and party match before locking.
- **Payment over-allocation:** `allocate_receipt` / `allocate_supplier_payment` lock invoice
  then payment (fixed order, CR-019), re-derive `unallocated` and `open_outstanding` under
  the locks; `_allocated_of_payment` filters `reversed_at__isnull=True`. Concurrent
  allocations of one receipt to two invoices serialize on the receipt lock.
- **Draft numbering:** sales & purchase invoice `create()` do **not** call `next_number`;
  number is assigned in `complete()` under the header lock. `perform_destroy` refuses
  non-`DRAFT` and purges `IdempotencyRecord` rows for the resource.
- **Document-chain double-convert:** `convert_quotation`, `convert_sales_order`,
  `convert_sales_order_to_challan`, `convert_delivery_challan` all `select_for_update` the
  source and reject when `converted_invoice_id` / `converted_order` / `converted_challan` is
  already set, under the lock.
- **Derived ledger:** `LedgerService.sales_invoice_outstanding` /
  `purchase_invoice_outstanding` / `customer_exposure_for_credit_limit` compute from
  documents + completed CN/DN + non-reversed allocations every call — no cached balance
  table; when books are on they cross-check GL 1200/2300 and take the more conservative
  figure, logging drift. `purchase_invoice_outstanding` has explicit double-relief guards
  for auto-CN-vs-return (LED-02/BB-000281).
- **Rounding:** `compute_document_totals` quantizes each line with `q2` (ROUND_HALF_UP),
  sums line-wise (GSTR-1 rate-wise convention), and for `BEFORE_TAX` invoice discount
  redistributes the residual across lines with headroom instead of dumping it on the last
  line (R1-020). Invoice-level discount exceeding invoice value is a 400, not a silent ₹0.
- **Offline outbox:** `flushPosDraft` reuses one derived idempotency-key family
  (`key`, `key-complete`, `key-receipt`, `key-alloc`) across retries; `flushOutbox` holds a
  `navigator.locks` (or localStorage) mutex; sign-out (`AuthContext.logout` and
  `session-expired`) calls `clearAllDrafts` **and** `indexedDB.deleteDatabase(
  'bizboard-invoice-outbox')`. Plaintext-on-device is disclosed
  (`OUTBOX_PLAINTEXT_WARNING`).
- **GST worksheets:** GSTR-1/2B/3B builders filter `status IN (COMPLETED, RETURNED)` for
  invoices and `COMPLETED` for CN/DN, all `company=company`-scoped; `accounting/reports.py`
  TB/P&L/BS/cash-flow all filter `entry__company=company` and bound dates (B1-011/012/018
  fixes present).

---

## Gaps in this pass (recommended follow-up before release)

1. **Reporting figure reconciliation** — I checked scoping/filters, not that each KPI and
   each GSTR section total foots to the underlying documents. Dashboard KPIs
   (`web/src/pages/DashboardPage.tsx` + backend) and `reporting/gst_returns_sections.py`
   deserve a figure-level pass, especially any place tax/COGS is recomputed rather than read
   from the write-path line values.
2. **Accounting dual-ledger / GL balance** — `PostingService.post_*` and
   `adjust_*_postings` were not read line-by-line; confirm every posting is balanced and that
   `adjust_*_postings` reverses the prior JE on the amend date and re-posts, with the period
   gate enforced (it is called from `complete`/`cancel`, but the amend path via
   `set_items` → `adjust_*_postings` should be re-checked).
3. **BoE / bill-import (`imports/services.py` `BillImportService.commit`, line ~2804)** —
   only the outer `commit` wrapper and idempotency were read; the ITC-gating / 2B-recon /
   RCM-inference and partial-commit-on-row-error behaviour of the bill path were not traced.
4. **Serial/batch edge cases** — serial double-sale, serial re-entry on return, batch
   expiry block, FEFO selection under WARN — the code paths exist and look consistent but
   were not exercised against adversarial inputs in this pass.
5. **`godownConflict.ts` / `StockConflictModal.tsx`** offline two-device merge — not reviewed.

## Test suite

`cd backend && python -m pytest -q -p no:randomly` (Python 3.13; the checklist says 3.12 but
the repo standardised on 3.13 per the founder call 2026-09-08):

```
1292 passed, 57 skipped, 1 warning in 324.54s (0:05:24)   EXIT=0
```

No failures, no xfails surfaced. Notes:

- **The concurrency invariants relied on in "Verified-clean notes" are NOT exercised on the
  local run.** `tests/test_concurrency_races.py` (concurrent invoice oversell, concurrent
  payment over-allocation, concurrent over-return) and `tests/test_rls_coverage.py` /
  `tests/test_ws01_gateway_refund_integrity.py` are `@pytest.mark.postgres` and skip
  themselves when `connection.vendor != "postgresql"` (they need real `SELECT … FOR UPDATE`).
  Before release, run the full suite against Postgres and confirm these pass — the
  `select_for_update` reasoning in this review is a code read, not a locally-verified result.
- **22 of the 28 chains in `tests/workflows/test_wf_todo_stubs.py` are `@pytest.mark.skip`
  ("Phase 2 chain not yet implemented")** — a correction to an earlier draft of this note:
  the core money paths **are** covered end-to-end (`test_wf19_pos_checkout`,
  `test_wf03_sales_return`, `test_wf05_purchase_return`,
  `test_wf21_stock_transfer_between_godowns`, `test_wf06_quotation_to_invoice`,
  `test_wf28_two_tenant_interleave` all run and pass, calling `assert_consistent(company)`).
  What is still an unimplemented stub, and in review scope: **CN/DN chains**
  (wf07/wf08/wf12/wf13), **SO reserve→convert** (wf09), **delivery challan → invoice**
  (wf10), **PO → purchase** (wf16), **bill-upload idempotency** (wf14/wf15), **stock
  adjustment / write-off** (wf22). Worth implementing wf07/wf12 (credit notes) and wf10
  (challan) before release — they touch stock + AR/AP + GL and only have unit coverage today.
- The other skips are feature-flag-dark / environment-gated (`s` markers throughout).
- Running two `pytest` processes against the shared SQLite `--reuse-db` file at once produces
  spurious `database is locked` collection errors (seen once during this review) — run the
  suite single-threaded.
- Thin-coverage gaps noted while reading — **now closed** by
  `backend/tests/test_review_2026_09_fixes.py`:
  - CR-001 — `test_cr001_completed_purchase_qty_amend_rejected_at_service_level` +
    `…_via_api`.
  - CR-002 — `test_cr002_warn_policy_allows_cancel_of_partly_consumed_purchase` +
    `…_block_policy_still_blocks…`.
  - CR-003 — `test_cr003_pos_overpayment_books_receipt_equal_to_invoice_total` +
    `test_cr003_pos_partial_payment_still_allowed`.
  - CR-004 — `test_cr004_deterministic_4xx_on_complete_is_stored_and_needs_a_fresh_key`
    (documents the intentional contract).
