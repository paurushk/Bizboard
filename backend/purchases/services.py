"""Purchase Service — invoices, returns, status transitions (E3)."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.events import emit
from core.exceptions import BusinessRuleError
from core.services.billing import compute_document_totals, is_intra_state
from core.services.document_numbers import DocumentNumberService
from inventory.models import MovementType
from inventory.services import InventoryService

from .models import PurchaseInvoice, PurchaseItem, PurchaseReturn, PurchaseReturnItem


def _validate_lines(items_data, company):
    if not items_data:
        raise BusinessRuleError("At least one line item is required.")
    for line in items_data:
        if Decimal(line["quantity"]) <= 0:
            raise BusinessRuleError("Quantity on each line must be greater than zero.")
        if line["product"].company_id != company.id:
            raise BusinessRuleError("Invalid product reference.")


class PurchaseService:
    # ---------------- Purchase invoice ----------------

    @staticmethod
    @transaction.atomic
    def set_items(invoice: PurchaseInvoice, items_data, user):
        if invoice.status != PurchaseInvoice.Status.DRAFT:
            raise BusinessRuleError("Completed purchase cannot be line-edited; use Return or Cancel.")
        _validate_lines(items_data, invoice.company)
        invoice.items.all().delete()
        items = []
        for line in items_data:
            product = line["product"]
            items.append(PurchaseItem(
                invoice=invoice,
                product=product,
                description=line.get("description") or product.name,
                quantity=line["quantity"],
                unit_price=line.get("unit_price", product.purchase_price),
                discount_percent=line.get("discount_percent", Decimal("0")),
                gst_rate=line.get("gst_rate", product.gst_rate),
            ))
        compute_document_totals(
            invoice, items,
            tax_enabled=invoice.purchase_type == PurchaseInvoice.PurchaseType.GST,
            intra_state=is_intra_state(invoice.company.state, invoice.supplier.state),
        )
        PurchaseItem.objects.bulk_create(items)
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

        invoice.number = DocumentNumberService.next_number(invoice.company, "PURCHASE_INVOICE")
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
            intra_state=is_intra_state(purchase_return.company.state, purchase_return.supplier.state),
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
        if purchase_return.purchase_invoice and purchase_return.purchase_invoice.status != PurchaseInvoice.Status.COMPLETED:
            raise BusinessRuleError("Purchase return must reference a completed purchase invoice.")

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
