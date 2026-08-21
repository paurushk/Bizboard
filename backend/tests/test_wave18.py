"""Wave 18: cess, GSTR-1 DOC/AT, GSTR-9 table 17, ITC eligibility."""

from decimal import Decimal

import pytest

from reporting.gst_returns import build_gstr1, build_gstr9
from reporting.gstr2b import claimable_itc_from_2b
from reporting.models import Gstr2bIngest
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def test_cess_rolls_into_invoice_total(tenant_a):
    product = make_product(tenant_a.company, gst_rate="18")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18", "cess_rate": "1"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    detail = tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/").json()["data"]
    assert Decimal(str(detail.get("cessTotal") or detail.get("cess_total") or 0)) == Decimal("1.00")


def test_cess_rolls_into_purchase_total(tenant_a):
    product = make_product(tenant_a.company, gst_rate="18")
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18", "cess_rate": "1"}],
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    detail = tenant_a.client.get(f"/api/v1/purchases/invoices/{pur['id']}/").json()["data"]
    assert Decimal(str(detail.get("cessTotal") or detail.get("cess_total") or 0)) == Decimal("1.00")


def test_gstr1_has_doc_at_supecom(tenant_a):
    product = make_product(tenant_a.company, gst_rate="0")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company, gstin="29AABCU9603R1ZJ", state="29")
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    from sales.models import SalesInvoice

    period = SalesInvoice.objects.get(pk=inv["id"]).invoice_date.strftime("%Y-%m")
    payload = build_gstr1(tenant_a.company, period)
    assert "doc" in payload and isinstance(payload["doc"], list)
    assert "at" in payload
    assert payload["supecom"]["supported"] is False


def test_gstr9_table_17_from_hsn(tenant_a):
    payload = build_gstr9(tenant_a.company, "2025-26")
    assert payload["tables"]["17"]["aid_kind"] == "hsn_outward"
    assert "rows" in payload["tables"]["17"]


def test_2b_ineligible_excluded_from_claimable(tenant_a):
    Gstr2bIngest.objects.create(
        company=tenant_a.company,
        period="2026-04",
        supplier_gstin="27AAAAA0000A1Z2",
        invoice_number="X1",
        taxable_value=Decimal("100"),
        cgst=Decimal("9"),
        sgst=Decimal("9"),
        match_status=Gstr2bIngest.MatchStatus.MATCHED,
        itc_eligibility=Gstr2bIngest.ItcEligibility.INELIGIBLE,
    )
    itc = claimable_itc_from_2b(tenant_a.company, "2026-04")
    assert itc["cgst"] == Decimal("0")
    assert itc["sgst"] == Decimal("0")
