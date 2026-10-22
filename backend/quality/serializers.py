from django.db import transaction
from rest_framework import serializers

from core.permissions import get_company_user
from core.serializers import CompanyPrimaryKeyRelatedField
from accounts.models import CompanyUser
from complaints.models import Complaint
from inventory.models import BatchLot
from masters.models import Customer, Product, Supplier

from .models import (
    DefectCode, Inspection, InspectionParameter, InspectionResult, InspectionTemplate, NonConformance,
)


class DefectCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DefectCode
        fields = ["id", "code", "name", "severity", "is_active"]

    def validate_code(self, value):
        value = value.strip().upper()
        request = self.context.get("request")
        cu = get_company_user(request) if request else None
        if cu is not None:
            clash = DefectCode.objects.filter(company=cu.company, code=value)
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError("You already have a defect code with this code.")
        return value


class InspectionParameterSerializer(serializers.ModelSerializer):
    class Meta:
        model = InspectionParameter
        fields = ["id", "name", "kind", "min_value", "max_value", "unit", "mandatory", "sequence"]

    def validate(self, attrs):
        lo, hi = attrs.get("min_value"), attrs.get("max_value")
        if lo is not None and hi is not None and lo > hi:
            raise serializers.ValidationError("The lower limit is above the upper limit.")
        if attrs.get("kind") == InspectionParameter.Kind.NUMERIC and lo is None and hi is None:
            raise serializers.ValidationError("A number parameter needs at least one limit.")
        return attrs


class InspectionTemplateSerializer(serializers.ModelSerializer):
    product = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all(), allow_null=True, required=False)
    parameters = InspectionParameterSerializer(many=True, required=False)

    class Meta:
        model = InspectionTemplate
        fields = ["id", "name", "product", "stage", "sample_size", "notes", "is_active", "parameters"]

    @transaction.atomic
    def create(self, validated_data):
        params = validated_data.pop("parameters", [])
        tpl = InspectionTemplate.objects.create(**validated_data)
        for i, p in enumerate(params):
            InspectionParameter.objects.create(template=tpl, company_id=tpl.company_id, **{"sequence": i, **p})
        return tpl

    @transaction.atomic
    def update(self, instance, validated_data):
        params = validated_data.pop("parameters", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        if params is not None:
            # Past inspections keep their own copy of the parameters, so replacing these is safe.
            instance.parameters.all().delete()
            for i, p in enumerate(params):
                InspectionParameter.objects.create(template=instance, company_id=instance.company_id, **{"sequence": i, **p})
        return instance


class InspectionResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = InspectionResult
        fields = [
            "id", "name", "kind", "min_value", "max_value", "unit", "mandatory", "value_numeric", "value_text", "passed",
        ]
        read_only_fields = fields


class InspectionSerializer(serializers.ModelSerializer):
    results = InspectionResultSerializer(many=True, read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    batch_no = serializers.CharField(source="batch.batch_no", read_only=True, default="")

    class Meta:
        model = Inspection
        fields = [
            "id", "number", "template", "template_name", "stage", "status", "decision", "source_type", "product",
            "product_name", "batch", "batch_no", "grn_item", "receipt_id", "supplier", "qty_inspected",
            "qty_accepted", "qty_rejected", "inspector", "inspected_on", "decided_at", "notes", "results",
            "created_at",
        ]
        read_only_fields = fields


class InspectionCreateIn(serializers.Serializer):
    product = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=12, decimal_places=3)
    stage = serializers.ChoiceField(choices=InspectionTemplate.Stage.choices)
    source_type = serializers.ChoiceField(choices=Inspection.Source.choices, required=False)
    template = serializers.IntegerField(required=False, allow_null=True)
    batch = serializers.IntegerField(required=False, allow_null=True)
    grn_item = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)


class InspectionCompleteIn(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["PASS", "FAIL", "HOLD", "REWORK"], required=False)
    qty_accepted = serializers.DecimalField(max_digits=12, decimal_places=3, required=False)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)


class NonConformanceSerializer(serializers.ModelSerializer):
    defect_code = CompanyPrimaryKeyRelatedField(queryset=DefectCode.objects.all(), allow_null=True, required=False)
    complaint = CompanyPrimaryKeyRelatedField(queryset=Complaint.objects.all(), allow_null=True, required=False)
    product = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all(), allow_null=True, required=False)
    batch = CompanyPrimaryKeyRelatedField(queryset=BatchLot.objects.all(), allow_null=True, required=False)
    supplier = CompanyPrimaryKeyRelatedField(queryset=Supplier.objects.all(), allow_null=True, required=False)
    customer = CompanyPrimaryKeyRelatedField(queryset=Customer.objects.all(), allow_null=True, required=False)
    owner = CompanyPrimaryKeyRelatedField(queryset=CompanyUser.objects.all(), allow_null=True, required=False)
    product_name = serializers.CharField(source="product.name", read_only=True, default="")

    class Meta:
        model = NonConformance
        fields = [
            "id", "number", "source_type", "inspection", "complaint", "product", "product_name", "batch",
            "supplier", "customer", "defect_code", "qty", "description", "root_cause", "action_taken",
            "preventive_action", "owner", "due_date", "status", "closed_at", "created_at",
        ]
        read_only_fields = ["number", "status", "closed_at", "created_at", "source_type", "inspection"]
