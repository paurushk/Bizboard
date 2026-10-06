"""Read-only counts for the growth admin view. No posting side effects."""

from __future__ import annotations

from django.utils import timezone


def growth_metrics(company) -> dict:
    from contracts.models import Contract
    from crm.models import Lead, ReferralCode, ReferralReward
    from support.models import Ticket
    from support.tickets import tickets_past_sla_q

    today = timezone.localdate()
    now = timezone.now()
    leads = Lead.objects.filter(company=company)
    lead_count = leads.count()
    converted = leads.filter(customer__isnull=False).count()
    open_statuses = [Ticket.Status.OPEN, Ticket.Status.IN_PROGRESS, Ticket.Status.WAITING]
    open_tickets = Ticket.objects.filter(company=company, status__in=open_statuses)
    renewals = Contract.objects.filter(
        company=company,
        status__in=[Contract.Status.ACTIVE, Contract.Status.EXPIRING],
        end_date__gte=today,
    )
    codes = ReferralCode.objects.filter(company=company).count()
    approved = ReferralReward.objects.filter(
        company=company,
        reward_status__in=[ReferralReward.Status.APPROVED, ReferralReward.Status.PAID],
    ).count()
    return {
        "leads": lead_count,
        "leads_with_customer": converted,
        "open_tickets": open_tickets.count(),
        "tickets_past_sla": open_tickets.filter(tickets_past_sla_q(now)).count(),
        "contracts_still_open": renewals.count(),
        "referral_codes": codes,
        "referral_rewards_approved": approved,
    }
