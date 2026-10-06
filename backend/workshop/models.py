from decimal import Decimal

from django.db import models

from core.models import CompanyScopedModel


class ServiceBay(CompanyScopedModel):
    name = models.CharField(max_length=80)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_service_bay_name_per_company"),
        ]


class JobCard(CompanyScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        IN_PROGRESS = "IN_PROGRESS"
        INVOICED = "INVOICED"
        CANCELLED = "CANCELLED"

    number = models.CharField(max_length=32, blank=True)
    customer = models.ForeignKey("masters.Customer", on_delete=models.PROTECT, related_name="job_cards")
    technician = models.ForeignKey(
        "accounts.CompanyUser", null=True, blank=True, on_delete=models.SET_NULL, related_name="job_cards",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    complaint = models.TextField(blank=True)
    registration_no = models.CharField(max_length=32, blank=True)
    vehicle_model = models.CharField(max_length=80, blank=True)
    odometer_reading = models.DecimalField(max_digits=12, decimal_places=1, null=True, blank=True)
    service_bay = models.ForeignKey(
        ServiceBay, null=True, blank=True, on_delete=models.SET_NULL, related_name="jobs",
    )
    scheduled_start = models.DateTimeField(null=True, blank=True)
    scheduled_end = models.DateTimeField(null=True, blank=True)
    sales_invoice = models.ForeignKey(
        "sales.SalesInvoice", null=True, blank=True, on_delete=models.PROTECT, related_name="job_cards",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=~models.Q(number=""),
                name="uniq_jobcard_number_per_company",
            ),
        ]


class JobCardLine(CompanyScopedModel):
    class Kind(models.TextChoices):
        PART = "PART"
        LABOUR = "LABOUR"

    job = models.ForeignKey(JobCard, on_delete=models.CASCADE, related_name="lines")
    kind = models.CharField(max_length=8, choices=Kind.choices)
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="job_card_lines")
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    labour_minutes = models.PositiveIntegerField(default=0)
    technician_commission_percent = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("0"),
    )
    batch = models.ForeignKey(
        "inventory.BatchLot", null=True, blank=True, on_delete=models.PROTECT, related_name="job_card_lines",
    )
    batch_no = models.CharField(max_length=64, blank=True)
    serial = models.ForeignKey(
        "inventory.SerialNumber", null=True, blank=True, on_delete=models.PROTECT, related_name="job_card_lines",
    )

    class Meta:
        ordering = ["id"]
