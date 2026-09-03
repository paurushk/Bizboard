import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_REFUND_ATTEMPTS = 20
FAST_REFUND_ATTEMPTS = 8


@shared_task(bind=True, max_retries=0)
def execute_gateway_refund(self, outbox_id, company_id=None):
    """Retry adapter.refund; unwind books only after the provider confirms.

    ``company_id`` must be passed so Celery RLS prerun can SET the GUC before
    any tenant SELECT. Callers that omit it no-op under POSTGRES_RLS_ENABLED.
    Beat retries (not Celery autoretry) so FAILED does not burn the attempt cap.
    """
    from django.db import transaction

    from payments.models import GatewayPaymentStatus, GatewayRefundOutbox, GatewayRefundOutboxStatus
    from payments.services import decrypt_gateway_credentials, get_adapter, refund_idempotency_key

    with transaction.atomic():
        row = (
            GatewayRefundOutbox.objects.select_for_update()
            .select_related("gateway_payment", "company")
            .filter(pk=outbox_id)
            .first()
        )
        if row is None:
            return
        if row.status == GatewayRefundOutboxStatus.SUCCEEDED:
            return
        if row.status == GatewayRefundOutboxStatus.IN_PROGRESS:
            from datetime import timedelta

            age = timezone.now() - (row.updated_at or timezone.now())
            if age < timedelta(minutes=10):
                return
        gp = row.gateway_payment
        if gp.status == GatewayPaymentStatus.REFUNDED:
            row.status = GatewayRefundOutboxStatus.SUCCEEDED
            row.last_error = ""
            row.next_attempt_at = None
            row.save(update_fields=["status", "last_error", "next_attempt_at", "updated_at"])
            return
        row.status = GatewayRefundOutboxStatus.IN_PROGRESS
        row.attempts = (row.attempts or 0) + 1
        row.save(update_fields=["status", "attempts", "updated_at"])
        company = row.company
        provider_payment_id = row.provider_payment_id
        amount = row.amount
        provider = gp.provider
        key = (getattr(row, "idempotency_key", None) or "").strip() or refund_idempotency_key(
            gp.id, amount
        )

    creds = decrypt_gateway_credentials(
        getattr(company, "payment_gateway_credentials_encrypted", "") or ""
    )
    adapter = get_adapter(provider, creds if creds else None)
    try:
        refund_id = provider_payment_id
        if provider == "cashfree":
            from payments.gateway import cashfree_order_id_for_refund

            refund_id = cashfree_order_id_for_refund(
                provider_payment_id, getattr(gp, "raw_payload", None)
            )
        adapter.refund(
            provider_payment_id=refund_id,
            amount=amount,
            idempotency_key=key,
        )
        from payments.services import PaymentService

        from decimal import Decimal

        remaining = Decimal(str(gp.amount or 0))
        raw = gp.raw_payload if isinstance(gp.raw_payload, dict) else {}
        for prior in raw.get("partial_refunds") or []:
            try:
                remaining -= Decimal(str((prior or {}).get("amount") or 0))
            except Exception:
                continue
        remaining = max(Decimal("0"), remaining)
        full = amount >= remaining
        already_unwound = (
            bool(raw.get("books_unwound"))
            or gp.status == GatewayPaymentStatus.REFUNDED
            or (key in (raw.get("applied_refund_keys") or []))
        )
        with transaction.atomic():
            if not already_unwound:
                # `refund_key` makes this idempotent for PARTIAL refunds too
                # (B4-001): a retried task cannot double-unwind.
                PaymentService._unwind_refund_books(
                    gp,
                    user=row.updated_by or row.created_by,
                    refund_amount=amount,
                    reason="outbox",
                    full=full,
                    refund_key=key,
                )
                # Move gp -> REFUNDED / PARTIALLY_REFUNDED and record the
                # partial-refund entry, same as the synchronous path.
                PaymentService._finalise_refund_state(
                    gp,
                    refund_amount=amount,
                    reason="outbox",
                    full=full,
                    user=row.updated_by or row.created_by,
                )
            row.status = GatewayRefundOutboxStatus.SUCCEEDED
            row.last_error = ""
            row.next_attempt_at = None
            row.save(update_fields=["attempts", "status", "last_error", "next_attempt_at", "updated_at"])
            if full and gp.status != GatewayPaymentStatus.REFUNDED:
                gp.status = GatewayPaymentStatus.REFUNDED
                gp.save(update_fields=["status", "updated_at"])
    except Exception as exc:
        from datetime import timedelta

        row.status = GatewayRefundOutboxStatus.FAILED
        row.last_error = str(exc)[:2000]
        delay_minutes = 10 if (row.attempts or 0) < FAST_REFUND_ATTEMPTS else 360
        row.next_attempt_at = timezone.now() + timedelta(minutes=delay_minutes)
        row.save(update_fields=["attempts", "status", "last_error", "next_attempt_at", "updated_at"])
        logger.exception("Gateway refund outbox %s failed", outbox_id)


@shared_task
def retry_pending_gateway_refunds():
    from datetime import timedelta

    from django.db.models import Q

    from core.rls import iter_company_ids, set_rls_company
    from payments.models import GatewayRefundOutbox, GatewayRefundOutboxStatus

    cutoff = timezone.now() - timedelta(minutes=10)
    now = timezone.now()
    for cid in iter_company_ids():
        set_rls_company(cid)
        qs = GatewayRefundOutbox.objects.filter(company_id=cid).filter(
            Q(status__in=(GatewayRefundOutboxStatus.PENDING, GatewayRefundOutboxStatus.FAILED))
            | Q(status=GatewayRefundOutboxStatus.IN_PROGRESS, updated_at__lte=cutoff),
        ).filter(
            Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now)
        ).order_by("id")[:50]
        for row in qs:
            if (row.attempts or 0) >= MAX_REFUND_ATTEMPTS:
                continue
            execute_gateway_refund.delay(row.id, company_id=row.company_id)
    set_rls_company(None)


@shared_task
def run_ar_dunning_task():
    from core.rls import iter_company_ids, set_rls_company
    from payments.dunning import run_dunning_for_company
    from accounts.models import Company

    totals = {"sent": 0, "skipped": 0, "companies": 0}
    for cid in iter_company_ids():
        set_rls_company(cid)
        company = Company.objects.filter(pk=cid, dunning_enabled=True).first()
        if company is None:
            continue
        result = run_dunning_for_company(company)
        totals["sent"] += result.get("sent", 0)
        totals["skipped"] += result.get("skipped", 0)
        totals["companies"] += 1
    set_rls_company(None)
    return totals


@shared_task
def reconcile_gateway_captures_task():
    from core.rls import iter_company_ids, set_rls_company
    from payments.services import PaymentService

    posted = attempted = 0
    for cid in iter_company_ids():
        set_rls_company(cid)
        p, a = PaymentService.reconcile_gateway_captures(company_id=cid, older_than_minutes=5)
        posted += p
        attempted += a
    set_rls_company(None)
    logger.info("Gateway holding reconcile attempted=%s posted=%s", attempted, posted)
    return {"attempted": attempted, "posted": posted}
