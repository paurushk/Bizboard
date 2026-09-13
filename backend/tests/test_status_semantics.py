"""Exhaustive unit tests for sales/status_semantics.py (CF-001).

Parametrized over the *entire* SalesInvoice.Status enum, not hand-picked
cases — directly closes weak-assumption #11's lesson (TESTING_STRATEGY.md
§8): a unit test covering the inputs someone thought to write isn't the
same as one covering the full state space. `paidAwareStatus()` had passing
tests and still shipped G-17 for exactly this reason. Automatically extends
if a 5th status is ever added, since ALL_STATUSES is derived from the enum.

No django_db marker — SalesInvoice.Status is a plain TextChoices enum,
needs no database.
"""

import pytest

from sales.models import SalesInvoice
from sales.status_semantics import (
    OPEN_RECEIVABLE_STATUSES,
    OPEN_SALES_STATUSES,
    OPERATIONAL_SALE_STATUSES,
    is_open_receivable,
    is_operational_sale,
)

ALL_STATUSES = list(SalesInvoice.Status)


@pytest.mark.parametrize("status", ALL_STATUSES)
def test_is_open_receivable_exhaustive(status):
    expected = status in (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED)
    assert is_open_receivable(status) is expected


@pytest.mark.parametrize("status", ALL_STATUSES)
def test_is_operational_sale_exhaustive(status):
    expected = status == SalesInvoice.Status.COMPLETED
    assert is_operational_sale(status) is expected


def test_operational_sale_is_always_a_subset_of_open_receivable():
    for status in ALL_STATUSES:
        if is_operational_sale(status):
            assert is_open_receivable(status), (
                f"{status}: a status counted as an operational sale must also "
                "be an open receivable — a live sale can always still owe money"
            )


def test_open_sales_statuses_backcompat_alias_matches_open_receivable():
    assert OPEN_SALES_STATUSES == OPEN_RECEIVABLE_STATUSES


def test_status_sets_have_no_surprise_members():
    # Pins the exact tuples so a future enum addition is a deliberate
    # decision (which predicate should the new status join?), not a silent
    # inclusion via `in ALL_STATUSES`-style iteration.
    assert OPEN_RECEIVABLE_STATUSES == (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED)
    assert OPERATIONAL_SALE_STATUSES == (SalesInvoice.Status.COMPLETED,)
