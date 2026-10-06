# Sales / Purchase / POS — Implementation Plan

**Status:** Decisions locked 2026-09-21 · **Created:** 2026-09-21 · **Source:** [SALES_PURCHASE_UX_FIX_PLAN_2026-09-21.md](SALES_PURCHASE_UX_FIX_PLAN_2026-09-21.md)

This is the **how/when** companion to the fix plan, which is the **what/why**. The fix
plan records status and rationale per item (including live-reproduced bugs and
reference-app specs); this document sequences the work into buildable phases with
concrete files, data-model changes, API contracts, and test obligations. Item numbers
below match the original 67-item list and the fix plan — cross-reference either
document by number.

Nothing in this plan has been implemented yet. Each phase is independently shippable;
phases are ordered by leverage (unlocks other work cheaply) and risk (small confirmed
bugs before large structural builds), not strictly by the original ticket numbering.

**Start order (confirmed 2026-09-21):** Phase 0 first, in this sequence: **#59 → #67 → #16 → 0.4**. Then Phase 1.

**Explicitly out of scope for this plan:**
- **#4** (month-based invoice prefix) — discarded by founder decision, not being built.
- **#61** real e-invoice IRP submission to the government portal — in scope long-term but sized as its own separate project (IRP credential/API research, NIC sandbox, IRN/QR handling); only the explainer help text for #61 is in this plan.
- **#57** — resolved; no longer an open item, its findings are distributed across this plan.
- **Unified Customer/Supplier Party model** and GSTIN/phone-based ledger merge — follow-up idea only; v1 ledger is sales-side only.
- **Supplier ledger page** — does not exist today; not adding it in this plan.
- **Offline-safe POS multi-session** — Phase 11.1 is online-only v1.
- **Editable-total modes B/C** (scale line discounts / scale unit prices) — parked; v1 is header discount only.
- **Fix-plan Section 11 extras** (Price History as a standalone feature, MRP % OFF, barcode on invoice, favourite reports) — stay out unless explicitly requested to bundle into a specific phase. Price History *toggle* may still land cheaply inside Phase 7.1's settings surface once that exists.

**Testing convention:** this repo's layered strategy is in
[docs/TESTING_STRATEGY.md](../TESTING_STRATEGY.md) (L1–L10). Each phase below calls out
which tiers apply: **service/unit tests** (`backend/tests/test_*.py`), **workflow chain
tests** (`backend/tests/workflows/`), and **golden e2e** (`web/e2e-golden/*.spec.ts`,
Playwright against a real backend). New surface area should get at least one workflow
chain test; anything touching money/tax gets a unit test on the calculation itself.
Phase 2 live-click verification uses the running local stack, not code-reading alone.

---

## Locked decisions (2026-09-21)

| # | Topic | Decision |
|---|---|---|
| 1 | POS tax-rate (0.4) | Narrower (c): show `serverTenderTotal` as soon as known; extend the existing CR-111 gate to UPI + walk-in; mismatch → fresh tender, or a Reconcile step if cash may already have changed hands. Continuous debounced preview → Phase 11. |
| 2 | Sales History drafts (4.2) | "Drafts" quick-filter chip, not a draft-first sort. |
| 3 | Editable grand total (7.2) | Option A — extra header discount only; taxable value / GST untouched. Modes B/C parked. |
| 4 | Delivery Route (8.1) | SO-only v1; reuse `CanCreateSales`; removable while `PLANNED`; once `IN_TRANSIT` mark `FAILED`/`RETURNED` but do not silently remove; design (A) planning overlay. |
| 5 | POS multi-session (11.1) | Online-only v1 (M). Offline-safe is a future decision. |
| 6 | Recurring (12) | Per-template `stop_stage` (Invoice / SO / DC). Existing templates default to Invoice. Auto-created DC is `DRAFT` (stock posts only on complete). |
| 7 | Customer Ledger (6) | Sales-side only. No Customer/Supplier merge. No Supplier ledger in this plan. |
| 8 | Delivery address | Phase 5: per-document snapshot on Quote/SO. Phase 6 Profile: multiple saved shipping addresses. |
| 9 | Cheque (3) | Add `CHEQUE` to `payments.PaymentMode` only (ignore `masters.PaymentMode`). `cheque_status` PENDING_CLEARANCE → CLEARED / BOUNCED. Invoice can show Paid immediately; Day Book / cash-position count CLEARED only. Bounce = basic status flip + un-mark-paid, not a recon subsystem. |
| 10 | Payment-in discount (4.3) | Settlement / write-off (AR down, invoice GST untouched). Same convention as existing "Cash discount (after tax)". |
| 11 | Conversion chain (5) | Quote → SO → DC → Invoice. Skips Quote→Invoice and SO→Invoice already exist; no new backend for those. |
| 12 | Salesman / Channel (5) | Salesman = FK to `payroll.Employee`. Channel = sales channel (Walk-in / Online / Distributor), choice field or small master — not a notification channel. |
| 13 | Day Book | Build **once** (shared transaction-union query, company-wide). Link from Sales Reports and Accounting/Expense. Not two builds. |
| 14 | Invoice Share (0.3) | Extract/reuse `InvoiceDetailPage` + existing `shareInvoice`. History row menu is the same invoice-PDF share, not a payment-link-only variant. |
| 15 | Bulk PDF zip (4.7) | Sync zip for v1, response shaped as a download URL so an async job can replace it later without a frontend contract change. Typical bulk size still open (see Open items). |
| 16 | Custom fields (7.1) | Reuse `item_custom_field_defs` JSON pattern for invoice-header and party scopes. `mrp` / `batch_no` / `exp_date` stay first-class. "Industry Type" is a UI preset-picker only. |
| 17 | Start order | Phase 0: #59 → #67 → #16 → 0.4. Then Phase 1. |
| 18 | Branching | Fresh branch from a clean tree. **Still open:** whether current dirty files are safe to stash (see Open items). |
| 19 | Phase 2 verification | Live-click on the running local stack. |
| 20 | Section 11 extras | Out of this plan unless explicitly bundled. |

Inline markers: search "decided 2026-09-21" / "confirmed 2026-09-21" / "corrected 2026-09-21" / "scoped 2026-09-21".

---

## Phase map (quick reference)

| Phase | Theme | Items | Size | Depends on |
|---|---|---|---|---|
| 0 | Confirmed bugs, fix immediately | #59, #67, #16, POS tax-rate mismatch | S+S+S+M | none |
| 1 | Shared list-page component | #58 (infra) | M | none |
| 2 | Verification pass (live stack) | #1, #2, #6, #8, #15(sub-displays), #18/19, #28, #32, #44/45, #46a, #47, #53/55, #61(help only) | S×many | none |
| 3 | Payment modes & cheque | #9, #10, #66 | M | none |
| 4 | Sales History enhancements | #12, #13, #14a, #14b, #17, #20, #21, #22, #23 | M×several | Phase 1; Day Book shares query with Phase 6 |
| 5 | Quotation & Sales Order parity | #27, #29/39, #30/37, #31/38, #33/35, #34/36, #40, #41 | M×several | Phase 1 |
| 6 | Customer Ledger rebuild | #48, #49, #50, #51(done), #52 | L | Phase 1 |
| 7 | Invoice structural work | #3, #5, #7, #11, #24/25, #26 | L | none (but #3/#26 share design) |
| 8 | Delivery Route feature | #42 (route concept), #42(DC return), #43 | L | #34/36 (Phase 5) for delivery address |
| 9 | Purchase & Stock | #54, #56 | M | Phase 1 (for #56) |
| 10 | Accounting: Expense entity | #60, #62 | L | Day Book itself is Phase 4.8 (menu link only here) |
| 11 | POS structural | #63, #65, continuous preview polish | M+M | Phase 0.4 |
| 12 | Recurring invoice flow change | #46b | M | existing Quote→SO→DC convert actions (not a hard Phase 8 block) |

Items not listed above are already 🟢 no-action per the fix plan (#6, #8, #18/19, #43's
logic, #44/45, #46a's backend, #51, #57) and only need the verification tasks in Phase 2.

---

## Phase 0 — Confirmed bugs (fix immediately)

All four were live-reproduced against the running dev stack on 2026-09-21 with root
causes already isolated. Sequence: **#59 → #67 → #16 → 0.4**. The walk-in sub-case of
0.4 still needs a targeted live repro before that coverage gap is treated as confirmed
(see 0.4); everything else is ready to start.

### 0.1 — Discount report crash (#59)

- **Files:** `web/src/types/domain.ts` (`DiscountReportResponse`, lines 1017-1030), `web/src/pages/reports/DiscountReportPage.tsx` (lines 48-52 and column `key`s).
- **Change:** rename every field from snake_case to camelCase to match what `EnvelopeJSONRenderer` actually serializes: `by_party`→`byParty`, `by_product`→`byProduct`, `by_period`→`byPeriod`, `totals.invoice_count`→`totals.invoiceCount`, `.discounted_invoice_count`→`.discountedInvoiceCount`, `.line_discount_total`→`.lineDiscountTotal`, `.header_discount_total`→`.headerDiscountTotal`, `.total_discount`→`.totalDiscount`, `.avg_discount_percent`→`.avgDiscountPercent`, and each row's `line_discount`→`lineDiscount`.
- **Regression check:** grep other report pages/types for the same snake_case pattern against a camelized API — this bug pattern suggests this page was never run against a live response before merging; worth a 10-minute sweep of sibling report pages while in there.
- **Test:** add a component/integration test that renders `DiscountReportPage` against a realistic camelCase fixture (the live response captured 2026-09-21 is a ready-made fixture) — this is exactly the class of bug a snapshot/shape test would have caught.
- **Effort:** S. **No design decisions needed — start here.**

### 0.2 — POS thermal receipt too long (#67)

- **File:** `backend/sales/pdf/thermal_receipt.py:112`.
- **Change:** replace the hardcoded `pagesize=(page_width, 800 * mm)` with a height computed from actual content. Reportlab options: (a) build the `story` list first, measure its wrapped height via `Flowable.wrap()` summation before constructing the `SimpleDocTemplate`, or (b) switch to `canvas.Canvas` with manual `y`-cursor tracking sized to content plus a fixed margin, growing the page as items are drawn. Prefer (a) — smaller diff, keeps the existing `SimpleDocTemplate`/`story` structure.
- **Test:** unit test asserting the rendered PDF's `/MediaBox` height scales with item count — e.g. a 1-item receipt and a 10-item receipt should produce different heights, and a 1-item receipt should not be 800mm. Use the same `/MediaBox` regex approach used to diagnose this live.
- **Effort:** S.

### 0.3 — Share invoice wiring (#16)

- **Backend:** nothing to change — `SalesInvoiceViewSet.share` ([views.py:588-647](../../backend/sales/views.py)) is complete: `POST /api/v1/sales/invoices/{id}/share/` with `{channel: 'EMAIL'|'WHATSAPP', recipient?}`, returns `{..., mode, whatsapp_send_status, pdf_url}`.
- **Corrected 2026-09-21:** this is smaller than originally scoped. `shareInvoice` **already exists** as a client function ([web/src/api/legacy/sales.ts:585](../../web/src/api/legacy/sales.ts)) and is **already fully wired** in `InvoiceDetailPage.tsx` — dialog state, channel toggle, recipient fields, mutation, both `shareInvoice` (PDF/WhatsApp/email) and `sharePaymentLink`. The gap is the list view: `SalesHistoryPage.tsx`'s row menu never surfaces it.
- **Frontend, extract-and-reuse (not build-new):**
  1. Pull the existing share dialog + `shareInvoice` mutation logic out of `InvoiceDetailPage.tsx` into a small shared component/hook (e.g. `useShareInvoiceDialog`) so both the detail page and the history row menu use the same implementation instead of forking it.
  2. `web/src/pages/sales/SalesHistoryPage.tsx` (row menu, near line 379-475) — add a "Share" `MenuItem` opening that shared dialog. History's "Share" is the same **invoice-PDF share** as the detail page — not a second, payment-link-only variant.
  3. On success, toast using the response's `mode` (cloud/link/fallback) and `whatsapp_send_status`.
  4. Guard: the backend already 400s for non-COMPLETED/RETURNED invoices — disable the row action on Draft rows rather than let it fail.
- **Test:** one golden e2e case — complete an invoice, open the row menu, share via email, assert the API call and toast. Backend and the underlying share function already have coverage (verify, don't re-test).
- **Effort:** S (UI reuse, not new integration).

### 0.4 — POS tax-rate mismatch (new finding, not in original 67) — **P0, highest priority in this plan**

- **What's wrong:** POS's on-screen cart total is computed client-side from `line.product.gstRate` ([PosPage.tsx:167,437,446,460](../../web/src/pages/pos/PosPage.tsx)), never consulting the authoritative HSN rate table (`masters.hsn_catalog.rate_for()`). When a product's stored rate and its HSN's effective-dated rate diverge, the cashier sees one total; the system can book a different one. Confirmed live: cart showed ₹314 (12%), booked invoice was ₹330 (18%).
- **Correction, 2026-09-21 (found on re-review, not in the original diagnosis):** a partial server-side gate already exists — `CR-111`, [PosPage.tsx:1228-1263](../../web/src/pages/pos/PosPage.tsx) calls `previewSalesTotals` and gates the tender amount **when `mode === 'CASH' && navigator.onLine && effectiveCustomerId` is already resolved**. This is very likely what was actually observed during live repro (the "Finish payment ₹330.00" / stuck "payment already in progress" state). It doesn't fully close the hole:
  1. `effectiveCustomerId` is resolved *later* in the same function for a genuine walk-in/no-customer-selected sale ([PosPage.tsx:1203-1222](../../web/src/pages/pos/PosPage.tsx)) — the gate may run late or be skippable on that path. **Needs a targeted live repro before treating as confirmed vs. already-safe.**
  2. **UPI has no equivalent gate at all** — `mode === 'UPI'` only checks `navigator.onLine` ([PosPage.tsx:1269](../../web/src/pages/pos/PosPage.tsx)).
  3. Even where the gate fires, **the on-screen cart display is never corrected** before the cashier commits to a tender amount — the number the cashier is looking at stays wrong even if the backend already knows the right one.
- **Decision (made 2026-09-21):** narrower Phase 0 (c), not a full rebuild:
  1. Make the cart display render `serverTenderTotal` the moment CR-111's existing call resolves, instead of leaving the stale client-computed figure on screen. Plumbing already exists; this is a render fix.
  2. Extend the same CR-111 gate to UPI, and to the walk-in/no-customer-id-yet path (repro first to confirm the gap is real, then fix).
  3. On a mismatch, re-show the corrected total and **require a fresh tender/confirm** — no auto-adjusting change. If cash may already have physically changed hands before the mismatch surfaces, don't let the system silently pick a number: surface a **Reconcile** step showing both figures and let the cashier decide (short-collect vs. re-collect).
  4. Full continuous debounced-preview-on-every-cart-edit (always-live pricing, not just at tender time) is deferred to **Phase 11.3** — that's the bigger lift and belongs with the multi-session cart rework, which touches the same state.
- **Test:** a workflow chain test (`backend/tests/workflows/`) seeding an `HsnRate` row effective on the sale date that differs from the product's `gst_rate`, covering: (a) known-customer online CASH (gate already exists — assert it still works after the display fix), (b) walk-in CASH (assert the gate fires here too, once confirmed as a real gap), (c) UPI (assert a new gate now exists). Frontend: cart display updates to `serverTenderTotal`; Reconcile UI requires an explicit choice on mismatch.
- **Effort:** M — narrower than originally scoped since CR-111 provides a base to extend rather than build from zero.

---

## Phase 1 — Shared list-page component (#58)

**Why first after Phase 0:** `SalesHistoryPage`/`PurchaseHistoryPage`/`CustomersPage` already share `HistoryFilterBar` (search + status filter). `QuotationsPage`/`SalesOrdersPage` use the bare `DocumentListPage` with none of that. Standardizing unlocks #12, #14a, #21, #22, #31, #38, #47, #56 cheaply — build this before touching those items individually.

- **File:** `web/src/components/HistoryFilterBar.tsx` — extend, don't fork:
  1. Add an optional `dateRangePresets` prop (Today/This Week/Last 15 Days/This Month/Last 365 Days/Custom) feeding #14b — currently only raw from/to date pickers ([HistoryFilterBar.tsx:75-95](../../web/src/components/HistoryFilterBar.tsx)).
  2. Add an optional `bulkSelect` prop: renders row checkboxes + a selection toolbar (count, bulk actions slot) — feeds #22.
  3. Add an optional `statusOptions` prop generalized beyond the current fixed set, so Quotations can pass `['All', 'Open', 'Closed']` (#31) and Sales Orders the same (#38) without a new component.
- **File:** `web/src/components/DocumentListPage.tsx` — retire in favor of `HistoryFilterBar` once the above lands, or leave as a thin wrapper if other callers still need the bare version. Check all current usages before removing.
- **Migration path:** swap `QuotationsPage.tsx` and `SalesOrdersPage.tsx` onto the extended `HistoryFilterBar` as part of Phase 5 (they need the new features anyway); `InventoryReportPage`/`CurrentStockPage` swap onto it in Phase 9 for #56.
- **Test:** component tests for the new `HistoryFilterBar` props (preset selection emits correct date range, bulk-select emits correct id list); no new backend work in this phase — it's a pure frontend component.
- **Effort:** M.

---

## Phase 2 — Verification pass (live stack, not code-reading)

These are either already-working items that need a live check (not just code-reading —
Phase 0's bugs are proof static reading isn't sufficient) or trivial help-text additions.
**Confirmed 2026-09-21:** run this pass against the running local `docker`-composed
stack, same as Phase 0. Batch into one PR-sized pass.

| # | Task |
|---|---|
| #1 | Confirm Cancel/Sales Return actions are visibly reachable from the invoice row menu; relabel if unclear. |
| #2 | Manually create an invoice with a backdated `invoice_date`, confirm the resulting number is correct and sequential with existing invoices for that FY. |
| #6 | Live-click through NON_GST/GST/Retail/Tax invoice type switches, confirm GST fields show/hide correctly (static-verified only so far; the fix plan flagged this as a real gap). |
| #8 | Run `backend/tests/test_tax_calc_properties.py` and the 14 files referencing CGST/SGST/IGST in a real test environment (the sandbox container had no pytest installed — needs a proper dev/CI environment, not a shortcut). |
| #15 sub-displays | Fix the line-item TAX cell, line AMOUNT, and Balance Amount box in `NewInvoicePage.tsx` to read from the resolved `usePreviewTotals` response instead of local/stale state — same root class as the POS bug in Phase 0.4, smaller blast radius since the document total is already correct. |
| #18/19 | Already live-confirmed correct — no action. |
| #28 | Confirm `Quotation.valid_until` is rendered as an input on `NewQuotationPage` and printed on the PDF; wire it in if either is missing. |
| #32 | Change `useCustomerSearch`/`useProductSearch` ([usePartySearch.ts:14,33](../../web/src/hooks/usePartySearch.ts)) to fetch a default "recent/top" list when the query is empty, instead of gating entirely on `minChars`. |
| #44/45 | Confirm the `?` help icon is visible and reachable on Credit Note / Debit Note pages. |
| #46a | Confirm the recurring-invoice frontend form allows multiple line items (backend already does); fix the form if it artificially caps at one. |
| #47 | Add a sort dropdown (name / balance / recently active) to `CustomersPage`. |
| #53/55 | Add contextHelp entries for RCM, ITC eligibility, BOE, cost center on the Purchase Invoice/Order pages, reusing the Credit/Debit Note help pattern. |
| #61 | Add contextHelp explaining e-invoicing, explicit that current implementation is payload-prep only (real IRP submission is a separate future project, see the scope note at the top of this doc). |

**Test:** for the ones with genuine behavior changes (#15, #32, #47), add or extend a
component test; the rest are confirm-only and don't need new test coverage beyond
existing suites passing.

**Effort:** S × 13 items, batchable into 1-2 PRs.

---

## Phase 3 — Payment modes & cheque support (#9, #10, #66)

One shared backend change serving invoices, purchase payments, and POS at once.

- **Migration:** `backend/payments/models.py:9-14` — add `CHEQUE` to `PaymentMode` choices. **Confirmed 2026-09-21:** there is a separate, unrelated `masters.PaymentMode` model (`CompanyScopedModel`, a named-list master) in a different app — unused by actual receipts. Ignore it; extend `payments.PaymentMode` (the `TextChoices` enum) only.
- **Model fields, new** (on `CustomerReceipt`/`SupplierPayment` per `payments/models.py`): `cheque_number`, `cheque_bank_name`, `cheque_date`, and an attachment FK to `core.FileAsset` for the cheque image/copy (reuse the existing FileAsset pattern already used for invoice PDFs and signatures).
- **Cheque clearing status (decided 2026-09-21):** add `cheque_status` (`PENDING_CLEARANCE` default → `CLEARED` / `BOUNCED`), matching standard Indian SME practice of not treating a cheque as settled cash until it clears.
  - The invoice can still show **Paid** immediately (a payment instrument was legally tendered).
  - Day Book / cash-position figures count the receipt **only when `CLEARED`**.
  - A `BOUNCED` cheque is a basic status flip + un-mark-paid / reverse the allocation for v1 — not a full bank-reconciliation subsystem.
- **Backend service:** `backend/payments/services.py:259-334` — extend the mode-based required-field validation (currently requires `reference` for UPI/BANK) to require `cheque_number` + `cheque_bank_name` when mode is `CHEQUE`.
- **Frontend, invoices:** `NewInvoicePage.tsx` payment section — add cheque fields (number/bank/date) + file upload, shown conditionally when `CHEQUE` is selected, mirroring how UPI/BANK reference fields already appear conditionally.
- **Frontend, POS:** `PosPage.tsx:1955-1979` — the domain type already supports `BANK`/`CARD`/`CREDIT`, just not wired into the checkout UI. Wire all of them in, plus the new `CHEQUE` option with its fields.
- **Frontend, purchases:** same fields on `NewPurchasePage.tsx`'s payment section (supplier payments go out via cheque at least as often as they come in via one).
- **Test:** service-level unit test for the new validation rule; workflow chain test completing an invoice with a cheque payment end-to-end (including the attachment upload); status-transition tests for `PENDING_CLEARANCE` → `CLEARED` (Day Book includes it) and → `BOUNCED` (invoice un-marked paid, allocation reversed).
- **Effort:** M.

---

## Phase 4 — Sales History enhancements

Depends on Phase 1's extended `HistoryFilterBar`.

### 4.1 — Payment-status filter (#14a) + date presets (#14b)

- Add a payment-status filter (Paid/Partial/Unpaid) alongside the existing document-status chips in `SalesHistoryPage.tsx` — the underlying `paidAwareStatus` per-row value already exists ([SalesHistoryPage.tsx:307-308](../../web/src/pages/sales/SalesHistoryPage.tsx)), just needs to become filterable server-side too (add a query param, filter in `SalesInvoiceViewSet.get_queryset`).
- Wire in Phase 1's `dateRangePresets` prop.
- Add a stats strip above the list cross-tabbing payment status × the selected date range (counts + amounts) — new small aggregation endpoint, or compute client-side from the already-paginated response if approximate counts are acceptable (flag this tradeoff rather than assume — exact counts across all pages need a backend aggregate).

### 4.2 — Drafts quick-filter (#12)

- **Decided 2026-09-21:** a "Drafts" quick-filter chip, not a strict draft-first sort — keeps the list chronological within each view rather than reordering the whole history around status.

### 4.3 — Payment confirmation modal (#13)

- Backend: `complete` action payload — add `discount` (numeric) and `payment_date` (date, distinct from `invoice_date`) fields; currently only amount/mode/reference/notes/bank_account.
- **Discount semantics (decided 2026-09-21):** this is a **settlement/write-off** — it reduces AR, it does not amend the invoice's already-computed GST/taxable value. Matches the existing "Cash discount (after tax)" field already present on `NewInvoicePage.tsx` — reuse that convention rather than inventing a second rule.
- Frontend: build the "Record Payment" modal per the reference-app spec — Amount Received, Payment-In Discount (with info tooltip distinguishing it from line-item discount), Payment Date, Payment Mode, Notes, plus a live calculation panel (Invoice Pending Amt → Amount Received/Discount → Balance Amount).

### 4.4 — Inline profit on invoice/list (#17)

- Reuse the calculation already powering `InvoiceProfitReportPage`/`InvoiceProfitRollupPage`; surface it on the invoice detail view (and optionally the list row) behind the existing financial-reports permission gate (`CanViewFinancialReports`, already used server-side for margin data in the preview endpoint — reuse the same gate, don't invent a new one).

### 4.5 — HSN-wise tax breakout on invoice (#20)

- Reuse the GSTR-1 aggregation logic in `backend/reporting/gst_returns_sections.py:9-21`, scoped to a single invoice instead of a filing period. Add to the invoice PDF template and as a standalone report page.

### 4.6 — Search by name/mobile (#21)

- `backend/sales/views.py:201-202` — extend the `q` filter from `number__icontains` only to also join `customer__name__icontains` / `customer__phone__icontains`.

### 4.7 — Bulk download (#22)

- Frontend: bulk-select via Phase 1's `HistoryFilterBar` prop.
- Backend: new endpoint accepting a list of invoice ids. **Pragmatic default (pending scale confirmation):** build a synchronous zip for now (fine to roughly 50–100 invoices), but shape the response as a **download URL** rather than streamed bytes, so swapping to an async job + link later doesn't change the frontend contract. If typical real-world bulk actions are in the hundreds (e.g. "select all unpaid"), this needs to be an async job from the start instead — see Open items.
- Cap the sync path (reject or warn above the cap) so a 500-id select cannot hang the request.

### 4.8 — Sales Summary dashboard + Day Book (#23)

- `SalesReportPage.tsx` today is a CSV register, not a dashboard — build a real summary view (revenue over time, top customers/products, payment-status breakdown).
- **Day Book — build once, not twice (corrected 2026-09-21):** originally listed under both Phase 4.8 and Phase 10; that was a sequencing error. One report, two menu entries (Sales Reports + Accounting/Expense in Phase 10).
- **Shared transaction-union query:** Day Book (company-wide, one day) and Phase 6's Ledger Transactions tab (per-party, date range) consume the same union. Implement the query **once** as a reporting service; whichever consumer lands first owns it, the other reuses it. Do not duplicate. Cheque receipts in this query follow Phase 3: cash-position / Day Book rows count `CLEARED` only. Confirmed as its own distinct report by the reference app, not a Cash Book relabel.

**Test:** workflow chain tests for the `complete` payload changes (4.3) and the search extension (4.6); component tests for the new filter/modal UI.

**Effort:** M × 6 sub-items, L for the dashboard build in 4.8.

---

## Phase 5 — Quotation & Sales Order parity

Both documents share nearly identical gaps — implement once, apply to both models/pages.

- **#27** — inline customer creation from the Quotation form: reuse the pattern already built for `CustomersPage`'s inline-create.
- **#29/#39** — guided bulk conversion, **direction corrected 2026-09-21: Quote → SO → DC → Invoice**, not SO→Quote as originally mis-stated. Confirmed in the model: `Quotation` carries forward-FKs (`converted_order`, `converted_invoice`), so Quote is upstream of SO. The point-to-point `convert` / `convert_to_order` / `convert_to_challan` actions already exist ([views.py:690-701](../../backend/sales/views.py), [phase1_views.py:269-354](../../backend/sales/phase1_views.py)) in this direction, plus separate skip-path actions (Quote→Invoice, SO→Invoice) that already work today — no new backend work needed for those skips. Build one frontend orchestration action that walks Quote→SO→DC→Invoice in sequence with a single confirm; the skip shortcuts stay as they are.
- **#30/#37** — Quotation edit route (mirror `/sales/orders/:id`, currently Quotation has none); Sales Order gets a guarded cancel/void action (currently only `cancel` exists with no delete — keep it that way, add clearer affordance).
- **#31/#38** — swap both pages onto Phase 1's extended `HistoryFilterBar` with `statusOptions: ['All', 'Open', 'Closed']`.
- **#33/#35 — Salesman / Channel (decided 2026-09-21):** Salesman as an FK to `payroll.Employee` (already exists, [payroll/models.py:10](../../backend/payroll/models.py)) rather than `User` (a salesman may not need app login) or a new master. Channel as a sales channel (Walk-in / Online / Distributor), a simple choice field or small master mirroring `ExpenseCategory` — explicitly **not** a notification channel. Add both fields to `Quotation` and `SalesOrder` models (migration), plus form fields.
- **#34/#36 — Delivery address, scoped 2026-09-21:** `Customer.shipping_address` already exists as a single text field. This phase builds a **per-document snapshot** field on Quotation/SO only — copied from the customer's address at document-creation time, editable for that one order. "Multiple saved shipping addresses to pick from" (the reference app's "Manage Shipping Addresses" link) belongs in **Phase 6** (Ledger/Profile tab), not duplicated here. This snapshot field is still a dependency for Phase 8's Delivery Route feature; sequence this before or alongside Phase 8.
- **#40** — add `expected_price` alongside `unit_price` on SO/Quotation/DC line items (migration).
- **#41** — **do not build a separate calculation.** The expected-profit service being built for Phase 8 (Delivery Route rollups) is the same number this item needs — build it once in Phase 8, surface it on SO/Quotation/DC detail views here.

**Test:** model/migration tests for the new fields; workflow chain test for the guided bulk-conversion action; one e2e case for inline customer creation.

**Effort:** M × 7 sub-items.

---

## Phase 6 — Customer Ledger rebuild (#48, #49, #50, #52)

Largest coherent single workstream after Phase 7/8. Treat as one PR series, not four
separate patches — the reference-app screenshots gave an exact target (#51, already
resolved).

**Scope, decided 2026-09-21: sales-side only.** `Customer` and `Supplier` are separate
models — a party is never both. V1 covers this customer's invoices, receipts, returns,
notes, and quotations only. Explicitly **not** doing GSTIN/phone-based matching to merge
Customer and Supplier records, and **not** building a unified Party model. A business
that is both customer and supplier sees two separate ledger pages, correctly reflecting
the data model. Follow-up idea only (not in this plan): there is no symmetric Supplier
ledger page today.

**Target: `CustomerLedgerPage.tsx` rebuilt as 4 tabs**, per-party:

1. **Transactions** — combined list (not per-doc-type screens): Date / Transaction Type / Number / Amount / Status. Filters: date-range preset (reuse Phase 1), Transaction Type dropdown (**sales-side only:** Sales / Payment In / Quotation / Sales Return / Credit Note / Debit Note — drop Purchase / Payment Out / Purchase Return from the reference screenshot for v1), Status dropdown (All / Paid / Unpaid / Partial / Overdue / Cancelled). Rows link through to the source document.
   - **Backend:** aggregation endpoint unioning `SalesInvoice`, `CustomerReceipt`, `Quotation`, `SalesReturn`, `SalesCreditNote`, `SalesDebitNote` for one customer — a `UNION` query or Python-side merge of per-model querysets sorted by date. **Do not** include `PurchaseInvoice` / `SupplierPayment` / `PurchaseReturn`. Reuse the shared transaction-union service from Phase 4.8 if it already exists (scoped to one customer here; company-wide there). Profile before shipping; a naive per-model fan-out could be slow.
2. **Profile** — General Details (name/type/mobile/category/email/opening balance), Business Details (GSTIN/PAN/billing address), Credit Details (period/limit), Party Bank Details, Custom Fields — all editable inline via the existing Customer update endpoint. **"Manage Shipping Addresses" lives here** (new child model — multiple saved addresses per customer to pick from), distinct from Phase 5's simpler per-document snapshot field on Quotation/SO.
3. **Ledger (Statement)** — 4 KPI tiles (Total Receivable, Overdue Amount, Total Sales Amount, Total Received Amount), date-range filter, Download Excel / Print PDF / Share actions, Date/Voucher/Sr No/Payment Mode table. This tab **is** the resolved #51 spec.
4. **Item Wise Report** — per-party, per-item **Sales Qty / Sales Amount** for v1 (same date filter). Purchase Qty/Amount from the reference screenshot is out of scope while the ledger is sales-side only.

**Test:** backend aggregation query gets a dedicated unit test (multiple sales-side doc types, verify union correctness and ordering, and that purchase-side docs for a same-named supplier do **not** appear); one golden e2e walking all 4 tabs for a seeded customer with mixed sales-side transaction types.

**Effort:** L.

---

## Phase 7 — Invoice structural work

The two highest-risk/highest-effort items in the whole plan. 7.2's back-calculation
**rule is now locked** (Option A below); 7.1 still lands as a PR series, not one
changeset.

### 7.1 — Invoice settings centralization + custom fields (#3, #26)

- **Data model, reuse the existing pattern (confirmed 2026-09-21):** `Company.item_custom_field_defs` ([accounts/models.py](../../backend/accounts/models.py), a JSONField list) and `Product.custom_fields` ([masters/models.py:251](../../backend/masters/models.py), a JSONField dict) already establish the working pattern for item-scoped custom fields. Build the two missing scopes the same way — a company-level `invoice_custom_field_defs` list + per-invoice JSON values, and a company-level `party_custom_field_defs` list + per-customer JSON values — rather than a new relational model per scope. Three scopes total: invoice-header, party, item.
- **Explicit boundary (decided 2026-09-21):** line items already have `mrp`, `batch_no`, `exp_date`, `mfg_date` as first-class typed model columns — these stay first-class, they do **not** become custom fields. Custom fields are for genuinely business-specific data the schema doesn't already model.
- **UI:** one "Quick Settings" modal off the invoice page, three tabs:
  - **Invoice Details** — prefix/sequence toggle + live number preview (fixes the existing BUG-514 read-only-preview issue while in there), custom-field visibility keyed to an "Industry Type" dropdown suggesting relevant fields (PO Number, E-way Bill Number, Vehicle Number). **Scoped 2026-09-21:** this dropdown is a lightweight preset-picker for which fields to suggest — not a persisted company classification with downstream business logic. At most, remember the last-picked value as a UI convenience default; nothing else in the system reads it.
  - **Party Details** — party-level custom fields.
  - **Item Table Details** — column show/hide, item-level custom fields (Brand as an example of a genuinely custom field a business might add — **not** a reimplementation of first-class `batch_no` / `exp_date`), "show purchase price while adding items" toggle, optional "Price History" toggle (last 5 sales/purchase prices per item×party — nice-to-have in the fix plan's Section 11; cheap to bundle here once the settings surface exists, still not a standalone feature).
- **Render:** custom field values on the invoice form, and on the PDF template.
- **Sequencing note:** build the settings modal shell first (empty tabs wired to real endpoints), then land each field scope (invoice/party/item) as a separate PR — this is too large to land as one changeset.

### 7.2 — Editable grand total, auto back-calculate (#7)

- **Rule decided 2026-09-21: Option A — extra header discount only.** Editing the grand total down (e.g. ₹1,180 → ₹1,000) posts the ₹180 difference as additional header-level discount; taxable value and GST per line stay untouched. GST-safest of the options considered (never retroactively changes a line's tax base) and needs no rounding-distribution rule. No worked example from the reference app was available for a scaling approach — **not building B/C speculatively.** B (scale line discounts) and C (scale unit prices, GST moves with them) are parked as future "smart" modes, only if specifically requested later with their own rounding spec.
- `NewInvoicePage.tsx`'s total field becomes editable; on edit, compute `delta = currentTotal - newTotal` (edit-down) and apply it as additional `invoiceDiscount` (the header discount field that already exists), reusing the existing after-tax discount convention already established for #13's payment-in discount (same principle: settlement-style adjustment, not a tax-base change). Editing the total *up* is out of v1 unless a later spec defines it (would imply a negative discount or a surcharge).
- **Test:** unit tests covering the delta-to-header-discount calculation across rounding boundaries (paise-level) and auto-round-off interaction (the existing `autoRoundOff` field already on the model) — table-driven, extending `test_tax_calc_properties.py`.

### 7.3 — Line-item description, resizable (#24, #25)

- `NewInvoicePage.tsx:460-461,749` — `description` is carried in data mapping but has no rendered input. Add a resizable textarea per line item (mirror the header notes/terms field, already `minRows`/`maxRows`). Render on PDF.

### 7.4 — Invoice type descriptions (#5) + signature empty-box option (#11)

- Small, bundle into whichever PR touches `NewInvoicePage.tsx` in this phase: one-line description text under each invoice-type dropdown option; add "Show Empty Signature Box on Invoice" as a second option next to the existing upload.

**Effort:** L overall (7.1 is the single largest item in this plan after the Ledger rebuild); 7.2's rule is locked — no remaining spec gate; 7.3/7.4 are S and can land independently/earlier if useful as quick wins.

---

## Phase 8 — Delivery Route feature (#42) + Delivery Challan return (#42b) + return test coverage (#43)

Full design already written in the fix plan's Section 13 — summarized here for
sequencing; **read that section before starting**, it has the complete schema and API
surface. Founder decisions that were open there are locked below.

### 8.1 — Delivery Route (supersedes the original #42 "vehicle/driver on challan" framing)

- **Depends on** Phase 5's per-document delivery-address snapshot (#34/#36) — a route's per-stop "delivery details" are meaningless without a real delivery address distinct from billing.
- **New models:** `DeliveryRoute` (vehicle, driver, date, status, estimated/actual logistics cost) + `DeliveryRouteStop` (join to `SalesOrder`, sequence, per-stop delivery status).
- **New service:** expected-profit-per-SO calculation — **shared with #41** (Phase 5), build once here since Phase 8 needs it regardless and #41 needs the identical number. UI must label it **Expected/Estimated Profit**, not "Profit" — it uses current purchase price, not FIFO layers at invoice-complete time, and will disagree with `InvoiceProfitSnapshot` later.
- **New API:** create route, add orders, update stop status, complete route, get route detail with rollup.
- **New UI:** Delivery Routes list + detail page, multi-select entry point from `SalesOrdersPage` (reuses Phase 1's bulk-select), route manifest PDF for the driver.
- **Phasing within this phase** (from the fix plan Section 13): models+migration+profit-service+CRUD API → list/detail UI → per-stop status + manifest PDF → (later) tie actual logistics cost to the Phase 10 Expense entity once it exists.
- **Decisions locked 2026-09-21:**
  - Scope: **SO-only for v1**, not POS/ad-hoc deliveries.
  - Permission: reuse `CanCreateSales` — matches every other sales-document action already, no new role.
  - Removable after adding: **yes, while the route is `PLANNED`**. Once `IN_TRANSIT`, a stop can be marked `FAILED`/`RETURNED` but not silently removed, so the trip record stays honest about what was actually planned and attempted.
  - Design confirmed as **(A)** — a planning overlay on existing SOs/challans, not one consolidated van-wide challan.

### 8.2 — Delivery Challan return (#42b)

- `DeliveryChallanViewSet` currently only has `complete`/`convert`/`cancel` ([phase1_views.py:332-354](../../backend/sales/phase1_views.py)). Add a `return` action modeled directly on the existing `SalesReturnViewSet`/`return_service.py` pattern — same partial-quantity logic, scoped to a challan instead of an invoice.
- Independent of 8.1 — can land in parallel or before the Route work if sequencing pressure demands it.

### 8.3 — Partial sales return test coverage (#43)

- Logic already correct in `return_service.py:63-149` — this is pure test-writing, no product code changes. Add explicit coverage for partial and multiple-partial returns against one invoice. Cheap, do it early, doesn't need to wait for the rest of this phase.

**Test:** workflow chain test for the full Route lifecycle (create → add orders → update stop status → complete, with rollup figures asserted at each stage; also: remove-stop while `PLANNED` succeeds, remove-stop while `IN_TRANSIT` is rejected, `FAILED`/`RETURNED` while `IN_TRANSIT` succeeds); workflow chain test for challan return mirroring the existing sales-return tests; the #43 unit tests as described.

**Effort:** L for 8.1, M for 8.2, S for 8.3.

---

## Phase 9 — Purchase & Stock

- **#54** — Ship From field + address on Purchase Invoice: migration on `PurchaseInvoice`, form field, PDF template.
- **#56** — Stock Report search/download/share/print: unify `InventoryReportPage`/`CurrentStockPage` onto Phase 1's `HistoryFilterBar` (search), add KPI tiles (Total Stock Value/Quantity) and Email Excel/Download Excel/Print PDF actions per the reference-app pattern.

**Effort:** M × 2.

---

## Phase 10 — Accounting: Expense entity (#60, #62)

- **New model:** `Expense` transaction entity (currently only `ExpenseCategory` master exists, [masters/models.py:66](../../backend/masters/models.py)) — date, number, party (optional), category FK, amount, notes, attachment.
- **New API:** CRUD + list with category filter.
- **New UI:** Expenses list page (Date/Expense Number/Party/Category/Amount + row actions), "Create Expense" button, category filter dropdown with inline "+ Add/Manage Category", a Reports menu entry **linking to the single Day Book report built in Phase 4.8** (not a second build — see the correction there).
- **Future tie-in:** once this exists, Phase 8's `DeliveryRoute.actual_logistics_cost` can optionally pull from a tagged Expense record instead of manual entry (Phase 8's later slice, deferred).

**Effort:** L.

---

## Phase 11 — POS structural work (#63, #65) + live preview polish

Sequence after Phase 0.4's tax-rate safety fix lands — this phase touches the same
cart-state code, so do the safety-critical fix first and standalone.

### 11.1 — Multiple billing screens (#63)

- **Current state:** `PosPage.tsx` holds `cart`, `customerId`, `warehouseId`, `cashTendered`, `idempotencyKey`, `upiPending`, `cashPending` as flat single-instance `useState` hooks ([PosPage.tsx:189-275](../../web/src/pages/pos/PosPage.tsx)), `cart` persisted to one localStorage key. The explicit "No hold-and-recall" banner in the current UI suggests this was a deliberate v1 scope cut, likely because of the offline-outbox sync layer (`hasOutboxItems`, `isFlushing`) already in this component — multi-session state interacting with offline sync is genuinely tricky.
- **Design:** introduce a `PosSession` shape bundling everything currently top-level; replace the single `cart` state + localStorage key with `sessions: PosSession[]` + `activeSessionId`. Tabs UI matching the reference pattern (Billing Screen 1/2, "+ Hold Bill & Create Another"), `Ctrl+1..9` to switch, `Ctrl+B` for a new session — following the existing keybinding pattern already in this file (F2 for scan barcode).
- **Decided 2026-09-21: online-only v1** — don't attempt to solve cross-session offline-outbox interleaving in this pass. A session with a payment in-flight blocks only its own tab. Sized as **M**, not L; offline-safe multi-session stays a future decision if ever needed, not built speculatively now.

### 11.2 — POS line-item fields (#65)

- Add MRP, item code, HSN, per-line discount (already exists per fix plan), additional-charges, and bill-level discount fields to the POS cart line model and checkout UI, matching the reference column set (NO/ITEMS/ITEM CODE/MRP/SP/DISC%/QUANTITY/AMOUNT) and the "Add Discount [F2]"/"Add Additional Charge [F3]" bill-level actions. Extend the thermal receipt template to print the new fields.

### 11.3 — Continuous debounced preview (deferred from 0.4)

- Always-live pricing: call `previewSalesTotals` on cart edits (debounced, same hook `NewInvoicePage` already uses) so the cart display tracks the HSN table continuously, not only at tender time. Phase 0.4 closes the money-safety hole at checkout; this is the UX polish that removes the remaining race between last preview and tender.

**Test:** the multi-session work needs its own workflow chain test suite (session isolation — completing/discarding tab 1 must not affect tab 2's cart or in-flight payment); component tests for the new POS line-item fields.

**Effort:** M for 11.1 (online-only), M for 11.2, M for 11.3.

---

## Phase 12 — Recurring invoice flow change (#46b)

- **Decided 2026-09-21, refined from the original plan:** not an all-or-nothing switch — a **per-template configurable stop stage** (Invoice / SO / DC). Auto-creating a Delivery Challan would otherwise imply a delivery document exists when nobody is delivering; forcing that on every template is the wrong default.
- Existing templates default to **Invoice** (today's behavior, non-breaking). New templates can opt into stopping at SO or DC.
- **Confirmed, not a new design decision:** an auto-created DC from a recurring trigger lands as `DRAFT` by construction — `DeliveryChallan` only posts stock **on complete** ("Dispatch record — stock posts on complete when company.stock_on_delivery_challan," per the model's own docstring). A human still has to complete the DC before anything moves.
- **Depends on** the existing SO→Challan conversion actions (already work today) — not a hard Phase 8 block. Reuse them; don't build new conversion logic.
- **Change:** add a `stop_stage` field to the recurring-invoice template (`INVOICE` / `SALES_ORDER` / `DELIVERY_CHALLAN`, default `INVOICE`); `recurring.py`'s trigger function branches on it — for `SALES_ORDER`/`DELIVERY_CHALLAN` templates, create the `SalesOrder` first, optionally convert to a `DRAFT` `DeliveryChallan`, stopping there instead of creating the invoice.
- **Test:** workflow chain tests covering all three stop stages, asserting correct linkage between the documents created and that a `DELIVERY_CHALLAN`-stage template produces a `DRAFT` challan with no stock movement.

**Effort:** M.

---

## Cross-phase risks and dependencies to track

- **Phase 5 (#34/#36 per-document delivery address) blocks Phase 8 (Delivery Route)** — sequence accordingly; don't start Route work until the snapshot field exists. Phase 6's multi-address child model is *not* a Route blocker.
- **Phase 8's expected-profit service is shared with Phase 5's #41** — build once in Phase 8, don't duplicate in Phase 5; Phase 5's #41 row is just "surface the Phase 8 number here."
- **Shared transaction-union query** is consumed by Phase 4.8 (Day Book, company-wide) and Phase 6 (Ledger Transactions, per-party). First consumer lands the service; the other reuses it.
- **Phase 10's Expense entity is a soft dependency for Phase 8's actual-logistics-cost reconciliation** — Phase 8 ships without it (manual cost entry), Phase 10 upgrades it later. Not a hard blocker either direction. Phase 10 only *links* to Day Book; it does not rebuild it.
- **Phase 0.4's POS tax-rate fix and Phase 11's POS rework touch the same file** (`PosPage.tsx`) — land 0.4 first and cleanly, so Phase 11 isn't rebasing around a half-finished safety fix. Continuous preview (11.3) waits until 0.4 is in.
- **Phase 7.1 (custom fields) and Phase 7.2 (editable total) are independent of each other** despite both touching `NewInvoicePage.tsx` — can be parallelized across two workstreams if capacity allows, but expect merge friction on the same file; sequence one fully before starting the other if working with a single engineer.
- **Phase 3 cheque_status** feeds Day Book cash-position rules in 4.8 — land cheque clearing before (or with) Day Book, otherwise Day Book will over-count uncleared cheques.

---

## Open items (not product-rule decisions)

Three things are still open; none of them block starting Phase 0.1–0.3:

1. **Branching (process)** — new work should land on a fresh branch from a clean tree. The working tree currently has unrelated uncommitted changes (`backend/config/settings.py`, `core/services/feature_flags.py`, `insights/attention.py`, `insights/reorder.py`, `masters/views.py`, `payments/recon.py`, `payments/views.py`, `reporting/ims.py`, and several test files). Need confirmation these are safe to stash / commit separately (or already tracked elsewhere) before branching, so they don't leak into the new branch or get lost.
2. **Phase 4.7 bulk-download scale (business)** — tens vs. hundreds of invoices per action. Default in this plan is a sync zip capped ~50–100 with a download-URL response shape. If "select all 500 unpaid" is realistic, size this as a job+link from the start instead.
3. **Phase 0.4 walk-in path (repro, not a design call)** — whether the existing CR-111 cash-preview gate actually skips the walk-in / no-customer-id-yet path. Targeted live repro before that coverage gap is treated as confirmed; UPI-has-no-gate and "display never updates" are already confirmed from code.

---

## Process notes

- **Do not start Phase 0 until branching is confirmed.** Once confirmed: fresh branch, then #59 → #67 → #16 → 0.4 (walk-in repro as the first step of 0.4).
- **Phase 2 verification** uses the running local dev stack (the same `docker`-composed environment used for Phase 0's live repros), not code-reading alone — this session's own findings (#59, #67, and the POS tax-rate bug) are the evidence that static reading isn't sufficient proof of correctness for this codebase.
- **Section 11 reference-app extras** stay out of this plan unless explicitly requested to bundle into a specific phase.
