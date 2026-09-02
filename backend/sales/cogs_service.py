"""COGS accumulation helpers — extracted from SalesService (BB-000476)."""

from decimal import Decimal

from django.db.models import Sum

from core.exceptions import BusinessRuleError
from inventory.models import MovementType, SerialNumber, StockMovement
from inventory.services import InventoryService, InventoryValuationService, SerialNumberService

from .models import SalesReturn


class CogsService:
    @staticmethod
    def invoice_sale_moves(invoice, *, product=None):
        from sales.models import DeliveryChallan

        si = StockMovement.objects.filter(
            company=invoice.company,
            movement_type=MovementType.SALE,
            reference_type="sales_invoice",
            reference_id=str(invoice.pk),
        )
        challan_ids = list(
            DeliveryChallan.objects.filter(
                converted_invoice=invoice, stock_posted=True,
            ).values_list("id", flat=True)
        )
        dc = StockMovement.objects.filter(
            company=invoice.company,
            movement_type=MovementType.SALE,
            reference_type="delivery_challan",
            reference_id__in=[str(pk) for pk in challan_ids],
        )
        if product is not None:
            si = si.filter(product=product)
            dc = dc.filter(product=product)
        return list(si.order_by("id")) + list(dc.order_by("id"))

    @staticmethod
    def post_sale_stock_and_cogs(invoice, items, user, *, stock_from_challan: bool, warnings=None) -> Decimal:
        """Issue stock on invoice complete; return total COGS.

        R2-007: appends a warning to `warnings` (if given) for any line whose
        cost basis resolves to zero, so a ₹0-COGS sale is never silent.
        """
        cogs_total = Decimal("0")
        zero_cost_products: list[str] = []
        if not stock_from_challan:
            from .services import SalesService

            for item in items:
                from inventory.item_stock import tracks_inventory

                if not tracks_inventory(item.product):
                    continue
                if item.product.track_serial:
                    SerialNumberService.transition(
                        company=invoice.company,
                        product=item.product,
                        warehouse=invoice.warehouse,
                        numbers=item.serial_numbers,
                        quantity=item.quantity,
                        source=SerialNumber.Status.AVAILABLE,
                        target=SerialNumber.Status.SOLD,
                        user=user,
                    )
                for batch, quantity in SalesService._sale_batches(invoice, item):
                    # BB-000601: COGS from stamped FIFO peel, not pre-peel WAVG.
                    move = InventoryService.post_movement(
                        company=invoice.company,
                        warehouse=invoice.warehouse,
                        product=item.product,
                        batch=batch,
                        movement_type=MovementType.SALE,
                        quantity=quantity,
                        reference_type="sales_invoice",
                        reference_id=invoice.pk,
                        user=user,
                    )
                    unit_cost = Decimal(str(move.unit_cost or 0))
                    if unit_cost == 0:
                        unit_cost = InventoryValuationService.unit_cost(
                            invoice.company, item.product, invoice.warehouse, batch=batch
                        )
                        if unit_cost:
                            StockMovement.objects.filter(pk=move.pk).update(unit_cost=unit_cost)
                            move.unit_cost = unit_cost
                        else:
                            # R2-007: last resort — the product master purchase
                            # price, so a sale with no layer history doesn't book
                            # ₹0 COGS silently.
                            fallback = Decimal(str(getattr(item.product, "purchase_price", 0) or 0))
                            if fallback > 0:
                                unit_cost = fallback
                                StockMovement.objects.filter(pk=move.pk).update(unit_cost=unit_cost)
                                move.unit_cost = unit_cost
                            elif item.product.name not in zero_cost_products:
                                zero_cost_products.append(item.product.name)
                    cogs_total += Decimal(str(unit_cost or 0)) * quantity
        else:
            from sales.models import DeliveryChallan

            challans = DeliveryChallan.objects.filter(
                converted_invoice=invoice, stock_posted=True
            )
            for challan in challans:
                for move in StockMovement.objects.filter(
                    company=invoice.company,
                    reference_type="delivery_challan",
                    reference_id=challan.pk,
                    movement_type=MovementType.SALE,
                ):
                    cogs_total += Decimal(str(move.unit_cost or 0)) * abs(Decimal(str(move.quantity)))
            if cogs_total == 0:
                for item in items:
                    unit_cost = InventoryValuationService.unit_cost(
                        invoice.company,
                        item.product,
                        invoice.warehouse,
                        batch=getattr(item, "batch", None),
                    )
                    if not unit_cost:
                        unit_cost = Decimal(str(getattr(item.product, "purchase_price", 0) or 0))
                    if not unit_cost and item.product.name not in zero_cost_products:
                        zero_cost_products.append(item.product.name)
                    cogs_total += Decimal(str(unit_cost or 0)) * item.quantity
        if zero_cost_products and warnings is not None:
            warnings.append(
                f"{len(zero_cost_products)} line(s) have no cost basis — COGS was "
                f"booked as ₹0 for: {', '.join(zero_cost_products[:5])}"
                + ("…" if len(zero_cost_products) > 5 else "")
            )
        return cogs_total

    @staticmethod
    def restore_return_stock_and_cogs(sales_return: SalesReturn, invoice, items, user) -> Decimal:
        """Restore stock on return complete; return COGS reversal total."""
        cogs_rev = Decimal("0")
        unit_names = {
            row.product_id: getattr(row, "unit_name", None)
            for row in invoice.items.all()
        }
        for item in items:
            from inventory.item_stock import base_quantity, tracks_inventory

            if not tracks_inventory(item.product):
                continue
            damaged = getattr(item, "condition", "SELLABLE") == "DAMAGED"
            if item.product.track_serial:
                # BB-000615: sellable returns become available; damaged units are scrapped.
                SerialNumberService.transition(
                    company=sales_return.company,
                    product=item.product,
                    warehouse=invoice.warehouse,
                    numbers=item.serial_numbers,
                    quantity=item.quantity,
                    source=SerialNumber.Status.SOLD,
                    target=SerialNumber.Status.SCRAPPED if damaged else SerialNumber.Status.AVAILABLE,
                    user=user,
                )
            sale_moves = CogsService.invoice_sale_moves(invoice, product=item.product)
            remaining = base_quantity(
                item.product,
                item.quantity,
                getattr(item, "unit_name", None) or unit_names.get(item.product_id),
            )
            # R2-009: loop-invariant — the other completed returns on this
            # invoice don't change as we walk this return's sale moves.
            prior_sr_ids = [
                str(pk)
                for pk in SalesReturn.objects.filter(
                    sales_invoice=invoice,
                    status=SalesReturn.Status.COMPLETED,
                )
                .exclude(pk=sales_return.pk)
                .values_list("id", flat=True)
            ]
            restored_lots = []
            if sale_moves:
                prior_returned = (
                    StockMovement.objects.filter(
                        company=sales_return.company,
                        movement_type=MovementType.SALES_RETURN,
                        product=item.product,
                        reference_type="sales_return",
                        reference_id__in=prior_sr_ids,
                    ).aggregate(total=Sum("quantity"))["total"]
                    or Decimal("0")
                )
                consumed_prior = Decimal(str(prior_returned))
                for move in sale_moves:
                    if remaining <= 0:
                        break
                    lot_qty = abs(Decimal(str(move.quantity)))
                    move_unit_cost = Decimal(str(move.unit_cost or 0))
                    already_this_move = min(consumed_prior, lot_qty)
                    consumed_prior = max(Decimal("0"), consumed_prior - lot_qty)
                    available_on_lot = lot_qty - already_this_move
                    if available_on_lot <= 0:
                        continue
                    take = min(remaining, available_on_lot)
                    # BB-000720: restore original sale peels instead of inventing a new layer.
                    inbound = InventoryService.post_movement(
                        company=sales_return.company,
                        warehouse=move.warehouse or invoice.warehouse,
                        product=item.product,
                        batch=move.batch,
                        movement_type=MovementType.SALES_RETURN,
                        quantity=take,
                        unit_cost=move_unit_cost,
                        reference_type="sales_return",
                        reference_id=sales_return.pk,
                        user=user,
                    )
                    InventoryService.restore_fifo_peels(move, inbound)
                    cogs_rev += move_unit_cost * take
                    remaining -= take
                    restored_lots.append((move.batch, take))
            if remaining > 0:
                # R2-008 (kept as-is): a return whose sold lots can't be
                # identified is refused by design (test_sales_return_unidentified
                # _lot_refused) — the operator posts a manual RETURN_UNIDENTIFIED
                # adjustment rather than the system inventing a cost basis.
                raise BusinessRuleError(
                    "Cannot restore this return: sold lots could not be identified. "
                    "Post an ADJUSTMENT with reason RETURN_UNIDENTIFIED for the leftover quantity."
                )
            if damaged:
                for batch, take in restored_lots:
                    InventoryService.post_movement(
                        company=sales_return.company,
                        warehouse=invoice.warehouse,
                        product=item.product,
                        batch=batch,
                        movement_type=MovementType.ADJUSTMENT,
                        quantity=-take,
                        reason="DAMAGED",
                        reference_type="sales_return_damaged",
                        reference_id=sales_return.pk,
                        user=user,
                    )
        return cogs_rev
