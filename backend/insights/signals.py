"""DAN-07: an action that changes what the Attention feed says must show on the next load.

The raw feed is cached for 60 s per company. These handlers drop that entry when a document that
feeds it changes, so a posted receipt or a completed invoice does not leave a stale "Fix" row for a
minute.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models.signals import post_delete, post_save


def _drop_cache(sender, instance, **kwargs):
    company_id = getattr(instance, "company_id", None)
    if company_id is None:
        return
    from insights.attention import invalidate_attention_cache_for

    transaction.on_commit(lambda: invalidate_attention_cache_for(company_id))


def connect() -> None:
    from django.apps import apps

    for label in (
        "sales.SalesInvoice",
        "sales.SalesReturn",
        "purchases.PurchaseInvoice",
        "payments.CustomerReceipt",
        "payments.SupplierPayment",
        "payments.PaymentLink",
        "payments.GatewayPayment",
        "payments.PaymentPromise",
    ):
        try:
            model = apps.get_model(label)
        except LookupError:
            continue
        uid = f"insights.attention_cache.{label}"
        post_save.connect(_drop_cache, sender=model, dispatch_uid=uid + ".save", weak=False)
        post_delete.connect(_drop_cache, sender=model, dispatch_uid=uid + ".delete", weak=False)
