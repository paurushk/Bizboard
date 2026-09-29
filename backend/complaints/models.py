from django.db import models

from core.models import CompanyScopedModel


class Complaint(CompanyScopedModel):
    class Category(models.TextChoices):
        DAMAGED = "DAMAGED"
        WRONG_DELIVERY = "WRONG_DELIVERY"
        QUALITY = "QUALITY"
        OTHER = "OTHER"

    class Status(models.TextChoices):
        OPEN = "OPEN"
        INSPECTING = "INSPECTING"
        APPROVED = "APPROVED"
        REJECTED = "REJECTED"
        RESOLVED = "RESOLVED"

    number = models.CharField(max_length=32, blank=True)
    customer = models.ForeignKey("masters.Customer", on_delete=models.PROTECT, related_name="complaints")
    source_invoice = models.ForeignKey(
        "sales.SalesInvoice", null=True, blank=True, on_delete=models.PROTECT, related_name="complaints",
    )
    category = models.CharField(max_length=16, choices=Category.choices)
    description = models.TextField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    inspection_notes = models.TextField(blank=True)
    sales_return = models.ForeignKey(
        "sales.SalesReturn", null=True, blank=True, on_delete=models.PROTECT, related_name="complaints",
    )
    sales_credit_note = models.ForeignKey(
        "sales.SalesCreditNote", null=True, blank=True, on_delete=models.PROTECT, related_name="complaints",
    )
    replacement_order = models.ForeignKey(
        "sales.SalesOrder", null=True, blank=True, on_delete=models.PROTECT, related_name="complaints",
    )
    assigned_to = models.ForeignKey(
        "accounts.CompanyUser", null=True, blank=True, on_delete=models.SET_NULL, related_name="complaints",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=~models.Q(number=""),
                name="uniq_complaint_number_per_company",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "status"], name="complaint_company_status_idx"),
            models.Index(fields=["company", "customer"], name="complaint_company_customer_idx"),
            models.Index(fields=["company", "source_invoice"], name="complaint_company_invoice_idx"),
        ]


class ComplaintAttachment(CompanyScopedModel):
    complaint = models.ForeignKey(Complaint, on_delete=models.CASCADE, related_name="attachments")
    file = models.ForeignKey("core.FileAsset", on_delete=models.PROTECT, related_name="+")


class SupplierComplaint(CompanyScopedModel):
    """Same workflow as a customer complaint, pointed at a purchase bill and a debit note."""

    class Category(models.TextChoices):
        DAMAGED = "DAMAGED"
        WRONG_DELIVERY = "WRONG_DELIVERY"
        QUALITY = "QUALITY"
        OTHER = "OTHER"

    class Status(models.TextChoices):
        OPEN = "OPEN"
        INSPECTING = "INSPECTING"
        APPROVED = "APPROVED"
        REJECTED = "REJECTED"
        RESOLVED = "RESOLVED"

    number = models.CharField(max_length=32, blank=True)
    supplier = models.ForeignKey("masters.Supplier", on_delete=models.PROTECT, related_name="supplier_complaints")
    source_invoice = models.ForeignKey(
        "purchases.PurchaseInvoice",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="supplier_complaints",
    )
    category = models.CharField(max_length=16, choices=Category.choices)
    description = models.TextField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    inspection_notes = models.TextField(blank=True)
    purchase_debit_note = models.ForeignKey(
        "purchases.PurchaseDebitNote",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="supplier_complaints",
    )
    assigned_to = models.ForeignKey(
        "accounts.CompanyUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supplier_complaints",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=~models.Q(number=""),
                name="uniq_scomp_number_per_company",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "status"], name="scomp_company_status_idx"),
            models.Index(fields=["company", "supplier"], name="scomp_company_supplier_idx"),
            models.Index(fields=["company", "source_invoice"], name="scomp_company_invoice_idx"),
        ]


class SupplierComplaintAttachment(CompanyScopedModel):
    complaint = models.ForeignKey(SupplierComplaint, on_delete=models.CASCADE, related_name="attachments")
    file = models.ForeignKey("core.FileAsset", on_delete=models.PROTECT, related_name="+")
