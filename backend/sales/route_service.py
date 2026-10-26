"""Delivery Route planning overlay (SO-only v1)."""

from __future__ import annotations

import logging
import secrets
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services.document_numbers import DocumentNumberService, resolve_series_gstin
from core.services.feature_flags import flag_enabled

from .expected_profit import expected_profit_for_order
from .models import DeliveryRoute, DeliveryRouteStop, RouteCashHandover, SalesOrder
from .route_optimization import SequencedStop, StopInput, get_route_optimizer
from .status_semantics import OPEN_RECEIVABLE_STATUSES

logger = logging.getLogger(__name__)

POD_OTP_MAX_ATTEMPTS = 5
POD_OTP_LOCK_SECONDS = 15 * 60


class RouteService:
    @staticmethod
    def _ensure_number(route: DeliveryRoute):
        if not route.number:
            route.number = DocumentNumberService.next_number(
                route.company, "DELIVERY_ROUTE", gstin=resolve_series_gstin(route.company),
                on_date=route.route_date,
            )
            route.save(update_fields=["number"])
        return route

    @staticmethod
    def rollup(route: DeliveryRoute) -> dict:
        # Plain .all() (no .select_related chained on the related manager) so
        # the viewset's prefetch_related("stops__sales_order__customer",
        # "stops__sales_order__items__product") is reused instead of
        # triggering a fresh, unprefetched query per route.
        stops = list(route.stops.all())
        order_ids = [s.sales_order_id for s in stops]
        profits = []
        expected = Decimal("0")
        for stop in stops:
            p = expected_profit_for_order(stop.sales_order)
            profits.append({"sales_order_id": stop.sales_order_id, **p, "stop_id": stop.id, "status": stop.status})
            expected += Decimal(str(p["expected_profit"]))
        return {
            "stop_count": len(stops),
            "order_ids": order_ids,
            "expected_profit": expected,
            "estimated_logistics_cost": route.estimated_logistics_cost,
            "actual_logistics_cost": route.actual_logistics_cost,
            "stops": [
                {
                    "id": s.id,
                    "sales_order": s.sales_order_id,
                    "order_number": s.sales_order.number,
                    "customer_name": s.sales_order.customer.name,
                    "delivery_address": s.sales_order.delivery_address,
                    "sequence": s.sequence,
                    "status": s.status,
                    "notes": s.notes,
                }
                for s in stops
            ],
            "per_order_expected_profit": profits,
        }

    @staticmethod
    @transaction.atomic
    def add_orders(
        route: DeliveryRoute,
        order_ids: list[int],
        user,
        *,
        acknowledgements=None,
        viewer=None,
        enforce_risks: bool = True,
    ):
        """Put orders on a planned route, refusing what cannot go and recording what was accepted.

        Every order is checked against the planning rules (``route_planning``): a Block stops the
        whole request (nothing is added), a Warn needs an acknowledgement with a reason in
        ``acknowledgements`` (``[{"order": id, "code": "...", "reason": "..."}]``), and a draft order
        is accepted only from the owner with a reason (DEC-P1). Accepted risks are kept on the stop.
        ``enforce_risks=False`` is for internal callers that already vouch for the orders.
        """
        from .route_planning import order_summaries, unresolved_risks, viewer_from_user

        route = DeliveryRoute.objects.select_for_update().get(pk=route.pk)
        if route.status != DeliveryRoute.Status.PLANNED:
            raise BusinessRuleError("Orders can only be added while the route is PLANNED.")
        seq = route.stops.count()
        orders_by_id = {
            o.id: o
            for o in SalesOrder.objects.filter(pk__in=order_ids, company=route.company)
            .select_related("customer", "warehouse")
            .prefetch_related("items__product")
        }
        existing_order_ids = set(
            DeliveryRouteStop.objects.filter(route=route, sales_order_id__in=order_ids)
            .values_list("sales_order_id", flat=True)
        )
        pending = []
        for oid in order_ids:
            order = orders_by_id.get(oid)
            if order is None:
                raise BusinessRuleError(f"Sales order {oid} was not found.")
            if oid in existing_order_ids or order in pending:
                continue
            pending.append(order)
        accepted: dict[int, dict[str, str]] = {}
        if enforce_risks and pending:
            viewer = viewer or viewer_from_user(route.company, user)
            given = RouteService._parse_acknowledgements(acknowledgements, by="order")
            summaries = order_summaries(route.company, pending, viewer=viewer, route=route)
            problems = []
            for order in pending:
                summary = summaries[order.pk]
                mine = given.get(order.pk, {})
                result = unresolved_risks(summary, set(mine), viewer)
                for kind in ("blocked", "not_allowed", "needs_ack"):
                    for item in result[kind]:
                        problems.append((kind, order, item))
                accepted[order.pk] = {
                    item["code"]: mine[item["code"]]
                    for item in summary["risks"]
                    if item["code"] in mine and viewer.may_accept(item["code"]) and item["level"] != "info"
                }
            if problems:
                first_kind, first_order, first = problems[0]
                first_label = first_order.number or f"#{first_order.pk}"
                code = {
                    "blocked": "route_order_blocked",
                    "not_allowed": "route_risk_not_allowed",
                    "needs_ack": "route_risk_needs_acknowledgement",
                }[first_kind]
                raise BusinessRuleError(
                    f"Sales order {first_label}: {first['message']}"
                    + (f" (and {len(problems) - 1} more problem(s))" if len(problems) > 1 else ""),
                    code=code,
                    extra={
                        "risks": [
                            {"order": order.pk, "order_number": order.number, "kind": kind, **item}
                            for kind, order, item in problems
                        ]
                    },
                )
        else:
            for order in pending:
                if order.status == SalesOrder.Status.CANCELLED:
                    raise BusinessRuleError("Cancelled orders cannot be added to a route.")
                RouteService._assert_not_on_another_route(order, route)
        added = []
        for order in pending:
            seq += 1
            stop = DeliveryRouteStop.objects.create(
                company=route.company,
                route=route,
                sales_order=order,
                sequence=seq,
                created_by=user,
                updated_by=user,
            )
            added.append(stop)
            RouteService._record_acknowledgements(route, stop, accepted.get(order.pk, {}), user)
        route.updated_by = user
        route.save(update_fields=["updated_by", "updated_at"])
        return added

    @staticmethod
    def _parse_acknowledgements(raw, *, by: str) -> dict[int, dict[str, str]]:
        """{order id or stop id: {risk code: reason}} from the request's list, validating each reason."""
        out: dict[int, dict[str, str]] = {}
        if not raw:
            return out
        if not isinstance(raw, list):
            raise BusinessRuleError("acknowledgements must be a list.")
        for row in raw:
            if not isinstance(row, dict):
                raise BusinessRuleError("Each acknowledgement needs an order, a risk code and a reason.")
            key = row.get(by) if row.get(by) is not None else row.get(f"{by}_id", row.get(f"{by}Id"))
            code = str(row.get("code") or "").strip()
            reason = str(row.get("reason") or "").strip()
            try:
                key = int(key)
            except (TypeError, ValueError) as exc:
                raise BusinessRuleError(f"Each acknowledgement needs a {by}.") from exc
            if not code or len(reason) < 3:
                raise BusinessRuleError("Each acknowledgement needs a risk code and a reason.")
            out.setdefault(key, {})[code] = reason[:500]
        return out

    @staticmethod
    def _record_acknowledgements(route, stop, accepted: dict[str, str], user):
        """Keep each accepted risk on the stop (table + audit): who accepted what, and why."""
        from core.services.audit import record_document_event

        from .models import RouteStopAcknowledgement
        from .route_planning import RISKS

        for code, reason in accepted.items():
            level = RISKS[code][0]
            RouteStopAcknowledgement.objects.update_or_create(
                stop=stop,
                risk_code=code,
                defaults={"company": route.company, "level": level, "reason": reason, "created_by": user, "updated_by": user},
            )
            record_document_event(
                document=route,
                user=user,
                event="delivery_route.risk_acknowledged",
                metadata={
                    "stop_id": stop.pk,
                    "sales_order_id": stop.sales_order_id,
                    "risk": code,
                    "level": level,
                    "reason": reason,
                },
            )

    @staticmethod
    def _assert_not_on_another_route(order, route):
        """One order, one active route (RT-04).

        An order on a planned or in-transit route is already being dispatched; one already
        delivered on a finished route has gone. A failed, rejected or returned stop, and anything
        on a cancelled route, is free to go out again.
        """
        label = order.number or f"#{order.pk}"
        busy = (
            DeliveryRouteStop.objects.filter(
                company_id=route.company_id,
                sales_order_id=order.pk,
                route__status__in=(DeliveryRoute.Status.PLANNED, DeliveryRoute.Status.IN_TRANSIT),
            )
            .exclude(route_id=route.pk)
            .exclude(
                status__in=(
                    DeliveryRouteStop.StopStatus.FAILED,
                    DeliveryRouteStop.StopStatus.REJECTED,
                    DeliveryRouteStop.StopStatus.RETURNED,
                )
            )
            .select_related("route")
            .first()
        )
        if busy is not None:
            raise BusinessRuleError(
                f"Sales order {label} is already on route {busy.route.number or '#' + str(busy.route_id)}. "
                "Remove it from that route first.",
                code="order_already_on_route",
            )
        delivered = (
            DeliveryRouteStop.objects.filter(
                company_id=route.company_id,
                sales_order_id=order.pk,
                status=DeliveryRouteStop.StopStatus.DELIVERED,
            )
            .exclude(route_id=route.pk)
            .select_related("route")
            .first()
        )
        if delivered is not None:
            raise BusinessRuleError(
                f"Sales order {label} was already delivered on route "
                f"{delivered.route.number or '#' + str(delivered.route_id)}.",
                code="order_already_delivered",
            )

    @staticmethod
    @transaction.atomic
    def remove_stop(route: DeliveryRoute, stop: DeliveryRouteStop, user):
        route = DeliveryRoute.objects.select_for_update().get(pk=route.pk)
        if route.status != DeliveryRoute.Status.PLANNED:
            raise BusinessRuleError(
                "Stops can only be removed while the route is PLANNED. "
                "Mark FAILED or RETURNED once the route is in transit."
            )
        if stop.route_id != route.id:
            raise BusinessRuleError("Stop does not belong to this route.")
        stop.delete()
        route.updated_by = user
        route.save(update_fields=["updated_by", "updated_at"])

    @staticmethod
    @transaction.atomic
    def set_stop_status(
        route: DeliveryRoute,
        stop: DeliveryRouteStop,
        status: str,
        user,
        *,
        completion_source: str = "",
        otp_code: str = "",
        pod_note: str = "",
        received_by_name: str = "",
        pod_photo=None,
        customer_receipt=None,
        collected_cash=None,
        collected_upi=None,
        upi_reference=None,
        reason: str = "",
        returned_lines=None,
    ):
        route = DeliveryRoute.objects.select_for_update().get(pk=route.pk)
        stop = DeliveryRouteStop.objects.select_for_update().get(pk=stop.pk, route=route)
        status = (status or "").upper()
        if status not in DeliveryRouteStop.StopStatus.values:
            raise BusinessRuleError("Invalid stop status.")
        if route.status == DeliveryRoute.Status.PLANNED and status != DeliveryRouteStop.StopStatus.PENDING:
            raise BusinessRuleError("Start the route (IN_TRANSIT) before updating stop delivery status.")
        if route.status == DeliveryRoute.Status.IN_TRANSIT and status == DeliveryRouteStop.StopStatus.PENDING:
            raise BusinessRuleError("Cannot revert an in-transit stop to PENDING.")
        if route.status in (DeliveryRoute.Status.COMPLETED, DeliveryRoute.Status.CANCELLED):
            raise BusinessRuleError("Cannot update stops on a completed or cancelled route.")
        source = (completion_source or "").upper()
        if source and source not in ("PHONE", "OFFICE"):
            raise BusinessRuleError("completion_source must be PHONE or OFFICE.")
        previous = stop.status
        recorded = (
            DeliveryRouteStop.StopStatus.DELIVERED,
            DeliveryRouteStop.StopStatus.FAILED,
            DeliveryRouteStop.StopStatus.REJECTED,
            DeliveryRouteStop.StopStatus.RETURNED,
        )
        reason = (reason or "").strip()
        if previous in recorded and status != previous:
            # An outcome already written down (delivered, failed...) is not silently flipped.
            if len(reason) < 3:
                raise BusinessRuleError(
                    "This stop already has an outcome. Give a reason to change it.",
                    code="stop_change_needs_reason",
                )
            stop.notes = (f"{stop.notes}\n" if stop.notes else "") + (
                f"Changed from {previous} to {status}: {reason}"
            )
        stop.status = status
        stop.updated_by = user
        if source:
            stop.completion_source = source
        if status == DeliveryRouteStop.StopStatus.DELIVERED:
            if source == "OFFICE":
                # The office is recording what the driver reported: no customer code is asked for,
                # and a code that was issued is cleared so it cannot confirm this stop again
                # later (DEC-O1). The stop is marked as recorded by office and the audit says who.
                stop.delivery_otp_hash = ""
            else:
                RouteService._verify_delivery_otp(stop, otp_code)
        cash = RouteService._optional_money(collected_cash, "collected cash")
        upi = RouteService._optional_money(collected_upi, "collected UPI")
        if cash is not None:
            if cash < 0:
                raise BusinessRuleError("Collected cash cannot be negative.")
            stop.collected_cash = cash
        if upi is not None:
            if upi < 0:
                raise BusinessRuleError("Collected UPI cannot be negative.")
            stop.collected_upi = upi
        if upi_reference is not None:
            stop.upi_reference = str(upi_reference).strip()[:64]
        upi_total = stop.collected_upi if upi is None else upi
        ref = stop.upi_reference if upi_reference is None else str(upi_reference).strip()
        if upi_total and upi_total > 0 and not ref:
            raise BusinessRuleError("A UPI reference is required for a UPI collection.")
        if pod_note:
            stop.pod_note = pod_note
        if status == DeliveryRouteStop.StopStatus.DELIVERED:
            name = (received_by_name or "").strip()
            if not name:
                raise BusinessRuleError("Who received the goods is required when a stop is delivered.")
            stop.received_by_name = name[:128]
            stop.delivered_at = timezone.now()
            if pod_photo is not None:
                if pod_photo.company_id != stop.company_id:
                    raise BusinessRuleError("Proof photo is not in this company.")
                stop.pod_photo = pod_photo
            if customer_receipt is not None:
                if customer_receipt.company_id != stop.company_id:
                    raise BusinessRuleError("Receipt is not in this company.")
                if customer_receipt.customer_id != stop.sales_order.customer_id:
                    raise BusinessRuleError("Receipt customer does not match this stop.")
                stop.customer_receipt = customer_receipt
        stop.save()
        if source == "PHONE" and route.completion_source != "PHONE":
            route.completion_source = "PHONE"
            route.save(update_fields=["completion_source", "updated_at"])
        if (
            status == DeliveryRouteStop.StopStatus.DELIVERED
            and returned_lines
            and any(Decimal(str(row.get("quantity") or 0)) > 0 for row in returned_lines if isinstance(row, dict))
        ):
            # Delivered, but the customer sent some of it back: the godown checks those in.
            RouteService._open_goods_return(
                stop, SalesOrder.objects.select_for_update().get(pk=stop.sales_order_id), user, returned_lines
            )
        if status != previous:
            from core.services.audit import record_document_event

            record_document_event(
                document=route,
                user=user,
                event="delivery_route.stop_status",
                before={"status": previous},
                metadata={
                    "stop_id": stop.pk,
                    "sales_order_id": stop.sales_order_id,
                    "from": previous,
                    "to": status,
                    "reason": reason,
                    "completion_source": stop.completion_source,
                    "recorded_by_office": stop.completion_source == "OFFICE",
                },
            )
        failed = status in (
            DeliveryRouteStop.StopStatus.FAILED,
            DeliveryRouteStop.StopStatus.REJECTED,
        )
        was_failed = previous in (
            DeliveryRouteStop.StopStatus.FAILED,
            DeliveryRouteStop.StopStatus.REJECTED,
        )
        if failed and not was_failed:
            RouteService._release_failed_stop(stop, user, returned_lines=returned_lines)
        return stop

    @staticmethod
    def _release_failed_stop(stop, user, returned_lines=None):
        """A refused delivery must not keep goods reserved that nobody will deliver.

        Cases, none of which may release stock twice (H-02):
        - nothing has left the godown (no completed challan, no completed invoice): the order
          still holds its stock; release what it holds and send the order back to DRAFT, because
          it now holds nothing and must be confirmed again before it can be routed (confirming
          re-reserves). A draft challan or draft invoice stays as it is;
        - a challan has completed: that challan already released its share and the goods are
          coming back, so nothing is released here; a draft challan return is opened for the
          godown to check the goods in (the return reopens the order when it completes);
        - the goods were invoiced: the invoice stands; the office is told (see the stop payload).
        """
        from core.services.audit import record_document_event
        from inventory.services import InventoryService

        from .models import DeliveryChallan, SalesOrder
        from .order_quantities import order_still_held

        order = SalesOrder.objects.select_for_update().get(pk=stop.sales_order_id)
        if stop.stock_released_at is not None:
            return
        stop.stock_released_at = timezone.now()
        stop.save(update_fields=["stock_released_at"])

        live_challans = DeliveryChallan.objects.filter(
            sales_order=order, company_id=order.company_id
        ).exclude(status=DeliveryChallan.Status.CANCELLED)
        from .order_quantities import invoices_for_order

        gone_out = live_challans.filter(status=DeliveryChallan.Status.COMPLETED).exists() or (
            invoices_for_order(order)
            .filter(status__in=OPEN_RECEIVABLE_STATUSES)
            .exists()
        )
        if order.stock_held and not gone_out:
            held = order_still_held(order)
            warehouse = order.warehouse or InventoryService.default_warehouse(order.company)
            for item in order.items.select_related("product"):
                qty = held.get(item.product_id, Decimal("0"))
                if qty > 0:
                    InventoryService.release_reservation(order.company, warehouse, item.product, qty, user)
                    held[item.product_id] = Decimal("0")
            order.status = SalesOrder.Status.DRAFT
            order.stock_held = False
            order.updated_by = user
            order.save(update_fields=["status", "stock_held", "updated_by", "updated_at"])
            record_document_event(document=order, user=user, event="sales_order.reopened_after_failed_stop")
            return

        RouteService._open_goods_return(stop, order, user, returned_lines)

    @staticmethod
    def _open_goods_return(stop, order, user, returned_lines=None):
        """Open the draft return the godown checks goods in against (OG-31, OG-32).

        All of the latest completed, uninvoiced challan unless the office says only some came back.
        Does nothing when the goods were invoiced (a challan return is refused once converted; the
        stop payload tells the office about the standing invoice) or when nothing is left to return.
        """
        from .challan_return import ChallanReturnService
        from .models import DeliveryChallan, DeliveryChallanReturn

        challan = (
            DeliveryChallan.objects.filter(company_id=order.company_id, sales_order=order)
            .filter(status=DeliveryChallan.Status.COMPLETED)
            .order_by("-id")
            .first()
        )
        if challan is None or challan.converted_invoice_id:
            return
        if DeliveryChallanReturn.objects.filter(
            company_id=order.company_id,
            challan=challan,
            reason__startswith="Stop ",
        ).exclude(status=DeliveryChallanReturn.Status.CANCELLED).exists():
            return
        # What actually came back: all of it unless the office says otherwise (a partial refusal).
        already = ChallanReturnService.returned_quantities(challan)
        asked = RouteService._returned_by_product(returned_lines)
        lines = []
        left_to_take = dict(asked) if asked is not None else None
        for item in challan.items.select_related("product"):
            room = Decimal(str(item.quantity or 0)) - Decimal(str(already.get(item.product_id, 0) or 0))
            if room <= 0:
                continue
            if left_to_take is None:
                qty = room
            else:
                qty = min(room, left_to_take.get(item.product_id, Decimal("0")))
                left_to_take[item.product_id] = left_to_take.get(item.product_id, Decimal("0")) - qty
            if qty <= 0:
                continue
            lines.append({
                "product": item.product,
                "description": item.description,
                "quantity": qty,
                "unit_price": item.unit_price,
                "discount_percent": item.discount_percent,
                "gst_rate": item.gst_rate,
            })
        if left_to_take is not None and any(v > 0 for v in left_to_take.values()):
            raise BusinessRuleError(
                "More was marked as returned than went out on the challan.", code="return_exceeds_shipped"
            )
        if not lines:
            return
        route_label = stop.route.number or f"#{stop.route_id}"
        challan_return = DeliveryChallanReturn.objects.create(
            company=order.company,
            customer=order.customer,
            challan=challan,
            reason=f"Stop {stop.status} on route {route_label} ({order.number or order.pk})"[:255],
            created_by=user,
            updated_by=user,
        )
        ChallanReturnService.set_items(challan_return, lines, user)

    @staticmethod
    def _returned_by_product(returned_lines):
        """{product id: quantity} from the office's list, or None meaning "all of it"."""
        if returned_lines is None:
            return None
        out: dict[int, Decimal] = {}
        for row in returned_lines:
            if not isinstance(row, dict):
                raise BusinessRuleError("returned_lines must be a list of {product, quantity}.")
            try:
                product_id = int(row.get("product"))
                qty = Decimal(str(row.get("quantity")))
            except (TypeError, ValueError, InvalidOperation) as exc:
                raise BusinessRuleError("Each returned line needs a product and a quantity.") from exc
            if qty < 0:
                raise BusinessRuleError("A returned quantity cannot be negative.")
            out[product_id] = out.get(product_id, Decimal("0")) + qty
        return out

    @staticmethod
    @transaction.atomic
    def cancel_route(route: DeliveryRoute, user, *, reason: str = ""):
        """Cancel a route that should not run (RT-02, OG-07).

        A planned route can be cancelled outright; one already on the road needs a reason. Its
        orders are free to be routed again (stops on a cancelled route no longer count). A route
        cannot be cancelled once goods were delivered or money collected on it: close it instead,
        so the delivery and the cash count stay on record.
        """
        from core.services.audit import record_document_event

        route = DeliveryRoute.objects.select_for_update().get(pk=route.pk)
        if route.status in (DeliveryRoute.Status.COMPLETED, DeliveryRoute.Status.CANCELLED):
            raise BusinessRuleError(f"A route that is {route.status.lower()} cannot be cancelled.")
        reason = (reason or "").strip()
        if route.status == DeliveryRoute.Status.IN_TRANSIT and len(reason) < 3:
            raise BusinessRuleError(
                "A route that has started needs a reason to cancel.", code="route_cancel_needs_reason"
            )
        stops = list(route.stops.all())
        if any(stop.status == DeliveryRouteStop.StopStatus.DELIVERED for stop in stops):
            raise BusinessRuleError(
                "Goods were already delivered on this route. Mark the remaining stops and close the "
                "route instead of cancelling it.",
                code="route_has_deliveries",
            )
        cash, upi = RouteService._collection_totals(route)
        if cash > 0 or upi > 0:
            raise BusinessRuleError(
                "Money was collected on this route. Verify the cashier count and close the route "
                "instead of cancelling it.",
                code="route_has_collections",
            )
        before = route.status
        route.status = DeliveryRoute.Status.CANCELLED
        if reason:
            route.notes = (f"{route.notes}\n" if route.notes else "") + f"Cancelled: {reason}"
        route.updated_by = user
        route.save()
        record_document_event(
            document=route,
            user=user,
            event="delivery_route.cancelled",
            before={"status": before},
            metadata={"reason": reason, "pending_stops": sum(1 for s in stops if s.status == "PENDING")},
        )
        return route

    @staticmethod
    def preflight(route: DeliveryRoute, viewer, *, extra_acknowledged=None) -> dict:
        """The planning view of a route as it stands: every stop's facts and risks, and whether it may start.

        Pure read. ``extra_acknowledged`` ({stop id: {code: reason}}) counts as accepted for this
        check, so the start request can be validated with the acknowledgements it brings.
        """
        from .models import RouteStopAcknowledgement
        from .route_planning import order_summaries, route_totals, unresolved_risks

        stops = list(route.stops.order_by("sequence", "id"))
        orders = list(
            SalesOrder.objects.filter(pk__in=[s.sales_order_id for s in stops], company=route.company)
            .select_related("customer", "warehouse")
            .prefetch_related("items__product")
        )
        summaries = order_summaries(route.company, orders, viewer=viewer, route=route) if stops else {}
        saved: dict[int, dict[str, RouteStopAcknowledgement]] = {}
        for ack in RouteStopAcknowledgement.objects.filter(stop__route=route).select_related("created_by"):
            saved.setdefault(ack.stop_id, {})[ack.risk_code] = ack
        extra_acknowledged = extra_acknowledged or {}
        rows, open_problems, order_summaries_list = [], 0, []
        for stop in stops:
            summary = summaries[stop.sales_order_id]
            order_summaries_list.append(summary)
            mine = saved.get(stop.pk, {})
            codes = set(mine) | set(extra_acknowledged.get(stop.pk, {}))
            result = unresolved_risks(summary, codes, viewer)
            risks = []
            for item in summary["risks"]:
                ack = mine.get(item["code"])
                risks.append({
                    **item,
                    "acknowledged": item["code"] in codes and item["level"] != "info",
                    "acknowledged_reason": ack.reason if ack else extra_acknowledged.get(stop.pk, {}).get(item["code"], ""),
                    "can_accept": viewer.may_accept(item["code"]),
                })
            status = "blocked" if (result["blocked"] or result["not_allowed"]) else ("needs_ack" if result["needs_ack"] else "ok")
            open_problems += len(result["blocked"]) + len(result["not_allowed"]) + len(result["needs_ack"])
            rows.append({
                "stop": stop.pk,
                "order": stop.sales_order_id,
                "number": summary["number"],
                "customer": summary["customer"]["name"],
                "status": status,
                "risks": risks,
                "summary": summary,
            })
        return {
            "stops": rows,
            "totals": route_totals(order_summaries_list),
            "open_problems": open_problems,
            "can_start": open_problems == 0 and bool(stops),
        }

    @staticmethod
    @transaction.atomic
    def start_route(route: DeliveryRoute, user, *, acknowledgements=None, viewer=None, enforce_risks: bool = True):
        """Send a planned route out, after checking it again.

        The world moves between planning and dispatch: stock gets sold, a customer is blocked, credit
        changes. The planning rules run again here against the stops as they are now; whatever is
        blocked stops the start, and a warning that was not accepted at planning (or is new) needs
        an acknowledgement in ``acknowledgements`` (``[{"stop": id, "code": "...", "reason": "..."}]``).
        """
        from .route_planning import viewer_from_user

        route = DeliveryRoute.objects.select_for_update().get(pk=route.pk)
        if route.status != DeliveryRoute.Status.PLANNED:
            raise BusinessRuleError("Only a PLANNED route can be started.")
        if not route.stops.exists():
            raise BusinessRuleError("Add at least one sales order before starting the route.")
        if enforce_risks:
            viewer = viewer or viewer_from_user(route.company, user)
            given = RouteService._parse_acknowledgements(acknowledgements, by="stop")
            check = RouteService.preflight(route, viewer, extra_acknowledged=given)
            if not check["can_start"]:
                problem = next(
                    (s for s in check["stops"] if s["status"] != "ok"),
                    None,
                )
                first = next(r for r in problem["risks"] if not r["acknowledged"] and r["level"] != "info")
                kind = "blocked" if problem["status"] == "blocked" else "needs_ack"
                raise BusinessRuleError(
                    f"Sales order {problem['number'] or problem['order']}: {first['message']}"
                    + (f" (and {check['open_problems'] - 1} more problem(s))" if check["open_problems"] > 1 else ""),
                    code="route_order_blocked" if kind == "blocked" else "route_risk_needs_acknowledgement",
                    extra={"preflight": check},
                )
            stops_by_id = {s.pk: s for s in route.stops.all()}
            for stop_id, accepted in given.items():
                stop = stops_by_id.get(stop_id)
                if stop is None:
                    raise BusinessRuleError(f"Stop {stop_id} is not on this route.")
                allowed = {
                    code: reason
                    for code, reason in accepted.items()
                    if code in {r["code"] for s in check["stops"] if s["stop"] == stop_id for r in s["risks"]}
                    and viewer.may_accept(code)
                }
                RouteService._record_acknowledgements(route, stop, allowed, user)
        RouteService._ensure_number(route)
        route.status = DeliveryRoute.Status.IN_TRANSIT
        route.updated_by = user
        route.save(update_fields=["status", "updated_by", "updated_at", "number"])
        return route

    @staticmethod
    @transaction.atomic
    def complete_route(route: DeliveryRoute, user, *, actual_logistics_cost=None):
        route = DeliveryRoute.objects.select_for_update().get(pk=route.pk)
        if route.status != DeliveryRoute.Status.IN_TRANSIT:
            raise BusinessRuleError("Only an IN_TRANSIT route can be completed.")
        pending = list(
            route.stops.filter(status=DeliveryRouteStop.StopStatus.PENDING).select_related("sales_order")
        )
        if pending:
            names = ", ".join(
                (stop.sales_order.number or f"#{stop.sales_order_id}") for stop in pending[:8]
            ) + (f" and {len(pending) - 8} more" if len(pending) > 8 else "")
            raise BusinessRuleError(
                f"{len(pending)} stop(s) have no outcome yet: {names}. "
                "Mark each one delivered or failed before closing the route.",
                code="route_pending_stops",
            )
        if actual_logistics_cost is not None:
            try:
                route.actual_logistics_cost = Decimal(str(actual_logistics_cost)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            except (InvalidOperation, ValueError) as exc:
                raise BusinessRuleError("Invalid actual logistics cost.") from exc
        route.status = DeliveryRoute.Status.COMPLETED
        route.updated_by = user

        if flag_enabled(route.company, "ENABLE_ROUTE_PROFIT"):
            from core.services.flag_observability import log_flag_event
            from .route_profit_service import compute_route_financials

            log_flag_event(route.company, "ENABLE_ROUTE_PROFIT", "route_completed")

            financials = compute_route_financials(route)
            route.realized_revenue = financials.realized_revenue
            route.realized_cogs = financials.realized_cogs
            route.realized_profit = financials.realized_profit
            route.invoiced_stop_count = financials.invoiced_stop_count
            route.stop_count = financials.stop_count
        RouteService._require_cashier_handover(route)
        route.save()
        return route

    @staticmethod
    def _optional_money(raw, label):
        if raw is None or raw == "":
            return None
        try:
            return Decimal(str(raw)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError) as exc:
            raise BusinessRuleError(f"Invalid {label}.") from exc

    @staticmethod
    def _verify_delivery_otp(stop, otp_code):
        """Refuse an arbitrary OTP. A blank code is allowed only when none was issued."""
        from accounts.otp_utils import verify_otp

        supplied = (otp_code or "").strip()
        stored = (stop.delivery_otp_hash or "").strip()
        if not supplied and not stored:
            return
        from django.core.cache import cache

        fail_key = f"pod_otp_fail:{stop.pk}"
        if int(cache.get(fail_key, 0) or 0) >= POD_OTP_MAX_ATTEMPTS:
            raise BusinessRuleError(
                "Too many wrong delivery codes. Ask the customer for a new code.",
                code="pod_otp_locked",
            )
        if not stored or not verify_otp(stored, supplied):
            # A six-digit code must not be guessable by retrying.
            try:
                from core.services.counters import incr

                incr(fail_key, 1, POD_OTP_LOCK_SECONDS)
            except Exception:  # noqa: BLE001 - a cache outage must not block a delivery
                pass
            raise BusinessRuleError(
                "Proof of delivery OTP does not match the code sent to the customer.",
                code="pod_otp_mismatch",
            )
        cache.delete(fail_key)
        # One code proves one delivery: spend it, so the same code cannot confirm it again later.
        if stored:
            DeliveryRouteStop.objects.filter(pk=stop.pk).update(delivery_otp_hash="")
            stop.delivery_otp_hash = ""

    @staticmethod
    @transaction.atomic
    def issue_delivery_otp(route: DeliveryRoute, stop: DeliveryRouteStop, user):
        """Issue a customer OTP and store only its hash."""
        from accounts.otp_utils import hash_otp

        route = DeliveryRoute.objects.select_for_update().get(pk=route.pk)
        stop = DeliveryRouteStop.objects.select_for_update().get(pk=stop.pk, route=route)
        if route.status in (DeliveryRoute.Status.COMPLETED, DeliveryRoute.Status.CANCELLED):
            raise BusinessRuleError("Cannot issue a delivery OTP on a closed route.")
        code = f"{secrets.randbelow(900000) + 100000}"
        stop.delivery_otp_hash = hash_otp(code)
        from django.core.cache import cache

        cache.delete(f"pod_otp_fail:{stop.pk}")
        stop.otp_code = ""
        stop.updated_by = user
        stop.save(update_fields=["delivery_otp_hash", "otp_code", "updated_by", "updated_at"])
        RouteService._dispatch_delivery_otp(stop, code)
        return code

    @staticmethod
    def _dispatch_delivery_otp(stop, code):
        customer = stop.sales_order.customer
        phone = (getattr(customer, "phone", "") or "").strip()
        if not phone or not getattr(customer, "whatsapp_opt_in", False):
            return
        try:
            from core.services.whatsapp import send_whatsapp_template

            send_whatsapp_template(
                phone,
                "delivery_otp",
                [code],
                company=stop.company,
                allow_cloud=True,
                opt_in=True,
            )
        except Exception:
            logger.exception("delivery OTP dispatch failed for stop %s", stop.pk)

    @staticmethod
    def _collection_totals(route):
        cash = Decimal("0")
        upi = Decimal("0")
        for stop in route.stops.all():
            cash += Decimal(str(stop.collected_cash or 0))
            upi += Decimal(str(stop.collected_upi or 0))
        cash = cash.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        upi = upi.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return cash, upi

    @staticmethod
    def _require_cashier_handover(route):
        expected_cash, expected_upi = RouteService._collection_totals(route)
        if expected_cash <= 0 and expected_upi <= 0:
            return
        try:
            handover = route.cash_handover
        except RouteCashHandover.DoesNotExist:
            handover = None
        if handover is None or handover.status not in (
            RouteCashHandover.Status.VERIFIED,
            RouteCashHandover.Status.VARIANCE,
        ):
            raise BusinessRuleError(
                "Cashier must verify driver cash and UPI before closing the route."
            )
        if handover.expected_cash != expected_cash or handover.expected_upi != expected_upi:
            raise BusinessRuleError(
                "Driver collections changed after cashier verification. Verify the drawer again."
            )

    @staticmethod
    @transaction.atomic
    def verify_cashier_handover(route: DeliveryRoute, user, *, cash_counted, upi_counted, variance_note=""):
        """Record the cashier's count. Does not post a receipt or a cash journal."""
        route = DeliveryRoute.objects.select_for_update().get(pk=route.pk)
        if route.status in (DeliveryRoute.Status.COMPLETED, DeliveryRoute.Status.CANCELLED):
            raise BusinessRuleError("Cannot verify cash on a closed route.")
        counted_cash = RouteService._optional_money(cash_counted, "counted cash")
        counted_upi = RouteService._optional_money(upi_counted, "counted UPI")
        if counted_cash is None or counted_upi is None:
            raise BusinessRuleError("Counted cash and counted UPI are required.")
        if counted_cash < 0 or counted_upi < 0:
            raise BusinessRuleError("Counted amounts cannot be negative.")
        # The person who recorded the collections must not also be the one who verifies the count,
        # or a short count can be signed off by the same hands. An owner or manager may.
        from accounts.models import CompanyUser

        recorded_by_user = route.stops.filter(updated_by=user).exclude(
            collected_cash=0, collected_upi=0
        ).exists()
        if recorded_by_user and not CompanyUser.objects.filter(
            company=route.company, user=user, is_active=True, role__in=["OWNER", "MANAGER"],
        ).exists():
            raise BusinessRuleError(
                "A different person must verify the cash count. Ask the cashier, a manager or the owner.",
                code="handover_same_person",
            )
        expected_cash, expected_upi = RouteService._collection_totals(route)
        variance = (counted_cash - expected_cash) + (counted_upi - expected_upi)
        variance = variance.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        status = (
            RouteCashHandover.Status.VERIFIED if variance == 0 else RouteCashHandover.Status.VARIANCE
        )
        # A short or over count is recorded as it is; the note says why. The route stays on the
        # "needs attention" list until a note exists (it can be added by counting again).
        note = (variance_note or "").strip()[:500] if variance != 0 else ""
        handover, _created = RouteCashHandover.objects.update_or_create(
            route=route,
            defaults={
                "company": route.company,
                "status": status,
                "expected_cash": expected_cash,
                "expected_upi": expected_upi,
                "counted_cash": counted_cash,
                "counted_upi": counted_upi,
                "variance_amount": variance,
                "variance_note": note,
                "verified_at": timezone.now(),
                "updated_by": user,
            },
        )
        if handover.created_by_id is None:
            handover.created_by = user
            handover.save(update_fields=["created_by"])
        return handover

    @staticmethod
    @transaction.atomic
    def link_receipt(route: DeliveryRoute, stop: DeliveryRouteStop, receipt, user, *, reason: str = ""):
        """Attach the receipt the cashier made to the money the driver collected (DEC-R2).

        The system never creates the receipt: the cashier posts it through the receipts screen and
        points the stop at it. It must be this customer's, in this company, posted, and not already
        used by another stop. If it differs from what was collected a reason is required, and the
        difference is written on the stop so it survives.
        """
        from core.services.audit import record_document_event
        from payments.models import ReceiptStatus

        route = DeliveryRoute.objects.select_for_update().get(pk=route.pk)
        stop = DeliveryRouteStop.objects.select_for_update().get(pk=stop.pk, route=route)
        if route.status not in (DeliveryRoute.Status.IN_TRANSIT, DeliveryRoute.Status.COMPLETED):
            raise BusinessRuleError("A receipt can be linked once the route has started.")
        if receipt.company_id != route.company_id:
            raise BusinessRuleError("Receipt was not found.")
        if receipt.customer_id != stop.sales_order.customer_id:
            raise BusinessRuleError("This receipt belongs to a different customer than the stop.")
        if receipt.status != ReceiptStatus.POSTED:
            raise BusinessRuleError("Only a posted receipt can be linked.")
        taken = DeliveryRouteStop.objects.filter(customer_receipt=receipt).exclude(pk=stop.pk).first()
        if taken is not None:
            raise BusinessRuleError("This receipt is already linked to another stop.")
        collected = Decimal(str(stop.collected_cash or 0)) + Decimal(str(stop.collected_upi or 0))
        difference = (Decimal(str(receipt.amount or 0)) - collected).quantize(Decimal("0.01"))
        reason = (reason or "").strip()
        if difference != 0:
            if len(reason) < 3:
                raise BusinessRuleError(
                    f"The receipt is {abs(difference)} {'more' if difference > 0 else 'less'} than the "
                    f"{collected} collected on this stop. Give a reason to link it anyway.",
                    code="receipt_amount_differs",
                )
            stop.notes = (f"{stop.notes}\n" if stop.notes else "") + (
                f"Receipt {receipt.number or receipt.pk} differs by {difference} from the collection: {reason}"
            )
        stop.customer_receipt = receipt
        stop.updated_by = user
        stop.save()
        record_document_event(
            document=route,
            user=user,
            event="delivery_route.receipt_linked",
            metadata={
                "stop_id": stop.pk,
                "receipt_id": receipt.pk,
                "collected": str(collected),
                "receipt_amount": str(receipt.amount),
                "difference": str(difference),
                "reason": reason,
            },
        )
        return stop

    @staticmethod
    def suggest_stop_sequence(route: DeliveryRoute, strategy_name: str | None = None) -> list[SequencedStop]:
        """Suggest a stop order for `route` using the pluggable
        RouteOptimizer registry (see `route_optimization.py`).

        Pure read: does not persist anything, so a dispatcher can preview a
        suggestion (from exactly one strategy at a time -- pass
        `strategy_name` to pick a fallback, otherwise the default
        NearestNeighborTwoOptStrategy is used) before applying it with
        `apply_stop_sequence`.

        Gated behind the existing ENABLE_ROUTE_OPTIMIZATION flag, same as
        `route_combine.combine_suggestions()` -- returns [] when the flag
        is off rather than raising, so callers can treat "no suggestion"
        uniformly.

        PERF: elapsed time is stored per company. The suggest-sequence view
        stays synchronous (HTTP 200) unless the caller sends defer=1 after a
        previous run on this company took longer than 1.5s. That path queues
        suggest_route_sequence_task.
        """
        if not flag_enabled(route.company, "ENABLE_ROUTE_OPTIMIZATION"):
            return []
        import time

        from django.core.cache import cache

        started = time.perf_counter()
        stops = list(route.stops.select_related("sales_order__customer").all())
        stop_inputs = []
        for stop in stops:
            customer = stop.sales_order.customer
            lat = getattr(customer, "latitude", None)
            lon = getattr(customer, "longitude", None)
            stop_inputs.append(StopInput(
                stop_id=stop.id,
                pincode=(getattr(customer, "pincode", "") or "").strip(),
                delivery_address=stop.sales_order.delivery_address or "",
                sales_order_id=stop.sales_order_id,
                latitude=float(lat) if lat is not None else None,
                longitude=float(lon) if lon is not None else None,
            ))
        optimizer = get_route_optimizer(strategy_name)
        sequenced = optimizer.sequence(stop_inputs)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        cache.set(f"route-seq-ms:{route.company_id}", elapsed_ms, 60 * 60 * 24)
        return sequenced

    @staticmethod
    @transaction.atomic
    def apply_stop_sequence(route: DeliveryRoute, sequenced_stops: list[SequencedStop], user):
        """Persist a previously-suggested sequence (from
        `suggest_stop_sequence`) onto each DeliveryRouteStop.sequence.

        Stops omitted from `sequenced_stops` are left untouched.
        """
        route = DeliveryRoute.objects.select_for_update().get(pk=route.pk)
        if route.status != DeliveryRoute.Status.PLANNED:
            raise BusinessRuleError("Stop sequence can only be changed while the route is PLANNED.")
        stops_by_id = {stop.id: stop for stop in route.stops.all()}
        updated = []
        for seq_stop in sequenced_stops:
            stop = stops_by_id.get(seq_stop.stop_id)
            if stop is None:
                continue
            stop.sequence = seq_stop.sequence
            stop.save(update_fields=["sequence"])
            updated.append(stop)
        route.updated_by = user
        route.save(update_fields=["updated_by", "updated_at"])
        return updated
