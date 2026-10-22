"""Quality: inspections, non-conformances and the codes that classify defects (MFG-20..23).

Behind the MFG_QUALITY company flag. Batch hold status lives on ``inventory.BatchLot``; this app
decides it. Nothing here imports manufacturing: a production receipt is referenced by id.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models

from core.models import CompanyScopedModel


class DefectCode(CompanyScopedModel):
    class Severity(models.TextChoices):
        MINOR = "MINOR", "Minor"
        MAJOR = "MAJOR", "Major"
        CRITICAL = "CRITICAL", "Critical"

    code = models.CharField(max_length=24)
    name = models.CharField(max_length=120)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.MINOR)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_defect_code_per_company"),
        ]


class InspectionTemplate(CompanyScopedModel):
    class Stage(models.TextChoices):
        INCOMING = "INCOMING", "Incoming material"
        IN_PROCESS = "IN_PROCESS", "In process"
        FINAL = "FINAL", "Finished goods"

    name = models.CharField(max_length=120)
    product = models.ForeignKey(
        "masters.Product", null=True, blank=True, on_delete=models.PROTECT, related_name="inspection_templates",
    )
    stage = models.CharField(max_length=12, choices=Stage.choices, default=Stage.INCOMING)
    sample_size = models.PositiveIntegerField(default=1)
    notes = models.CharField(max_length=500, blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]


class InspectionParameter(models.Model):
    class Kind(models.TextChoices):
        NUMERIC = "NUMERIC", "Number within limits"
        TEXT = "TEXT", "Text"
        PASS_FAIL = "PASS_FAIL", "Pass or fail"

    template = models.ForeignKey(InspectionTemplate, on_delete=models.CASCADE, related_name="parameters")
    company = models.ForeignKey("accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PASS_FAIL)
    min_value = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    max_value = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    unit = models.CharField(max_length=24, blank=True, default="")
    mandatory = models.BooleanField(default=True)
    sequence = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sequence", "id"]

    def save(self, *args, **kwargs):
        if self.template_id and not self.company_id:
            self.company_id = self.template.company_id
        super().save(*args, **kwargs)


class Inspection(CompanyScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        COMPLETED = "COMPLETED"
        CANCELLED = "CANCELLED"

    class Decision(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PASS = "PASS", "Pass"
        FAIL = "FAIL", "Fail"
        HOLD = "HOLD", "Hold"
        REWORK = "REWORK", "Rework"

    class Source(models.TextChoices):
        GRN_ITEM = "GRN_ITEM", "Goods receipt line"
        RECEIPT = "RECEIPT", "Production receipt"
        BATCH = "BATCH", "Batch in stock"

    number = models.CharField(max_length=32, blank=True, default="", db_index=True)
    template = models.ForeignKey(
        InspectionTemplate, null=True, blank=True, on_delete=models.SET_NULL, related_name="inspections",
    )
    template_name = models.CharField(max_length=120, blank=True, default="")
    stage = models.CharField(max_length=12, choices=InspectionTemplate.Stage.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    decision = models.CharField(max_length=8, choices=Decision.choices, default=Decision.PENDING)
    source_type = models.CharField(max_length=10, choices=Source.choices)
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="inspections")
    batch = models.ForeignKey(
        "inventory.BatchLot", null=True, blank=True, on_delete=models.PROTECT, related_name="inspections",
    )
    grn_item = models.ForeignKey(
        "purchases.GoodsReceiptItem", null=True, blank=True, on_delete=models.SET_NULL, related_name="inspections",
    )
    # A production receipt, by id (this app does not import manufacturing).
    receipt_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    supplier = models.ForeignKey(
        "masters.Supplier", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    qty_inspected = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    qty_accepted = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    qty_rejected = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    inspector = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    inspected_on = models.DateField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["company", "status", "decision"], name="insp_company_state_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"], condition=~models.Q(number=""), name="uniq_inspection_number_per_company",
            ),
        ]


class InspectionResult(models.Model):
    inspection = models.ForeignKey(Inspection, on_delete=models.CASCADE, related_name="results")
    company = models.ForeignKey("accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True)
    # The parameter as it stood when the inspection was made: later template edits do not change it.
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=10, choices=InspectionParameter.Kind.choices)
    min_value = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    max_value = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    unit = models.CharField(max_length=24, blank=True, default="")
    mandatory = models.BooleanField(default=True)
    sequence = models.PositiveSmallIntegerField(default=0)
    value_numeric = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    value_text = models.CharField(max_length=255, blank=True, default="")
    passed = models.BooleanField(null=True, blank=True)

    class Meta:
        ordering = ["sequence", "id"]

    def save(self, *args, **kwargs):
        if self.inspection_id and not self.company_id:
            self.company_id = self.inspection.company_id
        super().save(*args, **kwargs)


class NonConformance(CompanyScopedModel):
    class Status(models.TextChoices):
        OPEN = "OPEN"
        ACTION = "ACTION", "Action under way"
        VERIFIED = "VERIFIED", "Verified"
        CLOSED = "CLOSED"

    class Source(models.TextChoices):
        INSPECTION = "INSPECTION", "Failed inspection"
        GRN = "GRN", "Goods receipt rejection"
        COMPLAINT = "COMPLAINT", "Customer complaint"
        INTERNAL = "INTERNAL", "Found inside"

    number = models.CharField(max_length=32, blank=True, default="", db_index=True)
    source_type = models.CharField(max_length=12, choices=Source.choices, default=Source.INTERNAL)
    inspection = models.ForeignKey(
        Inspection, null=True, blank=True, on_delete=models.SET_NULL, related_name="non_conformances",
    )
    complaint = models.ForeignKey(
        "complaints.Complaint", null=True, blank=True, on_delete=models.SET_NULL, related_name="non_conformances",
    )
    product = models.ForeignKey("masters.Product", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey("inventory.BatchLot", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    supplier = models.ForeignKey("masters.Supplier", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    customer = models.ForeignKey("masters.Customer", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    defect_code = models.ForeignKey(DefectCode, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    qty = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    description = models.TextField(blank=True, default="")
    root_cause = models.TextField(blank=True, default="")
    action_taken = models.TextField(blank=True, default="")
    preventive_action = models.TextField(blank=True, default="")
    owner = models.ForeignKey(
        "accounts.CompanyUser", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["company", "status", "due_date"], name="ncr_company_state_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"], condition=~models.Q(number=""), name="uniq_ncr_number_per_company",
            ),
        ]
