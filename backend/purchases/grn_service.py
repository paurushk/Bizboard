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

from .models import GoodsReceipt, PurchaseDebitNote, PurchaseInvoice, PurchaseNoteReason


def _draft_rejection_debit_note(grn, items, user):
    """Draft a supplier debit note for quantities rejected at receipt."""
    rejected = [
        item for item in items
        if Decimal(str(item.quantity_rejected or 0)) > 0
    ]
    if not rejected:
        return None
    if PurchaseDebitNote.objects.filter(goods_receipt=grn).exclude(
        status=PurchaseDebitNote.Status.CANCELLED
    ).exists():
        return None
    reasons = [((item.rejection_reason or "").strip()) for item in rejected]
    reason_detail = next((text for text in reasons if text), "Inspection rejection")[:255]
    note = PurchaseDebitNote.objects.create(
        company=grn.company,
        supplier=grn.supplier,
        goods_receipt=grn,
        status=PurchaseDebitNote.Status.DRAFT,
        note_date=grn.receipt_date,
        reason=PurchaseNoteReason.OTHERS,
        reason_detail=reason_detail,
        notes=(
            f"Draft debit note for goods rejected on GRN {grn.number or grn.pk}."
            + (
                " Convert the receipt to a purchase bill first; the note can be completed only against that bill."
                if grn.company.is_gst_registered
                else ""
            )
        ),
        created_by=user,
        updated_by=user,
    )
    payload = []
    for item in rejected:
        payload.append({
            "product": item.product,
            "quantity": Decimal(str(item.quantity_rejected)),
            "unit_price": Decimal(str(item.unit_price or 0)).quantize(Decimal("0.01")),
            "gst_rate": getattr(item.product, "gst_rate", None) or Decimal("0"),
            "description": (item.rejection_reason or "").strip() or f"Rejected on GRN {grn.number or grn.pk}",
        })
    from .notes_services import PurchaseNotesService

    PurchaseNotesService.set_debit_note_items(note, payload, user)
    return note


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
        grn = GoodsReceipt.objects.select_for_update().get(pk=grn.pk)
        if grn.status != GoodsReceipt.Status.DRAFT:
            raise BusinessRuleError(f"Cannot complete GRN in status '{grn.status}'.")

        items = list(grn.items.select_related("product", "batch").all())
        if not items:
            raise BusinessRuleError("Cannot complete GRN with no line items.")

        for item in items:
            received = Decimal(str(item.quantity_received or 0))
            accepted = Decimal(str(item.quantity_accepted or 0))
            rejected = Decimal(str(item.quantity_rejected or 0))
            if accepted + rejected != received:
                raise BusinessRuleError(
                    f"Accepted ({accepted}) plus rejected ({rejected}) must equal "
                    f"received ({received}) for '{item.product.name}'."
                )

        # MFG-21: an item that needs inspection is not received until its inspection is decided.
        from quality.hooks import assert_grn_inspected

        assert_grn_inspected(grn, items)

        # G-21: period gate before number/status/stock — a GRN posts
        # valuation-carrying stock (unit_cost), same as PurchaseInvoice.complete,
        # so it must not be completable with a receipt_date inside a locked period.
        from reporting.gst_periods import assert_period_allows_money_amend

        assert_period_allows_money_amend(grn.company, grn.receipt_date)

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

        from inventory.item_stock import get_or_create_batch
        from inventory.services import SerialNumberService

        for item in items:
            accepted = Decimal(str(item.quantity_accepted or 0))
            if accepted <= 0:
                continue
            if not tracks_inventory(item.product):
                continue
            batch = item.batch
            if item.product.track_batch:
                if batch is None:
                    batch_no = (item.batch_no or "").strip()
                    if not batch_no:
                        raise BusinessRuleError(
                            f"A batch is required for tracked product '{item.product.name}'."
                        )
                    batch = get_or_create_batch(
                        company=grn.company,
                        product=item.product,
                        batch_no=batch_no,
                        expiry_date=item.exp_date,
                        manufacturing_date=item.mfg_date,
                        user=user,
                    )
                    item.batch = batch
                    item.save(update_fields=["batch", "updated_at"])
            # MFG-20: an item flagged "receive into quarantine" goes to the quarantine godown, in a lot
            # that cannot be used until quality releases it.
            from quality import hooks as quality_hooks

            post_warehouse = quality_hooks.quarantine_target(grn.company, item.product) or warehouse
            if post_warehouse is not warehouse and batch is not None:
                quality_hooks.mark_quarantined(batch, user)
            if item.product.track_serial:
                numbers = list(item.serial_numbers or [])
                if len(numbers) != int(accepted):
                    raise BusinessRuleError(
                        f"Serial numbers are required to receive '{item.product.name}'."
                    )
                SerialNumberService.receive(
                    company=grn.company,
                    product=item.product,
                    warehouse=post_warehouse,
                    numbers=numbers,
                    quantity=accepted,
                    user=user,
                )

            InventoryService.post_movement(
                company=grn.company,
                warehouse=post_warehouse,
                product=item.product,
                batch=batch,
                movement_type=MovementType.PURCHASE,
                quantity=accepted,
                # G-02: a blank receipt price would put stock in at zero cost; use the product's
                # purchase price until the bill gives the real one.
                unit_cost=item.unit_price or getattr(item.product, "purchase_price", None) or Decimal("0.00"),
                reference_type="goods_receipt",
                reference_id=grn.pk,
                user=user,
                movement_date=grn.receipt_date,
            )
            if post_warehouse is not warehouse:
                quality_hooks.after_grn_item_received(grn, item, batch, accepted, user)

        if getattr(warehouse, "kind", "NORMAL") == "JOB_WORKER":
            # MFG-24: the supplier shipped straight to the job worker. Write the challan that lets the
            # sending be settled, aged and reported (ITC-04 table 4, "sent directly from supplier").
            from jobwork.services.out import register_direct_receipt

            register_direct_receipt(grn, user)

        _draft_rejection_debit_note(grn, items, user)
        from core.services.audit import record_document_event

        record_document_event(document=grn, user=user, event="goods_receipt.completed")
        return grn

    @staticmethod
    @transaction.atomic
    def convert_to_bill(grn: GoodsReceipt, user) -> PurchaseInvoice:
        grn = GoodsReceipt.objects.select_for_update().get(pk=grn.pk)
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
        for item in grn.items.select_related("product", "batch").all():
            # Bill only accepted quantity. A zero here means the line was
            # rejected; do not fall through to quantity_received.
            qty = Decimal(str(item.quantity_accepted or 0))
            if qty <= 0:
                continue
            from_master = not item.unit_price
            price = Decimal(str(item.unit_price or getattr(item.product, "purchase_price", 0) or 0))
            gst_rate = Decimal(str(getattr(item.product, "gst_rate", 0) or 0))

            items_data.append({
                "product": item.product,
                "quantity": qty,
                "unit_price": price,
                "gst_rate": gst_rate,
                "description": f"Received via GRN {grn.number}"
                + (" (price taken from the product, check it against the supplier's bill)" if from_master else ""),
                "batch": item.batch,
                "batch_no": item.batch_no or getattr(item.batch, "batch_no", "") or "",
                "exp_date": item.exp_date,
                "mfg_date": item.mfg_date,
                "serial_numbers": list(item.serial_numbers or []),
            })

        if items_data:
            PurchaseService.set_items(invoice, items_data, user)

        grn.converted_purchase = invoice
        grn.save(update_fields=["converted_purchase", "updated_at"])
        from .models import PurchaseDebitNote

        PurchaseDebitNote.objects.filter(
            company=grn.company,
            goods_receipt=grn,
            purchase_invoice__isnull=True,
            status=PurchaseDebitNote.Status.DRAFT,
        ).update(purchase_invoice=invoice)
        return invoice

    @staticmethod
    @transaction.atomic
    def cancel(grn: GoodsReceipt, user) -> GoodsReceipt:
        grn = GoodsReceipt.objects.select_for_update().get(pk=grn.pk)
        if grn.status == GoodsReceipt.Status.CANCELLED:
            raise BusinessRuleError("GRN is already cancelled.")

        # G-21: mirrors PurchaseInvoice.cancel's gate — allow_soft_closed=True
        # so a completed GRN can still be unwound after a soft-close, matching
        # every other cancel/reverse call site of this gate.
        from reporting.gst_periods import assert_period_allows_money_amend

        assert_period_allows_money_amend(grn.company, grn.receipt_date, allow_soft_closed=True)

        # G-01: the debit note drafted for this receipt's rejected goods goes with it.
        if PurchaseDebitNote.objects.filter(
            goods_receipt=grn, status=PurchaseDebitNote.Status.COMPLETED
        ).exists():
            raise BusinessRuleError(
                "A debit note for the rejected goods on this receipt is already completed. "
                "Cancel that debit note before cancelling the receipt."
            )
        PurchaseDebitNote.objects.filter(
            goods_receipt=grn, status=PurchaseDebitNote.Status.DRAFT
        ).update(status=PurchaseDebitNote.Status.CANCELLED, updated_at=timezone.now())

        if grn.status == GoodsReceipt.Status.COMPLETED:
            bill = grn.converted_purchase
            if bill is not None and bill.status != PurchaseInvoice.Status.CANCELLED:
                raise BusinessRuleError(
                    "Cancel the purchase bill created from this GRN before cancelling the receipt."
                )
            from inventory.models import StockMovement

            already_unwound = StockMovement.objects.filter(
                company=grn.company,
                reference_type="goods_receipt_unwind",
                reference_id=str(grn.pk),
            ).exists()
            if not already_unwound:
                warehouse = grn.warehouse or GoodsReceiptService.get_default_warehouse(grn.company)
                from inventory.models import SerialNumber

                for item in grn.items.select_related("product", "batch").all():
                    accepted = Decimal(str(item.quantity_accepted or 0))
                    if accepted > 0 and item.product.track_serial and item.serial_numbers:
                        sold = SerialNumber.objects.filter(
                            company=grn.company,
                            product=item.product,
                            serial_number__in=list(item.serial_numbers),
                        ).exclude(status=SerialNumber.Status.AVAILABLE)
                        if sold.exists():
                            raise BusinessRuleError(
                                f"Cannot cancel GRN: serialized '{item.product.name}' is no longer available."
                            )
                    if accepted > 0 and tracks_inventory(item.product):
                        InventoryService.post_movement(
                            company=grn.company,
                            warehouse=warehouse,
                            product=item.product,
                            batch=item.batch,
                            movement_type=MovementType.PURCHASE_RETURN,
                            quantity=accepted,
                            unit_cost=item.unit_price or Decimal("0.00"),
                            reference_type="goods_receipt_cancel",
                            reference_id=grn.pk,
                            user=user,
                            movement_date=grn.receipt_date,
                        )
                    if item.product.track_serial and item.serial_numbers:
                        SerialNumber.objects.filter(
                            company=grn.company,
                            product=item.product,
                            serial_number__in=list(item.serial_numbers),
                            status=SerialNumber.Status.AVAILABLE,
                        ).delete()

        grn.status = GoodsReceipt.Status.CANCELLED
        grn.cancelled_at = timezone.now()
        grn.save(update_fields=["status", "cancelled_at", "updated_at"])
        return grn
