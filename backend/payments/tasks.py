import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=8)
def execute_gateway_refund(self, outbox_id):
    """Retry adapter.refund after books were unwound (D-018)."""
    from django.db import transaction

    from payments.models import GatewayRefundOutbox, GatewayRefundOutboxStatus
    from payments.services import decrypt_gateway_credentials, get_adapter

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
            # Stale IN_PROGRESS (worker died after the flip) is reclaimable.
            # A live worker refreshed updated_at within the last 10 minutes.
            from datetime import timedelta

            age = timezone.now() - (row.updated_at or timezone.now())
            if age < timedelta(minutes=10):
                return
        row.status = GatewayRefundOutboxStatus.IN_PROGRESS
        row.attempts = (row.attempts or 0) + 1
        row.save(update_fields=["status", "attempts", "updated_at"])
        gp = row.gateway_payment
        company = row.company
        provider_payment_id = row.provider_payment_id
        amount = row.amount
        provider = gp.provider

    creds = decrypt_gateway_credentials(
        getattr(company, "payment_gateway_credentials_encrypted", "") or ""
    )
    adapter = get_adapter(provider, creds if creds else None)
    try:
        adapter.refund(
            provider_payment_id=provider_payment_id,
            amount=amount,
            idempotency_key=f"bb-refund-outbox-{row.id}",
        )
        row.status = GatewayRefundOutboxStatus.SUCCEEDED
        row.last_error = ""
        row.next_attempt_at = None
        row.save(update_fields=["attempts", "status", "last_error", "next_attempt_at", "updated_at"])
        from payments.models import GatewayPaymentStatus

        if gp.status == GatewayPaymentStatus.CAPTURED_PENDING_BOOKS:
            gp.status = GatewayPaymentStatus.REFUNDED
            gp.save(update_fields=["status", "updated_at"])
    except Exception as exc:
        row.status = GatewayRefundOutboxStatus.FAILED
        row.last_error = str(exc)[:2000]
        row.next_attempt_at = timezone.now()
        row.save(update_fields=["attempts", "status", "last_error", "next_attempt_at", "updated_at"])
        logger.exception("Gateway refund outbox %s failed", outbox_id)
        raise


@shared_task
def retry_pending_gateway_refunds():
    from datetime import timedelta

    from django.db.models import Q

    from payments.models import GatewayRefundOutbox, GatewayRefundOutboxStatus

    cutoff = timezone.now() - timedelta(minutes=10)
    qs = GatewayRefundOutbox.objects.filter(
        Q(status__in=(GatewayRefundOutboxStatus.PENDING, GatewayRefundOutboxStatus.FAILED))
        | Q(status=GatewayRefundOutboxStatus.IN_PROGRESS, updated_at__lte=cutoff),
        attempts__lt=8,
    ).order_by("id")[:50]
    for row in qs:
        execute_gateway_refund.delay(row.id)


@shared_task
def run_ar_dunning_task():
    from payments.dunning import run_dunning_all

    return run_dunning_all()


@shared_task
def reconcile_gateway_captures_task():
    from payments.services import PaymentService

    posted, attempted = PaymentService.reconcile_gateway_captures(older_than_minutes=5)
    logger.info("Gateway holding reconcile attempted=%s posted=%s", attempted, posted)
    return {"attempted": attempted, "posted": posted}
