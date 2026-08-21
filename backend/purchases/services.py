"""Purchase Service — invoices, returns, status transitions (E3)."""

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.events import emit
from core.exceptions import BusinessRuleError
from core.services.billing import apply_rcm_memo_after_tax, compute_document_totals
from core.services.place_of_supply import assert_place_of_supply_for_gst, party_intra_state
from core.services.document_numbers import DocumentNumberService, resolve_series_gstin
from inventory.models import BatchLot, MovementType
from inventory.services import InventoryService, SerialNumberService
from masters.models import Product

from .models import PurchaseInvoice, PurchaseItem, PurchaseReturn, PurchaseReturnItem


def _validate_lines(items_data, company):
    from core.validators import ALLOWED_GST_RATES

    allowed_gst = {Decimal(r) for r in ALLOWED_GST_RATES}
    if not items_data:
        raise BusinessRuleError("At least one line item is required.")
    for line in items_data:
        if Decimal(line["quantity"]) <= 0:
            raise BusinessRuleError("Quantity on each line must be greater than zero.")
        unit_price = Decimal(str(line.get("unit_price", line["product"].purchase_price)))
        if unit_price < 0:
            raise BusinessRuleError("Unit price cannot be negative.")
        discount_percent = Decimal(str(line.get("discount_percent", 0) or 0))
        if discount_percent < 0 or discount_percent > 100:
            raise BusinessRuleError("Discount percent must be between 0 and 100.")
        gst_rate = Decimal(str(line.get("gst_rate", line["product"].gst_rate)))
        if gst_rate not in allowed_gst:
            raise BusinessRuleError(
                f"Invalid GST rate {gst_rate}. Allowed: {', '.join(ALLOWED_GST_RATES)}%."
            )
        if line["product"].company_id != company.id:
            raise BusinessRuleError("Invalid product reference.")


def _build_purchase_items(invoice, items_data):
    from core.services.uqc import snapshot_unit_fields

    product_ids = [line["product"].pk for line in items_data]
    products = {
        p.pk: p
        for p in Product.objects.filter(pk__in=product_ids).select_related("unit")
    }
    items = []
    for line in items_data:
        product = products.get(line["product"].pk, line["product"])
        snap = snapshot_unit_fields(product, line)
        inclusive = line.get("unit_price_inclusive")
        items.append(PurchaseItem(
            invoice=invoice,
            company_id=invoice.company_id,
            product=product,
            batch=line.get("batch"),
            description=line.get("description") or product.name,
            quantity=line["quantity"],
            unit_price=line.get("unit_price", product.purchase_price),
            discount_percent=line.get("discount_percent", Decimal("0")),
            gst_rate=line.get("gst_rate", product.gst_rate),
            cess_rate=line.get("cess_rate", Decimal("0")),
            cess_amount=line.get("cess_amount", Decimal("0")),
            hsn_code=snap["hsn_code"],
            mrp=line.get("mrp", product.mrp or Decimal("0")),
            unit_name=snap["unit_name"],
            uqc_code=snap["uqc_code"],
            unit_price_inclusive=(
                Decimal(str(inclusive)) if inclusive is not None else None
            ),
            batch_no=line.get("batch_no") or "",
            exp_date=line.get("exp_date"),
            mfg_date=line.get("mfg_date"),
            serial_numbers=line.get("serial_numbers") or [],
        ))
    return items


class PurchaseService:
    # ---------------- Purchase invoice ----------------

    @staticmethod
    def _returned_quantities(invoice, exclude_return=None):
        qs = PurchaseReturnItem.objects.filter(
            purchase_return__purchase_invoice=invoice,
            purchase_return__status=PurchaseReturn.Status.COMPLETED,
        )
        if exclude_return is not None:
            qs = qs.exclude(purchase_return=exclude_return)
        return {
            row["product"]: row["total"]
            for row in qs.values("product").annotate(total=Sum("quantity"))
        }

    @staticmethod
    @transaction.atomic
    def set_items(invoice: PurchaseInvoice, items_data, user):
        if invoice.status == PurchaseInvoice.Status.CANCELLED:
            raise BusinessRuleError("Cancelled purchase cannot be line-edited.")
        if invoice.status not in (PurchaseInvoice.Status.DRAFT, PurchaseInvoice.Status.COMPLETED):
            raise BusinessRuleError(f"Cannot edit purchase in status {invoice.status}.")

        old_qty = defaultdict(Decimal)
        adjust_stock = invoice.status == PurchaseInvoice.Status.COMPLETED
        # BUG-213: same pre-edit snapshot as SalesService.set_items.
        old_totals = {
            "grand_total": str(invoice.grand_total), "taxable_total": str(invoice.taxable_total),
            "tax_total": str(invoice.cgst_total + invoice.sgst_total + invoice.igst_total),
        } if adjust_stock else None
        if adjust_stock:
            for item in invoice.items.select_related("product"):
                old_qty[item.product_id] += item.quantity

        _validate_lines(items_data, invoice.company)
        from masters.models import Customer as _Customer

        if getattr(invoice.supplier, "taxpayer_type", None) == _Customer.TaxpayerType.COMPOSITION:
            for line in items_data:
                rate = Decimal(str(line.get("gst_rate", line["product"].gst_rate) or 0))
                if rate != 0:
                    raise BusinessRuleError(
                        "Composition suppliers cannot have non-zero GST on purchase lines. "
                        "Set gst_rate to 0 on all lines."
                    )
            if invoice.itc_eligibility != PurchaseInvoice.ItcEligibility.INELIGIBLE:
                invoice.itc_eligibility = PurchaseInvoice.ItcEligibility.INELIGIBLE

        new_qty_preview = defaultdict(Decimal)
        for line in items_data:
            new_qty_preview[line["product"].pk] += Decimal(line["quantity"])

        if adjust_stock:
            already = PurchaseService._returned_quantities(invoice)
            for product_id, returned_qty in already.items():
                if new_qty_preview.get(product_id, Decimal("0")) < returned_qty:
                    raise BusinessRuleError(
                        f"Quantity cannot be below already-returned quantity {returned_qty}."
                    )
            # Reducing purchased qty removes stock — enforce negative-stock policy.
            for product_id in set(old_qty) | set(new_qty_preview):
                delta = new_qty_preview.get(product_id, Decimal("0")) - old_qty.get(
                    product_id, Decimal("0")
                )
                if delta < 0:
                    product = next(
                        (line["product"] for line in items_data if line["product"].pk == product_id),
                        None,
                    ) or Product.objects.get(pk=product_id)
                    InventoryService.check_negative_stock(invoice.company, product, -delta)

        invoice.items.all().delete()
        items = _build_purchase_items(invoice, items_data)
        compute_document_totals(
            invoice, items,
            tax_enabled=invoice.purchase_type == PurchaseInvoice.PurchaseType.GST,
            intra_state=party_intra_state(
                invoice.company,
                invoice.supplier.state,
                invoice.supplier.gstin or "",
                seller_state=(getattr(invoice.company_gstin, "state", None) or ""),
                seller_gstin=(getattr(invoice.company_gstin, "gstin", None) or ""),
            ),
            additional_charges=invoice.additional_charges,
            invoice_discount=invoice.invoice_discount,
            auto_round_off=invoice.auto_round_off,
            invoice_discount_mode=getattr(invoice, "invoice_discount_mode", None),
        )
        if invoice.is_reverse_charge and invoice.purchase_type == PurchaseInvoice.PurchaseType.GST:
            apply_rcm_memo_after_tax(invoice, items)
        else:
            # BB-000362: RCM was turned off (or invoice is no longer GST) — clear
            # any stale memo from a prior save, else GL/GSTR would still see it.
            invoice.rcm_taxable = Decimal("0.00")
            invoice.rcm_cgst = Decimal("0.00")
            invoice.rcm_sgst = Decimal("0.00")
            invoice.rcm_igst = Decimal("0.00")
            invoice.rcm_cess = Decimal("0.00")
        PurchaseItem.objects.bulk_create(items)

        if adjust_stock:
            new_qty = defaultdict(Decimal)
            product_by_id = {}
            for item in items:
                new_qty[item.product_id] += item.quantity
                product_by_id[item.product_id] = item.product
            for product_id in set(old_qty) | set(new_qty):
                delta = new_qty[product_id] - old_qty[product_id]
                if delta == 0:
                    continue
                product = product_by_id.get(product_id) or Product.objects.get(pk=product_id)
                if delta > 0:
                    InventoryService.post_movement(
                        company=invoice.company,
                        warehouse=invoice.warehouse,
                        product=product,
                        movement_type=MovementType.PURCHASE,
                        quantity=delta,
                        unit_cost=next(
                            (i.unit_price for i in items if i.product_id == product_id),
                            product.purchase_price,
                        ),
                        reference_type="purchase_invoice",
                        reference_id=invoice.pk,
                        user=user,
                    )
                else:
                    InventoryService.post_movement(
                        company=invoice.company,
                        warehouse=invoice.warehouse,
                        product=product,
                        movement_type=MovementType.ADJUSTMENT,
                        quantity=delta,
                        reference_type="purchase_invoice_edit",
                        reference_id=invoice.pk,
                        reason=f"Edit of {invoice.number or invoice.pk}",
                        user=user,
                    )
            emit("purchase_invoice.edited", invoice=invoice, user=user, old_totals=old_totals)

        invoice.updated_by = user
        invoice.save()
        return invoice

    @staticmethod
    def restamp_fifo_layers_for_price_amend(invoice):
        """H9 price-only: update remaining FIFO layers; refuse if any qty peeled."""
        from inventory.models import InventoryCostLayer, StockMovement

        if getattr(invoice.company, "inventory_valuation_method", "WAVG") != "FIFO":
            return
        price_by_product = {item.product_id: Decimal(str(item.unit_price or 0)) for item in invoice.items.all()}
        moves = StockMovement.objects.filter(
            company=invoice.company,
            movement_type=MovementType.PURCHASE,
            reference_type="purchase_invoice",
            reference_id=str(invoice.pk),
        )
        for move in moves:
            new_cost = price_by_product.get(move.product_id)
            if new_cost is None:
                continue
            original_qty = abs(Decimal(str(move.quantity or 0)))
            layers = list(InventoryCostLayer.objects.select_for_update().filter(source_movement=move))
            for layer in layers:
                if original_qty and layer.qty_remaining < original_qty:
                    raise BusinessRuleError(
                        "Cannot price-amend a purchase whose FIFO layers have been issued. "
                        "Use a debit/credit note or purchase return."
                    )
                layer.unit_cost = new_cost
                layer.save(update_fields=["unit_cost", "updated_at"])
            StockMovement.objects.filter(pk=move.pk).update(unit_cost=new_cost)

    @staticmethod
    def _assert_composition_supplier_gst(invoice, items):
        from masters.models import Customer

        supplier = invoice.supplier
        if getattr(supplier, "taxpayer_type", None) != Customer.TaxpayerType.COMPOSITION:
            return
        for item in items:
            if Decimal(str(item.gst_rate or 0)) != 0:
                raise BusinessRuleError(
                    "Composition suppliers cannot have non-zero GST on purchase lines. "
                    "Set gst_rate to 0 on all lines."
                )
        if invoice.itc_eligibility != PurchaseInvoice.ItcEligibility.INELIGIBLE:
            invoice.itc_eligibility = PurchaseInvoice.ItcEligibility.INELIGIBLE

    @staticmethod
    def _assert_duplicate_supplier_bill(invoice, *, confirm_duplicate_bill=False):
        bill_no = (invoice.supplier_bill_number or "").strip()
        if not bill_no:
            return
        qs = PurchaseInvoice.objects.filter(
            company=invoice.company,
            supplier=invoice.supplier,
            supplier_bill_number__iexact=bill_no,
        ).exclude(status=PurchaseInvoice.Status.CANCELLED)
        if invoice.pk:
            qs = qs.exclude(pk=invoice.pk)
        if qs.exists() and not confirm_duplicate_bill:
            raise BusinessRuleError(
                f"A purchase with supplier bill number '{bill_no}' already exists for this "
                "supplier. Pass confirm_duplicate_bill=true to proceed."
            )

    @staticmethod
    def _unregistered_rcm_gate(invoice, items, *, confirm_no_rcm=False, warnings=None):
        """PUR-03/PUR-08: unregistered / blank GSTIN without RCM needs confirm; GTA warn."""
        from masters.models import Customer

        warnings = warnings if warnings is not None else []
        supplier = invoice.supplier
        taxpayer = getattr(supplier, "taxpayer_type", "") or ""
        gstin = (supplier.gstin or "").strip()
        if invoice.is_reverse_charge:
            return warnings
        if invoice.purchase_type != PurchaseInvoice.PurchaseType.GST:
            return warnings

        is_unregistered = taxpayer == Customer.TaxpayerType.UNREGISTERED
        blank_gstin = not gstin
        if is_unregistered and not confirm_no_rcm:
            raise BusinessRuleError(
                "Supplier is unregistered and reverse charge is off. "
                "Enable is_reverse_charge, or pass confirm_no_rcm=true to proceed."
            )
        if blank_gstin and not is_unregistered:
            warnings.append(
                "Supplier has blank GSTIN and reverse charge is off — "
                "confirm whether RCM applies for this purchase."
            )
        # GTA-ish lines (SAC 9965/9967 or name/category containing GTA).
        if is_unregistered or blank_gstin:
            for item in items:
                hsn = (
                    getattr(item, "hsn_code", None)
                    or getattr(item.product, "hsn_code", "")
                    or ""
                ).strip()
                name = (item.product.name or "").casefold()
                cat = ""
                if getattr(item.product, "category_id", None) and item.product.category:
                    cat = (item.product.category.name or "").casefold()
                if hsn.startswith(("9965", "9967")) or "gta" in name or "gta" in cat:
                    warnings.append(
                        f"Line '{item.product.name}' looks like GTA/transport — "
                        "confirm whether reverse charge (Sec 9(3)) applies."
                    )
                    break
        return warnings

    @staticmethod
    @transaction.atomic
    def complete(invoice: PurchaseInvoice, user, *, confirm_no_rcm=False, confirm_duplicate_bill=False):
        """Atomic Complete: number + PURCHASE movements + event (E3.3)."""
        invoice = PurchaseInvoice.objects.select_for_update().get(pk=invoice.pk)
        if invoice.warehouse_id is None:
            invoice.warehouse = InventoryService.default_warehouse(invoice.company)
        if invoice.status != PurchaseInvoice.Status.DRAFT:
            raise BusinessRuleError(f"Cannot complete a purchase in status {invoice.status}.")
        items = list(invoice.items.select_related("product", "product__category"))
        if not items:
            raise BusinessRuleError("Cannot complete a purchase without line items.")

        tax_enabled = invoice.purchase_type == PurchaseInvoice.PurchaseType.GST
        from core.services.registration_gates import assert_may_issue_gst_tax_invoice

        assert_may_issue_gst_tax_invoice(invoice.company, tax_enabled=tax_enabled)

        assert_place_of_supply_for_gst(
            company=invoice.company,
            party_state=invoice.supplier.state or "",
            party_gstin=invoice.supplier.gstin or "",
            tax_enabled=tax_enabled,
        )

        # PUR-04: foreign / non-India supplier — do not silently treat as local GST.
        if tax_enabled:
            from core.services.billing import extract_state_code

            supplier = invoice.supplier
            state = (supplier.state or "").strip()
            gstin = (supplier.gstin or "").strip()
            tt = (getattr(supplier, "taxpayer_type", None) or "").strip().upper()
            foreign_tt = tt in ("EXPWP", "EXPWOP", "DEXP", "SEZWP", "SEZWOP")
            has_india_state = bool(extract_state_code(gstin) or extract_state_code(state))
            # Explicit non-Indian state text (unmappable) with no Indian GSTIN → import path.
            if foreign_tt or (state and not has_india_state and not gstin):
                raise BusinessRuleError(
                    "Foreign supplier / import-of-goods (Bill of Entry / customs IGST) "
                    "is not supported yet. Set a valid Indian state or GSTIN on the supplier, "
                    "or wait for import purchase support."
                )

        PurchaseService._assert_composition_supplier_gst(invoice, items)
        PurchaseService._assert_duplicate_supplier_bill(
            invoice, confirm_duplicate_bill=confirm_duplicate_bill
        )

        # RCM: ensure memo/payable even if draft was saved before RCM flag.
        if invoice.is_reverse_charge and invoice.purchase_type == PurchaseInvoice.PurchaseType.GST:
            if (invoice.rcm_taxable or 0) == 0 and (invoice.cgst_total or 0) + (invoice.sgst_total or 0) + (
                invoice.igst_total or 0
            ) > 0:
                apply_rcm_memo_after_tax(invoice, items)
            else:
                # Re-zero line taxes if header already memoized but lines still carry tax.
                for item in items:
                    if (item.cgst or 0) or (item.sgst or 0) or (item.igst or 0):
                        item.cgst = Decimal("0.00")
                        item.sgst = Decimal("0.00")
                        item.igst = Decimal("0.00")
                        item.line_total = Decimal(str(item.taxable_amount or 0))
                        item.save(update_fields=["cgst", "sgst", "igst", "line_total"])
        elif (invoice.rcm_taxable or 0) or (invoice.rcm_cgst or 0) or (invoice.rcm_sgst or 0) or (
            invoice.rcm_igst or 0
        ) or (invoice.rcm_cess or 0):
            # BB-000362: RCM flag was cleared (e.g. header PATCH) after an earlier
            # memoized save — stale rcm_* must not leak into GL/GSTR at Complete.
            invoice.rcm_taxable = Decimal("0.00")
            invoice.rcm_cgst = Decimal("0.00")
            invoice.rcm_sgst = Decimal("0.00")
            invoice.rcm_igst = Decimal("0.00")
            invoice.rcm_cess = Decimal("0.00")

        warnings = []
        if invoice.purchase_type == PurchaseInvoice.PurchaseType.GST:
            missing_hsn = [i for i in items if not (i.hsn_code or "").strip()]
            if missing_hsn:
                warnings.append(
                    f"{len(missing_hsn)} line(s) missing HSN — GSTR / ITC aids may fail."
                )
        warnings = PurchaseService._unregistered_rcm_gate(
            invoice, items, confirm_no_rcm=confirm_no_rcm, warnings=warnings
        )

        series_gstin = resolve_series_gstin(invoice.company, invoice.company_gstin)
        invoice.number = invoice.number or DocumentNumberService.next_number(
            invoice.company,
            "PURCHASE_INVOICE",
            gstin=series_gstin,
            on_date=invoice.invoice_date if series_gstin else None,
        )
        invoice.status = PurchaseInvoice.Status.COMPLETED
        invoice.completed_at = timezone.now()
        invoice.updated_by = user
        if (invoice.notes or "").strip() == "TALLY_OPENING" and not getattr(
            invoice, "is_opening_balance", False
        ):
            raise BusinessRuleError(
                "TALLY_OPENING notes are not accepted. Opening invoices must be imported via Tally adapter."
            )
        is_tally_opening = bool(getattr(invoice, "is_opening_balance", False))
        if invoice.company_gstin_id is None:
            from accounts.models import CompanyGstin

            primary = (
                CompanyGstin.objects.filter(company=invoice.company, is_primary=True, is_active=True)
                .order_by("-id")
                .first()
            )
            if primary is None:
                primary = (
                    CompanyGstin.objects.filter(company=invoice.company, is_active=True)
                    .order_by("-is_primary", "id")
                    .first()
                )
            if primary is not None:
                invoice.company_gstin = primary
        invoice.save()

        # BB-000337 / BB-000699: money Complete hard-blocks closed periods; no except-pass.
        if not is_tally_opening:
            from reporting.gst_periods import assert_period_allows_money_amend, mark_period_dirty_if_snapshotted

            assert_period_allows_money_amend(invoice.company, invoice.invoice_date)
            mark_period_dirty_if_snapshotted(invoice.company, invoice.invoice_date)

        for item in items:
            if item.product.track_batch and not item.batch_id:
                if not item.batch_no:
                    raise BusinessRuleError(f"A batch is required for tracked product '{item.product.name}'.")
                item.batch, _ = BatchLot.objects.get_or_create(
                    company=invoice.company, product=item.product, batch_no=item.batch_no,
                    defaults={"expiry_date": item.exp_date, "manufacturing_date": item.mfg_date, "created_by": user, "updated_by": user},
                )
                item.save(update_fields=["batch"])
            if item.product.track_serial:
                SerialNumberService.receive(
                    company=invoice.company, product=item.product, warehouse=invoice.warehouse,
                    numbers=item.serial_numbers, quantity=item.quantity, user=user,
                )
            if not is_tally_opening:
                InventoryService.post_movement(
                    company=invoice.company,
                    warehouse=invoice.warehouse,
                    product=item.product,
                    batch=item.batch,
                    movement_type=MovementType.PURCHASE,
                    quantity=item.quantity,
                    unit_cost=item.unit_price,
                    reference_type="purchase_invoice",
                    reference_id=invoice.pk,
                    user=user,
                )
        if not is_tally_opening:
            if invoice.company.accounting_enabled:
                from accounting.services import PostingService

                PostingService.post_purchase(invoice, user)
            emit("document.completed", document=invoice, user=user, event="purchase_invoice.completed")
            from core.models import StatutoryDocumentEvent, log_statutory_event

            log_statutory_event(
                company=invoice.company,
                entity_type="purchase_invoice",
                entity_id=invoice.pk,
                event_type=StatutoryDocumentEvent.EventType.COMPLETE,
                payload={"number": invoice.number, "grand_total": str(invoice.grand_total)},
                user=user,
            )
        else:
            # BB-000381: opening AP vs equity when books enabled.
            if invoice.company.accounting_enabled:
                from accounting.services import PostingService

                PostingService.post_opening_purchase_invoice(invoice, user)
        return invoice, warnings

    @staticmethod
    @transaction.atomic
    def cancel(invoice: PurchaseInvoice, user):
        invoice = PurchaseInvoice.objects.select_for_update().get(pk=invoice.pk)
        from reporting.gst_periods import assert_period_allows_money_amend

        assert_period_allows_money_amend(invoice.company, invoice.invoice_date, allow_soft_closed=True)
        if invoice.status == PurchaseInvoice.Status.CANCELLED:
            raise BusinessRuleError("Purchase is already cancelled.")
        if invoice.returns.filter(status=PurchaseReturn.Status.COMPLETED).exists():
            raise BusinessRuleError("Cannot cancel a purchase with completed returns.")
        if invoice.allocations.filter(reversed_at__isnull=True).exists():
            # BUG-722 (purchase side) — same reasoning as sales invoices.
            raise BusinessRuleError(
                "Cannot cancel a purchase with payment allocations against it. "
                "Remove the allocation(s) first."
            )

        if invoice.status == PurchaseInvoice.Status.COMPLETED:
            if invoice.company.accounting_enabled:
                from accounting.models import JournalEntry
                from accounting.services import PostingService

                for entry in JournalEntry.objects.filter(
                    company=invoice.company, source_type="PURCHASE_INVOICE", source_id=invoice.id,
                    status=JournalEntry.Status.POSTED,
                ):
                    PostingService.reverse(entry, user, invoice.invoice_date)
            # Reverse stock via ADJUSTMENT — movements stay append-only (§5.3).
            # BB-000718: retire the original PURCHASE layers (do not peel FIFO-oldest).
            from inventory.models import SerialNumber, StockMovement
            from inventory.services import SerialNumberService

            for move in StockMovement.objects.filter(
                company=invoice.company,
                movement_type=MovementType.PURCHASE,
                reference_type="purchase_invoice",
                reference_id=str(invoice.pk),
            ):
                InventoryService.post_movement(
                    company=invoice.company,
                    warehouse=move.warehouse or invoice.warehouse,
                    product=move.product,
                    batch=move.batch,
                    movement_type=MovementType.ADJUSTMENT,
                    quantity=-abs(Decimal(str(move.quantity))),
                    unit_cost=move.unit_cost,
                    reference_type="purchase_invoice_cancel",
                    reference_id=invoice.pk,
                    reason=f"Cancellation of {invoice.number}",
                    user=user,
                )
                InventoryService.retire_source_layers(move, abs(Decimal(str(move.quantity))))
            for item in invoice.items.select_related("product"):
                if item.product.track_serial and item.serial_numbers:
                    SerialNumberService.transition(
                        company=invoice.company,
                        product=item.product,
                        warehouse=invoice.warehouse,
                        numbers=item.serial_numbers,
                        quantity=item.quantity,
                        source=SerialNumber.Status.AVAILABLE,
                        target=SerialNumber.Status.SCRAPPED,
                        user=user,
                    )
        invoice.status = PurchaseInvoice.Status.CANCELLED
        invoice.cancelled_at = timezone.now()
        invoice.updated_by = user
        invoice.save()
        emit("document.cancelled", document=invoice, user=user, event="purchase_invoice.cancelled")
        from core.models import StatutoryDocumentEvent, log_statutory_event

        log_statutory_event(
            company=invoice.company,
            entity_type="purchase_invoice",
            entity_id=invoice.pk,
            event_type=StatutoryDocumentEvent.EventType.CANCEL,
            payload={"number": invoice.number},
            user=user,
        )
        return invoice

    # ---------------- Purchase return ----------------

    @staticmethod
    @transaction.atomic
    def set_return_items(purchase_return: PurchaseReturn, items_data, user):
        if purchase_return.status != PurchaseReturn.Status.DRAFT:
            raise BusinessRuleError("Completed return cannot be edited.")
        _validate_lines(items_data, purchase_return.company)
        purchase_return.items.all().delete()
        items = []
        for line in items_data:
            product = line["product"]
            serial_numbers = line.get("serial_numbers") or []
            # BB-000722: require serials when product is track_serial.
            if product.track_serial:
                numbers = [str(n).strip() for n in serial_numbers if str(n).strip()]
                if len(numbers) != int(Decimal(str(line["quantity"]))):
                    raise BusinessRuleError(
                        f"Exactly {line['quantity']} serial number(s) are required for "
                        f"tracked product '{product.name}'."
                    )
            items.append(PurchaseReturnItem(
                purchase_return=purchase_return,
                company_id=purchase_return.company_id,
                product=product,
                description=line.get("description") or product.name,
                quantity=line["quantity"],
                unit_price=line.get("unit_price", product.purchase_price),
                discount_percent=line.get("discount_percent", Decimal("0")),
                gst_rate=line.get("gst_rate", product.gst_rate),
                cess_rate=line.get("cess_rate", Decimal("0")),
                cess_amount=line.get("cess_amount", Decimal("0")),
                batch=line.get("batch"),
                serial_numbers=serial_numbers,
            ))
        source = purchase_return.purchase_invoice
        tax_enabled = source.purchase_type == PurchaseInvoice.PurchaseType.GST if source else True
        compute_document_totals(
            purchase_return, items,
            tax_enabled=tax_enabled,
            intra_state=party_intra_state(
                purchase_return.company,
                purchase_return.supplier.state,
                purchase_return.supplier.gstin or "",
            ),
        )
        PurchaseReturnItem.objects.bulk_create(items)
        purchase_return.updated_by = user
        purchase_return.save()
        return purchase_return

    @staticmethod
    @transaction.atomic
    def complete_return(purchase_return: PurchaseReturn, user):
        purchase_return = PurchaseReturn.objects.select_for_update().get(pk=purchase_return.pk)
        from reporting.gst_periods import assert_period_allows_money_amend

        assert_period_allows_money_amend(purchase_return.company, purchase_return.return_date)
        if purchase_return.status != PurchaseReturn.Status.DRAFT:
            raise BusinessRuleError(f"Cannot complete a return in status {purchase_return.status}.")
        items = list(purchase_return.items.select_related("product"))
        if not items:
            raise BusinessRuleError("Cannot complete a return without line items.")
        invoice = purchase_return.purchase_invoice
        # BB-000020: GST-registered companies cannot orphan returns (AP/GSTR distortion).
        if purchase_return.company.is_gst_registered and invoice is None:
            raise BusinessRuleError(
                "GST-registered companies require a linked purchase invoice on purchase returns."
            )
        if purchase_return.company.accounting_enabled and invoice is None:
            raise BusinessRuleError(
                "Accounting-enabled companies require a linked purchase invoice on purchase returns."
            )
        if invoice and invoice.status != PurchaseInvoice.Status.COMPLETED:
            raise BusinessRuleError("Purchase return must reference a completed purchase invoice.")

        if invoice:
            purchased = {
                row["product"]: row["total"]
                for row in invoice.items.values("product").annotate(total=Sum("quantity"))
            }
            already = PurchaseService._returned_quantities(invoice)
            requested = defaultdict(Decimal)
            for item in items:
                requested[item.product_id] += item.quantity
            for product_id, qty in requested.items():
                remaining = purchased.get(product_id, Decimal("0")) - already.get(
                    product_id, Decimal("0")
                )
                if qty > remaining:
                    raise BusinessRuleError(
                        f"Return quantity {qty} exceeds remaining returnable quantity {remaining}."
                    )

        purchase_return.number = DocumentNumberService.next_number(
            purchase_return.company,
            "PURCHASE_RETURN",
            gstin=resolve_series_gstin(
                purchase_return.company,
                getattr(invoice, "company_gstin", None) if invoice else None,
            ),
            on_date=purchase_return.return_date,
        )
        purchase_return.status = PurchaseReturn.Status.COMPLETED
        purchase_return.completed_at = timezone.now()
        purchase_return.updated_by = user
        purchase_return.save()

        from inventory.models import SerialNumber, StockMovement as CostMove
        from inventory.services import SerialNumberService

        def _return_unit_cost(product, fallback_price):
            if invoice is None:
                return fallback_price
            move = (
                CostMove.objects.filter(
                    company=purchase_return.company,
                    movement_type=MovementType.PURCHASE,
                    reference_type="purchase_invoice",
                    reference_id=str(invoice.pk),
                    product=product,
                )
                .order_by("id")
                .first()
            )
            if move is not None and move.unit_cost is not None:
                return move.unit_cost
            return fallback_price

        for item in items:
            if item.product.track_serial:
                if not item.serial_numbers:
                    raise BusinessRuleError(
                        f"Serial numbers are required to complete return of '{item.product.name}'."
                    )
                SerialNumberService.transition(
                    company=purchase_return.company,
                    product=item.product,
                    warehouse=invoice.warehouse if invoice else None,
                    numbers=item.serial_numbers,
                    quantity=item.quantity,
                    source=SerialNumber.Status.AVAILABLE,
                    target=SerialNumber.Status.SCRAPPED,
                    user=user,
                )
            batch = getattr(item, "batch", None)
            # BB-000383: if track_batch and no batch on line, take from purchase PURCHASE movements FEFO/LIFO replay.
            if item.product.track_batch and batch is None and invoice is not None:
                from inventory.models import StockMovement

                purchase_moves = list(
                    StockMovement.objects.filter(
                        company=purchase_return.company,
                        movement_type=MovementType.PURCHASE,
                        reference_type="purchase_invoice",
                        reference_id=str(invoice.pk),
                        product=item.product,
                    ).order_by("-id")
                )
                remaining = item.quantity
                for move in purchase_moves:
                    if remaining <= 0:
                        break
                    take = min(remaining, abs(Decimal(str(move.quantity))))
                    InventoryService.post_movement(
                        company=purchase_return.company,
                        warehouse=invoice.warehouse if invoice else None,
                        product=item.product,
                        batch=move.batch,
                        movement_type=MovementType.PURCHASE_RETURN,
                        quantity=take,
                        unit_cost=move.unit_cost if move.unit_cost is not None else _return_unit_cost(item.product, item.unit_price),
                        reference_type="purchase_return",
                        reference_id=purchase_return.pk,
                        user=user,
                    )
                    remaining -= take
                if remaining > 0:
                    raise BusinessRuleError(
                        f"Cannot return {item.quantity} of batched '{item.product.name}' without lot coverage."
                    )
                continue
            InventoryService.post_movement(
                company=purchase_return.company,
                warehouse=invoice.warehouse if invoice else None,
                product=item.product,
                batch=batch,
                movement_type=MovementType.PURCHASE_RETURN,
                quantity=item.quantity,
                unit_cost=_return_unit_cost(item.product, item.unit_price),
                reference_type="purchase_return",
                reference_id=purchase_return.pk,
                user=user,
            )

        # BUG-212: mark the invoice Returned once every purchased quantity
        # has come back, mirroring SalesService.complete_return.
        if invoice:
            now_returned = PurchaseService._returned_quantities(invoice)
            fully_returned = all(
                now_returned.get(pid, Decimal("0")) >= qty for pid, qty in purchased.items()
            )
            if fully_returned and invoice.status != PurchaseInvoice.Status.RETURNED:
                invoice.status = PurchaseInvoice.Status.RETURNED
                invoice.save(update_fields=["status"])

        # BB-000263: auto purchase CN for AP relief (mirrors sales return).
        from .models import PurchaseCreditNote, PurchaseNoteReason
        from .notes_services import PurchaseNotesService

        existing_linked = PurchaseCreditNote.objects.filter(
            purchase_return=purchase_return,
            status=PurchaseCreditNote.Status.COMPLETED,
        ).exists()
        if not existing_linked and invoice is not None:
            note = PurchaseCreditNote.objects.create(
                company=purchase_return.company,
                supplier=purchase_return.supplier,
                purchase_invoice=invoice,
                purchase_return=purchase_return,
                note_date=purchase_return.return_date,
                reason=PurchaseNoteReason.PURCHASE_RETURN,
                reason_detail=f"Auto from purchase return {purchase_return.number}",
                invoice_discount=invoice.invoice_discount,
                invoice_discount_mode=invoice.invoice_discount_mode,
                auto_round_off=invoice.auto_round_off if fully_returned else False,
                created_by=user,
                updated_by=user,
            )
            inv_taxable = Decimal(str(invoice.taxable_total or 0))
            ret_taxable = sum((Decimal(str(i.taxable_amount or 0)) for i in items), Decimal("0"))
            ratio = Decimal("1")
            if inv_taxable > 0 and not fully_returned:
                ratio = min(Decimal("1"), ret_taxable / inv_taxable)
            note.invoice_discount = (Decimal(str(invoice.invoice_discount or 0)) * ratio).quantize(Decimal("0.01"))
            note.additional_charges = (Decimal(str(invoice.additional_charges or 0)) * ratio).quantize(Decimal("0.01"))
            # BB-000364: map each returned line back to its originating invoice
            # line (by product) so the auto CN carries the invoiced HSN/lineage
            # instead of the product master's current (possibly since-changed) HSN.
            invoice_items_by_product = {}
            for inv_item in invoice.items.all():
                invoice_items_by_product.setdefault(inv_item.product_id, inv_item)
            items_data = []
            for item in items:
                source_item = invoice_items_by_product.get(item.product_id)
                items_data.append({
                    "product": item.product,
                    "description": getattr(item, "description", "") or "",
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "discount_percent": item.discount_percent,
                    "gst_rate": item.gst_rate,
                    "cess_rate": getattr(item, "cess_rate", None)
                    if getattr(item, "cess_rate", None) is not None
                    else getattr(source_item, "cess_rate", Decimal("0")),
                    "source_item": source_item,
                    "hsn_code": getattr(source_item, "hsn_code", "") or "",
                })
            PurchaseNotesService.set_credit_note_items(note, items_data, user)
            PurchaseNotesService.complete_credit_note(note, user)

        emit("document.completed", document=purchase_return, user=user, event="purchase_return.completed")
        return purchase_return

    @staticmethod
    @transaction.atomic
    def cancel_return(purchase_return: PurchaseReturn, user):
        purchase_return = PurchaseReturn.objects.select_for_update().get(pk=purchase_return.pk)
        from reporting.gst_periods import assert_period_allows_money_amend

        assert_period_allows_money_amend(
            purchase_return.company, purchase_return.return_date, allow_soft_closed=True
        )
        if purchase_return.status == PurchaseReturn.Status.CANCELLED:
            raise BusinessRuleError("Return is already cancelled.")
        if purchase_return.status == PurchaseReturn.Status.COMPLETED:
            # BB-000545 / BB-000549: replay PURCHASE_RETURN lots with original unit_cost.
            from inventory.models import SerialNumber, StockMovement, MovementType as InvMovementType
            from inventory.services import SerialNumberService

            for item in purchase_return.items.select_related("product"):
                if item.product.track_serial and item.serial_numbers:
                    SerialNumberService.transition(
                        company=purchase_return.company,
                        product=item.product,
                        warehouse=(
                            purchase_return.purchase_invoice.warehouse
                            if purchase_return.purchase_invoice_id
                            else None
                        ),
                        numbers=item.serial_numbers,
                        quantity=item.quantity,
                        source=SerialNumber.Status.SCRAPPED,
                        target=SerialNumber.Status.AVAILABLE,
                        user=user,
                    )

            return_moves = list(
                StockMovement.objects.filter(
                    company=purchase_return.company,
                    movement_type=InvMovementType.PURCHASE_RETURN,
                    reference_type="purchase_return",
                    reference_id=str(purchase_return.pk),
                )
            )
            if return_moves:
                for move in return_moves:
                    InventoryService.post_movement(
                        company=purchase_return.company,
                        warehouse=move.warehouse,
                        product=move.product,
                        batch=move.batch,
                        movement_type=MovementType.ADJUSTMENT,
                        quantity=abs(Decimal(str(move.quantity))),
                        unit_cost=move.unit_cost,
                        reference_type="purchase_return_cancel",
                        reference_id=purchase_return.pk,
                        reason=f"Cancellation of {purchase_return.number}",
                        user=user,
                    )
            else:
                wh = (
                    purchase_return.purchase_invoice.warehouse
                    if purchase_return.purchase_invoice_id
                    else None
                )
                for item in purchase_return.items.select_related("product"):
                    InventoryService.post_movement(
                        company=purchase_return.company,
                        warehouse=wh,
                        product=item.product,
                        movement_type=MovementType.ADJUSTMENT,
                        quantity=item.quantity,
                        reference_type="purchase_return_cancel",
                        reference_id=purchase_return.pk,
                        reason=f"Cancellation of {purchase_return.number}",
                        user=user,
                    )
            invoice = purchase_return.purchase_invoice
            if invoice and invoice.status == PurchaseInvoice.Status.RETURNED:
                invoice.status = PurchaseInvoice.Status.COMPLETED
                invoice.save(update_fields=["status"])
            # BB-000263: cancel linked auto purchase CNs.
            from .models import PurchaseCreditNote
            from .notes_services import PurchaseNotesService

            for note in PurchaseCreditNote.objects.filter(
                purchase_return=purchase_return,
                status=PurchaseCreditNote.Status.COMPLETED,
            ).select_for_update():
                PurchaseNotesService.cancel_credit_note(note, user)
        purchase_return.status = PurchaseReturn.Status.CANCELLED
        purchase_return.cancelled_at = timezone.now()
        purchase_return.updated_by = user
        purchase_return.save()
        emit("document.cancelled", document=purchase_return, user=user, event="purchase_return.cancelled")
        return purchase_return
