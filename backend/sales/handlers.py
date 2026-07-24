from django.conf import settings
from django.db import transaction

from core.events import subscribe

from .tasks import generate_invoice_pdf


@subscribe("sales_invoice.completed")
def enqueue_invoice_pdf(*, invoice, **kwargs):
    """Queue async PDF after Complete. Task never re-raises into the business txn."""
    invoice_id = invoice.pk
    if settings.CELERY_TASK_ALWAYS_EAGER:
        # In-process (dev/tests): run immediately. generate_invoice_pdf swallows errors
        # so a render failure cannot roll back Complete.
        generate_invoice_pdf.delay(invoice_id)
    else:
        transaction.on_commit(lambda: generate_invoice_pdf.delay(invoice_id))
