from rest_framework import serializers

from core.permissions import get_company_user
from core.serializers import CompanyPrimaryKeyRelatedField
from masters.models import Product

from .models import (
    BatchLot, SerialNumber, StockBalance, StockCountLine, StockCountSession,
    StockMovement, StockTransfer, StockTransferLine, Warehouse, WarehouseReorderLevel,
)


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
    custom_fields = serializers.JSONField(source="product.custom_fields", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    batch_no = serializers.CharField(source="batch.batch_no", read_only=True, default=None)
    nearest_expiry = serializers.DateField(source="batch.expiry_date", read_only=True, default=None)
    reorder_level = serializers.SerializerMethodField()
    available = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)

    class Meta:
        model = StockBalance
        fields = [
            "id", "warehouse", "warehouse_name", "batch", "batch_no", "nearest_expiry",
            "product", "product_name", "sku", "custom_fields", "on_hand", "reserved", "available", "reorder_level",
        ]

    def get_reorder_level(self, obj):
        value = getattr(obj, "_reorder", None)
        if value is None:
            value = obj.product.reorder_level
        return value


    def to_representation(self, instance):
        from masters.custom_fields import defs_for_company, surface_values

        data = super().to_representation(instance)
        product = getattr(instance, "product", None)
        defs = getattr(self, "_cached_cf_defs", None)
        if defs is None:
            request = self.context.get("request")
            if request:
                try:
                    defs = defs_for_company(get_company_user(request).company)
                except Exception:
                    defs = []
            self._cached_cf_defs = defs
        data["custom_fields"] = surface_values(
            getattr(product, "custom_fields", None) if product else {},
            defs,
        )
        return data


class AdjustmentSerializer(serializers.Serializer):
    product = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    reason = serializers.CharField(max_length=255)
    warehouse = serializers.IntegerField(required=False)
    batch = serializers.IntegerField(required=False, allow_null=True)
    batch_no = serializers.CharField(required=False, allow_blank=True, default="")


class OpeningStockSerializer(serializers.Serializer):
    product = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0, required=False)
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    warehouse = serializers.IntegerField(required=False)
    batch = serializers.IntegerField(required=False, allow_null=True)
    batch_no = serializers.CharField(required=False, allow_blank=True, default="")
    expiry_date = serializers.DateField(required=False, allow_null=True)
    manufacturing_date = serializers.DateField(required=False, allow_null=True)
    serial_numbers = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    as_of = serializers.DateField(required=False, allow_null=True)


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
        if not transfer.number:
            from core.services.document_numbers import DocumentNumberService
            transfer.number = DocumentNumberService.next_number(company, "STOCK_TRANSFER")
            transfer.save(update_fields=["number"])
        StockTransferLine.objects.bulk_create([
            StockTransferLine(transfer=transfer, company_id=company.id, **line) for line in lines
        ])
        return transfer

    def update(self, instance, validated_data):
        if instance.status != StockTransfer.Status.DRAFT:
            raise serializers.ValidationError("Only draft transfers can be edited.")
        lines = validated_data.pop("lines", None)
        company = instance.company
        from_wh = validated_data.get("from_warehouse", instance.from_warehouse)
        to_wh = validated_data.get("to_warehouse", instance.to_warehouse)
        if from_wh and from_wh.company_id != company.id:
            raise serializers.ValidationError({"from_warehouse": "Invalid warehouse."})
        if to_wh and to_wh.company_id != company.id:
            raise serializers.ValidationError({"to_warehouse": "Invalid warehouse."})
        if from_wh and to_wh and from_wh.id == to_wh.id:
            raise serializers.ValidationError({"to_warehouse": "Source and destination must differ."})
        instance = super().update(instance, validated_data)
        if lines is not None:
            for line in lines:
                product = line.get("product")
                batch = line.get("batch")
                if product and product.company_id != company.id:
                    raise serializers.ValidationError({"lines": "Invalid product."})
                if batch and (batch.company_id != company.id or (product and batch.product_id != product.id)):
                    raise serializers.ValidationError({"lines": "Invalid batch."})
            instance.lines.all().delete()
            StockTransferLine.objects.bulk_create([
                StockTransferLine(transfer=instance, company_id=company.id, **line) for line in lines
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


class WarehouseReorderLevelSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    warehouse = CompanyPrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    product = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all())

    class Meta:
        model = WarehouseReorderLevel
        fields = ["id", "warehouse", "warehouse_name", "product", "product_name", "reorder_level"]


class StockCountLineSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    product_name = serializers.CharField(source="product.name", read_only=True)
    batch_no = serializers.CharField(source="batch.batch_no", read_only=True, default=None)
    variance = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)
    product = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all(), required=False)
    batch = CompanyPrimaryKeyRelatedField(
        queryset=BatchLot.objects.all(), required=False, allow_null=True,
    )

    class Meta:
        model = StockCountLine
        fields = ["id", "product", "product_name", "batch", "batch_no", "system_qty", "counted_qty", "variance"]
        extra_kwargs = {
            "product": {"required": False},
            "batch": {"required": False, "allow_null": True},
            "system_qty": {"read_only": True},
        }


def _assert_count_line_tenant(session, product, batch):
    if product is not None and product.company_id != session.company_id:
        raise serializers.ValidationError({"lines": "Invalid product."})
    if batch is not None and (
        batch.company_id != session.company_id or (product and batch.product_id != product.id)
    ):
        raise serializers.ValidationError({"lines": "Invalid batch."})


def _count_line_system_qty(session, product, batch):
    from .item_stock import remaining_qty

    return remaining_qty(
        session.company, product, warehouse=session.warehouse, batch=batch, unbatched_only=batch is None,
    )


def _make_count_line(session, line):
    product = line["product"]
    batch = line.get("batch")
    _assert_count_line_tenant(session, product, batch)
    return StockCountLine(
        session=session,
        company=session.company,
        product=product,
        batch=batch,
        system_qty=_count_line_system_qty(session, product, batch),
        counted_qty=line.get("counted_qty"),
    )


class StockCountSessionSerializer(serializers.ModelSerializer):
    lines = StockCountLineSerializer(many=True, required=False)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)

    class Meta:
        model = StockCountSession
        fields = [
            "id", "warehouse", "warehouse_name", "status", "counted_on", "notes",
            "posted_at", "lines", "created_at", "updated_at",
        ]
        read_only_fields = ["status", "posted_at"]

    def create(self, validated_data):
        lines = validated_data.pop("lines", None)
        session = super().create(validated_data)
        warehouse = session.warehouse
        if not lines:
            balances = StockBalance.objects.filter(
                company=session.company, warehouse=warehouse, on_hand__gt=0,
            ).select_related("product", "batch")
            StockCountLine.objects.bulk_create([
                StockCountLine(
                    session=session,
                    company=session.company,
                    product=b.product,
                    batch=b.batch,
                    system_qty=b.on_hand,
                )
                for b in balances
            ])
        else:
            StockCountLine.objects.bulk_create([
                _make_count_line(session, line) for line in lines
            ])
        return session

    def update(self, instance, validated_data):
        from core.exceptions import BusinessRuleError

        lines = validated_data.pop("lines", None)
        instance = super().update(instance, validated_data)
        if lines is None:
            return instance
        if instance.status not in (
            StockCountSession.Status.DRAFT,
            StockCountSession.Status.COUNTED,
        ):
            raise BusinessRuleError("Only a draft or counted session can be edited.")
        existing = {row.id: row for row in instance.lines.all()}
        ids = [line.get("id") for line in lines]
        if ids and all(i in existing for i in ids):
            for line in lines:
                row = existing[line["id"]]
                if "counted_qty" in line:
                    row.counted_qty = line["counted_qty"]
                    row.save(update_fields=["counted_qty"])
            if not instance.lines.filter(counted_qty__isnull=True).exists():
                instance.status = StockCountSession.Status.COUNTED
                instance.save(update_fields=["status"])
            return instance
        instance.lines.all().delete()
        created_lines = StockCountLine.objects.bulk_create([
            _make_count_line(instance, line) for line in lines
        ])
        if created_lines and not any(line.counted_qty is None for line in created_lines):
            instance.status = StockCountSession.Status.COUNTED
            instance.save(update_fields=["status"])
        return instance
