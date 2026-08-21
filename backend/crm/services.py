"""CRM preview helpers — lead convert + activities; not a full CRM suite."""

from django.db import transaction

from masters.models import Customer

from .models import Lead, Opportunity


@transaction.atomic
def convert_lead(lead: Lead, user, *, won: bool = False) -> tuple[Lead, Opportunity, Customer]:
    # BB-000731: lock + idempotent re-convert (no duplicate customer/opportunity).
    lead = Lead.objects.select_for_update().get(pk=lead.pk)
    if lead.customer_id and lead.status == Lead.Status.QUALIFIED:
        existing = (
            Opportunity.objects.filter(company=lead.company, lead=lead)
            .order_by("id")
            .first()
        )
        if existing is not None:
            if won and existing.stage != Opportunity.Stage.WON:
                existing.stage = Opportunity.Stage.WON
                existing.updated_by = user
                existing.save(update_fields=["stage", "updated_by", "updated_at"])
            return lead, existing, lead.customer

    if lead.customer_id:
        customer = lead.customer
    else:
        customer = Customer.objects.create(
            company=lead.company,
            name=lead.name,
            phone=lead.phone or "",
            email=lead.email or "",
            created_by=user,
            updated_by=user,
        )
        lead.customer = customer
    lead.status = Lead.Status.QUALIFIED
    lead.updated_by = user
    lead.save(update_fields=["customer", "status", "updated_by", "updated_at"])
    opportunity = Opportunity.objects.create(
        company=lead.company,
        lead=lead,
        customer=customer,
        title=f"{lead.name} opportunity",
        amount=0,
        stage=Opportunity.Stage.WON if won else Opportunity.Stage.OPEN,
        created_by=user,
        updated_by=user,
    )
    return lead, opportunity, customer
