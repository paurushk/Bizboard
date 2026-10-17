# Order-to-delivery and delivery routes — decisions

**Date:** 2026-10-14
**Recorded from:** the founder's answers in chat on 2026-10-14, to questions asked one by one.
**Plans these decisions unblock:**
[ORDER_TO_DELIVERY_HARDENING_PLAN.md](../plans/ORDER_TO_DELIVERY_HARDENING_PLAN.md),
[DELIVERY_ROUTES_REVIEW_AND_ACTION_ITEMS.md](../plans/DELIVERY_ROUTES_REVIEW_AND_ACTION_ITEMS.md),
[DELIVERY_ROUTES_OFFICE_GODOWN_LOOP.md](../plans/DELIVERY_ROUTES_OFFICE_GODOWN_LOOP.md),
[DELIVERY_ROUTE_PLANNING_HARDENING.md](../plans/DELIVERY_ROUTE_PLANNING_HARDENING.md).
The four plans were re-reviewed and updated to these decisions (revision 2, 2026-10-14); this file remains the record. Where a decision differs from the recommendation, the "Effect" column says what changes.

## A. Decisions taken

| ID | Question | Decision | Taken as recommended? | Effect on the plans |
|---|---|---|---|---|
| DEC-1 | One order shipped in several challans, an invoice for each? | **Yes** | Yes | WP-6 goes ahead: replace the "order already has an invoice" blocks with a per-line remaining-quantity check; OG-33, OG-36 unblocked |
| DEC-3 | Do shipped but uninvoiced challans count toward credit exposure? | **Yes** | Yes | WP-3 goes ahead, under `ENABLE_ORDER_GATES`; list affected customers before enabling |
| DEC-4 | Cancel a confirmed order from the screen? | **Yes, with a confirm dialog** | Yes | WP-4 includes Cancel on CONFIRMED orders; dialog says stock will be released |
| DEC-2 | Label for a shipped, not yet invoiced order | **"Shipped"** | Yes | WP-8: label only, stored status stays CONVERTED |
| DEC-5 | Failed delivery on an already invoiced order | **Warn only** | Yes | WP-7 / RT-11: message names the invoice and points to Sales Return; no automatic documents. Also settles DEC-R4 |
| DEC-6 | Challan invoice type from an order | **Inherit from the order** | Yes | WP-5: standalone challans keep the registration-based rule |
| DEC-P1 | Can a draft order be routed? | **No; owner override with reason** | Yes | OG-01 / PL-04: confirmed orders or orders with a completed challan only. Also settles DEC-R7 |
| DEC-P2 | Stock shortage when planning | **Warning, re-checked at start** | Yes | PL-03 / PL-05: acknowledge with a reason |
| DEC-P4 | Over credit limit or credit hold when planning | **Warning; manager or owner reason** | Yes | PL-03: same rule as the order-gate override |
| DEC-O1 | Office records a delivery without the customer's code | **Yes, audited, marked "recorded by office"** | Yes | OG-13 goes ahead |
| DEC-O3 | Goods come back after a failed delivery | **Godown completes the return; the order reopens to ready and stock is held again** | Yes | OG-33 goes ahead. Also settles DEC-O2 (godown inspects first) |
| DEC-P5 | Who sees customer money data in the planner | **Same as Customer 360 today** | Yes | Confirm the exact Customer 360 rule when PL-01 is built |
| DEC-R2 | When does driver-collected money become a customer receipt | **Only link a receipt the cashier made** | **No** (recommended: create at cashier confirmation) | OG-22 / RT-24 changes from "create the receipt" to "link an existing receipt". No automatic receipt creation. Reduces risk and effort |
| DEC-R3 | Should routes also dispatch challans, not only orders | **Yes, challans too** | **No** (recommended: not now) | See section B: this is new capability, not hardening |
| DEC-R1 | Driver tool for now | **Web page on a phone** | **No** (recommended: office only, no driver tool) | RT-31 (phone-width pass for the route detail) comes back into scope |
| DEC-P3 | Where a planning acknowledgement is stored | **A new structured field** | **No** (recommended: stop notes plus audit event) | See section B: needs a migration |

## B. Consequences of the four decisions that differ from the recommendation

1. **DEC-R3 (challans on routes).**
   - A stop can no longer reference only an order. It must reference an order or a challan (a stop with both is not allowed), which needs a model change and a migration (`DeliveryRouteStop.delivery_challan`), a new uniqueness rule, and updates to every place that reads `stop.sales_order`: rollup, manifest, delivery slip, failed-stop release, trip profit, combine and sequencing suggestions, search, and the planning candidates list.
   - It also means a stop for a standalone challan has no order to take a reservation or address from, so the stop needs its own address source (the challan's `delivery_address`, falling back to the customer).
   - This is the biggest item in the whole list and is **new capability**. The earlier instruction was "no new feature scope; harden". Treat it as a separate work package after the order-route hardening, not inside it. Reference: RT-40.
   - Challans that are already converted to an invoice, or that have returns, need explicit rules before work starts (open question Q-1).
2. **DEC-P3 (structured acknowledgement field).** Needs a migration. The recommended shape is a child record per stop (stop, risk code, level, reason, who, when) so risks can be reported on, rather than a text column. Reference: PL-06. Open question Q-2.
3. **DEC-R1 (web page on a phone).** RT-31 is in scope: stacked stop cards, large tap targets, and offline-safe actions on the route detail. Customer delivery codes and proof photos (RT-06, RT-10, RT-21) were out of the office/godown scope; with a phone-usable page they come back as candidates and need a scope decision (open question Q-3).
4. **DEC-R2 (link, not create).** The stop already has a receipt link field. The work is to let the cashier pick or enter an existing receipt for the customer, check the amount against what was counted, and show the link. Variance (counted vs receipt) still needs a reason.

## C. Decisions not asked; default applied

These follow from the answers above or were low risk. Say so if you want any changed.

| ID | Question | Default | Why |
|---|---|---|---|
| DEC-R4 | Auto-create a return/credit note on a refused delivery | No, warn only | Follows DEC-5 |
| DEC-R5 | Route optimisation as a priority | No; keep behind its flag | Not part of hardening |
| DEC-R6 | Post logistics cost to the books | No | Not part of hardening |
| DEC-R7 | Does "dispatchable" need a challan | A confirmed order is enough | Follows DEC-P1 |
| DEC-O2 | Godown inspects returned goods before restock | Yes | Follows DEC-O3 |
| DEC-P6 | How "area" is defined | Pincode, with city and state shown | No area field exists |

## D. Open questions raised by these decisions

| ID | Question | Why it matters |
|---|---|---|
| Q-1 | For routes that carry challans (DEC-R3): are challans that are already invoiced, or that have a return, routable? | Decides the stop eligibility rules and the stock/return effects |
| Q-2 | For DEC-P3: structured field as a child record per stop (recommended) or a single JSON column? | Affects reporting and migration size |
| Q-3 | With the web page as the phone tool (DEC-R1): are delivery codes and proof photos back in scope for this round? | Reopens RT-06, RT-10, RT-21 |
| Q-4 | Is DEC-R3 (challans on routes) to be done in this round after the order-route hardening, or scheduled as its own project? | Largest single item; do not mix with hardening |

## D2. Answers to the open questions (founder, in chat, 2026-10-14)

| ID | Decision | Taken as recommended? | Effect |
|---|---|---|---|
| Q-1 | Routable challans: **also already-invoiced challans** (so: completed challans, whether or not invoiced) | **No** (recommended: completed, not invoiced, no return) | Draft challans stay out. A failed or refused stop on an invoiced challan cannot use the challan-return path (it is refused once a challan is converted), so it falls under DEC-5: warn, name the invoice, point to Sales Return. Trip profit and "amount to collect" must read the invoice balance for such stops. A challan with a completed return still needs a rule (open question Q-5). |
| Q-2 | Acknowledgements: **one record per stop and risk** | Yes | PL-06 becomes a new table (stop, risk code, level, reason, who, when) with a migration. The stop notes field is not used for this. |
| Q-3 | Phone work this round: **phone-width layout only** | Yes | RT-31 in scope. Delivery code dead end (RT-06 beyond OG-13), code sending (RT-21) and proof-photo loss (RT-10) stay out of this round. |
| Q-4 | Challans on routes: **separate project after hardening** | Yes | RT-40 / DEC-R3 is not part of the hardening release. Section B item 1 applies to that project. Its design must follow Q-1: invoiced challans are routable. |

### New open question

| ID | Question | Why it matters |
|---|---|---|
| Q-5 | In the challans-on-routes project, may a challan that already has a completed return be routed again? | Decides whether returned quantity is excluded from the stop and from "amount to collect" |

## E. What can start now

Everything except the challans-on-routes project (Q-4: separate, later). In the planned order: reproduce each finding as a failing test (RT-00 / WP-0), then the stock and credit group (WP-1 to WP-3), the screens group (WP-4, WP-8), the conversion group (WP-5 to WP-7), and the route planning items (PL-03, PL-01, then the rest). Execution has not started.
