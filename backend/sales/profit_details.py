"""Line-level profit for one invoice. Does not rewrite InvoiceProfitSnapshot."""

from __future__ import annotations

from decimal import Decimal

from core.services.billing import q2
from inventory.item_stock import tracks_inventory

FORMULA = "Profit = Sales amount − Total cost − GST collected"


def _line_name(item) -> str:
    description = (getattr(item, "description", None) or "").strip()
    if description:
        return description
    return item.product.name


def _tax_payable(invoice) -> Decimal:
    if getattr(invoice, "is_reverse_charge", False):
        return Decimal("0.00")
    tax = (
        Decimal(str(invoice.cgst_total or 0))
        + Decimal(str(invoice.sgst_total or 0))
        + Decimal(str(invoice.igst_total or 0))
        + Decimal(str(getattr(invoice, "cess_total", 0) or 0))
    )
    from core.services.charges import charge_line

    # Charge GST is folded into the invoice tax totals. The split (CGST vs IGST)
    # does not change the amount to subtract.
    charge = charge_line(invoice, intra_state=True)
    if charge is not None:
        tax -= (
            Decimal(str(charge.cgst or 0))
            + Decimal(str(charge.sgst or 0))
            + Decimal(str(charge.igst or 0))
            + Decimal(str(getattr(charge, "cess", 0) or 0))
        )
    if tax < 0:
        tax = Decimal("0")
    return q2(tax)


def _moves_by_product(invoice) -> dict:
    """One query for every line, instead of one per line."""
    from sales.cogs_service import CogsService

    grouped: dict = {}
    for move in CogsService.invoice_sale_moves(invoice):
        grouped.setdefault(move.product_id, []).append(move)
    return grouped


def _completed_unit_cost(item, moves):
    qty = Decimal("0")
    cost = Decimal("0")
    saw_cost = False
    for move in moves:
        taken = abs(Decimal(str(move.quantity or 0)))
        if move.unit_cost is None:
            continue
        saw_cost = True
        qty += taken
        cost += taken * Decimal(str(move.unit_cost))
    if saw_cost and qty > 0:
        return q2(cost / qty), False
    fallback = Decimal(str(getattr(item.product, "purchase_price", 0) or 0))
    return q2(fallback), True


def invoice_profit_details(invoice) -> dict:
    from core.exceptions import BusinessRuleError

    if invoice.status == "CANCELLED":
        raise BusinessRuleError("A cancelled invoice has no profit.")
    items = list(invoice.items.select_related("product", "product__unit").all())
    status = invoice.status
    estimated = status == "DRAFT"
    draft_costs = {}
    if estimated:
        from inventory.services import InventoryValuationService

        stocked = [item.product for item in items if tracks_inventory(item.product)]
        if stocked:
            draft_costs = InventoryValuationService.bulk_unit_cost(
                invoice.company, stocked, warehouse=invoice.warehouse,
            )

    moves_by_product = {} if estimated else _moves_by_product(invoice)
    cost_incomplete = False
    lines = []
    total_cost = Decimal("0")
    for item in items:
        qty = Decimal(str(item.quantity or 0))
        if not tracks_inventory(item.product):
            lines.append({
                "name": _line_name(item),
                "quantity": qty,
                "unit_name": item.unit_name or "PCS",
                "unit_cost": None,
                "line_cost": Decimal("0.00"),
                "fell_back_to_purchase_price": False,
            })
            continue
        fell_back = False
        if estimated:
            raw = draft_costs.get(item.product.pk)
            if not raw:
                # No cost yet: say so. A silent zero would overstate profit.
                cost_incomplete = True
                unit_cost = None
                line_cost = Decimal("0.00")
            else:
                unit_cost = q2(raw)
                line_cost = q2(Decimal(str(raw)) * qty)
        else:
            unit_cost, fell_back = _completed_unit_cost(item, moves_by_product.get(item.product_id, []))
            line_cost = q2(Decimal(str(unit_cost or 0)) * qty)
        total_cost += line_cost
        lines.append({
            "name": _line_name(item),
            "quantity": qty,
            "unit_name": item.unit_name or "PCS",
            "unit_cost": unit_cost,
            "line_cost": line_cost,
            "fell_back_to_purchase_price": fell_back,
            "cost_missing": estimated and unit_cost is None,
        })

    # TCS is collected for the government, not earned, so it is not sales.
    sales_amount = q2(
        Decimal(str(invoice.grand_total or 0))
        - Decimal(str(invoice.additional_charges or 0))
        - Decimal(str(invoice.tcs_amount or 0))
    )
    total_cost = q2(total_cost)
    tax_payable = _tax_payable(invoice)
    profit = q2(sales_amount - total_cost - tax_payable)
    return {
        "lines": lines,
        "sales_amount": sales_amount,
        "total_cost": total_cost,
        "tax_payable": tax_payable,
        "profit": profit,
        "estimated": estimated,
        "cost_incomplete": cost_incomplete,
        "formula": FORMULA,
    }
