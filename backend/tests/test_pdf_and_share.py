"""Async PDF flow (§14) and share via Notification Service (E4.10)."""

import pytest

from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _complete(tenant):
    product = make_product(tenant.company)
    add_stock(tenant, product, "10")
    customer = make_customer(tenant.company, phone="9876543210", email="c@x.test")
    inv = create_draft_invoice(tenant, customer, [
        {"product": product.id, "quantity": "2", "unit_price": "100"}
    ])
    resp = tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 200
    return resp.data


def test_pdf_generated_after_complete(tenant_a):
    data = _complete(tenant_a)
    # Celery eager: PDF task ran synchronously in tests
    resp = tenant_a.client.get(f"/api/v1/sales/invoices/{data['id']}/pdf-status/")
    assert resp.data["pdf_status"] == "READY"
    assert resp.data["pdf_file"] is not None

    download = tenant_a.client.get(f"/api/v1/sales/invoices/{data['id']}/pdf/")
    assert download.status_code == 200
    content = b"".join(download.streaming_content)
    assert content.startswith(b"%PDF")


def test_draft_invoice_has_no_pdf(tenant_a):
    product = make_product(tenant_a.company)
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"}
    ])
    assert inv["pdf_status"] == "NONE"
    resp = tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/pdf/")
    assert resp.status_code == 400


def test_share_whatsapp_returns_link(tenant_a):
    data = _complete(tenant_a)
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{data['id']}/share/", {
        "channel": "whatsapp",
    }, format="json")
    assert resp.status_code == 200
    assert resp.data["status"] == "SENT"
    assert resp.data["share_link"].startswith("https://wa.me/")


def test_share_email_queued_and_sent(tenant_a):
    data = _complete(tenant_a)
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{data['id']}/share/", {
        "channel": "email",
    }, format="json")
    assert resp.status_code == 200
    # Console email backend + eager celery → SENT
    assert resp.data["status"] == "SENT"

    listing = tenant_a.client.get("/api/v1/notifications/")
    assert listing.data["count"] >= 1


def test_cannot_share_draft(tenant_a):
    product = make_product(tenant_a.company)
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"}
    ])
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/share/", {
        "channel": "whatsapp",
    }, format="json")
    assert resp.status_code == 400
