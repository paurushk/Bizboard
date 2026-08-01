import json
from decimal import Decimal
from pathlib import Path

import pytest

from core.services.billing import DISCOUNT_BEFORE_TAX, compute_document_totals, q2

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tax_parity_cases.json"
PARITY_CASES = json.loads(FIXTURE_PATH.read_text())


class _Doc:
    additional_charges = Decimal("0")
    invoice_discount = Decimal("0")
    invoice_discount_mode = "AFTER_TAX"
    auto_round_off = True
    subtotal = Decimal("0")
    discount_total = Decimal("0")
    taxable_total = Decimal("0")
    cgst_total = Decimal("0")
    sgst_total = Decimal("0")
    igst_total = Decimal("0")
    round_off = Decimal("0")
    grand_total = Decimal("0")


class _Item:
    def __init__(self, qty, price, discount_percent=0, gst_rate=18):
        self.quantity = Decimal(str(qty))
        self.unit_price = Decimal(str(price))
        self.discount_percent = Decimal(str(discount_percent))
        self.gst_rate = Decimal(str(gst_rate))
        self.taxable_amount = Decimal("0")
        self.cgst = Decimal("0")
        self.sgst = Decimal("0")
        self.igst = Decimal("0")
        self.line_total = Decimal("0")


def test_additional_charges_and_invoice_discount():
    doc = _Doc()
    doc.additional_charges = Decimal("10")
    doc.invoice_discount = Decimal("5")
    items = [_Item(1, 100, gst_rate=0)]
    compute_document_totals(doc, items, tax_enabled=True, intra_state=True)
    assert doc.taxable_total == Decimal("100.00")
    assert doc.grand_total == Decimal("105.00")  # 100 + 10 - 5


def test_auto_round_off_can_be_disabled():
    doc = _Doc()
    doc.auto_round_off = False
    items = [_Item(1, 99.4, gst_rate=0)]
    compute_document_totals(doc, items, tax_enabled=True, intra_state=True)
    assert doc.grand_total == Decimal("99.40")
    assert doc.round_off == Decimal("0.00")


def test_cgst_sgst_halves_sum_to_tax():
    """Odd tax amounts must split so CGST + SGST == q2(tax), residual on SGST."""
    doc = _Doc()
    items = [_Item(1, 10.05, gst_rate=18)]
    compute_document_totals(doc, items, tax_enabled=True, intra_state=True)
    item = items[0]
    assert item.cgst == Decimal("0.90")
    assert item.sgst == Decimal("0.91")
    assert item.cgst + item.sgst == q2(Decimal("10.05") * Decimal("18") / Decimal("100"))
    assert item.line_total == Decimal("11.86")


def test_before_tax_invoice_discount_reduces_gst():
    doc = _Doc()
    doc.invoice_discount = Decimal("10")
    doc.invoice_discount_mode = DISCOUNT_BEFORE_TAX
    items = [_Item(1, 100, gst_rate=18)]
    compute_document_totals(doc, items, tax_enabled=True, intra_state=True)
    assert doc.taxable_total == Decimal("90.00")
    assert doc.cgst_total + doc.sgst_total == Decimal("16.20")
    # 90 + 16.20 = 106.20 → rounds to 106
    assert doc.grand_total == Decimal("106.00")


def test_additional_charges_are_taxed_at_line_rate():
    """BUG-205 — additional charges are part of the value of supply and
    taxable at the invoice's blended rate, not permanently GST-exempt."""
    doc = _Doc()
    doc.additional_charges = Decimal("100")
    items = [_Item(1, 100, gst_rate=18)]
    compute_document_totals(doc, items, tax_enabled=True, intra_state=True)
    assert doc.taxable_total == Decimal("100.00")
    # 18% of the charges (100) = 18, on top of the line's own 18 tax.
    assert doc.cgst_total + doc.sgst_total == Decimal("36.00")


def test_additional_charges_untaxed_when_tax_disabled():
    doc = _Doc()
    doc.additional_charges = Decimal("100")
    items = [_Item(1, 100, gst_rate=0)]
    compute_document_totals(doc, items, tax_enabled=False, intra_state=True)
    assert doc.cgst_total == doc.sgst_total == doc.igst_total == Decimal("0.00")
    assert doc.grand_total == Decimal("200.00")


@pytest.mark.parametrize("case", PARITY_CASES, ids=[c["id"] for c in PARITY_CASES])
def test_line_tax_matches_frontend_fixture(case):
    """BUG-216/724 — single canonical fixture shared with web/src/utils/tax.test.ts
    so FE/BE line-tax math can't silently drift apart."""
    doc = _Doc()
    item = _Item(
        case["quantity"],
        case["unitPrice"],
        discount_percent=case["discountPercent"],
        gst_rate=case["gstRate"],
    )
    compute_document_totals(doc, [item], tax_enabled=True, intra_state=case["intraState"])
    expected = case["expected"]
    assert item.taxable_amount == Decimal(str(expected["taxableAmount"]))
    assert item.cgst == Decimal(str(expected["cgst"]))
    assert item.sgst == Decimal(str(expected["sgst"]))
    assert item.igst == Decimal(str(expected["igst"]))
    assert item.line_total == Decimal(str(expected["lineTotal"]))
