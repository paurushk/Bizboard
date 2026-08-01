"""Inventory Service — balances, typed movements, adjustments (E2)."""

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from core.exceptions import BusinessRuleError

from .models import MOVEMENT_SIGN, MovementType, StockBalance, StockMovement


class InventoryService:
    @staticmethod
    def post_movement(*, company, product, movement_type, quantity, unit_cost=None,
                      reference_type="", reference_id="", reason="", user=None,
                      skip_negative_check=False):
        """
        Append a typed movement and update the balance cache atomically.
        `quantity` is a positive magnitude for typed movements; for ADJUSTMENT
        it is the signed delta (±).

        The balance row is locked (select_for_update) *before* the
        negative-stock policy is (re-)checked and *before* the movement is
        written, so two concurrent postings against the same product can no
        longer both pass a stale availability read and both succeed — the
        second one blocks on the row lock and re-checks against the
        now-updated balance (BUG-222/309). Callers may still do an earlier,
        advisory-only check_negative_stock() call for fast user-facing
        feedback before committing to a whole document; this check is the
        authoritative one.
        """
        quantity = Decimal(quantity)
        if movement_type == MovementType.ADJUSTMENT:
            if quantity == 0:
                raise BusinessRuleError("Adjustment quantity cannot be zero.")
            delta = quantity
        else:
            if quantity <= 0:
                raise BusinessRuleError("Movement quantity must be greater than zero.")
            delta = quantity * MOVEMENT_SIGN[movement_type]

        if movement_type == MovementType.OPENING_STOCK:
            # BUG-312: re-submitting the same opening-stock entry (double
            # click, re-imported CSV) used to additively stack forever.
            already_has_opening = StockMovement.objects.filter(
                company=company, product=product, movement_type=MovementType.OPENING_STOCK,
            ).exists()
            if already_has_opening:
                raise BusinessRuleError(
                    f"Opening stock has already been recorded for '{product.name}'."
                )

        with transaction.atomic():
            StockBalance.objects.get_or_create(company=company, product=product)
            balance = StockBalance.objects.select_for_update().get(company=company, product=product)

            if delta < 0 and not skip_negative_check:
                resulting = balance.available + delta
                if resulting < 0 and company.negative_stock_policy == "BLOCK":
                    raise BusinessRuleError(
                        f"Insufficient stock for '{product.name}': available "
                        f"{balance.available}, required {-delta}."
                    )

            movement = StockMovement.objects.create(
                company=company,
                product=product,
                movement_type=movement_type,
                quantity=delta,
                unit_cost=unit_cost,
                reference_type=reference_type,
                reference_id=str(reference_id),
                reason=reason,
                created_by=user,
            )
            balance.on_hand = balance.on_hand + delta
            balance.save(update_fields=["on_hand"])
        return movement

    @staticmethod
    def available_quantity(company, product) -> Decimal:
        balance = StockBalance.objects.filter(company=company, product=product).first()
        return balance.available if balance else Decimal("0")

    @staticmethod
    def check_negative_stock(company, product, required_qty):
        """Negative-stock policy on available qty — enforced on sales complete (E2.5)."""
        available = InventoryService.available_quantity(company, product)
        if available < Decimal(required_qty):
            if company.negative_stock_policy == "BLOCK":
                raise BusinessRuleError(
                    f"Insufficient stock for '{product.name}': available {available}, required {required_qty}."
                )
            return f"Stock for '{product.name}' will go negative (available {available})."
        return None

    @staticmethod
    def rebuild_balance(company, product):
        """Balances are a cache — always rebuildable from movements."""
        total = (
            StockMovement.objects.filter(company=company, product=product)
            .aggregate(total=Sum("quantity"))["total"]
            or Decimal("0")
        )
        balance, _ = StockBalance.objects.get_or_create(company=company, product=product)
        balance.on_hand = total
        balance.save(update_fields=["on_hand"])
        return balance
