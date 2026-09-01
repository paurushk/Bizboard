from rest_framework import serializers

from core.serializers import CompanyPrimaryKeyRelatedField
from inventory.models import Warehouse
from masters.models import Product

from .models import Bom, BomLine, WorkOrder, WorkOrderLine


class BomLineSerializer(serializers.ModelSerializer):
    component = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all())

    class Meta:
        model = BomLine
        fields = ["id", "component", "qty"]


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
    class Meta:
        model = WorkOrderLine
        fields = ["id", "component", "qty_per_unit", "qty", "batch", "lot_allocations", "serial_numbers"]
        read_only_fields = ["id", "component", "qty_per_unit", "qty"]


class WorkOrderSerializer(serializers.ModelSerializer):
    bom = CompanyPrimaryKeyRelatedField(queryset=Bom.objects.all())
    warehouse = CompanyPrimaryKeyRelatedField(
        queryset=Warehouse.objects.all(), allow_null=True, required=False
    )
    component_lines = WorkOrderLineSerializer(many=True, read_only=True)

    class Meta:
        model = WorkOrder
        fields = [
            "id", "bom", "qty", "status", "warehouse", "serial_numbers", "component_lines",
            "released_at", "completed_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "status", "component_lines", "released_at", "completed_at",
            "created_at", "updated_at",
        ]
        extra_kwargs = {"serial_numbers": {"required": False}}
