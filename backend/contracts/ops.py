"""Contract operations beyond create/read: billing sync, renewal, overlap and coverage lookup."""

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services.audit import AuditService

from .models import Contract, ContractRenewal
from .services import resume_renewed_contract_schedules


def billing_product_id(contract):
    if contract.product_id:
        return contract.product_id
    covered = contract.covered_products.order_by("id").first()
    return covered.product_id if covered is not None else None


def sync_schedule_line(contract, user):
    """Copy the contract's current product and value onto its schedule's billing line (CON-02).

    Only runs still to come are affected; invoices already drafted are left alone.
    """
    with transaction.atomic():
        contract = Contract.objects.select_for_update().get(pk=contract.pk)
        schedule = contract.recurring_schedule
        if schedule is None:
            raise BusinessRuleError("This contract has no billing schedule.")
        product_id = billing_product_id(contract)
        if product_id is None or contract.value is None:
            raise BusinessRuleError("Set a product and a value before updating the billing line.")
        before = dict(schedule.line_template or {})
        schedule.line_template = {
            **before,
            "items": [{"product": product_id, "quantity": "1", "unit_price": str(contract.value)}],
        }
        schedule.updated_by = user
        schedule.save(update_fields=["line_template", "updated_by", "updated_at"])
        AuditService.log(
            action="contract_schedule_synced", company=contract.company, user=user,
            entity_type="Contract", entity_id=contract.pk,
            metadata={"schedule": schedule.pk, "value": str(contract.value), "product": product_id},
        )
    return schedule


def set_schedule_active(contract, user, active: bool):
    from sales.recurring import next_future_run

    schedule = contract.recurring_schedule
    if schedule is None:
        raise BusinessRuleError("This contract has no billing schedule.")
    if active:
        if contract.status in (Contract.Status.EXPIRED, Contract.Status.CANCELLED):
            raise BusinessRuleError("Renew or un-cancel the contract before resuming its billing.")
        schedule.next_run_at = next_future_run(schedule)
        schedule.is_active = True
        schedule.paused_reason = ""
    else:
        schedule.is_active = False
        # A blank reason marks a pause a person chose; only CONTRACT_ENDED is auto-resumed on renewal.
        schedule.paused_reason = ""
    schedule.updated_by = user
    schedule.save(update_fields=["next_run_at", "is_active", "paused_reason", "updated_by", "updated_at"])
    AuditService.log(
        action="contract_schedule_resumed" if active else "contract_schedule_paused",
        company=contract.company, user=user, entity_type="Contract", entity_id=contract.pk,
        metadata={"schedule": schedule.pk},
    )
    return schedule


def renew_contract(contract, user, *, new_end_date, value=None, note=""):
    """Extend the term in place and keep the history (decision D7)."""
    with transaction.atomic():
        contract = Contract.objects.select_for_update().get(pk=contract.pk)
        if contract.status == Contract.Status.CANCELLED:
            raise BusinessRuleError("Un-cancel the contract before renewing it.")
        if new_end_date is None or new_end_date <= contract.end_date:
            raise BusinessRuleError("The new end date must be after the current end date.")
        new_value = contract.value
        if value not in (None, ""):
            try:
                new_value = Decimal(str(value))
            except (InvalidOperation, ValueError):
                raise BusinessRuleError("Value must be a number.") from None
            if new_value < 0:
                raise BusinessRuleError("Value cannot be negative.")
        previous_end, previous_value = contract.end_date, contract.value
        contract.end_date = new_end_date
        contract.value = new_value
        contract.updated_by = user
        contract.save()
        ContractRenewal.objects.create(
            company=contract.company, contract=contract, previous_end_date=previous_end,
            new_end_date=new_end_date, previous_value=previous_value, new_value=new_value,
            note=note or "", created_by=user, updated_by=user,
        )
        AuditService.log(
            action="contract_renewed", company=contract.company, user=user,
            entity_type="Contract", entity_id=contract.pk,
            metadata={"from": previous_end.isoformat(), "to": new_end_date.isoformat()},
        )
        if contract.recurring_schedule_id:
            resume_renewed_contract_schedules(contract.company_id, [contract.recurring_schedule_id])
            if new_value != previous_value:
                sync_schedule_line(contract, user)
    return contract


def find_overlaps(company, customer_id, product_ids, contract_type, start, end, exclude_id=None):
    """Live contracts of the same type for the same customer and product whose term overlaps."""
    if not product_ids or start is None or end is None:
        return Contract.objects.none()
    qs = Contract.objects.filter(
        company=company, customer_id=customer_id, contract_type=contract_type,
        start_date__lte=end, end_date__gte=start,
    ).exclude(status=Contract.Status.CANCELLED)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs.filter(
        Q(product_id__in=product_ids) | Q(covered_products__product_id__in=product_ids)
    ).distinct()


def coverage_for(company, customer_id, product_id, on_date=None):
    """Contracts that cover this product for this customer on a date (XLK-02).

    Matches the main product and every covered product, and judges the term by its dates, never by
    the cached status.
    """
    on_date = on_date or timezone.localdate()
    qs = Contract.objects.filter(
        company=company, customer_id=customer_id, start_date__lte=on_date, end_date__gte=on_date,
    ).exclude(status=Contract.Status.CANCELLED)
    if product_id:
        qs = qs.filter(Q(product_id=product_id) | Q(covered_products__product_id=product_id))
    return qs.distinct().order_by("end_date", "id")
