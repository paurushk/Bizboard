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


class Customer(CompanyScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE"
        BLOCKED = "BLOCKED"

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

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["company", "status"])]

    def __str__(self):
        return self.name


class Supplier(CompanyScopedModel):
    name = models.CharField(max_length=255, db_index=True)
    phone = models.CharField(max_length=20, blank=True, db_index=True)
    email = models.EmailField(blank=True)
    gstin = models.CharField(max_length=15, blank=True, validators=[validate_gstin])
    address = models.TextField(blank=True)
    state = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(CompanyScopedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE"
        INACTIVE = "INACTIVE"

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
    reorder_level = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "sku"],
                condition=~models.Q(sku=""),
                name="uniq_product_sku_per_company",
            )
        ]
        indexes = [models.Index(fields=["company", "status"])]

    def __str__(self):
        return self.name

    def is_referenced(self):
        """True if the product appears on any document or stock movement."""
        return (
            self.stock_movements.exists()
            or self.sales_items.exists()
            or self.purchase_items.exists()
        )
