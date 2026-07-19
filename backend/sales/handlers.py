from django.conf import settings
from django.db import transaction

from core.events import subscribe

from .tasks import generate_invoice_pdf


@subscribe("sales_invoice.completed")
def enqueue_invoice_pdf(*, invoice, **kwargs):
    """Queue async PDF after the business post succeeds (§14)."""
    if settings.CELERY_TASK_ALWAYS_EAGER:
        # Eager mode runs in-process within the same transaction.
        generate_invoice_pdf.delay(invoice.pk)
    else:
        transaction.on_commit(lambda: generate_invoice_pdf.delay(invoice.pk))
