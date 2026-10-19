"""Copy one ticket into the vendor company. The bypass wraps only that write."""

from django.conf import settings
from django.db import transaction
from django.http import Http404
from django.utils import timezone

from accounts.models import CompanyUser
from core.exceptions import BusinessRuleError
from core.rls import rls_bypass
from core.services.audit import AuditService

from .models import Ticket, TicketComment, VendorTicketShare, VendorTicketShareComment


def vendor_company_id():
    raw = str(getattr(settings, "VENDOR_COMPANY_ID", "") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def is_vendor_company(company) -> bool:
    vendor_id = vendor_company_id()
    return vendor_id is not None and company is not None and company.pk == vendor_id


def _require_owner(ticket, user):
    membership = CompanyUser.objects.filter(
        company_id=ticket.company_id, user=user, role=CompanyUser.Role.OWNER, is_active=True,
    ).first()
    if membership is None:
        from rest_framework.exceptions import PermissionDenied

        raise PermissionDenied("Only the company owner can share a ticket.")
    return membership


def share_map(company_id, ticket_ids) -> dict:
    """{ticket_id: (shared_at, include_description)} for live shares of these tickets, in one query."""
    ids = list(ticket_ids)
    if not ids:
        return {}
    with rls_bypass():
        rows = VendorTicketShare.objects.filter(
            source_company_id=company_id, source_ticket_id__in=ids, revoked_at__isnull=True,
        ).values_list("source_ticket_id", "shared_at", "include_description")
        return {tid: (at, inc) for tid, at, inc in rows}


def share_ticket(ticket: Ticket, user, *, include_description: bool = False):
    _require_owner(ticket, user)
    vendor_id = vendor_company_id()
    if vendor_id is None:
        raise BusinessRuleError("No vendor company is configured.")
    include = bool(include_description)
    with rls_bypass():
        row, _created = VendorTicketShare.objects.update_or_create(
            vendor_company_id=vendor_id,
            source_company_id=ticket.company_id,
            source_ticket_id=ticket.pk,
            defaults={
                "company_id": vendor_id,
                "source_number": ticket.number,
                "subject": ticket.subject,
                "status": ticket.status,
                "description": ticket.description if include else "",
                "include_description": include,
                "shared_at": timezone.now(),
                "revoked_at": None,
            },
        )
    AuditService.log(
        action="support.ticket_shared",
        company=ticket.company,
        user=user,
        entity_type="Ticket",
        entity_id=ticket.pk,
        metadata={"vendor_company_id": vendor_id, "include_description": include},
    )
    return row


def revoke_share(ticket: Ticket, user):
    """Stop sharing. Safe to repeat: a ticket that is not shared simply stays not shared."""
    _require_owner(ticket, user)
    vendor_id = vendor_company_id()
    if vendor_id is None:
        raise Http404()
    with rls_bypass():
        row = VendorTicketShare.objects.filter(
            vendor_company_id=vendor_id,
            source_company_id=ticket.company_id,
            source_ticket_id=ticket.pk,
            revoked_at__isnull=True,
        ).first()
        if row is None:
            return None
        row.revoked_at = timezone.now()
        row.save(update_fields=["revoked_at", "updated_at"])
    AuditService.log(
        action="support.ticket_share_revoked",
        company=ticket.company,
        user=user,
        entity_type="Ticket",
        entity_id=ticket.pk,
        metadata={"vendor_company_id": vendor_id},
    )
    return row


def sync_share(ticket: Ticket) -> None:
    """Keep the vendor's copy in step with the ticket after an edit or status change."""
    with rls_bypass():
        shares = VendorTicketShare.objects.filter(
            source_company_id=ticket.company_id, source_ticket_id=ticket.pk, revoked_at__isnull=True,
        )
        for share in shares:
            share.subject = ticket.subject
            share.status = ticket.status
            share.source_number = ticket.number
            share.description = ticket.description if share.include_description else ""
            share.save(update_fields=["subject", "status", "source_number", "description", "updated_at"])


def vendor_reply(share: VendorTicketShare, user, company, body: str):
    """A vendor reply, written once for the vendor and once for the source company.

    ``VendorTicketShareComment`` belongs to the vendor company and ``TicketComment`` to the source
    company, both written inside one bypass block, so each side only ever reads its own rows. The
    acting company must be the share's vendor and the share must be live.
    """
    text = (body or "").strip()
    if not text:
        raise BusinessRuleError("A reply cannot be empty.")
    with rls_bypass(), transaction.atomic():
        live = VendorTicketShare.objects.select_for_update().filter(pk=share.pk).first()
        if live is None or live.company_id != company.pk:
            raise Http404()
        if live.revoked_at is not None:
            raise BusinessRuleError("This ticket is no longer shared with you.")
        ticket = Ticket.objects.filter(pk=live.source_ticket_id, company_id=live.source_company_id).first()
        if ticket is None:
            raise Http404()
        mine = VendorTicketShareComment.objects.create(
            company=company, share=live, body=text, created_by=user, updated_by=user,
        )
        TicketComment.objects.create(
            company_id=live.source_company_id,
            ticket=ticket,
            body=text,
            is_internal=False,
            from_vendor=True,
            author_label=company.name[:120],
        )
        assignee = ticket.assigned_to
    if assignee is not None:
        from core.care import notify_member

        notify_member(
            ticket.company,
            assignee,
            subject=f"Vendor reply on {ticket.number}",
            body=text[:500],
        )
    return mine
