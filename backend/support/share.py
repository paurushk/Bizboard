"""Copy one ticket into the vendor company. The bypass wraps only that write."""

from django.conf import settings
from django.http import Http404
from django.utils import timezone

from accounts.models import CompanyUser
from core.exceptions import BusinessRuleError
from core.models import AuditEvent
from core.rls import rls_bypass

from .models import Ticket, VendorTicketShare


def vendor_company_id():
    raw = str(getattr(settings, "VENDOR_COMPANY_ID", "") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _require_owner(ticket, user):
    membership = CompanyUser.objects.filter(
        company_id=ticket.company_id, user=user, role=CompanyUser.Role.OWNER, is_active=True,
    ).first()
    if membership is None:
        from rest_framework.exceptions import PermissionDenied

        raise PermissionDenied("Only the company owner can share a ticket.")
    return membership


def share_ticket(ticket: Ticket, user, *, include_description: bool = False):
    _require_owner(ticket, user)
    vendor_id = vendor_company_id()
    if vendor_id is None:
        raise BusinessRuleError("No vendor company is configured.")
    payload = {
        "source_number": ticket.number,
        "subject": ticket.subject,
        "status": ticket.status,
        "description": ticket.description if include_description else "",
        "source_company_id": ticket.company_id,
        "source_ticket_id": ticket.pk,
    }
    with rls_bypass():
        row, _created = VendorTicketShare.objects.update_or_create(
            vendor_company_id=vendor_id,
            source_company_id=payload["source_company_id"],
            source_ticket_id=payload["source_ticket_id"],
            defaults={
                "company_id": vendor_id,
                "source_number": payload["source_number"],
                "subject": payload["subject"],
                "status": payload["status"],
                "description": payload["description"],
                "shared_at": timezone.now(),
                "revoked_at": None,
            },
        )
    AuditEvent.objects.create(
        company_id=ticket.company_id,
        user=user,
        action="support.ticket_shared",
        entity_type="Ticket",
        entity_id=str(ticket.pk),
        metadata={
            "vendor_company_id": vendor_id,
            "include_description": bool(include_description),
        },
    )
    return row


def revoke_share(ticket: Ticket, user):
    _require_owner(ticket, user)
    vendor_id = vendor_company_id()
    if vendor_id is None:
        raise Http404()
    with rls_bypass():
        row = VendorTicketShare.objects.filter(
            vendor_company_id=vendor_id,
            source_company_id=ticket.company_id,
            source_ticket_id=ticket.pk,
        ).first()
        if row is None or row.source_company_id != ticket.company_id:
            raise Http404()
        row.revoked_at = timezone.now()
        row.save(update_fields=["revoked_at", "updated_at"])
    return row
