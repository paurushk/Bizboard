"""JWT authentication that also accepts httpOnly access cookie (BB-000375)."""

from django.conf import settings
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication


class CookieJWTAuthentication(JWTAuthentication):
    """Cookie access JWT with CSRF on unsafe methods.

    Local/dev may still accept Authorization Bearer (no CSRF). Production and
    staging are cookie-only so Bearer cannot skip CSRF (BB-000547 / BB-000603).
    """

    def extract_raw_token(self, header):
        if header is not None:
            return super().extract_raw_token(header)
        return None

    def authenticate(self, request):
        env = (getattr(settings, "DJANGO_ENV", "") or "").strip().lower()
        cookie_only = env in ("production", "staging")
        header = self.get_header(request)
        if header is not None and not cookie_only:
            # R1-005: dev/test only. This Bearer path skips CSRF by design; it is
            # unreachable in production/staging (cookie_only). A browser that
            # sends BOTH a bearer header and cookies on a cross-site request in
            # dev would bypass CSRF here — acceptable for local tooling, but do
            # not relax `cookie_only` for any internet-facing environment.
            return super().authenticate(request)
        raw = request.COOKIES.get(getattr(settings, "JWT_ACCESS_COOKIE_NAME", "bb_access"))
        if not raw:
            return None
        validated = self.get_validated_token(raw)
        user = self.get_user(validated)
        # BB-000417: cookie-borne JWT must satisfy CSRF on unsafe methods.
        SessionAuthentication().enforce_csrf(request)
        return user, validated
