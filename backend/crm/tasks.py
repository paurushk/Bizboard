"""Lead capture that was accepted on the request and finishes in the worker."""

from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

STALE_AFTER = timedelta(minutes=15)


@shared_task
def process_lead_ingest(job_id: int, company_id: int | None = None) -> None:
    from django.core.exceptions import ValidationError

    from core.exceptions import BusinessRuleError
    from crm.models import LeadIngestJob
    from crm.pipeline import import_lead_rows, ingest_whatsapp_message

    with transaction.atomic():
        try:
            job = LeadIngestJob.objects.select_for_update().get(pk=job_id)
        except LeadIngestJob.DoesNotExist:
            return
        if job.status == LeadIngestJob.Status.DONE:
            return
        if job.status == LeadIngestJob.Status.FAILED:
            return
        fresh = job.status == LeadIngestJob.Status.PENDING
        stale = (
            job.status == LeadIngestJob.Status.RUNNING
            and job.updated_at < timezone.now() - STALE_AFTER
        )
        if not fresh and not stale:
            return
        job.status = LeadIngestJob.Status.RUNNING
        job.save(update_fields=["status", "updated_at"])
        kind = job.kind
        payload = job.payload or {}

    job = LeadIngestJob.objects.select_related("company").get(pk=job_id)
    try:
        if kind == LeadIngestJob.Kind.CSV:
            result = import_lead_rows(job.company, job.created_by, payload.get("rows") or [])
        else:
            lead = ingest_whatsapp_message(
                job.company,
                message_id=str(payload.get("message_id") or ""),
                sender=str(payload.get("sender") or ""),
                text=str(payload.get("text") or ""),
                sent_at=str(payload.get("sent_at") or ""),
            )
            result = {"ok": True, "lead_id": lead.id if lead else None}
    except (BusinessRuleError, ValidationError) as exc:
        LeadIngestJob.objects.filter(pk=job_id).update(
            status=LeadIngestJob.Status.FAILED,
            error=str(exc),
            updated_at=timezone.now(),
        )
        return
    LeadIngestJob.objects.filter(pk=job_id, status=LeadIngestJob.Status.RUNNING).update(
        status=LeadIngestJob.Status.DONE,
        result=result,
        error="",
        updated_at=timezone.now(),
    )


@shared_task
def remind_due_lead_activities() -> dict:
    """One in-app reminder per due lead activity. Quiet hours leave reminded_at empty."""
    from accounts.models import CompanyUser
    from core.models import Notification
    from core.services.notifications import NotificationService
    from crm.models import LeadActivity
    from payments.dunning import in_quiet_hours

    now = timezone.now()
    sent = 0
    quiet = 0
    due = (
        LeadActivity.objects.filter(due_at__isnull=False, reminded_at__isnull=True, due_at__lte=now)
        .select_related("lead", "lead__assigned_to__user", "company")
        .order_by("id")
    )
    for activity in due.iterator():
        if in_quiet_hours(activity.company, now):
            quiet += 1
            continue
        assignee = activity.lead.assigned_to
        recipient = ""
        if assignee is not None and getattr(assignee, "user", None) is not None:
            recipient = (assignee.user.email or "").strip()
        if not recipient:
            owner = (
                CompanyUser.objects.filter(
                    company=activity.company, role=CompanyUser.Role.OWNER, is_active=True,
                )
                .select_related("user")
                .order_by("id")
                .first()
            )
            recipient = (owner.user.email if owner else "") or "in-app"
        NotificationService.send(
            company=activity.company,
            channel=Notification.Channel.IN_APP,
            recipient=recipient,
            subject=f"Lead follow-up due — {activity.lead.name}",
            body=activity.body,
        )
        activity.reminded_at = now
        activity.save(update_fields=["reminded_at", "updated_at"])
        sent += 1
    return {"sent": sent, "quiet": quiet}
