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
        collected_cash=None,
        collected_upi=None,
        upi_reference=None,
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
        stop.status = status
        stop.updated_by = user
        if source:
            stop.completion_source = source
        if status == DeliveryRouteStop.StopStatus.DELIVERED:
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
        failed = status in (
            DeliveryRouteStop.StopStatus.FAILED,
            DeliveryRouteStop.StopStatus.REJECTED,
        )
        was_failed = previous in (
            DeliveryRouteStop.StopStatus.FAILED,
            DeliveryRouteStop.StopStatus.REJECTED,
        )
        if failed and not was_failed:
            RouteService._release_failed_stop(stop, user)
        return stop

    @staticmethod
    def _release_failed_stop(stop, user):
        """A refused delivery must not keep the goods reserved, and opens a return."""
        from inventory.services import InventoryService

        from .challan_return import ChallanReturnService
        from .models import DeliveryChallan, DeliveryChallanReturn, SalesOrder

        order = SalesOrder.objects.select_for_update().get(pk=stop.sales_order_id)
        if stop.stock_released_at is not None:
            return
        from django.utils import timezone as _tz

        stop.stock_released_at = _tz.now()
        stop.save(update_fields=["stock_released_at"])
        if order.status in (SalesOrder.Status.CONFIRMED, SalesOrder.Status.PARTIALLY_CONVERTED):
            warehouse = order.warehouse or InventoryService.default_warehouse(order.company)
            for item in order.items.select_related("product"):
                open_qty = Decimal(str(item.quantity or 0)) - Decimal(str(item.shipped_quantity or 0))
                if open_qty <= 0:
                    # Fully shipped on a challan: the challan still holds the whole
                    # reservation until the goods are delivered, so release it all.
                    open_qty = Decimal(str(item.quantity or 0))
                InventoryService.release_reservation(
                    order.company, warehouse, item.product, open_qty, user,
                )
        challan = (
            DeliveryChallan.objects.filter(sales_order=order, company_id=order.company_id)
            .exclude(status=DeliveryChallan.Status.CANCELLED)
            .order_by("-id")
            .first()
        )
        if challan is None:
            return
        if DeliveryChallanReturn.objects.filter(
            company_id=order.company_id,
            challan=challan,
            reason__startswith="Stop ",
        ).exclude(status=DeliveryChallanReturn.Status.CANCELLED).exists():
            return
        challan_return = DeliveryChallanReturn.objects.create(
            company=order.company,
            customer=order.customer,
            challan=challan,
            reason=f"Stop {stop.status}",
            created_by=user,
            updated_by=user,
        )
        lines = []
        for item in challan.items.select_related("product"):
            lines.append({
                "product": item.product,
                "description": item.description,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "discount_percent": item.discount_percent,
                "gst_rate": item.gst_rate,
            })
        if lines:
            ChallanReturnService.set_items(challan_return, lines, user)

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
                cache.add(fail_key, 0, timeout=POD_OTP_LOCK_SECONDS)
                cache.incr(fail_key)
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
    def verify_cashier_handover(route: DeliveryRoute, user, *, cash_counted, upi_counted):
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
                "verified_at": timezone.now(),
                "updated_by": user,
            },
        )
        if handover.created_by_id is None:
            handover.created_by = user
            handover.save(update_fields=["created_by"])
        return handover

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
