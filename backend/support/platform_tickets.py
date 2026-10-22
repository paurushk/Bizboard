"""WP-PO3: a tenant asks Bizboard for help (not the merchant's own customer helpdesk).

``support.Ticket`` is the merchant-to-buyer helpdesk (it needs a ``masters.Customer``, is gated by
``ENABLE_SUPPORT_TICKETS`` and held off in trials), so it is not touched. A ``PlatformTicket`` can
be raised by any active member of any company, trial included, with no plan flag. Members see the
tickets they raised; owners see all of their company's. Bizboard staff work the queue in Django
admin (Support → Platform tickets) with SLA timers per severity.

The form sends the Support ID, the screen route, the app version and up to five recent error codes
— never request bodies or form data.
"""

from __future__ import annotations

import re
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from core.exceptions import BusinessRuleError

DEFAULT_SLA_HOURS = {"P0": 2, "P1": 8, "P2": 24, "P3": 72}
_CODE_RE = re.compile(r"^[A-Z0-9_]{2,64}$")


def sla_hours(severity: str) -> int:
    table = {**DEFAULT_SLA_HOURS, **(getattr(settings, "PLATFORM_TICKET_SLA_HOURS", None) or {})}
    return int(table.get(severity, table["P3"]))


def _clean_codes(codes) -> list[str]:
    out = []
    for code in (codes or [])[:5]:
        code = str(code or "").strip().upper()
        if _CODE_RE.match(code):
            out.append(code)
    return out


def open_ticket(*, company, user, subject, description, severity="P2", tag="", support_id="", route="",
                app_version="", error_codes=None):
    from .models import PlatformTicket

    subject = (subject or "").strip()
    if len(subject) < 3:
        raise BusinessRuleError("Say in a few words what you need help with.")
    if severity not in DEFAULT_SLA_HOURS:
        severity = "P2"
    now = timezone.now()
    ticket = PlatformTicket.objects.create(
        company=company,
        raised_by=user,
        subject=subject[:200],
        description=(description or "").strip()[:5000],
        severity=severity,
        tag=(tag or "")[:64],
        support_id=(support_id or "")[:64],
        route=(route or "")[:200],
        app_version=(app_version or "")[:32],
        error_codes=_clean_codes(error_codes),
        sla_due_at=now + timedelta(hours=sla_hours(severity)),
        created_by=user,
        updated_by=user,
    )
    _notify_ops(ticket)
    return ticket


def _notify_ops(ticket) -> None:
    if ticket.severity not in ("P0", "P1"):
        return
    try:
        from core.services.telegram import send_ops_alert

        send_ops_alert(f"{ticket.severity} support ticket #{ticket.pk} from company {ticket.company_id}: {ticket.subject}")
    except Exception:  # noqa: BLE001
        pass


def add_message(ticket, *, author, body: str, from_staff: bool):
    from .models import PlatformTicket, PlatformTicketMessage

    body = (body or "").strip()
    if not body:
        raise BusinessRuleError("Write a message first.")
    msg = PlatformTicketMessage.objects.create(
        company=ticket.company, ticket=ticket, author=author, from_staff=from_staff, body=body[:5000],
        created_by=author, updated_by=author,
    )
    if from_staff:
        ticket.status = PlatformTicket.Status.WAITING_CUSTOMER
        if ticket.first_response_at is None:
            ticket.first_response_at = timezone.now()
        _email_customer(ticket, body)
    elif ticket.status in (PlatformTicket.Status.WAITING_CUSTOMER, PlatformTicket.Status.RESOLVED):
        ticket.status = PlatformTicket.Status.OPEN
    ticket.save(update_fields=["status", "first_response_at", "updated_at"])
    return msg


def _email_customer(ticket, body: str) -> None:
    from core.models import Notification
    from core.services.notifications import NotificationService

    email = getattr(ticket.raised_by, "email", "")
    if email:
        NotificationService.send(
            company=ticket.company, channel=Notification.Channel.EMAIL, recipient=email,
            subject=f"Re: {ticket.subject} (support #{ticket.pk})", body=body,
        )


def visible_to(qs, company_user):
    """Owners see the company's tickets; everyone else sees the ones they raised."""
    qs = qs.filter(company=company_user.company)
    if company_user.role != "OWNER":
        qs = qs.filter(raised_by=company_user.user)
    return qs
