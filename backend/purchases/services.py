"""Purchase Service — invoices, returns, status transitions (E3)."""

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.events import emit
from core.exceptions import BusinessRuleError
from core.services.billing import compute_document_totals
from core.services.place_of_supply import assert_place_of_supply_for_gst, party_intra_state
from core.services.document_numbers import DocumentNumberService
from inventory.models import MovementType
from inventory.services import InventoryService
from masters.models import Product

from .models import PurchaseInvoice, PurchaseItem, PurchaseReturn, PurchaseReturnItem


def _validate_lines(items_data, company):
    if not items_data:
        raise BusinessRuleError("At least one line item is required.")
    for line in items_data:
        if Decimal(line["quantity"]) <= 0:
            raise BusinessRuleError("Quantity on each line must be greater than zero.")
        if line["product"].company_id != company.id:
            raise BusinessRuleError("Invalid product reference.")


def _build_purchase_items(invoice, items_data):
    product_ids = [line["product"].pk for line in items_data]
    products = {
        p.pk: p
        for p in Product.objects.filter(pk__in=product_ids).select_related("unit")
    }
    items = []
    for line in items_data:
        product = products.get(line["product"].pk, line["product"])
        unit = getattr(product, "unit", None)
        items.append(PurchaseItem(
            invoice=invoice,
            product=product,
            description=line.get("description") or product.name,
            quantity=line["quantity"],
            unit_price=line.get("unit_price", product.purchase_price),
            discount_percent=line.get("discount_percent", Decimal("0")),
            gst_rate=line.get("gst_rate", product.gst_rate),
            hsn_code=line.get("hsn_code") or product.hsn_code or "",
            mrp=line.get("mrp", product.mrp or Decimal("0")),
            unit_name=(
                line.get("unit_name")
                or (unit.short_name.upper() if unit and unit.short_name else None)
                or (unit.name.upper()[:16] if unit and unit.name else None)
                or "PCS"
            ),
            batch_no=line.get("batch_no") or "",
            exp_date=line.get("exp_date"),
            mfg_date=line.get("mfg_date"),
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
        if adjust_stock:
            for item in invoice.items.select_related("product"):
                old_qty[item.product_id] += item.quantity

        _validate_lines(items_data, invoice.company)

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
                invoice.company, invoice.supplier.state, invoice.supplier.gstin or ""
            ),
            additional_charges=invoice.additional_charges,
            invoice_discount=invoice.invoice_discount,
            auto_round_off=invoice.auto_round_off,
            invoice_discount_mode=getattr(invoice, "invoice_discount_mode", None),
        )
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
                        product=product,
                        movement_type=MovementType.ADJUSTMENT,
                        quantity=delta,
                        reference_type="purchase_invoice_edit",
                        reference_id=invoice.pk,
                        reason=f"Edit of {invoice.number or invoice.pk}",
                        user=user,
                    )
            emit("purchase_invoice.edited", invoice=invoice, user=user)

        invoice.updated_by = user
        invoice.save()
        return invoice

    @staticmethod
    @transaction.atomic
    def complete(invoice: PurchaseInvoice, user):
        """Atomic Complete: number + PURCHASE movements + event (E3.3)."""
        invoice = PurchaseInvoice.objects.select_for_update().get(pk=invoice.pk)
        if invoice.status != PurchaseInvoice.Status.DRAFT:
            raise BusinessRuleError(f"Cannot complete a purchase in status {invoice.status}.")
        items = list(invoice.items.select_related("product"))
        if not items:
            raise BusinessRuleError("Cannot complete a purchase without line items.")

        assert_place_of_supply_for_gst(
            company=invoice.company,
            party_state=invoice.supplier.state or "",
            party_gstin=invoice.supplier.gstin or "",
            tax_enabled=invoice.purchase_type == PurchaseInvoice.PurchaseType.GST,
        )

        invoice.number = invoice.number or DocumentNumberService.next_number(
            invoice.company, "PURCHASE_INVOICE"
        )
        invoice.status = PurchaseInvoice.Status.COMPLETED
        invoice.completed_at = timezone.now()
        invoice.updated_by = user
        invoice.save()

        for item in items:
            InventoryService.post_movement(
                company=invoice.company,
                product=item.product,
                movement_type=MovementType.PURCHASE,
                quantity=item.quantity,
                unit_cost=item.unit_price,
                reference_type="purchase_invoice",
                reference_id=invoice.pk,
                user=user,
            )
        emit("document.completed", document=invoice, user=user, event="purchase_invoice.completed")
        return invoice

    @staticmethod
    @transaction.atomic
    def cancel(invoice: PurchaseInvoice, user):
        invoice = PurchaseInvoice.objects.select_for_update().get(pk=invoice.pk)
        if invoice.status == PurchaseInvoice.Status.CANCELLED:
            raise BusinessRuleError("Purchase is already cancelled.")
        if invoice.returns.filter(status=PurchaseReturn.Status.COMPLETED).exists():
            raise BusinessRuleError("Cannot cancel a purchase with completed returns.")

        if invoice.status == PurchaseInvoice.Status.COMPLETED:
            # Reverse stock via ADJUSTMENT — movements stay append-only (§5.3).
            for item in invoice.items.select_related("product"):
                InventoryService.post_movement(
                    company=invoice.company,
                    product=item.product,
                    movement_type=MovementType.ADJUSTMENT,
                    quantity=-item.quantity,
                    reference_type="purchase_invoice_cancel",
                    reference_id=invoice.pk,
                    reason=f"Cancellation of {invoice.number}",
                    user=user,
                )
        invoice.status = PurchaseInvoice.Status.CANCELLED
        invoice.cancelled_at = timezone.now()
        invoice.updated_by = user
        invoice.save()
        emit("document.cancelled", document=invoice, user=user, event="purchase_invoice.cancelled")
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
            items.append(PurchaseReturnItem(
                purchase_return=purchase_return,
                product=product,
                description=line.get("description") or product.name,
                quantity=line["quantity"],
                unit_price=line.get("unit_price", product.purchase_price),
                discount_percent=line.get("discount_percent", Decimal("0")),
                gst_rate=line.get("gst_rate", product.gst_rate),
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
        if purchase_return.status != PurchaseReturn.Status.DRAFT:
            raise BusinessRuleError(f"Cannot complete a return in status {purchase_return.status}.")
        items = list(purchase_return.items.select_related("product"))
        if not items:
            raise BusinessRuleError("Cannot complete a return without line items.")
        invoice = purchase_return.purchase_invoice
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

        purchase_return.number = DocumentNumberService.next_number(purchase_return.company, "PURCHASE_RETURN")
        purchase_return.status = PurchaseReturn.Status.COMPLETED
        purchase_return.completed_at = timezone.now()
        purchase_return.updated_by = user
        purchase_return.save()

        for item in items:
            InventoryService.post_movement(
                company=purchase_return.company,
                product=item.product,
                movement_type=MovementType.PURCHASE_RETURN,
                quantity=item.quantity,
                unit_cost=item.unit_price,
                reference_type="purchase_return",
                reference_id=purchase_return.pk,
                user=user,
            )
        emit("document.completed", document=purchase_return, user=user, event="purchase_return.completed")
        return purchase_return

    @staticmethod
    @transaction.atomic
    def cancel_return(purchase_return: PurchaseReturn, user):
        purchase_return = PurchaseReturn.objects.select_for_update().get(pk=purchase_return.pk)
        if purchase_return.status == PurchaseReturn.Status.CANCELLED:
            raise BusinessRuleError("Return is already cancelled.")
        if purchase_return.status == PurchaseReturn.Status.COMPLETED:
            for item in purchase_return.items.select_related("product"):
                InventoryService.post_movement(
                    company=purchase_return.company,
                    product=item.product,
                    movement_type=MovementType.ADJUSTMENT,
                    quantity=item.quantity,
                    reference_type="purchase_return_cancel",
                    reference_id=purchase_return.pk,
                    reason=f"Cancellation of {purchase_return.number}",
                    user=user,
                )
        purchase_return.status = PurchaseReturn.Status.CANCELLED
        purchase_return.cancelled_at = timezone.now()
        purchase_return.updated_by = user
        purchase_return.save()
        emit("document.cancelled", document=purchase_return, user=user, event="purchase_return.cancelled")
        return purchase_return
