# Inventory — deep screen-by-screen review (12 screens)

Date: 2026-10-16. Method: the 20-point Screen, Flow & Product Impact prompt, applied to each screen.
Companion to `INVENTORY_SCREEN_REVIEW_2026-10-15.md` (pass 1-2) and `..._2026-10-16_PASS3.md`. This document supersedes pass 3 where they differ.

**Evidence tags.** **[O]** read in code this pass · **[I]** inferred · **[U]** unknown · **[V]** needs verification (run it, ask the owner/CA).

**What was read in full:** all 12 page files, `ItemFormDialog`, `GodownReorderRules`, `countHelpers`, `lowStockHelpers`, `stockKpis`,
`adjustmentHelpers`, `expiryHelpers`, `labelHelpers`, `serialActions`; backend `inventory/views.py` (adjustment, expiry, count, transfer,
serial, warehouse), `low_stock.py`, `planning.py`, `forecast.py`, `reorder_maps.py`, `suggest_replenishment`, count serializers/models,
`masters` Product model/viewset, `core/idempotency.py`, `core/exceptions.py` (IntegrityError mapping), `core/permissions.py`.
**Not read / not done:** `useStockOffline`, `StockLedgerPage`, `InventoryReportPage`, `post_movement` internals, the valuation engine, any backend test,
no running app, no Postgres, no role-matrix run, no screenshots (so layout/contrast/touch-target statements are inferred from code).

---

## 0. Master findings table (all screens)

Priority: P0 data/security/severe · P1 major workflow or correctness · P2 moderate · P3 minor. IDs are used in the screen sections below.

| ID | Pri | Screen | Problem | Evidence |
|---|---|---|---|---|
| F-01 | **P1** | Adjustment, Transfers, Counts | **Idempotency key is not renewed after a server rejection, so a corrected retry is blocked.** The server stores deterministic 4xx answers under the key. Adjustment reuses one key until success (`StockAdjustmentPage.tsx:140,174`); transfer dispatch/receive and count post use fixed per-document keys (`StockTransferPage.tsx:327,357`, `StockCountPage.tsx:208`). Same body: the old error is replayed even after the cause is fixed (e.g. stock added). Changed body (new quantity): HTTP 422 "Idempotency-Key was already used for a different request". | **[O]** `core/idempotency.py` `wrap_idempotent` stores non-transient 4xx and fingerprints the body; `TRANSIENT_4XX_CODES` lists period-locked/stock-count-conflict but not stock or validation errors. **[V]** which error codes insufficient-stock raises |
| F-02 | **P1** | Serials | **"Return to stock" on a SOLD serial posts a stock return with no sales return / credit note.** It adds a `SALES_RETURN` movement and restores FIFO layers while the invoice, receivable and GST stay as they were. | **[O]** `views.py` `SerialNumberViewSet.transition` (SOLD→AVAILABLE), `serialActions.ts`. **[V]** whether COGS is reversed in the GL |
| F-03 | **P1** | Expiry, Counts, Serials | **Approval rule (value ≥ ₹10,000 or ≥ 10 % of on-hand) exists only on the Adjustment screen.** Expiry write-off, count post and serial scrap move stock with no second approver. | **[O]** `stock_adjustment_needs_second` referenced only at `views.py:313-321` |
| F-04 | **P1** | Counts | Count "recheck" is a client checkbox the same user ticks (`canPostReview`); the server posts regardless. | **[O]** `countHelpers.ts`, `views.py` post |
| F-05 | **P1** | Counts | Drift handling is all-or-nothing, and `KEEP_LOCAL` subtracts a sale twice (counted figure predates the sale, posted variance = counted − current). | **[O]** `views.py:1063-1117` |
| F-06 | P2 | Counts | Two people counting the same godown overwrite each other: the page saves **every** line (typed or not) in one request; last save wins. Also two open sessions for the same godown are allowed. | **[O]** `saveBody()`, `serializers.py` update; **[V]** no open-session guard found |
| F-07 | P2 | Counts | Online "Post variances" closes the dialog with **no success message**; only an invisible "last synced" line changes. Offline path shows a notice but the pending counter lives in component state and is lost on reload. | **[O]** `StockCountPage.tsx:236-250` |
| F-08 | P2 | Counts | Counting scans cannot name a lot: scan adds +1 to the first matching line, so a batch item is counted into the wrong lot. "Count equals system" fills every open line with the system quantity, which lets a counter confirm without counting (governance). | **[O]** `countHelpers.ts` `applyScan`, `fillWithSystemQty` |
| F-09 | P2 | Counts | Session sheet contains only lines with `on_hand > 0`: negative-stock items never get corrected by a count. Cancel is not row-locked and can overwrite a just-posted session. | **[O]** `serializers.py create`, `views.py cancel` |
| F-10 | P2 | Expiry | Write-off loops row by row with no idempotency; after a partial failure the dialog still holds the rows that succeeded, so "Write off" again re-posts them (double write-off when a partial quantity was typed). Non-numeric quantity or `days` raises a server error instead of a message. | **[O]** `ExpiryAlertsPage.tsx:76-102`, `views.py:865-930` |
| F-11 | P2 | Expiry | "Return to supplier" opens a blank return form (`/purchases/returns?create=1`) and drops the product, lot and quantity. Whole page is replaced by a spinner on every day/godown filter change. | **[O]** `ExpiryAlertsPage.tsx:104,251` |
| F-12 | P2 | Transfers | "Create draft" has no idempotency key: a double click or retry makes two drafts. No success notice after create. | **[O]** `StockTransferPage.tsx:291-311` |
| F-13 | P2 | Transfers | Shortage on receive (`shortage_qty`) is recorded, but nothing on screen says where the missing stock went (written off, claim on carrier, still in transit). | **[O]** detail table only; **[V]** accounting treatment |
| F-14 | P2 | Planning | Godown-specific rows still use the old 14-day *gross* SALE velocity inside `suggest_replenishment`, not the "one velocity" (30-day, net of returns) the record claims. Forecast and planning can disagree for the same item. | **[O]** `services.py:2493-2503` vs `forecast.py` |
| F-15 | P2 | Planning | Transfer suggestion is not capped by the donor godown's surplus; a donor with a surplus of 2 is proposed for a transfer of the whole shortfall. System/in-transit godowns are in the donor list. | **[O]** `services.py:2512-2540`, `reorder_maps.py` |
| F-16 | P2 | Planning | "On order" counts only DRAFT purchase orders: abandoned old drafts suppress real suggestions; a converted-but-unposted bill is invisible; "Create drafts" has no duplicate guard. The `last_price` column is the item master purchase price, not the last price paid. | **[O]** `planning.py`, `PurchaseOrder.Status` = DRAFT/CONVERTED/CANCELLED |
| F-17 | P2 | Forecast | Includes inactive and non-stock items that sold; treats out-of-stock days as zero demand; shows only items that sold in 30 days; windows (30/14/30 days) are fixed; it is a trailing average, not a forecast. | **[O]** `forecast.py` |
| F-18 | P2 | Products | **Export CSV ignores the on-screen filters** (category, brand, stock, tax, needs-review) and exports the whole catalogue (search only). | **[O]** `ProductsPage.tsx:192-240` |
| F-19 | P2 | Products | "In stock" filter excludes low-stock items (shown only by "Low"), so In + Low + Out ≠ all. Delete of a used item: the UI has a "marked inactive" success branch, but the server refuses with an error; the branch never runs. | **[O]** `ProductsPage.tsx:169`, `masters/views.py perform_destroy` |
| F-20 | P2 | Products | Duplicate-name warning checks only the loaded page of 50. After "Item saved, but opening stock failed" the products list is not refreshed (cache invalidated only on success), so the item is invisible and may be created again. | **[O]** `ItemFormDialog.tsx:565,580`, `ProductsPage.tsx:557` |
| F-21 | P2 | Products | No price sanity checks: selling price may be 0 or above MRP; purchase price above selling price not warned. HSN is optional even for regular dealers. | **[O]** `validateForm` |
| F-22 | P2 | Products, Adjustment, Current stock | Whole-company stock (`listStock()` with no filter) is loaded to show one balance (item form, adjustment) or the full list (current stock has no server paging). Item form also pulls the whole demand forecast for one reorder hint. | **[O]** `ItemFormDialog.tsx:200,272`, `StockAdjustmentPage.tsx:69` |
| F-23 | P2 | Current stock | **Print prints only the visible window** (rows are virtualized); row key `${warehouse}-${product}` repeats when one product has several lot rows in the same godown view. CSV export ignores the search and godown filter. | **[O]** `CurrentStockPage.tsx:192,231,227`; **[V]** repeat keys |
| F-24 | P2 | Labels | ZPL download carries only name and code: no price, lot, expiry, label size, so thermal labels differ from the on-screen/browser labels. "Add items without barcode" loads the entire catalogue and takes an arbitrary first 100. | **[O]** `views.py:209-224`, `LabelPrintPage.tsx:169-185` |
| F-25 | P2 | Serials | Transition is not locked or idempotent (two requests can both pass the SOLD check and post two returns); scrap of a RETURNED unit with no on-hand sets SCRAPPED without a stock movement; no serial history/trace, no product or godown filter. | **[O]** `views.py` transition |
| F-26 | P2 | Several | Role split uneven: reads open to sales/purchase/finance; Labels, Godowns, Counts, Transfers, Serials need manage-inventory; serial *lookup* is allowed to sales but the menu hides the page. Cost visibility checked per endpoint (expiry/valuation) but **[V]** not on planning `last_price` or count `variance_value_estimate`. | **[O]** `menu.ts`, `views.py` |
| F-27 | P3 | Low stock | Rows on the "Out of stock" tab carry the chip "At or below reorder" (no rule exists). | **[O]** `LowStockPage.tsx:123` |
| F-28 | P3 | Many | English literals and raw enums in Hindi-capable UI: ItemForm validation messages, "Hide lots/Show lots", "All godowns", Serials column heads and statuses, count status in dialog title. | **[O]** |
| F-29 | P3 | Planning/Forecast | Two overlapping menu entries; Planning menu shows when `ENABLE_REPLENISHMENT` is off. | **[O]** |
| F-30 | P3 | Docs | Implementation record is stale (still says no `reason_code`). | **[O]** |

---

## 1. Products

**1 Purpose.** [O] Catalogue of items: find, add, edit, delete, bulk entry points, filter by category/brand/stock/tax, columns, needs-review queue (bill imports). Users: owner, inventory staff, purchase/sales staff read-only. Primary action: Add/Edit item. Should *not* hold stock corrections after creation (Adjustment) or per-godown rules (Low stock).
**2 UX.** Search + four dropdown filters + two chips + column picker + export + bulk + Add on one row: dense but conventional. "More columns" toggle and the column picker overlap in purpose. Stock chip colours (red/amber/green) are outline chips with number+unit (not colour-only). Item form: core essentials first, tabs for stock/pricing/custom — good. Stock tab hidden on create until "Add opening stock" is pressed — clear.
**3 Cognitive load.** Item form has ~35 fields across 4 tabs; a typical grocery item needs name, SKU, price, GST, unit. Reduce by auto-suggesting SKU (it is required but blank) and defaulting HSN from category. Free-text category/brand with datalist invites typos (server matches case-insensitively, so duplicates only differ by spelling).
**4 Flow.** Menu → list → Add → dialog → Save / Save & New → (second request: opening stock) → list. Edit from row. Delete asks, server refuses used items with a message "Deactivate it instead" — the user must then open Edit and set Inactive (F-19). Back/refresh safe; dialog has unsaved-changes guard (F-011 style) and discard confirm.
**5 Functional.** Present: paging (50), server search, custom-field filters, virtualized table, CSV, loading/empty/error states, retry opening stock. Missing: server-side category/brand/stock filters (done client-side by loading the *whole* catalogue once a filter is opened), bulk edit (price/GST/category), bulk deactivate, duplicate-item merge, item image, supplier/preferred vendor field.
**6 Data/state.** Reads products, stock, low-stock ids. Creates product (+ opening stock via separate calls with stable idempotency keys). States: ACTIVE/INACTIVE, `needs_review`. Risks: partial create (item without opening stock, F-20); stale list after that failure; the stock map is for the current page only.
**7 Business logic.** [O] SKU unique per company (partial unique, case-sensitive?) and barcode unique — a clash surfaces as a generic "duplicate value" message (IntegrityError mapping), not "SKU already used by X". Tracking flags/type/unit locked after movements (good). Service items cannot hold stock. [V] SKU uniqueness case sensitivity; whether inactive items are blocked from new sales/purchases everywhere; HSN length rules by turnover.
**8 Cross-screen.** Price/GST/HSN → Sales, POS offline catalogue (`pos-catalog` returns only ACTIVE), Quotations, labels. Reorder level → Low stock, Planning, Dashboard. Unit/tracking → Adjustment, Counts, Transfers, Serials, Expiry.
**9 Cross-module (HIGH).** GST/HSN (invoices, GSTR), purchase pricing, POS offline cache (changes reach tills only on next catalogue sync), imports (Tally/CSV create products), Shopify mapping. MEDIUM: reports, search. LOW: notifications.
**10 Edge cases.** Name/SKU 255/64 chars; unicode; duplicate SKU with different case; price with 3 decimals (field is 2); batch item with qty but no batch no (lot silently skipped if qty ≤ 0); pasted serial list replaces typed rows; "Save & New" keeps nothing; double click on Save (button disabled while pending); two staff editing same item (last write wins, no version check [V]).
**11 Errors.** Good: field-level focus on first invalid field; HelpErrorAlert. Gaps: duplicate-SKU message generic; opening-stock failure message says item saved but list not refreshed (F-20); delete refusal leaves the user to guess how to deactivate.
**12 Security.** Reads need catalogue permission; writes need manage-inventory (server-enforced, `get_permissions`). Cost fields masked for roles without cost view (`can_see_product_cost`) [O in list cache key]. The list is cached server-side (`cost`/`nocost` variants) — good.
**13 Consistency.** Uses shared DataTable patterns but the Products page builds its own Table + virtualization; Stock page is similar. Many literals are English (F-28).
**14 Accessibility/responsive.** Table region is focusable with label; filters wrap; dialog `maxWidth md` with `sm` row stacks; 4-tab scrollable. Row action buttons (Ledger/Edit/Delete) are text buttons, 3 per row: crowded on mobile.
**15 Automation.** HSN→GST rate autofill exists; add: generate SKU from category+counter; copy-from-existing item; remember last category; barcode auto-generate on save (button exists).
**16 Regression risk — HIGH.** Product schema/validators feed billing, GST, POS, imports, labels. Unit/tracking rules touch every stock screen.
**17 Tests.** Duplicate SKU/barcode; edit item with movements (tracking locked); unit change at zero stock; create batch item with 2 lots then fail second lot → retry; export with each filter on; delete used item; inactive item in POS and in a new invoice; custom-field required; Hindi locale; item with 4,000+ products and "Low" filter.
**18 Problems.** F-18, F-19, F-20, F-21, F-22, F-28 (above) + P3: category typos; three row buttons on mobile.
**19 Top changes.** (1) Server-side filters + filter-aware export. (2) Price sanity checks (MRP ≥ selling price, zero price warning) and clear duplicate-SKU message. (3) Make the delete → deactivate path one click.
**20 Scores.** Purpose 8 · UX 7 · Cognitive load 6 · Flow 7 · Functionality 7 · Business logic 7 · Data/state 6 · Error handling 6 · Integration 8 · Consistency 6 · Accessibility 7 · **Overall 7**.
**Verdict: 🟡 READY WITH FIXES.**

---

## 2. Current Stock

**1 Purpose.** [O] Read view of what is on hand, reserved and available per item (grouped across godowns, expandable by godown/lot), with entry links to Ledger, Adjust, Transfer. Users: store, sales, owner. Not for editing numbers.
**2 UX.** KPI chips (items in stock, out, value), drift warning bar, godown filter, search/custom filters, column picker. Good: actions on the row; red for negative availability. Weak: Name cell holds up to four controls (Show lots, Ledger, Adjust, Transfer) and is sticky on mobile, crowding the key identifier.
**3 Cognitive load.** On hand vs reserved vs available is explained by a tooltip (keyboard-focusable). "Items in stock" counts items, not units (correct for mixed units). Low.
**4 Flow.** Menu/Dashboard → list → row action (ledger/adjust/transfer prefill) → target screen. Return to list via menu (no "back to this filtered view"; filters are not in the URL).
**5 Functional.** Present: server search and godown filter, grouped rows, lot expand, CSV, print, empty/filtered-empty/error. Missing: sort, "zero/negative only" filter, value and cost columns, reorder level column, last movement date, server paging (the whole company's balances load at once, F-22), filters in URL.
**6 Data/state.** Reads `StockBalance` + summary. Creates nothing. Stale: no refresh button or timestamp; relies on other screens invalidating `['stock']`. Concurrency: another user's sale changes numbers silently.
**7 Business logic.** Available = on hand − reserved. Reserved comes from open orders/quotes [V which documents]. KPI value uses the summary report rows narrowed by the same filters; hidden with custom-field filters (honest). Drift flag reads the balance-vs-movements check (good).
**8 Cross-screen.** Reflects every stock write: Adjustment, Counts, Transfers, Expiry write-off, Serials, purchases, sales, returns, manufacturing.
**9 Cross-module (HIGH).** Sales availability and negative-stock policy, route planning free stock, reports, dashboard. MEDIUM: offline POS stock cache.
**10 Edge cases.** 10,000+ rows; item with 5 lots in one godown (row key collision, F-23); negative stock; zero-reserved; item in system in-transit godown (hidden); decimal quantities display rounding; search for SKU with special characters.
**11 Errors.** ErrorState with retry; export failure shows alert. No indication when data is old.
**12 Security.** `CanViewInventorySurfaces` (not VIEWER). Cost value in KPI shown to anyone who can view? The summary value is a cost figure — **[V]** masked for sales-only role. Export gated by `canExport` in UI; **[V]** server.
**13 Consistency.** Own table vs `DataTable`/`PageShell` pattern on other inventory pages; English literals ("All godowns", "Hide lots").
**14 Accessibility.** Region focusable, tooltip icon labelled; colour plus number for state; print/virtualization problem (F-23).
**15 Automation.** Remember last godown; "Adjust" opens prefilled (done); add "needs counting" suggestion from drift flag.
**16 Regression — MEDIUM** (read-only) but it is the screen everyone trusts.
**17 Tests.** Print 300 rows → all printed; filter + export; lots expansion with duplicate keys; negative availability; role without cost view; godown filter then adjust link carries godown.
**18 Problems.** F-22, F-23, F-28; P3: no sort, no URL state.
**19 Top changes.** (1) Real paging/server grouping. (2) Fix print/export to honour what is shown. (3) Add sort + "negative/zero" filter.
**20 Scores.** 8 · 7 · 8 · 7 · 7 · 8 · 7 · 7 · 8 · 6 · 7 · **7**. **Verdict: 🟡.**

---

## 3. Stock Adjustment

**1 Purpose.** [O] Manual correction of a single item's quantity in a godown (add/reduce) with a reason, date and, for lot items, a lot. Users: stock-keeper with manage-inventory; owner approves large ones. Should not be used for counts (Counts), expiry (Expiry), transfers.
**2 UX.** Single card: product, godown, live "current → projected (+value)" banner, lot, add/reduce toggle, quantity, date, reason preset (+custom), Save. Reduce asks for confirmation with before/after. Strong error prevention. Weak: no cost input on Add (valued at valuation cost), value shown only when purchase price > 0.
**3 Cognitive load.** Low-medium; lot logic for reductions defaults to first-expiring lot (helpful).
**4 Flow.** Entry: menu or "Adjust" on a stock row (prefilled) or item form. Save → success/pending/warning notice, form resets, balances refetched. Cancel/back: nothing saved, no draft.
**5 Functional.** Present: idempotency, FEFO default, negative warning, reason codes, date (≤ today). Missing: multi-line adjustment (one item per submit), notes beyond reason, attachment/photo, serial-tracked item handling (serial items are selectable; **[V]** server behaviour for add/reduce without serial numbers), reason "Found stock" exists in API (`FOUND`) but not in the preset list.
**6 Data/state.** Creates an `ADJUSTMENT` stock movement (+ optional GL journal behind flag, + audit entry). States: APPLIED or PENDING (approval). Risks: after PENDING nothing tells the user how to track the approval (no link); partial failure not possible (atomic).
**7 Business logic.** [O] Period lock on the adjustment date; approval when value ≥ ₹10,000 or ≥ 10 % of on-hand (value uses master purchase price, not valuation cost — can disagree with what is booked [V]); BLOCK/WARN negative-stock policy. Approver rule: sole owner auto-approves with "owner exception".
**8 Cross-screen.** Current stock, Low stock, Ledger, Approvals inbox, Dashboard counts, Reports.
**9 Cross-module (HIGH).** Accounting (shrinkage journal when flag on), valuation, approvals, audit log, sales availability.
**10 Edge cases.** Quantity 0.0005 (server 3 decimals); huge quantity; date in a locked period (error, transient — fine); reduce lot that was sold meanwhile; two users adjusting the same item; offline (no offline path); wrong godown default.
**11 Errors.** Server message shown. **F-01:** after a rejection the same idempotency key is reused — retry with the same data replays the old error; with a changed quantity gives 422 "key reused". The user would need to reload.
**12 Security.** Server `CanManageInventory`; page redirects non-managers. Approval bypass exists via other screens (F-03). Cost/value shown to the manager (fine).
**13 Consistency.** Uses react-hook-form (others use useState) and its own card layout; confirm dialog consistent.
**14 Accessibility.** Labelled fields, toggle group, number input; error text under fields.
**15 Automation.** Prefill from row (done); suggest reason from context; allow "set to counted quantity" (target-qty mode) instead of delta.
**16 Regression — HIGH** (every stock number, GL).
**17 Tests.** Reject then retry (changed qty) → must work; approval threshold edge (₹9,999.99 / ₹10,000); batch add with new lot; reduce over available (BLOCK vs WARN company setting); closed period; double click; serial item; Hindi locale; approval accepted → stock changes once.
**18 Problems.** **F-01**, F-03 (applies here as the only guarded path), F-22, stale record F-30; P3: `FOUND` reason missing; no link to the pending approval.
**19 Top changes.** (1) New idempotency key per attempt after any failure (or per distinct body). (2) Show "view approval" link on PENDING. (3) Single shared "post stock loss" path for all screens.
**20 Scores.** 8 · 8 · 7 · 7 · 7 · 7 · 7 · 5 · 7 · 7 · 8 · **7**. **Verdict: 🟡** (🔴 until F-01 is fixed if users hit rejections often).

---

## 4. Low Stock

**1 Purpose.** [O] Worklist of items at or below reorder level ("Low") and zero-stock items with no rule ("Out of stock"), with link to Purchase planning and per-godown rules. Users: buyer, owner.
**2 UX.** Two tabs with counts, search, shortfall sort, per-row "Reorder" and one primary "Plan purchases". Clear. Per-godown rules table sits below the list — discoverable.
**3 Cognitive load.** Low. "All godowns" vs a named godown explained by column.
**4 Flow.** Dashboard tile/menu → list → Reorder row (prefills a PO with product and quantity — the editor reads `product`, `qty` [O]) or Plan purchases (select all) → Planning → draft POs.
**5 Functional.** Present: search, sort, tabs, empty states, rule add. Missing: supplier column, sort choice, ignore/snooze item, bulk reorder from selection (only "all"), edit/delete of an existing godown rule (the rules table is read-only; a rule is added via dialog; **[V]** whether the create endpoint upserts).
**6 Data/state.** Reads the single `low_stock_rows` definition. Writes `WarehouseReorderLevel`. Staleness: query keyed `['low-stock','all']`; Adjust/Count/Transfers invalidate it.
**7 Business logic.** [O] Active, stock-tracked items only; company total vs reorder level unless a godown has its own rule; if *all* godowns have rules the company total is not checked; never-stocked items with a rule are low at zero. Available excludes reserved. Company total includes every godown including stock still in transit [V intent].
**8 Cross-screen.** Dashboard tile, Products "Low" filter, Planning, Forecast, Alerts API, insights, balance filter — all one service.
**9 Cross-module (HIGH).** Purchases (draft POs), notifications/insights, dashboard.
**10 Edge cases.** Negative stock (shows as low with negative available); item with rule 0 (never low); duplicates (godown row and company row for the same item); 5,000 low items (no paging); inactive item (excluded).
**11 Errors.** Loading/error/empty handled.
**12 Security.** `CanViewInventorySurfaces`; rule creation server `CanManageInventory`, but the **Add rule button is visible to everyone who can open the page** (disabled only by subscription state) [O]; a read-only user gets a 403 after filling the dialog.
**13 Consistency.** Mixes `DataTable` (rules) and MUI Table (list); chip tabs same as Forecast/Expiry (consistent).
**14 Accessibility.** Tab chips are clickable chips (role/keyboard semantics weak: they are not tabs); colour red for available plus number.
**15 Automation.** Suggest reorder level from sales (exists on item form); show supplier and last price; one-click "add to draft PO".
**16 Regression — MEDIUM** (shared definition: changes move 7 surfaces at once).
**17 Tests.** Rule on one godown only; all godowns with rules; never-stocked with rule; reserved stock; role without manage rights (hide Add rule); in-transit stock.
**18 Problems.** F-27, plus P3: Add-rule visible to non-managers; chips not real tabs; no supplier.
**19 Top changes.** (1) Hide/disable rule actions by permission. (2) Fix chip text on the Out tab. (3) Show supplier and last price to make Reorder one decision.
**20 Scores.** 9 · 8 · 8 · 8 · 8 · 8 · 8 · 8 · 9 · 7 · 7 · **8**. **Verdict: 🟢 READY** (minor polish only).

---

## 5. Purchase Planning

**1 Purpose.** [O] Turn low stock into draft purchase orders (per supplier) or inter-godown transfers, with quantity editing and supplier override. Users: buyer.
**2 UX.** Filters (godown, supplier, urgency days), select rows, preview dialog, "needs supplier" assignment, transfer links, notice and draft links. Better than before (preview, edits, overrides).
**3 Cognitive load.** Medium: rows mix "buy" and "transfer"; scope godown/company explained in rows [I]. Suggested quantity logic is not explained on screen (lead time, safety stock, velocity).
**4 Flow.** Low stock → Plan purchases → preselect → Create drafts → preview → POs created → one PO opens, several go to PO list. Transfer rows → Transfers prefilled. Recovery: user can edit drafts later.
**5 Functional.** Present: urgency filter, qty edit, supplier assign, covered-by-orders note, replenishment-off message. Missing: price/amount estimate per supplier, minimum order quantity/pack size, lead time column, per-row exclude reason, history.
**6 Data/state.** Reads low rows, drafts, last suppliers. Creates `PurchaseOrder` DRAFTs (one per supplier). States: draft only. Risks: duplicate drafts (F-16), stale plan after another user creates drafts (invalidated only for this user).
**7 Business logic.** [O] "On order" = quantity on DRAFT POs only; whole-unit rounding up unless fractional UQC; unit price = master purchase price; days-to-stockout = available ÷ daily velocity; transfer suggested when any other godown is above its own reorder level (not capped by surplus, F-15); godown rows use the old gross 14-day velocity (F-14).
**8 Cross-screen.** Purchase orders list/editor, Transfers, Low stock, Forecast.
**9 Cross-module (HIGH).** Purchases (POs, supplier ledger once sent), Inventory transfers.
**10 Edge cases.** Supplier missing; item sold only in returns; fractional-unit item; supplier deleted; two buyers creating drafts at once; urgency filter with items that never sold (days = none → excluded).
**11 Errors.** Server errors surfaced; empty-plan POST returns a bare 404 "Not found" (P3). Create fails atomically (transaction) — good.
**12 Security.** GET `CanViewInventorySurfaces` (fixed); POST requires `CanCreatePurchases` + subscription gate. Plan rows posted from the browser are trusted for product/qty/supplier but re-validated against company. Price comes from the server product, not the client — good.
**13 Consistency.** Own layout; chip/filters like others; English/Hindi mix low.
**14 Accessibility.** Region labelled; checkboxes; wide table scrolls.
**15 Automation.** Auto-select urgent rows; remember supplier per item; group by supplier min order value; schedule weekly plan.
**16 Regression — HIGH** (PO creation, low-stock definition, velocity).
**17 Tests.** Create twice; draft PO then plan again (covered); cancelled PO frees demand; unposted converted PO; transfer donor with small surplus; fractional item; supplier override; role without create-purchases sees no buttons.
**18 Problems.** F-14, F-15, F-16, F-29 + P3 bare 404.
**19 Top changes.** (1) Use the one velocity everywhere; cap transfers by donor surplus. (2) Count open POs correctly (DRAFT + sent/unposted converted) and add a duplicate guard. (3) Explain the suggestion (formula tooltip, lead time).
**20 Scores.** 8 · 7 · 6 · 8 · 8 · 6 · 7 · 7 · 8 · 7 · 7 · **7**. **Verdict: 🟡.**

---

## 6. Demand Forecast

**1 Purpose.** [O] Show how fast items sell and how much to buy to cover 30 days. Users: buyer/owner. Should not be a second planning screen.
**2 UX.** Two tabs (needs action/all), one table with sold qty, daily rate, available, on order, cover days, suggested qty, supplier, method, action link.
**3 Cognitive load.** Medium: ten columns; method column shows an enum label plus window days ("· 30").
**4 Flow.** Menu or Planning link → table → "Plan purchase" (prefilled PO). Dead end otherwise.
**5 Functional.** Present: needs-action tab, supplier. Missing: chart/trend, per-godown view, date window choice, filter/search, export, overstock/dead-stock view, seasonality.
**6 Data/state.** Reads movements, balances, drafts. Writes nothing. Stale until reload.
**7 Business logic.** [O] 30-day mean net of returns; cover target 30 days; reorder level = 14 days; whole-unit ceil. Includes any product that sold (inactive/non-stock included, F-17); stock-out days count as zero demand; ignores promotions and lead time.
**8 Cross-screen.** Item form (suggested reorder level), Planning, PO editor.
**9 Cross-module (MEDIUM).** Purchases, item master. LOW: insights.
**10 Edge cases.** New item (1 sale) → huge daily rate swing; bulk one-off sale; return exceeding sales (excluded); item sold only via challan (movement type) [V]; very high volume.
**11 Errors.** Loading/error/empty fine.
**12 Security.** `CanViewInventorySurfaces`. Sales velocity is commercially sensitive; the sales-only role sees all items' velocity [V intent].
**13 Consistency.** Matches Low stock pattern; English "Method".
**14 Accessibility.** Table region labelled; no colour-only signals (no signals at all).
**15 Automation.** Auto-flag fast movers stocking out; seasonal index; ABC class.
**16 Regression — MEDIUM.**
**17 Tests.** Item out of stock 15/30 days; inactive item; returns; fractional unit; zero sales; many products performance.
**18 Problems.** F-17, F-14 (consistency), F-29.
**19 Top changes.** (1) Exclude inactive/non-stock; compute demand on in-stock days. (2) Add search/filter/export. (3) Merge with Planning or make it clearly "insight only".
**20 Scores.** 6 · 6 · 7 · 6 · 5 · 6 · 7 · 7 · 7 · 7 · 7 · **6**. **Verdict: 🟡.**

---

## 7. Print Labels

**1 Purpose.** [O] Print barcode shelf labels (browser print) or download ZPL for thermal printers. Users: store staff. Entry also from a purchase bill (`?items=`).
**2 UX.** Add product → rows with copies/lot → on-screen label preview sheet → Print all. Size choice (3). Clear, WYSIWYG. MRP printed when set (good, falls back to selling price).
**3 Cognitive load.** Low.
**4 Flow.** Menu / purchase bill / item form → build list → Print (browser dialog) or ZPL per row.
**5 Functional.** Present: copies cap 200, lot picker, bill prefill, barcode fallback to SKU, safe failure when the code cannot be encoded. Missing: multi-up sheet templates (A4 sticker grids), custom size, choose fields (price/MRP/date), save list, print history, generate-missing-barcodes, ZPL for all rows at once.
**6 Data/state.** Reads products/lots; creates nothing. State is page memory — lost on refresh (no warning).
**7 Business logic.** Price = MRP if > 0 (Legal Metrology expectation [V] for packaged goods; also needs net quantity, packing date, manufacturer for pre-packed goods). ZPL has name + code only (F-24). SKU-as-barcode only works if scan lookup accepts SKU [V].
**8 Cross-screen.** Purchase bill → labels; Item form barcode generate/print.
**9 Cross-module (LOW-MEDIUM).** Product master, purchases link.
**10 Edge cases.** Name > 40 chars (ZPL truncated); `^`/`~` in names (replaced); barcode chars outside CODE128 (no barcode, no warning on the label list); 200 copies × many rows (DOM weight); lot expired; product without MRP.
**11 Errors.** Alerts for load/download failure; invalid barcode silent (the label shows no barcode but looks printable).
**12 Security.** ZPL endpoint `CanViewInventorySurfaces`; menu needs manage-inventory (mismatch, harmless). Output escaping done for ZPL; browser labels are React-rendered (safe).
**13 Consistency.** Uses PageTitle/Stack (not PageShell); fine.
**14 Accessibility.** Controls labelled; printed output not an a11y concern; icon delete labelled.
**15 Automation.** Auto-add items received on the last bill (exists via link); print on GRN; remember size.
**16 Regression — LOW.**
**17 Tests.** Print 3 rows × 5 copies; batch label; item without barcode; ZPL parity with browser label; long Hindi name; 200 copies; print preview shows no app chrome (print CSS hides header/nav [O]).
**18 Problems.** F-24 + P3: unsupported-barcode warning, no persistence of list.
**19 Top changes.** (1) ZPL carries price/lot/expiry/size. (2) Sticker-sheet templates. (3) Warn when a barcode cannot be encoded.
**20 Scores.** 8 · 8 · 8 · 7 · 6 · 7 · 7 · 6 · 7 · 7 · 7 · **7**. **Verdict: 🟡.**

---

## 8. Godowns

**1 Purpose.** [O] Manage storage locations: add, edit name/code, activate/deactivate, make default, delete. Users: owner/inventory manager. System in-transit godown is hidden and unreachable [O server].
**2 UX.** Filter chips (active/off/all with counts), table with default/status chips, actions per row, confirm dialogs. Simple.
**3 Cognitive load.** Low. Consequences of "make default" are only in the confirm text.
**4 Flow.** List → Add/Edit dialog → refresh. Deactivate/delete refused by server when stock or history exists (`assert_can_deactivate/delete_warehouse`) with a message.
**5 Functional.** Present: code auto-from-name, default invariants (exactly one active default enforced after every write), deactivate/reactivate. Missing: stock summary per godown (items/value), address/contact fields (serializer has them, dialog does not), who uses it (counts/transfers pending), merge godowns.
**6 Data/state.** Writes `Warehouse`. Invariants good (B8-030). Concurrency: two admins toggling default — server re-asserts.
**7 Business logic.** [O] Unique code per company (conflict → generic duplicate message); first godown becomes default; default cannot be deactivated or deleted (UI hides buttons). Default godown is the destination for company-wide low items in Planning and the fallback for stock writes with no godown.
**8 Cross-screen.** Every stock screen's dropdowns (inactive ones disappear from them), POS, routes.
**9 Cross-module (MEDIUM).** Sales/POS default godown, route planning, purchase receiving, GST (godown address as place of supply if used [V]).
**10 Edge cases.** Name with spaces/Hindi; code collisions from `codeFromName`; deactivate with in-transit transfer [V]; delete last-but-one godown; rename affects printed documents' history (names resolved live [V]).
**11 Errors.** HelpErrorAlert; server refusal text shown.
**12 Security.** Mutations `CanManageInventory`; list `CanViewWarehouseSurfaces`. Buttons are visible to anyone who opens the page; route gated by menu predicate.
**13 Consistency.** Uses shared PageShell/DataTable; English literals in a few labels (F-28).
**14 Accessibility.** Chips are buttons (group labelled); normal table.
**15 Automation.** None needed; maybe prefill address from company.
**16 Regression — MEDIUM.**
**17 Tests.** Deactivate with stock/pending transfer/open count; delete with history; make default then low-stock destination; duplicate code; Hindi name; role without manage rights.
**18 Problems.** P3: generic duplicate-code message; address/contact not editable; no stock summary.
**19 Top changes.** (1) Show stock and open documents per godown. (2) Friendly duplicate-code message. (3) Edit address/contact.
**20 Scores.** 9 · 8 · 9 · 8 · 7 · 9 · 8 · 8 · 8 · 8 · 8 · **8**. **Verdict: 🟢 READY.**

---

## 9. Stock Counts

**1 Purpose.** [O] Physical stock-take: create a session for a godown (optionally blind), enter counts, skip lines, review variance, post adjustments. Users: stock-keeper (count), owner/manager (review/post).
**2 UX.** List of sessions → dialog with count lines, scan field, "Count equals system", "Skip all uncounted", Save, Review → Post. Review shows variance value and recheck ticks. Strong flow; blind mode hides expected quantity. Weak: all inside one tall dialog; lines unsorted by rack; no search within lines.
**3 Cognitive load.** Medium-high for large godowns (hundreds of lines, not virtualized by design for printing).
**4 Flow.** New count → count → Save (manual) → Review → Post (confirm with totals) → close. Cancel allowed. Print sheet available. Offline post queues a request. Recovery: conflicts modal, KEEP_SERVER / KEEP_LOCAL.
**5 Functional.** Present: add found item, partial counts (skip), scan, review summary. Missing: auto-save, line search/filter/sort by rack or category, count by category/aisle (cycle count), recount request/assignment, multiple counters, variance threshold approval, count date picker, history/compare sessions.
**6 Data/state.** Session DRAFT→COUNTED→POSTED/CANCELLED; lines hold system snapshot. Posting creates one ADJUSTMENT per variance line, audit, optional journal. Risks: F-06 overwrite, F-09, stale system snapshot, offline queue state lost on reload (F-07).
**7 Business logic.** [O] Lines created for `on_hand > 0` rows only; recheck at > 5 units or ≥ ₹10,000 (UI-enforced only, F-04); drift compares live quantity to the snapshot and forces a single global choice (F-05); blind session hides system quantity until review; locked tracking; period gate on count date; held_for_review flag does not stop posting.
**8 Cross-screen.** Current stock, Low stock, Ledger, Approvals (not used), Dashboard.
**9 Cross-module (HIGH).** Accounting (shrinkage journal), valuation, sales availability, audit, offline queue (PWA outbox).
**10 Edge cases.** Sale during count; two counters; item counted twice via scan; lot items scanned; decimal units; negative counted quantity typed (client allows, server field has no validator, add-line rejects negative [V]); 3,000-line dialog; browser closed mid-count (unsaved guard warns only on in-app close/nav).
**11 Errors.** Conflict modal is good; generic errors in dialog. **F-01:** fixed key `stock-count-{id}` — a deterministic rejection (e.g. negative-stock block while posting a reduction) is replayed even after fixing stock.
**12 Security.** `CanManageInventory` everywhere. Posting needs no second person (F-03/F-04). Count variance values visible to all managers.
**13 Consistency.** Different shell from Adjustment; status shown raw in the dialog title (F-28).
**14 Accessibility.** Inputs labelled; long dialog scroll; scan field keyboard-friendly; colour in review rows plus signs.
**15 Automation.** Auto-save every N seconds; sort by rack; cycle-count suggestions (ABC, high-value, recently adjusted); pre-fill by barcode scan with lot prompt.
**16 Regression — HIGH.**
**17 Tests.** Sale mid-count then each resolution; two counters saving; scan batch item; post twice; cancel vs post race (Postgres); offline post then reload; negative stock item on sheet; recheck bypass via API; large godown render.
**18 Problems.** F-01, F-03–F-09.
**19 Top changes.** (1) Per-line drift choice and server-enforced recheck/approval. (2) Auto-save + line-level save (no overwrite of other counters). (3) Success confirmation and visible pending state.
**20 Scores.** 8 · 7 · 6 · 8 · 7 · 6 · 6 · 6 · 7 · 6 · 6 · **6**. **Verdict: 🟡** (do not use "Count equals system" or KEEP_LOCAL on a trading godown until fixed).

---

## 10. Stock Transfers

**1 Purpose.** [O] Move stock between godowns with three stages: draft → dispatch (in transit) → receive (with short-receipt reasons); cancel rules. Users: stock-keepers; receiver at destination.
**2 UX.** List with items summary and status, per-row actions by status/role, dialogs for create, detail, receive. Queued chip for offline dispatch (present now). Available-at-source hint per line, lot defaulted to earliest expiry.
**3 Cognitive load.** Medium: separate Create, Dispatch, Receive steps; reasonable and honest.
**4 Flow.** Current stock/Planning → prefilled form → Create draft → Dispatch (confirm) → destination Receive → completed. Cancel at each stage; completed cancel owner/manager.
**5 Functional.** Present: serial numbers per line, partial receipt with reasons, offline dispatch, prefill via URL. Missing: transfer value, in-transit dashboard, receiver-specific permission/godown assignment, print challan/transfer note [V], edit draft after creation, search/filter on list, notes entry in the create dialog (column shows notes but form has no field).
**6 Data/state.** Draft (no stock effect) → DISPATCHED (stock moved to the system in-transit godown) → COMPLETED (landed). Locks and period gate in service. Risks: F-12 duplicate drafts; F-01 stuck dispatch; offline queue vs online click race (UI hides actions on queued rows).
**7 Business logic.** [O] Source ≠ destination; active godowns only; lot required for batch items; serial count must equal quantity; negative-stock policy on dispatch (warn/block); cancel of completed transfers restricted by role; period gate on cancel. Shortage handling accounting unknown (F-13).
**8 Cross-screen.** Current stock, Ledger, Low stock/Planning (donor suggestions), route planning ("goods to check in").
**9 Cross-module (MEDIUM-HIGH).** Sales routes/orders (free stock per godown), accounting (none unless shortage written off), audit, offline outbox.
**10 Edge cases.** Receive more than sent (blocked client-side); lot expired in transit; destination godown deactivated while in transit; serial moved/sold meanwhile; two receivers; dispatch with insufficient stock; deep-link `lines` JSON tampered.
**11 Errors.** Errors in a banner or inside the receive dialog; no per-line server errors. **F-01** for dispatch/receive keys.
**12 Security.** `CanManageInventory` for all actions; no distinction between sender and receiver roles. Cancel-after-receive restricted (good).
**13 Consistency.** Uses PageShell/DataTable (matches Godowns/Counts).
**14 Accessibility.** Standard dialogs/inputs; chips show text; action buttons labelled.
**15 Automation.** Receive-all in one click (default values are prefilled, good); auto-create transfer from planning (exists); barcode scan to receive.
**16 Regression — HIGH** (stock, serials, offline queue, invariants `transfer_pairs_net_zero`).
**17 Tests.** Dispatch insufficient → add stock → dispatch again; double create; short receipt; cancel at each stage by each role; serial item transfer; lot expiry in transit; offline dispatch then online click; destination deactivated.
**18 Problems.** F-01, F-12, F-13, P3 no filter/search, no notes field.
**19 Top changes.** (1) Fresh key per attempt. (2) Idempotent create + success feedback. (3) Explain shortage treatment and add a "goods in transit" view.
**20 Scores.** 8 · 8 · 7 · 8 · 8 · 8 · 8 · 6 · 8 · 8 · 7 · **8**. **Verdict: 🟡.**

---

## 11. Expiry Alerts

**1 Purpose.** [O] See lots expired or expiring within 7/30/60/90 days, then sell first, return to supplier, or write off. Users: owner/inventory/pharmacy staff.
**2 UX.** Day chips, godown filter, expired/expiring tabs (auto-opens the non-empty one), select-all, multi-write-off dialog with total value and a warning for not-yet-expired lots. Good.
**3 Cognitive load.** Low-medium.
**4 Flow.** Menu/dashboard → list → Sell first (Quick Entry) / Return to supplier (blank form, F-11) / Write off (dialog) → result alert.
**5 Functional.** Present: free quantity = on hand less reserved, partial quantities, reason EXPIRED/DAMAGED, daily email/bands job (server). Missing: discount/clearance suggestion, return prefill, per-lot supplier, lot trace to purchase bill, export, reserved-stock resolution (cannot write off held stock; no link to the order holding it).
**6 Data/state.** Writes ADJUSTMENT movements (reason EXPIRED/DAMAGED) + audit + optional journal. Not idempotent (F-10). States per row not tracked ("written off" only via stock).
**7 Business logic.** [O] Write-off limited to available; date = today; period gate on today; no approval (F-03); unit cost used for value; reason restricted. [V] Expired-lot sales blocked on invoices.
**8 Cross-screen.** Current stock, Low stock, Ledger, Quick Entry, Purchase returns, Dashboard.
**9 Cross-module (HIGH).** Accounting (loss), pharmacy compliance (drug schedule), returns, notifications/email.
**10 Edge cases.** Lot with reserved stock; written off twice; expiry date missing (rows need expiry [V]); timezone day boundary; 5,000 lots; negative stock lot.
**11 Errors.** Partial failures listed per row (good) but retry hazard (F-10); invalid input server errors (F-10).
**12 Security.** GET view permission; POST manage-inventory; costs masked for roles without cost visibility [O].
**13 Consistency.** Chip tabs/filters like Low stock; spinner replaces page on filter change (F-11).
**14 Accessibility.** Select-all and row checkboxes labelled; colour chips carry text "x days ago/left".
**15 Automation.** Auto-propose write-off at expiry; clearance price suggestions; supplier return pre-fill; weekly digest.
**16 Regression — MEDIUM.**
**17 Tests.** Write off 3 rows with one failure then retry; partial quantity then retry; reserved stock; role without cost view; DAMAGED reason; period lock; lot already zero; 7/30/60/90 filters; Hindi.
**18 Problems.** F-03, F-10, F-11.
**19 Top changes.** (1) Idempotent per-row write-off + remove successes from the dialog. (2) Prefilled supplier return. (3) Approval/threshold parity with Adjustment.
**20 Scores.** 8 · 7 · 7 · 7 · 7 · 7 · 7 · 6 · 7 · 7 · 8 · **7**. **Verdict: 🟡.**

---

## 12. Serial Numbers

**1 Purpose.** [O] Look up serial-tracked units and their status, scrap or return them. Users: service/warehouse staff, sales (lookup).
**2 UX.** Search + status filter + table; row actions by status; "View sale" for SOLD. Minimal. Columns and statuses are raw English enums (F-28).
**3 Cognitive load.** Low, but consequences of actions are only explained in confirm text.
**4 Flow.** Search a serial → see product/godown/status → action with confirm → refresh. No detail page.
**5 Functional.** Present: search, filter, sale document link, scrap, return. Missing: serial history (purchase, transfers, sale, customer, warranty), product/godown filters, import of serial lists, bulk scrap, export, paging (virtualized, whole list loaded).
**6 Data/state.** Statuses AVAILABLE/SOLD/RETURNED/SCRAPPED. Transitions whitelisted; SOLD→AVAILABLE posts a stock return (F-02); scrap posts −1 adjustment and journal. Not locked/idempotent (F-25).
**7 Business logic.** [O] Scrap needs on-hand ≥ 1 for AVAILABLE; SOLD can come back only via this action (no document); scrapped is final; warehouse can be changed on transition to any company godown (including system godown, filter lacks `is_system` exclusion [O]). [V] GL effect of the manual return.
**8 Cross-screen.** Invoices/challans (View sale), Current stock, Ledger, Low stock.
**9 Cross-module (HIGH).** Sales (returns/credit notes/GST), warranty/service [V], accounting.
**10 Edge cases.** Serial typed with spaces/case; duplicate serial across products; serial scrapped then re-received (allow_reactivate_scrap path exists on receipt); concurrent actions; 100k serials.
**11 Errors.** Error banner from server; "no document" message when a sale cannot be traced.
**12 Security.** List/retrieve for sales or inventory users; writes manage-inventory; scrap without approval (F-03).
**13 Consistency.** Uses DataTable/PageShell; labels not translated.
**14 Accessibility.** Standard.
**15 Automation.** Scan to search; auto-link to warranty; bulk receive serials via paste (exists on item form).
**16 Regression — MEDIUM-HIGH.**
**17 Tests.** SOLD→Return: invoice unchanged, stock +1, GL; double click; concurrent returns; scrap at zero on-hand; View sale for invoice and challan; search partial; role matrix; 50k rows scroll.
**18 Problems.** F-02, F-03, F-25, F-28.
**19 Top changes.** (1) Replace manual "return" with a link into the sales-return/credit-note flow. (2) Add serial history. (3) Lock + idempotency + approval on scrap.
**20 Scores.** 7 · 7 · 8 · 7 · 5 · 5 · 6 · 6 · 6 · 6 · 7 · **6**. **Verdict: 🟡** (hide "Return" until F-02 is fixed).

---

## 13. Module-level summary

**Cross-module impact (all HIGH unless noted):** Accounting (shrinkage journal only behind `ACCOUNTING_POST_STOCK_ADJUSTMENTS`, default off, needs CA sign-off), Sales/POS availability and negative-stock policy, Purchases (draft POs, bills, GRN), Reports/Dashboard (low stock, valuation), Approvals (only Adjustment uses it), Audit log (adjustment, count, serial and write-off log; transfers via document events), Offline outbox (counts, transfers), Imports/Tally/Shopify (write stock outside these screens, MEDIUM), Manufacturing (MEDIUM).

**What is good and should be kept as the model for the rest of the product:** row locks and period gates in services; idempotent posts; tracking lock after movements; FEFO defaults; blind count; live projected balance on Adjustment; one low-stock definition; plain-language empty/error states; destructive-action confirms that state before/after quantities.

**The three changes with the greatest payoff**
1. **One stock-loss path** (F-03, F-04, F-10): adjustment, expiry write-off, count post and serial scrap all go through the same function with approval, idempotency, period gate, reason code and journal. *Correctness + control.*
2. **Retry that actually works** (F-01, F-12, F-10): new idempotency key per attempt (or per distinct body) on every stock write; idempotent creates; clear success/pending feedback (F-07). *User outcome: no stuck documents, no duplicates.*
3. **Counts that survive a busy shop** (F-05, F-06, F-08, F-09): per-line drift choice, auto-save and line-level save, lot-aware scanning, negative-stock lines on the sheet. *Business value: believable stock numbers.*

**Scores (module)**

| Dimension | Score |
|---|---:|
| Purpose clarity | 8 |
| UX | 7 |
| Cognitive load | 7 |
| Flow | 7 |
| Functionality | 7 |
| Business logic | 6 |
| Data/state handling | 7 |
| Error handling | 6 |
| Cross-product integration | 7 |
| Consistency | 6 |
| Accessibility | 7 |
| **Overall** | **7** |

## FINAL VERDICT
🟡 **READY WITH FIXES.** Godowns and Low stock are ready. Every other screen is usable but carries at least one P1/P2 defect. Fix before relying on it for money: F-01 (stuck retries), F-02 (serial return without a document), F-03/F-04 (approval parity), F-05/F-06 (count correctness). Also get the CA decision on GL posting of stock losses, and run the Postgres concurrency tests and a browser/role-matrix pass that this review could not do.
