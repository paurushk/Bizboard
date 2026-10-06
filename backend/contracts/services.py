from django.utils import timezone

from core.services.flag_observability import log_flag_event

from .models import ContractServiceEvent
from .status import compute_contract_status

__all__ = ["compute_contract_status", "log_service_event", "log_contract_created"]


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
