"""Nightly reminder for project milestones that are past their target date and still unbilled."""

from celery import shared_task
from django.utils import timezone

from core.services.feature_flags import flag_enabled


@shared_task
def send_milestone_due_reminders():
    from accounts.models import Company, CompanyUser
    from core.care import notify_member
    from core.models import AuditEvent
    from core.rls import iter_company_ids, set_rls_company
    from core.services.audit import AuditService

    from .models import Project, ProjectMilestone

    today = timezone.localdate()
    sent = 0
    try:
        for cid in iter_company_ids():
            set_rls_company(cid)
            company = Company.objects.filter(pk=cid).first()
            if company is None or not flag_enabled(company, "ENABLE_PROJECTS"):
                continue
            owners = list(
                CompanyUser.objects.filter(company=company, role=CompanyUser.Role.OWNER, is_active=True)
                .select_related("user")
            )
            late = ProjectMilestone.objects.filter(
                company_id=cid, target_completion_date__lt=today, project__status=Project.Status.OPEN,
            ).exclude(status=ProjectMilestone.Status.INVOICED).select_related("project")
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
    finally:
        set_rls_company(None)
    return {"reminders": sent}
