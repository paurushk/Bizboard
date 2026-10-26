"""WP-5 mutation gap in reporting.tds_worksheets.tds_worksheet_rows: every column of every row.

The TDS worksheet is what the CA files Form 26Q from: purchase bills and supplier payments with TDS,
purchase credit notes (negative) and debit notes against a TDS bill, with the note's TDS worked out
from the bill's rate. Documents are built through the ORM: this checks the report itself.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from reporting.tds_worksheets import tds_worksheet_rows
from tests.conftest import make_supplier

pytestmark = [pytest.mark.django_db, pytest.mark.no_invariant_check]

D = Decimal


def _bill(company, supplier, number, day, **kw):
    from purchases.models import PurchaseInvoice

    fields = dict(
        company=company, supplier=supplier, number=number, invoice_date=date(2026, 6, day),
        status="COMPLETED", taxable_total=D("1000.00"), grand_total=D("1180.00"),
    )
    fields.update(kw)
    return PurchaseInvoice.objects.create(**fields)


def _payment(company, supplier, number, day, **kw):
    from payments.models import SupplierPayment, SupplierPaymentStatus

    fields = dict(
        company=company, supplier=supplier, number=number, payment_date=date(2026, 6, day),
        status=SupplierPaymentStatus.POSTED, amount=D("500.00"), mode="CASH",
    )
    fields.update(kw)
    return SupplierPayment.objects.create(**fields)


def _note(model, company, supplier, bill, number, day, **kw):
    fields = dict(
        company=company, supplier=supplier, purchase_invoice=bill, number=number, note_date=date(2026, 6, day),
        status=model.Status.COMPLETED, taxable_total=D("200.00"), grand_total=D("236.00"),
    )
    fields.update(kw)
    return model.objects.create(**fields)


@pytest.fixture
def books(tenant_a, tenant_b):
    company = tenant_a.company
    vendor = make_supplier(company, name="Contractor Co", gstin="29CCCCC2222C1Z5")
    plain = make_supplier(company, name="No GSTIN Vendor")
    return company, vendor, plain, tenant_b


def _by(rows):
    return {r["invoice"]: r for r in rows}


def test_bill_rows_carry_every_column_and_only_tds_bills_qualify(books):
    company, vendor, plain, _ = books
    _bill(company, vendor, "BILL-TDS", 5, tds_amount=D("20.00"), tds_rate=D("2"), tds_section="194C")
    _bill(company, plain, "BILL-SECTION-ONLY", 6, tds_amount=D("0"), tds_rate=D("0"), tds_section="194J")
    _bill(company, vendor, "BILL-HALF", 7, tds_amount=D("0.50"), tds_rate=D("1"), tds_section="")
    _bill(company, vendor, "BILL-NONE", 8, tds_amount=D("0"), tds_rate=D("0"), tds_section="")

    rows = tds_worksheet_rows(company, "2026-06")
    assert [r["invoice"] for r in rows] == ["BILL-TDS", "BILL-SECTION-ONLY", "BILL-HALF"]
    row = _by(rows)["BILL-TDS"]
    assert row == {
        "date": "2026-06-05", "invoice": "BILL-TDS", "supplier": "Contractor Co", "supplier_gstin": "29CCCCC2222C1Z5",
        "section": "194C", "rate": row["rate"], "taxable": "1000.00", "grand_total": "1180.00",
        "tds_amount": "20.00", "net_payable": "1160.00", "source": "purchase_invoice",
    }
    assert D(row["rate"]) == D("2")
    assert _by(rows)["BILL-SECTION-ONLY"]["supplier_gstin"] == ""
    assert _by(rows)["BILL-HALF"]["section"] == "" and _by(rows)["BILL-HALF"]["net_payable"] == "1179.50"


def test_period_company_and_status_bounds(books):
    company, vendor, _, tenant_b = books
    kw = dict(tds_amount=D("10.00"), tds_rate=D("1"), tds_section="194C")
    _bill(company, vendor, "BILL-MAY", 1, invoice_date=date(2026, 5, 31), **kw)
    _bill(company, vendor, "BILL-JUN-1", 1, **kw)
    _bill(company, vendor, "BILL-JUN-30", 30, **kw)
    _bill(company, vendor, "BILL-JUL", 1, invoice_date=date(2026, 7, 1), **kw)
    _bill(company, vendor, "BILL-DRAFT", 10, status="DRAFT", **kw)
    _bill(company, vendor, "BILL-OPENING", 11, is_opening_balance=True, **kw)
    other = make_supplier(tenant_b.company, name="Other tenant vendor")
    _bill(tenant_b.company, other, "BILL-OTHER-CO", 12, **kw)
    assert [r["invoice"] for r in tds_worksheet_rows(company, "2026-06")] == ["BILL-JUN-1", "BILL-JUN-30"]


def test_supplier_payment_rows(books):
    from payments.models import SupplierPaymentStatus

    company, vendor, _, _ = books
    _payment(company, vendor, "PAY-TDS", 9, tds_amount=D("10.00"), tds_rate=D("2"), tds_section="194C")
    _payment(company, vendor, "PAY-NONE", 10, tds_amount=D("0"), tds_rate=D("0"), tds_section="")
    _payment(company, vendor, "PAY-VOID", 11, tds_amount=D("10.00"), tds_rate=D("2"), tds_section="194C",
             status=SupplierPaymentStatus.VOIDED)
    rows = tds_worksheet_rows(company, "2026-06")
    assert [r["invoice"] for r in rows] == ["PAY-TDS"]
    row = rows[0]
    assert row == {
        "date": "2026-06-09", "invoice": "PAY-TDS", "supplier": "Contractor Co", "supplier_gstin": "29CCCCC2222C1Z5",
        "section": "194C", "rate": row["rate"], "taxable": "500.00", "grand_total": "500.00",
        "tds_amount": "10.00", "net_payable": "490.00", "source": "supplier_payment",
    }


def test_credit_and_debit_notes_take_tds_from_the_bill_rate(books):
    from purchases.models import PurchaseCreditNote, PurchaseDebitNote

    company, vendor, _, _ = books
    bill = _bill(company, vendor, "BILL-1", 2, tds_amount=D("20.00"), tds_rate=D("2"), tds_section="194C")
    _note(PurchaseCreditNote, company, vendor, bill, "PCN-1", 12)
    _note(PurchaseDebitNote, company, vendor, bill, "PDN-1", 13)
    rows = tds_worksheet_rows(company, "2026-06")
    by = _by(rows)
    assert [r["source"] for r in rows] == ["purchase_invoice", "purchase_credit_note", "purchase_debit_note"]
    # 2% of the note's taxable value, rounded to paise.
    assert by["PCN-1"] == {
        "date": "2026-06-12", "invoice": "PCN-1", "supplier": "Contractor Co", "supplier_gstin": "29CCCCC2222C1Z5",
        "section": "194C", "rate": by["PCN-1"]["rate"], "taxable": "-200.00", "grand_total": "-236.00",
        "tds_amount": "-4.00", "net_payable": "-232.00", "source": "purchase_credit_note",
    }
    assert by["PDN-1"] == {
        "date": "2026-06-13", "invoice": "PDN-1", "supplier": "Contractor Co", "supplier_gstin": "29CCCCC2222C1Z5",
        "section": "194C", "rate": by["PDN-1"]["rate"], "taxable": "200.00", "grand_total": "236.00",
        "tds_amount": "4.00", "net_payable": "232.00", "source": "purchase_debit_note",
    }
    assert D(by["PCN-1"]["rate"]) == D("2") == D(by["PDN-1"]["rate"])


def test_notes_against_a_bill_without_tds_or_not_completed_are_left_out(books):
    from purchases.models import PurchaseCreditNote, PurchaseDebitNote

    company, vendor, _, _ = books
    plain = _bill(company, vendor, "BILL-PLAIN", 2, tds_amount=D("0"), tds_rate=D("0"), tds_section="")
    tds = _bill(company, vendor, "BILL-TDS", 3, tds_amount=D("20.00"), tds_rate=D("2"), tds_section="194C")
    _note(PurchaseCreditNote, company, vendor, plain, "PCN-PLAIN", 10)
    _note(PurchaseDebitNote, company, vendor, plain, "PDN-PLAIN", 11)
    _note(PurchaseDebitNote, company, vendor, tds, "PDN-DRAFT", 12, status=PurchaseDebitNote.Status.DRAFT)
    assert [r["invoice"] for r in tds_worksheet_rows(company, "2026-06")] == ["BILL-TDS"]
