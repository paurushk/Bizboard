from decimal import Decimal

import pytest

from accounts.models import CompanyGstin
from reporting.gst_returns import build_gstr1
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, create_draft_purchase, make_customer, make_product, make_supplier


pytestmark = pytest.mark.django_db


def _id(payload):
    return payload.get("id") or (payload.get("data") or {}).get("id")


def _gst_ready(company, *, recompute=True):
    company.gstin = "29ABCDE1234F1ZW"
    company.state = "Karnataka"
    company.registration_type = company.RegistrationType.REGULAR
    company.recompute_tax_on_complete = recompute
    company.save()
    return company


def test_single_gstin_intra_and_inter_complete(tenant_a):
    company = _gst_ready(tenant_a.company)
    CompanyGstin.objects.create(
        company=company, gstin="29ABCDE1234F1ZW", state="Karnataka", is_primary=True, is_active=True,
    )
    product = make_product(company, gst_rate="18")
    add_stock(tenant_a, product, "10")
    intra_cust = make_customer(company, name="KA Buyer", state="Karnataka", gstin="29AABCU9603R1ZJ")
    inter_cust = make_customer(company, name="MH Buyer", state="Maharashtra", gstin="27AAAAA0000A1Z2")

    intra = create_draft_invoice(tenant_a, intra_cust, [{"product": product.id, "quantity": "1", "unit_price": "100"}])
    r1 = tenant_a.client.post(f"/api/v1/sales/invoices/{_id(intra)}/complete/")
    assert r1.status_code == 200, r1.data
    intra_row = SalesInvoice.objects.get(pk=_id(intra))
    assert intra_row.cgst_total > 0
    assert intra_row.igst_total == 0

    inter = create_draft_invoice(tenant_a, inter_cust, [{"product": product.id, "quantity": "1", "unit_price": "100"}])
    r2 = tenant_a.client.post(f"/api/v1/sales/invoices/{_id(inter)}/complete/")
    assert r2.status_code == 200, r2.data
    inter_row = SalesInvoice.objects.get(pk=_id(inter))
    assert inter_row.igst_total > 0
    assert inter_row.cgst_total == 0


def test_multi_gstin_complete_flips_to_igst(tenant_a):
    company = _gst_ready(tenant_a.company)
    ho = CompanyGstin.objects.create(
        company=company, gstin="29ABCDE1234F1ZW", state="Karnataka", is_primary=True, is_active=True,
    )
    mh = CompanyGstin.objects.create(
        company=company, gstin="27AAAAA0000A1Z2", state="Maharashtra", is_primary=False, is_active=True,
    )
    product = make_product(company, gst_rate="18")
    add_stock(tenant_a, product, "10")
    customer = make_customer(company, state="Karnataka", gstin="29AABCU9603R1ZJ")
    created = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer.id,
            "invoice_type": "GST",
            "company_gstin": ho.id,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    inv_id = _id(created.data)
    before = SalesInvoice.objects.get(pk=inv_id)
    assert before.cgst_total > 0
    # Stamp MH without going through set_items so Complete must recompute the split.
    SalesInvoice.objects.filter(pk=inv_id).update(company_gstin=mh)
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv_id}/complete/")
    assert resp.status_code == 200, resp.data
    row = SalesInvoice.objects.get(pk=inv_id)
    assert row.company_gstin_id == mh.id
    assert row.igst_total > 0
    assert row.cgst_total == 0
    assert abs(row.grand_total - before.grand_total) <= Decimal("0.01")
    gstr = build_gstr1(company, row.invoice_date.strftime("%Y-%m"))
    assert any(Decimal(str(r.get("igst") or 0)) > 0 for r in (gstr.get("b2b") or []))
    assert abs(Decimal(str((gstr["b2b"][0].get("igst") or 0))) - row.igst_total) <= Decimal("0.01")


def test_grand_total_change_requires_confirm(tenant_a):
    company = _gst_ready(tenant_a.company, recompute=True)
    CompanyGstin.objects.create(
        company=company, gstin="29ABCDE1234F1ZW", state="Karnataka", is_primary=True, is_active=True,
    )
    product = make_product(company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(company, state="Karnataka")
    draft = create_draft_invoice(tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}])
    inv_id = _id(draft)
    SalesInvoice.objects.filter(pk=inv_id).update(grand_total=Decimal("9999.00"))
    blocked = tenant_a.client.post(f"/api/v1/sales/invoices/{inv_id}/complete/")
    assert blocked.status_code == 409, blocked.data
    err = blocked.data.get("error") or blocked.data
    assert err.get("code") == "GSTIN_TOTAL_CHANGED"
    details = err.get("details") or {}
    assert "before" in details or details.get("code") == "GSTIN_TOTAL_CHANGED"
    ok = tenant_a.client.post(
        f"/api/v1/sales/invoices/{inv_id}/complete/",
        {"confirm_gstin_total_change": True},
        format="json",
    )
    assert ok.status_code == 200, ok.data
    row = SalesInvoice.objects.get(pk=inv_id)
    assert row.status == SalesInvoice.Status.COMPLETED
    assert row.grand_total != Decimal("9999.00")


def test_flag_off_does_not_409_on_stale_header_total(tenant_a):
    company = _gst_ready(tenant_a.company, recompute=False)
    CompanyGstin.objects.create(
        company=company, gstin="29ABCDE1234F1ZW", state="Karnataka", is_primary=True, is_active=True,
    )
    product = make_product(company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(company, state="Karnataka")
    draft = create_draft_invoice(tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}])
    inv_id = _id(draft)
    SalesInvoice.objects.filter(pk=inv_id).update(grand_total=Decimal("9999.00"))
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv_id}/complete/")
    assert resp.status_code == 200, resp.data


def test_legacy_company_without_companygstin_rows(tenant_a):
    company = _gst_ready(tenant_a.company)
    assert not CompanyGstin.objects.filter(company=company).exists()
    product = make_product(company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(company, state="Karnataka")
    draft = create_draft_invoice(tenant_a, customer, [{"product": product.id, "quantity": "1"}])
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{_id(draft)}/complete/")
    assert resp.status_code == 200, resp.data


def test_purchase_complete_confirm_path(tenant_a):
    from purchases.models import PurchaseInvoice

    company = _gst_ready(tenant_a.company, recompute=True)
    CompanyGstin.objects.create(
        company=company, gstin="29ABCDE1234F1ZW", state="Karnataka", is_primary=True, is_active=True,
    )
    product = make_product(company)
    supplier = make_supplier(company, state="Karnataka", gstin="29AABCU9603R1ZJ")
    draft = create_draft_purchase(tenant_a, supplier, [{"product": product.id, "quantity": "1", "unit_price": "50"}])
    pk = _id(draft)
    PurchaseInvoice.objects.filter(pk=pk).update(grand_total=Decimal("8888.00"))
    blocked = tenant_a.client.post(f"/api/v1/purchases/invoices/{pk}/complete/")
    assert blocked.status_code == 409, blocked.data
    ok = tenant_a.client.post(
        f"/api/v1/purchases/invoices/{pk}/complete/",
        {"confirm_gstin_total_change": True},
        format="json",
    )
    assert ok.status_code == 200, ok.data
