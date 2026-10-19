"""SET-03: the statutory licences an invoice carried when it was issued.

The invoice PDF used to read the live licence table, so editing, deactivating or letting a licence
expire changed how old invoices reprinted. The set printed is now captured once, when the invoice
completes, and stored on the invoice (`statutory_licences_snapshot`). `None` means "never
captured" (an invoice from before this change, until the backfill runs); `[]` means "captured,
and there were none".

A licence that lands on a snapshot is locked (`locked_at`): its identity can no longer be edited,
only renewed or replaced (see `accounts.views.CompanyStatutoryLicenceViewSet`).

Premises: a licence covers the state of the premises it was issued for. When the invoice's
branch state is known, only licences with no state, or the same state, apply. When either state
cannot be recognised nothing is filtered out, so an odd free-text value never hides a licence.
"""

from __future__ import annotations

from datetime import date

from django.db.models import Q
from django.utils import timezone

from accounts.models import CompanyStatutoryLicence
from core.services.tax_engine.india import extract_state_code


def invoice_state_code(invoice) -> str | None:
    """GST state code of the branch the invoice is issued from, or None when unknown."""
    branch = getattr(invoice, "company_gstin", None)
    if branch is None:
        return None
    return extract_state_code(getattr(branch, "gstin", None)) or extract_state_code(
        getattr(branch, "state", None)
    )


def licence_covers_state(licence: CompanyStatutoryLicence, state_code: str | None) -> bool:
    if not state_code:
        return True
    code = extract_state_code(licence.premises_state)
    return code is None or code == state_code


def _row(licence: CompanyStatutoryLicence) -> dict:
    return {
        "id": licence.pk,
        "type": licence.licence_type,
        "number": licence.licence_number,
        "premises_state": licence.premises_state or "",
        "valid_from": licence.valid_from.isoformat() if licence.valid_from else None,
        "valid_upto": licence.valid_upto.isoformat() if licence.valid_upto else None,
    }


def _valid_on(on_date: date) -> Q:
    return (Q(valid_from__isnull=True) | Q(valid_from__lte=on_date)) & (
        Q(valid_upto__isnull=True) | Q(valid_upto__gte=on_date)
    )


def licences_for(
    company, on_date: date, *, historical: bool = False, state_code: str | None = None
) -> list[CompanyStatutoryLicence]:
    """Licence records that cover ``on_date`` (and the premises state, when given).

    Live use (issuing an invoice now): active licences only. Historical use (backfilling an old
    invoice): a licence switched off since then still counts if it carries an end date that covers
    the invoice date, because it was genuinely valid then. An inactive licence with no end date
    gives no evidence either way, so it is left out.
    """
    qs = CompanyStatutoryLicence.objects.filter(company=company).filter(_valid_on(on_date))
    if historical:
        qs = qs.filter(Q(is_active=True) | Q(valid_upto__isnull=False))
    else:
        qs = qs.filter(is_active=True)
    return [
        licence
        for licence in qs.order_by("licence_type", "licence_number")
        if licence_covers_state(licence, state_code)
    ]


def licences_valid_on(
    company, on_date: date, *, historical: bool = False, state_code: str | None = None
) -> list[dict]:
    return [_row(lic) for lic in licences_for(company, on_date, historical=historical, state_code=state_code)]


def lock_licences(rows: list[dict]) -> None:
    """Mark every licence that appears on a snapshot as locked (idempotent)."""
    ids = [r["id"] for r in rows if r.get("id")]
    if ids:
        CompanyStatutoryLicence.objects.filter(pk__in=ids, locked_at__isnull=True).update(
            locked_at=timezone.now()
        )


def capture_snapshot(invoice) -> list[dict]:
    """Set (do not save) the snapshot on ``invoice``, and lock the licences it carries."""
    rows = licences_valid_on(
        invoice.company, invoice.invoice_date, state_code=invoice_state_code(invoice)
    )
    invoice.statutory_licences_snapshot = rows
    lock_licences(rows)
    return rows


def licences_to_print(invoice) -> list[dict]:
    """What the invoice PDF prints: the stored snapshot, else the licences valid on the invoice date."""
    stored = getattr(invoice, "statutory_licences_snapshot", None)
    if stored is not None:
        return list(stored)
    return licences_valid_on(
        invoice.company, invoice.invoice_date, state_code=invoice_state_code(invoice)
    )
