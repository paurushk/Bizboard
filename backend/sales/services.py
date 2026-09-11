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
from inventory.models import BatchLot, MovementType, StockMovement
from inventory.services import InventoryService, InventoryValuationService
from ledgers.services import LedgerService
from masters.models import Customer, Product

from .models import (
    Quotation,
    QuotationItem,
    SalesCreditNote,
    SalesCreditNoteItem,
    SalesDebitNote,
    SalesDebitNoteItem,
    SalesInvoice,
    SalesItem,
    SalesReturn,
    SalesReturnItem,
)
from .statutory_forms_guard import assert_statutory_licence_present


def _validate_lines(items_data, company, *, check_active=True):
    from core.validators import ALLOWED_GST_RATES

    allowed_gst = {Decimal(r) for r in ALLOWED_GST_RATES}
    if not items_data:
        raise BusinessRuleError("At least one line item is required.")
    for line in items_data:
        # B2-024: the qty column is 3dp — anything below 0.001 is stored as
        # 0.000. Reject it explicitly (the model's MinValueValidator isn't run
        # on bulk_create / .save() without full_clean()).
        if Decimal(str(line["quantity"])) < Decimal("0.001"):
            raise BusinessRuleError("Quantity on each line must be at least 0.001.")
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
        # CR-028: validate cess bounds (model validators bypassed on bulk_create)
        cess_rate = Decimal(str(line.get("cess_rate", 0) or 0))
        if cess_rate < 0 or cess_rate > 100:
            raise BusinessRuleError("Cess rate must be between 0 and 100.")
        cess_amount = Decimal(str(line.get("cess_amount", 0) or 0))
        if cess_amount < 0:
            raise BusinessRuleError("Cess amount cannot be negative.")
        product = line["product"]
        if product.company_id != company.id:
            raise BusinessRuleError("Invalid product reference.")
        batch = line.get("batch")
        if batch is not None:
            if getattr(batch, "company_id", None) != company.id:
                raise BusinessRuleError("Invalid batch reference.")
            if getattr(batch, "product_id", None) not in (None, product.pk):
                raise BusinessRuleError("Batch does not belong to this product.")
        if check_active and product.status != Product.Status.ACTIVE:
            raise BusinessRuleError(
                f"Cannot sell inactive product '{product.name}'.",
                code=HelpCode.INACTIVE_PRODUCT,
            )
        # CR-021: validate string field bounds before bulk_create
        desc = str(line.get("description") or "")
        if len(desc) > 255:
            raise BusinessRuleError("Line description exceeds maximum length of 255 characters.")
        batch_no = str(line.get("batch_number") or getattr(batch, "batch_number", "") or "")
        if len(batch_no) > 64:
            raise BusinessRuleError("Batch number exceeds maximum length of 64 characters.")


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
    from decimal import ROUND_HALF_UP

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
    # BILL-06: 206C(1H) is on the whole sale consideration (CBDT circular
    # 17/2020) — non-taxable freight / packing on the invoice is part of it and
    # `taxable_total` does not include it.
    _charges = Decimal(str(getattr(invoice, "additional_charges", 0) or 0))
    if _charges > 0:
        from core.services.charges import charges_are_taxable

        if not charges_are_taxable(invoice):
            consideration += _charges
    rate_amount = (
        # BILL-05: ROUND_HALF_UP so TCS rounds the same way as every other money
        # figure on the invoice (q2), not Decimal's default banker's rounding.
        (consideration * tcs_rate / Decimal("100")).quantize(two, rounding=ROUND_HALF_UP)
        if tcs_rate > 0
        else Decimal("0")
    )

    invoice._tcs_override = None
    manual = bool(getattr(invoice, "tcs_amount_manual", False))
    if manual:
        # Operator-supplied amount — including explicit 0 against a positive rate.
        explicit = prior
    else:
        explicit = prior if (prior > 0 and not already_folded) else None
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
            # D9b: default compensation cess from the product master, like gst_rate.
            cess_rate = line.get("cess_rate", getattr(product, "cess_rate", None) or Decimal("0"))
            cess_amount = line.get("cess_amount", getattr(product, "cess_amount", None) or Decimal("0"))
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
        if model_cls in (SalesCreditNoteItem, SalesDebitNoteItem) and source_item is not None:
            kwargs["source_item"] = source_item
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
        """Resolve an explicit batch or allocate the issue across FEFO lots.

        CR-050: under ``negative_stock_policy=WARN``, shortfalls allow + warn
        (same as unbatched invoice complete) instead of hard-failing. ``BLOCK``
        still raises. Callers should already have collected WARN strings via
        ``check_negative_stock``.
        """
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
        policy = getattr(invoice.company, "negative_stock_policy", "BLOCK") or "BLOCK"
        if batch_id or batch is not None:
            chosen = batch or item.batch
            warehouse = getattr(invoice, "warehouse", None)
            available = InventoryService.available_quantity(
                invoice.company, item.product, warehouse, chosen
            )
            if available < qty and policy == "BLOCK":
                raise BusinessRuleError(
                    f"Insufficient stock in batch '{getattr(chosen, 'batch_no', chosen)}' "
                    f"for '{item.product.name}': available {available}, required {qty}."
                )
            return [(chosen, qty)]

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
        if remaining > 0:
            if policy == "BLOCK":
                if not allocations:
                    raise BusinessRuleError(
                        f"No stock batch is available for '{item.product.name}'."
                    )
                raise BusinessRuleError(
                    f"Insufficient batched stock for '{item.product.name}': "
                    f"{remaining} unavailable."
                )
            # WARN: hang the shortfall on the last allocated lot, else any lot.
            if allocations:
                last_lot, last_qty = allocations[-1]
                allocations[-1] = (last_lot, last_qty + remaining)
            else:
                fallback = (
                    BatchLot.objects.filter(company=invoice.company, product=item.product)
                    .order_by("expiry_date", "id")
                    .first()
                )
                if fallback is None:
                    raise BusinessRuleError(
                        f"No stock batch is available for '{item.product.name}'."
                    )
                allocations.append((fallback, remaining))
        if hasattr(item, "batch") and hasattr(item, "save"):
            item.batch = allocations[0][0]
            if hasattr(item, "batch_no"):
                nos = []
                for lot, _qty in allocations:
                    no = (getattr(lot, "batch_no", None) or "").strip()
                    if no:
                        nos.append(no)
                item.batch_no = ",".join(nos)[:64]
                item.save(update_fields=["batch", "batch_no"])
            else:
                item.save(update_fields=["batch"])
        return allocations

    @staticmethod
    @transaction.atomic
    def set_items(invoice: SalesInvoice, items_data, user):
        if invoice.status in (SalesInvoice.Status.CANCELLED, SalesInvoice.Status.RETURNED):
            raise BusinessRuleError("Cancelled/returned invoice cannot be line-edited.")
        if invoice.status not in (SalesInvoice.Status.DRAFT, SalesInvoice.Status.COMPLETED):
            raise BusinessRuleError(f"Cannot edit invoice in status {invoice.status}.")
        if invoice.status == SalesInvoice.Status.COMPLETED:
            from .irn_guard import assert_no_live_eway, assert_no_live_irn

            assert_no_live_irn(invoice, kind="invoice")
            assert_no_live_eway(invoice, kind="invoice")

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

        # CR-123: invoice converted from SO — freeze quantities to SO line qtys.
        from sales.models import SalesOrder

        source_orders = list(
            SalesOrder.objects.filter(converted_invoice=invoice).prefetch_related("items")
        )
        if source_orders:
            so_qty = defaultdict(Decimal)
            for order in source_orders:
                for soi in order.items.all():
                    so_qty[soi.product_id] += Decimal(str(soi.quantity or 0))
            for product_id, new_q in new_qty_preview.items():
                cap = so_qty.get(product_id, Decimal("0"))
                if new_q > cap:
                    raise BusinessRuleError(
                        f"Quantity {new_q} exceeds sales-order quantity {cap} for this "
                        "converted invoice. Amend the order before convert, or use a "
                        "separate invoice for extra qty."
                    )
            for product_id, cap in so_qty.items():
                if product_id not in new_qty_preview and cap > 0:
                    # Dropping an SO line on the draft invoice is also a freeze breach.
                    raise BusinessRuleError(
                        "Cannot remove sales-order lines from a converted invoice. "
                        "Quantities are frozen to the source order."
                    )

        if adjust_stock:
            # CR-024 / CR-128: completed invoices cannot change quantities
            # via set_items (use credit note / return instead).
            for product_id in set(old_qty) | set(new_qty_preview):
                if new_qty_preview.get(product_id, Decimal("0")) != old_qty.get(
                    product_id, Decimal("0")
                ):
                    raise BusinessRuleError(
                        "Cannot amend quantity on a completed invoice. "
                        "Use a credit note or sales return instead."
                    )
            # Cannot reduce a line below quantities already returned.
            already = SalesService._returned_quantities(invoice)
            for product_id, returned_qty in already.items():
                if new_qty_preview.get(product_id, Decimal("0")) < returned_qty:
                    raise BusinessRuleError(
                        f"Quantity cannot be below already-returned quantity {returned_qty}."
                    )

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
                supply_type=getattr(invoice, "supply_type", ""),
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
            # CR-024 / CR-128: quantities on completed invoices are immutable; no stock delta to post.
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
            if invoice.company.accounting_enabled:
                from accounting.services import PostingService
                PostingService.adjust_sales_invoice_postings(invoice, user=user)
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
                 confirm_gstin_total_change=False, confirm_missing_licence=False):
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
        assert_statutory_licence_present(
            invoice.company, items, confirm_missing_licence=confirm_missing_licence
        )

        # BB-000264: opening bypass only via internal flag, never user-writable notes magic.
        if (invoice.notes or "").strip() == "TALLY_OPENING" and not getattr(
            invoice, "is_opening_balance", False
        ):
            raise BusinessRuleError(
                "TALLY_OPENING notes are not accepted. Opening invoices must be imported via Tally adapter."
            )
        is_tally_opening = bool(getattr(invoice, "is_opening_balance", False))

        from core.services.billing import place_of_supply_known

        # BB: when the customer state is blank, the GST-settings flag
        # 'assume_local_state_for_blank_party' is itself the standing confirmation
        # that such sales are intra-state (POS falls back to the seller's state) --
        # mirror assert_place_of_supply_for_gst's own blank-party bypass so the flag
        # also satisfies this complete-time pre-check without a per-invoice
        # confirm_blank_pos. (A non-blank GSTIN never reaches here: its state code
        # makes place_of_supply_known() true and short-circuits this guard.)
        assume_local_blank_party = not (invoice.customer.state or "").strip() and getattr(
            invoice.company, "assume_local_state_for_blank_party", False
        )

        if (
            tax_enabled
            and not is_tally_opening
            and not is_export_or_sez_supply(invoice.supply_type or "")
            and not place_of_supply_known(
                party_state=invoice.customer.state or "",
                party_gstin=invoice.customer.gstin or "",
            )
            and not assume_local_blank_party
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
        # QOS-0044: the check above only fires for a customer with an explicit
        # credit_limit. Opt-in: also hold a customer whose collection-risk
        # status is already stop_credit/overdue_severe, even with no limit set —
        # the ladder's "hold new orders" rung driven by risk status, not just a
        # static ceiling. Off by default so existing tenants see no change.
        if invoice.company.auto_credit_hold_on_severe_overdue and not is_tally_opening:
            from payments.dunning import customer_risk_snapshot

            snap = customer_risk_snapshot(invoice.company, customer)
            if snap["collection_status"] in ("stop_credit", "overdue_severe"):
                raise BusinessRuleError(
                    f"{customer.name} is on collection hold ({snap['collection_status'].replace('_', ' ')}); "
                    f"clear the overdue balance or lift the hold before billing further.",
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
                if getattr(invoice.company, "einvoice_enabled", False) and (
                    customer.gstin or ""
                ).strip():
                    raise BusinessRuleError(
                        f"{len(missing_hsn)} line(s) missing HSN — required before completing "
                        "an e-invoice GST invoice."
                    )
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
                    # CHG-02: a non-GST charge on a B2B invoice is legal (a pure
                    # reimbursement / exempt line) but must be disclosed, not
                    # silently swelling the grand total. Warn instead of hard
                    # blocking Complete; `build_gstr1` also flags it
                    # (ADDITIONAL_CHARGES_NONTAXABLE) so the return isn't short
                    # without the filer noticing. Set charges HSN + GST rate to
                    # carry tax on it.
                    warnings.append(
                        f"Additional charges of {invoice.additional_charges} carry no GST "
                        "(no charges HSN / rate set) — they are added to the invoice total "
                        "but will not appear as taxable value on GSTR-1."
                    )
        # C-02: converted challan lots must match even when stock posted on the challan.
        from .models import DeliveryChallan

        assert_converted_challan_lot_identity(invoice, items)
        stock_from_challan = DeliveryChallan.objects.filter(
            converted_invoice=invoice, stock_posted=True
        ).exists()
        for item in items:
            if item.product.status != Product.Status.ACTIVE:
                raise BusinessRuleError(
                    f"Cannot sell inactive product '{item.product.name}'.",
                    code=HelpCode.INACTIVE_PRODUCT,
                )
            if item.quantity <= 0:
                raise BusinessRuleError("Quantity on each line must be greater than zero.")
        if not stock_from_challan:
            from inventory.item_stock import tracks_inventory

            for item in items:
                # Non-inventory lines (services / non-stock items) have no stock
                # to check or deduct — skip them, same as CogsService.post_sale_
                # stock_and_cogs and the purchase posting path do.
                if not tracks_inventory(item.product):
                    continue
                if item.product.track_batch and not getattr(item, "batch_id", None):
                    remaining = item.quantity
                    warehouse = invoice.warehouse
                    for lot in InventoryValuationService.fefo_batches(
                        invoice.company, item.product, warehouse
                    ):
                        available = InventoryService.available_quantity(
                            invoice.company, item.product, warehouse, lot
                        )
                        remaining -= min(remaining, max(available, Decimal("0")))
                        if remaining <= 0:
                            break
                    if remaining > 0:
                        warning = InventoryService.check_negative_stock(
                            invoice.company, item.product, remaining, warehouse
                        )
                        if warning:
                            warnings.append(warning)
                else:
                    warning = InventoryService.check_negative_stock(
                        invoice.company,
                        item.product,
                        item.quantity,
                        invoice.warehouse,
                        batch=getattr(item, "batch", None),
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
        # CR-023: period gate before number/status/stock (fail fast; no SALE under lock).
        if not is_tally_opening:
            from reporting.gst_periods import assert_period_allows_money_amend

            assert_period_allows_money_amend(invoice.company, invoice.invoice_date)
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
        if tax_enabled:
            # TAX-10: after TCS fold so the threshold sees the TCS-inclusive total.
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
            # CR-020: release SO reservation held through draft invoice, then mark CONVERTED.
            from .models import SalesOrder

            for order in SalesOrder.objects.select_for_update().filter(converted_invoice=invoice):
                inv_qty_by_product = defaultdict(Decimal)
                for it in invoice.items.all():
                    inv_qty_by_product[it.product_id] += Decimal(str(it.quantity or 0))

                if order.status == SalesOrder.Status.CONFIRMED:
                    warehouse = order.warehouse or InventoryService.default_warehouse(order.company)
                    for item in order.items.select_related("product"):
                        release_qty = min(
                            Decimal(str(item.quantity or 0)),
                            inv_qty_by_product.get(item.product_id, Decimal(str(item.quantity or 0))),
                        )
                        if release_qty > 0:
                            InventoryService.release_reservation(
                                order.company, warehouse, item.product, release_qty, user
                            )

                fully_converted = all(
                    inv_qty_by_product.get(it.product_id, Decimal("0")) >= Decimal(str(it.quantity or 0))
                    for it in order.items.all()
                )
                if fully_converted and order.status in (SalesOrder.Status.DRAFT, SalesOrder.Status.CONFIRMED):
                    order.status = SalesOrder.Status.CONVERTED
                    order.updated_by = user
                    order.save(update_fields=["status", "updated_by", "updated_at"])

            cogs_total = CogsService.post_sale_stock_and_cogs(
                invoice, items, user, stock_from_challan=stock_from_challan, warnings=warnings
            )
            from reporting.gst_periods import mark_period_dirty_if_snapshotted

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
        # CR-034: completed CN/DN leave AR/GSTR history — cancel would orphan them.
        if invoice.credit_notes.filter(status=SalesCreditNote.Status.COMPLETED).exists() or invoice.debit_notes.filter(
            status=SalesDebitNote.Status.COMPLETED
        ).exists():
            raise BusinessRuleError(
                "Cannot cancel an invoice with completed credit or debit notes. "
                "Cancel the note(s) first."
            )
        # CR-097 twin: draft notes would also be orphaned against a cancelled invoice.
        if invoice.credit_notes.exclude(
            status__in=(SalesCreditNote.Status.COMPLETED, SalesCreditNote.Status.CANCELLED)
        ).exists() or invoice.debit_notes.exclude(
            status__in=(SalesDebitNote.Status.COMPLETED, SalesDebitNote.Status.CANCELLED)
        ).exists():
            raise BusinessRuleError(
                "Cancel or delete the draft credit/debit note(s) against this invoice first."
            )
        if invoice.allocations.filter(reversed_at__isnull=True).exists():
            # BUG-722: cancelling a paid/partially-paid invoice would leave
            # payment allocations pointing at a document that's no longer
            # completed — the ledger has no defined meaning for that.
            raise BusinessRuleError(
                "Cannot cancel an invoice with payment allocations against it. "
                "Remove the allocation(s) first."
            )
        from .irn_guard import assert_no_live_eway, assert_no_live_irn

        assert_no_live_irn(invoice, kind="invoice")
        assert_no_live_eway(invoice, kind="invoice")

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

                linked_qs = list(
                    DeliveryChallan.objects.filter(
                        company=invoice.company,
                        converted_invoice=invoice,
                        stock_posted=True,
                    )
                )
                for linked in linked_qs:
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
                    linked.converted_invoice = None
                    linked.save(update_fields=["stock_posted", "converted_invoice", "updated_at"])
        invoice.status = SalesInvoice.Status.CANCELLED
        invoice.cancelled_at = timezone.now()
        invoice.updated_by = user
        invoice.save()
        # CR-020: unlink SO so reservation stays and order can be re-converted / cancelled.
        from .models import SalesOrder

        SalesOrder.objects.filter(converted_invoice=invoice).exclude(
            status=SalesOrder.Status.CONVERTED
        ).update(converted_invoice=None, updated_by=user, updated_at=timezone.now())
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
                supply_type=getattr(quotation, "supply_type", ""),
            ),
            # CR-021: apply header discount / charges / round-off like SO/invoice.
            additional_charges=getattr(quotation, "additional_charges", 0) or 0,
            invoice_discount=getattr(quotation, "invoice_discount", 0) or 0,
            auto_round_off=getattr(quotation, "auto_round_off", True),
            invoice_discount_mode=getattr(quotation, "invoice_discount_mode", None),
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

        from accounts.models import CompanyGstin

        active_gstins = list(
            CompanyGstin.objects.filter(company=quotation.company, is_active=True).order_by(
                "-is_primary", "id"
            )
        )
        stamp = active_gstins[0] if len(active_gstins) == 1 else None
        invoice = SalesInvoice.objects.create(
            company=quotation.company,
            customer=quotation.customer,
            warehouse=InventoryService.default_warehouse(quotation.company),
            invoice_type=quotation.invoice_type,
            company_gstin=getattr(quotation, "company_gstin", None) or stamp,
            supply_type=getattr(quotation, "supply_type", None) or SalesInvoice.SupplyType.B2B,
            payment_terms_days=getattr(quotation, "payment_terms_days", 0) or 0,
            additional_charges=getattr(quotation, "additional_charges", 0) or 0,
            charges_hsn=getattr(quotation, "charges_hsn", "") or "",
            charges_gst_rate=getattr(quotation, "charges_gst_rate", 0) or 0,
            invoice_discount=getattr(quotation, "invoice_discount", 0) or 0,
            invoice_discount_mode=getattr(quotation, "invoice_discount_mode", None)
            or SalesInvoice.DiscountMode.AFTER_TAX,
            auto_round_off=getattr(quotation, "auto_round_off", True),
            notes=quotation.notes,
            terms_text=getattr(quotation, "terms_text", "") or "",
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
                "rate_override": getattr(item, "rate_override", False),
                "rate_override_reason": getattr(item, "rate_override_reason", "") or "",
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
            warehouse=InventoryService.default_warehouse(quotation.company),
            invoice_type=quotation.invoice_type,
            company_gstin=getattr(quotation, "company_gstin", None),
            supply_type=getattr(quotation, "supply_type", None) or SalesInvoice.SupplyType.B2B,
            payment_terms_days=getattr(quotation, "payment_terms_days", 0) or 0,
            additional_charges=getattr(quotation, "additional_charges", 0) or 0,
            charges_hsn=getattr(quotation, "charges_hsn", "") or "",
            charges_gst_rate=getattr(quotation, "charges_gst_rate", 0) or 0,
            invoice_discount=getattr(quotation, "invoice_discount", 0) or 0,
            invoice_discount_mode=getattr(quotation, "invoice_discount_mode", None)
            or SalesInvoice.DiscountMode.AFTER_TAX,
            auto_round_off=getattr(quotation, "auto_round_off", True),
            notes=quotation.notes,
            terms_text=getattr(quotation, "terms_text", "") or "",
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
                "rate_override": getattr(item, "rate_override", False),
                "rate_override_reason": getattr(item, "rate_override_reason", "") or "",
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
