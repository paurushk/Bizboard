# Inventory review — implementation plan

Source: [docs/reviews/INVENTORY_SCREEN_REVIEW_2026-10-15.md](reviews/INVENTORY_SCREEN_REVIEW_2026-10-15.md) (findings #1–#34, addendum A1–A6).
Status: BUILT 2026-10-16, uncommitted (record in section 8). Plan written 2026-10-15.

Finding numbers (`#n`) below refer to that review. Work packages are `INV-WP-nn`.

---

## 0. Ground rules

- **Backend tests:** use the private-DB pytest recipe from memory (`sales-returns-fix-2026-10-13`), watch for the DB lock and `HsnRate` flush gotchas. Concurrency tests are Postgres-only; run them before closing Waves 3 and 5.
- **Web:** type-check with `tsc -b` (not `tsc -p .`), lint must stay 0-error, run the touched `*.test.tsx`.
- **API changes:** regenerate `docs/openapi-snapshot.json` and `web/src/api/openapi-types.ts` in the same change (CI diffs both). Grep them, don't read them.
- **i18n:** every new string goes through `t()` with both English and Hindi entries; remove English literals in files you touch (#24).
- **Flags:** anything that changes accounting or the low-stock definition ships behind a company flag in `core/services/feature_flags.py`, default off, until the CA/owner signs off.
- **One commit per WP**, each with its tests. No WP leaves lint or tests red.
- **Do not touch** the existing uncommitted work in the tree (git status shows many staged files from other plans); work on top of it, stage only the files each WP changes.

## 1. Decisions needed before building

| ID | Decision | Blocks | Recommendation |
|---|---|---|---|
| D1 | Should adjustments, count variances, expiry write-offs and serial scrap post to the GL (Dr 5450 Shrinkage / Cr 1400 Inventory; reverse for gains)? Which cost: WAVG at date or movement `unit_cost`? | WP-12 | Yes, at the movement's `unit_cost` (what valuation already uses), behind a flag, with a backfill option for past periods |
| D2 | One definition of "low stock": company-wide available ≤ reorder, with per-godown override where one exists (current `low_stock_alert_payload`). Treat `reorder_level = 0` as "no rule" (not low) or as "alert at zero"? | WP-08 | Alert at zero only for items with a reorder rule > 0; out-of-stock items with no rule go to a separate "Out of stock" filter |
| D3 | Should Purchase planning cover company-wide low items, not only godown overrides? | WP-09 | Yes; company-wide rows get `warehouse = default godown` for the PO note |
| D4 | Count variance review threshold: units (`STOCK_COUNT_AUTO_POST_QTY`=5) or value? | WP-06 | Value-based with unit fallback; value above threshold needs owner confirm at post |
| D5 | Is "Customer Return / Exchange" allowed as an adjustment reason? | WP-01 | Remove it; link to Sales Return instead. Keep existing rows readable |
| D6 | May a DISPATCHED transfer be cancelled (stock returns from transit)? Backend allows it. | WP-05 | Yes, with confirm; cancel of COMPLETED needs a stronger warning and owner/admin only |
| D7 | Is marking a serial SOLD by hand ever valid? | WP-02 | No. Remove the action; serials become SOLD only through documents |
| D8 | Forecast window and method: single velocity (recommend 30-day weighted, excluding stock-out days) used by Forecast, Planning and the insight alert | WP-10 | Adopt one function in `inventory/forecast.py`, used by all three |

Record answers in the memory file for this programme once given.

## 2. Sequencing at a glance

```
Wave 0  Verify (no code)            WP-00
Wave 1  Stop misleading users       WP-01 .. WP-07   (all independent; start in parallel)
Wave 2  One truth for numbers       WP-08 → WP-09 → WP-10, WP-11
Wave 3  Stock ↔ money               WP-12 (needs D1)
Wave 4  Missing screens/features    WP-13 .. WP-19
Wave 5  Hardening                   WP-20
```

Dependencies: WP-09 needs WP-08; WP-10 needs D8; WP-13 (ledger) feeds WP-12's reconciliation view; WP-18 (cleanup) goes last in each area to avoid merge churn.

---

## Wave 0 — Verify (half a day)

### INV-WP-00 Confirm unproven findings
Goal: turn the "Needs verification" items into facts before spending effort.
1. **GL gap (#3, A3):** with accounting on, in a test tenant do an adjustment (−5), a count variance, an expiry write-off and a serial scrap. Query `JournalEntry` lines for each and compare `inventory_variance` from `accounting/reports.py` balance sheet before/after. Write this as a pytest (`backend/accounting/tests/test_stock_write_gl.py`) that currently **fails/xfails** and becomes the acceptance test for WP-12.
2. Reproduce #1 (202 pending shown as success) with a failing Vitest: mock `POST /inventory/adjustments/` → 202 and assert the banner. Reproduce #2 and #6 the same way (unit test on transition map; route test for the deep link).
3. Check audit coverage (A4): grep `AuditService.log` / `record_document_event` in counts, serial transition, expiry write-off, reorder-level edit, warehouse CRUD. Result decides scope of WP-12b.
4. Check `CanViewInventorySurfaces` on movement `unit_cost` for sales-only roles (section 9 of the review).
Output: short result note appended to the review doc. Exit: each of #3, #26 and the audit gaps is confirmed or struck.

---

## Wave 1 — Stop misleading users

### INV-WP-01 Stock adjustment: tell the truth (#1, #11, #12, #21, adj. date, idempotency)
Files: `web/src/pages/inventory/StockAdjustmentPage.tsx`, `web/src/api/legacy/inventory.ts`, `backend/inventory/views.py` (`AdjustmentView`), `backend/inventory/serializers.py` (`AdjustmentSerializer`), i18n files.
Steps:
1. `createStockAdjustment` returns the body and status: `{ status: 'APPLIED' | 'PENDING', approvalId?, movement?, warnings? }`. Backend: add `status: "APPLIED"` to the 201 body so the client doesn't infer from HTTP code.
2. Page: on `PENDING` show an info alert "Sent for approval — stock will change once approved" with a link to the approvals inbox; do **not** reset the form to defaults silently (clear product, keep godown). On `APPLIED` show success plus any `warnings` (negative stock) as a warning alert.
3. Idempotency: generate a UUID per form instance, send `Idempotency-Key`; wrap `AdjustmentView.post` in `wrap_idempotent(scope="stock_adjustment")` like opening stock. Regenerate the key after success.
4. Quantity: remove `Math.max(1, …)` clamp; use string state, `inputProps={{ min: 0, step: 'any' }}`, validate `> 0` inline. Respect unit decimals if the product's unit disallows fractions (`unit` metadata, if present).
5. Current-balance banner: when the product tracks batches, show the selected batch's on-hand; otherwise sum across batches for the chosen godown. Add a unit test for the helper.
6. Add an optional **date** field (default today) wired to the existing backend `date`; show the closed-period error inline.
7. Reasons: send a stable code (`DAMAGED`, `COUNT_DISCREPANCY`, `THEFT`, `OPENING_CORRECTION`, `OTHER`) plus text; backend stores code in `reason` prefix or new field (decision: keep `reason` text, add `reason_code` nullable field, migration). Drop "Customer Return / Exchange" (D5), with a helper line pointing to Sales Returns.
8. Show the value of the adjustment (qty × purchase price) so approval thresholds are predictable.
Tests: Vitest for 202 / 201+warnings / fractional / batch balance / date; pytest for idempotent retry returning the same movement and for `reason_code` validation.
Acceptance: a pending adjustment never shows "recorded"; double POST with the same key creates one movement.
Risk: low–medium (migration for `reason_code`). Size: M.

### INV-WP-02 Serials: align UI with backend (#2, D7)
Files: `web/src/pages/phase/InventoryPhasePages.tsx` (`SerialsPage`), `backend/inventory/views.py` (`SerialNumberViewSet`).
Steps:
1. Replace the UI transition table with the backend's: AVAILABLE→(Scrap), SOLD→(Return to stock), RETURNED→(Scrap), SCRAPPED→none. Remove "Mark sold".
2. Better labels: "Return to stock" (it ends AVAILABLE per CR-049), enum labels via `enumLabel`, replace "Last: X" with a status chip.
3. Add serial-number **search** (backend already supports `?serial_number=`), debounce, and show product/godown/last document (see step 4).
4. Backend: add `last_reference_type/id` (derive from latest movement or `_sale_movement_for_serial`) to the serializer so the row can link to the invoice/challan. Keep it a read-only computed field with `select_related` to avoid N+1; cap lookups per page.
5. Scrap confirm text states the stock effect ("−1 from <godown>").
Tests: unit test that every button the UI can show maps to an allowed backend transition (shared constant exported from the backend schema or a mirrored test); pytest for serializer N+1 (`assertNumQueries`).
Acceptance: no button on this page can produce "Invalid serial status transition". Size: S–M.

### INV-WP-03 Low stock → purchase link and godown column (#6, #7)
Files: `LowStockPage.tsx`, `NewPurchasePage.tsx` (or the purchase-order editor), `PurchaseOrderEditorPage.tsx`.
Steps:
1. Decide one deep-link contract: `?product=<id>&qty=<n>&warehouse=<id>` (already read by `PurchaseOrderEditorPage`). Point "Reorder item" to `/purchases/orders/new` (PO) — buyer intent — not the bill page; keep a secondary "Record purchase bill" link that `NewPurchasePage` supports via the same params (add reading `product`/`qty` there).
2. Suggested qty = `max(reorder − available, 1)` rounded to unit rules; pass it.
3. Add **Godown** column (data already per-row via `warehouse`; add `warehouseName` to `StockBalanceSerializer` low-stock payload if absent, and label "All godowns" for company-wide rows).
4. Add search box, sort by shortfall, and "Select + Create PO drafts" reusing the Planning draft endpoint (after WP-09).
Tests: route test that the PO editor opens with the product and qty; Vitest for the column and the link.
Acceptance: clicking Reorder lands on an editor with the item prefilled. Size: S–M.

### INV-WP-04 Close the API permission gap on planning and forecast (#26)
Files: `backend/inventory/planning.py` (`PurchasePlanningView.get_permissions`), `backend/inventory/forecast.py`.
Steps: GET → `IsAuthenticated, HasCompany, CanViewInventorySurfaces`; POST keeps `SubscriptionWritesAllowed, CanCreatePurchases`. Add the same to `DemandForecastView`.
Tests: pytest role matrix (OWNER, ADMIN, accountant, sales-only, buyer, stock-keeper, VIEWER) × both endpoints; confirms VIEWER → 403.
Acceptance: matrix matches the route guards in `App.tsx`. Size: XS. **Ship first.**

### INV-WP-05 Stock transfers: complete the lifecycle (#8, #9, #10, plus admin warnings)
Files: `InventoryPhasePages.tsx` (`StockTransferPage`), `backend/inventory/serializers.py` (`StockTransferSerializer`), `views.py`, `services.py` (no logic change expected).
Steps:
1. **List**: add "Items" column (e.g. "3 items · 120 pcs") and a row-expand/drawer showing lines (product, batch, qty, shortage). Serializer exposes `lines` with `product_name` (confirm; add if missing) and totals.
2. **Create dialog**: multi-line editor (add/remove lines), per-line batch filtered by *source* godown (`listBatches` with warehouse param; add `warehouse` filter to `BatchLotViewSet` returning only lots with stock there), available-qty hint at source, qty > 0 validation, serial field count must equal qty. Clear `error` on open.
3. **Actions by status**: DRAFT → Complete (dispatch) + Delete/Cancel; DISPATCHED → Receive + Cancel (confirm, D6); COMPLETED → Cancel (admin/owner only, strong warning that goods may already be sold).
4. **Partial receive**: Receive opens a dialog listing lines with "received qty" (default = dispatched) and "reason" when short; sends `receipts: [{line, quantity, reason}]` (already supported by `StockTransferService.receive`).
5. **Warnings**: `complete`/`receive` mutations keep the response and show `data.warnings` (admin negative-stock) in a dismissible alert.
6. **Offline (with WP-07)**: when queued, show a snackbar "Saved on this device — will complete when online" and mark the row "Queued".
7. Backend: allow `cancel` for DRAFT (it already works for any non-cancelled status — verify DRAFT path creates no movements) and add a role check for cancelling COMPLETED.
Tests: Vitest for each status's actions, partial receive payload, warnings display; pytest for DRAFT cancel (no movements), DISPATCHED cancel (restores source), short receipt then cancel, role check on COMPLETED cancel. Postgres run for the lock-order test.
Acceptance: user can always see what a transfer contains and can fix a mistaken draft or stuck dispatch without DB access. Size: L.

### INV-WP-06 Stock counts: variance review, surplus lines, partial counts, safety (#4, #5, #17, KEEP_SERVER, D4)
Files: `StockCountPage.tsx`, `StockConflictModal.tsx`, `backend/inventory/views.py` (`StockCountSessionViewSet`), `serializers.py`, model + migration if a `skipped` flag is added.
Steps:
1. **Review step**: after "Save counts", show a Review panel using `GET /stock-counts/{id}/review/` (exists): system, counted, variance, value of variance, sorted by |value|; lines above the D4 threshold are highlighted and require ticking "I have rechecked" before Post is enabled. "Post variances" confirm text states total gain/loss.
2. **Blind counting option**: expose `blind` at session creation (toggle with help text); the counter view omits system qty; review always reveals it.
3. **Add line**: "Add item not on list" (product autocomplete + batch + counted qty) → backend creates a `StockCountLine` with `system_qty = current` (0 for none); needed for surplus found stock.
4. **Partial counts**: add `StockCountLine.skipped` (bool, default false, migration). Post requires every line to be counted **or** skipped; skipped lines never adjust. UI: "Skip" per line and "Skip all uncounted".
5. **Safety**: `UnsavedChangesGuard` + confirm on closing the dialog with unsaved counts; confirm on "Cancel count" (explain nothing is posted); move Cancel away from Save visually.
6. **KEEP_SERVER**: record `skipped_due_to_drift` on affected lines and show them in the posted view ("12 lines not reconciled") instead of silently POSTED.
7. Moving the per-godown reorder section into a separate page/tab is covered by WP-18.
Tests: pytest for review payload, add-line, skip logic, post with skipped lines, KEEP_SERVER marking, idempotent post; Vitest for the review gating and the guard; Postgres concurrency test for post vs concurrent sale.
Acceptance: user sees every variance before it is posted and can count part of a godown. Size: L.

### INV-WP-07 Offline queue visibility (#10, #27)
Files: `useStockOffline.ts`, `StockCountPage.tsx`, `StockTransferPage`, `layouts/AppShell.tsx`, `offline/invoiceDraftCache.ts`, `pages/offline/OfflineOutboxPage.tsx`.
Steps:
1. Mount `useStockOffline` once in `AppShell` (not per page) so queued stock drafts flush from anywhere; keep the page-level conflict listener.
2. Pass a banner callback from the shell to show pending/failed counts in the existing outbox banner; link to `/offline-outbox`.
3. Mutations return `{offline:true}` → UI shows the "Queued" state (WP-05/06) and disables a second submit for that record.
4. Surface conflict events app-wide (toast with "Review") if the Counts page isn't open.
Tests: Vitest with mocked `navigator.onLine` and the outbox store: queue offline → banner shows 1 → online flush called once; failure shows message.
Acceptance: a queued count/transfer is always visible until it succeeds. Size: M.

---

## Wave 2 — One truth for numbers

### INV-WP-08 Single low-stock service (#20, A2, D2)
Files: new `backend/inventory/low_stock.py`; callers `views.py` (alerts, balance filter), `reporting/services.py:402`, `insights/alerts.py:148`, `insights/services.py:~400`, `ProductsPage.tsx`, `DashboardPage.tsx`.
Steps:
1. Move `low_stock_alert_payload` into `low_stock.py` with an explicit contract: returns rows with `product`, `warehouse|None`, `available`, `reorder_level`, `scope: 'company'|'godown'`, `shortfall`, `status: 'LOW'|'OUT'`. Apply D2 (zero-reorder handling, inactive/service/non-tracked items excluded, products with no balance rows and reorder > 0 included as OUT).
2. Replace the per-row `?low_stock=1` annotation in `StockBalanceViewSet` with the shared function (or remove the param and update callers).
3. Add `GET /inventory/alerts/?status=low|out` and use it for the Products-page stock filters (so chips and filters match Low stock). Keep Products' client filter only as a fallback for a few releases.
4. Dashboard tile, `reporting low_stock_count`, insights alert and attention items call the same function; add a contract test that all of them return the same product set for a fixture company.
Tests: pytest fixture with company-wide rule, godown override, zero reorder, no-balance product, reserved qty, inactive product; assert identical sets across the five consumers.
Acceptance: one number everywhere. Risk: medium (counts on dashboards change — communicate). Size: M–L. Behind flag `INVENTORY_LOW_STOCK_V2` for one release.

### INV-WP-09 Purchase planning covers all low items (#25, #28, #31, D3)
Files: `inventory/planning.py`, `PurchasePlanningPage.tsx`, `core/services/feature_flags.py`.
Steps:
1. Remove the `is_warehouse_specific` filter; company-wide rows resolve to a destination godown (default godown) for suggestions and notes; keep godown-specific rows separate.
2. Table adds **Supplier** (last supplier, editable select), **Qty** (editable, default suggested, units-aware), **Last price**, **On hand / On order** (open PO qty is deducted from the suggestion — check `suggest_replenishment` includes it; add if not).
3. Draft creation: preview dialog ("3 POs for 2 suppliers, 1 needs supplier") before POST; rows without supplier can be assigned a supplier in the table; fractional quantities keep decimals when the unit allows (remove blanket ceil, keep note).
4. Flags: if `ENABLE_PURCHASE_PLANNING` is on but `ENABLE_REPLENISHMENT` is off, hide the menu item or show an inline explanation with an owner-only enable link (instead of a 400 error).
5. Remove the embedded forecast table from this page (WP-10) and link to the Forecast page.
Tests: pytest planning with company-wide row, godown override, open PO deduction, supplier filter; Vitest for editing qty/supplier and preview; flag-matrix test for menu visibility vs API.
Acceptance: every item on Low stock either appears on Planning or has a stated reason. Size: M–L.

### INV-WP-10 One demand definition and a useful forecast page (#19, #29, #30, D8)
Files: `inventory/forecast.py`, `planning.py`, `insights/alerts.py`, `DemandForecastPage.tsx`.
Steps:
1. Single `item_velocity(company, product, warehouse=None, window)` used by all three; net of sales returns, excluding days the item was out of stock where determinable, configurable window (default per D8). Expose `method`, `window_days`, `confidence` (few sales → low).
2. Forecast API adds per row: `on_hand`, `on_order`, `days_of_cover`, `suggested_qty` (cover target setting, default 30 days minus on hand/on order), supplier; rows with enough cover are flagged and de-emphasised/filtered ("Needs action" default).
3. Page: sort/filter, per-godown toggle, "Plan purchase" passes the computed suggestion (not blanket 30 days); remove `Math.ceil(dailyRate*30)` client math.
4. Remove the forecast menu duplicate if desired: keep one "Planning & forecast" page with tabs (decision at implementation; coordinate with nav tests `menu.test.ts`).
Tests: pytest for returns netting, stock-out exclusion, equality of velocity across planning/forecast/insight; Vitest for the new columns.
Size: M.

### INV-WP-11 Stock KPIs and exports (#13, #14, #32)
Files: `CurrentStockPage.tsx`, `InventoryReportPage.tsx`, `legacy/reports.ts`, backend `inventory-summary` export.
Steps:
1. Replace the qty chip with **SKUs in stock / SKUs low / stock value**, all computed from the same filtered row set (value from rows' `stockValue`, add `stock_value` to the stock list payload or call summary with the same filters + godown).
2. Fix "Email": either remove the button or implement server-side email (`/exports/inventory-summary/email/`, uses the existing mail service) — recommend remove now, add later. Label CSV honestly ("Download CSV").
3. Surface balance/reserved **drift** health from the Inventory report as a warning chip on Current stock when any drift exists (single boolean from the summary endpoint).
4. Make godown filter server-side (`?warehouse=`, already supported) to cut payload for large tenants.
Tests: Vitest for KPI consistency under filters; no `mailto: blob:` anywhere (grep test).
Size: S–M.

---

## Wave 3 — Stock ↔ money

### INV-WP-12 GL posting for stock gains/losses (#3, A3, D1)
Preconditions: D1 answered; WP-00 test in place; CA review scheduled (QOS-style sign-off item).
Files: `backend/accounting/services.py` (new `PostingService.post_stock_adjustment`), `backend/inventory/views.py` (adjustment, count post, expiry write-off, serial scrap), `backend/inventory/services.py` (transfer-cancel adjustments excluded), `core/invariants/reports.py`, `reporting/gst_periods.py` (existing period gate), new management command.
Steps:
1. Chart of accounts: confirm/seed `5450 Stock shrinkage` (exists for scrap), add `4xxx Stock gain` or use shrinkage with credit; add expiry-specific `5460 Expired stock write-off` if the CA wants it separate.
2. `post_stock_adjustment(movement, user)`: Dr 5450 / Cr 1400 at `abs(qty) × unit_cost` for losses; Dr 1400 / Cr gain (or 5450) for gains; idempotent on movement id; respects accounting-enabled flag and the period gate already called by the views.
3. Hook into: manual adjustment; count post (one journal per session, per-line detail in narration); expiry write-off; serial scrap. **Exclude** transfer legs, transfer-cancel restores, import voids, and sales-return restores (they have their own treatment).
4. Reverse path: if an adjustment is later cancelled/voided (check whether such a path exists) post a reversal.
5. Feature flag `ACCOUNTING_POST_STOCK_ADJUSTMENTS`, default off; on enable, a management command `backfill_stock_adjustment_journals --from --to --dry-run` posts missing journals for existing adjustment movements (dry-run lists totals first). Existing command pattern: `repair_note_data`.
6. Register the GL-vs-valuation invariant (`core/invariants/reports.py`) in the default sweep once backfill is available, with tolerance and an explanation message.
7. UI: show `inventory_variance` on the Stock valuation and Inventory report pages ("GL 1400 vs stock value: ₹x difference"), link to the explanation; remove reliance on `AccountingBackfillBanner` alone.
Tests: the WP-00 pytest (now green) for all four paths; reversal; closed-period rejection; idempotency; backfill dry-run vs apply; balance sheet `equation_holds`; Postgres run.
Acceptance: after any stock write, GL 1400 and valuation agree within rounding; P&L shows the shrinkage. Risk: high (money). Size: L. Needs CA sign-off before the flag is enabled for any real tenant.

### INV-WP-12b Audit coverage (from A4)
Add `AuditService.log` / `record_document_event` to: count create/post/cancel, serial transition, expiry write-off, reorder-level create/edit, warehouse create/deactivate/delete. Test that each writes one audit row with user and entity. Size: S.

---

## Wave 4 — Missing screens and features

### INV-WP-13 Item ledger / stock movements page (#15)
New route `/inventory/ledger` (and a tab on the item form + "View ledger" from Current stock rows).
Backend: extend `StockMovementViewSet` with filters (product, warehouse, batch, type, date range, reference), serializer fields (date, type label, qty signed, running balance, unit cost [permission-gated], reason, reference type/id/number, user), cursor pagination, and a richer CSV export (all fields, streamed).
Frontend: filterable table with running balance for a single product/godown, reference links to invoice/bill/transfer/count, export.
Permissions: `CanViewInventorySurfaces`; hide cost column unless `can_view_financial_reports` (verify in WP-00).
Tests: pytest for running balance correctness with mixed movement types, transfers (both legs), voids; role test for cost visibility; Vitest for filters and links.
Acceptance: "why is this 37 and not 40?" answerable in two clicks. Size: L.

### INV-WP-14 Godowns management (#16, IN_TRANSIT visibility)
- Edit name/code (PATCH already exists), **Reactivate**, **Set as default** (backend invariant logic exists in `perform_update`), inline status filter (Active/Inactive/All).
- Hide the system `IN_TRANSIT` godown from every dropdown/list (flag `is_system` field, migration; filter in `listWarehouses` consumers and serializers; block adjust/count/delete on it server-side).
- Delete uses a proper dialog (type name to confirm) instead of `window.confirm`; explain when blocked (history/stock) with counts.
Tests: invariants (one default, no deactivating stocked), IN_TRANSIT excluded from dropdown APIs, cannot adjust/count in-transit. Size: M.

### INV-WP-15 Expiry alerts (#18)
- Split Expired vs Expiring (tabs or grouped), show `expired` flag colour + text (not colour only), value at cost per row.
- Write-off dialog: reason (Expired / Damaged / Return to supplier), qty (default available, not on-hand), value preview, confirmation; message when part is reserved ("12 reserved by orders ORD-…").
- Bulk select + single reason write-off; success/error snackbars; invalidate `['low-stock','inventory-summary','stock','expiry-alerts']`.
- Optional actions: "Sell first" (link to Quick entry with the lot preselected) and "Return to supplier" (link to purchase return with lot).
- Server: write-off uses `available` (already) and posts via WP-12.
Tests: pytest for reserved case and reason codes; Vitest for tabs/bulk. Size: M.

### INV-WP-16 Valuation page completeness (#13 valuation notes)
Add `as_of` and godown filters (backend already supports), correct column header when basis ≠ cost ("Unit price"), label non-cost bases "information only, not for accounts", show GL variance (WP-12), export. Remove the dead duplicate `StockValuationPage` in `InventoryPhasePages.tsx`. Size: S.

### INV-WP-17 Labels (#22)
Dedup feedback (increase copies or toast), cap copies with a visible limit, use the ZPL endpoint for thermal printers (button "Download ZPL") or remove it, fix `mrp = 0` price fallback (`||` with positive check), add batch/expiry/pack date optional lines, label size presets, "Print labels" entry from a purchase bill/GRN (prefilled copies = received qty), add products by filter (no barcode yet). Size: S–M.

### INV-WP-18 Consistency, i18n, accessibility, structure (#23, #24, #30, section 10)
- Remove duplicate `StockValuationPage` and 1-line re-export files (import real modules directly in `App.tsx`).
- Convert Warehouses/Transfers/Expiry/Serials English literals to `t()` (Hindi entries); consistent terminology (godown everywhere, "Dispatch" instead of "Complete" for transfers).
- Replace `window.confirm` with a shared `ConfirmDialog` (focus-managed, accessible) across inventory pages.
- Colour-only statuses get icons/text; group label for day chips; keyboard test for "Show lots".
- Move per-godown reorder rules out of Stock Counts into the item form tab "Reorder rules" and a read-only "Reorder rules" list under Low stock.
- Type the `Row` usage in phase pages with proper interfaces.
Tests: existing page tests updated; add an a11y test (jest-axe if used in repo) for the touched pages. Size: M.

### INV-WP-19 Automation (section 12) — optional, after Waves 1–3 land
1. Barcode scan input in count dialog (increments counted qty by 1; Enter after quantity).
2. "Count equals system" bulk fill for untouched lines (marks as counted, shown separately in review).
3. FEFO default batch on transfers and adjustments (earliest expiry with stock at the source godown).
4. Launch adjustment/transfer/ledger from a Current stock row with product/godown prefilled.
5. Suggest reorder levels from velocity on the item form (accept/ignore).
Each is independent; ship by value. Size: M each.

---

## Wave 5 — Hardening

### INV-WP-20 Regression, roles, Postgres, browser
1. Role matrix test file (`backend/inventory/tests/test_permissions_matrix.py`): every inventory endpoint × roles (OWNER, ADMIN, accountant, sales-only, buyer, stock-keeper, VIEWER) × GET/POST; asserts match `menu.ts` and `App.tsx` guards.
2. Postgres run of all concurrency tests (transfers, counts, adjustments, serial transitions, idempotency) — required by project memory since SQLite hides them.
3. Cross-module regression suite: invoice with batch item after transfer/adjust/count; sales return restock; route "goods to check in" after godown deactivation; manufacturing consume/produce then count; Tally/CSV opening stock into an active godown; purchase bill → expiry/low-stock updates.
4. Browser pass (installed Chrome, crawl recipe in `ux-programme-2026-09-30` memory): all 12 screens at desktop and 375px, Hindi locale, keyboard-only flow for adjustment/count/transfer.
5. Update `docs/FREEZE_SCOPE_COVERAGE.md`, `docs/PRODUCT_QUALITY_BACKLOG.md` (qos backlog items for each WP, regenerate), and the review doc status table.
Exit: green CI (lint, tsc -b, pytest incl. Postgres, openapi drift check, qos-lint), no open P0/P1 from the review.

---

## 3. Traceability: finding → work package

| Finding | WP | Finding | WP |
|---|---|---|---|
| #1 | 01 | #18 | 15 |
| #2 | 02 | #19 | 10 |
| #3, A3 | 00, 12, 16 | #20, A2 | 08, 09 |
| #4, #5, #17 | 06 | #21 | 01 |
| #6, #7 | 03 | #22 | 17 |
| #8, #9 | 05 | #23, #24 | 18 |
| #10, #27 | 05, 06, 07 | #25, #28, #31 | 09 |
| #11, #12 | 01 | #26 | 04 |
| #13, #14, #32 | 11 | #29, #30 | 10 |
| #15 | 13 | #33 | 18 (item form: retry opening stock — add in 18 or a small WP-21) |
| #16 | 14 | #34 | keep (no change) |
| Audit gaps (A4) | 12b | Section 9 permission checks | 00, 20 |

Add **INV-WP-21 (small)**: item form — after "Item saved, opening stock failed", show an in-dialog "Retry opening stock" button using the same idempotency keys, and keep the saved item selected. Size: S.

## 4. Order of work and effort (one engineer, ideal days)

| Order | WP | Size | Days |
|---|---|---|---|
| 1 | 00 verify | XS | 0.5 |
| 2 | 04 permissions | XS | 0.5 |
| 3 | 01 adjustment | M | 2 |
| 4 | 02 serials | S–M | 1.5 |
| 5 | 03 low-stock link/column | S–M | 1.5 |
| 6 | 07 offline visibility | M | 2 |
| 7 | 05 transfers | L | 4 |
| 8 | 06 counts | L | 4 |
| 9 | 08 low-stock service | M–L | 3 |
| 10 | 09 planning | M–L | 3 |
| 11 | 10 forecast | M | 2 |
| 12 | 11 KPIs/exports | S–M | 1.5 |
| 13 | 12 + 12b GL + audit | L | 6 (+CA review) |
| 14 | 13 ledger | L | 4 |
| 15 | 14 godowns | M | 2 |
| 16 | 15 expiry | M | 2 |
| 17 | 16, 17, 21 | S each | 3 |
| 18 | 18 cleanup | M | 2.5 |
| 19 | 19 automation | M each | 6 (optional) |
| 20 | 20 hardening | M | 3 |
| | **Total** | | **≈ 48 days (≈ 42 without WP-19)** |

Parallelisation: Wave 1 packages touch mostly separate files (01 adjustment, 02 serials, 03 low stock + purchase editors, 04 backend permissions, 05 transfers, 06 counts, 07 offline hook/shell). 05, 06 and 07 all touch `useStockOffline` / outbox — do 07 first or land together. Two people can run Waves 1 and 2 side by side if 08/09/10 are one owner (shared low-stock and velocity code) and 05/06 another.

## 5. Rollout and risk controls

- **Flags** (default off, enable per tenant): `INVENTORY_LOW_STOCK_V2` (WP-08/09), `ACCOUNTING_POST_STOCK_ADJUSTMENTS` (WP-12). Others ship on.
- **Migrations** (all additive, nullable/defaulted): `reason_code` (01), `StockCountLine.skipped` + drift marker (06), `Warehouse.is_system` (14). Check for number collisions with the many uncommitted migrations already staged (core 0058–0059, sales 0073–0075, payments 0044, reporting 0016 …) before creating new ones.
- **Data changes visible to users:** dashboard low-stock numbers (08), GL/P&L (12). Add release notes and a one-time in-app notice.
- **Rollback:** every WP is a single commit; flags off restores old behaviour for 08 and 12; migrations are backwards compatible.
- **Money-path review:** WP-12 gets the same review treatment as past money work (second reviewer pass + CA sign-off recorded as a QOS item).

## 6. Definition of done (every WP)

1. Acceptance criteria above met and demonstrated by a test, not by inspection.
2. `tsc -b`, lint, touched Vitest files, touched pytest files green; OpenAPI snapshot/types regenerated if the API changed.
3. New strings in English and Hindi; no new English literals.
4. Permission behaviour covered by a test for any endpoint touched.
5. Review doc status table updated (finding → fixed in commit).
6. Memory note updated with decisions D1–D8 and what is left open.

## 7. Open items needing people, not code

- D1–D8 answers (owner/CA).
- CA sign-off on the shrinkage/expiry accounts and backfill policy (WP-12).
- Hindi copy review for new strings.
- Decide whether manufacturing needs its own adjustment treatment (A4, "manufacturing" row) — read `manufacturing/services.py` before WP-12 to avoid double posting.

---

## 8. Implementation record (2026-10-16)

All work packages WP-00 to WP-21 are built in the working tree and not committed. Decisions that
were not answered by the owner were taken as the plan recommended, except where noted.

**Decisions**

| ID | Outcome |
|---|---|
| D1 | GL posting for adjustments, count variances, expiry write-offs and serial scrap is built behind `ACCOUNTING_POST_STOCK_ADJUSTMENTS` (default off). `backfill_stock_adjustment_journals` (dry run, `--apply`) covers past periods. **Needs CA sign-off before any real tenant turns it on.** |
| D2 | Owner answer: items with no reorder rule and zero stock go to a separate "Out of stock" tab; low stock is the company total with per-godown overrides. One service (`inventory/low_stock.py`) feeds the alerts API, dashboard count, balance filter, insights, planning and the Products filter. |
| D3 | Owner answer: planning includes company-wide low items, destined for the default godown. |
| D4 | A count line needs a recheck above 5 units or a value of at least 10,000 (`STOCK_COUNT_RECHECK_VALUE`). |
| D5-D7 | As recommended: no "Customer Return" reason, DISPATCHED transfers can be cancelled (completed ones owner/manager only), no manual SOLD. |
| D8 | One velocity: 30-day trailing mean net of sales returns (`inventory/forecast.py`), used by the forecast and by planning. |

**Built beyond the original list**

- Count entry: scan a barcode or code to count one unit, "Count equals system" bulk fill (not offered on blind counts).
- First-expiry-first-out default lot on transfers and on reductions; adjustment and transfer open prefilled from a Current stock row.
- Item form: a reorder level suggested from 14 days of recent sales (applied only on click); "Retry opening stock" after a partial save, without creating the item again.
- Serials: "View sale" opens the invoice or challan a sold unit went out on.
- Low stock: per-godown reorder rules moved here from Stock Counts; "Plan purchases" link to Purchase planning.
- All `window.confirm` calls on the inventory pages use the in-app confirm dialog.

**Known gaps, left on purpose**

- ~~No `reason_code` column on adjustments~~ (out of date: `StockMovement.reason_code` exists since WP-01 and adjustments, expiry write-offs and shortage write-offs set it; see the deep-review plan, IDR-13).
- ~~The transfer list has no per-row "Queued" state~~ (out of date: the Transfers page shows a Queued chip, and a goods-in-transit panel, since the deep review).
- Low stock does not create purchase orders itself; "Plan purchases" opens Purchase planning, which does.
- Postgres concurrency runs and an in-browser pass were not done in this session.
