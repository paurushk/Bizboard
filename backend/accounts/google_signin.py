"""WP-ID5: Sign in with Google.

The web app gets a Google ID token (Google Identity Services) and posts it to
``POST /api/v1/auth/google/``. The server checks it here — signature against Google's published
keys, audience is one of our client ids (``GOOGLE_OAUTH_CLIENT_IDS``), issuer is Google, not
expired, and ``email_verified`` is true — and then:

- an existing user with that email signs in exactly like a password sign-in: the same
  membership checks, the same two-step challenge or enrolment for money roles, the same session;
- a new email signs up only when the request carries the sign-up fields (company name, terms
  accepted). The email counts as verified (Google checked it), so no email code is asked;
  the bot check (WP-AB2) and one-trial-per-business (WP-AB3) still apply.

No account is ever linked by an unverified email. PyJWT does the verification (already installed
with SimpleJWT), so no Google SDK is added. Off unless ``GOOGLE_OAUTH_CLIENT_IDS`` is set.
"""

from __future__ import annotations

import logging

import jwt
from django.conf import settings
from django.db import IntegrityError
from rest_framework import serializers, status
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")
_jwk_client = None


def client_ids() -> list[str]:
    raw = getattr(settings, "GOOGLE_OAUTH_CLIENT_IDS", "") or ""
    if isinstance(raw, (list, tuple)):
        return [c for c in raw if c]
    return [c.strip() for c in str(raw).split(",") if c.strip()]


def _signing_key(token: str):
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = jwt.PyJWKClient(GOOGLE_CERTS_URL, cache_keys=True, lifespan=3600)
    return _jwk_client.get_signing_key_from_jwt(token).key


def verify_id_token(token: str) -> dict:
    """Return the verified claims, or raise ``AuthenticationFailed``."""
    audiences = client_ids()
    if not audiences:
        raise AuthenticationFailed("Sign in with Google is not set up.")
    try:
        claims = jwt.decode(
            token,
            key=_signing_key(token),
            algorithms=["RS256"],
            audience=audiences,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "email"]},
            leeway=30,
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationFailed("Google sign-in could not be checked. Try again.") from exc
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise AuthenticationFailed("Google sign-in could not be checked. Try again.")
    if claims.get("email_verified") not in (True, "true"):
        raise AuthenticationFailed("Your Google account's email is not verified.")
    claims["email"] = str(claims["email"]).strip().lower()
    return claims


class GoogleSignupSerializer(serializers.Serializer):
    company_name = serializers.CharField(max_length=255)
    full_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    state = serializers.CharField(max_length=64, required=False, allow_blank=True)
    registration_type = serializers.CharField(max_length=20, required=False, allow_blank=True)
    gstin = serializers.CharField(max_length=15, required=False, allow_blank=True)
    accept_terms = serializers.BooleanField()

    def validate_accept_terms(self, value):
        if not value:
            raise serializers.ValidationError("Accept the terms to create an account.")
        return value


class GoogleSignInView(APIView):
    """POST /api/v1/auth/google/ ``{credential, company_name?, accept_terms?, ...}``."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_scope = "login"

    def get_authenticate_header(self, request):
        return "Bearer"  # so a refused Google token is a 401, like a refused password

    def post(self, request):
        from core.services.bot_check import require_human

        from .models import User
        from .views import (
            _complete_login,
            _tokens_for_user,
            create_owner_account,
        )

        if not client_ids():
            return Response({"detail": "Sign in with Google is not set up."}, status=status.HTTP_404_NOT_FOUND)
        claims = verify_id_token(str(request.data.get("credential") or ""))
        email = claims["email"]
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            if not request.data.get("company_name"):
                # The caller proved they own this address, so saying it has no account leaks nothing.
                return Response({"needs_signup": True, "email": email, "full_name": claims.get("name", "")})
            require_human(request, action="register")  # WP-AB2: creating an account needs the bot check
            data = GoogleSignupSerializer(data=request.data)
            data.is_valid(raise_exception=True)
            fields = {**data.validated_data, "email": email}
            fields.setdefault("full_name", claims.get("name", "") or "")
            if fields.get("registration_type") in ("", None):
                fields.pop("registration_type", None)
            try:
                user, _company = create_owner_account(request, fields, password=None)
            except IntegrityError:
                raise AuthenticationFailed("This account already exists. Sign in instead.") from None
        if not user.is_active:
            raise AuthenticationFailed("This account is not active.")
        return self._sign_in(request, user, _tokens_for_user, _complete_login)

    def _sign_in(self, request, user, tokens_for_user, complete_login):
        from .mfa_service import enrolment_required, mfa_challenge_response, mfa_enrollment_response, mfa_is_enabled

        if not user.company_memberships.filter(is_active=True).exists():
            if user.company_memberships.filter(is_active=False).exists():
                raise AuthenticationFailed("Accept your invite to activate this account before signing in.")
            raise PermissionDenied("No active company membership. Ask an owner to invite you.")
        if mfa_is_enabled(user):
            return mfa_challenge_response(user)  # Google is one factor; the authenticator is still asked
        if enrolment_required(user):
            return mfa_enrollment_response(user)
        response = Response(tokens_for_user(user))
        return complete_login(request, response, user)
