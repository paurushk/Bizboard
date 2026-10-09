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


def _real_atomic_blocks(connection):
    return [block for block in connection.atomic_blocks if not getattr(block, "_from_testcase", False)]


def _run_after_savepoint(connection, sid, func):
    """Run func when savepoint sid commits; drop it if that savepoint rolls back.

    Test-only path: CELERY_TASK_ALWAYS_EAGER is refused in production settings.

    on_commit waits for the outermost transaction. Tests keep that open and roll
    it back, so a successful inner complete would never render. A rolled-back
    complete still must not render.
    """
    pending = getattr(connection, "_eager_pdf_on_savepoint", None)
    if pending is None:
        pending = {}
        connection._eager_pdf_on_savepoint = pending
        orig_commit = connection.savepoint_commit
        orig_rollback = connection.savepoint_rollback

        def savepoint_commit(this_sid):
            orig_commit(this_sid)
            for callback in pending.pop(this_sid, ()):
                callback()

        def savepoint_rollback(this_sid):
            orig_rollback(this_sid)
            pending.pop(this_sid, None)

        connection.savepoint_commit = savepoint_commit
        connection.savepoint_rollback = savepoint_rollback
    # Savepoint ids can be reused after an outer rollback. Drop entries whose savepoint
    # no longer exists so a stale callback can never fire for a different document.
    live = set(connection.savepoint_ids)
    for stale in [key for key in pending if key not in live and key != sid]:
        pending.pop(stale, None)
    pending.setdefault(sid, []).append(func)


def _enqueue(task, pk, company_id):
    from core.seed_guard import seed_load_active

    if seed_load_active():
        return
    kwargs = {"company_id": company_id}
    call = lambda t=task, i=pk, k=kwargs: safe_delay(t, i, **k)
    connection = transaction.get_connection()
    real_blocks = _real_atomic_blocks(connection)
    # Eager and not inside a business transaction: render now so tests that are
    # not nested in atomic() still see the PDF. Inside atomic(), wait until that
    # block commits — a rolled-back complete must not generate a PDF.
    if settings.CELERY_TASK_ALWAYS_EAGER and not real_blocks:
        call()
        return
    if not settings.CELERY_TASK_ALWAYS_EAGER or not connection.savepoint_ids:
        transaction.on_commit(call)
        return
    outer_index = connection.atomic_blocks.index(real_blocks[0])
    if outer_index == 0:
        transaction.on_commit(call)
        return
    sid = connection.savepoint_ids[outer_index - 1]
    if sid is None:
        transaction.on_commit(call)
        return
    _run_after_savepoint(connection, sid, call)


@subscribe("sales_invoice.completed")
def enqueue_invoice_pdf(*, invoice, **kwargs):
    """Queue async PDF after Complete. Task never re-raises into the business txn."""
    from core.seed_guard import seed_load_active

    if seed_load_active():
        return
    _enqueue(generate_invoice_pdf, invoice.pk, invoice.company_id)
    try:
        from insights.telemetry import record_pdf_started

        record_pdf_started(invoice.company, user=getattr(invoice, "updated_by", None))
    except Exception:  # noqa: BLE001
        pass


@subscribe("sales_credit_note.completed")
def enqueue_credit_note_pdf(*, document, **kwargs):
    _enqueue(generate_credit_note_pdf, document.pk, document.company_id)


@subscribe("sales_debit_note.completed")
def enqueue_debit_note_pdf(*, document, **kwargs):
    _enqueue(generate_debit_note_pdf, document.pk, document.company_id)


@subscribe("delivery_challan.completed")
def enqueue_challan_pdf(*, document, **kwargs):
    _enqueue(generate_challan_pdf, document.pk, document.company_id)
