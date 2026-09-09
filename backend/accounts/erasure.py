"""SR-40..45 / D13 — automated tenant right-to-erasure.

Two modes:

* ``tombstone`` (default for the owner endpoint) — the founder-signed retention
  carve-out (SR-40): every operational row is deleted, but the **statutory tax
  documents** (sales/purchase invoices, credit/debit notes, returns, Bill of
  Entry, GST return snapshots and periods) are kept with all **party PII
  scrubbed**, and the ``Company`` row survives as a scrubbed tombstone with
  ``erased_at`` set. ``purge_expired_tombstones`` hard-deletes them once the
  8-year GST retention window elapses.

* ``hard`` — used by the CLI, the sandbox sweep and the purge job: the company
  and 100% of its rows go, nothing kept.

Every mode writes an immutable :class:`~accounts.models.TenantErasureLog` that
carries **no** party PII. Idempotent.

:func:`assert_erasure_model_coverage` is the SR-41 drift guard — it fails if a
new model gains a ``company`` FK that is neither auto-resolved by
``company.delete()``, explicitly handled here, nor in the retained set.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import timedelta

from django.apps import apps
from django.db import transaction
from django.db.models import ProtectedError
from django.utils import timezone

GST_RETENTION = timedelta(days=365 * 8 + 2)

# Company FKs cleared by hand before ``company.delete()`` (their on_delete is PROTECT).
PROTECT_MODELS_HANDLED = {
    "core.AuditEvent",
    "core.MoneyFieldAudit",
    "core.StatutoryDocumentEvent",
}
_SAFE_ON_DELETE = {"CASCADE", "SET_NULL", "SET_DEFAULT", "DO_NOTHING"}

# Statutory tax documents (+ the masters they PROTECT-reference) kept in
# ``tombstone`` mode with party PII scrubbed.
TOMBSTONE_RETAINED = {
    "masters.Customer", "masters.Supplier", "masters.Product", "masters.Unit",
    "masters.Category", "masters.Brand", "masters.TaxRate", "masters.PaymentMode",
    "masters.ExpenseCategory", "masters.PriceList", "masters.PriceListItem",
    "sales.SalesInvoice", "sales.SalesItem",
    "sales.SalesCreditNote", "sales.SalesCreditNoteItem",
    "sales.SalesDebitNote", "sales.SalesDebitNoteItem",
    "sales.SalesReturn", "sales.SalesReturnItem",
    "purchases.PurchaseInvoice", "purchases.PurchaseItem",
    "purchases.PurchaseCreditNote", "purchases.PurchaseCreditNoteItem",
    "purchases.PurchaseDebitNote", "purchases.PurchaseDebitNoteItem",
    "purchases.PurchaseReturn", "purchases.PurchaseReturnItem",
    "purchases.BillOfEntry",
    "reporting.GstReturnPeriod", "reporting.GstReturnSnapshot",
    "accounts.CompanyGstin", "core.DocumentSeries",
    # PROTECT-referenced by the retained tax documents; no third-party PII.
    "inventory.Warehouse", "inventory.BatchLot", "accounting.CostCenter",
}

# Non-retained models whose self-referential PROTECT FK must be nulled first.
_SELF_REF_PRECLEAR = {
    "accounting.Account": "parent",
    "accounting.CostCenter": "parent",
    "accounting.JournalEntry": "reversed_entry",
}


def company_fk_relations() -> list[tuple[str, str, str]]:
    """(``app.Model``, field, on_delete-name) for every FK / O2O to Company."""
    from accounts.models import Company

    out: list[tuple[str, str, str]] = []
    for model in apps.get_models():
        for f in model._meta.get_fields():
            if not getattr(f, "is_relation", False):
                continue
            if getattr(f, "related_model", None) is not Company:
                continue
            if not (f.many_to_one or f.one_to_one):
                continue
            od = getattr(getattr(f, "remote_field", None), "on_delete", None)
            out.append((f"{model._meta.app_label}.{model.__name__}", f.name, getattr(od, "__name__", str(od))))
    return sorted(out)


def assert_erasure_model_coverage() -> None:
    """SR-41 drift guard."""
    unhandled = [
        f"{label}.{fname} (on_delete={od})"
        for (label, fname, od) in company_fk_relations()
        if od not in _SAFE_ON_DELETE
        and label not in PROTECT_MODELS_HANDLED
        and label not in TOMBSTONE_RETAINED
    ]
    if unhandled:
        raise AssertionError(
            "erasure wipe set is incomplete — these company FKs are neither "
            "auto-resolved by company.delete(), handled in accounts.erasure, nor "
            "in TOMBSTONE_RETAINED:\n  " + "\n  ".join(unhandled)
        )


@dataclass
class ErasureResult:
    company_id: int
    company_name: str
    mode: str
    export_sha256: str
    log_id: int
    retained: dict = field(default_factory=dict)


def _rls_bypass():
    try:
        from core.rls import rls_bypass

        return rls_bypass()
    except Exception:  # noqa: BLE001
        from contextlib import nullcontext

        return nullcontext()


def _delete_protect_rows(company) -> None:
    from core.models import AuditEvent, MoneyFieldAudit, StatutoryDocumentEvent

    AuditEvent.objects.filter(company=company).delete()
    MoneyFieldAudit.objects.filter(company=company).delete()
    StatutoryDocumentEvent.objects.filter(company=company).delete()


def _delete_non_retained(company, retained: set[str]) -> None:
    """Delete every owned (CASCADE/PROTECT) ``company``-scoped row whose model is
    not retained; null the SET_NULL back-references. A retry loop resolves
    inter-model PROTECT ordering; self-referential PROTECT FKs are nulled up
    front."""
    for label, fk in _SELF_REF_PRECLEAR.items():
        if label in retained:
            continue
        try:
            m = apps.get_model(label)
            m.objects.filter(**{f"{_company_field(m)}": company}).update(**{fk: None})
        except Exception:  # noqa: BLE001 — model/field may not exist in a build
            pass

    owned: list = []
    for label, fname, od in company_fk_relations():
        if label in retained or label in PROTECT_MODELS_HANDLED:
            continue
        model = apps.get_model(label)
        if od in ("SET_NULL", "SET_DEFAULT"):
            model.objects.filter(**{fname: company}).update(**{fname: None})
            continue
        if od in ("CASCADE", "PROTECT"):
            owned.append((model, fname))

    remaining = list(dict.fromkeys(owned))
    for _ in range(8):
        stuck = []
        for model, fname in remaining:
            try:
                model.objects.filter(**{fname: company}).delete()
            except ProtectedError:
                stuck.append((model, fname))
        remaining = stuck
        if not remaining:
            break
    if remaining:
        raise AssertionError(
            "tombstone delete stuck on: " + ", ".join(m.__name__ for m, _ in remaining)
        )


def _company_field(model) -> str:
    from accounts.models import Company

    for f in model._meta.get_fields():
        if getattr(f, "related_model", None) is Company and (f.many_to_one or f.one_to_one):
            return f.name
    return "company"


def _scrub_parties(company) -> None:
    from masters.models import Customer, Supplier

    Customer.objects.filter(company=company).update(
        name="[erased]", phone="", email="", gstin="", billing_address="",
        shipping_address="", notes="", gstin_legal_name="", gstin_raw_payload={},
    )
    Supplier.objects.filter(company=company).update(
        name="[erased]", phone="", email="", gstin="", address="", notes="",
        gstin_legal_name="", gstin_raw_payload={},
    )


def _scrub_invoice_pii(company) -> None:
    from sales.models import SalesInvoice

    SalesInvoice.objects.filter(company=company).update(
        transporter_name="", filing_party_gstin="", ecommerce_operator_gstin="",
    )


def _scrub_company(company) -> None:
    company.name = f"[erased tenant {company.pk}]"
    company.legal_name = ""
    for f in (
        "gstin", "address", "city", "pincode", "phone", "email", "upi_id",
        "bank_name", "bank_account", "bank_ifsc", "pan", "udyam",
        "gstin_legal_name", "pan_legal_name", "udyam_enterprise_name",
        "gsp_credentials_encrypted", "payment_gateway_credentials_encrypted",
    ):
        if hasattr(company, f):
            setattr(company, f, "")
    for f in ("gstin_raw_payload", "pan_raw_payload", "udyam_raw_payload"):
        if hasattr(company, f):
            setattr(company, f, {})
    company.erased_at = timezone.now()
    company.save()


def _write_log(*, company_id, company_name, requested_by_email, reason, mode, export_sha, retained):
    from accounts.models import TenantErasureLog

    return TenantErasureLog.objects.create(
        company_id=company_id,
        company_name=company_name,
        requested_by_email=requested_by_email or "",
        reason=(reason or "")[:2000],
        export_sha256=export_sha,
        mode=mode,
        retained_counts=retained,
    )


@transaction.atomic
def erase_company(
    company,
    *,
    mode: str = "tombstone",
    requested_by_email: str = "",
    reason: str = "",
    skip_export: bool = False,
) -> ErasureResult:
    from accounts.models import CompanyUser, User
    from accounts.tenant_backup import (
        build_export_payload,
        encrypt_export_zip,
        wipe_logical_tenant_rows,
    )

    if mode not in ("tombstone", "hard"):
        raise ValueError(f"unknown erase mode {mode!r}")
    company_id = int(company.pk)
    company_name = company.name

    export_sha = ""
    if not skip_export:
        export_sha = hashlib.sha256(encrypt_export_zip(build_export_payload(company))).hexdigest()

    retained: dict[str, int] = {}
    with _rls_bypass():
        if mode == "hard":
            wipe_logical_tenant_rows(company)
            _delete_protect_rows(company)
            User.objects.filter(active_company=company).update(active_company=None)
            CompanyUser.objects.filter(company=company).delete()
            try:
                company.delete()
            except ProtectedError as exc:
                raise AssertionError(f"hard erase blocked by an unhandled PROTECT FK: {exc}") from exc
        else:  # tombstone
            _delete_non_retained(company, TOMBSTONE_RETAINED)
            _delete_protect_rows(company)
            _scrub_parties(company)
            _scrub_invoice_pii(company)
            User.objects.filter(active_company=company).update(active_company=None)
            CompanyUser.objects.filter(company=company).update(is_active=False)
            _scrub_company(company)
            for label in TOMBSTONE_RETAINED:
                try:
                    n = apps.get_model(label).objects.filter(company=company).count()
                except Exception:  # noqa: BLE001
                    n = 0
                if n:
                    retained[label] = n

        log = _write_log(
            company_id=company_id, company_name=company_name,
            requested_by_email=requested_by_email, reason=reason, mode=mode,
            export_sha=export_sha, retained=retained,
        )

    return ErasureResult(
        company_id=company_id, company_name=company_name, mode=mode,
        export_sha256=export_sha, log_id=log.pk, retained=retained,
    )


def purge_expired_tombstones(*, now=None) -> int:
    """Hard-delete tombstoned companies past the GST retention window."""
    from accounts.models import Company

    now = now or timezone.now()
    cutoff = now - GST_RETENTION
    purged = 0
    with _rls_bypass():
        stale = list(Company.objects.filter(erased_at__isnull=False, erased_at__lt=cutoff))
    for c in stale:
        try:
            erase_company(c, mode="hard", requested_by_email="purge-job",
                          reason="8-year GST retention elapsed", skip_export=True)
            purged += 1
        except Exception:  # noqa: BLE001 — one bad tombstone must not block the sweep
            import logging

            logging.getLogger("accounts.erasure").exception("purge failed for company %s", c.pk)
    return purged
