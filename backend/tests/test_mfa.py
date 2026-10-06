"""TOTP multi-factor authentication (F-SEC-02)."""

from __future__ import annotations

import time

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from accounts import mfa
from accounts.models import UserMfa
from core.models import AuditEvent

pytestmark = pytest.mark.django_db

PASSWORD = "StrongPass123!"


# --- RFC 6238 test vectors (SHA-1, secret "12345678901234567890") ------------------

RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # base32 of the ASCII secret above


@pytest.mark.parametrize("t,expected", [
    (59, "287082"),
    (1111111109, "081804"),
    (1111111111, "050471"),
    (1234567890, "005924"),
    (2000000000, "279037"),
    (20000000000, "353130"),
])
def test_totp_matches_rfc6238_vectors(t, expected):
    assert mfa.totp_at(RFC_SECRET, t) == expected


def test_verify_accepts_window_and_rejects_outside_it():
    now = 1_700_000_000
    cur = mfa.totp_at(RFC_SECRET, now)
    assert mfa.verify_totp(RFC_SECRET, cur, now=now) is not None
    assert mfa.verify_totp(RFC_SECRET, mfa.totp_at(RFC_SECRET, now - 30), now=now) is not None   # previous step
    assert mfa.verify_totp(RFC_SECRET, mfa.totp_at(RFC_SECRET, now + 30), now=now) is not None   # next step
    assert mfa.verify_totp(RFC_SECRET, mfa.totp_at(RFC_SECRET, now - 120), now=now) is None      # too old
    assert mfa.verify_totp(RFC_SECRET, "12345", now=now) is None                                  # wrong length
    assert mfa.verify_totp(RFC_SECRET, "", now=now) is None


def test_a_used_step_cannot_be_replayed():
    now = 1_700_000_000
    code = mfa.totp_at(RFC_SECRET, now)
    step = mfa.verify_totp(RFC_SECRET, code, now=now)
    assert step is not None
    assert mfa.verify_totp(RFC_SECRET, code, last_used_step=step, now=now) is None


def test_secret_is_encrypted_at_rest_and_round_trips():
    secret = mfa.generate_secret()
    enc = mfa.encrypt_secret(secret)
    assert secret not in enc
    assert mfa.decrypt_secret(enc) == secret


def test_decrypt_with_wrong_key_fails_closed(settings):
    enc = mfa.encrypt_secret(mfa.generate_secret())
    settings.SECRET_KEY = "a-completely-different-secret-key-for-this-test-0123456789"
    with pytest.raises(ValueError):
        mfa.decrypt_secret(enc)


def test_recovery_codes_are_single_use_and_stored_hashed():
    codes, hashes = mfa.new_recovery_codes()
    assert len(codes) == mfa.RECOVERY_CODE_COUNT and len(set(codes)) == len(codes)
    assert all(c not in "".join(hashes) for c in codes)
    left = mfa.consume_recovery_code(hashes, codes[0])
    assert left is not None and len(left) == len(hashes) - 1
    assert mfa.consume_recovery_code(left, codes[0]) is None            # already used
    assert mfa.consume_recovery_code(hashes, codes[1].lower()) is not None   # case-insensitive
    assert mfa.consume_recovery_code(hashes, "AAAAA-AAAAA") is None


# --- API flow -----------------------------------------------------------------------

def _current_code(user) -> str:
    rec = UserMfa.objects.get(user=user)
    return mfa.totp_at(mfa.decrypt_secret(rec.secret_enc))


def _next_step_code(user) -> str:
    """A valid code for the NEXT step, so a second login right after enrolment is not a replay."""
    rec = UserMfa.objects.get(user=user)
    return mfa.totp_at(mfa.decrypt_secret(rec.secret_enc), time.time() + 30)


def _enrol(tenant):
    c = tenant.client
    setup = c.post("/api/v1/auth/mfa/setup/", {"password": PASSWORD}, format="json")
    assert setup.status_code == 200, setup.content
    confirm = c.post(
        "/api/v1/auth/mfa/confirm/",
        {"code": _current_code(tenant.owner), "password": PASSWORD},
        format="json",
    )
    assert confirm.status_code == 200, confirm.content
    return setup.data, confirm.data["recovery_codes"]


def _login(tenant, password=PASSWORD):
    cache.clear()
    return APIClient().post(
        "/api/v1/auth/login/", {"email": tenant.owner.email, "password": password}, format="json"
    )


def test_login_without_mfa_is_unchanged(tenant_a):
    r = _login(tenant_a)
    assert r.status_code == 200
    assert "mfa_required" not in r.data
    assert r.cookies.get("bb_access") is not None


def test_setup_returns_secret_uri_and_qr_but_enforces_nothing_yet(tenant_a):
    r = tenant_a.client.post("/api/v1/auth/mfa/setup/", {"password": PASSWORD}, format="json")
    assert r.status_code == 200
    assert r.data["otpauth_uri"].startswith("otpauth://totp/")
    assert r.data["qr_png"].startswith("data:image/png;base64,")
    assert r.data["secret"] not in UserMfa.objects.get(user=tenant_a.owner).secret_enc
    # pending setup must not change login behaviour
    login = _login(tenant_a)
    assert login.status_code == 200 and "mfa_required" not in login.data


def test_confirm_rejects_a_wrong_code_and_accepts_the_right_one(tenant_a):
    tenant_a.client.post("/api/v1/auth/mfa/setup/", {"password": PASSWORD}, format="json")
    bad = tenant_a.client.post(
        "/api/v1/auth/mfa/confirm/", {"code": "000000", "password": PASSWORD}, format="json",
    )
    assert bad.status_code == 400
    assert not UserMfa.objects.get(user=tenant_a.owner).is_active
    ok = tenant_a.client.post(
        "/api/v1/auth/mfa/confirm/",
        {"code": _current_code(tenant_a.owner), "password": PASSWORD},
        format="json",
    )
    assert ok.status_code == 200 and len(ok.data["recovery_codes"]) == mfa.RECOVERY_CODE_COUNT
    assert UserMfa.objects.get(user=tenant_a.owner).is_active
    assert AuditEvent.objects.filter(user=tenant_a.owner, action="MFA_ENABLED").exists()


def test_password_login_with_mfa_issues_no_session(tenant_a):
    _enrol(tenant_a)
    r = _login(tenant_a)
    assert r.status_code == 200
    assert r.data["mfa_required"] is True and r.data["mfa_token"]
    assert not r.cookies.get("bb_access") and not r.cookies.get("bb_refresh")
    assert "access" not in r.data and "refresh" not in r.data and "user" not in r.data
    assert not AuditEvent.objects.filter(user=tenant_a.owner, action="LOGIN").exists()


def test_correct_code_completes_login_with_a_normal_session(tenant_a):
    _enrol(tenant_a)
    r = _login(tenant_a)
    token = r.data["mfa_token"]
    v = APIClient().post(
        "/api/v1/auth/mfa/verify/", {"mfa_token": token, "code": _next_step_code(tenant_a.owner)}, format="json"
    )
    assert v.status_code == 200, v.content
    assert v.cookies.get("bb_access") and v.cookies.get("bb_refresh")
    assert v.data["user"]["email"] == tenant_a.owner.email
    assert AuditEvent.objects.filter(user=tenant_a.owner, action="LOGIN").exists()


def test_a_code_cannot_be_used_twice(tenant_a):
    _enrol(tenant_a)
    token = _login(tenant_a).data["mfa_token"]
    code = _next_step_code(tenant_a.owner)
    c = APIClient()
    assert c.post("/api/v1/auth/mfa/verify/", {"mfa_token": token, "code": code}, format="json").status_code == 200
    again = APIClient().post("/api/v1/auth/mfa/verify/", {"mfa_token": token, "code": code}, format="json")
    assert again.status_code == 401


def test_wrong_code_is_rejected_and_five_failures_lock_the_second_factor(tenant_a):
    _enrol(tenant_a)
    token = _login(tenant_a).data["mfa_token"]
    c = APIClient()
    for _ in range(5):
        r = c.post("/api/v1/auth/mfa/verify/", {"mfa_token": token, "code": "000000"}, format="json")
        assert r.status_code == 401
    locked = c.post("/api/v1/auth/mfa/verify/", {"mfa_token": token, "code": _next_step_code(tenant_a.owner)}, format="json")
    assert locked.status_code == 429  # even the right code is refused while locked


def test_forged_or_expired_mfa_token_is_rejected(tenant_a, monkeypatch):
    _enrol(tenant_a)
    c = APIClient()
    assert c.post("/api/v1/auth/mfa/verify/", {"mfa_token": "garbage", "code": "123456"}, format="json").status_code == 401
    token = _login(tenant_a).data["mfa_token"]
    from accounts import mfa_service

    monkeypatch.setattr(mfa_service, "MFA_TOKEN_MAX_AGE", -1)
    r = c.post("/api/v1/auth/mfa/verify/", {"mfa_token": token, "code": _next_step_code(tenant_a.owner)}, format="json")
    assert r.status_code == 401


def test_recovery_code_logs_in_once_then_is_burned(tenant_a):
    _, codes = _enrol(tenant_a)
    token = _login(tenant_a).data["mfa_token"]
    c = APIClient()
    ok = c.post("/api/v1/auth/mfa/verify/", {"mfa_token": token, "recovery_code": codes[0]}, format="json")
    assert ok.status_code == 200
    assert UserMfa.objects.get(user=tenant_a.owner).recovery_hashes.__len__() == mfa.RECOVERY_CODE_COUNT - 1
    token2 = _login(tenant_a).data["mfa_token"]
    again = APIClient().post("/api/v1/auth/mfa/verify/", {"mfa_token": token2, "recovery_code": codes[0]}, format="json")
    assert again.status_code == 401


def test_disable_needs_password_and_a_valid_second_factor(tenant_a):
    _enrol(tenant_a)
    c = tenant_a.client
    no_pw = c.post("/api/v1/auth/mfa/disable/", {"password": "wrong", "code": _next_step_code(tenant_a.owner)}, format="json")
    assert no_pw.status_code == 400
    no_code = c.post("/api/v1/auth/mfa/disable/", {"password": PASSWORD, "code": "000000"}, format="json")
    assert no_code.status_code == 400
    assert UserMfa.objects.filter(user=tenant_a.owner).exists()
    ok = c.post("/api/v1/auth/mfa/disable/", {"password": PASSWORD, "code": _next_step_code(tenant_a.owner)}, format="json")
    assert ok.status_code == 200
    assert not UserMfa.objects.filter(user=tenant_a.owner).exists()
    assert AuditEvent.objects.filter(user=tenant_a.owner, action="MFA_DISABLED").exists()
    assert "mfa_required" not in _login(tenant_a).data


def test_regenerating_recovery_codes_invalidates_the_old_ones(tenant_a):
    _, old = _enrol(tenant_a)
    r = tenant_a.client.post(
        "/api/v1/auth/mfa/recovery-codes/", {"password": PASSWORD, "code": _next_step_code(tenant_a.owner)}, format="json"
    )
    assert r.status_code == 200 and set(r.data["recovery_codes"]).isdisjoint(old)
    token = _login(tenant_a).data["mfa_token"]
    bad = APIClient().post("/api/v1/auth/mfa/verify/", {"mfa_token": token, "recovery_code": old[0]}, format="json")
    assert bad.status_code == 401


def test_setup_is_refused_while_enabled_and_status_reports_state(tenant_a):
    assert tenant_a.client.get("/api/v1/auth/mfa/status/").data["enabled"] is False
    _enrol(tenant_a)
    st = tenant_a.client.get("/api/v1/auth/mfa/status/").data
    assert st["enabled"] is True and st["recovery_codes_remaining"] == mfa.RECOVERY_CODE_COUNT
    assert tenant_a.client.post(
        "/api/v1/auth/mfa/setup/", {"password": PASSWORD}, format="json",
    ).status_code == 400


def test_mfa_endpoints_need_authentication_except_verify():
    c = APIClient()
    for path in ("status", "setup", "confirm", "disable", "recovery-codes"):
        r = c.get(f"/api/v1/auth/mfa/{path}/") if path == "status" else c.post(f"/api/v1/auth/mfa/{path}/", {}, format="json")
        assert r.status_code in (401, 403), path


def test_one_users_mfa_does_not_affect_another(tenant_a, tenant_b):
    _enrol(tenant_a)
    r = _login(tenant_b)
    assert r.status_code == 200 and "mfa_required" not in r.data


# --- paths that mint a session from ONE factor must not bypass MFA --------------------

def test_phone_otp_login_does_not_bypass_mfa(tenant_a, monkeypatch):
    from accounts.otp_utils import phone_lookup_values  # noqa: F401  (import check)

    _enrol(tenant_a)
    monkeypatch.setattr("accounts.views.secrets.randbelow", lambda n: 123456)
    monkeypatch.setattr("django.conf.settings.OTP_ENABLED", True)
    monkeypatch.setattr("django.conf.settings.SMS_PROVIDER", "console")
    c = APIClient()
    assert c.post("/api/v1/auth/otp/request/", {"phone": tenant_a.owner.phone}, format="json").status_code == 200
    r = c.post("/api/v1/auth/otp/verify/", {"phone": tenant_a.owner.phone, "code": "123456"}, format="json")
    assert r.status_code == 200
    assert r.data.get("mfa_required") is True and r.data.get("mfa_token")
    assert not r.cookies.get("bb_access") and not r.cookies.get("bb_refresh")
    assert "access" not in r.data and "user" not in r.data
    # and the challenge it hands out completes with a valid authenticator code
    v = APIClient().post(
        "/api/v1/auth/mfa/verify/",
        {"mfa_token": r.data["mfa_token"], "code": _next_step_code(tenant_a.owner)}, format="json",
    )
    assert v.status_code == 200 and v.cookies.get("bb_access")


def test_phone_otp_login_without_mfa_still_works(tenant_a, monkeypatch):
    monkeypatch.setattr("accounts.views.secrets.randbelow", lambda n: 123456)
    monkeypatch.setattr("django.conf.settings.OTP_ENABLED", True)
    monkeypatch.setattr("django.conf.settings.SMS_PROVIDER", "console")
    c = APIClient()
    c.post("/api/v1/auth/otp/request/", {"phone": tenant_a.owner.phone}, format="json")
    r = c.post("/api/v1/auth/otp/verify/", {"phone": tenant_a.owner.phone, "code": "123456"}, format="json")
    assert r.status_code == 200 and "mfa_required" not in r.data and r.cookies.get("bb_access")


def test_invite_acceptance_does_not_mint_a_session_for_an_mfa_account(tenant_a, tenant_b):
    """An existing MFA user accepting an invite to ANOTHER company proves only their password
    there; no session until they sign in (with the authenticator)."""
    from accounts.models import CompanyUser
    from accounts.views import _make_invite_token

    _enrol(tenant_a)
    membership = CompanyUser.objects.create(
        company=tenant_b.company, user=tenant_a.owner, role=CompanyUser.Role.SALES_STAFF, is_active=False,
    )
    token = _make_invite_token(user_id=tenant_a.owner.pk, company_id=tenant_b.company.pk, membership_id=membership.pk)
    r = APIClient().post(
        "/api/v1/auth/invite/accept/", {"token": token, "password": PASSWORD}, format="json"
    )
    assert r.status_code == 200, r.content
    assert r.data.get("mfa_required") is True
    assert not r.cookies.get("bb_access") and not r.cookies.get("bb_refresh")
    assert "access" not in r.data and "user" not in r.data
    membership.refresh_from_db()
    assert membership.is_active, "membership is still activated; only the session is withheld"


def _invite(user, company, role="SALES_STAFF"):
    from accounts.models import CompanyUser
    from accounts.views import _make_invite_token

    membership = CompanyUser.objects.create(
        company=company, user=user, role=role, is_active=False,
    )
    token = _make_invite_token(user_id=user.pk, company_id=company.pk, membership_id=membership.pk)
    return membership, token


def test_authenticated_invite_without_a_code_does_not_mint_a_session(tenant_a, tenant_b):
    _enrol(tenant_a)
    _membership, token = _invite(tenant_a.owner, tenant_b.company)
    r = tenant_a.client.post(
        "/api/v1/auth/invite/accept/", {"token": token, "password": PASSWORD}, format="json",
    )
    assert r.status_code == 200, r.content
    assert r.data.get("mfa_required") is True and r.data.get("mfa_token")
    assert not r.cookies.get("bb_access") and not r.cookies.get("bb_refresh")
    _membership.refresh_from_db()
    assert _membership.is_active


def test_authenticated_invite_with_a_valid_code_issues_a_session(tenant_a, tenant_b):
    _enrol(tenant_a)
    _membership, token = _invite(tenant_a.owner, tenant_b.company)
    r = tenant_a.client.post(
        "/api/v1/auth/invite/accept/",
        {"token": token, "password": PASSWORD, "code": _next_step_code(tenant_a.owner)},
        format="json",
    )
    assert r.status_code == 200, r.content
    assert r.cookies.get("bb_refresh")
    assert r.data.get("mfa_required") is not True


def test_replayed_invite_totp_does_not_mint_another_session(tenant_a, tenant_b):
    from accounts.models import Company

    _enrol(tenant_a)
    code = _next_step_code(tenant_a.owner)
    _first, token = _invite(tenant_a.owner, tenant_b.company)
    ok = tenant_a.client.post(
        "/api/v1/auth/invite/accept/",
        {"token": token, "password": PASSWORD, "code": code},
        format="json",
    )
    assert ok.status_code == 200 and ok.cookies.get("bb_refresh"), ok.content
    other = Company.objects.create(name="Third", state="Karnataka", gstin="29BBBBB0000B1Z5")
    _second, token2 = _invite(tenant_a.owner, other)
    replay = tenant_a.client.post(
        "/api/v1/auth/invite/accept/",
        {"token": token2, "password": PASSWORD, "code": code},
        format="json",
    )
    assert replay.status_code == 200, replay.content
    assert replay.data.get("mfa_required") is True
    assert not replay.cookies.get("bb_refresh")


def test_authenticated_invite_without_mfa_still_issues_a_session(tenant_a, tenant_b):
    _membership, token = _invite(tenant_a.owner, tenant_b.company)
    r = tenant_a.client.post(
        "/api/v1/auth/invite/accept/", {"token": token, "password": PASSWORD}, format="json",
    )
    assert r.status_code == 200, r.content
    assert "mfa_required" not in r.data
    assert r.cookies.get("bb_refresh")


def test_flag_off_owner_login_still_sets_cookies(settings, tenant_a):
    settings.MFA_ENFORCE_FOR_MONEY_ROLES = False
    r = _login(tenant_a)
    assert r.status_code == 200 and r.cookies.get("bb_access")
    assert "mfa_enrollment_required" not in r.data


def test_flag_on_owner_without_mfa_must_enrol(settings, tenant_a):
    settings.MFA_ENFORCE_FOR_MONEY_ROLES = True
    r = _login(tenant_a)
    assert r.status_code == 200, r.content
    assert r.data.get("mfa_enrollment_required") is True and r.data.get("enrol_token")
    assert not r.cookies.get("bb_access") and not r.cookies.get("bb_refresh")


def test_flag_on_accountant_must_enrol(settings, tenant_a):
    from accounts.models import CompanyUser, User

    accountant = User.objects.create_user(email="acct@alpha.test", password=PASSWORD, full_name="Acct")
    CompanyUser.objects.create(company=tenant_a.company, user=accountant, role=CompanyUser.Role.ACCOUNTANT)
    settings.MFA_ENFORCE_FOR_MONEY_ROLES = True
    r = APIClient().post("/api/v1/auth/login/", {"email": accountant.email, "password": PASSWORD}, format="json")
    assert r.status_code == 200 and r.data.get("mfa_enrollment_required") is True
    assert not r.cookies.get("bb_refresh")


def test_flag_on_owner_who_is_only_a_viewer_elsewhere_must_enrol(settings, tenant_a, tenant_b):
    from accounts.models import CompanyUser

    CompanyUser.objects.create(
        company=tenant_b.company, user=tenant_a.owner, role=CompanyUser.Role.VIEWER, is_active=True,
    )
    settings.MFA_ENFORCE_FOR_MONEY_ROLES = True
    r = _login(tenant_a)
    assert r.data.get("mfa_enrollment_required") is True
    assert not r.cookies.get("bb_refresh")


def test_flag_on_journal_poster_must_enrol(settings, tenant_a):
    from accounts.models import CompanyUser, User

    manager = User.objects.create_user(email="mgr@alpha.test", password=PASSWORD, full_name="Mgr")
    CompanyUser.objects.create(
        company=tenant_a.company, user=manager, role=CompanyUser.Role.MANAGER, can_post_journals=True,
    )
    settings.MFA_ENFORCE_FOR_MONEY_ROLES = True
    r = APIClient().post("/api/v1/auth/login/", {"email": manager.email, "password": PASSWORD}, format="json")
    assert r.status_code == 200, r.content
    assert r.data.get("mfa_enrollment_required") is True
    assert not r.cookies.get("bb_access") and not r.cookies.get("bb_refresh")


def test_flag_on_sales_staff_still_gets_a_session(settings, tenant_a):
    settings.MFA_ENFORCE_FOR_MONEY_ROLES = True
    r = APIClient().post(
        "/api/v1/auth/login/", {"email": tenant_a.staff.email, "password": PASSWORD}, format="json",
    )
    assert r.status_code == 200, r.content
    assert "mfa_enrollment_required" not in r.data
    assert r.cookies.get("bb_refresh")


def test_flag_on_owner_with_mfa_still_needs_the_second_factor(settings, tenant_a):
    settings.MFA_ENFORCE_FOR_MONEY_ROLES = True
    _enrol(tenant_a)
    r = _login(tenant_a)
    assert r.data.get("mfa_required") is True
    assert "mfa_enrollment_required" not in r.data
    assert not r.cookies.get("bb_refresh")
    done = APIClient().post(
        "/api/v1/auth/mfa/verify/",
        {"mfa_token": r.data["mfa_token"], "code": _next_step_code(tenant_a.owner)},
        format="json",
    )
    assert done.status_code == 200 and done.cookies.get("bb_refresh"), done.content


def test_production_enforce_off_without_waiver_is_misconfigured():
    from django.core.exceptions import ImproperlyConfigured

    from config.settings import _assert_mfa_enforcement

    with pytest.raises(ImproperlyConfigured):
        _assert_mfa_enforcement(django_env="production", enforce=False, waiver=False)
    _assert_mfa_enforcement(django_env="production", enforce=False, waiver=True)
    _assert_mfa_enforcement(django_env="staging", enforce=True, waiver=False)


def test_deploy_check_errors_when_enforcement_is_on_and_the_key_is_empty(settings):
    from django.core.checks import run_checks

    settings.MFA_ENFORCE_FOR_MONEY_ROLES = True
    settings.MFA_ENCRYPTION_KEY = ""
    errors = [item for item in run_checks(include_deployment_checks=True) if item.id == "accounts.E001"]
    assert errors


def test_enrol_token_is_not_a_session(settings, tenant_a):
    settings.MFA_ENFORCE_FOR_MONEY_ROLES = True
    token = _login(tenant_a).data["enrol_token"]
    anonymous = APIClient()
    get_invoices = anonymous.get("/api/v1/sales/invoices/", {"enrol_token": token})
    post_invoices = anonymous.post(
        "/api/v1/sales/invoices/", {"enrol_token": token}, format="json",
    )
    assert get_invoices.status_code in (401, 403)
    assert post_invoices.status_code in (401, 403)


def test_enrol_token_setup_confirm_cap_and_burn(settings, tenant_a):
    settings.MFA_ENFORCE_FOR_MONEY_ROLES = True
    token = _login(tenant_a).data["enrol_token"]
    client = APIClient()
    for n in range(8):
        setup = client.post("/api/v1/auth/mfa/setup/", {"enrol_token": token}, format="json")
        assert setup.status_code == 200, (n, setup.content)
    ninth = client.post("/api/v1/auth/mfa/setup/", {"enrol_token": token}, format="json")
    assert ninth.status_code == 401

    fresh = _login(tenant_a).data["enrol_token"]
    setup = client.post("/api/v1/auth/mfa/setup/", {"enrol_token": fresh}, format="json")
    assert setup.status_code == 200, setup.content
    code = mfa.totp_at(setup.data["secret"])
    confirm = client.post(
        "/api/v1/auth/mfa/confirm/", {"enrol_token": fresh, "code": code}, format="json",
    )
    assert confirm.status_code == 200, confirm.content
    assert confirm.data["recovery_codes"]
    burned = client.post("/api/v1/auth/mfa/setup/", {"enrol_token": fresh}, format="json")
    assert burned.status_code == 401
    again = _login(tenant_a)
    assert again.data.get("mfa_required") is True
    assert not again.cookies.get("bb_refresh")


def test_refresh_for_a_money_role_without_mfa_cannot_be_reused(settings, tenant_a):
    from django.conf import settings as dj_settings

    settings.MFA_ENFORCE_FOR_MONEY_ROLES = False
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/", {"email": tenant_a.owner.email, "password": PASSWORD}, format="json",
    )
    cookie = login.cookies[dj_settings.JWT_REFRESH_COOKIE_NAME].value
    settings.MFA_ENFORCE_FOR_MONEY_ROLES = True
    client.cookies[dj_settings.JWT_REFRESH_COOKIE_NAME] = cookie
    refreshed = client.post("/api/v1/auth/refresh/", {}, format="json")
    # A refresh cookie alone must not hand out an enrol token (a stolen cookie could then bind the
    # attacker's authenticator). The user signs in again; the password login issues the enrol token.
    assert refreshed.status_code == 401, refreshed.content
    assert b"enrol" not in refreshed.content.lower().replace(b"two-step", b"")
    assert not refreshed.cookies.get(dj_settings.JWT_REFRESH_COOKIE_NAME)
    reuse = APIClient()
    reuse.cookies[dj_settings.JWT_REFRESH_COOKIE_NAME] = cookie
    assert reuse.post("/api/v1/auth/refresh/", {}, format="json").status_code == 401


def test_session_issuers_are_only_the_known_call_sites():
    from pathlib import Path

    views = (Path(__file__).resolve().parents[1] / "accounts" / "views.py").read_text(encoding="utf-8")
    mfa_views = (Path(__file__).resolve().parents[1] / "accounts" / "mfa_views.py").read_text(encoding="utf-8")
    # def + CookieTokenRefreshView + VerifyOtpView + SwitchCompanyView + AcceptInviteView
    assert views.count("_tokens_for_user(") == 5, views.count("_tokens_for_user(")
    # def + LoginView. MfaLoginVerifyView is the only other session completion.
    assert views.count("_complete_login(") == 2, views.count("_complete_login(")
    assert mfa_views.count("_complete_login(") == 1
    assert mfa_views.count("_tokens_for_user(") == 0


def test_reencrypt_then_drop_the_old_key(settings):
    import base64
    import hashlib

    from cryptography.fernet import Fernet
    from django.core.management import call_command

    from accounts.models import User

    secret = mfa.generate_secret()
    settings.MFA_ENCRYPTION_KEY = ""
    stored = mfa.encrypt_secret(secret)
    derived_key = base64.urlsafe_b64encode(
        hashlib.sha256(("bizboard-mfa|" + settings.SECRET_KEY).encode("utf-8")).digest()
    ).decode("ascii")
    new_key = Fernet.generate_key().decode("ascii")
    settings.MFA_ENCRYPTION_KEY = new_key
    with pytest.raises(ValueError):
        mfa.decrypt_secret(stored)
    settings.MFA_ENCRYPTION_KEY = f"{new_key},{derived_key}"
    assert mfa.decrypt_secret(stored) == secret
    user = User.objects.create_user(email="reencrypt@alpha.test", password=PASSWORD, full_name="Re")
    UserMfa.objects.create(user=user, secret_enc=stored)
    call_command("reencrypt_mfa_secrets")
    settings.MFA_ENCRYPTION_KEY = new_key
    assert mfa.decrypt_secret(UserMfa.objects.get(user=user).secret_enc) == secret


def test_reset_user_mfa_deletes_the_row_and_blacklists_refresh(tenant_a):
    from django.core.management import call_command
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

    _enrol(tenant_a)
    login = _login(tenant_a)
    done = APIClient().post(
        "/api/v1/auth/mfa/verify/",
        {"mfa_token": login.data["mfa_token"], "code": _next_step_code(tenant_a.owner)},
        format="json",
    )
    assert done.status_code == 200, done.content
    call_command("reset_user_mfa", email=tenant_a.owner.email)
    assert not UserMfa.objects.filter(user=tenant_a.owner).exists()
    outstanding = OutstandingToken.objects.filter(user=tenant_a.owner)
    assert outstanding.exists()
    assert BlacklistedToken.objects.filter(token__in=outstanding).count() == outstanding.count()
