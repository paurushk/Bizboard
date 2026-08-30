from decimal import Decimal

from django.conf import settings
from django.db import models

from core.models import CompanyScopedModel


class MovementType(models.TextChoices):
    """Locked movement types (§7)."""

    OPENING_STOCK = "OPENING_STOCK"
    PURCHASE = "PURCHASE"
    SALE = "SALE"
    PURCHASE_RETURN = "PURCHASE_RETURN"
    SALES_RETURN = "SALES_RETURN"
    ADJUSTMENT = "ADJUSTMENT"
    TRANSFER_OUT = "TRANSFER_OUT"
    TRANSFER_IN = "TRANSFER_IN"
    MANUFACTURE_ISSUE = "MANUFACTURE_ISSUE"
    MANUFACTURE_RECEIPT = "MANUFACTURE_RECEIPT"


# Sign of stock effect per movement type; ADJUSTMENT carries its own sign.
MOVEMENT_SIGN = {
    MovementType.OPENING_STOCK: 1,
    MovementType.PURCHASE: 1,
    MovementType.SALE: -1,
    MovementType.PURCHASE_RETURN: -1,
    MovementType.SALES_RETURN: 1,
    MovementType.TRANSFER_OUT: -1,
    MovementType.TRANSFER_IN: 1,
    MovementType.MANUFACTURE_ISSUE: -1,
    MovementType.MANUFACTURE_RECEIPT: 1,
}


class Warehouse(CompanyScopedModel):
    """A company stock location. Every company owns one default location."""

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=32)
    address = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_warehouse_code_per_company"),
            models.UniqueConstraint(
                fields=["company"], condition=models.Q(is_default=True),
                name="one_default_warehouse_per_company",
            ),
        ]

    def __str__(self):
        return self.name


class BatchLot(CompanyScopedModel):
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="batch_lots")
    batch_no = models.CharField(max_length=64)
    expiry_date = models.DateField(null=True, blank=True, db_index=True)
    manufacturing_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["expiry_date", "id"]
        constraints = [
            models.UniqueConstraint(fields=["company", "product", "batch_no"], name="uniq_batch_per_product_company")
        ]

    def __str__(self):
        return f"{self.product} / {self.batch_no}"


class StockMovement(models.Model):
    """Append-only stock ledger. `quantity` is the signed stock delta."""

    company = models.ForeignKey("accounts.Company", on_delete=models.CASCADE, related_name="stock_movements")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="stock_movements")
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="stock_movements")
    batch = models.ForeignKey(BatchLot, null=True, blank=True, on_delete=models.PROTECT, related_name="stock_movements")
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    reference_type = models.CharField(max_length=64, blank=True)
    reference_id = models.CharField(max_length=64, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    layer_peels = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["company", "product", "created_at"]),
            models.Index(fields=["company", "warehouse", "product", "created_at"]),
            models.Index(fields=["company", "movement_type"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("Stock movements are append-only and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Stock movements are append-only and cannot be deleted.")


class StockBalance(models.Model):
    """Derived cache — rebuildable from movements (§12.1)."""

    company = models.ForeignKey("accounts.Company", on_delete=models.CASCADE, related_name="stock_balances")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="stock_balances")
    product = models.ForeignKey("masters.Product", on_delete=models.CASCADE, related_name="stock_balances")
    batch = models.ForeignKey(BatchLot, null=True, blank=True, on_delete=models.PROTECT, related_name="stock_balances")
    on_hand = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    reserved = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))

    class Meta:
        ordering = ["product__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "warehouse", "product"],
                condition=models.Q(batch__isnull=True),
                name="uniq_unbatched_balance_per_warehouse",
            ),
            models.UniqueConstraint(
                fields=["company", "warehouse", "product", "batch"],
                condition=models.Q(batch__isnull=False),
                name="uniq_batched_balance_per_warehouse",
            ),
        ]

    @property
    def available(self):
        return self.on_hand - self.reserved


class StockTransfer(CompanyScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        COMPLETED = "COMPLETED"
        CANCELLED = "CANCELLED"

    number = models.CharField(max_length=32, blank=True, db_index=True)
    from_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="outgoing_transfers")
    to_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="incoming_transfers")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"], condition=~models.Q(number=""),
                name="uniq_transfer_number_per_company",
            ),
            models.CheckConstraint(
                condition=~models.Q(from_warehouse=models.F("to_warehouse")),
                name="transfer_requires_distinct_warehouses",
            ),
        ]


class StockTransferLine(models.Model):
    transfer = models.ForeignKey(StockTransfer, on_delete=models.CASCADE, related_name="lines")
    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True,
    )
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey(BatchLot, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    serial_numbers = models.JSONField(default=list, blank=True)

    def save(self, *args, **kwargs):
        if self.transfer_id and not self.company_id:
            self.company_id = self.transfer.company_id
        super().save(*args, **kwargs)


class SerialNumber(CompanyScopedModel):
    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE"
        SOLD = "SOLD"
        RETURNED = "RETURNED"
        SCRAPPED = "SCRAPPED"

    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="serial_numbers")
    warehouse = models.ForeignKey(Warehouse, null=True, blank=True, on_delete=models.PROTECT, related_name="serial_numbers")
    serial_number = models.CharField(max_length=128)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.AVAILABLE)
    # R4-014: set to the ImportJob id when the unit was received via an import,
    # so voiding that import can precisely scrap the serials it created (not a
    # best-effort scan). Plain id, not an FK, to avoid inventory→imports coupling.
    import_job_ref = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["serial_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "product", "serial_number"],
                name="uniq_serial_per_company_product",
            )
        ]


class InventoryCostLayer(CompanyScopedModel):
    """Wave 16B perpetual FIFO cost layer (qty remaining at unit_cost)."""

    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="cost_layers")
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="cost_layers")
    batch = models.ForeignKey(BatchLot, null=True, blank=True, on_delete=models.PROTECT, related_name="cost_layers")
    qty_remaining = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal("0"))
    source_movement = models.ForeignKey(
        StockMovement, null=True, blank=True, on_delete=models.SET_NULL, related_name="cost_layers"
    )

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["company", "warehouse", "product"], name="fifo_layer_lookup_idx"),
        ]


class WarehouseReorderLevel(CompanyScopedModel):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name="reorder_levels")
    product = models.ForeignKey("masters.Product", on_delete=models.CASCADE, related_name="warehouse_reorder_levels")
    reorder_level = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "warehouse", "product"],
                name="uniq_reorder_per_warehouse_product",
            )
        ]


class StockCountSession(CompanyScopedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT"
        COUNTED = "COUNTED"
        POSTED = "POSTED"
        CANCELLED = "CANCELLED"

    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="stock_counts")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    counted_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]


class StockCountLine(models.Model):
    # Denormalized tenancy key (session.company) so the row can be enrolled in RLS.
    company = models.ForeignKey(
        "accounts.Company", on_delete=models.CASCADE, related_name="+", db_index=True,
    )
    session = models.ForeignKey(StockCountSession, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey(BatchLot, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    system_qty = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    counted_qty = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session", "product", "batch"],
                name="uniq_stock_count_line",
            )
        ]

    @property
    def variance(self):
        if self.counted_qty is None:
            return None
        return self.counted_qty - self.system_qty


class ExpiryAlertLog(CompanyScopedModel):
    """One row per lot × warehouse × band so expiry notices fire once."""

    batch = models.ForeignKey(BatchLot, on_delete=models.CASCADE, related_name="expiry_notices")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name="+")
    band_days = models.PositiveSmallIntegerField()
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "batch", "warehouse", "band_days"],
                name="uniq_expiry_notice_per_band",
            )
        ]
