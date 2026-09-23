"""Lead capture that was accepted on the request and finishes in the worker."""

from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

STALE_AFTER = timedelta(minutes=15)


@shared_task
def process_lead_ingest(job_id: int) -> None:
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
