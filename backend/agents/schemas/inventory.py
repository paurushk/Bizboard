from decimal import Decimal, InvalidOperation

from rest_framework import serializers

DEFAULT_COLUMNS = ["item", "qty", "unit", "note"]


class StockLineV1(serializers.Serializer):
    """One row of a transfer or purchase draft. The first four fields are what the lines grid shows and edits;
    the ids are what the executor uses, and it re-checks them against the books."""

    item = serializers.CharField(max_length=255)
    qty = serializers.CharField(max_length=20)
    unit = serializers.CharField(max_length=24, allow_blank=True, default="")
    note = serializers.CharField(max_length=240, allow_blank=True, default="")
    product_id = serializers.IntegerField(min_value=1)
    batch_id = serializers.IntegerField(min_value=1, allow_null=True, required=False, default=None)
    batch_no = serializers.CharField(max_length=64, allow_blank=True, required=False, default="")
    warehouse_id = serializers.IntegerField(min_value=1, allow_null=True, required=False, default=None)
    warehouse_name = serializers.CharField(max_length=255, allow_blank=True, required=False, default="")

    def validate_qty(self, value):
        try:
            q = Decimal(str(value).strip())
        except InvalidOperation:
            raise serializers.ValidationError("Quantity must be a number.")
        if not q.is_finite() or q <= 0 or q > Decimal("10000000"):
            raise serializers.ValidationError("Quantity must be above zero.")
        return format(q.normalize(), "f")


class TransferPayloadV1(serializers.Serializer):
    from_warehouse_id = serializers.IntegerField(min_value=1)
    from_warehouse_name = serializers.CharField(max_length=255, allow_blank=True, default="")
    to_warehouse_id = serializers.IntegerField(min_value=1)
    to_warehouse_name = serializers.CharField(max_length=255, allow_blank=True, default="")
    columns = serializers.ListField(child=serializers.CharField(max_length=24), max_length=10, required=False, default=lambda: list(DEFAULT_COLUMNS))
    lines = StockLineV1(many=True, min_length=1, max_length=100)
    notes = serializers.CharField(max_length=500, allow_blank=True, default="")


class PurchasePayloadV1(serializers.Serializer):
    supplier_id = serializers.IntegerField(min_value=1)
    supplier_name = serializers.CharField(max_length=255, allow_blank=True, default="")
    columns = serializers.ListField(child=serializers.CharField(max_length=24), max_length=10, required=False, default=lambda: list(DEFAULT_COLUMNS))
    lines = StockLineV1(many=True, min_length=1, max_length=100)
    notes = serializers.CharField(max_length=500, allow_blank=True, default="")


class NeedsSupplierPayloadV1(serializers.Serializer):
    """Items that are low but have no supplier on record, so no purchase draft could be made. Nothing to execute:
    approving means the person has seen the list and will pick suppliers on the Purchase planning page."""

    columns = serializers.ListField(child=serializers.CharField(max_length=24), max_length=10, required=False, default=lambda: ["item", "qty", "unit", "note"])
    lines = StockLineV1(many=True, min_length=1, max_length=100)
    notes = serializers.CharField(max_length=500, allow_blank=True, default="")
