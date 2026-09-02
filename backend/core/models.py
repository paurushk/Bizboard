from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.validators import validate_gst_rate


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
    cess_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    round_off = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0"))
    grand_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))

    class Meta:
        abstract = True


class DocumentLineModel(models.Model):
    """Shared line-item fields for tax documents.

    company is denormalized from the parent document for tenant defense-in-depth
    (BB-000017 / next-batch-8).
    """

    company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.CASCADE,
        related_name="+",
    )
    description = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(
        max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))]
    )
    # BUG-211: previously unvalidated — a negative unit_price or a
    # discount_percent > 100 silently produced negative taxable/tax amounts
    # with no server-side rejection.
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))],
    )
    discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    # BUG-210: Product.gst_rate is validated against ALLOWED_GST_RATES, but
    # the line-item rate actually used to compute charged/filed tax was not.
    gst_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0"), validators=[validate_gst_rate],
    )
    # B-06: rate legally in force on the document date, snapshotted so later
    # HsnRate edits never re-rate a filed month.
    applied_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    rate_version = models.CharField(max_length=64, blank=True, default="")
    rate_override = models.BooleanField(default=False)
    rate_override_reason = models.CharField(max_length=255, blank=True, default="")
    taxable_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    cgst = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    sgst = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    igst = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    cess_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    # TAX-12 / R1-016: specific (per-unit) compensation cess. This is ADDED to
    # any ad-valorem cess from `cess_rate` — it does NOT replace it (pan-masala /
    # tobacco style "X% + ₹Y per unit"). See core.services.billing._apply_line_tax
    # and reporting.gst_returns._rate_buckets, which must agree on this.
    cess_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    cess = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))

    class Meta:
        abstract = True


class DocumentSeries(models.Model):
    """Independent number sequences per document type (Document Number Service).

    BB-000646 / ADR-A25: unique per company + doc_type + GSTIN + FY.
    Empty gstin_key/fy_label is the legacy company-wide series.
    """

    company = models.ForeignKey("accounts.Company", on_delete=models.CASCADE, related_name="document_series")
    doc_type = models.CharField(max_length=32)
    prefix = models.CharField(max_length=16)
    next_number = models.PositiveIntegerField(default=1)
    padding = models.PositiveSmallIntegerField(default=5)
    gstin_key = models.CharField(max_length=15, blank=True, default="")
    fy_label = models.CharField(max_length=8, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "doc_type", "gstin_key", "fy_label"],
                name="uniq_document_series_gstin_fy",
            )
        ]

    def __str__(self):
        extra = f":{self.gstin_key}:{self.fy_label}" if (self.gstin_key or self.fy_label) else ""
        return f"{self.company_id}:{self.doc_type}{extra}"


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
    # 64, not 16: audit actions are dotted namespaces now (e.g.
    # "tenant.restore_sandbox"). SQLite ignores varchar length; Postgres raised
    # DataError on the longer values (test_bb_000668 restore 500).
    action = models.CharField(max_length=64)
    entity_type = models.CharField(max_length=64, blank=True)
    entity_id = models.CharField(max_length=64, blank=True)
    description = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["company", "action", "created_at"])]


def file_upload_path(instance, filename):
    import os
    import uuid

    ext = os.path.splitext(filename or "")[1][:16]
    safe_ext = ext if ext.startswith(".") else ""
    return f"company_{instance.company_id}/{instance.kind.lower()}/{uuid.uuid4().hex}{safe_ext}"


class FileAsset(CompanyScopedModel):
    """File Service storage — logos, invoice PDFs, attachments, import files (E0.14)."""

    class Kind(models.TextChoices):
        LOGO = "LOGO"
        INVOICE_PDF = "INVOICE_PDF"
        CREDIT_NOTE_PDF = "CREDIT_NOTE_PDF"
        DEBIT_NOTE_PDF = "DEBIT_NOTE_PDF"
        CHALLAN_PDF = "CHALLAN_PDF"
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
        # BB-000282: WhatsApp share-link ready (not a delivered send).
        LINK_READY = "LINK_READY"
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


class MoneyFieldAudit(CompanyScopedModel):
    """Wave 16B: append-only money field change log (BB-000522)."""

    entity_type = models.CharField(max_length=64)
    entity_id = models.PositiveBigIntegerField()
    field = models.CharField(max_length=64)
    old_value = models.CharField(max_length=64, blank=True)
    new_value = models.CharField(max_length=64, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "entity_type", "entity_id"], name="money_audit_entity_idx"),
        ]


def log_money_change(*, company, entity_type, entity_id, field, old_value, new_value, user=None):
    if str(old_value) == str(new_value):
        return None
    return MoneyFieldAudit.objects.create(
        company=company,
        entity_type=entity_type,
        entity_id=entity_id,
        field=field,
        old_value=str(old_value)[:64],
        new_value=str(new_value)[:64],
        user=user,
        created_by=user,
        updated_by=user,
    )


class StatutoryDocumentEvent(models.Model):
    """BB-000177: append-only statutory lifecycle log (complete / amend / cancel)."""

    class EventType(models.TextChoices):
        COMPLETE = "COMPLETE"
        AMEND = "AMEND"
        CANCEL = "CANCEL"
        IRN = "IRN"
        EWAY = "EWAY"

    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="statutory_events"
    )
    entity_type = models.CharField(max_length=64)
    entity_id = models.PositiveBigIntegerField()
    event_type = models.CharField(max_length=16, choices=EventType.choices)
    payload = models.JSONField(default=dict, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "entity_type", "entity_id"], name="stat_evt_entity_idx"),
        ]


class IdempotencyRecord(CompanyScopedModel):
    """BB-000610: durable Idempotency-Key store (survives cache flush / multi-worker)."""

    scope = models.CharField(max_length=64)
    key = models.CharField(max_length=128)
    status_code = models.PositiveSmallIntegerField(default=200)
    body = models.JSONField(default=dict, blank=True)
    resource_id = models.CharField(max_length=64, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "scope", "key"],
                name="uniq_idempotency_company_scope_key",
            ),
        ]


class HelpEvent(CompanyScopedModel):
    """First-party Help analytics (raw query text stays on-box)."""

    name = models.CharField(max_length=64, db_index=True)
    intent_id = models.CharField(max_length=64, blank=True)
    source = models.CharField(max_length=32, blank=True)
    state = models.CharField(max_length=24, blank=True)
    screen = models.CharField(max_length=128, blank=True)
    query = models.TextField(blank=True)
    props = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "name", "created_at"], name="help_evt_co_name_idx"),
            models.Index(fields=["company", "intent_id", "created_at"], name="help_evt_co_intent_idx"),
        ]


class HelpFeedback(CompanyScopedModel):
    """Capture-only 'still stuck' rows. No promise of a human reply."""

    query = models.TextField(blank=True)
    screen = models.CharField(max_length=128, blank=True)
    role = models.CharField(max_length=32, blank=True)
    intent_id = models.CharField(max_length=64, blank=True)
    note = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "created_at"], name="help_fb_co_created_idx"),
        ]


def log_statutory_event(
    *,
    company,
    entity_type: str,
    entity_id: int,
    event_type: str,
    payload: dict | None = None,
    user=None,
):
    """Record a statutory document lifecycle event."""
    return StatutoryDocumentEvent.objects.create(
        company=company,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        payload=payload or {},
        user=user,
    )
