import pytest
from rest_framework.test import APIClient

from core.models import AuditEvent

pytestmark = pytest.mark.django_db


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
    client = APIClient()
    resp = client.post("/api/v1/auth/otp/request/", {"phone": tenant_a.owner.phone}, format="json")
    assert resp.status_code == 200
    code = resp.data["debug_code"]

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
