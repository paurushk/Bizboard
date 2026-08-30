"""Inventory Service — balances, typed movements, adjustments (E2)."""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.help_codes import HelpCode

from .models import (
    MOVEMENT_SIGN, BatchLot, InventoryCostLayer, MovementType, StockBalance,
    StockMovement, SerialNumber, StockTransfer, Warehouse,
)


class InventoryService:
    @staticmethod
    def default_warehouse(company):
        warehouse = Warehouse.objects.filter(company=company, is_default=True).first()
        if warehouse:
            return warehouse
        # Safe for legacy/import callers and newly-created companies before the
        # data migration runs. The uniqueness constraint protects normal use.
        warehouse, _ = Warehouse.objects.get_or_create(
            company=company, code="DEFAULT",
            defaults={"name": "Default Godown", "is_default": True},
        )
        if not warehouse.is_default:
            warehouse.is_default = True
            warehouse.save(update_fields=["is_default"])
        return warehouse

    @staticmethod
    def post_movement(*, company, product, movement_type, quantity, unit_cost=None,
                      reference_type="", reference_id="", reason="", user=None,
                      skip_negative_check=False, warehouse=None, batch=None):
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
        warehouse = warehouse or InventoryService.default_warehouse(company)
        if warehouse.company_id != company.id:
            raise BusinessRuleError("Warehouse does not belong to this company.")
        if getattr(product, "company_id", None) not in (None, company.id):
            raise BusinessRuleError("Product does not belong to this company.")
        from .item_stock import tracks_inventory

        if not tracks_inventory(product):
            raise BusinessRuleError("Stock cannot be posted for a service or non-stock item.")
        inbound = Decimal(quantity) > 0 if movement_type == MovementType.ADJUSTMENT else MOVEMENT_SIGN.get(movement_type, 0) > 0
        if inbound and not warehouse.is_active:
            raise BusinessRuleError(f"Godown '{warehouse.name}' is inactive and cannot receive stock.")
        if batch is not None:
            if batch.company_id != company.id or batch.product_id != product.id:
                raise BusinessRuleError("Batch does not belong to this product and company.")
        if product.track_batch and batch is None:
            raise BusinessRuleError(f"A batch is required for tracked product '{product.name}'.")
        if movement_type == MovementType.ADJUSTMENT:
            if quantity == 0:
                raise BusinessRuleError("Adjustment quantity cannot be zero.")
            delta = quantity
        else:
            if quantity <= 0:
                raise BusinessRuleError("Movement quantity must be greater than zero.")
            delta = quantity * MOVEMENT_SIGN[movement_type]

        with transaction.atomic():
            try:
                balance, _ = StockBalance.objects.get_or_create(
                    company=company, warehouse=warehouse, product=product, batch=batch
                )
            except IntegrityError:
                # BB-000236: concurrent first-movement race on unique balance.
                balance = StockBalance.objects.get(
                    company=company, warehouse=warehouse, product=product, batch=batch
                )
            balance = StockBalance.objects.select_for_update().get(pk=balance.pk)

            if movement_type == MovementType.OPENING_STOCK:
                # Unique per warehouse+product+batch; re-check after the balance lock.
                already_has_opening = StockMovement.objects.filter(
                    company=company,
                    warehouse=warehouse,
                    product=product,
                    batch=batch,
                    movement_type=MovementType.OPENING_STOCK,
                ).exclude(reference_type="import_voided").exists()
                if already_has_opening:
                    raise BusinessRuleError(
                        f"Opening stock has already been recorded for '{product.name}'"
                        + (f" batch '{batch.batch_no}'." if batch is not None else ".")
                    )

            if delta < 0 and not skip_negative_check:
                if batch and company.block_expired_stock and batch.expiry_date and batch.expiry_date < timezone.localdate():
                    raise BusinessRuleError(f"Batch '{batch.batch_no}' is expired and cannot be issued.")
                resulting = balance.available + delta
                if resulting < 0 and company.negative_stock_policy == "BLOCK":
                    raise BusinessRuleError(
                        f"Insufficient stock for '{product.name}': available "
                        f"{balance.available}, required {-delta}."
                    )

            movement = StockMovement.objects.create(
                company=company,
                warehouse=warehouse,
                product=product,
                batch=batch,
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
            # Wave 16B: perpetual FIFO layers
            InventoryService._apply_cost_layers(
                company=company,
                warehouse=warehouse,
                product=product,
                batch=batch,
                movement=movement,
                delta=delta,
                unit_cost=unit_cost,
                movement_type=movement_type,
            )
        return movement

    @staticmethod
    def post_opening(*, company, product, quantity, unit_cost=None, warehouse=None, batch=None,
                     batch_no="", expiry_date=None, manufacturing_date=None, serial_numbers=None,
                     as_of=None, user=None, reference_type="opening_stock", reference_id=""):
        """Validate and post one OPENING_STOCK row (lot/serial aware)."""
        from .item_stock import (
            get_or_create_batch,
            lot_is_expired,
            opening_unit_cost,
            resolve_warehouse,
            tracks_inventory,
            validate_opening_as_of,
        )

        if not tracks_inventory(product):
            raise BusinessRuleError("Service and non-stock items cannot have opening stock.")
        quantity = Decimal(str(quantity))
        if quantity <= 0:
            raise BusinessRuleError("Opening quantity must be greater than zero.")
        warehouse = resolve_warehouse(company, getattr(warehouse, "pk", warehouse))
        as_of = validate_opening_as_of(company, as_of, expiry_date)
        if isinstance(batch, int) or (isinstance(batch, str) and str(batch).isdigit()):
            from .models import BatchLot

            resolved = BatchLot.objects.filter(
                pk=int(batch), company=company, product=product
            ).first()
            if resolved is None:
                raise BusinessRuleError("Invalid batch for this product.")
            batch = resolved
        if product.track_batch:
            if batch is None:
                batch = get_or_create_batch(
                    company=company, product=product, batch_no=batch_no,
                    expiry_date=expiry_date, manufacturing_date=manufacturing_date, user=user,
                )
            if not batch.expiry_date:
                raise BusinessRuleError("Expiry date is required for batch-tracked opening stock.")
            if lot_is_expired(batch, as_of):
                raise BusinessRuleError("Expired lots cannot be posted as opening stock.")
        elif batch_no or expiry_date:
            raise BusinessRuleError("Batch and expiry are only allowed when batch tracking is on.")
        serials = [str(s).strip() for s in (serial_numbers or []) if str(s).strip()]
        if product.track_serial:
            if not serials:
                raise BusinessRuleError("Serial numbers are required for serial-tracked opening stock.")
            if Decimal(len(serials)) != quantity:
                raise BusinessRuleError("Opening quantity must equal the number of serials.")
        elif serials:
            raise BusinessRuleError("Serial numbers are only allowed when serial tracking is on.")
        cost = opening_unit_cost(product, unit_cost)
        with transaction.atomic():
            movement = InventoryService.post_movement(
                company=company,
                product=product,
                movement_type=MovementType.OPENING_STOCK,
                quantity=quantity,
                unit_cost=cost,
                reference_type=reference_type,
                reference_id=reference_id,
                reason=f"Opening as of {as_of.isoformat()}",
                user=user,
                warehouse=warehouse,
                batch=batch,
            )
            if serials:
                SerialNumberService.receive(
                    company=company, product=product, warehouse=warehouse,
                    numbers=serials, quantity=quantity, user=user,
                )
        return movement

    @staticmethod
    def post_opening_movements_batch(*, company, items, reference_type="", reference_id="", user=None):
        """
        Bulk-write OPENING_STOCK movements + balance/FIFO updates.

        `items` is a list of dicts: ``product``, ``quantity``, optional ``unit_cost``.
        Same invariants as ``post_movement`` (one-shot opening per warehouse+product,
        batch required for tracked products) but without a per-row query loop.
        """
        if not items:
            return []
        from .item_stock import opening_unit_cost, tracks_inventory

        warehouse = InventoryService.default_warehouse(company)
        product_ids = []
        prepared = []
        for item in items:
            product = item["product"]
            if not tracks_inventory(product):
                raise BusinessRuleError(
                    f"Service and non-stock items cannot have opening stock ('{product.name}')."
                )
            quantity = Decimal(item["quantity"])
            if quantity <= 0:
                raise BusinessRuleError("Movement quantity must be greater than zero.")
            if product.track_batch:
                raise BusinessRuleError(f"A batch is required for tracked product '{product.name}'.")
            if product.track_serial:
                raise BusinessRuleError("Serial numbers are required for serial-tracked opening stock.")
            product_ids.append(product.pk)
            prepared.append((product, quantity, opening_unit_cost(product, item.get("unit_cost"))))

        with transaction.atomic():
            now = timezone.now()
            # R2-026: two concurrent opening-stock imports of a brand-new product
            # (no StockBalance row yet) could both pass the one-shot check and
            # both write OPENING_STOCK. Lock the Product rows — which always
            # exist — so those imports serialise here.
            from masters.models import Product as _Product

            list(
                _Product.objects.select_for_update()
                .filter(pk__in=sorted(product_ids))
                .values_list("pk", flat=True)
            )
            existing = {
                b.product_id: b
                for b in StockBalance.objects.select_for_update().filter(
                    company=company,
                    warehouse=warehouse,
                    product_id__in=product_ids,
                    batch__isnull=True,
                )
            }
            already = set(
                StockMovement.objects.filter(
                    company=company,
                    warehouse=warehouse,
                    product_id__in=product_ids,
                    batch__isnull=True,
                    movement_type=MovementType.OPENING_STOCK,
                )
                .exclude(reference_type="import_voided")
                .values_list("product_id", flat=True)
            )
            if already:
                names = {
                    p.pk: p.name
                    for p in (item["product"] for item in items)
                    if p.pk in already
                }
                first = names.get(next(iter(already)), "product")
                raise BusinessRuleError(
                    f"Opening stock has already been recorded for '{first}'."
                )
            movements = [
                StockMovement(
                    company=company,
                    warehouse=warehouse,
                    product=product,
                    batch=None,
                    movement_type=MovementType.OPENING_STOCK,
                    quantity=quantity,
                    unit_cost=unit_cost,
                    reference_type=reference_type,
                    reference_id=str(reference_id),
                    created_by=user,
                    created_at=now,
                )
                for product, quantity, unit_cost in prepared
            ]
            created = StockMovement.objects.bulk_create(movements, batch_size=500)
            to_create, to_update = [], []
            for (product, quantity, _cost), _movement in zip(prepared, created):
                balance = existing.get(product.pk)
                if balance is None:
                    to_create.append(
                        StockBalance(
                            company=company,
                            warehouse=warehouse,
                            product=product,
                            batch=None,
                            on_hand=quantity,
                        )
                    )
                else:
                    balance.on_hand = balance.on_hand + quantity
                    to_update.append(balance)
            if to_create:
                StockBalance.objects.bulk_create(to_create, batch_size=500)
            if to_update:
                StockBalance.objects.bulk_update(to_update, ["on_hand"], batch_size=500)

            method = getattr(company, "inventory_valuation_method", "WAVG") or "WAVG"
            if method == "FIFO":
                from .models import InventoryCostLayer

                InventoryCostLayer.objects.bulk_create(
                    [
                        InventoryCostLayer(
                            company=company,
                            warehouse=warehouse,
                            product=product,
                            batch=None,
                            qty_remaining=quantity,
                            unit_cost=Decimal(str(unit_cost or 0)),
                            source_movement=movement,
                            created_by=user,
                            updated_by=user,
                            created_at=now,
                            updated_at=now,
                        )
                        for (product, quantity, unit_cost), movement in zip(prepared, created)
                    ],
                    batch_size=500,
                )
        return created

    @staticmethod
    def _apply_cost_layers(*, company, warehouse, product, batch, movement, delta, unit_cost, movement_type):
        from .models import InventoryCostLayer

        method = getattr(company, "inventory_valuation_method", "WAVG") or "WAVG"
        if method != "FIFO":
            return
        cancel_restore = (movement.reference_type or "") in (
            "sales_invoice_cancel",
            "sales_invoice_cancel_challan",
            "delivery_challan_cancel",
            "work_order_cancel",
            "stock_transfer_cancel",
        )
        if delta > 0 and cancel_restore:
            return
        # BB-000720: sales returns restore original sale peels via restore_fifo_peels —
        # do not invent a fresh SALES_RETURN layer here.
        if delta > 0 and movement_type in (
            MovementType.PURCHASE,
            MovementType.OPENING_STOCK,
            MovementType.TRANSFER_IN,
            MovementType.MANUFACTURE_RECEIPT,
            MovementType.ADJUSTMENT,
        ):
            InventoryCostLayer.objects.create(
                company=company,
                warehouse=warehouse,
                product=product,
                batch=batch,
                qty_remaining=delta,
                unit_cost=Decimal(str(unit_cost or 0)),
                source_movement=movement,
                created_by=movement.created_by,
                updated_by=movement.created_by,
            )
            return
        # BB-000718/719/724: negative reverses that retire a specific inbound layer
        # (caller invokes retire_source_layers) — do not peel FIFO-oldest.
        if delta < 0 and (movement.reference_type or "") in (
            "purchase_invoice_cancel",
            "purchase_invoice_edit",
            "purchase_return",
            "purchase_return_damaged",
            "stock_transfer_cancel",
            "work_order_cancel",
        ):
            return
        if delta < 0:
            need = -delta
            layers = list(
                InventoryCostLayer.objects.select_for_update()
                .filter(
                    company=company,
                    warehouse=warehouse,
                    product=product,
                    batch=batch,
                    qty_remaining__gt=0,
                )
                .order_by("id")
            )
            cost_total = Decimal("0")
            remaining = need
            peels = []
            for layer in layers:
                if remaining <= 0:
                    break
                take = min(remaining, layer.qty_remaining)
                cost_total += take * layer.unit_cost
                layer.qty_remaining -= take
                layer.save(update_fields=["qty_remaining", "updated_at"])
                peels.append({"layer_id": layer.pk, "qty": str(take), "unit_cost": str(layer.unit_cost)})
                remaining -= take
            if remaining > 0:
                # R2-025: NegativeStockPolicy only has BLOCK / WARN ("ALLOW" was
                # dead). Under WARN, cost the shortfall at the best available
                # basis: last known layer cost, else product-level WAVG, else the
                # master purchase price — never a silent ₹0.
                if company.negative_stock_policy != "BLOCK":
                    fallback_cost = Decimal("0")
                    if peels:
                        fallback_cost = Decimal(str(peels[-1].get("unit_cost") or 0))
                    if fallback_cost <= 0:
                        fallback_cost = Decimal(str(
                            InventoryValuationService.unit_cost(
                                company, product, warehouse=warehouse, batch=batch
                            ) or 0
                        ))
                    if fallback_cost <= 0:
                        fallback_cost = Decimal(str(product.purchase_price or 0))
                    cost_total += remaining * fallback_cost
                    peels.append({"layer_id": None, "qty": str(remaining), "unit_cost": str(fallback_cost)})
                    remaining = Decimal("0")
                else:
                    raise BusinessRuleError(
                        f"Insufficient FIFO cost layers for '{product.name}' "
                        f"(short {remaining})."
                    )
            # Stamp movement with weighted layer cost for this issue.
            # Use QuerySet.update to honor StockMovement append-only save() guard.
            if need > 0:
                stamped = (cost_total / need).quantize(Decimal("0.0001"))
                StockMovement.objects.filter(pk=movement.pk).update(unit_cost=stamped, layer_peels=peels)
                movement.unit_cost = stamped
                movement.layer_peels = peels

    @staticmethod
    def restore_fifo_peels(outbound_movement, inbound_movement=None) -> None:
        """BB-000601: put peeled qty back on the original layers (no new inbound layer)."""
        from .models import InventoryCostLayer

        if outbound_movement is None:
            return
        method = getattr(outbound_movement.company, "inventory_valuation_method", "WAVG") or "WAVG"
        if method != "FIFO":
            return
        peels = outbound_movement.layer_peels or []
        if peels:
            for peel in peels:
                layer = (
                    InventoryCostLayer.objects.select_for_update()
                    .filter(pk=peel.get("layer_id"))
                    .first()
                )
                if layer is None:
                    continue
                layer.qty_remaining += Decimal(str(peel.get("qty") or 0))
                layer.save(update_fields=["qty_remaining", "updated_at"])
            return
        if inbound_movement is None:
            return
        qty = abs(Decimal(str(inbound_movement.quantity or 0)))
        if qty <= 0:
            return
        InventoryCostLayer.objects.create(
            company=inbound_movement.company,
            warehouse=inbound_movement.warehouse,
            product=inbound_movement.product,
            batch=inbound_movement.batch,
            qty_remaining=qty,
            unit_cost=Decimal(str(outbound_movement.unit_cost or inbound_movement.unit_cost or 0)),
            source_movement=inbound_movement,
            created_by=inbound_movement.created_by,
            updated_by=inbound_movement.created_by,
        )

    @staticmethod
    def retire_source_layers(source_movement, quantity) -> None:
        """BB-000718: reduce/retire layers created by a specific inbound movement."""
        from .models import InventoryCostLayer

        if source_movement is None:
            return
        method = getattr(source_movement.company, "inventory_valuation_method", "WAVG") or "WAVG"
        if method != "FIFO":
            return
        need = Decimal(str(quantity))
        if need <= 0:
            return
        layers = list(
            InventoryCostLayer.objects.select_for_update()
            .filter(source_movement=source_movement, qty_remaining__gt=0)
            .order_by("id")
        )
        remaining = need
        for layer in layers:
            if remaining <= 0:
                break
            take = min(remaining, layer.qty_remaining)
            layer.qty_remaining -= take
            layer.save(update_fields=["qty_remaining", "updated_at"])
            remaining -= take
        if remaining > 0:
            raise BusinessRuleError(
                f"Cannot reverse stock: source FIFO layer for '{source_movement.product.name}' "
                f"has already been issued (short {remaining})."
            )

    @staticmethod
    def available_quantity(company, product, warehouse=None, batch=None) -> Decimal:
        """Available = on_hand - reserved (across matching balance rows)."""
        qs = StockBalance.objects.filter(company=company, product=product)
        if warehouse:
            qs = qs.filter(warehouse=warehouse)
        if batch is not None:
            qs = qs.filter(batch=batch)
        agg = qs.aggregate(on_hand=Sum("on_hand"), reserved=Sum("reserved"))
        on_hand = agg["on_hand"] or Decimal("0")
        reserved = agg["reserved"] or Decimal("0")
        return on_hand - reserved

    @staticmethod
    def _stock_in_other_warehouses(company, product, warehouse):
        """[(godown name, available qty)] for every OTHER godown holding this product."""
        rows = (
            StockBalance.objects.filter(company=company, product=product)
            .exclude(warehouse=warehouse)
            .values("warehouse__name")
            .annotate(on_hand=Sum("on_hand"), reserved=Sum("reserved"))
        )
        out = []
        for row in rows:
            qty = (row["on_hand"] or Decimal("0")) - (row["reserved"] or Decimal("0"))
            if qty > 0:
                out.append((row["warehouse__name"], qty))
        out.sort(key=lambda pair: pair[1], reverse=True)
        return out

    @staticmethod
    def check_negative_stock(company, product, required_qty, warehouse=None, batch=None):
        """Negative-stock policy on available qty (on_hand - reserved)."""
        required = Decimal(required_qty)
        available = InventoryService.available_quantity(company, product, warehouse, batch)
        if available >= required:
            return None

        where = f" in godown '{warehouse.name}'" if warehouse is not None else ""
        # The Products list shows a company-wide available total, so a per-godown
        # shortfall here looks like a contradiction. Point the user at the godown
        # that actually holds the stock instead of just reporting "available 0".
        elsewhere = ""
        if warehouse is not None and batch is None:
            other = InventoryService._stock_in_other_warehouses(company, product, warehouse)
            if other:
                listed = ", ".join(f"{name}: {qty}" for name, qty in other)
                elsewhere = f" Available in other godowns — {listed}."

        if company.negative_stock_policy == "BLOCK":
            raise BusinessRuleError(
                f"Insufficient stock for '{product.name}'{where}: "
                f"available {available}, required {required}.{elsewhere}",
                code=HelpCode.INSUFFICIENT_STOCK,
            )
        return (
            f"Stock for '{product.name}'{where} will go negative (available {available})."
            + elsewhere
        )

    @staticmethod
    @transaction.atomic
    def reserve_stock(company, warehouse, product, qty, user=None, batch=None):
        """Increase reserved against available (on_hand - reserved); BLOCK when insufficient.

        BB-000343: when product.track_batch and batch is None, allocate FEFO lots and
        reserve against each lot balance (not only the unbatched row).
        """
        qty = Decimal(qty)
        if qty <= 0:
            raise BusinessRuleError("Reservation quantity must be greater than zero.")
        warehouse = warehouse or InventoryService.default_warehouse(company)
        if warehouse.company_id != company.id:
            raise BusinessRuleError("Warehouse does not belong to this company.")

        if product.track_batch and batch is None:
            remaining = qty
            for lot in InventoryValuationService.fefo_batches(company, product, warehouse):
                if remaining <= 0:
                    break
                available = InventoryService.available_quantity(company, product, warehouse, lot)
                take = min(remaining, available)
                if take > 0:
                    InventoryService.reserve_stock(
                        company, warehouse, product, take, user=user, batch=lot
                    )
                    remaining -= take
            if remaining > 0 and company.negative_stock_policy == "BLOCK":
                raise BusinessRuleError(
                    f"Insufficient batched stock for '{product.name}': available short {remaining}."
                )
            if remaining > 0:
                try:
                    ub, _ = StockBalance.objects.get_or_create(
                        company=company, warehouse=warehouse, product=product, batch=None
                    )
                except IntegrityError:
                    ub = StockBalance.objects.get(
                        company=company, warehouse=warehouse, product=product, batch=None
                    )
                ub = StockBalance.objects.select_for_update().get(pk=ub.pk)
                available = ub.on_hand - ub.reserved
                take = min(remaining, max(available, Decimal("0")))
                if take > 0:
                    ub.reserved = ub.reserved + take
                    if ub.reserved > ub.on_hand:
                        ub.reserved = max(ub.on_hand, Decimal("0"))
                    ub.save(update_fields=["reserved"])
            return None

        try:
            balance, _ = StockBalance.objects.get_or_create(
                company=company, warehouse=warehouse, product=product, batch=batch
            )
        except IntegrityError:
            balance = StockBalance.objects.get(
                company=company, warehouse=warehouse, product=product, batch=batch
            )
        balance = StockBalance.objects.select_for_update().get(pk=balance.pk)
        available = balance.on_hand - balance.reserved
        if available < qty and company.negative_stock_policy == "BLOCK":
            raise BusinessRuleError(
                f"Insufficient stock for '{product.name}': available {available}, required {qty}."
            )
        take = min(qty, max(available, Decimal("0")))
        if take <= 0:
            return balance
        balance.reserved = balance.reserved + take
        balance.save(update_fields=["reserved"])
        return balance

    @staticmethod
    @transaction.atomic
    def release_reservation(company, warehouse, product, qty, user=None, batch=None):
        """Decrease reserved (floored at zero). BB-000343: release across FEFO lots when batched."""
        qty = Decimal(qty)
        if qty <= 0:
            return None
        warehouse = warehouse or InventoryService.default_warehouse(company)
        if product.track_batch and batch is None:
            remaining = qty
            # BB-000437: release in same FEFO order as reserve (expiry asc), not -id.
            balances = list(
                StockBalance.objects.select_for_update()
                .filter(
                    company=company, warehouse=warehouse, product=product, reserved__gt=0
                )
                .select_related("batch")
                .order_by("batch__expiry_date", "batch_id", "id")
            )
            for balance in balances:
                if remaining <= 0:
                    break
                take = min(remaining, balance.reserved)
                balance.reserved = balance.reserved - take
                balance.save(update_fields=["reserved"])
                remaining -= take
            return None
        try:
            balance = StockBalance.objects.select_for_update().get(
                company=company, warehouse=warehouse, product=product, batch=batch
            )
        except StockBalance.DoesNotExist:
            return None
        balance.reserved = max(Decimal("0"), balance.reserved - qty)
        balance.save(update_fields=["reserved"])
        return balance

    @staticmethod
    def rebuild_balance(company, product, warehouse=None, batch=None):
        """Balances are a cache — always rebuildable from movements."""
        warehouse = warehouse or InventoryService.default_warehouse(company)
        total = (
            StockMovement.objects.filter(
                company=company, product=product, warehouse=warehouse, batch=batch,
            )
            .aggregate(total=Sum("quantity"))["total"]
            or Decimal("0")
        )
        balance, _ = StockBalance.objects.get_or_create(
            company=company, warehouse=warehouse, product=product, batch=batch,
        )
        balance.on_hand = total
        # BB-000403: reserved must follow FEFO lot allocation, not dump onto unbatched row.
        reserved = Decimal("0")
        # BB-000757: lazy get_model avoids permanent sales.models import coupling.
        from django.apps import apps

        SalesOrder = apps.get_model("sales", "SalesOrder")
        SalesOrderItem = apps.get_model("sales", "SalesOrderItem")

        # BB-000733: only confirmed SOs scoped to this warehouse (null → default WH).
        default_wh = InventoryService.default_warehouse(company)
        so_qs = SalesOrderItem.objects.filter(
            sales_order__company=company,
            sales_order__status=SalesOrder.Status.CONFIRMED,
            product=product,
        )
        if warehouse.id == default_wh.id:
            so_qs = so_qs.filter(
                Q(sales_order__warehouse=warehouse)
                | Q(sales_order__warehouse__isnull=True)
            )
        else:
            so_qs = so_qs.filter(sales_order__warehouse=warehouse)
        so_qty = so_qs.aggregate(total=Sum("quantity"))["total"] or Decimal("0")
        if so_qty > 0 and product.track_batch:
            # Allocate confirmed SO qty across FEFO lots like reserve_stock.
            remaining = so_qty
            for lot in InventoryValuationService.fefo_batches(company, product, warehouse):
                if remaining <= 0:
                    break
                lot_on_hand = (
                    StockMovement.objects.filter(
                        company=company, product=product, warehouse=warehouse, batch=lot,
                    ).aggregate(total=Sum("quantity"))["total"]
                    or Decimal("0")
                )
                take = min(remaining, max(Decimal("0"), lot_on_hand))
                if batch_id := getattr(lot, "id", None):
                    if batch is not None and getattr(batch, "id", batch) == batch_id:
                        reserved = take
                remaining -= take
            if batch is None:
                reserved = Decimal("0")  # unbatched row holds none when FEFO used
        elif so_qty > 0 and batch is None:
            reserved = so_qty
        balance.reserved = min(max(reserved, Decimal("0")), max(balance.on_hand, Decimal("0")))
        balance.save(update_fields=["on_hand", "reserved"])
        return balance

    @staticmethod
    @transaction.atomic
    def seed_fifo_layers_from_balances(company):
        """
        Create InventoryCostLayer rows from current StockBalance.on_hand using
        weighted-average / purchase cost so a WAVG→FIFO switch can proceed.
        Skips products that already have covering layers.
        """
        created = 0
        balances = (
            StockBalance.objects.filter(company=company, on_hand__gt=0)
            .select_related("product", "warehouse", "batch")
        )
        for bal in balances:
            existing_qty = (
                InventoryCostLayer.objects.filter(
                    company=company,
                    warehouse=bal.warehouse,
                    product=bal.product,
                    batch=bal.batch,
                    qty_remaining__gt=0,
                ).aggregate(total=Sum("qty_remaining"))["total"]
                or Decimal("0")
            )
            gap = Decimal(str(bal.on_hand)) - Decimal(str(existing_qty))
            if gap <= 0:
                continue
            unit_cost = InventoryValuationService.unit_cost(
                company, bal.product, warehouse=bal.warehouse, batch=bal.batch
            )
            if not unit_cost:
                unit_cost = Decimal(str(bal.product.purchase_price or 0))
            if unit_cost <= 0:
                continue
            InventoryCostLayer.objects.create(
                company=company,
                warehouse=bal.warehouse,
                product=bal.product,
                batch=bal.batch,
                qty_remaining=gap,
                unit_cost=unit_cost,
                source_movement=None,
            )
            created += 1
        return created


class SerialNumberService:
    """Validate and transition uniquely identified stock units."""

    @staticmethod
    def _numbers(numbers, quantity, product):
        numbers = [str(number).strip() for number in (numbers or []) if str(number).strip()]
        if len(numbers) != len(set(numbers)):
            raise BusinessRuleError(f"Duplicate serial numbers supplied for '{product.name}'.")
        if Decimal(str(quantity)) != Decimal(len(numbers)):
            raise BusinessRuleError(
                f"Exactly {quantity} serial number(s) are required for tracked product '{product.name}'."
            )
        return numbers

    @classmethod
    def receive(cls, *, company, product, warehouse, numbers, quantity, user=None):
        for value in cls._numbers(numbers, quantity, product):
            try:
                serial, created = SerialNumber.objects.select_for_update().get_or_create(
                    company=company,
                    product=product,
                    serial_number=value,
                    defaults={
                        "warehouse": warehouse,
                        "status": SerialNumber.Status.AVAILABLE,
                        "created_by": user, "updated_by": user,
                    },
                )
            except IntegrityError:
                # BB-000081: concurrent first-receive race on unique serial (same as post_movement).
                serial = SerialNumber.objects.select_for_update().get(
                    company=company, product=product, serial_number=value,
                )
                created = False
            if not created:
                raise BusinessRuleError(f"Serial number '{value}' already exists.")

    @classmethod
    def transition(cls, *, company, product, warehouse, numbers, quantity, source, target, user=None):
        for value in cls._numbers(numbers, quantity, product):
            try:
                serial = SerialNumber.objects.select_for_update().get(
                    company=company, product=product, serial_number=value, status=source
                )
            except SerialNumber.DoesNotExist as exc:
                raise BusinessRuleError(
                    f"Serial number '{value}' is not {source.lower()} for '{product.name}'."
                ) from exc
            if warehouse is not None and serial.warehouse_id != warehouse.id:
                raise BusinessRuleError(f"Serial number '{value}' is not in the selected warehouse.")
            serial.status = target
            serial.warehouse = warehouse
            serial.updated_by = user
            serial.save(update_fields=["status", "warehouse", "updated_by", "updated_at"])


class StockTransferService:
    @staticmethod
    @transaction.atomic
    def complete(transfer: StockTransfer, user=None):
        transfer = StockTransfer.objects.select_for_update().get(pk=transfer.pk)
        if transfer.status != StockTransfer.Status.DRAFT:
            raise BusinessRuleError(f"Cannot complete transfer in status {transfer.status}.")
        lines = list(transfer.lines.select_related("product", "batch"))
        if not lines:
            raise BusinessRuleError("Cannot complete a transfer without line items.")
        if transfer.from_warehouse_id == transfer.to_warehouse_id:
            raise BusinessRuleError("Transfer source and destination must differ.")
        for line in lines:
            if line.quantity <= 0:
                raise BusinessRuleError("Transfer quantities must be greater than zero.")
            if line.product.track_serial:
                SerialNumberService.transition(
                    company=transfer.company, product=line.product, warehouse=transfer.from_warehouse,
                    numbers=line.serial_numbers, quantity=line.quantity,
                    source=SerialNumber.Status.AVAILABLE, target=SerialNumber.Status.AVAILABLE, user=user,
                )
                SerialNumber.objects.filter(
                    company=transfer.company, product=line.product,
                    serial_number__in=line.serial_numbers,
                ).update(warehouse=transfer.to_warehouse, updated_by=user)
            cost = InventoryValuationService.unit_cost(
                transfer.company, line.product,
                warehouse=transfer.from_warehouse, batch=line.batch,
            )
            out_move = InventoryService.post_movement(
                company=transfer.company, warehouse=transfer.from_warehouse,
                product=line.product, batch=line.batch, movement_type=MovementType.TRANSFER_OUT,
                quantity=line.quantity, unit_cost=cost,
                reference_type="stock_transfer", reference_id=transfer.pk, user=user,
            )
            InventoryService.post_movement(
                company=transfer.company, warehouse=transfer.to_warehouse,
                product=line.product, batch=line.batch, movement_type=MovementType.TRANSFER_IN,
                quantity=line.quantity, unit_cost=out_move.unit_cost or cost,
                reference_type="stock_transfer", reference_id=transfer.pk, user=user,
            )
        if not transfer.number:
            from core.services.document_numbers import DocumentNumberService
            transfer.number = DocumentNumberService.next_number(
                transfer.company, "STOCK_TRANSFER"
            )
        transfer.status = StockTransfer.Status.COMPLETED
        transfer.completed_at = timezone.now()
        transfer.updated_by = user
        transfer.save(update_fields=["number", "status", "completed_at", "updated_by"])
        return transfer

    @staticmethod
    @transaction.atomic
    def cancel(transfer: StockTransfer, user=None):
        transfer = StockTransfer.objects.select_for_update().get(pk=transfer.pk)
        if transfer.status == StockTransfer.Status.CANCELLED:
            raise BusinessRuleError("Transfer is already cancelled.")
        if transfer.status == StockTransfer.Status.COMPLETED:
            used_out_ids: set[int] = set()
            used_in_ids: set[int] = set()
            for line in transfer.lines.select_related("product", "batch"):
                if line.product.track_serial:
                    SerialNumberService.transition(
                        company=transfer.company, product=line.product, warehouse=transfer.to_warehouse,
                        numbers=line.serial_numbers, quantity=line.quantity,
                        source=SerialNumber.Status.AVAILABLE, target=SerialNumber.Status.AVAILABLE, user=user,
                    )
                    SerialNumber.objects.filter(
                        company=transfer.company, product=line.product,
                        serial_number__in=line.serial_numbers,
                    ).update(warehouse=transfer.from_warehouse, updated_by=user)
                # Match movements 1:1 — do not reuse the same TRANSFER_OUT/IN for duplicate product+batch lines.
                out_move = (
                    StockMovement.objects.filter(
                        company=transfer.company,
                        warehouse=transfer.from_warehouse,
                        product=line.product,
                        batch=line.batch,
                        movement_type=MovementType.TRANSFER_OUT,
                        reference_type="stock_transfer",
                        reference_id=str(transfer.pk),
                    )
                    .exclude(id__in=used_out_ids)
                    .order_by("id")
                    .first()
                )
                in_move = (
                    StockMovement.objects.filter(
                        company=transfer.company,
                        warehouse=transfer.to_warehouse,
                        product=line.product,
                        batch=line.batch,
                        movement_type=MovementType.TRANSFER_IN,
                        reference_type="stock_transfer",
                        reference_id=str(transfer.pk),
                    )
                    .exclude(id__in=used_in_ids)
                    .order_by("id")
                    .first()
                )
                if out_move is None or in_move is None:
                    raise BusinessRuleError(
                        "Cannot cancel transfer: expected stock movements are missing. "
                        "Do not invent unbatched restore layers."
                    )
                used_out_ids.add(out_move.id)
                used_in_ids.add(in_move.id)
                inbound = InventoryService.post_movement(
                    company=transfer.company, warehouse=transfer.from_warehouse,
                    product=line.product, batch=line.batch, movement_type=MovementType.ADJUSTMENT,
                    quantity=line.quantity, unit_cost=out_move.unit_cost if out_move else None,
                    reference_type="stock_transfer_cancel", reference_id=transfer.pk, user=user,
                    reason=f"Cancellation of transfer {transfer.number or transfer.pk}",
                )
                if out_move is not None:
                    InventoryService.restore_fifo_peels(out_move, inbound)
                InventoryService.post_movement(
                    company=transfer.company, warehouse=transfer.to_warehouse,
                    product=line.product, batch=line.batch, movement_type=MovementType.ADJUSTMENT,
                    quantity=-line.quantity, unit_cost=in_move.unit_cost if in_move else None,
                    reference_type="stock_transfer_cancel", reference_id=transfer.pk, user=user,
                    reason=f"Cancellation of transfer {transfer.number or transfer.pk}",
                )
                if in_move is not None:
                    InventoryService.retire_source_layers(in_move, abs(Decimal(str(in_move.quantity))))
        transfer.status = StockTransfer.Status.CANCELLED
        transfer.cancelled_at = timezone.now()
        transfer.updated_by = user
        transfer.save(update_fields=["status", "cancelled_at", "updated_by"])
        return transfer


class InventoryValuationService:
    """Replay-only inventory valuation; historical movements remain immutable.

    Honesty: WAVG is the default. FIFO peels perpetual cost layers when
    company.inventory_valuation_method is FIFO (see _apply_cost_layers).
    """

    @staticmethod
    def valuation(company, *, as_of=None, method=None, warehouse=None, product=None):
        from core.exceptions import BusinessRuleError

        method = method or company.inventory_valuation_method
        # Wave 16B: FIFO uses perpetual layers in post_movement; valuation replay
        # still supports FIFO layer walk for reports.
        if method not in ("WAVG", "FIFO"):
            raise BusinessRuleError(
                f"Unsupported inventory valuation method '{method}'. Use WAVG or FIFO."
            )
        movements = StockMovement.objects.filter(company=company).select_related("product", "batch", "warehouse")
        if as_of:
            movements = movements.filter(created_at__date__lte=as_of)
        if warehouse:
            movements = movements.filter(warehouse=warehouse)
        if product:
            movements = movements.filter(product=product)
        movements = movements.order_by("created_at", "id")
        state = {}
        zero_cost_transfer_in = set()
        for move in movements:
            key = (move.warehouse_id, move.product_id, move.batch_id)
            entry = state.setdefault(
                key,
                {
                    "warehouse": move.warehouse_id,
                    "warehouse_name": getattr(move.warehouse, "name", None),
                    "product": move.product_id,
                    "product_name": move.product.name if move.product_id else None,
                    "batch": move.batch_id,
                    "qty": Decimal("0"),
                    "value": Decimal("0"),
                    "layers": [],
                },
            )
            qty = Decimal(move.quantity)
            if qty > 0:
                cost = Decimal(move.unit_cost or "0")
                entry["qty"] += qty
                entry["value"] += qty * cost
                entry["layers"].append([qty, cost])
                if move.movement_type == MovementType.TRANSFER_IN and cost == 0:
                    zero_cost_transfer_in.add(key)
            elif qty < 0:
                issue = -qty
                if method == "FIFO":
                    cost = Decimal("0")
                    remaining = issue
                    for layer in entry["layers"]:
                        take = min(remaining, layer[0])
                        cost += take * layer[1]
                        layer[0] -= take
                        remaining -= take
                        if remaining == 0:
                            break
                    entry["value"] -= cost
                    entry["layers"] = [l for l in entry["layers"] if l[0] > 0]
                else:
                    average = entry["value"] / entry["qty"] if entry["qty"] else Decimal("0")
                    entry["value"] -= issue * average
                entry["qty"] -= issue
        # Legacy transfers posted unit_cost 0 on TRANSFER_IN. Report remaining
        # dest qty at sibling-warehouse WAVG so stock value is not silently 0.
        if zero_cost_transfer_in:
            need = [
                (key, row)
                for key, row in state.items()
                if key in zero_cost_transfer_in and row["qty"] > 0 and row["value"] == 0
            ]
            if need and warehouse is not None:
                full = InventoryValuationService.valuation(
                    company, as_of=as_of, method=method, warehouse=None, product=product,
                )
                full_by_key = {
                    (row["warehouse"], row["product"], row["batch"]): row for row in full
                }
                for key, row in need:
                    healed = full_by_key.get(key)
                    if healed is not None:
                        row["value"] = healed["value"]
            elif need:
                by_product = {}
                for key, row in state.items():
                    by_product.setdefault(row["product"], []).append((key, row))
                for items in by_product.values():
                    sibling_qty = sum(
                        (r["qty"] for k, r in items if r["qty"] > 0 and r["value"] > 0),
                        Decimal("0"),
                    )
                    sibling_val = sum(
                        (r["value"] for k, r in items if r["qty"] > 0 and r["value"] > 0),
                        Decimal("0"),
                    )
                    if sibling_qty <= 0:
                        continue
                    avg = sibling_val / sibling_qty
                    for key, row in items:
                        if key in zero_cost_transfer_in and row["qty"] > 0 and row["value"] == 0:
                            row["value"] = row["qty"] * avg
        return [
            {**row, "unit_cost": (row["value"] / row["qty"] if row["qty"] else Decimal("0"))}
            for row in state.values()
        ]

    @classmethod
    def unit_cost(cls, company, product, warehouse=None, batch=None):
        # R2-022 (perf follow-up, NOT done here): this replays every StockMovement
        # for the product via valuation(). A materialised running-cost cache is
        # the fix, but it must be threaded through every post_movement path
        # (issue / receive / adjust / cancel / transfer / FIFO peel) with its own
        # test pass — cramming it risks a silent inventory-valuation bug. Left as
        # a dedicated follow-up; the system is correct, just O(movements) here.
        rows = cls.valuation(company, warehouse=warehouse, product=product)
        if batch is not None:
            batch_id = getattr(batch, "pk", batch)
            matched = [row for row in rows if row.get("batch") == batch_id]
            if matched:
                return matched[0]["unit_cost"]
        if not rows:
            return Decimal("0")
        # R2-024: qty-weighted average across all rows that hold stock — not
        # rows[0], which (in dict order) can be a zeroed-out / qty-0 batch row
        # and would report ₹0 while other rows hold real stock at real cost.
        pos = [r for r in rows if Decimal(str(r.get("qty") or 0)) > 0]
        if pos:
            total_qty = sum((Decimal(str(r["qty"])) for r in pos), Decimal("0"))
            total_val = sum((Decimal(str(r.get("value") or 0)) for r in pos), Decimal("0"))
            if total_qty > 0:
                return total_val / total_qty
        for r in rows:
            if Decimal(str(r.get("unit_cost") or 0)) > 0:
                return r["unit_cost"]
        return rows[0]["unit_cost"]

    @staticmethod
    def fefo_batches(company, product, warehouse=None):
        from django.db.models import F

        from .item_stock import business_date, lot_is_expired

        qs = BatchLot.objects.filter(company=company, product=product, stock_balances__on_hand__gt=0)
        if warehouse:
            qs = qs.filter(stock_balances__warehouse=warehouse)
        if getattr(company, "block_expired_stock", True):
            qs = qs.exclude(expiry_date__lt=business_date(company))
        return qs.order_by(
            F("expiry_date").asc(nulls_last=True),
            F("manufacturing_date").asc(nulls_last=True),
            "batch_no",
            "id",
        ).distinct()
