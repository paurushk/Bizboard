import calendar
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services.audit import AuditService
from core.services.sequences import next_number
from crm.models import Lead
from support.tickets import create_ticket

from .models import (
    CommissionReceivable,
    Policy,
    PolicyClaim,
    PolicyEndorsement,
    PolicyKyc,
    PolicyOption,
    PolicyOptionSet,
    PolicyProduct,
    PolicyRenewalLead,
)


def add_calendar_months(start: date, months: int) -> date:
    """Anniversary date. 12 months from 1 Jan 2026 is 1 Jan 2027, not day 360."""
    months = int(months)
    index = start.month - 1 + months
    year = start.year + index // 12
    month = index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _require_product(company, product):
    if product is None or product.company_id != company.id:
        raise BusinessRuleError("Policy product is not in this company.")
    return product


@transaction.atomic
def create_option_set(company, user, *, lead, product_ids):
    if lead is None or lead.company_id != company.id:
        raise BusinessRuleError("Lead is not in this company.")
    products = list(PolicyProduct.objects.filter(company=company, pk__in=product_ids, is_active=True))
    if len(products) < 2 or len(products) != len(set(product_ids)):
        raise BusinessRuleError("An option set needs two or more policy products.")
    row = PolicyOptionSet.objects.create(company=company, lead=lead, created_by=user, updated_by=user)
    for product in products:
        PolicyOption.objects.create(
            company=company, option_set=row, product=product, created_by=user, updated_by=user,
        )
    return row


@transaction.atomic
def choose_option(option, user):
    option = PolicyOption.objects.select_for_update().select_related("option_set").get(pk=option.pk)
    PolicyOption.objects.filter(option_set=option.option_set).exclude(pk=option.pk).update(chosen=False)
    option.chosen = True
    option.updated_by = user
    option.save(update_fields=["chosen", "updated_by", "updated_at"])
    return option


@transaction.atomic
def issue_policy(company, user, *, option, customer, nominee, start_date, advisor=None):
    PolicyOptionSet.objects.select_for_update().get(pk=option.option_set_id, company=company)
    option = (
        PolicyOption.objects.select_for_update()
        .select_related("option_set__lead", "product")
        .get(pk=option.pk, company=company)
    )
    if not option.chosen:
        raise BusinessRuleError("Choose one option before issuing a policy.")
    if option.policies.exists():
        return option.policies.select_related("product").first()
    if Policy.objects.filter(
        company=company,
        option__option_set_id=option.option_set_id,
        status=Policy.Status.IN_FORCE,
    ).exists():
        raise BusinessRuleError(
            "This prospect already has an in-force policy. Cancel it before issuing another option."
        )
    if customer is None or customer.company_id != company.id:
        raise BusinessRuleError("Customer is not in this company.")
    product = option.product
    end = add_calendar_months(start_date, int(product.tenure_months))
    lead = option.option_set.lead
    policy = Policy.objects.create(
        company=company,
        customer=customer,
        product=product,
        option=option,
        lead=lead,
        campaign=lead.campaign,
        advisor=advisor,
        nominee=nominee or "",
        start_date=start_date,
        end_date=end,
        premium=product.premium,
        number=next_number(company, "POLICY", prefix="POL"),
        created_by=user,
        updated_by=user,
    )
    AuditService.log(
        company=company, user=user, action="insurance.policy_issued",
        entity_type="Policy", entity_id=policy.pk,
        metadata={"number": policy.number},
    )
    return policy


def _lapse_if_ended(policy):
    today = timezone.localdate()
    if policy.status == Policy.Status.IN_FORCE and policy.end_date and policy.end_date < today:
        policy.status = Policy.Status.EXPIRED
        policy.save(update_fields=["status", "updated_at"])
    return policy


@transaction.atomic
def endorse_policy(policy, user, *, note):
    policy = _lapse_if_ended(Policy.objects.select_for_update().get(pk=policy.pk))
    if policy.status != Policy.Status.IN_FORCE:
        raise BusinessRuleError("Only an in-force policy can be endorsed.")
    if not (note or "").strip():
        raise BusinessRuleError("An endorsement needs a note.")
    row = PolicyEndorsement.objects.create(
        company=policy.company, policy=policy, kind=PolicyEndorsement.Kind.ENDORSE,
        note=note.strip(), created_by=user, updated_by=user,
    )
    AuditService.log(
        company=policy.company, user=user, action="insurance.policy_endorsed",
        entity_type="Policy", entity_id=policy.pk, metadata={"endorsement_id": row.pk},
    )
    return row


@transaction.atomic
def cancel_policy(policy, user, *, note):
    policy = _lapse_if_ended(Policy.objects.select_for_update().get(pk=policy.pk))
    if policy.status != Policy.Status.IN_FORCE:
        raise BusinessRuleError("Only an in-force policy can be cancelled.")
    if not (note or "").strip():
        raise BusinessRuleError("A cancellation needs a note.")
    policy.status = Policy.Status.CANCELLED
    policy.updated_by = user
    policy.save(update_fields=["status", "updated_by", "updated_at"])
    row = PolicyEndorsement.objects.create(
        company=policy.company, policy=policy, kind=PolicyEndorsement.Kind.CANCEL,
        note=note.strip(), created_by=user, updated_by=user,
    )
    AuditService.log(
        company=policy.company, user=user, action="insurance.policy_cancelled",
        entity_type="Policy", entity_id=policy.pk, metadata={"endorsement_id": row.pk},
    )
    return policy


def parse_commission_amount(raw) -> Decimal:
    try:
        amount = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        raise BusinessRuleError("Commission amount must be a number.") from None
    amount = amount.quantize(Decimal("0.01"))
    if amount <= 0:
        raise BusinessRuleError("Commission amount must be positive.")
    if amount > Decimal("999999999999.99"):
        raise BusinessRuleError("Commission amount is too large.")
    return amount


@transaction.atomic
def open_commission(policy, user, *, amount):
    amount = parse_commission_amount(amount)
    return CommissionReceivable.objects.create(
        company=policy.company,
        policy=policy,
        insurer_name=policy.product.insurer_name,
        amount=amount,
        created_by=user,
        updated_by=user,
    )


@transaction.atomic
def renewal_diary(company, user, *, within_days):
    today = timezone.localdate()
    horizon = today + timedelta(days=int(within_days))
    created = []
    due = Policy.objects.filter(
        company=company, status=Policy.Status.IN_FORCE, end_date__gte=today, end_date__lte=horizon,
    ).select_related("customer", "campaign", "product")
    for policy in due:
        try:
            with transaction.atomic():
                if PolicyRenewalLead.objects.filter(company=company, policy=policy).exists():
                    continue
                lead = Lead.objects.create(
                    company=company,
                    name=policy.customer.name,
                    phone=getattr(policy.customer, "phone", "") or "",
                    campaign=policy.campaign,
                    assigned_to=policy.advisor,
                    customer=policy.customer,
                    message=f"Renewal {policy.number} ends {policy.end_date.isoformat()}",
                    created_by=user,
                    updated_by=user,
                )
                PolicyRenewalLead.objects.create(
                    company=company, policy=policy, lead=lead, created_by=user, updated_by=user,
                )
        except IntegrityError:
            continue
        else:
            created.append(lead)
    return created


@transaction.atomic
def open_claim(policy, user, *, summary):
    policy = _lapse_if_ended(Policy.objects.select_for_update().get(pk=policy.pk))
    if policy.status != Policy.Status.IN_FORCE:
        raise BusinessRuleError("Claims are opened on an in-force policy.")
    ticket = create_ticket(
        policy.company, user, customer=policy.customer,
        subject=f"Claim {policy.number}", description=summary or "",
    )
    return PolicyClaim.objects.create(
        company=policy.company, policy=policy, ticket=ticket, summary=summary or "",
        created_by=user, updated_by=user,
    )


@transaction.atomic
def attach_kyc(policy, user, *, kind, file_asset):
    if file_asset is None or file_asset.company_id != policy.company_id:
        raise BusinessRuleError("KYC file is not in this company.")
    return PolicyKyc.objects.create(
        company=policy.company, policy=policy, kind=kind, file=file_asset,
        created_by=user, updated_by=user,
    )


def advisor_book(company, membership):
    from crm.models import Campaign

    today = timezone.localdate()
    Policy.objects.filter(
        company=company, status=Policy.Status.IN_FORCE, end_date__lt=today,
    ).update(status=Policy.Status.EXPIRED, updated_at=timezone.now())
    policies = Policy.objects.filter(company=company, status=Policy.Status.IN_FORCE)
    leads = Lead.objects.filter(company=company)
    campaigns = Campaign.objects.filter(company=company)
    if membership.role != "OWNER":
        policies = policies.filter(advisor=membership)
        leads = leads.filter(assigned_to=membership)
        campaigns = campaigns.filter(leads__assigned_to=membership).distinct()
    return {
        "campaigns": list(campaigns.values("id", "name", "status")[:100]),
        "leads": list(leads.values("id", "name", "status", "campaign_id")[:100]),
        "policies": list(policies.values("id", "number", "status", "end_date", "customer_id")[:100]),
    }
