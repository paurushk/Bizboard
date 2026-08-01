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
    assert resp.status_code == 201
    assert "access" in resp.data and "refresh" in resp.data

    # Owner can immediately use the API
    auth_client = APIClient()
    auth_client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")
    me = auth_client.get("/api/v1/auth/me/")
    assert me.status_code == 200
    assert me.data["role"] == "OWNER"
    assert me.data["company"]["name"] == "Fresh Mart"


def test_login_returns_tokens_and_audits(tenant_a):
    client = APIClient()
    resp = client.post("/api/v1/auth/login/", {
        "email": tenant_a.owner.email, "password": "StrongPass123!",
    }, format="json")
    assert resp.status_code == 200
    assert "access" in resp.data
    assert "refresh" in resp.data
    assert resp.data["user"]["email"] == tenant_a.owner.email
    assert resp.data["user"]["role"] == "OWNER"
    assert resp.data["user"]["company_id"] == tenant_a.company.id
    assert AuditEvent.objects.filter(user=tenant_a.owner, action="LOGIN").exists()


def test_login_wrong_password_rejected(tenant_a):
    client = APIClient()
    resp = client.post("/api/v1/auth/login/", {
        "email": tenant_a.owner.email, "password": "wrong",
    }, format="json")
    assert resp.status_code == 401


def test_otp_login_flow(tenant_a):
    from accounts.models import OtpChallenge

    client = APIClient()
    resp = client.post("/api/v1/auth/otp/request/", {"phone": tenant_a.owner.phone}, format="json")
    assert resp.status_code == 200
    code = resp.data.get("debug_code")
    if not code:
        code = OtpChallenge.objects.filter(phone=tenant_a.owner.phone).latest("created_at").code

    bad = client.post("/api/v1/auth/otp/verify/", {"phone": tenant_a.owner.phone, "code": "000000"}, format="json")
    assert bad.status_code == 400

    ok = client.post("/api/v1/auth/otp/verify/", {"phone": tenant_a.owner.phone, "code": code}, format="json")
    assert ok.status_code == 200
    assert "access" in ok.data
    assert ok.data["user"]["email"] == tenant_a.owner.email


def test_health_is_public():
    resp = APIClient().get("/api/v1/health/")
    assert resp.status_code == 200


def test_staff_cannot_update_company_settings(tenant_a):
    resp = tenant_a.staff_client.patch("/api/v1/company/", {"gstin": "29ABCDE1234F1Z5"}, format="json")
    assert resp.status_code == 403


def test_owner_updates_company_gst_settings(tenant_a):
    resp = tenant_a.client.patch("/api/v1/company/", {"gstin": "29ABCDE1234F1Z5"}, format="json")
    assert resp.status_code == 200
    assert resp.data["gstin"] == "29ABCDE1234F1Z5"


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


def test_cannot_attach_existing_user_to_company_without_consent(tenant_a, tenant_b):
    """BUG-109/701 — inviting an existing user's email must not silently
    create an active membership for them with no consent."""
    resp = tenant_a.client.post("/api/v1/company/users/", {
        "email": tenant_b.owner.email, "password": "SomeoneElsesPass1!",
        "role": "OWNER",
    }, format="json")
    assert resp.status_code == 400
    assert not tenant_b.owner.company_memberships.filter(company=tenant_a.company).exists()


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


@override_settings(OTP_DEBUG_ECHO=False)
def test_otp_request_blocked_outside_debug(tenant_a):
    """BUG-102 — no real SMS gateway is wired up, so OTP must not report
    success outside local development."""
    client = APIClient()
    resp = client.post("/api/v1/auth/otp/request/", {"phone": tenant_a.owner.phone}, format="json")
    assert resp.status_code == 400


def test_otp_verify_locks_out_after_max_attempts(tenant_a):
    from accounts.models import OtpChallenge

    client = APIClient()
    client.post("/api/v1/auth/otp/request/", {"phone": tenant_a.owner.phone}, format="json")
    challenge = OtpChallenge.objects.filter(phone=tenant_a.owner.phone).latest("created_at")

    for _ in range(5):
        resp = client.post(
            "/api/v1/auth/otp/verify/", {"phone": tenant_a.owner.phone, "code": "000000"}, format="json"
        )
        assert resp.status_code == 400

    locked = client.post(
        "/api/v1/auth/otp/verify/", {"phone": tenant_a.owner.phone, "code": challenge.code}, format="json"
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
    app-level login/OTP lockouts tested elsewhere in this file."""
    client = APIClient()
    for i in range(5):
        resp = client.post("/api/v1/auth/register/", {
            "company_name": f"Throttle Co {i}",
            "email": f"throttle{i}@example.test",
            "password": "StrongPass123!",
            "state": "Karnataka",
        }, format="json")
        assert resp.status_code == 201

    throttled = client.post("/api/v1/auth/register/", {
        "company_name": "Throttle Co Overflow",
        "email": "throttle-overflow@example.test",
        "password": "StrongPass123!",
        "state": "Karnataka",
    }, format="json")
    assert throttled.status_code == 429


def test_logout_blacklists_refresh_token_and_prevents_reuse(tenant_a):
    client = APIClient()
    login = client.post("/api/v1/auth/login/", {
        "email": tenant_a.owner.email, "password": "StrongPass123!",
    }, format="json")
    refresh = login.data["refresh"]
    access = login.data["access"]

    auth_client = APIClient()
    auth_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    logout_resp = auth_client.post("/api/v1/auth/logout/", {"refresh": refresh}, format="json")
    assert logout_resp.status_code == 200

    reuse = APIClient().post("/api/v1/auth/refresh/", {"refresh": refresh}, format="json")
    assert reuse.status_code == 401


def test_refresh_rotates_token(tenant_a):
    client = APIClient()
    login = client.post("/api/v1/auth/login/", {
        "email": tenant_a.owner.email, "password": "StrongPass123!",
    }, format="json")
    old_refresh = login.data["refresh"]
    resp = client.post("/api/v1/auth/refresh/", {"refresh": old_refresh}, format="json")
    assert resp.status_code == 200
    assert resp.data["refresh"] != old_refresh
    # BUG-107: rotated tokens are blacklisted — the old one can't be reused.
    reuse = APIClient().post("/api/v1/auth/refresh/", {"refresh": old_refresh}, format="json")
    assert reuse.status_code == 401


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
