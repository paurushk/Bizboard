"""Live API round-trips for the 15 Help `code=` raise sites (HR-1.1)."""

from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import Company, CompanyGstin, CompanyUser
from masters.models import Customer, Product
from reporting.models import GstReturnPeriod
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _code(resp) -> str | None:
    err = resp.data.get("error") if isinstance(resp.data, dict) else None
    if isinstance(err, dict):
        return err.get("code")
    return None


def test_live_insufficient_stock(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "1")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "5", "unit_price": "100"}]
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 400
    assert _code(resp) == "insufficient_stock"


def test_live_inactive_product(tenant_a):
    product = make_product(tenant_a.company, status=Product.Status.INACTIVE)
    customer = make_customer(tenant_a.company)
    resp = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer.id,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
        },
        format="json",
    )
    assert resp.status_code == 400
    assert _code(resp) == "inactive_product"


def test_live_blocked_customer(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}]
    )
    customer.status = Customer.Status.BLOCKED
    customer.save()
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 400
    assert _code(resp) == "blocked_customer"


def test_live_completed_immutable(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    other = make_customer(tenant_a.company, name="Other Party")
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}]
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    resp = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv['id']}/",
        {"customer": other.id},
        format="json",
    )
    assert resp.status_code == 400
    assert _code(resp) == "completed_immutable"


def test_live_registration_gate_unregistered(tenant_a):
    tenant_a.company.registration_type = Company.RegistrationType.UNREGISTERED
    tenant_a.company.save(update_fields=["registration_type"])
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}]
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 400
    assert _code(resp) == "registration_gate"


def test_live_registration_gate_composition(tenant_a):
    tenant_a.company.registration_type = Company.RegistrationType.COMPOSITION
    tenant_a.company.gstin = ""
    tenant_a.company.save(update_fields=["registration_type", "gstin"])
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}]
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 400
    assert _code(resp) == "registration_gate"


def test_live_place_of_supply_unresolved(tenant_a):
    tenant_a.company.assume_local_state_for_blank_party = False
    tenant_a.company.save(update_fields=["assume_local_state_for_blank_party"])
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, state="", gstin="")
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}]
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 400
    assert _code(resp) == "place_of_supply_unresolved"


def test_live_credit_limit_exceeded(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "20")
    customer = make_customer(tenant_a.company, credit_limit=Decimal("100.00"))
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "10", "unit_price": "50", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 400
    assert _code(resp) == "credit_limit_exceeded"


def test_live_closed_period(tenant_a):
    today = date.today()
    GstReturnPeriod.objects.create(
        company=tenant_a.company,
        period=f"{today.year:04d}-{today.month:02d}",
        status=GstReturnPeriod.Status.SOFT_CLOSED,
    )
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 400
    assert _code(resp) == "closed_period"


def test_live_company_gstin_required(tenant_a):
    CompanyGstin.objects.create(
        company=tenant_a.company,
        gstin="29ABCDE1234F1ZW",
        state="Karnataka",
        is_primary=True,
        is_active=True,
    )
    CompanyGstin.objects.create(
        company=tenant_a.company,
        gstin="27AAAAA0000A1Z2",
        state="Maharashtra",
        is_primary=False,
        is_active=True,
    )
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}]
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 400
    assert _code(resp) == "company_gstin_required"


def test_live_sales_rcm_unconfirmed(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}]
    )
    tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv['id']}/",
        {"is_reverse_charge": True},
        format="json",
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 400
    assert _code(resp) == "sales_rcm_unconfirmed"


def test_live_invalid_gst_rate(tenant_a):
    product = make_product(tenant_a.company)
    customer = make_customer(tenant_a.company)
    resp = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer.id,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "17"}],
        },
        format="json",
    )
    assert resp.status_code == 400
    assert _code(resp) == "invalid_gst_rate"


def test_live_allocation_exceeds_and_party_mismatch(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "100")
    customer = make_customer(tenant_a.company, state="Karnataka")
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}]
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    receipt = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": "10", "mode": "UPI"},
        format="json",
    )
    assert receipt.status_code == 201, receipt.data
    over = tenant_a.client.post(
        "/api/v1/payments/allocations/",
        {"receipt": receipt.data["id"], "sales_invoice": inv["id"], "amount": "50"},
        format="json",
    )
    assert over.status_code == 400
    assert _code(over) == "allocation_exceeds_unallocated"

    other = make_customer(tenant_a.company, name="Other Party")
    other_receipt = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": other.id, "amount": "50", "mode": "UPI"},
        format="json",
    )
    mismatch = tenant_a.client.post(
        "/api/v1/payments/allocations/",
        {"receipt": other_receipt.data["id"], "sales_invoice": inv["id"], "amount": "10"},
        format="json",
    )
    assert mismatch.status_code == 400
    assert _code(mismatch) == "allocation_party_mismatch"


def test_live_import_invalid_rows(tenant_a):
    from django.core.files.uploadedfile import SimpleUploadedFile

    csv_content = (
        b"name,sku,gst_rate,selling_price,hsn_code\n"
        b"Soap,SOAP-1,18,45,3401\n"
        b"Bad Rate,BAD-1,17,10,3401\n"
    )
    job = tenant_a.client.post(
        "/api/v1/imports/",
        {"kind": "products", "file": SimpleUploadedFile("data.csv", csv_content, content_type="text/csv")},
        format="multipart",
    )
    assert job.status_code == 201, job.data
    resp = tenant_a.client.post(f"/api/v1/imports/{job.data['id']}/commit/")
    assert resp.status_code == 400
    assert _code(resp) == "import_invalid_rows"


def test_live_pdf_or_share_unavailable(tenant_a):
    product = make_product(tenant_a.company)
    customer = make_customer(tenant_a.company, email="c@x.test")
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}]
    )
    share = tenant_a.client.post(
        f"/api/v1/sales/invoices/{inv['id']}/share/",
        {"channel": "email"},
        format="json",
    )
    assert share.status_code == 400
    assert _code(share) == "pdf_or_share_unavailable"

    pdf = tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/pdf/")
    assert pdf.status_code == 400
    assert _code(pdf) == "pdf_or_share_unavailable"


def test_live_permission_denied(tenant_a):
    membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    membership.role = CompanyUser.Role.VIEWER
    for field, value in CompanyUser.capability_defaults_for_role(CompanyUser.Role.VIEWER).items():
        setattr(membership, field, value)
    membership.save()
    client = APIClient()
    client.force_authenticate(user=tenant_a.staff)
    resp = client.post(
        "/api/v1/sales/invoices/",
        {"customer": None, "invoice_type": "GST", "items": []},
        format="json",
    )
    assert resp.status_code == 403
    assert _code(resp) == "permission_denied"
