"""Document Number Service — independent, sequential, per-company (E0.13)."""

import pytest

from core.services.document_numbers import DocumentNumberService

pytestmark = pytest.mark.django_db


def test_sequences_are_sequential(tenant_a):
    n1 = DocumentNumberService.next_number(tenant_a.company, "SALES_INVOICE")
    n2 = DocumentNumberService.next_number(tenant_a.company, "SALES_INVOICE")
    assert n1 == "INV-00001"
    assert n2 == "INV-00002"


def test_sequences_are_independent_per_doc_type(tenant_a):
    DocumentNumberService.next_number(tenant_a.company, "SALES_INVOICE")
    assert DocumentNumberService.next_number(tenant_a.company, "PURCHASE_INVOICE") == "PUR-00001"
    assert DocumentNumberService.next_number(tenant_a.company, "QUOTATION") == "QTN-00001"
    assert DocumentNumberService.next_number(tenant_a.company, "SALES_RETURN") == "SRN-00001"
    assert DocumentNumberService.next_number(tenant_a.company, "CUSTOMER_RECEIPT") == "RCT-00001"


def test_sequences_are_independent_per_company(tenant_a, tenant_b):
    DocumentNumberService.next_number(tenant_a.company, "SALES_INVOICE")
    assert DocumentNumberService.next_number(tenant_b.company, "SALES_INVOICE") == "INV-00001"


def test_next_number_rolls_back_with_outer_transaction(tenant_a):
    """Allocation joins the outer txn so a failed create does not burn a sequence."""
    from django.db import transaction

    from core.models import DocumentSeries
    from core.services.document_numbers import DocumentNumberService

    DocumentNumberService._ensure_series(tenant_a.company, "SALES_INVOICE")
    series = DocumentSeries.objects.get(company=tenant_a.company, doc_type="SALES_INVOICE")
    before = series.next_number
    try:
        with transaction.atomic():
            DocumentNumberService.next_number(tenant_a.company, "SALES_INVOICE")
            raise RuntimeError("simulate failed create")
    except RuntimeError:
        pass
    series.refresh_from_db()
    assert series.next_number == before


def test_unknown_doc_type_rejected(tenant_a):
    with pytest.raises(ValueError):
        DocumentNumberService.next_number(tenant_a.company, "NOPE")


def test_deleting_draft_invoice_leaves_no_number_gap(tenant_a):
    """BUG-208 — numbers must be assigned on Complete, not draft creation,
    so an abandoned/deleted draft doesn't burn a slot in the GST series."""
    from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)

    draft = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"}
    ])
    assert not draft["number"]
    delete_resp = tenant_a.client.delete(f"/api/v1/sales/invoices/{draft['id']}/")
    assert delete_resp.status_code == 204

    second = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"}
    ])
    complete_resp = tenant_a.client.post(f"/api/v1/sales/invoices/{second['id']}/complete/")
    assert complete_resp.data["number"] == "INV-00001"
