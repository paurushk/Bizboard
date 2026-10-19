"""SET-05: Money-In rules are their own endpoint; gateway keys can be checked and removed."""

from types import SimpleNamespace

import pytest
import requests
from django.core.cache import cache

from core.models import AuditEvent
from payments.gateway import CashfreeGateway, PayUGateway, RazorpayAdapter, credential_hint_and_mode

GATEWAY = "/api/v1/payments/gateway-settings/"
VERIFY = "/api/v1/payments/gateway-settings/verify/"
RULES = "/api/v1/payments/money-in-rules/"
RZP = {"key_id": "rzp_test_ABCDEF123456", "key_secret": "s3cret-value"}


@pytest.fixture(autouse=True)
def _fresh_cache():
    cache.clear()
    yield
    cache.clear()


def _fake_get(status=200, exc=None):
    calls = []

    def fake(url, **kwargs):
        calls.append((url, kwargs))
        if exc:
            raise exc
        return SimpleNamespace(status_code=status)

    fake.calls = calls
    return fake


# ---- Money-In rules ---------------------------------------------------------------------------


def test_rules_endpoint_reads_and_saves_only_the_rules(tenant_a):
    tenant_a.client.patch(GATEWAY, {"provider": "razorpay", "credentials": RZP}, format="json")
    before = tenant_a.client.get(GATEWAY).data
    r = tenant_a.client.patch(
        RULES,
        {"cheque_allocation_on_clearance": True, "cash_269st_mode": "block",
         "advance_gst_treatment": "services", "advance_gst_default_rate": "18"},
        format="json",
    )
    assert r.status_code == 200, r.data
    assert r.data["cash_269st_mode"] == "block" and r.data["advance_gst_default_rate"] == "18.00"
    assert tenant_a.client.get(RULES).data["cheque_allocation_on_clearance"] is True
    after = tenant_a.client.get(GATEWAY).data
    for key in ("provider", "credentials_configured", "credentials_hint", "credentials_verified"):
        assert after[key] == before[key]


def test_rules_endpoint_validates_and_is_owner_only(tenant_a):
    for bad in ({"cash_269st_mode": "maybe"}, {"advance_gst_treatment": "wine"}, {"advance_gst_default_rate": "99"},
                {"advance_gst_default_rate": "abc"}):
        assert tenant_a.client.patch(RULES, bad, format="json").status_code == 400, bad
    assert tenant_a.staff_client.get(RULES).status_code == 403
    assert tenant_a.staff_client.patch(RULES, {"cash_269st_mode": "off"}, format="json").status_code == 403


def test_saving_the_gateway_does_not_change_the_rules(tenant_a):
    tenant_a.client.patch(RULES, {"cash_269st_mode": "block", "require_payment_reference": True}, format="json")
    tenant_a.client.patch(GATEWAY, {"provider": "razorpay", "credentials": RZP}, format="json")
    rules = tenant_a.client.get(RULES).data
    assert rules["cash_269st_mode"] == "block" and rules["require_payment_reference"] is True


def test_rules_save_is_audited_with_the_fields_it_changed(tenant_a):
    tenant_a.client.patch(RULES, {"cash_269st_mode": "warn"}, format="json")
    event = AuditEvent.objects.filter(company=tenant_a.company, entity_type="MoneyInRules").latest("id")
    assert event.metadata["fields"] == ["cash_269st_mode"]


def test_old_clients_can_still_save_rules_through_the_gateway_endpoint(tenant_a):
    r = tenant_a.client.patch(GATEWAY, {"cash_269st_mode": "block"}, format="json")
    assert r.status_code == 200 and r.data["cash_269st_mode"] == "block"


# ---- keys: hint, mode, never the secret --------------------------------------------------------


def test_saved_keys_show_a_hint_and_mode_but_never_the_secret(tenant_a):
    r = tenant_a.client.patch(GATEWAY, {"provider": "razorpay", "credentials": RZP}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["credentials_configured"] is True
    assert r.data["credentials_hint"] == "3456"
    assert r.data["credentials_mode"] == "test"
    assert r.data["credentials_verified"] is False
    assert "s3cret-value" not in str(r.data)


def test_key_mode_comes_from_the_razorpay_key_prefix():
    assert credential_hint_and_mode("razorpay", {"key_id": "rzp_live_XYZ9876"}) == ("9876", "live")
    assert credential_hint_and_mode("razorpay", {"key_id": "weird"}) == ("eird", "unknown")
    assert credential_hint_and_mode("cashfree", {"app_id": "CF12345678"}) == ("5678", "unknown")
    assert credential_hint_and_mode("razorpay", {}) == ("", "unknown")


def test_blank_key_fields_do_not_wipe_saved_keys(tenant_a):
    tenant_a.client.patch(GATEWAY, {"credentials": RZP}, format="json")
    r = tenant_a.client.patch(GATEWAY, {"credentials": {"key_id": "", "key_secret": ""}}, format="json")
    assert r.data["credentials_configured"] is True and r.data["credentials_hint"] == "3456"


def test_test_mode_switch_is_only_offered_where_the_server_allows_it(tenant_a):
    assert tenant_a.client.get(GATEWAY).data["test_mode_available"] is True  # test settings are not production


# ---- checking keys ----------------------------------------------------------------------------


def test_razorpay_accepts_good_keys_and_the_result_is_remembered(tenant_a, monkeypatch):
    tenant_a.client.patch(GATEWAY, {"provider": "razorpay", "credentials": RZP}, format="json")
    fake = _fake_get(200)
    monkeypatch.setattr(requests, "get", fake)
    r = tenant_a.client.post(VERIFY, {}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["status"] == "valid" and r.data["verified_at"]
    url, kwargs = fake.calls[0]
    assert url == "https://api.razorpay.com/v1/payments" and kwargs["params"] == {"count": 1}
    assert kwargs["auth"] == (RZP["key_id"], RZP["key_secret"])
    state = tenant_a.client.get(GATEWAY).data
    assert state["credentials_verified"] is True and state["credentials_verified_at"]


def test_changing_the_keys_clears_the_verified_mark(tenant_a, monkeypatch):
    tenant_a.client.patch(GATEWAY, {"credentials": RZP}, format="json")
    monkeypatch.setattr(requests, "get", _fake_get(200))
    tenant_a.client.post(VERIFY, {}, format="json")
    assert tenant_a.client.get(GATEWAY).data["credentials_verified"] is True
    r = tenant_a.client.patch(GATEWAY, {"credentials": {"key_secret": "another-secret"}}, format="json")
    assert r.data["credentials_verified"] is False


def test_verified_mark_does_not_carry_over_to_another_provider(tenant_a, monkeypatch):
    tenant_a.client.patch(GATEWAY, {"credentials": RZP}, format="json")
    monkeypatch.setattr(requests, "get", _fake_get(200))
    tenant_a.client.post(VERIFY, {}, format="json")
    r = tenant_a.client.patch(GATEWAY, {"provider": "sandbox"}, format="json")
    assert r.data["credentials_verified"] is False


def test_provider_refusal_is_reported_and_clears_an_older_mark(tenant_a, monkeypatch):
    tenant_a.client.patch(GATEWAY, {"credentials": RZP}, format="json")
    monkeypatch.setattr(requests, "get", _fake_get(200))
    tenant_a.client.post(VERIFY, {}, format="json")
    cache.clear()
    monkeypatch.setattr(requests, "get", _fake_get(401))
    r = tenant_a.client.post(VERIFY, {}, format="json")
    assert r.data["status"] == "invalid" and r.data["verified_at"] is None
    assert tenant_a.client.get(GATEWAY).data["credentials_verified"] is False


@pytest.mark.parametrize("fake", [_fake_get(503), _fake_get(exc=requests.ConnectionError("down"))])
def test_an_unanswered_check_changes_nothing(tenant_a, monkeypatch, fake):
    tenant_a.client.patch(GATEWAY, {"credentials": RZP}, format="json")
    monkeypatch.setattr(requests, "get", fake)
    r = tenant_a.client.post(VERIFY, {}, format="json")
    assert r.data["status"] == "unreachable"
    assert tenant_a.client.get(GATEWAY).data["credentials_verified"] is False


def test_checking_without_saved_keys_says_so(tenant_a, monkeypatch):
    fake = _fake_get(200)
    monkeypatch.setattr(requests, "get", fake)
    r = tenant_a.client.post(VERIFY, {}, format="json")
    assert r.data["status"] == "missing" and fake.calls == []


def test_checks_are_rate_limited_owner_only_and_audited(tenant_a, monkeypatch):
    tenant_a.client.patch(GATEWAY, {"credentials": RZP}, format="json")
    monkeypatch.setattr(requests, "get", _fake_get(200))
    assert tenant_a.client.post(VERIFY, {}, format="json").status_code == 200
    assert tenant_a.client.post(VERIFY, {}, format="json").status_code == 400
    assert tenant_a.staff_client.post(VERIFY, {}, format="json").status_code == 403
    assert AuditEvent.objects.filter(company=tenant_a.company, action="payment_gateway.verify_keys").count() == 1


def test_cashfree_and_payu_checks():
    def with_get(fake, fn):
        original = requests.get
        requests.get = fake
        try:
            return fn()
        finally:
            requests.get = original

    gw = CashfreeGateway({"app_id": "CF1", "secret_key": "sec"})
    assert with_get(_fake_get(404), gw.verify_credentials).status == "valid"
    assert with_get(_fake_get(401), gw.verify_credentials).status == "invalid"
    assert with_get(_fake_get(500), gw.verify_credentials).status == "unreachable"
    assert CashfreeGateway({}).verify_credentials().status == "missing"
    fake = _fake_get(404)
    with_get(fake, gw.verify_credentials)
    assert fake.calls[0][1]["headers"]["x-client-id"] == "CF1"
    assert PayUGateway({"merchant_key": "k", "merchant_salt": "s"}).verify_credentials().status == "unsupported"
    assert PayUGateway({}).verify_credentials().status == "missing"
    assert RazorpayAdapter({}).verify_credentials().status == "missing"


def test_sandbox_needs_no_keys(tenant_a):
    tenant_a.client.patch(GATEWAY, {"provider": "sandbox"}, format="json")
    assert tenant_a.client.post(VERIFY, {}, format="json").data["status"] == "valid"


# ---- removing keys ----------------------------------------------------------------------------


def test_removing_the_keys_clears_them_and_is_audited(tenant_a, monkeypatch):
    tenant_a.client.patch(GATEWAY, {"credentials": RZP}, format="json")
    monkeypatch.setattr(requests, "get", _fake_get(200))
    tenant_a.client.post(VERIFY, {}, format="json")
    r = tenant_a.client.patch(GATEWAY, {"clear_credentials": True}, format="json")
    assert r.status_code == 200
    assert r.data["credentials_configured"] is False and r.data["credentials_hint"] == ""
    assert r.data["credentials_verified"] is False
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.payment_gateway_credentials_encrypted == ""
    assert AuditEvent.objects.filter(
        company=tenant_a.company, entity_type="PaymentGatewaySettings", description="Payment keys removed"
    ).exists()
    assert tenant_a.staff_client.patch(GATEWAY, {"clear_credentials": True}, format="json").status_code == 403


# ---- payment links need keys the provider has not refused (SET-05) ----------------------------


def _link_ready_invoice(tenant):
    from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

    product = make_product(tenant.company, sku="LINK-1", hsn_code="1001")
    add_stock(tenant, product, "10")
    draft = create_draft_invoice(
        tenant,
        make_customer(tenant.company),
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    assert tenant.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200
    return draft["id"]


def _make_link(tenant, invoice_id):
    return tenant.client.post("/api/v1/payments/links/", {"sales_invoice": invoice_id}, format="json")


def test_a_payment_link_is_refused_when_the_provider_refuses_the_keys(tenant_a, monkeypatch):
    tenant_a.client.patch(GATEWAY, {"provider": "razorpay", "credentials": RZP}, format="json")
    invoice = _link_ready_invoice(tenant_a)
    posted = []
    monkeypatch.setattr("payments.gateway._provider_post", lambda *a, **k: posted.append(a) or None)
    monkeypatch.setattr(requests, "get", _fake_get(401))
    r = _make_link(tenant_a, invoice)
    assert r.status_code == 400, r.data
    assert "did not accept" in str(r.data)
    assert posted == []  # nothing was sent to create a link


def test_keys_the_provider_accepted_once_are_not_checked_again(tenant_a, monkeypatch):
    tenant_a.client.patch(GATEWAY, {"provider": "razorpay", "credentials": RZP}, format="json")
    fake = _fake_get(200)
    monkeypatch.setattr(requests, "get", fake)
    tenant_a.client.post(VERIFY, {}, format="json")
    assert len(fake.calls) == 1
    from payments.services import PaymentService

    tenant_a.company.refresh_from_db()
    PaymentService.assert_gateway_keys_accepted(tenant_a.company)
    PaymentService.assert_gateway_keys_accepted(tenant_a.company)
    assert len(fake.calls) == 1


def test_unchecked_keys_are_checked_on_first_use_and_remembered(tenant_a, monkeypatch):
    from payments.services import PaymentService

    tenant_a.client.patch(GATEWAY, {"provider": "razorpay", "credentials": RZP}, format="json")
    fake = _fake_get(200)
    monkeypatch.setattr(requests, "get", fake)
    tenant_a.company.refresh_from_db()
    PaymentService.assert_gateway_keys_accepted(tenant_a.company)
    assert len(fake.calls) == 1
    assert tenant_a.client.get(GATEWAY).data["credentials_verified"] is True
    tenant_a.company.refresh_from_db()
    PaymentService.assert_gateway_keys_accepted(tenant_a.company)
    assert len(fake.calls) == 1


@pytest.mark.parametrize("fake", [_fake_get(503), _fake_get(exc=requests.ConnectionError("down"))])
def test_a_check_that_could_not_finish_does_not_block_a_link(tenant_a, monkeypatch, fake):
    from payments.services import PaymentService

    tenant_a.client.patch(GATEWAY, {"provider": "razorpay", "credentials": RZP}, format="json")
    monkeypatch.setattr(requests, "get", fake)
    tenant_a.company.refresh_from_db()
    PaymentService.assert_gateway_keys_accepted(tenant_a.company)  # no exception
    assert tenant_a.client.get(GATEWAY).data["credentials_verified"] is False


def test_sandbox_and_providers_without_a_check_are_never_blocked(tenant_a, monkeypatch):
    from payments.services import PaymentService

    fake = _fake_get(401)
    monkeypatch.setattr(requests, "get", fake)
    tenant_a.client.patch(GATEWAY, {"provider": "sandbox"}, format="json")
    tenant_a.company.refresh_from_db()
    PaymentService.assert_gateway_keys_accepted(tenant_a.company)
    PaymentService.assert_gateway_keys_accepted(tenant_a.company, "payu")
    assert fake.calls == []
