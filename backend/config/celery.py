import inspect
import os

from celery import Celery
from celery.signals import task_prerun

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
    """Resolve company_id from a document PK — only when kwargs lack company_id."""
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
        for key in _DOC_ID_KEYS:
            pk = merged.get(key)
            if pk is None:
                continue
            company_id = _company_id_from_document(key, pk)
            if company_id is not None:
                break
    from core.rls import set_rls_company

    set_rls_company(company_id)
