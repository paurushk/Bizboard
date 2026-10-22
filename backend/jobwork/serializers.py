from rest_framework import serializers

from .models import (
    Itc04Filing, JobWorkChallan, JobWorkChallanLine, JobWorkOrder, JobWorkReceipt, JobWorkReceiptLine,
    PrincipalMaterialMovement,
)


class JobWorkOrderSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True, default="")
    customer_name = serializers.CharField(source="customer.name", read_only=True, default="")

    class Meta:
        model = JobWorkOrder
        fields = [
            "id", "number", "direction", "status", "supplier", "supplier_name", "customer", "customer_name",
            "process", "expected_return_date", "service_sac", "direct_supply_declared", "job_worker_warehouse",
            "work_order_id", "job_card_id", "notes", "created_at",
        ]
        read_only_fields = fields


class ChallanLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    qty_open = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)

    class Meta:
        model = JobWorkChallanLine
        fields = [
            "id", "product", "product_name", "batch", "qty", "goods_kind", "serial_numbers", "unit_cost",
            "qty_settled", "qty_open",
        ]
        read_only_fields = fields


class JobWorkChallanSerializer(serializers.ModelSerializer):
    lines = ChallanLineSerializer(many=True, read_only=True)
    order_number = serializers.CharField(source="order.number", read_only=True)

    class Meta:
        model = JobWorkChallan
        fields = [
            "id", "number", "status", "order", "order_number", "challan_date", "origin", "warehouse",
            "source_challan", "supplier_invoice_ref", "vehicle_no", "eway_bill_no", "purpose", "notes", "lines",
            "posted_at", "reversed_at", "reverse_reason",
        ]
        read_only_fields = fields


class ReceiptLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = JobWorkReceiptLine
        fields = [
            "id", "kind", "product", "product_name", "qty", "batch", "input_product", "input_qty", "input_batch",
            "charge_amount", "unit_cost", "cost_amount", "other_order", "invoice_ref", "loss_qty",
        ]
        read_only_fields = fields


class JobWorkReceiptSerializer(serializers.ModelSerializer):
    lines = ReceiptLineSerializer(many=True, read_only=True)
    order_number = serializers.CharField(source="order.number", read_only=True)

    class Meta:
        model = JobWorkReceipt
        fields = [
            "id", "number", "status", "order", "order_number", "receipt_date", "warehouse", "notes", "lines",
            "posted_at", "reversed_at", "reverse_reason",
        ]
        read_only_fields = fields


class Itc04FilingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Itc04Filing
        fields = ["id", "period_label", "from_date", "to_date", "status", "summary", "filed_on", "acknowledgement"]
        read_only_fields = fields


class PrincipalMovementSerializer(serializers.ModelSerializer):
    principal_name = serializers.CharField(source="principal.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = PrincipalMaterialMovement
        fields = [
            "id", "principal", "principal_name", "product", "product_name", "kind", "qty", "move_date",
            "reference", "reversed", "challan", "order",
        ]
        read_only_fields = fields


# --- input -------------------------------------------------------------------------------------

class OrderIn(serializers.Serializer):
    direction = serializers.ChoiceField(choices=JobWorkOrder.Direction.choices, default="OUT")
    supplier = serializers.IntegerField(required=False, allow_null=True)
    customer = serializers.IntegerField(required=False, allow_null=True)
    process = serializers.CharField(required=False, allow_blank=True, max_length=200)
    expected_return_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)
    direct_supply_declared = serializers.BooleanField(required=False)


class ChallanLineIn(serializers.Serializer):
    product = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=12, decimal_places=3)
    batch = serializers.IntegerField(required=False, allow_null=True)
    goods_kind = serializers.ChoiceField(choices=JobWorkChallanLine.GoodsKind.choices, required=False)
    serial_numbers = serializers.ListField(child=serializers.CharField(), required=False)


class ChallanIn(serializers.Serializer):
    order = serializers.IntegerField()
    challan_date = serializers.DateField(required=False, allow_null=True)
    warehouse = serializers.IntegerField(required=False, allow_null=True)
    vehicle_no = serializers.CharField(required=False, allow_blank=True, max_length=20)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)
    lines = ChallanLineIn(many=True)


class ReceiptLineIn(serializers.Serializer):
    kind = serializers.ChoiceField(choices=JobWorkReceiptLine.Kind.choices)
    product = serializers.IntegerField(required=False, allow_null=True)
    qty = serializers.DecimalField(max_digits=12, decimal_places=3, required=False)
    batch = serializers.IntegerField(required=False, allow_null=True)
    input_product = serializers.IntegerField(required=False, allow_null=True)
    input_qty = serializers.DecimalField(max_digits=12, decimal_places=3, required=False)
    input_batch = serializers.IntegerField(required=False, allow_null=True)
    charge_amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=4, required=False, allow_null=True)
    other_order = serializers.IntegerField(required=False, allow_null=True)
    invoice_ref = serializers.CharField(required=False, allow_blank=True, max_length=64)
    loss_qty = serializers.DecimalField(max_digits=12, decimal_places=3, required=False)


class ReceiptIn(serializers.Serializer):
    order = serializers.IntegerField()
    receipt_date = serializers.DateField(required=False, allow_null=True)
    warehouse = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)
    lines = ReceiptLineIn(many=True)


class ReasonIn(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


class PrincipalLinesIn(serializers.Serializer):
    challan_date = serializers.DateField(required=False, allow_null=True)
    vehicle_no = serializers.CharField(required=False, allow_blank=True, max_length=20)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)
    lines = ChallanLineIn(many=True)
