from rest_framework import serializers

from core.permissions import get_company_user

from .models import BatchLot, SerialNumber, StockBalance, StockMovement, StockTransfer, StockTransferLine, Warehouse


class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            "id", "product", "product_name", "movement_type", "quantity",
            "warehouse", "batch", "unit_cost", "reference_type", "reference_id", "reason",
            "created_by", "created_at",
        ]


class StockBalanceSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    sku = serializers.CharField(source="product.sku", read_only=True)
    reorder_level = serializers.DecimalField(
        source="product.reorder_level", max_digits=12, decimal_places=3, read_only=True
    )
    available = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)

    class Meta:
        model = StockBalance
        fields = ["id", "warehouse", "batch", "product", "product_name", "sku", "on_hand", "reserved", "available", "reorder_level"]


class AdjustmentSerializer(serializers.Serializer):
    product = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    reason = serializers.CharField(max_length=255)
    warehouse = serializers.IntegerField(required=False)
    batch = serializers.IntegerField(required=False, allow_null=True)


class OpeningStockSerializer(serializers.Serializer):
    product = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0)
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    warehouse = serializers.IntegerField(required=False)
    batch = serializers.IntegerField(required=False, allow_null=True)


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = ["id", "name", "code", "address", "is_default", "is_active", "created_at", "updated_at"]

    def _clear_other_defaults(self, company, exclude_pk=None):
        qs = Warehouse.objects.filter(company=company, is_default=True)
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        qs.update(is_default=False)

    def create(self, validated_data):
        from django.db import transaction
        from django.db.utils import IntegrityError

        from core.exceptions import BusinessRuleError

        company = validated_data.get("company")
        try:
            with transaction.atomic():
                if validated_data.get("is_default") and company is not None:
                    self._clear_other_defaults(company)
                return super().create(validated_data)
        except IntegrityError as exc:
            raise BusinessRuleError(
                "Could not set default warehouse — another default may already exist. Retry."
            ) from exc

    def update(self, instance, validated_data):
        from django.db import transaction
        from django.db.utils import IntegrityError

        from core.exceptions import BusinessRuleError

        try:
            with transaction.atomic():
                if validated_data.get("is_default"):
                    self._clear_other_defaults(instance.company, exclude_pk=instance.pk)
                return super().update(instance, validated_data)
        except IntegrityError as exc:
            raise BusinessRuleError(
                "Could not set default warehouse — another default may already exist. Retry."
            ) from exc


class BatchLotSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = BatchLot
        fields = ["id", "product", "product_name", "batch_no", "expiry_date", "manufacturing_date", "created_at"]


class StockTransferLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockTransferLine
        fields = ["id", "product", "batch", "quantity", "serial_numbers"]


class StockTransferSerializer(serializers.ModelSerializer):
    lines = StockTransferLineSerializer(many=True)
    # UXW2B-016: from_warehouse/to_warehouse are plain FK ids — the transfers list
    # showed raw numeric ids in the From/To columns with nothing to resolve them to
    # names. Same join-a-display-name pattern already used for product_name above.
    from_warehouse_name = serializers.CharField(source="from_warehouse.name", read_only=True, default=None)
    to_warehouse_name = serializers.CharField(source="to_warehouse.name", read_only=True, default=None)

    class Meta:
        model = StockTransfer
        fields = [
            "id", "number", "from_warehouse", "from_warehouse_name",
            "to_warehouse", "to_warehouse_name", "status", "notes",
            "lines", "completed_at", "cancelled_at", "created_at", "updated_at",
        ]
        read_only_fields = ["number", "status", "completed_at", "cancelled_at"]

    def create(self, validated_data):
        request = self.context.get("request")
        company = getattr(request, "company", None) or (
            get_company_user(request).company if request else None
        )
        if company is None:
            raise serializers.ValidationError("Company context required.")
        from_wh = validated_data.get("from_warehouse")
        to_wh = validated_data.get("to_warehouse")
        if from_wh and from_wh.company_id != company.id:
            raise serializers.ValidationError({"from_warehouse": "Invalid warehouse."})
        if to_wh and to_wh.company_id != company.id:
            raise serializers.ValidationError({"to_warehouse": "Invalid warehouse."})
        if from_wh and to_wh and from_wh.id == to_wh.id:
            raise serializers.ValidationError({"to_warehouse": "Source and destination must differ."})
        lines = validated_data.pop("lines")
        for line in lines:
            product = line.get("product")
            batch = line.get("batch")
            if product and product.company_id != company.id:
                raise serializers.ValidationError({"lines": "Invalid product."})
            if batch and (batch.company_id != company.id or (product and batch.product_id != product.id)):
                raise serializers.ValidationError({"lines": "Invalid batch."})
        transfer = super().create(validated_data)
        StockTransferLine.objects.bulk_create([
            StockTransferLine(transfer=transfer, **line) for line in lines
        ])
        return transfer

    def update(self, instance, validated_data):
        if instance.status != StockTransfer.Status.DRAFT:
            raise serializers.ValidationError("Only draft transfers can be edited.")
        lines = validated_data.pop("lines", None)
        instance = super().update(instance, validated_data)
        if lines is not None:
            instance.lines.all().delete()
            StockTransferLine.objects.bulk_create([
                StockTransferLine(transfer=instance, **line) for line in lines
            ])
        return instance


class SerialNumberSerializer(serializers.ModelSerializer):
    # UXW2B-017: product/warehouse were plain FK ids with nothing to resolve them to
    # names — the list showed raw product ids and a blank Warehouse column even when
    # a warehouse was actually set. Same join-a-display-name pattern as elsewhere.
    product_name = serializers.CharField(source="product.name", read_only=True, default=None)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True, default=None)

    class Meta:
        model = SerialNumber
        fields = [
            "id", "product", "product_name", "warehouse", "warehouse_name",
            "serial_number", "status", "created_at", "updated_at",
        ]
