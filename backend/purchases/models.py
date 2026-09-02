from django.db import models
from django.utils import timezone

from core.models import DocumentLineModel, DocumentTotalsModel


class PurchaseInvoice(DocumentTotalsModel):
    """`Draft` → `Completed` → `Cancelled` (§4.2)."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        COMPLETED = "COMPLETED"
        CANCELLED = "CANCELLED"
        # BUG-212: mirrors SalesInvoice.Status.RETURNED — without this, a
        # fully-returned purchase stayed indistinguishable from COMPLETED in
        # listings/filters, unlike the equivalent sales flow.
        RETURNED = "RETURNED"

    class PurchaseType(models.TextChoices):
        GST = "GST"
        NON_GST = "NON_GST"

    supplier = models.ForeignKey("masters.Supplier", on_delete=models.PROTECT, related_name="purchase_invoices")
    warehouse = models.ForeignKey(
        "inventory.Warehouse", null=True, blank=True, on_delete=models.PROTECT, related_name="purchase_invoices"
    )
    cost_center = models.ForeignKey(
        "accounting.CostCenter", null=True, blank=True, on_delete=models.PROTECT, related_name="purchase_invoices"
    )
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
    # BB-000264: set only by Tally adapter.
    is_opening_balance = models.BooleanField(default=False)
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
    is_reverse_charge = models.BooleanField(default=False)

    class ItcEligibility(models.TextChoices):
        UNREVIEWED = "UNREVIEWED", "Unreviewed"
        CLAIMABLE = "CLAIMABLE", "Claimable"
        INELIGIBLE = "INELIGIBLE", "Ineligible"
        REVERSED = "REVERSED", "Reversed"

    itc_eligibility = models.CharField(
        max_length=12,
        choices=ItcEligibility.choices,
        default=ItcEligibility.UNREVIEWED,
        help_text="BB-000614: never claim ITC until explicitly marked CLAIMABLE.",
    )
    rcm_taxable = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    rcm_cgst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    rcm_sgst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    rcm_igst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    rcm_cess = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    company_gstin = models.ForeignKey(
        "accounts.CompanyGstin",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="purchase_invoices",
    )
    tds_section = models.CharField(max_length=16, blank=True)
    tds_rate = models.DecimalField(max_digits=6, decimal_places=3, default=0)
    tds_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class PriceMode(models.TextChoices):
        EXCLUSIVE = "EXCLUSIVE", "Tax exclusive"
        INCLUSIVE = "INCLUSIVE", "Tax inclusive"

    price_mode = models.CharField(
        max_length=12, choices=PriceMode.choices, default=PriceMode.EXCLUSIVE
    )

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
    batch = models.ForeignKey(
        "inventory.BatchLot", null=True, blank=True, on_delete=models.PROTECT, related_name="purchase_items"
    )
    # Snapshots at line save — document stays stable if product master changes later.
    hsn_code = models.CharField(max_length=8, blank=True)
    mrp = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unit_name = models.CharField(max_length=32, blank=True, default="PCS")
    uqc_code = models.CharField(max_length=8, blank=True)
    unit_price_inclusive = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    batch_no = models.CharField(max_length=64, blank=True)
    exp_date = models.DateField(null=True, blank=True)
    mfg_date = models.DateField(null=True, blank=True)
    serial_numbers = models.JSONField(default=list, blank=True)


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
    class Condition(models.TextChoices):
        SELLABLE = "SELLABLE", "Sellable"
        DAMAGED = "DAMAGED", "Damaged"

    purchase_return = models.ForeignKey(PurchaseReturn, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="purchase_return_items")
    # BB-000383: batch/serial for track_batch / track_serial returns.
    batch = models.ForeignKey(
        "inventory.BatchLot", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    serial_numbers = models.JSONField(default=list, blank=True)
    condition = models.CharField(max_length=16, choices=Condition.choices, default=Condition.SELLABLE)


class PurchaseNoteReason(models.TextChoices):
    SALES_RETURN = "SALES_RETURN", "Goods return"  # legacy; prefer PURCHASE_RETURN
    PURCHASE_RETURN = "PURCHASE_RETURN", "Purchase return"  # BB-000449
    POST_SALE_DISCOUNT = "POST_SALE_DISCOUNT", "Post-purchase discount"
    DEFICIENCY_IN_SERVICE = "DEFICIENCY_IN_SERVICE", "Deficiency in service"
    CORRECTION_OF_INVOICE = "CORRECTION_OF_INVOICE", "Correction of invoice"
    OTHERS = "OTHERS", "Others"


class PurchaseCreditNote(DocumentTotalsModel):
    """Recorded supplier credit note — feeds payables; no generated GST PDF required."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        COMPLETED = "COMPLETED"
        CANCELLED = "CANCELLED"

    supplier = models.ForeignKey("masters.Supplier", on_delete=models.PROTECT, related_name="purchase_credit_notes")
    purchase_invoice = models.ForeignKey(
        PurchaseInvoice, null=True, blank=True, on_delete=models.PROTECT, related_name="credit_notes"
    )
    purchase_return = models.ForeignKey(
        "PurchaseReturn",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="credit_notes",
    )
    number = models.CharField(max_length=32, blank=True, db_index=True)
    supplier_note_number = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    note_date = models.DateField(default=timezone.localdate)
    reason = models.CharField(
        max_length=32, choices=PurchaseNoteReason.choices, default=PurchaseNoteReason.CORRECTION_OF_INVOICE
    )
    reason_detail = models.CharField(max_length=255, blank=True)
    additional_charges = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    invoice_discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    invoice_discount_mode = models.CharField(
        max_length=12,
        choices=PurchaseInvoice.DiscountMode.choices,
        default=PurchaseInvoice.DiscountMode.AFTER_TAX,
    )
    auto_round_off = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    # BB-000336: RCM memo mirrors PurchaseInvoice — populated when the linked
    # invoice is reverse-charge so GL/GSTR can reverse RCM payable/ITC, not
    # normal Input GST/AP.
    rcm_taxable = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    rcm_cgst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    rcm_sgst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    rcm_igst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    rcm_cess = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ["-note_date", "-id"]
        indexes = [models.Index(fields=["company", "status", "note_date"])]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=~models.Q(number=""),
                name="uniq_purchase_credit_note_number_per_company",
            )
        ]


class PurchaseCreditNoteItem(DocumentLineModel):
    credit_note = models.ForeignKey(PurchaseCreditNote, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "masters.Product", on_delete=models.PROTECT, related_name="purchase_credit_note_items"
    )
    # BB-000364: lineage back to the originating purchase invoice line for HSN/UQC snapshot fidelity.
    source_item = models.ForeignKey(
        "PurchaseItem", null=True, blank=True, on_delete=models.SET_NULL, related_name="credit_note_items"
    )
    hsn_code = models.CharField(max_length=8, blank=True)
    unit_name = models.CharField(max_length=32, blank=True, default="PCS")
    uqc_code = models.CharField(max_length=8, blank=True)


class PurchaseDebitNote(DocumentTotalsModel):
    """Recorded supplier debit note."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        COMPLETED = "COMPLETED"
        CANCELLED = "CANCELLED"

    supplier = models.ForeignKey("masters.Supplier", on_delete=models.PROTECT, related_name="purchase_debit_notes")
    purchase_invoice = models.ForeignKey(
        PurchaseInvoice, null=True, blank=True, on_delete=models.PROTECT, related_name="debit_notes"
    )
    number = models.CharField(max_length=32, blank=True, db_index=True)
    supplier_note_number = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    note_date = models.DateField(default=timezone.localdate)
    reason = models.CharField(
        max_length=32, choices=PurchaseNoteReason.choices, default=PurchaseNoteReason.CORRECTION_OF_INVOICE
    )
    reason_detail = models.CharField(max_length=255, blank=True)
    invoice_discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    invoice_discount_mode = models.CharField(
        max_length=12,
        choices=PurchaseInvoice.DiscountMode.choices,
        default=PurchaseInvoice.DiscountMode.AFTER_TAX,
    )
    auto_round_off = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    # BB-000336: RCM memo mirrors PurchaseInvoice (see PurchaseCreditNote).
    rcm_taxable = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    rcm_cgst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    rcm_sgst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    rcm_igst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    rcm_cess = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ["-note_date", "-id"]
        indexes = [models.Index(fields=["company", "status", "note_date"])]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=~models.Q(number=""),
                name="uniq_purchase_debit_note_number_per_company",
            )
        ]


class PurchaseDebitNoteItem(DocumentLineModel):
    debit_note = models.ForeignKey(PurchaseDebitNote, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "masters.Product", on_delete=models.PROTECT, related_name="purchase_debit_note_items"
    )
    source_item = models.ForeignKey(
        "PurchaseItem", null=True, blank=True, on_delete=models.SET_NULL, related_name="debit_note_items"
    )
    hsn_code = models.CharField(max_length=8, blank=True)
    unit_name = models.CharField(max_length=32, blank=True, default="PCS")
    uqc_code = models.CharField(max_length=8, blank=True)


class PurchaseOrder(DocumentTotalsModel):
    """Commitment document — convert to draft purchase invoice (Phase 1.5)."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        CONVERTED = "CONVERTED"
        CANCELLED = "CANCELLED"

    supplier = models.ForeignKey("masters.Supplier", on_delete=models.PROTECT, related_name="purchase_orders")
    number = models.CharField(max_length=32, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    purchase_type = models.CharField(
        max_length=8,
        choices=PurchaseInvoice.PurchaseType.choices,
        default=PurchaseInvoice.PurchaseType.GST,
    )
    order_date = models.DateField(default=timezone.localdate)
    expected_delivery = models.DateField(null=True, blank=True)
    payment_terms_days = models.PositiveIntegerField(default=0)
    additional_charges = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    invoice_discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    invoice_discount_mode = models.CharField(
        max_length=12,
        choices=PurchaseInvoice.DiscountMode.choices,
        default=PurchaseInvoice.DiscountMode.AFTER_TAX,
    )
    auto_round_off = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    terms_text = models.TextField(blank=True)
    converted_purchase = models.ForeignKey(
        PurchaseInvoice, null=True, blank=True, on_delete=models.SET_NULL, related_name="source_orders"
    )

    class Meta:
        ordering = ["-order_date", "-id"]
        indexes = [models.Index(fields=["company", "status", "order_date"])]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=~models.Q(number=""),
                name="uniq_purchase_order_number_per_company",
            )
        ]


class PurchaseOrderItem(DocumentLineModel):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="purchase_order_items")
