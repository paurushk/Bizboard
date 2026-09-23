from rest_framework import serializers

from .challan_return import ChallanReturnService
from .models import (
    DeliveryChallanReturn,
    DeliveryChallanReturnItem,
    DeliveryRoute,
    DeliveryRouteStop,
)
from .route_service import RouteService
from .serializers import LINE_READONLY, TOTAL_READONLY, CompanyScopedSerializerMixin, _BaseLineSerializer


class DeliveryRouteStopSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="sales_order.number", read_only=True)
    customer_name = serializers.CharField(source="sales_order.customer.name", read_only=True)
    delivery_address = serializers.CharField(source="sales_order.delivery_address", read_only=True)

    class Meta:
        model = DeliveryRouteStop
        fields = [
            "id", "sales_order", "order_number", "customer_name", "delivery_address",
            "sequence", "status", "notes", "delivered_at",
        ]
        read_only_fields = ["id", "delivered_at"]


class DeliveryRouteSerializer(CompanyScopedSerializerMixin, serializers.ModelSerializer):
    stops = DeliveryRouteStopSerializer(many=True, read_only=True)
    rollup = serializers.SerializerMethodField()

    class Meta:
        model = DeliveryRoute
        fields = [
            "id", "number", "route_date", "vehicle_number", "driver_name", "driver",
            "status", "estimated_logistics_cost", "actual_logistics_cost",
            "realized_revenue", "realized_cogs", "realized_profit",
            "invoiced_stop_count", "stop_count",
            "notes",
            "stops", "rollup", "created_at", "updated_at",
        ]
        read_only_fields = [
            "number", "status",
            "realized_revenue", "realized_cogs", "realized_profit",
            "invoiced_stop_count", "stop_count",
        ]

    def get_rollup(self, obj):
        from .expected_profit import can_view_expected_profit

        if not can_view_expected_profit(self.context.get("request")):
            return None
        return RouteService.rollup(obj)

    def validate_driver(self, driver):
        if driver is not None:
            self.check_company_ref(driver, "driver")
        return driver


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
