"""Document-numbering integrity (§G7).

A duplicate document number is a statutory failure (two invoices with the same
number). Gap-free-ness within a series is desirable but harder to assert without
per-model mapping; duplicates are the hard invariant here.
"""

from __future__ import annotations

from .base import invariant

# Char fields that hold a user-facing document number on DocumentTotalsModel subclasses.
_NUMBER_FIELD_NAMES = ("number", "invoice_number", "document_number", "voucher_number", "bill_number")


@invariant(
    "numbering.no_duplicate_document_numbers",
    consequence="Two documents of the same type share a number — a statutory / audit failure.",
)
def no_duplicate_document_numbers(company) -> list[str]:
    from django.db.models import Count

    from .money import _document_total_models

    out: list[str] = []
    for model in _document_total_models():
        field_names = {f.name for f in model._meta.get_fields() if hasattr(f, "attname")}
        num_field = next((n for n in _NUMBER_FIELD_NAMES if n in field_names), None)
        if num_field is None:
            continue
        try:
            dupes = (
                model.objects.filter(company=company)
                .exclude(**{f"{num_field}__isnull": True})
                .exclude(**{num_field: ""})
                .values(num_field)
                .annotate(n=Count("id"))
                .filter(n__gt=1)
            )
        except Exception:
            continue
        for row in dupes:
            out.append(
                f"{model.__name__}: {row['n']} rows share {num_field}={row[num_field]!r}"
            )
    return out
