import pytest
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from core.models import AuditEvent

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_register_creates_user_company_and_owner_membership():
    client = APIClient()
    resp = client.post("/api/v1/auth/register/", {
        "company_name": "Fresh Mart",
        "email": "boss@freshmart.test",
        "password": "StrongPass123!",
        "state": "Karnataka",
    }, format="json")
    assert resp.status_code == 200
    # BB-000349 / BB-000389: body never exposes tokens/ids; register sets no cookies.
    assert resp.data["access"] is None
    assert resp.data["user_id"] is None
    assert resp.data["company_id"] is None
    assert "refresh" not in resp.data
    assert resp.data["detail"]
    from django.conf import settings
    assert settings.JWT_REFRESH_COOKIE_NAME not in resp.cookies
    assert settings.JWT_ACCESS_COOKIE_NAME not in resp.cookies

    login = client.post("/api/v1/auth/login/", {
        "email": "boss@freshmart.test",
        "password": "StrongPass123!",
    }, format="json")
    assert login.status_code == 200
    auth_client = APIClient()
    auth_client.cookies = login.cookies
    me = auth_client.get("/api/v1/auth/me/")
    assert me.status_code == 200
    assert me.data["role"] == "OWNER"
    assert me.data["company"]["name"] == "Fresh Mart"
    assert me.data["company"]["registration_type"] == "UNREGISTERED"
    assert me.data["company"].get("gstin", "") in ("", None)


def test_register_copies_phone_to_company():
    """E2E3-006 — register mobile is copied onto Company.phone."""
    from accounts.models import Company, User

    client = APIClient()
    resp = client.post("/api/v1/auth/register/", {
        "company_name": "Phone Mart",
        "email": "phoneboss@phonemart.test",
        "password": "StrongPass123!",
        "state": "Maharashtra",
        "phone": "9876543210",
    }, format="json")
    assert resp.status_code == 200
    user = User.objects.get(email="phoneboss@phonemart.test")
    company = Company.objects.get(memberships__user=user)
    assert company.phone == "9876543210"


def test_register_existing_email_same_shape_no_tokens():
    """BB-000349 — duplicate and new share identical body shape (all null tokens/ids)."""
    client = APIClient()
    first = client.post("/api/v1/auth/register/", {
        "company_name": "Fresh Mart",
        "email": "dup@freshmart.test",
        "password": "StrongPass123!",
        "state": "Karnataka",
    }, format="json")
    assert first.status_code == 200
    assert first.data["access"] is None

    again = client.post("/api/v1/auth/register/", {
        "company_name": "Other Co",
        "email": "dup@freshmart.test",
        "password": "StrongPass123!",
        "state": "Karnataka",
    }, format="json")
    assert again.status_code == 200
    assert set(again.data.keys()) == set(first.data.keys())
    assert again.data["access"] is None
    assert again.data["user_id"] is None
    assert again.data["company_id"] is None
    assert again.data["detail"] == first.data["detail"]


def test_login_returns_tokens_and_audits(tenant_a):
    client = APIClient()
    resp = client.post("/api/v1/auth/login/", {
        "email": tenant_a.owner.email, "password": "StrongPass123!",
    }, format="json")
    assert resp.status_code == 200
    assert "access" in resp.data
    assert "refresh" not in resp.data
    assert resp.data["user"]["email"] == tenant_a.owner.email
    assert resp.data["user"]["role"] == "OWNER"
    assert resp.data["user"]["company_id"] == tenant_a.company.id
    assert AuditEvent.objects.filter(user=tenant_a.owner, action="LOGIN").exists()
    # Refresh is httpOnly cookie only (BB-000257).
    from django.conf import settings
    assert settings.JWT_REFRESH_COOKIE_NAME in resp.cookies


def test_login_wrong_password_rejected(tenant_a):
    client = APIClient()
    resp = client.post("/api/v1/auth/login/", {
        "email": tenant_a.owner.email, "password": "wrong",
    }, format="json")
    assert resp.status_code == 401


def test_otp_login_flow(tenant_a, monkeypatch):
    from accounts.models import OtpChallenge
    from accounts.otp_utils import hash_otp

    # Console SMS + OTP_ENABLED (not OTP_DEBUG_ECHO) — BB-000332.
    monkeypatch.setattr("accounts.views.secrets.randbelow", lambda n: 123456)
    monkeypatch.setattr("django.conf.settings.OTP_ENABLED", True)
    monkeypatch.setattr("django.conf.settings.SMS_PROVIDER", "console")

    client = APIClient()
    resp = client.post("/api/v1/auth/otp/request/", {"phone": tenant_a.owner.phone}, format="json")
    assert resp.status_code == 200
    assert "debug_code" not in resp.data

    from accounts.otp_utils import phone_lookup_values

    challenge = OtpChallenge.objects.filter(
        phone__in=phone_lookup_values(tenant_a.owner.phone),
    ).latest("created_at")
    assert challenge.code == hash_otp("123456")
    assert challenge.code != "123456"

    bad = client.post("/api/v1/auth/otp/verify/", {"phone": tenant_a.owner.phone, "code": "000000"}, format="json")
    assert bad.status_code == 400

    ok = client.post("/api/v1/auth/otp/verify/", {"phone": tenant_a.owner.phone, "code": "123456"}, format="json")
    assert ok.status_code == 200
    assert "access" in ok.data
    assert "refresh" not in ok.data
    assert ok.data["user"]["email"] == tenant_a.owner.email


def test_health_is_public():
    resp = APIClient().get("/api/v1/health/")
    assert resp.status_code == 200
    assert resp.data["status"] in ("ok", "degraded")
    assert resp.data["version"] == "v1"
    # BB-000358: liveness omits topology keys.
    assert "db" not in resp.data
    assert "celery" not in resp.data

    ready = APIClient().get("/api/v1/health/?ready=1")
    assert ready.status_code in (200, 503)
    # BB-000626: unauthenticated ready omits topology keys.
    assert "db" not in ready.data
    assert "cache" not in ready.data
    assert "celery" not in ready.data


def test_gstr_company_throttle_returns_429(tenant_a):
    """CompanyRateThrottle on GSTR endpoints returns 429 after the scoped rate."""
    from unittest.mock import patch

    from core.throttles import CompanyRateThrottle

    cache.clear()
    # Patch rate so we don't burn 30 real GSTR builds in CI.
    with patch.object(CompanyRateThrottle, "get_rate", return_value="2/min"):
        for _ in range(2):
            resp = tenant_a.client.get("/api/v1/reports/gstr1/", {"period": "2026-07"})
            assert resp.status_code == 200
        throttled = tenant_a.client.get("/api/v1/reports/gstr1/", {"period": "2026-07"})
        assert throttled.status_code == 429


def test_staff_cannot_update_company_settings(tenant_a):
    resp = tenant_a.staff_client.patch("/api/v1/company/", {"gstin": "29ABCDE1234F1ZW"}, format="json")
    assert resp.status_code == 403


def test_owner_updates_company_gst_settings(tenant_a):
    resp = tenant_a.client.patch("/api/v1/company/", {"gstin": "29ABCDE1234F1ZW"}, format="json")
    assert resp.status_code == 200
    assert resp.data["gstin"] == "29ABCDE1234F1ZW"


def test_invalid_gstin_rejected(tenant_a):
    resp = tenant_a.client.patch("/api/v1/company/", {"gstin": "INVALID"}, format="json")
    assert resp.status_code == 400


def test_staff_cannot_manage_users(tenant_a):
    resp = tenant_a.staff_client.get("/api/v1/company/users/")
    assert resp.status_code == 403


def test_owner_invites_staff_user(tenant_a):
    resp = tenant_a.client.post("/api/v1/company/users/", {
        "email": "new.staff@alpha.test", "password": "StrongPass123!",
        "role": "SALES_STAFF", "can_manage_inventory": True,
    }, format="json")
    assert resp.status_code == 201
    assert resp.data["role"] == "SALES_STAFF"
    assert resp.data["can_create_sales"] is True
    assert resp.data["can_create_payments"] is True


def test_invite_sales_staff_can_omit_create_flags(tenant_a):
    resp = tenant_a.client.post("/api/v1/company/users/", {
        "email": "seller-defaults@alpha.test", "password": "StrongPass123!",
        "role": "SALES_STAFF",
    }, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["can_create_sales"] is True
    assert resp.data["can_create_payments"] is True


def test_invite_sales_staff_respects_explicit_false_create_flags(tenant_a):
    resp = tenant_a.client.post("/api/v1/company/users/", {
        "email": "seller-locked@alpha.test", "password": "StrongPass123!",
        "role": "SALES_STAFF",
        "can_create_sales": False,
        "can_create_payments": False,
    }, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["can_create_sales"] is False
    assert resp.data["can_create_payments"] is False


def test_cannot_attach_existing_user_to_company_without_consent(tenant_a, tenant_b):
    """BUG-109/701 — inviting an existing user's email must not silently
    create an active membership for them with no consent."""
    resp = tenant_a.client.post("/api/v1/company/users/", {
        "email": tenant_b.owner.email, "password": "SomeoneElsesPass1!",
        "role": "SALES_STAFF",
    }, format="json")
    # Consent invite: 201 with inactive membership + invite token (not a silent active join).
    assert resp.status_code == 201, resp.data
    assert resp.data.get("consent_required") is True
    membership = tenant_b.owner.company_memberships.filter(company=tenant_a.company).first()
    assert membership is not None
    assert membership.is_active is False


def test_duplicate_phone_rejected_at_creation(tenant_a):
    """BUG-108 — the phone uniqueness constraint prevents the data state that
    used to crash OTP verification with MultipleObjectsReturned."""
    from django.db import IntegrityError

    from accounts.models import User

    with pytest.raises(IntegrityError):
        User.objects.create_user(
            email="second@alpha.test", password="StrongPass123!",
            phone=tenant_a.owner.phone,
        )


def test_otp_request_response_identical_for_unknown_and_known_phone(tenant_a):
    """BUG-113 — no enumeration oracle via response shape."""
    client = APIClient()
    known = client.post("/api/v1/auth/otp/request/", {"phone": tenant_a.owner.phone}, format="json")
    unknown = client.post("/api/v1/auth/otp/request/", {"phone": "9999999999"}, format="json")
    assert known.status_code == unknown.status_code == 200
    assert known.data["detail"] == unknown.data["detail"]
    assert "debug_code" not in unknown.data


@override_settings(OTP_DEBUG_ECHO=False, OTP_ENABLED=False, SMS_PROVIDER="console")
def test_otp_request_blocked_outside_debug(tenant_a):
    """BUG-102 / BB-000332 — OTP off when not enabled and no real SMS provider."""
    client = APIClient()
    resp = client.post("/api/v1/auth/otp/request/", {"phone": tenant_a.owner.phone}, format="json")
    assert resp.status_code == 400


def test_otp_verify_locks_out_after_max_attempts(tenant_a, monkeypatch):
    monkeypatch.setattr("accounts.views.secrets.randbelow", lambda n: 654321)
    monkeypatch.setattr("django.conf.settings.OTP_ENABLED", True)
    monkeypatch.setattr("django.conf.settings.SMS_PROVIDER", "console")

    client = APIClient()
    client.post("/api/v1/auth/otp/request/", {"phone": tenant_a.owner.phone}, format="json")

    for _ in range(5):
        resp = client.post(
            "/api/v1/auth/otp/verify/", {"phone": tenant_a.owner.phone, "code": "000000"}, format="json"
        )
        assert resp.status_code == 400

    locked = client.post(
        "/api/v1/auth/otp/verify/", {"phone": tenant_a.owner.phone, "code": "654321"}, format="json"
    )
    assert locked.status_code == 400
    assert "Too many attempts" in str(locked.data)


def test_login_locks_out_after_repeated_failures(tenant_a):
    client = APIClient()
    for _ in range(10):
        resp = client.post("/api/v1/auth/login/", {
            "email": tenant_a.owner.email, "password": "wrong",
        }, format="json")
        assert resp.status_code == 401

    locked = client.post("/api/v1/auth/login/", {
        "email": tenant_a.owner.email, "password": "StrongPass123!",
    }, format="json")
    assert locked.status_code == 429


def test_register_throttle_scope_enforced_by_drf():
    """BUG-125 — verify DRF's ScopedRateThrottle itself rejects requests once
    the configured 'register' rate (5/min) is exceeded, distinct from the
    app-level login/OTP lockouts tested elsewhere in this file.

    Fresh client per request so cookie JWT auth does not switch the throttle
    cache key from anon-IP to per-user (BB-000375 access cookie).
    """
    for i in range(5):
        resp = APIClient().post("/api/v1/auth/register/", {
            "company_name": f"Throttle Co {i}",
            "email": f"throttle{i}@example.test",
            "password": "StrongPass123!",
            "state": "Karnataka",
        }, format="json")
        assert resp.status_code == 200

    throttled = APIClient().post("/api/v1/auth/register/", {
        "company_name": "Throttle Co Overflow",
        "email": "throttle-overflow@example.test",
        "password": "StrongPass123!",
        "state": "Karnataka",
    }, format="json")
    assert throttled.status_code == 429


def test_logout_blacklists_refresh_token_and_prevents_reuse(tenant_a):
    from django.conf import settings

    client = APIClient()
    login = client.post("/api/v1/auth/login/", {
        "email": tenant_a.owner.email, "password": "StrongPass123!",
    }, format="json")
    assert login.status_code == 200, login.data
    access = login.data.get("access")
    refresh_cookie = login.cookies[settings.JWT_REFRESH_COOKIE_NAME].value
    access_cookie_name = getattr(settings, "JWT_ACCESS_COOKIE_NAME", None)
    if not access and access_cookie_name and access_cookie_name in login.cookies:
        access = login.cookies[access_cookie_name].value
    assert access, "login must return an access token (JSON body or access cookie)"

    auth_client = APIClient()
    auth_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    auth_client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = refresh_cookie
    if access_cookie_name:
        auth_client.cookies[access_cookie_name] = access
    logout_resp = auth_client.post("/api/v1/auth/logout/", {}, format="json")
    assert logout_resp.status_code == 200, logout_resp.data

    reuse = APIClient()
    reuse.cookies[settings.JWT_REFRESH_COOKIE_NAME] = refresh_cookie
    reuse_resp = reuse.post("/api/v1/auth/refresh/", {}, format="json")
    assert reuse_resp.status_code == 401


def test_refresh_rotates_token(tenant_a):
    from django.conf import settings

    client = APIClient()
    login = client.post("/api/v1/auth/login/", {
        "email": tenant_a.owner.email, "password": "StrongPass123!",
    }, format="json")
    old_refresh = login.cookies[settings.JWT_REFRESH_COOKIE_NAME].value
    client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = old_refresh
    resp = client.post("/api/v1/auth/refresh/", {}, format="json")
    assert resp.status_code == 200
    assert "access" in resp.data
    assert "refresh" not in resp.data
    new_refresh = resp.cookies[settings.JWT_REFRESH_COOKIE_NAME].value
    assert new_refresh != old_refresh
    # BUG-107: rotated tokens are blacklisted — the old one can't be reused.
    reuse = APIClient()
    reuse.cookies[settings.JWT_REFRESH_COOKIE_NAME] = old_refresh
    reuse_resp = reuse.post("/api/v1/auth/refresh/", {}, format="json")
    assert reuse_resp.status_code == 401


def test_refresh_rejects_body_token_when_not_debug(tenant_a):
    """BB-000266: outside DEBUG, body refresh is rejected."""
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = str(RefreshToken.for_user(tenant_a.owner))
    with override_settings(DEBUG=False):
        resp = APIClient().post(
            "/api/v1/auth/refresh/", {"refresh": refresh}, format="json",
        )
        assert resp.status_code == 401


def test_owner_invites_staff_without_password(tenant_a):
    """BB-000306 / BB-000418 — password optional; invite token + accept flow."""
    resp = tenant_a.client.post("/api/v1/company/users/", {
        "email": "invite.nopw@alpha.test",
        "role": "SALES_STAFF",
    }, format="json")
    assert resp.status_code == 201
    assert resp.data.get("invite_token")
    from accounts.models import User
    user = User.objects.get(email="invite.nopw@alpha.test")
    assert not user.has_usable_password()

    accept = APIClient().post("/api/v1/auth/invite/accept/", {
        "token": resp.data["invite_token"],
        "new_password": "InvitePass123!",
    }, format="json")
    assert accept.status_code == 200
    user.refresh_from_db()
    assert user.has_usable_password()


def test_staff_cannot_read_bank_details(tenant_a):
    """BUG-111 — bank/UPI fields are owner-only reading material."""
    tenant_a.company.bank_account = "1234567890"
    tenant_a.company.upi_id = "alpha@upi"
    tenant_a.company.save(update_fields=["bank_account", "upi_id"])

    resp = tenant_a.staff_client.get("/api/v1/company/")
    assert resp.status_code == 200
    assert "bank_account" not in resp.data
    assert "upi_id" not in resp.data

    me = tenant_a.staff_client.get("/api/v1/auth/me/")
    assert "bank_account" not in me.data["company"]

    owner_resp = tenant_a.client.get("/api/v1/company/")
    assert owner_resp.data["bank_account"] == "1234567890"


def test_last_owner_cannot_be_demoted_or_removed(tenant_a):
    """BUG-112 — a company must always retain at least one active Owner."""
    from accounts.models import CompanyUser

    owner_membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.owner)

    demote = tenant_a.client.patch(
        f"/api/v1/company/users/{owner_membership.id}/", {"role": "SALES_STAFF"}, format="json"
    )
    assert demote.status_code == 400

    delete = tenant_a.client.delete(f"/api/v1/company/users/{owner_membership.id}/")
    assert delete.status_code == 400


def test_docs_view_accessible_to_owner_not_staff(tenant_a):
    """BUG-104/126 — Swagger UI namespace regression guard."""
    owner_resp = tenant_a.client.get("/api/v1/docs/")
    assert owner_resp.status_code == 200

    staff_resp = tenant_a.staff_client.get("/api/v1/docs/")
    assert staff_resp.status_code == 403


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_password_reset_token_is_single_use(tenant_a):
    from django.core import mail

    client = APIClient()
    requested = client.post(
        "/api/v1/auth/password/reset/",
        {"email": tenant_a.owner.email},
        format="json",
    )
    assert requested.status_code == 200
    assert mail.outbox
    token = mail.outbox[0].body.split("token=")[1].split()[0]
    first = client.post(
        "/api/v1/auth/password/reset/confirm/",
        {"token": token, "new_password": "NewStrongPass123!"},
        format="json",
    )
    assert first.status_code == 200, first.data
    second = client.post(
        "/api/v1/auth/password/reset/confirm/",
        {"token": token, "new_password": "AnotherStrongPass123!"},
        format="json",
    )
    assert second.status_code == 400
