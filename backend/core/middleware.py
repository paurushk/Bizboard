"""BB-000372 / BB-000443 / BB-000478: request-id + JSON access log with duration + hashed IDs."""

import hashlib
import json
import logging
import re
import time
import uuid

from django.conf import settings

logger = logging.getLogger("bizboard.request")

_DOC_NUMBER_RE = re.compile(
    r"(?<=/)(?:INV|SI|PI|CN|DN|PR|SR|PO|SO|DC|RCP|PMT)-\d[\w-]*(?=/|$)",
    re.I,
)
_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.I,
)


def _hash_id(value) -> str:
    if value is None:
        return ""
    return hashlib.sha256(str(value).encode()).hexdigest()[:12]


def _redact_path(path: str) -> str:
    """BB-000587: drop document numbers / UUIDs from access logs."""
    redacted = _DOC_NUMBER_RE.sub(":doc", path)
    return _UUID_RE.sub(":id", redacted)


class MaxBodySizeMiddleware:
    """B7-006: reject an oversized request by its declared Content-Length before
    Django reads/spools the body to disk. The per-file `validate_upload` guard
    only fires *after* the whole multipart body has already landed on disk, so a
    stream of large uploads can fill the temp volume. This is a coarse hard
    ceiling above every legitimate upload; the proxy `client_max_body_size` is
    the other layer."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.max_bytes = int(getattr(settings, "MAX_REQUEST_BODY_SIZE", 25 * 1024 * 1024))

    def __call__(self, request):
        if request.method in ("POST", "PUT", "PATCH") and self.max_bytes > 0:
            raw = request.META.get("CONTENT_LENGTH") or ""
            try:
                declared = int(raw)
            except (TypeError, ValueError):
                declared = 0
            if declared > self.max_bytes:
                from django.http import JsonResponse

                return JsonResponse(
                    {
                        "error": {
                            "code": "request_too_large",
                            "message": (
                                f"Request body {declared} bytes exceeds the "
                                f"{self.max_bytes}-byte limit."
                            ),
                        }
                    },
                    status=413,
                )
        return self.get_response(request)


class RequestIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.request_id = rid
        started = time.monotonic()
        try:
            from core.views import bump_request_count

            bump_request_count()
        except Exception:  # noqa: BLE001 — metrics must not break requests
            pass
        response = self.get_response(request)
        response["X-Request-ID"] = rid
        if getattr(settings, "JSON_REQUEST_LOGS", True):
            user_id_h = ""
            company_id_h = ""
            user = getattr(request, "user", None)
            if user is not None and getattr(user, "is_authenticated", False):
                user_id_h = _hash_id(user.pk)
                try:
                    from core.permissions import get_company_user

                    cu = get_company_user(request)
                    if cu is not None:
                        company_id_h = _hash_id(cu.company_id)
                except Exception:  # noqa: BLE001 — logging must not break requests
                    pass
            duration_ms = int((time.monotonic() - started) * 1000)
            logger.info(
                json.dumps(
                    {
                        "event": "request",
                        "request_id": rid,
                        "method": request.method,
                        "path": _redact_path(request.path),
                        "status": response.status_code,
                        "duration_ms": duration_ms,
                        "user_id": user_id_h,
                        "company_id": company_id_h,
                    },
                    separators=(",", ":"),
                )
            )
        return response


class PostgresRlsMiddleware:
    """SET SESSION app.company_id when POSTGRES_RLS_ENABLED (Postgres only).

    Authenticates Cookie JWT before resolving company so RLS is not skipped
    for DRF cookie/bearer sessions (BB-000604).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, "POSTGRES_RLS_ENABLED", False):
            return self.get_response(request)

        from core.rls import set_rls_company

        if not getattr(getattr(request, "user", None), "is_authenticated", False):
            try:
                from core.authentication import CookieJWTAuthentication

                result = CookieJWTAuthentication().authenticate(request)
                if result is not None:
                    request.user, request.auth = result
            except Exception:  # noqa: BLE001 — unauthenticated requests continue
                pass
        # B6-010: outside production/staging, DRF also accepts a Bearer token
        # (settings.py REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES). Without
        # trying that here too, a Bearer-authenticated request never resolves
        # a company_id at middleware time and set_rls_company(None) fails RLS
        # closed for the whole request — every tenant table reads as empty
        # even though the caller is legitimately authenticated.
        if (
            not getattr(getattr(request, "user", None), "is_authenticated", False)
            and getattr(settings, "DJANGO_ENV", "") not in ("production", "staging")
        ):
            try:
                from rest_framework_simplejwt.authentication import JWTAuthentication

                result = JWTAuthentication().authenticate(request)
                if result is not None:
                    request.user, request.auth = result
            except Exception:  # noqa: BLE001 — unauthenticated requests continue
                pass
        company_id = None
        try:
            from core.permissions import get_company_user

            cu = get_company_user(request)
            if cu is not None:
                company_id = cu.company_id
        except Exception:  # noqa: BLE001
            company_id = None

        # B6-013: set_rls_company can raise (fail-closed) — keep it inside the
        # try so the finally still clears any GUC left on this pooled connection
        # by a previous request/job.
        try:
            set_rls_company(company_id)
            return self.get_response(request)
        finally:
            # R1-009 / SYS-01: a pooled connection must never carry this
            # request's app.company_id (or help_staff_all / rls_bypass) into the
            # next request that reuses it (which might be unauthenticated or a
            # different tenant). Clear them all, fail closed.
            try:
                from core.rls import clear_all_rls_gucs

                clear_all_rls_gucs()
            except Exception:
                logger.exception("Failed to clear RLS session GUCs")
                raise
