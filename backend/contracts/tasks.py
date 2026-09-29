from celery import shared_task
from django.utils import timezone

from core.services.audit import AuditService

from .models import Contract
from .status import compute_contract_status


@shared_task
def refresh_contract_statuses():
    """Per company, under that company's RLS GUC. An argument-free beat used to
    scan with an empty ``app.company_id`` and, once RLS is on, update nothing."""
    from accounts.models import Company
    from core.rls import iter_company_ids, set_rls_company

    today = timezone.localdate()
    changed = 0
    try:
        for cid in iter_company_ids():
            set_rls_company(cid)
            company = Company.objects.filter(pk=cid).first()
            if company is None:
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
    return changed
