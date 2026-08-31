"""A-06: WhatsApp invoice + pay link — Cloud opt-in, wa.me fallback, persist status."""

from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product
from tests.test_pdf_and_share import _complete

pytestmark = pytest.mark.django_db


def test_share_whatsapp_without_opt_in_is_wa_me_not_silent(tenant_a):
    data, _ = _complete(tenant_a)
    assert data["whatsapp_offer"]["opt_in"] is False
    assert data["whatsapp_offer"]["has_phone"] is True

    resp = tenant_a.client.post(
        f"/api/v1/sales/invoices/{data['id']}/share/",
        {"channel": "whatsapp"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["status"] == "LINK_READY"
    assert resp.data["mode"] == "link"
    assert resp.data["share_link"].startswith("https://wa.me/")
    assert resp.data["whatsapp_send_status"] == "FALLBACK_LINK"

    invoice = SalesInvoice.objects.get(pk=data["id"])
    assert invoice.whatsapp_send_status == SalesInvoice.WhatsAppSendStatus.FALLBACK_LINK
    assert invoice.whatsapp_share_link.startswith("https://wa.me/")


@override_settings(ENABLE_WHATSAPP_CLOUD=True)
@patch("core.services.whatsapp.requests.post")
def test_cloud_send_after_complete_when_opted_in(mock_post, tenant_a):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"messages": [{"id": "wamid.a06"}]}
    mock_post.return_value = mock_resp

    upsert = tenant_a.client.put(
        "/api/v1/integrations/whatsapp/connection/",
        {"token": "tenant-token", "phone_number_id": "111222333"},
        format="json",
    )
    assert upsert.status_code == 200, upsert.data

    data, _ = _complete(tenant_a, customer_kwargs={"whatsapp_opt_in": True})
    resp = tenant_a.client.post(
        f"/api/v1/sales/invoices/{data['id']}/share/",
        {"channel": "whatsapp"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["status"] == "SENT"
    assert resp.data["mode"] == "cloud"
    assert resp.data["whatsapp_send_status"] == "SENT"
    mock_post.assert_called()

    invoice = SalesInvoice.objects.get(pk=data["id"])
    assert invoice.whatsapp_send_status == SalesInvoice.WhatsAppSendStatus.SENT
    assert invoice.whatsapp_message_id == "wamid.a06"


@override_settings(ENABLE_WHATSAPP_CLOUD=True)
@patch("core.services.whatsapp.requests.post")
def test_opt_in_false_never_calls_cloud(mock_post, tenant_a):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"messages": [{"id": "wamid.should-not"}]}
    mock_post.return_value = mock_resp

    tenant_a.client.put(
        "/api/v1/integrations/whatsapp/connection/",
        {"token": "tenant-token", "phone_number_id": "111222333"},
        format="json",
    )
    data, _ = _complete(tenant_a, customer_kwargs={"whatsapp_opt_in": False})
    resp = tenant_a.client.post(
        f"/api/v1/sales/invoices/{data['id']}/share/",
        {"channel": "whatsapp"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["mode"] == "link"
    assert resp.data["status"] == "LINK_READY"
    mock_post.assert_not_called()


@override_settings(ENABLE_WHATSAPP_CLOUD=True)
@patch("core.services.whatsapp.requests.post")
def test_cloud_token_missing_falls_back_to_wa_me(mock_post, tenant_a):
    data, _ = _complete(tenant_a, customer_kwargs={"whatsapp_opt_in": True})
    resp = tenant_a.client.post(
        f"/api/v1/sales/invoices/{data['id']}/share/",
        {"channel": "whatsapp"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["mode"] == "link"
    assert resp.data["status"] == "LINK_READY"
    assert resp.data["share_link"].startswith("https://wa.me/")
    mock_post.assert_not_called()
    invoice = SalesInvoice.objects.get(pk=data["id"])
    assert invoice.whatsapp_send_status == SalesInvoice.WhatsAppSendStatus.FALLBACK_LINK


def test_customer_whatsapp_opt_in_defaults_false(tenant_a):
    customer = make_customer(tenant_a.company, phone="9876543210")
    assert customer.whatsapp_opt_in is False
    resp = tenant_a.client.patch(
        f"/api/v1/customers/{customer.id}/",
        {"whatsapp_opt_in": True},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    customer.refresh_from_db()
    assert customer.whatsapp_opt_in is True


def test_share_whatsapp_includes_pay_link_when_present(tenant_a):
    data, _ = _complete(tenant_a)
    created = tenant_a.client.post(
        "/api/v1/payments/links/",
        {"sales_invoice": data["id"], "amount": data["grand_total"], "provider": "sandbox"},
        format="json",
    )
    assert created.status_code in (200, 201), created.data
    resp = tenant_a.client.post(
        f"/api/v1/sales/invoices/{data['id']}/share/",
        {"channel": "whatsapp"},
        format="json",
    )
    assert resp.status_code == 200
    assert "/pay/" in (resp.data.get("body") or "") or "/pay/" in (resp.data.get("share_link") or "")
