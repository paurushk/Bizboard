from django.db import models

from core.models import CompanyScopedModel


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
    serial = models.ForeignKey(
        "inventory.SerialNumber", null=True, blank=True, on_delete=models.PROTECT, related_name="job_card_lines",
    )

    class Meta:
        ordering = ["id"]
