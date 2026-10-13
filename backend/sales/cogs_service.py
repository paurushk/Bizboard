"""COGS accumulation helpers — extracted from SalesService (BB-000476)."""

from decimal import Decimal

from django.db.models import Sum

from core.exceptions import BusinessRuleError
from inventory.models import MovementType, SerialNumber, StockMovement
from inventory.services import InventoryService, InventoryValuationService, SerialNumberService

from .models import SalesReturn, SalesReturnItem


class CogsService:
    @staticmethod
    def line_tag(line_pk):
        """Stamped on SALE / SALES_RETURN movements so a return restores the lot
        its own invoice line sold from (SRF line-exact restore)."""
        return f"SALE_LINE:{line_pk}" if line_pk else ""

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

            # DATA-01: Sort items deterministically by (product_id, batch_id, pk)
            # to guarantee lock hierarchy and prevent PostgreSQL 40P01 deadlocks on concurrent sales.
            sorted_items = sorted(
                items,
                key=lambda it: (
                    it.product_id or 0,
                    getattr(it, "batch_id", 0) or 0,
                    it.pk or 0,
                ),
            )
            for item in sorted_items:
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
                        reason=CogsService.line_tag(item.pk),
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
    def line_sale_moves(invoice, item, sale_moves):
        """Sale movements that belong to the invoice line a return line names.

        Returns ``(moves, mode, keys)``. ``mode`` is ``"tag"`` (movements carry
        ``SALE_LINE:<id>``), ``"seq"`` (older invoice: the postings are replayed in
        the order they were made and accepted only if they add up exactly),
        ``"batch"`` (the line names a batch, e.g. a delivery-challan sale) or ``""``
        (cannot tell: whole-product FIFO order). ``keys`` are the invoice-line ids
        that share those movements, used to count what earlier returns consumed.
        """
        from inventory.item_stock import base_quantity

        sid = getattr(item, "source_item_id", None)
        if not sid:
            return sale_moves, "", []
        tagged = [m for m in sale_moves if m.reason == CogsService.line_tag(sid)]
        if tagged:
            return tagged, "tag", [sid]
        inv_items = list(
            invoice.items.filter(product_id=item.product_id).select_related("product").order_by("id")
        )
        target = next((i for i in inv_items if i.id == sid), None)
        if target is None or not sale_moves:
            return sale_moves, "", []
        if all(m.reference_type == "sales_invoice" for m in sale_moves):
            ordered = sorted(inv_items, key=lambda i: (i.batch_id or 0, i.pk))
            pos, mapping, ok = 0, {}, True
            for it in ordered:
                need = base_quantity(it.product, it.quantity, getattr(it, "unit_name", None))
                got, mine = Decimal("0"), []
                while pos < len(sale_moves) and got < need:
                    got += abs(Decimal(str(sale_moves[pos].quantity)))
                    mine.append(sale_moves[pos])
                    pos += 1
                if got != need:
                    ok = False
                    break
                mapping[it.id] = mine
            if ok and pos == len(sale_moves):
                return mapping[sid], "seq", [sid]
        challan_moves = CogsService._challan_line_moves(invoice, target, inv_items, sale_moves)
        if challan_moves:
            return challan_moves, "seq", [sid]
        if target.batch_id:
            by_batch = [m for m in sale_moves if m.batch_id == target.batch_id]
            if by_batch:
                return by_batch, "batch", [i.id for i in inv_items if i.batch_id == target.batch_id]
        return sale_moves, "", []

    @staticmethod
    def _challan_line_moves(invoice, target, inv_items, sale_moves):
        """Movements of the challan line that became ``target`` (single-challan invoices).

        Needs the invoice to still mirror its challan line for line (same products and
        quantities in the same order); anything else returns [] and the caller falls back.
        New challan postings carry ``CHALLAN_LINE:<id>``; older ones are replayed in
        posting order and accepted only if they add up exactly.
        """
        from inventory.item_stock import base_quantity
        from sales.models import DeliveryChallan

        challans = list(DeliveryChallan.objects.filter(converted_invoice=invoice, stock_posted=True))
        if len(challans) != 1:
            return []
        challan = challans[0]
        moves = [m for m in sale_moves if m.reference_type == "delivery_challan" and str(m.reference_id) == str(challan.pk)]
        if not moves:
            return []
        c_items = list(challan.items.select_related("product").order_by("id"))
        all_inv = list(invoice.items.select_related("product").order_by("id"))
        if len(c_items) != len(all_inv):
            return []
        for ci, ii in zip(c_items, all_inv):
            if ci.product_id != ii.product_id:
                return []
            if base_quantity(ci.product, ci.quantity, getattr(ci, "unit_name", None)) != base_quantity(
                ii.product, ii.quantity, getattr(ii, "unit_name", None)
            ):
                return []
        position = next((i for i, ii in enumerate(all_inv) if ii.id == target.id), None)
        if position is None:
            return []
        line = c_items[position]
        tagged = [m for m in moves if m.reason == f"CHALLAN_LINE:{line.pk}"]
        if tagged:
            return tagged
        same_product = [ci for ci in c_items if ci.product_id == target.product_id]
        pos, mapping = 0, {}
        for ci in same_product:
            need = base_quantity(ci.product, ci.quantity, getattr(ci, "unit_name", None))
            got, mine = Decimal("0"), []
            while pos < len(moves) and got < need:
                got += abs(Decimal(str(moves[pos].quantity)))
                mine.append(moves[pos])
                pos += 1
            if got != need:
                return []
            mapping[ci.pk] = mine
        if pos != len(moves):
            return []
        return mapping.get(line.pk, [])

    @staticmethod
    def restore_return_stock_and_cogs(sales_return: SalesReturn, invoice, items, user) -> Decimal:
        """Restore stock on return complete; return COGS reversal total."""
        cogs_rev = Decimal("0")
        damaged_cogs_rev = Decimal("0")
        done_by_line: dict[int, Decimal] = {}
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
            all_moves = CogsService.invoice_sale_moves(invoice, product=item.product)
            sale_moves, mode, line_keys = CogsService.line_sale_moves(invoice, item, all_moves)
            tag = CogsService.line_tag(getattr(item, "source_item_id", None)) if mode == "tag" else ""
            remaining = base_quantity(
                item.product,
                item.quantity,
                getattr(item, "unit_name", None) or unit_names.get(item.product_id),
            )
            # R2-009 + SR-06: include current sales_return.pk so multi-line returns
            # of the same product within the same return advance through sale_moves
            # sequentially instead of double-restoring the first lot.
            prior_sr_ids = [
                str(pk)
                for pk in SalesReturn.objects.filter(
                    sales_invoice=invoice,
                    status=SalesReturn.Status.COMPLETED,
                ).values_list("id", flat=True)
            ]
            if str(sales_return.pk) not in prior_sr_ids:
                prior_sr_ids.append(str(sales_return.pk))
            restored_lots = []
            if sale_moves:
                prior_qs = StockMovement.objects.filter(
                    company=sales_return.company,
                    movement_type=MovementType.SALES_RETURN,
                    product=item.product,
                    reference_type="sales_return",
                    reference_id__in=prior_sr_ids,
                )
                if tag:
                    prior_qs = prior_qs.filter(reason=tag)
                if mode in ("seq", "batch"):
                    # Earlier returns are attributed through the invoice lines (the same
                    # per-line accounting Complete uses, which also places returns that
                    # named no line); their movements carry no line tag on these invoices.
                    from .return_service import ReturnService

                    consumed_prior = Decimal("0")
                    try:
                        st = ReturnService.line_state(invoice, exclude_return=sales_return)
                        for k in line_keys:
                            consumed_prior += base_quantity(
                                item.product,
                                st["sold"].get(k, Decimal("0")) - st["after_returns"].get(k, Decimal("0")),
                                unit_names.get(item.product_id),
                            )
                    except BusinessRuleError:
                        for row in SalesReturnItem.objects.filter(
                            sales_return__sales_invoice=invoice,
                            sales_return__status=SalesReturn.Status.COMPLETED,
                            source_item_id__in=line_keys,
                        ).exclude(sales_return=sales_return).select_related("product"):
                            consumed_prior += base_quantity(
                                row.product, row.quantity,
                                getattr(row, "unit_name", None) or unit_names.get(row.product_id),
                            )
                    consumed_prior += sum((done_by_line.get(k, Decimal("0")) for k in line_keys), Decimal("0"))
                else:
                    prior_returned = prior_qs.aggregate(total=Sum("quantity"))["total"] or Decimal("0")
                    consumed_prior = Decimal(str(prior_returned))
                restoring = list(
                    StockMovement.objects.filter(
                        company=sales_return.company,
                        movement_type=MovementType.SALES_RETURN,
                        product=item.product,
                        reference_type="sales_return",
                        reference_id__in=prior_sr_ids,
                    )
                )
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
                        # tag mode: the line tag; otherwise point at the exact sale
                        # movement restored so cancel can undo that same movement.
                        reason=tag or f"SALE_MOVE:{move.pk}",
                        user=user,
                    )
                    InventoryService.restore_fifo_peels(
                        move,
                        inbound,
                        already_restored=InventoryService.already_restored_by_layer(move, restoring),
                    )
                    restoring.append(inbound)
                    cogs_rev += move_unit_cost * take
                    remaining -= take
                    restored_lots.append((move.batch, take, move_unit_cost))
                    for k in line_keys:
                        done_by_line[k] = done_by_line.get(k, Decimal("0")) + take
                        break
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
                for batch, take, move_unit_cost in restored_lots:
                    InventoryService.post_movement(
                        company=sales_return.company,
                        warehouse=invoice.warehouse,
                        product=item.product,
                        batch=batch,
                        movement_type=MovementType.ADJUSTMENT,
                        quantity=-take,
                        unit_cost=move_unit_cost,
                        reason="DAMAGED",
                        reference_type="sales_return_damaged",
                        reference_id=sales_return.pk,
                        user=user,
                    )
                    damaged_cogs_rev += move_unit_cost * take
        sales_return._damaged_cogs_rev = damaged_cogs_rev.quantize(Decimal("0.01"))
        return cogs_rev
