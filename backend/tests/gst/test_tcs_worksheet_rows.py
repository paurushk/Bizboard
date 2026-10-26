"""WP-5 mutation survivors in reporting.tds_worksheets.tcs_worksheet_rows: every column of every row.

The worksheet is what a CA files Form 27EQ from, so each field is pinned: which documents qualify
(TCS amount above zero or a TCS section set), the period and company bounds, the sign of credit
notes, the TCS worked out from the invoice rate when a note carries none, and the receivable with
and without TCS already inside the grand total. Documents are built through the ORM: this checks
the report, not the posting paths (those have their own tests).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from reporting.tds_worksheets import tcs_worksheet_rows
from tests.conftest import make_customer

pytestmark = [pytest.mark.django_db, pytest.mark.no_invariant_check]

D = Decimal


def _invoice(company, customer, number, day, **kw):
    from sales.models import SalesInvoice

    fields = dict(
        company=company, customer=customer, number=number, invoice_date=date(2026, 6, day),
        status="COMPLETED", invoice_type="GST", taxable_total=D("1000.00"), grand_total=D("1180.00"),
    )
    fields.update(kw)
    return SalesInvoice.objects.create(**fields)


def _note(model, company, customer, inv, number, day, **kw):
    fields = dict(
        company=company, customer=customer, sales_invoice=inv, number=number, note_date=date(2026, 6, day),
        status=model.Status.COMPLETED, taxable_total=D("100.00"), grand_total=D("118.00"),
    )
    fields.update(kw)
    return model.objects.create(**fields)


@pytest.fixture
def books(tenant_a, tenant_b):
    company = tenant_a.company
    buyer = make_customer(company, name="Big Buyer", gstin="29BBBBB1111B1Z5")
    plain = make_customer(company, name="No GSTIN Buyer")
    return company, buyer, plain, tenant_b


def _by_number(rows):
    return {r["invoice"]: r for r in rows}


def test_invoice_rows_carry_every_column_and_only_tcs_invoices_qualify(books):
    company, buyer, plain, _ = books
    _invoice(company, buyer, "INV-TCS", 5, tcs_amount=D("1.18"), tcs_rate=D("0.1"), tcs_section="206C(1H)")
    _invoice(company, plain, "INV-SECTION-ONLY", 6, tcs_amount=D("0"), tcs_rate=D("0"), tcs_section="206C(1H)")
    _invoice(company, buyer, "INV-HALF-RUPEE", 7, tcs_amount=D("0.50"), tcs_rate=D("0.1"), tcs_section="")
    _invoice(company, buyer, "INV-NO-TCS", 8, tcs_amount=D("0"), tcs_rate=D("0"), tcs_section="")

    rows = tcs_worksheet_rows(company, "2026-06")
    by = _by_number(rows)
    assert [r["invoice"] for r in rows] == ["INV-TCS", "INV-SECTION-ONLY", "INV-HALF-RUPEE"]  # date order
    assert by["INV-TCS"] == {
        "date": "2026-06-05", "invoice": "INV-TCS", "customer": "Big Buyer", "customer_gstin": "29BBBBB1111B1Z5",
        "section": "206C(1H)", "rate": "0.100", "taxable": "1000.00", "grand_total": "1180.00",
        "tcs_amount": "1.18", "receivable": "1181.18", "source": "sales_invoice",
    }
    assert by["INV-SECTION-ONLY"]["customer_gstin"] == "" and by["INV-SECTION-ONLY"]["tcs_amount"] == "0"
    assert by["INV-HALF-RUPEE"]["section"] == "" and by["INV-HALF-RUPEE"]["tcs_amount"] == "0.50"


def test_tcs_already_inside_the_grand_total_is_not_added_twice(books):
    company, buyer, _, _ = books
    _invoice(company, buyer, "INV-IN-TOTAL", 5, tcs_amount=D("1.18"), tcs_rate=D("0.1"),
             tcs_section="206C(1H)", grand_total=D("1181.18"), tcs_in_grand_total=True)
    row = tcs_worksheet_rows(company, "2026-06")[0]
    assert row["receivable"] == "1181.18"


def test_period_company_and_status_bounds(books):
    company, buyer, _, tenant_b = books
    kw = dict(tcs_amount=D("1.00"), tcs_rate=D("0.1"), tcs_section="206C(1H)")
    _invoice(company, buyer, "INV-MAY", 1, invoice_date=date(2026, 5, 31), **kw)
    _invoice(company, buyer, "INV-JUN-1", 1, **kw)
    _invoice(company, buyer, "INV-JUN-30", 30, **kw)
    _invoice(company, buyer, "INV-JUL", 1, invoice_date=date(2026, 7, 1), **kw)
    _invoice(company, buyer, "INV-DRAFT", 10, status="DRAFT", **kw)
    _invoice(company, buyer, "INV-OPENING", 11, is_opening_balance=True, **kw)
    other = make_customer(tenant_b.company, name="Other tenant")
    _invoice(tenant_b.company, other, "INV-OTHER-CO", 12, **kw)
    assert [r["invoice"] for r in tcs_worksheet_rows(company, "2026-06")] == ["INV-JUN-1", "INV-JUN-30"]


def test_credit_note_rows_are_negative_and_fall_back_to_the_invoice_rate(books):
    from sales.models import SalesCreditNote

    company, buyer, _, _ = books
    inv = _invoice(company, buyer, "INV-1", 2, tcs_amount=D("1.18"), tcs_rate=D("1"), tcs_section="206C(1H)")
    _note(SalesCreditNote, company, buyer, inv, "CN-OWN", 10, tcs_amount=D("2.00"))
    _note(SalesCreditNote, company, buyer, inv, "CN-RATE", 11, tcs_amount=D("0"))
    by = _by_number(tcs_worksheet_rows(company, "2026-06"))
    assert by["CN-OWN"] == {
        "date": "2026-06-10", "invoice": "CN-OWN", "customer": "Big Buyer", "customer_gstin": "29BBBBB1111B1Z5",
        "section": "206C(1H)", "rate": "1.000", "taxable": "-100.00", "grand_total": "-118.00",
        "tcs_amount": "-2.00", "receivable": "-120.00", "source": "sales_credit_note",
    }
    # No TCS on the note: 1% of the note's grand total, rounded to paise.
    assert by["CN-RATE"]["tcs_amount"] == "-1.18" and by["CN-RATE"]["receivable"] == "-119.18"


def test_debit_note_rows_are_positive_and_fall_back_to_the_invoice_rate(books):
    from sales.models import SalesDebitNote

    company, buyer, _, _ = books
    inv = _invoice(company, buyer, "INV-1", 2, tcs_amount=D("0"), tcs_rate=D("1"), tcs_section="206C(1H)")
    _note(SalesDebitNote, company, buyer, inv, "DN-RATE", 12, tcs_amount=D("0"))
    _note(SalesDebitNote, company, buyer, inv, "DN-OWN", 13, tcs_amount=D("3.00"))
    rows = tcs_worksheet_rows(company, "2026-06")
    by = _by_number(rows)
    assert [r["source"] for r in rows] == ["sales_invoice", "sales_debit_note", "sales_debit_note"]
    assert by["DN-RATE"] == {
        "date": "2026-06-12", "invoice": "DN-RATE", "customer": "Big Buyer", "customer_gstin": "29BBBBB1111B1Z5",
        "section": "206C(1H)", "rate": "1.000", "taxable": "100.00", "grand_total": "118.00",
        "tcs_amount": "1.18", "receivable": "119.18", "source": "sales_debit_note",
    }
    assert by["DN-OWN"]["tcs_amount"] == "3.00" and by["DN-OWN"]["receivable"] == "121.00"


def test_notes_against_an_invoice_without_tcs_are_left_out(books):
    from sales.models import SalesCreditNote, SalesDebitNote

    company, buyer, _, _ = books
    inv = _invoice(company, buyer, "INV-PLAIN", 2, tcs_amount=D("0"), tcs_rate=D("0"), tcs_section="")
    _note(SalesCreditNote, company, buyer, inv, "CN-PLAIN", 10, tcs_amount=D("0"))
    _note(SalesDebitNote, company, buyer, inv, "DN-PLAIN", 11, tcs_amount=D("0"))
    _note(SalesDebitNote, company, buyer, inv, "DN-DRAFT", 12, tcs_amount=D("5.00"),
          status=SalesDebitNote.Status.DRAFT)
    assert tcs_worksheet_rows(company, "2026-06") == []
