"""WP-H5 (DPDP): who accepted which version of the Terms, Privacy Policy and DPA, and when."""

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from accounts.models import LegalAcceptance, User
from tests.conftest import register_via_api

pytestmark = pytest.mark.django_db
ON = override_settings(LEGAL_ACCEPTANCE_REQUIRED=True, OTP_DEBUG_ECHO=True)


def _payload(email):
    return {"company_name": "Legal Co", "email": email, "password": "StrongPass123!", "state": "Karnataka"}


@ON
def test_sign_up_without_agreeing_is_refused():
    client = APIClient()
    otp = client.post("/api/v1/auth/register/otp/request/", {"email": "noagree@example.test"}, format="json")
    resp = client.post(
        "/api/v1/auth/register/", {**_payload("noagree@example.test"), "otp_code": otp.data["debug_code"]},
        format="json",
    )
    assert resp.status_code == 400
    assert not User.objects.filter(email="noagree@example.test").exists()


@ON
def test_sign_up_records_the_current_versions():
    assert register_via_api(APIClient(), _payload("agree@example.test")).status_code == 200
    user = User.objects.get(email="agree@example.test")
    rows = {a.document: a for a in LegalAcceptance.objects.filter(user=user)}
    assert set(rows) == {"TOS", "PRIVACY", "DPA"}
    assert rows["DPA"].company_id is not None and rows["TOS"].company_id is None
    assert rows["TOS"].version == "draft-2026-10"


@ON
def test_a_new_version_is_pending_until_accepted(tenant_a):
    client = tenant_a.client
    first = client.get("/api/v1/auth/legal/")
    assert {p["document"] for p in first.data["pending"]} == {"TOS", "PRIVACY", "DPA"}  # owner
    me = client.get("/api/v1/auth/me/")
    assert {p["document"] for p in me.data["legal_pending"]} == {"TOS", "PRIVACY", "DPA"}
    done = client.post("/api/v1/auth/legal/", {"documents": ["TOS", "PRIVACY", "DPA"]}, format="json")
    assert done.status_code == 200 and done.data["pending"] == []
    with override_settings(LEGAL_DOCUMENT_VERSIONS={"TOS": "v2", "PRIVACY": "draft-2026-10", "DPA": "draft-2026-10"}):
        again = client.get("/api/v1/auth/legal/")
        assert [p["document"] for p in again.data["pending"]] == ["TOS"]
        assert again.data["pending"][0]["version"] == "v2"
        client.post("/api/v1/auth/legal/", {"documents": ["TOS"]}, format="json")
        assert client.get("/api/v1/auth/legal/").data["pending"] == []
    history = client.get("/api/v1/auth/legal/").data["history"]
    assert [h["version"] for h in history if h["document"] == "TOS"] == ["v2", "draft-2026-10"]


@ON
def test_staff_do_not_sign_the_company_dpa(tenant_a):
    pending = tenant_a.staff_client.get("/api/v1/auth/legal/").data["pending"]
    assert {p["document"] for p in pending} == {"TOS", "PRIVACY"}
    resp = tenant_a.staff_client.post("/api/v1/auth/legal/", {"documents": ["DPA"]}, format="json")
    assert resp.status_code == 400


def test_acceptances_are_append_only(tenant_a):
    row = LegalAcceptance.objects.create(user=tenant_a.owner, document="TOS", version="x")
    row.version = "y"
    with pytest.raises(ValueError):
        row.save()
