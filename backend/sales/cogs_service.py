"""COGS accumulation helpers — extracted from SalesService (BB-000476)."""

from decimal import Decimal

from django.db.models import Sum

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
    def post_sale_stock_and_cogs(invoice, items, user, *, stock_from_challan: bool) -> Decimal:
        """Issue stock on invoice complete; return total COGS."""
        cogs_total = Decimal("0")
        if not stock_from_challan:
            from .services import SalesService

            for item in items:
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
                    cogs_total += Decimal(str(unit_cost or 0)) * item.quantity
        return cogs_total

    @staticmethod
    def restore_return_stock_and_cogs(sales_return: SalesReturn, invoice, items, user) -> Decimal:
        """Restore stock on return complete; return COGS reversal total."""
        cogs_rev = Decimal("0")
        for item in items:
            if item.product.track_serial:
                # BB-000615: returned units must be sellable again.
                SerialNumberService.transition(
                    company=sales_return.company,
                    product=item.product,
                    warehouse=invoice.warehouse,
                    numbers=item.serial_numbers,
                    quantity=item.quantity,
                    source=SerialNumber.Status.SOLD,
                    target=SerialNumber.Status.AVAILABLE,
                    user=user,
                )
            sale_moves = CogsService.invoice_sale_moves(invoice, product=item.product)
            remaining = item.quantity
            last_sale_unit_cost = Decimal("0")
            if sale_moves:
                for move in sale_moves:
                    if remaining <= 0:
                        break
                    lot_qty = abs(Decimal(str(move.quantity)))
                    move_unit_cost = Decimal(str(move.unit_cost or 0))
                    last_sale_unit_cost = move_unit_cost
                    prior_sr_ids = [
                        str(pk)
                        for pk in SalesReturn.objects.filter(
                            sales_invoice=invoice,
                            status=SalesReturn.Status.COMPLETED,
                        )
                        .exclude(pk=sales_return.pk)
                        .values_list("id", flat=True)
                    ]
                    already_lot = (
                        StockMovement.objects.filter(
                            company=sales_return.company,
                            movement_type=MovementType.SALES_RETURN,
                            product=item.product,
                            batch=move.batch,
                            reference_type="sales_return",
                            reference_id__in=prior_sr_ids,
                        ).aggregate(total=Sum("quantity"))["total"]
                        or Decimal("0")
                    )
                    available_on_lot = lot_qty - already_lot
                    if available_on_lot <= 0:
                        continue
                    take = min(remaining, available_on_lot)
                    # BB-000720: restore original sale peels instead of inventing a new layer.
                    inbound = InventoryService.post_movement(
                        company=sales_return.company,
                        warehouse=invoice.warehouse,
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
            if remaining > 0:
                inv_line = invoice.items.filter(product=item.product).first()
                fallback_cost = last_sale_unit_cost
                if fallback_cost <= 0 and sale_moves:
                    fallback_cost = Decimal(str(sale_moves[-1].unit_cost or 0))
                inbound = InventoryService.post_movement(
                    company=sales_return.company,
                    warehouse=invoice.warehouse,
                    product=item.product,
                    batch=getattr(inv_line, "batch", None) if inv_line else None,
                    movement_type=MovementType.SALES_RETURN,
                    quantity=remaining,
                    unit_cost=fallback_cost,
                    reference_type="sales_return",
                    reference_id=sales_return.pk,
                    user=user,
                )
                # No matching peels — restore_fifo_peels creates a fallback layer from inbound.
                stub = type("OutboundStub", (), {"layer_peels": [], "unit_cost": fallback_cost})()
                InventoryService.restore_fifo_peels(stub, inbound)
                cogs_rev += fallback_cost * remaining
        return cogs_rev
