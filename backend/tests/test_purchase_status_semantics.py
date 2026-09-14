"""Exhaustive unit tests for purchases/status_semantics.py (Phase 7.1).

Parametrized over the entire PurchaseInvoice.Status enum — same discipline as
backend/tests/test_status_semantics.py for SalesInvoice.
"""

import pytest

from purchases.models import PurchaseInvoice
from purchases.status_semantics import (
    OPEN_PAYABLE_STATUSES,
    OPERATIONAL_PURCHASE_STATUSES,
    is_open_payable,
    is_operational_purchase,
)

ALL_STATUSES = list(PurchaseInvoice.Status)


@pytest.mark.parametrize("status", ALL_STATUSES)
def test_is_open_payable_exhaustive(status):
    expected = status in (PurchaseInvoice.Status.COMPLETED, PurchaseInvoice.Status.RETURNED)
    assert is_open_payable(status) is expected


@pytest.mark.parametrize("status", ALL_STATUSES)
def test_is_operational_purchase_exhaustive(status):
    expected = status == PurchaseInvoice.Status.COMPLETED
    assert is_operational_purchase(status) is expected


def test_operational_purchase_is_subset_of_open_payable():
    for status in ALL_STATUSES:
        if is_operational_purchase(status):
            assert is_open_payable(status), (
                f"{status}: an operational purchase must also be an open payable"
            )


def test_status_sets_have_no_surprise_members():
    assert OPEN_PAYABLE_STATUSES == (
        PurchaseInvoice.Status.COMPLETED,
        PurchaseInvoice.Status.RETURNED,
    )
    assert OPERATIONAL_PURCHASE_STATUSES == (PurchaseInvoice.Status.COMPLETED,)
