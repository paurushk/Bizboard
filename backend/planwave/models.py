from django.conf import settings
from django.db import models
from core.models import CompanyScopedModel, TimeStampedModel


class IntegrityQuarantine(CompanyScopedModel):
    """An open row blocks period close and GST export. Billing stays open."""

    keys = models.JSONField(default=list)
    detail = models.JSONField(default=dict)
    cleared_at = models.DateTimeField(null=True, blank=True)
    cleared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        indexes = [models.Index(fields=["company", "cleared_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["company"], condition=models.Q(cleared_at__isnull=True),
                name="uniq_open_quarantine_per_company",
            ),
        ]


class ApprovalRequest(CompanyScopedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING"
        APPROVED = "APPROVED"
        REJECTED = "REJECTED"
        EXPIRED = "EXPIRED"

    action = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    reason = models.TextField(blank=True)
    expires_at = models.DateTimeField()
    decided_at = models.DateTimeField(null=True, blank=True)
    token = models.CharField(max_length=64, blank=True)
    token_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["company", "status", "action"])]


class CreditUnlock(CompanyScopedModel):
    customer = models.ForeignKey("masters.Customer", on_delete=models.PROTECT, related_name="credit_unlocks")
    code = models.CharField(max_length=32)
    reason = models.TextField()
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_credit_unlock_code"),
        ]


class PartySnapshot(CompanyScopedModel):
    entity_type = models.CharField(max_length=64)
    entity_id = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    backfill_from_master = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "entity_type", "entity_id"], name="uniq_party_snapshot"),
        ]


class ItcBillCheck(CompanyScopedModel):
    source_type = models.CharField(max_length=32)
    source_id = models.CharField(max_length=64)
    invoice_held = models.BooleanField(default=False)
    goods_received = models.BooleanField(default=False)
    paid_within_180 = models.BooleanField(default=False)
    supplier_tax_attested = models.BooleanField(default=False)
    return_filed_attested = models.BooleanField(default=False)
    blocked_credit = models.BooleanField(default=False)
    claimed = models.BooleanField(default=False)
    deadline_status = models.CharField(max_length=16, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "source_type", "source_id"], name="uniq_itc_bill_check"),
        ]


class BlockedCreditRule(TimeStampedModel):
    """Statutory table. Not tenant-scoped, so a company session can still read it."""

    hsn_prefix = models.CharField(max_length=8, blank=True)
    expense_category = models.CharField(max_length=64, blank=True)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    description = models.CharField(max_length=255)


class EwayStubAction(CompanyScopedModel):
    class Action(models.TextChoices):
        PART_B = "PART_B"
        EXTEND = "EXTEND"
        SPLIT = "SPLIT"
        TRANSFER_PART_B = "TRANSFER_PART_B"

    document_type = models.CharField(max_length=32)
    document_id = models.CharField(max_length=64)
    action = models.CharField(max_length=32, choices=Action.choices)
    payload = models.JSONField(default=dict)
    history = models.JSONField(default=list)
    bill_status = models.CharField(max_length=16, default="ACTIVE")

    class Meta:
        indexes = [models.Index(fields=["company", "document_type", "document_id"])]


class PharmacyDispense(CompanyScopedModel):
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="pharmacy_dispenses")
    schedule = models.CharField(max_length=8)
    patient_name = models.CharField(max_length=255)
    prescriber_name = models.CharField(max_length=255)
    prescriber_registration = models.CharField(max_length=64)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    batch_no = models.CharField(max_length=64, blank=True)
    invoice_number = models.CharField(max_length=32, blank=True)
    prescription_note = models.TextField(blank=True)
    prescription_image = models.ForeignKey(
        "core.FileAsset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )


class AnomalyReview(CompanyScopedModel):
    class Status(models.TextChoices):
        OPEN = "OPEN"
        DISMISSED = "DISMISSED"

    kind = models.CharField(max_length=32)
    subject_id = models.CharField(max_length=64)
    detail = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)


class LoggingWindow(CompanyScopedModel):
    """A window with logging_enabled False refuses the Rule 11(g) certificate."""

    starts_on = models.DateField()
    ends_on = models.DateField(null=True, blank=True)
    logging_enabled = models.BooleanField(default=True)


class BulkImportBatch(CompanyScopedModel):
    file_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=16, default="DRY_RUN")
    report = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "file_hash"], name="uniq_bulk_import_hash"),
        ]


class TallyImportJob(CompanyScopedModel):
    """TallyPrime mapping step. ENABLE_TALLY stays off; this stores the map only."""

    ledger_map = models.JSONField(default=dict)
    stock_map = models.JSONField(default=dict)
    financial_year = models.CharField(max_length=7)
    status = models.CharField(max_length=16, default="MAPPED")
    voucher_count = models.PositiveIntegerField(default=0)


class UserWarehouseAccess(CompanyScopedModel):
    """A user may work in many godowns, with one default."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="warehouse_access")
    warehouse = models.ForeignKey("inventory.Warehouse", on_delete=models.PROTECT, related_name="user_access")
    is_default = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "user", "warehouse"], name="uniq_user_warehouse"),
        ]


class PosCartHold(CompanyScopedModel):
    """A held POS cart. Expiry releases the hold and keeps the row."""

    label = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    expires_at = models.DateTimeField()
    released_at = models.DateTimeField(null=True, blank=True)
