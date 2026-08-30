"""Optional taxable freight/packing lines (HSN + GST rate required — no default rate)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from core.services.billing import q2


def charges_are_taxable(document) -> bool:
    charges = q2(Decimal(str(getattr(document, "additional_charges", 0) or 0)))
    rate = Decimal(str(getattr(document, "charges_gst_rate", 0) or 0))
    hsn = (getattr(document, "charges_hsn", "") or "").strip()
    return charges > 0 and rate > 0 and bool(hsn)


def charge_line(document, *, intra_state: bool):
    """Return a GSTR/e-invoice-shaped synthetic line, or None if charges are not taxed."""
    if not charges_are_taxable(document):
        return None
    charges = q2(Decimal(str(document.additional_charges or 0)))
    rate = Decimal(str(document.charges_gst_rate or 0))
    tax = q2(charges * rate / Decimal("100"))
    if intra_state:
        half = q2(tax / 2)
        cgst, sgst, igst = half, q2(tax) - half, Decimal("0.00")
    else:
        cgst = sgst = Decimal("0.00")
        igst = tax
    hsn = (document.charges_hsn or "").strip()
    return SimpleNamespace(
        hsn_code=hsn,
        uqc_code="OTH",
        quantity=Decimal("1"),
        gst_rate=rate,
        taxable_amount=charges,
        cgst=cgst,
        sgst=sgst,
        igst=igst,
        cess=Decimal("0.00"),
        cess_rate=Decimal("0"),
        # R1-022: some GSTR / e-invoice line builders read `.cess_amount`
        # directly (not via getattr default) — expose it so a taxable freight
        # line never AttributeErrors those builders.
        cess_amount=Decimal("0.00"),
        description="Freight / packing",
        unit_price=charges,
        discount_percent=Decimal("0"),
        line_total=q2(charges + cgst + sgst + igst),
        supply_nature="TAXABLE",
    )


def note_tcs_amount(note) -> Decimal:
    return q2(Decimal(str(getattr(note, "tcs_amount", 0) or 0)))
