"""Purchase Service — invoices, returns, status transitions (E3)."""

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from core.events import emit
from core.services.audit import record_document_event, record_edited_document_event
from core.exceptions import BusinessRuleError, raise_confirm_required
from core.help_codes import HelpCode
from core.services.billing import (
    apply_rcm_memo_after_tax,
    fold_tds_from_rate,
    recompute_totals_for_stamped_gstin,
)
from core.services.tax_engine.registry import get_tax_engine
from core.services.place_of_supply import assert_place_of_supply_for_gst, party_intra_state
from core.services.document_numbers import DocumentNumberService
from core.services.uqc import snapshot_unit_fields
from inventory.item_stock import base_quantity, base_unit_cost, get_or_create_batch, tracks_inventory
from inventory.models import MovementType
from inventory.services import InventoryService, InventoryValuationService, SerialNumberService
from masters.models import Product

from .models import (
    BillOfEntry,
    GoodsReceipt,
    GoodsReceiptItem,
    PurchaseCreditNote,
    PurchaseDebitNote,
    PurchaseInvoice,
    PurchaseInvoiceRevision,
    PurchaseItem,
    PurchaseReturn,
    PurchaseReturnItem,
)

# Line match: a rate may drift by half a percent of the reference rate (never less than
# one paisa, so inclusive-price rounding does not block a bill). Quantity may not drift.
_THREE_WAY_RATE_TOLERANCE_PCT = Decimal("0.005")
_THREE_WAY_RATE_TOLERANCE_FLOOR = Decimal("0.01")
_THREE_WAY_QTY_TOLERANCE = Decimal("0.000")


def _three_way_rate_tolerance(reference_rate) -> Decimal:
    reference = abs(Decimal(str(reference_rate or 0)))
    return max(_THREE_WAY_RATE_TOLERANCE_FLOOR, (reference * _THREE_WAY_RATE_TOLERANCE_PCT).quantize(Decimal("0.01")))
STATUTORY_TDS_SECTIONS = frozenset({"194C", "194I", "194J", "194Q"})


def assert_invoice_tds_exclusive(invoice):
    """Refuse invoice-level TDS when this supplier already withheld TDS on a payment."""
    from payments.models import SupplierPayment, SupplierPaymentStatus

    tds = Decimal(str(getattr(invoice, "tds_amount", 0) or 0))
    tds_rate = Decimal(str(getattr(invoice, "tds_rate", 0) or 0))
    if tds <= 0 and tds_rate <= 0:
        return
    if SupplierPayment.objects.filter(
        company=invoice.company,
        supplier_id=invoice.supplier_id,
        tds_amount__gt=0,
        status=SupplierPaymentStatus.POSTED,
    ).exists():
        raise BusinessRuleError(
            "This supplier already has payments with TDS. Record TDS on the payment only; "
            "do not also set TDS on the invoice."
        )


def assert_claimable_itc_allowed(invoice, *, goods_will_be_received: bool = False):
    """CLAIMABLE requires the Section 16(2) checklist (2B match when the period has 2B)."""
    if getattr(invoice, "itc_eligibility", None) != PurchaseInvoice.ItcEligibility.CLAIMABLE:
        return
    from reporting.ims import assert_section_16_2_for_claim

    assert_section_16_2_for_claim(invoice, goods_will_be_received=goods_will_be_received)


_PURCHASE_ITEM_UPDATE_FIELDS = [
    "product", "batch", "description", "quantity", "unit_price",
    "discount_percent", "gst_rate", "cess_rate", "cess_amount",
    "hsn_code", "mrp", "unit_name", "uqc_code", "unit_price_inclusive",
    "batch_no", "exp_date", "mfg_date", "serial_numbers",
    "taxable_amount", "cgst", "sgst", "igst", "cess", "line_total",
]


def _line_stock_qty(product, quantity, unit_name=None):
    return base_quantity(product, quantity, unit_name)


def _line_stock_cost(product, unit_price, unit_name=None):
    return base_unit_cost(product, unit_price, unit_name)


def _invoice_unit_name_by_product(invoice):
    if invoice is None:
        return {}
    names = {}
    for row in invoice.items.all():
        names.setdefault(row.product_id, getattr(row, "unit_name", None))
    return names


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
        batch = line.get("batch")
        if batch is not None:
            if getattr(batch, "company_id", None) != company.id:
                raise BusinessRuleError("Invalid batch reference.")
            if getattr(batch, "product_id", None) not in (None, line["product"].pk):
                raise BusinessRuleError("Batch does not belong to this product.")
        # CR-021: validate string field bounds before bulk_create
        desc = str(line.get("description") or "")
        if len(desc) > 255:
            raise BusinessRuleError("Line description exceeds maximum length of 255 characters.")
        batch_no = str(line.get("batch_no") or line.get("batch_number") or getattr(batch, "batch_number", "") or "")
        if len(batch_no) > 64:
            raise BusinessRuleError("Batch number exceeds maximum length of 64 characters.")


def _build_purchase_items(invoice, items_data):
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
            # D9b: default compensation cess from the product master, like gst_rate.
            cess_rate=line.get("cess_rate", getattr(product, "cess_rate", None) or Decimal("0")),
            cess_amount=line.get("cess_amount", getattr(product, "cess_amount", None) or Decimal("0")),
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
            rate_override=bool(line.get("rate_override")),
            rate_override_reason=(line.get("rate_override_reason") or "")[:255],
        ))
    return items


def _update_purchase_items_in_place(invoice: PurchaseInvoice, items_data):
    """
    Update existing PurchaseItem rows in place (match by id, else product).
    Preserves PKs so credit/debit note source_item FKs remain valid.
    """
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
                f"Line item for product '{product.name}' was not on the original purchase "
                "and cannot be added after completion."
            )
        snap = snapshot_unit_fields(product, line)
        inclusive = line.get("unit_price_inclusive")
        old.product = product
        old.batch = line.get("batch")
        old.description = line.get("description") or product.name
        old.quantity = line["quantity"]
        old.unit_price = line.get("unit_price", product.purchase_price)
        old.discount_percent = line.get("discount_percent", Decimal("0"))
        old.gst_rate = line.get("gst_rate", product.gst_rate)
        old.cess_rate = line.get("cess_rate", Decimal("0"))
        old.cess_amount = line.get("cess_amount", Decimal("0"))
        old.hsn_code = snap["hsn_code"]
        old.mrp = line.get("mrp", product.mrp or Decimal("0"))
        old.unit_name = snap["unit_name"]
        old.uqc_code = snap["uqc_code"]
        old.unit_price_inclusive = (
            Decimal(str(inclusive)) if inclusive is not None else None
        )
        old.batch_no = line.get("batch_no") or ""
        old.exp_date = line.get("exp_date")
        old.mfg_date = line.get("mfg_date")
        old.serial_numbers = line.get("serial_numbers") or []
        items.append(old)

    removed_ids = set(by_id) - used_ids
    if removed_ids:
        from purchases.models import PurchaseCreditNoteItem, PurchaseDebitNoteItem

        if (
            PurchaseCreditNoteItem.objects.filter(source_item_id__in=removed_ids).exists()
            or PurchaseDebitNoteItem.objects.filter(source_item_id__in=removed_ids).exists()
        ):
            raise BusinessRuleError("Cannot remove purchase line items that have linked credit or debit notes.")
        PurchaseItem.objects.filter(id__in=removed_ids).delete()

    return items


class PurchaseService:
    # ---------------- Purchase invoice ----------------

    @staticmethod
    def _returned_quantities(invoice, exclude_return=None):
        """Returned qty in *base* units (CR-131 / CR-045)."""
        from collections import defaultdict

        qs = PurchaseReturnItem.objects.filter(
            purchase_return__purchase_invoice=invoice,
            purchase_return__status=PurchaseReturn.Status.COMPLETED,
        ).select_related("product", "product__alternate_unit")
        if exclude_return is not None:
            qs = qs.exclude(purchase_return=exclude_return)
        out = defaultdict(Decimal)
        for item in qs:
            out[item.product_id] += _line_stock_qty(
                item.product, item.quantity, getattr(item, "unit_name", None)
            )
        return dict(out)

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
            PurchaseService.snapshot_completed_purchase(invoice, user)
            for item in invoice.items.select_related("product", "product__alternate_unit"):
                old_qty[item.product_id] += _line_stock_qty(
                    item.product, item.quantity, getattr(item, "unit_name", None)
                )

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

        new_qty_doc = defaultdict(Decimal)
        new_qty_preview = defaultdict(Decimal)
        for line in items_data:
            new_qty_doc[line["product"].pk] += Decimal(line["quantity"])
            new_qty_preview[line["product"].pk] += _line_stock_qty(
                line["product"], Decimal(line["quantity"]), line.get("unit_name")
            )

        if adjust_stock:
            already = PurchaseService._returned_quantities(invoice)
            for product_id, returned_qty in already.items():
                if new_qty_preview.get(product_id, Decimal("0")) < returned_qty:
                    raise BusinessRuleError(
                        f"Quantity cannot be below already-returned quantity {returned_qty}."
                    )
            # CR-001 / H9-A: completed purchase quantities are immutable via
            # set_items — twin of SalesService.set_items (CR-024 / CR-128). A qty
            # correction goes through a debit/credit note or a purchase return so
            # the stock + AP + GL effect is a first-class reversible document.
            # The former in-place qty-delta path posted a `purchase_invoice_edit`
            # ADJUSTMENT that `PurchaseService.cancel` never reversed, leaving a
            # completed+amended bill un-cancellable and stock/FIFO drifted.
            for product_id in set(old_qty) | set(new_qty_preview):
                if new_qty_preview.get(product_id, Decimal("0")) != old_qty.get(
                    product_id, Decimal("0")
                ):
                    raise BusinessRuleError(
                        "Cannot amend quantity on a completed purchase. "
                        "Issue a debit/credit note or a purchase return instead."
                    )

        if adjust_stock:
            items = _update_purchase_items_in_place(invoice, items_data)
        else:
            invoice.items.all().delete()
            items = _build_purchase_items(invoice, items_data)

        get_tax_engine(invoice.company).compute_document_totals(
            invoice, items,
            tax_enabled=invoice.purchase_type == PurchaseInvoice.PurchaseType.GST,
            intra_state=party_intra_state(
                invoice.company,
                invoice.supplier.state,
                invoice.supplier.gstin or "",
                seller_state=(getattr(invoice.company_gstin, "state", None) or ""),
                seller_gstin=(getattr(invoice.company_gstin, "gstin", None) or ""),
                supply_type=getattr(invoice, "supply_type", ""),
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
        if adjust_stock:
            PurchaseItem.objects.bulk_update(items, _PURCHASE_ITEM_UPDATE_FIELDS)
        else:
            PurchaseItem.objects.bulk_create(items)

        if adjust_stock:
            # CR-001: quantities are immutable on a completed purchase (rejected
            # above), so there is no stock delta to post here — only price /
            # discount / charge amends reach this point. Refresh the GL for those
            # and re-price the remaining FIFO layers via the caller
            # (restamp_fifo_layers_for_price_amend).
            record_edited_document_event(invoice=invoice, user=user, old_totals=old_totals)
            emit("purchase_invoice.edited", invoice=invoice, user=user, old_totals=old_totals)
            if invoice.company.accounting_enabled:
                from accounting.services import PostingService
                PostingService.adjust_purchase_invoice_postings(invoice, user=user)

        invoice.updated_by = user
        invoice.save()
        return invoice

    @staticmethod
    def snapshot_completed_purchase(invoice, user):
        """Store the full bill (header + lines) before a completed-document mutation."""
        if invoice.status != PurchaseInvoice.Status.COMPLETED:
            return None
        if getattr(invoice, "_pur_revision_taken", False):
            return None
        invoice._pur_revision_taken = True
        last = (
            PurchaseInvoiceRevision.objects.filter(invoice=invoice)
            .order_by("-revision")
            .values_list("revision", flat=True)
            .first()
        ) or 0
        lines = []
        for item in invoice.items.all():
            lines.append({
                "id": item.pk,
                "product_id": item.product_id,
                "quantity": str(item.quantity),
                "unit_price": str(item.unit_price),
                "discount_percent": str(item.discount_percent),
                "gst_rate": str(item.gst_rate),
                "taxable_amount": str(item.taxable_amount),
                "line_total": str(item.line_total),
                "hsn_code": item.hsn_code or "",
            })
        snapshot = {
            "number": invoice.number,
            "status": invoice.status,
            "supplier_id": invoice.supplier_id,
            "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
            "supplier_bill_number": invoice.supplier_bill_number or "",
            "purchase_type": invoice.purchase_type,
            "subtotal": str(invoice.subtotal),
            "taxable_total": str(invoice.taxable_total),
            "cgst_total": str(invoice.cgst_total),
            "sgst_total": str(invoice.sgst_total),
            "igst_total": str(invoice.igst_total),
            "grand_total": str(invoice.grand_total),
            "additional_charges": str(invoice.additional_charges),
            "invoice_discount": str(invoice.invoice_discount),
            "tds_section": invoice.tds_section or "",
            "tds_rate": str(invoice.tds_rate),
            "tds_amount": str(invoice.tds_amount),
            "items": lines,
        }
        actor = user if getattr(user, "pk", None) else None
        return PurchaseInvoiceRevision.objects.create(
            company=invoice.company,
            invoice=invoice,
            revision=int(last) + 1,
            snapshot=snapshot,
            created_by=actor,
            updated_by=actor,
        )

    @staticmethod
    def restamp_fifo_layers_for_price_amend(invoice):
        """H9 price-only: update remaining FIFO layers; refuse if any qty peeled.

        WAVG companies revalue the remaining weighted-average pool and, when
        part of the receipt was already issued, post a balanced COGS variance.
        """
        from inventory.models import InventoryCostLayer, StockMovement

        # CR-027: Map cost per base unit accounting for line discounts and alternate units
        cost_by_product_batch = {}
        for item in invoice.items.all():
            base_qty = _line_stock_qty(item.product, item.quantity, getattr(item, "unit_name", None))
            if base_qty and Decimal(str(base_qty)) > 0:
                cost = (Decimal(str(item.taxable_amount)) / Decimal(str(base_qty))).quantize(
                    Decimal("0.0001")
                )
            else:
                cost = _line_stock_cost(item.product, item.unit_price, getattr(item, "unit_name", None))
            key = (item.product_id, getattr(item, "batch_id", None))
            cost_by_product_batch[key] = cost

        method = getattr(invoice.company, "inventory_valuation_method", "WAVG") or "WAVG"
        if method != "FIFO":
            PurchaseService._restamp_wavg_price_amend(invoice, cost_by_product_batch)
            return

        moves = StockMovement.objects.filter(
            company=invoice.company,
            movement_type=MovementType.PURCHASE,
            reference_type="purchase_invoice",
            reference_id=str(invoice.pk),
        )
        for move in moves:
            key = (move.product_id, move.batch_id)
            new_cost = cost_by_product_batch.get(key)
            if new_cost is None:
                for (p_id, _b_id), c in cost_by_product_batch.items():
                    if p_id == move.product_id:
                        new_cost = c
                        break
            if new_cost is None:
                continue
            original_qty = abs(Decimal(str(move.quantity or 0)))
            layers = list(InventoryCostLayer.objects.select_for_update().filter(source_movement=move))
            for layer in layers:
                # R2-016: a zero original_qty is corrupt data — do not blindly
                # restamp; and any layer that has less remaining than the move
                # supplied has already been (partly) issued.
                if original_qty <= 0 or layer.qty_remaining < original_qty:
                    raise BusinessRuleError(
                        "Cannot price-amend a purchase whose FIFO layers have been issued. "
                        "Use a debit/credit note or purchase return."
                    )
                layer.unit_cost = new_cost
                layer.save(update_fields=["unit_cost", "updated_at"])
            # CR-144: append-only — use stamp_cost, never bare QuerySet.update.
            StockMovement.stamp_cost(move.pk, unit_cost=new_cost)

    @staticmethod
    def _movement_cost(move, cost_by_product_batch):
        key = (move.product_id, move.batch_id)
        new_cost = cost_by_product_batch.get(key)
        if new_cost is None:
            for (p_id, _b_id), c in cost_by_product_batch.items():
                if p_id == move.product_id:
                    return c
        return new_cost

    @staticmethod
    def _restamp_wavg_price_amend(invoice, cost_by_product_batch):
        """Revalue remaining WAVG stock and journal the consumed cost delta."""
        from inventory.models import InventoryRunningCost, StockMovement

        moves = StockMovement.objects.filter(
            company=invoice.company,
            movement_type=MovementType.PURCHASE,
            reference_type="purchase_invoice",
            reference_id=str(invoice.pk),
        )
        variance = Decimal("0")
        for move in moves:
            new_cost = PurchaseService._movement_cost(move, cost_by_product_batch)
            if new_cost is None:
                continue
            new_cost = Decimal(str(new_cost)).quantize(Decimal("0.0001"))
            old_cost = Decimal(str(move.unit_cost or 0)).quantize(Decimal("0.0001"))
            delta = new_cost - old_cost
            if delta == 0:
                continue
            original_qty = abs(Decimal(str(move.quantity or 0)))
            if original_qty <= 0:
                continue
            row = (
                InventoryRunningCost.objects.select_for_update()
                .filter(
                    company=invoice.company,
                    warehouse_id=move.warehouse_id,
                    product_id=move.product_id,
                    batch_id=move.batch_id,
                )
                .first()
            )
            if row is None:
                continue
            pool_qty = Decimal(str(row.qty or 0))
            revalue_qty = min(original_qty, pool_qty) if pool_qty > 0 else Decimal("0")
            consumed_qty = original_qty - revalue_qty
            row.value = (Decimal(str(row.value or 0)) + (revalue_qty * delta)).quantize(Decimal("0.0001"))
            row.save(update_fields=["value", "updated_at"])
            StockMovement.stamp_cost(move.pk, unit_cost=new_cost)
            variance += consumed_qty * delta

        variance = variance.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if variance == 0 or not getattr(invoice.company, "accounting_enabled", False):
            return
        from accounting.services import PostingService

        amount = abs(variance)
        cogs = PostingService._account(invoice.company, "5400")
        inventory = PostingService._account(invoice.company, "1400")
        if variance > 0:
            lines = [
                {"account": cogs, "debit": amount, "cost_center": invoice.cost_center},
                {"account": inventory, "credit": amount, "cost_center": invoice.cost_center},
            ]
        else:
            lines = [
                {"account": inventory, "debit": amount, "cost_center": invoice.cost_center},
                {"account": cogs, "credit": amount, "cost_center": invoice.cost_center},
            ]
        PostingService.post(
            company=invoice.company,
            source_type="PURCHASE_INVOICE",
            source_id=invoice.id,
            # The posting key is (source, purpose), so a second price amend would be answered with
            # the first journal and the GL would stop following the stock revaluation. One purpose
            # per amend (the revision count) keeps each journal.
            purpose=f"WAVG_PRICE_VARIANCE_{invoice.revisions.count()}",
            entry_date=invoice.invoice_date,
            user=None,
            narration=f"WAVG price variance: {invoice.number or invoice.pk}",
            lines=lines,
        )

    @staticmethod
    def _is_foreign_import_supplier(supplier) -> bool:
        from core.services.billing import extract_state_code

        country = (getattr(supplier, "country", None) or "").strip().upper()
        if country in {"IN", "IND", "INDIA"}:
            return False
        if country:
            return True
        # Country not captured yet: keep the GSTIN/state inference so suppliers
        # saved before this field still cannot skip a Bill of Entry.
        state = (supplier.state or "").strip()
        gstin = (supplier.gstin or "").strip()
        tt = (getattr(supplier, "taxpayer_type", None) or "").strip().upper()
        foreign_tt = tt in ("EXPWP", "EXPWOP", "DEXP", "SEZWP", "SEZWOP")
        has_india_state = bool(extract_state_code(gstin) or extract_state_code(state))
        return bool(foreign_tt or (state and not has_india_state and not gstin))

    @staticmethod
    def _match_manager(company, user) -> bool:
        from accounts.models import CompanyUser

        if user is None or not getattr(user, "pk", None):
            return False
        role = (
            CompanyUser.objects.filter(company=company, user=user)
            .values_list("role", flat=True)
            .first()
        )
        return role in (CompanyUser.Role.OWNER, CompanyUser.Role.MANAGER)

    @staticmethod
    def match_bill_to_po(invoice, *, user=None, confirm_override=False):
        """Line-level 3-way match of the bill against its PO and GRN.

        Aggregate totals can hide a rate increase on one line offset by a cut
        on another. Quantity is checked against GRN accepted qty when a receipt
        is linked, and rate against the PO (else the GRN). An owner or manager
        may pass confirm_override to accept the breaches.
        """
        orders = list(invoice.source_orders.prefetch_related("items"))
        grns = list(
            invoice.source_grns.filter(status=GoodsReceipt.Status.COMPLETED)
            .select_related("purchase_order")
            .prefetch_related("items", "purchase_order__items")
        )
        seen_order_ids = {order.pk for order in orders}
        for grn in grns:
            po = grn.purchase_order
            if po is not None and po.pk not in seen_order_ids:
                orders.append(po)
                seen_order_ids.add(po.pk)
        if not orders and not grns:
            return []

        # Several PO lines (different rates) or GRN lines (different batches) can carry one product,
        # and so can the bill. Compare per product: summed quantities, and any of the agreed rates.
        po_qty = defaultdict(Decimal)
        po_rates = defaultdict(list)
        for order in orders:
            for line in order.items.all():
                po_qty[line.product_id] += Decimal(str(line.quantity or 0))
                po_rates[line.product_id].append(Decimal(str(line.unit_price or 0)).quantize(Decimal("0.01")))
        grn_qty = defaultdict(Decimal)
        grn_rates = defaultdict(list)
        for grn in grns:
            for line in grn.items.all():
                grn_qty[line.product_id] += Decimal(str(line.quantity_accepted or 0))
                price = Decimal(str(line.unit_price or 0)).quantize(Decimal("0.01"))
                if price > 0:
                    grn_rates[line.product_id].append(price)

        def _outside(rate, agreed):
            return all(abs(rate - a) > _three_way_rate_tolerance(a) for a in agreed)

        bill_qty = defaultdict(Decimal)
        names = {}
        lines = list(invoice.items.select_related("product"))
        for item in lines:
            bill_qty[item.product_id] += Decimal(str(item.quantity or 0))
            names[item.product_id] = item.product.name

        breaches = []
        for item in lines:
            pid = item.product_id
            name = item.product.name
            rate = Decimal(str(item.unit_price or 0)).quantize(Decimal("0.01"))
            if pid in po_rates and _outside(rate, po_rates[pid]):
                breaches.append(f"{name}: bill rate {rate} differs from PO rate {po_rates[pid][-1]}")
            elif pid not in po_rates and pid in grn_rates and _outside(rate, grn_rates[pid]):
                breaches.append(f"{name}: bill rate {rate} differs from GRN rate {grn_rates[pid][-1]}")
            if orders and pid not in po_rates:
                breaches.append(f"{name}: billed but not on the purchase order")
        for pid, qty in bill_qty.items():
            name = names[pid]
            if grns:
                accepted = grn_qty.get(pid, Decimal("0"))
                if abs(qty - accepted) > _THREE_WAY_QTY_TOLERANCE:
                    breaches.append(f"{name}: bill qty {qty} differs from GRN accepted {accepted}")
            elif orders and qty - po_qty.get(pid, Decimal("0")) > _THREE_WAY_QTY_TOLERANCE:
                breaches.append(
                    f"{name}: bill qty {qty} exceeds PO qty {po_qty.get(pid, Decimal('0'))}"
                )
        if grns:
            for pid, accepted in grn_qty.items():
                if accepted > 0 and pid not in bill_qty:
                    breaches.append(f"product {pid}: GRN accepted {accepted} is missing on the bill")

        if not breaches:
            return []
        if confirm_override and PurchaseService._match_manager(invoice.company, user):
            return breaches
        raise BusinessRuleError(
            "3-way match failed: " + "; ".join(breaches)
            + ". An owner or manager may pass confirm_three_way_override=true."
        )

    @staticmethod
    def _assert_import_bill_of_entry(invoice: PurchaseInvoice) -> None:
        """R-024: import Complete requires THIS invoice's completed BoE.

        A stale completed BoE for the same supplier must not unlock later imports.
        """
        if not PurchaseService._is_foreign_import_supplier(invoice.supplier):
            return
        if invoice.purchase_type == PurchaseInvoice.PurchaseType.GST:
            raise BusinessRuleError(
                "Customs IGST belongs on a Bill of Entry, not a GST purchase invoice. "
                "Create and complete a Bill of Entry at /purchases/bills-of-entry, "
                "then complete this import as NON_GST linked to that Bill of Entry."
            )
        boe = invoice.bill_of_entry
        if (
            boe is None
            or boe.status != BillOfEntry.Status.COMPLETED
            or boe.supplier_id != invoice.supplier_id
        ):
            raise BusinessRuleError(
                "This import purchase needs its own completed Bill of Entry "
                "(same supplier) before Complete. One completed BoE does not "
                "unlock later imports. Open /purchases/bills-of-entry."
            )

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
            return (
                HelpCode.CONFIRM_DUPLICATE_BILL,
                f"A purchase with supplier bill number '{bill_no}' already exists for this "
                "supplier. Pass confirm_duplicate_bill=true to proceed.",
            )
        return None

    @staticmethod
    def _unregistered_rcm_gate(invoice, items, *, confirm_no_rcm=False, warnings=None):
        """PUR-03/PUR-08: unregistered / blank GSTIN without RCM needs confirm; GTA warn."""
        from masters.models import Customer

        warnings = warnings if warnings is not None else []
        supplier = invoice.supplier
        taxpayer = getattr(supplier, "taxpayer_type", "") or ""
        gstin = (supplier.gstin or "").strip()
        if invoice.is_reverse_charge:
            return None, warnings
        if invoice.purchase_type != PurchaseInvoice.PurchaseType.GST:
            return None, warnings

        is_unregistered = taxpayer == Customer.TaxpayerType.UNREGISTERED
        blank_gstin = not gstin
        _registered_type = taxpayer in (
            Customer.TaxpayerType.REGULAR,
            Customer.TaxpayerType.COMPOSITION,
        )
        # R2-011: the common data state is a supplier with NO GSTIN and a blank
        # taxpayer_type — that is an unregistered dealer for RCM purposes and
        # must hit the same hard confirm gate, not a soft warning.
        needs_rcm_confirm = is_unregistered or (blank_gstin and not _registered_type)
        pending = None
        if needs_rcm_confirm and not confirm_no_rcm:
            pending = (
                HelpCode.CONFIRM_NO_RCM,
                "Supplier is unregistered (no GSTIN) and reverse charge is off. "
                "Enable is_reverse_charge, or pass confirm_no_rcm=true to proceed.",
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
        return pending, warnings

    @staticmethod
    @transaction.atomic
    def complete(invoice: PurchaseInvoice, user, *, confirm_no_rcm=False, confirm_duplicate_bill=False, confirm_blank_pos=False,
                 confirm_gstin_total_change=False, confirm_three_way_override=False, gstin_cancel_override=False,
                 gstin_cancel_reason=""):
        """Atomic Complete: number + PURCHASE movements + event (E3.3)."""
        invoice = PurchaseInvoice.objects.select_for_update().get(pk=invoice.pk)
        cancelled_on = getattr(invoice.supplier, "gstin_cancelled_on", None)
        if (
            cancelled_on
            and invoice.invoice_date
            and invoice.invoice_date >= cancelled_on
            and not gstin_cancel_override
        ):
            from planwave.services import alert_purchase_team

            alert_purchase_team(
                invoice.company,
                "Supplier GSTIN cancelled",
                f"{invoice.supplier.name} is cancelled from {cancelled_on}. New ITC is blocked.",
            )
            raise BusinessRuleError(
                "Supplier GSTIN is cancelled on or before this bill. ITC is blocked until an authorised override is recorded.",
            )
        if gstin_cancel_override and cancelled_on:
            from planwave.services import assert_gstin_override

            assert_gstin_override(invoice.company, user, gstin_cancel_reason)
        from billing.quotas import assert_complete_allowed

        assert_complete_allowed(invoice.company)
        if invoice.warehouse_id is None:
            invoice.warehouse = InventoryService.default_warehouse(invoice.company)
        if invoice.status != PurchaseInvoice.Status.DRAFT:
            raise BusinessRuleError(f"Cannot complete a purchase in status {invoice.status}.")
        items = list(invoice.items.select_related("product", "product__category", "product__alternate_unit"))
        if not items:
            raise BusinessRuleError("Cannot complete a purchase without line items.")

        tax_enabled = invoice.purchase_type == PurchaseInvoice.PurchaseType.GST
        PurchaseService._assert_import_bill_of_entry(invoice)
        PurchaseService.match_bill_to_po(
            invoice, user=user, confirm_override=confirm_three_way_override,
        )
        from core.services.registration_gates import assert_may_issue_gst_tax_invoice

        assert_may_issue_gst_tax_invoice(invoice.company, tax_enabled=tax_enabled)

        from core.services.billing import place_of_supply_known

        pending_confirms = []
        if (
            tax_enabled
            and not place_of_supply_known(
                party_state=invoice.supplier.state or "",
                party_gstin=invoice.supplier.gstin or "",
            )
            and not confirm_blank_pos
        ):
            pending_confirms.append((
                HelpCode.PLACE_OF_SUPPLY_UNRESOLVED,
                "Place of supply is blank. Confirm this purchase is intra-state, or set the supplier state/GSTIN.",
            ))
        else:
            assert_place_of_supply_for_gst(
                company=invoice.company,
                party_state=invoice.supplier.state or "",
                party_gstin=invoice.supplier.gstin or "",
                tax_enabled=tax_enabled,
            )

        PurchaseService._assert_composition_supplier_gst(invoice, items)
        dup = PurchaseService._assert_duplicate_supplier_bill(
            invoice, confirm_duplicate_bill=confirm_duplicate_bill
        )
        if dup:
            pending_confirms.append(dup)

        # RCM: ensure memo/payable even if draft was saved before RCM flag.
        if invoice.is_reverse_charge and invoice.purchase_type == PurchaseInvoice.PurchaseType.GST:
            if (invoice.rcm_taxable or 0) == 0 and (invoice.cgst_total or 0) + (invoice.sgst_total or 0) + (
                invoice.igst_total or 0
            ) > 0:
                apply_rcm_memo_after_tax(invoice, items)
            else:
                # Header already memoized. Restore charged tax from the memo (and
                # leftover line cess the prior path failed to clear) so
                # apply_rcm_memo_after_tax can rewrite the memo and zero lines.
                leftover_cess = sum(
                    (Decimal(str(getattr(it, "cess", 0) or 0)) for it in items),
                    Decimal("0"),
                )
                invoice.cgst_total = Decimal(str(invoice.rcm_cgst or 0))
                invoice.sgst_total = Decimal(str(invoice.rcm_sgst or 0))
                invoice.igst_total = Decimal(str(invoice.rcm_igst or 0))
                invoice.cess_total = max(Decimal(str(invoice.rcm_cess or 0)), leftover_cess)
                apply_rcm_memo_after_tax(invoice, items)
                for item in items:
                    if item.pk:
                        item.save(update_fields=["cgst", "sgst", "igst", "cess", "line_total"])
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
                # CHG-02 pattern: HSN on a *purchase* is not filed HSN-wise by the
                # buyer (the supplier's invoice carries it; 3B ITC is an
                # aggregate, GSTR-2B matching is by invoice not HSN). Recording
                # the purchase must not be blocked because the HSN hasn't been
                # looked up yet — warn and let the user add it before filing.
                warnings.append(
                    f"{len(missing_hsn)} line(s) missing HSN — add it before filing GSTR / "
                    "for a complete purchase register."
                )
        rcm_pending, warnings = PurchaseService._unregistered_rcm_gate(
            invoice, items, confirm_no_rcm=confirm_no_rcm, warnings=warnings
        )
        if rcm_pending:
            pending_confirms.append(rcm_pending)
        if pending_confirms:
            raise_confirm_required(
                [code for code, _msg in pending_confirms],
                " ".join(msg for _code, msg in pending_confirms),
            )
        assert_invoice_tds_exclusive(invoice)
        assert_claimable_itc_allowed(invoice, goods_will_be_received=True)

        if (invoice.notes or "").strip() == "TALLY_OPENING" and not getattr(
            invoice, "is_opening_balance", False
        ):
            raise BusinessRuleError(
                "TALLY_OPENING notes are not accepted. Opening invoices must be imported via Tally adapter."
            )
        is_tally_opening = bool(getattr(invoice, "is_opening_balance", False))
        # CR-023: period gate before number/status/stock (purchase twin of sales).
        if not is_tally_opening:
            from reporting.gst_periods import assert_period_allows_money_amend

            assert_period_allows_money_amend(invoice.company, invoice.invoice_date)

        # CR-025: Resolve company_gstin, validate multi-GSTIN, and recompute totals
        # BEFORE allocating document sequence numbers.
        if invoice.company_gstin_id is None:
            from accounts.models import CompanyGstin

            active = list(
                CompanyGstin.objects.filter(company=invoice.company, is_active=True).order_by(
                    "-is_primary", "id"
                )
            )
            if len(active) > 1:
                raise BusinessRuleError(
                    "company_gstin is required when multiple GSTINs are active."
                )
            if len(active) == 1:
                invoice.company_gstin = active[0]

        # R2-001 / W0-02: recompute tax against the stamped filing GSTIN.
        recompute_totals_for_stamped_gstin(
            invoice,
            items,
            party_state=invoice.supplier.state,
            party_gstin=invoice.supplier.gstin or "",
            tax_enabled=tax_enabled,
            item_model=PurchaseItem,
            confirm_gstin_total_change=confirm_gstin_total_change,
            is_opening=is_tally_opening,
        )

        # R1-013: company-level series-scope policy (not "did a gstin resolve").
        from core.services.document_numbers import series_identity

        _gk, _fy, _on = series_identity(
            invoice.company, invoice.company_gstin, invoice.invoice_date
        )
        invoice.number = invoice.number or DocumentNumberService.next_number(
            invoice.company,
            "PURCHASE_INVOICE",
            gstin=_gk or None,
            on_date=_on,
        )
        invoice.status = PurchaseInvoice.Status.COMPLETED
        invoice.completed_at = timezone.now()
        invoice.updated_by = user
        # R-023: rate-only TDS (194C etc.) folds amount from taxable on Complete.
        invoice.tds_amount = fold_tds_from_rate(
            tds_rate=getattr(invoice, "tds_rate", 0),
            tds_amount=getattr(invoice, "tds_amount", 0),
            taxable_total=invoice.taxable_total,
            document=invoice,
        )
        # CR-035: re-verify TDS exclusivity after rate fold in case tds_rate was provided without explicit tds_amount
        assert_invoice_tds_exclusive(invoice)
        invoice.save()

        if not is_tally_opening:
            from reporting.gst_periods import mark_period_dirty_if_snapshotted

            mark_period_dirty_if_snapshotted(invoice.company, invoice.invoice_date)

        # Stock was already received (per product) when this bill was raised
        # from a completed GRN. Posting PURCHASE again for that quantity would
        # double on-hand and the FIFO layers -- but the draft bill can still be
        # edited (a corrected quantity, or a line the GRN never covered)
        # before Complete, and that extra quantity was never received, so it
        # must still be posted. Track remaining already-received quantity per
        # product rather than skipping the whole invoice.
        grn_received_by_product: dict[int, Decimal] = {}
        for row in GoodsReceiptItem.objects.filter(
            goods_receipt__company_id=invoice.company_id,
            goods_receipt__converted_purchase_id=invoice.pk,
            goods_receipt__status=GoodsReceipt.Status.COMPLETED,
        ).values("product_id", "quantity_accepted"):
            pid = row["product_id"]
            grn_received_by_product[pid] = grn_received_by_product.get(pid, Decimal("0")) + Decimal(
                str(row["quantity_accepted"] or 0)
            )

        # DATA-01: Sort items deterministically to guarantee deadlock-free lock acquisition
        sorted_items = sorted(
            items,
            key=lambda it: (
                it.product_id or 0,
                getattr(it, "batch_id", 0) or 0,
                it.pk or 0,
            ),
        )
        for item in sorted_items:
            # Opening outstanding is a balance, not goods received.
            if is_tally_opening:
                break
            # CR-023: non-inventory / service lines do not move stock or require batch/serial tracking
            if not tracks_inventory(item.product):
                continue
            if item.product.track_batch and not item.batch_id:
                if not item.batch_no:
                    raise BusinessRuleError(f"A batch is required for tracked product '{item.product.name}'.")
                # R-055: same hard-error as item_stock.get_or_create_batch —
                # an expiry clash must 400, not keep the existing lot's date.
                item.batch = get_or_create_batch(
                    company=invoice.company,
                    product=item.product,
                    batch_no=item.batch_no,
                    expiry_date=item.exp_date,
                    manufacturing_date=item.mfg_date,
                    user=user,
                )
                item.save(update_fields=["batch"])
            if item.product.track_serial:
                from inventory.models import SerialNumber

                numbers = list(item.serial_numbers or [])
                found = dict(
                    SerialNumber.objects.filter(
                        company=invoice.company,
                        product=item.product,
                        serial_number__in=numbers,
                    ).values_list("serial_number", "status")
                )
                # A serial already on hand is expected when this bill follows a goods receipt that
                # registered it. One that is sold (or otherwise not available) cannot be received
                # again: posting +1 stock for it with no serial row would corrupt both.
                unavailable = sorted(n for n, st in found.items() if st != SerialNumber.Status.AVAILABLE)
                if unavailable:
                    raise BusinessRuleError(
                        f"Serial number(s) {', '.join(unavailable[:5])} on {item.product.name} are already "
                        "in use and cannot be received again."
                    )
                existing = set(found)
                missing = [n for n in numbers if n not in existing]
                if missing:
                    SerialNumberService.receive(
                        company=invoice.company, product=item.product, warehouse=invoice.warehouse,
                        numbers=missing, quantity=len(missing), user=user,
                    )
            if not is_tally_opening:
                qty = _line_stock_qty(item.product, item.quantity, getattr(item, "unit_name", None))
                # CR-032 / CR-033: layers stay at taxable/commercial line cost only.
                # additional_charges and BoE BCD (and ineligible customs) are
                # expensed to GL 5110 by PostingService — never capitalized into
                # unit_cost / FIFO layers. Do not read invoice.bill_of_entry.* here.
                # CR-024: FIFO layer unit cost must be net of line discount (taxable_amount / base qty)
                if qty and Decimal(str(qty)) > 0:
                    unit_cost = (Decimal(str(item.taxable_amount)) / Decimal(str(qty))).quantize(
                        Decimal("0.0001")
                    )
                else:
                    unit_cost = _line_stock_cost(
                        item.product, item.unit_price, getattr(item, "unit_name", None)
                    )
                # Only touch the posted quantity when this product actually
                # had a GRN receipt against this invoice -- otherwise this
                # must behave exactly as it always has (including
                # post_movement's own validation of a zero/negative
                # quantity). unit_cost above is deliberately computed from the
                # full line, not the reduced post_qty, since taxable_amount is
                # for the whole line.
                already = grn_received_by_product.get(item.product_id, Decimal("0"))
                post_qty = qty
                if already > 0:
                    qty_decimal = Decimal(str(qty)) if qty else Decimal("0")
                    consumed = min(qty_decimal, already)
                    grn_received_by_product[item.product_id] = already - consumed
                    post_qty = qty_decimal - consumed
                    if post_qty <= 0:
                        continue
                InventoryService.post_movement(
                    company=invoice.company,
                    warehouse=invoice.warehouse,
                    product=item.product,
                    batch=item.batch,
                    movement_type=MovementType.PURCHASE,
                    quantity=post_qty,
                    unit_cost=unit_cost,
                    reference_type="purchase_invoice",
                    reference_id=invoice.pk,
                    user=user,
                )
        if not is_tally_opening:
            if invoice.company.accounting_enabled:
                from accounting.services import PostingService, apply_specified_person_tds

                apply_specified_person_tds(invoice)
                if getattr(invoice.supplier, "income_tax_specified_person", False) and (
                    invoice.tds_section or ""
                ).strip():
                    invoice.save(update_fields=["tds_rate", "tds_amount", "updated_at"])
                PostingService.post_purchase(invoice, user)
                emit("document.completed", document=invoice, user=user, event="purchase_invoice.completed")
            record_document_event(
                document=invoice, user=user, event="purchase_invoice.completed",
                before={"status": "DRAFT"},
            )
            from planwave.services import stamp_document_party
            from planwave.finish import classify_purchase_bill

            stamp_document_party(invoice)
            classify_purchase_bill(invoice)
            from core.models import StatutoryDocumentEvent, log_statutory_event

            log_statutory_event(
                company=invoice.company,
                entity_type="purchase_invoice",
                entity_id=invoice.pk,
                event_type=StatutoryDocumentEvent.EventType.COMPLETE,
                payload={
                    "number": invoice.number,
                    "grand_total": str(invoice.grand_total),
                    **(
                        {"tds_override": invoice._tds_override}
                        if getattr(invoice, "_tds_override", None)
                        else {}
                    ),
                },
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
        invoice = PurchaseInvoice.objects.select_for_update().get(
            pk=invoice.pk, company_id=invoice.company_id
        )
        from reporting.gst_periods import assert_period_allows_money_amend

        assert_period_allows_money_amend(invoice.company, invoice.invoice_date, allow_soft_closed=True)
        if invoice.status == PurchaseInvoice.Status.CANCELLED:
            raise BusinessRuleError("Purchase is already cancelled.")
        if invoice.returns.filter(status=PurchaseReturn.Status.COMPLETED).exists():
            raise BusinessRuleError("Cannot cancel a purchase with completed returns.")
        # CR-035 / R2-005: draft / in-progress returns would be orphaned.
        if invoice.returns.exclude(
            status__in=(PurchaseReturn.Status.COMPLETED, PurchaseReturn.Status.CANCELLED)
        ).exists():
            raise BusinessRuleError(
                "Cancel or delete the draft purchase return(s) against this bill first."
            )
        # CR-034: completed CN/DN leave AP/GSTR history — cancel would orphan them.
        if invoice.credit_notes.filter(status=PurchaseCreditNote.Status.COMPLETED).exists() or invoice.debit_notes.filter(
            status=PurchaseDebitNote.Status.COMPLETED
        ).exists():
            raise BusinessRuleError(
                "Cannot cancel a purchase with completed credit or debit notes. "
                "Cancel the note(s) first."
            )
        # CR-097: draft notes would also be orphaned against a cancelled bill.
        if invoice.credit_notes.exclude(
            status__in=(PurchaseCreditNote.Status.COMPLETED, PurchaseCreditNote.Status.CANCELLED)
        ).exists() or invoice.debit_notes.exclude(
            status__in=(PurchaseDebitNote.Status.COMPLETED, PurchaseDebitNote.Status.CANCELLED)
        ).exists():
            raise BusinessRuleError(
                "Cancel or delete the draft credit/debit note(s) against this bill first."
            )
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
                    # R2-004: post the reversal on the cancellation date, not the
                    # original invoice date.
                    PostingService.reverse(entry, user)
            # Reverse stock via ADJUSTMENT — movements stay append-only (§5.3).
            # BB-000718: retire the original PURCHASE layers (do not peel FIFO-oldest).
            from inventory.models import SerialNumber, StockBalance, StockMovement

            # CR-006: verify that tracked serial numbers have not already been sold or issued
            for item in invoice.items.select_related("product"):
                if item.product.track_serial and item.serial_numbers:
                    non_avail = SerialNumber.objects.filter(
                        company=invoice.company,
                        product=item.product,
                        serial_number__in=list(item.serial_numbers),
                    ).exclude(status=SerialNumber.Status.AVAILABLE)
                    if non_avail.exists():
                        bad_serials = list(non_avail.values_list("serial_number", flat=True)[:5])
                        raise BusinessRuleError(
                            f"Cannot cancel purchase invoice {invoice.number}: one or more serialized "
                            f"items ({', '.join(bad_serials)}) have already been sold or issued. "
                            f"Create a Purchase Return instead."
                        )

            # CR-006: verify remaining stock on hand before negative adjustment
            for move in StockMovement.objects.filter(
                company=invoice.company,
                movement_type=MovementType.PURCHASE,
                reference_type="purchase_invoice",
                reference_id=str(invoice.pk),
            ):
                req_qty = abs(Decimal(str(move.quantity)))
                bal = StockBalance.objects.filter(
                    company=invoice.company,
                    warehouse=move.warehouse or invoice.warehouse,
                    product=move.product,
                    batch=move.batch,
                ).first()
                # CR-002: gate on the real company policy field. `allow_negative_stock`
                # was never defined on Company (only `negative_stock_policy`), so the
                # old getattr() default made this guard unconditional and blind to a
                # WARN-policy company that is otherwise allowed to drive stock negative.
                if (
                    bal
                    and bal.on_hand < req_qty
                    and (getattr(invoice.company, "negative_stock_policy", "BLOCK") or "BLOCK") == "BLOCK"
                ):
                    raise BusinessRuleError(
                        f"Cannot cancel purchase invoice {invoice.number}: on-hand stock for "
                        f"{move.product.name} ({bal.on_hand}) is less than the purchase quantity ({req_qty})."
                    )

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
            PurchaseService._unwind_grn_stock(invoice, user)
            for item in invoice.items.select_related("product"):
                if item.product.track_serial and item.serial_numbers:
                    SerialNumber.objects.filter(
                        company=invoice.company,
                        product=item.product,
                        serial_number__in=list(item.serial_numbers),
                        status=SerialNumber.Status.AVAILABLE,
                    ).delete()
        invoice.status = PurchaseInvoice.Status.CANCELLED
        invoice.cancelled_at = timezone.now()
        invoice.updated_by = user
        invoice.save()
        record_document_event(document=invoice, user=user, event="purchase_invoice.cancelled")
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

    @staticmethod
    def _unwind_grn_stock(invoice, user):
        """Reverse goods-receipt layers that this bill did not post a second time."""
        from inventory.models import SerialNumber, StockBalance, StockMovement

        grns = list(
            GoodsReceipt.objects.filter(
                company_id=invoice.company_id,
                converted_purchase_id=invoice.pk,
                status=GoodsReceipt.Status.COMPLETED,
            )
        )
        for grn in grns:
            moves = list(
                StockMovement.objects.filter(
                    company=invoice.company,
                    movement_type=MovementType.PURCHASE,
                    reference_type="goods_receipt",
                    reference_id=str(grn.pk),
                )
            )
            for move in moves:
                req_qty = abs(Decimal(str(move.quantity)))
                bal = StockBalance.objects.filter(
                    company=invoice.company,
                    warehouse=move.warehouse or invoice.warehouse,
                    product=move.product,
                    batch=move.batch,
                ).first()
                if (
                    bal
                    and bal.on_hand < req_qty
                    and (getattr(invoice.company, "negative_stock_policy", "BLOCK") or "BLOCK") == "BLOCK"
                ):
                    raise BusinessRuleError(
                        f"Cannot cancel purchase invoice {invoice.number}: on-hand stock for "
                        f"{move.product.name} ({bal.on_hand}) is less than the receipt quantity ({req_qty})."
                    )
            for move in moves:
                InventoryService.post_movement(
                    company=invoice.company,
                    warehouse=move.warehouse or invoice.warehouse,
                    product=move.product,
                    batch=move.batch,
                    movement_type=MovementType.ADJUSTMENT,
                    quantity=-abs(Decimal(str(move.quantity))),
                    unit_cost=move.unit_cost,
                    reference_type="goods_receipt_unwind",
                    reference_id=grn.pk,
                    reason=f"Cancellation of {invoice.number}",
                    user=user,
                )
                InventoryService.retire_source_layers(move, abs(Decimal(str(move.quantity))))
            for item in grn.items.select_related("product"):
                if not item.product.track_serial or not item.serial_numbers:
                    continue
                non_avail = SerialNumber.objects.filter(
                    company=invoice.company,
                    product=item.product,
                    serial_number__in=list(item.serial_numbers),
                ).exclude(status=SerialNumber.Status.AVAILABLE)
                if non_avail.exists():
                    raise BusinessRuleError(
                        f"Cannot cancel purchase invoice {invoice.number}: serialized "
                        f"'{item.product.name}' received on the GRN is no longer available."
                    )
                SerialNumber.objects.filter(
                    company=invoice.company,
                    product=item.product,
                    serial_number__in=list(item.serial_numbers),
                    status=SerialNumber.Status.AVAILABLE,
                ).delete()

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
                        f"tracked product '{product.name}'.",
                        code="serial_required",
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
                condition=line.get("condition") or PurchaseReturnItem.Condition.SELLABLE,
                # CR-045: snapshot unit from line / source invoice for stock conversion.
                unit_name=(
                    line.get("unit_name")
                    or getattr(line.get("source_item"), "unit_name", None)
                    or getattr(product.unit, "short_name", None)
                    or "PCS"
                ),
            ))
        source = purchase_return.purchase_invoice
        tax_enabled = source.purchase_type == PurchaseInvoice.PurchaseType.GST if source else True
        from .notes_services import _invoice_intra_state as _pi_intra

        get_tax_engine(purchase_return.company).compute_document_totals(
            purchase_return, items,
            tax_enabled=tax_enabled,
            intra_state=_pi_intra(source) if source else False,
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
        items = list(purchase_return.items.select_related("product", "product__alternate_unit"))
        if not items:
            raise BusinessRuleError("Cannot complete a return without line items.")
        # CR-036: lock source invoice before remaining-qty headroom check.
        invoice = None
        if purchase_return.purchase_invoice_id:
            invoice = PurchaseInvoice.objects.select_for_update().get(
                pk=purchase_return.purchase_invoice_id,
                company_id=purchase_return.company_id,
            )
        # BB-000020: GST-registered companies cannot orphan returns (AP/GSTR distortion).
        if purchase_return.company.is_gst_registered and invoice is None:
            raise BusinessRuleError(
                "GST-registered companies require a linked purchase invoice on purchase returns."
            )
        if purchase_return.company.accounting_enabled and invoice is None:
            raise BusinessRuleError(
                "Accounting-enabled companies require a linked purchase invoice on purchase returns."
            )
        if invoice and invoice.status not in (
            PurchaseInvoice.Status.COMPLETED,
            PurchaseInvoice.Status.RETURNED,
        ):
            raise BusinessRuleError("Purchase return must reference a completed purchase invoice.")
        if (
            invoice
            and purchase_return.return_date
            and invoice.invoice_date
            and purchase_return.return_date < invoice.invoice_date
        ):
            raise BusinessRuleError(
                "Return date cannot be before the original invoice date."
            )

        if invoice:
            # CR-131: headroom in base units so BOX vs PCS cannot over-return stock.
            unit_names = _invoice_unit_name_by_product(invoice)
            purchased = defaultdict(Decimal)
            for row in invoice.items.select_related("product", "product__alternate_unit"):
                purchased[row.product_id] += _line_stock_qty(
                    row.product, row.quantity, getattr(row, "unit_name", None)
                )
            already = PurchaseService._returned_quantities(invoice)
            requested = defaultdict(Decimal)
            for item in items:
                unit_name = getattr(item, "unit_name", None) or unit_names.get(item.product_id)
                requested[item.product_id] += _line_stock_qty(
                    item.product, item.quantity, unit_name
                )
            for product_id, qty in requested.items():
                remaining = purchased.get(product_id, Decimal("0")) - already.get(
                    product_id, Decimal("0")
                )
                if qty > remaining:
                    raise BusinessRuleError(
                        f"Return quantity {qty} exceeds remaining returnable quantity {remaining}."
                    )

        # R1-013 / R2-014: same company-level series-scope policy as
        # PurchaseService.complete, so the return and its invoice share a family.
        from core.services.document_numbers import series_identity

        _gk, _fy, _on = series_identity(
            purchase_return.company,
            getattr(invoice, "company_gstin", None) if invoice else None,
            purchase_return.return_date,
        )
        purchase_return.number = DocumentNumberService.next_number(
            purchase_return.company,
            "PURCHASE_RETURN",
            gstin=_gk or None,
            on_date=_on,
        )
        purchase_return.status = PurchaseReturn.Status.COMPLETED
        purchase_return.completed_at = timezone.now()
        purchase_return.updated_by = user
        purchase_return.save()

        from inventory.models import SerialNumber, StockMovement as CostMove
        from inventory.services import SerialNumberService

        unit_names = _invoice_unit_name_by_product(invoice)

        def _item_stock_qty(item):
            unit_name = getattr(item, "unit_name", None) or unit_names.get(item.product_id)
            return _line_stock_qty(item.product, item.quantity, unit_name)

        def _receipt_move_filter():
            if invoice is None:
                return Q(pk__in=[])
            grn_ids = [
                str(pk)
                for pk in GoodsReceipt.objects.filter(
                    company_id=invoice.company_id,
                    converted_purchase_id=invoice.pk,
                ).values_list("pk", flat=True)
            ]
            clause = Q(reference_type="purchase_invoice", reference_id=str(invoice.pk))
            if grn_ids:
                clause = clause | Q(reference_type="goods_receipt", reference_id__in=grn_ids)
            return clause

        def _return_unit_cost(product, fallback_price):
            if invoice is None:
                return fallback_price
            move = (
                CostMove.objects.filter(
                    company=purchase_return.company,
                    movement_type=MovementType.PURCHASE,
                    product=product,
                )
                .filter(_receipt_move_filter())
                .order_by("id")
                .first()
            )
            # Prefer the goods-receipt layer cost when the bill did not post stock.
            grn_move = (
                CostMove.objects.filter(
                    company=purchase_return.company,
                    movement_type=MovementType.PURCHASE,
                    reference_type="goods_receipt",
                    product=product,
                )
                .filter(_receipt_move_filter())
                .order_by("id")
                .first()
            )
            chosen = grn_move or move
            if chosen is not None and chosen.unit_cost is not None:
                return chosen.unit_cost
            return fallback_price

        for item in items:
            # CR-026: non-inventory / service lines do not move stock or require serial/batch transition
            if not tracks_inventory(item.product):
                continue
            if item.product.track_serial:
                if not item.serial_numbers:
                    raise BusinessRuleError(
                        f"Serial numbers are required to complete return of '{item.product.name}'.",
                        code="serial_required",
                    )
                SerialNumberService.transition(
                    company=purchase_return.company,
                    product=item.product,
                    warehouse=invoice.warehouse if invoice else None,
                    numbers=item.serial_numbers,
                    quantity=item.quantity,
                    source=SerialNumber.Status.AVAILABLE,
                    target=(
                        SerialNumber.Status.SCRAPPED
                        if item.condition == PurchaseReturnItem.Condition.DAMAGED
                        else SerialNumber.Status.RETURNED
                    ),
                    user=user,
                )
            damaged = item.condition == PurchaseReturnItem.Condition.DAMAGED

            def _post_return_qty(*, batch, quantity, unit_cost):
                InventoryService.post_movement(
                    company=purchase_return.company,
                    warehouse=invoice.warehouse if invoice else None,
                    product=item.product,
                    batch=batch,
                    movement_type=MovementType.ADJUSTMENT if damaged else MovementType.PURCHASE_RETURN,
                    quantity=(-quantity if damaged else quantity),
                    unit_cost=unit_cost,
                    reason="DAMAGED" if damaged else "",
                    reference_type="purchase_return_damaged" if damaged else "purchase_return",
                    reference_id=purchase_return.pk,
                    user=user,
                )
                if invoice is not None:
                    remaining = Decimal(str(quantity))
                    for move in CostMove.objects.filter(
                        company=purchase_return.company,
                        movement_type=MovementType.PURCHASE,
                        product=item.product,
                        batch=batch,
                    ).filter(_receipt_move_filter()).order_by("id"):
                        if remaining <= 0:
                            break
                        take = min(remaining, abs(Decimal(str(move.quantity))))
                        InventoryService.retire_source_layers(move, take)
                        remaining -= take

            batch = getattr(item, "batch", None)
            stock_qty = _item_stock_qty(item)
            # R-039 / BB-000383: unspecified lot — retire FEFO (earliest expiry),
            # not LIFO by movement id. Locks stay inside this atomic Complete.
            if item.product.track_batch and batch is None and invoice is not None:
                from inventory.models import BatchLot

                warehouse = invoice.warehouse
                remaining = stock_qty
                lot_ids = list(
                    InventoryValuationService.fefo_batches(
                        purchase_return.company, item.product, warehouse
                    ).values_list("pk", flat=True)
                )
                locked = {
                    lot.pk: lot
                    for lot in BatchLot.objects.filter(pk__in=lot_ids).select_for_update()
                }
                for lot_id in lot_ids:
                    if remaining <= 0:
                        break
                    lot = locked.get(lot_id)
                    if lot is None:
                        continue
                    available = InventoryService.available_quantity(
                        purchase_return.company, item.product, warehouse, lot
                    )
                    take = min(remaining, available)
                    if take <= 0:
                        continue
                    _post_return_qty(
                        batch=lot,
                        quantity=take,
                        unit_cost=_return_unit_cost(item.product, item.unit_price),
                    )
                    remaining -= take
                if remaining > 0:
                    raise BusinessRuleError(
                        f"Cannot return {item.quantity} of batched '{item.product.name}' without lot coverage."
                    )
                continue
            _post_return_qty(
                batch=batch,
                quantity=stock_qty,
                unit_cost=_return_unit_cost(item.product, item.unit_price),
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
            inv_discount = Decimal(str(invoice.invoice_discount or 0))
            ratio = Decimal("1")
            if inv_taxable > 0 and not fully_returned:
                ratio = min(Decimal("1"), ret_taxable / inv_taxable)
            elif not fully_returned:
                inv_grand = Decimal(str(invoice.grand_total or 0))
                ret_grand = sum(
                    (Decimal(str(getattr(i, "line_total", None) or i.taxable_amount or 0)) for i in items),
                    Decimal("0"),
                )
                ratio = min(Decimal("1"), ret_grand / inv_grand) if inv_grand > 0 else Decimal("0")
            # R2-015: on the return that closes the invoice, give the CN the EXACT
            # unallocated remainder of the invoice-level discount (what prior
            # auto-CNs on this invoice haven't already taken) so repeated partial
            # returns never leave a few paise of AP residue. Freight/additional
            # charges are prorated the same way.
            if fully_returned:
                _prior_d = PurchaseCreditNote.objects.filter(
                    purchase_invoice=invoice,
                    purchase_return__isnull=False,
                    status=PurchaseCreditNote.Status.COMPLETED,
                ).exclude(purchase_return=purchase_return).aggregate(
                    d=Sum("invoice_discount")
                )["d"] or Decimal("0")
                note.invoice_discount = (inv_discount - _prior_d).quantize(Decimal("0.01"))
            else:
                note.invoice_discount = (inv_discount * ratio).quantize(Decimal("0.01"))
            inv_charges = Decimal(str(invoice.additional_charges or 0))
            if fully_returned:
                _prior_c = PurchaseCreditNote.objects.filter(
                    purchase_invoice=invoice,
                    purchase_return__isnull=False,
                    status=PurchaseCreditNote.Status.COMPLETED,
                ).exclude(purchase_return=purchase_return).aggregate(
                    c=Sum("additional_charges")
                )["c"] or Decimal("0")
                note.additional_charges = (inv_charges - _prior_c).quantize(Decimal("0.01"))
            else:
                note.additional_charges = (inv_charges * ratio).quantize(Decimal("0.01"))
            note.save(update_fields=["invoice_discount", "additional_charges"])
            # BB-000364: map each returned line back to its originating invoice
            # line (by product) so the auto CN carries the invoiced HSN/lineage
            # instead of the product master's current (possibly since-changed) HSN.
            items_by_id = {inv_item.id: inv_item for inv_item in invoice.items.all()}
            remaining_by_line = {
                inv_item.id: Decimal(str(inv_item.quantity))
                for inv_item in items_by_id.values()
            }
            lines_by_product = {}
            for inv_item in items_by_id.values():
                lines_by_product.setdefault(inv_item.product_id, []).append(inv_item.id)
            items_data = []
            for item in items:
                need = Decimal(str(item.quantity))
                for lid in lines_by_product.get(item.product_id, []):
                    if need <= 0:
                        break
                    avail = remaining_by_line.get(lid, Decimal("0"))
                    if avail <= 0:
                        continue
                    take = min(need, avail)
                    remaining_by_line[lid] -= take
                    need -= take
                    source_item = items_by_id.get(lid)
                    items_data.append({
                        "product": item.product,
                        "description": getattr(item, "description", "") or "",
                        "quantity": take,
                        "unit_price": item.unit_price,
                        "discount_percent": item.discount_percent,
                        "gst_rate": item.gst_rate,
                        "cess_rate": getattr(item, "cess_rate", None)
                        if getattr(item, "cess_rate", None) is not None
                        else getattr(source_item, "cess_rate", Decimal("0")),
                        "source_item": source_item,
                        "hsn_code": getattr(source_item, "hsn_code", "") or "",
                    })
                if need > 0:
                    raise BusinessRuleError(
                        f"Return quantity for '{item.product.name}' exceeds remaining "
                        "returnable quantity on matching invoice lines."
                    )
            PurchaseNotesService.set_credit_note_items(note, items_data, user)
            PurchaseNotesService.complete_credit_note(
                note, user, confirm_paid_invoice=True, confirm_price_override=True
            )

        record_document_event(document=purchase_return, user=user, event="purchase_return.completed")
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
                        source=(
                            SerialNumber.Status.SCRAPPED
                            if item.condition == PurchaseReturnItem.Condition.DAMAGED
                            else SerialNumber.Status.RETURNED
                        ),
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
            damaged_moves = list(
                StockMovement.objects.filter(
                    company=purchase_return.company,
                    movement_type=InvMovementType.ADJUSTMENT,
                    reference_id=str(purchase_return.pk),
                ).filter(
                    Q(reference_type="purchase_return_damaged")
                    | Q(reference_type="purchase_return", reason="DAMAGED")
                )
            )
            invoice = purchase_return.purchase_invoice
            if return_moves:
                for move in return_moves:
                    inbound = InventoryService.post_movement(
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
                    peels = getattr(move, "layer_peels", None) or []
                    if peels:
                        InventoryService.restore_fifo_peels(move, inbound)
                    elif invoice is not None:
                        remaining = abs(Decimal(str(move.quantity)))
                        for src in StockMovement.objects.filter(
                            company=purchase_return.company,
                            movement_type=InvMovementType.PURCHASE,
                            reference_type="purchase_invoice",
                            reference_id=str(invoice.pk),
                            product=move.product,
                            batch=move.batch,
                        ).order_by("id"):
                            if remaining <= 0:
                                break
                            take = min(remaining, abs(Decimal(str(src.quantity))))
                            InventoryService.restore_source_layers(src, take)
                            remaining -= take
            if damaged_moves:
                for move in damaged_moves:
                    inbound = InventoryService.post_movement(
                        company=purchase_return.company,
                        warehouse=move.warehouse,
                        product=move.product,
                        batch=move.batch,
                        movement_type=MovementType.ADJUSTMENT,
                        quantity=abs(Decimal(str(move.quantity))),
                        unit_cost=move.unit_cost,
                        reference_type="purchase_return_damaged_cancel",
                        reference_id=purchase_return.pk,
                        reason=f"Restore damaged write-off of {purchase_return.number}",
                        user=user,
                    )
                    peels = getattr(move, "layer_peels", None) or []
                    if peels:
                        InventoryService.restore_fifo_peels(move, inbound)
                    elif invoice is not None:
                        remaining = abs(Decimal(str(move.quantity)))
                        for src in StockMovement.objects.filter(
                            company=purchase_return.company,
                            movement_type=InvMovementType.PURCHASE,
                            reference_type="purchase_invoice",
                            reference_id=str(invoice.pk),
                            product=move.product,
                            batch=move.batch,
                        ).order_by("id"):
                            if remaining <= 0:
                                break
                            take = min(remaining, abs(Decimal(str(src.quantity))))
                            InventoryService.restore_source_layers(src, take)
                            remaining -= take
            if not return_moves and not damaged_moves:
                raise BusinessRuleError(
                    "Cannot cancel this purchase return: original stock movements are missing. "
                    "Restore stock with a manual adjustment instead of inventing unbatched quantity."
                )
            if invoice and invoice.status == PurchaseInvoice.Status.RETURNED:
                from .models import PurchaseInvoice as PI
                from .models import PurchaseReturn as PR

                # CR-095 twin: lock bill before other_open check + status flip.
                invoice = PI.objects.select_for_update().get(
                    pk=invoice.pk,
                    company_id=purchase_return.company_id,
                )
                other_open = PR.objects.filter(
                    purchase_invoice=invoice,
                    status=PR.Status.COMPLETED,
                ).exclude(pk=purchase_return.pk).exists()
                if not other_open and invoice.status == PI.Status.RETURNED:
                    invoice.status = PI.Status.COMPLETED
                    invoice.save(update_fields=["status"])
            # BB-000263: cancel linked auto purchase CNs. Mark the return
            # CANCELLED *first* so `cancel_credit_note`'s "cancel the return
            # instead" guard (which fires only while the return is COMPLETED)
            # does not block this very flow.
            purchase_return.status = PurchaseReturn.Status.CANCELLED
            purchase_return.cancelled_at = timezone.now()
            purchase_return.updated_by = user
            purchase_return.save(update_fields=["status", "cancelled_at", "updated_by", "updated_at"])

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
        record_document_event(document=purchase_return, user=user, event="purchase_return.cancelled")
        emit("document.cancelled", document=purchase_return, user=user, event="purchase_return.cancelled")
        return purchase_return
