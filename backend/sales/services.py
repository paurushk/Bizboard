"""Sales Service — quotations, invoices, returns, status transitions (E4)."""

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.events import emit
from core.exceptions import BusinessRuleError
from core.help_codes import HelpCode
from core.services.billing import apply_rcm_memo_after_tax, compute_document_totals, recompute_totals_for_stamped_gstin
from core.services.place_of_supply import (
    assert_place_of_supply_for_gst,
    is_export_or_sez_supply,
    party_intra_state,
    resolve_place_of_supply_code,
)
from core.services.registration_gates import assert_may_issue_gst_tax_invoice
from core.services.document_numbers import DocumentNumberService
from inventory.models import BatchLot, MovementType, SerialNumber, StockMovement
from inventory.services import InventoryService, InventoryValuationService, SerialNumberService
from ledgers.services import LedgerService
from masters.models import Customer, Product

from .models import (
    Quotation,
    QuotationItem,
    SalesCreditNoteItem,
    SalesDebitNoteItem,
    SalesInvoice,
    SalesItem,
    SalesReturn,
    SalesReturnItem,
)


def _validate_lines(items_data, company, *, check_active=True):
    from core.validators import ALLOWED_GST_RATES

    allowed_gst = {Decimal(r) for r in ALLOWED_GST_RATES}
    if not items_data:
        raise BusinessRuleError("At least one line item is required.")
    for line in items_data:
        if Decimal(line["quantity"]) <= 0:
            raise BusinessRuleError("Quantity on each line must be greater than zero.")
        unit_price = Decimal(str(line.get("unit_price", line["product"].selling_price)))
        if unit_price < 0:
            raise BusinessRuleError("Unit price cannot be negative.")
        discount_percent = Decimal(str(line.get("discount_percent", 0) or 0))
        if discount_percent < 0 or discount_percent > 100:
            raise BusinessRuleError("Discount percent must be between 0 and 100.")
        gst_rate = Decimal(str(line.get("gst_rate", line["product"].gst_rate)))
        # Allowed slab set (0–28); reject non-slab overrides like 17%.
        if gst_rate not in allowed_gst:
            raise BusinessRuleError(
                f"Invalid GST rate {gst_rate}. Allowed: {', '.join(ALLOWED_GST_RATES)}%.",
                code=HelpCode.INVALID_GST_RATE,
            )
        product = line["product"]
        if product.company_id != company.id:
            raise BusinessRuleError("Invalid product reference.")
        if check_active and product.status != Product.Status.ACTIVE:
            raise BusinessRuleError(
                f"Cannot sell inactive product '{product.name}'.",
                code=HelpCode.INACTIVE_PRODUCT,
            )


def apply_tcs_fold(invoice) -> None:
    """Fold TCS into grand_total. 206C(1H) is levied on sale consideration.

    Precedence (owner decision 2026-08-31): an operator-supplied ``tcs_amount``
    that has **not** yet been system-folded wins over the rate — a CA / portal
    reconciliation may pass a specific figure (rounding adjustment, collection
    notice). The rate only auto-computes ``tcs_amount`` when none was supplied,
    or on a re-fold of a prior system computation. When an override diverges
    from the rate result, both figures are recorded on ``invoice._tcs_override``
    for the COMPLETE audit event. Unfold any prior fold first so amend/complete
    stays idempotent and credit-limit sees the TCS-inclusive total.
    """
    two = Decimal("0.01")
    prior = Decimal(str(getattr(invoice, "tcs_amount", 0) or 0))
    already_folded = bool(getattr(invoice, "tcs_in_grand_total", False)) and prior > 0
    if already_folded:
        invoice.grand_total = (Decimal(str(invoice.grand_total or 0)) - prior).quantize(two)
        invoice.tcs_in_grand_total = False

    tcs_rate = Decimal(str(getattr(invoice, "tcs_rate", 0) or 0))
    consideration = (
        Decimal(str(invoice.taxable_total or 0))
        + Decimal(str(invoice.cgst_total or 0))
        + Decimal(str(invoice.sgst_total or 0))
        + Decimal(str(invoice.igst_total or 0))
        + Decimal(str(getattr(invoice, "cess_total", 0) or 0))
    )
    rate_amount = (
        (consideration * tcs_rate / Decimal("100")).quantize(two) if tcs_rate > 0 else Decimal("0")
    )

    invoice._tcs_override = None
    manual = bool(getattr(invoice, "tcs_amount_manual", False))
    if manual and prior > 0:
        # Operator-supplied amount — wins over the rate on every fold pass,
        # including a re-fold after a prior system fold (already_folded).
        explicit = prior
    else:
        explicit = prior if (prior > 0 and not already_folded and not manual) else None
    if explicit is not None:
        invoice.tcs_amount = explicit
        if tcs_rate > 0 and rate_amount != explicit:
            invoice._tcs_override = {
                "provided_amount": str(explicit),
                "calculated_rate_amount": str(rate_amount),
                "tcs_rate": str(tcs_rate),
                "consideration": str(consideration),
            }
    elif tcs_rate > 0:
        invoice.tcs_amount = rate_amount
    else:
        invoice.tcs_amount = Decimal("0")

    if invoice.tcs_amount:
        invoice.grand_total = (Decimal(str(invoice.grand_total or 0)) + invoice.tcs_amount).quantize(two)
        invoice.tcs_in_grand_total = True
    else:
        invoice.tcs_in_grand_total = False


def _resolve_source_item(line, company_id, invoice_id=None):
    """Resolve and tenant-check a CN/DN source SalesItem, or return None."""
    source_item = line.get("source_item")
    if source_item is None and line.get("source_item_id") is not None:
        source_item = line.get("source_item_id")
    if source_item is None:
        return None
    if isinstance(source_item, (int, str)):
        try:
            item = SalesItem.objects.get(
                pk=int(source_item),
                invoice__company_id=company_id,
            )
        except (SalesItem.DoesNotExist, TypeError, ValueError) as exc:
            raise BusinessRuleError(
                "source_item does not belong to this company."
            ) from exc
        if invoice_id is not None and item.invoice_id != invoice_id:
            raise BusinessRuleError("source_item does not belong to this invoice.")
        return item
    if getattr(source_item, "invoice_id", None) is not None:
        if not SalesItem.objects.filter(
            pk=source_item.pk, invoice__company_id=company_id
        ).exists():
            raise BusinessRuleError(
                "source_item does not belong to this company."
            )
        if invoice_id is not None and source_item.invoice_id != invoice_id:
            raise BusinessRuleError("source_item does not belong to this invoice.")
    return source_item


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
        from core.services.uqc import snapshot_unit_fields

        source_item = None
        if model_cls in (SalesCreditNoteItem, SalesDebitNoteItem):
            source_item = _resolve_source_item(
                line, parent.company_id, invoice_id=getattr(parent, "sales_invoice_id", None)
            )
            if source_item is None and getattr(parent, "sales_invoice_id", None):
                matches = list(
                    SalesItem.objects.filter(
                        invoice_id=parent.sales_invoice_id, product=product
                    )
                )
                if len(matches) == 1:
                    source_item = matches[0]
                else:
                    raise BusinessRuleError(
                        "GST credit/debit note lines must reference a source invoice item "
                        "(source_item) so rates match the original invoice."
                    )

        if source_item is not None:
            # GST rate always comes from the linked invoice line.
            gst_rate = source_item.gst_rate
            cess_rate = getattr(source_item, "cess_rate", None) or Decimal("0")
            cess_amount = getattr(source_item, "cess_amount", None) or Decimal("0")
            discount_percent = source_item.discount_percent
            applied_list_name = ""
            if model_cls in (SalesDebitNoteItem, SalesCreditNoteItem) and line.get("unit_price") is not None:
                unit_price = Decimal(str(line["unit_price"]))
            else:
                unit_price = source_item.unit_price
        else:
            from masters.pricing import resolve_party_price, resolve_unit_price

            unit_price = resolve_unit_price(
                customer=getattr(parent, "customer", None),
                product=product,
                requested_price=line.get("unit_price", None),
                role=getattr(parent, "_price_role", None),
                quantity=line.get("quantity"),
            )
            discount_percent = line.get("discount_percent", Decimal("0"))
            gst_rate = line.get("gst_rate", product.gst_rate)
            cess_rate = line.get("cess_rate", Decimal("0"))
            cess_amount = line.get("cess_amount", Decimal("0"))
            _list_price, applied_list_name = resolve_party_price(
                customer=getattr(parent, "customer", None),
                product=product,
                quantity=line.get("quantity"),
            )

        kwargs = {
            parent_field: parent,
            "company_id": parent.company_id,
            "product": product,
            "description": line.get("description") or product.name,
            "quantity": line["quantity"],
            "unit_price": unit_price,
            "discount_percent": discount_percent,
            "gst_rate": gst_rate,
            "cess_rate": cess_rate,
            "cess_amount": cess_amount,
        }
        if model_cls is SalesItem:
            kwargs["applied_price_list_name"] = applied_list_name
        if model_cls in (SalesItem, SalesCreditNoteItem, SalesDebitNoteItem):
            nature = line.get("supply_nature")
            if source_item is not None:
                nature = getattr(source_item, "supply_nature", None) or nature
            nature = (nature or "TAXABLE").upper()
            if nature in ("NIL", "EXEMPT", "NON_GST"):
                kwargs["gst_rate"] = Decimal("0")
            kwargs["supply_nature"] = nature if nature in ("TAXABLE", "NIL", "EXEMPT", "NON_GST") else "TAXABLE"

        # Snapshot HSN/UQC onto GST filing lines (invoice + CN/DN).
        if model_cls in (SalesItem, SalesCreditNoteItem, SalesDebitNoteItem):
            snap = snapshot_unit_fields(product, line)
            if source_item is not None:
                if getattr(source_item, "hsn_code", None):
                    snap["hsn_code"] = source_item.hsn_code or snap["hsn_code"]
                if getattr(source_item, "unit_name", None):
                    snap["unit_name"] = source_item.unit_name or snap["unit_name"]
                if getattr(source_item, "uqc_code", None):
                    snap["uqc_code"] = source_item.uqc_code or snap["uqc_code"]
            kwargs.update(snap)
            if model_cls is SalesItem:
                inclusive = line.get("unit_price_inclusive")
                kwargs.update({
                    "batch": line.get("batch"),
                    "mrp": line.get("mrp", product.mrp or Decimal("0")),
                    "unit_price_inclusive": (
                        Decimal(str(inclusive)) if inclusive is not None else None
                    ),
                    "batch_no": line.get("batch_no") or "",
                    "exp_date": line.get("exp_date"),
                    "mfg_date": line.get("mfg_date"),
                    "serial_numbers": line.get("serial_numbers") or [],
                    "rate_override": bool(line.get("rate_override")),
                    "rate_override_reason": (line.get("rate_override_reason") or "")[:255],
                })
        from sales.models import DeliveryChallanItem

        if model_cls is DeliveryChallanItem:
            kwargs["serial_numbers"] = line.get("serial_numbers") or []
            kwargs["batch"] = line.get("batch")
            kwargs["batch_no"] = line.get("batch_no") or ""
        # BB-000340: SalesReturnItem is not in the GST snapshot tuple — serials must still persist.
        if model_cls is SalesReturnItem:
            kwargs["serial_numbers"] = line.get("serial_numbers") or []
            kwargs["condition"] = line.get("condition") or SalesReturnItem.Condition.SELLABLE
        items.append(model_cls(**kwargs))
    return items


def _tax_enabled(invoice_type):
    return invoice_type != SalesInvoice.InvoiceType.NON_GST


def _lot_identity_key(item) -> tuple:
    """Product + lot + serials. Batch identity is the batch_no, not the FK pk."""
    batch_no = (getattr(item, "batch_no", None) or "").strip()
    if not batch_no:
        batch = getattr(item, "batch", None)
        if batch is not None:
            batch_no = (getattr(batch, "batch_no", None) or "").strip()
    serials = tuple(
        sorted(str(s).strip() for s in (getattr(item, "serial_numbers", None) or []) if str(s).strip())
    )
    return (item.product_id, batch_no, serials)


def assert_converted_challan_lot_identity(invoice, items) -> None:
    """C-02: converted invoice lines must match remaining challan product+batch+serial qty."""
    from sales.models import DeliveryChallan, DeliveryChallanItem

    challan_ids = list(
        DeliveryChallan.objects.filter(converted_invoice=invoice).values_list("pk", flat=True)
    )
    if not challan_ids:
        return
    posted = defaultdict(Decimal)
    for row in DeliveryChallanItem.objects.filter(challan_id__in=challan_ids):
        posted[_lot_identity_key(row)] += Decimal(str(row.quantity or 0))
    inv_qty = defaultdict(Decimal)
    for item in items:
        inv_qty[_lot_identity_key(item)] += Decimal(str(item.quantity or 0))
    if set(posted.keys()) != set(inv_qty.keys()) or any(posted[key] != inv_qty[key] for key in inv_qty):
        raise BusinessRuleError(
            "Invoice product, batch, and serials must match the converted delivery challan."
        )


def _update_items_in_place(invoice: SalesInvoice, items_data):
    """
    Update existing SalesItem rows in place (match by id, else product).
    Preserves PKs so credit/debit note source_item FKs remain valid.
    """
    from masters.pricing import resolve_unit_price

    existing = list(invoice.items.select_related("product").all())
    by_id = {i.id: i for i in existing}
    by_product: dict[int, list] = {}
    for i in existing:
        by_product.setdefault(i.product_id, []).append(i)

    used_ids: set[int] = set()
    items = []
    for line in items_data:
        product = line["product"]
        product_id = product.pk if hasattr(product, "pk") else int(product)
        old = None
        line_id = line.get("id")
        if line_id is not None:
            try:
                line_id = int(line_id)
            except (TypeError, ValueError):
                line_id = None
        if line_id is not None and line_id in by_id and line_id not in used_ids:
            old = by_id[line_id]
            used_ids.add(line_id)
        else:
            bucket = by_product.get(product_id) or []
            while bucket:
                candidate = bucket.pop(0)
                if candidate.id in used_ids:
                    continue
                old = candidate
                used_ids.add(candidate.id)
                break
        if old is None:
            raise BusinessRuleError(
                "Completed invoice amend cannot add or rematch lines; "
                "use a credit/debit note instead."
            )
        if old.product_id != product_id:
            raise BusinessRuleError(
                "Completed invoice amend cannot change products; "
                "use a credit/debit note instead."
            )

        unit_price = resolve_unit_price(
            customer=getattr(invoice, "customer", None),
            product=old.product,
            requested_price=line.get("unit_price", old.unit_price),
            role=getattr(invoice, "_price_role", None),
            quantity=line.get("quantity", old.quantity),
        )
        old.description = line.get("description") or old.description or old.product.name
        old.quantity = line["quantity"]
        old.unit_price = unit_price
        if hasattr(old, "applied_price_list_name"):
            from masters.pricing import resolve_party_price

            _p, name = resolve_party_price(
                customer=getattr(invoice, "customer", None),
                product=old.product,
                quantity=line.get("quantity", old.quantity),
            )
            old.applied_price_list_name = name
        old.discount_percent = line.get("discount_percent", old.discount_percent)
        old.gst_rate = line.get("gst_rate", old.gst_rate)
        if "supply_nature" in line or hasattr(old, "supply_nature"):
            nature = (line.get("supply_nature") or getattr(old, "supply_nature", None) or "TAXABLE").upper()
            if nature in ("NIL", "EXEMPT", "NON_GST"):
                old.gst_rate = Decimal("0")
            if hasattr(old, "supply_nature"):
                old.supply_nature = nature if nature in ("TAXABLE", "NIL", "EXEMPT", "NON_GST") else "TAXABLE"
        old.cess_rate = line.get("cess_rate", getattr(old, "cess_rate", Decimal("0")))
        if hasattr(old, "cess_amount"):
            old.cess_amount = line.get("cess_amount", getattr(old, "cess_amount", Decimal("0")))
        if "unit_price_inclusive" in line:
            inclusive = line.get("unit_price_inclusive")
            old.unit_price_inclusive = (
                Decimal(str(inclusive)) if inclusive is not None else None
            )
        items.append(old)

    orphan_ids = [i.id for i in existing if i.id not in used_ids]
    if orphan_ids:
        raise BusinessRuleError(
            "Completed invoice amend cannot remove lines; "
            "use a credit/debit note instead."
        )
    return items


class SalesService:
    # ---------------- Sales invoice ----------------

    @staticmethod
    def _sale_batches(invoice, item):
        """Resolve an explicit batch or allocate the issue across FEFO lots."""
        from inventory.item_stock import base_quantity

        qty = base_quantity(item.product, item.quantity, getattr(item, "unit_name", None))
        if not item.product.track_batch:
            return [(getattr(item, "batch", None), qty)]
        batch = getattr(item, "batch", None)
        batch_id = getattr(item, "batch_id", None)
        batch_no = getattr(item, "batch_no", "") or ""
        if batch_id is None and batch_no:
            try:
                batch = BatchLot.objects.get(
                    company=invoice.company, product=item.product, batch_no=batch_no
                )
                if hasattr(item, "batch"):
                    item.batch = batch
            except BatchLot.DoesNotExist as exc:
                raise BusinessRuleError(
                    f"Unknown batch '{batch_no}' for '{item.product.name}'."
                ) from exc
        if batch_id or batch is not None:
            return [(batch or item.batch, qty)]

        remaining = qty
        allocations = []
        warehouse = getattr(invoice, "warehouse", None)
        for lot in InventoryValuationService.fefo_batches(
            invoice.company, item.product, warehouse
        ):
            available = InventoryService.available_quantity(
                invoice.company, item.product, warehouse, lot
            )
            take = min(remaining, available)
            if take > 0:
                allocations.append((lot, take))
                remaining -= take
            if remaining <= 0:
                break
        if not allocations:
            raise BusinessRuleError(f"No stock batch is available for '{item.product.name}'.")
        if hasattr(item, "batch") and hasattr(item, "save"):
            item.batch = allocations[0][0]
            if hasattr(item, "batch_no"):
                item.batch_no = item.batch.batch_no
                item.save(update_fields=["batch", "batch_no"])
            else:
                item.save(update_fields=["batch"])
        if remaining > 0:
            raise BusinessRuleError(
                f"Insufficient batched stock for '{item.product.name}': {remaining} unavailable."
            )
        return allocations

    @staticmethod
    @transaction.atomic
    def set_items(invoice: SalesInvoice, items_data, user):
        if invoice.status in (SalesInvoice.Status.CANCELLED, SalesInvoice.Status.RETURNED):
            raise BusinessRuleError("Cancelled/returned invoice cannot be line-edited.")
        if invoice.status not in (SalesInvoice.Status.DRAFT, SalesInvoice.Status.COMPLETED):
            raise BusinessRuleError(f"Cannot edit invoice in status {invoice.status}.")

        old_qty = defaultdict(Decimal)
        adjust_stock = invoice.status == SalesInvoice.Status.COMPLETED
        # BUG-213: snapshot pre-edit totals so a completed-document edit
        # leaves a real diff in the audit log, not just a bare "UPDATE".
        old_totals = {
            "grand_total": str(invoice.grand_total), "taxable_total": str(invoice.taxable_total),
            "tax_total": str(invoice.cgst_total + invoice.sgst_total + invoice.igst_total),
        } if adjust_stock else None
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
            # BB-000721: H9 qty amend on batch/serial-tracked SKUs risks FIFO/serial
            # desync — refuse rather than posting bare SALE/ADJUSTMENT.
            for product_id in set(old_qty) | set(new_qty_preview):
                delta = new_qty_preview.get(product_id, Decimal("0")) - old_qty.get(
                    product_id, Decimal("0")
                )
                if delta == 0:
                    continue
                product = next(
                    (line["product"] for line in items_data if line["product"].pk == product_id),
                    None,
                ) or Product.objects.get(pk=product_id)
                if product.track_serial or product.track_batch:
                    raise BusinessRuleError(
                        f"Cannot amend quantity on completed invoices for batch/serial-tracked "
                        f"product '{product.name}'. Use a credit note or sales return instead."
                    )
            # Extra stock sold on edit must pass negative-stock policy.
            for product_id, new_q in new_qty_preview.items():
                delta = new_q - old_qty.get(product_id, Decimal("0"))
                if delta > 0:
                    product = next(
                        (line["product"] for line in items_data if line["product"].pk == product_id),
                        None,
                    ) or Product.objects.get(pk=product_id)
                    InventoryService.check_negative_stock(invoice.company, product, delta, invoice.warehouse)

        if adjust_stock:
            # H9-A: update existing lines in place so CN/DN source_item FKs stay valid.
            items = _update_items_in_place(invoice, items_data)
        else:
            invoice.items.all().delete()
            items = _build_items(SalesItem, "invoice", invoice, items_data)

        compute_document_totals(
            invoice, items,
            tax_enabled=_tax_enabled(invoice.invoice_type),
            intra_state=party_intra_state(
                invoice.company,
                invoice.customer.state,
                invoice.customer.gstin or "",
                seller_state=(getattr(invoice.company_gstin, "state", None) or ""),
                seller_gstin=(getattr(invoice.company_gstin, "gstin", None) or ""),
            ),
            additional_charges=invoice.additional_charges,
            invoice_discount=invoice.invoice_discount,
            auto_round_off=invoice.auto_round_off,
            invoice_discount_mode=getattr(invoice, "invoice_discount_mode", None),
        )
        apply_rcm_memo_after_tax(invoice, items)
        apply_tcs_fold(invoice)
        if adjust_stock:
            for item in items:
                item.save()
        else:
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
                        warehouse=invoice.warehouse,
                        product=product,
                        movement_type=MovementType.SALE,
                        quantity=delta,
                        reference_type="sales_invoice",
                        reference_id=invoice.pk,
                        user=user,
                    )
                else:
                    restore_cost = InventoryValuationService.unit_cost(
                        invoice.company, product, warehouse=invoice.warehouse
                    )
                    InventoryService.post_movement(
                        company=invoice.company,
                        warehouse=invoice.warehouse,
                        product=product,
                        movement_type=MovementType.ADJUSTMENT,
                        quantity=-delta,
                        unit_cost=restore_cost,
                        reference_type="sales_invoice_edit",
                        reference_id=invoice.pk,
                        reason=f"Edit of {invoice.number or invoice.pk}",
                        user=user,
                    )
            invoice.pdf_status = SalesInvoice.PdfStatus.QUEUED
            invoice.updated_by = user
            invoice.save()
            emit(
                "sales_invoice.edited",
                invoice=invoice,
                user=user,
                old_totals=old_totals,
                amend=True,
            )
            from core.models import StatutoryDocumentEvent, log_statutory_event

            log_statutory_event(
                company=invoice.company,
                entity_type="sales_invoice",
                entity_id=invoice.pk,
                event_type=StatutoryDocumentEvent.EventType.AMEND,
                payload={"number": invoice.number, "old_totals": old_totals},
                user=user,
            )
            # Do not re-emit sales_invoice.completed (would re-fire first-complete
            # handlers). Queue PDF regeneration explicitly after amend.
            from django.conf import settings as django_settings

            from .tasks import generate_invoice_pdf

            invoice_id = invoice.pk
            company_id = invoice.company_id
            if django_settings.CELERY_TASK_ALWAYS_EAGER:
                generate_invoice_pdf.delay(invoice_id, company_id=company_id)
            else:
                transaction.on_commit(
                    lambda: generate_invoice_pdf.delay(invoice_id, company_id=company_id)
                )
            return invoice

        invoice.updated_by = user
        invoice.save()
        return invoice

    @staticmethod
    @transaction.atomic
    def complete(invoice: SalesInvoice, user, *, confirm_sales_rcm=False, confirm_blank_pos=False,
                 confirm_gstin_total_change=False):
        """Atomic Complete: rules + number + SALE movements + PDF event (E4.4)."""
        invoice = SalesInvoice.objects.select_for_update().get(pk=invoice.pk)
        if invoice.warehouse_id is None:
            invoice.warehouse = InventoryService.default_warehouse(invoice.company)
        # BB-000708: fail closed when multi-GSTIN and stamp unset; else stamp only single active.
        if invoice.company_gstin_id is None:
            from accounts.models import CompanyGstin

            active = list(
                CompanyGstin.objects.filter(company=invoice.company, is_active=True).order_by(
                    "-is_primary", "id"
                )
            )
            if len(active) > 1:
                raise BusinessRuleError(
                    "company_gstin is required when multiple GSTINs are active.",
                    code=HelpCode.COMPANY_GSTIN_REQUIRED,
                )
            if len(active) == 1:
                invoice.company_gstin = active[0]
            # Zero active: leave unset (legacy company.gstin-only tenants).
        if invoice.status != SalesInvoice.Status.DRAFT:
            raise BusinessRuleError(f"Cannot complete an invoice in status {invoice.status}.")
        if invoice.customer.status == Customer.Status.BLOCKED:
            raise BusinessRuleError(
                "Cannot create an invoice for a blocked customer.",
                code=HelpCode.BLOCKED_CUSTOMER,
            )
        items = list(invoice.items.select_related("product", "batch"))
        if not items:
            raise BusinessRuleError("Cannot complete an invoice without line items.")

        tax_enabled = _tax_enabled(invoice.invoice_type)
        assert_may_issue_gst_tax_invoice(invoice.company, tax_enabled=tax_enabled)

        # BB-000264: opening bypass only via internal flag, never user-writable notes magic.
        if (invoice.notes or "").strip() == "TALLY_OPENING" and not getattr(
            invoice, "is_opening_balance", False
        ):
            raise BusinessRuleError(
                "TALLY_OPENING notes are not accepted. Opening invoices must be imported via Tally adapter."
            )
        is_tally_opening = bool(getattr(invoice, "is_opening_balance", False))

        from core.services.billing import place_of_supply_known

        if (
            tax_enabled
            and not is_tally_opening
            and not is_export_or_sez_supply(invoice.supply_type or "")
            and not place_of_supply_known(
                party_state=invoice.customer.state or "",
                party_gstin=invoice.customer.gstin or "",
            )
            and not confirm_blank_pos
        ):
            raise BusinessRuleError(
                "Place of supply is blank. Confirm this sale is intra-state, or set the customer state/GSTIN.",
                code=HelpCode.PLACE_OF_SUPPLY_UNRESOLVED,
            )

        # R2-001 / W0-02: recompute tax against the stamped filing GSTIN.
        recompute_totals_for_stamped_gstin(
            invoice,
            items,
            party_state=invoice.customer.state,
            party_gstin=invoice.customer.gstin or "",
            tax_enabled=tax_enabled,
            item_model=SalesItem,
            confirm_gstin_total_change=confirm_gstin_total_change,
            is_opening=is_tally_opening,
        )

        tax_left = (
            Decimal(str(invoice.cgst_total or 0))
            + Decimal(str(invoice.sgst_total or 0))
            + Decimal(str(invoice.igst_total or 0))
            + Decimal(str(getattr(invoice, "cess_total", 0) or 0))
        )
        if invoice.is_reverse_charge and tax_left > 0:
            apply_rcm_memo_after_tax(invoice, items)
            SalesItem.objects.bulk_update(
                items, ["cgst", "sgst", "igst", "cess", "line_total"]
            )
        apply_tcs_fold(invoice)
        customer = Customer.objects.select_for_update().get(pk=invoice.customer_id)
        limit = customer.credit_limit or Decimal("0")
        if limit > 0 and not is_tally_opening:
            exposure = LedgerService.customer_exposure_for_credit_limit(
                invoice.company, customer
            )
            projected = exposure + invoice.grand_total
            if projected > limit:
                raise BusinessRuleError(
                    f"Credit limit exceeded. Exposure {exposure} + invoice "
                    f"{invoice.grand_total} > limit {limit}.",
                    code=HelpCode.CREDIT_LIMIT_EXCEEDED,
                )

        assert_place_of_supply_for_gst(
            company=invoice.company,
            party_state=customer.state or "",
            party_gstin=customer.gstin or "",
            tax_enabled=tax_enabled,
            supply_type=invoice.supply_type or "",
        )

        supply = (invoice.supply_type or "").strip().upper()
        line_gst = sum(
            (
                Decimal(str(it.cgst or 0)) + Decimal(str(it.sgst or 0)) + Decimal(str(it.igst or 0))
                for it in items
            ),
            Decimal("0"),
        )
        if supply in ("SEZWOP", "EXPWOP") and line_gst > 0:
            raise BusinessRuleError(
                f"{supply} invoices must be zero-GST (without payment of tax)."
            )
        if supply in ("SEZWP", "EXPWP") and any(
            Decimal(str(it.cgst or 0)) + Decimal(str(it.sgst or 0)) > 0 for it in items
        ):
            raise BusinessRuleError(
                f"{supply} invoices must use IGST only (with payment of tax)."
            )

        # BB-000038/BB-000361: AFTER_TAX cash discount on any B2B GST-bearing
        # invoice type (GST/TAX/RETAIL — not just InvoiceType.GST) breaks the
        # GSTR invoice-value identity whenever the party has a GSTIN.
        from reporting.gst_returns import GST_INVOICE_TYPES

        if (
            tax_enabled
            and invoice.invoice_type in GST_INVOICE_TYPES
            and (customer.gstin or "").strip()
            and (invoice.invoice_discount or Decimal("0")) != 0
            and invoice.invoice_discount_mode == SalesInvoice.DiscountMode.AFTER_TAX
        ):
            raise BusinessRuleError(
                "B2B GST invoices cannot use AFTER_TAX invoice discount. "
                "Use BEFORE_TAX discount or issue a credit note after completion."
            )

        if invoice.is_reverse_charge and not confirm_sales_rcm:
            raise BusinessRuleError(
                "Sales reverse charge must be explicitly confirmed "
                "(confirm_sales_rcm=true) before Complete.",
                code=HelpCode.SALES_RCM_UNCONFIRMED,
            )

        warnings = []
        if tax_enabled:
            missing_hsn = [i for i in items if not (i.hsn_code or "").strip()]
            if missing_hsn:
                warnings.append(
                    f"{len(missing_hsn)} line(s) missing HSN — GSTR Table 12 / e-Invoice may fail."
                )
            from reporting.gst_health import hsn_digits_insufficient_for_turnover

            short_hsn = [
                i for i in items
                if (i.hsn_code or "").strip()
                and hsn_digits_insufficient_for_turnover(
                    i.hsn_code,
                    getattr(invoice.company, "aato_turnover", None),
                    is_b2b=bool((customer.gstin or "").strip()),
                )
            ]
            if short_hsn:
                warnings.append(
                    f"{len(short_hsn)} line(s) have HSN shorter than 6 digits — "
                    "may be insufficient for current AATO / GSTR Table 12."
                )
            if (
                invoice.invoice_type in GST_INVOICE_TYPES
                and (customer.gstin or "").strip()
                and (invoice.additional_charges or Decimal("0")) != 0
            ):
                from core.services.charges import charges_are_taxable

                if not charges_are_taxable(invoice):
                    warnings.append(
                        "B2B GST invoice has additional charges outside taxable value — "
                        "set charges HSN and GST rate, or invoice value may not reconcile for GSTR."
                    )
            # TAX-10: soft warning when taxable invoice meets e-Way threshold without e-Way.
            eway_threshold = getattr(invoice.company, "eway_threshold_amount", None) or Decimal(
                "50000"
            )
            if (
                invoice.grand_total >= Decimal(str(eway_threshold))
                and getattr(invoice, "eway_status", None)
                != SalesInvoice.EwayStatus.GENERATED
            ):
                warnings.append(
                    f"Invoice total ≥ ₹{eway_threshold}: e-Way Bill may be required — "
                    "generate before goods movement if applicable."
                )
        # C-02: converted challan lots must match even when stock posted on the challan.
        from .models import DeliveryChallan

        assert_converted_challan_lot_identity(invoice, items)
        stock_from_challan = DeliveryChallan.objects.filter(
            converted_invoice=invoice, stock_posted=True
        ).exists()
        # Aggregate per product for the negative-stock check.
        required = defaultdict(Decimal)
        for item in items:
            if item.product.status != Product.Status.ACTIVE:
                raise BusinessRuleError(
                    f"Cannot sell inactive product '{item.product.name}'.",
                    code=HelpCode.INACTIVE_PRODUCT,
                )
            if item.quantity <= 0:
                raise BusinessRuleError("Quantity on each line must be greater than zero.")
            required[item.product] += item.quantity
        if not stock_from_challan:
            for product, qty in required.items():
                warning = InventoryService.check_negative_stock(
                    invoice.company, product, qty, invoice.warehouse
                )
                if warning:
                    warnings.append(warning)

        stamp = invoice.company_gstin
        if stamp is None:
            from accounts.models import CompanyGstin

            stamp = (
                CompanyGstin.objects.filter(company=invoice.company, is_primary=True, is_active=True)
                .order_by("-id")
                .first()
            ) or CompanyGstin.objects.filter(company=invoice.company, is_active=True).order_by("id").first()
            if stamp is not None:
                invoice.company_gstin = stamp
        # R1-013: series scoping comes from the company policy, not from whether
        # a gstin happened to resolve here.
        from core.services.document_numbers import series_identity

        _gk, _fy, _on = series_identity(invoice.company, stamp, invoice.invoice_date)
        fy_warn = DocumentNumberService.fy_restart_warning(
            invoice.company, "SALES_INVOICE", gstin_key=_gk or "", fy_label=_fy or ""
        )
        invoice.number = invoice.number or DocumentNumberService.next_number(
            invoice.company,
            "SALES_INVOICE",
            gstin=_gk or None,
            on_date=_on,
        )
        if fy_warn:
            warnings.append(fy_warn)
        if not (invoice.filing_party_gstin or "").strip():
            invoice.filing_party_gstin = (invoice.customer.gstin or "").strip().upper()
        if not (invoice.filing_place_of_supply or "").strip():
            # Export/SEZ → POS 96 before normal party/seller resolution.
            stamp = invoice.company_gstin
            resolved_code = resolve_place_of_supply_code(
                party_state=invoice.customer.state or "",
                party_gstin=invoice.filing_party_gstin or (invoice.customer.gstin or ""),
                supply_type=invoice.supply_type or "",
                company=invoice.company,
                seller_gstin=getattr(stamp, "gstin", None) or "",
                seller_state=getattr(stamp, "state", None) or "",
            )
            if not resolved_code and not is_export_or_sez_supply(invoice.supply_type) and tax_enabled:
                raise BusinessRuleError(
                    f"Cannot determine a valid GST place-of-supply state code for customer "
                    f"'{invoice.customer.name}' (state '{invoice.customer.state or ''}' is not a recognised "
                    "Indian state/UT). Set the customer's GSTIN or a valid state before completing."
                )
            invoice.filing_place_of_supply = resolved_code or (invoice.customer.state or "").strip()
        apply_tcs_fold(invoice)
        invoice.status = SalesInvoice.Status.COMPLETED
        invoice.completed_at = timezone.now()
        invoice.pdf_status = (
            SalesInvoice.PdfStatus.NONE if is_tally_opening else SalesInvoice.PdfStatus.QUEUED
        )
        invoice.updated_by = user
        invoice.save()

        from .cogs_service import CogsService

        cogs_total = Decimal("0")
        if not is_tally_opening:
            cogs_total = CogsService.post_sale_stock_and_cogs(
                invoice, items, user, stock_from_challan=stock_from_challan, warnings=warnings
            )
        # BB-000699: period gate must abort atomic Complete (no except-pass swallow).
        if not is_tally_opening:
            from reporting.gst_periods import assert_period_allows_money_amend, mark_period_dirty_if_snapshotted

            assert_period_allows_money_amend(invoice.company, invoice.invoice_date)
            mark_period_dirty_if_snapshotted(invoice.company, invoice.invoice_date)

        if not is_tally_opening:
            if invoice.company.accounting_enabled:
                from accounting.services import PostingService

                PostingService.post_sales_invoice(invoice, user)
                PostingService.post_sales_cogs(invoice, cogs_total, user)
            emit("document.completed", document=invoice, user=user, event="sales_invoice.completed")
            emit("sales_invoice.completed", invoice=invoice, user=user)
            from core.models import StatutoryDocumentEvent, log_statutory_event

            _complete_payload = {"number": invoice.number, "grand_total": str(invoice.grand_total)}
            if getattr(invoice, "_tcs_override", None):
                _complete_payload["tcs_override"] = invoice._tcs_override
            log_statutory_event(
                company=invoice.company,
                entity_type="sales_invoice",
                entity_id=invoice.pk,
                event_type=StatutoryDocumentEvent.EventType.COMPLETE,
                payload=_complete_payload,
                user=user,
            )
        else:
            # BB-000381: opening AR vs equity when books enabled.
            if invoice.company.accounting_enabled:
                from accounting.services import PostingService

                PostingService.post_opening_sales_invoice(invoice, user)
        return invoice, warnings

    @staticmethod
    @transaction.atomic
    def cancel(invoice: SalesInvoice, user, *, reason: str = ""):
        invoice = SalesInvoice.objects.select_for_update().get(pk=invoice.pk)
        from reporting.gst_periods import assert_period_allows_money_amend

        assert_period_allows_money_amend(invoice.company, invoice.invoice_date, allow_soft_closed=True)
        if invoice.status == SalesInvoice.Status.CANCELLED:
            raise BusinessRuleError("Invoice is already cancelled.")
        if invoice.returns.filter(status=SalesReturn.Status.COMPLETED).exists():
            # Fully returned invoices are status RETURNED and always have completed
            # returns, so they never reach stock restore below.
            raise BusinessRuleError("Cannot cancel an invoice with completed returns.")
        # R2-005: a DRAFT / in-progress return would be orphaned against a
        # cancelled invoice — make the user clear it first.
        if invoice.returns.exclude(
            status__in=(SalesReturn.Status.COMPLETED, SalesReturn.Status.CANCELLED)
        ).exists():
            raise BusinessRuleError(
                "Cancel or delete the draft sales return(s) against this invoice first."
            )
        if invoice.allocations.filter(reversed_at__isnull=True).exists():
            # BUG-722: cancelling a paid/partially-paid invoice would leave
            # payment allocations pointing at a document that's no longer
            # completed — the ledger has no defined meaning for that.
            raise BusinessRuleError(
                "Cannot cancel an invoice with payment allocations against it. "
                "Remove the allocation(s) first."
            )

        if invoice.status in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED):
            if invoice.company.accounting_enabled:
                from accounting.models import JournalEntry
                from accounting.services import PostingService

                for entry in JournalEntry.objects.filter(
                    company=invoice.company, source_type="SALES_INVOICE", source_id=invoice.id,
                    status=JournalEntry.Status.POSTED,
                ):
                    # R2-004: reversal is a fresh event — post it on the
                    # cancellation date (current open period), never back-date
                    # into the original (possibly soft-closed) period.
                    PostingService.reverse(entry, user)
            # Restore only if this invoice posted SALE movements (skip when stock
            # was already issued on a linked delivery challan).
            posted_sale = StockMovement.objects.filter(
                company=invoice.company,
                movement_type=MovementType.SALE,
                reference_type="sales_invoice",
                reference_id=str(invoice.pk),
            ).exists()
            if posted_sale:
                # BB-000321: restore per SALE movement lot (FEFO multi-batch), not line.batch only.
                for move in StockMovement.objects.filter(
                    company=invoice.company,
                    movement_type=MovementType.SALE,
                    reference_type="sales_invoice",
                    reference_id=str(invoice.pk),
                ):
                    inbound = InventoryService.post_movement(
                        company=invoice.company,
                        warehouse=move.warehouse_id and move.warehouse or invoice.warehouse,
                        product=move.product,
                        batch=move.batch,
                        movement_type=MovementType.ADJUSTMENT,
                        quantity=abs(Decimal(str(move.quantity))),
                        unit_cost=move.unit_cost,
                        reference_type="sales_invoice_cancel",
                        reference_id=invoice.pk,
                        reason=f"Cancellation of {invoice.number}",
                        user=user,
                    )
                    InventoryService.restore_fifo_peels(move, inbound)
                # BB-000401 / BB-000615: restore serials SOLD → AVAILABLE.
                from inventory.services import SerialNumberService
                from inventory.models import SerialNumber

                for item in invoice.items.select_related("product"):
                    if item.product.track_serial and item.serial_numbers:
                        SerialNumberService.transition(
                            company=invoice.company,
                            product=item.product,
                            warehouse=invoice.warehouse,
                            numbers=item.serial_numbers,
                            quantity=item.quantity,
                            source=SerialNumber.Status.SOLD,
                            target=SerialNumber.Status.AVAILABLE,
                            user=user,
                        )
            else:
                # BB-000405: challan-stocked invoice — reverse linked challan SALE lots.
                from sales.models import DeliveryChallan

                linked = DeliveryChallan.objects.filter(
                    company=invoice.company,
                    converted_invoice=invoice,
                    stock_posted=True,
                ).first()
                if linked:
                    for move in StockMovement.objects.filter(
                        company=invoice.company,
                        movement_type=MovementType.SALE,
                        reference_type="delivery_challan",
                        reference_id=str(linked.pk),
                    ):
                        inbound = InventoryService.post_movement(
                            company=invoice.company,
                            warehouse=move.warehouse,
                            product=move.product,
                            batch=move.batch,
                            movement_type=MovementType.ADJUSTMENT,
                            quantity=abs(Decimal(str(move.quantity))),
                            unit_cost=move.unit_cost,
                            reference_type="sales_invoice_cancel_challan",
                            reference_id=invoice.pk,
                            reason=f"Cancel invoice {invoice.number} / reverse challan {linked.number}",
                            user=user,
                        )
                        InventoryService.restore_fifo_peels(move, inbound)
                    # BB-000615: challan-stocked cancel must restore serials too.
                    from inventory.services import SerialNumberService
                    from inventory.models import SerialNumber

                    for item in linked.items.select_related("product"):
                        if item.product.track_serial and item.serial_numbers:
                            SerialNumberService.transition(
                                company=invoice.company,
                                product=item.product,
                                warehouse=linked.warehouse or invoice.warehouse,
                                numbers=item.serial_numbers,
                                quantity=item.quantity,
                                source=SerialNumber.Status.SOLD,
                                target=SerialNumber.Status.AVAILABLE,
                                user=user,
                            )
                    linked.stock_posted = False
                    linked.save(update_fields=["stock_posted", "updated_at"])
        invoice.status = SalesInvoice.Status.CANCELLED
        invoice.cancelled_at = timezone.now()
        invoice.updated_by = user
        invoice.save()
        # GAP-005: cancel open payment links so public pay pages cannot collect
        # against a cancelled invoice.
        from payments.models import PaymentLink, PaymentLinkStatus

        PaymentLink.objects.filter(
            company=invoice.company,
            sales_invoice=invoice,
            status__in=(
                PaymentLinkStatus.CREATED,
                PaymentLinkStatus.SENT,
                PaymentLinkStatus.PARTIALLY_PAID,
                PaymentLinkStatus.EXPIRED,
            ),
        ).update(
            status=PaymentLinkStatus.CANCELLED,
            updated_by=user,
            updated_at=timezone.now(),
        )
        emit("document.cancelled", document=invoice, user=user, event="sales_invoice.cancelled")
        from core.models import StatutoryDocumentEvent, log_statutory_event

        log_statutory_event(
            company=invoice.company,
            entity_type="sales_invoice",
            entity_id=invoice.pk,
            event_type=StatutoryDocumentEvent.EventType.CANCEL,
            payload={"number": invoice.number, "reason": (reason or "").strip()},
            user=user,
        )
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
                quotation.company,
                quotation.customer.state,
                quotation.customer.gstin or "",
                seller_state=quotation.company.state or "",
                seller_gstin=quotation.company.gstin or "",
            ),
        )
        QuotationItem.objects.bulk_create(items)
        quotation.updated_by = user
        quotation.save()
        return quotation

    @staticmethod
    @transaction.atomic
    def convert_quotation(quotation: Quotation, user, *, confirm_expired=False):
        """Quotation → draft sales invoice, preserving lines (E4.5)."""
        quotation = Quotation.objects.select_for_update().get(pk=quotation.pk)
        if quotation.status != Quotation.Status.DRAFT:
            raise BusinessRuleError(f"Cannot convert a quotation in status {quotation.status}.")
        if quotation.customer.status == Customer.Status.BLOCKED:
            raise BusinessRuleError("Cannot create an invoice for a blocked customer.")
        if quotation.valid_until and timezone.localdate() > quotation.valid_until:
            if not confirm_expired:
                raise BusinessRuleError(
                    "Quotation validity has expired. Refresh pricing or pass "
                    "confirm_expired=true to convert anyway."
                )
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
        # R2-003: carry the full line tax classification across — cess, supply
        # nature and inclusive-price fields were being dropped, silently turning
        # an inclusive / cess-bearing / exempt quotation into a plain exclusive
        # taxable invoice.
        items_data = [
            {
                "product": item.product, "description": item.description,
                "quantity": item.quantity, "unit_price": item.unit_price,
                "discount_percent": item.discount_percent, "gst_rate": item.gst_rate,
                "cess_rate": getattr(item, "cess_rate", Decimal("0")),
                "cess_amount": getattr(item, "cess_amount", Decimal("0")),
                "supply_nature": getattr(item, "supply_nature", None),
                "hsn_code": getattr(item, "hsn_code", "") or "",
                "unit_price_inclusive": getattr(item, "unit_price_inclusive", None),
            }
            for item in quotation.items.select_related("product")
        ]
        if getattr(quotation, "price_mode", None) and hasattr(invoice, "price_mode"):
            invoice.price_mode = quotation.price_mode
            invoice.save(update_fields=["price_mode"])
        SalesService.set_items(invoice, items_data, user)
        quotation.status = Quotation.Status.CONVERTED
        quotation.converted_invoice = invoice
        quotation.updated_by = user
        quotation.save()
        return invoice

    @staticmethod
    @transaction.atomic
    def convert_quotation_to_order(quotation: Quotation, user, *, confirm_expired=False):
        """Quotation → draft sales order, preserving lines."""
        from .models import SalesOrder
        from .notes_services import SalesNotesService

        quotation = Quotation.objects.select_for_update().get(pk=quotation.pk)
        if quotation.status != Quotation.Status.DRAFT:
            raise BusinessRuleError(f"Cannot convert a quotation in status {quotation.status}.")
        if quotation.customer.status == Customer.Status.BLOCKED:
            raise BusinessRuleError("Cannot create an order for a blocked customer.")
        if quotation.valid_until and timezone.localdate() > quotation.valid_until:
            if not confirm_expired:
                raise BusinessRuleError(
                    "Quotation validity has expired. Refresh pricing or pass "
                    "confirm_expired=true to convert anyway."
                )
        if not quotation.number:
            quotation.number = DocumentNumberService.next_number(quotation.company, "QUOTATION")

        order = SalesOrder.objects.create(
            company=quotation.company,
            customer=quotation.customer,
            invoice_type=quotation.invoice_type,
            notes=quotation.notes,
            created_by=user,
            updated_by=user,
        )
        # R2-003: keep cess / supply nature / inclusive fields on conversion.
        items_data = [
            {
                "product": item.product,
                "description": item.description,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "discount_percent": item.discount_percent,
                "gst_rate": item.gst_rate,
                "cess_rate": getattr(item, "cess_rate", Decimal("0")),
                "cess_amount": getattr(item, "cess_amount", Decimal("0")),
                "supply_nature": getattr(item, "supply_nature", None),
                "hsn_code": getattr(item, "hsn_code", "") or "",
                "unit_price_inclusive": getattr(item, "unit_price_inclusive", None),
            }
            for item in quotation.items.select_related("product")
        ]
        if getattr(quotation, "price_mode", None) and hasattr(order, "price_mode"):
            order.price_mode = quotation.price_mode
            order.save(update_fields=["price_mode"])
        SalesNotesService.set_order_items(order, items_data, user)
        quotation.status = Quotation.Status.CONVERTED
        quotation.converted_order = order
        quotation.updated_by = user
        quotation.save()
        return order

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
        from .return_service import ReturnService

        return ReturnService.set_return_items(sales_return, items_data, user)

    @staticmethod
    def _returned_quantities(invoice, exclude_return=None):
        from .return_service import ReturnService

        return ReturnService.returned_quantities(invoice, exclude_return=exclude_return)

    @staticmethod
    @transaction.atomic
    def complete_return(sales_return: SalesReturn, user):
        from .return_service import ReturnService

        return ReturnService.complete_return(sales_return, user)

    @staticmethod
    @transaction.atomic
    def cancel_return(sales_return: SalesReturn, user):
        from .return_service import ReturnService

        return ReturnService.cancel_return(sales_return, user)
