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


def test_unknown_doc_type_rejected(tenant_a):
    with pytest.raises(ValueError):
        DocumentNumberService.next_number(tenant_a.company, "NOPE")
