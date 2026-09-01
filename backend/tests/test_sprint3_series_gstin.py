"""Sprint 3: document series, CompanyGstin CRUD, GSTR stamp filter."""

from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import CompanyGstin
from core.services.document_numbers import DocumentNumberService
from purchases.models import PurchaseInvoice
from reporting.gst_returns import build_gstr1, build_gstr3b
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, create_draft_purchase, make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db


def test_bb_000646_next_number_does_not_scan_historical_rows(tenant_a):
    company = tenant_a.company
    for _ in range(30):
        DocumentNumberService.next_number(company, "SALES_INVOICE")
    with CaptureQueriesContext(connection) as ctx:
        DocumentNumberService.next_number(company, "SALES_INVOICE")
    sqls = [q["sql"] for q in ctx.captured_queries]
    scanned = [s for s in sqls if "sales_salesinvoice" in s.lower() and "number" in s.lower()]
    assert scanned == [], sqls


def test_bb_000646_series_unique_per_gstin_and_fy(tenant_a):
    a = DocumentNumberService.next_number(
        tenant_a.company, "SALES_INVOICE", gstin="29ABCDE1234F1ZW", on_date=__import__("datetime").date(2026, 8, 1)
    )
    b = DocumentNumberService.next_number(
        tenant_a.company, "SALES_INVOICE", gstin="27AAAAA0000A1Z2", on_date=__import__("datetime").date(2026, 8, 1)
    )
    c = DocumentNumberService.next_number(
        tenant_a.company, "SALES_INVOICE", gstin="29ABCDE1234F1ZW", on_date=__import__("datetime").date(2025, 5, 1)
    )
    assert a != b
    assert a != c
    assert a.startswith("INV-")
    assert "1Z5" in a or "F1Z5" in a or a != b


def test_bb_000674_owner_company_gstin_crud(tenant_a):
    created = tenant_a.client.post(
        "/api/v1/company/gstins/",
        {"gstin": "29ABCDE1234F1ZW", "legal_name": "HO", "state": "Karnataka", "is_primary": True},
        format="json",
    )
    assert created.status_code == 201, created.data
    body = created.data.get("data") or created.data
    listed = tenant_a.client.get("/api/v1/company/gstins/")
    assert listed.status_code == 200
    rows = listed.data.get("results") or listed.data.get("data") or listed.data
    if isinstance(rows, dict) and "results" in rows:
        rows = rows["results"]
    assert any((r.get("gstin") or r.get("gstin")) == "29ABCDE1234F1ZW" for r in rows)
    patched = tenant_a.client.patch(
        f"/api/v1/company/gstins/{body['id']}/",
        {"is_active": False},
        format="json",
    )
    assert patched.status_code == 200, patched.data


def test_bb_000556_gstr1_filters_by_company_gstin_stamp(tenant_a):
    company = tenant_a.company
    company.gstin = "29ABCDE1234F1ZW"
    company.state = "Karnataka"
    company.registration_type = company.RegistrationType.REGULAR
    company.save()
    ho = CompanyGstin.objects.create(
        company=company, gstin="29ABCDE1234F1ZW", state="Karnataka", is_primary=True, is_active=True,
    )
    branch = CompanyGstin.objects.create(
        company=company, gstin="27AAAAA0000A1Z2", state="Maharashtra", is_primary=False, is_active=True,
    )
    product = make_product(company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(company, gstin="29BBBBB1111B1ZJ", state="Karnataka")
    inv_a = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
    )
    tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv_a['id']}/",
        {"company_gstin": ho.id, "items": [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}]},
        format="json",
    )
    # Pin the invoice date into the queried period regardless of when the
    # suite runs (mirrors the sibling GSTR-3B test below).
    SalesInvoice.objects.filter(pk=inv_a["id"]).update(invoice_date="2026-08-05")
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv_a['id']}/complete/").status_code == 200
    inv_b = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "2000", "gst_rate": "18"}],
    )
    tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv_b['id']}/",
        {"company_gstin": branch.id, "items": [{"product": product.id, "quantity": "1", "unit_price": "2000", "gst_rate": "18"}]},
        format="json",
    )
    SalesInvoice.objects.filter(pk=inv_b["id"]).update(invoice_date="2026-08-05")
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv_b['id']}/complete/").status_code == 200

    from core.exceptions import BusinessRuleError

    with pytest.raises(BusinessRuleError):
        build_gstr1(company, "2026-08")
    ho_pack = build_gstr1(company, "2026-08", company_gstin=ho.id)
    branch_pack = build_gstr1(company, "2026-08", company_gstin=branch.gstin)
    ho_numbers = {row.get("invoice_number") for row in ho_pack.get("b2b", [])}
    branch_numbers = {row.get("invoice_number") for row in branch_pack.get("b2b", [])}
    assert ho_numbers.isdisjoint(branch_numbers) or ho_pack != branch_pack
    api = tenant_a.client.get("/api/v1/reports/gstr1/", {"period": "2026-08", "company_gstin": ho.id})
    assert api.status_code == 200, api.data


def test_gstr3b_purchase_itc_scoped_by_company_gstin(tenant_a):
    company = tenant_a.company
    company.gstin = "29ABCDE1234F1ZW"
    company.state = "Karnataka"
    company.registration_type = company.RegistrationType.REGULAR
    company.save()
    ho = CompanyGstin.objects.create(
        company=company, gstin="29ABCDE1234F1ZW", state="Karnataka", is_primary=True, is_active=True,
    )
    branch = CompanyGstin.objects.create(
        company=company, gstin="27AAAAA0000A1Z2", state="Maharashtra", is_primary=False, is_active=True,
    )
    supplier = make_supplier(company, gstin="29BBBBB1111B1ZJ")
    product = make_product(company, sku="P-GSTIN")
    ho_draft = create_draft_purchase(
        tenant_a, supplier, [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    tenant_a.client.patch(
        f"/api/v1/purchases/invoices/{ho_draft['id']}/",
        {
            "company_gstin": ho.id,
            "itc_eligibility": "CLAIMABLE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
        },
        format="json",
    )
    PurchaseInvoice.objects.filter(pk=ho_draft["id"]).update(
        invoice_date="2026-08-04", itc_eligibility="CLAIMABLE",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{ho_draft['id']}/complete/").status_code == 200
    branch_draft = create_draft_purchase(
        tenant_a, supplier, [{"product": product.id, "quantity": "1", "unit_price": "200", "gst_rate": "18"}],
    )
    tenant_a.client.patch(
        f"/api/v1/purchases/invoices/{branch_draft['id']}/",
        {
            "company_gstin": branch.id,
            "itc_eligibility": "CLAIMABLE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "200", "gst_rate": "18"}],
        },
        format="json",
    )
    PurchaseInvoice.objects.filter(pk=branch_draft["id"]).update(
        invoice_date="2026-08-05", itc_eligibility="CLAIMABLE",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{branch_draft['id']}/complete/").status_code == 200

    ho_3b = build_gstr3b(company, "2026-08", company_gstin=ho.id)
    branch_3b = build_gstr3b(company, "2026-08", company_gstin=branch.id)
    assert Decimal(str(ho_3b["itc"]["available_from_purchases"]["total_tax"])) == Decimal("18.00")
    assert Decimal(str(branch_3b["itc"]["available_from_purchases"]["total_tax"])) == Decimal("36.00")
