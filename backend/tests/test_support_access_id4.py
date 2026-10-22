"""WP-ID4: customer-approved, read-only support access. Replaces "no access ever" with
"no access without a live grant" (the no-impersonation guard still holds: no act-as route)."""

from datetime import timedelta

import pytest
from django.db import DatabaseError
from django.utils import timezone

from accounts.models import User
from core.exceptions import BusinessRuleError
from masters.models import Customer
from support.access import expire_due_grants, grant_access, read_only_tenant, revoke, usable_grant, view_section
from support.models import PlatformTicket, SupportAccessLog
from support.platform_tickets import open_ticket
from tests.rls_helpers import needs_pg

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff(db):
    return User.objects.create_user(email="helpdesk@bizboard.example", password="x-Strong-pass-1", is_staff=True)


def _ticket(tenant):
    return open_ticket(company=tenant.company, user=tenant.owner, subject="Stock looks wrong", description="d")


def _grant(tenant, **kw):
    return grant_access(company=tenant.company, owner=tenant.owner, ticket_id=_ticket(tenant).pk, **kw)


def test_no_grant_means_no_view(client, staff, tenant_a):
    client.force_login(staff)
    assert client.get("/admin/ops/support-view/999/").status_code == 403


def test_live_grant_shows_only_that_company_and_is_logged(client, staff, tenant_a, tenant_b):
    Customer.objects.create(company=tenant_a.company, name="Alpha Traders")
    Customer.objects.create(company=tenant_b.company, name="Beta Stores")
    grant = _grant(tenant_a)
    client.force_login(staff)
    page = client.get(f"/admin/ops/support-view/{grant.pk}/?section=customers")
    assert page.status_code == 200
    assert b"Alpha Traders" in page.content and b"Beta Stores" not in page.content
    log = SupportAccessLog.objects.get(grant=grant)
    assert log.section == "customers" and log.staff_user == staff and log.rows_shown == 1


def test_non_safe_methods_are_refused_before_anything_is_read(client, staff, tenant_a):
    grant = _grant(tenant_a)
    client.force_login(staff)
    resp = client.post(f"/admin/ops/support-view/{grant.pk}/?section=customers")
    assert resp.status_code == 403 and b"SUPPORT_READ_ONLY" in resp.content
    assert not SupportAccessLog.objects.exists()


def test_a_write_inside_the_read_only_view_fails_loudly(tenant_a):
    with pytest.raises(DatabaseError):
        with read_only_tenant(tenant_a.company.pk):
            Customer.objects.create(company=tenant_a.company, name="Sneaky write")
    assert not Customer.objects.filter(name="Sneaky write").exists()
    # The connection is writable again afterwards (the audit write happens outside).
    Customer.objects.create(company=tenant_a.company, name="Normal write")


def test_view_section_logs_after_the_read_only_transaction(staff, tenant_a):
    grant = _grant(tenant_a)
    data = view_section(grant, staff_user=staff, section="activity")
    assert "action" in data["fields"]
    assert SupportAccessLog.objects.filter(grant=grant, section="activity").count() == 1


def test_named_staff_only_and_expiry_and_revoke(staff, tenant_a):
    other = User.objects.create_user(email="other-staff@bizboard.example", password="x-Strong-pass-1", is_staff=True)
    grant = _grant(tenant_a, staff_email=staff.email)
    assert usable_grant(grant.pk, staff) is not None
    assert usable_grant(grant.pk, other) is None
    assert usable_grant(grant.pk, tenant_a.owner) is None  # not staff
    type(grant).objects.filter(pk=grant.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
    assert usable_grant(grant.pk, staff) is None
    assert expire_due_grants() == 1
    grant.refresh_from_db()
    assert grant.revoke_reason == "expired"

    second = _grant(tenant_a)
    revoke(second, user=tenant_a.owner)
    assert usable_grant(second.pk, staff) is None


def test_resolving_the_ticket_ends_access(staff, tenant_a):
    grant = _grant(tenant_a)
    PlatformTicket.objects.filter(pk=grant.ticket_id).update(status=PlatformTicket.Status.RESOLVED)
    assert expire_due_grants() == 1
    assert usable_grant(grant.pk, staff) is None


def test_grant_rules(tenant_a, tenant_b):
    with pytest.raises(BusinessRuleError, match="1 to 72"):
        _grant(tenant_a, hours=100)
    with pytest.raises(BusinessRuleError, match="open support request"):
        grant_access(company=tenant_a.company, owner=tenant_a.owner, ticket_id=_ticket(tenant_b).pk)
    with pytest.raises(BusinessRuleError, match="support address"):
        _grant(tenant_a, staff_email="someone@gmail.com")


def test_owner_api_needs_password_and_members_only_see_that_access_is_live(staff, tenant_a):
    ticket = _ticket(tenant_a)
    denied = tenant_a.client.post("/api/v1/support/access-grants/", {"ticket_id": ticket.pk}, format="json")
    assert denied.status_code in (400, 403), denied.content
    created = tenant_a.client.post(
        "/api/v1/support/access-grants/", {"ticket_id": ticket.pk, "hours": 24, "password": "StrongPass123!"},
        format="json",
    )
    assert created.status_code == 201, created.content
    grant_id = created.json()["data"]["id"]
    assert tenant_a.staff_client.post(
        "/api/v1/support/access-grants/", {"ticket_id": ticket.pk, "password": "StrongPass123!"}, format="json",
    ).status_code == 403
    member_view = tenant_a.staff_client.get("/api/v1/support/access-grants/").json()["data"]
    assert len(member_view) == 1 and member_view[0]["live"] is True and member_view[0]["views"] == []
    from support.models import SupportAccessGrant

    view_section(SupportAccessGrant.objects.get(pk=grant_id), staff_user=staff, section="products")
    owner_view = tenant_a.client.get("/api/v1/support/access-grants/").json()["data"]
    assert owner_view[0]["views"][0]["section"] == "products"
    ended = tenant_a.client.post(f"/api/v1/support/access-grants/{grant_id}/revoke/")
    assert ended.status_code == 200 and ended.json()["data"]["live"] is False


def test_grant_revoke_is_company_scoped(tenant_a, tenant_b):
    grant = _grant(tenant_a)
    assert tenant_b.client.post(f"/api/v1/support/access-grants/{grant.pk}/revoke/").status_code == 404
    grant.refresh_from_db()
    assert grant.revoked_at is None


@pytest.mark.postgres
@needs_pg
@pytest.mark.django_db(transaction=True)
def test_read_only_view_under_the_app_role_sees_one_company_and_refuses_writes():
    """The staff path under the real NOBYPASSRLS app role: the grant's company only, and the
    database itself refuses a write inside the read-only transaction."""
    from django.test import override_settings

    from core.rls import rls_bypass
    from tests.conftest import make_tenant
    from tests.rls_helpers import app_role
    a, b = make_tenant("rlsida"), make_tenant("rlsidb")
    with rls_bypass():
        Customer.objects.create(company=a.company, name="Alpha Only")
        Customer.objects.create(company=b.company, name="Beta Only")
        grant = grant_access(company=a.company, owner=a.owner, ticket_id=_ticket(a).pk)
    staff = User.objects.create_user(email="pg-helpdesk@bizboard.example", password="x-Strong-pass-1", is_staff=True)
    with override_settings(POSTGRES_RLS_ENABLED=True), app_role():
        with read_only_tenant(a.company.pk):
            names = set(Customer.objects.values_list("name", flat=True))  # no company filter on purpose
        assert names == {"Alpha Only"}
        with pytest.raises(DatabaseError):
            with read_only_tenant(a.company.pk):
                Customer.objects.create(company=a.company, name="Sneaky")
        data = view_section(grant, staff_user=staff, section="customers")
    assert [r["name"] for r in data["rows"]] == ["Alpha Only"]
