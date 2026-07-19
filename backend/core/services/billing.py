"""
Invoice Service — shared tax/discount/rounding math used by sales & purchases
(E3.2, E4.3). GST split: intra-state = CGST+SGST, inter-state = IGST.
"""

from decimal import ROUND_HALF_UP, Decimal

TWO_PLACES = Decimal("0.01")
RUPEE = Decimal("1")


def q2(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def is_intra_state(company_state: str, party_state: str) -> bool:
    """Missing party state defaults to intra-state (local trade)."""
    if not (party_state or "").strip():
        return True
    return (party_state or "").strip().lower() == (company_state or "").strip().lower()


def compute_document_totals(document, items, *, tax_enabled: bool, intra_state: bool):
    """
    Mutates each item's computed fields and the document's totals.
    Does not save — callers persist inside their own transaction.
    """
    subtotal = Decimal("0")
    discount_total = Decimal("0")
    taxable_total = Decimal("0")
    cgst_total = Decimal("0")
    sgst_total = Decimal("0")
    igst_total = Decimal("0")

    for item in items:
        gross = q2(Decimal(item.quantity) * Decimal(item.unit_price))
        discount = q2(gross * Decimal(item.discount_percent) / Decimal("100"))
        taxable = q2(gross - discount)
        rate = Decimal(item.gst_rate) if tax_enabled else Decimal("0")
        tax = taxable * rate / Decimal("100")

        if intra_state:
            item.cgst = q2(tax / 2)
            item.sgst = q2(tax / 2)
            item.igst = Decimal("0.00")
        else:
            item.cgst = Decimal("0.00")
            item.sgst = Decimal("0.00")
            item.igst = q2(tax)

        item.taxable_amount = taxable
        item.line_total = q2(taxable + item.cgst + item.sgst + item.igst)

        subtotal += gross
        discount_total += discount
        taxable_total += taxable
        cgst_total += item.cgst
        sgst_total += item.sgst
        igst_total += item.igst

    raw_total = taxable_total + cgst_total + sgst_total + igst_total
    grand_total = raw_total.quantize(RUPEE, rounding=ROUND_HALF_UP)

    document.subtotal = q2(subtotal)
    document.discount_total = q2(discount_total)
    document.taxable_total = q2(taxable_total)
    document.cgst_total = q2(cgst_total)
    document.sgst_total = q2(sgst_total)
    document.igst_total = q2(igst_total)
    document.round_off = q2(grand_total - raw_total)
    document.grand_total = q2(grand_total)
    return document
