"""Edge cases for TOTP MFA (F-SEC-02). Complements test_mfa.py: key rotation, re-enrolment,
recovery-code exhaustion, token confusion, lockout behaviour and interaction with sessions."""

from __future__ import annotations

import base64
import time

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from accounts import mfa
from accounts.models import UserMfa
from core.models import AuditEvent

pytestmark = pytest.mark.django_db

PASSWORD = "StrongPass123!"


def _secret(user) -> str:
    return mfa.decrypt_secret(UserMfa.objects.get(user=user).secret_enc)


def _code(user, offset=0) -> str:
    return mfa.totp_at(_secret(user), time.time() + offset)


def _enrol(tenant):
    c = tenant.client
    assert c.post("/api/v1/auth/mfa/setup/", {"password": PASSWORD}, format="json").status_code == 200
    ok = c.post(
        "/api/v1/auth/mfa/confirm/",
        {"code": _code(tenant.owner), "password": PASSWORD},
        format="json",
    )
    assert ok.status_code == 200, ok.content
    return ok.data["recovery_codes"]


def _challenge(tenant):
    cache.clear()
    r = APIClient().post("/api/v1/auth/login/", {"email": tenant.owner.email, "password": PASSWORD}, format="json")
    assert r.status_code == 200 and r.data.get("mfa_required"), r.content
    return r.data["mfa_token"]


def _verify(token, **body):
    return APIClient().post("/api/v1/auth/mfa/verify/", {"mfa_token": token, **body}, format="json")


# --- primitives -----------------------------------------------------------------------

def test_provisioning_uri_is_url_encoded_and_names_the_issuer():
    uri = mfa.provisioning_uri("a+b@example.test", "ABCDEFGH")
    assert uri.startswith("otpauth://totp/BizBoard%3Aa%2Bb%40example.test?")
    assert "secret=ABCDEFGH" in uri and "issuer=BizBoard" in uri and "digits=6" in uri and "period=30" in uri


def test_qr_is_a_real_png():
    data = mfa.qr_png_data_uri("otpauth://totp/x?secret=ABC")
    assert data.startswith("data:image/png;base64,")
    assert base64.b64decode(data.split(",", 1)[1])[:8] == b"\x89PNG\r\n\x1a\n"


def test_generated_secrets_are_unique_base32_of_160_bits():
    secrets_ = {mfa.generate_secret() for _ in range(50)}
    assert len(secrets_) == 50
    for s in secrets_:
        assert len(s) == 32 and set(s) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")
        assert len(base64.b32decode(s)) == 20


def test_code_matching_ignores_spaces_and_dashes_users_type():
    now = 1_700_000_000
    code = mfa.totp_at("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", now)
    spaced = f"{code[:3]} {code[3:]}"
    assert mfa.verify_totp("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", spaced, now=now) is not None
    assert mfa.verify_totp("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", f"{code[:3]}-{code[3:]}", now=now) is not None


def test_secret_key_rotation_keeps_old_secrets_readable(settings):
    from cryptography.fernet import Fernet

    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    settings.MFA_ENCRYPTION_KEY = old
    token = mfa.encrypt_secret("ABCDEFGH")
    settings.MFA_ENCRYPTION_KEY = f"{new},{old}"          # rotate: newest first, old kept for reading
    assert mfa.decrypt_secret(token) == "ABCDEFGH"
    assert mfa.decrypt_secret(mfa.encrypt_secret("ZZZZ")) == "ZZZZ"   # new writes use the new key
    settings.MFA_ENCRYPTION_KEY = new                      # old key retired: old ciphertext now unreadable
    with pytest.raises(ValueError):
        mfa.decrypt_secret(token)


# --- enrolment ------------------------------------------------------------------------

def test_restarting_setup_replaces_the_secret_and_the_old_one_stops_working(tenant_a):
    c = tenant_a.client
    first = c.post("/api/v1/auth/mfa/setup/", {"password": PASSWORD}, format="json").data["secret"]
    second = c.post("/api/v1/auth/mfa/setup/", {"password": PASSWORD}, format="json").data["secret"]
    assert first != second
    stale = mfa.totp_at(first)
    assert c.post(
        "/api/v1/auth/mfa/confirm/", {"code": stale, "password": PASSWORD}, format="json",
    ).status_code == 400
    assert c.post(
        "/api/v1/auth/mfa/confirm/",
        {"code": mfa.totp_at(second), "password": PASSWORD},
        format="json",
    ).status_code == 200


def test_status_reports_pending_setup(tenant_a):
    tenant_a.client.post("/api/v1/auth/mfa/setup/", {"password": PASSWORD}, format="json")
    st = tenant_a.client.get("/api/v1/auth/mfa/status/").data
    assert st["pending_setup"] is True and st["enabled"] is False and st["recovery_codes_remaining"] == 0


def test_confirm_twice_is_refused_and_does_not_reissue_recovery_codes(tenant_a):
    _enrol(tenant_a)
    again = tenant_a.client.post(
        "/api/v1/auth/mfa/confirm/",
        {"code": _code(tenant_a.owner, 30), "password": PASSWORD},
        format="json",
    )
    assert again.status_code == 400 and "recovery_codes" not in again.data


def test_the_code_used_to_confirm_cannot_be_reused_to_log_in(tenant_a):
    _enrol(tenant_a)  # confirm consumed the current time step
    token = _challenge(tenant_a)
    assert _verify(token, code=_code(tenant_a.owner)).status_code == 401
    assert _verify(token, code=_code(tenant_a.owner, 30)).status_code == 200


def test_a_user_can_only_enrol_themselves(tenant_a, tenant_b):
    _enrol(tenant_a)
    assert UserMfa.objects.filter(user=tenant_b.owner).count() == 0
    assert tenant_b.client.get("/api/v1/auth/mfa/status/").data["enabled"] is False


# --- login --------------------------------------------------------------------------

def test_drift_of_one_step_either_way_is_accepted_two_steps_is_not(tenant_a):
    _enrol(tenant_a)
    assert _verify(_challenge(tenant_a), code=_code(tenant_a.owner, 30)).status_code == 200
    assert _verify(_challenge(tenant_a), code=_code(tenant_a.owner, 90)).status_code == 401


def test_a_deactivated_user_cannot_finish_a_login(tenant_a):
    _enrol(tenant_a)
    token = _challenge(tenant_a)
    tenant_a.owner.is_active = False
    tenant_a.owner.save(update_fields=["is_active"])
    assert _verify(token, code=_code(tenant_a.owner, 30)).status_code == 401


def test_other_signed_tokens_cannot_be_used_as_an_mfa_token(tenant_a):
    """Same SECRET_KEY, different salt: an invite token must not unlock the second step."""
    from django.core import signing

    _enrol(tenant_a)
    invite_like = signing.dumps({"uid": tenant_a.owner.pk}, salt="bizboard.invite.v1")
    assert _verify(invite_like, code=_code(tenant_a.owner, 30)).status_code == 401


def test_missing_or_blank_inputs_are_rejected_not_500(tenant_a):
    _enrol(tenant_a)
    token = _challenge(tenant_a)
    assert _verify("", code="123456").status_code == 401
    assert _verify(token).status_code == 401                       # no code at all
    assert _verify(token, code="").status_code == 401
    assert _verify(token, recovery_code="").status_code == 401
    assert _verify(token, code=None).status_code == 401


def test_a_successful_login_clears_the_failure_counter(tenant_a):
    _enrol(tenant_a)
    token = _challenge(tenant_a)
    for _ in range(4):
        assert _verify(token, code="000000").status_code == 401
    assert cache.get(f"mfa_fail:{tenant_a.owner.pk}") == 4
    assert _verify(token, code=_code(tenant_a.owner, 30)).status_code == 200
    assert cache.get(f"mfa_fail:{tenant_a.owner.pk}") is None


def test_session_cookies_from_mfa_login_work_and_refresh_still_functions(tenant_a):
    _enrol(tenant_a)
    token = _challenge(tenant_a)
    client = APIClient()
    r = client.post("/api/v1/auth/mfa/verify/", {"mfa_token": token, "code": _code(tenant_a.owner, 30)}, format="json")
    assert r.status_code == 200
    for name, morsel in r.cookies.items():
        client.cookies[name] = morsel.value
    me = client.get("/api/v1/auth/me/")
    assert me.status_code == 200 and me.data["email"] == tenant_a.owner.email
    refreshed = client.post("/api/v1/auth/refresh/", {}, format="json")
    assert refreshed.status_code == 200, refreshed.content


def test_logging_in_again_requires_the_second_factor_again(tenant_a):
    _enrol(tenant_a)
    assert _verify(_challenge(tenant_a), code=_code(tenant_a.owner, 30)).status_code == 200
    again = APIClient().post("/api/v1/auth/login/", {"email": tenant_a.owner.email, "password": PASSWORD}, format="json")
    assert again.data.get("mfa_required") is True and not again.cookies.get("bb_access")


def test_login_audit_is_written_only_after_the_second_factor(tenant_a):
    _enrol(tenant_a)
    AuditEvent.objects.filter(user=tenant_a.owner, action="LOGIN").exists()  # baseline: none from enrolment
    token = _challenge(tenant_a)
    assert not AuditEvent.objects.filter(user=tenant_a.owner, action="LOGIN").exists()
    assert _verify(token, code=_code(tenant_a.owner, 30)).status_code == 200
    assert AuditEvent.objects.filter(user=tenant_a.owner, action="LOGIN").count() == 1


# --- recovery codes ----------------------------------------------------------------------

def test_all_recovery_codes_work_once_and_then_none_are_left(tenant_a):
    codes = _enrol(tenant_a)
    assert len(codes) == mfa.RECOVERY_CODE_COUNT
    for i, code in enumerate(codes, start=1):
        assert _verify(_challenge(tenant_a), recovery_code=code).status_code == 200, f"code {i}"
        assert len(UserMfa.objects.get(user=tenant_a.owner).recovery_hashes) == mfa.RECOVERY_CODE_COUNT - i
    assert _verify(_challenge(tenant_a), recovery_code=codes[0]).status_code == 401
    assert tenant_a.client.get("/api/v1/auth/mfa/status/").data["recovery_codes_remaining"] == 0


def test_recovery_codes_are_never_stored_in_clear(tenant_a):
    codes = _enrol(tenant_a)
    stored = " ".join(UserMfa.objects.get(user=tenant_a.owner).recovery_hashes)
    assert all(c.replace("-", "") not in stored for c in codes)


def test_a_recovery_code_does_not_work_as_a_totp_code_and_vice_versa(tenant_a):
    codes = _enrol(tenant_a)
    token = _challenge(tenant_a)
    assert _verify(token, code=codes[0]).status_code == 401
    assert _verify(token, recovery_code=_code(tenant_a.owner, 30)).status_code == 401


# --- disabling / regenerating ----------------------------------------------------------

def test_reauth_failures_lock_after_five_wrong_codes(tenant_a):
    _enrol(tenant_a)
    for _ in range(5):
        r = tenant_a.client.post("/api/v1/auth/mfa/disable/", {"password": PASSWORD, "code": "000000"}, format="json")
        assert r.status_code == 400
    locked = tenant_a.client.post(
        "/api/v1/auth/mfa/disable/", {"password": PASSWORD, "code": _code(tenant_a.owner, 30)}, format="json"
    )
    assert locked.status_code == 429
    assert UserMfa.objects.filter(user=tenant_a.owner).exists(), "a locked attempt must not disable MFA"


def test_a_recovery_code_can_authorise_disabling(tenant_a):
    codes = _enrol(tenant_a)
    r = tenant_a.client.post("/api/v1/auth/mfa/disable/", {"password": PASSWORD, "recovery_code": codes[3]}, format="json")
    assert r.status_code == 200
    assert not UserMfa.objects.filter(user=tenant_a.owner).exists()


def test_disable_when_not_enabled_is_a_clear_400(tenant_a):
    r = tenant_a.client.post("/api/v1/auth/mfa/disable/", {"password": PASSWORD, "code": "123456"}, format="json")
    assert r.status_code == 400


def test_regenerated_codes_are_audited(tenant_a):
    _enrol(tenant_a)
    r = tenant_a.client.post(
        "/api/v1/auth/mfa/recovery-codes/", {"password": PASSWORD, "code": _code(tenant_a.owner, 30)}, format="json"
    )
    assert r.status_code == 200
    assert AuditEvent.objects.filter(user=tenant_a.owner, action="MFA_RECOVERY_CODES_REGENERATED").exists()


# --- contract -------------------------------------------------------------------------------

def test_mfa_routes_are_in_the_openapi_schema():
    """The OpenAPI snapshot (CI drift check) and the generated web types come from this schema."""
    from drf_spectacular.generators import SchemaGenerator

    paths = SchemaGenerator().get_schema(request=None, public=True)["paths"]
    for name in ("status", "setup", "confirm", "disable", "recovery-codes", "verify"):
        assert f"/api/v1/auth/mfa/{name}/" in paths, name


def test_the_committed_openapi_snapshot_includes_the_mfa_routes():
    import json
    import pathlib

    snap = json.loads((pathlib.Path(__file__).resolve().parents[2] / "docs" / "openapi-snapshot.json").read_text(encoding="utf-8"))
    for name in ("status", "setup", "confirm", "disable", "recovery-codes", "verify"):
        assert f"/api/v1/auth/mfa/{name}/" in snap["paths"], f"regenerate docs/openapi-snapshot.json: {name} missing"
