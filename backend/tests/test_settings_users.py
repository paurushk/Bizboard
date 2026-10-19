"""SET-09: the Users screen can show last sign-in and invite state, and resend or revoke an invite."""

from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import CompanyUser, InviteJti
from core.models import AuditEvent

URL = "/api/v1/company/users/"


def _invite(tenant, email="new.person@alpha.test", **extra):
    r = tenant.client.post(URL, {"email": email, "role": "SALES_STAFF", **extra}, format="json")
    assert r.status_code == 201, r.data
    return r


def _rows(tenant):
    data = tenant.client.get(URL).data
    return {row["email"]: row for row in (data["results"] if isinstance(data, dict) else data)}


def test_signing_in_stamps_last_login_and_the_list_shows_it(db):
    cache.clear()
    from tests.conftest import make_tenant

    tenant = make_tenant("lastlogin")
    assert _rows(tenant)[tenant.owner.email]["last_login"] is None
    r = APIClient().post(
        "/api/v1/auth/login/", {"email": tenant.owner.email, "password": "StrongPass123!"}, format="json"
    )
    assert r.status_code == 200, r.data
    tenant.owner.refresh_from_db()
    assert tenant.owner.last_login is not None
    assert _rows(tenant)[tenant.owner.email]["last_login"] is not None
    assert _rows(tenant)[tenant.staff.email]["last_login"] is None


def test_a_member_who_has_joined_is_accepted(tenant_a):
    row = _rows(tenant_a)[tenant_a.owner.email]
    assert row["invite_state"] == "accepted" and row["invite_expires_at"] is None


def test_an_invited_person_shows_as_pending_with_an_expiry(tenant_a):
    _invite(tenant_a)
    row = _rows(tenant_a)["new.person@alpha.test"]
    assert row["invite_state"] == "pending" and row["invite_expires_at"] is not None


def test_an_invite_with_no_valid_link_shows_as_expired(tenant_a):
    _invite(tenant_a)
    InviteJti.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
    assert _rows(tenant_a)["new.person@alpha.test"]["invite_state"] == "expired"


def test_resending_gives_a_new_link_and_the_old_one_stops_working(tenant_a):
    first = _invite(tenant_a)
    membership = CompanyUser.objects.get(pk=first.data["id"])
    again = tenant_a.client.post(f"{URL}{membership.id}/resend-invite/")
    assert again.status_code == 200, again.data
    assert again.data["invite_url"] and again.data["invite_expires_at"]
    assert again.data["invite_token"] != first.data["invite_token"]
    old = APIClient().post(
        "/api/v1/auth/invite/accept/", {"token": first.data["invite_token"], "new_password": "InvitePass123!"}, format="json"
    )
    assert old.status_code >= 400
    new = APIClient().post(
        "/api/v1/auth/invite/accept/", {"token": again.data["invite_token"], "new_password": "InvitePass123!"}, format="json"
    )
    assert new.status_code == 200, new.data
    assert AuditEvent.objects.filter(company=tenant_a.company, description="Invite re-sent").count() == 1


def test_resending_revives_an_expired_invite(tenant_a):
    first = _invite(tenant_a)
    InviteJti.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
    assert tenant_a.client.post(f"{URL}{first.data['id']}/resend-invite/").status_code == 200
    assert _rows(tenant_a)["new.person@alpha.test"]["invite_state"] == "pending"


def test_revoking_cancels_the_link(tenant_a):
    first = _invite(tenant_a)
    r = tenant_a.client.post(f"{URL}{first.data['id']}/revoke-invite/")
    assert r.status_code == 200 and r.data["revoked"] == 1
    assert _rows(tenant_a)["new.person@alpha.test"]["invite_state"] == "expired"
    accept = APIClient().post(
        "/api/v1/auth/invite/accept/", {"token": first.data["invite_token"], "new_password": "InvitePass123!"}, format="json"
    )
    assert accept.status_code >= 400
    assert AuditEvent.objects.filter(company=tenant_a.company, description="Invite revoked").count() == 1


def test_a_person_who_has_joined_cannot_be_resent_or_revoked(tenant_a):
    for action in ("resend-invite", "revoke-invite"):
        r = tenant_a.client.post(f"{URL}{tenant_a.staff.company_memberships.first().id}/{action}/")
        assert r.status_code == 400 and "already joined" in str(r.data)


def test_invite_actions_are_owner_only_and_company_scoped(tenant_a, tenant_b):
    mine = _invite(tenant_a)
    assert tenant_a.staff_client.post(f"{URL}{mine.data['id']}/resend-invite/").status_code == 403
    assert tenant_b.client.post(f"{URL}{mine.data['id']}/revoke-invite/").status_code == 404
    assert InviteJti.objects.filter(membership_id=mine.data["id"], consumed_at__isnull=True).exists()


def test_someone_who_signed_in_and_was_switched_off_is_deactivated_not_expired(tenant_a):
    staff_membership = tenant_a.staff.company_memberships.first()
    tenant_a.staff.last_login = timezone.now()
    tenant_a.staff.save(update_fields=["last_login"])
    CompanyUser.objects.filter(pk=staff_membership.pk).update(is_active=False)
    assert _rows(tenant_a)[tenant_a.staff.email]["invite_state"] == "deactivated"


def test_a_person_never_invited_and_switched_off_is_deactivated_even_without_a_sign_in_record(tenant_a):
    from accounts.models import CompanyUser

    CompanyUser.objects.filter(user=tenant_a.staff).update(is_active=False)
    tenant_a.staff.last_login = None
    tenant_a.staff.save(update_fields=["last_login"])
    assert _rows(tenant_a)[tenant_a.staff.email]["invite_state"] == "deactivated"


def test_inviting_twice_with_the_same_key_adds_one_person(tenant_a):
    body = {"email": "twice@alpha.test", "full_name": "Twice", "role": "SALES_STAFF"}
    key = {"HTTP_IDEMPOTENCY_KEY": "invite-key-1"}
    first = tenant_a.client.post(URL, body, format="json", **key)
    second = tenant_a.client.post(URL, body, format="json", **key)
    assert first.status_code == 201 and second.status_code == 201, (first.data, second.data)
    assert CompanyUser.objects.filter(company=tenant_a.company, user__email="twice@alpha.test").count() == 1
