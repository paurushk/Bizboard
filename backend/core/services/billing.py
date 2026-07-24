"""
Invoice Service — shared tax/discount/rounding math used by sales & purchases
(E3.2, E4.3). GST split: intra-state = CGST+SGST, inter-state = IGST.
"""

from decimal import ROUND_HALF_UP, Decimal

TWO_PLACES = Decimal("0.01")
RUPEE = Decimal("1")

DISCOUNT_AFTER_TAX = "AFTER_TAX"
DISCOUNT_BEFORE_TAX = "BEFORE_TAX"


def q2(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def extract_state_code(value: str | None) -> str | None:
    """Return GSTIN/state code (first two digits) when present."""
    if not value:
        return None
    trimmed = value.strip()
    if len(trimmed) >= 2 and trimmed[:2].isdigit():
        return trimmed[:2]
    return None


def place_of_supply_known(*, party_state: str = "", party_gstin: str = "") -> bool:
    """True when party has a usable state name or GSTIN state code."""
    if (party_state or "").strip():
        return True
    return extract_state_code(party_gstin) is not None


def is_intra_state(
    company_state: str,
    party_state: str,
    *,
    company_gstin: str = "",
    party_gstin: str = "",
) -> bool:
    """
    Prefer GSTIN state codes when available; else compare state names.
    Missing party state/GSTIN still returns True for calc fallback — callers must
    gate Complete via place_of_supply_known / company.assume_local_state_for_blank_party.
    """
    company_code = extract_state_code(company_gstin) or extract_state_code(company_state)
    party_code = extract_state_code(party_gstin) or extract_state_code(party_state)
    if company_code and party_code:
        return company_code == party_code

    a = (company_state or "").strip().lower()
    b = (party_state or "").strip().lower()
    if not b:
        return True
    if not a:
        return True
    return a == b


def _apply_line_tax(item, taxable: Decimal, rate: Decimal, *, tax_enabled: bool, intra_state: bool):
    tax = taxable * rate / Decimal("100") if tax_enabled else Decimal("0")
    if intra_state:
        half = q2(tax / 2)
        item.cgst = half
        item.sgst = q2(tax) - half  # residual so halves sum to q2(tax)
        item.igst = Decimal("0.00")
    else:
        item.cgst = Decimal("0.00")
        item.sgst = Decimal("0.00")
        item.igst = q2(tax)
    item.taxable_amount = taxable
    item.line_total = q2(taxable + item.cgst + item.sgst + item.igst)


def compute_document_totals(
    document,
    items,
    *,
    tax_enabled: bool,
    intra_state: bool,
    additional_charges: Decimal | None = None,
    invoice_discount: Decimal | None = None,
    auto_round_off: bool | None = None,
    invoice_discount_mode: str | None = None,
):
    """
    Mutates each item's computed fields and the document's totals.
    Does not save — callers persist inside their own transaction.

    invoice_discount_mode:
      AFTER_TAX  — subtract from grand total after GST (legacy default)
      BEFORE_TAX — allocate across line taxables proportionally, then compute GST
    """
    subtotal = Decimal("0")
    line_discount_total = Decimal("0")
    taxables: list[Decimal] = []

    for item in items:
        gross = q2(Decimal(item.quantity) * Decimal(item.unit_price))
        discount = q2(gross * Decimal(item.discount_percent) / Decimal("100"))
        taxable = q2(gross - discount)
        taxables.append(taxable)
        subtotal += gross
        line_discount_total += discount
        # stash rate for second pass
        item._billing_rate = Decimal(item.gst_rate) if tax_enabled else Decimal("0")  # noqa: SLF001
        item._billing_gross = gross  # noqa: SLF001
        item._billing_line_discount = discount  # noqa: SLF001

    charges = q2(
        Decimal(
            additional_charges
            if additional_charges is not None
            else getattr(document, "additional_charges", 0) or 0
        )
    )
    inv_discount = q2(
        Decimal(
            invoice_discount
            if invoice_discount is not None
            else getattr(document, "invoice_discount", 0) or 0
        )
    )
    mode = (
        invoice_discount_mode
        if invoice_discount_mode is not None
        else getattr(document, "invoice_discount_mode", DISCOUNT_AFTER_TAX) or DISCOUNT_AFTER_TAX
    )
    do_round = (
        auto_round_off
        if auto_round_off is not None
        else bool(getattr(document, "auto_round_off", True))
    )

    adjusted = list(taxables)
    if mode == DISCOUNT_BEFORE_TAX and inv_discount > 0 and items:
        taxable_sum = sum(taxables, Decimal("0"))
        if taxable_sum > 0:
            remaining = min(inv_discount, taxable_sum)
            allocated = Decimal("0")
            for i in range(len(adjusted) - 1):
                share = q2(taxables[i] / taxable_sum * remaining)
                share = min(share, adjusted[i])
                adjusted[i] = q2(adjusted[i] - share)
                allocated += share
            last = q2(remaining - allocated)
            adjusted[-1] = q2(max(Decimal("0"), adjusted[-1] - last))
        else:
            adjusted = [Decimal("0.00") for _ in adjusted]

    cgst_total = Decimal("0")
    sgst_total = Decimal("0")
    igst_total = Decimal("0")
    taxable_total = Decimal("0")

    for item, taxable in zip(items, adjusted):
        _apply_line_tax(
            item,
            taxable,
            getattr(item, "_billing_rate", Decimal("0")),
            tax_enabled=tax_enabled,
            intra_state=intra_state,
        )
        taxable_total += item.taxable_amount
        cgst_total += item.cgst
        sgst_total += item.sgst
        igst_total += item.igst

    if mode == DISCOUNT_BEFORE_TAX:
        raw_total = taxable_total + cgst_total + sgst_total + igst_total + charges
    else:
        raw_total = taxable_total + cgst_total + sgst_total + igst_total + charges - inv_discount

    if raw_total < 0:
        raw_total = Decimal("0")
    if do_round:
        grand_total = raw_total.quantize(RUPEE, rounding=ROUND_HALF_UP)
    else:
        grand_total = q2(raw_total)

    if hasattr(document, "additional_charges"):
        document.additional_charges = charges
    if hasattr(document, "invoice_discount"):
        document.invoice_discount = inv_discount
    if hasattr(document, "invoice_discount_mode"):
        document.invoice_discount_mode = mode

    document.subtotal = q2(subtotal)
    document.discount_total = q2(line_discount_total + inv_discount)
    document.taxable_total = q2(taxable_total)
    document.cgst_total = q2(cgst_total)
    document.sgst_total = q2(sgst_total)
    document.igst_total = q2(igst_total)
    document.round_off = q2(grand_total - raw_total)
    document.grand_total = q2(grand_total)
    return document
