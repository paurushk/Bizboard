"""Nightly reminder for project milestones that are past their target date and still unbilled."""

import logging

from celery import shared_task
from django.utils import timezone

from core.services.feature_flags import flag_enabled

logger = logging.getLogger(__name__)


@shared_task
def send_milestone_due_reminders():
    """WP-E1: visits only companies with a milestone past its target; one crash never stops the rest."""
    from core.rls import company_ids_having, set_rls_company

    from .models import ProjectMilestone

    today = timezone.localdate()
    sent = 0
    late_ids = company_ids_having(ProjectMilestone, target_completion_date__lt=today)
    try:
        for cid in late_ids:  # inline-company-loop-ok: light; only companies with a late milestone
            set_rls_company(cid)
            try:
                sent += _remind_company(cid, today)
            except Exception:  # noqa: BLE001 - keep reminding the other companies
                logger.exception("send_milestone_due_reminders failed company=%s", cid)
    finally:
        set_rls_company(None)
    return {"reminders": sent}


def _remind_company(cid, today) -> int:
    from accounts.models import Company, CompanyUser
    from core.care import notify_member
    from core.models import AuditEvent
    from core.services.audit import AuditService

    from .models import Project, ProjectMilestone

    company = Company.objects.filter(pk=cid).first()
    if company is None or not flag_enabled(company, "ENABLE_PROJECTS"):
        return 0
    owners = list(
        CompanyUser.objects.filter(company=company, role=CompanyUser.Role.OWNER, is_active=True)
        .select_related("user")
    )
    late = ProjectMilestone.objects.filter(
        company_id=cid, target_completion_date__lt=today, project__status=Project.Status.OPEN,
    ).exclude(status=ProjectMilestone.Status.INVOICED).select_related("project")
    sent = 0
    for milestone in late:
        marker = f"{milestone.pk}:{milestone.target_completion_date.isoformat()}"
        if AuditEvent.objects.filter(
            company_id=cid, action="milestone_overdue_reminder", entity_type="Project",
            entity_id=str(milestone.project_id), description=marker,
        ).exists():
            continue
        for owner in owners:
            notify_member(
                company, owner,
                subject=f"{milestone.project.number}: milestone '{milestone.name}' is overdue",
                body=f"Target was {milestone.target_completion_date.isoformat()}; not yet invoiced.",
            )
        AuditService.log(
            action="milestone_overdue_reminder", company=company, entity_type="Project",
            entity_id=milestone.project_id, description=marker,
        )
        sent += 1
    return sent
