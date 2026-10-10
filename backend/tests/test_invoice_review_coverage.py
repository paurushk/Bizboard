"""Coverage for the sales invoice review fixes: profit details, preview PDF, shared links, public page helpers."""

from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from accounts.models import CompanyUser, User
from sales.models import InvoicePublicLink, SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _member(tenant, *, role, suffix, **flags):
    user = User.objects.create_user(
        email=f"{role.lower()}-{suffix}@{tenant.company.id}.test",
        password="StrongPass123!",
        full_name=f"{role.title()} {suffix}",
    )
    CompanyUser.objects.create(company=tenant.company, user=user, role=role, **flags)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _completed_invoice(tenant, sku, *, qty="1", price="100"):
    product = make_product(tenant.company, sku=sku, hsn_code="3004", gst_rate="18")
    add_stock(tenant, product, "10")
    customer = make_customer(tenant.company, name=f"{sku} Buyer", state="Karnataka")
    draft = create_draft_invoice(tenant, customer, [
        {"product": product.id, "quantity": qty, "unit_price": price, "gst_rate": "18"},
    ])
    done = tenant.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert done.status_code == 200, done.data
    return draft["id"], product, customer


# --- profit details -------------------------------------------------------


def test_completed_profit_has_no_cost_warning_and_reads_moves_in_one_query(tenant_a):
    invoice_id, _, _ = _completed_invoice(tenant_a, "PRF-1", qty="2")
    with CaptureQueriesContext(connection) as ctx:
        res = tenant_a.client.get(f"/api/v1/sales/invoices/{invoice_id}/profit-details/")
    assert res.status_code == 200, res.data
    assert res.data["estimated"] is False
    assert res.data["cost_incomplete"] is False
    reads = [
        q for q in ctx.captured_queries
        if "inventory_stockmovement" in q["sql"].lower() and q["sql"].lstrip().upper().startswith("SELECT")
    ]
    assert len(reads) <= 2, f"stock movements are read once per line again: {len(reads)}"


def test_draft_profit_with_a_service_line_does_not_crash_or_warn_about_it(tenant_a):
    service = make_product(
        tenant_a.company, sku="PRF-SVC", hsn_code="9983", gst_rate="18",
        product_type="SERVICE", track_inventory=False,
    )
    customer = make_customer(tenant_a.company, name="Svc Buyer", state="Karnataka")
    draft = create_draft_invoice(tenant_a, customer, [
        {"product": service.id, "quantity": "1", "unit_price": "500", "gst_rate": "18"},
    ])
    res = tenant_a.client.get(f"/api/v1/sales/invoices/{draft['id']}/profit-details/")
    assert res.status_code == 200, res.data
    assert res.data["cost_incomplete"] is False
    assert res.data["lines"][0]["cost_missing"] is False
    assert Decimal(str(res.data["total_cost"])) == Decimal("0")


def test_profit_details_is_forbidden_without_financial_reports(tenant_a):
    invoice_id, _, _ = _completed_invoice(tenant_a, "PRF-403")
    seller = _member(tenant_a, role=CompanyUser.Role.SALES_STAFF, suffix="prf-s", can_create_sales=True)
    assert seller.get(f"/api/v1/sales/invoices/{invoice_id}/profit-details/").status_code == 403


# --- preview PDF ----------------------------------------------------------


def test_preview_pdf_rejects_bad_numbers_and_too_many_lines(tenant_a):
    product = make_product(tenant_a.company, sku="PV-1", hsn_code="3004", gst_rate="18")
    customer = make_customer(tenant_a.company, name="Pv Buyer 2", state="Karnataka")
    url = "/api/v1/sales/invoices/preview-pdf/"
    bad = tenant_a.client.post(url, {
        "customer": customer.id,
        "items": [{"product": product.id, "quantity": "abc", "unit_price": "10", "gst_rate": "18"}],
    }, format="json")
    assert bad.status_code == 400, getattr(bad, "data", bad.status_code)
    many = tenant_a.client.post(url, {
        "customer": customer.id,
        "items": [{"product": product.id, "quantity": "1", "unit_price": "1", "gst_rate": "18"}] * 301,
    }, format="json")
    assert many.status_code == 400, getattr(many, "data", many.status_code)


# --- shared links ---------------------------------------------------------


@override_settings(FRONTEND_URL="http://front.test")
def test_amending_a_completed_invoice_keeps_the_shared_link(tenant_a):
    invoice_id, product, _ = _completed_invoice(tenant_a, "AMD-LINK")
    url = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice_id}/public-link/").data["url"]
    token = url.rsplit("/", 1)[-1]
    current = tenant_a.client.get(f"/api/v1/sales/invoices/{invoice_id}/").data
    # An amend may change the price but not the GST rate, so keep the rate the invoice has.
    kept_rate = current["items"][0]["gst_rate"]
    amend = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{invoice_id}/",
        {
            "confirm_amend": True,
            "expected_amend_revision": current.get("amend_revision", 0),
            "items": [{"product": product.id, "quantity": "1", "unit_price": "90", "gst_rate": kept_rate}],
        },
        format="json",
    )
    assert amend.status_code == 200, amend.data
    assert InvoicePublicLink.objects.get(token=token).revoked_at is None
    assert APIClient().get(f"/api/v1/public/invoices/{token}/").status_code == 200


@override_settings(FRONTEND_URL="http://front.test")
def test_revoking_links_makes_the_public_page_disappear(tenant_a):
    from sales.public_links import revoke_invoice_public_links

    invoice_id, _, _ = _completed_invoice(tenant_a, "RET-LINK")
    token = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice_id}/public-link/").data["url"].rsplit("/", 1)[-1]
    revoke_invoice_public_links(SalesInvoice.objects.get(pk=invoice_id))
    assert APIClient().get(f"/api/v1/public/invoices/{token}/").status_code == 404


def test_a_draft_invoice_cannot_get_a_shared_link(tenant_a):
    product = make_product(tenant_a.company, sku="DRAFT-LINK", hsn_code="3004", gst_rate="18")
    customer = make_customer(tenant_a.company, name="Draft Link", state="Karnataka")
    draft = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "18"},
    ])
    res = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/public-link/")
    assert res.status_code == 400
    assert not InvoicePublicLink.objects.filter(invoice_id=draft["id"]).exists()


# --- public page helpers --------------------------------------------------


def test_link_preview_detection_recognises_chat_apps_and_not_browsers():
    from sales.public_invoice_views import _is_link_preview

    def req(agent):
        return SimpleNamespace(META={} if agent is None else {"HTTP_USER_AGENT": agent})

    for agent in ("WhatsApp/2.23.20", "facebookexternalhit/1.1", "Slackbot-LinkExpanding 1.0", "TelegramBot", None, ""):
        assert _is_link_preview(req(agent)) is True, agent
    assert _is_link_preview(req("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36")) is False


def test_public_pay_throttle_is_stricter_than_reads():
    from rest_framework.throttling import AnonRateThrottle

    from sales.public_invoice_views import PublicInvoicePayThrottle

    rates = dict(AnonRateThrottle.THROTTLE_RATES)
    rates["customer_portal_read"] = "60/min"
    rates.pop("public_invoice_pay", None)
    with mock.patch.object(AnonRateThrottle, "THROTTLE_RATES", rates):
        assert PublicInvoicePayThrottle().get_rate() == "10/min"
        rates["public_invoice_pay"] = "3/min"
        assert PublicInvoicePayThrottle().get_rate() == "3/min"


def test_public_pdf_for_a_live_invoice_is_a_fresh_pdf_with_no_store_header(tenant_a):
    invoice_id, _, _ = _completed_invoice(tenant_a, "PDF-LIVE")
    token = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice_id}/public-link/").data["url"].rsplit("/", 1)[-1]
    res = APIClient().get(f"/api/v1/public/invoices/{token}/pdf/")
    assert res.status_code == 200
    assert res.content.startswith(b"%PDF")
    assert "no-store" in res["Cache-Control"]


# --- payment settle edge --------------------------------------------------


def test_zero_due_with_a_card_tender_still_completes_without_a_receipt(tenant_a):
    from payments.models import CustomerReceipt

    product = make_product(tenant_a.company, sku="ZERO-CARD", hsn_code="3004", gst_rate="0")
    add_stock(tenant_a, product, "3")
    customer = make_customer(tenant_a.company, name="Zero Card", state="Karnataka")
    draft = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "0", "gst_rate": "0"},
    ])
    res = tenant_a.client.post(
        f"/api/v1/sales/invoices/{draft['id']}/complete/",
        {"amount_received": "10", "payment_mode": "CARD"}, format="json",
    )
    assert res.status_code == 200, res.data
    assert not CustomerReceipt.objects.filter(customer=customer).exists()
