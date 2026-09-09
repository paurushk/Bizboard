"""Cross-report reconciliation (§H7).

The individual reports are derived views; this asserts they agree with each
other and with the underlying ledgers, so a change that breaks one report's
aggregation is caught even if that report has no direct test.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from .base import invariant

_ALL_TIME_FROM = date(1900, 1, 1)
_ALL_TIME_TO = date(2999, 12, 31)

_RUPEE = Decimal("1.00")
_CENT = Decimal("0.01")
_ZERO = Decimal("0")


@invariant(
    "reports.pnl_reconciles_to_trial_balance",
    consequence="Profit & Loss net profit does not match the trial-balance income/expense rows — one of them is aggregating wrong.",
)
def pnl_reconciles_to_trial_balance(company) -> list[str]:
    from accounting.models import Account
    from accounting.reports import profit_and_loss, trial_balance

    if not getattr(company, "accounting_enabled", False):
        return []
    from accounting.reports import _balances

    # All-time on both sides, and exclude FY_CLOSE on both sides — profit_and_loss
    # excludes it, so the TB comparison must too, otherwise a year-end close
    # (which zeroes income/expense into retained earnings) looks like a mismatch.
    pnl = profit_and_loss(company, date_from=_ALL_TIME_FROM, date_to=_ALL_TIME_TO)
    rows = _balances(company, date_from=_ALL_TIME_FROM, date_to=_ALL_TIME_TO, exclude_fy_close=True)
    # TB balance = debit - credit. Income accounts sit credit (negative balance),
    # expense accounts debit (positive). So Σ(income+expense balances) == expenses - income == -net_profit.
    tb_ie = _ZERO
    for row in rows:
        if row["account_type"] in (Account.Type.INCOME, Account.Type.EXPENSE):
            tb_ie += row["balance"]
    net_profit = pnl["net_profit"]
    if abs(tb_ie + net_profit) > _CENT:
        return [
            f"P&L net_profit {net_profit} + Σ(TB income/expense balances) {tb_ie} "
            f"= {tb_ie + net_profit}, expected 0"
        ]
    return []


# NOT registered in the default sweep: balance_sheet() computes current_earnings
# as the P&L for the FY containing `as_of` (default: current FY), while `assets`
# is as-of-now. When test data is dated in a prior FY (and the clock isn't
# frozen to match), the equation legitimately won't hold for the current-FY
# view. WF-31 (FY close) calls this directly with controlled dates:
#   from core.invariants.reports import balance_sheet_equation_holds
#   assert not balance_sheet_equation_holds(company)
def balance_sheet_equation_holds(company) -> list[str]:
    from accounting.reports import balance_sheet

    if not getattr(company, "accounting_enabled", False):
        return []
    bs = balance_sheet(company)
    if not bs.get("equation_holds", False):
        return [
            f"assets {bs['assets']} != liabilities {bs['liabilities']} + equity "
            f"{bs['equity']} + current_earnings {bs['current_earnings']} "
            f"(= {bs['liabilities'] + bs['equity'] + bs['current_earnings']})"
        ]
    return []


# NOT registered in the default sweep: it only holds when opening stock was
# established through a GL-posting path. The `add_stock` test helper seeds
# StockBalance / running cost directly with no journal, so a large fraction of
# the suite would trip it. WF-32 (opening balances) calls this directly:
#   from core.invariants.reports import inventory_gl_matches_running_cost
#   assert not inventory_gl_matches_running_cost(company)
def inventory_gl_matches_running_cost(company) -> list[str]:
    from django.db.models import Sum

    from accounting.models import Account, JournalEntry, JournalLine
    from inventory.models import InventoryRunningCost

    if not getattr(company, "accounting_enabled", False):
        return []
    acc = (
        Account.objects.filter(company=company, type=Account.Type.ASSET)
        .filter(name__icontains="inventor")
        .first()
    ) or Account.objects.filter(company=company, code="1400").first()
    if acc is None:
        return []
    agg = JournalLine.objects.filter(
        account=acc,
        entry__company=company,
        entry__status__in=[JournalEntry.Status.POSTED, JournalEntry.Status.REVERSED],
    ).aggregate(d=Sum("debit"), c=Sum("credit"))
    gl_balance = (agg["d"] or _ZERO) - (agg["c"] or _ZERO)
    valuation = (
        InventoryRunningCost.objects.filter(company=company).aggregate(v=Sum("value"))["v"] or _ZERO
    )
    # Only reconcile when the GL genuinely carries an inventory asset balance
    # (positive debit). A zero/credit balance means acquisition was never posted
    # to GL (e.g. opening stock seeded outside the books) — not a drift to flag
    # here; that's a "books don't cover inventory acquisition" gap for a
    # dedicated chain.
    if gl_balance <= _ZERO:
        return []
    # Running cost carries 4dp; GL 2dp — allow a rupee of rounding slack.
    if abs(gl_balance - valuation) > _RUPEE:
        return [
            f"inventory GL account {acc.code} balance {gl_balance} != "
            f"Σ running-cost value {valuation} (diff {gl_balance - valuation})"
        ]
    return []
