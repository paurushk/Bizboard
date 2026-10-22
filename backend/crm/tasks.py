"""Lead capture that was accepted on the request and finishes in the worker."""

import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

STALE_AFTER = timedelta(minutes=15)


logger = logging.getLogger("bizboard.crm")

GENERIC_FAILURE = "The import stopped unexpectedly. Try again, and contact support if it keeps happening."


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
                name=str(payload.get("name") or ""),
            )
            result = {"ok": True, "lead_id": lead.id if lead else None}
    except (BusinessRuleError, ValidationError) as exc:
        _fail(job_id, "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc))
        return
    except Exception:  # noqa: BLE001 — a job must always end DONE or FAILED, never sit RUNNING
        logger.exception("lead_ingest_failed job_id=%s company_id=%s", job_id, getattr(job, "company_id", None))
        _fail(job_id, GENERIC_FAILURE)
        return
    # E1: the rows hold names, phones and emails; once imported they are not kept.
    LeadIngestJob.objects.filter(pk=job_id, status=LeadIngestJob.Status.RUNNING).update(
        status=LeadIngestJob.Status.DONE,
        result=result,
        error="",
        payload={},
        updated_at=timezone.now(),
    )


def _fail(job_id: int, message: str) -> None:
    from crm.models import LeadIngestJob

    LeadIngestJob.objects.filter(pk=job_id).update(
        status=LeadIngestJob.Status.FAILED,
        error=message[:500],
        payload={},
        updated_at=timezone.now(),
    )


@shared_task
def reap_stale_lead_ingest_jobs() -> dict:
    """A job stuck RUNNING (worker died) is retried once, then marked FAILED."""
    from core.rls import company_scope, rls_bypass
    from crm.models import LeadIngestJob

    cutoff = timezone.now() - STALE_AFTER
    retried = failed = 0
    # A beat task has no tenant: under FORCE RLS an unscoped read finds no job (WP-C2).
    with rls_bypass():
        stale = list(
            LeadIngestJob.objects.filter(status=LeadIngestJob.Status.RUNNING, updated_at__lt=cutoff)
            .values_list("id", "company_id", "payload")
        )
    for job_id, company_id, payload in stale:
        payload = dict(payload or {})
        with company_scope(company_id):
            if int(payload.get("_retries") or 0) >= 1:
                _fail(job_id, "The import did not finish in time. Upload it again.")
                failed += 1
                continue
            payload["_retries"] = 1
            LeadIngestJob.objects.filter(pk=job_id).update(
                status=LeadIngestJob.Status.PENDING, payload=payload, updated_at=timezone.now(),
            )
        process_lead_ingest.delay(job_id, company_id=company_id)
        retried += 1
    return {"retried": retried, "failed": failed}


@shared_task
def remind_due_lead_activities() -> dict:
    """One in-app reminder per due lead activity. Quiet hours leave reminded_at empty."""
    from crm.models import LeadActivity

    from core.rls import company_ids_having, set_rls_company

    now = timezone.now()
    sent = 0
    quiet = 0
    due_filter = {"due_at__isnull": False, "reminded_at__isnull": True, "due_at__lte": now}
    # A beat task has no tenant: find the companies with a due activity under the bypass,
    # then read and notify one company at a time under its own RLS context (WP-C2).
    try:
        for cid in company_ids_having(LeadActivity, **due_filter):  # inline-company-loop-ok: only companies with a due activity
            set_rls_company(cid)
            try:
                s, q = _remind_company_activities(cid, now, due_filter)
            except Exception:  # noqa: BLE001 - keep reminding the other companies
                logger.exception("remind_due_lead_activities failed company=%s", cid)
                continue
            sent += s
            quiet += q
    finally:
        set_rls_company(None)
    return {"sent": sent, "quiet": quiet}


def _remind_company_activities(company_id, now, due_filter) -> tuple[int, int]:
    from accounts.models import CompanyUser
    from core.models import Notification
    from core.services.notifications import NotificationService
    from crm.models import LeadActivity
    from payments.dunning import in_quiet_hours

    sent = quiet = 0
    due = (
        LeadActivity.objects.filter(company_id=company_id, **due_filter)
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
    return sent, quiet
