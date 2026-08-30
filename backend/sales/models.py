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
    warehouse = models.ForeignKey(
        "inventory.Warehouse", null=True, blank=True, on_delete=models.PROTECT, related_name="sales_invoices"
    )
    cost_center = models.ForeignKey(
        "accounting.CostCenter", null=True, blank=True, on_delete=models.PROTECT, related_name="sales_invoices"
    )
    number = models.CharField(max_length=32, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    invoice_type = models.CharField(max_length=8, choices=InvoiceType.choices, default=InvoiceType.GST)
    # Wave 16D: SEZ / export supply classification for e-invoice + GSTR-1.
    class SupplyType(models.TextChoices):
        B2B = "B2B", "B2B"
        SEZWP = "SEZWP", "SEZ with payment"
        SEZWOP = "SEZWOP", "SEZ without payment"
        EXPWP = "EXPWP", "Export with payment"
        EXPWOP = "EXPWOP", "Export without payment"
        DEXP = "DEXP", "Deemed export"

    supply_type = models.CharField(
        max_length=8, choices=SupplyType.choices, default=SupplyType.B2B, blank=True
    )
    is_reverse_charge = models.BooleanField(default=False)
    rcm_taxable = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    rcm_cgst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    rcm_sgst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    rcm_igst = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    rcm_cess = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    ecommerce_operator_gstin = models.CharField(max_length=15, blank=True)
    invoice_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)
    payment_terms_days = models.PositiveIntegerField(default=0)
    class DiscountMode(models.TextChoices):
        AFTER_TAX = "AFTER_TAX", "Cash discount (after tax)"
        BEFORE_TAX = "BEFORE_TAX", "Discount (reduces GST)"

    additional_charges = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    charges_hsn = models.CharField(max_length=8, blank=True)
    charges_gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    invoice_discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    invoice_discount_mode = models.CharField(
        max_length=12, choices=DiscountMode.choices, default=DiscountMode.AFTER_TAX
    )
    auto_round_off = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    terms_text = models.TextField(blank=True)
    # BB-000264: set only by Tally adapter — never trust notes==TALLY_OPENING.
    is_opening_balance = models.BooleanField(default=False)
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

    class EInvoiceStatus(models.TextChoices):
        NONE = "NONE"
        READY = "READY"
        QUEUED = "QUEUED"
        GENERATED = "GENERATED"
        MANUAL_IRN = "MANUAL_IRN"  # BB-000214: client-attested IRN (not GSP-verified)
        FAILED = "FAILED"
        CANCELLED = "CANCELLED"

    class EwayStatus(models.TextChoices):
        NONE = "NONE"
        READY = "READY"
        GENERATED = "GENERATED"
        MANUAL_EWB = "MANUAL_EWB"  # BB-000273: client-attested e-Way (not GSP-verified)
        FAILED = "FAILED"
        CANCELLED = "CANCELLED"

    einvoice_status = models.CharField(
        max_length=16, choices=EInvoiceStatus.choices, default=EInvoiceStatus.NONE
    )
    irn = models.CharField(max_length=64, blank=True)
    ack_no = models.CharField(max_length=32, blank=True)
    ack_date = models.DateTimeField(null=True, blank=True)
    einvoice_qr = models.TextField(blank=True)
    einvoice_error = models.TextField(blank=True)
    eway_status = models.CharField(max_length=12, choices=EwayStatus.choices, default=EwayStatus.NONE)
    eway_bill_no = models.CharField(max_length=32, blank=True)
    eway_valid_upto = models.DateTimeField(null=True, blank=True)
    eway_error = models.TextField(blank=True)
    # Filing identity overlays (D16) — blank means use live customer fields.
    filing_party_gstin = models.CharField(max_length=15, blank=True)
    filing_place_of_supply = models.CharField(max_length=64, blank=True)
    # Phase 2 tax mode / transport
    class PriceMode(models.TextChoices):
        EXCLUSIVE = "EXCLUSIVE", "Tax exclusive"
        INCLUSIVE = "INCLUSIVE", "Tax inclusive"

    price_mode = models.CharField(
        max_length=12, choices=PriceMode.choices, default=PriceMode.EXCLUSIVE
    )
    transporter_name = models.CharField(max_length=128, blank=True)
    transporter_id = models.CharField(max_length=32, blank=True)
    vehicle_number = models.CharField(max_length=32, blank=True)
    transport_distance_km = models.PositiveIntegerField(null=True, blank=True)
    sub_supply_type = models.CharField(max_length=8, default="1")
    trans_mode = models.CharField(max_length=8, default="1")
    # Wave 17A: stamp which company GSTIN this document was issued under.
    company_gstin = models.ForeignKey(
        "accounts.CompanyGstin",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sales_invoices",
    )
    tcs_section = models.CharField(max_length=16, blank=True)
    tcs_rate = models.DecimalField(max_digits=6, decimal_places=3, default=0)
    tcs_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # True once complete() folded tcs_amount into grand_total (avoid ledger double-count).
    tcs_in_grand_total = models.BooleanField(default=False)

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
    class SupplyNature(models.TextChoices):
        TAXABLE = "TAXABLE", "Taxable"
        NIL = "NIL", "Nil rated"
        EXEMPT = "EXEMPT", "Exempt"
        NON_GST = "NON_GST", "Non-GST"

    invoice = models.ForeignKey(SalesInvoice, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="sales_items")
    batch = models.ForeignKey(
        "inventory.BatchLot", null=True, blank=True, on_delete=models.PROTECT, related_name="sales_items"
    )
    # Snapshots at line save — PDF / GSTR stay stable if product master changes later.
    hsn_code = models.CharField(max_length=8, blank=True)
    mrp = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unit_name = models.CharField(max_length=32, blank=True, default="PCS")
    uqc_code = models.CharField(max_length=8, blank=True)
    # Tax-inclusive entered price (kept so re-save does not double-extract).
    unit_price_inclusive = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    batch_no = models.CharField(max_length=64, blank=True)
    exp_date = models.DateField(null=True, blank=True)
    mfg_date = models.DateField(null=True, blank=True)
    serial_numbers = models.JSONField(default=list, blank=True)
    supply_nature = models.CharField(
        max_length=12, choices=SupplyNature.choices, default=SupplyNature.TAXABLE
    )


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
    converted_order = models.ForeignKey(
        "SalesOrder", null=True, blank=True, on_delete=models.SET_NULL, related_name="source_quotations"
    )

    class Meta:
        ordering = ["-quotation_date", "-id"]
        # BUG-717: SalesInvoice/SalesReturn both get this same shape of
        # index; Quotation was missed despite being listed/filtered the
        # same way (company + status, ordered by date).
        indexes = [models.Index(fields=["company", "status", "quotation_date"])]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=~models.Q(number=""),
                name="uniq_quotation_number_per_company",
            )
        ]


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
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=~models.Q(number=""),
                name="uniq_sales_return_number_per_company",
            )
        ]


class SalesReturnItem(DocumentLineModel):
    class Condition(models.TextChoices):
        SELLABLE = "SELLABLE", "Sellable"
        DAMAGED = "DAMAGED", "Damaged"

    sales_return = models.ForeignKey(SalesReturn, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="sales_return_items")
    serial_numbers = models.JSONField(default=list, blank=True)
    condition = models.CharField(max_length=16, choices=Condition.choices, default=Condition.SELLABLE)


class NoteReason(models.TextChoices):
    """GSTR-1 Table 9B-aligned reason categories (Phase 1 D9)."""

    SALES_RETURN = "SALES_RETURN", "Sales return"
    POST_SALE_DISCOUNT = "POST_SALE_DISCOUNT", "Post-sale discount"
    DEFICIENCY_IN_SERVICE = "DEFICIENCY_IN_SERVICE", "Deficiency in service"
    CORRECTION_OF_INVOICE = "CORRECTION_OF_INVOICE", "Correction of invoice"
    OTHERS = "OTHERS", "Others"


class SalesCreditNote(DocumentTotalsModel):
    """Value-only credit against a completed sales invoice — no stock movement."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        COMPLETED = "COMPLETED"
        CANCELLED = "CANCELLED"

    customer = models.ForeignKey("masters.Customer", on_delete=models.PROTECT, related_name="sales_credit_notes")
    sales_invoice = models.ForeignKey(SalesInvoice, on_delete=models.PROTECT, related_name="credit_notes")
    sales_return = models.ForeignKey(
        "SalesReturn",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="credit_notes",
    )
    number = models.CharField(max_length=32, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    note_date = models.DateField(default=timezone.localdate)
    reason = models.CharField(max_length=32, choices=NoteReason.choices, default=NoteReason.CORRECTION_OF_INVOICE)
    reason_detail = models.CharField(max_length=255, blank=True)
    invoice_discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    invoice_discount_mode = models.CharField(
        max_length=12,
        choices=SalesInvoice.DiscountMode.choices,
        default=SalesInvoice.DiscountMode.AFTER_TAX,
    )
    auto_round_off = models.BooleanField(default=True)
    additional_charges = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    charges_hsn = models.CharField(max_length=8, blank=True)
    charges_gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tcs_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tcs_in_grand_total = models.BooleanField(default=False)
    filing_party_gstin = models.CharField(max_length=15, blank=True)
    filing_place_of_supply = models.CharField(max_length=64, blank=True)
    company_gstin = models.ForeignKey(
        "accounts.CompanyGstin",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sales_credit_notes",
    )
    notes = models.TextField(blank=True)
    pdf_status = models.CharField(
        max_length=8, choices=SalesInvoice.PdfStatus.choices, default=SalesInvoice.PdfStatus.NONE
    )
    pdf_file = models.ForeignKey(
        "core.FileAsset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    irn = models.CharField(max_length=64, blank=True)
    ack_no = models.CharField(max_length=32, blank=True)
    ack_date = models.DateTimeField(null=True, blank=True)
    einvoice_qr = models.TextField(blank=True)
    einvoice_status = models.CharField(
        max_length=16,
        choices=SalesInvoice.EInvoiceStatus.choices,
        default=SalesInvoice.EInvoiceStatus.NONE,
    )
    einvoice_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-note_date", "-id"]
        indexes = [models.Index(fields=["company", "status", "note_date"])]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=~models.Q(number=""),
                name="uniq_sales_credit_note_number_per_company",
            )
        ]


class SalesCreditNoteItem(DocumentLineModel):
    credit_note = models.ForeignKey(SalesCreditNote, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="sales_credit_note_items")
    source_item = models.ForeignKey(
        SalesItem, null=True, blank=True, on_delete=models.SET_NULL, related_name="credit_note_items"
    )
    hsn_code = models.CharField(max_length=8, blank=True)
    unit_name = models.CharField(max_length=32, blank=True, default="PCS")
    uqc_code = models.CharField(max_length=8, blank=True)
    supply_nature = models.CharField(
        max_length=12,
        choices=SalesItem.SupplyNature.choices,
        default=SalesItem.SupplyNature.TAXABLE,
    )


class SalesDebitNote(DocumentTotalsModel):
    """Value-only debit against a completed sales invoice — no stock movement."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        COMPLETED = "COMPLETED"
        CANCELLED = "CANCELLED"

    customer = models.ForeignKey("masters.Customer", on_delete=models.PROTECT, related_name="sales_debit_notes")
    sales_invoice = models.ForeignKey(SalesInvoice, on_delete=models.PROTECT, related_name="debit_notes")
    number = models.CharField(max_length=32, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    note_date = models.DateField(default=timezone.localdate)
    reason = models.CharField(max_length=32, choices=NoteReason.choices, default=NoteReason.CORRECTION_OF_INVOICE)
    reason_detail = models.CharField(max_length=255, blank=True)
    invoice_discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    invoice_discount_mode = models.CharField(
        max_length=12,
        choices=SalesInvoice.DiscountMode.choices,
        default=SalesInvoice.DiscountMode.AFTER_TAX,
    )
    auto_round_off = models.BooleanField(default=True)
    additional_charges = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    charges_hsn = models.CharField(max_length=8, blank=True)
    charges_gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tcs_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tcs_in_grand_total = models.BooleanField(default=False)
    filing_party_gstin = models.CharField(max_length=15, blank=True)
    filing_place_of_supply = models.CharField(max_length=64, blank=True)
    company_gstin = models.ForeignKey(
        "accounts.CompanyGstin",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sales_debit_notes",
    )
    notes = models.TextField(blank=True)
    pdf_status = models.CharField(
        max_length=8, choices=SalesInvoice.PdfStatus.choices, default=SalesInvoice.PdfStatus.NONE
    )
    pdf_file = models.ForeignKey(
        "core.FileAsset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    irn = models.CharField(max_length=64, blank=True)
    ack_no = models.CharField(max_length=32, blank=True)
    ack_date = models.DateTimeField(null=True, blank=True)
    einvoice_qr = models.TextField(blank=True)
    einvoice_status = models.CharField(
        max_length=16,
        choices=SalesInvoice.EInvoiceStatus.choices,
        default=SalesInvoice.EInvoiceStatus.NONE,
    )
    einvoice_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-note_date", "-id"]
        indexes = [models.Index(fields=["company", "status", "note_date"])]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=~models.Q(number=""),
                name="uniq_sales_debit_note_number_per_company",
            )
        ]


class SalesDebitNoteItem(DocumentLineModel):
    debit_note = models.ForeignKey(SalesDebitNote, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="sales_debit_note_items")
    source_item = models.ForeignKey(
        SalesItem, null=True, blank=True, on_delete=models.SET_NULL, related_name="debit_note_items"
    )
    hsn_code = models.CharField(max_length=8, blank=True)
    unit_name = models.CharField(max_length=32, blank=True, default="PCS")
    uqc_code = models.CharField(max_length=8, blank=True)
    supply_nature = models.CharField(
        max_length=12,
        choices=SalesItem.SupplyNature.choices,
        default=SalesItem.SupplyNature.TAXABLE,
    )


class SalesOrder(DocumentTotalsModel):
    """Commitment document — confirm (reserve) then convert to draft sales invoice."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        CONFIRMED = "CONFIRMED"
        CONVERTED = "CONVERTED"
        CANCELLED = "CANCELLED"

    customer = models.ForeignKey("masters.Customer", on_delete=models.PROTECT, related_name="sales_orders")
    warehouse = models.ForeignKey(
        "inventory.Warehouse", null=True, blank=True, on_delete=models.PROTECT, related_name="sales_orders"
    )
    number = models.CharField(max_length=32, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    invoice_type = models.CharField(
        max_length=8, choices=SalesInvoice.InvoiceType.choices, default=SalesInvoice.InvoiceType.GST
    )
    order_date = models.DateField(default=timezone.localdate)
    expected_delivery = models.DateField(null=True, blank=True)
    payment_terms_days = models.PositiveIntegerField(default=0)
    additional_charges = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    invoice_discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    invoice_discount_mode = models.CharField(
        max_length=12,
        choices=SalesInvoice.DiscountMode.choices,
        default=SalesInvoice.DiscountMode.AFTER_TAX,
    )
    auto_round_off = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    terms_text = models.TextField(blank=True)
    converted_invoice = models.ForeignKey(
        SalesInvoice, null=True, blank=True, on_delete=models.SET_NULL, related_name="source_orders"
    )

    class Meta:
        ordering = ["-order_date", "-id"]
        indexes = [models.Index(fields=["company", "status", "order_date"])]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=~models.Q(number=""),
                name="uniq_sales_order_number_per_company",
            )
        ]


class SalesOrderItem(DocumentLineModel):
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="sales_order_items")


class DeliveryChallan(DocumentTotalsModel):
    """Dispatch record — stock posts on complete when company.stock_on_delivery_challan."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        COMPLETED = "COMPLETED"
        CANCELLED = "CANCELLED"

    customer = models.ForeignKey("masters.Customer", on_delete=models.PROTECT, related_name="delivery_challans")
    warehouse = models.ForeignKey(
        "inventory.Warehouse", null=True, blank=True, on_delete=models.PROTECT, related_name="delivery_challans"
    )
    sales_order = models.ForeignKey(
        SalesOrder, null=True, blank=True, on_delete=models.SET_NULL, related_name="challans"
    )
    number = models.CharField(max_length=32, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    challan_date = models.DateField(default=timezone.localdate)
    vehicle_number = models.CharField(max_length=32, blank=True)
    transporter_name = models.CharField(max_length=128, blank=True)
    transporter_id = models.CharField(max_length=32, blank=True)
    transport_distance_km = models.PositiveIntegerField(null=True, blank=True)
    sub_supply_type = models.CharField(max_length=8, default="8")
    trans_mode = models.CharField(max_length=8, default="1")
    notes = models.TextField(blank=True)
    pdf_status = models.CharField(
        max_length=8, choices=SalesInvoice.PdfStatus.choices, default=SalesInvoice.PdfStatus.NONE
    )
    pdf_file = models.ForeignKey(
        "core.FileAsset", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    # True when complete posted outbound SALE movements (company.stock_on_delivery_challan).
    stock_posted = models.BooleanField(default=False)
    converted_invoice = models.ForeignKey(
        SalesInvoice, null=True, blank=True, on_delete=models.SET_NULL, related_name="source_challans"
    )
    eway_status = models.CharField(
        max_length=12, choices=SalesInvoice.EwayStatus.choices, default=SalesInvoice.EwayStatus.NONE
    )
    eway_bill_no = models.CharField(max_length=32, blank=True)
    eway_valid_upto = models.DateTimeField(null=True, blank=True)
    eway_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-challan_date", "-id"]
        indexes = [models.Index(fields=["company", "status", "challan_date"])]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=~models.Q(number=""),
                name="uniq_delivery_challan_number_per_company",
            )
        ]


class DeliveryChallanItem(DocumentLineModel):
    challan = models.ForeignKey(DeliveryChallan, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="delivery_challan_items")
    # BB-000402: serial tracking on challan stock path.
    serial_numbers = models.JSONField(default=list, blank=True)


class RecurringInvoiceSchedule(models.Model):
    """BB-000669: template that spawns DRAFT sales invoices on a cadence."""

    class Cadence(models.TextChoices):
        MONTHLY = "MONTHLY"
        WEEKLY = "WEEKLY"

    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="recurring_invoice_schedules",
    )
    customer = models.ForeignKey(
        "masters.Customer", on_delete=models.PROTECT, related_name="recurring_invoice_schedules",
    )
    company_gstin = models.ForeignKey(
        "accounts.CompanyGstin", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="recurring_invoice_schedules",
    )
    cadence = models.CharField(max_length=12, choices=Cadence.choices, default=Cadence.MONTHLY)
    next_run_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    line_template = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    updated_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        ordering = ["-next_run_at", "-id"]
        indexes = [
            models.Index(fields=["company", "is_active", "next_run_at"], name="sales_recur_company_idx"),
        ]


class RecurringInvoiceRun(models.Model):
    """Skip-duplicate record for a generated draft (schedule + YYYY-MM / YYYY-Www)."""

    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="recurring_invoice_runs",
    )
    schedule = models.ForeignKey(
        RecurringInvoiceSchedule, on_delete=models.CASCADE, related_name="runs",
    )
    period_key = models.CharField(max_length=16)
    invoice = models.ForeignKey(
        SalesInvoice, null=True, blank=True, on_delete=models.SET_NULL, related_name="recurring_runs",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["schedule", "period_key"], name="uniq_recurring_invoice_run_period",
            ),
        ]
        indexes = [models.Index(fields=["company", "period_key"], name="sales_recurrun_co_period_idx")]
