"""INVENTORY_RISK executors (R4). Both create DRAFT documents only: no stock moves and nothing is sent until a
person completes the transfer or sends the purchase order from the normal screens.

Each one re-reads the books at approval time. If the donor godown no longer has the stock (or the lot has
expired), the draft is stale and nothing is created.
"""

from __future__ import annotations

from decimal import Decimal

from core.exceptions import BusinessRuleError

from .. import error_codes as E
from . import ExecContext, StaleProposal


def execute_transfer(proposal, ctx: ExecContext) -> dict:
    from core.services.document_numbers import DocumentNumberService
    from inventory.models import BatchLot, StockTransfer, StockTransferLine, Warehouse
    from inventory.services import InventoryService
    from masters.models import Product

    company, user = ctx.company, ctx.company_user.user
    payload = proposal.effective_payload
    from_wh = Warehouse.objects.filter(company=company, pk=payload.get("from_warehouse_id")).first()
    to_wh = Warehouse.objects.filter(company=company, pk=payload.get("to_warehouse_id")).first()
    if from_wh is None or to_wh is None:
        raise StaleProposal("A godown on this draft no longer exists.")
    if from_wh.pk == to_wh.pk:
        raise BusinessRuleError("Source and destination must differ.", code=E.AGT_E_VALIDATION)
    for wh in (from_wh, to_wh):
        if getattr(wh, "is_system", False) or not getattr(wh, "is_active", True):
            raise StaleProposal(f"{wh.name} is not available for transfers any more.")

    prepared = []
    for line in payload.get("lines") or []:
        product = Product.objects.filter(company=company, pk=line.get("product_id")).first()
        if product is None or product.status != Product.Status.ACTIVE:
            raise StaleProposal("An item on this draft is no longer active.")
        qty = Decimal(str(line["qty"]))
        batch = None
        if line.get("batch_id"):
            batch = BatchLot.objects.filter(company=company, pk=line["batch_id"], product=product).first()
            if batch is None:
                raise StaleProposal(f"A lot of {product.name} no longer exists.")
            if getattr(company, "block_expired_stock", True) and batch.expiry_date and batch.expiry_date < ctx.today:
                raise StaleProposal(f"Lot {batch.batch_no} of {product.name} has expired.")
        available = InventoryService.available_quantity(company, product, warehouse=from_wh, batch=batch)
        if available < qty:
            raise StaleProposal(f"{from_wh.name} has only {available.normalize():f} of {product.name} now.")
        prepared.append((product, batch, qty))

    transfer = StockTransfer.objects.create(
        company=company, from_warehouse=from_wh, to_warehouse=to_wh, transfer_date=ctx.today,
        notes=(f"Suggested by the inventory agent (draft #{proposal.pk}). {payload.get('notes') or ''}").strip()[:2000],
        created_by=user, updated_by=user,
    )
    transfer.number = DocumentNumberService.next_number(company, "STOCK_TRANSFER")
    transfer.save(update_fields=["number"])
    StockTransferLine.objects.bulk_create([
        StockTransferLine(transfer=transfer, company_id=company.id, product=p, batch=b, quantity=q) for p, b, q in prepared
    ])
    return {
        "type": "stock_transfer", "id": transfer.pk, "number": transfer.number, "status": transfer.status,
        "lines": len(prepared), "ref": ctx.external_ref, "date": ctx.today.isoformat(),
    }


def execute_purchase(proposal, ctx: ExecContext) -> dict:
    """One draft purchase order, made by the same function the Purchase planning page uses."""
    from inventory.planning import materialize_supplier_drafts

    payload = proposal.effective_payload
    rows = [
        {
            "product_id": line["product_id"], "suggested_qty": line["qty"], "supplier_id": payload.get("supplier_id"),
            "warehouse_name": line.get("warehouse_name") or "",
        }
        for line in payload.get("lines") or []
    ]
    created, needs_supplier, _needs_transfer = materialize_supplier_drafts(ctx.company, ctx.company_user.user, rows)
    if needs_supplier or not created:
        raise BusinessRuleError("This draft has no supplier.", code=E.AGT_E_VALIDATION)
    return {
        "type": "purchase_order", "ids": [o.pk for o in created], "number": created[0].number,
        "ref": ctx.external_ref, "date": ctx.today.isoformat(),
    }


def acknowledge_needs_supplier(proposal, ctx: ExecContext) -> dict:
    """Nothing to create: the person has seen which items need a supplier chosen."""
    return {"type": "acknowledged", "items": len(proposal.effective_payload.get("lines") or []), "ref": ctx.external_ref, "date": ctx.today.isoformat()}
