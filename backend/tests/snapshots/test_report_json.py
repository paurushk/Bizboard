"""FG-2f — the core financial reports' shape is pinned.

After a fixed sale + purchase, snapshot trial balance / P&L / balance sheet as
{account_code: balance} maps (volatile keys stripped) so a change to any
report's aggregation shows up as a diff.
"""

from __future__ import annotations

import pytest

from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def company_with_activity(tenant_a):
    c = tenant_a.company
    c.accounting_enabled = True
    c.gstin = "29AAAAA0000A1ZY"
    c.save(update_fields=["accounting_enabled", "gstin"])
    product = make_product(c, gst_rate="18", selling_price="100", purchase_price="60")
    add_stock(tenant_a, product, "20", unit_cost="60")
    cust = make_customer(c, state="Karnataka", gstin="29AAAAA0000A1ZY")
    sup = make_supplier(c, state="Karnataka")
    inv = create_draft_invoice(
        tenant_a, cust,
        [{"product": product.id, "quantity": "3", "unit_price": "100.00", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    pur = create_draft_purchase(
        tenant_a, sup,
        [{"product": product.id, "quantity": "10", "unit_price": "60.00", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    return c


def _by_code(rows):
    return {r["account_code"]: str(r["balance"]) for r in rows}


def test_trial_balance_snapshot(company_with_activity, assert_snapshot):
    from accounting.reports import trial_balance

    tb = trial_balance(company_with_activity)
    assert_snapshot(
        "trial_balance",
        {
            "balanced": tb["balanced"],
            "total_debit": str(tb["total_debit"]),
            "total_credit": str(tb["total_credit"]),
            "rows": _by_code(tb["rows"]),
        },
    )


def test_profit_and_loss_snapshot(company_with_activity, assert_snapshot):
    from datetime import date

    from accounting.reports import profit_and_loss

    pnl = profit_and_loss(company_with_activity, date_from=date(1900, 1, 1), date_to=date(2999, 12, 31))
    assert_snapshot(
        "profit_and_loss",
        {"income": str(pnl["income"]), "expenses": str(pnl["expenses"]),
         "net_profit": str(pnl["net_profit"]), "rows": _by_code(pnl["rows"])},
    )


def test_balance_sheet_snapshot(company_with_activity, assert_snapshot):
    from accounting.reports import balance_sheet

    bs = balance_sheet(company_with_activity)
    assert_snapshot(
        "balance_sheet",
        {
            "assets": str(bs["assets"]), "liabilities": str(bs["liabilities"]),
            "equity": str(bs["equity"]), "current_earnings": str(bs["current_earnings"]),
            "equation_holds": bs["equation_holds"],
            "rows": _by_code(bs["rows"]),
        },
    )
