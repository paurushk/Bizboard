from django.utils import timezone

from core.services.flag_observability import log_flag_event

from .models import ContractServiceEvent
from .status import compute_contract_status

__all__ = [
    "compute_contract_status", "log_service_event", "log_contract_created", "pause_ended_contract_schedules",
    "resume_renewed_contract_schedules",
]


def log_service_event(contract, user, *, ticket=None, notes="", occurred_at=None):
    return ContractServiceEvent.objects.create(
        company=contract.company,
        contract=contract,
        ticket=ticket,
        notes=notes or "",
        occurred_at=occurred_at or timezone.now(),
        created_by=user,
        updated_by=user,
    )


def log_contract_created(contract):
    log_flag_event(contract.company, "ENABLE_CONTRACTS", "contract_created", contract_id=contract.id)


def create_contract_schedule(contract, user):
    """One recurring schedule whose line copies the contract value.

    Saving a contract does not call this. A second call returns the schedule
    already stored on the contract.
    """
    from django.db import transaction

    from core.exceptions import BusinessRuleError
    from sales.models import RecurringInvoiceSchedule

    with transaction.atomic():
        contract = type(contract).objects.select_for_update().get(pk=contract.pk)
        if contract.recurring_schedule_id:
            return contract.recurring_schedule
        product_id = contract.product_id
        if product_id is None:
            covered = contract.covered_products.order_by("id").first()
            product_id = covered.product_id if covered is not None else None
        if product_id is None or contract.value is None:
            raise BusinessRuleError("Set a product and a value before creating the schedule.")
        start = contract.start_date
        today = timezone.localdate()
        if start and start > today:
            from datetime import datetime, time

            next_run = timezone.make_aware(datetime.combine(start, time.min))
        else:
            # A start of today must not enqueue a draft on the next beat.
            # The first automatic invoice is the following month.
            from sales.recurring import advance_next_run

            next_run = advance_next_run(timezone.now(), RecurringInvoiceSchedule.Cadence.MONTHLY)
        schedule = RecurringInvoiceSchedule.objects.create(
            company=contract.company,
            customer=contract.customer,
            cadence=RecurringInvoiceSchedule.Cadence.MONTHLY,
            next_run_at=next_run,
            auto_complete=False,
            line_template={
                "items": [{
                    "product": product_id,
                    "quantity": "1",
                    "unit_price": str(contract.value),
                }],
            },
            notes=f"Contract {contract.number or contract.pk}",
            created_by=user,
            updated_by=user,
        )
        contract.recurring_schedule = schedule
        contract.save(update_fields=["recurring_schedule", "updated_at"])
        if start and start > today:
            # The contract has not started. Drafting now would bill before the term begins and
            # push the first scheduled run a month past the start date. The beat creates it.
            return schedule
        from sales.models import SalesInvoice
        from sales.recurring import generate_draft_for_schedule

        run = generate_draft_for_schedule(schedule, user=user)
        invoice = getattr(run, "invoice", None)
        if invoice is None or invoice.status != SalesInvoice.Status.DRAFT:
            raise BusinessRuleError("The schedule did not create a draft invoice.")
        schedule.draft_invoice_id = invoice.id
    return schedule


def pause_ended_contract_schedules(company_id=None, schedule_ids=None) -> int:
    """Switch off schedules whose every contract has expired or been cancelled.

    A contract's schedule bills monthly; once the contract is over nothing else
    would stop it. A schedule shared with a still-live contract keeps running.
    Returns how many schedules were paused.
    """
    from django.db.models import Count, Q

    from sales.models import RecurringInvoiceSchedule

    from .models import Contract

    ended = [Contract.Status.EXPIRED, Contract.Status.CANCELLED]
    qs = RecurringInvoiceSchedule.objects.filter(is_active=True, contracts__isnull=False)
    if company_id is not None:
        qs = qs.filter(company_id=company_id)
    if schedule_ids is not None:
        qs = qs.filter(pk__in=list(schedule_ids))
    ids = list(
        qs.annotate(live=Count("contracts", filter=~Q(contracts__status__in=ended)))
        .filter(live=0)
        .values_list("pk", flat=True)
    )
    if not ids:
        return 0
    return RecurringInvoiceSchedule.objects.filter(pk__in=ids).update(
        is_active=False, paused_reason=RecurringInvoiceSchedule.PausedReason.CONTRACT_ENDED,
        updated_at=timezone.now(),
    )


def resume_renewed_contract_schedules(company_id, schedule_ids) -> int:
    """Restart a schedule the system paused when its contract ended, once a contract is live again.

    Only a pause made by the contract ending is undone (never one a person chose), and only if the
    customer is active. The next run is the first date after now, so no back-dated invoices appear.
    """
    from sales.models import RecurringInvoiceSchedule
    from sales.recurring import next_future_run

    from .models import Contract

    resumed = 0
    live = [Contract.Status.ACTIVE, Contract.Status.EXPIRING]
    candidates = RecurringInvoiceSchedule.objects.filter(
        company_id=company_id, pk__in=list(schedule_ids), is_active=False,
        paused_reason=RecurringInvoiceSchedule.PausedReason.CONTRACT_ENDED,
        customer__status="ACTIVE", contracts__status__in=live,
    ).distinct()
    for schedule in candidates:
        schedule.next_run_at = next_future_run(schedule)
        schedule.is_active = True
        schedule.paused_reason = ""
        schedule.save(update_fields=["next_run_at", "is_active", "paused_reason", "updated_at"])
        resumed += 1
    return resumed
