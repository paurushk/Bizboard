# Order-to-delivery flow hardening — implementation plan

**Date:** 2026-10-14
**Status:** PLAN ONLY. Nothing here has been executed. No code was changed.
**Revision 2 (2026-10-14):** re-reviewed against the code and updated with the founder's decisions, recorded in [../decisions/ORDER_DELIVERY_ROUTES_DECISIONS.md](../decisions/ORDER_DELIVERY_ROUTES_DECISIONS.md). Companion plans: [DELIVERY_ROUTES_REVIEW_AND_ACTION_ITEMS.md](DELIVERY_ROUTES_REVIEW_AND_ACTION_ITEMS.md), [DELIVERY_ROUTES_OFFICE_GODOWN_LOOP.md](DELIVERY_ROUTES_OFFICE_GODOWN_LOOP.md), [DELIVERY_ROUTE_PLANNING_HARDENING.md](DELIVERY_ROUTE_PLANNING_HARDENING.md).

**What changed in revision 2**
- Section 2: all six decisions are now taken; no package is blocked by a decision any more.
- WP-8: the "Shipped" label needs a small **read-only derived field** on the order (the order payload carries no challan information today, so the label cannot be computed in the browser). The earlier text assumed it could.
- WP-6: now lists the inventory files for H-04 (`inventory/services.py::_confirmed_so_qty`, `inventory/item_stock.py::_OPEN_DOCUMENT_CHECKS`) instead of leaving H-04 as a note.
- WP-10: now includes delivery routes in global search (RT-16 and OG-41 point here).
- Ground rules: read-only derived fields are allowed; "no new fields" meant no stored fields.
- Section 9: challans on routes is confirmed as a separate later project (decision Q-4).
**Scope:** Quotation, Quick Order Entry (QOE), Sales Order (SO), Delivery Challan (DC), Delivery Route, and what reads them.
**Basis:** a code-reading review of the working tree on 2026-10-14 (uncommitted changes present). No tests or app runs were done, so every finding starts with a reproduction step (WP-0).

## 0. Ground rules

- **Hardening only.** No new screens, endpoints, statuses, fields or flags. Fix wrong behaviour, close dead ends, make labels truthful.
- **No migrations** unless a work package says so. None in this plan do. (The route planning plan adds one table for acknowledgements; that is separate.)
- **No new stored fields.** Read-only derived fields on existing API responses are allowed (WP-7, WP-8) and need the OpenAPI snapshot and web types regenerated (CI diffs both).
- Copy changes (button and status labels) are allowed because they fix confusion in existing screens. They add no capability.
- Anything that would be new capability is listed in section 9 and **not planned here**.
- Every fix lands with a test that fails before the fix and passes after.
- Backend concurrency and idempotency tests are Postgres-only; use the private test DB recipe in the project notes. Web: `cd web && npx tsc -b` (not `tsc -p .`), lint stays at 0 errors.
- Locate code by symbol; line numbers drift in this tree.

## 1. Findings, with IDs

| ID | Finding | Severity | Area |
|---|---|---|---|
| H-01 | Reservation released twice on a partial shipment: challan complete, then invoice complete from that challan | High (stock) | backend |
| H-02 | Failed route stop re-releases a line already released by challan complete | High (stock) | backend |
| H-03 | Credit exposure ignores goods shipped on a completed challan until it is invoiced | High (credit) | backend |
| H-04 | Reserved-stock rebuild and unit-change guard ignore `PARTIALLY_CONVERTED` orders | Medium | backend |
| H-05 | Gates off: a confirmed order has no Convert, To Challan or Cancel button (dead end; QOE auto-confirm produces it) | High (UX) | web |
| H-06 | SO list "Open" filter = DRAFT only, "Closed" = nonexistent `COMPLETED`; list Cancel shows for `COMPLETED` only; editor Cancel for DRAFT only | High (UX) | web |
| H-07 | No labels for `CONFIRMED` / `PARTIALLY_CONVERTED` (raw `status.CONFIRMED` shown) | Medium | web |
| H-08 | Challan editor SO picker lists DRAFT orders only; hand-linking a challan does not move `shipped_quantity` | Medium | web, backend |
| H-09 | Route dialog loads DRAFT and CONFIRMED only; ready-to-dispatch orders (`CONVERTED`, `PARTIALLY_CONVERTED`) excluded | Medium | web |
| H-10 | SO to invoice drops `price_mode`; quotation to SO never copies it (guard reads a field Quotation lacks) | Medium (money) | backend |
| H-11 | Challan tax and challan-to-invoice type ignore the order's `invoice_type` | Medium (tax) | backend |
| H-12 | One invoice from a challan blocks later challans on the same order (CR-120 guard too broad) | Medium | backend |
| H-13 | Second partial convert overwrites `SalesOrder.converted_invoice`; cancel guard and route profit see the latest only | Medium | backend |
| H-14 | Failed or rejected stop does nothing for an already-issued invoice | Low-Medium | backend, web |
| H-15 | Vocabulary: "Convert" means three things; order shows "Converted" when only shipped | Medium (confusion) | web copy |
| H-16 | Global search finds quotations only | Low | backend |
| H-17 | No user-facing explanation of the flow; mode (gates on/off) invisible to users | Medium | docs, web copy |

## 2. Decisions (all taken by the founder, 2026-10-14)

| ID | Decision | Package |
|---|---|---|
| DEC-1 | **Yes.** One order may ship in several challans with an invoice per challan. Replace the "order has an invoice" guards with a per-line remaining-quantity check. | WP-6 |
| DEC-2 | **"Shipped"** label for a `CONVERTED` order that has a completed challan and no invoice. The stored status does not change. | WP-8 |
| DEC-3 | **Yes.** Uninvoiced completed challans count toward credit exposure at the challan's grand total, until the converted invoice is completed. Only for customers with a limit, only where `ENABLE_ORDER_GATES` is on. | WP-3 |
| DEC-4 | **Yes.** A `CONFIRMED` order can be cancelled from the screen, behind `CanCancelDocuments`, with a confirm dialog that says stock will be released. | WP-4 |
| DEC-5 | **Warn only.** A failed stop on an invoiced order shows the invoice number and points to Sales Returns. No automatic documents. | WP-7 |
| DEC-6 | **Inherit from the order.** A challan linked to an order takes its `invoice_type`; a standalone challan keeps the registration-based rule. | WP-5 |

DEC-1 and DEC-3 change money and stock behaviour: ship WP-3 and WP-6 each as its own commit with its own rollback (section 6).

## 3. Work packages

Order of work: WP-0 first, then the stock and credit group (WP-1 to WP-3), then the screens group (WP-4, WP-8) which is independent and can run in parallel, then the conversion group (WP-5 to WP-7), then WP-9 to WP-10.

### WP-0 · Reproduce every finding (S)

**Goal:** turn each H-item from "read in code" into a failing test or a recorded "not reproducible". Nothing else starts until this is done for that item.

**Steps**
1. Add failing tests, one per finding, in the files listed in each package below. Mark them `xfail(strict=True)` on the backend (or `it.fails` on the web) so the suite stays green and flips loud when fixed.
2. For H-01, H-02, H-04 assert on `StockBalance.reserved` for a product shared by two orders.
3. For H-07 and H-09, render the page in Vitest and assert on text, not raw keys.
4. Record the outcome per item in section 7 (status table). Drop or downgrade any item that does not reproduce.

**Acceptance:** each H-item has a test or a written "not reproducible" note.

---

### WP-1 · Single release of reservations across challan and invoice (H-01) (M)

**Problem:** `complete_challan` releases the order's reservation. `SalesService.complete` releases it again when the converted invoice completes and the order is still `PARTIALLY_CONVERTED`. `release_reservation` floors at zero, so the second release eats other orders' holds.

**Files:** `backend/sales/notes_services.py` (`complete_challan`, `convert_delivery_challan`), `backend/sales/services.py` (invoice completion block near "CR-020"), tests in `backend/tests/test_next_batch_so_challan.py` and a new `backend/tests/test_so_reservation_release_once.py`.

**Approach:** the invoice completion path must skip the release when the invoice came from a challan, because the challan already released that quantity.
1. Identify the source: an invoice with a `DeliveryChallan.converted_invoice` pointing at it. Compute `challan_sourced = DeliveryChallan.objects.filter(converted_invoice=invoice).exists()`.
2. In the release loop, if `challan_sourced`, skip the release for that order. The status roll-up below the loop (CONVERTED or PARTIALLY_CONVERTED) stays as is.
3. Do not touch the direct order-to-invoice path (`source_order` set, no challan): it correctly holds the reservation until the invoice completes.

**Tests**
- Two confirmed orders for the same product, `reserved` = sum of both. Ship order A partly by challan, convert and complete its invoice. Assert `reserved` equals order B's quantity plus order A's unshipped remainder, never below.
- Direct order-to-invoice path still releases exactly once.
- Full shipment path (status `CONVERTED`) unchanged.

**Acceptance:** `reserved` after each step matches a hand-computed table in the test. **Risk:** an invoice built from a challan whose order was DRAFT (no reservation) must not go negative; the floor handles it, and a test pins it. **Rollback:** revert the one condition.

---

### WP-2 · Failed stop releases only what is still held (H-02) (S)

**Files:** `backend/sales/route_service.py` (`_release_failed_stop`), `backend/tests/personas/test_pj_route_pod.py` or a new `test_route_failed_stop_release.py`.

**Approach**
1. Compute the amount still held per line instead of falling back to the full quantity: held = `quantity - shipped_quantity` while the challan has not completed, and 0 once the challan has completed (its completion already released it).
2. Remove the `open_qty <= 0 → release whole quantity` branch and its incorrect comment.
3. The challan-return creation below stays unchanged.

**Tests:** fully shipped and completed challan, stop FAILED, assert `reserved` unchanged. Unshipped remainder is released once. FAILED to DELIVERED to FAILED still releases once (existing `stock_released_at` guard).

**Acceptance:** no change to other orders' `reserved` from a failed stop on a shipped order.

---

### WP-3 · Credit exposure includes shipped, uninvoiced challans (H-03) (M) — decided (DEC-3)

**Files:** `backend/sales/order_gates.py` (`sales_order_exposure`, `_ledger_covered_by_order`), possibly `backend/planwave/services.py` (`assert_chronic_credit_allowed` used by `complete_challan`), tests in `backend/tests/test_sales_order_guards.py`.

**Approach**
1. In `sales_order_exposure`, add to `extra` the grand total of the customer's COMPLETED challans that have no `converted_invoice`, or whose invoice is not yet in an open-receivable status.
2. Avoid double counting: a challan whose invoice is counted by the ledger is already in `posted`; a challan on an order already in `others` is counted once (extend `_ledger_covered_by_order` rather than adding a second path).
3. Include `PARTIALLY_CONVERTED` orders in `others` with only their unshipped, uninvoiced remainder.
4. Apply the same figure wherever the order gate and the chronic-credit check read exposure, so the two cannot drift. Keep the single function; do not copy the logic.

**Tests:** limit 1000; invoice 400 posted; completed challan 500 uninvoiced; new order 200 is blocked (1100 > 1000). After the challan is invoiced and completed, exposure is 400 + 500 once, not twice. Credit override by owner still works and copies to the invoice.

**Acceptance:** exposure never counts one rupee twice and never omits shipped goods. **Risk:** behaviour change blocks orders that passed before. Mitigation: ship behind the existing `ENABLE_ORDER_GATES` flag (already the gate for this check) and list affected customers with a read-only report before enabling. **Rollback:** revert the additions.

---

### WP-4 · Order list and editor actions match the order's status (H-05, H-06) (M) — decided (DEC-4)

**Files:** `web/src/pages/sales/SalesOrdersPage.tsx`, `web/src/pages/sales/SalesOrderEditorPage.tsx`, tests `SalesOrdersPage.test.tsx`, `SalesOrderEditorPage.test.tsx`. Extract one helper, `orderActions(status, gatesOn, canWrite, canCancel)`, so list and editor cannot disagree.

**Action matrix (the single source of truth)**

| Status | Confirm | To Challan / Create invoice | Cancel |
|---|---|---|---|
| DRAFT, gates off | shown | shown | shown |
| DRAFT, gates on | shown | hidden (backend demands confirm) | shown |
| CONFIRMED | hidden | shown (both modes) | shown |
| PARTIALLY_CONVERTED | hidden | shown for the remainder | hidden (backend refuses) |
| CONVERTED, CANCELLED | hidden | hidden | hidden |

**Steps**
1. Implement the matrix once and use it in both screens.
2. Fix filters: "Open" sends no single status; send a multi-status request or three requests merged (DRAFT, CONFIRMED, PARTIALLY_CONVERTED). "Closed" means CONVERTED and CANCELLED. If the list endpoint accepts only one status, extend `get_queryset` to accept a comma-separated `status` (a filter fix, not a feature).
3. Remove the `COMPLETED` check on the list's Cancel button.
4. Cancel on a CONFIRMED order opens the existing `ConfirmDialog` with text saying reserved stock will be released.
5. After Confirm with gates off, the row immediately shows the next actions (invalidate `['sales-orders']`, `['sales-order', id]`).

**Tests:** one test per matrix row for both screens; "Open" returns a confirmed order; "Closed" returns a converted one; confirm-then-convert path works with gates off (this is the QOE auto-confirm path).

**Acceptance:** no order status exists that the UI renders without a way forward or a visible reason. **Risk:** low, web only.

---

### WP-5 · Carry price mode and invoice type through every conversion (H-10, H-11) (M) — decided (DEC-6)

**Files:** `backend/sales/notes_services.py` (`convert_sales_order`, `convert_sales_order_to_challan`, `set_challan_items`, `convert_delivery_challan`), `backend/sales/services.py` (`convert_quotation_to_order`), `backend/sales/models.py` only if DEC-6 needs a field (it does not; read the order via `challan.sales_order`).

**Approach**
1. `convert_sales_order`: pass `price_mode=order.price_mode` to the invoice, as the challan path already does.
2. `convert_quotation_to_order`: remove the dead `getattr(quotation, "price_mode")` branch. A quotation has no price mode, so the order keeps its default EXCLUSIVE. Add a comment that this is deliberate, and verify that quote line prices are exclusive (they are stored as `unit_price` with `unit_price_inclusive` separate). If quote lines can be inclusive, convert them to the order's mode, and write that conversion as a tested helper.
3. Challan tax: when the challan has a linked order, `set_challan_items` uses `order.invoice_type`: NON_GST means `tax_enabled=False`. Standalone challans keep the current rule.
4. `convert_delivery_challan`: when the order exists, use `order.invoice_type` instead of recomputing from registration; fall back to the current rule only for standalone challans. Keep the REGISTRATION_GATE protections for composition and unregistered companies (the invoice completion still enforces them).

**Tests:** inclusive-mode company round trip (order to invoice, order to challan to invoice) gives identical totals to the order. NON_GST order produces an untaxed challan and a NON_GST invoice. Standalone challan behaviour unchanged. Quote to order to invoice totals match the quote to the paisa (existing quotation closure tests must stay green).

**Acceptance:** for any chain, document totals agree at every step. **Risk:** totals shift on in-flight drafts, but only for drafts converted after the fix.

---

### WP-6 · Partial shipments: one invoice per challan (H-12, H-13) (L) — decided (DEC-1)

**Files:** `backend/sales/notes_services.py` (`complete_challan` CR-120 guard, `convert_delivery_challan`, `convert_sales_order`, `cancel_sales_order`), `backend/sales/phase1_serializers.py` (`validate_sales_order`), `backend/sales/services.py` (invoice completion roll-up), `backend/sales/route_profit_service.py`, **`backend/inventory/services.py` (`_confirmed_so_qty`) and `backend/inventory/item_stock.py` (`_OPEN_DOCUMENT_CHECKS`) for H-04**, tests including `test_next_batch_so_challan.py`.

**Approach (DEC-1 = yes)**
1. Stop treating "order has `converted_invoice`" as meaning "fully invoiced". Replace the three CR-120 guards with a quantity check: an invoice or challan may take at most the line's `quantity - invoiced_quantity - shipped_quantity` (the shared remainder), using the counters that already exist. Do this in one helper, `order_remaining(order)`, used by every guard.
2. Keep refusing the genuinely unsafe case: the same quantity must not be both shipped by challan and invoiced directly (double stock and AR). The helper makes that fall out naturally, since both consume the same remainder.
3. `converted_invoice` stays as "latest". Cancel and route-profit logic must read all invoices linked via `source_order` and challan `converted_invoice`, not the single pointer. Add one query helper, `invoices_for_order(order)`, and use it in `cancel_sales_order`, `compute_route_financials`, `_ledger_covered_by_order` and campaigns attribution.
4. Order status roll-up uses the counters only.
5. **H-04 (same helper):** `_confirmed_so_qty` and the unit-change guard must include `PARTIALLY_CONVERTED` orders and count only what is still owed. Define "still held" precisely and test it: reserved stock for an order is `quantity` minus quantity on **completed** challans minus quantity on **completed** invoices (a draft invoice from the order still holds its reservation until it completes, so the draft-time `invoiced_quantity` counter must not be used for this). Write the definition once, as a function next to `order_remaining`. **Introduce it in WP-1** (it needs it to decide what the invoice may still release) and reuse it here, in WP-2's failed-stop release, the rebuild and the guard.

**Tests (these are the contract):**
- Order 10 units: challan 4, invoice it, challan 6, invoice it. Both complete; order ends `CONVERTED`; `reserved` returns to baseline; stock moves once per unit.
- Challan 4 shipped, then direct invoice for 7 is refused (only 6 left).
- Cancel order with one completed and one draft invoice is refused with a message naming both.
- Route profit counts both invoices.
- H-04: rebuild of `reserved` after a partial challan equals the unshipped remainder, not zero and not the full quantity; the unit-change guard blocks a product that a partly processed order still owes.

**Acceptance:** no scenario ships or bills a unit twice or loses a unit. **Risk:** highest of the plan, because it touches money paths. Do it after WP-1 and WP-3, keep it in its own commit, and run the Postgres concurrency tests. **Rollback:** revert the commit; the counters are unchanged by it.

---

### WP-7 · Failed stop on an invoiced order tells the user (H-14) (S) — decided (DEC-5)

**Files:** `backend/sales/route_service.py` (`set_stop_status` response), `backend/sales/route_serializers.py`, `web/src/pages/sales/DeliveryRoutesPage.tsx`, tests in `DeliveryRoutesPage.test.tsx`.

**Approach:** when a stop becomes FAILED, REJECTED or RETURNED and the order has an invoice in an open-receivable status, return the invoice number in the existing stop payload and show an info message: "Invoice X is still active. Record a sales return if the goods were not accepted." No state change, no new endpoint; use fields the serializer already returns, adding the invoice reference as a read-only attribute on the existing response.

**Acceptance:** message appears only when an active invoice exists. Adding a read-only field to the response requires regenerating `docs/openapi-snapshot.json` and `web/src/api/openapi-types.ts` (CI diffs both).

---

### WP-8 · Status labels and button vocabulary (H-07, H-09, H-15) (M) — decided (DEC-2)

**Files:** `web/src/i18n/en.ts`, `web/src/i18n/hi.ts`, `web/src/utils/status.ts`, `SalesOrderEditorPage.tsx`, `SalesOrdersPage.tsx`, `DeliveryChallanEditorPage.tsx`, `DeliveryChallansPage.tsx`, `DeliveryRoutesPage.tsx`, `ConvertQuotationDialog.tsx`, `QuotationsPage.tsx`.

**Steps**
1. Add `status.CONFIRMED` ("Confirmed") and `status.PARTIALLY_CONVERTED` ("Partly processed") in English and Hindi. Tones: confirmed = info, partially converted = warning.
2. Order-specific display: a small `orderStatusLabel(order)` returns "Shipped" when the status is `CONVERTED`, a completed challan exists and no invoice does; otherwise the plain status label. The order payload carries `convertedInvoice` but **no challan information** (checked in `SalesOrderSerializer`), so the label cannot be derived in the browser. Add one **read-only derived field** on the order, `fulfilment_state` (`none`, `shipped_not_invoiced`, `invoiced`), computed from prefetched challans and invoices (no extra query per row), and show "Shipped" for `shipped_not_invoiced`. Regenerate the OpenAPI snapshot and web types. No stored field, no migration.
3. Rename actions (copy only): order "Convert" becomes "Create invoice", "To Challan" becomes "Create challan"; challan "Convert" becomes "Create invoice"; quotation "Convert" becomes "Create invoice", "To Order" becomes "Create order". Keep i18n keys; change values. Update affected tests and the Hindi strings (flag Hindi for native review, as already noted in the QOE rollout).
4. Route dialog and the SO list's "Add to route" use the same eligible-order rule, decided in DEC-P1 and enforced by the server (route planning plan, PL-04): `CONFIRMED`, `PARTIALLY_CONVERTED`, or `CONVERTED` with a completed challan, and not already on an active route. Draft orders are not offered; an owner may add one with a reason. Load the eligible statuses (H-09) and show the status chip next to each so a dispatcher can see what is ready. The screen only reflects the server rule; it does not decide it.
5. Challan editor order picker: list CONFIRMED and PARTIALLY_CONVERTED orders (and DRAFT when gates are off), not DRAFT only (H-08, UI part).

**Acceptance:** no raw `status.*` text anywhere; one verb per action across all five screens; routes dialog shows every shippable order. Add a test that scans `en.ts` and `hi.ts` for every status the backend enums emit for Quotation, SalesOrder, DeliveryChallan, DeliveryRoute and DeliveryRouteStop, so a missing label fails CI.

---

### WP-9 · Backend guard for hand-linked challans (H-08, backend part) (S)

**Files:** `backend/sales/phase1_serializers.py` (`DeliveryChallanSerializer`), `backend/sales/phase1_views.py`, tests in `test_sales_order_guards.py`.

**Approach:** when a challan is created with `sales_order` set and lines supplied directly, validate each line quantity against `order_remaining(order)` (the WP-6 helper), and add the quantities to `shipped_quantity` on create and subtract on draft delete or cancel (the delete and cancel paths already call `release_order_conversion`). Without this the "To Challan" button is the only protected path.

**Acceptance:** a hand-linked challan cannot exceed the order's remaining quantity, and deleting it gives the quantity back. Depends on WP-6's helper; if WP-6 is deferred, implement the helper alone first.

---

### WP-10 · Search and a plain-language flow guide (H-16, H-17) (S)

1. `backend/search/views.py`: include sales orders, delivery challans **and delivery routes** (by number, vehicle, driver name) in the same visibility block as quotations (same `can_view_sales` rule, same `LIMIT`, search by number and customer name). RT-16 and OG-41 are this item. This is an existing endpoint reading existing models; add no new result kinds to the UI beyond rendering them where `kind` is already switched on. If the UI needs a new kind, defer (section 9).
2. Docs: add a "How sales documents connect" page to the existing Help content (`web/src/pages/help/faqContent.tsx` entry in the "Quotations, orders & challans" group). One entry, plain words: which steps are optional, which statuses mean what, what changes when order checks are on. It is text in the existing help system, not a new screen.
3. In the SO editor, show one line of existing-style helper text stating whether order checks (gates) are on: "Orders must be confirmed before they can be invoiced" or "Orders can be invoiced directly". Read from the flag the page already reads.

**Acceptance:** searching an order number returns it; the help entry renders and passes the existing help tests (`faqContent.portalMapping.test.tsx`, help snapshot tests).

## 4. Dependency graph

```
WP-0 ──┬─ WP-1 ─┬─ WP-6 ─ WP-9
       ├─ WP-2  │
       ├─ WP-3 ─┘
       ├─ WP-4 ─┐
       ├─ WP-8 ─┴─ WP-10
       ├─ WP-5
       └─ WP-7
```

WP-4 and WP-8 touch the same pages: do WP-4 first, then WP-8, in one branch to avoid conflicts.

## 5. Test plan

The full case-by-case catalogue (about 200 cases with IDs, files, scenarios and expected results, covering all four plans) is [ORDER_DELIVERY_ROUTES_TEST_CASES.md](ORDER_DELIVERY_ROUTES_TEST_CASES.md). The summary below is kept for orientation.

**New or extended tests**
- `backend/tests/test_so_reservation_release_once.py` (WP-1, WP-2)
- `backend/tests/test_sales_order_guards.py` (WP-3, WP-5, WP-9)
- `backend/tests/test_next_batch_so_challan.py` (WP-1, WP-6)
- `backend/tests/personas/test_pj_route_pod.py` and `test_route_profit.py` (WP-2, WP-6, WP-7)
- Web: `SalesOrdersPage.test.tsx`, `SalesOrderEditorPage.test.tsx`, `DeliveryRoutesPage.test.tsx`, a new status-label coverage test (WP-4, WP-7, WP-8)

**Regression suites that must stay green**
- Quotation: `test_quotation_closure*.py`, `test_quotation_plan_phases.py`, `test_quotation_remediation.py`, `test_quotation_concurrency_postgres.py`
- Cross flow: `docs/CROSS_FLOW_TEST_CHECKLIST.md` rows for convert, cancel, complete
- Web: `QuickEntryPage.test.tsx`, `quickEntryHelp.test.tsx`, `quotationHelp.test.tsx`

**End-to-end scenarios to script once, after WP-1 to WP-6** (real backend, golden style like `web/e2e-golden/route-pod-golden.spec.ts`)
1. Quote, order, confirm, challan, complete, invoice, route, deliver. Stock and AR agree at each step.
2. Quick Entry order with auto-confirm, gates off: convert from the list.
3. Two-challan partial shipment with an invoice each.
4. Failed stop on a shipped and invoiced order.
5. Cancel a confirmed order; reserved stock returns.

## 6. Rollout and rollback

- Web-only packages (WP-4, WP-7 web part, WP-8, WP-10) deploy first, no data impact.
- WP-1, WP-2 are pure bug fixes; deploy together.
- WP-3 changes who gets blocked. Before enabling, run a read-only listing of customers whose exposure changes by the new rule; share it with the founder; it only takes effect where `ENABLE_ORDER_GATES` is on.
- WP-5 and WP-6 deploy last, each as a single commit, so either can be reverted alone.
- No migrations, so rollback is a code revert in every case.
- After deploy, run a reservation reconciliation (recompute `reserved` from open documents) on the pilot company and compare to stored balances. The existing `reconcile_dual_fulfillment_and_cost` command in `backend/inventory/management/commands/` is a starting point; confirm what it covers before relying on it.

## 7. Status tracker (fill in as work proceeds)

| ID | Reproduced? | Package | Decision | Done |
|---|---|---|---|---|
| H-01 | | WP-1 | none | |
| H-02 | | WP-2 | none | |
| H-03 | | WP-3 | DEC-3 | |
| H-04 | | WP-6 (counter helper) | none | |
| H-05 | | WP-4 | DEC-4 | |
| H-06 | | WP-4 | DEC-4 | |
| H-07 | | WP-8 | none | |
| H-08 | | WP-8, WP-9 | none | |
| H-09 | | WP-8 | none | |
| H-10 | | WP-5 | none | |
| H-11 | | WP-5 | DEC-6 | |
| H-12 | | WP-6 | DEC-1 | |
| H-13 | | WP-6 | DEC-1 | |
| H-14 | | WP-7 | DEC-5 | |
| H-15 | | WP-8 | DEC-2 | |
| H-16 | | WP-10 | none | |
| H-17 | | WP-10 | none | |

H-04 is assigned to WP-6 because the fix is to read partial orders from the shared remainder helper in `inventory/services.py::_confirmed_so_qty` and `inventory/item_stock.py::_OPEN_DOCUMENT_CHECKS`: include `PARTIALLY_CONVERTED` and count only `quantity - shipped - invoiced`. Do it with WP-6 so there is one definition of "still owed".

## 8. Effort estimate

S = 0.5 day or less, M = 1 to 2 days, L = 3 to 5 days, tests included.
WP-0 S, WP-1 M, WP-2 S, WP-3 M, WP-4 M, WP-5 M, WP-6 L, WP-7 S, WP-8 M, WP-9 S, WP-10 S. Total about 10 to 14 engineer-days, plus review of DEC-1 and DEC-3 by the founder.

## 9. Explicitly out of scope (new capability, not hardening)

Decided 2026-10-14: **routes that carry challans** is a separate project after this hardening (decision Q-4); invoiced challans are routable in that project (Q-1). Nothing in this plan assumes it.

- Letting a route stop reference a challan or an invoice, or routing standalone challans and direct invoices.
- Auto-creating a sales return or credit note on a failed delivery.
- Linking a route's vehicle and driver to challan transport fields or e-way bills.
- New order statuses, a "Shipped" status value, or new list columns and API fields beyond the single read-only attribute in WP-7.
- A user to Employee link for salesman attribution on Quick Entry orders.
- Unifying "New Invoice", Quick Entry, POS and Bill Upload into one entry point, or moving menu items.
- A dedicated document-flow visual or timeline screen.

Record these as backlog items after hardening, not in this plan.

## 10. One release sequence across all four plans (added in revision 2)

The four plans overlap on purpose; this is the order that avoids doing anything twice.

| Release | Contents | Migration |
|---|---|---|
| R0 | WP-0 and RT-00: failing tests for every finding | none |
| R1 | Stock and credit: WP-1, WP-2, WP-3 | none |
| R2 | Order and challan screens: WP-4, WP-8 (with the read-only `fulfilment_state` field), WP-10 (search incl. routes) | none |
| R3 | Conversions: WP-5, WP-6 (with H-04), WP-7, WP-9 | none |
| R4 | Route rules and office loop: RT-01..04, RT-08, RT-09, RT-15, OG-01..03, OG-07, OG-08, OG-11..13, OG-35, OG-36 | none |
| R5 | Route screens: OG-10, OG-14, OG-15, OG-20, OG-21, OG-22 (link only), RT-31 (phone-width layout), OG-40, OG-42 | none |
| R6 | Goods return loop: OG-31, OG-32, OG-33, OG-34, OG-30 | none |
| R7 | Route planning intelligence: PL-03, PL-01, PL-02, PL-04..PL-10, PL-20..PL-28 | **one**: acknowledgement table (PL-06) |
| Later project | Challans on routes (RT-40): invoiced challans routable, open question Q-5 | yes, designed then |

Reproduce-first applies to every release. Each release is deployable on its own and reverted by a code revert, except R7, which also drops one additive table.

