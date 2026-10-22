"""WP-ID2: a user in two companies never reads or writes the wrong one.

The web side (other tabs reload on a switch; outboxes stop when the company changed) is tested in
``web/src/api/companyContext.test.ts`` and the outbox tests.
"""

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from accounts.models import CompanyUser
from masters.models import Customer
from tests.conftest import make_customer

pytestmark = pytest.mark.django_db


@pytest.fixture
def two_company_owner(tenant_a, tenant_b):
    user = tenant_a.owner
    CompanyUser.objects.create(company=tenant_b.company, user=user, role=CompanyUser.Role.OWNER)
    user.active_company_id = tenant_a.company.id
    user.save(update_fields=["active_company_id"])
    client = APIClient()
    client.force_authenticate(user=user)
    return user, client


@override_settings(REQUIRE_COMPANY_HEADER_FOR_MULTI=True)
def test_multi_company_user_without_header_gets_company_required(two_company_owner, tenant_a):
    _user, client = two_company_owner
    make_customer(tenant_a.company, name="A only")
    resp = client.get("/api/v1/customers/")
    assert resp.status_code == 409
    body = resp.json()
    detail = body.get("detail", body)
    assert "COMPANY_REQUIRED" in str(detail)


@override_settings(REQUIRE_COMPANY_HEADER_FOR_MULTI=True)
def test_auth_endpoints_still_work_without_header(two_company_owner):
    _user, client = two_company_owner
    assert client.get("/api/v1/auth/me/").status_code == 200
    assert client.get("/api/v1/auth/memberships/").status_code == 200


@override_settings(REQUIRE_COMPANY_HEADER_FOR_MULTI=True)
def test_single_company_user_keeps_the_fallback(tenant_a):
    resp = tenant_a.client.get("/api/v1/customers/")
    assert resp.status_code == 200


@override_settings(REQUIRE_COMPANY_HEADER_FOR_MULTI=True)
def test_with_header_reads_only_that_company(two_company_owner, tenant_a, tenant_b):
    _user, client = two_company_owner
    make_customer(tenant_a.company, name="A customer")
    make_customer(tenant_b.company, name="B customer")
    resp = client.get("/api/v1/customers/", HTTP_X_COMPANY_ID=str(tenant_a.company.id))
    assert resp.status_code == 200
    text = str(resp.json())
    assert "A customer" in text and "B customer" not in text


@override_settings(REQUIRE_COMPANY_HEADER_FOR_MULTI=True)
def test_stale_tab_write_after_switch_is_refused_and_writes_nothing(two_company_owner, tenant_a, tenant_b):
    user, client = two_company_owner
    switched = client.post(
        "/api/v1/auth/switch-company/", {"company_id": tenant_b.company.id}, format="json",
    )
    assert switched.status_code == 200
    before = Customer.objects.filter(company=tenant_b.company).count()
    # Tab 2 still believes it is company A.
    resp = client.post(
        "/api/v1/customers/",
        {"name": "Typed in the stale tab", "status": "ACTIVE"},
        format="json",
        HTTP_X_COMPANY_ID=str(tenant_a.company.id),
    )
    assert resp.status_code == 409
    assert Customer.objects.filter(company=tenant_b.company).count() == before
    assert not Customer.objects.filter(name="Typed in the stale tab").exists()


@override_settings(REQUIRE_COMPANY_HEADER_FOR_MULTI=True)
def test_file_link_from_company_a_is_not_served_under_company_b(two_company_owner, tenant_a, tenant_b):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from core.services.files import FileService

    user, client = two_company_owner
    asset = FileService.store_upload(
        company=tenant_a.company,
        uploaded_file=SimpleUploadedFile("a.txt", b"company A only", content_type="text/plain"),
        kind="ATTACHMENT",
        user=user,
    )
    ok = client.get(f"/api/v1/files/{asset.id}/download/", HTTP_X_COMPANY_ID=str(tenant_a.company.id))
    assert ok.status_code == 200
    # The same link opened while acting as company B: not found, never B's or A's bytes.
    client.post("/api/v1/auth/switch-company/", {"company_id": tenant_b.company.id}, format="json")
    under_b = client.get(f"/api/v1/files/{asset.id}/download/", HTTP_X_COMPANY_ID=str(tenant_b.company.id))
    assert under_b.status_code == 404
    bare = client.get(f"/api/v1/files/{asset.id}/download/")
    assert bare.status_code == 409
