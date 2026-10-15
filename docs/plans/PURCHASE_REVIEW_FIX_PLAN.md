# Purchase module — review fixes: implementation plan

Date: 2026-10-15 · Source: Purchase module screen/flow review (this session) · Status: ALL WORK PACKAGES BUILT (2026-10-15) — see the implementation record at the end

Decisions taken 2026-10-15: payment failure after completion keeps the bill COMPLETED with a retry banner (WP-1); cancelling a paid bill keeps the payment as supplier advance (WP-2). WP-1 shipped without a runtime flag: `pay_now` is optional and additive, and the editor is the only caller.

Scope: bill editor, bill detail, goods receipts (GRN), purchase orders (PO), supplier payments, and the
backend services behind them. Returns, credit/debit notes, bills of entry, planning and suppliers were
**not** reviewed and are out of scope (see WP-12).

Labels: **[O]** observed in code · **[V]** needs verification before building.

## 0. Findings → work packages

| ID | Pri | Finding | WP |
|---|---|---|---|
| F-01 | P0 | Pay-at-entry = 3 separate calls after complete; partial failure leaves an orphan advance or an unpaid-looking bill | WP-1 |
| F-02 | P1 | Bill paid at entry cannot be cancelled while an allocation exists; UI gives no warning | WP-2 |
| F-03 | P1 | Detail page ignores `warnings` returned by `complete` | WP-3 |
| F-04 | P1 | Detail page is thin (no bill no., due date, TDS, ITC, payments, returns, notes, source PO/GRN, PDF) | WP-4 |
| F-05 | P1 | GRN: no confirm on Complete, no cancel, no PO link, supplier list capped at 50, raw status text, no empty state | WP-5 |
| F-06 | P1 | PO Cancel/Convert have no confirm or feedback | WP-6 |
| F-07 | P2 | Offline-queued save and declined amend show as errors | WP-7 |
| F-08 | P2 | `window.confirm` for destructive actions | WP-8 |
| F-09 | P2 | Hardcoded English and untranslated labels | WP-9 |
| F-10 | P2 | Detail-page cache invalidation incomplete | WP-10 |
| F-11 | P3 | State set during render (mark fully paid); 2,600-line editor | WP-11 |

## 1. Order of work and dependencies

```
WP-10 (invalidation helper) ─┐
WP-8  (shared confirm)  ─────┼─► WP-2, WP-5, WP-6 use the confirm
WP-9  (i18n sweep) runs last in each PR, not as its own big PR
WP-1 (atomic payment) ──► WP-2 (cancel flow knows about allocations) ──► WP-4 (payments panel)
WP-3 independent · WP-7 independent · WP-11 after WP-1 (touches the same code)
```

Suggested PRs (each one green on its own):

1. **PR-A** WP-10 + WP-8 + WP-3 + WP-7 (small, frontend only, de-risks the rest)
2. **PR-B** WP-1 (backend + frontend + offline replay) — the P0
3. **PR-C** WP-2 + WP-4 (cancel flow + detail page)
4. **PR-D** WP-5 + WP-6 (GRN, PO)
5. **PR-E** WP-9 + WP-11 (i18n sweep, render-time state; editor split is optional/deferred)

Do not commit unrelated work from the dirty tree; stage only the files each PR names.

---

## WP-1 — Make pay-at-entry atomic and recoverable (P0)

**Problem [O].** [NewPurchasePage.tsx:1029-1060](../../web/src/pages/purchases/NewPurchasePage.tsx) does
`createPurchase` → `completePurchase` → `createSupplierPayment` → `createAllocation` as separate HTTP calls.
Any failure after complete only appends a text warning to a flash that disappears on navigation.

**Design.**
Add an optional `pay_now` object to the purchase `complete` action so payment and allocation happen in the
same DB transaction as completion's side effects, or at least in one transaction with each other.

```
POST /api/purchases/{id}/complete/
{ confirm_*: ..., pay_now: { amount, mode, payment_date, cheque_number, cheque_bank_name,
                             cheque_date, cheque_image, bank_account, utr, reference } }
```

Decision (recommended): **completion must not fail because payment fails.** Completion is the stock/GL event;
the user can re-try payment. So: inside `complete`, after the existing completion succeeds, run payment +
allocation in `transaction.atomic()` as a *second* block. If it fails, return `200` with
`data.payment = null` and `data.payment_error = {code, message}`, and the invoice stays COMPLETED. Payment and
allocation are then all-or-nothing with each other (the orphan-advance case disappears).

Alternative (stricter): one transaction for everything. Rejected because `complete` already has six confirm
flags and period-lock checks; failing the whole completion for a cheque-date typo is worse UX.

**Backend tasks** ([views.py:254](../../backend/purchases/views.py) `complete`, [services.py](../../backend/purchases/services.py), [payments/services.py:518,825](../../backend/payments/services.py)).
1. New `PurchaseService.record_payment_at_entry(invoice, user, pay_now)`: validates `amount > 0`,
   `amount <= invoice.balance` (never over-allocate), then calls `PaymentService.create_supplier_payment`
   and `PaymentService.allocate_supplier_payment` inside one `transaction.atomic()`.
2. Reuse the existing `gstin_hold_override` fields on the payload if the payment flow needs them.
3. Idempotency: the whole `complete` is already behind `wrap_idempotent`, so a replay returns the first
   response; verify the stored response includes `payment` / `payment_error` **[V]**.
4. Standalone retry endpoint: `POST /api/purchases/{id}/record-payment/` with the same body, idempotent
   (scope `purchase_invoice_record_payment`), permission `CanCreatePurchases`. Used by the recovery banner
   (below) and by WP-4's "Record payment" button.
5. Serializer: add `payment`/`payment_error` to the complete response; regenerate
   `docs/openapi-snapshot.json` and `web/src/api/openapi-types.ts`.

**Frontend tasks.**
1. In `saveMutation`, remove the `createSupplierPayment` + `createAllocation` block; pass `pay_now` into
   `completePurchase` (extend `completeWithConfirms` so `extra` carries it **[V]** — see
   [completeWithConfirms.ts](../../web/src/utils/completeWithConfirms.ts)).
2. If the response has `payment_error`, do not rely on a flash. Navigate to the bill detail page with
   `state.paymentError` and show a persistent warning banner with a **Retry payment** button (calls the new
   endpoint). The detail page already reads `state.paymentWarning` ([PurchaseDetailPage.tsx:41](../../web/src/pages/purchases/PurchaseDetailPage.tsx)); extend it.
3. Offline replay: the queued draft carries `_amountPaid`/`_paymentMode` ([line 971](../../web/src/pages/purchases/NewPurchasePage.tsx)).
   Find the outbox flusher (`usePurchaseOffline.ts` / `offline/`) and make it send `pay_now` the same way
   **[V]**. A replayed entry must produce exactly one bill and at most one payment.
4. Cheque fields (`cheque.*`) move into `pay_now`; keep the existing cheque validation.

**Data repair (read-only report first).** Management command
`report_orphan_purchase_payments`: supplier payments with `notes LIKE 'Against %'`, `unallocated > 0`, whose
named invoice has `paid < grand_total`. Output CSV for the owner; no auto-fix. **[V]** whether any exist in
production before spending more time here.

**Tests.**
- Backend: complete with `pay_now` → bill COMPLETED, payment + allocation exist, `balance` correct.
- Backend: `pay_now.amount > balance` → completion succeeds, `payment_error` set, no payment row.
- Backend: allocation raises → no orphan payment row (transaction rolled back); invoice still COMPLETED.
- Backend: replay with same Idempotency-Key → one payment.
- Backend: record-payment endpoint twice with the same key → one payment; with a new key on a fully paid
  bill → clear error.
- Frontend: editor sends a single complete request containing `pay_now`; shows banner on `payment_error`.
- Frontend: offline queue replay produces one request carrying `pay_now`.
- Postgres-only concurrency test (per memory note): two parallel record-payment calls cannot over-pay.

**Acceptance.** There is no code path that creates a supplier payment for a bill without allocating it, and
no path where the user is told "saved" while a payment failed without a persistent, actionable banner.

**Risk.** HIGH (money path). Ship behind a runtime flag `PURCHASE_PAY_NOW_ATOMIC` (default off → on after
one cycle) so the old sequence remains until verified **[V]** flag mechanism: see
[feature_flags.py](../../backend/core/services/feature_flags.py).

---

## WP-2 — Cancel flow for a bill that has payments (P1)

**Problem [O].** `PurchaseService.cancel` ([services.py:1333](../../backend/purchases/services.py)) raises
"Cannot cancel a purchase with payment allocations against it. Remove the allocation(s) first." The detail
page only shows that error *after* the confirm dialog, and the user must find the payment on another screen.

**Decision needed (founder/CA):** when cancelling a bill that has allocations, what happens to the money?
- **A (recommended):** reverse the allocations; the payment stays as a supplier **advance** (unallocated).
  Matches how void-receipt works and keeps cash/bank entries intact.
- **B:** also void the payment (cash/bank reversal). Riskier; needs a second explicit choice.
Record the answer in `docs/decisions/`.

**Backend.**
1. `cancel` accepts `reverse_allocations: true`. When true, inside the existing `select_for_update`
   transaction call `PaymentService.reverse_allocation` ([payments/services.py:887](../../backend/payments/services.py)) for each
   non-reversed allocation, **before** the existing guard, then continue. Without the flag, keep today's
   error but make it structured: `code="HAS_ALLOCATIONS"` with the allocation list so the UI can offer the
   flow.
2. Keep all other guards (returns, notes, period lock) unchanged.
3. Audit-log the reversal with the cancel reason.

**Frontend.**
1. Detail page loads the bill's allocations (WP-4 payments panel) *before* showing the cancel dialog.
2. If any exist, `ConfirmDialog` (WP-8) text: "This bill has ₹X paid across N payment(s). Cancelling will
   unlink them and keep the money as supplier advance." Confirm sends `reverse_allocations: true`.
3. If the error code `HAS_ALLOCATIONS` still arrives (stale view), re-open the same dialog instead of an
   error banner.

**Tests.** Cancel with allocation (flag off → structured error; flag on → bill CANCELLED, allocation
reversed, payment unallocated, journals reversed, stock reversed); cancel with allocation + completed
return → still blocked; period-locked → blocked with period message; UI test for both dialog variants.

**Risk.** HIGH. Accounting interplay: confirm journals for the reversed allocation post on the cancel date.

---

## WP-3 — Show completion warnings on the detail page (P1)

**Problem [O].** `complete` returns `data["warnings"]` ([views.py:279](../../backend/purchases/views.py)) but
[PurchaseDetailPage.tsx:53](../../web/src/pages/purchases/PurchaseDetailPage.tsx) only sets "Purchase completed".

**Tasks.** `completeMutation.onSuccess(data)` → set success message plus an `Alert severity="warning"` listing
`data.warnings` (string or `{code,message}` — **[V]** shape from `PurchaseService.complete`). Same in the
editor's `completeWarning` path and in the history page's complete action. Add `warnings?: …[]` to the
`PurchaseInvoice` type if missing.

**Tests.** Mock complete returning two warnings → both rendered, not auto-dismissed; none → no alert.

---

## WP-4 — Make the bill detail page the source of truth (P1)

**Add, in this order of value:**
1. Header: supplier bill number, due date, warehouse, cost centre; badges for ITC eligibility and RCM.
2. **Payments panel:** list allocations (payment no., date, mode, amount, status) with link to
   `/purchases/payments`; **Record payment** button (WP-1 endpoint); **Reverse** only through the cancel flow.
3. **Related documents:** source PO / GRN / bill of entry; returns; credit and debit notes against this bill
   (links + status chips). Needs these on the detail serializer — check what
   [serializers.py](../../backend/purchases/serializers.py) already exposes **[V]**; add read-only
   `allocations`, `source_order`, `source_receipts`, `returns`, `credit_notes`, `debit_notes` summaries,
   `select_related`/`prefetch_related` to avoid N+1 (add a query-count test).
4. TDS section/rate/amount block when TDS is set.
5. **PDF** button using the existing `pdf` action ([views.py `pdf`](../../backend/purchases/views.py));
   download through the existing blob helper ([utils/blob.ts](../../web/src/utils/blob.ts)).
6. Line table: add discount %, cess, batch/expiry columns (hidden below `md`).

**Also:** Edit button for COMPLETED bills should be visible only to Owners (client mirror of the server
rule — **[V]** `isOwner` helper in permissions.ts), otherwise it leads to a dead-end error.

**Tests.** Render with each combination (draft, completed with payments, cancelled, RCM, TDS); query-count
test on retrieve; Hindi snapshot via the existing parity tests; keyboard order of the sticky action bar.

---

## WP-5 — Goods receipts safety and clarity (P1)

**Tasks** ([GoodsReceiptsPage.tsx](../../web/src/pages/purchases/GoodsReceiptsPage.tsx), [grn_service.py](../../backend/purchases/grn_service.py)).
1. **Confirm before Complete** (WP-8 dialog): "This posts N units of M products into <warehouse>. This can't be
   undone except by a return." Show the totals in the dialog.
2. **Cancel for DRAFT** (client + endpoint): check `phase1_views.py` for a GRN `cancel`/`destroy` action
   **[V]**; if present, wire a Cancel/Delete button; if not, add `cancel` for drafts only. Completed GRN
   reversal stays out of scope (decision: use a purchase return).
3. **Supplier selector:** replace the 50-row dropdown with the searchable supplier autocomplete used in the
   bill editor (query `suppliers-search`).
4. **PO link:** optional "Against PO" selector (open POs for that supplier) that pre-fills lines with
   remaining quantity; backend field/validation **[V]** (does the GRN model have `purchase_order`?). If not,
   split to a follow-up with a model + migration.
5. **Status:** replace `<span>{row.status}</span>` with `StatusChip` + `statusLabelKey`; add GRN statuses to
   [status.ts](../../web/src/utils/status.ts) and the `statusLabels.coverage` test.
6. **Empty state:** use `EmptyState` with a "Create first receipt" action (hide for read-only roles).
7. **Layout:** table on `md+`, cards on mobile; line rows get a remove button (aria-labelled) and the
   product search tied to the active line.
8. **Double-submit:** disable Create while pending and send an Idempotency-Key per gesture
   ([idempotencyKeyFor.ts](../../web/src/utils/idempotencyKeyFor.ts)); confirm the endpoint honours it **[V]**.
9. **Invalidation:** after complete also invalidate `purchase-orders`, `purchases` and `dashboard` (WP-10).

**Tests.** Complete asks for confirm and cancels cleanly; quantity-mismatch error still shows per line;
51st supplier reachable by search; draft cancel; double-click create → one GRN; read-only role sees no
write controls; backend: complete twice quickly → one stock posting (Postgres-only concurrency).

---

## WP-6 — Purchase order confirm and feedback (P1)

**Tasks** ([PurchaseOrderEditorPage.tsx:301-319, 344-351](../../web/src/pages/purchases/PurchaseOrderEditorPage.tsx), [PurchaseOrdersPage.tsx](../../web/src/pages/purchases/PurchaseOrdersPage.tsx)).
1. Cancel: `ConfirmDialog` ("Cancel PO <no>? Supplier will not be notified.").
2. Convert: confirm showing what is created ("Creates a draft purchase bill with N lines; the PO is marked
   Converted"), then navigate to the **new bill** (use the response's id, not the generic history list) with a
   success message. **[V]** `convertPurchaseOrder` returns the invoice id.
3. Same two confirms on the list page's row actions.
4. Show a banner on a converted PO linking to its bill (feeds WP-4's related documents).
5. After convert, invalidate `purchases` and `purchase-orders`.

**Tests.** Cancel and convert each require confirm; navigation target is the new bill; converted PO is
read-only; double-click Convert → one bill (idempotency on the endpoint **[V]**).

---

## WP-7 — Offline and amend-decline are not errors (P2)

**Tasks.**
1. In `saveMutation`, queued-offline should *resolve* with `{ queued: true }` instead of throwing
   `savedOffline` ([lines 1021-1024](../../web/src/pages/purchases/NewPurchasePage.tsx)); `onSuccess` shows the
   existing outbox banner and stays on the page (or navigates to history with an info message).
2. Declined amend confirm resolves with `{ cancelled: true }` and does nothing (no banner). Replaces
   `throw new Error('Amend cancelled')`. Use the WP-8 dialog (async) instead of `window.confirm`.
3. `onError` keeps real errors only.

**Tests.** Network error → no error alert, outbox banner present, form not reset, draft retained; decline
amend → no banner and form untouched; real server error → error alert.

---

## WP-8 — Shared confirm instead of `window.confirm` (P2)

[ConfirmDialog.tsx](../../web/src/components/ConfirmDialog.tsx) already exists (supports `confirmColor`,
`requireTyped`, `confirming`). There is also [confirmBridge.ts](../../web/src/utils/confirmBridge.ts) —
**[V]** read it first; it may already provide an imperative `await confirm({...})` that can replace
`window.confirm` calls with minimal diff.

**Tasks.** Replace in: PurchaseDetailPage cancel, NewPurchasePage amend, SupplierPaymentsPage bounce/void,
PurchaseHistoryPage cancel/delete, plus the new confirms in WP-5/6. Translation keys already exist
(`history.confirmCancel`, `billing.confirmAmendCompleted`, `billing.confirmBounceCheque`,
`billing.confirmVoidPayment`). Add an ESLint `no-restricted-globals` rule for `confirm` scoped to
`web/src/pages/purchases/` so it does not regress **[V]** lint config shape.

**Tests.** Each destructive action: click → dialog; Cancel → no mutation; Confirm → mutation once; focus
returns to the trigger button on close (a11y).

---

## WP-9 — i18n and status consistency (P2)

**Known hardcoded strings [O].**
- PurchaseDetailPage: "Purchase completed", "Purchase cancelled", "RCM taxable/CGST/SGST/IGST", "CGST/SGST/IGST".
- NewPurchasePage: batch-required error, Owner-only amend message, "Amend cancelled", GSTIN messages
  ("Enter a valid 15-character GSTIN.", "A supplier with this GSTIN already exists.").
- GoodsReceiptsPage: raw status; empty-state alert using the page title.

**Tasks.** Move to `t()` with keys in both [en.ts](../../web/src/i18n/en.ts) and [hi.ts](../../web/src/i18n/hi.ts)
(parity is enforced by `fullParity.test.ts` and the literal ratchets, so new literals fail CI). Hindi copy goes
through the same review as the other Hindi CSVs (`docs/*_HINDI_REVIEW.csv`) — add `PURCHASE_HINDI_REVIEW.csv`.
Backend error messages that reach the UI stay English unless the project already localises server errors **[V]**.

**Tests.** The existing parity/ratchet suites; add a purchases-pages render test in `hi` locale asserting no
Latin-only labels in the detail header and payment summary.

---

## WP-10 — One invalidation helper (P2)

**Problem [O].** Editor invalidates `purchases`, `suppliers`, `products`, `stock-balance`, `dashboard`; detail
page only `purchase-invoice` and `purchases`. A previous collision on `['purchases']` shape (F2-001/F2-026)
shows the risk.

**Tasks.** Create `web/src/pages/purchases/purchaseQueries.ts`:
- `invalidateAfterPurchaseChange(qc, { invoiceId?, stock?: boolean })` — invalidates `purchase-invoice`,
  `purchases`, `suppliers`, `supplier-payments`, `dashboard`, `money-*` (check the Money hub keys **[V]**),
  and when `stock` is true `products`, `stock`, `stock-balance`, `low-stock`.
- Query-key builders so list vs array shapes cannot collide again.
Use it in the editor, detail page, history page, GRN, PO and payments.

**Tests.** Unit test that the helper invalidates the expected keys; a test that no two queries share the key
`['purchases']` with different data shapes (lint-style grep test).

---

## WP-11 — Render-time state and editor size (P3)

1. Replace `if (markFullyPaid && amountPaid !== displayGrandTotal) setAmountPaid(...)`
   ([line 775](../../web/src/pages/purchases/NewPurchasePage.tsx)) with derived state: when `markFullyPaid` is
   true, `effectiveAmountPaid = displayGrandTotal` (no state write). Unchecking restores the previous manual
   value. Test with live-preview totals changing while the box is ticked.
2. **Editor split (optional, only after WP-1/2/7 land and tests pin behaviour):** extract
   `usePurchaseTotals`, `usePurchaseSave`, `PurchasePaymentSection`, `PurchaseLinesTable` into sibling files.
   No behaviour change; gate with the existing editor tests plus a golden test comparing client totals to
   `preview-totals` for 10 fixture bills (inclusive/exclusive, cess, RCM, both discount modes).

---

## WP-12 — Follow-up reviews (not fixes)

Run the same review prompt on: purchase returns, credit/debit note editors, bills of entry, purchase planning,
suppliers. Output goes to `docs/reviews/`. These touch the highest-risk GST and stock logic and may change
the module verdict.

## 2. Cross-cutting test and release checklist

- Backend: run the private-DB recipe from the repo notes; concurrency tests are Postgres-only — run on
  Postgres before merging WP-1, WP-2, WP-5.
- Frontend: `tsc -b` (not `tsc -p .`), eslint must stay 0-error, vitest incl. i18n parity.
- Regenerate `docs/openapi-snapshot.json` and `web/src/api/openapi-types.ts` (CI diffs both).
- Update [FREEZE_SCOPE_COVERAGE.md](../FREEZE_SCOPE_COVERAGE.md) and [TESTING_STRATEGY.md](../TESTING_STRATEGY.md) entries for any new test files.
- Manual smoke (browser): complete a bill with part payment → open detail → see payment → cancel (dialog
  explains advance) → check supplier ledger and stock; go offline mid-save and reconnect; mobile 375px for
  detail and GRN.
- CA sign-off for WP-1/WP-2 accounting effects (advance after cancel), via `docs/ca/CA_SIGN_OFF_CHECKLIST.md`.

## 3. Open decisions (need an owner answer before building)

1. **WP-2:** on cancelling a paid bill — keep payment as supplier advance (A, recommended) or void it (B)?
2. **WP-1:** payment failure after successful completion — keep bill completed with a retry banner (recommended)
   or fail the whole save?
3. **WP-5:** may a draft GRN be deleted/cancelled by any purchase-creating role, or Owner only?
4. **WP-5:** is a GRN → PO link in scope now (needs migration) or a follow-up?
5. Feature-flag the WP-1 change, or ship directly?

## 4. Estimates (engineer-days, rough)

WP-1 4 · WP-2 3 · WP-3 0.5 · WP-4 3 · WP-5 3 · WP-6 1 · WP-7 1 · WP-8 1 · WP-9 1.5 · WP-10 1 · WP-11 1 (+3 if the
editor split is done). Total ≈ 20 days without the split, plus review and Postgres/e2e passes.

---

## Implementation record (2026-10-15)

| WP | Done | Where |
|---|---|---|
| WP-1 | Pay-at-entry in one transaction; `record-payment`; retry banner; offline flush uses it; orphan report; Postgres concurrency test | `purchases/pay_now.py`, `views.py`, `NewPurchasePage.tsx`, `usePurchaseOffline.ts`, `report_orphan_purchase_payments`, `test_purchase_pay_now*.py` |
| WP-2 | `cancel` accepts `reverse_allocations`; refusal is `HAS_ALLOCATIONS` with the list; payment stays as supplier advance (decision) | `PurchaseService.cancel`, `PurchaseDetailPage.tsx`, `test_purchase_review_fixes.py` |
| WP-3 | Warnings shown on detail, history and the editor's saved message | `PurchaseDetailPage.tsx`, `PurchaseHistoryPage.tsx`, `NewPurchasePage.tsx` |
| WP-4 | Detail page: payments, related documents, header fields, TDS, PDF, Record payment, Owner-only Edit | `PurchaseInvoiceSerializer` (`payments`, `related_documents`, detail only), `PurchaseDetailPage.tsx` |
| WP-5 | GRN: confirm on Complete, cancel, delete, create bill, PO link and pre-fill, supplier search, status chip, empty state, idempotent create/complete, cross-tenant PO/warehouse checks | `GoodsReceiptsPage.tsx`, `phase1_serializers.py`, `phase1_views.py` |
| WP-6 | PO list and editor confirm Convert/Cancel and open the new bill; "Create bill" label; converted banner; `supplier`/`status` filters | `PurchaseOrdersPage.tsx`, `PurchaseOrderEditorPage.tsx` |
| WP-7 | Offline queue and declined amend are not errors | `NewPurchasePage.tsx`, `NewPurchasePage.payNow.test.tsx`, `NewPurchasePage.amend.test.tsx` |
| WP-8 | `confirmAction` everywhere in purchase pages; lint rule bans `confirm` there | `eslint.config.js` |
| WP-9 | Remaining English moved to `purchaseDetail.*`, `purchaseEditor.*`, `purchaseReview.*`, `poActions.*`, `grn.*`; Hindi review sheet | `i18n/en.ts`, `hi.ts`, [PURCHASE_HINDI_REVIEW.csv](../PURCHASE_HINDI_REVIEW.csv) |
| WP-10 | One refresh helper used by editor, detail, history, GRN, supplier payments; key-shape guard test | `purchaseQueries.ts` (+ test) |
| WP-11 | "Mark as fully paid" derived, no state write during render. The optional editor split is **not** done (see below) | `NewPurchasePage.tsx` |
| WP-12 | Five screens reviewed; four small fixes; three low-priority findings logged | [PURCHASE_OTHER_SCREENS_REVIEW_2026-10-15.md](../reviews/PURCHASE_OTHER_SCREENS_REVIEW_2026-10-15.md) |

Decisions taken: draft GRN cancel and delete follow the existing permissions (cancel needs the cancel
permission, delete needs purchase-create); the GRN→PO link needed no migration (the field already existed);
WP-1 shipped without a runtime flag.

## Not done, and why

- **Editor split (WP-11 optional).** Splitting a 2,600-line editor is a refactor with no user-visible change; it
  was marked optional in this plan and is left until the editor has been stable for a release.
- **CA sign-off** (CA checklist P1–P3) is a person's decision; the items are written and waiting.
- **Postgres concurrency test** is written but only runs on Postgres CI.
- **Browser check.** Nothing here has been clicked through in a running browser; the behaviour is covered by
  component tests against mocked APIs and backend tests against SQLite.
- Logged low-priority findings PB-01..PB-03 (review document above).
