from decimal import Decimal

from django.db import models

from core.models import CompanyScopedModel
from core.validators import validate_gst_rate, validate_gstin, validate_hsn


class Category(CompanyScopedModel):
    name = models.CharField(max_length=100)

    class Meta:
        unique_together = [("company", "name")]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Brand(CompanyScopedModel):
    name = models.CharField(max_length=100)

    class Meta:
        unique_together = [("company", "name")]

    def __str__(self):
        return self.name


class Unit(CompanyScopedModel):
    name = models.CharField(max_length=50)
    short_name = models.CharField(max_length=10)
    # GSTN Unit Quantity Code for GSTR-1 Table 12 (e.g. PCS, KGS, NOS).
    uqc_code = models.CharField(max_length=8, blank=True)

    class Meta:
        unique_together = [("company", "name")]

    def __str__(self):
        return self.short_name


class TaxRate(CompanyScopedModel):
    name = models.CharField(max_length=50)
    rate = models.DecimalField(max_digits=5, decimal_places=2, validators=[validate_gst_rate])

    class Meta:
        unique_together = [("company", "name")]

    def __str__(self):
        return f"{self.name} ({self.rate}%)"


class PaymentMode(CompanyScopedModel):
    name = models.CharField(max_length=50)
    code = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("company", "name")]

    def __str__(self):
        return self.name


class ExpenseCategory(CompanyScopedModel):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("company", "name")]
        verbose_name_plural = "expense categories"

    def __str__(self):
        return self.name


class Customer(CompanyScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE"
        BLOCKED = "BLOCKED"
        INACTIVE = "INACTIVE"

    name = models.CharField(max_length=255, db_index=True)
    phone = models.CharField(max_length=20, blank=True, db_index=True)
    email = models.EmailField(blank=True)
    gstin = models.CharField(max_length=15, blank=True, validators=[validate_gstin])
    billing_address = models.TextField(blank=True)
    shipping_address = models.TextField(blank=True)
    state = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    credit_limit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    credit_days = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    gstin_verification_status = models.CharField(max_length=16, blank=True, default="UNVERIFIED")
    gstin_legal_name = models.CharField(max_length=255, blank=True)
    gstin_verified_at = models.DateTimeField(null=True, blank=True)
    gstin_raw_payload = models.JSONField(null=True, blank=True)
    # Wave 17A: SEZ / export / regular classification for GSTR + e-invoice.
    class TaxpayerType(models.TextChoices):
        REGULAR = "REGULAR", "Regular"
        SEZWP = "SEZWP", "SEZ with payment"
        SEZWOP = "SEZWOP", "SEZ without payment"
        EXPWP = "EXPWP", "Export with payment"
        EXPWOP = "EXPWOP", "Export without payment"
        DEXP = "DEXP", "Deemed export"
        COMPOSITION = "COMPOSITION", "Composition"
        UNREGISTERED = "UNREGISTERED", "Unregistered"

    taxpayer_type = models.CharField(
        max_length=16, choices=TaxpayerType.choices, default=TaxpayerType.REGULAR, blank=True
    )
    whatsapp_opt_in = models.BooleanField(
        default=False,
        help_text="A-06: Cloud WhatsApp only when True. wa.me open-in-app is always allowed.",
    )
    dunning_opt_out = models.BooleanField(
        default=False,
        help_text="A-07: when True, skip automated AR reminders for this customer.",
    )
    price_list = models.ForeignKey(
        "PriceList", null=True, blank=True, on_delete=models.SET_NULL, related_name="customers"
    )

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["company", "status"])]
        constraints = [
            # BUG-321: gstin is a legally-unique-per-entity identifier;
            # without this, duplicate customer records fragment purchase
            # history and understate true outstanding balances.
            models.UniqueConstraint(
                fields=["company", "gstin"], condition=~models.Q(gstin=""),
                name="uniq_customer_gstin_per_company",
            ),
        ]

    def __str__(self):
        return self.name

    def is_referenced(self):
        """True if the customer appears on any document or payment."""
        return (
            self.sales_invoices.exists()
            or self.quotations.exists()
            or self.sales_returns.exists()
            or self.sales_credit_notes.exists()
            or self.sales_debit_notes.exists()
            or self.sales_orders.exists()
            or self.delivery_challans.exists()
            or self.receipts.exists()
            or self.payment_links.exists()
        )


class Supplier(CompanyScopedModel):
    name = models.CharField(max_length=255, db_index=True)
    phone = models.CharField(max_length=20, blank=True, db_index=True)
    email = models.EmailField(blank=True)
    gstin = models.CharField(max_length=15, blank=True, validators=[validate_gstin])
    address = models.TextField(blank=True)
    state = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    gstin_verification_status = models.CharField(max_length=16, blank=True, default="UNVERIFIED")
    gstin_legal_name = models.CharField(max_length=255, blank=True)
    gstin_verified_at = models.DateTimeField(null=True, blank=True)
    gstin_raw_payload = models.JSONField(null=True, blank=True)
    taxpayer_type = models.CharField(
        max_length=16,
        choices=Customer.TaxpayerType.choices,
        default=Customer.TaxpayerType.REGULAR,
        blank=True,
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "gstin"], condition=~models.Q(gstin=""),
                name="uniq_supplier_gstin_per_company",
            ),
        ]

    def __str__(self):
        return self.name

    def is_referenced(self):
        """True if the supplier appears on any document or payment."""
        return (
            self.purchase_invoices.exists()
            or self.purchase_returns.exists()
            or self.purchase_credit_notes.exists()
            or self.purchase_debit_notes.exists()
            or self.purchase_orders.exists()
            or self.payments.exists()
        )


class Product(CompanyScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE"
        INACTIVE = "INACTIVE"

    class ProductType(models.TextChoices):
        GOODS = "GOODS", "Goods"
        SERVICE = "SERVICE", "Service"

    name = models.CharField(max_length=255, db_index=True)
    sku = models.CharField(max_length=64, blank=True, db_index=True)
    barcode = models.CharField(max_length=64, blank=True, db_index=True)
    hsn_code = models.CharField(max_length=8, blank=True, validators=[validate_hsn])
    description = models.TextField(blank=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="products")
    brand = models.ForeignKey(Brand, null=True, blank=True, on_delete=models.SET_NULL, related_name="products")
    unit = models.ForeignKey(Unit, null=True, blank=True, on_delete=models.SET_NULL, related_name="products")
    gst_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0"), validators=[validate_gst_rate]
    )
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    mrp = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    wholesale_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    reorder_level = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    product_type = models.CharField(
        max_length=16, choices=ProductType.choices, default=ProductType.GOODS, db_index=True,
    )
    track_inventory = models.BooleanField(default=True)
    track_batch = models.BooleanField(default=False)
    track_serial = models.BooleanField(default=False)
    selling_tax_inclusive = models.BooleanField(default=False)
    purchase_tax_inclusive = models.BooleanField(default=False)
    custom_fields = models.JSONField(default=dict, blank=True)
    alternate_unit = models.ForeignKey(
        Unit, null=True, blank=True, on_delete=models.SET_NULL, related_name="alternate_products",
    )
    conversion_rate = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("1"))
    default_discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "sku"],
                condition=~models.Q(sku=""),
                name="uniq_product_sku_per_company",
            ),
            # BUG-320: without this, two products can share a barcode and a
            # barcode-scan/import match picks an arbitrary one, silently
            # applying stock/price changes to the wrong SKU.
            models.UniqueConstraint(
                fields=["company", "barcode"],
                condition=~models.Q(barcode=""),
                name="uniq_product_barcode_per_company",
            ),
        ]
        indexes = [models.Index(fields=["company", "status"])]

    def __str__(self):
        return self.name

    def is_referenced(self):
        """True if the product appears on any document, order, challan, or stock movement."""
        for rel in (
            "stock_movements",
            "stock_balances",
            "sales_items",
            "sales_return_items",
            "sales_credit_note_items",
            "sales_debit_note_items",
            "purchase_items",
            "purchase_return_items",
            "purchase_order_items",
            "purchase_credit_note_items",
            "purchase_debit_note_items",
            "quotation_items",
            "sales_order_items",
            "delivery_challan_items",
            "batch_lots",
            "serial_numbers",
            "cost_layers",
            "running_costs",
            "warehouse_reorder_levels",
            "bom_items",
            "bom_components",
        ):
            accessor = getattr(self, rel, None)
            if accessor is not None:
                try:
                    if accessor.exists():
                        return True
                except Exception:
                    pass
        return False


class PriceList(CompanyScopedModel):
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["company", "name"], name="uniq_price_list_per_company")]

    def __str__(self):
        return self.name


class PriceListItem(models.Model):
    # BB-000017: denormalized tenancy key (price_list.company).
    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True,
    )
    price_list = models.ForeignKey(PriceList, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="price_list_items")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    min_qty = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("1"))
    max_qty = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    discount_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["price_list", "product", "min_qty"],
                name="uniq_product_slab_per_list",
            ),
            # B8-017: min_qty/unit_price positivity previously only lived in
            # serializer validation (imports, admin, bulk_create bypass it).
            # unit_price allows 0 (a deliberate free/promotional slab is
            # legitimate); min_qty must be positive — pricing.assert_slab_bounds
            # already assumes it defaults to 1 and never checked it directly.
            models.CheckConstraint(condition=models.Q(min_qty__gt=0), name="pricelistitem_min_qty_gt_0"),
            models.CheckConstraint(condition=models.Q(unit_price__gte=0), name="pricelistitem_unit_price_gte_0"),
        ]
        ordering = ["product_id", "min_qty"]


class HsnRate(models.Model):
    """Curated HSN/SAC GST rate with an effective window (B-06). Not company-typed."""

    hsn_sac = models.CharField(max_length=8, db_index=True)
    rate = models.DecimalField(max_digits=5, decimal_places=2, validators=[validate_gst_rate])
    cess = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)
    version = models.CharField(max_length=64)
    source_ref = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["hsn_sac", "valid_from"]),
        ]
        ordering = ["hsn_sac", "-valid_from"]

    def __str__(self):
        return f"{self.hsn_sac} {self.rate}% {self.version}"
