"""Tenancy invariants — no row owned by company A points at a row of company B.

The exhaustive per-endpoint isolation check is a generated test over the URL
conf (FG-2d, tests/tenancy/test_endpoint_isolation.py). These are data-at-rest
cross-company FK-leak checks for the highest-value tables.
"""

from __future__ import annotations

from .base import invariant


@invariant(
    "tenancy.stock_rows_same_company",
    consequence="A stock movement/balance references a warehouse or product from another company — tenant data has leaked.",
)
def stock_rows_same_company(company) -> list[str]:
    from django.db.models import F, Q

    from inventory.models import StockBalance, StockMovement

    out = []
    for model, label in ((StockMovement, "movement"), (StockBalance, "balance")):
        bad = (
            model.objects.filter(company=company)
            .filter(~Q(warehouse__company_id=company.id) | ~Q(product__company_id=company.id))
            .count()
        )
        if bad:
            out.append(f"{bad} stock {label} row(s) with a foreign warehouse/product")
    return out


@invariant(
    "tenancy.journal_parties_same_company",
    consequence="A journal line tags a customer/supplier from another company — the sub-ledger is cross-tenant.",
)
def journal_parties_same_company(company) -> list[str]:
    from django.db.models import Q

    from accounting.models import JournalLine

    bad = (
        JournalLine.objects.filter(company=company)
        .filter(
            Q(customer__isnull=False, customer__company_id__isnull=False)
            & ~Q(customer__company_id=company.id)
            | Q(supplier__isnull=False) & ~Q(supplier__company_id=company.id)
        )
        .count()
    )
    return [f"{bad} journal line(s) tagged with a foreign customer/supplier"] if bad else []
