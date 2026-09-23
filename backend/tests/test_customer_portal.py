"""COMP-003 customer portal magic link."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from masters.models import Customer
from payments.models import CustomerPortalToken, PaymentLink, PaymentLinkStatus
from sales.models import SalesInvoice
from tests.conftest import make_customer


def _enable(company):
    flags = dict(company.feature_flags or {})
    flags["ENABLE_CUSTOMER_PORTAL"] = True
    company.feature_flags = flags
    company.save(update_fields=["feature_flags"])


def _invoice(company, customer, number, grand="100"):
    return SalesInvoice.objects.create(
        company=company,
        customer=customer,
        number=number,
        status=SalesInvoice.Status.COMPLETED,
        invoice_date=timezone.localdate(),
        grand_total=Decimal(grand),
        taxable_total=Decimal(grand),
    )


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", FRONTEND_URL="http://localhost:5173")
@pytest.mark.django_db
def test_email_link_is_sent_and_reusable_until_expiry(tenant_a):
    from django.core.cache import cache
    cache.clear()
    client = APIClient()
    _enable(tenant_a.company)
    customer = make_customer(tenant_a.company, email="buyer@example.com")
    invoice = _invoice(tenant_a.company, customer, "CP-1")
    other = make_customer(tenant_a.company, name="Other", email="other@example.com")
    secret = _invoice(tenant_a.company, other, "CP-SECRET")

    unknown = client.post("/api/v1/public/customer-portal/request-link/", {"email": "nobody@example.com"}, format="json")
    assert unknown.status_code == 200
    assert "token" not in unknown.content.decode().lower()
    assert CustomerPortalToken.objects.count() == 0

    sent = client.post("/api/v1/public/customer-portal/request-link/", {"email": "buyer@example.com"}, format="json")
    assert sent.status_code == 200
    assert "portal/" not in sent.content.decode()
    assert len(mail.outbox) == 1
    token = CustomerPortalToken.objects.get().token
    assert token in mail.outbox[0].body

    first = client.get(f"/api/v1/public/customer-portal/{token}/")
    second = client.get(f"/api/v1/public/customer-portal/{token}/")
    assert first.status_code == 200
    assert second.status_code == 200
    ids = [row["id"] for row in second.data["invoices"]]
    assert invoice.id in ids
    assert secret.id not in ids

    pdf = client.get(f"/api/v1/public/customer-portal/{token}/invoices/{secret.id}/pdf/")
    assert pdf.status_code == 404

    row = CustomerPortalToken.objects.get()
    row.expires_at = timezone.now() - timedelta(minutes=1)
    row.save(update_fields=["expires_at"])
    assert client.get(f"/api/v1/public/customer-portal/{token}/").status_code == 404


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", FRONTEND_URL="http://localhost:5173")
@pytest.mark.django_db
def test_whatsapp_without_opt_in_does_not_leak_the_token(tenant_a):
    from django.core.cache import cache
    cache.clear()
    client = APIClient()
    _enable(tenant_a.company)
    make_customer(tenant_a.company, phone="9876543210", whatsapp_opt_in=False)
    resp = client.post("/api/v1/public/customer-portal/request-link/", {"phone": "9876543210"}, format="json")
    assert resp.status_code == 200
    assert "portal/" not in resp.content.decode()
    assert mail.outbox == []
    assert CustomerPortalToken.objects.count() == 1


@pytest.mark.django_db
def test_pay_path_uses_existing_payment_link(tenant_a):
    client = APIClient()
    _enable(tenant_a.company)
    customer = make_customer(tenant_a.company, email="pay@example.com")
    invoice = _invoice(tenant_a.company, customer, "CP-PAY")
    link = PaymentLink.objects.create(
        company=tenant_a.company,
        customer=customer,
        sales_invoice=invoice,
        token="paytok_existing_001",
        amount=Decimal("100"),
        status=PaymentLinkStatus.CREATED,
    )
    row = CustomerPortalToken.objects.create(
        company=tenant_a.company,
        customer=customer,
        token="portaltok_existing_001",
        requested_via=CustomerPortalToken.Channel.EMAIL,
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    body = client.get(f"/api/v1/public/customer-portal/{row.token}/").data
    assert body["invoices"][0]["pay_path"] == f"/pay/{link.token}"


@pytest.mark.django_db
def test_request_is_rate_limited():
    from django.core.cache import cache

    cache.clear()
    client = APIClient()
    statuses = [
        client.post("/api/v1/public/customer-portal/request-link/", {"email": f"n{i}@example.com"}, format="json").status_code
        for i in range(6)
    ]
    assert statuses[:5] == [200, 200, 200, 200, 200]
    assert statuses[5] == 429


@pytest.mark.django_db
def test_other_company_customer_is_not_visible(tenant_a, tenant_b):
    client = APIClient()
    _enable(tenant_a.company)
    _enable(tenant_b.company)
    a = make_customer(tenant_a.company, email="shared@example.com")
    b = Customer.objects.create(company=tenant_b.company, name="B", email="shared-b@example.com")
    invoice_b = _invoice(tenant_b.company, b, "CP-B")
    token = CustomerPortalToken.objects.create(
        company=tenant_a.company,
        customer=a,
        token="portaltok_scope_0001",
        requested_via=CustomerPortalToken.Channel.EMAIL,
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    body = client.get(f"/api/v1/public/customer-portal/{token.token}/").data
    assert invoice_b.id not in [row["id"] for row in body["invoices"]]
    assert client.get(f"/api/v1/public/customer-portal/{token.token}/invoices/{invoice_b.id}/pdf/").status_code == 404


@pytest.mark.django_db
def test_debug_echo_off_by_default_never_leaks_the_token(tenant_a, settings):
    """F1-011: PORTAL_DEBUG_ECHO defaults off — the existing GENERIC_SENT
    body assertions already prove no token leaks in the normal case; this
    pins the field name explicitly, matching the OTP_DEBUG_ECHO test pattern
    (test_auth.py) this mirrors.
    """
    settings.PORTAL_DEBUG_ECHO = False
    client = APIClient()
    _enable(tenant_a.company)
    customer = make_customer(tenant_a.company, email="noecho@example.com")
    resp = client.post(
        "/api/v1/public/customer-portal/request-link/", {"email": "noecho@example.com"}, format="json",
    )
    assert resp.status_code == 200
    assert "debug_token" not in resp.data
    assert CustomerPortalToken.objects.filter(customer=customer).exists()


@pytest.mark.django_db
def test_debug_echo_on_returns_the_real_usable_token(tenant_a, settings):
    settings.PORTAL_DEBUG_ECHO = True
    client = APIClient()
    _enable(tenant_a.company)
    make_customer(tenant_a.company, email="echo@example.com")
    resp = client.post(
        "/api/v1/public/customer-portal/request-link/", {"email": "echo@example.com"}, format="json",
    )
    assert resp.status_code == 200
    token = resp.data.get("debug_token")
    assert token
    row = CustomerPortalToken.objects.get(token=token)
    assert row.customer.email == "echo@example.com"
    # And the echoed token is genuinely usable, not a decoy.
    assert client.get(f"/api/v1/public/customer-portal/{token}/").status_code == 200


@pytest.mark.django_db
def test_debug_echo_stays_absent_on_no_match(tenant_a, settings):
    settings.PORTAL_DEBUG_ECHO = True
    client = APIClient()
    resp = client.post(
        "/api/v1/public/customer-portal/request-link/", {"email": "nobody-echo@example.com"}, format="json",
    )
    assert resp.status_code == 200
    assert "debug_token" not in resp.data


@pytest.mark.django_db
def test_pay_view_happy_path_creates_a_link_when_none_exists(tenant_a):
    client = APIClient()
    _enable(tenant_a.company)
    # No gateway credentials configured in this fixture; test_mode routes
    # PaymentService.create_payment_link through the sandbox provider
    # instead of requiring real Razorpay creds (test/dev/local only).
    tenant_a.company.payment_gateway_test_mode = True
    tenant_a.company.save(update_fields=["payment_gateway_test_mode"])
    customer = make_customer(tenant_a.company, email="paynew@example.com")
    invoice = _invoice(tenant_a.company, customer, "CP-PAYNEW")
    token = CustomerPortalToken.objects.create(
        company=tenant_a.company,
        customer=customer,
        token="portaltok_paynew_0001",
        requested_via=CustomerPortalToken.Channel.EMAIL,
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    resp = client.post(f"/api/v1/public/customer-portal/{token.token}/invoices/{invoice.id}/pay/")
    assert resp.status_code == 200
    assert resp.data["pay_path"].startswith("/pay/")
    assert PaymentLink.objects.filter(company=tenant_a.company, sales_invoice=invoice).count() == 1


@pytest.mark.django_db
def test_pay_view_is_idor_safe_against_another_customers_invoice(tenant_a):
    """F1-009 (top test gap from the COMP-003 review): a valid token for
    customer A must not be able to pay an invoice belonging to customer B —
    the one mutating endpoint on this public surface had zero coverage.
    """
    client = APIClient()
    _enable(tenant_a.company)
    customer_a = make_customer(tenant_a.company, email="idor-a@example.com")
    customer_b = make_customer(tenant_a.company, name="B", email="idor-b@example.com")
    invoice_b = _invoice(tenant_a.company, customer_b, "CP-IDOR-B")
    token = CustomerPortalToken.objects.create(
        company=tenant_a.company,
        customer=customer_a,
        token="portaltok_idor_0001",
        requested_via=CustomerPortalToken.Channel.EMAIL,
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    resp = client.post(f"/api/v1/public/customer-portal/{token.token}/invoices/{invoice_b.id}/pay/")
    assert resp.status_code == 404
    assert PaymentLink.objects.filter(company=tenant_a.company, sales_invoice=invoice_b).count() == 0


@pytest.mark.django_db
def test_pay_view_is_idor_safe_across_companies(tenant_a, tenant_b):
    client = APIClient()
    _enable(tenant_a.company)
    _enable(tenant_b.company)
    customer_a = make_customer(tenant_a.company, email="idor-x@example.com")
    customer_b = Customer.objects.create(company=tenant_b.company, name="Bx", email="idor-y@example.com")
    invoice_b = _invoice(tenant_b.company, customer_b, "CP-IDOR-X")
    token = CustomerPortalToken.objects.create(
        company=tenant_a.company,
        customer=customer_a,
        token="portaltok_idor_0002",
        requested_via=CustomerPortalToken.Channel.EMAIL,
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    resp = client.post(f"/api/v1/public/customer-portal/{token.token}/invoices/{invoice_b.id}/pay/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_pay_view_rejects_when_nothing_outstanding(tenant_a):
    client = APIClient()
    _enable(tenant_a.company)
    customer = make_customer(tenant_a.company, email="paid@example.com")
    invoice = _invoice(tenant_a.company, customer, "CP-PAID")
    from payments.models import CustomerReceipt, PaymentAllocation

    receipt = CustomerReceipt.objects.create(
        company=tenant_a.company, customer=customer,
        amount=Decimal("100"), receipt_date=timezone.localdate(),
    )
    PaymentAllocation.objects.create(
        company=tenant_a.company, receipt=receipt, sales_invoice=invoice, amount=Decimal("100"),
    )
    token = CustomerPortalToken.objects.create(
        company=tenant_a.company,
        customer=customer,
        token="portaltok_paid_0001",
        requested_via=CustomerPortalToken.Channel.EMAIL,
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    resp = client.post(f"/api/v1/public/customer-portal/{token.token}/invoices/{invoice.id}/pay/")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_default_off_flag_short_circuits_request_and_read(tenant_a):
    """No test previously confirmed the default-off behavior (every existing
    test calls _enable() first)."""
    from django.core.cache import cache

    cache.clear()
    client = APIClient()
    customer = make_customer(tenant_a.company, email="flagoff@example.com")
    resp = client.post(
        "/api/v1/public/customer-portal/request-link/", {"email": "flagoff@example.com"}, format="json",
    )
    assert resp.status_code == 200
    # flag_enabled() is checked before token creation, so a matched customer
    # under a flag-off company gets no token at all.
    assert CustomerPortalToken.objects.filter(customer=customer).count() == 0
    # And a token that somehow existed anyway (e.g. flag flipped off after
    # issuance) must not be servable by _load_token's own flag check.
    stale = CustomerPortalToken.objects.create(
        company=tenant_a.company, customer=customer, token="portaltok_stale_0001",
        requested_via=CustomerPortalToken.Channel.EMAIL, expires_at=timezone.now() + timedelta(minutes=15),
    )
    assert client.get(f"/api/v1/public/customer-portal/{stale.token}/").status_code == 404


@pytest.mark.django_db
def test_whatsapp_opt_in_false_never_attempts_a_network_send(tenant_a, monkeypatch):
    """Strengthens test_whatsapp_without_opt_in_does_not_leak_the_token: that
    test only asserted an irrelevant email outbox was empty. This mocks the
    actual WhatsApp send function and proves it is never called when
    whatsapp_opt_in is False, so a regression moving the opt-in check after
    the network call would be caught.
    """
    from django.core.cache import cache

    cache.clear()
    client = APIClient()
    _enable(tenant_a.company)
    make_customer(tenant_a.company, phone="9876500000", whatsapp_opt_in=False)

    def boom(*_a, **_k):
        raise AssertionError("WhatsApp send must not be attempted without opt-in")

    monkeypatch.setattr("core.services.whatsapp.send_whatsapp_template", boom)
    resp = client.post(
        "/api/v1/public/customer-portal/request-link/", {"phone": "9876500000"}, format="json",
    )
    assert resp.status_code == 200


@pytest.mark.django_db
def test_whatsapp_opt_in_true_sends_via_the_template(tenant_a, monkeypatch):
    from django.core.cache import cache

    cache.clear()
    client = APIClient()
    _enable(tenant_a.company)
    make_customer(tenant_a.company, phone="9876511111", whatsapp_opt_in=True)
    calls = []

    class _Result:
        mode = "cloud"

    def fake_send(phone, template, args, *, company, allow_cloud):
        calls.append((phone, template, args))
        return _Result()

    monkeypatch.setattr("core.services.whatsapp.send_whatsapp_template", fake_send)
    resp = client.post(
        "/api/v1/public/customer-portal/request-link/", {"phone": "9876511111"}, format="json",
    )
    assert resp.status_code == 200
    assert len(calls) == 1
    assert calls[0][1] == "invoice_share"


@pytest.mark.django_db
def test_own_invoice_pdf_is_returned(tenant_a, monkeypatch):
    from django.core.cache import cache
    cache.clear()
    _enable(tenant_a.company)
    customer = make_customer(tenant_a.company, email="pdf@example.com")
    invoice = _invoice(tenant_a.company, customer, "CP-PDF")
    token = CustomerPortalToken.objects.create(
        company=tenant_a.company,
        customer=customer,
        token="portaltok_pdf_0001",
        requested_via=CustomerPortalToken.Channel.EMAIL,
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    monkeypatch.setattr(
        "sales.pdf.render_gst_tax_invoice",
        lambda invoice, copy="ORIGINAL": b"%PDF-1.4 portal",
    )
    client = APIClient()
    response = client.get(f"/api/v1/public/customer-portal/{token.token}/invoices/{invoice.id}/pdf/")
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert "CP-PDF" in response["Content-Disposition"]
