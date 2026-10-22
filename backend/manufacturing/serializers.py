from django.db import transaction
from rest_framework import serializers

from core.permissions import get_company_user
from core.serializers import CompanyPrimaryKeyRelatedField
from inventory.models import BatchLot, Warehouse
from masters.models import Customer, Product, Unit
from sales.models import SalesOrder, SalesOrderItem

from .models import (
    Bom, BomAdditionalCost, BomLine, BomOutput, MfgSettings, WorkOrder, WorkOrderLine,
    WorkOrderOutput, WorkOrderVariance,
)
from .permissions import can_see_costs


class SalesOrderItemField(serializers.PrimaryKeyRelatedField):
    """A sales-order line of the requesting company (the line has no company column of its own)."""

    def get_queryset(self):
        qs = super().get_queryset()
        request = self.context.get("request") if self.context else None
        cu = get_company_user(request) if request is not None else None
        if cu is None:
            return qs.none()
        return qs.filter(sales_order__company=cu.company)


def _qty_must_be_positive(value):
    if value is None or value <= 0:
        raise serializers.ValidationError("Quantity must be greater than zero.")
    return value


class CostMaskMixin:
    """Leave cost fields out (not zero them) for roles that may not see costs."""

    cost_fields: tuple = ()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request is not None and not can_see_costs(request):
            for name in self.cost_fields:
                data.pop(name, None)
        return data


class BomLineSerializer(serializers.ModelSerializer):
    component = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all())
    unit = CompanyPrimaryKeyRelatedField(queryset=Unit.objects.all(), allow_null=True, required=False)
    source_warehouse = CompanyPrimaryKeyRelatedField(
        queryset=Warehouse.objects.all(), allow_null=True, required=False,
    )

    class Meta:
        model = BomLine
        fields = [
            "id", "component", "qty", "unit", "scrap_pct", "issue_method", "is_optional", "is_phantom",
            "alternate_group", "alternate_priority", "source_warehouse", "sequence", "notes",
        ]

    def validate_qty(self, value):
        return _qty_must_be_positive(value)


class BomOutputSerializer(serializers.ModelSerializer):
    product = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all())
    target_warehouse = CompanyPrimaryKeyRelatedField(
        queryset=Warehouse.objects.all(), allow_null=True, required=False,
    )

    class Meta:
        model = BomOutput
        fields = ["id", "product", "kind", "qty", "cost_share_pct", "recovery_rate", "target_warehouse"]

    def validate_qty(self, value):
        return _qty_must_be_positive(value)


class BomAdditionalCostSerializer(serializers.ModelSerializer):
    class Meta:
        model = BomAdditionalCost
        fields = ["id", "label", "element", "basis", "amount"]


class BomSerializer(CostMaskMixin, serializers.ModelSerializer):
    cost_fields = ("additional_costs",)

    product = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all())
    customer = CompanyPrimaryKeyRelatedField(queryset=Customer.objects.all(), allow_null=True, required=False)
    fg_warehouse = CompanyPrimaryKeyRelatedField(
        queryset=Warehouse.objects.all(), allow_null=True, required=False,
    )
    lines = BomLineSerializer(many=True, required=False)
    outputs = BomOutputSerializer(many=True, required=False)
    additional_costs = BomAdditionalCostSerializer(many=True, required=False)
    is_locked = serializers.BooleanField(read_only=True)

    class Meta:
        model = Bom
        fields = [
            "id", "product", "name", "status", "revision_no", "effective_from", "effective_to",
            "is_default", "customer", "parent_revision", "change_reason", "output_qty", "yield_pct",
            "fg_warehouse", "notes", "is_locked", "locked_at", "lines", "outputs", "additional_costs",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "revision_no", "is_default", "parent_revision", "locked_at", "created_at", "updated_at",
        ]
        extra_kwargs = {
            "effective_from": {"required": False, "allow_null": True},
            "effective_to": {"required": False, "allow_null": True},
            "change_reason": {"required": False, "allow_blank": True},
            "notes": {"required": False, "allow_blank": True},
        }

    CONTENT_KEYS = ("product", "customer", "output_qty", "yield_pct", "fg_warehouse")

    def _validate_payload(self, company, product, lines, outputs, instance=None, attrs=None):
        from .services import bom as bom_service

        attrs = attrs or {}
        bom_service.validate_content(
            company, product, lines, outputs,
            output_qty=attrs.get("output_qty", getattr(instance, "output_qty", None)),
            yield_pct=attrs.get("yield_pct", getattr(instance, "yield_pct", None)),
        )

    @staticmethod
    def _write_children(bom, lines, outputs, costs):
        for i, line in enumerate(lines or []):
            line = dict(line)
            line.setdefault("sequence", i)
            BomLine.objects.create(bom=bom, company_id=bom.company_id, **line)
        for out in outputs or []:
            BomOutput.objects.create(bom=bom, company_id=bom.company_id, **out)
        for cost in costs or []:
            BomAdditionalCost.objects.create(bom=bom, company_id=bom.company_id, **cost)

    def create(self, validated_data):
        from .services import bom as bom_service

        lines = validated_data.pop("lines", [])
        outputs = validated_data.pop("outputs", [])
        costs = validated_data.pop("additional_costs", [])
        company = validated_data.get("company")
        product = validated_data["product"]
        # B8-002: validate the whole payload before any write.
        self._validate_payload(company, product, lines, outputs, attrs=validated_data)
        wanted = validated_data.get("status") or Bom.Status.DRAFT
        user = validated_data.get("created_by")
        with transaction.atomic():
            validated_data["status"] = Bom.Status.DRAFT
            validated_data["revision_no"] = bom_service.next_revision_no(company, product)
            bom = Bom.objects.create(**validated_data)
            self._write_children(bom, lines, outputs, costs)
            if wanted == Bom.Status.ACTIVE:
                bom = bom_service.activate_revision(bom, user)
            elif wanted == Bom.Status.ARCHIVED:
                bom = bom_service.archive_revision(bom, user)
        return bom

    def update(self, instance, validated_data):
        from .services import bom as bom_service

        lines = validated_data.pop("lines", None)
        outputs = validated_data.pop("outputs", None)
        costs = validated_data.pop("additional_costs", None)
        wanted = validated_data.pop("status", None)
        changes_recipe = (
            lines is not None or outputs is not None or costs is not None
            or any(k in validated_data and validated_data[k] != getattr(instance, k) for k in self.CONTENT_KEYS)
        )
        if changes_recipe:
            bom_service.assert_editable(instance)
        if lines is not None or outputs is not None:
            use_lines = lines if lines is not None else [
                {"component": ln.component, "unit": ln.unit, "scrap_pct": ln.scrap_pct}
                for ln in instance.lines.all()
            ]
            use_outputs = outputs if outputs is not None else [
                {"product": o.product, "kind": o.kind, "cost_share_pct": o.cost_share_pct}
                for o in instance.outputs.all()
            ]
            self._validate_payload(
                instance.company, validated_data.get("product", instance.product),
                use_lines, use_outputs, instance=instance, attrs=validated_data,
            )
            if lines is not None:
                bom_service.assert_no_bom_cycle(
                    instance.company, instance.product_id, [ln.get("component") for ln in lines],
                    ignore_bom_id=instance.pk,
                )
        user = validated_data.get("updated_by")
        with transaction.atomic():
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()
            if lines is not None:
                instance.lines.all().delete()
            if outputs is not None:
                instance.outputs.all().delete()
            if costs is not None:
                instance.additional_costs.all().delete()
            self._write_children(instance, lines, outputs, costs)
            if wanted and wanted != instance.status:
                if wanted == Bom.Status.ACTIVE:
                    instance = bom_service.activate_revision(instance, user)
                elif wanted == Bom.Status.ARCHIVED:
                    instance = bom_service.archive_revision(instance, user)
                else:
                    instance.status = wanted
                    instance.save(update_fields=["status", "updated_at"])
        return instance


class WorkOrderLineSerializer(serializers.ModelSerializer):
    component = CompanyPrimaryKeyRelatedField(queryset=Product.objects.all(), required=False)
    batch = CompanyPrimaryKeyRelatedField(
        queryset=BatchLot.objects.all(), allow_null=True, required=False
    )
    unit = CompanyPrimaryKeyRelatedField(queryset=Unit.objects.all(), allow_null=True, required=False)

    class Meta:
        model = WorkOrderLine
        fields = [
            "id", "component", "qty_per_unit", "qty", "batch", "lot_allocations", "serial_numbers",
            "unit", "scrap_pct", "issue_method", "is_optional", "alternate_group",
            "alternate_priority", "source_warehouse", "qty_issued", "qty_returned",
            "principal_supplied",
        ]
        read_only_fields = [
            "component", "qty_per_unit", "qty", "unit", "scrap_pct", "issue_method", "is_optional",
            "alternate_group", "alternate_priority", "source_warehouse", "qty_issued",
            "qty_returned",
        ]
        extra_kwargs = {"id": {"required": False}}


class WorkOrderOutputSerializer(CostMaskMixin, serializers.ModelSerializer):
    cost_fields = ("estimated_unit_cost", "recovery_rate")

    class Meta:
        model = WorkOrderOutput
        fields = [
            "id", "product", "kind", "qty", "cost_share_pct", "recovery_rate", "target_warehouse",
            "estimated_unit_cost",
        ]
        read_only_fields = fields


class WorkOrderVarianceSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkOrderVariance
        fields = [
            "id", "kind", "component", "standard_qty", "actual_qty", "standard_cost", "actual_cost",
            "variance", "posted_to_gl",
        ]
        read_only_fields = fields


class WorkOrderSerializer(CostMaskMixin, serializers.ModelSerializer):
    cost_fields = (
        "estimated_unit_cost", "cost_issued", "cost_returned", "cost_absorbed", "cost_received",
        "cost_variance", "wip_value",
    )

    bom = CompanyPrimaryKeyRelatedField(queryset=Bom.objects.all())
    warehouse = CompanyPrimaryKeyRelatedField(
        queryset=Warehouse.objects.all(), allow_null=True, required=False
    )
    fg_warehouse = CompanyPrimaryKeyRelatedField(
        queryset=Warehouse.objects.all(), allow_null=True, required=False
    )
    batch = CompanyPrimaryKeyRelatedField(
        queryset=BatchLot.objects.all(), allow_null=True, required=False
    )
    principal = CompanyPrimaryKeyRelatedField(queryset=Customer.objects.all(), allow_null=True, required=False)
    sales_order = CompanyPrimaryKeyRelatedField(
        queryset=SalesOrder.objects.all(), allow_null=True, required=False,
    )
    sales_order_item = SalesOrderItemField(
        queryset=SalesOrderItem.objects.all(), allow_null=True, required=False,
    )
    component_lines = WorkOrderLineSerializer(many=True, required=False)
    planned_outputs = WorkOrderOutputSerializer(many=True, read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    wip_value = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = WorkOrder
        fields = [
            "id", "number", "kind", "bom", "product", "product_name", "qty", "status", "warehouse",
            "fg_warehouse", "serial_numbers", "component_lines", "planned_outputs",
            "batch_no", "exp_date", "mfg_date", "batch", "due_date", "planned_start", "priority",
            "delay_reason", "sales_order", "sales_order_item", "parent_work_order", "principal", "issue_mode",
            "qty_completed", "qty_rejected", "qty_rework", "estimated_unit_cost", "cost_issued",
            "cost_returned", "cost_absorbed", "cost_received", "cost_variance", "wip_value", "notes",
            "released_at", "completed_at", "closed_at", "created_at", "updated_at",
        ]
        read_only_fields = [
            "number", "kind", "product", "status", "parent_work_order", "issue_mode",
            "qty_completed", "qty_rejected", "qty_rework", "estimated_unit_cost", "cost_issued",
            "cost_returned", "cost_absorbed", "cost_received", "cost_variance",
            "released_at", "completed_at", "closed_at", "created_at", "updated_at",
        ]
        extra_kwargs = {
            "serial_numbers": {"required": False},
            "batch_no": {"required": False, "allow_blank": True},
            "exp_date": {"required": False, "allow_null": True},
            "mfg_date": {"required": False, "allow_null": True},
            "due_date": {"required": False, "allow_null": True},
            "planned_start": {"required": False, "allow_null": True},
            "notes": {"required": False, "allow_blank": True},
        }

    def validate_qty(self, value):
        return _qty_must_be_positive(value)

    def validate_priority(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError("Priority is from 1 (most urgent) to 5.")
        return value

    def create(self, validated_data):
        from .services import _snapshot_bom
        from .services import bom as bom_service
        from .services.common import get_settings, next_number

        lines_data = validated_data.pop("component_lines", None)
        company = validated_data["company"]
        with transaction.atomic():
            validated_data["issue_mode"] = get_settings(company).default_issue_mode
            validated_data["number"] = next_number(company, "mfg_wo", "WO")
            wo = WorkOrder.objects.create(**validated_data)
            _snapshot_bom(wo)
            bom_service.lock_bom(wo.bom)
            if lines_data:
                self._apply_component_lines(wo, lines_data)
        return wo

    def update(self, instance, validated_data):
        lines_data = validated_data.pop("component_lines", None)
        if instance.status != WorkOrder.Status.DRAFT:
            # Once released only the plan fields move (dates, priority, notes, delay reason).
            allowed = {"due_date", "planned_start", "priority", "notes", "delay_reason"}
            validated_data = {k: v for k, v in validated_data.items() if k in allowed}
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
            if "principal_supplied" in payload and instance.principal_id:
                line.principal_supplied = bool(payload.get("principal_supplied"))
            line.save()


class MfgSettingsSerializer(serializers.ModelSerializer):
    rm_warehouse = CompanyPrimaryKeyRelatedField(queryset=Warehouse.objects.all(), allow_null=True, required=False)
    fg_warehouse = CompanyPrimaryKeyRelatedField(queryset=Warehouse.objects.all(), allow_null=True, required=False)
    scrap_warehouse = CompanyPrimaryKeyRelatedField(
        queryset=Warehouse.objects.all(), allow_null=True, required=False,
    )
    quarantine_warehouse = CompanyPrimaryKeyRelatedField(
        queryset=Warehouse.objects.all(), allow_null=True, required=False,
    )

    class Meta:
        model = MfgSettings
        fields = [
            "id", "default_issue_mode", "backflush_default", "rm_warehouse", "fg_warehouse",
            "scrap_warehouse", "quarantine_warehouse", "backdate_days", "extra_issue_approval_pct",
            "final_receipt_tolerance_pct", "auto_close_days", "over_receipt_pct", "itc04_frequency",
            "jw_input_limit_days", "jw_capital_limit_days", "jw_input_alert_days", "jw_capital_alert_days",
        ]
