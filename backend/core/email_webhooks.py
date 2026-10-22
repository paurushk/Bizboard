"""WP-CM1: bounce/complaint webhook from the email provider, and one-click unsubscribe.

``POST /api/v1/email/events/`` accepts Amazon SES notifications delivered through SNS and Postmark
bounce/spam webhooks. Both providers can call an HTTPS endpoint with HTTP Basic credentials in the
URL, so the endpoint requires ``EMAIL_WEBHOOK_USER`` / ``EMAIL_WEBHOOK_PASSWORD`` (it refuses all
requests when they are unset outside tests). An SNS subscription confirmation is confirmed only for
an ``https://sns.<region>.amazonaws.com`` URL. A body that can't be read is parked in the DLQ.

``GET|POST /api/v1/email/unsubscribe/?a=<hash>&c=<category>&t=<token>`` records an opt-out for that
category (no login; the HMAC token proves the link came from us). POST is the RFC 8058 one-click.
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import re

from django.conf import settings
from django.http import HttpResponse
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

logger = logging.getLogger(__name__)
_SNS_URL = re.compile(r"^https://sns\.[a-z0-9-]+\.amazonaws\.com/")


def _authorised(request) -> bool:
    user = (getattr(settings, "EMAIL_WEBHOOK_USER", "") or "").strip()
    password = (getattr(settings, "EMAIL_WEBHOOK_PASSWORD", "") or "").strip()
    if not user or not password:
        return False
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header.startswith("Basic "):
        return False
    try:
        got = base64.b64decode(header[6:]).decode()
    except (ValueError, UnicodeDecodeError):
        return False
    return hmac.compare_digest(got, f"{user}:{password}")


def parse_events(payload: dict) -> list[tuple[str, str]]:
    """``[(address, kind)]`` with kind hard_bounce | soft_bounce | complaint."""
    out: list[tuple[str, str]] = []
    # Postmark
    record = payload.get("RecordType")
    if record == "Bounce":
        kind = "hard_bounce" if payload.get("Type") in ("HardBounce", "BadEmailAddress", "Blocked") else "soft_bounce"
        if payload.get("Email"):
            out.append((payload["Email"], kind))
        return out
    if record == "SpamComplaint" and payload.get("Email"):
        return [(payload["Email"], "complaint")]
    # SES (inside an SNS Notification, or posted raw)
    message = payload
    if payload.get("Type") == "Notification" and isinstance(payload.get("Message"), str):
        try:
            message = json.loads(payload["Message"])
        except json.JSONDecodeError:
            return out
    ntype = message.get("notificationType") or message.get("eventType")
    if ntype == "Bounce":
        bounce = message.get("bounce") or {}
        kind = "hard_bounce" if bounce.get("bounceType") == "Permanent" else "soft_bounce"
        out += [(r.get("emailAddress", ""), kind) for r in bounce.get("bouncedRecipients") or [] if r.get("emailAddress")]
    elif ntype == "Complaint":
        complaint = message.get("complaint") or {}
        out += [(r.get("emailAddress", ""), "complaint") for r in complaint.get("complainedRecipients") or []
                if r.get("emailAddress")]
    return out


class EmailEventWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        if not _authorised(request):
            return Response({"detail": "Unauthorised."}, status=401)
        try:
            payload = json.loads((request.body or b"{}").decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        if not isinstance(payload, dict):
            from billing.services import park_dead_letter

            park_dead_letter(provider="email_events", event_id=f"bad:{len(request.body or b'')}",
                             payload={}, error="Unreadable email webhook body.")
            return Response({"ok": True, "parked": True})
        if payload.get("Type") == "SubscriptionConfirmation":
            url = str(payload.get("SubscribeURL") or "")
            if not _SNS_URL.match(url):
                return Response({"detail": "Not an SNS URL."}, status=400)
            from urllib.request import urlopen

            with urlopen(url, timeout=10):  # noqa: S310 - checked against the SNS host pattern above
                pass
            return Response({"ok": True, "confirmed": True})
        from core.mail import record_event

        events = parse_events(payload)
        for address, kind in events:
            record_event(address, kind, source="ses" if "notificationType" in json.dumps(payload) else "postmark")
        return Response({"ok": True, "recorded": len(events)})


class UnsubscribeView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AnonRateThrottle]

    def _handle(self, request):
        from core.mail import OPTIONAL
        from core.models import EmailOptOut

        q = request.query_params
        address_hash, category, token = q.get("a", ""), q.get("c", ""), q.get("t", "")
        expected = hmac.new(settings.SECRET_KEY.encode(), f"{address_hash}:{category}".encode(), "sha256").hexdigest()[:32]
        if category not in OPTIONAL or not hmac.compare_digest(token, expected):
            return HttpResponse("This unsubscribe link is not valid.", status=400, content_type="text/plain")
        EmailOptOut.objects.get_or_create(address_hash=address_hash, category=category)
        return HttpResponse(
            f"You will no longer get {category} emails from Bizboard. Invoices, sign-in and billing emails continue.",
            content_type="text/plain",
        )

    def get(self, request):
        return self._handle(request)

    def post(self, request):
        return self._handle(request)
