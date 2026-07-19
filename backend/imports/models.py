from django.db import models

from core.models import CompanyScopedModel


class ImportJob(CompanyScopedModel):
    """Upload → Validate → Preview → Commit → Error report (§15)."""

    class Kind(models.TextChoices):
        CUSTOMERS = "CUSTOMERS"
        SUPPLIERS = "SUPPLIERS"
        PRODUCTS = "PRODUCTS"
        OPENING_STOCK = "OPENING_STOCK"

    class Status(models.TextChoices):
        UPLOADED = "UPLOADED"
        PREVIEWED = "PREVIEWED"
        COMMITTED = "COMMITTED"
        FAILED = "FAILED"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    file = models.ForeignKey("core.FileAsset", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.UPLOADED)
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    error_rows = models.PositiveIntegerField(default=0)
    preview = models.JSONField(default=list, blank=True)
    errors = models.JSONField(default=list, blank=True)
    committed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
