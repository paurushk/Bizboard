"""Sprint E (BB-000624) — GSP protocol layer, fail-closed live, signed QR."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services.gsp_adapters import (
    HttpSandboxGstrAdapter,
    HttpSandboxIrpAdapter,
    LiveEwayAdapter,
    LiveIrpAdapter,
    StubGstrFilingAdapter,
    get_gstr_filing_adapter,
    get_irp_adapter,
    parse_eway_valid_upto,
)
from core.services.gsp_secrets import encrypt_gsp_credentials
from sales.einvoice_eway_actions import _assert_sandbox_gsp_allowed
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db

GSTIN_CO = "29ABCDE1234F1ZW"
GSTIN_CU = "29AABCU9603R1ZJ"
IRN_OK = "a" * 64

IRP_CASSETTE = {
    "Irn": IRN_OK,
    "AckNo": "121234567890123",
    "AckDt": "2026-08-05 10:00:00",
    "SignedQRCode": json.dumps({"irn": IRN_OK, "ack": "121234567890123"}),
}
EWAY_CASSETTE = {
    "ewayBillNo": "123456789012",
    "validUpto": "2026-08-07 23:59:00",
}
GSTR1_CASSETTE = {"status": "uploaded", "reference_id": "ref-sandbox-1"}
GSTR2B_CASSETTE = {"period": "2026-04", "invoices": []}


class _CassetteResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _cassette_urlopen(cassettes: dict):
    def _open(req, timeout=30):
        url = getattr(req, "full_url", None) or str(req)
        for suffix, payload in cassettes.items():
            if suffix in url:
                return _CassetteResponse(payload)
        raise AssertionError(f"no cassette for {url}")

    return _open


def _gst_ready(tenant):
    company = tenant.company
    company.gstin = GSTIN_CO
    company.state = "29-Karnataka"
    company.address = "1 Main St"
    company.pincode = "560001"
    company.einvoice_enabled = True
    company.eway_enabled = True
    company.gsp_provider = "cleartax"
    company.gsp_credentials_encrypted = encrypt_gsp_credentials({"api_key": "test-gsp-key"})
    company.save()
    product = make_product(company, sku="SPRINT-E", hsn_code="3004")
    add_stock(tenant, product, "5")
    customer = make_customer(
        company,
        name="B2B",
        state="29-Karnataka",
        gstin=GSTIN_CU,
        billing_address="Buyer Street, 560002",
    )
    inv = create_draft_invoice(
        tenant,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "2000", "gst_rate": "18"}],
    )
    assert tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    invoice.transport_distance_km = 120
    invoice.save(update_fields=["transport_distance_km"])
    return invoice


@override_settings(DJANGO_ENV="production", GSP_LIVE_ENABLED=True, GSP_CERTIFIED=False)
def test_prod_uncertified_live_still_fail_closed(tenant_a):
    tenant_a.company.gsp_provider = "cleartax"
    with pytest.raises(BusinessRuleError, match="fail-closed|not NIC"):
        get_irp_adapter(tenant_a.company)
    with pytest.raises(BusinessRuleError, match="not NIC-protocol|fail-closed|Disable GSP_LIVE|GSP_CERTIFIED"):
        LiveIrpAdapter(tenant_a.company)
    with pytest.raises(BusinessRuleError, match="not available in production"):
        _assert_sandbox_gsp_allowed(tenant_a.company)


@override_settings(DJANGO_ENV="staging", GSP_LIVE_ENABLED=True, GSP_CERTIFIED=False)
def test_staging_uncertified_live_still_fail_closed(tenant_a):
    tenant_a.company.gsp_provider = "mastergst"
    with pytest.raises(BusinessRuleError, match="fail-closed|not NIC"):
        get_irp_adapter(tenant_a.company)
    with pytest.raises(BusinessRuleError, match="GSP_CERTIFIED|Disable GSP_LIVE"):
        LiveIrpAdapter(tenant_a.company)


@override_settings(
    DJANGO_ENV="development",
    GSP_LIVE_ENABLED=True,
    GSP_CERTIFIED=True,
    GSP_LIVE_BASE_URL="https://gsp.example.test",
    GSP_PROVIDER="custom",
)
def test_certified_live_dev_submit_marks_generated_with_ack_qr(tenant_a):
    invoice = _gst_ready(tenant_a)
    with patch(
        "urllib.request.urlopen",
        side_effect=_cassette_urlopen({"/irp/invoice": IRP_CASSETTE}),
    ):
        resp = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice.id}/submit-einvoice/")
    assert resp.status_code == 200, resp.data
    invoice.refresh_from_db()
    assert invoice.einvoice_status == SalesInvoice.EInvoiceStatus.GENERATED
    assert invoice.irn == IRN_OK
    assert invoice.ack_no == "121234567890123"
    assert invoice.einvoice_qr
    assert IRN_OK in invoice.einvoice_qr


@override_settings(
    DJANGO_ENV="development",
    GSP_LIVE_ENABLED=True,
    GSP_CERTIFIED=True,
    GSP_LIVE_BASE_URL="https://gsp.example.test",
    GSP_PROVIDER="custom",
)
def test_missing_signed_qr_marks_failed(tenant_a):
    invoice = _gst_ready(tenant_a)
    incomplete = {"Irn": IRN_OK, "AckNo": "ACK-ONLY"}
    with patch(
        "urllib.request.urlopen",
        side_effect=_cassette_urlopen({"/irp/invoice": incomplete}),
    ):
        resp = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice.id}/submit-einvoice/")
    assert resp.status_code == 400, resp.data
    invoice.refresh_from_db()
    assert invoice.einvoice_status == SalesInvoice.EInvoiceStatus.FAILED
    assert "SignedQRCode" in (invoice.einvoice_error or "")
    assert not invoice.irn


@override_settings(
    GSP_LIVE_ENABLED=True,
    GSP_CERTIFIED=True,
    GSP_LIVE_BASE_URL="https://gsp.example.test",
    GSP_PROVIDER="custom",
)
def test_eway_valid_upto_parsed_from_provider_response(tenant_a):
    tenant_a.company.gsp_provider = "cleartax"
    tenant_a.company.gsp_credentials_encrypted = encrypt_gsp_credentials({"api_key": "k"})
    adapter = LiveEwayAdapter(tenant_a.company)
    with patch(
        "urllib.request.urlopen",
        side_effect=_cassette_urlopen({"/eway/generate": EWAY_CASSETTE}),
    ):
        result = adapter.submit({"distance": 100})
    assert result.eway_bill_no == "123456789012"
    assert result.eway_valid_upto.year == 2026
    assert result.eway_valid_upto.month == 8
    assert result.eway_valid_upto.day == 7
    parsed = parse_eway_valid_upto(EWAY_CASSETTE, allow_default=False)
    assert parsed.day == 7
    with pytest.raises(BusinessRuleError, match="validUpto"):
        parse_eway_valid_upto({"ewayBillNo": "1"}, allow_default=False)


def test_submit_einvoice_async_sets_queued(tenant_a):
    invoice = _gst_ready(tenant_a)
    tenant_a.company.gsp_provider = "sandbox"
    tenant_a.company.save(update_fields=["gsp_provider"])
    with patch("sales.tasks.submit_einvoice_async.delay") as delay:
        delay.return_value = SimpleNamespace(id="task-sprint-e")
        resp = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice.id}/submit-einvoice-async/")
    assert resp.status_code == 202, resp.data
    assert resp.data["status"] == "queued"
    assert resp.data["task_id"] == "task-sprint-e"
    invoice.refresh_from_db()
    assert invoice.einvoice_status == SalesInvoice.EInvoiceStatus.QUEUED
    delay.assert_called_once()


@override_settings(
    GSP_HTTP_SANDBOX=True,
    GSP_SANDBOX_BASE_URL="https://sandbox.example.test",
    GSP_LIVE_ENABLED=False,
)
def test_http_sandbox_irp_cassette(tenant_a):
    tenant_a.company.gsp_provider = "sandbox"
    adapter = get_irp_adapter(tenant_a.company)
    assert isinstance(adapter, HttpSandboxIrpAdapter)
    with patch(
        "urllib.request.urlopen",
        side_effect=_cassette_urlopen({"/irp/invoice": IRP_CASSETTE, "/irp/cancel": {"cancelled": True}}),
    ):
        result = adapter.submit({"DocDtls": {"No": "1"}})
        cancel = adapter.cancel(result.irn)
    assert result.irn == IRN_OK
    assert result.ack_no == "121234567890123"
    assert result.einvoice_qr
    assert cancel["cancelled"] is True


@override_settings(
    GSP_HTTP_SANDBOX=True,
    GSP_SANDBOX_BASE_URL="https://sandbox.example.test",
)
def test_http_sandbox_gstr_upload_fetch_cassette(tenant_a):
    adapter = get_gstr_filing_adapter(tenant_a.company)
    assert isinstance(adapter, HttpSandboxGstrAdapter)
    with patch(
        "urllib.request.urlopen",
        side_effect=_cassette_urlopen(
            {
                "/gstr1/upload": GSTR1_CASSETTE,
                "/gstr2b/fetch": GSTR2B_CASSETTE,
            }
        ),
    ):
        uploaded = adapter.upload_gstr1({"period": "2026-04"})
        fetched = adapter.fetch_gstr2b("2026-04")
    assert uploaded["reference_id"] == "ref-sandbox-1"
    assert fetched["period"] == "2026-04"


@override_settings(GSP_HTTP_SANDBOX=False, GSP_LIVE_ENABLED=True)
def test_gstr_live_stays_stub(tenant_a):
    adapter = get_gstr_filing_adapter(tenant_a.company)
    assert isinstance(adapter, StubGstrFilingAdapter)
    with pytest.raises(BusinessRuleError, match="Final Gate|live GSP"):
        adapter.upload_gstr1({})


def test_hash_sandbox_eway_defaults_plus_one_day_when_no_validity():
    before = timezone.now()
    valid = parse_eway_valid_upto({"provider": "sandbox"}, allow_default=True)
    assert valid >= before
    assert (valid - before).total_seconds() >= 23 * 3600
