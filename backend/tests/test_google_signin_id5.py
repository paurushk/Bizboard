"""WP-ID5: Sign in with Google — token checks, same MFA as a password sign-in, sign-up rules."""

import time
from unittest import mock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.test import override_settings
from rest_framework.test import APIClient

from accounts.models import Company, LegalAcceptance, User

pytestmark = pytest.mark.django_db

CLIENT_ID = "test-client.apps.googleusercontent.com"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _token(email, *, aud=CLIENT_ID, iss="https://accounts.google.com", verified=True, exp_in=600, name="Asha",
           hd="same"):
    now = int(time.time())
    claims = {"iss": iss, "aud": aud, "sub": "1234567890", "email": email, "email_verified": verified,
              "iat": now, "exp": now + exp_in, "name": name}
    if hd == "same":  # a Google Workspace account for the address's own domain
        hd = email.rsplit("@", 1)[-1].lower()
    if hd:
        claims["hd"] = hd
    return jwt.encode(claims, _KEY, algorithm="RS256")


@pytest.fixture(autouse=True)
def _google():
    with override_settings(GOOGLE_OAUTH_CLIENT_IDS=CLIENT_ID), \
            mock.patch("accounts.google_signin._signing_key", return_value=_KEY.public_key()):
        yield


def _post(body):
    return APIClient().post("/api/v1/auth/google/", body, format="json")


@pytest.mark.parametrize("bad", [
    {"aud": "someone-else.apps.googleusercontent.com"},
    {"iss": "https://evil.example"},
    {"exp_in": -120},
    {"verified": False},
])
def test_bad_tokens_are_refused(tenant_a, bad):
    resp = _post({"credential": _token(tenant_a.owner.email, **bad)})
    assert resp.status_code == 401, resp.content
    assert settings.JWT_REFRESH_COOKIE_NAME not in resp.cookies


def test_off_without_client_ids(tenant_a):
    with override_settings(GOOGLE_OAUTH_CLIENT_IDS=""):
        assert _post({"credential": _token(tenant_a.owner.email)}).status_code == 404


def test_existing_user_signs_in_like_a_password_sign_in(tenant_a):
    resp = _post({"credential": _token(tenant_a.owner.email.upper())})
    assert resp.status_code == 200, resp.content
    assert resp.data["user"]["email"] == tenant_a.owner.email
    assert settings.JWT_REFRESH_COOKIE_NAME in resp.cookies


def test_existing_account_is_not_opened_by_a_google_account_google_does_not_own(tenant_a):
    """Review fix: a consumer Google account made on a company address (no ``hd``) only proves the
    address was reachable once; it must not open the existing Bizboard account."""
    resp = _post({"credential": _token(tenant_a.owner.email, hd=None)})
    assert resp.status_code == 401, resp.content
    assert settings.JWT_REFRESH_COOKIE_NAME not in resp.cookies


def test_two_step_is_still_asked(tenant_a):
    with mock.patch("accounts.mfa_service.mfa_is_enabled", return_value=True):
        resp = _post({"credential": _token(tenant_a.owner.email)})
    assert resp.status_code == 200
    assert settings.JWT_REFRESH_COOKIE_NAME not in resp.cookies
    assert resp.data["mfa_required"] is True


def test_new_email_needs_the_sign_up_fields_then_creates_the_owner(db):
    first = _post({"credential": _token("new.owner@alphatraders.in")})
    assert first.status_code == 200 and first.data["needs_signup"] is True
    assert not User.objects.filter(email="new.owner@alphatraders.in").exists()
    refused = _post({"credential": _token("new.owner@alphatraders.in"), "company_name": "Alpha", "accept_terms": False})
    assert refused.status_code == 400
    created = _post({"credential": _token("new.owner@alphatraders.in"), "company_name": "Alpha Traders",
                     "state": "Maharashtra", "accept_terms": True})
    assert created.status_code == 200, created.content
    user = User.objects.get(email="new.owner@alphatraders.in")
    assert not user.has_usable_password()
    assert Company.objects.filter(name="Alpha Traders").exists()
    assert LegalAcceptance.objects.filter(user=user).exists()
    assert settings.JWT_REFRESH_COOKIE_NAME in created.cookies


def test_trial_dedupe_still_applies_to_google_sign_up(tenant_a):
    from billing.models import Subscription

    tenant_a.company.gstin = "27AAAPL1234C1ZE"
    tenant_a.company.save(update_fields=["gstin"])
    from billing.trial_guard import record_trial

    record_trial(tenant_a.company, tenant_a.owner)
    with override_settings(REQUIRE_SUBSCRIPTION=True):
        resp = _post({"credential": _token("second@alphatraders.in"), "company_name": "Alpha Again",
                      "state": "Maharashtra", "gstin": "27AAAPL1234C1ZE", "registration_type": "REGULAR",
                      "accept_terms": True})
    assert resp.status_code == 200, resp.content
    from django.utils import timezone

    sub = Subscription.objects.get(company__name="Alpha Again")
    assert sub.trial_ends_at <= timezone.now() and sub.churn_reason == "TRIAL_ALREADY_USED"


def test_google_sign_up_keeps_the_password_sign_up_rules(db):
    """Review fix: state is required and registration type is one of the choices, as on the
    password sign-up (a free-text type used to reach a Postgres length error)."""
    base = {"credential": _token("rules@alphatraders.in"), "company_name": "Rules Co", "accept_terms": True}
    assert _post(base).status_code == 400  # no state
    assert _post({**base, "state": "Maharashtra", "registration_type": "COMPOSITION_SCHEME"}).status_code == 400
    ok = _post({**base, "state": "Maharashtra"})
    assert ok.status_code == 200, ok.content
