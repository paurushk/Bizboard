# Cross-Flow Impact Map

**Status:** Living document · **Created:** 2026-09-12 · **Last extended:** 2026-09-13 · **Owner:** backend + web  
**Role in the quality model:** **Graph 2 (Impact)** — writers and readers of shared state. Philosophy and the three-graph operating model: [`HOLISTIC_VALIDATION_REVIEW.md`](HOLISTIC_VALIDATION_REVIEW.md) §0. Method: [`TESTING_STRATEGY.md`](TESTING_STRATEGY.md) L8.

## Why this exists

Bizboard is ~19 backend apps plus a frontend that all read a handful of
shared, mutable fields — an invoice's `status`, a stock balance, an
allocation's `reversed_at`. A write to one of those fields doesn't stay
inside its own flow: it fans out to ledgers, reporting, insights, dunning,
GST filings, and multiple frontend pages, each of which embeds its own
assumption about what the value means. Those assumptions drift
independently, because nothing forces the readers to agree with each other
or with the writer.

**This document is the reader index of Graph 2, not the whole validation
framework.** The stronger primitive is a **business event**, not a field:

```text
BUSINESS EVENT → canonical state → writers → all projections
  → all user surfaces → user decision → subsequent event → historical truth
```

Today's entries are still field-shaped (`SalesInvoice.status`, `StockBalance`,
…). That remains useful for code review. The **target** is an event ×
projection matrix (complete, return, allocate, reverse, amend, close, …)
with cells for stock, GL, AR/AP, GST, reports, attention, badge, PDF,
public payment page, and notifications. Until that matrix is machine-readable,
treat every field entry below as *necessary but not sufficient* product-truth
coverage.

This document is not an exhaustive flow diagram — that would be stale within
a month in a codebase this size and nobody would trust it. It is a **fan-out
map for the small number of fields that have already been proven to cause
this class of bug**, seeded from a fully-returned invoice rendering as "Paid"
on four frontend pages (2026-09-12), then extended by deliberately auditing
the same shape of bug — two independent readers of one field/gate silently
disagreeing — across five more fields. That second pass (2026-09-13) found
four more live instances and cleared two fields as genuinely consistent
(worth recording as a negative result, not just a positive one).

**Every entry follows the same question**: *if I change how this field is
written, or add a new value to it, who reads it — and what will they get
wrong if I don't tell them?*

**How to use it:**
- **Before changing a listed field's write path or its set of possible
  values** — read its "Readers & assumptions" list and update every reader
  whose assumption your change invalidates, not just the one you're working
  on.
- **When code review touches a listed field** — check the diff against the
  reader list below; a PR that changes one reader's status-set filter
  without a coordinating note is the exact shape of bug this doc exists to
  catch.
- **When adding a test for a flow that writes one of these fields** — the
  "Suggested tests" column is the minimum cross-flow assertion to add
  alongside the flow's own happy-path test. Prefer one topology-rich
  lifecycle assertion (invoice → pay → return → residual → all surfaces)
  over another isolated reader test.
- **When you find a new shared field with 3+ independent readers across app
  boundaries, or add a new money/stock *event*** — add it here *and* to the
  event catalog. Do not wait to be bitten. The old "only after 3+ readers
  have already failed" growth rule is retired as of 2026-09-13
  (`HOLISTIC_VALIDATION_REVIEW.md` §0.8).

---

## Quick index

| Field | Writers (single path?) | # independent readers traced | Known open inconsistency |
|---|---|---|---|
| [`SalesInvoice.status` / `payment_state` / `return_state`](#1-salesinvoicestatus--payment_state--return_state) | 3 services | 9 | Fixed 2026-09-12 (G-17) |
| [`PurchaseInvoice.status`](#2-purchaseinvoicestatus) | 4 (incl. Tally import) | 10 | Fixed 2026-09-13 (G-18) |
| [`StockBalance` on-hand/reserved](#3-stockbalance--on-hand-quantity) | 1 (`InventoryService.post_movement`, ~20 callers) | 9 | Fixed 2026-09-13 (G-19) |
| [Credit Note / Debit Note status + `grand_total`](#4-credit-note--debit-note-status--grand_total) | 4 services | ~20 call sites | None found — most consistent field audited |
| [`PaymentAllocation` / invoice outstanding](#5-paymentallocation--invoice-outstanding-balance) | 4 (allocate ×2, reverse, void) | 10 | Fixed 2026-09-13 (G-20) |
| [GST/accounting period-lock (`assert_period_allows_money_amend`)](#6-gstaccounting-period-lock-assert_period_allows_money_amend) | n/a (enforcement gate, not a stored field) | ~25 call sites across 10 apps | Fixed 2026-09-13 (G-21/G-22) + structural guard added |
| [`Company.accounting_enabled`](#7-companyaccounting_enabled) | 1 (`AccountingSettingsView`) | ~20 posting gates + report view | None found — API-level mixin gates every report reader; see backfill note |

<!-- BEGIN GENERATED EVENT SUMMARY -->

**Generated event × projection summary** (P2-T5). Full grid: [`EVENT_MATRIX.md`](EVENT_MATRIX.md). Do not hand-edit this block.

| Verb | Docs | stock | GL | AR/AP | GST | reports | attention | dash | badge | channel | closed-period |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `complete` | `sales_invoice`, `purchase_invoice`, `sales_return`, … | yes | yes | yes | yes | yes | yes | yes | yes | yes | required |
| `cancel` | `sales_invoice`, `purchase_invoice`, `delivery_challan`, … | yes | yes | yes | yes | yes | yes | yes | yes | yes | required |
| `return` | `sales_invoice`, `purchase_invoice`, `pos_sale` | yes | yes | yes | yes | yes | yes | yes | yes | yes | required |
| `credit_note` | `sales_credit_note`, `purchase_credit_note` | lim | yes | yes | yes | yes | yes | yes | yes | no | required |
| `debit_note` | `sales_debit_note`, `purchase_debit_note` | no | yes | yes | yes | yes | yes | yes | yes | yes | required |
| `allocate` | `customer_receipt`, `supplier_payment` | no | yes | yes | no | yes | yes | yes | yes | yes | required |
| `reverse_allocation` | `customer_receipt`, `supplier_payment` | no | yes | yes | no | yes | yes | yes | yes | yes | required |
| `void` | `customer_receipt`, `supplier_payment` | no | yes | yes | no | yes | yes | yes | yes | yes | required |
| `amend` | `sales_invoice`, `purchase_invoice` | yes | yes | yes | yes | yes | yes | yes | yes | yes | required |
| `close_period` | `accounting_period`, `gst_period` | no | yes | no | yes | yes | yes | yes | no | no | n/a |
| `stock_count` | `stock_count_session` | yes | lim | no | no | yes | yes | yes | no | no | required |
| `stock_transfer` | `stock_transfer` | yes | no | no | no | yes | no | yes | no | no | required |
| `import` | `import_job` | yes | lim | yes | lim | yes | yes | yes | yes | no | required |
| `flag_flip` | `company` | no | yes | no | lim | yes | yes | yes | no | no | n/a |
| `invite` | `company_user` | no | no | no | no | no | no | no | no | yes | n/a |

<!-- END GENERATED EVENT SUMMARY -->

---

## 1. `SalesInvoice.status` / `payment_state` / `return_state`

`status` ∈ `DRAFT / COMPLETED / CANCELLED / RETURNED`
(`backend/sales/models.py:10-14`). `payment_state` and `return_state` are
computed, not stored (`backend/sales/serializers.py:178-196`).

**Writers**
- `backend/sales/services.py` — `complete()` DRAFT→COMPLETED, `cancel()` →CANCELLED.
- `backend/sales/return_service.py:169-178` — `complete_return()` flips
  COMPLETED→RETURNED once every sold line is fully returned
  (`ReturnService.returned_quantities`); a **partial** return leaves `status`
  at COMPLETED on purpose (it's still a valid sale for the lines the
  customer kept).
- `backend/sales/return_service.py:416-431` — `cancel_return()` flips
  RETURNED→COMPLETED if no other completed return remains against the
  invoice.

**Canonical predicates (2026-09-13)**: `backend/sales/status_semantics.py`
now holds `is_open_receivable()` / `OPEN_RECEIVABLE_STATUSES` (may still owe
money) and `is_operational_sale()` / `OPERATIONAL_SALE_STATUSES` (counts as
a live sale) — every reader below either sources from this module directly
or via a same-valued re-export, closing CF-001 as a class for this field
(§8 weak assumption 12 in `TESTING_STRATEGY.md`). No third
"is_dunning_eligible" predicate — dunning eligibility is `is_open_receivable`
plus a due-date rule, not a distinct status set.

**Readers & assumptions**
- `backend/ledgers/services.py` — `OPEN_SALES_STATUSES` is now a re-export
  of `status_semantics.OPEN_RECEIVABLE_STATUSES` (was independently defined
  until 2026-09-13) — used in ~7 outstanding/aging/statement functions —
  **assumes a RETURNED invoice can still carry a balance** (true: the auto
  credit-note's unallocation doesn't always net to exactly zero).
- `backend/reporting/services.py` `NET_SALES`/`OPEN_SALES` — both now source
  from `OPEN_RECEIVABLE_STATUSES` too (previously two independently-defined,
  identically-valued constants) — dashboard money totals (netted via CN
  subtraction), `receivables_aging`, `recent_invoices`/`invoice_count`
  (normalized off an `exclude(DRAFT, CANCELLED)` spelling that encoded a
  different intent but matched today), and `product_sales`/`customer_sales`
  revenue ranking — same assumption, consistent with ledgers.
- `backend/insights/services.py` `OPEN_SALES` — now sources
  `OPERATIONAL_SALE_STATUSES` — **excludes RETURNED on purpose**: analytics
  (best-seller, trending, margin) treat a fully-reversed sale as never
  having happened.
- `backend/insights/alerts.py` — same `OPERATIONAL_SALE_STATUSES` source
  (fixed 2026-09-12; previously wrongly included RETURNED, over-counting
  reversed sales in fast-mover/margin/concentration alerts — see G-17).
- `backend/payments/dunning.py::eligible_invoices` — now sources
  `OPEN_SALES_STATUSES` from `status_semantics` directly (fixed 2026-09-12,
  G-20: previously `status=COMPLETED` only, excluding a RETURNED invoice
  with residual AR from dunning even though the payment-health query below
  already considered it outstanding).
- `backend/payments/dunning.py::customer_risk_snapshot` — same source (fixed
  2026-09-13, G-23: previously `status=COMPLETED` only, making that same
  residual AR invisible to credit-risk aging/overdue and the
  auto-credit-hold check that reads this snapshot).
- `backend/payments/services.py` — UPI reminder / payment-health query now
  sources `OPEN_RECEIVABLE_STATUSES` (was a raw string tuple) — assumes a
  returned invoice's residual balance still deserves a reminder link.
- Frontend `web/src/utils/status.ts` `paidAwareStatus()` — the FE's own
  re-derivation of "what badge to show," consumed by `SalesHistoryPage.tsx`,
  `InvoiceDetailPage.tsx`, `DashboardPage.tsx` — fixed 2026-09-12 to gate the
  PAID override on `status === COMPLETED` first; previously a RETURNED
  invoice with a zeroed balance rendered "Paid." Deliberately **not** folded
  into the predicate module — different language/problem shape
  (single-invoice display override, not queryset filtering).

**Known inconsistencies**: none currently open (G-17/18/19/20/23 fixed;
G-21/22 tracked under §6 below). The predicate module itself is exhaustively
unit-tested (`backend/tests/test_status_semantics.py`), so a future reader
adopting it can't silently reintroduce a hand-picked-cases-only test the way
`paidAwareStatus()`'s original tests did (weak assumption #11).

**Suggested tests**: `backend/tests/test_return_state_visibility.py` (backend
`return_state` across full/partial/none); `web/src/pages/sales/*.test.tsx` +
`web/src/pages/DashboardPage.test.tsx` (badge text across
status × payment_state × return_state combinations);
`backend/tests/test_status_semantics.py` (the predicates themselves,
exhaustive over the full status enum).

---

## 2. `PurchaseInvoice.status`

`status` ∈ `DRAFT / COMPLETED / CANCELLED / RETURNED`
(`backend/purchases/models.py:12-19`) — RETURNED was added later
specifically to mirror `SalesInvoice.status` (comment references BUG-212).

**Writers**
- `backend/purchases/services.py:740` `complete()`, `:973` `cancel()`.
- `backend/purchases/services.py:1272-1274` `_post_return_movements` — mirrors
  `SalesService.complete_return`'s "flip to RETURNED once fully returned" rule.
- `backend/integrations/tally/adapter.py:213,358,365` — Tally import writes
  DRAFT/COMPLETED directly, bypassing `complete()`'s recompute/number logic
  (opening-balance import path).

**Readers & assumptions**
- `backend/ledgers/services.py` (`purchase_invoice_outstanding`,
  `_supplier_outstanding_documents`, `bulk_*`, `supplier_statement`) —
  `(COMPLETED, RETURNED)` — assumes a RETURNED purchase can still carry a
  payable balance.
- `backend/reporting/services.py:230-233` (dashboard `purchases_month`,
  "CR-043/045: include RETURNED"), `:643` `payables_aging` — same set,
  consistent with ledgers.
- `backend/reporting/services.py:426-433` `purchase_register` — includes
  RETURNED (document list, not a money total).
- `backend/reporting/gstr2b.py`, `gst_health.py`, `gst_returns.py`,
  `ims.py`, `tds_worksheets.py` — all `(COMPLETED, RETURNED)` uniformly:
  a fully-returned purchase still has real GST/ITC/TDS consequences.
- `backend/purchases/boe_services.py:79-95` — Bill-of-Entry cancel-link
  guard blocks unlinking only for COMPLETED invoices; RETURNED invoices fall
  into the "silently unlink" branch — **treats RETURNED like DRAFT (unlink
  freely) instead of like COMPLETED (protect the link)**.
- `backend/purchases/serializers.py:220,222,248,252,292` — amend rules treat
  RETURNED as terminal/non-editable, same as CANCELLED.
- `backend/purchases/notes_services.py:241-242,457-458` — a purchase CN/DN
  can be raised against either COMPLETED or RETURNED.
- `web/src/pages/purchases/PurchaseHistoryPage.tsx` — renders raw `status`
  with no payment-state overlay (no equivalent of the sales-side
  `paidAwareStatus` bug is possible here — confirmed by
  `PurchaseHistoryPage.test.tsx`, added 2026-09-12).
- **`backend/insights/alerts.py:118-130` `_ap` (AP_DUE_7D alert) and
  `backend/insights/services.py:520-533` (cash-flow forecast `ap_by_day`)** —
  both filter `status=COMPLETED` **only**, excluding RETURNED, then call
  `LedgerService.purchase_invoice_outstanding(inv)` — a function that itself
  treats RETURNED as balance-bearing.

**Known inconsistency — FIXED 2026-09-13**: a purchase invoice that's fully
RETURNED but still carries a payable balance (e.g. a partial-return/
debit-note mismatch) was counted in `payables_aging` and the dashboard AP
total, but never appeared in the AP_DUE_7D alert or the 14-day cash-flow
outflow forecast — the exact inverse of the sales-side G-17 bug (there,
RETURNED was wrongly *included*; here it was wrongly *excluded*). Tracked as
**G-18** in `TESTING_STRATEGY.md`. Both filters now include RETURNED,
matching `payables_aging`/`purchase_invoice_outstanding`.

**Regression test**: `test_phase6_insights.py::test_g18_ap_due_and_cashflow_include_returned_purchase_with_residual_payable`
— fully returns a purchase invoice, then raises a post-return debit note
(`CORRECTION_OF_INVOICE`) leaving a genuine ₹50 residual payable, and
asserts `payables_aging`, `AP_DUE_7D`, and `forecast_cashflow` all agree on it.

---

## 3. `StockBalance` — on-hand quantity

`backend/inventory/models.py:183-210` — `on_hand`, `reserved`,
`available = on_hand - reserved`. Explicitly documented as a **derived
cache, rebuildable from `StockMovement`** (model docstring, §12.1).

**The single write path**: `backend/inventory/services.py:137-251`
`InventoryService.post_movement()` — locks the balance row
(`select_for_update`) before the negative-stock re-check and the write
(BUG-222/309). This is the *only* place `on_hand` is mutated. Every caller
below funnels through it: sales complete/return
(`sales/services.py`, `sales/cogs_service.py`, `sales/return_service.py`,
`sales/notes_services.py`), purchase complete/cancel/return
(`purchases/grn_service.py`, `purchases/services.py`), manufacturing
work-order release (`manufacturing/services.py:198,334,395,428`),
adjustments/transfers/opening/imports (`inventory/views.py`,
`imports/services.py:2047`), and Tally sync (`integrations/tally/adapter.py`).

**Readers & assumptions**
- `backend/inventory/services.py:930-940` `available_quantity()` — the
  canonical read (`on_hand - reserved`), used by essentially every oversell/
  availability check below — **assumes `StockBalance` is always current with
  `StockMovement`, no drift**.
- `backend/inventory/services.py:960-968` `check_negative_stock()` — an
  advisory pre-check, not authoritative (`post_movement`'s own re-check is)
  — **assumes it's always called in the same transaction as the eventual
  `post_movement`**; a caller that checks but doesn't immediately post gets
  a stale-safe "OK" that isn't binding.
- FEFO/batch picking (`inventory/services.py:1005,1177,2042`) — allocates
  against `available_quantity` per lot. `manufacturing/services.py:60-76`
  pre-locks the full component/warehouse balance set to close a documented
  race; **sales/purchases FEFO callers do not pre-lock the same way** and
  rely solely on `post_movement`'s per-row lock — a documented, only
  partially-mitigated race under concurrent release.
- `backend/inventory/item_stock.py:164-169` `assert_unit_change_allowed` —
  blocks a unit-of-measure change if aggregate `on_hand != 0 or reserved != 0`
  — assumes any nonzero balance anywhere means "actively stocked."
- `backend/inventory/item_stock.py:330-338` `remaining_qty()` — plain
  `Sum(on_hand)`, **no `reserved` subtraction** — used by serial-scrap flows
  (`inventory/views.py:567-576,629-634`) — **different assumption than
  `available_quantity`** (reserved doesn't matter for scrap eligibility).
- `backend/inventory/views.py:54-91` `low_stock_alert_payload()` —
  reserved-aware (`on_hand - reserved`), per-warehouse override support.
- `backend/reporting/services.py:521-548` `inventory_summary()` — the one
  reader that **doesn't trust the cache**: independently recomputes on-hand
  from `Sum(StockMovement.quantity)` and flags drift against `StockBalance`
  (CR-062).
- `backend/core/invariants/inventory.py:37-60` `balance_equals_movements` —
  the formal statement of the assumption every reader above makes
  implicitly: `on_hand == Σ movements`, or "every quantity/valuation/COGS
  read off it is wrong."
- `web/src/pages/pos/PosPage.tsx:317-321` — `s.available ?? s.onHand` — falls
  back to raw on-hand if `available` is missing from the payload, same
  reserved-blind-spot shape as `remaining_qty` if the serializer ever drops it.

**Known inconsistency — FIXED 2026-09-13**:
`backend/insights/alerts.py:524-530` (DEAD_STOCK alert) filtered
`on_hand__gt=0` and money-valued **raw `on_hand`**, with no `reserved`
subtraction — while `low_stock_alert_payload` and the health-score
`stock_score` (`insights/services.py:345-356`) are both reserved-aware. A
SKU fully reserved against an open sales order (`available == 0`) could be
flagged and money-valued as "dead stock" in the same breath the low-stock
logic treated it as unavailable/committed. Tracked as **G-19**. Both the
candidate filter and the valuation now use `on_hand - reserved` (an
`F()`-annotated `_available`).

**Regression test**: `test_b05_attention.py::test_g19_dead_stock_ignores_fully_reserved_stock`
— reserves a product's entire on-hand against a confirmed sales order,
asserts DEAD_STOCK does not fire.

**Suggested test**: reserve a product's entire on-hand quantity against an
open (uncompleted) sales order/challan, then assert `DEAD_STOCK` does *not*
fire for it (currently fails — pins G-19).

---

## 4. Credit Note / Debit Note status + `grand_total`

`backend/sales/models.py` `SalesCreditNote`/`SalesDebitNote`,
`backend/purchases/models.py` mirrors — `DRAFT / COMPLETED / CANCELLED`
(no RETURNED equivalent; these are value-only notes, not documents that
themselves get returned).

**Writers**
- `backend/sales/notes_services.py:298,342,487,522` — complete/cancel for
  both note types; cancel reverses the POSTED journal entry first if one exists.
- `backend/purchases/notes_services.py:348,390,558,590` — mirror.
- `backend/accounting/services.py:1479` `PostingService.post_note()` — only
  ever invoked from the 4 `complete_*` call sites above.

**Readers & assumptions**
- `backend/ledgers/services.py` — ~15 outstanding/aging/statement call
  sites, all sum `grand_total` of CN/DN filtered to `status=COMPLETED` only
  — uniform across every site (no inconsistency found here).
- `backend/reporting/services.py` — dashboard netting, register/aging
  totals — same COMPLETED-only filter, consistent with ledgers.
- `backend/reporting/gst_returns.py:700-751` + `gst_returns_sections.py:185-251`
  — GSTR-1 CDNR section, COMPLETED-only, keyed off `note.sales_invoice`
  (non-nullable, `on_delete=PROTECT` — safe to assume it always resolves).
  Notes on an e-commerce-operator invoice route to CDNUR instead (`:704-721`).
- `backend/reporting/gst_returns.py:830-836` — a **separate** CANCELLED-note
  section for filing reconciliation — a deliberately different assumption
  from the money-netting readers (which drop CANCELLED entirely).
- `backend/accounting/services.py:1984,2100-2136` — reconciliation/backfill,
  COMPLETED-only, consistent.

**Known inconsistencies**: none found — this is the most internally
consistent field audited. One structural risk worth a standing checklist
item rather than a bug: `PostingService.post_note()` is wired only through
the 4 `complete_*` call sites: **any new way to flip a CN/DN to COMPLETED
must call it too**, or the note nets correctly against AR/AP/GST filings
while silently never hitting the books.

**Suggested test**: none currently missing; if a new completion path is
added, assert its journal entry exists (mirrors the existing
`guard_no_raw_unit_cost_update`-style structural guard pattern).

---

## 5. `PaymentAllocation` / invoice outstanding balance

`backend/payments/models.py:162-200` — `receipt` XOR `supplier_payment`,
`sales_invoice` XOR `purchase_invoice` (CheckConstraints), `reversed_at`
(nullable — soft-reversal, never hard-deleted).

**Writers**
- `backend/payments/services.py:397-436` `allocate_receipt()` (AR).
- `backend/payments/services.py:~460-503` supplier-payment allocation (AP).
- `backend/payments/services.py:517-536` `reverse_allocation()` — the only
  writer of `reversed_at`; reverses the linked journal entry first.
- `backend/payments/services.py:540+` `void_receipt()` — cascades into
  reversing that receipt's allocations.

**Readers & assumptions**
- `backend/ledgers/services.py:147-176` `sales_invoice_outstanding()` —
  `grand_total + tcs − CN + DN − allocated`, `allocated` filtered to
  `receipt__isnull=False, reversed_at__isnull=True` — guards against a
  mis-linked `supplier_payment` row polluting the AR side (R2-020/CR-061).
- `backend/ledgers/services.py:178-200+` `purchase_invoice_outstanding()` —
  AP mirror.
- `backend/ledgers/services.py` `bulk_sales_invoice_outstanding()` /
  `bulk_purchase_invoice_outstanding()` — same formula, vectorized;
  **self-documented divergence**: no legacy-CN amount-matching fallback the
  single-invoice path has — a caller needing exact precision on
  pre-BB-000323 data must use the single-invoice function.
- `backend/sales/serializers.py:151-166` `get_balance()` — DRAFT
  short-circuits to `receivable` without calling `LedgerService`; list view
  uses a bulk-attached `_list_outstanding` (CR-016); detail view falls
  through to the single-invoice `LedgerService` call — **assumes the bulk
  attachment is wired for the `list` action specifically**; a new
  list-shaped endpoint that forgets to wire it silently falls back to the
  slower (still correct) path.
- `backend/sales/return_service.py:286-293` (CR-124) — a return against a
  paid invoice routes through `complete_credit_note(confirm_paid_invoice=True)`
  rather than duplicating unallocate logic — **assumes exactly one code path
  ever auto-unallocates**, and explicitly leaves a mis-linked
  `supplier_payment` row on a sales invoice untouched.
- `backend/accounting/services.py:2278-2312` — `CUSTOMER_ADVANCE_MISMATCH`
  check compares `Σ POSTED receipts − Σ allocated(not reversed)` against GL
  account 2300 — assumes every non-reversed allocation has a POSTED receipt.
- `web/src/pages/sales/InvoiceDetailPage.tsx` — `inv.balance ?? inv.grandTotal`
  fallback: if the API ever omits `balance`, the UI overstates the owed
  amount as the full grand total rather than 0, and the UPI-QR CTA triggers
  off the same value.
- **`backend/payments/dunning.py:133-145` `eligible_invoices()`** — filters
  `status=COMPLETED` only (not `ledgers.OPEN_SALES_STATUSES =
  (COMPLETED, RETURNED)`), so a RETURNED invoice never even reaches the
  outstanding-balance check that would otherwise say "yes, this owes money."
- **`backend/payments/services.py:1679-1683` `_payment_health_uncached`**
  (payment-health / UPI-reminder alert) — filters
  `status__in=(COMPLETED, RETURNED)` before calling
  `bulk_sales_invoice_outstanding`.
- **`backend/payments/dunning.py:445-460` `customer_risk_snapshot()`** —
  filtered `status=COMPLETED` only, then summed each matching invoice's
  outstanding balance into aging/overdue buckets. Feeds
  `sales/services.py`'s auto-credit-hold check at invoice completion, plus
  the customer-risk API and attention feed.

**Known inconsistency — FIXED 2026-09-13** (two instances, found together
while designing G-20's fix — G-23 wasn't independently rediscovered, it
surfaced from tracing every reader of this field in one pass):
- **G-20**: the payment-health strip correctly flagged a
  RETURNED-but-still-outstanding invoice, but the dunning reminder pipeline
  silently excluded it one layer above where the outstanding check would
  say it owes money — so that invoice's customer was shown as "needs
  attention" in one surface and never got an actual reminder from the
  other. `eligible_invoices()` now filters on
  `ledgers.services.OPEN_SALES_STATUSES`, matching the payment-health query.
- **G-23**: `customer_risk_snapshot()` made the exact same residual-AR
  invisible to credit-risk aging/overdue, and by extension to the
  auto-credit-hold check that reads it — a customer whose only overdue
  exposure was a fully-returned invoice with genuine residual AR (a
  post-return debit note) could not trigger a hold that should have fired.
  Confirmed with the user before fixing, since this changes real
  credit-hold behavior, not just a read-only report. Now filters on
  `OPEN_SALES_STATUSES` too.

**Regression tests**: `test_a07_dunning.py::test_g20_eligible_invoices_matches_payment_health_for_returned_invoice`
and `::test_g23_customer_risk_snapshot_sees_returned_invoice_with_residual_ar`
— both build the same realistic scenario (partial payment, full return with
CR-124 auto-unallocate netting to zero on its own, then a post-return debit
note leaving genuine residual AR) and assert the respective reader now sees it.

---

## 6. GST/accounting period-lock (`assert_period_allows_money_amend`)

Not a stored field — an enforcement **gate function**
(`backend/reporting/gst_periods.py:109-177`) that every money-amend flow is
expected to call before writing, so a document can't be created/completed/
cancelled/amended with a date that falls inside a closed or soft-closed GST
return period or accounting period. `CLOSED` always blocks; `SOFT_CLOSED`
blocks unless the caller passes `allow_soft_closed=True` (the convention for
cancel/reverse "unwind" operations, so a completed document can still be
undone after a soft-close). This entry's risk shape is different from the
others above: it's not "two readers disagree on a value," it's **"one
sibling flow enforces the gate and another doesn't,"** which is just as
capable of producing silent drift between what was filed for a period and
what the system now shows for it.

**Call sites** (confirmed via full trace, 2026-09-13) span sales invoice
complete/cancel/amend, sales return complete/cancel, sales CN/DN complete/
cancel, purchase invoice complete/cancel/amend, purchase return complete/
cancel, purchase CN/DN complete/cancel, Bill of Entry complete/cancel, every
payment/allocation/reversal/refund action, manual stock adjustments/expiry
write-off/stock-count post, stock transfer complete/cancel, manufacturing
work-order release/complete/cancel, payroll pay-run complete/cancel, and the
shared low-level `PostingService.post`/`.reverse`. All confirmed to gate
**before** the status flip / stock or GL write, inside the same
`select_for_update` + atomic block — the established pattern is consistent
almost everywhere it's used.

**Known inconsistency — FIXED 2026-09-13** (two sibling-flow gaps, both
verified by direct read of the function body before fixing):
- `backend/purchases/grn_service.py` — `GoodsReceiptService.complete()`
  (line 30) and `.cancel()` (line 118) post stock movements carrying
  `unit_cost` (valuation-relevant) with **no `gst_periods` import at all** —
  its direct sibling, `PurchaseInvoice.complete()`/`.cancel()`
  (`purchases/services.py:697,849`), gates consistently on `invoice_date`.
  Mitigating detail: neither `complete()` nor `cancel()` passes a
  `movement_date` to `InventoryService.post_movement()`, so the
  `StockMovement` row itself always lands on today's date regardless of
  `grn.receipt_date` — the actual stock ledger can't be backdated through
  this path today. The real exposure is document-level: a GRN whose
  `receipt_date` falls inside a closed period can still be completed or
  cancelled, so the period's *document/valuation-event picture* can change
  after that period was filed, even though the movement's own date doesn't
  move.
- `backend/sales/notes_services.py` — `complete_challan()` (line 807) gates
  on `challan.challan_date` before posting stock (`:817-820`, "CR-019: gate
  closed periods before stock/number when challan posts stock"); its
  unwind counterpart `cancel_challan()` (line 1013) reverses that same
  stock posting (restoring quantities, reversing FIFO peels,
  `:1039-1060`) with **no gate call anywhere in the function**. Same
  mitigating detail applies (the reversal's `post_movement` call doesn't
  pass `movement_date` either) — the live exposure is the challan's own
  status/date retroactively changing a closed period's document picture,
  not a backdated stock ledger entry.

Fixed — tracked as **G-21** (GRN) and **G-22** (challan cancel) in
`TESTING_STRATEGY.md`. `GoodsReceiptService.complete()`/`.cancel()` now gate
on `grn.receipt_date` (cancel with `allow_soft_closed=True`, mirroring
`PurchaseInvoice.cancel`); `cancel_challan()` now gates on `challan_date`
(guarded by `challan.stock_posted`, also `allow_soft_closed=True`) before
reversing the stock posting. Each fix verified red-before-green: the new
regression test was confirmed to fail with the fix temporarily reverted, then
pass restored — `tests/workflows/test_wf_grn.py::test_wf_grn_complete_blocked_in_soft_closed_period`
/ `::test_wf_grn_cancel_blocked_in_hard_closed_period`,
`tests/test_a10_period_centralization.py::test_g22_challan_cancel_blocked_in_hard_closed_period`.

**Structural guard built**: `scripts/ci_gates/guards/guard_period_gate_coverage.py`
— a static, `ast`-based registry guard covering 23 individually-verified call
sites across sales/purchases/notes/GRN/BoE/payments services. It fails if any
registered `complete()`/`cancel()` stops calling
`assert_period_allows_money_amend`, the same way `guard_no_raw_unit_cost_update`
guards its own concern. Auto-discovered and self-tested by
`run_guards.py`/`--selftest`. This would have caught G-21/G-22 the moment
they were written — extend its registry (and this section's call-site list)
together as more sites get individually verified; don't add an entry you
haven't personally confirmed calls the gate.

---

## 7. `Company.accounting_enabled`

`backend/accounts/models.py:203` — `BooleanField(default=False)`, a
two-way toggle (can be disabled after being enabled; nothing prevents
flipping back and forth). Only changeable via
`AccountingSettingsView.post` (`backend/accounting/views.py:442-458`,
Owner-only) — excluded from the general company-settings PATCH serializer
on purpose.

**GL-posting gates** (~20 call sites checking `if company.accounting_enabled:`
before calling `PostingService`/creating a `JournalEntry`): sales invoice
complete/amend/cancel (`sales/services.py`), sales return completion
(`sales/return_service.py:295`), sales/purchase CN/DN complete/cancel
(`notes_services.py` both sides), purchase invoice complete/amend/cancel,
Bill of Entry post/reverse, every receipt/payment/allocation posting
(`payments/services.py`), manufacturing work-order release/complete/cancel,
and payroll pay-run post/cancel/void.

**Readers, verified 2026-09-13** (this entry started from an agent claim
that turned out to be wrong on the most important point — see below;
recorded here so the same overstated claim doesn't get re-investigated
from scratch later):
- `backend/accounting/reports.py` — `trial_balance()`, `profit_and_loss()`,
  `balance_sheet()`, `cash_flow()` have **no `accounting_enabled` check
  inside the functions themselves** — querying `JournalLine` with the flag
  off returns a clean, "balanced" all-zero report, indistinguishable from a
  genuinely inactive company. **This looked like a live masking bug**, the
  same shape as G-17/18/19/20 — but it isn't one: the *only* production
  caller of these four functions is `AccountingReportView`
  (`accounting/views.py:495`), which extends `AccountingEnabledMixin`
  (`:36-40`) — its `initial()` raises `BusinessRuleError` before `get()`
  ever runs if `accounting_enabled` is False. The misleading-zeros path is
  unreachable through the real API. (Other callers of these functions —
  `core/invariants/reports.py`, `core/invariants/gl.py`, a demo-seed
  management command — are internal correctness/ops tooling where a
  vacuous pass on empty data is fine, not a user-facing report.)
- `accounting/services.py` `BooksHealthService` — `DOCUMENT_MISSING_POSTING`,
  `CUSTOMER_ADVANCE_MISMATCH`, and the `DOCS_GL_*_MISMATCH` checks all
  explicitly branch on `company.accounting_enabled` (short-circuit or
  downgrade severity when off) — correctly distinguishes "disabled" from
  "genuinely zero."
- `reporting/gst_health.py`, `reporting/tds_worksheets.py`, `insights/alerts.py`
  — none of these reference `JournalLine`/`JournalEntry` at all; they're
  purely document-derived and structurally can't be affected by the flag.

**Known inconsistencies**: none found in the live system — the one plausible
bug (misleading all-zero financial statements) is closed off by the view-layer
mixin, verified by reading `AccountingReportView`'s class declaration
directly. This field joins Credit/Debit Note status as an audited-clean
entry.

**Operational gotcha, not a bug** (documented so it isn't mistaken for one):
enabling `accounting_enabled` does **not** backfill historical postings —
`AccountingSettingsView.post` only seeds the chart of accounts
(`accounting/views.py:456-457`). Two management commands
(`backfill_accounting_postings.py`, `backfill_missing_postings.py`) exist for
an operator to run manually after flipping the flag on; if nobody runs them,
every document completed before the flag was enabled permanently has no GL
trail, silently, while documents completed after do. Worth surfacing in the
Owner-facing UI when they enable accounting (out of scope for this doc to
fix — noted here as a real gap in the *product*, not in test coverage).

**Suggested test**: none needed for the reports themselves (already
covered — a request to `AccountingReportView` with `accounting_enabled=False`
should 4xx; if that test doesn't already exist, add it as a straightforward
regression, not a cross-flow gap).

---

## Known inconsistencies — summary (all six fixed, 2026-09-13)

| ID | Field | What was wrong | Direction | Regression test |
|---|---|---|---|---|
| G-17 | `SalesInvoice.status` (FE) | `paidAwareStatus()` checked payment state before status | Masked | `SalesHistoryPage.test.tsx` + 3 more page tests |
| G-18 | `PurchaseInvoice.status` | AP_DUE_7D alert + cash-flow forecast excluded RETURNED; ledgers/aging/dashboard included it | Under-alerted | `test_g18_ap_due_and_cashflow_include_returned_purchase_with_residual_payable` |
| G-19 | `StockBalance` | DEAD_STOCK alert ignored `reserved`; low-stock/health-score didn't | Over-alerted | `test_g19_dead_stock_ignores_fully_reserved_stock` |
| G-20 | `PaymentAllocation` | Dunning excluded RETURNED invoices; payment-health alert included them | Under-reminded | `test_g20_eligible_invoices_matches_payment_health_for_returned_invoice` |
| G-21 | Period-lock gate | `GoodsReceiptService.complete()`/`.cancel()` never called the gate; sibling `PurchaseInvoice` does | Under-enforced | `test_wf_grn_complete_blocked_in_soft_closed_period` + cancel variant |
| G-22 | Period-lock gate | `cancel_challan()` never called the gate; its own `complete_challan()` does | Under-enforced | `test_g22_challan_cancel_blocked_in_hard_closed_period` |

G-17/18/19/20 are one bug shape (**CF-001**, `TESTING_STRATEGY.md` §7): two
independent readers of the same field disagreeing on its status-set, with
nothing forcing them to agree. G-21/22 are a sibling shape one level up: two
flows doing the same kind of write (post/reverse stock with valuation)
disagreeing on whether to enforce the period lock. G-18/19/20 were fixed in
a separate session (its own fresh worktree, so it independently rediscovered
and verified all three from first principles rather than trusting this
document — a useful cross-check) and merged into this branch's working tree
on 2026-09-13; combined regression run: 415 passed, 6 skipped (pre-existing).
A structural guard (`guard_period_gate_coverage`) now prevents G-21/22's
shape from recurring for its 23 registered call sites — no equivalent
guard exists yet for the G-17/18/20 shape (a reader's status-set filter
drifting from its sibling's); that remains open as weak-assumption #12 in
`TESTING_STRATEGY.md` §8 (the canonical-semantics recommendation). See
`TESTING_STRATEGY.md` §7 for the full gap register these feed into.
