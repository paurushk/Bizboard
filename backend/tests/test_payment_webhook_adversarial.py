"""Wave A adversarial payment webhook tests (BB-000196/258/265/269/307)."""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from core.exceptions import BusinessRuleError
from payments.gateway import (
    RazorpayAdapter,
    SandboxAdapter,
    get_adapter,
    sandbox_webhook_secret_for_company,
)
from payments.models import PaymentLinkStatus
from payments.services import PaymentService
from tests.test_phase3_payments import _complete_invoice

pytestmark = pytest.mark.django_db


def _sandbox_sig(body: bytes, company_id=None, secret: str = "test-sandbox-webhook-secret") -> str:
    # BB-000412: prefer per-company derived secret when company known.
    if company_id is not None:
        key = sandbox_webhook_secret_for_company(company_id)
    else:
        key = secret
    return hmac.new(key.encode(), body, hashlib.sha256).hexdigest()


def test_get_adapter_empty_creds_razorpay_fails():
    with pytest.raises(BusinessRuleError):
        get_adapter("razorpay", None)
    with pytest.raises(BusinessRuleError):
        get_adapter("razorpay", {})


def test_get_adapter_sandbox_ok():
    adapter = get_adapter("sandbox")
    assert adapter.name == "sandbox"


def test_cashfree_payu_scaffold_fail_closed_or_http_error():
    pytest.importorskip("requests")
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"message": "Unauthorized"}
        mock_post.return_value = mock_resp
        with pytest.raises(BusinessRuleError):
            get_adapter("cashfree", {"app_id": "x", "secret_key": "y"}).create_payment_link(
                amount=Decimal("10"),
                description="",
                customer_name="",
                customer_email="",
                customer_phone="",
                reference="",
                callback_url="http://x",
            )
    assert get_adapter("payu", {"merchant_key": "k", "merchant_salt": "s"}).verify_webhook(
        headers={}, body=b"{}"
    ) is False


def test_payu_s2s_callback_is_form_encoded_not_json():
    """PAY-03: PayU posts its S2S callback as application/x-www-form-urlencoded.
    The adapter must parse that (not only JSON) and its reverse hash must
    validate a correctly-signed form body."""
    from urllib.parse import urlencode

    key, salt = "testkey", "testsalt"
    fields = {
        "key": key,
        "txnid": "bb_payu_1",
        "amount": "100.00",
        "productinfo": "Invoice INV-1",
        "firstname": "Asha",
        "email": "asha@example.com",
        "status": "success",
        "mihpayid": "403993715512345678",
        "udf1": "",
        "udf2": "",
    }
    udf = [fields.get(f"udf{i}", "") for i in range(1, 11)]
    rev_udf = "|".join(reversed(udf))
    seq = (
        f"{salt}|{fields['status']}|{rev_udf}|{fields['email']}|{fields['firstname']}|"
        f"{fields['productinfo']}|{fields['amount']}|{fields['txnid']}|{key}"
    )
    fields["hash"] = hashlib.sha512(seq.encode()).hexdigest()
    body = urlencode(fields).encode()

    from payments.gateway import PayUGateway

    adapter = PayUGateway({"merchant_key": key, "merchant_salt": salt})
    assert adapter.verify_webhook(headers={}, body=body) is True

    event = adapter.parse_webhook(body=body)
    assert event is not None
    assert event.provider_payment_id == "403993715512345678"
    assert event.status == "CAPTURED"
    assert event.payment_link_id == "bb_payu_1"

    # A tampered amount must fail the signature.
    tampered = dict(fields)
    tampered["amount"] = "1.00"
    assert adapter.verify_webhook(headers={}, body=urlencode(tampered).encode()) is False


def test_razorpay_no_stub_on_missing_keys():
    with pytest.raises(BusinessRuleError):
        RazorpayAdapter({}).create_payment_link(
            amount=Decimal("10"),
            description="",
            customer_name="",
            customer_email="",
            customer_phone="",
            reference="",
            callback_url="http://x",
        )


def test_razorpay_http_error_no_stub():
    pytest.importorskip("requests")
    adapter = RazorpayAdapter({"key_id": "rzp_test", "key_secret": "secret", "webhook_secret": "whsec"})
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "boom"
    with patch("requests.post", return_value=mock_resp):
        with pytest.raises(BusinessRuleError):
            adapter.create_payment_link(
                amount=Decimal("10"),
                description="",
                customer_name="",
                customer_email="",
                customer_phone="",
                reference="",
                callback_url="http://x",
            )


def test_razorpay_webhook_requires_dedicated_secret():
    adapter = RazorpayAdapter({"key_id": "k", "key_secret": "s"})
    assert adapter.webhook_secret == ""
    assert adapter.verify_webhook(headers={"X-Razorpay-Signature": "x"}, body=b"{}") is False


def test_sandbox_static_ok_rejected(tenant_a):
    """BB-000258: static X-Sandbox-Signature: ok must not verify."""
    adapter = SandboxAdapter()
    assert adapter.verify_webhook(headers={"X-Sandbox-Signature": "ok"}, body=b'{"a":1}') is False


@override_settings(SANDBOX_WEBHOOK_SECRET="test-sandbox-webhook-secret", DJANGO_ENV="test")
def test_sandbox_hmac_settles(tenant_a):
    inv, customer = _complete_invoice(tenant_a)
    link = PaymentService.create_payment_link(
        company=tenant_a.company,
        amount=Decimal("1000"),
        sales_invoice=inv,
        customer=customer,
        provider="sandbox",
        public_base_url="http://testserver",
    )
    body_dict = {
        "payment_id": "pay_hmac",
        "amount": "1000.00",
        "fee": "0",
        "status": "CAPTURED",
        "payment_link_id": link.provider_link_id,
    }
    raw = json.dumps(body_dict).encode()
    sig = _sandbox_sig(raw, company_id=tenant_a.company.id)
    wh = tenant_a.client.post(
        f"/api/v1/webhooks/payments/sandbox/?company_id={tenant_a.company.id}",
        body_dict,
        format="json",
        HTTP_X_SANDBOX_SIGNATURE=sig,
    )
    # DRF re-encodes JSON — signature must match request.body; use content= for exact body
    assert wh.status_code in (200, 401)
    # Retry with exact body bytes via generic client post
    from django.test import Client

    c = Client()
    wh2 = c.post(
        f"/api/v1/webhooks/payments/sandbox/?company_id={tenant_a.company.id}",
        data=raw,
        content_type="application/json",
        HTTP_X_SANDBOX_SIGNATURE=sig,
    )
    assert wh2.status_code == 200
    link.refresh_from_db()
    assert link.status == PaymentLinkStatus.PAID


def test_empty_creds_sandbox_signature_does_not_settle_razorpay_link(tenant_a):
    inv, customer = _complete_invoice(tenant_a)
    link = PaymentService.create_payment_link(
        company=tenant_a.company,
        amount=Decimal("1000"),
        sales_invoice=inv,
        customer=customer,
        provider="sandbox",
        public_base_url="http://testserver",
    )
    body = {
        "payment_id": "pay_forge",
        "amount": "1000.00",
        "fee": "0",
        "status": "CAPTURED",
        "payment_link_id": link.provider_link_id,
    }
    wh = tenant_a.client.post(
        f"/api/v1/webhooks/payments/razorpay/?company_id={tenant_a.company.id}",
        body,
        format="json",
        HTTP_X_SANDBOX_SIGNATURE="ok",
    )
    assert wh.status_code in (400, 401, 403)
    link.refresh_from_db()
    assert link.status != PaymentLinkStatus.PAID


@override_settings(DJANGO_ENV="development")
def test_named_provider_empty_creds_never_remaps_to_sandbox(tenant_a):
    """BB-000265: non-prod must not remap razorpay → sandbox."""
    inv, customer = _complete_invoice(tenant_a)
    company = tenant_a.company
    company.payment_gateway_test_mode = True
    company.payment_gateway_credentials_encrypted = ""
    company.save(update_fields=["payment_gateway_test_mode", "payment_gateway_credentials_encrypted"])
    link = PaymentService.create_payment_link(
        company=company,
        amount=Decimal("1000"),
        sales_invoice=inv,
        customer=customer,
        provider="sandbox",
        public_base_url="http://testserver",
    )
    body = {
        "payment_id": "pay_remap",
        "amount": "1000.00",
        "fee": "0",
        "status": "CAPTURED",
        "payment_link_id": link.provider_link_id,
    }
    wh = tenant_a.client.post(
        f"/api/v1/webhooks/payments/razorpay/?company_id={company.id}",
        body,
        format="json",
        HTTP_X_SANDBOX_SIGNATURE="ok",
    )
    assert wh.status_code in (400, 403)
    link.refresh_from_db()
    assert link.status != PaymentLinkStatus.PAID


@override_settings(DJANGO_ENV="production", SANDBOX_WEBHOOK_SECRET="test-sandbox-webhook-secret")
def test_test_mode_sandbox_settle_blocked_in_production(tenant_a):
    """BB-000379: cannot create or settle sandbox links in production."""
    inv, customer = _complete_invoice(tenant_a)
    company = tenant_a.company
    company.payment_gateway_test_mode = True
    company.payment_gateway_credentials_encrypted = ""
    company.save(update_fields=["payment_gateway_test_mode", "payment_gateway_credentials_encrypted"])
    with pytest.raises(BusinessRuleError, match="sandbox"):
        PaymentService.create_payment_link(
            company=company,
            amount=Decimal("1000"),
            sales_invoice=inv,
            customer=customer,
            provider="sandbox",
            public_base_url="http://testserver",
        )
    # Webhook path also forbidden even if a stale sandbox link existed.
    from payments.models import PaymentLink
    import secrets
    from django.utils import timezone
    from datetime import timedelta

    link = PaymentLink.objects.create(
        company=company,
        token=secrets.token_urlsafe(16),
        sales_invoice=inv,
        customer=customer,
        amount=Decimal("1000"),
        status=PaymentLinkStatus.CREATED,
        expires_at=timezone.now() + timedelta(hours=1),
        provider="sandbox",
        provider_link_id="plink_stale_prod",
    )
    body = {
        "payment_id": "pay_prod_block",
        "amount": "1000.00",
        "fee": "0",
        "status": "CAPTURED",
        "payment_link_id": link.provider_link_id,
    }
    raw = json.dumps(body).encode()
    sig = _sandbox_sig(raw, company_id=company.id)
    from django.test import Client

    wh = Client().post(
        f"/api/v1/webhooks/payments/sandbox/?company_id={company.id}",
        data=raw,
        content_type="application/json",
        HTTP_X_SANDBOX_SIGNATURE=sig,
    )
    assert wh.status_code == 403
    link.refresh_from_db()
    assert link.status != PaymentLinkStatus.PAID


def test_public_pay_omits_customer_and_invoice(tenant_a):
    inv, customer = _complete_invoice(tenant_a)
    link = PaymentService.create_payment_link(
        company=tenant_a.company,
        amount=Decimal("1000"),
        sales_invoice=inv,
        customer=customer,
        provider="sandbox",
    )
    r = tenant_a.client.get(f"/api/v1/public/pay/{link.token}/")
    assert r.status_code == 200
    assert "customer_name" not in r.data
    assert "invoice_number" not in r.data
    assert "amount" in r.data
    assert "company_name" in r.data


def test_company_patch_cannot_set_gateway_test_mode(tenant_a):
    """BB-000259: gateway fields read-only on CompanySerializer."""
    r = tenant_a.client.patch(
        "/api/v1/company/",
        {"payment_gateway_test_mode": True, "payment_gateway_provider": "cashfree"},
        format="json",
    )
    assert r.status_code == 200
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.payment_gateway_test_mode is False
    assert (tenant_a.company.payment_gateway_provider or "razorpay") != "cashfree"
