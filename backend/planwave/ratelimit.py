"""Token buckets for public and authenticated routes.

Redis is the shared cache when configured. When the cache raises, login and OTP
fail closed on a strict in-process limit and the general API fails open.
"""

from __future__ import annotations

import time
from collections import defaultdict

from django.core.cache import cache
from django.http import JsonResponse

_LOCAL: dict[str, list[float]] = defaultdict(list)
_LOCAL_MAX = 20
_CACHE_ALERTED = False
_CLOSED = ("login:", "otp:", "register:")


def _client_ip(request) -> str:
    """Same trusted-proxy client IP the login lock uses. Raw REMOTE_ADDR is the load
    balancer behind a proxy, which would put every caller in one bucket."""
    try:
        from accounts.views import _client_ip as trusted_client_ip

        return (trusted_client_ip(request) or "0")[:64]
    except Exception:  # noqa: BLE001 - never fail a request because of the limiter
        return (request.META.get("REMOTE_ADDR") or "0")[:64]


def _api_identity(request) -> str:
    """Who is calling. DRF resolves JWT users inside the view, so at middleware time
    request.user is anonymous for them. Key on the credential, not on the IP."""
    import hashlib

    user = getattr(request, "user", None)
    pk = getattr(user, "pk", None)
    if pk:
        return f"u{pk}"
    cred = (request.META.get("HTTP_AUTHORIZATION") or "").strip()
    if not cred:
        from django.conf import settings

        cred = request.COOKIES.get(getattr(settings, "JWT_ACCESS_COOKIE_NAME", "bb_access"), "") or ""
    if cred:
        return "t" + hashlib.sha256(cred.encode("utf-8")).hexdigest()[:24]
    return _client_ip(request)


def _cache_down() -> None:
    global _CACHE_ALERTED
    if _CACHE_ALERTED:
        return
    _CACHE_ALERTED = True
    import logging

    logging.getLogger("planwave.ratelimit").error("Rate-limit cache is down.")


def _fail_closed(key: str) -> bool:
    return key.startswith(_CLOSED)


def _hit(key: str, limit: int, window: int) -> bool:
    """Return True when the caller is still inside the limit."""
    now = time.time()
    try:
        added = cache.add(key, 1, timeout=window)
        if added:
            return True
        try:
            count = cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=window)
            return True
        return count <= limit
    except Exception:
        _cache_down()
        if not _fail_closed(key):
            return True
        if len(_LOCAL) > 5000:  # bound memory during a long outage
            for stale in [k for k, v in _LOCAL.items() if not v or now - v[-1] > 3600]:
                _LOCAL.pop(stale, None)
            if len(_LOCAL) > 5000:
                _LOCAL.clear()
        bucket = [t for t in _LOCAL[key] if now - t < window]
        cap = min(limit, _LOCAL_MAX)
        if len(bucket) >= cap:
            _LOCAL[key] = bucket
            return False
        bucket.append(now)
        _LOCAL[key] = bucket
        return True


def _body_account(request) -> str:
    try:
        import json

        raw = request.body or b""
        data = json.loads(raw.decode() or "{}")
    except Exception:
        return ""
    if not isinstance(data, dict):  # a JSON list or null body must not turn into a 500
        return ""
    return str(data.get("email") or data.get("phone") or data.get("mobile") or "")[:80].lower()


def _otp_target(request) -> str:
    """The OTP target in one canonical form, so +91 98765 43210, 919876543210 and 09876543210
    share a bucket instead of each getting a fresh one."""
    raw = _body_account(request)
    digits = "".join(ch for ch in raw if ch.isdigit())
    if "@" not in raw and len(digits) >= 10:
        return digits[-10:]
    return raw


def _login_account(request) -> str:
    return _body_account(request)


def classify(request) -> tuple[str, int, int] | None:
    path = request.path or ""
    if "/auth/login" in path:
        return (f"login:ip:{_client_ip(request)}", 10, 60)
    if "/auth/otp" in path or path.endswith("/otp/"):
        target = _body_account(request) or _client_ip(request)
        return (f"otp:target:{target}", 3, 60)
    if "/auth/register" in path:
        return (f"register:{_client_ip(request)}", 5, 3600)
    if "/portal/" in path:
        return (f"portal:{_client_ip(request)}", 60, 60)
    if path.startswith("/api/"):
        return (f"api:{_api_identity(request)}", 600, 60)
    return None


def rules_for(request) -> list[tuple[str, int, int]]:
    path = request.path or ""
    ip = _client_ip(request)
    rules: list[tuple[str, int, int]] = []
    if "/auth/login" in path:
        rules.append((f"login:ip:{ip}", 10, 60))
        account = _login_account(request)
        if account:
            # Per account AND address. A bucket per account alone lets anyone lock a
            # victim out of their own login by posting wrong passwords for their email.
            rules.append((f"login:acct:{account}:{ip}", 5, 60))
    if "/auth/otp" in path or path.endswith("/otp/"):
        # Request and verify have separate buckets, and an address bucket sits beside the
        # target bucket, so one caller cannot lock another person out of OTP login.
        kind = "verify" if "verify" in path else "request"
        target = _otp_target(request) or ip
        rules.append((f"otp:{kind}:target:{target}", 3 if kind == "request" else 10, 60))
        rules.append((f"otp:{kind}:target:{target}:h", 10 if kind == "request" else 30, 3600))
        rules.append((f"otp:ip:{ip}", 30, 3600))
    if "/auth/register" in path:
        rules.append((f"register:ip:{ip}", 5, 3600))
    if "/portal/" in path:
        token = (request.META.get("HTTP_AUTHORIZATION") or ip)[:80]
        rules.append((f"portal:{token}", 60, 60))
        # A caller who sends a different junk token each time still hits this address bucket.
        rules.append((f"portal:ip:{ip}", 600, 60))
    if "/webhooks/" in path or path.endswith("/webhook/"):
        rules.append((f"webhook:ip:{ip}", 2000, 60))
    elif path.startswith("/api/"):
        rules.append((f"api:{_api_identity(request)}", 100, 10))
        rules.append((f"api:ip:{ip}", 1500, 60))
    return rules


class PlanRateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings

        if not getattr(settings, "PLANWAVE_RATE_LIMIT", False):
            return self.get_response(request)
        blocked_window = None
        for key, limit, window in rules_for(request):
            if not _hit(key, limit, window):
                blocked_window = window
                break
        if blocked_window is None:
            return self.get_response(request)
        response = JsonResponse({"detail": "Too many requests."}, status=429)
        response["Retry-After"] = str(blocked_window)
        return response
