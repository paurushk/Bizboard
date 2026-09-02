from rest_framework import serializers

from core.serializers import CompanyPrimaryKeyRelatedField
from inventory.models import BatchLot, Warehouse
from masters.models import Product

from .models import Bom, BomLine, WorkOrder, WorkOrderLine


def _qty_must_be_positive(value):
    if value is None or value <= 0:
        raise serializers.ValidationError("Quantity must be greater than zero.")
    return value


class BomLineSerializer(serializers.ModelSerializer):
    component = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all())

    class Meta:
        model = BomLine
        fields = ["id", "component", "qty"]

    def validate_qty(self, value):
        return _qty_must_be_positive(value)


class BomSerializer(serializers.ModelSerializer):
    product = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all())
    lines = BomLineSerializer(many=True, required=False)

    class Meta:
        model = Bom
        fields = ["id", "product", "name", "status", "lines", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]

    def create(self, validated_data):
        lines_data = validated_data.pop("lines", [])
        bom = Bom.objects.create(**validated_data)
        for line in lines_data:
            if getattr(line.get("component"), "pk", None) == bom.product_id:
                raise serializers.ValidationError("A BOM cannot list its finished good as a component.")
            BomLine.objects.create(bom=bom, company_id=bom.company_id, **line)
        return bom

    def update(self, instance, validated_data):
        lines_data = validated_data.pop("lines", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if lines_data is not None:
            instance.lines.all().delete()
            for line in lines_data:
                if getattr(line.get("component"), "pk", None) == instance.product_id:
                    raise serializers.ValidationError(
                        "A BOM cannot list its finished good as a component."
                    )
                BomLine.objects.create(bom=instance, company_id=instance.company_id, **line)
        return instance


class WorkOrderLineSerializer(serializers.ModelSerializer):
    component = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all(), required=False)
    batch = CompanyPrimaryKeyRelatedField(
        queryset=BatchLot.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = WorkOrderLine
        fields = ["id", "component", "qty_per_unit", "qty", "batch", "lot_allocations", "serial_numbers"]
        read_only_fields = ["component", "qty_per_unit", "qty"]
        extra_kwargs = {"id": {"required": False}}


class WorkOrderSerializer(serializers.ModelSerializer):
    bom = CompanyPrimaryKeyRelatedField(queryset=Bom.objects.all())
    warehouse = CompanyPrimaryKeyRelatedField(
        queryset=Warehouse.objects.all(), allow_null=True, required=False
    )
    batch = CompanyPrimaryKeyRelatedField(
        queryset=BatchLot.objects.all(), allow_null=True, required=False
    )
    component_lines = WorkOrderLineSerializer(many=True, required=False)

    class Meta:
        model = WorkOrder
        fields = [
            "id", "bom", "qty", "status", "warehouse", "serial_numbers", "component_lines",
            "batch_no", "exp_date", "mfg_date", "batch",
            "released_at", "completed_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "status", "released_at", "completed_at",
            "created_at", "updated_at",
        ]
        extra_kwargs = {
            "serial_numbers": {"required": False},
            "batch_no": {"required": False, "allow_blank": True},
            "exp_date": {"required": False, "allow_null": True},
            "mfg_date": {"required": False, "allow_null": True},
        }

    def validate_qty(self, value):
        return _qty_must_be_positive(value)

    def create(self, validated_data):
        from .services import _snapshot_bom

        lines_data = validated_data.pop("component_lines", None)
        wo = WorkOrder.objects.create(**validated_data)
        _snapshot_bom(wo)
        if lines_data:
            self._apply_component_lines(wo, lines_data)
        return wo

    def update(self, instance, validated_data):
        lines_data = validated_data.pop("component_lines", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if lines_data is not None and instance.status == WorkOrder.Status.DRAFT:
            self._apply_component_lines(instance, lines_data)
        return instance

    @staticmethod
    def _apply_component_lines(instance, lines_data):
        by_id = {line.id: line for line in instance.component_lines.all()}
        by_component = {}
        for line in instance.component_lines.all():
            by_component.setdefault(line.component_id, []).append(line)
        for payload in lines_data:
            line_id = payload.get("id")
            line = by_id.get(line_id) if line_id else None
            if line is None:
                component = payload.get("component")
                cid = getattr(component, "pk", component)
                candidates = by_component.get(cid) or []
                line = candidates.pop(0) if candidates else None
            if line is None:
                continue
            if "batch" in payload:
                line.batch = payload.get("batch")
            if "lot_allocations" in payload:
                line.lot_allocations = payload.get("lot_allocations") or []
            if "serial_numbers" in payload:
                line.serial_numbers = payload.get("serial_numbers") or []
            line.save()
