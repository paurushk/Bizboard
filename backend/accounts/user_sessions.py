"""WP-ID3: a user's signed-in devices ("sessions"), revoke one, and a new-device email.

A session is one chain of refresh tokens: sign-in starts it, each refresh moves ``current_jti`` on
to the rotated token, and revoking it blacklists the current refresh token so the next refresh is
refused (access tokens are short-lived and lapse on their own). Only the device label from the user
agent and the /24 (IPv4) or /48 (IPv6) network prefix are kept, never the full address.

A sign-in from a device label + network prefix not seen for this user in 90 days emails the user
(category ``security``, always sent) — unless it is the user's very first session.
"""

from __future__ import annotations

import ipaddress
import logging
import re
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

NEW_DEVICE_WINDOW = timedelta(days=90)


def ip_prefix(ip: str | None) -> str:
    try:
        addr = ipaddress.ip_address((ip or "").strip())
    except ValueError:
        return ""
    bits = 24 if addr.version == 4 else 48
    return str(ipaddress.ip_network(f"{addr}/{bits}", strict=False))


_BROWSERS = (("Edg/", "Edge"), ("OPR/", "Opera"), ("Chrome/", "Chrome"), ("Firefox/", "Firefox"),
             ("Safari/", "Safari"))
_SYSTEMS = (("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"), ("Windows", "Windows"),
            ("Mac OS X", "Mac"), ("Linux", "Linux"))


def device_label(user_agent: str | None) -> str:
    ua = user_agent or ""
    if "Capacitor" in ua or "BizboardApp" in ua:
        app = "Bizboard app"
    else:
        app = next((name for key, name in _BROWSERS if key in ua), "")
    system = next((name for key, name in _SYSTEMS if key in ua), "")
    label = " on ".join(p for p in (app, system) if p)
    return label or (re.sub(r"\s+", " ", ua)[:40] or "Unknown device")


def _jti(raw: str) -> str:
    from rest_framework_simplejwt.tokens import RefreshToken

    # verify=False: the token being replaced is already blacklisted by the time it is recorded.
    return str(RefreshToken(str(raw), verify=False).get("jti") or "")


def track(request, refresh_raw: str, *, previous: str | None = None) -> None:
    """Record a newly issued refresh token. ``previous`` is the refresh token it replaces (a
    refresh or a company switch); without it this is a new sign-in."""
    from .models import UserSession

    try:
        jti = _jti(refresh_raw)
        user = getattr(request, "user", None)
        from rest_framework_simplejwt.tokens import RefreshToken

        user_id = RefreshToken(str(refresh_raw), verify=False).get("user_id")
    except Exception:  # noqa: BLE001 - session tracking must never break sign-in
        logger.exception("could not read a refresh token for session tracking")
        return
    now = timezone.now()
    prev_jti = ""
    if previous:
        try:
            prev_jti = _jti(previous)
        except Exception:  # noqa: BLE001
            prev_jti = ""
    if prev_jti:
        moved = UserSession.objects.filter(user_id=user_id, current_jti=prev_jti, revoked_at__isnull=True).update(
            current_jti=jti, last_used_at=now,
        )
        if moved:
            return
    from core.observability import current_client_ip

    meta = getattr(request, "META", {}) or {}
    label = device_label(meta.get("HTTP_USER_AGENT"))
    prefix = ip_prefix(current_client_ip() or meta.get("REMOTE_ADDR"))
    seen_before = UserSession.objects.filter(user_id=user_id)
    had_any = seen_before.exists()
    known = seen_before.filter(device_label=label, ip_prefix=prefix, last_used_at__gte=now - NEW_DEVICE_WINDOW).exists()
    UserSession.objects.create(
        user_id=user_id, current_jti=jti, device_label=label, ip_prefix=prefix, last_used_at=now,
    )
    if had_any and not known and not prev_jti:
        _new_device_email(user if getattr(user, "pk", None) == user_id else None, user_id, label, prefix)


def _new_device_email(user, user_id: int, label: str, prefix: str) -> None:
    from core.mail import Suppressed, send

    from .models import User

    user = user or User.objects.filter(pk=user_id).first()
    if user is None or not user.email:
        return
    when = timezone.localtime().strftime("%d %b %Y %H:%M")
    try:
        send(
            to=user.email,
            category="security",
            subject="New sign-in to Bizboard",
            body=(
                f"Your Bizboard account was signed in from {label} (network {prefix or 'unknown'}) "
                f"at {when}.\n\nIf this was you, there is nothing to do. If not, open Settings → "
                "Security → Signed-in devices, sign that device out and change your password."
            ),
        )
    except Suppressed:
        pass
    except Exception:  # noqa: BLE001
        logger.exception("new-device email failed for user %s", user_id)


def list_for(user):
    from .models import UserSession

    return UserSession.objects.filter(user=user, revoked_at__isnull=True).order_by("-last_used_at")


def revoke(user, session_id: int) -> bool:
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

    from .models import UserSession

    row = UserSession.objects.filter(user=user, pk=session_id, revoked_at__isnull=True).first()
    if row is None:
        return False
    token = OutstandingToken.objects.filter(jti=row.current_jti).first()
    if token is not None:
        BlacklistedToken.objects.get_or_create(token=token)
    row.revoked_at = timezone.now()
    row.save(update_fields=["revoked_at"])
    return True


def revoke_all(user) -> None:
    from .models import UserSession

    UserSession.objects.filter(user=user, revoked_at__isnull=True).update(revoked_at=timezone.now())
