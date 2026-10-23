"""WP-CM1: every email goes through ``send()`` so bounces and complaints stop further mail.

A hard bounce or spam complaint suppresses the address for good; three soft bounces in seven days
suppress it for 30 days (``core.EmailSuppression``, fed by the provider webhook in
``core.email_webhooks``). Sending to a suppressed address is skipped and reported to the caller,
so the sender's reputation — and with it OTP and invoice delivery — holds up.

Each email has a category. ``security``, ``billing`` and ``transactional`` are always sent.
``product`` and ``marketing`` (digests, tips, trial nurture) carry ``List-Unsubscribe`` +
``List-Unsubscribe-Post: List-Unsubscribe=One-Click`` and a footer link, and are skipped for anyone
who opted out of that category (``core.EmailOptOut``).

``guard_no_direct_send_mail`` fails CI on a ``send_mail`` call outside this module.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

ALWAYS = frozenset({"security", "billing", "transactional"})
OPTIONAL = frozenset({"product", "marketing"})
SOFT_LIMIT = 3
SOFT_WINDOW = timedelta(days=7)
SOFT_SUPPRESS = timedelta(days=30)


class Suppressed(Exception):
    """The address bounced or complained before; nothing was sent."""


def address_hash(address: str) -> str:
    return hashlib.sha256((address or "").strip().lower().encode()).hexdigest()


def is_suppressed(address: str) -> bool:
    from core.models import EmailSuppression

    row = EmailSuppression.objects.filter(address_hash=address_hash(address)).first()
    if row is None or row.reason == EmailSuppression.Reason.SOFT_BOUNCE and row.soft_count < SOFT_LIMIT:
        return False
    return row.expires_at is None or row.expires_at > timezone.now()


def record_event(address: str, kind: str, *, source: str = "") -> None:
    """``kind``: hard_bounce | soft_bounce | complaint. Called by the provider webhook."""
    from core.models import EmailSuppression

    from django.db import transaction

    now = timezone.now()
    h = address_hash(address)
    if kind in ("hard_bounce", "complaint"):
        reason = EmailSuppression.Reason.COMPLAINT if kind == "complaint" else EmailSuppression.Reason.HARD_BOUNCE
        EmailSuppression.objects.update_or_create(
            address_hash=h, defaults={"reason": reason, "source": source[:32], "expires_at": None, "soft_count": 0},
        )
        _event(f"email_suppressed_{kind}")
        return
    with transaction.atomic():  # locked: two bounces delivered at once both count
        row = EmailSuppression.objects.select_for_update().filter(address_hash=h).first()
        if row is not None and row.reason != EmailSuppression.Reason.SOFT_BOUNCE:
            return  # already permanently suppressed
        if row is not None and row.expires_at and row.expires_at > now:
            return  # a soft suppression is running; a late bounce must not lift it early
        if row is None or row.window_start is None or now - row.window_start > SOFT_WINDOW:
            EmailSuppression.objects.update_or_create(
                address_hash=h,
                defaults={"reason": EmailSuppression.Reason.SOFT_BOUNCE, "source": source[:32], "soft_count": 1,
                          "window_start": now, "expires_at": None},
            )
            return
        row.soft_count += 1
        if row.soft_count >= SOFT_LIMIT:
            row.expires_at = now + SOFT_SUPPRESS
            _event("email_suppressed_soft_bounce")
        row.save(update_fields=["soft_count", "expires_at", "updated_at"])


def _event(name: str) -> None:
    try:
        from core.ops_metrics import bump_event

        bump_event(name)
    except Exception:  # noqa: BLE001
        pass


def unsubscribe_token_for_hash(hashed: str, category: str) -> str:
    """The token in an unsubscribe link (one function, so the link and its check never drift)."""
    msg = f"{hashed}:{category}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()[:32]


def unsubscribe_token(address: str, category: str) -> str:
    return unsubscribe_token_for_hash(address_hash(address), category)


def unsubscribe_url(address: str, category: str) -> str:
    from urllib.parse import urlencode

    base = (getattr(settings, "API_PUBLIC_URL", "") or getattr(settings, "FRONTEND_URL", "") or "").rstrip("/")
    q = urlencode({"a": address_hash(address), "c": category, "t": unsubscribe_token(address, category)})
    return f"{base}/api/v1/email/unsubscribe/?{q}"


def opted_out(address: str, category: str) -> bool:
    from core.models import EmailOptOut

    return EmailOptOut.objects.filter(address_hash=address_hash(address), category=category).exists()


def send(*, subject: str, body: str, to: str, category: str = "transactional", from_email: str | None = None) -> bool:
    """Send one email. Returns False when skipped (suppressed or opted out). Raises on SMTP error."""
    from django.core.mail import EmailMessage

    if category not in ALWAYS | OPTIONAL:
        raise ValueError(f"Unknown email category '{category}'.")
    if is_suppressed(to):
        logger.info("Email to a suppressed address skipped (%s).", category)
        _event("email_skipped_suppressed")
        raise Suppressed(to)
    headers = {}
    if category in OPTIONAL:
        if opted_out(to, category):
            return False
        url = unsubscribe_url(to, category)
        headers = {"List-Unsubscribe": f"<{url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
        body = f"{body}\n\nTo stop these emails: {url}"
    EmailMessage(
        subject=subject or "Bizboard",
        body=body,
        from_email=from_email or settings.DEFAULT_FROM_EMAIL,
        to=[to],
        headers=headers,
    ).send(fail_silently=False)
    return True
