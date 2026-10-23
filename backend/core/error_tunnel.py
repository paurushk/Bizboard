"""POST /api/v1/client-errors/ — same-origin tunnel for browser error reports.

The SPA's Sentry SDK posts its envelopes here instead of straight to the error
tracker. That keeps the page CSP at ``connect-src 'self'`` for a self-hosted
GlitchTip on any host, and ad blockers that drop requests to ``*.sentry.io``
no longer lose reports.

Only envelopes addressed to the one configured browser DSN
(``SENTRY_BROWSER_DSN``, the same value the SPA was built with as
``VITE_SENTRY_DSN``) are forwarded. Anything else is refused, so this cannot be
used to make the API POST to an arbitrary host.
"""

from __future__ import annotations

import json
import logging
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.http import HttpResponse
from rest_framework.decorators import api_view, authentication_classes, throttle_classes
from rest_framework.decorators import permission_classes as drf_permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle

logger = logging.getLogger(__name__)

# A browser envelope with a stack trace and breadcrumbs is a few KB; replays and
# attachments are not enabled in the SPA.
MAX_ENVELOPE_BYTES = 1024 * 1024
FORWARD_TIMEOUT_SECONDS = 5


class ClientErrorTunnelThrottle(AnonRateThrottle):
    # Per client IP, in its own bucket: AnonRateThrottle's default "anon" scope would
    # share one request history with every other anonymous endpoint. The SDK already
    # de-duplicates repeats; an office behind one NAT address still fits.
    scope = "client_errors"
    rate = "120/min"


def _dsn_parts(dsn: str) -> tuple[str, str, str, str] | None:
    """(origin, path prefix, project id, public key) of a DSN, or None when it is not one."""
    try:
        parts = urlsplit(dsn.strip())
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname or not parts.username:
        return None
    prefix, _, project_id = parts.path.rstrip("/").rpartition("/")
    if not project_id.isdigit():
        return None
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{parts.hostname}{port}", prefix, project_id, parts.username


def _envelope_dsn(body: bytes) -> str:
    header_line = body.split(b"\n", 1)[0]
    try:
        header = json.loads(header_line)
    except ValueError:
        return ""
    return header.get("dsn", "") if isinstance(header, dict) else ""


@api_view(["POST"])
@authentication_classes([])
@drf_permission_classes([AllowAny])
@throttle_classes([ClientErrorTunnelThrottle])
def client_error_tunnel(request):
    configured = _dsn_parts(getattr(settings, "SENTRY_BROWSER_DSN", "") or "")
    if configured is None:
        return HttpResponse(status=404)

    declared = request.META.get("CONTENT_LENGTH") or "0"
    if not declared.isdigit() or int(declared) > MAX_ENVELOPE_BYTES:
        return HttpResponse(status=413)
    body = request.body
    if not body or len(body) > MAX_ENVELOPE_BYTES:
        return HttpResponse(status=413 if body else 400)

    declared_dsn = _dsn_parts(_envelope_dsn(body))
    if declared_dsn is None or declared_dsn[:3] != configured[:3]:
        return HttpResponse(status=400)

    origin, prefix, project_id, public_key = configured
    try:
        upstream = requests.post(
            f"{origin}{prefix}/api/{project_id}/envelope/",
            data=body,
            # GlitchTip authenticates by this query key only (it ignores the DSN in the
            # envelope header); Sentry accepts either.
            params={"sentry_key": public_key},
            headers={"Content-Type": "application/x-sentry-envelope"},
            timeout=FORWARD_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.warning("client error tunnel: forward failed: %s", exc.__class__.__name__)
        return HttpResponse(status=502)
    response = HttpResponse(status=upstream.status_code)
    # The SDK backs off on these; pass them through so a throttled tracker is respected.
    for name in ("Retry-After", "X-Sentry-Rate-Limits"):
        if name in upstream.headers:
            response[name] = upstream.headers[name]
    return response
