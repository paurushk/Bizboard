from django.conf import settings
from django.db import transaction

from core.celery_utils import safe_delay
from core.events import subscribe

from .tasks import (
    generate_challan_pdf,
    generate_credit_note_pdf,
    generate_debit_note_pdf,
    generate_invoice_pdf,
)


def _enqueue(task, pk, company_id):
    kwargs = {"company_id": company_id}
    if settings.CELERY_TASK_ALWAYS_EAGER:
        safe_delay(task, pk, **kwargs)
    else:
        transaction.on_commit(lambda t=task, i=pk, k=kwargs: safe_delay(t, i, **k))


@subscribe("sales_invoice.completed")
def enqueue_invoice_pdf(*, invoice, **kwargs):
    """Queue async PDF after Complete. Task never re-raises into the business txn."""
    _enqueue(generate_invoice_pdf, invoice.pk, invoice.company_id)


@subscribe("sales_credit_note.completed")
def enqueue_credit_note_pdf(*, document, **kwargs):
    _enqueue(generate_credit_note_pdf, document.pk, document.company_id)


@subscribe("sales_debit_note.completed")
def enqueue_debit_note_pdf(*, document, **kwargs):
    _enqueue(generate_debit_note_pdf, document.pk, document.company_id)


@subscribe("delivery_challan.completed")
def enqueue_challan_pdf(*, document, **kwargs):
    _enqueue(generate_challan_pdf, document.pk, document.company_id)
