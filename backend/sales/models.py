from django.db import models
from django.utils import timezone

from core.models import DocumentLineModel, DocumentTotalsModel


class SalesInvoice(DocumentTotalsModel):
    """`Draft` → `Completed` → (`Cancelled` | `Returned`) (§4.1)."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        COMPLETED = "COMPLETED"
        CANCELLED = "CANCELLED"
        RETURNED = "RETURNED"

    class InvoiceType(models.TextChoices):
        GST = "GST", "GST Invoice"
        TAX = "TAX", "Tax Invoice"
        RETAIL = "RETAIL", "Retail Invoice"
        NON_GST = "NON_GST", "Non-GST Invoice"

    class PdfStatus(models.TextChoices):
        NONE = "NONE"
        QUEUED = "QUEUED"
        READY = "READY"
        FAILED = "FAILED"

    customer = models.ForeignKey("masters.Customer", on_delete=models.PROTECT, related_name="sales_invoices")
    number = models.CharField(max_length=32, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    invoice_type = models.CharField(max_length=8, choices=InvoiceType.choices, default=InvoiceType.GST)
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
    notes = models.TextField(blank=True)
    terms_text = models.TextField(blank=True)
    include_bank_details = models.BooleanField(default=False)
    include_payment_qr = models.BooleanField(default=True)
    include_terms = models.BooleanField(default=True)
    signature = models.ForeignKey(
        "core.FileAsset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    pdf_status = models.CharField(max_length=8, choices=PdfStatus.choices, default=PdfStatus.NONE)
    pdf_file = models.ForeignKey(
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
                name="uniq_sales_number_per_company",
            )
        ]
        indexes = [models.Index(fields=["company", "status", "invoice_date"])]

    def __str__(self):
        return self.number or f"Sales draft #{self.pk}"


class SalesItem(DocumentLineModel):
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="sales_items")
    # Snapshots at line save — PDF stays stable if product master changes later.
    hsn_code = models.CharField(max_length=8, blank=True)
    mrp = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unit_name = models.CharField(max_length=32, blank=True, default="PCS")
    batch_no = models.CharField(max_length=64, blank=True)
    exp_date = models.DateField(null=True, blank=True)
    mfg_date = models.DateField(null=True, blank=True)


class Quotation(DocumentTotalsModel):
    """`Draft` → `Converted` / `Cancelled` (§4.3)."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        CONVERTED = "CONVERTED"
        CANCELLED = "CANCELLED"

    customer = models.ForeignKey("masters.Customer", on_delete=models.PROTECT, related_name="quotations")
    number = models.CharField(max_length=32, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    invoice_type = models.CharField(
        max_length=8, choices=SalesInvoice.InvoiceType.choices, default=SalesInvoice.InvoiceType.GST
    )
    quotation_date = models.DateField(default=timezone.localdate)
    valid_until = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    converted_invoice = models.ForeignKey(
        SalesInvoice, null=True, blank=True, on_delete=models.SET_NULL, related_name="source_quotations"
    )

    class Meta:
        ordering = ["-quotation_date", "-id"]


class QuotationItem(DocumentLineModel):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="quotation_items")


class SalesReturn(DocumentTotalsModel):
    """`Draft` → `Completed` → `Cancelled` (§4.4). Always linked to an invoice."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        COMPLETED = "COMPLETED"
        CANCELLED = "CANCELLED"

    customer = models.ForeignKey("masters.Customer", on_delete=models.PROTECT, related_name="sales_returns")
    sales_invoice = models.ForeignKey(SalesInvoice, on_delete=models.PROTECT, related_name="returns")
    number = models.CharField(max_length=32, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    return_date = models.DateField(default=timezone.localdate)
    reason = models.CharField(max_length=255, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-return_date", "-id"]
        indexes = [models.Index(fields=["company", "status", "return_date"])]


class SalesReturnItem(DocumentLineModel):
    sales_return = models.ForeignKey(SalesReturn, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="sales_return_items")
