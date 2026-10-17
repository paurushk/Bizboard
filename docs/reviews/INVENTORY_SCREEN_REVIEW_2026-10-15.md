# Inventory module — screen, flow and product-impact review

Date: 2026-10-15 · Scope: every screen under the Inventory nav group, with the backend they call.

**Status 2026-10-16:** all findings were worked through in the working tree (uncommitted). See section 8 of [INVENTORY_REVIEW_IMPLEMENTATION_PLAN.md](../INVENTORY_REVIEW_IMPLEMENTATION_PLAN.md) for what was built, the decisions taken and the gaps left on purpose.

**Evidence labels:** **[O]** Observed in code · **[I]** Inferred · **[U]** Unknown · **[V]** Needs verification (running app, accounting, or business rule).

**How this was done.** I read the page source and the backing API/service code. I did not run the app, so nothing here is based on visual rendering, performance or real data. Not read in full: `ItemFormDialog.tsx` (1,356 lines), `PurchasePlanningPage`, `InventoryReportPage`, and `planning.py` / `forecast.py` internals. Those are called out as gaps in section 21.

Screens covered:

| # | Screen | Route | File |
|---|---|---|---|
| 1 | Products (items) | `/inventory/products` | `pages/inventory/ProductsPage.tsx` + `ItemFormDialog.tsx` |
| 2 | Current stock | `/inventory/stock` | `CurrentStockPage.tsx` |
| 3 | Low stock | `/inventory/low-stock` | `LowStockPage.tsx` |
| 4 | Purchase planning | `/inventory/purchase-planning` | `PurchasePlanningPage.tsx` (not read) |
| 5 | Demand forecast | `/inventory/demand-forecast` | `DemandForecastPage.tsx` |
| 6 | Expiry alerts | `/inventory/expiry-alerts` | `phase/InventoryPhasePages.tsx` |
| 7 | Stock adjustment | `/inventory/adjustments` | `StockAdjustmentPage.tsx` |
| 8 | Godowns (warehouses) | `/inventory/warehouses` | `phase/InventoryPhasePages.tsx` |
| 9 | Stock counts + per-godown reorder | `/inventory/stock-counts` | `StockCountPage.tsx` |
| 10 | Stock transfers | `/inventory/transfers` | `phase/InventoryPhasePages.tsx` |
| 11 | Serial numbers | `/inventory/serials` | `phase/InventoryPhasePages.tsx` |
| 12 | Barcode labels | `/inventory/labels` | `LabelPrintPage.tsx` |
| 13 | Stock valuation / inventory report | `/reports/stock-valuation`, `/reports/inventory` | `pages/reports/*` |

---

## 1. Module purpose and who uses it

- **[O]** A godown-aware stock ledger for a trading/distribution business: items, balances per (product × godown × batch), manual adjustments, physical counts, inter-godown transfers with an "in transit" stage, expiry, serials, labels, valuation.
- **[O]** Two permission tiers on the routes: *view* surfaces (`canViewInventorySurfaces`: products, stock, low stock, planning, forecast, expiry) and *act* surfaces (`canAdjustInventory`: adjustments, godowns, counts, transfers, serials, labels).
- **[I]** Users: owner/admin (valuation, adjustments), a stock-keeper/godown person (counts, transfers, labels, expiry), a buyer (low stock, planning, forecast). The stock-keeper is the one most likely to be on a phone or a shared PC at a godown, which matters for several findings below.
- **Purpose clarity:** good for Products / Current stock / Low stock. Weak for Demand forecast (no stated decision it supports) and for Serials (looks like a status editor, not a lookup).

---

## 2. Findings that matter most (read this first)

| Pri | # | Problem | Evidence | Why it matters |
|---|---|---|---|---|
| **P0** | 1 | **Stock adjustment pending approval is shown as "recorded successfully".** The API returns HTTP 202 `{status: PENDING, approval_id}` when a second approver is needed; `createStockAdjustment` returns `void` and the page's `onSuccess` always shows the success banner and resets the form. | **[O]** `backend/inventory/views.py:306` vs `web/src/api/legacy/inventory.ts:66`, `StockAdjustmentPage.tsx:123` | The user believes stock changed; it did not. Next count or sale is wrong, and nobody is told an approval is waiting. Negative-stock `warnings` in the response are also discarded. |
| **P0** | 2 | **Serials: "Mark sold" is offered for AVAILABLE serials but the backend rejects it.** UI maps AVAILABLE→SOLD, SOLD→RETURNED, RETURNED→SCRAPPED. Backend allows AVAILABLE→{SCRAPPED} only. | **[O]** `InventoryPhasePages.tsx:605` vs `views.py:667` | The primary action on the most common row always returns "Invalid serial status transition". The one legitimate action for an AVAILABLE serial (scrap) is unreachable from the UI. Marking sold by hand would also bypass invoice/COGS — it should not exist. |
| **P0/V** | 3 | **No GL posting found for manual adjustments, stock-count variances, expiry write-offs, or serial scrap.** Only opening stock (`post_opening_stock`) and sales-return scrap (Dr 5450 / Cr 1400) post journals. `AdjustmentView` has a comment saying adjustments hit the GL, but no call exists. | **[O]** grep of `backend/accounting`, `inventory/services.py`; **[V]** there may be a signal/batch job I did not find | If true, the stock valuation report and the Inventory control account on the balance sheet drift apart with every shrinkage, and write-offs never reach P&L. Needs an accountant-level check (the project already has CA sign-off items open for other modules). |
| **P1** | 4 | **Stock count has no variance review before posting.** The `review` endpoint exists; the UI never calls it. "System" qty is only shown once the count is POSTED. The user confirms "Post variances" without seeing a single variance. | **[O]** `StockCountPage.tsx:352-356`, `views.py:871` | The final, stock-changing step is blind. Large shrinkage can be posted by a typo (e.g. 100 for 10). |
| **P1** | 5 | **Stock count cannot record found-but-not-in-system stock, and cannot be partial.** Lines are auto-built from balances with `on_hand > 0`; the UI has no "add line"; posting requires every line counted. | **[O]** `serializers.py:398`, `views.py:892` | A product physically present but at 0 in the system can't be counted. A large godown can't be counted in sections (all-or-nothing). |
| **P1** | 6 | **"Reorder item" on Low stock goes to `/purchases/new?productId=…` but the new-purchase page doesn't read that param.** The forecast page uses a different param (`/purchases/orders/new?product=&qty=`, which *is* read). | **[O]** `LowStockPage.tsx:61`; `NewPurchasePage.tsx` only reads `location.state` | The main call-to-action on the buyer's alert screen lands on a blank bill. |
| **P1** | 7 | **Low stock list hides which godown.** Rows can be per-godown (override) or company-wide totals, but there is no godown column and no sort/filter/search. | **[O]** `LowStockPage.tsx:36-43`; `views.py:56-123` | "Rice 5 below reorder" – in which godown? Transfer vs purchase is a different decision. |
| **P1** | 8 | **Transfer list shows no products or quantities.** Columns: number, from, to, status, notes. Create dialog only builds a single-line transfer (multi-line only via planning deep-link). | **[O]** `InventoryPhasePages.tsx:316-322, 215-224` | You cannot see what is in transit. Stock-keeper has to open the DB/report to know what a "DISPATCHED" transfer contains. |
| **P1** | 9 | **Transfer lifecycle gaps in the UI.** DRAFT has no cancel/delete. DISPATCHED has no cancel and no **partial receive** (backend supports `receipts[]` with shortage reason; UI sends none). Cancel is only offered on COMPLETED (the most destructive stage). | **[O]** `InventoryPhasePages.tsx:323-340`, `services.py:1594-1603` | A wrong draft stays forever. Short deliveries can't be recorded, so receive always books the full dispatched qty at destination. Stock "in transit" can get stranded. |
| **P1** | 10 | **Offline queue gives no feedback.** Completing a transfer or posting a count while offline returns `{offline:true}`; transfer `onSuccess` ignores it, row stays DRAFT, no message. Counts show a counter in an info bar but the dialog just closes. | **[O]** `InventoryPhasePages.tsx:239-268`, `StockCountPage.tsx:133-140` | User retries, double-taps, or assumes it failed. Idempotency keys protect the server, but the user can't tell. |
| **P2** | 11 | Stock adjustment quantity is clamped with `Math.max(1, n)` — can't enter 0.5 kg or 0.25 m; clearing the field snaps to 1. | **[O]** `StockAdjustmentPage.tsx:356` | Wrong for fractional units. |
| **P2** | 12 | Adjustment "current recorded balance" uses the **first** stock row for product+godown, not the sum across batches. For batch items the projected balance and the REDUCE confirmation text can be wrong. | **[O]** `StockAdjustmentPage.tsx:81-88` | Confirmation dialog misstates the result. |
| **P2** | 13 | **Current stock KPIs are inconsistent and unit-blind.** "Stock qty" is filtered and sums all units (kg + pcs + boxes); "Stock value" comes from an unfiltered company summary. | **[O]** `CurrentStockPage.tsx:195-212` | Filtering by godown or search changes qty but not value. The qty chip has no meaning. |
| **P2** | 14 | **"Email Excel" is broken.** It `mailto:`s a `blob:` URL (only valid in that browser tab), and the file is CSV. | **[O]** `CurrentStockPage.tsx:231-234`, `legacy/reports.ts:96` | Recipient gets a dead link. |
| **P2** | 15 | **No stock movement / item ledger screen.** The API exists (`/inventory/movements/`, `export`), but there is no page. Nothing answers "why is this 37 and not 40?". Export is 4 columns (no date, godown, batch, cost, reason). | **[O]** no route; `views.py:183-193` | The #1 trust question for inventory has no answer in the product. |
| **P2** | 16 | **Godowns can't be renamed, reactivated or have the default changed.** UI only offers Add, Deactivate, Delete. Inactive godowns appear in the list with no way back. | **[O]** `InventoryPhasePages.tsx:95-114` | Typos in names are permanent; deactivation is one-way. |
| **P2** | 17 | Stock count: cancel has no confirmation and sits next to Save; closing the dialog discards typed counts without a guard. | **[O]** `StockCountPage.tsx:370-393` | Easy to lose an hour of counting. |
| **P2** | 18 | Expiry write-off: acts on the whole row qty with no reason, preview of value lost, or distinction between *already expired* and *7 days out*; fails with a backend message if part of the lot is reserved. No success message. | **[O]** `InventoryPhasePages.tsx:453-472`, `views.py:786-794` | Easy to write off sellable stock; reserved qty case is confusing. |
| **P2** | 19 | Demand forecast always suggests 30 days × daily rate regardless of current stock, lead time or open POs; the page doesn't show on-hand or days of cover. | **[O]** `DemandForecastPage.tsx:64` | "Plan purchase" is offered for every product, including ones with ample stock. |
| **P2** | 20 | Low-stock definition differs by surface. Alerts page: company total ≤ reorder (per-godown override if set). Balance API `?low_stock=1`: per balance row ≤ effective reorder. Products page: sum of available ≤ reorder. Products with `reorder_level = 0` and zero stock show as "low". Products with no balance row at all never appear. | **[O]** `views.py:56-123, 137-141`; `ProductsPage.tsx:159-163` | Same product can be "low" on one screen and fine on another; dashboards/attention counts may differ. |
| **P2** | 21 | Adjustment reasons include "Customer Return / Exchange" and "Opening Stock Correction". The first bypasses the sales return/credit-note flow (no revenue/GST reversal); the second duplicates the opening-stock mechanism. Reason is stored as the English label (not a code). | **[O]** `StockAdjustmentPage.tsx:40-47` | Bad data in reports; GST impact missed. |
| **P3** | 22 | Label page: silently ignores adding a duplicate product; copies unbounded in UI (ZPL endpoint caps at 50 and the UI never uses it); price uses `mrp ?? sellingPrice` so an `mrp` of `0` prints ₹0.00; no batch/expiry/pack-date, no size choice. | **[O]** `LabelPrintPage.tsx:50,84-91` | Minor, but the ZPL endpoint is dead code from the UI. |
| **P3** | 23 | `StockValuationPage` exists twice (`reports/` and `phase/InventoryPhasePages.tsx`); only the first is routed. `ExpiryAlertsPage.tsx`, `SerialsPage.tsx`, `WarehousesPage.tsx`, `StockTransferPage.tsx` are 1-line re-exports. | **[O]** file sizes, `App.tsx:159-164` | Drift risk; edit the wrong copy. |
| **P3** | 24 | Inconsistent page chrome: some pages use `PageShell`+`DataTable`, others `PageTitle`+raw `Table`; `window.confirm` for destructive actions; `Row` (untyped) used heavily in phase pages. | **[O]** | Consistency/a11y debt. |

---

## 3. Per-screen review

Format: purpose → what works → problems → data effects. Numbers refer to the table above.

### 3.1 Products
- **Purpose [O]:** item master + stock-at-a-glance, bulk add, bill-upload entry, needs-review queue.
- **Works:** server pagination, filter + export that falls back to "all products" when a filter is active; stock chip colour logic; delete confirm; "needs review" workflow; column picker.
- **Problems:** stock chip is `available` summed over godowns and batches, no godown view [I]; filters (stock/category/brand/tax) are client-side over a second "all products" query — scale risk at large catalogues [V]; the low/out/in filters have slightly different rules from Low stock page (#20).
- **Data:** creates/edits items (affects billing, GST, labels, purchases); delete — **[V]** what happens to an item with stock or history (the Godowns page blocks delete when history exists; confirm Products does the same).
- **Not reviewed:** `ItemFormDialog` (opening stock, batch/serial flags, price tiers, custom fields). It is the biggest screen in the module and the first one a new user hits. Treat as unreviewed.

### 3.2 Current stock
- **Purpose [O]:** read-only balances by product, expand to lots/godowns; export/print.
- **Works:** virtualised rows, lot expansion, negative availability highlighted, custom-field search.
- **Problems:** #13, #14, #15. Godown filter is client-side over the full balance list. Search label reuses a custom-fields hint. "Show lots" button sits inside the name cell and changes row height (measured rows OK, but keyboard/AT use is awkward). No link from a row to the item, its ledger, adjust, or transfer.
- **Cross-screen:** it is the destination for adjustment-page redirect when the user lacks permission (`Navigate to=/inventory/stock`) — fine.

### 3.3 Low stock
- See #6, #7, #20. Also: no "create PO for all selected / grouped by supplier", no suggested qty, no supplier, no last purchase price. This screen should be the buyer's worklist; today it is a list with a broken link.

### 3.4 Purchase planning / 3.5 Demand forecast
- Planning page not read **[U]**. Forecast: see #19. Forecast is a separate page from planning with a button between them — **[I]** one screen would do.

### 3.6 Expiry alerts
- **Works:** day chips, godown filter, row-level write-off, disabled when no batch/zero qty, F3-037 guard against wrong-batch write-off.
- **Problems:** #18. Only shows lots with `on_hand > 0`; expired lots are mixed with "expiring in 7 days" with no visual or filter distinction (`expired` flag is returned but not shown) **[O]**. No "sell first / discount / return to supplier" actions. Written-off stock is posted with reason literal `"EXPIRED"` — check it is excluded from COGS-related reports **[V]**. Background task records bands/emails (`record_expiry_bands_task`) — good (GET has no side effects).

### 3.7 Stock adjustment
- **Works:** projected balance, negative warning, confirm on REDUCE, batch rules (REDUCE needs existing lot; ADD can create one), default godown seeded once, permission redirect.
- **Problems:** #1, #11, #12, #21. No date field although the backend accepts `date` and enforces closed-period checks — a user back-dating hits a period error with no way to choose a date. No idempotency key: a network retry after a lost response creates a second movement. No note/attachment. Value of the adjustment isn't shown, yet approval is driven by value (`stock_adjustment_needs_second(value, quantity, on_hand)`) — user can't predict why one adjustment needs approval and another doesn't.
- **Data:** creates an ADJUSTMENT `StockMovement`, may create a `BatchLot`, audit log entry. GL: see #3 **[V]**.

### 3.8 Godowns
- **Works:** server guards are solid (default can't be deactivated/deleted, stock blocks deactivate, history blocks delete, default invariant re-asserted after update, unique code per company).
- **Problems:** #16. Delete is a hard action on a list row with `window.confirm`. The "In transit" godown (code `IN_TRANSIT`, auto-created) is a real `Warehouse` row — **[V]** it will appear in this list, in stock filters, count-creation dropdown, adjustment dropdown (only `isActive` filtered) and valuation. Users could adjust or count the in-transit godown.

### 3.9 Stock counts (+ per-godown reorder levels)
- **Works:** server-side conflict detection (live qty vs snapshot) with KEEP_SERVER / KEEP_LOCAL, idempotent post, period gate, offline queue with conflict modal, print sheet, no-skip of adjustment for large variances.
- **Problems:** #4, #5, #17. `blind` mode exists in the model and serializer but the UI never sets or explains it; the UI hides system qty until posted regardless. `held_for_review` flags variance > `STOCK_COUNT_AUTO_POST_QTY` (5 units) — a flat unit threshold, not value, and the flag is only a marker; **[V]** where it's surfaced (Attention?). KEEP_SERVER silently drops counted lines for drifted SKUs but marks session POSTED, so the session record says "done" while those lines were never reconciled **[O]** (`views.py:931-934`). Reorder-level section is unrelated to counting and lives on this page (discoverability: nobody looks for reorder rules under "Stock counts").
- **Data:** posts ADJUSTMENT movements per line with `reason=STOCK_COUNT`, session → POSTED.

### 3.10 Stock transfers
- **Works:** two-step (dispatch → receive) via in-transit godown, deadlock-safe lock order, serial moves, shortage fields, period checks, cost carried from source, idempotent complete/receive, prefill from planning.
- **Problems:** #8, #9, #10. Create form: no available-qty hint at the source godown, qty accepts 0/negative client-side (server rejects at dispatch, not at create), the batch dropdown isn't filtered to the chosen source godown, serials are free text. Error state isn't cleared when the dialog reopens. Cancel of a COMPLETED transfer reverses stock via ADJUSTMENT movements — **[V]** if goods have since been sold from the destination, the reversal can push the destination negative (guarded only by the negative-stock policy) and cost layers are "retired" — high-risk code path with no UI explanation.
- **Cross-module:** transfers change godown balances used by invoicing, route planning (stock held, goods-to-check-in), reorder per godown, valuation by godown.

### 3.11 Serials
- #2. Also: no search by serial number (the API supports `serial_number=`; list is the whole table with only a status filter), no history, no link to the invoice that sold it, column label "Last: SOLD" reads like an event not a state, status values are raw enum strings, button text "Mark returned" for SOLD→RETURNED while the backend actually restocks and sets AVAILABLE (CR-049) — label and result disagree.
- This is where a counter person goes to check warranty/"did we sell this one" — it needs search and history, not a state machine editor.

### 3.12 Labels
- #22. Works: dedupe, CODE128 guard (QOS-0047), print CSS, scanning falls back to SKU. **[V]** that POS/quick-entry barcode lookup also matches SKU, otherwise SKU-barcodes won't scan.

### 3.13 Valuation / inventory report
- **Works:** WAVG vs FIFO banner, basis switch (cost/purchase/selling/MRP), virtualised table, permission is `CanViewFinancialReports`.
- **Problems:** backend supports `as_of` and `warehouse`; the page offers neither. Total is summed client-side from rows — fine, but with `basis != cost` the "unit cost" column header is wrong (it's price). No reconciliation line to the GL Inventory account (#3). Selling/MRP basis values are not valuations in an accounting sense — fine as an info tool, but should be labelled "not for accounts".

---

## 4. User flows that cross the module

```
Purchase bill / GRN ──► stock in ─┐
Sales invoice / challan ► stock out ├─► StockBalance (product×godown×batch)
Sales return ───────────► stock in ─┤        │
                                    │        ├─► Current stock, Products chip, Low stock, Dashboard, Attention
Adjustment / Count / Expiry / Serial scrap ─┘  ├─► Valuation, Inventory report, GL (?)  ← #3
Transfer: DRAFT → DISPATCHED (in-transit godown) → COMPLETED / CANCELLED
```

Broken or thin links in these flows: Low stock → Purchase (#6); Forecast → PO uses a different deep-link contract from Low stock (#6); Planning → Transfer deep-link exists and works; Expiry → no sales/discount action; Stock → no drill to ledger (#15).

---

## 5. Data and state

| State machine | States | UI communicates it? |
|---|---|---|
| Transfer | DRAFT → DISPATCHED → COMPLETED; CANCELLED from DRAFT/DISPATCHED/COMPLETED | Status chip yes; cancel from DRAFT/DISPATCHED not reachable (#9) |
| Count | DRAFT → COUNTED (auto when all lines have qty) → POSTED; CANCELLED | Chip yes; "COUNTED" appears only after Save; Post disabled until then with no hint why |
| Serial | AVAILABLE → SCRAPPED; SOLD → RETURNED/AVAILABLE; RETURNED → SCRAPPED | UI contradicts backend (#2) |
| Adjustment | Immediate, or PENDING approval | UI shows only "success" (#1) |

Silent-incorrectness risks:
- Pending adjustment shown as done (#1).
- KEEP_SERVER count marks POSTED but skips drifted lines (3.9).
- Cancel-after-complete transfer reversal interplay with later sales (3.10).
- Current stock chips mix filtered and unfiltered sources (#13).
- Two different "low stock" definitions (#20).
- Possible stock-vs-GL drift (#3).

---

## 6. Business rules to verify with the owner/CA (not bugs yet)

1. Should a manual adjustment/count variance/expiry write-off post Dr Shrinkage / Cr Inventory (and the reverse for gains)? At what cost (WAVG at date, last purchase)? Is the owner-only-approver exception (`owner_exception=True`) acceptable audit-wise?
2. Count variance threshold: units (5) or value? Per product class?
3. Should "available" for low stock subtract reserved? (Alerts: yes; Products chip: uses `available` from stock list — **[V]** same definition.)
4. Is write-off of *near-expiry but still valid* stock intended, or should it be limited to expired lots?
5. Should negative stock ever be allowed by transfer for admins (current code: admins get a warning, others a block)?
6. Is `Customer Return / Exchange` an allowed adjustment reason, given there is a Sales Return flow?

---

## 7. Cross-module impact

| Area | Impact | What |
|---|---|---|
| Accounting / GL | **HIGH** | #3; scrap-only posting; period locks are enforced on adjustments/counts/transfers/write-offs (good) |
| Sales / quick entry / POS / challans | **HIGH** | Any change to `StockBalance` semantics, batch selection, reserved qty, or negative-stock policy changes invoice-time behaviour |
| Purchases / planning / GRN | **HIGH** | Low stock and forecast deep-links; GRN creates stock and batches; reorder levels drive suggestions |
| Routes / orders | **MEDIUM** | `stock_held`, goods-to-check-in, route planning read godown balances; transfers and godown deactivation move them |
| Reports / Dashboard / Attention / Insights | **MEDIUM** | Low-stock counts (`reporting/services.py:441`), attention items, inventory summary all use their own aggregations (#20) |
| GST / e-way | **MEDIUM** | Adjustment reason "Customer Return" skips tax reversal (#21); transfers between godowns of the same GSTIN need no invoice, but a transfer between different GSTINs would (**[V]** single-GSTIN assumption) |
| Offline / PWA | **MEDIUM** | Queue kinds `stock_transfer`, `stock_count`; conflict event bus |
| Permissions / audit | **MEDIUM** | Adjustments are audit-logged; transfers log document events; counts, serial transitions, expiry write-offs, reorder-level edits — **[V]** audit entries for these |
| Search / notifications | **LOW** | Expiry band emails via daily task |

---

## 8. Edge cases and failure handling

**Data:** batch-tracked items with no batch chosen; fractional units; very long product names (labels use `noWrap`, OK); a barcode with characters CODE128 can't encode (handled); same product in two lines of a transfer (backend handles duplicates in cancel); serial typed with trailing spaces/commas (split/trim exists, case sensitivity **[V]**).

**User behaviour:** double-click adjustment Save (button disabled while pending — OK) but no idempotency key on retry after timeout; refresh in the middle of a count (counts are persisted only on "Save counts"; unsaved typed values are lost, **no guard**); back button from a transfer prefilled by `?lines=` re-opens the dialog because the prefill is derived from the URL on every render key change **[I]**.

**System:** network failure mid-post → queued (no feedback, #10); timeouts on counts of thousands of lines (all lines rendered, non-virtualised by design for print); concurrent counters in the same godown (two sessions can be open at once, nothing warns; conflict check at post time protects stock but not effort).

**Business:** count posted after a sale from the same godown (handled by conflict modal); transfer dispatched with insufficient stock (non-admin blocked, admin warned — the warning is returned in `data.warnings` but the page's `complete` mutation ignores response data, so the admin never sees it **[O]** `InventoryPhasePages.tsx:239-262`); deactivating a godown with only reserved stock (blocked, message is generic); period closed → backend error text is raw-ish.

**Error/recovery:** most pages use `HelpErrorAlert` (consistent, with help links) — good. Missing: loading state on action buttons for expiry write-off/serial transition; success confirmation for expiry write-off, serial transition, godown create, transfer create/complete/receive, count save.

---

## 9. Security and permissions

- **[O]** Routes are role-gated (`RoleRoute`), and every viewset has a permission class; list vs write are split on Warehouses and Serials; Valuation requires financial-report permission; VIEWER cannot see balances/movements/warehouses (BB-000418/618). Queries are company-scoped.
- **Concerns:**
  - `StockMovementViewSet` list/export use `CanViewInventorySurfaces`, but `unit_cost` is exposed in movement detail — **[V]** that the permission class excludes roles that must not see cost (sales-only staff).
  - `BatchLotViewSet`, `WarehouseReorderLevelViewSet`, `StockCountSessionViewSet`, `StockTransferViewSet` require `CanManageInventory` even for GET, so a buyer/viewer with "view inventory" can't read transfers or counts (consistent with route gating) — fine, but `Batch` list is also used on Current-stock-like flows; **[V]** no 403 on invoice screens for sales users who need batch pick.
  - Adjustment approvals: the owner-as-sole-approver path approves their own request in one call (`owner_exception=True`). Recorded, but it makes the control cosmetic for single-owner shops — acceptable only if intended.
  - Subscription gating: pages disable buttons with `writesBlocked`, but adjustments, counts-cancel, expiry write-off don't all check it in the UI (Serials, Warehouses do) — server still enforces on Serials via `SubscriptionWritesAllowed`; **[V]** others.
  - `window.confirm` is the only guard on destructive actions; no "type to confirm" for godown delete or count cancel.

---

## 10. Consistency, accessibility, responsiveness

- **Consistency:** two UI idioms (`PageShell + DataTable` vs `PageTitle + Table`); mixed terminology: godown / warehouse (`nav.warehouses` label used on Current stock filter while pages say "Godown"), "item" / "product", "Complete" (button) = dispatch (backend), "Receive" = complete; English literals mixed with `t()` (e.g. "No godowns.", "Mark sold", "Last:", "days" chips, "Remaining", "Hide lots"), which breaks the Hindi build the product ships **[O]**.
- **Accessibility:** good — table regions with `tabIndex` + `aria-label`, info-tooltip with `role="img"`. Gaps — chips used as buttons for day filters have no group label; coloured-only status (green/red) in Current stock; `window.confirm`; Autocomplete + custom-field filter bar inside dialogs on small screens; dense number-input rows in the count dialog (140px fields) on phones.
- **Responsive:** count dialog uses column on xs — good; transfer/adjustment dialogs are single column; Current stock has sticky name column on xs; label sheet is print-only layout. The stock-keeper on a phone has no barcode-scan entry point anywhere (counts, transfers, adjustments all use text search) **[I]**.

---

## 11. Cognitive load

- Adjustment: 7 controls plus a conditional batch block; the "Add/Reduce + batch existing vs new" logic is the heavy part. Reduce unneeded choice: hide new-batch when product has no batches yet; default the reason by type (REDUCE→"Damaged", ADD→"Count discrepancy").
- Stock counts page mixes three jobs (count sessions, per-godown reorder rules, offline status). Split reorder rules into Products/Item form or a "Reorder rules" tab.
- Current stock: 8 default columns + custom fields + godown filter + custom-field filters + search; the "all godowns" grouped view with expandable lots is a good default.
- Transfers: the user must remember what each transfer contains (#8).

---

## 12. Automation opportunities

| Manual now | Automate | Benefit |
|---|---|---|
| Typing counted qty for every line | Barcode scan → increment; "count = system" bulk button for untouched lines (with review) | Hours saved per count |
| Searching an item then typing qty in adjustment/transfer | Launch from a stock row (prefill product/godown) | Fewer taps and wrong-item errors |
| Low stock → remember to buy | Group by supplier/last supplier, prefill qty = reorder gap, one-click "make PO" | Buyer worklist |
| Choosing a batch for transfer | Default to FEFO (earliest expiry) at the source godown | Fewer expired write-offs |
| Writing off expired lots one-by-one | Bulk select + one reason | Month-end clean-up |
| Printing labels one product at a time | "Print labels for this purchase bill / these new items" | Receiving workflow |
| Reorder levels typed per product | Suggest from sales velocity (forecast already computes it) | Better thresholds |

---

## 13. Regression risk if this module changes

| Change | Risk | Why |
|---|---|---|
| Stock balance/movement semantics, negative-stock policy, reserved qty | **HIGH** | Sales, POS, challans, routes, purchases, returns all call `InventoryService.post_movement` / `check_negative_stock` |
| Low-stock definition | **HIGH** | At least four consumers (alerts API, balance API filter, Products page, reporting/insights) |
| Transfer service / in-transit godown | **HIGH** | Cancel logic depends on exact movement matching and cost-layer restoration |
| Serial transitions | **MEDIUM** | Invoices, challans, returns share `SerialNumberService` |
| `listStock()` shape | **MEDIUM** | Products, Current stock, Adjustment, Expiry cache keys (`['stock']`) |
| Warehouse model/guards | **MEDIUM** | Every godown dropdown; deactivated godowns still referenced by history |
| Labels/forecast/valuation pages | **LOW** | Leaf screens |

Note on query keys: Expiry write-off invalidates `['stock']` and `['expiry-alerts']` but not `['low-stock']` or `['inventory-summary']`; counts invalidate `['stock']` only. Stale low-stock / KPI chips after write-offs.

---

## 14. Test scenarios (high value)

**Functional / business**
1. Adjustment requiring second approval → expect "Awaiting approval" and no stock change; after approval, stock changes once.
2. REDUCE on a batch product with two lots → projected balance equals the chosen lot, not the first row.
3. Fractional adjustment (0.5) accepted; 0 and negative rejected inline.
4. Serial AVAILABLE → scrap works from UI; no "Mark sold" on AVAILABLE; SOLD → return restocks and status becomes AVAILABLE; label matches.
5. Count: type counts, save, **view variance table**, post; add an unexpected item; partial section count. Count then sell one unit before posting → conflict modal; KEEP_SERVER leaves session in a state that says which lines were skipped.
6. Transfer: create multi-line; dispatch; partial receive with shortage; cancel from DRAFT and DISPATCHED; cancel COMPLETED after destination has sold part → defined outcome.
7. Expiry: expired vs expiring split; write-off when part reserved; written-off qty excluded from low-stock/valuation correctly.
8. Low stock → Reorder opens purchase with product (and qty) prefilled; godown visible.

**Data / reconciliation**
9. For each of adjustment / count variance / expiry write-off / serial scrap, with accounting enabled: Inventory valuation total equals GL Inventory (1400) balance at same date. **This is the test that confirms or kills finding #3.**
10. Same product shows the same low/out/ok status on Products, Low stock, Dashboard, Attention.

**Reliability**
11. Offline: complete transfer, post count → visible "queued" state; reconnect → single movement set (idempotency); conflict event path.
12. Network drop after adjustment POST succeeded → retry doesn't create a second movement (needs idempotency key).
13. Refresh mid-count with unsaved values → guard prompts.

**Permissions**
14. VIEWER, sales-only, buyer, stock-keeper, accountant: route access, API 403s, cost not leaked in movements/balances.
15. Subscription lapsed: every write button disabled and server rejects.

**Regression**
16. Invoice with batch item after transfer/adjust; returns restock; route "goods to check in" after godown deactivation.

---

## 15. Priority list (all problems)

See section 2 (24 rows). Items I'd want fixed before calling this module reliable: **#1, #2, #3 (verify), #4, #6, #8, #9, #10**.

---

## 16. The three changes with the most payoff

1. **Make every stock-changing action tell the truth** (#1, #4, #10, success messages): return values drive the UI — PENDING vs applied, warnings, queued-offline, variance preview before count post. *Outcome:* users trust the numbers; fixes the only P0s that silently corrupt behaviour.
2. **Close the loop between stock and money** (#3 + valuation reconciliation + an item ledger page, #15): one place to see every movement with reason/cost/reference, and a "Stock vs GL" check. *Correctness + business value:* shrinkage reaches P&L, valuation matches the balance sheet, and every "why is this wrong?" ticket is answerable.
3. **Turn alert screens into worklists** (#6, #7, #19, #20): one low-stock definition, godown shown, supplier/qty suggested, links that actually prefill the PO or transfer. *Outcome:* fewer stock-outs and expiry losses with less manual searching; the most visible daily-use improvement.

---

## 17. Scores (1–10)

| Dimension | Score | Note |
|---|---:|---|
| Purpose clarity | 7 | Clear except forecast/serials |
| UX | 6 | Solid basics; dead-end actions |
| Cognitive load | 6 | Adjustment and counts heavy |
| Flow | 5 | Broken links, missing stages in transfer/count |
| Functionality | 6 | Backend rich, UI exposes a subset (partial receive, review, ledger, blind count) |
| Business logic | 7 | Server rules are careful (locks, periods, idempotency); GL gap unverified |
| Data/state handling | 6 | Good concurrency design; UI misreports pending/queued |
| Error handling | 6 | Good error component; weak success/pending feedback |
| Cross-product integration | 5 | Low-stock divergence, dead deep link, GL |
| Consistency | 5 | Two UI idioms, English literals, label drift |
| Accessibility | 6 | Better than average; colour-only status, confirm dialogs |
| **Overall** | **6** | |

## Final verdict

🟡 **READY WITH FIXES** — conditional on finding #3.

The backend is carefully built (row locks, period gates, idempotent posts, conflict detection, tenant checks) and the read screens are sound. The write screens misreport outcomes (#1, #2, #10), the count flow's final step is blind (#4), and the main alert → purchase link is dead (#6). If the GL check in test 9 shows adjustments and write-offs don't post, that item alone moves this to 🔴 NOT READY for any customer who relies on the balance sheet.

---

## 18. Gaps in this review (updated after pass 2)

- Pass 2 read `PurchasePlanningPage`, `planning.py`, `forecast.py`, `useStockOffline.ts`, `InventoryReportPage`, the Products/Item form logic (validation, opening stock, tracking lock) and the cross-module stock writers/readers. See the addendum below.
- Still not done: line-by-line read of `ItemFormDialog` JSX (pricing tabs, custom-field tab, batch-lot grid), the 2,500-line `inventory/services.py` outside the transfer service, and all backend tests. No running app, no Postgres-only concurrency tests.
- GL finding (#3) is from code search, not a ledger run — but see addendum A3, which strengthens it.
- Permission findings need an actual role-matrix pass.

---

# ADDENDUM (pass 2) — remaining screens and cross-module impact

Menu check: the sidebar (`web/src/navigation/menu.ts:229-264`) has exactly 12 Inventory entries — Products, Current Stock, Stock Adjustment, Low Stock, Purchase planning (flag-gated), Demand forecast, Print Labels, Godowns, Stock Counts, Stock Transfers, Expiry Alerts, Serial Numbers. All 12 are now covered. Two more stock screens sit under **Reports** (Inventory report, Stock valuation) and are in scope for cross-module purposes.

## A1. New findings

| Pri | # | Problem | Evidence | Why it matters |
|---|---|---|---|---|
| **P1** | 25 | **Purchase planning silently omits most low-stock items.** `purchase_plan()` keeps only rows where `is_warehouse_specific` is true, i.e. products that have a *per-godown reorder override*. Company-wide low-stock items (the default) never appear. | **[O]** `inventory/planning.py:35-39` vs `views.py:104-122` | Low stock shows 40 items, Purchase planning shows 3, and nothing explains why. The buyer trusts the plan and under-orders. |
| **P1** | 26 | **API permission gap on planning and forecast.** Both `GET` endpoints use only `IsAuthenticated + HasCompany`. Routes are gated by `canViewInventorySurfaces` (blocks VIEWER), the API is not. | **[O]** `planning.py:111-119`, `forecast.py:19`; compare `CanViewInventorySurfaces` which excludes VIEWER (`permissions.py:317-324`) | A VIEWER (or any role) can call the API directly and read sales velocity, suggested quantities, last supplier ids. UI hiding is not security. |
| **P1** | 27 | **Offline sync is invisible on the screens that queue.** `useStockOffline` takes an optional banner callback; `StockCountPage` and `StockTransferPage` call it without one. Queued items flush only while one of those pages is mounted (or on the outbox page). Failures never surface there. | **[O]** `useStockOffline.ts:82-163`; callers pass 2 args | A stock-keeper queues a count, closes the tab, and nothing ever tells them it didn't post. Related to #10. |
| **P2** | 28 | **Planning table doesn't show the supplier**, yet drafts are created one PO per last-purchased supplier. Rows with no supplier are put in "needs supplier" after the click. No qty edit before creating drafts. Quantities are rounded **up** to whole units on the PO (fractional kg items get over-ordered); price is `purchase_price` at draft time. | **[O]** `PurchasePlanningPage.tsx:176-211`, `planning.py:206-220` | Surprise POs, no chance to adjust. |
| **P2** | 29 | **Two different demand numbers.** Forecast uses a 90-day mean over SALE movements; planning and the alert insight use a 14-day velocity. Forecast also ignores sales returns, lumps all godowns, and counts stock-out periods as zero demand. | **[O]** `forecast.py:26-57`, `planning.py:34,60` | "Daily rate" on one page and "days to stock-out" on the other disagree for the same product. |
| **P2** | 30 | **Forecast is duplicated** — the same table is embedded at the bottom of Purchase planning and is also its own page/menu item, with a link between them. | **[O]** `PurchasePlanningPage.tsx:215-241`, `DemandForecastPage.tsx` | One menu entry too many; two places to maintain. |
| **P2** | 31 | **Planning needs two flags** (`ENABLE_PURCHASE_PLANNING` for the menu, `ENABLE_REPLENISHMENT` for the data). With replenishment off the page gets HTTP 400 `replenishment_required`. | **[O]** `planning.py:22-28`, `menu.ts:250` | Menu item visible → page shows an error. Should hide or explain. |
| **P2** | 32 | **Inventory report has the same KPI flaw as Current stock** (qty summed across units; "Email Excel" mails a `blob:` URL). It *does* carry a useful health column (balance drift / reserved drift) that Current stock lacks. | **[O]** `InventoryReportPage.tsx:123-131,150-153` | Drift detection exists but is buried under Reports; the daily-use screens give no hint a balance is unhealthy. |
| **P2** | 33 | **Item form: opening stock is a second request after the item save.** If it fails the item exists without stock and the user sees "Item saved, but opening stock failed" (idempotency keys make retry safe, which is good). Opening stock only on create; later corrections must go through Adjustment ("Opening Stock Correction" reason). | **[O]** `ItemFormDialog.tsx:485-541` | Acceptable design, but the failure state should offer "retry opening stock" rather than a generic error. |
| **P3** | 34 | Positive: tracking flags and type are frozen after any stock movement (`assert_tracking_unlocked`), item delete is blocked when referenced, form has unsaved-changes guard, HSN/SAC validation, barcode print is escaped (XSS fixed). | **[O]** `item_stock.py:143-157`, `masters/views.py:1156-1166` | Worth keeping as the model for other screens. |

### A2. Impact of #25 and #29 together
A buyer using Low stock (company-wide), Dashboard tile (company-wide), Planning (godown-override only) and Forecast (90-day, all godowns) sees four different answers to "what should I buy?". This is the single biggest *product-level* inconsistency in the module.

### A3. GL finding (#3) — strengthened
`accounting/reports.py:508-545` returns `inventory_gl` (GL 1400), `inventory_valuation` (stock engine) and `inventory_variance` — the system already expects the two to differ. `core/invariants/reports.py:105-130` has a GL-vs-valuation check that is deliberately *not* in the default sweep because GL posting is not guaranteed on every stock path. The only UI that references the variance is `AccountingBackfillBanner`. So: manual adjustments, count variances, expiry write-offs and serial scrap change the valuation engine but (by code search) post no journal; the balance-sheet `equation_holds` uses GL assets. Still needs a ledger run to confirm, but the design evidence now points the same way.

## A4. Cross-module impact map (what each Inventory action touches)

Stock movement writers found: `sales/services.py`, `sales/cogs_service.py`, `sales/return_service.py`, `sales/notes_services.py`, `purchases/services.py`, `purchases/grn_service.py`, `manufacturing/services.py`, `imports/services.py`, `integrations/shopify.py`, `integrations/tally/adapter.py`, plus the inventory screens. Readers of `StockBalance`: `reporting/services.py`, `insights/alerts.py`, `insights/services.py`, `planwave/finish.py`, `sales/route_planning.py`, `sales/views.py`, `core/invariants/*`, `accounts/tenant_backup.py`.

| Inventory action | Other module | What changes → where → why it matters | Impact |
|---|---|---|---|
| Stock adjustment / count post / expiry write-off / serial scrap | **Accounting** | Valuation changes; no journal found → Trial balance, P&L (no shrinkage expense), Balance sheet GL 1400 vs valuation (A3) | **HIGH** |
| Same | **Sales / POS / Quick entry** | `on_hand` changes availability → next invoice allowed/blocked by `negative_stock_policy` (BLOCK/WARN; `services.py:211,732`) | **HIGH** |
| Same | **Reports** | Stock valuation, Inventory report, dashboard `low_stock_count` (`reporting/services.py:402`), insights stock score | **HIGH** |
| Adjustment with value over threshold | **Approvals (planwave)** | Creates pending approval; UI shows success (#1) → Approvals inbox, requester believes done | **HIGH** |
| Count post, adjustment, transfer, write-off | **Audit log** | Adjustment logs `AuditService`; transfers log document events; counts/serials/write-offs: **[V]** no `AuditService.log` seen in the views | **MEDIUM** |
| Transfer dispatch/receive | **Sales routes / orders** | `route_planning` free stock per godown, `stock_held`, goods-to-check-in → route plans change when stock moves between godowns | **MEDIUM** |
| Transfer, godown deactivation | **Purchases / planning** | Planning proposes transfers from surplus godowns (`transfer_from_warehouse_id`); deactivated godowns vanish from dropdowns but stay in history | **MEDIUM** |
| Low stock / forecast / planning "Reorder" | **Purchases** | Creates draft POs (`PurchaseOrder`) at product `purchase_price`; Low stock link param isn't consumed (#6) | **HIGH** |
| Purchase bill / GRN | **Inventory** | PURCHASE movements, batch creation, expiry; changes Expiry, Low stock, Current stock, valuation cost (WAVG/FIFO) | **HIGH** |
| Sales return / credit note | **Inventory** | SALES_RETURN movement, FIFO peel restore; scrap posts Dr 5450 / Cr 1400 (the only shrinkage GL path) | **HIGH** |
| Manufacturing | **Inventory** | Consumes/produces stock through `post_movement`; adjustment/count of components or finished goods can desync BOM cost assumptions **[V]** | **MEDIUM** |
| Imports (CSV, bill upload), Shopify, Tally | **Inventory** | Opening-stock and import movements; `import_void` compensating adjustments; Tally adapter writes balances — each bypasses the screens' guards | **MEDIUM** |
| Item edit (price, GST, HSN, reorder level, unit) | **Billing / GST / Labels / Planning** | Reorder level drives Low stock/Planning/Dashboard; price drives labels and PO draft price; unit change guarded after movements | **MEDIUM** |
| Item type/tracking change | **Serials / Batches** | Frozen after first movement — good; before that, switching affects which dialogs (batch/serial) apply on invoices | **LOW** |
| Expiry alerts | **Notifications / email** | Daily task logs bands and emails (`record_expiry_bands`) | **LOW** |
| Offline queue | **PWA outbox** | Queued transfers/counts flush from two pages only (#27) | **MEDIUM** |
| Whole module | **Tenant backup / invariants** | `balance_equals_movements`, `transfer_pairs_net_zero`, `serial_traceability` invariants — transfer cancel and KEEP_SERVER count paths are the ones most likely to trip them | **MEDIUM** |

## A5. Extra test scenarios from pass 2
1. Product with company-wide reorder only: appears on Low stock and Dashboard; **expected** on Planning (currently missing — #25).
2. Same product: forecast daily rate × days vs planning "days to stock-out" — numbers consistent or explained.
3. VIEWER / sales-only user calls `GET /inventory/purchase-planning/` and `/inventory/demand-forecast/` → expect 403.
4. Replenishment flag off, planning flag on → menu hidden or page shows a clear explanation.
5. Plan → create drafts with fractional-qty item and a row with no supplier → PO quantities, notes, "needs supplier" feedback.
6. Queue a count offline, close tab, reopen on Dashboard → user is told it is pending; opening Counts page flushes it once.
7. Adjustment, count variance, expiry write-off, serial scrap with accounting on → compare `inventory_variance` on the balance sheet before/after (the decisive test for A3).
8. Manufacturing run, then count/adjust the output item → cost, valuation, and COGS on next sale.
9. Tally/CSV import of opening stock after the godown already has movements → unique-constraint behaviour and the screens' view of it.

## A6. Updated scores
Cross-product integration drops from 5 to **4** (planning/low-stock divergence, GL gap, permission gap). Overall stays **6**; verdict stays 🟡 READY WITH FIXES, with #3, #25 and #26 added to the must-fix list alongside #1, #2, #4, #6, #8, #9, #10.
