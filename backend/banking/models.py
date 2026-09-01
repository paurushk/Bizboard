
from django.db import models
from django.utils import timezone

from core.models import CompanyScopedModel


class AaConsent(CompanyScopedModel):
    """Account Aggregator consent record (Wave 17F scaffold)."""

    class Status(models.TextChoices):
        PENDING = "PENDING"
        ACTIVE = "ACTIVE"
        REVOKED = "REVOKED"
        EXPIRED = "EXPIRED"

    consent_id = models.CharField(max_length=128, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    fi_type = models.CharField(max_length=32, default="DEPOSIT")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "consent_id"], name="uniq_aa_consent_per_company"),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.consent_id} ({self.status})"


class AaTransaction(CompanyScopedModel):
    """AA-ingested bank transaction row."""

    consent = models.ForeignKey(AaConsent, on_delete=models.CASCADE, related_name="transactions")
    txn_id = models.CharField(max_length=128, db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    txn_date = models.DateField(default=timezone.localdate)
    raw = models.JSONField(default=dict, blank=True)
    matched_payment = models.ForeignKey(
        "payments.CustomerReceipt",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="aa_transactions",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "txn_id"], name="uniq_aa_txn_per_company"),
        ]
        ordering = ["-txn_date", "-id"]

    def __str__(self):
        return f"{self.txn_id} {self.amount}"
