"""Document-numbering integrity (§G7).

A duplicate document number is a statutory failure (two invoices with the same
number). Gap-free-ness within a series is desirable but harder to assert without
per-model mapping; duplicates are the hard invariant here.
"""

from __future__ import annotations

import re

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


# --- plain callable, NOT registered ------------------------------------------
# Gap-free-ness only holds when *every* number in a series was issued by this
# system in this database. A chain that seeds partial numbering history, or a
# suite where many companies share a DB, would trip it. Chains that control the
# whole series call it directly:
#     from core.invariants.numbering import sequences_intact
#     assert not sequences_intact(company)

_SUFFIX_RE = re.compile(r"^(.*?)[-/ _]*(\d+)$")

_SEQUENCE_MODELS = {
    "sales_invoice": ("sales.models", "SalesInvoice"),
    "purchase_invoice": ("purchases.models", "PurchaseInvoice"),
}


def sequences_intact(company, doc: str = "sales_invoice") -> list[str]:
    """Within each numbering series (the alpha prefix of the document number) the
    issued numeric suffixes are contiguous: sorted == range(min, max + 1). A gap
    means a number was allocated and never persisted — a GST invoice-numbering
    compliance break (Rule 46(b): consecutive serial numbers)."""
    from importlib import import_module

    spec = _SEQUENCE_MODELS.get(doc)
    if spec is None:
        return []
    model = getattr(import_module(spec[0]), spec[1])

    groups: dict[str, list[int]] = {}
    rows = (
        model.objects.filter(company=company)
        .exclude(number__isnull=True)
        .exclude(number="")
        .values_list("number", flat=True)
    )
    for raw in rows:
        m = _SUFFIX_RE.match((raw or "").strip())
        if not m:
            continue
        groups.setdefault(m.group(1).upper(), []).append(int(m.group(2)))

    out: list[str] = []
    for prefix, nums in groups.items():
        label = prefix or "(no prefix)"
        if len(set(nums)) != len(nums):
            out.append(f"{label}: duplicate suffix among {sorted(nums)}")
            continue
        nums.sort()
        expected = list(range(nums[0], nums[-1] + 1))
        if nums != expected:
            missing = sorted(set(expected) - set(nums))
            out.append(f"{label}: gap(s) at {missing} (issued {nums[0]}..{nums[-1]})")
    return out
