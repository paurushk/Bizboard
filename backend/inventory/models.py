from decimal import Decimal

from django.conf import settings
from django.db import models


class MovementType(models.TextChoices):
    """Locked movement types (§7)."""

    OPENING_STOCK = "OPENING_STOCK"
    PURCHASE = "PURCHASE"
    SALE = "SALE"
    PURCHASE_RETURN = "PURCHASE_RETURN"
    SALES_RETURN = "SALES_RETURN"
    ADJUSTMENT = "ADJUSTMENT"


# Sign of stock effect per movement type; ADJUSTMENT carries its own sign.
MOVEMENT_SIGN = {
    MovementType.OPENING_STOCK: 1,
    MovementType.PURCHASE: 1,
    MovementType.SALE: -1,
    MovementType.PURCHASE_RETURN: -1,
    MovementType.SALES_RETURN: 1,
}


class StockMovement(models.Model):
    """Append-only stock ledger. `quantity` is the signed stock delta."""

    company = models.ForeignKey("accounts.Company", on_delete=models.CASCADE, related_name="stock_movements")
    product = models.ForeignKey("masters.Product", on_delete=models.PROTECT, related_name="stock_movements")
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    reference_type = models.CharField(max_length=64, blank=True)
    reference_id = models.CharField(max_length=64, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["company", "product", "created_at"]),
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
    product = models.OneToOneField("masters.Product", on_delete=models.CASCADE, related_name="stock_balance")
    on_hand = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    reserved = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))  # always 0 in MVP

    class Meta:
        unique_together = [("company", "product")]
        ordering = ["product__name"]

    @property
    def available(self):
        return self.on_hand - self.reserved
