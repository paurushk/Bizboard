"""Serializers for the issue / return / receipt documents (read shape plus input validation)."""

from rest_framework import serializers

from core.serializers import CompanyPrimaryKeyRelatedField

from .models import (
    MaterialIssue, MaterialIssueLine, MaterialReturn, MaterialReturnLine, ProductionReceipt,
    ProductionReceiptLine, WorkOrder,
)
from .serializers import CostMaskMixin


class _Doc(CostMaskMixin, serializers.ModelSerializer):
    work_order_number = serializers.CharField(source="work_order.number", read_only=True)


class MaterialIssueLineSerializer(CostMaskMixin, serializers.ModelSerializer):
    cost_fields = ("unit_cost", "cost_amount")
    component_name = serializers.CharField(source="component.name", read_only=True)

    class Meta:
        model = MaterialIssueLine
        fields = [
            "id", "wo_line", "component", "component_name", "warehouse", "batch", "qty",
            "lot_allocations", "serial_numbers", "is_extra", "extra_reason", "unit_cost", "cost_amount",
        ]
        read_only_fields = fields


class MaterialIssueSerializer(_Doc):
    lines = MaterialIssueLineSerializer(many=True, read_only=True)

    class Meta:
        model = MaterialIssue
        fields = [
            "id", "number", "status", "work_order", "work_order_number", "doc_date", "notes", "lines",
            "approval", "approval_note", "approval_decided_at",
            "posted_at", "reversed_at", "reverse_reason", "created_at",
        ]
        read_only_fields = fields


class MaterialReturnLineSerializer(CostMaskMixin, serializers.ModelSerializer):
    cost_fields = ("unit_cost", "cost_amount", "sources")
    component_name = serializers.CharField(source="component.name", read_only=True)

    class Meta:
        model = MaterialReturnLine
        fields = [
            "id", "wo_line", "component", "component_name", "warehouse", "batch", "qty",
            "serial_numbers", "source_issue_line", "unit_cost", "cost_amount", "sources",
        ]
        read_only_fields = fields


class MaterialReturnSerializer(_Doc):
    lines = MaterialReturnLineSerializer(many=True, read_only=True)

    class Meta:
        model = MaterialReturn
        fields = [
            "id", "number", "status", "work_order", "work_order_number", "doc_date", "notes", "lines",
            "posted_at", "reversed_at", "reverse_reason", "created_at",
        ]
        read_only_fields = fields


class ProductionReceiptLineSerializer(CostMaskMixin, serializers.ModelSerializer):
    cost_fields = ("unit_cost", "cost_amount", "recovery_rate")
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = ProductionReceiptLine
        fields = [
            "id", "kind", "product", "product_name", "warehouse", "batch", "qty_good", "qty_rejected",
            "qty_rework", "reject_warehouse", "rework_warehouse", "serial_numbers", "recovery_rate",
            "unit_cost", "cost_amount",
        ]
        read_only_fields = fields


class ProductionReceiptSerializer(_Doc):
    cost_fields = ("total_cost", "absorbed_cost")
    lines = ProductionReceiptLineSerializer(many=True, read_only=True)

    class Meta:
        model = ProductionReceipt
        fields = [
            "id", "number", "status", "work_order", "work_order_number", "doc_date", "is_final", "batch_no",
            "exp_date", "mfg_date", "notes", "total_cost", "absorbed_cost", "backflush_issue", "lines",
            "posted_at", "reversed_at", "reverse_reason", "created_at",
        ]
        read_only_fields = fields


# --- input ------------------------------------------------------------------------------------

class _Base(serializers.Serializer):
    work_order = CompanyPrimaryKeyRelatedField(queryset=WorkOrder.objects.all())
    doc_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)


class IssueLineIn(serializers.Serializer):
    wo_line = serializers.IntegerField(required=False, allow_null=True)
    component = serializers.IntegerField(required=False, allow_null=True)
    qty = serializers.DecimalField(max_digits=12, decimal_places=3)
    warehouse = serializers.IntegerField(required=False, allow_null=True)
    batch = serializers.IntegerField(required=False, allow_null=True)
    serial_numbers = serializers.ListField(child=serializers.CharField(), required=False)
    lot_allocations = serializers.ListField(child=serializers.DictField(), required=False)
    extra_reason = serializers.CharField(required=False, allow_blank=True, max_length=255)


class IssueIn(_Base):
    lines = IssueLineIn(many=True, required=False)


class ReturnLineIn(serializers.Serializer):
    wo_line = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=12, decimal_places=3)
    warehouse = serializers.IntegerField(required=False, allow_null=True)
    batch = serializers.IntegerField(required=False, allow_null=True)
    serial_numbers = serializers.ListField(child=serializers.CharField(), required=False)
    source_issue_line = serializers.IntegerField(required=False, allow_null=True)


class ReturnIn(_Base):
    lines = ReturnLineIn(many=True)


class ReceiptLineIn(serializers.Serializer):
    kind = serializers.ChoiceField(choices=ProductionReceiptLine.Kind.choices, required=False)
    product = serializers.IntegerField(required=False, allow_null=True)
    qty_good = serializers.DecimalField(max_digits=12, decimal_places=3, required=False)
    qty_rejected = serializers.DecimalField(max_digits=12, decimal_places=3, required=False)
    qty_rework = serializers.DecimalField(max_digits=12, decimal_places=3, required=False)
    warehouse = serializers.IntegerField(required=False, allow_null=True)
    reject_warehouse = serializers.IntegerField(required=False, allow_null=True)
    rework_warehouse = serializers.IntegerField(required=False, allow_null=True)
    serial_numbers = serializers.ListField(child=serializers.CharField(), required=False)
    recovery_rate = serializers.DecimalField(max_digits=12, decimal_places=4, required=False, allow_null=True)


class ReceiptIn(_Base):
    is_final = serializers.BooleanField(required=False)
    batch_no = serializers.CharField(required=False, allow_blank=True, max_length=64)
    exp_date = serializers.DateField(required=False, allow_null=True)
    mfg_date = serializers.DateField(required=False, allow_null=True)
    lines = ReceiptLineIn(many=True, required=False)


class ReasonIn(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


class ApprovalNoteIn(serializers.Serializer):
    note = serializers.CharField(max_length=500, required=False, allow_blank=True)


class QuickComponentIn(serializers.Serializer):
    component = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=12, decimal_places=3)


class QuickProductionIn(serializers.Serializer):
    product = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=12, decimal_places=3)
    doc_date = serializers.DateField(required=False, allow_null=True)
    customer = serializers.IntegerField(required=False, allow_null=True)
    warehouse = serializers.IntegerField(required=False, allow_null=True)
    fg_warehouse = serializers.IntegerField(required=False, allow_null=True)
    batch_no = serializers.CharField(required=False, allow_blank=True, max_length=64)
    exp_date = serializers.DateField(required=False, allow_null=True)
    mfg_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)
    components = QuickComponentIn(many=True, required=False)
