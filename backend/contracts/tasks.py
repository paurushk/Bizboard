"""Per company, under that company's RLS GUC. Companies with ENABLE_CONTRACTS
off are counted and left unchanged.

WP-E1: each beat visits only the companies that have matching contracts, and one
company's crash is logged and skipped instead of stopping the rest."""

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
    from core.rls import company_ids_having, set_rls_company

    today = timezone.localdate()
    changed = 0
    paused = 0
    skipped: list[int] = []
    failed: list[int] = []
    try:
        for cid in company_ids_having(Contract):  # inline-company-loop-ok: light; only companies with contracts
            set_rls_company(cid)
            try:
                c, p, flag_off = _refresh_company(cid, today)
            except Exception:  # noqa: BLE001 - keep refreshing the other companies
                logger.exception("refresh_contract_statuses failed company=%s", cid)
                failed.append(cid)
                continue
            changed += c
            paused += p
            if flag_off:
                skipped.append(cid)
    finally:
        set_rls_company(None)
    logger.info(
        "refresh_contract_statuses skipped_flag_off=%s companies=%s failed=%s",
        len(skipped),
        skipped,
        failed,
    )
    return {"changed": changed, "skipped_flag_off": len(skipped), "schedules_paused": paused}


def _refresh_company(cid, today) -> tuple[int, int, bool]:
    """(status changes, schedules paused, flag off) for one company."""
    from accounts.models import Company

    company = Company.objects.filter(pk=cid).first()
    if company is None:
        return 0, 0, False
    if not flag_enabled(company, "ENABLE_CONTRACTS"):
        # Statuses are left alone, but a schedule must still stop when its contract is over.
        return 0, pause_ended_contract_schedules(company_id=cid), True
    changed = 0
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
    return changed, pause_ended_contract_schedules(company_id=cid), False


@shared_task
def send_contract_renewal_reminders():
    """Once per contract term, tell the owners a contract is inside its reminder window (CON-09).

    The audit row for ``(contract, end_date)`` is the de-duplication key, so a renewal that moves
    the end date earns a fresh reminder and a re-run on the same day sends nothing.
    """
    from core.rls import company_ids_having, set_rls_company

    today = timezone.localdate()
    sent = 0
    due_ids = company_ids_having(Contract, end_date__gte=today, expiring_from_date__lte=today)
    try:
        for cid in due_ids:  # inline-company-loop-ok: light; only companies with a contract in its window
            set_rls_company(cid)
            try:
                sent += _remind_company(cid, today)
            except Exception:  # noqa: BLE001 - keep reminding the other companies
                logger.exception("send_contract_renewal_reminders failed company=%s", cid)
    finally:
        set_rls_company(None)
    return {"reminders": sent}


def _remind_company(cid, today) -> int:
    from accounts.models import Company, CompanyUser
    from core.care import notify_member
    from core.models import AuditEvent

    company = Company.objects.filter(pk=cid).first()
    if company is None or not flag_enabled(company, "ENABLE_CONTRACTS"):
        return 0
    owners = list(
        CompanyUser.objects.filter(company=company, role=CompanyUser.Role.OWNER, is_active=True)
        .select_related("user")
    )
    due = Contract.objects.filter(
        company_id=cid, end_date__gte=today, expiring_from_date__lte=today,
    ).exclude(status=Contract.Status.CANCELLED).select_related("customer")
    sent = 0
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
    return sent
