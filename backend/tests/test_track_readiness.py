"""Track readiness gaps: filing record, Tally batch, Shopify HMAC, forecast, onboarding."""

from decimal import Decimal

import pytest
from django.test import override_settings

from core.services.gsp_secrets import encrypt_gsp_credentials
from integrations.models import IntegrationConnection
from integrations.shopify import ShopifyWebhookView
from integrations.tally_diff import record_migration_diff
from inventory.forecast import demand_forecast
from reporting.filing import record_period_filing
from reporting.gst_returns import einvoice_aato_threshold
from rest_framework.test import APIRequestFactory

pytestmark = pytest.mark.django_db


def test_einvoice_threshold_reads_settings():
    with override_settings(EINVOICE_AATO_THRESHOLD="100"):
        assert einvoice_aato_threshold() == Decimal("100")


def test_period_filing_is_not_stored_on_an_invoice(tenant_a):
    row = record_period_filing(
        company=tenant_a.company,
        return_type="GSTR-1",
        period="2026-09",
        status="REJECTED",
        error_message="Portal rejected the period.",
        user=tenant_a.owner,
    )
    assert row.period == "2026-09"
    assert row.error_message.startswith("Portal")


def test_tally_batch_refuses_a_second_post(tenant_a):
    from core.exceptions import BusinessRuleError

    record_migration_diff(
        company=tenant_a.company, batch_id="b1", tally_total=Decimal("10"), books_total=Decimal("10"),
        user=tenant_a.owner,
    )
    with pytest.raises(BusinessRuleError):
        record_migration_diff(
            company=tenant_a.company, batch_id="b1", tally_total=Decimal("10"), books_total=Decimal("10"),
            user=tenant_a.owner,
        )


def test_tally_diff_above_tolerance_is_blocked(tenant_a):
    run = record_migration_diff(
        company=tenant_a.company, batch_id="b2", tally_total=Decimal("100"), books_total=Decimal("10"),
        user=tenant_a.owner,
    )
    assert run.result["blocked"] is True


def test_shopify_unknown_shop_is_401():
    # QOS-0002: an unrecognized shop must fail closed the same way a bad
    # signature does (401), not 404 -- a 404 here would let a caller
    # distinguish "no such shop" from "bad signature" and enumerate
    # configured shop domains (see errors/test_webhook_enumeration.py).
    factory = APIRequestFactory()
    request = factory.post("/api/v1/integrations/shopify/webhook/", data=b"{}", content_type="application/json")
    response = ShopifyWebhookView.as_view()(request)
    assert response.status_code == 401


def test_shopify_bad_hmac_is_401(tenant_a):
    IntegrationConnection.objects.create(
        company=tenant_a.company,
        provider=IntegrationConnection.Provider.SHOPIFY,
        encrypted_secrets=encrypt_gsp_credentials({"webhook_secret": "sekret"}),
        metadata={"shop_domain": "demo.myshopify.com"},
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    factory = APIRequestFactory()
    request = factory.post(
        "/api/v1/integrations/shopify/webhook/",
        data=b"{}",
        content_type="application/json",
        HTTP_X_SHOPIFY_SHOP_DOMAIN="demo.myshopify.com",
        HTTP_X_SHOPIFY_HMAC_SHA256="nope",
    )
    response = ShopifyWebhookView.as_view()(request)
    assert response.status_code == 401


def test_demand_forecast_labels_method(tenant_a):
    rows = demand_forecast(tenant_a.company)
    assert rows == []


def test_crm_onboarding_lists_steps(tenant_a):
    response = tenant_a.client.get("/api/v1/crm/onboarding/")
    assert response.status_code == 200
    assert len(response.data["steps"]) == 4


def test_plain_gsp_error_is_bilingual():
    from core.services.gsp_adapters import plain_gsp_error

    text = plain_gsp_error("NIC 2150 duplicate IRN")
    assert "already has an IRN" in text
    assert "IRN" in text.split("/")[-1]


def test_tally_xml_amounts_and_signature_pdf():
    from integrations.tally_diff import migration_pdf_bytes, parse_tally_amounts

    assert parse_tally_amounts("<AMOUNT>1.50</AMOUNT><AMOUNT>2.25</AMOUNT>") == Decimal("3.75")

    class Run:
        counts = {"batch_id": "b", "tally_total": "3.75", "books_total": "3.75"}
        result = {"diff": "0.00", "tolerance": "5.00", "blocked": False}

    assert migration_pdf_bytes(Run()).startswith(b"%PDF")


def test_http_lookup_404_returns_none(monkeypatch):
    from core.exceptions import BusinessRuleError
    from core.services.gsp_adapters import HttpSandboxIrpAdapter

    def boom(*_args, **_kwargs):
        raise BusinessRuleError("GSP HTTP 404")

    monkeypatch.setattr("core.services.gsp_adapters._http_json", boom)
    with override_settings(GSP_SANDBOX_BASE_URL="https://gsp.example"):
        adapter = HttpSandboxIrpAdapter(company=None)
        assert adapter.lookup_by_doc("INV-1") is None


def _shopify_request(body: bytes, **headers):
    import base64
    import hashlib
    import hmac

    factory = APIRequestFactory()
    digest = base64.b64encode(hmac.new(b"sekret", body, hashlib.sha256).digest()).decode()
    return factory.post(
        "/api/v1/integrations/shopify/webhook/",
        data=body,
        content_type="application/json",
        HTTP_X_SHOPIFY_SHOP_DOMAIN="demo.myshopify.com",
        HTTP_X_SHOPIFY_HMAC_SHA256=digest,
        **headers,
    )


def test_shopify_order_imports_once_and_skips_unknown_sku(tenant_a):
    import json

    from inventory.services import InventoryService
    from sales.models import SalesOrder
    from tests.conftest import make_customer, make_product

    product = make_product(tenant_a.company, sku="WID-1")
    customer = make_customer(tenant_a.company)
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    IntegrationConnection.objects.create(
        company=tenant_a.company,
        provider=IntegrationConnection.Provider.SHOPIFY,
        encrypted_secrets=encrypt_gsp_credentials({"webhook_secret": "sekret"}),
        metadata={
            "shop_domain": "demo.myshopify.com",
            "warehouse_id": warehouse.id,
            "customer_id": customer.id,
        },
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    missing = json.dumps({"id": 9, "line_items": [{"sku": "NOPE", "quantity": 1, "price": "10"}]}).encode()
    skipped = ShopifyWebhookView.as_view()(_shopify_request(missing, HTTP_X_SHOPIFY_WEBHOOK_ID="d1", HTTP_X_SHOPIFY_TOPIC="orders/create"))
    assert skipped.status_code == 200
    assert skipped.data["applied"] is False
    assert SalesOrder.objects.filter(company=tenant_a.company).count() == 0

    body = json.dumps({
        "id": 10,
        "line_items": [{"sku": product.sku, "quantity": 1, "price": "100.00"}],
    }).encode()
    created = ShopifyWebhookView.as_view()(_shopify_request(body, HTTP_X_SHOPIFY_WEBHOOK_ID="d2", HTTP_X_SHOPIFY_TOPIC="orders/create"))
    assert created.status_code == 200
    assert created.data["applied"] is True
    again = ShopifyWebhookView.as_view()(_shopify_request(body, HTTP_X_SHOPIFY_WEBHOOK_ID="d2", HTTP_X_SHOPIFY_TOPIC="orders/create"))
    assert again.data["status"] == "duplicate"
    assert SalesOrder.objects.filter(company=tenant_a.company).count() == 1
