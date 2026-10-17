from rest_framework import serializers

from .challan_return import ChallanReturnService
from .models import (
    DeliveryChallanReturn,
    DeliveryChallanReturnItem,
    DeliveryRoute,
    DeliveryRouteStop,
    RouteCashHandover,
)
from .route_service import RouteService
from .serializers import LINE_READONLY, TOTAL_READONLY, CompanyScopedSerializerMixin, _BaseLineSerializer


class DeliveryRouteStopSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="sales_order.number", read_only=True)
    customer_name = serializers.CharField(source="sales_order.customer.name", read_only=True)
    delivery_address = serializers.CharField(source="sales_order.delivery_address", read_only=True)
    active_invoice = serializers.SerializerMethodField()
    bill = serializers.SerializerMethodField()
    returnable_lines = serializers.SerializerMethodField()
    acknowledgements = serializers.SerializerMethodField()
    customer_phone = serializers.CharField(source="sales_order.customer.phone", read_only=True)
    customer = serializers.IntegerField(source="sales_order.customer_id", read_only=True)

    def get_bill(self, obj):
        """Bill, terms and amount to collect (one query set per stop: detail only, not the list)."""
        view = self.context.get("view")
        if view is not None and getattr(view, "action", None) == "list":
            return None
        from core.permissions import get_company_user
        from insights.customer_360 import can_open_customer_360

        from .route_stop_info import stop_bill_info

        request = self.context.get("request")
        company_user = get_company_user(request) if request is not None else None
        return stop_bill_info(obj, include_customer_money=can_open_customer_360(company_user))

    def get_acknowledgements(self, obj):
        """Risks someone accepted when this order was put on the route (or the route started), with why."""
        return [
            {
                "code": ack.risk_code,
                "level": ack.level,
                "reason": ack.reason,
                "by": getattr(ack.created_by, "full_name", "") or getattr(ack.created_by, "email", "") or "",
                "at": ack.created_at.isoformat() if ack.created_at else None,
            }
            for ack in obj.acknowledgements.all()
        ]

    def get_returnable_lines(self, obj):
        """What went out on the order's latest completed, uninvoiced challan and can still come back."""
        view = self.context.get("view")
        if view is not None and getattr(view, "action", None) == "list":
            return None
        from .challan_return import ChallanReturnService
        from .models import DeliveryChallan

        challan = (
            DeliveryChallan.objects.filter(
                company_id=obj.company_id, sales_order_id=obj.sales_order_id,
                status=DeliveryChallan.Status.COMPLETED, converted_invoice__isnull=True,
            )
            .order_by("-id")
            .first()
        )
        if challan is None:
            return None
        already = ChallanReturnService.returned_quantities(challan)
        rows = []
        for item in challan.items.select_related("product"):
            room = item.quantity - already.get(item.product_id, 0)
            if room > 0:
                rows.append({
                    "product": item.product_id,
                    "product_name": item.product.name,
                    "quantity": str(room),
                })
        return rows

    def get_active_invoice(self, obj):
        """The live invoice behind a stop whose delivery did not happen (H-14, DEC-5).

        A failed, rejected or returned stop changes nothing on an invoice that was already issued;
        the office is told which one is still standing so it can record a sales return. Warn only:
        no document is created. Stops that were delivered or are still pending carry nothing.
        """
        failed = (
            DeliveryRouteStop.StopStatus.FAILED,
            DeliveryRouteStop.StopStatus.REJECTED,
            DeliveryRouteStop.StopStatus.RETURNED,
        )
        if obj.status not in failed:
            return None
        from .models import SalesInvoice
        from .order_quantities import invoices_for_order

        live = [
            inv
            for inv in invoices_for_order(obj.sales_order).order_by("-id")
            if inv.status in (SalesInvoice.Status.COMPLETED,)
        ]
        if not live:
            return None
        return {"id": live[0].pk, "number": live[0].number or ""}

    class Meta:
        model = DeliveryRouteStop
        fields = [
            "id", "sales_order", "order_number", "customer_name", "delivery_address",
            "sequence", "status", "notes", "delivered_at",
            "completion_source", "otp_code", "pod_note",
            "received_by_name", "pod_photo", "customer_receipt",
            "collected_cash", "collected_upi", "upi_reference", "active_invoice",
            "bill", "customer_phone", "customer", "returnable_lines", "acknowledgements",
        ]
        read_only_fields = ["id", "delivered_at"]


class SequencedStopSerializer(serializers.Serializer):
    """Read-only shape for a `route_optimization.SequencedStop` (dataclass) --
    one stop's place in a suggested/applied route order. Renders as
    camelCase (stopId, sequence, pincode, needsManualSequencing) via the
    global EnvelopeJSONRenderer, same as every other endpoint here."""

    stop_id = serializers.IntegerField()
    sequence = serializers.IntegerField()
    pincode = serializers.CharField(allow_blank=True)
    needs_manual_sequencing = serializers.BooleanField()


class DeliveryRouteSerializer(CompanyScopedSerializerMixin, serializers.ModelSerializer):
    stops = DeliveryRouteStopSerializer(many=True, read_only=True)
    rollup = serializers.SerializerMethodField()
    cash_handover = serializers.SerializerMethodField()
    warnings = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()

    class Meta:
        model = DeliveryRoute
        fields = [
            "id", "number", "route_date", "vehicle_number", "driver_name", "driver",
            "status", "estimated_logistics_cost", "actual_logistics_cost",
            "realized_revenue", "realized_cogs", "realized_profit",
            "invoiced_stop_count", "stop_count", "completion_source",
            "notes",
            "stops", "rollup", "cash_handover", "warnings", "progress", "created_at", "updated_at",
        ]
        read_only_fields = [
            "number", "status",
            "realized_revenue", "realized_cogs", "realized_profit",
            "invoiced_stop_count", "stop_count",
        ]

    def get_cash_handover(self, obj):
        try:
            row = obj.cash_handover
        except RouteCashHandover.DoesNotExist:
            return None
        return {
            "status": row.status,
            "expected_cash": row.expected_cash,
            "expected_upi": row.expected_upi,
            "counted_cash": row.counted_cash,
            "counted_upi": row.counted_upi,
            "variance_amount": row.variance_amount,
            "variance_note": row.variance_note,
        }

    def get_progress(self, obj):
        """How far along the route is and whether anything needs the office (cheap: prefetched stops)."""
        from decimal import Decimal

        stops = list(obj.stops.all())
        counts = {"pending": 0, "delivered": 0, "failed": 0}
        collected = Decimal("0")
        for stop in stops:
            if stop.status == DeliveryRouteStop.StopStatus.DELIVERED:
                counts["delivered"] += 1
            elif stop.status == DeliveryRouteStop.StopStatus.PENDING:
                counts["pending"] += 1
            else:
                counts["failed"] += 1
            collected += Decimal(str(stop.collected_cash or 0)) + Decimal(str(stop.collected_upi or 0))
        try:
            handover = obj.cash_handover
        except RouteCashHandover.DoesNotExist:
            handover = None
        attention = []
        if counts["failed"]:
            attention.append("failed_stops")
        if collected > 0 and (handover is None or handover.status not in (
            RouteCashHandover.Status.VERIFIED, RouteCashHandover.Status.VARIANCE
        )):
            attention.append("cash_unverified")
        if handover is not None and handover.status == RouteCashHandover.Status.VARIANCE and not handover.variance_note:
            attention.append("cash_variance_unexplained")
        if obj.status == DeliveryRoute.Status.IN_TRANSIT and counts["pending"] == 0 and stops:
            attention.append("ready_to_close")
        if obj.status in (DeliveryRoute.Status.COMPLETED, DeliveryRoute.Status.CANCELLED):
            # A finished route is only worth the office's attention for money not yet explained.
            attention = [a for a in attention if a in ("cash_unverified", "cash_variance_unexplained")]
        return {
            "stops_total": len(stops),
            **counts,
            "collected": str(collected.quantize(Decimal("0.01"))),
            "needs_attention": attention,
        }

    def get_rollup(self, obj):
        from .expected_profit import can_view_expected_profit

        if not can_view_expected_profit(self.context.get("request")):
            return None
        return RouteService.rollup(obj)

    def validate_driver(self, driver):
        if driver is not None:
            self.check_company_ref(driver, "driver")
        return driver

    # Fields that describe the trip itself. Once a route has left PLANNED they stand: the
    # realised profit and the cash count were taken against them (RT-03, OG-08).
    _LOCKED_AFTER_PLANNED = (
        "route_date", "vehicle_number", "driver_name", "driver",
        "estimated_logistics_cost", "actual_logistics_cost",
    )

    def validate(self, attrs):
        from core.exceptions import BusinessRuleError

        instance = self.instance
        if instance is None:
            return attrs
        if instance.status in (DeliveryRoute.Status.COMPLETED, DeliveryRoute.Status.CANCELLED):
            if attrs:
                raise BusinessRuleError(
                    f"A {instance.status.lower()} route cannot be edited.", code="route_locked"
                )
            return attrs
        if instance.status != DeliveryRoute.Status.PLANNED:
            changed = [
                name for name in self._LOCKED_AFTER_PLANNED
                if name in attrs and attrs[name] != getattr(instance, name)
            ]
            if changed:
                raise BusinessRuleError(
                    "A route that has started cannot change its vehicle, driver, date or costs. "
                    "The actual cost is entered when the route is closed.",
                    code="route_locked",
                )
        return attrs

    def get_warnings(self, obj):
        """Other live routes the same day using this vehicle or driver (RT-09, OG-03). Warn only."""
        if obj.status in (DeliveryRoute.Status.COMPLETED, DeliveryRoute.Status.CANCELLED):
            return []
        from django.db.models import Q

        others = DeliveryRoute.objects.filter(
            company_id=obj.company_id, route_date=obj.route_date,
        ).exclude(pk=obj.pk).exclude(status=DeliveryRoute.Status.CANCELLED)
        warnings = []
        vehicle = (obj.vehicle_number or "").strip()
        if vehicle:
            for other in others.filter(vehicle_number__iexact=vehicle).order_by("id")[:5]:
                warnings.append({
                    "code": "vehicle_clash", "route": other.pk, "number": other.number,
                    "message": f"Vehicle {vehicle} is also on route {other.number or '#' + str(other.pk)} that day.",
                })
        driver_match = Q()
        if obj.driver_id:
            driver_match |= Q(driver_id=obj.driver_id)
        if (obj.driver_name or "").strip():
            driver_match |= Q(driver_name__iexact=obj.driver_name.strip())
        if driver_match:
            for other in others.filter(driver_match).order_by("id")[:5]:
                warnings.append({
                    "code": "driver_clash", "route": other.pk, "number": other.number,
                    "message": f"The driver is also on route {other.number or '#' + str(other.pk)} that day.",
                })
        return warnings


class DeliveryChallanReturnItemSerializer(_BaseLineSerializer):
    class Meta:
        model = DeliveryChallanReturnItem
        fields = [
            "id", "product", "product_name", "description", "quantity",
            "unit_price", "discount_percent", "gst_rate",
        ] + LINE_READONLY
        extra_kwargs = {"unit_price": {"required": False}, "gst_rate": {"required": False}}


class DeliveryChallanReturnSerializer(CompanyScopedSerializerMixin, serializers.ModelSerializer):
    items = DeliveryChallanReturnItemSerializer(many=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    challan_number = serializers.CharField(source="challan.number", read_only=True)

    class Meta:
        model = DeliveryChallanReturn
        fields = [
            "id", "number", "status", "customer", "customer_name", "challan", "challan_number",
            "return_date", "reason", "items", "completed_at", "created_at", "updated_at",
        ] + TOTAL_READONLY
        read_only_fields = ["number", "status", "completed_at"] + TOTAL_READONLY

    def validate_challan(self, challan):
        self.check_company_ref(challan, "challan")
        return challan

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        challan = validated_data.get("challan")
        if challan is not None:
            validated_data.setdefault("customer", challan.customer)
        obj = DeliveryChallanReturn.objects.create(**validated_data)
        ChallanReturnService.set_items(obj, [dict(l) for l in items_data], self.context["request"].user)
        return obj

    def update(self, instance, validated_data):
        from core.exceptions import BusinessRuleError

        if instance.status != DeliveryChallanReturn.Status.DRAFT:
            raise BusinessRuleError("Completed challan return cannot be edited.")
        items_data = validated_data.pop("items", None)
        instance = super().update(instance, validated_data)
        if items_data is not None:
            ChallanReturnService.set_items(
                instance, [dict(l) for l in items_data], self.context["request"].user
            )
        return instance
