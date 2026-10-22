"""WP-GR2: the onboarding checklist on the home screen, and the time each step first happened.

Each step is stamped once on ``TenantActivation`` when the real action happens (model signals
below, wired in ``BillingConfig.ready``) — never from the client. No separate telemetry event is
written: the timestamps are the record (a second event would be the dual write OG2-E8 forbids,
and ``invoice_complete`` already feeds Journey Health). The card hides at
100% or when the owner dismisses it. PO2's monthly table reads ``first_invoice_at`` for the
median time to first invoice by sign-up week.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# (step, TenantActivation field). Order is the order shown on the card.
STEPS: tuple[tuple[str, str], ...] = (
    ("gstin_verified", "gstin_verified_at"),
    ("first_item", "first_item_at"),
    ("first_party", "first_party_at"),
    ("first_invoice", "first_invoice_at"),
    ("first_purchase", "first_purchase_at"),
    ("first_payment", "first_payment_at"),
    ("invited_user", "invited_user_at"),
    ("imported", "imported_at"),
)
_FIELD = dict(STEPS)


def mark(company_or_id, step: str) -> None:
    """Stamp ``step`` the first time. Never raises (a checklist must not break a money path)."""
    from billing.models import TenantActivation

    field = _FIELD.get(step)
    if field is None or company_or_id is None:
        return
    from django.core.cache import cache

    company_id = getattr(company_or_id, "pk", company_or_id)
    done_key = f"gr2:done:{company_id}:{step}"
    if cache.get(done_key):
        return  # already stamped: keeps a bulk import of thousands of rows from querying each time
    try:
        with transaction.atomic():
            row, _ = TenantActivation.objects.get_or_create(company_id=company_id)
            if getattr(row, field) is not None:
                cache.set(done_key, 1, 24 * 3600)
                return
            setattr(row, field, timezone.now())
            row.save(update_fields=[field, "updated_at"])
    except Exception:  # noqa: BLE001
        logger.debug("onboarding mark %s failed for company %s", step, company_id, exc_info=True)
        return
    cache.set(done_key, 1, 24 * 3600)


def checklist(company) -> dict:
    from billing.models import TenantActivation

    row = TenantActivation.objects.filter(company=company).first()
    steps = [{"step": step, "done_at": getattr(row, field, None) if row else None} for step, field in STEPS]
    done = sum(1 for s in steps if s["done_at"])
    return {
        "steps": steps,
        "done": done,
        "total": len(steps),
        "dismissed": bool(row and row.checklist_dismissed_at),
        "visible": not (row and row.checklist_dismissed_at) and done < len(steps),
    }


def dismiss(company) -> None:
    from billing.models import TenantActivation

    row, _ = TenantActivation.objects.get_or_create(company=company)
    if row.checklist_dismissed_at is None:
        row.checklist_dismissed_at = timezone.now()
        row.save(update_fields=["checklist_dismissed_at", "updated_at"])


# --- signal handlers ---------------------------------------------------------------------------


def _on_product(sender, instance, created, **kwargs):
    if created and not kwargs.get("raw"):
        mark(instance.company_id, "first_item")


def _on_party(sender, instance, created, **kwargs):
    if created and not kwargs.get("raw") and not getattr(instance, "is_pos_walk_in", False):
        mark(instance.company_id, "first_party")


def _on_purchase(sender, instance, **kwargs):
    if not kwargs.get("raw") and getattr(instance, "status", "") == "COMPLETED":
        mark(instance.company_id, "first_purchase")


def _on_payment(sender, instance, created, **kwargs):
    if created and not kwargs.get("raw"):
        mark(instance.company_id, "first_payment")


def _on_member(sender, instance, created, **kwargs):
    if created and not kwargs.get("raw") and getattr(instance, "role", "") != "OWNER":
        mark(instance.company_id, "invited_user")


def _on_import(sender, instance, **kwargs):
    if not kwargs.get("raw") and getattr(instance, "status", "") == "COMMITTED":
        mark(instance.company_id, "imported")


def _on_company(sender, instance, **kwargs):
    if not kwargs.get("raw") and getattr(instance, "gstin_verification_status", "") == "VERIFIED":
        mark(instance.pk, "gstin_verified")


def connect() -> None:
    from django.db.models.signals import post_save

    pairs = (
        ("masters", "Product", _on_product),
        ("masters", "Customer", _on_party),
        ("masters", "Supplier", _on_party),
        ("purchases", "PurchaseInvoice", _on_purchase),
        ("payments", "CustomerReceipt", _on_payment),
        ("payments", "SupplierPayment", _on_payment),
        ("accounts", "CompanyUser", _on_member),
        ("imports", "ImportJob", _on_import),
        ("accounts", "Company", _on_company),
    )
    from django.apps import apps

    for app_label, model_name, handler in pairs:
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            continue
        post_save.connect(handler, sender=model, dispatch_uid=f"gr2-onboarding-{app_label}-{model_name}")
