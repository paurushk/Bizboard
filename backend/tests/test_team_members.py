"""BB-100 F10: any active member can list the team for the pickers — id, name and role only."""

import pytest
from rest_framework.test import APIClient

from accounts.models import CompanyUser, User

pytestmark = pytest.mark.django_db

URL = "/api/v1/company/members/"


def _member(tenant, email, role, *, full_name="", active=True):
    user = User.objects.create_user(email=email, password="StrongPass123!", full_name=full_name)
    flags = CompanyUser.capability_defaults_for_role(role) or {}
    CompanyUser.objects.create(company=tenant.company, user=user, role=role, is_active=active, **flags)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.parametrize("role", ["MANAGER", "SALES_STAFF", "ACCOUNTANT", "VIEWER"])
def test_any_active_member_can_list_the_team(tenant_a, role):
    client = _member(tenant_a, f"{role.lower()}@alpha.test", role, full_name=f"Alpha {role}")
    res = client.get(URL)
    assert res.status_code == 200, res.data
    names = {row["name"] for row in res.data}
    assert {"alpha owner", "alpha staff", f"Alpha {role}"} <= names


def test_only_id_name_and_role_are_shared(tenant_a):
    res = tenant_a.staff_client.get(URL)
    assert res.status_code == 200
    assert res.data and all(set(row) == {"id", "name", "role"} for row in res.data)
    owner = next(row for row in res.data if row["name"] == "alpha owner")
    assert owner["role"] == "OWNER"
    assert owner["id"] == CompanyUser.objects.get(company=tenant_a.company, role="OWNER").id


def test_pending_invites_and_other_companies_are_left_out(tenant_a, tenant_b):
    _member(tenant_a, "invited@alpha.test", "SALES_STAFF", full_name="Not yet joined", active=False)
    res = tenant_a.staff_client.get(URL)
    names = {row["name"] for row in res.data}
    assert "Not yet joined" not in names
    assert not any(name.startswith("beta") for name in names)


def test_a_member_without_a_name_shows_the_part_before_the_at(tenant_a):
    _member(tenant_a, "ravi.k@alpha.test", "SALES_STAFF")
    names = {row["name"] for row in tenant_a.client.get(URL).data}
    assert "ravi.k" in names
    assert not any("@" in name for name in names)


def test_signed_out_users_get_nothing(tenant_a):
    assert APIClient().get(URL).status_code in (401, 403)
