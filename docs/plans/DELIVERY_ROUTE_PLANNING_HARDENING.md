# Delivery route planning — hardening and order intelligence

**Date:** 2026-10-14
**Status:** PLAN ONLY. Nothing executed, no code changed.
**Revision 2 (2026-10-14):** re-reviewed and updated with the founder's decisions ([../decisions/ORDER_DELIVERY_ROUTES_DECISIONS.md](../decisions/ORDER_DELIVERY_ROUTES_DECISIONS.md)). Changes: acknowledgements are a **new table with a migration** (DEC-P3 / Q-2), so principle 6 and PL-06 changed; `eway_needed` corrected (orders carry no e-way fields); the "not ready" block now has an owner override (DEC-P1); section 7 shows all decisions taken; candidates are **orders only** this round (challans on routes is a separate later project, Q-4); PL-02 and PL-04 name their dependency on the hardening plan's counters (WP-6).
**Relates to:** [DELIVERY_ROUTES_OFFICE_GODOWN_LOOP.md](DELIVERY_ROUTES_OFFICE_GODOWN_LOOP.md) (OG-xx), [DELIVERY_ROUTES_REVIEW_AND_ACTION_ITEMS.md](DELIVERY_ROUTES_REVIEW_AND_ACTION_ITEMS.md) (RT-xx), [ORDER_TO_DELIVERY_HARDENING_PLAN.md](ORDER_TO_DELIVERY_HARDENING_PLAN.md) (WP-xx). Those documents are unchanged. Items here (PL-xx) extend the planning stage and point to the earlier IDs they absorb so nothing is built twice.
**Basis:** code reading of the route planning path (`DeliveryRoutesPage.tsx` create dialog, `RouteService.add_orders`, `start_route`, `route_combine.py`, `route_optimization.py`) and of the data that already exists to describe an order, its customer, its bill and its risks.

## 1. What a dispatcher sees when planning today

The "create route" dialog lists up to 100 draft and 100 confirmed orders as a checkbox with **order number and customer name only**. There is no date, area, value, items, stock position, bill, payment or risk. The dispatcher cannot tell whether an order is ready, whether the customer is blocked or over limit, whether goods exist in the godown, or whether the customer already owes money. The backend accepts whatever is ticked (any non-cancelled order, even if already on another route) and starting the route performs no checks. The route detail repeats the same bare order number, customer and address.

## 2. What data already exists (so this is mostly assembly, not invention)

| Need | Where it already lives |
|---|---|
| Order header, lines, products, quantities, prices, totals, expected delivery date, delivery address | `SalesOrder`, `SalesOrderItem` |
| Shipped and invoiced quantity per line | `shipped_quantity`, `invoiced_quantity` |
| Challan and invoice linked to the order, their status | `DeliveryChallan.sales_order`, `SalesOrder.converted_invoice`, `SalesInvoice.source_order` |
| Customer status (blocked or inactive), phone, pincode, state, GSTIN, WhatsApp opt-in, price list, credit limit and days | `Customer` |
| Customer money position: outstanding, overdue, ageing, average payment delay, available credit, collection status (`clear / open / overdue / overdue_severe / stop_credit`) | `payments/dunning.py::customer_risk_snapshot` |
| Unallocated advances | `LedgerService.customer_unallocated_receipts` |
| Credit held for chronic overdue (> 60 days) | `planwave/services.py::chronic_overdue` |
| Order exposure against limit | `sales/order_gates.py::sales_order_exposure` |
| Margin below threshold | `order_gates.margin_warnings`, `expected_profit_for_order` (cost visible only to users who can see financial reports) |
| Stock on hand, reserved, available per product in the default godown | `StockBalance`; `StockHintView` |
| Batch and expiry, serial tracking | `BatchLot`, `Product.track_batch`, `track_serial` |
| e-Way Bill threshold | `company.eway_threshold_amount`, default ₹50,000 |
| Lat/long, pincode for sequencing | `Customer.latitude`, `longitude`, `pincode` |

**Not available (do not promise):** product weight or volume (no fields), vehicle capacity, delivery time windows, driver phone on the route. Anything needing those is a new feature and is listed in section 8, not planned here.

## 3. Principles

1. **Read-only intelligence first, then rules.** Show everything the dispatcher needs; only then block what is clearly wrong.
2. **Three levels of risk:** **Block** (cannot be routed), **Warn** (can proceed with an acknowledged reason), **Info** (shown, no action). Blocks are few and unambiguous.
3. **One source of truth.** A single backend function builds the order summary; the picker, the route detail, the pre-start check and the manifest all read it.
4. **Respect existing permissions.** Cost and margin appear only for users who already see them (`can_view_expected_profit`). Customer money data appears only to users with sales-surface access, as in Customer 360.
5. **Fast.** Planning lists are paged and capped; customer risk is computed once per customer per request, not per order.
6. **No new documents or statuses.** One read endpoint, one check endpoint, and **one new table** for risk acknowledgements (decision DEC-P3 / Q-2): one row per stop and risk, with who, when and why, so risks can be reported on. That table is the only migration in this plan.

## 4. Order summary: what the planner shows

For each candidate order (and later each stop), in this order of importance:

**Header** — order number, order date, expected delivery date (and "late" if past), age in days, current status (using the labels from WP-8), channel, salesman.

**Customer** — name, phone, delivery address (the order's address, falling back as the order already does), pincode, area; flags if phone, address or pincode is missing; blocked or inactive; credit hold.

**Items and products** — number of lines, total quantity, and per line: product, quantity, unit, **stock available now** (on hand minus reserved, excluding this order's own reservation so it does not count against itself), shortfall, batch or expiry note where tracked. Totals row. Lines with cost or margin only for permitted users.

**Bills** — the document the goods travel on: sales order only / challan (number, status) / invoice (number, status, total). "Delivered but not invoiced" and "invoiced but not delivered" are named states.

**Payment** — amount to collect on delivery: the invoice balance if invoiced, else the order total; whether the customer has advance receipts on account that cover it; payment terms (cash or credit days).

**Customer money position** — outstanding, overdue, oldest overdue age, available credit, collection status, and whether this order takes them over the limit.

**Risk flags** — see the catalog in section 5.

## 5. Risk catalog

| Code | Level | Meaning | Source | Override |
|---|---|---|---|---|
| `order_cancelled` | Block | Cancelled order | status | none |
| `already_on_route` | Block | On another active route, or already delivered | stops | none (remove from the other route) |
| `customer_blocked` | Block | Customer blocked or inactive | `Customer.status` | none |
| `not_ready` | Block | Draft order, unconfirmed, no stock held (DEC-P1: owner may add with a reason) | status | owner reason |
| `fully_shipped_invoiced` | Block | Nothing left to deliver | counters | none |
| `credit_hold` | Warn | Chronic overdue credit hold | `chronic_overdue` | owner or manager reason |
| `over_credit_limit` | Warn | Exposure above limit | `sales_order_exposure` | owner or manager reason |
| `customer_overdue` | Warn | Overdue invoices exist, severity from `collection_status` | risk snapshot | acknowledge |
| `stock_short` | Warn | Available less than quantity for one or more lines | stock | acknowledge |
| `expired_or_near_expiry` | Warn | Batch expired or within the company's near-expiry window | batch | acknowledge |
| `no_address` | Warn | No usable delivery address | order and customer | fix or acknowledge |
| `no_phone` | Warn | No customer phone | customer | fix or acknowledge |
| `no_pincode` | Info | Cannot be grouped or sequenced | customer | none |
| `eway_needed` | Info on an order; Warn when a linked challan or invoice at or above the threshold has no e-way details | company threshold; `eway_status` exists on challans and invoices only, not on orders | acknowledge |
| `low_margin` | Info | Below margin threshold (permitted users only) | `margin_warnings` | none |
| `partial_delivery` | Info | Only the remaining quantity will travel | counters | none |
| `late` | Info | Past expected delivery date | order | none |
| `gstin_unverified` | Info | Customer GSTIN not verified | customer | none |

Overrides are recorded in the new acknowledgement table (DEC-P3): stop, risk code, level, reason, who, when. The route screen and the manifest show them.

## 6. Action items

Effort: S ≤ 0.5 day, M 1 to 2 days, L 3 to 5 days, tests included.

### A. The summary and the check (backend)

| ID | Action | Absorbs | Effort |
|---|---|---|---|
| PL-01 | **One order-summary builder** that returns the sections in section 4 for a list of orders, batching all queries (orders, lines, products, stock balances, challans, invoices, customers, risk snapshots once per customer). Pure read, company-scoped, cost fields masked | new | L |
| PL-02 | **Candidate list endpoint** on the existing route viewset: paged, filtered by date (expected delivery), status, customer, pincode or area, "ready only", "has risk"; sorted by expected delivery then oldest. Replaces the two fixed calls of 100 orders. **Orders only** this round (challans on routes is a separate project) | OG-01 | M |
| PL-03 | **Risk evaluator** with the catalog in section 5: one function, codes and levels in one table, used by candidates, add-orders, start and the manifest. Same rules everywhere | new | M |
| PL-04 | **Enforce Blocks on add:** `add_orders` refuses blocked orders with the code and a plain message; all-or-nothing, never partly added. `fully_shipped_invoiced` and `already_on_route` need the corrected counters from hardening plan WP-6, so land after it | RT-04, RT-05, OG-01, OG-02 | M |
| PL-05 | **Pre-start check endpoint:** returns the summary and risks for the route's stops; `start` refuses unresolved Blocks and requires acknowledgement (with reason) for Warns. Re-run at start, not only at add, because the world changes between planning and dispatch | OG-05 | M |
| PL-06 | **Record acknowledgements** in a new table (stop, risk code, level, reason, who, when), audit-logged, shown on the route and the manifest. Needs a migration (additive, reversible) and an OpenAPI regeneration | new | M |
| PL-07 | **Route-level totals:** stops, orders, lines, quantities, value, amount to collect, number of warnings, e-way count, estimated profit for permitted users | extends route rollup | M |
| PL-08 | **Re-check on change:** when an order is edited, cancelled or its customer blocked after being planned, the route shows the new risk (computed at read, not stored), and the dispatcher sees it on the route list | OG-14 | M |
| PL-09 | **Same-day clash checks:** vehicle or driver already on another route that day | RT-09, OG-03 | S |
| PL-10 | **Failed-stop re-plan safety:** an order from a failed stop shows "stock released, re-reserve needed" and cannot be re-added until reconfirmed | RT-07, OG-33 | M |

### B. Planning screens (web)

| ID | Action | Absorbs | Effort |
|---|---|---|---|
| PL-20 | **Replace the checkbox list with a planning table:** columns order, customer and area, expected date, items count, value, to collect, stock status, bill status, risk badges. Filters and search. Selection shows running totals (orders, quantity, value, to collect) | extends OG-15 | L |
| PL-21 | **Order detail drawer** from any row: customer and contact, full item list with stock per line, bills and payments, customer money position, every risk with its reason. Read-only, no navigation away from planning | new | L |
| PL-22 | **Risk badges with plain wording** (not codes): "Customer over credit limit by ₹X", "3 items short of stock". Blocks cannot be ticked and show why; warns can be ticked and ask for a reason on save | new | M |
| PL-23 | **Route detail uses the same summary:** per-stop card shows items, bill, amount to collect, and risks, with the dispatcher-friendly layout from OG-10 | OG-10, OG-20 | M |
| PL-24 | **Grouping helpers:** group by area or pincode, show suggested combine groups already computed, and highlight stops with missing coordinates. No new optimisation | route_combine | S |
| PL-25 | **Add to existing route** from the planning table and from the sales order list | OG-15 | M |
| PL-26 | **Load list for the godown** generated from the same summary: items and quantities grouped by product across the route, per-stop breakdown, stock short markers | OG-04, RT-29 | M |
| PL-27 | **Terminology and labels** for every status, risk and action, English and Hindi | OG-40, WP-8 | S |
| PL-28 | **Help entry:** how to read a planning row, what each warning means, who can override | OG-42 | S |

### C. Tests and safeguards

| ID | Action | Effort |
|---|---|---|
| PL-30 | Backend tests for every risk code: positive, negative and boundary (exactly at limit, exactly at e-way threshold, stock exactly equal, expiry on the day) | M |
| PL-31 | Query-count test on the summary builder: fixed number of queries for 1, 20 and 100 orders (guards against N+1, since the customer risk snapshot loops invoices) | S |
| PL-32 | Permission tests: cost and margin masked for a role without financial reports; another company's orders never appear | S |
| PL-33 | Consistency test: the risks shown at planning equal the risks enforced at add and at start for the same data | S |
| PL-34 | Web tests: blocked rows cannot be ticked, warns require a reason, totals update, drawer shows the same facts as the table | M |
| PL-35 | Golden end-to-end: plan a route from the table with one warning acknowledged, start it, confirm the manifest shows the acknowledgement | M |

## 7. Decisions (all taken, 2026-10-14)

| ID | Decision |
|---|---|
| DEC-P1 | Draft orders cannot be routed. Confirmed orders, or orders with a completed challan only. Owner may override with a reason |
| DEC-P2 | Stock shortage is a **Warn**; the check runs again at start |
| DEC-P3 | Acknowledgements are stored in **a new structured table** (one record per stop and risk, Q-2). Differs from the earlier recommendation (notes plus audit event) |
| DEC-P4 | Over-credit and credit-hold are **Warn** with a manager or owner reason |
| DEC-P5 | Customer money data is visible under the **same rule as Customer 360**; read that rule when PL-01 is built and reuse it, do not restate it |
| DEC-P6 | "Area" is the pincode, with city and state from the customer record (default, not asked) |
| Q-4 | Challans on routes is a **separate later project**; this plan covers orders only |

## 8. Deliberately not planned (needs data or capability that does not exist)

Weight or volume loading and vehicle capacity (no product weight or vehicle fields), delivery time windows, road-distance optimisation and maps, traffic or ETAs, driver phone contact on the route, customer notifications, automatic route building. List these as backlog with the missing data named.

## 9. Order of work

1. PL-03 (risk table) and PL-01 (summary builder), with PL-30 to PL-32 alongside.
2. PL-02, PL-04, PL-05, PL-06 (the backend enforces what the summary shows).
3. PL-09, PL-10, PL-07, PL-08.
4. PL-20, PL-21, PL-22, then PL-23, PL-24, PL-25.
5. PL-26, PL-27, PL-28, then PL-33 to PL-35.

Do after the shared stock work (WP-2, WP-6, WP-4/8) has landed, because the risks `already_on_route`, `fully_shipped_invoiced` and `not_ready` depend on the corrected counters and status rules.

## 10. Acceptance

A dispatcher planning tomorrow's routes can, without leaving the screen:
1. See every order that is ready, with customer, area, items, value, stock position, bill status and what must be collected.
2. See, for each order, what is risky about it in plain words (credit, overdue, stock, missing contact, expiry, e-way) and who can override.
3. Not add an order that is cancelled, blocked, already routed or delivered, and be told why.
4. Add a risky order only by acknowledging the risk with a reason that appears on the route and the load list.
5. Start the route only after the checks pass again at that moment.
6. See route totals (orders, quantity, value, to collect, warnings) before dispatch.

And in tests: the planning view, the add rule and the start rule always agree, the summary uses a fixed number of queries, and no user sees cost or another company's data they should not.

## 11. Effort

Backend A: about 11 to 15 days (PL-06 now includes a migration). Screens B: about 10 to 14 days. Tests C: about 4 to 6 days. In addition to the shared hardening work already planned. The summary builder (PL-01) and the planning table (PL-20) are the largest and most valuable pieces.
