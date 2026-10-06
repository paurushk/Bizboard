"""Per company, under that company's RLS GUC. Companies with ENABLE_CONTRACTS
off are counted and left unchanged."""

import logging

from celery import shared_task
from django.utils import timezone

from core.services.audit import AuditService
from core.services.feature_flags import flag_enabled

from .models import Contract
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
    skipped: list[int] = []
    try:
        for cid in iter_company_ids():
            set_rls_company(cid)
            company = Company.objects.filter(pk=cid).first()
            if company is None:
                continue
            if not flag_enabled(company, "ENABLE_CONTRACTS"):
                skipped.append(cid)
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
    finally:
        set_rls_company(None)
    logger.info(
        "refresh_contract_statuses skipped_flag_off=%s companies=%s",
        len(skipped),
        skipped,
    )
    return {"changed": changed, "skipped_flag_off": len(skipped)}
