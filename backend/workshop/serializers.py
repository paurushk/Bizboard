from rest_framework import serializers

from .models import JobCard, JobCardLine, ServiceBay


def _person(member):
    user = getattr(member, "user", None)
    if user is None:
        return ""
    return (getattr(user, "full_name", "") or getattr(user, "email", "") or "").strip()


class ServiceBaySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceBay
        fields = ["id", "name", "is_active"]

    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("A bay needs a name.")
        request = self.context.get("request")
        if request is not None:
            from core.permissions import get_company_user

            company = get_company_user(request).company
            clash = ServiceBay.objects.filter(company=company, name__iexact=value)
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError("A bay with this name already exists.")
        return value


class JobCardLineSerializer(serializers.ModelSerializer):
    commission_amount = serializers.SerializerMethodField()
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = JobCardLine
        fields = [
            "id", "kind", "product", "product_name", "quantity", "unit_price",
            "labour_minutes", "technician_commission_percent", "commission_amount",
            "serial", "batch", "batch_no", "covered_by_contract",
        ]
        read_only_fields = ["id", "commission_amount", "product_name"]

    def get_commission_amount(self, line):
        from .services import labour_commission_amount

        return str(labour_commission_amount(line))

    def validate_quantity(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate_unit_price(self, value):
        # Zero is legitimate: warranty parts and goodwill labour are not billed.
        if value is None or value < 0:
            raise serializers.ValidationError("Price cannot be negative.")
        return value


class _JobCardBase(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    technician_name = serializers.SerializerMethodField()
    service_bay_name = serializers.SerializerMethodField()
    contract_number = serializers.SerializerMethodField()
    ticket_number = serializers.SerializerMethodField()
    complaint_number = serializers.SerializerMethodField()
    invoice_number = serializers.SerializerMethodField()
    invoice_status = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()
    gst_total = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()

    def get_technician_name(self, job):
        return _person(job.technician)

    def get_service_bay_name(self, job):
        return job.service_bay.name if job.service_bay_id else ""

    def get_contract_number(self, job):
        return (job.contract.number or f"#{job.contract_id}") if job.contract_id else ""

    def get_ticket_number(self, job):
        return job.ticket.number if job.ticket_id else ""

    def get_complaint_number(self, job):
        return job.source_complaint.number if job.source_complaint_id else ""

    def get_invoice_number(self, job):
        invoice = job.sales_invoice if job.sales_invoice_id else None
        return (invoice.number or "") if invoice else ""

    def get_invoice_status(self, job):
        return job.sales_invoice.status if job.sales_invoice_id else ""

    def _totals(self, job):
        from .services import job_totals

        cache = getattr(job, "_totals_cache", None)
        if cache is None:
            cache = job._totals_cache = job_totals(job)
        return cache

    def get_subtotal(self, job):
        return str(self._totals(job)["subtotal"])

    def get_gst_total(self, job):
        return str(self._totals(job)["gst_total"])

    def get_total(self, job):
        return str(self._totals(job)["total"])

    COMMON = [
        "id", "number", "customer", "customer_name", "technician", "technician_name", "status",
        "complaint", "registration_no", "vehicle_model", "odometer_reading", "service_bay",
        "service_bay_name", "scheduled_start", "scheduled_end", "sales_invoice", "invoice_number",
        "invoice_status", "contract", "contract_number", "ticket", "ticket_number", "source_complaint",
        "complaint_number", "warehouse", "subtotal", "gst_total", "total", "created_at", "updated_at",
    ]


class JobCardListSerializer(_JobCardBase):
    """List rows: no nested lines and no serial history (those ran a query per row)."""

    line_count = serializers.SerializerMethodField()

    def get_line_count(self, job):
        return len(job.lines.all())

    class Meta:
        model = JobCard
        fields = [*_JobCardBase.COMMON, "line_count"]
        read_only_fields = fields


class JobCardSerializer(_JobCardBase):
    lines = JobCardLineSerializer(many=True, read_only=True)
    serial_history = serializers.SerializerMethodField()

    class Meta:
        model = JobCard
        fields = [*_JobCardBase.COMMON, "lines", "serial_history"]
        read_only_fields = ["id", "number", "status", "sales_invoice", "created_at", "updated_at"]

    def get_serial_history(self, job):
        from .history import serial_history

        return serial_history(job)
