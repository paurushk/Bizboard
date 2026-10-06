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


class AliveManager(models.Manager):
    """Lists, search and reports hide soft-deleted masters. Relations use all_objects."""

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class CompanyScopedModel(AuditFieldsModel):
    """Tenancy mixin — every business table carries company_id (E0.7)."""

    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True
    )

    class Meta:
        abstract = True


class SoftDeleteFields(models.Model):
    """Masters are hidden, not erased. Transactions are cancelled, never soft-deleted."""

    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        from django.db.models.deletion import ProtectedError

        referenced = getattr(self, "is_referenced", None)
        if callable(referenced) and referenced():
            raise ProtectedError(
                "This master has transactions and cannot be hard-deleted.",
                {self},
            )
        return super().delete(*args, **kwargs)


class DocumentTotalsModel(CompanyScopedModel):
    """Shared monetary totals for tax documents."""

    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    taxable_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    cgst_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    sgst_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    igst_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    cess_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    # CORE-19: was max_digits=6 (±9999.99). Widened so a future "round to
    # nearest ₹10 / ₹100" rule on a large invoice cannot overflow silently.
    round_off = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
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


def _audit_guard(operation: str) -> None:
    from core.audit_guard import guard

    guard(operation)


class AuditEventQuerySet(models.QuerySet):
    """Append-only: bulk mutation needs ``audit_maintenance()`` (F-SEC-03)."""

    def update(self, **kwargs):
        _audit_guard("QuerySet.update()")
        return super().update(**kwargs)

    def delete(self):
        _audit_guard("QuerySet.delete()")
        return super().delete()

    def bulk_update(self, objs, fields, batch_size=None):
        _audit_guard("QuerySet.bulk_update()")
        return super().bulk_update(objs, fields, batch_size)


class AuditEvent(models.Model):
    """Activity audit log — Create/Update/Delete/Login/Logout/Import (E0.11)."""

    class Action(models.TextChoices):
        CREATE = "CREATE"
        UPDATE = "UPDATE"
        DELETE = "DELETE"
        LOGIN = "LOGIN"
        LOGOUT = "LOGOUT"
        IMPORT = "IMPORT"

    # B7-014: this is a statutory-adjacent activity trail — CASCADE meant a
    # tenant delete (or a stray `.delete()` on Company) silently wiped it.
    # PROTECT forces any such deletion to explicitly deal with the audit
    # trail first (archive/export it) rather than losing it as a side effect.
    company = models.ForeignKey(
        "accounts.Company", null=True, blank=True, on_delete=models.PROTECT, related_name="audit_events"
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
    # F-SEC-03 hash chain, filled by core.services.audit_chain.seal (never at insert).
    # chain_seq orders sealing, not insertion: a row can commit after a higher id.
    chain_seq = models.PositiveBigIntegerField(null=True, blank=True)
    chain_prev = models.CharField(max_length=64, blank=True, default="")
    chain_hash = models.CharField(max_length=64, blank=True, default="")
    sealed_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = AuditEventQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["company", "action", "created_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "chain_seq"],
                condition=models.Q(chain_seq__isnull=False),
                name="uniq_audit_chain_seq_per_company",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            _audit_guard("save() on an existing row")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        _audit_guard("delete()")
        return super().delete(*args, **kwargs)


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
        TELEGRAM = "TELEGRAM"
        IN_APP = "IN_APP"

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

    # B7-014: overrides CompanyScopedModel's abstract `company` field (which
    # is CASCADE for every ordinary business table — that's the right
    # default there) to PROTECT here specifically, since this table is an
    # append-only financial audit trail: a Company delete silently wiping it
    # would erase evidence of every money-field change, not just business
    # data. Redeclared (not a global CompanyScopedModel change) so no other
    # model's cascade behavior is affected.
    company = models.ForeignKey(
        "accounts.Company", on_delete=models.PROTECT, related_name="+", db_index=True
    )

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


MONEY_AUDIT_FIELDS = (
    "additional_charges",
    "invoice_discount",
    "grand_total",
    "taxable_total",
)


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


def money_field_snapshot(instance) -> dict:
    """Capture header money fields before an update so a later diff can log."""
    return {fld: getattr(instance, fld, "") for fld in MONEY_AUDIT_FIELDS}


def log_money_field_diff(*, company, entity_type, entity_id, before: dict, instance, user=None):
    """Log each money field that actually changed (line amends included).

    Serializer `validated_data` does not carry recomputed `grand_total` /
    `taxable_total` after `set_items`; callers must snapshot before the write
    and diff afterwards so completed-doc money edits cannot silently skip
    MoneyFieldAudit (FREEZE_SCOPE_COVERAGE money-field audit ⛔).
    """
    for fld, old in before.items():
        log_money_change(
            company=company,
            entity_type=entity_type,
            entity_id=entity_id,
            field=fld,
            old_value=old,
            new_value=getattr(instance, fld, ""),
            user=user,
        )


class StatutoryDocumentEvent(models.Model):
    """BB-000177: append-only statutory lifecycle log (complete / amend / cancel)."""

    class EventType(models.TextChoices):
        COMPLETE = "COMPLETE"
        AMEND = "AMEND"
        CANCEL = "CANCEL"
        IRN = "IRN"
        EWAY = "EWAY"

    # B7-014: GST audit trail for document lifecycle events — same reasoning
    # as AuditEvent.company above: PROTECT so a Company delete can't
    # silently take the statutory trail with it.
    company = models.ForeignKey(
        "accounts.Company", on_delete=models.PROTECT, related_name="statutory_events"
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
    # sha256 of method + path + body of the request that claimed the key. A later request
    # with the same key but a different hash is rejected (422), not silently replayed.
    # Blank on rows created before this column existed (never rejected).
    request_hash = models.CharField(max_length=64, blank=True, default="")

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


class SequenceCounter(CompanyScopedModel):
    """Per-company counter for non-GST numbers (complaint, ticket, contract)."""

    scope = models.CharField(max_length=32)
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "scope"], name="core_sequence_company_scope_uniq"),
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
