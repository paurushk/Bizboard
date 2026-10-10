"""Public invoice link: mint, repeat, revoke, anonymous read."""

from django.test import override_settings
from rest_framework.test import APIClient

from sales.models import InvoicePublicLink, SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

import pytest

pytestmark = pytest.mark.django_db


def _completed(tenant):
    product = make_product(tenant.company, sku="PUB-1", hsn_code="3004", gst_rate="18")
    add_stock(tenant, product, "5")
    customer = make_customer(
        tenant.company, name="Public Buyer", billing_address="12 Lane", state="Karnataka",
    )
    draft = create_draft_invoice(tenant, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"},
    ])
    SalesInvoice.objects.filter(pk=draft["id"]).update(notes="secret-internal-note")
    done = tenant.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert done.status_code == 200, done.data
    return draft["id"]


@override_settings(FRONTEND_URL="http://front.test")
def test_public_link_mint_repeat_revoke_and_anonymous_get(tenant_a):
    invoice_id = _completed(tenant_a)
    first = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice_id}/public-link/")
    assert first.status_code == 200, first.data
    url = first.data["url"]
    assert url.startswith("http://front.test/i/")
    token = url.rsplit("/", 1)[-1]
    second = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice_id}/public-link/")
    assert second.status_code == 200, second.data
    assert second.data["url"] == url
    assert InvoicePublicLink.objects.filter(invoice_id=invoice_id, revoked_at__isnull=True).count() == 1

    anon = APIClient()
    page = anon.get(f"/api/v1/public/invoices/{token}/")
    assert page.status_code == 200, page.data
    assert page["Referrer-Policy"] == "no-referrer"
    assert "no-store" in page["Cache-Control"]
    assert page["X-Robots-Tag"] == "noindex"
    assert page.data["seller_name"]
    assert page.data["number"]
    assert page.data["lines"]
    assert "paid" in page.data and "unpaid" in page.data
    assert "secret-internal-note" not in str(page.data)
    assert "unit_cost" not in str(page.data)
    assert "purchase_price" not in str(page.data)
    assert "profit" not in str(page.data).lower()
    assert "margin" not in str(page.data).lower()

    pdf = anon.get(f"/api/v1/public/invoices/{token}/pdf/")
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    assert "no-store" in pdf["Cache-Control"]

    missing = anon.get("/api/v1/public/invoices/not-a-real-token/")
    assert missing.status_code == 404

    revoked = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice_id}/public-link/revoke/")
    assert revoked.status_code == 200, revoked.data
    gone = anon.get(f"/api/v1/public/invoices/{token}/")
    assert gone.status_code == 404

    minted = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice_id}/public-link/")
    assert minted.status_code == 200, minted.data
    assert minted.data["url"] != url
    assert minted.data["url"].startswith("http://front.test/i/")


def test_public_pay_mints_a_pay_path_and_reuses_it(tenant_a):
    invoice_id = _completed(tenant_a)
    minted = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice_id}/public-link/")
    assert minted.status_code == 200, minted.data
    token = minted.data["url"].rsplit("/", 1)[-1]
    anon = APIClient()
    first = anon.post(f"/api/v1/public/invoices/{token}/pay/")
    assert first.status_code == 200, first.data
    assert str(first.data["path"]).startswith("/pay/")
    second = anon.post(f"/api/v1/public/invoices/{token}/pay/")
    assert second.status_code == 200, second.data
    assert second.data["path"] == first.data["path"]


@override_settings(DJANGO_ENV="production")
def test_public_pay_without_gateway_credentials_names_the_requirement(tenant_a):
    invoice_id = _completed(tenant_a)
    minted = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice_id}/public-link/")
    token = minted.data["url"].rsplit("/", 1)[-1]
    anon = APIClient()
    resp = anon.post(f"/api/v1/public/invoices/{token}/pay/")
    assert resp.status_code == 400, resp.data
    assert "credential" in str(resp.data).lower()


@override_settings(DJANGO_ENV="production")
def test_public_pay_with_gateway_credentials_returns_a_path(tenant_a, monkeypatch):
    from payments.gateway import CreateLinkResult, encrypt_gateway_credentials

    invoice_id = _completed(tenant_a)
    company = tenant_a.company
    company.payment_gateway_provider = "razorpay"
    company.payment_gateway_credentials_encrypted = encrypt_gateway_credentials(
        {"key_id": "rzp_test", "key_secret": "secret"},
    )
    company.save(update_fields=["payment_gateway_provider", "payment_gateway_credentials_encrypted"])

    class Adapter:
        name = "razorpay"

        def create_payment_link(self, **kwargs):
            return CreateLinkResult(provider_link_id="pl_1", short_url="https://pay.example/1", raw={})

    monkeypatch.setattr("payments.services.get_adapter", lambda *args, **kwargs: Adapter())
    minted = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice_id}/public-link/")
    token = minted.data["url"].rsplit("/", 1)[-1]
    anon = APIClient()
    resp = anon.post(f"/api/v1/public/invoices/{token}/pay/")
    assert resp.status_code == 200, resp.data
    assert str(resp.data["path"]).startswith("/pay/")


@override_settings(FRONTEND_URL="http://front.test")
def test_cancel_keeps_the_public_page_and_blocks_the_pdf(tenant_a):
    """Cancel does not revoke the link. The page can say Cancelled; the PDF cannot download."""
    invoice_id = _completed(tenant_a)
    token = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice_id}/public-link/").data["url"].rsplit("/", 1)[-1]
    cancelled = tenant_a.client.post(
        f"/api/v1/sales/invoices/{invoice_id}/cancel/",
        {"reason": "wrong bill"},
        format="json",
    )
    assert cancelled.status_code == 200, cancelled.data
    assert cancelled.data["status"] == "CANCELLED"
    assert InvoicePublicLink.objects.filter(invoice_id=invoice_id, revoked_at__isnull=True).count() == 1

    anon = APIClient()
    page = anon.get(f"/api/v1/public/invoices/{token}/")
    assert page.status_code == 200, page.data
    assert page.data["status"] == "CANCELLED"
    pdf = anon.get(f"/api/v1/public/invoices/{token}/pdf/")
    assert pdf.status_code == 410


@override_settings(FRONTEND_URL="http://front.test")
def test_full_return_removes_the_public_link(tenant_a):
    product = make_product(tenant_a.company, sku="PUB-RET", hsn_code="3004", gst_rate="18")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Return Buyer", state="Karnataka")
    draft = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "18"},
    ])
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200
    token = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/public-link/").data["url"].rsplit("/", 1)[-1]

    created = tenant_a.client.post("/api/v1/sales/returns/", {
        "customer": customer.id,
        "sales_invoice": draft["id"],
        "items": [{"product": product.id, "quantity": "2", "unit_price": "100"}],
    }, format="json")
    assert created.status_code == 201, created.data
    done = tenant_a.client.post(f"/api/v1/sales/returns/{created.data['id']}/complete/")
    assert done.status_code == 200, done.data

    assert InvoicePublicLink.objects.filter(invoice_id=draft["id"], revoked_at__isnull=True).count() == 0
    anon = APIClient()
    assert anon.get(f"/api/v1/public/invoices/{token}/").status_code == 404


@override_settings(FRONTEND_URL="http://front.test")
def test_partial_return_keeps_the_public_link(tenant_a):
    product = make_product(tenant_a.company, sku="PUB-PART", hsn_code="3004", gst_rate="18")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Partial Buyer", state="Karnataka")
    draft = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "18"},
    ])
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200
    token = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/public-link/").data["url"].rsplit("/", 1)[-1]

    created = tenant_a.client.post("/api/v1/sales/returns/", {
        "customer": customer.id,
        "sales_invoice": draft["id"],
        "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
    }, format="json")
    assert created.status_code == 201, created.data
    assert tenant_a.client.post(f"/api/v1/sales/returns/{created.data['id']}/complete/").status_code == 200

    assert InvoicePublicLink.objects.filter(invoice_id=draft["id"], revoked_at__isnull=True).count() == 1
    page = APIClient().get(f"/api/v1/public/invoices/{token}/")
    assert page.status_code == 200, page.data
    assert page.data["status"] == "COMPLETED"


def test_public_link_rejects_a_draft(tenant_a):
    product = make_product(tenant_a.company, sku="PUB-D", gst_rate="0")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company)
    draft = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/public-link/")
    assert resp.status_code == 400, resp.data
    assert InvoicePublicLink.objects.filter(invoice_id=draft["id"]).count() == 0
