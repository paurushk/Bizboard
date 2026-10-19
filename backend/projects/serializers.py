from decimal import ROUND_HALF_UP, Decimal

from rest_framework import serializers

from .models import Project, ProjectMilestone
from .services import project_totals


class ProjectMilestoneSerializer(serializers.ModelSerializer):
    service_product_name = serializers.CharField(source="service_product.name", read_only=True)
    gst_rate = serializers.SerializerMethodField()
    gst_amount = serializers.SerializerMethodField()
    amount_incl_gst = serializers.SerializerMethodField()
    invoice_number = serializers.SerializerMethodField()
    invoice_status = serializers.SerializerMethodField()

    class Meta:
        model = ProjectMilestone
        fields = [
            "id", "name", "sequence", "amount", "target_completion_date",
            "service_product", "service_product_name", "status", "sales_invoice", "invoice_number",
            "invoice_status", "gst_rate", "gst_amount", "amount_incl_gst",
        ]
        read_only_fields = ["id", "status", "sales_invoice"]

    def get_gst_rate(self, obj):
        return str(obj.service_product.gst_rate)

    def _gst(self, obj):
        rate = Decimal(str(obj.service_product.gst_rate or 0))
        return (Decimal(str(obj.amount)) * rate / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def get_gst_amount(self, obj):
        return str(self._gst(obj))

    def get_amount_incl_gst(self, obj):
        return str(Decimal(str(obj.amount)) + self._gst(obj))

    def get_invoice_number(self, obj):
        return (obj.sales_invoice.number or "") if obj.sales_invoice_id else ""

    def get_invoice_status(self, obj):
        return obj.sales_invoice.status if obj.sales_invoice_id else ""


class _ProjectBase(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    contract_number = serializers.SerializerMethodField()
    planned_total = serializers.SerializerMethodField()
    invoiced_total = serializers.SerializerMethodField()
    ready_total = serializers.SerializerMethodField()
    remaining_total = serializers.SerializerMethodField()
    percent_complete = serializers.SerializerMethodField()
    over_budget = serializers.SerializerMethodField()

    def get_contract_number(self, obj):
        return (obj.contract.number or f"#{obj.contract_id}") if obj.contract_id else ""

    def _totals(self, obj):
        cache = getattr(obj, "_totals_cache", None)
        if cache is None:
            cache = obj._totals_cache = project_totals(obj)
        return cache

    def get_planned_total(self, obj):
        return str(self._totals(obj)["planned_total"])

    def get_invoiced_total(self, obj):
        return str(self._totals(obj)["invoiced_total"])

    def get_ready_total(self, obj):
        return str(self._totals(obj)["ready_total"])

    def get_remaining_total(self, obj):
        return str(self._totals(obj)["remaining_total"])

    def get_percent_complete(self, obj):
        return self._totals(obj)["percent_complete"]

    def get_over_budget(self, obj):
        return self._totals(obj)["over_budget"]

    COMMON = [
        "id", "number", "customer", "customer_name", "name", "status", "notes", "start_date", "end_date",
        "contract_value", "contract", "contract_number", "planned_total", "invoiced_total", "ready_total",
        "remaining_total", "percent_complete", "over_budget", "created_at", "updated_at",
    ]


class ProjectListSerializer(_ProjectBase):
    """List rows carry milestone totals and a count, not the milestone array."""

    milestone_count = serializers.SerializerMethodField()

    def get_milestone_count(self, obj):
        return len(obj.milestones.all())

    class Meta:
        model = Project
        fields = [*_ProjectBase.COMMON, "milestone_count"]
        read_only_fields = fields


class ProjectSerializer(_ProjectBase):
    milestones = ProjectMilestoneSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = [*_ProjectBase.COMMON, "milestones"]
        read_only_fields = ["id", "number", "status", "created_at", "updated_at"]
