# Delivery Routes — review and action items

**Date:** 2026-10-14
**Status:** REVIEW AND ACTION LIST ONLY. No code changed, nothing executed.
**Revision 2 (2026-10-14):** re-reviewed and updated with the founder's decisions ([../decisions/ORDER_DELIVERY_ROUTES_DECISIONS.md](../decisions/ORDER_DELIVERY_ROUTES_DECISIONS.md)). Changes: RT-24 is now "link the cashier's receipt" (not create); RT-31 phone-width layout is in scope; RT-06, RT-10, RT-21 are out of this round; RT-40 (challans on routes) is a separate later project and must allow invoiced challans; section 6 shows each decision's outcome; RT-16 now has a real owner (hardening plan WP-10 includes routes). The "layman" list below is otherwise unchanged.
**Companion to:** [ORDER_TO_DELIVERY_HARDENING_PLAN.md](ORDER_TO_DELIVERY_HARDENING_PLAN.md). That plan is **unchanged**. Where an item overlaps it, the item says so (for example "= plan WP-2"). Do not do the same work twice.
**Basis:** code reading of the working tree: `sales/models.py`, `route_service.py`, `route_views.py`, `route_serializers.py`, `route_combine.py`, `route_optimization.py`, `route_profit_service.py`, `pdf/note_documents.py` (manifest), `pod_slip.py`, `DeliveryRoutesPage.tsx`, `api/legacy/sales.ts`, `offline/photoOutbox.ts`. Each finding should be reproduced with a test before it is fixed (RT-00).

## 1. Current state in plain words

The backend is further along than the screen. It already has: stops with delivered, failed, rejected and returned statuses; customer OTP for proof of delivery; recipient name and photo; cash and UPI collection per stop; a cashier count with variance and a same-person guard; stop sequencing suggestions; expected and realised trip profit; a manifest PDF and a per-stop delivery slip.

The screen exposes a fraction of that. From the web app a dispatcher can create a route, add orders, start it, change a stop's status from a dropdown, and complete it. They **cannot**: send a delivery code, record cash or UPI collected, run the cashier count, cancel a route, add orders to an existing route, pick a driver from the staff list, or see what each stop is worth or whether it is paid. The mobile app has no route screens at all.

So routes behave like a checklist of order numbers, not a delivery tool. The value a business expects from this module is "who is delivering what today, did it arrive, did we collect the money, what is left". The data model can answer most of that. The screens and a few rules cannot yet.

## 2. How to read the list

- **Tier 1 — Harden:** wrong or unsafe behaviour today. Do these first.
- **Tier 2 — Make usable:** the backend already supports it; the screen or the rule is missing. Low risk, high everyday value.
- **Tier 3 — Add value:** genuinely new capability. Each needs a decision before work starts. Not part of the hardening plan.
- Effort: S ≤ 0.5 day, M 1 to 2 days, L 3 to 5 days, tests included.
- "Depends" lists items or plan packages that must land first.

## 3. Tier 1 — Harden

| ID | Action item | Why (what happens today) | Where | Effort | Depends |
|---|---|---|---|---|---|
| RT-00 | Reproduce every Tier 1 finding as a failing test first | All findings below come from reading code | `backend/tests/personas/test_pj_route_pod.py`, `test_route_sequencing_api.py`, new route test files | S | none |
| RT-01 | Refuse to complete a route that still has PENDING stops | `complete_route` checks only the route status. A route can be completed with undelivered stops and no outcome recorded | `route_service.py::complete_route` | S | RT-00 |
| RT-02 | Add a cancel-route action with stock-safe rules | Status `CANCELLED` exists but no endpoint or button can reach it. A wrong route can only be deleted while PLANNED; once started it can never be undone | `route_views.py`, `route_service.py` | M | RT-00 |
| RT-03 | Lock a route's fields once it leaves PLANNED | Standard update is open: vehicle, driver, date, costs and notes can be changed on a completed route, so realised profit snapshots go stale | `route_serializers.py` (validate by status), `route_views.py` | S | RT-00 |
| RT-04 | Stop one order being on two active routes | `add_orders` only checks the same route. An order can be dispatched twice, or sit on a completed route and be added again | `route_service.py::add_orders` | S | RT-00 |
| RT-05 | Only allow orders that are really ready to go | Any non-cancelled order is accepted, including unconfirmed drafts that hold no stock and orders with no challan or invoice. Define "dispatchable" once and enforce it on add and on start | `route_service.py::add_orders`, `start_route` | M | plan WP-4/WP-8 (shared status rules) |
| RT-06 | Fix the delivery-code dead end (**out of this round**, Q-3; the office path is OG-13) | Issuing a code returns "sent" even when nothing was sent (customer has no phone or no WhatsApp opt-in). The stop then needs a code nobody can read, and cannot be marked delivered | `route_service.py::issue_delivery_otp`, `_dispatch_delivery_otp`, `route_views.py::issue_otp` | M | RT-00 |
| RT-07 | Make a failed stop safe to retry | A failed stop releases the order's reserved stock, but the order stays confirmed. Adding it to a new route re-dispatches goods nothing is holding. Re-reserve on re-route or mark the order so it must be reconfirmed | `route_service.py::_release_failed_stop`, `add_orders` | M | plan WP-2, RT-04 |
| RT-08 | Make stop status changes a controlled path | Any move is allowed except back to PENDING: delivered to failed to delivered. Each change should record who and when, and a delivered stop should not be silently flipped | `route_service.py::set_stop_status` | M | RT-00 |
| RT-09 | Stop double-booking a vehicle or driver | Two routes can use the same vehicle or driver on the same day with no warning | `route_service.py` / serializer validation | S | RT-00 |
| RT-10 | Keep proof photos from being lost (**out of this round**, Q-3) | The photo is queued offline and attached later by calling set-stop-status again. If the route is completed first the call is refused and the photo never attaches. The re-call also overwrites the delivered time. The note is stored as the literal text "photo" | `offline/photoOutbox.ts`, `DeliveryRoutesPage.tsx`, `route_service.py::set_stop_status` | M | RT-08 |
| RT-11 | Report the failed-stop effect on invoices and returns | Failed stop on an invoiced order changes nothing on the invoice; the draft challan return it creates is easy to miss | `route_service.py`, route detail screen | S | = plan WP-7 |
| RT-12 | Release stock once only on failed stops | = plan **WP-2**. Do not duplicate | `route_service.py::_release_failed_stop` | S | plan WP-2 |
| RT-13 | Count partial invoices in trip profit | = plan **WP-6** (all invoices per order, not the latest pointer) | `route_profit_service.py` | M | plan WP-6 |
| RT-14 | Route list and filters must scale and be searchable | Only `status` and `date` filters; no vehicle, driver or order search; no pagination check | `route_views.py::get_queryset` | S | none |
| RT-15 | Give routes a number from creation | The number is allocated only on start, so planned routes show blank in lists, search and the manifest | `route_service.py::_ensure_number`, `perform_create` | S | none |
| RT-16 | Add routes to global search | Quotations are searchable; routes are not | `search/views.py` | S | = plan WP-10 |

## 4. Tier 2 — Make usable (backend exists, screen or rule missing)

| ID | Action item | What the user gets | Where | Effort | Depends |
|---|---|---|---|---|---|
| RT-20 | Rebuild the route detail screen around the stop, not the page | Today receiver name, code and "from office" are shared boxes above the list and the Delivered option is disabled until the box is filled. Replace with one stop card: customer, address, phone, order value, status, and a single "Mark delivered" form (receiver, code, photo, cash, UPI) | `DeliveryRoutesPage.tsx` | L | RT-08 |
| RT-21 | Add "Send delivery code" per stop, with a visible fallback (**out of this round**, Q-3) | The code field exists but nothing can send a code. Add the button, show "sent to +91…" or "no WhatsApp: ask customer to read code / mark as office delivery with reason" | `DeliveryRoutesPage.tsx`, `api/legacy/sales.ts` | M | RT-06 |
| RT-22 | Record cash and UPI collected on the stop | The backend stores amounts and the UPI reference; no field exists on screen, so the cashier handover is always empty | `DeliveryRoutesPage.tsx` | M | RT-20 |
| RT-23 | Cashier handover screen | Backend has verify, variance and a same-person rule; no screen. Show expected vs counted, variance reason, and block route completion with a plain message when collections are unverified | `DeliveryRoutesPage.tsx` | M | RT-22 |
| RT-24 | **Link the cashier's receipt to the collection** (decision DEC-R2: link only, never create) | Collected money is recorded on the stop but the order still shows unpaid. The cashier makes the receipt in the existing receipts flow; the stop lets them pick that receipt for the customer, checks the amount against what was counted, and shows the link. Variance between the count and the receipt needs a reason. No automatic receipt creation | stop card, `payments` receipt lookup | M | RT-22, RT-23 |
| RT-25 | Add and remove orders on an existing route | Orders can be added only when creating a route or from the order list (which makes a new route each time). Add "Add orders" on the route detail and "Add to existing route" in the order list | `DeliveryRoutesPage.tsx`, `SalesOrdersPage.tsx` | M | RT-04, RT-05 |
| RT-26 | Pick the driver from staff; keep the free-text fallback | `driver` (staff link) exists on the model; the form has only a name box. Pre-fill name and phone from the staff record | route create form | S | none |
| RT-27 | Show progress and money on the list | Add stops (done/total), collection due, collected, and a clear "needs attention" marker (failed stops, unverified cash). Remove the profit info banner for people who cannot see profit | `DeliveryRoutesPage.tsx` | M | RT-01 |
| RT-28 | Show payment and invoice status on each stop | A driver should see "cash to collect ₹X" or "already paid". Read order total, invoice status and balance from existing fields | stop card, `route_serializers.py` (read-only fields) | M | RT-20 |
| RT-29 | Make the manifest usable on the road | Add customer phone, amount to collect, item lines with quantities, notes, and driver/vehicle contact. Today it shows number, customer, address and status only | `pdf/note_documents.py::render_route_manifest` | M | RT-28 |
| RT-30 | Fix terminology and status labels | Routes use Planned / In transit / Completed; stops Pending / Delivered / Failed / Returned. Add labels for every value (stops include `REJECTED`, which has no dropdown entry), keep wording consistent with the order and challan screens | `i18n/en.ts`, `hi.ts`, `DeliveryRoutesPage.tsx` | S | = plan WP-8 |
| RT-31 | Mobile-width pass for the route detail (**in scope**: web page on a phone is the driver tool for now, DEC-R1; layout only, Q-3) | Drivers use phones. Stack stop cards, large tap targets, offline-safe actions. Mobile app has no route screens; decide whether the web page is the driver tool (see DEC-R1) | route detail, `offline/*` | M | RT-20 |
| RT-32 | Help and FAQ | One short "How delivery routes work" entry: who can do what, what the codes are, what happens on a failed delivery, what the cashier check is | `pages/help/faqContent.tsx` | S | RT-20..23 |

## 5. Tier 3 — Add value (needs a decision; not hardening)

| ID | Idea | Business value | Decision needed |
|---|---|---|---|
| RT-40 | Route stops can reference a **challan** as well as an order (decided: yes, as a **separate project after hardening**, Q-4; completed challans are routable whether or not invoiced, Q-1; invoices alone are not planned) | Lets challan-only sales be dispatched; needs `DeliveryRouteStop.delivery_challan`, a one-of-order-or-challan rule, a migration and changes in manifest, slip, failed-stop release, trip profit, search and planning. Open: Q-5 (challan with a completed return) | decided |
| RT-41 | Driver-only login view: "my route today" | Drivers see only their stops; today everyone with sales access sees every route | DEC-R1 |
| RT-42 | Delivered stop updates the order and challan | A delivered stop currently changes nothing elsewhere. Could mark "delivered" on the order and prompt invoicing | DEC-R3 |
| RT-43 | Auto-create sales return or credit note on a refused delivery | Stops today only draft a challan return | DEC-R4 |
| RT-44 | Map and road-distance based sequencing | Current sequencing uses pincode and a nearest-neighbour method; no real distances or time windows | DEC-R5 |
| RT-45 | Vehicle capacity, driver shifts, time windows | Prevent overloaded routes | DEC-R5 |
| RT-46 | Customer tracking link and "arriving" message | Fewer failed deliveries and calls | DEC-R5 |
| RT-47 | Route reports: on-time rate, failure reasons, cost per stop, driver cash variance | Management view of the delivery operation | DEC-R5 |
| RT-48 | Fuel and toll expense posting from a route | Logistics cost is a typed number today and posts nowhere | DEC-R6 |

## 6. Decisions to make

| ID | Question | Recommendation |
|---|---|---|
| DEC-R1 | Who is the driver's tool: the web page on a phone, or the mobile app? | **Decided: web page on a phone, layout only** (RT-31). Driver-only view (RT-41) later. |
| DEC-R2 | Should collections on a stop create a customer receipt automatically, on confirmation, or only link one the cashier made? | **Decided: only link one the cashier made** (RT-24). |
| DEC-R3 | Should routes dispatch challans and invoices as well as orders? | **Decided: challans too, as a separate project after hardening.** Invoices alone are not planned. |
| DEC-R4 | Should a refused delivery draft a credit note or return? | **Decided: warn only** (hardening plan WP-7, DEC-5). |
| DEC-R5 | Is route optimisation a priority? | No. The existing pincode method is enough until dispatchers ask for it. Keep behind its flag. |
| DEC-R6 | Should logistics cost post to the books? | Not now; keep as a trip-profit input. |
| DEC-R7 | Does "dispatchable" (RT-05) require a challan, or only a confirmed order? | **Decided with DEC-P1:** a confirmed order (or one with a completed challan) is enough; drafts need an owner override with a reason. |

## 7. How this ties into dependent modules

| Module | Interaction today | Gap | Items |
|---|---|---|---|
| Sales Order | Stop references an order; failed stop releases its reservation | Reservation not restored on retry; ready-to-dispatch statuses missing from picker; order on two routes | RT-04, RT-05, RT-07, plan WP-8 |
| Delivery Challan | Failed stop drafts a challan return against the latest challan | Delivered stop does not touch the challan; standalone challans cannot be routed | RT-11, RT-40, RT-42 |
| Sales Invoice / Ledger | Trip profit reads the order's invoice | Collections never reach the customer's account; partial invoices miscounted | RT-13, RT-22, RT-24 |
| Payments / Receipts | Stop can link a receipt | Not offered on screen, no creation flow | RT-24 |
| Inventory | Failed stop releases stock | Double release; no re-reserve | RT-07, RT-12 |
| Customers | Phone and WhatsApp opt-in decide delivery codes | No fallback when absent; phone not on manifest | RT-06, RT-21, RT-29 |
| Staff / Payroll | `driver` links an Employee | Screen uses free text only | RT-26 |
| Search, Help, Mobile | — | Routes not searchable; no help entry; no mobile screens | RT-16, RT-32, RT-31 |

## 8. Suggested order of work

1. **RT-00**, then **RT-01, RT-03, RT-04, RT-09, RT-15** (small, safe rules that stop bad data).
2. **RT-06, RT-08, RT-07, RT-10, RT-02** (the code, status and retry paths).
3. Shared with the hardening plan, once: **RT-12 (WP-2), RT-11 (WP-7), RT-13 (WP-6), RT-16 (WP-10), RT-30 (WP-8)**.
4. **RT-20, RT-21, RT-22, RT-23, RT-25, RT-26** (the screen rebuild; do RT-20 first, the rest hang off it).
5. **RT-27, RT-28, RT-29, RT-31, RT-32** (visibility and everyday polish).
6. **RT-24** after DEC-R2 is answered.
7. Tier 3 only after Tier 1 and 2 are live and the founder has usage data.

## 9. Acceptance for "hardened and usable"

A dispatcher, driver and cashier can, using only the web app:
1. Build a route from ready orders, assign vehicle and staff driver, and see no double-booking.
2. Start it and see each stop with address, phone and amount to collect.
3. Send a delivery code, or use a clear office-delivery fallback, and mark each stop delivered with receiver, photo and amounts.
4. Mark a stop failed, see the stock and return effect, and re-route it safely.
5. Have the cashier count cash and UPI, see variance, and only then close the route.
6. See, on the route list, what is done, what is left and what needs attention.
7. Print a manifest a driver can actually use.

And, in tests: no path double-releases stock, loses a photo, completes a route with open stops, or edits a closed route.

## 10. Out of scope here

The Order, Challan, credit and screens work is in the other plan. This list does not change that plan.
