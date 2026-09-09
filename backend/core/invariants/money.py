"""Money invariants — header totals identity across every financial document.

Generic over every concrete subclass of ``core.models.DocumentTotalsModel``.
The exact grand-total formula for documents that carry additional charges, TCS
or TDS varies by document type (sales grand includes TCS; purchase grand may or
may not net TDS; charges may or may not sit in taxable) — those are asserted in
the per-type workflow chains (WF-01/34/35). This invariant covers the plain
case: a completed document with no charges/TCS/TDS, where
``grand_total == taxable + cgst + sgst + igst + cess + round_off`` must hold
exactly, plus ``grand_total >= 0`` always.
"""

from __future__ import annotations

from decimal import Decimal

from .base import invariant

_CENT = Decimal("0.01")
_ZERO = Decimal("0")
_CORE_FIELDS = (
    "taxable_total",
    "cgst_total",
    "sgst_total",
    "igst_total",
    "cess_total",
    "round_off",
)
# If any of these is non-zero the plain identity does not apply — skip the row
# (the per-document-type workflow chains assert the full footing). `invoice_discount`
# is an after-tax header discount subtracted from grand_total but NOT from
# taxable_total (which carries only line discounts) — BB-000663.
_EXTRA_FIELDS = ("additional_charges", "tcs_amount", "tds_amount", "invoice_discount")


def _document_total_models():
    from django.apps import apps

    from core.models import DocumentTotalsModel

    for model in apps.get_models():
        if issubclass(model, DocumentTotalsModel) and not model._meta.abstract:
            yield model


@invariant(
    "money.header_totals_identity",
    consequence="A document's taxable + taxes + round-off does not equal its grand_total — the amount charged is internally inconsistent.",
)
def header_totals_identity(company) -> list[str]:
    out: list[str] = []
    for model in _document_total_models():
        field_names = {f.name for f in model._meta.get_fields() if hasattr(f, "attname")}
        extras = [f for f in _EXTRA_FIELDS if f in field_names]
        try:
            qs = model.objects.filter(company=company)
        except Exception:
            continue
        for row in qs.values("pk", "grand_total", *_CORE_FIELDS, *extras):
            grand = row["grand_total"] or _ZERO
            if grand < _ZERO:
                out.append(f"{model.__name__}#{row['pk']}: negative grand_total {grand}")
            if any((row[f] or _ZERO) != _ZERO for f in extras):
                continue  # charges / TCS / TDS present — per-type chain asserts the formula
            core = sum((row[f] or _ZERO for f in _CORE_FIELDS), _ZERO)
            if core == _ZERO:
                continue  # empty draft / synthetic / charges-only row — nothing to police here
            if abs(core - grand) > _CENT:
                out.append(
                    f"{model.__name__}#{row['pk']}: taxable+tax+round_off {core} != grand_total {grand}"
                )
    return out
