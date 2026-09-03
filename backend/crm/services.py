"""CRM preview helpers — lead convert + activities; not a full CRM suite."""

from decimal import Decimal

from django.db import transaction

from accounts.otp_utils import phone_lookup_values
from core.exceptions import BusinessRuleError
from masters.models import Customer

from .models import Lead, Opportunity


def _unique_customer_by_phone(company, phone: str):
    variants = phone_lookup_values(phone)
    if not variants:
        return None
    matches = list(Customer.objects.filter(company=company, phone__in=variants)[:2])
    if len(matches) >= 2:
        raise BusinessRuleError(
            "Multiple customers share this phone. Link the lead to a customer before converting."
        )
    if len(matches) == 1:
        return matches[0]
    return None


def _unique_customer_by_email(company, email: str):
    if not email:
        return None
    matches = list(Customer.objects.filter(company=company, email__iexact=email)[:2])
    if len(matches) >= 2:
        raise BusinessRuleError(
            "Multiple customers share this email. Link the lead to a customer before converting."
        )
    if len(matches) == 1:
        return matches[0]
    return None


@transaction.atomic
def convert_lead(
    lead: Lead, user, *, won: bool = False, amount=None
) -> tuple[Lead, Opportunity, Customer]:
    # BB-000731: lock + idempotent re-convert (no duplicate customer/opportunity).
    lead = Lead.objects.select_for_update().get(pk=lead.pk)
    existing = (
        Opportunity.objects.filter(company=lead.company, lead=lead)
        .order_by("id")
        .first()
    )
    if existing is not None:
        updates = []
        if won and existing.stage != Opportunity.Stage.WON:
            existing.stage = Opportunity.Stage.WON
            updates.append("stage")
        if amount is not None:
            existing.amount = Decimal(str(amount))
            updates.append("amount")
        if updates:
            existing.updated_by = user
            existing.save(update_fields=updates + ["updated_by", "updated_at"])
        customer = lead.customer
        if customer is None:
            customer = existing.customer
        return lead, existing, customer

    if lead.customer_id:
        customer = lead.customer
    else:
        existing_cust = None
        if lead.phone:
            existing_cust = _unique_customer_by_phone(lead.company, lead.phone)
        if existing_cust is None and lead.email:
            existing_cust = _unique_customer_by_email(lead.company, lead.email)
        if existing_cust is not None:
            customer = existing_cust
            updates = []
            if not customer.state and getattr(lead, "state", None):
                customer.state = lead.state
                updates.append("state")
            if not customer.gstin and getattr(lead, "gstin", None):
                customer.gstin = lead.gstin
                updates.append("gstin")
            if not customer.billing_address and getattr(lead, "address", None):
                customer.billing_address = lead.address
                updates.append("billing_address")
            if updates:
                customer.updated_by = user
                updates.extend(["updated_by", "updated_at"])
                customer.save(update_fields=updates)
        else:
            state = getattr(lead, "state", None) or getattr(lead.company, "state", "") or ""
            gstin = getattr(lead, "gstin", "") or ""
            address = getattr(lead, "address", "") or ""
            customer = Customer.objects.create(
                company=lead.company,
                name=lead.name,
                phone=lead.phone or "",
                email=lead.email or "",
                state=state,
                gstin=gstin,
                billing_address=address,
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
        amount=Decimal(str(amount or 0)),
        stage=Opportunity.Stage.WON if won else Opportunity.Stage.OPEN,
        created_by=user,
        updated_by=user,
    )
    return lead, opportunity, customer
