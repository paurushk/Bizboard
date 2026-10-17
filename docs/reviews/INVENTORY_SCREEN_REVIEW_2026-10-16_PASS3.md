# Inventory module — screen, flow and product-impact review (pass 3, post-fix)

Date: 2026-10-16. Scope: Products, Current Stock, Stock Adjustment, Low Stock, Purchase Planning, Demand Forecast,
Print Labels, Godowns, Stock Counts, Stock Transfers, Expiry Alerts, Serial Numbers.

**Method and limits.** Static read of the working tree (uncommitted WP-00..21 from the 2026-10-15 review). Read in
full this pass: `inventory/views.py` (adjustment, expiry, count, transfer, serial permissions), `inventory/planning.py`,
`inventory/forecast.py`, `PurchasePlanningPage.tsx` (action area), `stockKpis.ts`, `navigation/menu.ts`, the
permission classes. Not done: running app, Postgres concurrency, role-matrix run, line-by-line read of every page.
Tags: **[O]** observed in code, **[I]** inferred, **[V]** needs verification, **[U]** unknown.

Earlier review: `docs/reviews/INVENTORY_SCREEN_REVIEW_2026-10-15.md`. This pass checks which of its fixes landed
and looks for what the fixes themselves introduced or left.

## 1. Confirmed fixed since pass 2 [O]
- Planning and forecast GET now use `CanViewInventorySurfaces` (`planning.py:186-197`, `forecast.py:32`).
- Adjustment is idempotent and returns `status: APPLIED` or 202 `PENDING` (`views.py:259-377`).
- Count post: idempotent, row-locked, period-gated, conflict list, `KEEP_SERVER` marks `drift_skipped`.
- Transfer dispatch/receive idempotent; cancelling a *received* transfer is owner/manager only (`views.py:557-568`).
- One velocity definition (30-day, net of returns) used by forecast and planning. Planning rounds up only whole-unit items.
- Current stock KPIs no longer add quantities across units (`stockKpis.ts`).
- `reason_code` now exists on adjustments (the implementation record still says it does not — record is stale).

## 2. Findings that matter most

| Pri | # | Problem | Evidence | Why it matters |
|---|---|---|---|---|
| **P1** | 1 | **The "second person must approve" control only guards the Adjustment screen.** Value ≥ ₹10,000 or ≥ 10 % of on-hand needs approval there, but **expiry write-off**, **stock count post**, and **serial scrap** call `post_movement` directly with no approval check. | **[O]** `stock_adjustment_needs_second` is referenced only at `views.py:313-321`; expiry POST `views.py:880-930`; count post `views.py:1034-1135`; serial scrap `views.py:819-844` | One person with inventory permission can write off any amount by choosing "Damaged" in Expiry, or by posting a count, and never reaches the Approvals inbox. The control is cosmetic. |
| **P1** | 2 | **Count "recheck" (D4) is advisory only.** `needs_recheck` is computed in the serializer; `post` never requires it. Large variances set `held_for_review` and post anyway. | **[O]** `serializers.py:468-476`; `views.py:1105-1117` | A large miscount reaches stock and, with the GL flag on, the P&L, with only a flag as a trail. The 2026-10-15 note says the rule was built; it is a UI hint. |
| **P1** | 3 | **Count post is all-or-nothing on drift, and `KEEP_LOCAL` can double-count.** Any line whose system quantity moved since the snapshot (a sale during the count) forces one choice for the whole session. `KEEP_LOCAL` posts `counted − current`, but the counted figure predates the later sale, so the sale is subtracted twice. | **[O]** `views.py:1063-1100` | In a trading godown every count that takes hours hits this. Users will pick `KEEP_LOCAL` and understate stock. Needs a per-line choice, or counting-time cut-off logic. |
| **P1** | 4 | **GL posting for stock gains and losses is off by default** (`ACCOUNTING_POST_STOCK_ADJUSTMENTS`) and awaiting CA sign-off. Until then valuation and GL 1400 diverge by every adjustment, count variance, write-off and scrap. | **[O]** `_post_stock_write_journal`, `_inventory_books_comparison` (`views.py:238-253, 935-962`) | The balance-sheet gap is now visible, which is good, but a tenant live today still has a growing gap. People problem, not code. |
| **P2** | 5 | **Expiry write-off has no idempotency, and bad input returns 500.** Unlike adjustments it is not wrapped in `wrap_idempotent`; a double click posts two write-offs (the second is capped by available quantity, so the damage is bounded, but a partial lot can be written off twice). `Decimal(str(request.data.get("quantity")))` and `int(days)` raise on non-numeric input. | **[O]** `views.py:880-930`, `865` | Retry after timeout, or a malformed call, gives a duplicate movement or a server error instead of a message. |
| **P2** | 6 | **Expiry write-off is dated today, not the lot's expiry date, and ignores the approval, reason code and the optional `movement_date`** that the adjustment path has. | **[O]** `views.py:910-930` | Period lock is checked against today, so a write-off of last month's expiry lands in this month. Probably intended; confirm with the CA. |
| **P2** | 7 | **Purchase planning "Create drafts" has no server-side duplicate protection.** The button is disabled while pending, but a second click after a reload creates a second set of draft POs; the plan only subtracts *confirmed* orders ("covered by orders"). Draft PO price comes from `product.purchase_price` (can be 0). | **[O]** `planning.py:231-310`, `PurchasePlanningPage.tsx:170-185` **[V]** whether drafts count as covered | Duplicate drafts for the same shortfall; zero-priced lines. |
| **P2** | 8 | **POST with no rows and an empty plan returns a bare 404** "Not found." with no explanation. | **[O]** `planning.py:215-217` | Shows as a generic error when nothing is low. |
| **P2** | 9 | **Count `cancel` is not row-locked.** It reads the session, checks status, saves `CANCELLED`. A concurrent `post` (which holds the lock) can finish first and cancel then overwrites `POSTED` with `CANCELLED`, while stock has moved. | **[O]** `views.py:1182-1197` vs `1034-1042` | Stock changed but the session shows cancelled — wrong audit trail. Postgres-only race. Fix: `select_for_update` and re-check. |
| **P2** | 10 | **Forecast treats stock-out days as zero demand.** A product that was out of stock half the window shows half its real daily rate, so suggested reorders and days-to-stockout look better than they are. | **[I]** `forecast.py:item_sales` is a flat mean over 30 days | Under-ordering of the fastest-selling items, exactly the ones that run out. |
| **P2** | 11 | **Role split is uneven across the 12 screens.** Read-only views (Products, Stock, Low stock, Planning, Forecast, Expiry) are open to sales/purchase/finance users; Labels, Godowns, Counts, Transfers, Serials need inventory manage. The serial list is readable by sales (`CanReadSerials`) but the menu hides it. Labels menu is `canAdjustInventory` while the ZPL API only needs view. | **[O]** `menu.ts:238-265`, `views.py:228, 696-720` | Not a leak, but inconsistent: a salesperson cannot open Serials from the menu yet can query it. Decide intended roles. |
| **P2** | 12 | **Cost visibility is handled per endpoint** (`_can_see_costs` in expiry; valuation needs financial reports). Planning's draft PO price and any "value" columns on Low stock/forecast rows were not checked. | **[V]** | A salesperson with view access may see purchase prices through a different endpoint. |
| **P3** | 13 | Implementation record (section 8) is stale: says no `reason_code` on adjustments, but the field is in the adjustment path. | **[O]** `views.py:352` | Misleads the next reviewer. |
| **P3** | 14 | Planning and forecast both need `ENABLE_REPLENISHMENT`; the page now explains this (good), but the menu entry still shows when the flag is off. | **[O]** `menu.ts:250-252` | One wasted click. |
| **P3** | 15 | Planning page links to Forecast and Forecast to Planning; two menu entries remain for overlapping data. | **[O]** | Candidate to merge later. |

## 3. Per-screen notes (what changed my view)
- **Products** — item form is large (1,400 lines); the tracking-lock after first movement and retry-opening-stock flow are good. Not re-read this pass. **[V]** pricing/custom-field tabs.
- **Current stock** — KPIs now honest; drift warning surfaces `hasDrift`. Value hidden when a custom-field filter is on instead of being wrong. Good pattern.
- **Stock adjustment** — safest write screen: idempotent, period gate, approval, audit, warnings. Gap: the approval value uses `purchase_price`, not valuation cost (WAVG/FIFO), so the threshold can differ from the booked value **[V]**.
- **Low stock / Planning / Forecast** — numbers now agree by construction. Remaining risk is #10 and #7.
- **Labels** — ZPL escapes name/code (`safe_name`, `safe_code`), copies capped at 50. Low risk.
- **Godowns** — system godowns excluded from write paths (`is_system=False`). Deactivation consequences for routes were flagged earlier; **[V]** after fix.
- **Counts** — strongest design (blind count, review step, conflicts) but see #2, #3, #9.
- **Transfers** — full lifecycle with idempotency and cancel rules. Offline dispatch has no per-row "queued" state (known gap).
- **Expiry** — read side is sound; write-off path is the weakest write endpoint (#1, #5, #6).
- **Serials** — status transitions are whitelisted; scrap requires on-hand ≥ 1. Scrap bypasses approval (#1).

## 4. Cross-module impact (HIGH items)
| What changes → where → why |
|---|
| Any stock write → `StockBalance` → next invoice allowed/blocked by `negative_stock_policy`, route free-stock, dashboard low-stock count, insights score. **HIGH** |
| Stock write with GL flag on → journal Dr shrinkage / Cr 1400 → P&L, trial balance, GST period lock (a refused journal also refuses the stock change). **HIGH** |
| Planning drafts → `PurchaseOrder` rows → Purchases list, supplier ledger once sent. **HIGH** |
| Count/adjustment of a manufacturing component → BOM cost assumptions. **MEDIUM [V]** |
| Offline queue flushes only from some pages. **MEDIUM** (banner added in WP-07; **[V]**) |

## 5. Edge cases worth a test
Double-click on expiry write-off; non-numeric quantity to expiry POST; count with a sale during the count then each of
`KEEP_SERVER`/`KEEP_LOCAL`; cancel and post a count at the same time (Postgres); planning create-drafts twice;
write-off of ₹50,000 of stock by a user with only inventory permission (expect approval, currently none);
batch item transferred then invoiced; closed GST period with write-off and count.

## 6. Test scenarios (high value)
1. Role matrix: VIEWER, SALES, PURCHASE, INVENTORY, MANAGER, OWNER against all 12 routes **and** their APIs.
2. Approval parity: adjustment, expiry write-off, count post and serial scrap of the same value — all should hit the same rule.
3. Count with mid-count sale; verify final on-hand equals physical count after post.
4. GL flag on: adjustment, count, write-off, scrap; compare `books_variance` before and after; flag off then backfill dry run.
5. Plan → create drafts → reload → create again: expect no duplicate for the same shortfall.
6. Forecast for an item out of stock 15 of 30 days.
7. Offline: queue a transfer and a count, close the tab, reopen on Dashboard.
8. Concurrency (Postgres): two dispatches, two receives, post vs cancel on a count.

## 7. Scores
| Dimension | Score |
|---|---:|
| Purpose clarity | 8 |
| UX | 7 |
| Cognitive load | 7 |
| Flow | 7 |
| Functionality | 8 |
| Business logic | 6 |
| Data/state handling | 7 |
| Error handling | 7 |
| Cross-product integration | 7 |
| Consistency | 7 |
| Accessibility | 7 |
| **Overall** | **7** |

## Final verdict
🟡 **READY WITH FIXES.**

The read screens, transfers and the adjustment screen are in good shape and the earlier P0/P1 findings are mostly closed.
Before relying on it with real money: bring expiry write-off, count post and serial scrap under the same approval,
idempotency and period rules as the adjustment (#1, #5, #6), make the count recheck and drift handling enforceable (#2, #3),
lock count cancel (#9), and get the CA decision that turns GL posting on (#4).

## Three changes with the most payoff
1. **One write path for every stock loss** (#1, #5, #6, #2): adjustment, write-off, count variance and scrap share one
   function that applies approval, idempotency, period gate, reason code and journal. Fixes correctness and the control.
2. **Per-line count drift handling** (#3, #9): stops the count from understating stock; the most frequent real-world failure.
3. **Turn on and prove GL posting** (#4): CA sign-off, run the backfill dry run on a copy, then enable per tenant.
