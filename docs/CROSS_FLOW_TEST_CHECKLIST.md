# Cross-Flow Test Checklist

**Status:** Living document · **Created:** 2026-09-14 · **Last extended:**
2026-09-14 (CFT ids gated: CFT-114–120 implemented; CFT index in
`FREEZE_SCOPE_COVERAGE.md`) ·
**Owner:** QA + product
**Role in the quality model:** A product-facing test checklist for **Graph 2
(Impact)** — for every business event, what should change, what must not
change, whether the change is reversible, and whether all surfaces agree.
Companion to [`CROSS_FLOW_IMPACT_MAP.md`](CROSS_FLOW_IMPACT_MAP.md) (the
field/reader index) and [`EVENT_MATRIX.md`](EVENT_MATRIX.md) (the generated
event × projection grid). Method: [`TESTING_STRATEGY.md`](TESTING_STRATEGY.md)
§2.2 ("the six questions").

**2026-09-14 extension**: the first version of this checklist was scoped to
the generic sales/purchase/inventory/reports shape of the source list. It was
then checked against [`FREEZE_SCOPE.md`](FREEZE_SCOPE.md)'s frozen pilot scope
(A1–A26) and [`TESTING_STRATEGY.md`](TESTING_STRATEGY.md) §7's open gap
register — several flows that are explicitly **SUPPORTED** for the pilot had
no cross-flow test case at all (tax breakup correctness, TDS/TCS, quotations,
advances/refunds, bank reconciliation, document numbering/audit trail,
RBAC/plan-limit gating, PDF/export correctness, concurrency races). Those are
now covered under "Additional coverage from the frozen pilot scope" below.

**IDs:** every case has a stable **`CFT-NNN`** (or **`CFT-NID-01`** for a
named non-identity). Cite that id from `FREEZE_SCOPE_COVERAGE.md` and from
tests. Do not cite bullet prose — wording will drift; the id will not.

**EVENT_MATRIX:** each section lists the generated `verb × document_type`
cells it exercises. Edit `validation/catalog/events.yaml` if a section has
no cell (do not let this file invent a parallel event list).

## Why this exists

This checklist was drafted from a generic ERP cross-dependency test list and
then corrected against BizBoard's actual status model, business rules, and
known bug history (`CROSS_FLOW_IMPACT_MAP.md`, `EVENT_MATRIX.md`,
`TESTING_STRATEGY.md`, `FREEZE_SCOPE.md`) — not against generic accounting
assumptions. Several of the original cases described behavior BizBoard does
not actually have (see "Corrections" below); those were fixed or removed
rather than carried forward.

**How to use it:** for each row, the case is not "does the button work" —
it's "does this business event propagate correctly through every reader of
the state it touches, and does nothing else move that shouldn't." When
writing the actual test, name the concrete BizBoard field/status/service it
exercises (many of these map directly to sections in
`CROSS_FLOW_IMPACT_MAP.md`) and record the result in
`FREEZE_SCOPE_COVERAGE.md` **as `CFT-NNN`**.

---

## Named non-identities (asserted to *differ*)

Same registration shape as locked **B2** (`pdf_as_issued` vs
`live_outstanding` → `projection.pdf_snapshot_differs_from_live_outstanding_after_return`).
A future PR that "unifies" these pairs is a defect, not a cleanup.

| Id | Pair | Must stay different | Gate |
|---|---|---|---|
| B2 | PDF snapshot vs live outstanding | After a full return with no residual DN, issued PDF totals must **not** equal live `/pay/:token` outstanding | `projection.pdf_snapshot_differs_from_live_outstanding_after_return` |
| **CFT-NID-01** | Reports/ledgers vs insights on RETURNED | Money reports include RETURNED (residual AR/AP); insights/analytics exclude RETURNED (the sale never happened, product-wise) | `projection.operational_sales_not_collapsed_into_open_receivables` + `test_status_semantics.test_reporting_includes_returned_insights_exclude` |

---

## Corrections to the source checklist (read before using the list below)

1. **Terminology**: BizBoard's status enum is `DRAFT → COMPLETED →
   CANCELLED/RETURNED`. Use "Complete" not "commit."
2. **Over-payment is rejected, not "handled consistently."** Allocating more
   than an invoice's open outstanding raises a hard error
   (`payments/services.py`). A customer can still pay a larger amount, but
   the excess must go to a different invoice or stay unallocated as advance
   — it cannot silently overpay one invoice.
3. **Negative stock is a company setting with two states, not one.**
   `negative_stock_policy` is `BLOCK` or `WARN` (a third `ALLOW` state
   existed and was removed — R2-025). "Insufficient stock" tests must be
   parameterized on this setting.
4. **A `RETURNED` invoice can still owe money.** This is the single
   most-bugged field in the system (G-17/18/20/23, all fixed 2026-09-12/13)
   — a fully-returned invoice with a post-return debit note can carry
   genuine residual AR. "Sales return → outstanding reduces" is true on
   average, not universally.
5. **Reports and analytics deliberately disagree on RETURNED, by design
   (CFT-NID-01).** Ledgers/reporting money totals *include* RETURNED (it
   can still carry a balance); insights/analytics (best-seller, trending,
   margin, alerts) *exclude* RETURNED (a fully-reversed sale never happened,
   product-wise). Don't write one test asserting both use the same status
   set. **Do not unify the two `OPEN_SALES` imports** — CI must stay red if
   they collapse.
6. **Costing is FIFO with a documented approximation.** Running
   weighted-average is used as an operational proxy for perpetual FIFO COGS
   (weak assumption C3, `TESTING_STRATEGY.md` §6.2).
7. **Backdating is governed by a period lock**, not a vague "system's
   defined rules." `assert_period_allows_money_amend` blocks any
   money-affecting write dated into a `CLOSED` period; a `SOFT_CLOSED`
   period blocks new documents but allows unwind operations (cancel,
   return) via `allow_soft_closed=True`.
8. **There is no voice-entry feature in BizBoard.** Verified — no
   speech/voice input path exists anywhere in the codebase. The real
   alternate-entry channels are **Tally import** and API-created documents
   (gateway webhook → receipt, POS sale). The "Voice / Alternate Entry"
   section below tests those instead.
9. **Credit/debit notes are separate document types from "return," not a
   synonym for it.** A return can auto-generate a credit note, but a
   credit/debit note can also be raised standalone (price correction,
   discount) with no stock movement (`debit_note` stock impact = "no" in
   the event matrix).
10. **Idempotency is a named contract.** Webhook replay is guaranteed a
    no-op; there's a general `IdempotencyRecord` contract for mutating calls
    (`test_wf51_idempotency_contract`).

---

## ID index

| Range | Section |
|---|---|
| CFT-NID-01 | Named non-identity (RETURNED reports vs insights) |
| CFT-001–011 | Sales & inventory |
| CFT-012–018 | Purchase & inventory |
| CFT-019–025 | Sales ↔ customer ↔ receivables |
| CFT-026–032 | Purchase ↔ supplier ↔ payables |
| CFT-033–041 | Inventory ↔ products |
| CFT-042–048 | Inventory ↔ reports |
| CFT-049–055 | Sales ↔ reports ↔ profit |
| CFT-056–059 | Dates & periods |
| CFT-060–065 | Customer/supplier statements |
| CFT-066–073 | Dashboard & insights |
| CFT-074–078 | Alternate entry channels |
| CFT-079–086 | Tax breakup |
| CFT-087–090 | TDS / TCS |
| CFT-091–094 | Advances, refunds & bad debt |
| CFT-095–096 | Bank reconciliation |
| CFT-097–099 | Numbering & audit |
| CFT-100–102 | H9 correction path |
| CFT-103–105 | RBAC / plan / tenant |
| CFT-106–108 | PDF / exports |
| CFT-109–111 | Concurrency (oversell / over-alloc / idempotency) |
| CFT-112–113 | Product lookup & quotation→invoice (direct) |
| CFT-114–115 | Quotation → SO → challan chain |
| CFT-116 | IRN / e-way lock |
| CFT-117–118 | Credit-hold / credit-limit |
| CFT-119 | Batch / serial restore on return |
| CFT-120 | Multi-tab concurrent invoice edit (G-11a) |
| CFT-121–125 | Core lifecycle assertions (per document type) |

---

## Sales & Inventory

**EVENT_MATRIX:** `complete × sales_invoice`, `amend × sales_invoice`,
`cancel × sales_invoice`, `return × sales_invoice`, `complete × pos_sale`,
`return × pos_sale`.

- **CFT-001** — Draft sales invoice: stock unchanged; sales/revenue/receivables/profit/
  insights unaffected; invoice does not appear in any committed report or
  dashboard total.
- **CFT-002** — Complete a sales invoice: stock decreases (FIFO/running-cost layer
  consumed); sales, revenue, receivables, GL, GST, dashboard,
  attention/badges all update together (one event, all Graph-2 projections).
- **CFT-003** — Amend a completed invoice (BizBoard's actual verb is `amend`, not
  in-place edit): stock, GL, AR, and reports move to match the revised
  lines; the period-lock gate must block amending into a closed period even
  if the original invoice predates the close.
- **CFT-004** — Cancel a completed invoice: stock restored, GL/AR/GST reversed,
  dashboard/insights reversed; cancel must still succeed against a
  soft-closed period (unwind exception) but not a hard-closed one.
- **CFT-005** — Fully return a completed invoice: status flips to RETURNED; stock
  restored for returned lines; revenue/COGS/profit reversed in reports;
  insights/analytics treat it as if the sale never happened (excluded),
  while ledgers/outstanding still check it for a residual balance — assert
  both, they're not supposed to match (**CFT-NID-01**).
- **CFT-006** — Partial return: status stays COMPLETED (BizBoard does not flip status
  until every sold line is fully returned); only the returned quantity/
  value reverses in stock, revenue, and COGS.
- **CFT-007** — Cancel/reverse a sales return: previously-returned stock is removed
  again, revenue/COGS/receivable restored, and invoice status reverts to
  COMPLETED only if no other completed return remains against it.
- **CFT-008** — Multi-line invoice, one line returned: only that line's stock and value
  change; other lines' stock/revenue untouched.
- **CFT-009** — Insufficient stock at invoice completion: behavior must match the
  company's `negative_stock_policy` — `BLOCK` rejects completion outright;
  `WARN` allows completion but stock goes negative and a warning is
  logged/surfaced. Test both settings explicitly.
- **CFT-010** — Duplicate submission of the same invoice (double-click save, retried
  request, replayed webhook): idempotency contract must prevent a second
  stock hit or a second invoice number.
- **CFT-011** — POS sale (a distinct document type, `pos_sale`): same complete/cancel/
  return cross-flow assertions as a sales invoice — verify independently,
  don't assume it's "just a fast invoice." POS returns go through
  `/sales/returns` (D15).

## Purchase & Inventory

**EVENT_MATRIX:** `complete × purchase_invoice`, `cancel × purchase_invoice`,
`return × purchase_invoice`, `amend × purchase_invoice`. GRN period-lock is
G-21 (not a separate matrix verb; still a required cancel/complete gate).

- **CFT-012** — Draft purchase invoice: stock unchanged; purchase/payable/GL/GST reports
  unaffected.
- **CFT-013** — Complete a purchase invoice: stock increases at the invoiced unit cost;
  payable, purchase reports, GST/ITC all update.
- **CFT-014** — Cancel a completed purchase: stock decreases back, payable/GL/GST
  reverse; must respect the period lock the same way the sales side does.
- **CFT-015** — Purchase return: stock decreases, payable reduces, GST/ITC impact
  reverses; if the return happens via GRN, confirm the GRN path also
  enforces the period-lock gate (historically a real bug — G-21 — GRN
  complete/cancel posted valuation-relevant stock with no period gate at
  all until 2026-09-13).
- **CFT-016** — Cancel a purchase return: stock and payable restored to the pre-return
  state.
- **CFT-017** — Amend a completed purchase: inventory valuation, COGS for any sales that
  already consumed that stock, and reports stay consistent — specifically
  check a sale that already sold from a purchase lot which then gets
  amended.
- **CFT-018** — GRN cancel: stock reversed, and the reversal itself must gate on the
  period lock (the unwind leg is the one that's historically been
  forgotten, not the forward leg — test cancel/reverse paths, not just
  complete, for period enforcement).

## Sales ↔ Customer ↔ Receivables

**EVENT_MATRIX:** `complete × sales_invoice`, `allocate × customer_receipt`,
`reverse_allocation × customer_receipt`, `void × customer_receipt`,
`return × sales_invoice`, `debit_note × sales_debit_note`,
`cancel × sales_invoice`.

- **CFT-019** — Complete a sales invoice: customer outstanding increases by grand_total
  (+ TCS, − any auto-applied CN).
- **CFT-020** — Record a customer receipt and allocate it: outstanding decreases by
  exactly the allocated amount.
- **CFT-021** — Reverse/void a payment allocation: outstanding increases back by that
  amount; the reversed journal entry is also reversed, not just the
  allocation flag.
- **CFT-022** — Return an invoice: outstanding reduces, but assert against the actual
  formula (`grand_total + tcs − CN + DN − allocated`), not just "it goes
  down" — a post-return debit note can leave genuine residual AR on a
  RETURNED invoice (see correction #4).
- **CFT-023** — Cancel an invoice: outstanding reverses to zero for that invoice.
- **CFT-024** — Partial payment: only the paid amount affects outstanding; balance =
  grand_total − allocated.
- **CFT-025** — Payment exceeding the invoice's open outstanding: must be rejected by
  allocation, not silently accepted — assert the error, then verify the
  payer can still allocate the excess to a different invoice or leave it
  as unallocated customer advance.

## Purchase ↔ Supplier ↔ Payables

**EVENT_MATRIX:** `complete × purchase_invoice`, `allocate × supplier_payment`,
`reverse_allocation × supplier_payment`, `void × supplier_payment`,
`return × purchase_invoice`, `debit_note × purchase_debit_note`,
`cancel × purchase_invoice`.

- **CFT-026** — Complete a purchase: supplier payable increases.
- **CFT-027** — Record supplier payment + allocate: payable decreases by the allocated
  amount.
- **CFT-028** — Reverse/void supplier payment allocation: payable increases back, linked
  journal entry reversed.
- **CFT-029** — Purchase return: payable reduces — same RETURNED-with-residual-payable
  risk as the sales side. This is the actual bug G-18 that was found and
  fixed: RETURNED purchases with residual payable were invisible to the
  AP-due alert and cash-flow forecast even though the dashboard AP total
  included them.
- **CFT-030** — Cancel a purchase: payable reverses.
- **CFT-031** — Partial supplier payment: only the paid amount affects payable.
- **CFT-032** — Over-allocation on AP: same hard reject as CFT-025 on the purchase side.

## Inventory ↔ Products

**EVENT_MATRIX:** `complete`/`return`/`cancel` × sales and purchase invoices;
`stock_transfer × stock_transfer`; `stock_count × stock_count_session`;
`import × import_job`.

- **CFT-033** — Sales completion reduces product stock balance (via the single write
  path, `InventoryService.post_movement` — there is no other place stock
  is mutated).
- **CFT-034** — Purchase completion increases product stock balance.
- **CFT-035** — Sales return increases stock; purchase return decreases stock.
- **CFT-036** — Manual stock adjustment: `StockBalance` after adjustment must equal
  `Σ StockMovement` for that product/warehouse (a formally checked
  invariant — `core/invariants/inventory.py::balance_equals_movements` —
  any drift is a first-class bug).
- **CFT-037** — Stock transfer between warehouses: total business-wide stock unchanged;
  per-warehouse stock changes correctly; transfer respects the period lock
  and appears in stock movement/reports.
- **CFT-038** — Cancelled/deleted invoice: no residual quantity change survives —
  re-verify against the movement-sum invariant above, not just "stock
  looks right on the product page."
- **CFT-039** — Reprocessed/re-synced transaction (e.g. Tally re-import): stock does not
  double-post — an explicit idempotency requirement at import scale.
- **CFT-040** — Fully-reserved stock (committed to an open, uncompleted sales order):
  `available = on_hand − reserved` must be the number every screen uses —
  raw `on_hand` without the reserved subtraction is a known bug shape
  (G-19: dead-stock alert once ignored `reserved` and could flag/value
  fully-committed stock as "dead"). Test that low-stock, dead-stock, and
  product-page stock all agree on a fully-reserved SKU.
- **CFT-041** — `inventory_summary()` independently recomputes on-hand from movements
  and flags drift against the cached `StockBalance` — a report-level
  self-check; test that drift is actually surfaced, not silently
  swallowed.

## Inventory ↔ Reports

**EVENT_MATRIX:** same stock verbs as above; `reports` column = yes on
complete/return/cancel/stock_transfer/stock_count.

- **CFT-042** — Product-page stock matches inventory report stock (same
  `available_quantity` read).
- **CFT-043** — Stock movement report reconciles: opening + purchases − sales + returns
  ± adjustments = closing, per warehouse and in aggregate.
- **CFT-044** — Sales return and purchase return appear consistently across stock
  movement, the respective sales/purchase report, and product stock — same
  event, same three surfaces.
- **CFT-045** — Cancelled transactions contribute nothing to active stock/report totals.
- **CFT-046** — Draft transactions never appear in committed/financial totals — confirm
  per surface (invoice list, dashboard, reports, GST) since each has its
  own status filter and they've drifted from each other before (the whole
  reason `status_semantics.py`'s shared predicates exist).
- **CFT-047** — Draft vs completed filters agree across invoice list, dashboard, GST
  worksheets, and exports for the same company/period.
- **CFT-048** — (reserved for warehouse-filtered inventory report vs all-godowns
  aggregate — must not silently use the default godown when the UI says All).

## Sales ↔ Reports ↔ Profit

**EVENT_MATRIX:** `complete`/`return`/`cancel`/`amend` × `sales_invoice`;
dashboard + reports columns. **CFT-NID-01** applies to every RETURNED case.

- **CFT-049** — Completed sale increases sales/revenue in reports.
- **CFT-050** — Sales return reduces sales/revenue — but verify against the *reporting*
  status set (includes RETURNED, netted via CN) vs the *insights* status
  set (excludes RETURNED entirely) separately; they're intentionally
  different views (**CFT-NID-01**).
- **CFT-051** — COGS/profit reflects the running-cost (FIFO-approximating) valuation at
  the time of sale, not a re-priced current cost.
- **CFT-052** — Return reverses the corresponding revenue and COGS/profit for the
  returned quantity only.
- **CFT-053** — Cancellation reverses all reporting impact of that invoice.
- **CFT-054** — Dashboard, sales report, customer statement, and invoice summary
  reconcile to the same number for the same period/invoice set.
- **CFT-055** — Dashboard profit reconciles with underlying sales and purchase/COGS data
  — same source, not independently recomputed.

## Dates & Periods

**EVENT_MATRIX:** `historical_period: required` on money verbs;
`close_period × accounting_period`, `close_period × gst_period`.

- **CFT-056** — Changing an invoice's date moves it to the correct reporting period,
  provided the target period isn't closed (if it is, the edit itself must
  be rejected by the period-lock gate, not silently succeed into a filed
  period).
- **CFT-057** — A transaction crossing a month/year boundary is reported by transaction
  date consistently across stock movement, GL, and GST.
- **CFT-058** — Backdating into a `CLOSED` period is always blocked; backdating into a
  `SOFT_CLOSED` period is blocked for new/forward postings but allowed for
  unwind operations (cancel, return) via the documented exception — test
  both the block and the exception explicitly, since forgetting the
  exception on a *cancel* path (not the *complete* path) is the exact bug
  class already found twice (G-21 GRN, G-22 challan cancel).
- **CFT-059** — A return dated into a different period than its original sale affects
  the return's own period correctly without altering the original
  period's historical totals.

## Customer/Supplier Statements

**EVENT_MATRIX:** `complete`/`return`/`allocate`/`void` × sales and purchase
documents; `channel` includes `/pay/:token` where live outstanding is B3.

- **CFT-060** — Every completed customer transaction appears in the customer statement.
- **CFT-061** — Sales return appears in the customer statement.
- **CFT-062** — Payment appears in the customer statement.
- **CFT-063** — Cancelled transactions contribute nothing to the statement balance.
- **CFT-064** — Customer-profile outstanding equals the statement balance — same
  `LedgerService` formula, not two separate computations.
- **CFT-065** — Supplier statement mirrors all of the above for purchases/returns/
  payments.

## Dashboard & Insights

**EVENT_MATRIX:** `dashboard` + `attention` columns on complete/return/allocate.
**CFT-NID-01** for any RETURNED vs best-seller comparison.

- **CFT-066** — Complete a sale → dashboard sales update.
- **CFT-067** — Sales return → dashboard sales decrease, but confirm which dashboard
  metric: money totals include RETURNED (netted), while "best-seller"/
  trending-style insights exclude it entirely — these can legitimately
  show different movement for the same return; that's not a bug
  (**CFT-NID-01**).
- **CFT-068** — Purchase → dashboard purchase/stock metrics update.
- **CFT-069** — Payment → receivable/payable metrics update.
- **CFT-070** — Cancellation → all dashboard metrics for that document reverse.
- **CFT-071** — Editing/amending a transaction updates insights without creating a
  duplicate value (no double-counting the old + new state).
- **CFT-072** — Draft transactions never contaminate KPIs.
- **CFT-073** — Dashboard and detailed reports use the same underlying query/status set
  — where they're allowed to differ (money vs. analytics, per CFT-NID-01),
  that difference should be intentional and documented, not accidental drift.

## Alternate entry channels (replaces "Voice" — no such feature exists)

**EVENT_MATRIX:** `import × import_job`; `complete × pos_sale`; allocate/void
on receipts (webhook capture). No `otp_login` verb. No PDF column (B2).

- **CFT-074** — Tally import creates DRAFT/COMPLETED documents directly, bypassing the
  normal `complete()` recompute/numbering path — verify imported documents
  still produce correct stock, GL, and numbering-sequence integrity (no
  gaps, no duplicates) despite the different write path.
- **CFT-075** — Large-scale import is idempotent: re-running the same import batch does
  not double-post stock or duplicate invoice numbers.
- **CFT-076** — A partial-failure import can be resumed without double-processing
  already-imported records.
- **CFT-077** — Gateway webhook (online payment collection) → receipt → allocation → GL:
  replaying the same webhook is a no-op; a capture against a cancelled or
  closed-period invoice parks the payment and refunds rather than
  corrupting that invoice's state.
- **CFT-078** — If a voice-entry feature is actually planned/roadmapped, its create/
  edit/commit flow needs to be defined before test cases can be written —
  nothing in the codebase currently implements it. (Keep as LIM / do-not-
  invent until then.)

## Additional coverage from the frozen pilot scope (FREEZE_SCOPE.md)

Everything below is **SUPPORTED** in the current freeze (A1–A26, G1–G7's
resolved decisions) and touches cross-flow state the same way the sections
above do, but had no case in the original list.

### Tax breakup correctness (GST, cess, RCM, composition)

**EVENT_MATRIX:** `complete`/`return`/`amend` × sales and purchase invoices;
`gst` column = yes. Freeze A1–A3.

- **CFT-079** — Intra-state sale: CGST + SGST computed and split correctly; both legs sum
  to the invoice's total tax; GL posts to the correct CGST/SGST control
  accounts (A1).
- **CFT-080** — Inter-state sale: IGST only (no CGST/SGST), driven by place-of-supply, not
  by customer address alone — a customer with a different billing vs
  shipping state must use the shipping/place-of-supply state to decide
  intra- vs inter-state (A2).
- **CFT-081** — Non-GST / nil-rated invoice: completes with zero tax; totals and GL still
  balance to zero tax without breaking the trial balance (A3).
- **CFT-082** — Per-unit/specific cess (e.g. pan masala): `cess_amount` is added on top of
  ad-valorem tax, flows into the invoice grand total, GL, and GST reports
  consistently — verify it survives a partial return (only the returned
  quantity's cess reverses) and a discount (cess base is/isn't discounted
  per the documented rule — confirm which).
- **CFT-083** — Reverse charge (RCM) purchase: self-invoice is generated, RCM liability is
  posted, and the corresponding ITC is recorded — both legs must appear
  together; a self-invoice without its ITC leg (or vice versa) is a defect.
- **CFT-084** — Composition-dealer company: bill of supply carries no CGST/SGST/IGST
  fields at all (not zero-valued fields — no tax fields), and its sales
  never appear in a regular-dealer GSTR-1 pipeline, only in CMP-08.
- **CFT-085** — ITC eligibility classification (`itc_eligibility`: blocked / ineligible):
  a purchase marked ITC-blocked still posts stock and payable normally but
  must **not** contribute to the ITC claimed in GST reports/worksheets —
  verify the exclusion at the report layer, not just a UI label.
- **CFT-086** — Discounts (line %, line amount, document-level): correctly reduce the
  taxable value before tax computation; a >100% discount is rejected, not
  silently clamped or allowed to produce a negative line total.

### TDS / TCS (194Q / 206C)

**EVENT_MATRIX:** `complete`/`return` × sales and purchase invoices; `gl` +
`gst` + `reports`.

- **CFT-087** — TCS (206C) on a qualifying sale: collected at the correct threshold/rate,
  posted to GL account 2265/206C control, and appears in the TCS worksheet
  reconciled to the source transaction.
- **CFT-088** — TDS (194Q) on a qualifying purchase: deducted correctly, posted to GL, and
  reconciles to the TDS worksheet.
- **CFT-089** — **Explicit override**: when a user enters an explicit withholding amount
  instead of letting it derive from the rate, both the entered amount *and*
  the rate-derived amount are logged (not just the final value) — a test
  should assert the log shows both, and that the explicit amount is what
  actually posts to GL, per [[tcs-explicit-amount-overrides-rate]].
- **CFT-090** — TCS/TDS on a return: the withheld amount reverses proportionally with the
  returned value, and the worksheet reflects the reversal in the correct
  period.

### Advances, refunds & bad debt

**EVENT_MATRIX:** `allocate`/`void` × `customer_receipt`; `debit_note` only
when residual AR is created — not for a goods return.

- **CFT-091** — Advance/on-account payment received before any invoice exists: posts as a
  liability (customer advance), with GST-on-advance where applicable (GSTR-1
  AT); when later allocated against a completed invoice, the advance
  liability is cleared and the GST-on-advance is adjusted (ATADJ) — not
  double-counted against the invoice's own GST.
- **CFT-092** — Customer refund (money returned, not a sales return of goods): reduces
  the receivable/advance balance and posts the correct GL entry; must not
  be confused with — or silently merged into — a sales-return credit note.
- **CFT-093** — Gateway refund + MDR/settlement reconciliation: a captured payment that
  is later refunded through the gateway reflects correctly in both the
  payment record and the bank/settlement reconciliation; a capture-vs-
  settlement amount mismatch (fees, partial settlement) is surfaced, not
  silently absorbed.
- **CFT-094** — Bad-debt write-off: reduces customer outstanding, posts to GL, and the
  written-off invoice no longer appears as collectible in aging/dunning —
  but its historical sales/COGS impact is **not** reversed (it was still a
  real sale; only the collectibility changed).

### Bank reconciliation & bank statement import

**EVENT_MATRIX:** no dedicated recon verb; B8 identity is
`projection.bank_recon_match_status_identity` (`match_status` on both UIs).
Import idempotency is G-3.

- **CFT-095** — Bank statement import auto-matches lines to existing receipts/payments;
  re-running the same import (or committing without an idempotency key —
  a "bare" re-commit) does not duplicate the auto-matched entries (G-3).
- **CFT-096** — A manually-matched reconciliation line and an auto-matched one both
  contribute to the same reconciled-balance total, without either being
  counted twice if the session is re-opened and re-saved. Both recon UIs
  write `BankStatementLine.match_status` (QOS-0082 / B8 — do not merge UIs
  in this checklist).

### Document numbering, audit trail & money-change audit

**EVENT_MATRIX:** `complete`/`cancel`/`amend` × sales_invoice (numbering is
an invariant, not a projection column).

- **CFT-097** — Document numbers are gap-free per series per financial year, including
  under concurrent completion (two invoices completed in parallel never
  collide or skip a number) — this is a formally checked invariant
  (`numbering.sequences_intact`), not just an eyeball check.
- **CFT-098** — Cancelling a completed invoice does not free its number for reuse; the
  gap left by a cancelled document is visible and explainable in numbering
  reports, distinct from a genuinely missing/corrupted sequence.
- **CFT-099** — Every mutation on a money-bearing entity writes an `AuditEvent`; every
  money-field change on an already-completed document additionally writes
  to the money-field audit log (`MoneyFieldAudit`) — verify both fire
  together on an amend, not just one.

### Invoice/purchase cancellation & amendment — number handling and the H9 correction path

**EVENT_MATRIX:** `cancel × sales_invoice`, `amend × sales_invoice`,
`close_period × accounting_period`.

- **CFT-100** — Cancelling a completed invoice reverses stock/GST/GL/AR as already
  covered above, **and** leaves the original document number retired
  (not reissued) with its cancelled state visible in every numbering and
  audit surface.
- **CFT-101** — Amending a completed invoice whose original period is still open uses
  the in-place `amend()` path (already covered in CFT-003).
- **CFT-102** — Amending a completed invoice whose original period is **closed** must
  instead go through the sanctioned H9 correction path: a reversing entry
  in the original (closed) period paired with a re-post entry in the
  current open period, the pair together netting to zero — verify the
  closed period's own totals are untouched and the real financial effect
  lands only in the open period.

### RBAC, plan limits & tenant isolation (transaction-gating)

**EVENT_MATRIX:** `invite × company_user` (channel); money verbs still
`historical_period: required` for the Owner path. G-4.

- **CFT-103** — A Sales-Staff-role user can complete/cancel/return within their granted
  capability flags and is blocked (with a clean 403, not a dead button)
  outside them — test this against the actual transaction endpoints, not
  just UI visibility, since a hidden-but-reachable action is its own bug
  class (G-4's actual root cause).
- **CFT-104** — Plan-limit enforcement (e.g. invoice-count quota) blocks the specific
  action it gates (fails closed) once the limit is hit, and unblocks
  immediately when the plan is upgraded — without needing a re-login.
- **CFT-105** — Every list/detail/mutation endpoint used in these cross-flow tests is
  company-scoped: tenant A's request against tenant B's invoice/customer/
  product id returns 404, not a permission error that leaks existence.

### PDF / document rendering & exports

**EVENT_MATRIX:** there is **no PDF column** (B2). Live outstanding is
`channel` on `return × sales_invoice`. Exports are `reports`.

- **CFT-106** — An invoice PDF generated after completion shows totals, tax breakup, and
  party details matching the live document at generation time.
- **CFT-107** — Re-generating the PDF after an amendment, partial return, or cancellation
  reflects the current state — an old cached PDF must not be served as if
  current, and a PDF generated pre-return should be identifiable as a
  snapshot of that point in time, not silently stale. After a full return
  with no residual DN, issued PDF vs `/pay/:token` **must differ** (B2/B3).
- **CFT-108** — Data exports (CSV/XLSX/JSON) match the source data for the same filter/
  period used on-screen — a report and its export must agree.

### Concurrency & idempotency (cross-cutting, formalized)

**EVENT_MATRIX:** `complete × sales_invoice` (stock), `allocate × customer_receipt`.
G-11a is Postgres-only locally.

- **CFT-109** — Two near-simultaneous completions against the same low-stock item cannot
  both succeed and oversell — the loser gets a clean rejection, not a
  negative-stock write that violates `negative_stock_policy=BLOCK`.
- **CFT-110** — Two near-simultaneous allocations against the same invoice's outstanding
  balance cannot together exceed it — same rejection guarantee as a single
  over-allocation (CFT-025), but under concurrency instead of sequential calls.
- **CFT-111** — Any mutating call replayed with the same idempotency key produces zero
  additional effect (WF-51's dedicated contract) — test this for at least
  one write in each major flow (invoice complete, payment allocate, stock
  adjustment), not only for the webhook-replay case already covered under
  "Alternate entry channels."

### Product lookup & quotation-to-invoice (direct)

**EVENT_MATRIX:** `convert × quotation` (extended). Direct convert does not
post stock/GL until the resulting invoice is completed (`complete × sales_invoice`).

- **CFT-112** — Barcode/SKU/name product lookup resolves to the correct, company-scoped
  product during invoice/purchase line entry — a search term that matches
  a product in another tenant must never resolve.
- **CFT-113** — A quotation has no stock or GL effect at any stage; converting it
  **directly** to an invoice creates a real invoice that then follows the
  normal draft→complete lifecycle — the quotation itself never appears in
  stock movement, GL, or financial reports at any point.

---

## Review-gap cases (added 2026-09-14)

In-scope for the rest of the quality model, previously missing from this
checklist. Do not treat these as optional.

### Quotation → Sales Order → Delivery Challan (WF-06/09/10)

**EVENT_MATRIX:** `convert × quotation`, `convert × sales_order`,
`convert × delivery_challan`, `complete × delivery_challan`,
`cancel × delivery_challan`, `complete × sales_invoice`.

- **CFT-114** — Cancel a Sales Order **after** a delivery challan was already created
  from it: reserved stock must release (or stay reserved only for the
  remaining open challan qty); the challan must not become an orphan that
  still holds reservation with no parent SO. Completing that challan then
  converting to invoice must not double-reserve or double-issue stock.
- **CFT-115** — Partial-convert a quotation: the converted qty becomes SO/challan/
  invoice through the normal chain; the **remainder** stays on the
  quotation and is still convertible. A second convert must not recreate
  the already-converted lines.

### E-invoice / e-way IRN lock

**EVENT_MATRIX:** `amend × sales_invoice` (note: live IRN blocks line amend),
`cancel × sales_invoice`. Suites: `test_einvoice_eway.py`,
`test_pj_einvoice_eway.py`.

- **CFT-116** — Once an IRN is generated (or marked MANUAL_IRN), line amend is blocked,
  and the block is **visible on the same screen that shows the IRN** (not
  only a 400 from a hidden API). Books cancel while a live IRN exists is
  blocked (`test_cancel_blocked_while_live_irn`); statutory IRN/ack fields
  are retained on allowed cancel (CR-013).

### Credit-hold / credit-limit

**EVENT_MATRIX:** `complete × sales_invoice`, `debit_note × sales_debit_note`
(G-23), `return × sales_invoice`. UI: `CreditHoldChip` /
`isCollectionHoldStatus`. Company flag
`auto_credit_hold_on_severe_overdue`.

- **CFT-117** — With auto credit-hold on, a customer in `stop_credit` /
  `overdue_severe` cannot Complete a new invoice even with **no** static
  credit limit; the hold is visible (chip/banner) on customer, collection
  card, and new-invoice. Complete error text includes "collection hold".
- **CFT-118** — A return (or payment) that clears residual / severe overdue AR
  **releases** the hold: a subsequent Complete for that customer succeeds,
  and the chip is gone. A return that leaves residual DN AR (G-23) must
  **keep** the hold.

### Batch / serial / lot-level restore

**EVENT_MATRIX:** `return × sales_invoice` / `return × pos_sale` (stock =
yes). Aggregate `balance_equals_movements` is CFT-036 — this case is
stricter.

- **CFT-119** — A return restores the **same batch and/or serial** that was sold, not
  merely the same SKU quantity. Selling serial SN-1 and returning "1 unit"
  must put SN-1 back to AVAILABLE (not consume SN-2). Batch-tracked sale
  must increment the sold lot's on-hand, not an arbitrary FEFO lot.
  `test_pj_batch_expiry.py` / serialized PJ are the starting evidence, not
  a substitute for this cross-flow assertion on the return path.

### Multi-tab / concurrent-edit of the same invoice (G-11a)

**EVENT_MATRIX:** `amend × sales_invoice`. Catalog action
`multi_tab_invoice_race` is gated by CFT-120 (`test_cft_cross_flow.py` +
postgres `test_concurrency_races`). Locally the threaded case is
`pytest -m postgres`.

- **CFT-120** — Two users (or two tabs) editing the same completed invoice: the second
  Complete/amend cannot silently clobber the first (lost update), cannot
  double-post stock/GL, and the loser gets a clean conflict/409 — not a
  second successful money write. Distinct from CFT-109 (oversell) and
  CFT-110 (over-allocation), which do not cover the same-document edit race.

---

## The core lifecycle test (per document type)

For every major document type (sales invoice, purchase invoice, POS sale,
sales/purchase return, credit/debit note, customer receipt/supplier
payment):

**Create → Draft → Amend → Complete → Partial/Full Payment or Allocation →
Return → Cancel → Report → Dashboard → Customer/Supplier Statement →
Inventory**

At each transition, assert:

- **CFT-121** — **What changed** — across stock, GL, AR/AP, GST, reports, dashboard,
  attention/badges, and the customer/public payment channel (BizBoard's
  actual Graph-2 projection list, not just "reports").
- **CFT-122** — **What must not change** — especially other lines on the same invoice,
  other periods, and the analytics-vs-ledger split (**CFT-NID-01**).
- **CFT-123** — **Is it reversible** — and does the *reversal* independently enforce
  the same period lock and idempotency guarantees as the forward action
  (this is where the real bugs have been — G-21/G-22 were both
  unwind-path gaps, not forward-path gaps).
- **CFT-124** — **Do all surfaces agree** — and where two surfaces are *supposed* to
  disagree (RETURNED in money reports vs. excluded from analytics;
  PDF snapshot vs live outstanding), is that the asserted behavior rather
  than an accident (CFT-NID-01, B2).
- **CFT-125** — **Can it happen twice** — via double-click, retry, or replayed
  webhook/import — without double-posting.
