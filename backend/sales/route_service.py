"""Delivery Route planning overlay (SO-only v1)."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services.document_numbers import DocumentNumberService, resolve_series_gstin
from core.services.feature_flags import flag_enabled

from .expected_profit import expected_profit_for_order
from .models import DeliveryRoute, DeliveryRouteStop, SalesOrder
from .route_optimization import SequencedStop, StopInput, get_route_optimizer


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
    def add_orders(route: DeliveryRoute, order_ids: list[int], user):
        route = DeliveryRoute.objects.select_for_update().get(pk=route.pk)
        if route.status != DeliveryRoute.Status.PLANNED:
            raise BusinessRuleError("Orders can only be added while the route is PLANNED.")
        seq = route.stops.count()
        orders_by_id = {
            o.id: o for o in SalesOrder.objects.filter(pk__in=order_ids, company=route.company)
        }
        existing_order_ids = set(
            DeliveryRouteStop.objects.filter(route=route, sales_order_id__in=order_ids)
            .values_list("sales_order_id", flat=True)
        )
        new_stops = []
        for oid in order_ids:
            order = orders_by_id.get(oid)
            if order is None:
                raise BusinessRuleError(f"Sales order {oid} was not found.")
            if order.status == SalesOrder.Status.CANCELLED:
                raise BusinessRuleError("Cancelled orders cannot be added to a route.")
            if oid in existing_order_ids:
                continue
            seq += 1
            new_stops.append(
                DeliveryRouteStop(
                    company=route.company,
                    route=route,
                    sales_order=order,
                    sequence=seq,
                    created_by=user,
                    updated_by=user,
                )
            )
        added = DeliveryRouteStop.objects.bulk_create(new_stops)
        route.updated_by = user
        route.save(update_fields=["updated_by", "updated_at"])
        return added

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
        # FAILED leaves stock reserved. A return is a separate document.
        stop.status = status
        stop.updated_by = user
        if source:
            stop.completion_source = source
        if otp_code:
            stop.otp_code = str(otp_code)[:8]
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
        return stop

    @staticmethod
    @transaction.atomic
    def start_route(route: DeliveryRoute, user):
        route = DeliveryRoute.objects.select_for_update().get(pk=route.pk)
        if route.status != DeliveryRoute.Status.PLANNED:
            raise BusinessRuleError("Only a PLANNED route can be started.")
        if not route.stops.exists():
            raise BusinessRuleError("Add at least one sales order before starting the route.")
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
        route.save()
        return route

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
