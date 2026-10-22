"""WP-C2: every public / pre-login endpoint must work under FORCE RLS as the real app role.

These endpoints run before the middleware knows a tenant (sign-in, OTP, password reset,
invite accept, MFA verify, customer portal, public invoice / quotation / receipt links,
the public pay page and payment webhooks). As a superuser they always work; as the
NOSUPERUSER NOBYPASSRLS app role, any read or write that forgets to scope itself to the
row's company fails with an RLS error or silently finds nothing. This is the bug class
found on staging with the sign-in audit row (tests/test_audit_company_scope.py).

Setup data is built as the superuser; only the HTTP call runs inside ``app_role()``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal

import pytest
from django.core import mail
from django.core.cache import cache
from django.test import Client, override_settings
from rest_framework.test import APIClient

from core.models import AuditEvent
from core.rls import rls_bypass
from tests.conftest import make_customer
from tests.rls_helpers import app_role, needs_pg

pytestmark = [
    needs_pg,
    pytest.mark.postgres,
    pytest.mark.django_db(transaction=True),
]

PASSWORD = "StrongPass123!"
RLS_ON = override_settings(
    POSTGRES_RLS_ENABLED=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    FRONTEND_URL="http://localhost:5173",
)


@pytest.fixture(autouse=True)
def _rls_on():
    with RLS_ON:
        cache.clear()
        yield


def test_password_login_writes_its_audit_row(tenant_a):
    with app_role():
        resp = APIClient().post(
            "/api/v1/auth/login/", {"email": tenant_a.owner.email, "password": PASSWORD}, format="json"
        )
    assert resp.status_code == 200, resp.content
    with rls_bypass():
        assert AuditEvent.objects.filter(user=tenant_a.owner, action="LOGIN").exists()


def test_phone_otp_request_and_verify(tenant_a, monkeypatch):
    monkeypatch.setattr("accounts.views.secrets.randbelow", lambda n: 123456)
    monkeypatch.setattr("django.conf.settings.OTP_ENABLED", True)
    monkeypatch.setattr("django.conf.settings.OTP_DEBUG_ECHO", False)
    monkeypatch.setattr("django.conf.settings.SMS_PROVIDER", "console")
    client = APIClient()
    with app_role():
        asked = client.post("/api/v1/auth/otp/request/", {"phone": tenant_a.owner.phone}, format="json")
        ok = client.post("/api/v1/auth/otp/verify/", {"phone": tenant_a.owner.phone, "code": "123456"}, format="json")
    assert asked.status_code == 200, asked.content
    assert ok.status_code == 200, ok.content
    assert "access" in ok.data


def test_password_reset_request_and_confirm(tenant_a):
    client = APIClient()
    with app_role():
        asked = client.post("/api/v1/auth/password/reset/", {"email": tenant_a.owner.email}, format="json")
    assert asked.status_code == 200, asked.content
    token = mail.outbox[-1].body.split("token=")[1].split()[0]
    with app_role():
        done = client.post(
            "/api/v1/auth/password/reset/confirm/", {"token": token, "new_password": "NewStrongPass123!"},
            format="json",
        )
    assert done.status_code == 200, done.content


def test_invite_accept(tenant_a):
    invited = tenant_a.client.post(
        "/api/v1/company/users/", {"email": "rls.invite@alpha.test", "role": "SALES_STAFF"}, format="json"
    )
    assert invited.status_code == 201, invited.content
    with app_role():
        accept = APIClient().post(
            "/api/v1/auth/invite/accept/",
            {"token": invited.data["invite_token"], "new_password": "InvitePass123!"},
            format="json",
        )
    assert accept.status_code == 200, accept.content


def test_mfa_login_verify(tenant_a):
    import time

    from accounts import mfa
    from accounts.models import UserMfa

    c = tenant_a.client
    assert c.post("/api/v1/auth/mfa/setup/", {"password": PASSWORD}, format="json").status_code == 200
    rec = UserMfa.objects.get(user=tenant_a.owner)
    code = mfa.totp_at(mfa.decrypt_secret(rec.secret_enc))
    assert c.post("/api/v1/auth/mfa/confirm/", {"code": code, "password": PASSWORD}, format="json").status_code == 200
    cache.clear()
    client = APIClient()
    with app_role():
        first = client.post("/api/v1/auth/login/", {"email": tenant_a.owner.email, "password": PASSWORD}, format="json")
        assert first.status_code == 200, first.content
        token = first.data["mfa_token"]
        rec.refresh_from_db()
        nxt = mfa.totp_at(mfa.decrypt_secret(rec.secret_enc), time.time() + 30)
        done = client.post("/api/v1/auth/mfa/verify/", {"mfa_token": token, "code": nxt}, format="json")
    assert done.status_code == 200, done.content


def _portal_company(tenant):
    company = tenant.company
    company.feature_flags = {**(company.feature_flags or {}), "ENABLE_CUSTOMER_PORTAL": True}
    company.save(update_fields=["feature_flags"])
    return make_customer(company, name="Portal Buyer", email="buyer@example.com")


def test_customer_portal_request_and_read(tenant_a):
    from payments.models import CustomerPortalToken

    _portal_company(tenant_a)
    client = APIClient()
    with app_role():
        sent = client.post(
            "/api/v1/public/customer-portal/request-link/", {"email": "buyer@example.com"}, format="json"
        )
    assert sent.status_code == 200, sent.content
    with rls_bypass():
        token = CustomerPortalToken.objects.filter(company=tenant_a.company).latest("id").token
    with app_role():
        page = client.get(f"/api/v1/public/customer-portal/{token}/")
    assert page.status_code == 200, page.content


def _completed_invoice(tenant):
    from tests.test_phase3_payments import _complete_invoice

    return _complete_invoice(tenant)


def test_public_invoice_page_pdf_and_pay(tenant_a):
    inv, _customer = _completed_invoice(tenant_a)
    minted = tenant_a.client.post(f"/api/v1/sales/invoices/{inv.id}/public-link/")
    assert minted.status_code in (200, 201), minted.content
    token = minted.data["url"].rsplit("/", 1)[-1]
    anon = APIClient()
    with app_role():
        page = anon.get(f"/api/v1/public/invoices/{token}/")
        pdf = anon.get(f"/api/v1/public/invoices/{token}/pdf/")
        pay = anon.post(f"/api/v1/public/invoices/{token}/pay/")
    assert page.status_code == 200, page.content
    assert pdf.status_code == 200
    assert pay.status_code < 500, pay.content


def test_public_quotation_page_and_pdf(tenant_a):
    from tests.test_quotation_closure_cross import _quote

    tenant_a.company.feature_flags = {**(tenant_a.company.feature_flags or {}), "QUOTE_LIFECYCLE": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    q = _quote(tenant_a)
    shared = tenant_a.client.post(f"/api/v1/sales/quotations/{q['id']}/share/", {"channel": "whatsapp"}, format="json")
    assert shared.status_code == 200, shared.content
    token = shared.data["url"].rsplit("/", 1)[-1]
    anon = APIClient()
    with app_role():
        page = anon.get(f"/api/v1/public/quotations/{token}/")
        pdf = anon.get(f"/api/v1/public/quotations/{token}/pdf/")
    assert page.status_code == 200, page.content
    assert pdf.status_code == 200


def test_public_receipt_voucher(tenant_a):
    from payments.receipt_share import mint_voucher_token
    from tests.test_money_in_phase2 import _receipt

    receipt = _receipt(tenant_a, make_customer(tenant_a.company), "100", "CASH")
    token = mint_voucher_token(receipt)
    with app_role():
        resp = Client().get(f"/api/v1/public/receipt-voucher/{token}/")
    assert resp.status_code == 200, resp.content[:200]


@override_settings(SANDBOX_WEBHOOK_SECRET="test-sandbox-webhook-secret", DJANGO_ENV="test")
def test_public_pay_page_and_signed_payment_webhook(tenant_a):
    from payments.gateway import sandbox_webhook_secret_for_company
    from payments.models import PaymentLinkStatus
    from payments.services import PaymentService

    inv, customer = _completed_invoice(tenant_a)
    link = PaymentService.create_payment_link(
        company=tenant_a.company, amount=Decimal("1000"), sales_invoice=inv, customer=customer,
        provider="sandbox", public_base_url="http://testserver",
    )
    raw = json.dumps({
        "payment_id": "pay_rls", "amount": "100000", "fee": "0", "status": "CAPTURED",
        "payment_link_id": link.provider_link_id,
    }).encode()
    key = sandbox_webhook_secret_for_company(tenant_a.company.id)
    sig = hmac.new(key.encode(), raw, hashlib.sha256).hexdigest()
    with app_role():
        page = Client().get(f"/api/v1/public/pay/{link.token}/")
        hook = Client().post(
            f"/api/v1/webhooks/payments/sandbox/?company_id={tenant_a.company.id}",
            data=raw, content_type="application/json", HTTP_X_SANDBOX_SIGNATURE=sig,
        )
    assert page.status_code == 200, page.content[:200]
    assert hook.status_code == 200, hook.content[:200]
    with rls_bypass():
        link.refresh_from_db()
    assert link.status == PaymentLinkStatus.PAID


def test_health_csrf_and_flags_need_no_tenant():
    with app_role():
        assert APIClient().get("/api/v1/health/").status_code == 200
        assert APIClient().get("/api/v1/auth/csrf/").status_code == 200
