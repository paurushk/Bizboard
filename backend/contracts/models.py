from django.db import models
from django.utils import timezone

from core.models import CompanyScopedModel

from .status import compute_contract_status


class Contract(CompanyScopedModel):
    class Type(models.TextChoices):
        WARRANTY = "WARRANTY"
        AMC = "AMC"
        SUBSCRIPTION = "SUBSCRIPTION"
        INSURANCE = "INSURANCE"
        OTHER = "OTHER"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE"
        EXPIRING = "EXPIRING"
        EXPIRED = "EXPIRED"
        CANCELLED = "CANCELLED"

    number = models.CharField(max_length=32, blank=True)
    customer = models.ForeignKey("masters.Customer", on_delete=models.PROTECT, related_name="contracts")
    product = models.ForeignKey(
        "masters.Product", null=True, blank=True, on_delete=models.PROTECT, related_name="contracts",
    )
    contract_type = models.CharField(max_length=16, choices=Type.choices)
    start_date = models.DateField()
    end_date = models.DateField()
    renewal_reminder_days = models.PositiveSmallIntegerField(default=30)
    value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    recurring_schedule = models.ForeignKey(
        "sales.RecurringInvoiceSchedule",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="contracts",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["end_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=~models.Q(number=""),
                name="uniq_contract_number_per_company",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "status"], name="contract_company_status_idx"),
            models.Index(fields=["company", "end_date"], name="contract_company_end_idx"),
            models.Index(fields=["company", "customer"], name="contract_company_customer_idx"),
        ]

    def save(self, *args, **kwargs):
        if self.status != self.Status.CANCELLED:
            self.status = compute_contract_status(
                self.end_date, self.renewal_reminder_days, timezone.localdate(),
            )
        super().save(*args, **kwargs)


class ContractProduct(CompanyScopedModel):
    """Products covered by one contract. A contract may list several. No serial."""

    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="covered_products")
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="contract_coverages")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["contract", "product"],
                name="uniq_contract_product",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "contract"], name="contract_product_co_idx"),
        ]


class ContractServiceEvent(CompanyScopedModel):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="service_events")
    ticket = models.ForeignKey(
        "support.Ticket", null=True, blank=True, on_delete=models.SET_NULL, related_name="service_events",
    )
    occurred_at = models.DateTimeField()
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-occurred_at"]


class ContractDocument(CompanyScopedModel):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="documents")
    file = models.ForeignKey("core.FileAsset", on_delete=models.PROTECT, related_name="+")
