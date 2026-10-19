"""Per company, under that company's RLS GUC. Companies with ENABLE_CONTRACTS
off are counted and left unchanged."""

import logging

from celery import shared_task
from django.utils import timezone

from core.services.audit import AuditService
from core.services.feature_flags import flag_enabled

from .models import Contract
from .services import pause_ended_contract_schedules
from .status import compute_contract_status

logger = logging.getLogger(__name__)


@shared_task
def refresh_contract_statuses():
    """Per company, under that company's RLS GUC. An argument-free beat used to
    scan with an empty ``app.company_id`` and, once RLS is on, update nothing."""
    from accounts.models import Company
    from core.rls import iter_company_ids, set_rls_company

    today = timezone.localdate()
    changed = 0
    paused = 0
    skipped: list[int] = []
    try:
        for cid in iter_company_ids():
            set_rls_company(cid)
            company = Company.objects.filter(pk=cid).first()
            if company is None:
                continue
            if not flag_enabled(company, "ENABLE_CONTRACTS"):
                skipped.append(cid)
                # Statuses are left alone, but a schedule must still stop when its contract is over.
                paused += pause_ended_contract_schedules(company_id=cid)
                continue
            qs = (
                Contract.objects.filter(company_id=cid)
                .exclude(status=Contract.Status.CANCELLED)
                .only("id", "end_date", "renewal_reminder_days", "status")
                .iterator()
            )
            for contract in qs:
                new_status = compute_contract_status(
                    contract.end_date, contract.renewal_reminder_days, today,
                )
                if new_status == contract.status:
                    continue
                Contract.objects.filter(pk=contract.pk, company_id=cid).update(
                    status=new_status, updated_at=timezone.now(),
                )
                AuditService.log(
                    action="contract_status_refreshed",
                    company=company,
                    entity_type="Contract",
                    entity_id=contract.pk,
                    metadata={"status": new_status},
                )
                changed += 1
            # An ended contract must stop billing: pause the schedule it created.
            paused += pause_ended_contract_schedules(company_id=cid)
    finally:
        set_rls_company(None)
    logger.info(
        "refresh_contract_statuses skipped_flag_off=%s companies=%s",
        len(skipped),
        skipped,
    )
    return {"changed": changed, "skipped_flag_off": len(skipped), "schedules_paused": paused}


@shared_task
def send_contract_renewal_reminders():
    """Once per contract term, tell the owners a contract is inside its reminder window (CON-09).

    The audit row for ``(contract, end_date)`` is the de-duplication key, so a renewal that moves
    the end date earns a fresh reminder and a re-run on the same day sends nothing.
    """
    from accounts.models import Company, CompanyUser
    from core.care import notify_member
    from core.models import AuditEvent
    from core.rls import iter_company_ids, set_rls_company

    today = timezone.localdate()
    sent = 0
    try:
        for cid in iter_company_ids():
            set_rls_company(cid)
            company = Company.objects.filter(pk=cid).first()
            if company is None or not flag_enabled(company, "ENABLE_CONTRACTS"):
                continue
            owners = list(
                CompanyUser.objects.filter(company=company, role=CompanyUser.Role.OWNER, is_active=True)
                .select_related("user")
            )
            due = Contract.objects.filter(
                company_id=cid, end_date__gte=today, expiring_from_date__lte=today,
            ).exclude(status=Contract.Status.CANCELLED).select_related("customer")
            for contract in due:
                marker = f"{contract.pk}:{contract.end_date.isoformat()}"
                if AuditEvent.objects.filter(
                    company_id=cid, action="contract_renewal_reminder", entity_type="Contract",
                    entity_id=str(contract.pk), description=marker,
                ).exists():
                    continue
                days = (contract.end_date - today).days
                for owner in owners:
                    notify_member(
                        company, owner,
                        subject=f"{contract.number} for {contract.customer.name} ends in {days} days",
                        body=f"Renew {contract.number} before {contract.end_date.isoformat()}.",
                    )
                AuditService.log(
                    action="contract_renewal_reminder", company=company, entity_type="Contract",
                    entity_id=contract.pk, description=marker,
                )
                sent += 1
    finally:
        set_rls_company(None)
    return {"reminders": sent}
