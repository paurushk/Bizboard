from decimal import Decimal

from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditFieldsModel(TimeStampedModel):
    """Row-level audit fields (E0.10)."""

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        abstract = True


class CompanyScopedModel(AuditFieldsModel):
    """Tenancy mixin — every business table carries company_id (E0.7)."""

    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True
    )

    class Meta:
        abstract = True


class DocumentTotalsModel(CompanyScopedModel):
    """Shared monetary totals for tax documents."""

    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    taxable_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    cgst_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    sgst_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    igst_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    round_off = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0"))
    grand_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))

    class Meta:
        abstract = True


class DocumentLineModel(models.Model):
    """Shared line-item fields for tax documents."""

    description = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    taxable_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    cgst = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    sgst = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    igst = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))

    class Meta:
        abstract = True


class DocumentSeries(models.Model):
    """Independent number sequences per document type (Document Number Service)."""

    company = models.ForeignKey("accounts.Company", on_delete=models.CASCADE, related_name="document_series")
    doc_type = models.CharField(max_length=32)
    prefix = models.CharField(max_length=16)
    next_number = models.PositiveIntegerField(default=1)
    padding = models.PositiveSmallIntegerField(default=5)

    class Meta:
        unique_together = [("company", "doc_type")]

    def __str__(self):
        return f"{self.company_id}:{self.doc_type}"


class AuditEvent(models.Model):
    """Activity audit log — Create/Update/Delete/Login/Logout/Import (E0.11)."""

    class Action(models.TextChoices):
        CREATE = "CREATE"
        UPDATE = "UPDATE"
        DELETE = "DELETE"
        LOGIN = "LOGIN"
        LOGOUT = "LOGOUT"
        IMPORT = "IMPORT"

    company = models.ForeignKey(
        "accounts.Company", null=True, blank=True, on_delete=models.CASCADE, related_name="audit_events"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_events"
    )
    action = models.CharField(max_length=16, choices=Action.choices)
    entity_type = models.CharField(max_length=64, blank=True)
    entity_id = models.CharField(max_length=64, blank=True)
    description = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["company", "action", "created_at"])]


def file_upload_path(instance, filename):
    return f"company_{instance.company_id}/{instance.kind.lower()}/{filename}"


class FileAsset(CompanyScopedModel):
    """File Service storage — logos, invoice PDFs, attachments, import files (E0.14)."""

    class Kind(models.TextChoices):
        LOGO = "LOGO"
        INVOICE_PDF = "INVOICE_PDF"
        ATTACHMENT = "ATTACHMENT"
        IMPORT = "IMPORT"
        EXPORT = "EXPORT"

    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.ATTACHMENT)
    file = models.FileField(upload_to=file_upload_path)
    original_name = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=128, blank=True)
    size = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]


class Notification(CompanyScopedModel):
    """Notification Service log — Email/WhatsApp (SMS/Push stubbed for later)."""

    class Channel(models.TextChoices):
        EMAIL = "EMAIL"
        WHATSAPP = "WHATSAPP"
        SMS = "SMS"
        PUSH = "PUSH"

    class Status(models.TextChoices):
        QUEUED = "QUEUED"
        SENT = "SENT"
        FAILED = "FAILED"

    channel = models.CharField(max_length=16, choices=Channel.choices)
    recipient = models.CharField(max_length=255)
    subject = models.CharField(max_length=255, blank=True)
    body = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    share_link = models.CharField(max_length=1024, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
