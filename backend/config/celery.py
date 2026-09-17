import inspect
import os

from celery import Celery
from celery.signals import before_task_publish, task_failure, task_postrun, task_prerun

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("bizboard")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# BB-000709: include note/challan/notification ids; prefer company_id in kwargs
# so we never SELECT tenant rows before setting the RLS GUC.
_DOC_ID_KEYS = (
    "invoice_id",
    "sales_invoice_id",
    "purchase_id",
    "purchase_invoice_id",
    "note_id",
    "challan_id",
    "notification_id",
)


def _company_id_from_document(key: str, pk) -> int | None:
    """Resolve company_id from document key if caller only passed document PK."""
    if not pk:
        return None
    try:
        if key in ("invoice_id", "sales_invoice_id"):
            from sales.models import SalesInvoice

            return SalesInvoice.objects.filter(pk=pk).values_list("company_id", flat=True).first()
        if key in ("purchase_id", "purchase_invoice_id"):
            from purchases.models import PurchaseInvoice

            return (
                PurchaseInvoice.objects.filter(pk=pk).values_list("company_id", flat=True).first()
            )
        if key == "note_id":
            from sales.models import SalesCreditNote, SalesDebitNote

            cid = SalesCreditNote.objects.filter(pk=pk).values_list("company_id", flat=True).first()
            if cid is not None:
                return cid
            return SalesDebitNote.objects.filter(pk=pk).values_list("company_id", flat=True).first()
        if key == "challan_id":
            from sales.models import DeliveryChallan

            return DeliveryChallan.objects.filter(pk=pk).values_list("company_id", flat=True).first()
        if key == "notification_id":
            from core.models import Notification

            return Notification.objects.filter(pk=pk).values_list("company_id", flat=True).first()
    except Exception:  # noqa: BLE001
        return None
    return None


def _company_id_from_document_disabled(key: str, pk) -> int | None:
    """Kept for tests that patch the old lookup; production never calls this."""
    try:
        if key in ("invoice_id", "sales_invoice_id"):
            from sales.models import SalesInvoice

            return SalesInvoice.objects.filter(pk=pk).values_list("company_id", flat=True).first()
        if key in ("purchase_id", "purchase_invoice_id"):
            from purchases.models import PurchaseInvoice

            return (
                PurchaseInvoice.objects.filter(pk=pk).values_list("company_id", flat=True).first()
            )
        if key == "note_id":
            from sales.models import SalesCreditNote, SalesDebitNote

            cid = SalesCreditNote.objects.filter(pk=pk).values_list("company_id", flat=True).first()
            if cid is not None:
                return cid
            return SalesDebitNote.objects.filter(pk=pk).values_list("company_id", flat=True).first()
        if key == "challan_id":
            from sales.models import DeliveryChallan

            return DeliveryChallan.objects.filter(pk=pk).values_list("company_id", flat=True).first()
        if key == "notification_id":
            from core.models import Notification

            return Notification.objects.filter(pk=pk).values_list("company_id", flat=True).first()
    except Exception:  # noqa: BLE001
        return None
    return None


def _merge_task_params(task, args, kwargs) -> dict:
    merged = dict(kwargs or {})
    try:
        run = getattr(task, "run", None)
        if run is None:
            return merged
        params = [
            name
            for name, param in inspect.signature(run).parameters.items()
            if name not in ("self", "cls")
            and param.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]
        for name, value in zip(params, args or ()):
            merged.setdefault(name, value)
    except Exception:  # noqa: BLE001
        return merged
    return merged


@task_prerun.connect
def set_rls_company_for_task(sender=None, task_id=None, task=None, args=None, kwargs=None, **_extras):
    merged = _merge_task_params(task, args, kwargs)
    # Prefer company_id from kwargs — set GUC without any tenant SELECT.
    company_id = merged.get("company_id")
    if company_id is None:
        # B7-005: the document -> company_id fallback SELECTs a tenant row
        # *before* the RLS GUC is set. On Postgres with FORCE RLS that SELECT
        # returns nothing (company_id stays None -> task runs tenant-blind).
        # Run the lookup under rls_bypass so it can actually resolve the owner.
        from core.rls import rls_bypass

        with rls_bypass():
            for key in _DOC_ID_KEYS:
                pk = merged.get(key)
                if pk is None:
                    continue
                company_id = _company_id_from_document(key, pk)
                if company_id is not None:
                    break
    from core.rls import set_rls_company

    set_rls_company(company_id)
    _bind_task_observability(task=task, task_id=task_id, company_id=company_id)


@task_postrun.connect
def clear_rls_company_for_task(
    sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **_extras
):
    try:
        # task_failure already emits the JSON line for FAILURE.
        if (state or "").upper() not in ("FAILURE", "REJECTED"):
            _log_celery_task(task=task, task_id=task_id, state=state, error=None)
    except Exception:  # noqa: BLE001 — observability must not break tasks
        pass
    from core.rls import set_rls_company

    set_rls_company(None)
    try:
        from core.observability import clear_request_context

        clear_request_context()
    except Exception:  # noqa: BLE001
        pass


@before_task_publish.connect
def _inject_request_id_header(headers=None, **_kwargs):
    if headers is None:
        return
    try:
        from core.observability import current_company_hash, current_request_id

        rid = current_request_id()
        if rid:
            headers.setdefault("request_id", rid)
        ch = current_company_hash()
        if ch:
            headers.setdefault("company_hash", ch)
    except Exception:  # noqa: BLE001
        return


@task_failure.connect
def _on_celery_task_failure(sender=None, task_id=None, exception=None, **_kwargs):
    try:
        from core.ops_metrics import bump_celery_failure

        bump_celery_failure()
    except Exception:  # noqa: BLE001
        pass
    try:
        _log_celery_task(
            task=sender,
            task_id=task_id,
            state="FAILURE",
            error=type(exception).__name__ if exception is not None else "Exception",
        )
    except Exception:  # noqa: BLE001
        pass


def _task_header(req, name: str):
    if req is None:
        return None
    val = getattr(req, name, None)
    if val:
        return val
    if hasattr(req, "get"):
        try:
            val = req.get(name)
        except Exception:  # noqa: BLE001
            val = None
        if val:
            return val
    headers = getattr(req, "headers", None)
    if isinstance(headers, dict):
        return headers.get(name)
    return None


def _bind_task_observability(*, task, task_id, company_id):
    import time

    from core.observability import apply_sentry_tags, bind_request_context, hash_id

    req = getattr(task, "request", None) if task is not None else None
    rid = _task_header(req, "request_id")
    ch = hash_id(company_id) if company_id is not None else None
    header_hash = _task_header(req, "company_hash")
    if header_hash and not ch:
        ch = str(header_hash)
    if req is not None:
        try:
            req._bizboard_started = time.monotonic()
        except Exception:  # noqa: BLE001
            pass
    bind_request_context(request_id=str(rid) if rid else None, company_hash=ch)
    apply_sentry_tags(request_id=str(rid) if rid else None, company_hash=ch, task_id=task_id)


def _log_celery_task(*, task, task_id, state, error):
    import json
    import logging
    import time

    from core.observability import current_company_hash, current_request_id

    req = getattr(task, "request", None) if task is not None else None
    started = getattr(req, "_bizboard_started", None) if req is not None else None
    duration_ms = None
    if started is not None:
        duration_ms = int((time.monotonic() - float(started)) * 1000)
    retries = 0
    if req is not None:
        retries = int(getattr(req, "retries", 0) or 0)
    name = getattr(task, "name", None) or getattr(getattr(task, "request", None), "task", None) or "unknown"
    status = "success"
    st = (state or "").upper()
    if st in ("FAILURE", "REJECTED"):
        status = "failure"
    elif st == "RETRY":
        status = "retry"
    logging.getLogger("bizboard.celery").info(
        json.dumps(
            {
                "event": "celery.task",
                "task": name,
                "task_id": str(task_id) if task_id else None,
                "request_id": current_request_id(),
                "company_hash": current_company_hash(),
                "status": status,
                "duration_ms": duration_ms,
                "retry_count": retries,
                "error": error,
            },
            separators=(",", ":"),
        )
    )

