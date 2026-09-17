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


def test_purchase_readers_do_not_collapse_payable_vs_operational():
    """CF-001 twin of CFT-NID-01: money/AP readers include RETURNED; analytics exclude it."""
    from insights.alerts import OPERATIONAL_PURCHASE_STATUSES as alerts_ops
    from insights.services import OPERATIONAL_PURCHASE_STATUSES as insights_ops
    from ledgers.services import OPEN_PAYABLE_STATUSES as ledger_ap
    from reporting.gst_health import OPEN_PAYABLE_STATUSES as gst_health_ap
    from reporting.gst_returns import OPEN_PAYABLE_STATUSES as gst_returns_ap
    from reporting.gstr2b import OPEN_PAYABLE_STATUSES as gstr2b_ap
    from reporting.ims import OPEN_PAYABLE_STATUSES as ims_ap
    from reporting.services import OPEN_PAYABLE_STATUSES as reporting_ap
    from reporting.tds_worksheets import OPEN_PAYABLE_STATUSES as tds_ap

    assert reporting_ap == OPEN_PAYABLE_STATUSES
    assert ledger_ap == OPEN_PAYABLE_STATUSES
    assert gstr2b_ap == OPEN_PAYABLE_STATUSES
    assert gst_health_ap == OPEN_PAYABLE_STATUSES
    assert gst_returns_ap == OPEN_PAYABLE_STATUSES
    assert ims_ap == OPEN_PAYABLE_STATUSES
    assert tds_ap == OPEN_PAYABLE_STATUSES
    assert PurchaseInvoice.Status.RETURNED in reporting_ap
    assert insights_ops == OPERATIONAL_PURCHASE_STATUSES
    assert alerts_ops == OPERATIONAL_PURCHASE_STATUSES
    assert PurchaseInvoice.Status.RETURNED not in insights_ops
    assert reporting_ap != insights_ops
