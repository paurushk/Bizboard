"""WP-ID3: signed-in devices, sign one out, new-device email, network prefix only."""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.core import mail
from rest_framework.test import APIClient

from accounts.models import UserSession
from accounts.user_sessions import device_label, ip_prefix

pytestmark = pytest.mark.django_db

PASSWORD = "StrongPass123!"
CHROME_WIN = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"
SAFARI_IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Safari/604.1"


def _login(user, *, ua=CHROME_WIN, ip="203.0.113.45"):
    client = APIClient(HTTP_USER_AGENT=ua, REMOTE_ADDR=ip)
    resp = client.post("/api/v1/auth/login/", {"email": user.email, "password": PASSWORD}, format="json")
    assert resp.status_code == 200, resp.content
    return client


def test_labels_and_prefixes_never_keep_the_full_address():
    assert device_label(CHROME_WIN) == "Chrome on Windows"
    assert device_label(SAFARI_IPHONE) == "Safari on iPhone"
    assert ip_prefix("203.0.113.45") == "203.0.113.0/24"
    assert ip_prefix("2001:db8:abcd:12::1") == "2001:db8:abcd::/48"
    assert ip_prefix("not an ip") == ""


def test_sign_in_records_a_device_and_refresh_keeps_the_same_row(tenant_a):
    client = _login(tenant_a.owner)
    rows = list(UserSession.objects.filter(user=tenant_a.owner))
    assert len(rows) == 1
    assert rows[0].device_label == "Chrome on Windows" and rows[0].ip_prefix == "203.0.113.0/24"
    assert "203.0.113.45" not in str(UserSession.objects.values().first())
    first_jti = rows[0].current_jti
    assert client.post("/api/v1/auth/refresh/", {}, format="json").status_code == 200
    rows = list(UserSession.objects.filter(user=tenant_a.owner))
    assert len(rows) == 1 and rows[0].current_jti != first_jti
    listed = client.get("/api/v1/auth/sessions/").json()["data"]
    assert len(listed) == 1 and listed[0]["current"] is True and listed[0]["device"] == "Chrome on Windows"


def test_only_own_sessions_are_listed_and_revocable(tenant_a):
    _login(tenant_a.owner)
    staff_client = _login(tenant_a.staff)
    owner_row = UserSession.objects.get(user=tenant_a.owner)
    assert all(r["id"] != owner_row.pk for r in staff_client.get("/api/v1/auth/sessions/").json()["data"])
    assert staff_client.post(f"/api/v1/auth/sessions/{owner_row.pk}/revoke/").status_code == 404


def test_signing_a_device_out_stops_its_refresh(tenant_a):
    phone = _login(tenant_a.owner, ua=SAFARI_IPHONE, ip="198.51.100.7")
    laptop = _login(tenant_a.owner)
    phone_row = UserSession.objects.get(user=tenant_a.owner, device_label="Safari on iPhone")
    resp = laptop.post(f"/api/v1/auth/sessions/{phone_row.pk}/revoke/")
    assert resp.status_code == 200, resp.content
    assert phone.post("/api/v1/auth/refresh/", {}, format="json").status_code == 401
    assert laptop.post("/api/v1/auth/refresh/", {}, format="json").status_code == 200
    assert [r["device"] for r in laptop.get("/api/v1/auth/sessions/").json()["data"]] == ["Chrome on Windows"]


def test_new_device_email_once_and_not_on_the_first_ever_sign_in(tenant_a, django_capture_on_commit_callbacks):
    mail.outbox.clear()
    # The email is queued once the sign-in commits (never sent inside the sign-in request).
    with django_capture_on_commit_callbacks(execute=True):
        _login(tenant_a.owner)
    assert not mail.outbox  # first ever session
    with django_capture_on_commit_callbacks(execute=True):
        _login(tenant_a.owner)
    assert not mail.outbox  # same device and network
    with django_capture_on_commit_callbacks(execute=True):
        _login(tenant_a.owner, ua=SAFARI_IPHONE, ip="198.51.100.7")
    assert len(mail.outbox) == 1
    assert "Safari on iPhone" in mail.outbox[0].body and "198.51.100.7" not in mail.outbox[0].body
    with django_capture_on_commit_callbacks(execute=True):
        _login(tenant_a.owner, ua=SAFARI_IPHONE, ip="198.51.100.9")  # same /24
    assert len(mail.outbox) == 1


def test_logout_all_ends_every_device(tenant_a):
    client = _login(tenant_a.owner)
    _login(tenant_a.owner, ua=SAFARI_IPHONE, ip="198.51.100.7")
    assert client.post("/api/v1/auth/logout-all/").status_code == 200
    assert not UserSession.objects.filter(user=tenant_a.owner, revoked_at__isnull=True).exists()


def test_owner_sees_member_session_counts_not_details(tenant_a):
    owner = _login(tenant_a.owner)
    _login(tenant_a.staff)
    _login(tenant_a.staff, ua=SAFARI_IPHONE, ip="198.51.100.7")
    body = owner.get("/api/v1/company/users/session-counts/").json()["data"]
    assert body[str(tenant_a.staff.pk)] == 2
    assert all(isinstance(v, int) for v in body.values())
    staff = _login(tenant_a.staff)
    assert staff.get("/api/v1/company/users/session-counts/").status_code == 403


def test_every_refresh_cookie_is_tracked():
    views = (Path(__file__).resolve().parents[1] / "accounts" / "views.py").read_text(encoding="utf-8")
    calls = re.findall(r"^\s+_set_refresh_cookie\(response, [^)]*\)", views, flags=re.M)
    assert calls and all("request=request" in c for c in calls), calls
    assert settings.JWT_REFRESH_COOKIE_NAME


def test_ip_prefix_handles_mapped_ipv4_and_ports():
    from accounts.user_sessions import ip_prefix

    assert ip_prefix("::ffff:203.0.113.45") == "203.0.113.0/24"
    assert ip_prefix("203.0.113.45:5555") == "203.0.113.0/24"
    assert ip_prefix("[2001:db8::1]:443") == "2001:db8::/48"
    assert ip_prefix("not an ip") == ""


def test_switch_company_refuses_a_signed_out_refresh_token(tenant_a):
    """Review fix: a device the user signed out cannot get a fresh session from its access token
    through /auth/switch-company/ (its refresh token is blacklisted)."""
    client = _login(tenant_a.owner)
    row = UserSession.objects.filter(user=tenant_a.owner, revoked_at__isnull=True).latest("pk")
    owner = _login(tenant_a.owner, ua=SAFARI_IPHONE, ip="198.51.100.7")
    assert owner.post(f"/api/v1/auth/sessions/{row.pk}/revoke/").status_code == 200
    resp = client.post("/api/v1/auth/switch-company/", {"company_id": tenant_a.company.pk}, format="json")
    assert resp.status_code == 401, resp.content
    assert settings.JWT_REFRESH_COOKIE_NAME not in resp.cookies
    # Only the device that did the revoking is still signed in.
    assert list(UserSession.objects.filter(user=tenant_a.owner, revoked_at__isnull=True)
                .values_list("device_label", flat=True)) == ["Safari on iPhone"]


def test_logout_closes_this_device_session(tenant_a):
    client = _login(tenant_a.owner)
    assert UserSession.objects.filter(user=tenant_a.owner, revoked_at__isnull=True).count() == 1
    assert client.post("/api/v1/auth/logout/").status_code == 200
    assert not UserSession.objects.filter(user=tenant_a.owner, revoked_at__isnull=True).exists()


def test_a_device_signed_out_is_not_known_for_the_new_device_email(tenant_a, django_capture_on_commit_callbacks):
    _login(tenant_a.owner)
    phone = _login(tenant_a.owner, ua=SAFARI_IPHONE, ip="198.51.100.7")
    row = UserSession.objects.filter(user=tenant_a.owner, device_label="Safari on iPhone").latest("pk")
    assert phone.post(f"/api/v1/auth/sessions/{row.pk}/revoke/").status_code == 200
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        _login(tenant_a.owner, ua=SAFARI_IPHONE, ip="198.51.100.7")
    assert len(mail.outbox) == 1  # the signed-out device signing in again is reported


# --- Refresh rotation grace: a reload that aborted the refresh response must not sign the user out.


def _refresh_cookie(client):
    return client.cookies[settings.JWT_REFRESH_COOKIE_NAME].value


def _replay(client, raw):
    client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = raw
    return client.post("/api/v1/auth/refresh/", {}, format="json")


def test_a_reload_that_lost_the_rotated_cookie_keeps_the_user_signed_in(tenant_a):
    client = _login(tenant_a.owner)
    before = _refresh_cookie(client)
    assert client.post("/api/v1/auth/refresh/", {}, format="json").status_code == 200
    lost = _refresh_cookie(client)  # the browser never stored this one: the reload aborted the response

    resp = _replay(client, before)
    assert resp.status_code == 200, resp.content
    now = _refresh_cookie(client)
    assert now not in (before, lost)
    # Still one device; the token the browser never received is retired, the new one works.
    rows = list(UserSession.objects.filter(user=tenant_a.owner, revoked_at__isnull=True))
    assert len(rows) == 1
    assert _replay(client, lost).status_code == 401
    assert _replay(client, before).status_code == 401  # the grace is single use
    assert _replay(client, now).status_code == 200


def test_the_grace_does_not_outlive_its_window(tenant_a, settings):
    settings.REFRESH_REUSE_GRACE_SECONDS = 0
    client = _login(tenant_a.owner)
    before = _refresh_cookie(client)
    assert client.post("/api/v1/auth/refresh/", {}, format="json").status_code == 200
    assert _replay(client, before).status_code == 401


def test_a_rotated_token_replayed_from_another_device_is_refused(tenant_a):
    client = _login(tenant_a.owner)
    before = _refresh_cookie(client)
    assert client.post("/api/v1/auth/refresh/", {}, format="json").status_code == 200
    thief = APIClient(HTTP_USER_AGENT=SAFARI_IPHONE, REMOTE_ADDR="198.51.100.7")
    assert _replay(thief, before).status_code == 401


def test_a_signed_out_token_never_comes_back_through_the_grace(tenant_a):
    client = _login(tenant_a.owner)
    raw = _refresh_cookie(client)
    assert client.post("/api/v1/auth/logout/").status_code == 200
    assert _replay(client, raw).status_code == 401
