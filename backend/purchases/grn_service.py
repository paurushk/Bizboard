"""Goods Receipt Note (GRN) Service (FR-018).

Handles creation, items, stock movement posting on completion, conversion to
draft purchase invoice, and cancellation.
"""

from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services.document_numbers import DocumentNumberService
from inventory.item_stock import tracks_inventory
from inventory.models import MovementType, Warehouse
from inventory.services import InventoryService

from .models import GoodsReceipt, GoodsReceiptItem, PurchaseInvoice, PurchaseItem


class GoodsReceiptService:
    @staticmethod
    def get_default_warehouse(company):
        wh = Warehouse.objects.filter(company=company, is_default=True).first()
        if not wh:
            wh = Warehouse.objects.filter(company=company, is_active=True).first()
        return wh

    @staticmethod
    @transaction.atomic
    def complete(grn: GoodsReceipt, user) -> GoodsReceipt:
        if grn.status != GoodsReceipt.Status.DRAFT:
            raise BusinessRuleError(f"Cannot complete GRN in status '{grn.status}'.")

        items = list(grn.items.select_related("product").all())
        if not items:
            raise BusinessRuleError("Cannot complete GRN with no line items.")

        warehouse = grn.warehouse or GoodsReceiptService.get_default_warehouse(grn.company)
        if not warehouse:
            raise BusinessRuleError("A warehouse is required to receive goods into stock.")
        if grn.warehouse_id != warehouse.pk:
            grn.warehouse = warehouse

        if not grn.number:
            grn.number = DocumentNumberService.next_number(grn.company, "GOODS_RECEIPT")

        grn.status = GoodsReceipt.Status.COMPLETED
        grn.completed_at = timezone.now()
        grn.save(update_fields=["warehouse", "number", "status", "completed_at", "updated_at"])

        for item in items:
            accepted = Decimal(str(item.quantity_accepted or 0))
            if accepted <= 0:
                continue
            if not tracks_inventory(item.product):
                continue

            InventoryService.post_movement(
                company=grn.company,
                warehouse=warehouse,
                product=item.product,
                batch=None,
                movement_type=MovementType.PURCHASE,
                quantity=accepted,
                unit_cost=item.unit_price or Decimal("0.00"),
                reference_type="goods_receipt",
                reference_id=grn.pk,
                user=user,
            )

        return grn

    @staticmethod
    @transaction.atomic
    def convert_to_bill(grn: GoodsReceipt, user) -> PurchaseInvoice:
        if grn.status != GoodsReceipt.Status.COMPLETED:
            raise BusinessRuleError("Only completed GRNs can be converted to a purchase bill.")
        if grn.converted_purchase_id:
            raise BusinessRuleError(f"GRN has already been converted to Purchase Invoice #{grn.converted_purchase_id}.")

        warehouse = grn.warehouse or GoodsReceiptService.get_default_warehouse(grn.company)
        invoice = PurchaseInvoice.objects.create(
            company=grn.company,
            supplier=grn.supplier,
            warehouse=warehouse,
            invoice_date=grn.receipt_date,
            status=PurchaseInvoice.Status.DRAFT,
            notes=f"Generated from GRN {grn.number or grn.pk}.",
            created_by=user,
        )

        from .services import PurchaseService
        items_data = []
        for item in grn.items.select_related("product").all():
            qty = Decimal(str(item.quantity_accepted or item.quantity_received or 0))
            if qty <= 0:
                continue
            price = Decimal(str(item.unit_price or getattr(item.product, "purchase_price", 0) or 0))
            gst_rate = Decimal(str(getattr(item.product, "tax_rate", 0) or 0))

            items_data.append({
                "product": item.product,
                "quantity": qty,
                "unit_price": price,
                "gst_rate": gst_rate,
                "description": f"Received via GRN {grn.number}",
            })

        if items_data:
            PurchaseService.set_items(invoice, items_data, user)

        grn.converted_purchase = invoice
        grn.save(update_fields=["converted_purchase", "updated_at"])
        return invoice

    @staticmethod
    @transaction.atomic
    def cancel(grn: GoodsReceipt, user) -> GoodsReceipt:
        if grn.status == GoodsReceipt.Status.CANCELLED:
            raise BusinessRuleError("GRN is already cancelled.")

        if grn.status == GoodsReceipt.Status.COMPLETED:
            warehouse = grn.warehouse or GoodsReceiptService.get_default_warehouse(grn.company)
            for item in grn.items.select_related("product").all():
                accepted = Decimal(str(item.quantity_accepted or 0))
                if accepted > 0 and tracks_inventory(item.product):
                    InventoryService.post_movement(
                        company=grn.company,
                        warehouse=warehouse,
                        product=item.product,
                        batch=None,
                        movement_type=MovementType.PURCHASE_RETURN,
                        quantity=accepted,
                        unit_cost=item.unit_price or Decimal("0.00"),
                        reference_type="goods_receipt_cancel",
                        reference_id=grn.pk,
                        user=user,
                    )

        grn.status = GoodsReceipt.Status.CANCELLED
        grn.cancelled_at = timezone.now()
        grn.save(update_fields=["status", "cancelled_at", "updated_at"])
        return grn
