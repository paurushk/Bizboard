# Delivery routes — office and godown loop (hardening scope)

**Date:** 2026-10-14
**Status:** SCOPED PLAN. Nothing executed, no code changed.
**Revision 2 (2026-10-14):** re-reviewed and updated with the founder's decisions ([../decisions/ORDER_DELIVERY_ROUTES_DECISIONS.md](../decisions/ORDER_DELIVERY_ROUTES_DECISIONS.md)). Changes: OG-22 is now "link the cashier's receipt", not "create the receipt" (DEC-R2); OG-13 states what to do when a code was already issued; OG-05 is a warning, not a block (DEC-R7/P1); the phone-width layout of the route detail is in scope (DEC-R1) while codes and photos stay out (Q-3); section 6 shows the decisions taken; effort for section C is reduced.
**Builds on:** [DELIVERY_ROUTES_REVIEW_AND_ACTION_ITEMS.md](DELIVERY_ROUTES_REVIEW_AND_ACTION_ITEMS.md) (RT-xx items) and [ORDER_TO_DELIVERY_HARDENING_PLAN.md](ORDER_TO_DELIVERY_HARDENING_PLAN.md) (WP-x). Both are unchanged; this document selects from them and adds the loop-closing items they lack (OG-xx).

## 1. Scope

**In scope: people at the office and the godown.**
- *Dispatcher / order desk:* builds routes, assigns vehicle and driver, starts and closes routes, records outcomes the driver phones in.
- *Godown / store:* picks and loads goods, checks goods back in when a delivery fails.
- *Cashier / accounts:* counts driver cash and UPI, posts receipts, follows up invoices.
- *Owner / manager:* sees what is open, what failed, what is short.

**Out of scope this round: the driver and the road.** Delivery codes sent to customers, proof photos (and their loss), driver-only login, maps and optimisation, customer tracking. Outcomes are entered by office staff (the stop's "from office" path already exists). **In scope by decision DEC-R1:** the route detail is usable at phone width (RT-31, layout only), because the web page on a phone is the driver's tool for now.

**Hardening only.** No new screens beyond completing what already exists, no new statuses or fields unless an item says so.

## 2. The loop, and where it is open today

```
1 Order confirmed ─▶ 2 Godown picks and loads ─▶ 3 Route planned and started
        ▲                                                │
        │                                                ▼
8 Route closed ◀── 7 Cash counted ◀── 6 Money posted ◀── 4 Outcome recorded (office)
        ▲                                                │
        │                                                ▼
        └──── 9 Failed/refused goods back in godown ◀── 5 Invoice follows delivery
```

| Step | Closed today? | What is open (verified in code) |
|---|---|---|
| 1 → 2 | Partly | Routes accept unconfirmed orders that hold no stock; godown has no list of what to load, and the manifest has no item lines or quantities |
| 3 | Partly | An order can be on two routes; a vehicle or driver can be double-booked; a started route cannot be cancelled |
| 4 | Partly | Office can set a stop's status, but a route can be completed with stops still pending, and a delivered stop can be flipped back |
| 5 | Open | Delivering does nothing to the invoice; nobody is told an order is delivered and not yet billed |
| 6 | Open | Cash and UPI amounts can be stored on a stop but no screen records them, and they never reach the customer's account |
| 7 | Open | The cashier count exists in the backend only; no screen |
| 8 | Partly | Closing needs the count only if amounts exist (so with no screen it is never needed) |
| 9 | Open | A failed stop drafts a challan return with **all** lines; nobody is alerted; the godown has no queue; completing the return restocks but does not reopen the order, so the order still reads "shipped" while goods sit on the shelf. If the challan was already invoiced, the return is refused and no other path is offered |

## 3. Action items

Legend: **RT/WP** = already defined in the other plans (do once, do not duplicate). **OG** = new here. Effort S ≤ 0.5 d, M 1–2 d, L 3–5 d.

### A. Before dispatch — office and godown agree on what goes out

| ID | Action | Source | Effort |
|---|---|---|---|
| OG-01 | **Dispatchable rule:** only confirmed orders (or orders with a completed challan) can be added to a route or start it. Say why on screen when refused. Closes the "route of orders with no stock held" hole | RT-05, plan WP-4/8 | M |
| OG-02 | **One order, one active route:** block adding an order that is on another planned or in-transit route, or already delivered | RT-04 | S |
| OG-03 | **Vehicle and driver clash warning** for the same day | RT-09 | S |
| OG-04 | **Godown load list:** extend the existing manifest PDF with item lines, quantities, unit and order total. Same document, more columns; no new report | RT-29 (office part) | M |
| OG-05 | **Pick-complete check at start:** a **warning** (not a block: a confirmed order is enough to be routed, DEC-R7) when a stop's order has no completed challan while the company posts stock on challan, so goods are not "out" in the system but still on the shelf (or the reverse). Acknowledged with a reason like other planning warnings | new | S |
| OG-06 | Give routes a number at creation so the load list and phone calls can refer to it | RT-15 | S |
| OG-07 | **Cancel a route** before it starts (return orders to ready) and after it starts (with a reason; stops left pending are released back to ready). Closes the "wrong route can never be undone" hole | RT-02 | M |
| OG-08 | **Lock the route** once it has started: vehicle, driver, date and costs are not editable on in-transit or closed routes except actual cost on close | RT-03 | S |

### B. During the trip — office records outcomes

| ID | Action | Source | Effort |
|---|---|---|---|
| OG-10 | **Office stop card:** one form per stop for outcome (delivered, failed, refused, returned), receiver name, reason, amount collected (cash and UPI with reference). Replaces the shared boxes above the list. Defaults to the office-recorded path | RT-20, RT-22 (office subset) | L |
| OG-11 | **Controlled status changes:** a delivered stop cannot be flipped without a reason, every change records who and when | RT-08 | M |
| OG-12 | **Block closing a route with pending stops;** list them in the message and offer "mark failed" per stop | RT-01 | S |
| OG-13 | **Delivery code is optional for office-recorded delivery (DEC-O1):** when the office records the outcome (`completion_source = OFFICE`), no customer code is required, the stop shows "recorded by office" with the recorder's name, and the audit log says so. **A code already issued is cleared** when the office path is used, so it cannot later confirm the same delivery (today `_verify_delivery_otp` rejects a blank code whenever a hash is stored, which is the dead end). The driver/phone path is untouched | RT-06 (office part) | S |
| OG-14 | **Route list with progress:** stops done / total, amount to collect vs collected, count of failed stops and unverified cash, "needs attention" first | RT-27 | M |
| OG-15 | **Add and remove orders on a planned route** from the route screen and from the order list ("add to existing route") | RT-25 | M |

### C. Money — cashier and accounts close the cash

| ID | Action | Source | Effort |
|---|---|---|---|
| OG-20 | **Show amount to collect per stop:** order total, invoice status and balance, from existing fields (read-only) | RT-28 | M |
| OG-21 | **Cashier count screen:** expected vs counted, variance and reason, with the existing different-person rule. Route cannot close until counted when money was collected | RT-23 | M |
| OG-22 | **Link the cashier's receipt to the collection (DEC-R2: link only):** after the count, the cashier picks the receipt they created in the existing receipts flow for this customer; the screen checks its amount against what was counted, shows the link on the stop, and asks for a reason if they differ. The system never creates the receipt. No new payment path | RT-24 | M |
| OG-23 | **Variance follow-up:** a route with a cash variance appears in the owner's "needs attention" list until someone records a reason | new, uses OG-14 | S |

### D. After the trip — invoice and stock close

| ID | Action | Source | Effort |
|---|---|---|---|
| OG-30 | **Delivered but not invoiced** shown on the route and on the order list, with a link to create the invoice from the order or challan. Display and link only, no automatic invoicing | new | M |
| OG-31 | **Godown return queue:** failed and refused stops create a draft return today; show these in one list ("Goods to check in") on the existing challan returns area, with route, customer, items and age. Add an attention marker so they are not forgotten | new (uses existing returns) | M |
| OG-32 | **Return what actually came back:** the stop form takes quantities returned per line (defaults to all) so a partial refusal creates a correct return, not a full one | new | M |
| OG-33 | **Completing a return reopens the order:** quantity back on the shelf must make the order show as not delivered, release the shipped count and re-reserve stock, so a re-route is safe. Today stock goes back but the order stays "shipped" and nothing holds the goods | plan WP-2/WP-6, RT-07 | L |
| OG-34 | **Invoiced order, failed delivery:** when the challan is already invoiced, the return is refused with no way forward. Show a plain message naming the invoice and send the user to Sales Return against it; do not auto-create documents | RT-11, plan WP-7 | S |
| OG-35 | **Stock release once only,** and release on failed stop only what is still held | RT-12, plan WP-2 | S |
| OG-36 | **Trip profit counts every invoice of the order,** not the latest | RT-13, plan WP-6 | M |

### E. Visibility and clarity for office users

| ID | Action | Source | Effort |
|---|---|---|---|
| OG-40 | Status labels everywhere (order confirmed and partly processed; stop refused; route planned/in transit/closed) and one verb per action | RT-30, plan WP-8 | S |
| OG-41 | Routes and orders searchable from the global search | RT-16, plan WP-10 | S |
| OG-42 | One help entry for office and godown: how an order reaches a route, who records outcomes, how cash is counted, what happens to failed goods | RT-32 | S |
| OG-43 | Hide the profit explanation banner from users who cannot see profit | RT-27 | S |

## 4. What is explicitly left out (driver and road)

Customer delivery codes and their sending (RT-06 beyond OG-13, RT-21), proof photo queue and loss (RT-10), driver-only login (RT-41), phone-width driver pass (RT-31), maps, capacity, time windows, tracking (RT-44 to RT-46). Keep these on the other list until the office loop works.

## 5. Order of work

1. **Reproduce** each item with a failing test first (RT-00 applies).
2. **Stop bad data in:** OG-01, OG-02, OG-03, OG-06, OG-08, OG-12.
3. **Stock correctness** (shared with the hardening plan, done once there): OG-35, OG-33 with WP-2 and WP-6.
4. **Close the office loop:** OG-10, OG-11, OG-13, OG-15, OG-07, then OG-14.
5. **Close the money:** OG-20, OG-21, then OG-22 after DEC-R2, then OG-23.
6. **Close the goods:** OG-31, OG-32, OG-34, OG-30.
7. **Clarity:** OG-04, OG-05, OG-36, OG-40 to OG-43.

## 6. Decisions (all taken)

| Decision | Taken (2026-10-14) |
|---|---|
| DEC-R2 | **Link only:** the cashier makes the receipt; the stop links it. Differs from the earlier recommendation (OG-22 reduced from L to M) |
| DEC-O1 | **Yes**, marked "recorded by office" with the recorder's name; audited |
| DEC-O2 | The godown completes the return after checking; stock returns on completion |
| DEC-O3 | **Yes**: completing the return reopens the order to ready and restores the reservation; the order desk sees it through the attention list |
| DEC-1 | **Yes** (one order, several challans, an invoice each). OG-33 and OG-36 are unblocked |
| DEC-5 | **Warn only** for a failed delivery on an invoiced order (OG-34) |
| DEC-R1 | Web page on a phone is the driver tool; layout only (RT-31) |
| Q-4 | Challans on routes is a separate later project; nothing here depends on it |

## 7. Acceptance — "the loop is closed" for office and godown

1. The dispatcher builds a route only from ready orders, sees no double-booking, prints a load list the godown can pick from.
2. The route cannot close with pending stops.
3. Every stop ends in a recorded outcome by a named person, and a delivered stop cannot be flipped without a reason.
4. Money collected is counted by a different person, posted to the customer's account, and variance is visible until explained.
5. Delivered-not-invoiced orders are visible with a link to bill them.
6. Goods that come back appear in one queue; completing the return restocks them and puts the order back to ready with stock held again.
7. Nothing in the loop releases or restocks the same unit twice, and trip profit counts every invoice.

## 8. Effort

About 10 to 14 engineer-days for A and B, 5 to 6 for C (OG-22 is now link-only), 6 to 9 for D, 2 to 3 for E, tests included, in addition to the shared hardening work (WP-2, WP-6, WP-7, WP-8, WP-10) that this list reuses rather than repeats.
