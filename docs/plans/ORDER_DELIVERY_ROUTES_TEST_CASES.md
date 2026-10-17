# Order-to-delivery and delivery routes — test case catalogue

**Date:** 2026-10-14
**Status:** READY TO EXECUTE (v1.0). No test files have been written or run yet and no code has changed. Work from section 1A (execution guide), then the case tables. Write each release's tests first and watch them fail, then fix. Companion: [ORDER_DELIVERY_ROUTES_EXECUTION_PLAN.md](ORDER_DELIVERY_ROUTES_EXECUTION_PLAN.md) (tasks T-x.x use these case IDs).
**Covers:** [ORDER_TO_DELIVERY_HARDENING_PLAN.md](ORDER_TO_DELIVERY_HARDENING_PLAN.md) (H-xx, WP-xx), [DELIVERY_ROUTES_REVIEW_AND_ACTION_ITEMS.md](DELIVERY_ROUTES_REVIEW_AND_ACTION_ITEMS.md) (RT-xx), [DELIVERY_ROUTES_OFFICE_GODOWN_LOOP.md](DELIVERY_ROUTES_OFFICE_GODOWN_LOOP.md) (OG-xx), [DELIVERY_ROUTE_PLANNING_HARDENING.md](DELIVERY_ROUTE_PLANNING_HARDENING.md) (PL-xx). Decisions: [ORDER_DELIVERY_ROUTES_DECISIONS.md](../decisions/ORDER_DELIVERY_ROUTES_DECISIONS.md).

## 1. How these tests fit the existing suites

| Convention (verified in the repo) | Use |
|---|---|
| Backend tests live in `backend/tests/`, files `test_*.py`, `pytestmark = pytest.mark.django_db` | All backend cases |
| Fixtures: `tenant_a`, `tenant_b` (each with `.company`, `.client`, `.owner`); helpers `make_customer`, `make_product`, `add_stock`, `create_draft_invoice` in `tests/conftest.py` | Reuse; do not invent new tenant setup |
| API style: `tenant.client.post("/api/v1/sales/orders/", {...}, format="json")` then assert on `resp.data` and on `StockBalance` / `StockMovement` | Behaviour tests |
| Service style: call `SalesNotesService`, `RouteService` directly with `tenant.owner` | Rule and edge tests |
| Markers: `regression` (permanent anti-regression for a fixed bug, `tests/regression/`), `workflow` (`tests/workflows/`), `postgres` (needs row locking), `no_invariant_check` (only for deliberately broken states) | Every fixed H-item gets a `regression` test; chains get `workflow`; locking cases get `postgres` |
| Invariant sweep runs automatically after each test (`core.invariants.assert_all_invariants`) | Stock and ledger invariants are asserted for free; do not disable it |
| Existing related files to extend rather than duplicate: `test_next_batch_so_challan.py`, `test_sales_order_guards.py`, `personas/test_pj_route_pod.py`, `personas/test_pj_route_sequencing.py`, `test_route_sequencing_api.py`, `test_route_profit.py`, `test_route_optimization.py`, `tenancy/test_route_isolation_matrix.py`, `test_quotation_*.py` | Add cases there when the topic matches |
| Web tests are co-located Vitest files (`*.test.tsx`); golden Playwright specs in `web/e2e-golden/` | Screen and end-to-end cases |
| Web type-check is `cd web && npx tsc -b`; lint must stay at 0 errors; OpenAPI snapshot and web types must be regenerated when an API field changes (CI diffs both) | Gate for every web or API change |
| Concurrency and idempotency tests are Postgres-only | Marked `postgres` |

**ID scheme:** `TC-<package>-<nn>`. **Type:** U unit/service, A API, W workflow (multi-step chain), R regression, P postgres/concurrency, V web component (Vitest), E end-to-end golden. **Reproduce-first:** until the fix lands, the case is marked `xfail(strict=True)` (backend) or `it.fails` (web) so the suite stays green and flips loudly when fixed.

## 1A. Execution guide (read first)

**Run commands** (from `E:\Bizboard`)

| What | Command |
|---|---|
| One backend file | `cd backend && pytest tests/<file>.py -q` (add `--create-db` once after a migration) |
| One case | `cd backend && pytest tests/<file>.py -k "<case id or name>" -q` |
| Postgres-only cases | run in the CI Postgres lane; locally they are skipped (marker `postgres`), not deleted |
| Full backend (CI parity) | `cd backend && pytest -m "not flaky_quarantine and not slow and not llm_accuracy" -q` |
| Strict invariants | `cd backend && INVARIANTS_STRICT=1 pytest tests/workflows/ tests/tenancy/ tests/gst/ -q` |
| One web file | `cd web && npx vitest run src/pages/sales/<File>.test.tsx` |
| All web | `cd web && npm run test:run`; then `npx tsc -b` and `npm run lint` |
| Golden e2e | `cd web && npm run test:e2e:golden` |

**Protocol for every case**
1. Create the test with the case ID in its name (for example `test_tc_wp1_01_...`) and a docstring giving the finding ID.
2. Mark it `@pytest.mark.xfail(strict=True, reason="<H-xx>")` (backend) or `it.fails` (web) before the fix; run; confirm it fails for the stated reason, not because of a setup error.
3. After the fix, remove the mark; the case must pass with the invariant sweep on (never use `no_invariant_check` unless the case builds a deliberately broken state, and say why in the docstring).
4. `pytest-randomly` shuffles order in CI: no case may depend on another case's data or on run order. Build state with `tenant_a`, `tenant_b` and the `conftest.py` helpers.
5. Fixed findings also get a permanent copy in `tests/regression/` (marker `regression`), named in section 6.

**Files to create or extend, by release** (create in this order; cases listed in section 2/3/4)

| Release | Backend files | Web / e2e files | Case groups |
|---|---|---|---|
| R0 | all files below as xfail only | all web files below as `it.fails` only | every case, failing first |
| R1 | `tests/test_so_reservation_release_once.py`, extend `tests/test_sales_order_guards.py` | none | 2.1, 2.2 |
| R2 | extend `tests/test_sales_order_guards.py` (search, field, list filter) | `SalesOrdersPage.test.tsx`, `SalesOrderEditorPage.test.tsx`, `routeStatusLabels.test.ts` (new), challan editor test (add if missing), `QuickEntryPage.test.tsx` | 2.6, 2.7, 3 (WP4, WP8), E2E-02, E2E-06 |
| R3 | `tests/test_order_conversion_fidelity.py`, `tests/test_order_partial_shipments.py`, extend `tests/test_next_batch_so_challan.py` | `DeliveryRoutesPage.test.tsx` | 2.3, 2.4, 2.5, 2.8, WF-01, WF-04, E2E-03 |
| R4 | `tests/test_route_rules.py`, extend `tests/personas/test_pj_route_pod.py`, `tests/tenancy/test_route_isolation_matrix.py` | none | 2.9, 2.13 |
| R5 | `tests/test_route_collections.py`, manifest content test | `DeliveryRoutesPage.test.tsx`, cashier screen test (new), `SalesOrdersPage.test.tsx` | 2.10, 3 (RT-V), WF-02, E2E-01, E2E-07 |
| R6 | `tests/test_route_return_loop.py` | `DeliveryChallansPage` returns tests | 2.11, WF-03, E2E-05 |
| R7 | `tests/test_route_planning_risks.py`, `tests/test_route_planning_summary.py`, migration test | `RoutePlanningTable.test.tsx` (new) | 2.12, 3 (PL), E2E-04 |

**Release test gate:** every case for the release passes (no leftover xfail), the full backend suite and strict-invariants lane are green, Vitest is green, `tsc -b` and lint are 0 errors, OpenAPI snapshot and web types are clean, and the tracker in the execution plan (section 7) is updated with case results.

**Data notes for authors**
- Order setup: `POST /api/v1/sales/orders/` then `.../confirm/`; challan: `.../orders/<id>/convert-to-challan/` then `.../delivery-challans/<id>/complete/`; invoice: `.../delivery-challans/<id>/convert/` then complete; route: `DeliveryRoute` + `DeliveryRouteStop` via `RouteService`.
- Stock assertions read `StockBalance` (`on_hand`, `reserved`, `available`) and `StockMovement`; set `company.stock_on_delivery_challan` explicitly in cases that depend on it (both values).
- Credit cases: set `Customer.credit_limit` and enable `ENABLE_ORDER_GATES` in the company flags.
- Time-dependent cases (overdue 60 days, expiry, late, e-way threshold 50,000) use the frozen-clock opt-in in `conftest.py`.

## 2. Backend cases

### 2.1 Stock reservation (H-01, H-02, H-04) — hardening WP-1, WP-2, WP-6; RT-12

New file `tests/test_so_reservation_release_once.py` (R, W). Common setup: two orders (A and B) for the same product, stock 20, both confirmed so `reserved` = A + B.

| ID | Type | Scenario | Expected |
|---|---|---|---|
| TC-WP1-01 | R | A=10, B=5. Ship A in two challans (4 then 6). Complete challan 1, convert it to an invoice, complete the invoice | `reserved` = B (5) + A's unshipped remainder (6) = 11; never below 11 (H-01) |
| TC-WP1-02 | R | Same as 01, then complete challan 2 and its invoice | `reserved` = 5 (only B); A is `CONVERTED` |
| TC-WP1-03 | A | Direct order-to-invoice (no challan), complete the invoice | Reservation released exactly once (path unchanged) |
| TC-WP1-04 | A | Full challan (all 10), convert to invoice, complete invoice | No second release (order already `CONVERTED`); `reserved` = 5 |
| TC-WP1-05 | A | Challan from a DRAFT order (no reservation held), complete, invoice | `reserved` does not go negative; no effect on B |
| TC-WP1-06 | U | "Still held" function: order qty 10, completed challans 4, completed invoices 0, draft invoice 3 | held = 6 (draft invoice still holds until it completes) |
| TC-WP1-07 | U | Same function, completed invoice 3 after a draft | held = 3 |
| TC-WP2-01 | R | Route IN_TRANSIT, stop for fully shipped and completed challan, mark stop FAILED | B's `reserved` unchanged (H-02) |
| TC-WP2-02 | A | Stop FAILED on order with unshipped remainder 6 | Exactly 6 released, once |
| TC-WP2-03 | A | FAILED to DELIVERED to FAILED on the same stop | Released once (`stock_released_at` guard) |
| TC-WP2-04 | A | Stop FAILED when order is DRAFT | No release, no error |
| TC-WP6-H04-01 | R | Partial challan (4 of 10) then `rebuild_balance` | `reserved` = 6 (not 0, not 10) |
| TC-WP6-H04-02 | R | Product unit change with a `PARTIALLY_CONVERTED` order owing quantity | Blocked, message names the order |
| TC-WP6-H04-03 | R | Same with a fully converted, delivered order | Not blocked |

### 2.2 Credit exposure (H-03) — WP-3, DEC-3

Extend `tests/test_sales_order_guards.py`. Company with `ENABLE_ORDER_GATES` on. Customer limit 1000.

| ID | Type | Scenario | Expected |
|---|---|---|---|
| TC-WP3-01 | R | Posted invoice 400; completed challan 500 (no invoice); new order 200, confirm | Blocked: 1100 > 1000 (H-03) |
| TC-WP3-02 | A | Owner confirms the same with a non-blank reason | Allowed; override recorded; copied to the invoice later |
| TC-WP3-03 | A | Non-owner with a reason | Still blocked |
| TC-WP3-04 | A | Challan then converted to an invoice, completed | Exposure = 400 + 500 once, not twice |
| TC-WP3-05 | A | `PARTIALLY_CONVERTED` order with remainder 300 | Only 300 counted, not the full order total |
| TC-WP3-06 | A | Customer with limit 0 (none) and a large uninvoiced challan | Never blocked |
| TC-WP3-07 | A | Gates flag off | No new blocking (behaviour unchanged) |
| TC-WP3-08 | U | Exposure exactly equals the limit | Allowed (boundary: `>` not `>=`) |
| TC-WP3-09 | A | Cancelled challan | Not counted |
| TC-WP3-10 | A | Two customers | One customer's challan never counts for the other |

### 2.3 Order and challan conversions (H-10, H-11) — WP-5, DEC-6

New file `tests/test_order_conversion_fidelity.py`.

| ID | Type | Scenario | Expected |
|---|---|---|---|
| TC-WP5-01 | R | Company price mode INCLUSIVE; order to invoice | Invoice `price_mode` INCLUSIVE; totals equal the order's (H-10) |
| TC-WP5-02 | R | Order to challan to invoice (INCLUSIVE) | Same totals at every step |
| TC-WP5-03 | A | Quotation to order | Order mode is the documented default; order, invoice totals match the quotation to the paisa (existing quotation tests stay green) |
| TC-WP5-04 | R | NON_GST (Bill of Supply) order to challan | Challan totals have no tax (H-11) |
| TC-WP5-05 | R | NON_GST order, challan converted to invoice | Invoice type NON_GST |
| TC-WP5-06 | A | GST order, regular company with GSTIN | Challan taxed; invoice GST |
| TC-WP5-07 | A | Standalone challan (no order) | Registration-based rule unchanged |
| TC-WP5-08 | A | Composition or unregistered company, GST order | Registration gate still refuses GST tax invoice at completion |

### 2.4 Partial shipments and several invoices (H-12, H-13) — WP-6, DEC-1; RT-13; OG-36

New file `tests/test_order_partial_shipments.py` (W). Order of 10 units.

| ID | Type | Scenario | Expected |
|---|---|---|---|
| TC-WP6-01 | W | Challan 4, complete, invoice, complete; challan 6, complete, invoice, complete | Both invoices complete; order `CONVERTED`; `reserved` back to baseline; stock moves once per unit (H-12) |
| TC-WP6-02 | A | Challan 4 shipped, then direct invoice for 7 | Refused: only 6 left |
| TC-WP6-03 | A | Direct invoice for 6 of 10, then challan for 5 | Refused: only 4 left |
| TC-WP6-04 | A | Two partial invoices from the order | `converted_invoice` is the latest; helper returns both |
| TC-WP6-05 | A | Cancel order with one completed and one draft invoice | Refused; message names both |
| TC-WP6-06 | A | Cancel order after the draft invoice is deleted and quantity given back | Allowed; reservation released |
| TC-WP6-07 | A | Complete second challan after the first was invoiced (old CR-120 block) | Allowed now |
| TC-WP6-08 | A | Convert second challan to an invoice | Allowed; no "already has an invoice" error |
| TC-WP6-09 | A | Hand-linked challan (WP-9) with quantity above remaining | Refused (see 2.5) |
| TC-WP6-10 | A | Route profit with two invoices on one stop | Revenue and COGS include both (H-13) |
| TC-WP6-11 | A | Cancel one of the two completed challans | Order status and counters roll back for that part only |
| TC-WP6-12 | P | Two concurrent converts each asking for the last 6 units | One succeeds, one refused; remainder never negative |
| TC-WP6-13 | P | Concurrent challan complete and direct invoice complete | No double stock out |

### 2.5 Hand-linked challans (H-08 backend) — WP-9

| ID | Type | Scenario | Expected |
|---|---|---|---|
| TC-WP9-01 | A | Create a challan with `sales_order` set and lines within remaining | Created; `shipped_quantity` increases |
| TC-WP9-02 | A | Lines above remaining | Refused with the remaining quantity in the message |
| TC-WP9-03 | A | Delete the draft challan | Quantity given back |
| TC-WP9-04 | A | Order from another company | Refused (existing company-scope check) |

### 2.6 Order status actions and cancel (H-05, H-06 backend) — WP-4, DEC-4

| ID | Type | Scenario | Expected |
|---|---|---|---|
| TC-WP4-B01 | A | Order list `status=` with several values (`DRAFT,CONFIRMED,PARTIALLY_CONVERTED`) | Returns all three; unknown value refused |
| TC-WP4-B02 | A | Cancel a CONFIRMED order (permission `CanCancelDocuments`) | Cancelled; reservation released; quotation conversion released |
| TC-WP4-B03 | A | User without cancel permission | 403 |
| TC-WP4-B04 | A | Cancel a PARTIALLY_CONVERTED order | Refused with the reason |
| TC-WP4-B05 | A | Idempotent retry of confirm with the same key | Same response; reservation made once |

### 2.7 Search and read-only fields (H-16, H-07) — WP-10, WP-8

| ID | Type | Scenario | Expected |
|---|---|---|---|
| TC-WP10-01 | A | Search by order number, challan number, route number, vehicle, driver name | Each found |
| TC-WP10-02 | A | User without sales-view permission | No sales rows |
| TC-WP10-03 | A | Other company's order | Never returned (also add to `tests/tenancy/`) |
| TC-WP8-B01 | A | `fulfilment_state` for: no challan; completed challan, no invoice; invoiced | `none`, `shipped_not_invoiced`, `invoiced` |
| TC-WP8-B02 | A | Query count for a page of 50 orders | Constant (no per-row query) |
| TC-WP8-B03 | A | OpenAPI snapshot | Regenerated and equal to a fresh run (CI drift check) |

### 2.8 Failed stop on an invoiced order (H-14) — WP-7, DEC-5, RT-11, OG-34

| ID | Type | Scenario | Expected |
|---|---|---|---|
| TC-WP7-01 | A | Stop FAILED, order has an active completed invoice | Response carries the invoice number; no document created; stock/return effect as before |
| TC-WP7-02 | A | Stop FAILED, no invoice | No invoice message |
| TC-WP7-03 | A | Invoice cancelled | No message |
| TC-WP7-04 | A | Challan already converted to an invoice, stop FAILED | Challan return not created; message points to Sales Return (no 500) |

### 2.9 Route rules (Tier 1) — RT-01..04, RT-08, RT-09, RT-14, RT-15; OG-01..03, OG-07, OG-08, OG-11..13

Extend `tests/personas/test_pj_route_pod.py`, add `tests/test_route_rules.py`.

| ID | Type | Scenario | Expected |
|---|---|---|---|
| TC-RT01-01 | R | Complete a route with a PENDING stop | Refused; message lists the pending stops (OG-12) |
| TC-RT01-02 | A | All stops delivered or failed | Completes |
| TC-RT01-03 | A | Route with no stops | Cannot be started (existing) and cannot be completed |
| TC-RT02-01 | R | Cancel a PLANNED route | Cancelled; orders free to route again |
| TC-RT02-02 | A | Cancel an IN_TRANSIT route without reason | Refused |
| TC-RT02-03 | A | Cancel IN_TRANSIT with reason and pending stops | Cancelled; pending stops released back to ready; delivered stops stay delivered |
| TC-RT02-04 | A | Cancel a COMPLETED route | Refused |
| TC-RT02-05 | A | Permission: needs the route write permission | 403 otherwise |
| TC-RT03-01 | R | PATCH vehicle or date on an IN_TRANSIT or COMPLETED route | Refused; only actual cost on closing is allowed |
| TC-RT03-02 | A | PATCH notes on a PLANNED route | Allowed |
| TC-RT04-01 | R | Same order on two planned routes | Second add refused with the other route's number |
| TC-RT04-02 | R | Order already DELIVERED on a completed route | Refused |
| TC-RT04-03 | A | Order on a CANCELLED route | Allowed |
| TC-RT04-04 | A | Add of several orders where one is invalid | None added (all-or-nothing) |
| TC-RT08-01 | R | DELIVERED to FAILED without a reason | Refused |
| TC-RT08-02 | A | With a reason | Allowed; audit shows who, when, from, to |
| TC-RT08-03 | A | Any change to PENDING after leaving it | Refused (existing) |
| TC-RT09-01 | A | Same vehicle on two routes the same day | Warning returned; blocking only if decided; same driver likewise |
| TC-RT09-02 | A | Same vehicle on different days | No warning |
| TC-RT14-01 | A | Filters: vehicle, driver, status, date range | Correct subsets; paged |
| TC-RT15-01 | A | New route | Has a number from creation; numbers unique per company |
| TC-OG13-01 | R | Office-recorded delivery (`completion_source = OFFICE`) with no code and no code issued | Delivered; marked "recorded by office"; audit has the user |
| TC-OG13-02 | R | Code already issued, then office-recorded delivery | Delivered; issued code cleared; the old code cannot confirm the stop again |
| TC-OG13-03 | A | Phone/driver path with a stored code and no code supplied | Still refused (driver flow unchanged) |
| TC-OG13-04 | A | Wrong code five times | Locked (existing behaviour kept) |

### 2.10 Route money (OG-20..23, RT-22..24) — DEC-R2 (link only)

New file `tests/test_route_collections.py`.

| ID | Type | Scenario | Expected |
|---|---|---|---|
| TC-OG21-01 | A | Collections recorded; cashier from a different user counts equal | Handover VERIFIED; route can close |
| TC-OG21-02 | A | Counted differs | Handover VARIANCE; variance amount correct; route can close only after a reason is recorded |
| TC-OG21-03 | A | Same user recorded and counts (not owner or manager) | Refused (`handover_same_person`) |
| TC-OG21-04 | A | Collections edited after the count | Closing refused until recounted |
| TC-OG21-05 | A | No money collected | No count required |
| TC-OG22-01 | A | Link a receipt of the right customer and the counted amount | Linked; shown on the stop |
| TC-OG22-02 | A | Receipt of another customer | Refused |
| TC-OG22-03 | A | Receipt from another company | Refused |
| TC-OG22-04 | A | Receipt amount differs from the count | Link allowed only with a reason; difference recorded |
| TC-OG22-05 | A | The system never creates a receipt on its own | Receipt count unchanged after a count and a close |
| TC-OG20-01 | A | Amount to collect on a stop: order only; invoiced; paid by advance | Total, invoice balance, balance after advance |
| TC-OG23-01 | A | Route closed with variance | Appears in the attention list until a reason is recorded |

### 2.11 Goods return loop (OG-30..34, RT-07) — DEC-O3

New file `tests/test_route_return_loop.py` (W).

| ID | Type | Scenario | Expected |
|---|---|---|---|
| TC-OG31-01 | W | Stop FAILED on a completed, uninvoiced challan | Draft return created; appears in the "goods to check in" list with route, customer, age |
| TC-OG32-01 | A | Partial refusal: returned 3 of 10 | Return has 3, not 10 |
| TC-OG32-02 | A | Returned quantity above shipped | Refused |
| TC-OG33-01 | W | Complete the return | Stock back on the shelf; order reopens to ready; shipped count reduced; reservation held again (DEC-O3) |
| TC-OG33-02 | W | Re-route the reopened order and deliver | Delivered once; no oversell; stock out once |
| TC-OG33-03 | A | Return completed when stock is not posted on challan (company setting off) | No stock movement; order still reopens; reservation restored |
| TC-OG33-04 | A | Return completed twice (retry) | Second refused; no double restock |
| TC-OG33-05 | W | Two orders share a product; one fails and returns | Other order's reservation untouched |
| TC-OG34-01 | A | Challan already invoiced | Return refused with the Sales Return pointer; no 500 |
| TC-OG30-01 | A | Delivered stop, no invoice | Listed as delivered-not-invoiced |
| TC-OG30-02 | A | Invoice then created | Disappears from that list |

### 2.12 Route planning (PL-01..PL-10) — DEC-P1, P2, P4, P5, P3 (acknowledgement table)

New files `tests/test_route_planning_risks.py`, `tests/test_route_planning_summary.py`.

**Risk evaluator (one case per code, with boundary):**

| ID | Type | Scenario | Expected |
|---|---|---|---|
| TC-PL03-01 | U | Cancelled order | `order_cancelled` Block |
| TC-PL03-02 | U | Order on another active route / delivered | `already_on_route` Block |
| TC-PL03-03 | U | Blocked or inactive customer | `customer_blocked` Block |
| TC-PL03-04 | U | Draft order | `not_ready` Block; owner with reason may add; non-owner cannot |
| TC-PL03-05 | U | Nothing left to deliver | `fully_shipped_invoiced` Block |
| TC-PL03-06 | U | Chronic overdue (> 60 days, over the floor) | `credit_hold` Warn |
| TC-PL03-07 | U | Exposure exactly at limit, then one rupee over | No flag, then `over_credit_limit` Warn |
| TC-PL03-08 | U | Overdue invoices, severity from collection status | `customer_overdue` with severity |
| TC-PL03-09 | U | Stock available exactly equals quantity; then one less | No flag; then `stock_short` Warn |
| TC-PL03-10 | U | The order's own reservation | Not counted against itself |
| TC-PL03-11 | U | Batch expiring on the day, day before, day after | Boundary behaviour per company window |
| TC-PL03-12 | U | No address, no phone, no pincode | `no_address` Warn, `no_phone` Warn, `no_pincode` Info |
| TC-PL03-13 | U | Order of 60,000 with no challan or invoice | `eway_needed` Info; with a challan lacking e-way: Warn |
| TC-PL03-14 | U | Margin below threshold; user without financial-report access | `low_margin` shown only to permitted users |
| TC-PL03-15 | U | Partly delivered, past expected date, unverified GSTIN | `partial_delivery`, `late`, `gstin_unverified` Info |

**Summary builder and endpoints:**

| ID | Type | Scenario | Expected |
|---|---|---|---|
| TC-PL01-01 | A | Candidate list for 1, 20 and 100 orders | Number of queries is the same for all three (N+1 guard) |
| TC-PL01-02 | A | Customer with 30 invoices on 10 orders | Risk snapshot computed once for that customer |
| TC-PL01-03 | A | Other company's orders | Never returned |
| TC-PL01-04 | A | User without financial-report access | Cost and margin fields are null |
| TC-PL01-05 | A | Customer money data visibility | Follows the Customer 360 rule |
| TC-PL02-01 | A | Filters: date, status, customer, pincode, ready only, has risk | Correct subsets; paged; stable sort |
| TC-PL04-01 | A | Add a Block order | Refused with code and plain message |
| TC-PL04-02 | A | Add a Warn order without acknowledgement | Refused; with acknowledgement and reason: added |
| TC-PL04-03 | A | One bad order in a list of five | None added |
| TC-PL05-01 | A | Start with an unresolved Block | Refused |
| TC-PL05-02 | A | Warning that appeared after planning (stock sold meanwhile) | Start requires a new acknowledgement |
| TC-PL05-03 | A | Customer blocked after planning | Start refused |
| TC-PL06-01 | A | Acknowledgement | One record per stop and risk: code, level, reason, who, when; audit event written |
| TC-PL06-02 | A | Acknowledgement without a reason | Refused |
| TC-PL06-03 | A | Stop removed | Its acknowledgements are kept for audit or removed with it, per the decision recorded when built |
| TC-PL06-04 | A | Migration | Forward and backward apply cleanly; `makemigrations --check` clean |
| TC-PL07-01 | A | Route totals | Orders, lines, quantity, value, to collect, warning count correct |
| TC-PL08-01 | A | Order edited or customer blocked after planning | Route read shows the new risk (computed at read) |
| TC-PL09-01 | A | Vehicle or driver clash same day | Warning |
| TC-PL10-01 | A | Order from a failed stop | Shows "reconfirm needed"; cannot be re-added until reconfirmed |
| TC-PL33-01 | A | Consistency | For the same data, risks shown at planning equal risks enforced at add and at start |

### 2.13 Tenancy, permissions, idempotency, audit (cross-cutting)

| ID | Type | Scenario | Expected |
|---|---|---|---|
| TC-X-01 | A | Extend `tests/tenancy/test_route_isolation_matrix.py` to every new endpoint (candidates, preflight, cancel, acknowledgements, receipt link, goods-to-check-in) | No cross-company read or write; add paths to the matrix and keep `_route_matrix_unprobed.txt` accurate |
| TC-X-02 | A | Each write endpoint with a role that lacks sales-create | 403; read endpoints allow sales-view only |
| TC-X-03 | A | Subscription write gate | New write endpoints respect `SubscriptionWritesAllowed` |
| TC-X-04 | A | Idempotency: confirm, cancel route, start, complete, link receipt retried with the same key | One effect |
| TC-X-05 | A | Audit: cancel, status change, office delivery, acknowledgement, receipt link | Event with actor, time, before and after |
| TC-X-06 | A | Closed accounting period | Stock-posting challan complete and cancel respect the period gate (existing G-22 tests stay green) |

## 3. Web cases (Vitest)

Extend `SalesOrdersPage.test.tsx`, `SalesOrderEditorPage.test.tsx`, `DeliveryRoutesPage.test.tsx`, `DeliveryChallansPage`/editor tests (add if missing), `QuickEntryPage.test.tsx`; new `RoutePlanningTable.test.tsx`, `routeStatusLabels.test.ts`.

| ID | Type | Scenario | Expected |
|---|---|---|---|
| TC-WP4-V01 | V | Action matrix, one case per row: DRAFT gates off/on, CONFIRMED, PARTIALLY_CONVERTED, CONVERTED, CANCELLED | Buttons exactly as the matrix; list and editor agree (same helper) |
| TC-WP4-V02 | V | Gates off: Confirm, then the row | Create invoice, Create challan, Cancel appear (H-05) |
| TC-WP4-V03 | V | Quick Entry auto-confirm then open the order | Order has actions |
| TC-WP4-V04 | V | "Open" filter | Returns draft, confirmed and partly processed; "Closed" returns converted and cancelled (H-06) |
| TC-WP4-V05 | V | Cancel a confirmed order | Dialog says stock will be released; confirm calls cancel once |
| TC-WP4-V06 | V | User without cancel permission | No cancel button |
| TC-WP8-V01 | V | Status chips for CONFIRMED and PARTIALLY_CONVERTED | Readable labels, not `status.CONFIRMED` (H-07) |
| TC-WP8-V02 | V | Label coverage test: every status value of Quotation, SalesOrder, DeliveryChallan, DeliveryRoute, DeliveryRouteStop, challan return exists in `en.ts` and `hi.ts` | Fails CI if one is missing |
| TC-WP8-V03 | V | Order with `fulfilment_state = shipped_not_invoiced` | Shows "Shipped" |
| TC-WP8-V04 | V | Action names | "Create invoice" / "Create challan" / "Create order" used consistently on quotation, order, challan screens |
| TC-WP8-V05 | V | Challan editor order picker | Lists confirmed and partly processed orders (and draft when gates off) |
| TC-WP8-V06 | V | Hindi switch | New strings render; none fall back to keys |
| TC-WP8-V07 | V | Create-route dialog (H-09, interim until the planning table) | Lists confirmed, partly processed and shipped (completed-challan) orders with a status chip; no drafts; cancelled orders never |
| TC-WP7-V01 | V | Failed stop on an invoiced order | Message names the invoice and points to Sales Returns |
| TC-RT-V01 | V | Complete route with pending stops | Error shows the stops; "mark failed" offered |
| TC-RT-V02 | V | Stop card: delivered requires receiver; amounts validate (no negatives; UPI needs reference) | Inline errors; no request sent |
| TC-RT-V03 | V | Office-recorded delivery without a code | Succeeds; label "recorded by office" |
| TC-RT-V04 | V | Cashier count screen | Expected vs counted, variance reason required, same-person error shown plainly |
| TC-RT-V05 | V | Link receipt: only receipts of this customer listed | Wrong-customer receipt not offered |
| TC-RT-V06 | V | Route list | Progress, collection due vs collected, "needs attention" first; profit banner hidden without permission |
| TC-RT-V07 | V | Cancel route | Reason required for in-transit; dialog; list refreshes |
| TC-RT-V08 | V | Phone width (375 px): stop cards stack, buttons are at least 44 px, no horizontal scroll | Layout assertions (RT-31) |
| TC-RT-V09 | V | Add to existing route from the order list | Chooses a planned route; no new route created |
| TC-PL20-V01 | V | Planning table columns and filters | Order, customer, area, date, items, value, to collect, stock, bill, risk badges |
| TC-PL20-V02 | V | Selection totals | Running orders, quantity, value, to collect update on tick |
| TC-PL22-V01 | V | Block row | Checkbox disabled, reason shown |
| TC-PL22-V02 | V | Warn row | Ticking asks for a reason; saved reason is sent |
| TC-PL21-V01 | V | Order drawer | Shows the same facts as the row; read-only; closes without losing selection |
| TC-PL24-V01 | V | Group by pincode | Groups and missing-coordinate marker |
| TC-PL26-V01 | V | Load list | Items grouped by product across the route; short-stock markers |
| TC-X-V01 | V | Accessibility: dialogs have titles, focus returns, status text not by colour alone | `jest-axe`/existing a11y helpers pass |
| TC-X-V02 | V | `tsc -b` and lint | 0 errors |

## 4. End-to-end golden (Playwright, real backend)

Add to `web/e2e-golden/` next to `route-pod-golden.spec.ts` and `comp005-route-profit.spec.ts`.

| ID | Type | Scenario | Expected |
|---|---|---|---|
| TC-E2E-01 | E | Quote, order, confirm, challan, complete, invoice, plan a route, start, deliver, count cash, link receipt, close | Stock, receivable and receipt agree at each step; no raw status keys on screen |
| TC-E2E-02 | E | Quick Entry order with auto-confirm, gates off; create invoice from the list | Works end to end (H-05 path) |
| TC-E2E-03 | E | Two-challan partial shipment with an invoice for each | Both invoices complete; stock out once per unit |
| TC-E2E-04 | E | Planning with one warning acknowledged | Reason appears on route and manifest; start re-checks |
| TC-E2E-05 | E | Failed stop, goods back, return completed, order reopens, second route delivers | Delivered once; no oversell |
| TC-E2E-06 | E | Cancel a confirmed order | Reserved stock returns on the stock screen |
| TC-E2E-07 | E | Phone viewport run of the route detail | All stop actions usable |

## 5. Workflow contracts (`tests/workflows/`, marker `workflow`)

| ID | Chain | Notes |
|---|---|---|
| TC-WF-01 | Order to challan to invoice to payment (cash and credit) | Extends the existing workflow list; asserts stock and ledger invariants |
| TC-WF-02 | Order to route to delivery to cash count to receipt link | Money and stock agree |
| TC-WF-03 | Failed delivery to return to reopen to re-route | Reservation and stock consistent at every step |
| TC-WF-04 | Quotation partial conversion to order to partial challans | Quotation ledger and order counters agree |

## 6. Regression register

Every fixed finding gets a permanent `regression` test named after its ID, kept in `tests/regression/`:

| Finding | Test |
|---|---|
| H-01 | `test_regression_h01_double_reservation_release.py` (TC-WP1-01, 02) |
| H-02 | `test_regression_h02_failed_stop_release.py` (TC-WP2-01) |
| H-03 | `test_regression_h03_uninvoiced_challan_exposure.py` (TC-WP3-01) |
| H-04 | `test_regression_h04_partial_order_reserved.py` (TC-WP6-H04-01, 02) |
| H-10, H-11 | `test_regression_h10_h11_conversion_fidelity.py` |
| H-12, H-13 | `test_regression_h12_h13_partial_invoices.py` |
| RT-01..04, RT-08 | `test_regression_route_rules.py` |
| OG-13 | `test_regression_office_delivery_without_code.py` |

## 7. Suggested additions to the quality registers (proposal; not edited)

Do not edit the canonical registers until the work starts, then add:
- **`docs/TESTING_STRATEGY.md` gap register:** new rows for "reservation conservation across SO, challan, invoice and route" and "route cash and receipt agreement", each mapped to the L-layers above.
- **`docs/FREEZE_SCOPE_COVERAGE.md`:** wire each SUPPORTED order, challan and route item to its gating case IDs above.
- **`qos/backlog/`:** one item per work package, citing the case IDs, so `qos-lint` can check them.
- **`docs/CROSS_FLOW_TEST_CHECKLIST.md`:** add rows for convert and cancel on routes and for the return-reopen path.

## 8. Counts and order

About 160 backend cases, 37 web cases, 7 end-to-end, 4 workflows. Write them in this order, each group failing first: 2.1 and 2.2 (stock and credit), 2.6 and 3 (screens), 2.3 to 2.5 and 2.8 (conversions), 2.9 to 2.11 (routes), 2.12 (planning), 2.13 (cross-cutting), then section 4 and 5 once the screens exist.

## 9. Definition of done for the test work

- Every H-item, RT item and OG/PL item with behaviour has at least one case above, and the tracker in the hardening plan (section 7) links to its case IDs.
- No case depends on another case's data; each builds its own tenant state.
- Postgres-only cases run in CI on Postgres; locally they are skipped, not deleted.
- `pytest -q`, `cd web && npx vitest run`, `npx tsc -b`, lint, and the OpenAPI drift check all pass before each release in the hardening plan's section 10.

## 10. Cases added during execution (2026-10-14)

| ID | Case | Test |
|---|---|---|
| TC-X-03 | Cancelling a completed direct invoice: order back to confirmed, stock reserved again, pointer cleared | `test_so_reservation_release_once.py::test_cancelling_a_completed_direct_invoice_reopens_the_order_and_holds_stock_again` |
| TC-X-04 | Cancelling one of two direct invoices leaves the order partly processed | `test_so_reservation_release_once.py::test_cancelling_one_of_two_direct_invoices_leaves_the_order_partly_processed` |
| TC-WP3-06 | Credit-impact report lists only customers with uncovered shipped challans | `test_credit_exposure_challans.py::test_tc_wp3_affected_customer_report_lists_only_uncovered_shipments` |
| TC-X-01b | Preflight, cancel, cashier count, receipt link, add-orders and start on another tenant's route never succeed or change it | `tests/tenancy/test_route_isolation_matrix.py::test_route_planning_and_cashier_actions_are_isolated` |
| TC-X-01c | Planning candidates never list another tenant's orders | `tests/tenancy/test_route_isolation_matrix.py::test_route_candidates_never_list_another_tenants_orders` |
| TC-PL-W1..W23 | Planning table: columns, blocked rows, warnings need a reason, totals, filters, drawer | `web/src/pages/sales/routes/PlanningTable.test.tsx` |
| TC-PL-P1..P7 | Preflight panel: clean start, blocked stop, accept and start, accepted reasons, errors, read-only | `web/src/pages/sales/routes/PreflightPanel.test.tsx` |
| TC-PL-T1..T6 | Planning rules and helpers | `web/src/pages/sales/routes/planningTypes.test.ts` |
