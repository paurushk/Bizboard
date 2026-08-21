"""GST return period control and export snapshots (Phase 2)."""

from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class GstReturnPeriod(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "OPEN"
        SOFT_CLOSED = "SOFT_CLOSED"
        CLOSED = "CLOSED"

    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="gst_return_periods"
    )
    period = models.CharField(max_length=7, db_index=True)  # YYYY-MM
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    dirty_after_snapshot = models.BooleanField(default=False)

    class Meta:
        unique_together = [("company", "period")]
        indexes = [models.Index(fields=["company", "period", "status"])]

    def __str__(self):
        return f"{self.company_id}:{self.period}:{self.status}"


class GstReturnSnapshot(TimeStampedModel):
    class ReturnType(models.TextChoices):
        GSTR1 = "GSTR1"
        GSTR3B = "GSTR3B"
        GSTR9 = "GSTR9"

    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="gst_return_snapshots"
    )
    return_type = models.CharField(max_length=8, choices=ReturnType.choices)
    period = models.CharField(max_length=16, db_index=True)  # YYYY-MM or FY label
    payload = models.JSONField()
    content_hash = models.CharField(max_length=64)
    builder_version = models.CharField(max_length=32)
    generated_at = models.DateTimeField()
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        indexes = [models.Index(fields=["company", "return_type", "period"])]
        ordering = ["-generated_at", "-id"]
        constraints = [
            # BB-000064: one snapshot row per company + return type + period.
            models.UniqueConstraint(
                fields=["company", "return_type", "period"],
                name="uniq_gst_return_snapshot_period",
            ),
        ]

    def __str__(self):
        return f"{self.return_type}:{self.period}:{self.content_hash[:8]}"


class Gstr2bIngest(TimeStampedModel):
    """Wave 16D: GSTR-2B snapshot rows for ITC match (file or GSP fetch)."""

    class MatchStatus(models.TextChoices):
        UNMATCHED = "UNMATCHED"
        MATCHED = "MATCHED"
        PARTIAL = "PARTIAL"
        REJECTED = "REJECTED"

    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="gstr2b_rows"
    )
    period = models.CharField(max_length=7, db_index=True)  # YYYY-MM
    supplier_gstin = models.CharField(max_length=15, blank=True, db_index=True)
    invoice_number = models.CharField(max_length=64, blank=True)
    invoice_date = models.DateField(null=True, blank=True)
    taxable_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    igst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cgst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    sgst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cess = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    match_status = models.CharField(
        max_length=12, choices=MatchStatus.choices, default=MatchStatus.UNMATCHED
    )

    class ItcEligibility(models.TextChoices):
        UNREVIEWED = "UNREVIEWED"
        CLAIMABLE = "CLAIMABLE"
        INELIGIBLE = "INELIGIBLE"
        REVERSED = "REVERSED"

    itc_eligibility = models.CharField(
        max_length=12,
        choices=ItcEligibility.choices,
        default=ItcEligibility.UNREVIEWED,
    )
    purchase_invoice = models.ForeignKey(
        "purchases.PurchaseInvoice",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gstr2b_matches",
    )
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["company", "period", "match_status"])]
        ordering = ["-id"]
