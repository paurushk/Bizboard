import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=8)
def execute_gateway_refund(self, outbox_id):
    """Retry adapter.refund after books were unwound (D-018)."""
    from payments.models import GatewayRefundOutbox, GatewayRefundOutboxStatus
    from payments.services import decrypt_gateway_credentials, get_adapter

    row = GatewayRefundOutbox.objects.select_related("gateway_payment", "company").filter(pk=outbox_id).first()
    if row is None:
        return
    if row.status == GatewayRefundOutboxStatus.SUCCEEDED:
        return
    gp = row.gateway_payment
    creds = decrypt_gateway_credentials(
        getattr(row.company, "payment_gateway_credentials_encrypted", "") or ""
    )
    adapter = get_adapter(gp.provider, creds if creds else None)
    row.attempts = (row.attempts or 0) + 1
    try:
        adapter.refund(provider_payment_id=row.provider_payment_id, amount=row.amount)
        row.status = GatewayRefundOutboxStatus.SUCCEEDED
        row.last_error = ""
        row.next_attempt_at = None
        row.save(update_fields=["attempts", "status", "last_error", "next_attempt_at", "updated_at"])
    except Exception as exc:
        row.status = GatewayRefundOutboxStatus.FAILED
        row.last_error = str(exc)[:2000]
        row.next_attempt_at = timezone.now()
        row.save(update_fields=["attempts", "status", "last_error", "next_attempt_at", "updated_at"])
        logger.exception("Gateway refund outbox %s failed", outbox_id)
        raise


@shared_task
def retry_pending_gateway_refunds():
    from payments.models import GatewayRefundOutbox, GatewayRefundOutboxStatus

    qs = GatewayRefundOutbox.objects.filter(
        status__in=(GatewayRefundOutboxStatus.PENDING, GatewayRefundOutboxStatus.FAILED),
        attempts__lt=8,
    ).order_by("id")[:50]
    for row in qs:
        execute_gateway_refund.delay(row.id)
