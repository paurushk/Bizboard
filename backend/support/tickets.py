from datetime import timedelta

from django.db import transaction
from django.db.models import Count, F, Q
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


def tickets_past_sla_q(now=None):
    """Open tickets already past the paused SLA.

    While WAITING, the stored due plus the pause is still in the past only
    when sla_due_at < waiting_since. That is a database filter.
    """
    now = now or timezone.now()
    waiting = Q(status=Ticket.Status.WAITING, waiting_since__isnull=False)
    return (waiting & Q(sla_due_at__lt=F("waiting_since"))) | (
        ~waiting & Q(sla_due_at__lt=now)
    )


_FINISHED = {Ticket.Status.RESOLVED, Ticket.Status.CLOSED}


def sla_state(ticket, now=None):
    """Server-side SLA verdict so every screen draws the same chip (TKT-01).

    running / paused / breached while open; met / breached_resolved once the ticket is finished,
    judged at resolve time, never against the wall clock.
    """
    now = now or timezone.now()
    due = effective_sla_due_at(ticket, now)
    if due is None:
        return {"state": "none", "remaining_seconds": None}
    if ticket.status in _FINISHED:
        if ticket.resolved_at is None:
            return {"state": "none", "remaining_seconds": None}
        late = (ticket.resolved_at - ticket.sla_due_at).total_seconds()
        return {"state": "breached_resolved" if late > 0 else "met", "remaining_seconds": int(-late)}
    if ticket.status == Ticket.Status.WAITING:
        return {"state": "paused", "remaining_seconds": int((ticket.sla_due_at - ticket.waiting_since).total_seconds())
                if ticket.waiting_since else None}
    remaining = int((due - now).total_seconds())
    return {"state": "breached" if remaining < 0 else "running", "remaining_seconds": remaining}


def reprioritise(ticket, user, new_priority):
    """Change priority without resetting the clock (TKT-02).

    The due time moves by the difference between the two SLA offsets, so the time already spent
    still counts: HIGH -> MEDIUM -> HIGH returns to the original deadline, and raising the priority
    of an old ticket can honestly show it as breached. Works while WAITING too, because the frozen
    due time is shifted and the pause is added back when the ticket resumes.
    """
    if new_priority not in SLA_OFFSETS:
        raise BusinessRuleError("Unknown ticket priority.")
    if new_priority == ticket.priority:
        return ticket
    if ticket.status in _FINISHED:
        raise BusinessRuleError("Re-open the ticket before changing its priority.")
    old = ticket.priority
    old_due = ticket.sla_due_at
    if ticket.sla_due_at is not None:
        ticket.sla_due_at = ticket.sla_due_at - SLA_OFFSETS[old] + SLA_OFFSETS[new_priority]
    ticket.priority = new_priority
    ticket.updated_by = user
    ticket.save(update_fields=["priority", "sla_due_at", "updated_by", "updated_at"])
    AuditService.log(
        action="ticket_priority",
        company=ticket.company,
        user=user,
        entity_type="Ticket",
        entity_id=ticket.pk,
        metadata={
            "from": old, "to": new_priority,
            "due_from": old_due.isoformat() if old_due else None,
            "due_to": ticket.sla_due_at.isoformat() if ticket.sla_due_at else None,
        },
    )
    return ticket


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


def create_ticket(
    company, user, *, customer, subject, description="", priority=Ticket.Priority.MEDIUM,
    category=Ticket.Category.GENERAL, assigned_to=None, source_invoice=None, contract=None,
):
    if customer is None:
        raise BusinessRuleError("A ticket requires a customer.")
    if source_invoice is not None and (
        source_invoice.company_id != company.id or source_invoice.customer_id != customer.id
    ):
        raise BusinessRuleError("The invoice must belong to the ticket's customer.")
    if contract is not None and (contract.company_id != company.id or contract.customer_id != customer.id):
        raise BusinessRuleError("The contract must belong to the ticket's customer.")
    if priority not in SLA_OFFSETS:
        raise BusinessRuleError("Unknown ticket priority.")
    if category not in Ticket.Category.values:
        raise BusinessRuleError("Unknown ticket category.")
    if assigned_to is not None and assigned_to.company_id != company.id:
        raise BusinessRuleError("Assignee is not in this company.")
    with transaction.atomic():
        row = Ticket.objects.create(
            company=company,
            customer=customer,
            subject=subject,
            description=description or "",
            priority=priority,
            category=category,
            number=next_number(company, "TICKET", prefix="TKT"),
            sla_due_at=timezone.now() + SLA_OFFSETS[priority],
            assigned_to=assigned_to or next_ticket_assignee(company),
            source_invoice=source_invoice,
            contract=contract,
            created_by=user,
            updated_by=user,
        )
    log_flag_event(company, "ENABLE_SUPPORT_TICKETS", "ticket_created", ticket_id=row.id)
    return row


def transition_status(ticket, user, *, new_status):
    with transaction.atomic():
        # Two people moving the same ticket must not both succeed (FND-12).
        ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
        return _transition_locked(ticket, user, new_status)


def _transition_locked(ticket, user, new_status):
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
    from core.rls import rls_bypass

    from .models import VendorTicketShare

    with rls_bypass():
        VendorTicketShare.objects.filter(
            source_company_id=ticket.company_id,
            source_ticket_id=ticket.pk,
            revoked_at__isnull=True,
        ).update(status=ticket.status)
    AuditService.log(
        action="ticket_status",
        company=ticket.company,
        user=user,
        entity_type="Ticket",
        entity_id=ticket.pk,
        metadata={"status": new_status},
    )
    return ticket
