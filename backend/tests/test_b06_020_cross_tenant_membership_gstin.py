"""B6-020: accounts_companyuser / accounts_companygstin sit outside RLS by
design (the tenant-resolving middleware must read them before app.company_id
is set) — every access relies solely on hand-written `.filter(company=...)`
in CompanyUserViewSet / CompanyGstinViewSet. The review's own "at minimum"
ask was targeted cross-tenant tests for every code path on these two models,
since there is no DB-level backstop if one of those filters is ever dropped.
"""

from accounts.models import CompanyGstin, CompanyUser


def _rows(resp):
    # List responses may be paginated ({"count": ..., "results": [...]}) or a
    # bare array depending on the viewset's pagination_class.
    return resp.data.get("results", resp.data) if isinstance(resp.data, dict) else resp.data


def test_company_users_list_excludes_other_tenant(tenant_a, tenant_b):
    resp = tenant_b.client.get("/api/v1/company/users/")
    assert resp.status_code == 200
    rows = _rows(resp)
    seen_companies = {row["company"] for row in rows}
    assert tenant_a.company.id not in seen_companies
    returned_ids = {row["id"] for row in rows}
    assert tenant_a.staff.company_memberships.get(company=tenant_a.company).id not in returned_ids


def test_company_users_cannot_read_other_tenant_by_id(tenant_a, tenant_b):
    other_membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    resp = tenant_b.client.get(f"/api/v1/company/users/{other_membership.id}/")
    assert resp.status_code == 404


def test_company_users_cannot_patch_other_tenant_by_id(tenant_a, tenant_b):
    other_membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    resp = tenant_b.client.patch(f"/api/v1/company/users/{other_membership.id}/", {"role": "OWNER"}, format="json")
    assert resp.status_code == 404
    other_membership.refresh_from_db()
    assert other_membership.role != CompanyUser.Role.OWNER


def test_company_users_cannot_delete_other_tenant_by_id(tenant_a, tenant_b):
    other_membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    resp = tenant_b.client.delete(f"/api/v1/company/users/{other_membership.id}/")
    assert resp.status_code == 404
    other_membership.refresh_from_db()
    assert other_membership.is_active is True


def test_company_gstins_list_excludes_other_tenant(tenant_a, tenant_b):
    gstin_a = CompanyGstin.objects.create(
        company=tenant_a.company, gstin="29AAAAA0000A1Z5", legal_name="Alpha Traders", state="Karnataka",
    )
    resp = tenant_b.client.get("/api/v1/company/gstins/")
    assert resp.status_code == 200
    returned_ids = {row["id"] for row in _rows(resp)}
    assert gstin_a.id not in returned_ids


def test_company_gstins_cannot_read_other_tenant_by_id(tenant_a, tenant_b):
    gstin_a = CompanyGstin.objects.create(
        company=tenant_a.company, gstin="29AAAAA0000A1Z5", legal_name="Alpha Traders", state="Karnataka",
    )
    resp = tenant_b.client.get(f"/api/v1/company/gstins/{gstin_a.id}/")
    assert resp.status_code == 404


def test_company_gstins_cannot_patch_other_tenant_by_id(tenant_a, tenant_b):
    gstin_a = CompanyGstin.objects.create(
        company=tenant_a.company, gstin="29AAAAA0000A1Z5", legal_name="Alpha Traders", state="Karnataka",
    )
    resp = tenant_b.client.patch(
        f"/api/v1/company/gstins/{gstin_a.id}/", {"legal_name": "Hijacked"}, format="json"
    )
    assert resp.status_code == 404
    gstin_a.refresh_from_db()
    assert gstin_a.legal_name == "Alpha Traders"


def test_company_gstins_cannot_delete_other_tenant_by_id(tenant_a, tenant_b):
    gstin_a = CompanyGstin.objects.create(
        company=tenant_a.company, gstin="29AAAAA0000A1Z5", legal_name="Alpha Traders", state="Karnataka",
    )
    resp = tenant_b.client.delete(f"/api/v1/company/gstins/{gstin_a.id}/")
    assert resp.status_code == 404
    assert CompanyGstin.objects.filter(id=gstin_a.id).exists()
