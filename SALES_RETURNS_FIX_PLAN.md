# Sales Returns: Fix Plan for Review Findings

**Source:** review of `SALES_RETURNS_IMPLEMENTATION_PLAN.md` (SR-01..SR-15), 2026-10-13.
**Scope:** close every bug, gap and test hole found in that review. Work package IDs are `SRF-xx` so they don't collide with `SR-xx`.

## 0. Completion record (2026-10-13)

Decisions taken (the two open questions): the live summary uses a **backend preview endpoint** (exact, rolled-back savepoint), and serials use **chips** (an `Autocomplete multiple` was not needed).

| Package | Result | Evidence |
|---|---|---|
| SRF-01 `tsc -b` error | Done | `npx tsc -b` clean |
| SRF-02 serial payloads | Done. Nothing pre-picked; first serial auto-picked on tick; quantity follows picks and is capped at the returnable quantity; already-returned serials are not offered; free-text lines trim serials to quantity. Also fixes Purchase Returns, which shares the table, and adds the same serial gate there | `invoiceSourceLines.test.ts`, `SalesReturnsPage.test.tsx`, `PurchaseReturnsPage.test.tsx` |
| SRF-03 stale-response race | Done (`loadSeq` ticket on pick, resume and reset) | `SalesReturnsPage.test.tsx` |
| SRF-04 clean-ups | Done: dead guards removed, "Cancel return" label, edit-draft title, memo warning gone | `SalesReturnsPage.test.tsx` |
| SRF-05 credit-note link | Done: COMPLETED note, else non-cancelled, else none | `test_sales_returns_fix.py` |
| SRF-06 standalone credit headroom | Done: `ReturnService.line_state` / `plan_takes`; early error names the note; `GET /sales/invoices/:id/returnable-lines/`; the page uses it and falls back to client arithmetic only if it fails | `test_sales_returns_fix.py`, `SalesReturnsPage.test.tsx` |
| SRF-07 backend tests | Done: 17 tests. Writing them found two more bugs, both fixed: (a) a return line naming its invoice line did not inherit that line's price/discount unless the client resent them; (b) sale stock movements were not tied to invoice lines, so returning the second line of a same-product invoice restored the first line's lot and cost. Sale and return movements now carry a `SALE_LINE:<id>` tag (older invoices fall back to FIFO order); cancel follows the tag | `test_sales_returns_fix.py` |
| SRF-08 frontend tests | Done (32 page tests + InvoiceDetailPage SR-04 tests) | vitest |
| SRF-09 GST Guard | Done in the dialog and on list-row Complete; shared parser `gstGuardErrors.ts` also used by `InvoiceDetailPage`; `getSalesReturn` now used to hydrate a resumed draft | `SalesReturnsPage.test.tsx` |
| SRF-10 filters | Done: server `q`, status, From/To dates, clear, invalid-range guard, localised status names | `test_sales_returns_fix.py`, `SalesReturnsPage.test.tsx` |
| SRF-11 live summary | Done: exact credit-note totals from `POST /sales/returns/preview-totals/` (same code path as Complete, rolled back); includes invoice-discount, charges and TCS shares; all strings localised | `test_sales_returns_fix.py`, `SalesReturnsPage.test.tsx` |
| SRF-12 detail dialog | Done: Disc %, GST %, tax breakdown | `SalesReturnsPage.test.tsx` |
| SRF-13 paid-invoice notice | Done, then corrected in round 2: `creditExceedsBalance` (credit from the exact preview vs the invoice balance). The API has no `amountPaid`, and `received` is derived (receivable minus balance), so it is not a reliable "was paid" signal | `returnHelpers.test.ts`, `SalesReturnsPage.test.tsx` |
| SRF-14 Simple Mode | **Not applicable.** The app has no Simple Mode and `menu.ts` has no such field. Sales Returns already sits under Sales > More for every role that can see sales; pinned by a menu test. The original plan text was corrected | `menu.test.ts` |
| SRF-15 docs and schema | Done: OpenAPI snapshot and generated types regenerated; `FREEZE_SCOPE_COVERAGE.md` and the original plan corrected | docs |

Also changed beyond the plan: "Return goods" is hidden on a fully returned invoice (the original SR-04 asked for this and it was missing).

### Round 2: items left open after the first pass (all closed)

| Item | Result | Evidence |
|---|---|---|
| Older (untagged) invoices restored the wrong lot | Closed. `CogsService.line_sale_moves` replays the original postings in order and accepts the mapping only if it adds up exactly (`seq`); returns on those invoices stamp `SALE_MOVE:<id>` so cancel undoes the same movement | `test_untagged_older_invoice_still_restores_the_named_lines_lot`, `test_cancel_of_an_untagged_invoice_return_reverses_the_same_lot` |
| Delivery-challan invoices restored the wrong lot | Closed for lines that carry a batch (challan conversion keeps the batch on the invoice line): moves are matched by batch (`batch` mode). A challan line with no batch and the same product on several lines still uses whole-product order, because nothing links a challan line to an invoice line | `test_challan_origin_invoice_restores_the_lot_named_on_the_line` |
| Page fallback ignored standalone credit notes | Closed by removing the fallback: if returnable quantities cannot be loaded the page says so and offers no lines | `SalesReturnsPage.test.tsx` |
| Part-credited invoice never became RETURNED; cancelling one of two returns left it RETURNED | Closed. "Fully returned" now means nothing is left to return (standalone credits count as spent), in Complete, Cancel and the preview. Credit-note discount/charges/TCS shares now subtract every earlier completed credit note | `test_part_credited_then_fully_returned_invoice_becomes_returned`, `test_cancelling_one_of_two_returns_reopens_a_fully_returned_invoice` |
| Second partial return re-restored the first FIFO layer (above its original quantity) | Closed. A layer can only get back what was taken from it; cancel undoes layers in reverse order. Postgres also exposed that the lock must be `of=("self",)` | `test_second_partial_return_never_pushes_a_cost_layer_above_its_original_quantity` |
| No concurrency test for returns; Postgres never run | Closed. `test_sales_returns_concurrency_postgres.py` (two returns completing together; complete racing cancel). Run on PostgreSQL 17: 25 passed, none skipped | Postgres run |
| A real browser run found two bugs no test caught | Closed. (1) The totals preview left a draft return and credit note behind on every edit when the request was not already inside a transaction (a bare savepoint is a no-op there); it now uses an explicit atomic block forced to roll back, with a test that runs with real commits. (2) "This invoice has recorded payments" appeared after a credit note was applied, because the API's `received` is receivable minus balance; the notice is now driven by "credit larger than the balance" | `test_preview_totals_leaves_nothing_behind_when_not_wrapped_in_a_transaction`, `returnHelpers.test.ts`, `SalesReturnsPage.test.tsx` |
| Reason presets (original plan section 15) | Closed. Four one-tap reasons; "Defective / damaged" also marks the selected lines Damaged. English and Hindi | `SalesReturnsPage.test.tsx` |
| Hindi strings unreviewed | Open for a human: the new keys are my translations. They need a Hindi reader's review before release (not something a test can settle) | n/a |
| Flaky catalog-import timing test | Not a returns test. `test_i4_catalog_import_of_5000_skus_meets_ten_seconds` takes about 9.6 s alone against a 10 s limit and fails when the machine is busy. Left unchanged; it needs its own fix | n/a |
| `Autocomplete multiple` serial picker | Closed by decision: chips were chosen and kept | n/a |
| Purchase Returns lacked the serial gate | Closed earlier in round 1 (gate + picker). Its server-side returnable endpoint, returned-serial tracking and draft lifecycle remain out of scope for a Sales Returns plan | `PurchaseReturnsPage.test.tsx` |

## 1. Guiding rules

1. Fix the failing CI gate first (SRF-01), because every later change is blocked by a red `tsc -b`.
2. Backend correctness and tests before UI polish. The money and stock paths are the risk.
3. Every work package ships with its own test. No package is "done" without a passing test named in its acceptance line.
4. Backend tests run on a private test DB (see memory: DB lock gotcha, `HsnRate` flush, `--reuse-db` HSN trap). Concurrency tests are Postgres-only.
5. Do not touch the unrelated bill-upload changes that share these files (`SalesBillUploadPage`, `imports/*`, `_preserve_requested_prices` in `sales/services.py`).

## 2. Release order

```
F1  Unblock + correctness   SRF-01 .. SRF-05          (CI green, no failing completes)
F2  Backend safety + tests  SRF-06 .. SRF-08          (headroom, regression tests)
F3  UX completeness         SRF-09 .. SRF-14
F4  Docs + sign-off         SRF-15
```

---

## F1: Unblock and correctness

### SRF-01: Fix the `tsc -b` error (B1) [P0, S]
- **File:** `web/src/pages/sales/SalesReturnsPage.tsx` (`invalidateAfterReturnLifecycle`, called from `cancelReturnMutation.onSuccess` and `completeDraftMutation.onSuccess`).
- **Cause:** `SalesReturn.salesInvoice` is typed `number | null | undefined`; `invalidateInvoiceSideEffects(qc, invoiceId?: number)` rejects `null`.
- **Fix:** change the helper parameter to `invoiceId?: number | null` and pass `invoiceId ?? undefined` into `invalidateInvoiceSideEffects`. Do not widen the shared helper's signature.
- **Accept:** `cd web && npx tsc -b` exits 0; `npx eslint` shows 0 errors.

### SRF-02: Serial-tracked lines must produce a valid payload (B2) [P0, M]
**Problem.** `invoiceItemsToSourceLines` pre-fills `serialNumbersText` with all sold serials. Ticking the line sets qty 1, so N serials go out for qty 1, and the server rejects it ("Exactly N serial number(s) are required", `backend/sales/return_service.py:43`). Quantity edits never trim serials.

**Design.** For serial-tracked lines, the selected serials are the source of truth and quantity is derived from them.
1. `invoiceSourceLines.ts`
   - Initialise `serialNumbersText: ''` (nothing pre-selected). Keep `soldSerialNumbers` as the pick list.
   - Add `returnedSerials?: string[]` input to `invoiceItemsToSourceLines` (new optional param, after `alreadyReturnedBySourceItem`) and set `soldSerialNumbers = serials.filter(s => !returned.has(s))`. This also fixes B3.
   - In `sourceLineReturnPayload`, for a `trackSerial` line send `serialNumbers` always (even if empty, so the server gives its clear error) and derive `quantity = serialNumbers.length` when the line is serial-tracked and has a pick list.
2. `InvoiceSourceLineTable.tsx` (`InvoiceReturnLineTable`)
   - Serial-tracked + non-empty `soldSerialNumbers`: render the chip picker only; make the Qty cell read-only and show the selected count. Selecting or clearing a chip sets `serialNumbersText` and `quantity` together, clamped to `maxQty` (disable further chips once `maxQty` is reached).
   - On `included: true` for such a line, do **not** default qty to 1; leave 0 until a serial is picked, and show the "pick serials" helper text.
   - Serial-tracked with no pick list (legacy invoices without stored serials): keep the free-text field; trim the text to `quantity` serials on quantity change, and show a mismatch error under the field when counts differ.
3. `completeBlockers.ts` / page: extend `returnCompleteDisabledReason` with `serialMismatch` and disable Save/Complete with a tooltip when any active serial-tracked line has `serials.length !== quantity`.
4. `SalesReturnsPage.tsx` `loadInvoiceSourceLines`: while summing prior COMPLETED returns, also collect `serialNumbers` per `sourceItem` (and per product for unlinked ones) into `returnedSerialsBySourceItem`, and pass it to `invoiceItemsToSourceLines`.
5. Resume-draft hydration: keep the draft's `serialNumbers`, and set `quantity` to their count.

- **Tests (vitest):** (a) tick a serial line, pick one chip, payload has qty 1 and one serial; (b) chip for a serial already returned is not offered; (c) Complete is disabled with a tooltip when serials and quantity disagree; (d) selecting more chips than `maxQty` is blocked; (e) legacy line without pick list trims serials on qty change.
- **Accept:** all five pass; manual run on a 3-serial invoice returns 1 serial end-to-end without a 400.

### SRF-03: Stale-response guard for invoice pick (B4) [P1, S]
- **File:** `SalesReturnsPage.tsx` (`onInvoicePick`, `onResumeDraft`, the `?invoice=` effect).
- **Fix:** add `const pickSeq = useRef(0)`. At the start of each load do `const seq = ++pickSeq.current`; after every `await`, `if (seq !== pickSeq.current) return;` before any `setInvoice` / `setLines` / `setLoadingInvoiceLines(false)`. `resetDialog` also increments `pickSeq`. Replace the inbound-URL effect's reliance on a stale `onInvoicePick` closure with a ref to the latest handler (`onPickRef.current = onInvoicePick`).
- **Test:** mock `getSalesInvoice` so invoice A resolves after B; pick A then B; assert lines on screen are B's.
- **Accept:** test passes; closing the dialog mid-load does not repopulate it.

### SRF-04: Clean-ups (B5, B6) [P3, S]
- Remove the always-true `if ( deleteSalesReturn )` guards (two places).
- Row buttons: COMPLETED row uses a dedicated label `phase1.cancelReturn` ("Cancel return" / Hindi) instead of `common.cancel`; the dialog's dismiss button keeps `common.close`. Add the key to `en.ts` and `hi.ts`.
- Dialog title: `phase1.newSalesReturn` for create, new key `phase1.editSalesReturnDraft` when `isExistingDraft`.
- Fix the `allReturns` `useMemo` dependency warning by moving `query.data?.results ?? []` inside the memo.
- **Accept:** eslint 0 warnings in these files; test asserts the title and button text.

### SRF-05: Credit-note link semantics on the serializer [P2, S]
- **File:** `backend/sales/serializers.py` `_linked_credit_note`.
- **Fix:** prefer a COMPLETED note; else the first non-CANCELLED note; else `None` (plan wording). A cancelled return then shows no link, and the list shows "—".
- **Test:** serializer test with return CANCELLED + cancelled note returns `credit_note_id is None`; with COMPLETED note returns that note; zero extra queries (`django_assert_num_queries`) because `credit_notes` is prefetched.

---

## F2: Backend safety and tests

### SRF-06: Standalone credit-note headroom check, early and clear [P1, M]
**Problem.** `ReturnService.complete_return` only checks `SalesReturnItem` headroom. If a standalone `SalesCreditNote` already credited quantity on the same invoice line, the failure happens midway inside `SalesNotesService.complete_credit_note` (`notes_services.py` ~line 304), after stock and number series have been touched. The frontend `maxQty` also ignores those credits.

**Backend** (`backend/sales/return_service.py`):
1. In `complete_return`, right after `_consume_prior(...)` and before the number is allocated, add a helper `_assert_credit_note_headroom(invoice, source_takes, sales_return)`:
   - For each `(item, lid, take)` in `source_takes`, sum `SalesCreditNoteItem.quantity` where `credit_note__sales_invoice=invoice`, `credit_note__status=COMPLETED`, `source_item_id=lid`, **and** `credit_note__sales_return__isnull=True` (standalone only, as return-linked notes are already counted via `SalesReturnItem`).
   - If `take + standalone_credited + (already consumed by returns on that line) > line.quantity`, raise `BusinessRuleError` naming the product, the line, the standalone credit note numbers, and the remaining quantity.
   - Keep the total-per-line math consistent with `_take_from` by subtracting standalone credits from `remaining_by_line[lid]` *before* the item loop, so partial headroom works.
2. Expose the same numbers to the UI: add read-only `returnable_quantity` to the invoice item representation used by the returns screen. Cheapest option is a new action `GET /sales/invoices/<id>/returnable-lines/` returning `[{source_item, product, sold, returned, credited_standalone, returnable}]` from one query set, reused by the frontend instead of re-deriving from `listSalesReturns`.

**Frontend:**
3. `loadInvoiceSourceLines` calls the new endpoint (SR-01's per-return summing becomes a fallback only if the endpoint fails). `maxQty = returnable`.
4. Keep `listSalesReturns({ sales_invoice })` for draft hydration only.

- **Backend tests** (`backend/tests/test_sales_returns_fix.py`, new): (a) standalone CN for 2 of 5 units, return of 4 → `BusinessRuleError` with the clear text, and **no** stock movement, number or journal created (assert counts); (b) return of 3 succeeds; (c) a return-linked CN is not double counted; (d) endpoint math matches `complete_return` for a mix of returns + standalone CN.
- **Frontend test:** `maxQty` shown equals `returnable`, never negative.
- **Accept:** a, b, c, d pass; atomicity assertion in (a) passes.

### SRF-07: Backend regression tests for SR-01/02/03/05/06 [P0, L]
Create `backend/tests/test_sales_returns_fix.py` (same file as SRF-06 or `test_sales_returns_sr.py`; follow the fixture style in `test_return_state_visibility.py` and `test_c02_lot_identity.py`). One test per checklist line in the original plan:

| Test | Asserts |
|---|---|
| `test_list_filters_by_sales_invoice_snake_and_camel` | `?sales_invoice=A` and `?salesInvoice=A` return only A's returns; B's never appear |
| `test_return_keeps_line_discount_on_return_and_credit_note` | line with 15% discount: `SalesReturnItem.discount_percent == 15` and the auto CN line total equals the discounted amount |
| `test_same_product_two_lines_restores_exact_lots` | batch A @100, batch B @200, returns naming each `source_item`: restored batch and COGS per line are exact; no double restore |
| `test_same_product_two_lines_in_one_return_advance_lots` | one return with two lines of the same product advances through sale moves sequentially (SR-06 core) |
| `test_mixed_condition_return_posts_exact_scrap` | SELLABLE COGS 5000 + DAMAGED COGS 100: `COGS_REVERSE == 5100`, `DAMAGED_SCRAP == 100` (not 2550) |
| `test_damaged_movement_carries_unit_cost` | `sales_return_damaged` movement has non-zero `unit_cost` |
| `test_serializer_credit_note_fields_no_n_plus_one` | `sales_invoice_number`, `credit_note_id`, `credit_note_number` present; query count flat for 10 returns |
| `test_cancel_reverses_everything` | stock movements reversed, FIFO peels un-restored, serials back to `SOLD`, CN cancelled, journals reversed, invoice `RETURNED` → `COMPLETED` |
| `test_cancel_return_sets_credit_note_link_empty` | pairs with SRF-05 |
| `test_date_filter_and_q_filter` | pairs with SRF-10 |

- **Also re-run** `test_c02_lot_identity.py`, `test_item_godown_expiry.py`, `test_return_state_visibility.py`, `test_b4_b5_notes_serial.py` and any `grep -l SalesReturn` test, because the scrap computation and prior-return set changed. Fix any that asserted the old ratio.
- **Postgres-only:** the concurrency case (two simultaneous completes on the same invoice line) goes in the existing concurrency suite and is run on Postgres, per project gotcha.
- **Accept:** all new tests green; the pre-existing return tests green; paste the run summary into the plan's sign-off section.

### SRF-08: Frontend tests for the unchecked items [P1, M]
Extend `web/src/pages/sales/SalesReturnsPage.test.tsx` and `InvoiceDetailPage.test.tsx`:
- **SR-04:** menu item "Return Goods" navigates to `/sales/returns?create=1&invoice=<id>`; "New credit note" navigates to `/sales/credit-notes/new?fromInvoice=<id>`; neither shows for a DRAFT or CANCELLED invoice.
- **SR-07:** complete fails (400) after implicit draft; switch invoice; `deleteSalesReturn(oldDraft)` called, next create uses a fresh idempotency key; existing draft (`isExistingDraft`) keeps the invoice picker disabled; Discard deletes only an implicit draft.
- **SR-08:** SALES_STAFF sees the info alert and an enabled Save, a disabled Complete; Save calls `createSalesReturn` then closes.
- **SR-09:** completing and cancelling each invalidate `sales-returns`, `completed-sales`, `sales-invoices`, `sales-credit-notes`, `products`, `stock-balance`, `customers` (spy on `invalidateQueries`).
- **SR-14:** a deferred `getSalesInvoice` promise: loader visible, "already returned" warning absent until resolve.
- **Resume draft:** hydration restores quantities, conditions and serials, and the draft's own quantities are not subtracted from `maxQty`.
- **Accept:** `npx vitest run src/pages/sales` green; coverage of each checklist line from the original plan Part III.

---

## F3: UX completeness

### SRF-09: GST-guard blocked-dialog flow [P1, M]
The page now contains the first version (guard issues state, override reason field gated by `canOverrideGstGuard`). Finish and prove it:
1. Confirm the backend response shape for a blocked `complete` (code, `blocking` list, whether warnings exist) from `backend/reporting/gst_guard.py` and the `InvoiceDetailPage` precedent, and reuse that parsing helper rather than a second copy (extract to `web/src/pages/sales/gstGuardErrors.ts` if both pages now duplicate it).
2. Both paths must handle it: the in-dialog **Complete**, and the row-level **Complete** on a DRAFT (`completeDraftMutation`). Retry sends `gstGuardOverrideReason` as `gst_guard_override_reason` (confirm the axios request transform snake-cases the body; add a test on the mapped body).
3. Users without `canOverrideGstGuard` see the issues and no override field.
4. Remove the now-unneeded `getSalesReturn` export or use it (draft refresh before resume); decide, don't leave dead code.
- **Tests:** blocked → dialog lists issues; override reason required (min length per backend rule); retry succeeds; non-override role sees read-only list.

### SRF-10: List filters, finished and consistent [P2, S]
- Server `q` is done; add the **From / To** date inputs to the filter bar, wired to `date_from` / `date_to`, included in the query key, and resetting `page` to 1 on change. Validate `from <= to` client side.
- Make sure the search is debounced (it is, via `debouncedSearch`) and resets `page`.
- Status filter options use `statusLabelKey(...)` (localised), not literals.
- Show the active filter count and a "Clear filters" button.
- **Backend test:** `test_date_filter_and_q_filter` (SRF-07 table). **Frontend test:** typing in search sends `q`; date change sends both params and page resets.

### SRF-11: Live summary: accuracy and localisation [P2, M]
1. Rename the label to "Estimated credit" and add a one-line note: "Final amount includes your share of invoice discount, charges and TCS."
2. Include cess (`line.cessRate` if carried on the source line; add it to `InvoiceSourceLine` from `item.cessRate`).
3. Price-inclusive invoices (`invoice.priceMode === 'INCLUSIVE'`): derive taxable from `unitPrice / (1 + gst)`. Add `priceMode` handling and a test.
4. Prorate invoice-level discount/charges using the same ratio as the backend (`ret_taxable / inv_taxable`, capped at 1). If that is judged too heavy for the client, instead call a lightweight preview endpoint: `POST /sales/returns/preview-totals/` accepting the draft lines and reusing `ReturnService` math without writing. **Recommendation:** build the endpoint, so there is a single source of truth and the numbers match the credit note to the paisa.
5. Move all strings into `en.ts` / `hi.ts` (`phase1.returnTaxable`, `phase1.returnGst`, `phase1.returnLinesUnits` with placeholders). No hard-coded English in JSX.
- **Accept:** for an invoice with a discount, charges and TCS, the preview equals the actual auto credit note total in a backend integration test (if the endpoint is built) or in a frontend test against fixtures (if client-side).

### SRF-12: Detail dialog completeness (SR-03) [P3, S]
Add columns: Discount %, GST %, Line total (use server `lineTotal`), and a tax breakdown footer (taxable, CGST, SGST, IGST, cess, round-off, grand total) from the fields already mapped on `SalesReturn`. Responsive: wrap the table in an `overflowX: 'auto'` container. Add a test that discount and GST columns render.

### SRF-13: Paid-invoice notice source of truth [P3, S]
Replace the `received` / `balance` inference with a single helper `invoiceHasReceipts(invoice)` that uses the field the API actually returns (`amountPaid` if present, else `received`), covered by a unit test for each shape. Add the field to `SalesInvoice` in `domain.ts` only if the backend serializer exposes it; check `openapi-types.ts` by grep.

### SRF-14: Simple Mode and navigation (SR-04) [P2, S]
1. Find how Simple Mode actually filters the menu (the review found no `visibleInSimpleMode` field in `menu.ts`; grep `simple` under `web/src/navigation` and `web/src/utils` for the real mechanism, such as a primary-id list).
2. Put `sales-returns` in whatever that mechanism uses for primary items, or promote it out of `sales-more`.
3. Update `menu.test.ts` with the expectation. If the plan's field does not exist, **amend the plan text** instead of inventing it.
4. Serial picker: convert to the `Autocomplete multiple` specified in SR-12 only if the chip UI from SRF-02 fails usability review; otherwise record "chips accepted" in the plan.

---

## F4: Documentation and sign-off

### SRF-15: Docs, OpenAPI, memory [P2, S]
1. Regenerate `docs/openapi-snapshot.json` and `web/src/api/openapi-types.ts` (`manage.py spectacular`, then the project's type generator) because the serializer gained fields and, with SRF-06/SRF-11, new endpoints. CI diffs both. Grep for the new operationIds; do not read the files whole.
2. Correct `SALES_RETURNS_IMPLEMENTATION_PLAN.md`:
   - Change the status line from "IMPLEMENTED & VERIFIED" to the real state until sign-off.
   - Remove the claim that `GstGuardBlockedDialog` existed at HEAD.
   - Fix `purchase_bill` → `purchase_invoice`.
   - Fix the SR-04 "visibleInSimpleMode" step per SRF-14.
   - Tick the verification checklist only for lines whose test now exists.
3. Update `docs/FREEZE_SCOPE_COVERAGE.md` for the sales-returns rows and `docs/TESTING_STRATEGY.md` if a new gap ID is closed.
4. Save a project memory note recording what is done and what is open once sign-off completes.

---

## 3. Order the work was done in

Backend first (`return_service.py`, `cogs_service.py`, serializers/views, `inventory/services.py`), then tests, then the shared web pieces (types, API client, billing line table, i18n), then `SalesReturnsPage.tsx` and its tests, then docs and the regenerated OpenAPI files.

## 4. Risks that turned out to matter

- **Shared line table:** the serial changes also drive Purchase Returns; its tests and a serial gate were added there.
- **Stock-movement `reason` is now used as a link** (`SALE_LINE:<id>`, `SALE_MOVE:<id>`). Nothing else reads it for SALE or SALES_RETURN movements (searched), but anything that starts to should treat these prefixes as reserved.
- **Savepoints are not enough outside a transaction.** Anything that must "run and roll back" in a request needs an explicit `transaction.atomic()` plus `set_rollback(True)`; the test suite's wrapping transaction hides the difference, so such code needs a `transaction=True` test.
- **Postgres locking:** `select_for_update` cannot lock across a nullable join; use `of=("self",)`.

## 5. Verification gate (all met, 2026-10-13)

- [x] `cd web && npx tsc -b` → 0 errors; `npx eslint .` → 0 errors (no warnings in touched files)
- [x] Full web suite: 239 files, 1,524 tests passed
- [x] `backend/tests/test_sales_returns_fix.py`: 17 passed
- [x] Full backend suite: 3,794 passed, 45 skipped, 1 failed. The failure was `test_i4_catalog_import_of_5000_skus_meets_ten_seconds`, a 10-second timing test that ran while the web suite was also running; it passes alone (9.6 s) and is unrelated to returns
- [x] OpenAPI snapshot and generated types regenerated; `ruff check` clean
- [x] Original plan's status line and checklist corrected
- [ ] Not done: manual browser smoke test and the Postgres-only concurrency run (no Postgres in this session)

## 6. Effort estimate

| Package | Size |
|---|---|
| SRF-01, 03, 04, 05, 12, 13, 14 | S each (about half a day or less) |
| SRF-02, 06, 08, 09, 10, 11 | M each (about 1 day) |
| SRF-07 | L (about 2 days, including fixing what the tests find) |
| SRF-15 | S |
| **Total** | **about 8 to 10 working days** |
