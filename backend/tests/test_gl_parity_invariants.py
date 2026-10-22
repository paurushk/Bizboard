"""WP-F4: documents and the ledger tie, and each tie can fail when the data is tampered with."""

from __future__ import annotations

from decimal import Decimal

import pytest

from accounting.models import JournalEntry, JournalLine
from core.invariants import run_invariants
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product, make_supplier
from tests.test_ar_ap_agreement_matrix import _books, _purchase, _receipt, _sale

pytestmark = pytest.mark.django_db
PARITY = {"gl.ar_ties_to_documents", "gl.ap_ties_to_documents", "gl.sales_output_gst_ties_to_invoices"}


def _parity(company):
    return {k: v for k, v in run_invariants(company, only=PARITY).items()}


def _gst_sale(t):
    product = make_product(t.company, sku="PAR-GST")
    add_stock(t, product, "10")
    customer = make_customer(t.company)
    inv = create_draft_invoice(
        t, customer, [{"product": product.id, "quantity": "2", "unit_price": "500", "gst_rate": "18"}],
    )
    assert t.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    return inv["id"]


def test_books_off_companies_have_nothing_to_compare(tenant_a):
    _sale(tenant_a, make_customer(tenant_a.company), make_product(tenant_a.company))
    assert _parity(tenant_a.company) == {}


def test_a_normal_books_on_flow_ties(tenant_a):
    _books(tenant_a, True)
    customer = make_customer(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company)
    inv = _sale(tenant_a, customer, product)
    _receipt(tenant_a, customer, "400", invoice=inv)
    _purchase(tenant_a, supplier, product)
    _gst_sale(tenant_a)
    assert _parity(tenant_a.company) == {}


@pytest.mark.no_invariant_check
def test_ar_fails_when_an_invoice_outstanding_disagrees_with_the_ledger(tenant_a):
    from sales.models import SalesInvoice

    _books(tenant_a, True)
    inv = _sale(tenant_a, make_customer(tenant_a.company), make_product(tenant_a.company))
    SalesInvoice.objects.filter(pk=inv.pk).update(grand_total=Decimal("5000"))
    failures = _parity(tenant_a.company)
    assert "gl.ar_ties_to_documents" in failures


@pytest.mark.no_invariant_check
def test_ap_fails_when_a_supplier_ledger_line_is_altered(tenant_a):
    _books(tenant_a, True)
    pur = _purchase(tenant_a, make_supplier(tenant_a.company), make_product(tenant_a.company, sku="AP-1"))
    line = JournalLine.objects.filter(
        entry__source_type="PURCHASE_INVOICE", entry__source_id=pur.pk, account__code="2100",
    ).first()
    JournalLine.objects.filter(pk=line.pk).update(credit=line.credit + Decimal("250"))
    assert "gl.ap_ties_to_documents" in _parity(tenant_a.company)


@pytest.mark.no_invariant_check
def test_output_gst_fails_when_the_posted_tax_differs_from_the_lines(tenant_a):
    _books(tenant_a, True)
    inv_id = _gst_sale(tenant_a)
    line = JournalLine.objects.filter(
        entry__source_type="SALES_INVOICE", entry__source_id=inv_id,
        entry__status=JournalEntry.Status.POSTED, account__code__in=("2210", "2230"),
    ).first()
    assert line is not None
    JournalLine.objects.filter(pk=line.pk).update(credit=line.credit + Decimal("10"))
    failures = _parity(tenant_a.company)
    assert "gl.sales_output_gst_ties_to_invoices" in failures
    assert "output GST posted" in failures["gl.sales_output_gst_ties_to_invoices"][0]


def test_an_invoice_with_taxed_freight_completes_and_its_gst_ties(tenant_a):
    """Found while building shadow books: header tax includes GST on freight, item lines do not, so
    posting used to refuse the invoice ("tax headers do not match") for any books-on company."""
    from tests.test_credit_debit_notes_plan import _invoice_with_freight

    _books(tenant_a, True)
    _product, _customer, inv = _invoice_with_freight(tenant_a, freight="100")
    gst = JournalLine.objects.filter(
        entry__source_type="SALES_INVOICE", entry__source_id=inv["id"], entry__status=JournalEntry.Status.POSTED,
        account__code__in=("2210", "2220", "2230"),
    )
    posted = sum((line.credit - line.debit for line in gst), Decimal("0"))
    assert posted == Decimal("90.00") + Decimal("18.00")  # 500 of goods @18% + 100 freight @18%
    assert _parity(tenant_a.company) == {}


# --------------------------------------------------------------------------------------------------
# Ledger-only party balances found by the strict sweep (2026-10-22). Each one used to raise a
# permanent DOCS_GL / CONTROL alert, and those alerts block period close.


def _close_alerts(company) -> set[str]:
    from accounting.services import BooksHealthService

    return {a["code"] for a in BooksHealthService.control_balances(company).get("alerts", [])}


def test_a_cheque_dishonour_fee_ties_and_does_not_block_close(tenant_a):
    from payments.models import ChequeStatus
    from payments.services import PaymentService
    from sales.models import SalesInvoice

    _books(tenant_a, True)
    product = make_product(tenant_a.company, sku="PAR-CHQ")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Cheque Party")
    inv = create_draft_invoice(tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}])
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    receipt = PaymentService.create_receipt(
        company=tenant_a.company, customer=customer, amount=Decimal("100.00"), mode="CHEQUE",
        cheque_number="445566", cheque_bank_name="HDFC", user=tenant_a.owner,
    )
    PaymentService.allocate_receipt(receipt=receipt, sales_invoice=invoice, amount=Decimal("100.00"), user=tenant_a.owner)
    PaymentService.set_cheque_status(
        receipt=receipt, cheque_status=ChequeStatus.BOUNCED, user=tenant_a.owner, bank_charge=Decimal("150"),
    )
    fee_lines = JournalLine.objects.filter(entry__source_type="CHEQUE_DISHONOUR", account__code="1200")
    assert sum(line.debit for line in fee_lines) == Decimal("150.00")
    assert _parity(tenant_a.company) == {}
    assert not _close_alerts(tenant_a.company) & {"DOCS_GL_AR_MISMATCH", "AR_CONTROL_MISMATCH"}


def test_a_bill_of_entry_without_a_supplier_does_not_block_close(tenant_a):
    from purchases.models import BillOfEntry

    _books(tenant_a, True)
    boe = BillOfEntry.objects.create(
        company=tenant_a.company, boe_number="BOE-NOSUP", boe_date="2026-06-11",
        assessable_value=Decimal("25000.00"), bcd_amount=Decimal("1000.00"), igst_amount=Decimal("5000.00"),
        itc_eligibility=BillOfEntry.ItcEligibility.ELIGIBLE,
    )
    resp = tenant_a.client.post(f"/api/v1/purchases/bills-of-entry/{boe.id}/complete/")
    assert resp.status_code == 200, resp.data
    duty = JournalLine.objects.get(entry__source_type="BILL_OF_ENTRY", account__code="2100")
    assert duty.supplier_id is None and duty.credit == Decimal("6000.00")
    assert _parity(tenant_a.company) == {}
    assert not _close_alerts(tenant_a.company) & {"DOCS_GL_AP_MISMATCH", "AP_CONTROL_MISMATCH"}


@pytest.mark.no_invariant_check  # builds an untagged payable on purpose
def test_an_untagged_payable_from_anything_else_still_raises_the_control_alert(tenant_a):
    """The Bill of Entry carve-out is by source: an untagged 2100 line from a manual journal still alerts."""
    from accounting.services import PostingService

    _books(tenant_a, True)
    PostingService.post(
        company=tenant_a.company, source_type="MANUAL_JOURNAL", source_id=1, purpose="TEST",
        entry_date="2026-06-11", user=tenant_a.owner,
        lines=[
            {"account": PostingService._account(tenant_a.company, "5110"), "debit": Decimal("500")},
            {"account": PostingService._account(tenant_a.company, "2100"), "credit": Decimal("500")},
        ],
    )
    assert "AP_CONTROL_MISMATCH" in _close_alerts(tenant_a.company)


@pytest.mark.usefixtures("_fixed_assets_on")
def test_a_fixed_asset_bought_on_credit_ties_and_does_not_block_close(tenant_a):
    _books(tenant_a, True)
    supplier = make_supplier(tenant_a.company, name="Dell")
    resp = tenant_a.client.post("/api/v1/accounting/fixed-assets/", {
        "name": "Laptop", "acquisition_date": "2026-01-10", "acquisition_cost": "36000.00",
        "useful_life_months": 36, "method": "SLM", "funding": "SUPPLIER", "funding_supplier": supplier.id,
    }, format="json")
    assert resp.status_code == 201, resp.data
    payable = JournalLine.objects.get(entry__source_type="FIXED_ASSET", account__code="2100")
    assert payable.supplier_id == supplier.id and payable.credit == Decimal("36000.00")
    assert _parity(tenant_a.company) == {}
    assert not _close_alerts(tenant_a.company) & {"DOCS_GL_AP_MISMATCH", "AP_CONTROL_MISMATCH"}


@pytest.fixture
def _fixed_assets_on():
    from django.test import override_settings

    with override_settings(ENABLE_FIXED_ASSETS=True):
        yield
