"""Sales Service — quotations, invoices, returns, status transitions (E4)."""

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
from masters.models import Customer, Product

from .models import (
    Quotation,
    QuotationItem,
    SalesInvoice,
    SalesItem,
    SalesReturn,
    SalesReturnItem,
)


def _validate_lines(items_data, company, *, check_active=True):
    if not items_data:
        raise BusinessRuleError("At least one line item is required.")
    for line in items_data:
        if Decimal(line["quantity"]) <= 0:
            raise BusinessRuleError("Quantity on each line must be greater than zero.")
        product = line["product"]
        if product.company_id != company.id:
            raise BusinessRuleError("Invalid product reference.")
        if check_active and product.status != Product.Status.ACTIVE:
            raise BusinessRuleError(f"Cannot sell inactive product '{product.name}'.")


def _build_items(model_cls, parent_field, parent, items_data):
    # Prefetch units to avoid N+1 when snapshotting unit_name.
    product_ids = [line["product"].pk for line in items_data]
    products = {
        p.pk: p
        for p in Product.objects.filter(pk__in=product_ids).select_related("unit")
    }
    items = []
    for line in items_data:
        product = products.get(line["product"].pk, line["product"])
        kwargs = {
            parent_field: parent,
            "product": product,
            "description": line.get("description") or product.name,
            "quantity": line["quantity"],
            "unit_price": line.get("unit_price", product.selling_price),
            "discount_percent": line.get("discount_percent", Decimal("0")),
            "gst_rate": line.get("gst_rate", product.gst_rate),
        }
        # Snapshot product fields onto sales lines for stable GST invoice PDFs.
        if model_cls is SalesItem:
            unit = getattr(product, "unit", None)
            kwargs.update({
                "hsn_code": line.get("hsn_code") or product.hsn_code or "",
                "mrp": line.get("mrp", product.mrp or Decimal("0")),
                "unit_name": (
                    line.get("unit_name")
                    or (unit.short_name.upper() if unit and unit.short_name else None)
                    or (unit.name.upper()[:16] if unit and unit.name else None)
                    or "PCS"
                ),
                "batch_no": line.get("batch_no") or "",
                "exp_date": line.get("exp_date"),
                "mfg_date": line.get("mfg_date"),
            })
        items.append(model_cls(**kwargs))
    return items


def _tax_enabled(invoice_type):
    return invoice_type != SalesInvoice.InvoiceType.NON_GST


class SalesService:
    # ---------------- Sales invoice ----------------

    @staticmethod
    @transaction.atomic
    def set_items(invoice: SalesInvoice, items_data, user):
        if invoice.status in (SalesInvoice.Status.CANCELLED, SalesInvoice.Status.RETURNED):
            raise BusinessRuleError("Cancelled/returned invoice cannot be line-edited.")
        if invoice.status not in (SalesInvoice.Status.DRAFT, SalesInvoice.Status.COMPLETED):
            raise BusinessRuleError(f"Cannot edit invoice in status {invoice.status}.")

        old_qty = defaultdict(Decimal)
        adjust_stock = invoice.status == SalesInvoice.Status.COMPLETED
        if adjust_stock:
            for item in invoice.items.select_related("product"):
                old_qty[item.product_id] += item.quantity

        _validate_lines(items_data, invoice.company)

        new_qty_preview = defaultdict(Decimal)
        for line in items_data:
            new_qty_preview[line["product"].pk] += Decimal(line["quantity"])

        if adjust_stock:
            # Cannot reduce a line below quantities already returned.
            already = SalesService._returned_quantities(invoice)
            for product_id, returned_qty in already.items():
                if new_qty_preview.get(product_id, Decimal("0")) < returned_qty:
                    raise BusinessRuleError(
                        f"Quantity cannot be below already-returned quantity {returned_qty}."
                    )
            # Extra stock sold on edit must pass negative-stock policy.
            for product_id, new_q in new_qty_preview.items():
                delta = new_q - old_qty.get(product_id, Decimal("0"))
                if delta > 0:
                    product = next(
                        (line["product"] for line in items_data if line["product"].pk == product_id),
                        None,
                    ) or Product.objects.get(pk=product_id)
                    InventoryService.check_negative_stock(invoice.company, product, delta)

        invoice.items.all().delete()
        items = _build_items(SalesItem, "invoice", invoice, items_data)
        compute_document_totals(
            invoice, items,
            tax_enabled=_tax_enabled(invoice.invoice_type),
            intra_state=party_intra_state(
                invoice.company, invoice.customer.state, invoice.customer.gstin or ""
            ),
            additional_charges=invoice.additional_charges,
            invoice_discount=invoice.invoice_discount,
            auto_round_off=invoice.auto_round_off,
            invoice_discount_mode=getattr(invoice, "invoice_discount_mode", None),
        )
        SalesItem.objects.bulk_create(items)

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
                        movement_type=MovementType.SALE,
                        quantity=delta,
                        reference_type="sales_invoice",
                        reference_id=invoice.pk,
                        user=user,
                    )
                else:
                    InventoryService.post_movement(
                        company=invoice.company,
                        product=product,
                        movement_type=MovementType.ADJUSTMENT,
                        quantity=-delta,
                        reference_type="sales_invoice_edit",
                        reference_id=invoice.pk,
                        reason=f"Edit of {invoice.number or invoice.pk}",
                        user=user,
                    )
            invoice.pdf_status = SalesInvoice.PdfStatus.QUEUED
            invoice.updated_by = user
            invoice.save()
            emit("sales_invoice.edited", invoice=invoice, user=user)
            emit("sales_invoice.completed", invoice=invoice, user=user)
            return invoice

        invoice.updated_by = user
        invoice.save()
        return invoice

    @staticmethod
    @transaction.atomic
    def complete(invoice: SalesInvoice, user):
        """Atomic Complete: rules + number + SALE movements + PDF event (E4.4)."""
        invoice = SalesInvoice.objects.select_for_update().get(pk=invoice.pk)
        if invoice.status != SalesInvoice.Status.DRAFT:
            raise BusinessRuleError(f"Cannot complete an invoice in status {invoice.status}.")
        if invoice.customer.status == Customer.Status.BLOCKED:
            raise BusinessRuleError("Cannot create an invoice for a blocked customer.")
        items = list(invoice.items.select_related("product"))
        if not items:
            raise BusinessRuleError("Cannot complete an invoice without line items.")

        assert_place_of_supply_for_gst(
            company=invoice.company,
            party_state=invoice.customer.state or "",
            party_gstin=invoice.customer.gstin or "",
            tax_enabled=_tax_enabled(invoice.invoice_type),
        )

        warnings = []
        # Aggregate per product for the negative-stock check.
        required = defaultdict(Decimal)
        for item in items:
            if item.product.status != Product.Status.ACTIVE:
                raise BusinessRuleError(f"Cannot sell inactive product '{item.product.name}'.")
            if item.quantity <= 0:
                raise BusinessRuleError("Quantity on each line must be greater than zero.")
            required[item.product] += item.quantity
        for product, qty in required.items():
            warning = InventoryService.check_negative_stock(invoice.company, product, qty)
            if warning:
                warnings.append(warning)

        invoice.number = invoice.number or DocumentNumberService.next_number(
            invoice.company, "SALES_INVOICE"
        )
        invoice.status = SalesInvoice.Status.COMPLETED
        invoice.completed_at = timezone.now()
        invoice.pdf_status = SalesInvoice.PdfStatus.QUEUED
        invoice.updated_by = user
        invoice.save()

        for item in items:
            InventoryService.post_movement(
                company=invoice.company,
                product=item.product,
                movement_type=MovementType.SALE,
                quantity=item.quantity,
                reference_type="sales_invoice",
                reference_id=invoice.pk,
                user=user,
            )
        emit("document.completed", document=invoice, user=user, event="sales_invoice.completed")
        emit("sales_invoice.completed", invoice=invoice, user=user)
        return invoice, warnings

    @staticmethod
    @transaction.atomic
    def cancel(invoice: SalesInvoice, user):
        invoice = SalesInvoice.objects.select_for_update().get(pk=invoice.pk)
        if invoice.status == SalesInvoice.Status.CANCELLED:
            raise BusinessRuleError("Invoice is already cancelled.")
        if invoice.returns.filter(status=SalesReturn.Status.COMPLETED).exists():
            raise BusinessRuleError("Cannot cancel an invoice with completed returns.")

        if invoice.status in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
            # Restore stock via ADJUSTMENT — never delete SALE movements (§5.3).
            for item in invoice.items.select_related("product"):
                InventoryService.post_movement(
                    company=invoice.company,
                    product=item.product,
                    movement_type=MovementType.ADJUSTMENT,
                    quantity=item.quantity,
                    reference_type="sales_invoice_cancel",
                    reference_id=invoice.pk,
                    reason=f"Cancellation of {invoice.number}",
                    user=user,
                )
        invoice.status = SalesInvoice.Status.CANCELLED
        invoice.cancelled_at = timezone.now()
        invoice.updated_by = user
        invoice.save()
        emit("document.cancelled", document=invoice, user=user, event="sales_invoice.cancelled")
        return invoice

    # ---------------- Quotation ----------------

    @staticmethod
    @transaction.atomic
    def set_quotation_items(quotation: Quotation, items_data, user):
        if quotation.status != Quotation.Status.DRAFT:
            raise BusinessRuleError("Only draft quotations can be edited.")
        _validate_lines(items_data, quotation.company)
        quotation.items.all().delete()
        items = _build_items(QuotationItem, "quotation", quotation, items_data)
        compute_document_totals(
            quotation, items,
            tax_enabled=_tax_enabled(quotation.invoice_type),
            intra_state=party_intra_state(
                quotation.company, quotation.customer.state, quotation.customer.gstin or ""
            ),
        )
        QuotationItem.objects.bulk_create(items)
        quotation.updated_by = user
        quotation.save()
        return quotation

    @staticmethod
    @transaction.atomic
    def convert_quotation(quotation: Quotation, user):
        """Quotation → draft sales invoice, preserving lines (E4.5)."""
        quotation = Quotation.objects.select_for_update().get(pk=quotation.pk)
        if quotation.status != Quotation.Status.DRAFT:
            raise BusinessRuleError(f"Cannot convert a quotation in status {quotation.status}.")
        if quotation.customer.status == Customer.Status.BLOCKED:
            raise BusinessRuleError("Cannot create an invoice for a blocked customer.")
        if not quotation.number:
            quotation.number = DocumentNumberService.next_number(quotation.company, "QUOTATION")

        invoice = SalesInvoice.objects.create(
            company=quotation.company,
            customer=quotation.customer,
            invoice_type=quotation.invoice_type,
            notes=quotation.notes,
            created_by=user,
            updated_by=user,
        )
        items_data = [
            {
                "product": item.product, "description": item.description,
                "quantity": item.quantity, "unit_price": item.unit_price,
                "discount_percent": item.discount_percent, "gst_rate": item.gst_rate,
            }
            for item in quotation.items.select_related("product")
        ]
        SalesService.set_items(invoice, items_data, user)
        quotation.status = Quotation.Status.CONVERTED
        quotation.converted_invoice = invoice
        quotation.updated_by = user
        quotation.save()
        return invoice

    @staticmethod
    @transaction.atomic
    def cancel_quotation(quotation: Quotation, user):
        if quotation.status != Quotation.Status.DRAFT:
            raise BusinessRuleError(f"Cannot cancel a quotation in status {quotation.status}.")
        quotation.status = Quotation.Status.CANCELLED
        quotation.updated_by = user
        quotation.save()
        return quotation

    # ---------------- Sales return ----------------

    @staticmethod
    @transaction.atomic
    def set_return_items(sales_return: SalesReturn, items_data, user):
        if sales_return.status != SalesReturn.Status.DRAFT:
            raise BusinessRuleError("Completed return cannot be edited.")
        _validate_lines(items_data, sales_return.company, check_active=False)
        sales_return.items.all().delete()
        items = _build_items(SalesReturnItem, "sales_return", sales_return, items_data)
        compute_document_totals(
            sales_return, items,
            tax_enabled=_tax_enabled(sales_return.sales_invoice.invoice_type),
            intra_state=party_intra_state(
                sales_return.company, sales_return.customer.state, sales_return.customer.gstin or ""
            ),
        )
        SalesReturnItem.objects.bulk_create(items)
        sales_return.updated_by = user
        sales_return.save()
        return sales_return

    @staticmethod
    def _returned_quantities(invoice, exclude_return=None):
        qs = SalesReturnItem.objects.filter(
            sales_return__sales_invoice=invoice,
            sales_return__status=SalesReturn.Status.COMPLETED,
        )
        if exclude_return is not None:
            qs = qs.exclude(sales_return=exclude_return)
        return {
            row["product"]: row["total"]
            for row in qs.values("product").annotate(total=Sum("quantity"))
        }

    @staticmethod
    @transaction.atomic
    def complete_return(sales_return: SalesReturn, user):
        sales_return = SalesReturn.objects.select_for_update().get(pk=sales_return.pk)
        if sales_return.status != SalesReturn.Status.DRAFT:
            raise BusinessRuleError(f"Cannot complete a return in status {sales_return.status}.")
        invoice = sales_return.sales_invoice
        if invoice.status not in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
            raise BusinessRuleError("Sales return must reference a completed invoice.")
        items = list(sales_return.items.select_related("product"))
        if not items:
            raise BusinessRuleError("Cannot complete a return without line items.")

        # Return qty per product cannot exceed sold qty minus already-returned qty.
        sold = {
            row["product"]: row["total"]
            for row in invoice.items.values("product").annotate(total=Sum("quantity"))
        }
        already = SalesService._returned_quantities(invoice)
        requested = defaultdict(Decimal)
        for item in items:
            requested[item.product_id] += item.quantity
        for product_id, qty in requested.items():
            remaining = sold.get(product_id, Decimal("0")) - already.get(product_id, Decimal("0"))
            if qty > remaining:
                raise BusinessRuleError(
                    f"Return quantity {qty} exceeds remaining returnable quantity {remaining}."
                )

        sales_return.number = DocumentNumberService.next_number(sales_return.company, "SALES_RETURN")
        sales_return.status = SalesReturn.Status.COMPLETED
        sales_return.completed_at = timezone.now()
        sales_return.updated_by = user
        sales_return.save()

        for item in items:
            InventoryService.post_movement(
                company=sales_return.company,
                product=item.product,
                movement_type=MovementType.SALES_RETURN,
                quantity=item.quantity,
                reference_type="sales_return",
                reference_id=sales_return.pk,
                user=user,
            )

        # Mark invoice Returned when every sold quantity has been returned.
        now_returned = SalesService._returned_quantities(invoice)
        fully_returned = all(
            now_returned.get(pid, Decimal("0")) >= qty for pid, qty in sold.items()
        )
        if fully_returned and invoice.status != SalesInvoice.Status.RETURNED:
            invoice.status = SalesInvoice.Status.RETURNED
            invoice.save(update_fields=["status"])

        emit("document.completed", document=sales_return, user=user, event="sales_return.completed")
        return sales_return

    @staticmethod
    @transaction.atomic
    def cancel_return(sales_return: SalesReturn, user):
        sales_return = SalesReturn.objects.select_for_update().get(pk=sales_return.pk)
        if sales_return.status == SalesReturn.Status.CANCELLED:
            raise BusinessRuleError("Return is already cancelled.")
        if sales_return.status == SalesReturn.Status.COMPLETED:
            for item in sales_return.items.select_related("product"):
                InventoryService.post_movement(
                    company=sales_return.company,
                    product=item.product,
                    movement_type=MovementType.ADJUSTMENT,
                    quantity=-item.quantity,
                    reference_type="sales_return_cancel",
                    reference_id=sales_return.pk,
                    reason=f"Cancellation of {sales_return.number}",
                    user=user,
                )
            invoice = sales_return.sales_invoice
            if invoice.status == SalesInvoice.Status.RETURNED:
                invoice.status = SalesInvoice.Status.COMPLETED
                invoice.save(update_fields=["status"])
        sales_return.status = SalesReturn.Status.CANCELLED
        sales_return.cancelled_at = timezone.now()
        sales_return.updated_by = user
        sales_return.save()
        emit("document.cancelled", document=sales_return, user=user, event="sales_return.cancelled")
        return sales_return
