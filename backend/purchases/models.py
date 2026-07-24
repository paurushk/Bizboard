from django.db import models
from django.utils import timezone

from core.models import DocumentLineModel, DocumentTotalsModel


class PurchaseInvoice(DocumentTotalsModel):
    """`Draft` → `Completed` → `Cancelled` (§4.2)."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        COMPLETED = "COMPLETED"
        CANCELLED = "CANCELLED"

    class PurchaseType(models.TextChoices):
        GST = "GST"
        NON_GST = "NON_GST"

    supplier = models.ForeignKey("masters.Supplier", on_delete=models.PROTECT, related_name="purchase_invoices")
    number = models.CharField(max_length=32, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    purchase_type = models.CharField(max_length=8, choices=PurchaseType.choices, default=PurchaseType.GST)
    invoice_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)
    payment_terms_days = models.PositiveIntegerField(default=0)
    class DiscountMode(models.TextChoices):
        AFTER_TAX = "AFTER_TAX", "Cash discount (after tax)"
        BEFORE_TAX = "BEFORE_TAX", "Discount (reduces GST)"

    additional_charges = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    invoice_discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    invoice_discount_mode = models.CharField(
        max_length=12, choices=DiscountMode.choices, default=DiscountMode.AFTER_TAX
    )
    auto_round_off = models.BooleanField(default=True)
    supplier_bill_number = models.CharField(max_length=64, blank=True)
    notes = models.TextField(blank=True)
    terms_text = models.TextField(blank=True)
    include_bank_details = models.BooleanField(default=False)
    include_payment_qr = models.BooleanField(default=False)
    include_terms = models.BooleanField(default=True)
    signature = models.ForeignKey(
        "core.FileAsset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    attachment = models.ForeignKey(
        "core.FileAsset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-invoice_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=~models.Q(number=""),
                name="uniq_purchase_number_per_company",
            )
        ]
        indexes = [models.Index(fields=["company", "status", "invoice_date"])]

    def __str__(self):
        return self.number or f"Purchase draft #{self.pk}"


class PurchaseItem(DocumentLineModel):
    invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="purchase_items")
    # Snapshots at line save — document stays stable if product master changes later.
    hsn_code = models.CharField(max_length=8, blank=True)
    mrp = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unit_name = models.CharField(max_length=32, blank=True, default="PCS")
    batch_no = models.CharField(max_length=64, blank=True)
    exp_date = models.DateField(null=True, blank=True)
    mfg_date = models.DateField(null=True, blank=True)


class PurchaseReturn(DocumentTotalsModel):
    """`Draft` → `Completed` → `Cancelled` (§4.4)."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        COMPLETED = "COMPLETED"
        CANCELLED = "CANCELLED"

    supplier = models.ForeignKey("masters.Supplier", on_delete=models.PROTECT, related_name="purchase_returns")
    purchase_invoice = models.ForeignKey(
        PurchaseInvoice, null=True, blank=True, on_delete=models.PROTECT, related_name="returns"
    )
    number = models.CharField(max_length=32, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    return_date = models.DateField(default=timezone.localdate)
    reason = models.CharField(max_length=255, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-return_date", "-id"]
        indexes = [models.Index(fields=["company", "status", "return_date"])]


class PurchaseReturnItem(DocumentLineModel):
    purchase_return = models.ForeignKey(PurchaseReturn, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="purchase_return_items")
