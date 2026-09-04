"""WS-05 — period-lock enforcement on paths that skipped it.

Findings B1-006, B1-022, B8-013. (B3-008 mark-period-dirty on BoE
complete/cancel is covered by test_gst08_bill_of_entry not regressing.)
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from accounting.models import Account, AccountingPeriod
from accounting.services import seed_chart_of_accounts
from reporting.gst_periods import soft_close_period
from tests.test_sprint_a_accounting_p1 import books  # noqa: F401

pytestmark = pytest.mark.django_db


def _this_period() -> str:
    d = timezone.localdate()
    return f"{d.year:04d}-{d.month:02d}"


def _soft_close_now(books):  # noqa: F811 (books re-imported from test_sprint_a_accounting_p1)
    seed_chart_of_accounts(books.company, books.owner)
    soft_close_period(books.company, _this_period(), books.owner)


def test_manual_journal_post_blocked_in_soft_closed_period(books):  # noqa: F811 (books re-imported from test_sprint_a_accounting_p1)
    _soft_close_now(books)
    coa = {a.code: a.id for a in Account.objects.filter(company=books.company)}
    payload = {
        "entryDate": timezone.localdate().isoformat(),
        "narration": "test",
        "lines": [
            {"account": coa["1100"], "debit": "100", "credit": "0"},
            {"account": coa["5800"], "debit": "0", "credit": "100"},
        ],
    }
    created = books.client.post("/api/v1/accounting/journals/", payload, format="json")
    assert created.status_code in (200, 201), created.data
    jid = (created.data.get("data") or created.data)["id"]
    posted = books.client.post(f"/api/v1/accounting/journals/{jid}/post/")
    assert posted.status_code == 400, posted.data  # B1-006: was allowed before


def test_non_contiguous_period_close_rejected(books):  # noqa: F811 (books re-imported from test_sprint_a_accounting_p1)
    feb = AccountingPeriod.objects.create(
        company=books.company, name="Feb 2026",
        start_date="2026-02-01", end_date="2026-02-28",
        status=AccountingPeriod.Status.OPEN,
        created_by=books.owner, updated_by=books.owner,
    )
    mar = AccountingPeriod.objects.create(
        company=books.company, name="Mar 2026",
        start_date="2026-03-01", end_date="2026-03-31",
        status=AccountingPeriod.Status.OPEN,
        created_by=books.owner, updated_by=books.owner,
    )
    resp = books.client.post(f"/api/v1/accounting/periods/{mar.id}/close/")
    assert resp.status_code == 400, resp.data  # B1-022
    assert "must be closed in order" in str(resp.data).lower() or "close feb" in str(resp.data).lower()

    # once the earlier period is no longer OPEN, the contiguity gate is gone
    feb.status = AccountingPeriod.Status.CLOSED
    feb.save(update_fields=["status"])
    resp2 = books.client.post(f"/api/v1/accounting/periods/{mar.id}/close/")
    if resp2.status_code == 400:
        assert "must be closed in order" not in str(resp2.data).lower()


def test_stock_adjustment_blocked_in_locked_period(books):  # noqa: F811 (books re-imported from test_sprint_a_accounting_p1)
    from masters.models import Product

    _soft_close_now(books)
    books.company.accounting_enabled = True
    books.company.save(update_fields=["accounting_enabled"])
    p = Product.objects.create(
        company=books.company, name="Adj", sku="ADJ-1",
        purchase_price=Decimal("10"), selling_price=Decimal("20"), gst_rate=Decimal("0"),
        created_by=books.owner, updated_by=books.owner,
    )
    resp = books.client.post(
        "/api/v1/inventory/adjustments/",
        {"product": p.id, "quantity": "5", "reason": "found"},
        format="json",
    )
    assert resp.status_code == 400, resp.data  # B8-013


# --------------------------------------------------------------------------- #
# WS-06 B7-015 — outbound URL scheme guard (pure; the RLS paths need a
# Postgres CI pass to exercise).
# --------------------------------------------------------------------------- #
def test_assert_safe_outbound_url_rejects_dangerous_schemes():
    from core.exceptions import BusinessRuleError
    from core.services.gsp_adapters import assert_safe_outbound_url

    assert_safe_outbound_url("https://api.example.com/v1/irp")  # ok
    for bad in (
        "file:///etc/passwd",
        "ftp://host/x",
        "gopher://host",
        "http://169.254.169.254/latest/meta-data/",
        "",
    ):
        with pytest.raises(BusinessRuleError):
            assert_safe_outbound_url(bad)
