from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import CompanyScopedModel, DocumentLineModel, DocumentTotalsModel


class SalesChannel(models.TextChoices):
    WALK_IN = "WALK_IN", "Walk-in"
    ONLINE = "ONLINE", "Online"
    DISTRIBUTOR = "DISTRIBUTOR", "Distributor"


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
    source_order = models.ForeignKey(
        "SalesOrder", null=True, blank=True, on_delete=models.SET_NULL, related_name="split_invoices",
    )
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
    credit_override_reason = models.CharField(max_length=500, blank=True, default="")
    credit_overridden_by = models.ForeignKey(
        "accounts.CompanyUser", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    credit_overridden_at = models.DateTimeField(null=True, blank=True)
    # GST Guard: OWNER/MANAGER override of a blocking pre-submission issue —
    # mirrors the credit_override_* shape above (reporting.gst_guard).
    gst_guard_override_reason = models.CharField(max_length=500, blank=True, default="")
    gst_guard_overridden_by = models.ForeignKey(
        "accounts.CompanyUser", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    gst_guard_overridden_at = models.DateTimeField(null=True, blank=True)
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
    cancel_reason = models.CharField(max_length=500, blank=True, default="")
    # CFT-120: optimistic concurrency token for completed-invoice amend.
    amend_revision = models.PositiveIntegerField(default=0)
    salesperson = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="pos_sales",
    )
    terminal_id = models.CharField(max_length=64, blank=True, default="")
    terminal_label = models.CharField(max_length=64, blank=True, default="")
    pos_offline = models.BooleanField(default=False)
    pos_outage_id = models.CharField(max_length=64, blank=True, default="")

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
        QUEUED = "QUEUED"
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
    # B2-015: when this e-Way bill was generated -- NIC allows cancellation
    # only within 24h of generation. Null for bills predating this field or
    # attested via mark-eway-generated (no real GSP generation time is known).
    eway_generated_at = models.DateTimeField(null=True, blank=True)
    eway_error = models.TextField(blank=True)
    # Filing identity overlays (D16) — blank means use live customer fields.
    filing_party_gstin = models.CharField(max_length=15, blank=True)
    filing_place_of_supply = models.CharField(max_length=64, blank=True)
    # Complete() set this when a blank customer state was treated as the
    # seller's state because assume_local_state_for_blank_party is on.
    pos_assumed_local = models.BooleanField(default=False)
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
    # True when the operator supplied tcs_amount explicitly — it then overrides the
    # rate at Complete (owner decision 2026-08-31); a rate-only edit clears this.
    tcs_amount_manual = models.BooleanField(default=False)
    # True once complete() folded tcs_amount into grand_total (avoid ledger double-count).
    tcs_in_grand_total = models.BooleanField(default=False)

    class WhatsAppSendStatus(models.TextChoices):
        NONE = "NONE"
        QUEUED = "QUEUED"
        SENT = "SENT"
        FALLBACK_LINK = "FALLBACK_LINK"
        FAILED = "FAILED"

    whatsapp_send_status = models.CharField(
        max_length=16, choices=WhatsAppSendStatus.choices, default=WhatsAppSendStatus.NONE
    )
    whatsapp_message_id = models.CharField(max_length=128, blank=True, default="")
    whatsapp_share_link = models.TextField(blank=True, default="")
    whatsapp_sent_at = models.DateTimeField(null=True, blank=True)
    custom_fields = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-invoice_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=~models.Q(number=""),
                name="uniq_sales_number_per_company",
            )
        ]
        indexes = [
            models.Index(fields=["company", "status", "invoice_date"]),
            models.Index(
                fields=["company", "customer", "status", "invoice_date"],
                name="sales_inv_co_cust_stat_dt_idx",
            ),
        ]

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
    applied_price_list_name = models.CharField(max_length=100, blank=True, default="")
    price_override_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )


class QuotationQuerySet(models.QuerySet):
    def expired(self, on=None):
        on = on or timezone.localdate()
        return self.filter(status__in=Quotation.OPEN_STATUSES, valid_until__lt=on)

    def live(self, on=None):
        on = on or timezone.localdate()
        return self.filter(status__in=Quotation.OPEN_STATUSES).filter(
            models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=on)
        )


class Quotation(DocumentTotalsModel):
    """`Draft` → `Sent` → `Accepted` / `Rejected`; any open status →
    `Converted` / `Cancelled` (§4.3). Expiry is computed from ``valid_until``."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        SENT = "SENT"
        ACCEPTED = "ACCEPTED"
        REJECTED = "REJECTED"
        CONVERTED = "CONVERTED"
        CANCELLED = "CANCELLED"

    EDITABLE_STATUSES = (Status.DRAFT,)
    CONVERTIBLE_STATUSES = (Status.DRAFT, Status.SENT, Status.ACCEPTED)
    OPEN_STATUSES = (Status.DRAFT, Status.SENT, Status.ACCEPTED)

    objects = QuotationQuerySet.as_manager()

    customer = models.ForeignKey("masters.Customer", on_delete=models.PROTECT, related_name="quotations")
    number = models.CharField(max_length=32, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    invoice_type = models.CharField(
        max_length=8, choices=SalesInvoice.InvoiceType.choices, default=SalesInvoice.InvoiceType.GST
    )
    quotation_date = models.DateField(default=timezone.localdate)
    valid_until = models.DateField(null=True, blank=True)
    payment_terms_days = models.PositiveIntegerField(default=0)
    additional_charges = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    charges_hsn = models.CharField(max_length=8, blank=True)
    charges_gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    invoice_discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    invoice_discount_mode = models.CharField(
        max_length=12,
        choices=SalesInvoice.DiscountMode.choices,
        default=SalesInvoice.DiscountMode.AFTER_TAX,
    )
    auto_round_off = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    terms_text = models.TextField(blank=True)
    supply_type = models.CharField(
        max_length=8, choices=SalesInvoice.SupplyType.choices, default=SalesInvoice.SupplyType.B2B, blank=True
    )
    company_gstin = models.ForeignKey(
        "accounts.CompanyGstin",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quotations",
    )
    converted_invoice = models.ForeignKey(
        SalesInvoice, null=True, blank=True, on_delete=models.SET_NULL, related_name="source_quotations"
    )
    converted_order = models.ForeignKey(
        "SalesOrder", null=True, blank=True, on_delete=models.SET_NULL, related_name="source_quotations"
    )
    opportunity = models.ForeignKey(
        "crm.Opportunity",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quotations",
    )
    salesman = models.ForeignKey(
        "payroll.Employee", null=True, blank=True, on_delete=models.SET_NULL, related_name="quotations",
    )
    sales_channel = models.CharField(max_length=16, choices=SalesChannel.choices, blank=True, default="")
    delivery_address = models.TextField(blank=True)
    revision = models.PositiveIntegerField(default=0)
    cancel_reason = models.CharField(max_length=500, blank=True, default="")
    # Open status to restore when a released conversion leaves quantity remaining (D2).
    status_before_conversion = models.CharField(max_length=12, blank=True, default="")
    # Close remaining (D-16): the unconverted quantity of a partly converted quote is abandoned.
    short_closed_at = models.DateTimeField(null=True, blank=True)
    short_closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    short_close_reason = models.CharField(max_length=500, blank=True, default="")
    # Set when the quote is first shared or marked sent.
    sent_at = models.DateTimeField(null=True, blank=True)
    # Duplicate-as-new-version (D-11); the source quote is never changed.
    copied_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="copies"
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
    hsn_code = models.CharField(max_length=8, blank=True)
    supply_nature = models.CharField(max_length=12, blank=True, default="TAXABLE")
    unit_price_inclusive = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    # CFT-115: qty already converted to an SO/invoice; remainder stays convertible.
    converted_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    expected_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))


class QuotationConversion(models.Model):
    """One row per quote line per conversion. The ledger is the source of
    truth; ``QuotationItem.converted_quantity`` is a cache recomputed from the
    unreleased rows."""

    class Target(models.TextChoices):
        ORDER = "ORDER", "Sales order"
        INVOICE = "INVOICE", "Sales invoice"
        UNKNOWN = "UNKNOWN", "Unknown (backfilled)"

    class ReleaseReason(models.TextChoices):
        DRAFT_DELETED = "DRAFT_DELETED"
        ORDER_CANCELLED = "ORDER_CANCELLED"
        INVOICE_CANCELLED = "INVOICE_CANCELLED"
        MANUAL_REOPEN = "MANUAL_REOPEN"

    company = models.ForeignKey("accounts.Company", on_delete=models.CASCADE, related_name="+")
    quotation = models.ForeignKey(Quotation, on_delete=models.PROTECT, related_name="conversions")
    # SET_NULL: a line whose conversions were all released may later be removed in an edit.
    quotation_item = models.ForeignKey(
        QuotationItem, null=True, blank=True, on_delete=models.SET_NULL, related_name="conversions"
    )
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="+")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    target = models.CharField(max_length=8, choices=Target.choices)
    sales_order = models.ForeignKey(
        "SalesOrder", null=True, blank=True, on_delete=models.SET_NULL, related_name="quotation_conversions"
    )
    sales_order_item = models.ForeignKey(
        "SalesOrderItem", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    sales_invoice = models.ForeignKey(
        SalesInvoice, null=True, blank=True, on_delete=models.SET_NULL, related_name="quotation_conversions"
    )
    sales_invoice_item = models.ForeignKey(
        SalesItem, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    release_reason = models.CharField(max_length=24, choices=ReleaseReason.choices, blank=True, default="")
    backfilled = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["company", "quotation"]),
            models.Index(fields=["sales_order"]),
            models.Index(fields=["sales_invoice"]),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="quote_conversion_qty_positive"),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        for related in (self.quotation, self.sales_order, self.sales_invoice):
            if related is not None and related.company_id != self.company_id:
                raise ValidationError("Quotation conversion rows must stay within one company.")


class QuotationRevision(models.Model):
    """Snapshot of a quote as the customer received it, kept before an edit (D8)."""

    company = models.ForeignKey("accounts.Company", on_delete=models.CASCADE, related_name="+")
    quotation = models.ForeignKey(Quotation, on_delete=models.PROTECT, related_name="revisions")
    revision = models.PositiveIntegerField()
    snapshot = models.JSONField(default=dict)
    reason = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-revision"]
        constraints = [
            models.UniqueConstraint(fields=["quotation", "revision"], name="uniq_quotation_revision"),
        ]


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
    source_item = models.ForeignKey(
        "SalesItem", null=True, blank=True, on_delete=models.SET_NULL, related_name="return_items",
    )
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
    # Receipt slices unallocated when this note completed against a paid invoice.
    # Cancel puts them back, up to the restored outstanding.
    peeled_receipt_allocations = models.JSONField(default=list, blank=True)
    # GST Guard: OWNER/MANAGER override of a blocking pre-submission issue —
    # mirrors SalesInvoice.gst_guard_override_* (reporting.gst_guard).
    gst_guard_override_reason = models.CharField(max_length=500, blank=True, default="")
    gst_guard_overridden_by = models.ForeignKey(
        "accounts.CompanyUser", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    gst_guard_overridden_at = models.DateTimeField(null=True, blank=True)
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
    gst_guard_override_reason = models.CharField(max_length=500, blank=True, default="")
    gst_guard_overridden_by = models.ForeignKey(
        "accounts.CompanyUser", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    gst_guard_overridden_at = models.DateTimeField(null=True, blank=True)
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
        PARTIALLY_CONVERTED = "PARTIALLY_CONVERTED"
        CONVERTED = "CONVERTED"
        CANCELLED = "CANCELLED"

    customer = models.ForeignKey("masters.Customer", on_delete=models.PROTECT, related_name="sales_orders")
    warehouse = models.ForeignKey(
        "inventory.Warehouse", null=True, blank=True, on_delete=models.PROTECT, related_name="sales_orders"
    )
    number = models.CharField(max_length=32, blank=True, db_index=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
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
    charges_hsn = models.CharField(max_length=8, blank=True)
    charges_gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    supply_type = models.CharField(
        max_length=8, choices=SalesInvoice.SupplyType.choices, default=SalesInvoice.SupplyType.B2B, blank=True
    )
    company_gstin = models.ForeignKey(
        "accounts.CompanyGstin",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sales_orders",
    )
    notes = models.TextField(blank=True)
    terms_text = models.TextField(blank=True)
    credit_override_reason = models.CharField(max_length=500, blank=True, default="")
    credit_overridden_by = models.ForeignKey(
        "accounts.CompanyUser", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    credit_overridden_at = models.DateTimeField(null=True, blank=True)
    converted_invoice = models.ForeignKey(
        SalesInvoice, null=True, blank=True, on_delete=models.SET_NULL, related_name="source_orders"
    )
    salesman = models.ForeignKey(
        "payroll.Employee", null=True, blank=True, on_delete=models.SET_NULL, related_name="sales_orders",
    )
    sales_channel = models.CharField(max_length=16, choices=SalesChannel.choices, blank=True, default="")
    delivery_address = models.TextField(blank=True)

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
    expected_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    shipped_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    invoiced_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))


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
    delivery_address = models.TextField(blank=True)
    eway_status = models.CharField(
        max_length=12, choices=SalesInvoice.EwayStatus.choices, default=SalesInvoice.EwayStatus.NONE
    )
    eway_bill_no = models.CharField(max_length=32, blank=True)
    eway_valid_upto = models.DateTimeField(null=True, blank=True)
    # B2-015: see SalesInvoice.eway_generated_at.
    eway_generated_at = models.DateTimeField(null=True, blank=True)
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
    # C-02: lot identity must survive challan → invoice convert.
    batch = models.ForeignKey(
        "inventory.BatchLot", null=True, blank=True, on_delete=models.PROTECT, related_name="delivery_challan_items"
    )
    batch_no = models.CharField(max_length=64, blank=True)
    # BB-000402: serial tracking on challan stock path.
    serial_numbers = models.JSONField(default=list, blank=True)
    expected_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))


class RecurringInvoiceSchedule(models.Model):
    """BB-000669: template that spawns DRAFT sales invoices on a cadence."""

    class Cadence(models.TextChoices):
        MONTHLY = "MONTHLY"
        WEEKLY = "WEEKLY"

    class StopStage(models.TextChoices):
        INVOICE = "INVOICE"
        SALES_ORDER = "SALES_ORDER"
        DELIVERY_CHALLAN = "DELIVERY_CHALLAN"

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
    # B2-009: the intended day-of-month for MONTHLY schedules. Without it a
    # "31st" schedule permanently drifts to the 28th after the first February.
    anchor_day = models.PositiveSmallIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    line_template = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    # CR-121: last generation failure text (optional; absent until migration).
    last_error = models.TextField(blank=True, default="")
    stop_stage = models.CharField(
        max_length=20,
        choices=StopStage.choices,
        default=StopStage.INVOICE,
        help_text="Where a generated run stops: draft invoice (default), sales order, or draft delivery challan.",
    )
    auto_complete = models.BooleanField(
        default=False,
        help_text="When true, an INVOICE run is completed unedited. Default stays a draft for review.",
    )
    # B2-026: header-level charges/discount/price-mode a recurring template
    # previously had no way to express at all -- every generated draft was
    # silently exclusive-priced with no charges/invoice discount, regardless
    # of what a one-off invoice for the same customer would normally carry.
    additional_charges = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    invoice_discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    invoice_discount_mode = models.CharField(
        max_length=12, choices=SalesInvoice.DiscountMode.choices, default=SalesInvoice.DiscountMode.AFTER_TAX,
    )
    price_mode = models.CharField(
        max_length=12, choices=SalesInvoice.PriceMode.choices, default=SalesInvoice.PriceMode.EXCLUSIVE,
    )
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
    sales_order = models.ForeignKey(
        "sales.SalesOrder", null=True, blank=True, on_delete=models.SET_NULL, related_name="recurring_runs",
    )
    delivery_challan = models.ForeignKey(
        "sales.DeliveryChallan", null=True, blank=True, on_delete=models.SET_NULL, related_name="recurring_runs",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["schedule", "period_key"], name="uniq_recurring_invoice_run_period",
            ),
        ]
        indexes = [models.Index(fields=["company", "period_key"], name="sales_recurrun_co_period_idx")]


class DeliveryRoute(CompanyScopedModel):
    """SO-only planning overlay for a van/driver day (Phase 8)."""

    class Status(models.TextChoices):
        PLANNED = "PLANNED"
        IN_TRANSIT = "IN_TRANSIT"
        COMPLETED = "COMPLETED"
        CANCELLED = "CANCELLED"

    number = models.CharField(max_length=32, blank=True, db_index=True)
    route_date = models.DateField(default=timezone.localdate)
    vehicle_number = models.CharField(max_length=32, blank=True)
    driver_name = models.CharField(max_length=128, blank=True)
    driver = models.ForeignKey(
        "payroll.Employee", null=True, blank=True, on_delete=models.SET_NULL, related_name="delivery_routes",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNED)
    estimated_logistics_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    actual_logistics_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    realized_revenue = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    realized_cogs = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    realized_profit = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    invoiced_stop_count = models.PositiveIntegerField(null=True, blank=True)
    stop_count = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    completion_source = models.CharField(max_length=8, blank=True, default="")

    class Meta:
        ordering = ["-route_date", "-id"]
        indexes = [models.Index(fields=["company", "status", "route_date"])]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                condition=~models.Q(number=""),
                name="uniq_delivery_route_number_per_company",
            )
        ]


class DeliveryRouteStop(CompanyScopedModel):
    class StopStatus(models.TextChoices):
        PENDING = "PENDING"
        DELIVERED = "DELIVERED"
        FAILED = "FAILED"
        REJECTED = "REJECTED"
        RETURNED = "RETURNED"

    route = models.ForeignKey(DeliveryRoute, on_delete=models.CASCADE, related_name="stops")
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name="route_stops")
    sequence = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=StopStatus.choices, default=StopStatus.PENDING)
    notes = models.TextField(blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    # Set when a failed or rejected stop gave its reservation back, so FAILED -> DELIVERED -> FAILED
    # cannot release the order's stock twice (the second release would eat other orders' holds).
    stock_released_at = models.DateTimeField(null=True, blank=True)
    completion_source = models.CharField(max_length=8, blank=True, default="")
    otp_code = models.CharField(max_length=8, blank=True, default="")
    # HMAC of the OTP issued to the customer. The submitted digits are checked
    # against this and are not stored.
    delivery_otp_hash = models.CharField(max_length=64, blank=True, default="")
    collected_cash = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    collected_upi = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    upi_reference = models.CharField(max_length=64, blank=True, default="")
    pod_note = models.TextField(blank=True, default="")
    received_by_name = models.CharField(max_length=128, blank=True, default="")
    pod_photo = models.ForeignKey(
        "core.FileAsset", null=True, blank=True, on_delete=models.SET_NULL, related_name="pod_stops",
    )
    customer_receipt = models.ForeignKey(
        "payments.CustomerReceipt", null=True, blank=True, on_delete=models.SET_NULL, related_name="pod_stops",
    )

    class Meta:
        ordering = ["sequence", "id"]
        constraints = [
            models.UniqueConstraint(fields=["route", "sales_order"], name="uniq_route_stop_order"),
        ]


class RouteCashHandover(CompanyScopedModel):
    """Cashier count of driver COD/UPI. Status and amounts only — no cash journal."""

    class Status(models.TextChoices):
        VERIFIED = "VERIFIED"
        VARIANCE = "VARIANCE"

    route = models.OneToOneField(DeliveryRoute, on_delete=models.CASCADE, related_name="cash_handover")
    status = models.CharField(max_length=12, choices=Status.choices)
    expected_cash = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    expected_upi = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    counted_cash = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    counted_upi = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    variance_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]


class DeliveryChallanReturn(DocumentTotalsModel):
    """Partial/full return against a completed delivery challan."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        COMPLETED = "COMPLETED"
        CANCELLED = "CANCELLED"

    customer = models.ForeignKey("masters.Customer", on_delete=models.PROTECT, related_name="delivery_challan_returns")
    challan = models.ForeignKey(DeliveryChallan, on_delete=models.PROTECT, related_name="returns")
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
                name="uniq_dc_return_number_per_company",
            )
        ]


class DeliveryChallanReturnItem(DocumentLineModel):
    challan_return = models.ForeignKey(DeliveryChallanReturn, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="delivery_challan_return_items")


class PosApproverPin(CompanyScopedModel):
    """A counter PIN belongs to one user. The row is the grant."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pos_approver_pins",
    )
    pin_hash = models.CharField(max_length=128)
    set_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "user"], name="uniq_pos_approver_pin"),
        ]


class PosCounterRefund(CompanyScopedModel):
    """Cash or bank handed back after a counter return. The credit note stays the sales reversal."""

    class Mode(models.TextChoices):
        CASH = "CASH"
        BANK = "BANK"
        ADVANCE = "ADVANCE"

    class Status(models.TextChoices):
        ADVANCE = "ADVANCE"
        POSTED = "POSTED"
        PENDING_GATEWAY = "PENDING_GATEWAY"

    customer = models.ForeignKey("masters.Customer", on_delete=models.PROTECT, related_name="pos_refunds")
    sales_return = models.ForeignKey(SalesReturn, on_delete=models.PROTECT, related_name="pos_refunds")
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    mode = models.CharField(max_length=12, choices=Mode.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.POSTED)
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="pos_refunds",
    )
    refund_date = models.DateField(default=timezone.localdate)
    bank_account = models.ForeignKey(
        "payments.BankAccount", null=True, blank=True, on_delete=models.SET_NULL, related_name="pos_refunds",
    )
    idempotency_key = models.CharField(max_length=64, blank=True, default="")
    shift = models.ForeignKey(
        "accounting.CashShiftRegister", null=True, blank=True, on_delete=models.SET_NULL, related_name="refunds",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_pos_refund_idempotency",
            ),
        ]


class QuotationPublicLink(CompanyScopedModel):
    """Unguessable link to a quotation's PDF. One active row per quotation."""

    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="public_links")
    token = models.CharField(max_length=64, unique=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    view_count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["quotation"],
                condition=models.Q(revoked_at__isnull=True),
                name="uniq_active_quotation_public_link",
            ),
        ]


class InvoicePublicLink(CompanyScopedModel):
    """Unguessable link for a completed invoice. One active row per invoice."""

    invoice = models.ForeignKey(
        SalesInvoice, on_delete=models.CASCADE, related_name="public_links",
    )
    token = models.CharField(max_length=64, unique=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    view_count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["invoice"],
                condition=models.Q(revoked_at__isnull=True),
                name="uniq_active_invoice_public_link",
            ),
        ]
