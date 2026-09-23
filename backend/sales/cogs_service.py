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
    def post_sale_stock_and_cogs(
        invoice, items, user, *, stock_from_challan: bool, warnings=None, cost_basis_counts: dict | None = None
    ) -> Decimal:
        """Issue stock on invoice complete; return total COGS.

        R2-007: appends a warning to `warnings` (if given) for any line whose
        cost basis resolves to zero, so a ₹0-COGS sale is never silent.

        `cost_basis_counts` (if given) is incremented at each of the tiers
        below — purely additive bookkeeping for reporting.InvoiceProfitService,
        no effect on the COGS total or the FIFO/valuation resolution itself.
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
                    if cost_basis_counts is not None:
                        cost_basis_counts["lines"] = cost_basis_counts.get("lines", 0) + 1
                    unit_cost = Decimal(str(move.unit_cost or 0))
                    if unit_cost == 0:
                        unit_cost = InventoryValuationService.unit_cost(
                            invoice.company, item.product, invoice.warehouse, batch=batch
                        )
                        if unit_cost:
                            # B8-029: stamp_cost() is the one documented,
                            # row-locked exception to append-only.
                            StockMovement.stamp_cost(move.pk, unit_cost=unit_cost)
                            move.unit_cost = unit_cost
                            if cost_basis_counts is not None:
                                cost_basis_counts["valuation_fallback"] = (
                                    cost_basis_counts.get("valuation_fallback", 0) + 1
                                )
                        else:
                            # R2-007: last resort — the product master purchase
                            # price, so a sale with no layer history doesn't book
                            # ₹0 COGS silently.
                            fallback = Decimal(str(getattr(item.product, "purchase_price", 0) or 0))
                            if fallback > 0:
                                unit_cost = fallback
                                StockMovement.stamp_cost(move.pk, unit_cost=unit_cost)
                                move.unit_cost = unit_cost
                                if cost_basis_counts is not None:
                                    cost_basis_counts["purchase_price_fallback"] = (
                                        cost_basis_counts.get("purchase_price_fallback", 0) + 1
                                    )
                            else:
                                if item.product.name not in zero_cost_products:
                                    zero_cost_products.append(item.product.name)
                                if cost_basis_counts is not None:
                                    cost_basis_counts["zero_cost"] = cost_basis_counts.get("zero_cost", 0) + 1
                    elif cost_basis_counts is not None:
                        cost_basis_counts["fifo"] = cost_basis_counts.get("fifo", 0) + 1
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
                    if cost_basis_counts is not None:
                        cost_basis_counts["lines"] = cost_basis_counts.get("lines", 0) + 1
                        # Already resolved when the challan's stock was posted —
                        # treat a non-zero stamped cost as FIFO-reliable here.
                        key = "fifo" if move.unit_cost else "zero_cost"
                        cost_basis_counts[key] = cost_basis_counts.get(key, 0) + 1
            if cogs_total == 0:
                for item in items:
                    unit_cost = InventoryValuationService.unit_cost(
                        invoice.company,
                        item.product,
                        invoice.warehouse,
                        batch=getattr(item, "batch", None),
                    )
                    if cost_basis_counts is not None:
                        cost_basis_counts["lines"] = cost_basis_counts.get("lines", 0) + 1
                    if unit_cost:
                        if cost_basis_counts is not None:
                            cost_basis_counts["valuation_fallback"] = (
                                cost_basis_counts.get("valuation_fallback", 0) + 1
                            )
                    else:
                        unit_cost = Decimal(str(getattr(item.product, "purchase_price", 0) or 0))
                        if unit_cost:
                            if cost_basis_counts is not None:
                                cost_basis_counts["purchase_price_fallback"] = (
                                    cost_basis_counts.get("purchase_price_fallback", 0) + 1
                                )
                        else:
                            if item.product.name not in zero_cost_products:
                                zero_cost_products.append(item.product.name)
                            if cost_basis_counts is not None:
                                cost_basis_counts["zero_cost"] = cost_basis_counts.get("zero_cost", 0) + 1
                    cogs_total += Decimal(str(unit_cost or 0)) * item.quantity
        if zero_cost_products and warnings is not None:
            warnings.append(
                f"{len(zero_cost_products)} line(s) have no cost basis — COGS was "
                f"booked as ₹0 for: {', '.join(zero_cost_products[:5])}"
                + ("…" if len(zero_cost_products) > 5 else "")
            )
        return cogs_total

    @staticmethod
    def challan_sale_moves(challan, *, product=None):
        qs = StockMovement.objects.filter(
            company=challan.company,
            movement_type=MovementType.SALE,
            reference_type="delivery_challan",
            reference_id=str(challan.pk),
        )
        if product is not None:
            qs = qs.filter(product=product)
        return list(qs.order_by("id"))

    @staticmethod
    def restore_challan_return_stock_and_cogs(challan_return, challan, items, user) -> Decimal:
        """Restore stock on a Delivery Challan return complete; return COGS reversal total.

        Mirrors restore_return_stock_and_cogs (sales-invoice returns) — same
        FIFO-peel-restore mechanics (BB-000720: restore the original sale
        peels instead of inventing a fresh SALES_RETURN layer), scoped to a
        challan's own SALE movements instead of an invoice's, since a
        Delivery Challan Return can complete against a challan that was
        never converted to an invoice.
        """
        from .models import DeliveryChallanReturn

        cogs_rev = Decimal("0")
        unit_names = {row.product_id: getattr(row, "unit_name", None) for row in challan.items.all()}
        for item in items:
            from inventory.item_stock import base_quantity, tracks_inventory

            if not tracks_inventory(item.product):
                continue
            if getattr(item.product, "track_serial", False):
                # DeliveryChallanReturnItem has no serial_numbers field (unlike
                # SalesReturnItem) — there is nowhere to record which specific
                # units come back, so SerialNumber status can't be transitioned
                # SOLD -> AVAILABLE. Refuse rather than silently desyncing serial
                # records from stock quantity.
                raise BusinessRuleError(
                    f"'{item.product.name}' is serial-tracked and cannot be returned via a "
                    "Delivery Challan Return yet — convert the challan to an invoice first "
                    "and use a Sales Return, which records serial numbers."
                )
            sale_moves = CogsService.challan_sale_moves(challan, product=item.product)
            remaining = base_quantity(
                item.product,
                item.quantity,
                getattr(item, "unit_name", None) or unit_names.get(item.product_id),
            )
            prior_return_ids = [
                str(pk)
                for pk in DeliveryChallanReturn.objects.filter(
                    challan=challan,
                    status=DeliveryChallanReturn.Status.COMPLETED,
                )
                .exclude(pk=challan_return.pk)
                .values_list("id", flat=True)
            ]
            if sale_moves:
                prior_returned = (
                    StockMovement.objects.filter(
                        company=challan_return.company,
                        movement_type=MovementType.SALES_RETURN,
                        product=item.product,
                        reference_type="DeliveryChallanReturn",
                        reference_id__in=prior_return_ids,
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
                    inbound = InventoryService.post_movement(
                        company=challan_return.company,
                        warehouse=move.warehouse or challan.warehouse,
                        product=item.product,
                        batch=move.batch,
                        movement_type=MovementType.SALES_RETURN,
                        quantity=take,
                        unit_cost=move_unit_cost,
                        reference_type="DeliveryChallanReturn",
                        reference_id=str(challan_return.pk),
                        user=user,
                    )
                    InventoryService.restore_fifo_peels(move, inbound)
                    cogs_rev += move_unit_cost * take
                    remaining -= take
            if remaining > 0:
                # No matching original SALE lot covers this quantity — restoring
                # at an invented cost (including 0) would desync FIFO layers /
                # dilute weighted-average cost, exactly the bug this method
                # exists to avoid. Fail loudly instead of guessing.
                raise BusinessRuleError(
                    f"Cannot restore stock for '{item.product.name}': no matching "
                    "original sale movement found for the returned quantity on this "
                    "delivery challan. Check the challan's stock history before retrying."
                )
        return cogs_rev

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
