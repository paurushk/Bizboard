"""Fixes from the October 2026 sales invoice code review."""

from decimal import Decimal

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from sales.models import InvoicePublicLink, SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _completed(tenant, sku="RVW-1"):
    product = make_product(tenant.company, sku=sku, hsn_code="3004", gst_rate="18")
    add_stock(tenant, product, "5")
    customer = make_customer(tenant.company, name="Review Buyer", billing_address="1 Rd", state="Karnataka")
    draft = create_draft_invoice(tenant, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"},
    ])
    done = tenant.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert done.status_code == 200, done.data
    return draft["id"]


@override_settings(FRONTEND_URL="http://front.test")
def test_device_share_mints_the_public_link_and_carries_it(tenant_a):
    invoice_id = _completed(tenant_a)
    res = tenant_a.client.post(
        f"/api/v1/sales/invoices/{invoice_id}/share/",
        {"channel": "WHATSAPP", "recipient": ""}, format="json",
    )
    assert res.status_code == 200, res.data
    assert res.data["mode"] == "device"
    link = InvoicePublicLink.objects.get(invoice_id=invoice_id, revoked_at__isnull=True)
    assert f"http://front.test/i/{link.token}" in res.data["text"]
    assert res.data["document_url"] == f"http://front.test/i/{link.token}"


@override_settings(FRONTEND_URL="http://front.test")
def test_email_share_uses_public_link_not_staff_url(tenant_a):
    invoice_id = _completed(tenant_a, sku="RVW-2")
    from core.models import Notification

    res = tenant_a.client.post(
        f"/api/v1/sales/invoices/{invoice_id}/share/",
        {"channel": "EMAIL", "recipient": "buyer@example.com"}, format="json",
    )
    assert res.status_code == 200, res.data
    body = Notification.objects.order_by("-id").first().body
    assert "/i/" in body
    assert "/sales/history/" not in body


@override_settings(FRONTEND_URL="http://front.test")
def test_cancelled_invoice_pdf_is_gone_on_public_link(tenant_a):
    invoice_id = _completed(tenant_a, sku="RVW-3")
    url = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice_id}/public-link/").data["url"]
    token = url.rsplit("/", 1)[-1]
    SalesInvoice.objects.filter(pk=invoice_id).update(status=SalesInvoice.Status.CANCELLED)
    anon = APIClient()
    assert anon.get(f"/api/v1/public/invoices/{token}/pdf/").status_code == 410


@override_settings(FRONTEND_URL="http://front.test")
def test_link_preview_bots_do_not_count_as_views(tenant_a):
    invoice_id = _completed(tenant_a, sku="RVW-4")
    token = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice_id}/public-link/").data["url"].rsplit("/", 1)[-1]
    anon = APIClient()
    anon.get(f"/api/v1/public/invoices/{token}/", HTTP_USER_AGENT="WhatsApp/2.23")
    assert InvoicePublicLink.objects.get(token=token).view_count == 0
    anon.get(f"/api/v1/public/invoices/{token}/", HTTP_USER_AGENT="Mozilla/5.0 (Windows NT 10.0) Chrome/120")
    assert InvoicePublicLink.objects.get(token=token).view_count == 1


def test_profit_details_excludes_tcs_and_rejects_cancelled(tenant_a):
    invoice_id = _completed(tenant_a, sku="RVW-5")
    base = tenant_a.client.get(f"/api/v1/sales/invoices/{invoice_id}/profit-details/")
    assert base.status_code == 200, base.data
    SalesInvoice.objects.filter(pk=invoice_id).update(tcs_amount=Decimal("10.00"))
    # grand_total is unchanged by this direct update, so only the TCS exclusion moves.
    with_tcs = tenant_a.client.get(f"/api/v1/sales/invoices/{invoice_id}/profit-details/")
    assert Decimal(str(with_tcs.data["sales_amount"])) == Decimal(str(base.data["sales_amount"])) - Decimal("10.00")
    SalesInvoice.objects.filter(pk=invoice_id).update(status=SalesInvoice.Status.CANCELLED)
    assert tenant_a.client.get(f"/api/v1/sales/invoices/{invoice_id}/profit-details/").status_code == 400


def test_zero_due_invoice_completes_without_a_receipt(tenant_a):
    product = make_product(tenant_a.company, sku="RVW-6", hsn_code="3004", gst_rate="0")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Zero Buyer", state="Karnataka")
    draft = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "0", "gst_rate": "0"},
    ])
    res = tenant_a.client.post(
        f"/api/v1/sales/invoices/{draft['id']}/complete/",
        {"amount_received": "50", "payment_mode": "CASH"}, format="json",
    )
    assert res.status_code == 200, res.data
    from payments.models import CustomerReceipt

    assert not CustomerReceipt.objects.filter(customer=customer).exists()


def test_preview_pdf_refuses_misaligned_lines(tenant_a):
    customer = make_customer(tenant_a.company, name="Pv Buyer", state="Karnataka")
    res = tenant_a.client.post(
        "/api/v1/sales/invoices/preview-pdf/",
        {"customer": customer.id, "items": [{"product": 999999, "quantity": "1", "unit_price": "10"}]},
        format="json",
    )
    assert res.status_code in (400, 404), res.status_code
