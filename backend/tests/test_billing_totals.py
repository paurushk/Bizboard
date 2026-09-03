import json
from decimal import Decimal
from pathlib import Path

import pytest

from core.services.billing import DISCOUNT_BEFORE_TAX, compute_document_totals

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tax_parity_cases.json"
PARITY_CASES = json.loads(FIXTURE_PATH.read_text())
LINE_CASES = [c for c in PARITY_CASES if c.get("level", "line") == "line"]
DOC_CASES = [c for c in PARITY_CASES if c.get("level") == "document"]


class _Doc:
    additional_charges = Decimal("0")
    invoice_discount = Decimal("0")
    invoice_discount_mode = "AFTER_TAX"
    auto_round_off = True
    price_mode = "EXCLUSIVE"
    subtotal = Decimal("0")
    discount_total = Decimal("0")
    taxable_total = Decimal("0")
    cgst_total = Decimal("0")
    sgst_total = Decimal("0")
    igst_total = Decimal("0")
    round_off = Decimal("0")
    grand_total = Decimal("0")


class _Item:
    def __init__(self, qty, price, discount_percent=0, gst_rate=18, unit_price_inclusive=None):
        self.quantity = Decimal(str(qty))
        self.unit_price = Decimal(str(price))
        self.unit_price_inclusive = (
            Decimal(str(unit_price_inclusive)) if unit_price_inclusive is not None else None
        )
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


def test_cgst_sgst_halves_are_equal():
    """BILL-01: intra-state CGST and SGST must be exactly equal (GSTN validation);
    any odd third-place paise is dropped from the line tax and absorbed by the
    document round-off leg, not pushed onto SGST."""
    doc = _Doc()
    items = [_Item(1, 10.05, gst_rate=18)]
    compute_document_totals(doc, items, tax_enabled=True, intra_state=True)
    item = items[0]
    # tax = 1.809 → q2(0.9045) = 0.90 each side.
    assert item.cgst == Decimal("0.90")
    assert item.sgst == Decimal("0.90")
    assert item.cgst == item.sgst
    assert item.line_total == Decimal("11.85")
    # The dropped 0.9 paise re-appears as round-off on the document.
    assert doc.grand_total == Decimal("12.00")


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


def test_additional_charges_are_non_taxable_for_pilot():
    """P0-209 / B11 — Phase 0 scopes additional charges as non-taxable."""
    doc = _Doc()
    doc.additional_charges = Decimal("100")
    items = [_Item(1, 100, gst_rate=18)]
    compute_document_totals(doc, items, tax_enabled=True, intra_state=True)
    assert doc.taxable_total == Decimal("100.00")
    # Line tax only (18); charges add to grand without GST.
    assert doc.cgst_total + doc.sgst_total == Decimal("18.00")
    assert doc.grand_total == Decimal("218.00")


def test_additional_charges_untaxed_when_tax_disabled():
    doc = _Doc()
    doc.additional_charges = Decimal("100")
    items = [_Item(1, 100, gst_rate=0)]
    compute_document_totals(doc, items, tax_enabled=False, intra_state=True)
    assert doc.cgst_total == doc.sgst_total == doc.igst_total == Decimal("0.00")
    assert doc.grand_total == Decimal("200.00")


@pytest.mark.parametrize("case", LINE_CASES, ids=[c["id"] for c in LINE_CASES])
def test_line_tax_matches_frontend_fixture(case):
    """BUG-216/724 — single canonical fixture shared with web/src/utils/tax.test.ts
    so FE/BE line-tax math can't silently drift apart."""
    doc = _Doc()
    doc.price_mode = case.get("priceMode", "EXCLUSIVE")
    inclusive = case.get("unitPriceInclusive")
    item = _Item(
        case["quantity"],
        case["unitPrice"],
        discount_percent=case["discountPercent"],
        gst_rate=case["gstRate"],
        unit_price_inclusive=inclusive,
    )
    compute_document_totals(doc, [item], tax_enabled=True, intra_state=case["intraState"])
    expected = case["expected"]
    assert item.taxable_amount == Decimal(str(expected["taxableAmount"]))
    assert item.cgst == Decimal(str(expected["cgst"]))
    assert item.sgst == Decimal(str(expected["sgst"]))
    assert item.igst == Decimal(str(expected["igst"]))
    assert item.line_total == Decimal(str(expected["lineTotal"]))
    if "exclusiveUnitPrice" in expected:
        assert item.unit_price == Decimal(str(expected["exclusiveUnitPrice"]))


@pytest.mark.parametrize("case", DOC_CASES, ids=[c["id"] for c in DOC_CASES])
def test_document_tax_parity_fixture(case):
    """P0-203 — document-level F4–F8 / BEFORE_TAX / AFTER_TAX / round-off / multi-rate."""
    doc = _Doc()
    doc.additional_charges = Decimal(str(case.get("additionalCharges", 0)))
    doc.invoice_discount = Decimal(str(case.get("invoiceDiscount", 0)))
    doc.invoice_discount_mode = case.get("invoiceDiscountMode", "AFTER_TAX")
    doc.auto_round_off = bool(case.get("autoRoundOff", True))
    doc.price_mode = case.get("priceMode", "EXCLUSIVE")
    items = [
        _Item(
            line["quantity"],
            line["unitPrice"],
            discount_percent=line.get("discountPercent", 0),
            gst_rate=line["gstRate"],
            unit_price_inclusive=line.get("unitPriceInclusive"),
        )
        for line in case["lines"]
    ]
    compute_document_totals(
        doc,
        items,
        tax_enabled=case.get("taxEnabled", True),
        intra_state=case["intraState"],
    )
    expected = case["expected"]
    assert doc.taxable_total == Decimal(str(expected["taxableTotal"]))
    assert doc.cgst_total == Decimal(str(expected["cgstTotal"]))
    assert doc.sgst_total == Decimal(str(expected["sgstTotal"]))
    assert doc.igst_total == Decimal(str(expected["igstTotal"]))
    assert doc.grand_total == Decimal(str(expected["grandTotal"]))
    assert doc.round_off == Decimal(str(expected["roundOff"]))
