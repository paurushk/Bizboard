from datetime import timedelta

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from accounts.models import CompanyUser
from core.exceptions import BusinessRuleError
from core.services.audit import AuditService
from core.services.flag_observability import log_flag_event
from core.services.round_robin import pick_least_loaded
from core.services.sequences import next_number

from .models import Ticket

SLA_OFFSETS = {
    Ticket.Priority.URGENT: timedelta(hours=4),
    Ticket.Priority.HIGH: timedelta(hours=24),
    Ticket.Priority.MEDIUM: timedelta(days=3),
    Ticket.Priority.LOW: timedelta(days=7),
}

_OPEN = {Ticket.Status.OPEN, Ticket.Status.IN_PROGRESS, Ticket.Status.WAITING}


def effective_sla_due_at(ticket, now=None):
    """Due time a reader should show. While WAITING the stored deadline is frozen
    and the remaining clock only starts again on exit."""
    now = now or timezone.now()
    if (
        ticket.status == Ticket.Status.WAITING
        and ticket.waiting_since
        and ticket.sla_due_at
    ):
        return ticket.sla_due_at + (now - ticket.waiting_since)
    return ticket.sla_due_at
_ALLOWED = {
    Ticket.Status.OPEN: {Ticket.Status.IN_PROGRESS},
    Ticket.Status.IN_PROGRESS: {Ticket.Status.WAITING, Ticket.Status.RESOLVED},
    Ticket.Status.WAITING: {Ticket.Status.IN_PROGRESS},
    Ticket.Status.RESOLVED: {Ticket.Status.CLOSED, Ticket.Status.IN_PROGRESS},
    Ticket.Status.CLOSED: {Ticket.Status.IN_PROGRESS},
}


def next_ticket_assignee(company):
    with transaction.atomic():
        members = list(
            CompanyUser.objects.select_for_update().filter(
                company=company,
                role=CompanyUser.Role.SALES_STAFF,
                is_active=True,
                user__is_active=True,
            ).order_by("id")
        )
        if not members:
            return None
        counts = {
            row["assigned_to"]: row["c"]
            for row in (
                Ticket.objects.filter(company=company, assigned_to__in=members, status__in=_OPEN)
                .values("assigned_to")
                .annotate(c=Count("id"))
            )
        }
        return pick_least_loaded(members, counts)


def create_ticket(company, user, *, customer, subject, description="", priority=Ticket.Priority.MEDIUM):
    if customer is None:
        raise BusinessRuleError("A ticket requires a customer.")
    if priority not in SLA_OFFSETS:
        raise BusinessRuleError("Unknown ticket priority.")
    with transaction.atomic():
        row = Ticket.objects.create(
            company=company,
            customer=customer,
            subject=subject,
            description=description or "",
            priority=priority,
            number=next_number(company, "TICKET", prefix="TKT"),
            sla_due_at=timezone.now() + SLA_OFFSETS[priority],
            assigned_to=next_ticket_assignee(company),
            created_by=user,
            updated_by=user,
        )
    log_flag_event(company, "ENABLE_SUPPORT_TICKETS", "ticket_created", ticket_id=row.id)
    return row


def transition_status(ticket, user, *, new_status):
    if new_status not in _ALLOWED.get(ticket.status, set()):
        raise BusinessRuleError(f"Cannot move a ticket from {ticket.status} to {new_status}.")
    now = timezone.now()
    fields = ["status", "updated_by", "updated_at", "waiting_since", "sla_due_at", "resolved_at"]
    if ticket.status == Ticket.Status.WAITING and ticket.waiting_since and ticket.sla_due_at:
        ticket.sla_due_at = ticket.sla_due_at + (now - ticket.waiting_since)
        ticket.waiting_since = None
    if new_status == Ticket.Status.WAITING:
        ticket.waiting_since = now
    if new_status == Ticket.Status.RESOLVED:
        ticket.resolved_at = now
    if new_status == Ticket.Status.IN_PROGRESS and ticket.status in (
        Ticket.Status.RESOLVED, Ticket.Status.CLOSED,
    ):
        ticket.resolved_at = None
        ticket.waiting_since = None
        ticket.sla_due_at = now + SLA_OFFSETS[ticket.priority]
    ticket.status = new_status
    ticket.updated_by = user
    ticket.save(update_fields=fields)
    AuditService.log(
        action="ticket_status",
        company=ticket.company,
        user=user,
        entity_type="Ticket",
        entity_id=ticket.pk,
        metadata={"status": new_status},
    )
    return ticket
