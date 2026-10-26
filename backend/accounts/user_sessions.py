"""WP-ID3: a user's signed-in devices ("sessions"), revoke one, and a new-device email.

A session is one chain of refresh tokens: sign-in starts it, each refresh moves ``current_jti`` on
to the rotated token, and revoking it blacklists the current refresh token so the next refresh is
refused (access tokens are short-lived and lapse on their own). Only the device label from the user
agent and the /24 (IPv4) or /48 (IPv6) network prefix are kept, never the full address.

A sign-in from a device label + network prefix not seen for this user in 90 days emails the user
(category ``security``, always sent) — unless it is the user's very first session.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from core.netutil import ip_prefix  # noqa: F401 - re-exported for callers and tests

logger = logging.getLogger(__name__)

NEW_DEVICE_WINDOW = timedelta(days=90)
_GRACE_KEY = "refresh-grace-used:"


_BROWSERS = (("Edg/", "Edge"), ("OPR/", "Opera"), ("Chrome/", "Chrome"), ("Firefox/", "Firefox"),
             ("Safari/", "Safari"))
_SYSTEMS = (("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"), ("Windows", "Windows"),
            ("Mac OS X", "Mac"), ("Linux", "Linux"))


def device_label(user_agent: str | None) -> str:
    ua = user_agent or ""
    if "Capacitor" in ua or "bizboardapp" in ua.lower():
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


def session_for_rotation_grace(request, raw: str):
    """The live session a just-rotated refresh token may be replayed into, or ``None``.

    A reload can abort the refresh response after the server rotated the token, so the browser
    presents the old one again. That is allowed only when the old token was blacklisted within
    ``REFRESH_REUSE_GRACE_SECONDS`` and this same device (user agent and IP prefix) still has a
    live, unrevoked session that was moved on in that window. Sign-out revokes the session, so a
    signed-out token never comes back.
    """
    from django.conf import settings
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
    from rest_framework_simplejwt.tokens import RefreshToken

    from core.netutil import client_ip

    from .models import UserSession

    grace = getattr(settings, "REFRESH_REUSE_GRACE_SECONDS", 0)
    if not grace:
        return None
    try:
        token = RefreshToken(str(raw), verify=False)
        jti, user_id = token["jti"], token.get("user_id")
    except Exception:  # noqa: BLE001
        return None
    since = timezone.now() - timedelta(seconds=grace)
    if not BlacklistedToken.objects.filter(token__jti=jti, blacklisted_at__gte=since).exists():
        return None
    meta = getattr(request, "META", {}) or {}
    session = (
        UserSession.objects.filter(
            user_id=user_id,
            revoked_at__isnull=True,
            last_used_at__gte=since,
            device_label=device_label(meta.get("HTTP_USER_AGENT")),
            ip_prefix=ip_prefix(client_ip(request)),
        )
        .exclude(current_jti=jti)
        .order_by("-last_used_at")
        .first()
    )
    # Single use: a replayed token, or one the grace itself retired, cannot be replayed again.
    if session is None or not cache.add(f"{_GRACE_KEY}{jti}", 1, grace):
        return None
    return session


def retire_after_grace(jti: str) -> None:
    """Blacklist the token the browser never received; it cannot use the grace either."""
    from django.conf import settings

    _blacklist_jti(jti)
    cache.set(f"{_GRACE_KEY}{jti}", 1, max(1, getattr(settings, "REFRESH_REUSE_GRACE_SECONDS", 0)))


def track(request, refresh_raw: str, *, previous: str | None = None, previous_jti: str = "") -> None:
    """Record a newly issued refresh token. ``previous`` is the refresh token it replaces (a
    refresh or a company switch); without it this is a new sign-in. ``previous_jti`` names the
    session's current token directly (the rotation-grace replay, where ``previous`` is stale)."""
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
    prev_jti = previous_jti
    if previous and not prev_jti:
        try:
            prev_jti = _jti(previous)
        except Exception:  # noqa: BLE001
            prev_jti = ""
    from core.netutil import client_ip

    meta = getattr(request, "META", {}) or {}
    label = device_label(meta.get("HTTP_USER_AGENT"))
    prefix = ip_prefix(client_ip(request))
    if prev_jti:
        moved = UserSession.objects.filter(user_id=user_id, current_jti=prev_jti, revoked_at__isnull=True).update(
            current_jti=jti, last_used_at=now, ip_prefix=prefix,
        )
        if moved:
            return
        if UserSession.objects.filter(user_id=user_id, current_jti=prev_jti, revoked_at__isnull=False).exists():
            # The device was signed out while this refresh was in flight: the token just issued
            # must not bring it back as a new session.
            _blacklist_jti(jti)
            return
    seen_before = UserSession.objects.filter(user_id=user_id)
    had_any = seen_before.exists()
    # Only live, recently used sessions make a device "known"; one the user signed out does not.
    known = seen_before.filter(
        device_label=label, ip_prefix=prefix, revoked_at__isnull=True, last_used_at__gte=now - NEW_DEVICE_WINDOW,
    ).exists()
    UserSession.objects.create(
        user_id=user_id, current_jti=jti, device_label=label, ip_prefix=prefix, last_used_at=now,
    )
    if had_any and not known:
        # Sent by a worker after the sign-in commits: SMTP must not add seconds to the sign-in.
        from django.db import transaction

        transaction.on_commit(lambda: _queue_new_device_email(user_id, label, prefix))


def _queue_new_device_email(user_id: int, label: str, prefix: str) -> None:
    try:
        from .tasks import new_device_email_task

        new_device_email_task.delay(user_id=user_id, label=label, prefix=prefix)
    except Exception:  # noqa: BLE001 - broker down: send it here rather than not at all
        _new_device_email(None, user_id, label, prefix)


def _blacklist_jti(jti: str) -> None:
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

    token = OutstandingToken.objects.filter(jti=jti).first()
    if token is not None:
        BlacklistedToken.objects.get_or_create(token=token)


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
                "Security in Bizboard, sign that device out and change your password."
            ),
        )
    except Suppressed:
        pass
    except Exception:  # noqa: BLE001
        logger.exception("new-device email failed for user %s", user_id)


def _live(qs):
    """Sessions still signed in: not revoked, and used within the refresh token's lifetime (a chain
    left alone longer than that can't refresh any more)."""
    from django.conf import settings

    lifetime = (getattr(settings, "SIMPLE_JWT", {}) or {}).get("REFRESH_TOKEN_LIFETIME") or timedelta(days=14)
    return qs.filter(revoked_at__isnull=True, last_used_at__gte=timezone.now() - lifetime)


def list_for(user):
    from .models import UserSession

    return _live(UserSession.objects.filter(user=user)).order_by("-last_used_at")


def revoke(user, session_id: int) -> bool:
    from django.db import transaction

    from .models import UserSession

    with transaction.atomic():
        # Locked, so a refresh moving this row to a new token waits and then sees it revoked.
        row = UserSession.objects.select_for_update().filter(user=user, pk=session_id, revoked_at__isnull=True).first()
        if row is None:
            return False
        _blacklist_jti(row.current_jti)
        row.revoked_at = timezone.now()
        row.save(update_fields=["revoked_at"])
    return True


def revoke_by_refresh(raw: str | None) -> None:
    """Sign-out of this device: close the session whose current token is ``raw``."""
    from .models import UserSession

    if not raw:
        return
    try:
        jti = _jti(raw)
    except Exception:  # noqa: BLE001
        return
    if jti:
        UserSession.objects.filter(current_jti=jti, revoked_at__isnull=True).update(revoked_at=timezone.now())


def revoke_all(user) -> None:
    from .models import UserSession

    UserSession.objects.filter(user=user, revoked_at__isnull=True).update(revoked_at=timezone.now())
