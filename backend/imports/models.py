from decimal import Decimal

from django.db import models

from core.models import CompanyScopedModel


class ImportJob(CompanyScopedModel):
    """Upload → Validate → Preview → Commit → Error report (§15)."""

    class Kind(models.TextChoices):
        CUSTOMERS = "CUSTOMERS"
        SUPPLIERS = "SUPPLIERS"
        PRODUCTS = "PRODUCTS"
        OPENING_STOCK = "OPENING_STOCK"
        PURCHASE_BILL = "PURCHASE_BILL"
        SALES_BILL = "SALES_BILL"

    class Status(models.TextChoices):
        UPLOADED = "UPLOADED"
        EXTRACTING = "EXTRACTING"
        NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
        PREVIEWED = "PREVIEWED"
        COMMITTED = "COMMITTED"
        FAILED = "FAILED"
        VOIDED = "VOIDED"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    file = models.ForeignKey("core.FileAsset", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPLOADED)
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    error_rows = models.PositiveIntegerField(default=0)
    preview = models.JSONField(default=list, blank=True)
    errors = models.JSONField(default=list, blank=True)
    # Fuzzy header alias resolutions shown at preview: [{"source","target"}].
    column_mappings = models.JSONField(default=list, blank=True)
    # Rows whose opening-stock movements were reversed via void-rows.
    voided_rows = models.JSONField(default=list, blank=True)
    # Document-level clarification Q&A (Bill Import Redesign Plan §4.3):
    # [{"field","question","options":[...], "answer": "..." | null}]
    clarifications = models.JSONField(default=list, blank=True)
    committed_at = models.DateTimeField(null=True, blank=True)
    supplier = models.ForeignKey(
        "masters.Supplier",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    customer = models.ForeignKey(
        "masters.Customer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    purchase_invoice = models.ForeignKey(
        "purchases.PurchaseInvoice",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    sales_invoice = models.ForeignKey(
        "sales.SalesInvoice",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    bill_template = models.ForeignKey(
        "imports.SupplierBillTemplate",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="jobs",
    )
    failure_reason = models.TextField(blank=True)

    BILL_KINDS = (Kind.PURCHASE_BILL, Kind.SALES_BILL)

    class Meta:
        ordering = ["-created_at"]
        # BUG-718: listing a company's import history filters by company
        # (and realistically status) ordered by created_at — unlike almost
        # every other document model, this had no supporting index at all.
        indexes = [models.Index(fields=["company", "status", "created_at"])]


class SupplierBillTemplate(CompanyScopedModel):
    """
    Learned per-vendor bill layout (Bill Import Redesign Plan §4.4).

    Matched primarily by GSTIN; `column_signature` (the set of raw column
    header strings last seen) is used as a secondary check so a template
    still applies when a vendor reorders columns, but is treated as stale
    when the vendor changes which columns are present at all.
    """

    class LineTotalFormula(models.TextChoices):
        # Gross Amt = Pcs x Pc Price (Pcs already the full billed quantity).
        SIMPLE = "SIMPLE"
        # Gross Amt = ((Cs x UPC) + Pcs) x Pc Price — UPC is a per-carton unit
        # count and Pcs is loose pieces on top of full cartons in Cs.
        CASE_UNITS_PLUS_LOOSE = "CASE_UNITS_PLUS_LOOSE"

    class TaxCalculationType(models.TextChoices):
        EXCLUSIVE = "EXCLUSIVE"
        INCLUSIVE = "INCLUSIVE"
        HEADER_LEVEL = "HEADER_LEVEL"  # discount/tax applied once for the whole bill, not per line

    gstin = models.CharField(max_length=15, db_index=True)
    party_name = models.CharField(max_length=255, blank=True)
    column_mapping = models.JSONField(default=dict, blank=True)
    line_total_formula = models.CharField(
        max_length=24, choices=LineTotalFormula.choices, default=LineTotalFormula.SIMPLE
    )
    tax_calculation_type = models.CharField(
        max_length=16, choices=TaxCalculationType.choices, default=TaxCalculationType.EXCLUSIVE
    )
    rounding_tolerance = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.50"))
    column_signature = models.JSONField(default=list, blank=True)
    confirmed_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-confirmed_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "gstin"],
                condition=~models.Q(gstin=""),
                name="uniq_bill_template_company_gstin",
            )
        ]
