from decimal import Decimal
import logging

from django.db.models import F, Q, Sum
from django.utils import timezone

from .models import Account, JournalEntry, JournalLine

logger = logging.getLogger(__name__)


def _balances(company, *, as_of=None, date_from=None, date_to=None, cost_center=None, exclude_fy_close=False, exclude_fy_close_after=None, cost_center_unassigned=False):
    rolled = _balances_from_rollup(
        company,
        as_of=as_of,
        date_from=date_from,
        date_to=date_to,
        cost_center=cost_center,
        exclude_fy_close=exclude_fy_close,
        exclude_fy_close_after=exclude_fy_close_after,
        cost_center_unassigned=cost_center_unassigned,
    )
    if rolled is not None:
        return rolled
    # BUG-PERF-004: filter the denormalized company column instead of joining
    # every line back to JournalEntry just to reach company_id.
    qs = JournalLine.objects.filter(
        company=company,
        entry__status__in=[JournalEntry.Status.POSTED, JournalEntry.Status.REVERSED],
    ).select_related("account")
    if as_of:
        qs = qs.filter(entry__entry_date__lte=as_of)
    if date_from:
        qs = qs.filter(entry__entry_date__gte=date_from)
    if date_to:
        qs = qs.filter(entry__entry_date__lte=date_to)
    if cost_center_unassigned:
        qs = qs.filter(cost_center__isnull=True)
    elif cost_center:
        qs = qs.filter(cost_center_id=cost_center)
    if exclude_fy_close:
        qs = qs.exclude(entry__purpose="FY_CLOSE")
    elif exclude_fy_close_after:
        qs = qs.exclude(entry__purpose="FY_CLOSE", entry__entry_date__gte=exclude_fy_close_after)
    # BB-000529 / UXW2B-018: alias the account__* FK lookups to clean single-underscore
    # names. djangorestframework_camel_case's camelize() only converts "_x" -> "X" when a
    # single underscore is followed directly by a lowercase letter; "account__code" (double
    # underscore) doesn't match that pattern and was passing through the renderer mangled
    # into "account_Code" instead of the expected "accountCode".
    # B1-028: values(...).annotate(...) already yields one row per account_id — no need to
    # re-key it through a dict.
    rows = []
    for row in qs.values(
        "account_id",
        account_code=F("account__code"),
        account_name=F("account__name"),
        account_type=F("account__type"),
    ).annotate(
        debit=Sum("debit"), credit=Sum("credit")
    ):
        row["debit"] = row["debit"] or Decimal("0")
        row["credit"] = row["credit"] or Decimal("0")
        row["balance"] = row["debit"] - row["credit"]
        rows.append(row)
    return rows


def _balances_from_rollup(
    company, *, as_of=None, date_from=None, date_to=None, cost_center=None,
    exclude_fy_close=False, exclude_fy_close_after=None, cost_center_unassigned=False,
):
    """Use AccountMonthlyBalance when a fresh checkpoint exists.

    Date-ranged, cost-centre, and FY-close-excluded reports stay on the live
    query. Returns None when the rollup must not be used.
    """
    if date_from or date_to or cost_center or cost_center_unassigned or exclude_fy_close or exclude_fy_close_after:
        return None
    from django.db.models import Max

    from .models import AccountBalanceRollup, AccountMonthlyBalance

    state = AccountBalanceRollup.objects.filter(company=company).first()
    if state is None:
        return None
    current_max = JournalLine.objects.filter(company=company).aggregate(m=Max("id"))["m"] or 0
    if int(state.max_line_id or 0) != int(current_max):
        return None
    month_start = None
    if as_of is not None:
        month_start = as_of.replace(day=1)
    qs = AccountMonthlyBalance.objects.filter(company=company).select_related("account")
    if month_start is not None:
        qs = qs.filter(period__lt=month_start)
    merged: dict[int, dict] = {}
    for row in qs:
        slot = merged.setdefault(row.account_id, {
            "account_id": row.account_id,
            "account_code": row.account.code,
            "account_name": row.account.name,
            "account_type": row.account.type,
            "debit": Decimal("0"),
            "credit": Decimal("0"),
        })
        slot["debit"] += row.debit or Decimal("0")
        slot["credit"] += row.credit or Decimal("0")
    if month_start is not None:
        live = JournalLine.objects.filter(
            company=company,
            entry__status__in=[JournalEntry.Status.POSTED, JournalEntry.Status.REVERSED],
            entry__entry_date__gte=month_start,
            entry__entry_date__lte=as_of,
        )
        for row in live.values(
            "account_id",
            account_code=F("account__code"),
            account_name=F("account__name"),
            account_type=F("account__type"),
        ).annotate(debit=Sum("debit"), credit=Sum("credit")):
            slot = merged.setdefault(row["account_id"], {
                "account_id": row["account_id"],
                "account_code": row["account_code"],
                "account_name": row["account_name"],
                "account_type": row["account_type"],
                "debit": Decimal("0"),
                "credit": Decimal("0"),
            })
            slot["debit"] += row["debit"] or Decimal("0")
            slot["credit"] += row["credit"] or Decimal("0")
    rows = []
    for slot in merged.values():
        slot["balance"] = slot["debit"] - slot["credit"]
        rows.append(slot)
    return rows


def refresh_account_monthly_balances(company):
    """Rebuild monthly account totals from posted lines (BUG-PERF-004).

    One transaction, and the checkpoint is read first and the lines are bounded by it: a reader
    never sees the table empty between the delete and the insert, and a line posted while this
    runs is not marked as included.
    """
    from django.db import transaction
    from django.db.models import Max
    from django.db.models.functions import TruncMonth

    from .models import AccountBalanceRollup, AccountMonthlyBalance

    with transaction.atomic():
        max_id = JournalLine.objects.filter(company=company).aggregate(m=Max("id"))["m"] or 0
        grouped = (
            JournalLine.objects.filter(
                company=company,
                id__lte=max_id,
                entry__status__in=[JournalEntry.Status.POSTED, JournalEntry.Status.REVERSED],
            )
            .annotate(period=TruncMonth("entry__entry_date"))
            .values("account_id", "period")
            .annotate(debit=Sum("debit"), credit=Sum("credit"))
        )
        AccountMonthlyBalance.objects.filter(company=company).delete()
        batch = []
        for row in grouped:
            period = row["period"]
            if period is None:
                continue
            if hasattr(period, "date"):
                period = period.date().replace(day=1)
            batch.append(AccountMonthlyBalance(
                company=company,
                account_id=row["account_id"],
                period=period,
                debit=row["debit"] or Decimal("0"),
                credit=row["credit"] or Decimal("0"),
            ))
        if batch:
            AccountMonthlyBalance.objects.bulk_create(batch)
        AccountBalanceRollup.objects.update_or_create(
            company=company, defaults={"max_line_id": max_id},
        )
    return {"months": len(batch), "max_line_id": max_id}


def comparative_store_pnl(company, *, date_from=None, date_to=None):
    """Side-by-side store P&L with shared overhead split evenly (BUG-ACC-007)."""
    from .models import CostCenter

    stores = list(CostCenter.objects.filter(company=company, is_active=True).order_by("code", "id"))
    columns = []
    for store in stores:
        pnl = profit_and_loss(company, date_from=date_from, date_to=date_to, cost_center=store.pk)
        columns.append({
            "store_id": store.pk,
            "store": store.name,
            "code": store.code,
            "income": pnl["income"],
            "expenses": pnl["expenses"],
            "net_profit": pnl["net_profit"],
        })
    shared_rows = _balances(
        company,
        date_from=date_from,
        date_to=date_to,
        cost_center_unassigned=True,
        exclude_fy_close=True,
    )
    shared_overhead = sum(
        (row["balance"] for row in shared_rows if row["account_type"] == Account.Type.EXPENSE),
        Decimal("0"),
    )
    n = len(columns)
    share = (shared_overhead / n) if n else Decimal("0")
    share = share.quantize(Decimal("0.01")) if n else Decimal("0")
    for col in columns:
        col["allocated_overhead"] = share
        col["net_profit_after_overhead"] = col["net_profit"] - share
    return {
        "date_from": date_from,
        "date_to": date_to,
        "shared_overhead": shared_overhead,
        "stores": columns,
    }


def trial_balance(company, as_of=None):
    rows = _balances(company, as_of=as_of)
    total_debit = sum((row["debit"] for row in rows), Decimal("0"))
    total_credit = sum((row["credit"] for row in rows), Decimal("0"))
    return {"as_of": as_of, "rows": rows, "total_debit": total_debit, "total_credit": total_credit,
            "balanced": total_debit == total_credit}


def _indian_fy_bounds(as_of, company=None):
    """Financial year containing as_of, using company.fy_start_month (default April)."""
    from calendar import monthrange
    from datetime import date

    if as_of is None:
        from django.utils import timezone

        as_of = timezone.localdate()
    if isinstance(as_of, str):
        try:
            as_of = date.fromisoformat(str(as_of)[:10])
        except (ValueError, TypeError):
            from django.utils import timezone

            # B1-018: caller-facing views (AccountingReportView._qp_date) already
            # 400 on a bad date param; this fallback is the last resort for
            # internal callers, but should not be fully silent.
            logger.warning("accounting.reports: unparseable as_of %r; defaulting to today", as_of)
            as_of = timezone.localdate()
    start_month = int(getattr(company, "fy_start_month", None) or 4) if company is not None else 4
    if start_month < 1 or start_month > 12:
        logger.warning(
            "accounting.reports: company %s fy_start_month=%r out of range; using April",
            getattr(company, "pk", None), start_month,
        )
        start_month = 4
    start_year = as_of.year if as_of.month >= start_month else as_of.year - 1
    start = date(start_year, start_month, 1)
    if start_month == 1:
        end = date(start_year, 12, 31)
    else:
        end_year = start_year + 1
        end_month = start_month - 1
        end = date(end_year, end_month, monthrange(end_year, end_month)[1])
    return start, end


def profit_and_loss(company, date_from=None, date_to=None, cost_center=None):
    # BB-000433: default P&L to current FY when dates omitted.
    if date_from is None and date_to is not None:
        date_from, _ = _indian_fy_bounds(date_to, company)
    elif date_from is None and date_to is None:
        date_from, date_to = _indian_fy_bounds(None, company)
    # B1-012: a `date_from` with no `date_to` otherwise left the query
    # upper-unbounded (all future postings included).
    if date_to is None:
        _, date_to = _indian_fy_bounds(date_from, company)
    rows = [row for row in _balances(company, date_from=date_from, date_to=date_to, cost_center=cost_center, exclude_fy_close=True)
            if row["account_type"] in (Account.Type.INCOME, Account.Type.EXPENSE)]
    income = sum((-row["balance"] for row in rows if row["account_type"] == Account.Type.INCOME), Decimal("0"))
    expenses = sum((row["balance"] for row in rows if row["account_type"] == Account.Type.EXPENSE), Decimal("0"))
    return {"date_from": date_from, "date_to": date_to, "cost_center": cost_center, "income": income, "expenses": expenses,
            "net_profit": income - expenses, "rows": rows,
            "schedule_iii": schedule_iii_profit_and_loss(rows)}


def _code_in(code, exact, prefixes) -> bool:
    if code in exact:
        return True
    return any(code.startswith(prefix) for prefix in prefixes)


def _schedule_iii_sections(rows, spec, *, credit_normal_sections, credit_normal_lines=()):
    """Bucket account rows into Schedule III headings. Empty headings stay."""
    buckets = {}
    for section_key, _section_label, lines in spec:
        for line_key, _line_label, exact, prefixes in lines:
            buckets[(section_key, line_key)] = {
                "exact": exact,
                "prefixes": prefixes,
                "accounts": [],
                "amount": Decimal("0"),
            }
    placed = set()
    for row in rows:
        code = str(row.get("account_code") or "")
        for section_key, _section_label, lines in spec:
            matched = False
            for line_key, _line_label, exact, prefixes in lines:
                if not exact and not prefixes:
                    continue
                if _code_in(code, exact, prefixes):
                    slot = buckets[(section_key, line_key)]
                    natural = Decimal(str(row.get("balance") or 0))
                    if section_key in credit_normal_sections or line_key in credit_normal_lines:
                        natural = -natural
                    slot["amount"] += natural
                    slot["accounts"].append({
                        "code": code,
                        "name": row.get("account_name") or "",
                        "amount": natural,
                    })
                    placed.add(id(row))
                    matched = True
                    break
            if matched:
                break
    # Accounts the chart does not name still appear, under the residual line
    # of their section, so a filing export does not drop a balance.
    for row in rows:
        if id(row) in placed:
            continue
        code = str(row.get("account_code") or "")
        account_type = row.get("account_type")
        if account_type == Account.Type.ASSET:
            key = ("current_assets", "other_current_assets")
            natural = Decimal(str(row.get("balance") or 0))
        elif account_type == Account.Type.LIABILITY:
            key = ("current_liabilities", "other_current_liabilities")
            natural = -Decimal(str(row.get("balance") or 0))
        elif account_type == Account.Type.EQUITY:
            key = ("equity", "other_equity")
            natural = -Decimal(str(row.get("balance") or 0))
        elif account_type == Account.Type.INCOME:
            key = ("pnl", "other_income")
            natural = -Decimal(str(row.get("balance") or 0))
        elif account_type == Account.Type.EXPENSE:
            key = ("pnl", "other_expenses")
            natural = Decimal(str(row.get("balance") or 0))
        else:
            continue
        slot = buckets.get(key)
        if slot is None:
            continue
        slot["amount"] += natural
        slot["accounts"].append({
            "code": code,
            "name": row.get("account_name") or "",
            "amount": natural,
        })
    sections = []
    for section_key, section_label, lines in spec:
        built = []
        section_amount = Decimal("0")
        for line_key, line_label, _exact, _prefixes in lines:
            slot = buckets[(section_key, line_key)]
            section_amount += slot["amount"]
            built.append({
                "key": line_key,
                "label": line_label,
                "amount": slot["amount"],
                "accounts": slot["accounts"],
            })
        sections.append({
            "key": section_key,
            "label": section_label,
            "amount": section_amount,
            "lines": built,
        })
    return {
        "taxonomy": "MCA Schedule III",
        "sections": sections,
    }


_SCHEDULE_III_BALANCE = (
    ("non_current_assets", "Non-current assets", (
        ("tangible_assets", "Tangible assets", {"1600", "1650"}, ()),
        ("capital_work_in_progress", "Capital work-in-progress", set(), ()),
        ("intangible_assets", "Intangible assets", set(), ()),
        ("non_current_investments", "Non-current investments", set(), ()),
        ("deferred_tax_assets", "Deferred tax assets", set(), ()),
        ("long_term_loans_and_advances", "Long-term loans and advances", set(), ()),
        ("other_non_current_assets", "Other non-current assets", set(), ()),
    )),
    ("current_assets", "Current assets", (
        ("inventories", "Inventories", {"1400", "1450"}, ()),
        ("trade_receivables", "Trade receivables", {"1200"}, ()),
        ("cash_and_cash_equivalents", "Cash and cash equivalents", {"1100", "1500"}, ("1500-",)),
        ("short_term_loans_and_advances", "Short-term loans and advances", {"1250"}, ()),
        ("other_current_assets", "Other current assets", {"1365", "1370", "1390"}, ("13",)),
    )),
    ("equity", "Equity", (
        ("share_capital", "Share capital", set(), ()),
        ("other_equity", "Other equity", {"3000", "3100", "3200"}, ()),
    )),
    ("non_current_liabilities", "Non-current liabilities", (
        ("long_term_borrowings", "Long-term borrowings", set(), ()),
        ("deferred_tax_liabilities", "Deferred tax liabilities", set(), ()),
        ("other_long_term_liabilities", "Other long-term liabilities", set(), ()),
        ("long_term_provisions", "Long-term provisions", set(), ()),
    )),
    ("current_liabilities", "Current liabilities", (
        ("short_term_borrowings", "Short-term borrowings", set(), ()),
        ("trade_payables", "Trade payables", {"2100"}, ()),
        ("other_current_liabilities", "Other current liabilities", {"2150", "2300"}, ("22",)),
        ("short_term_provisions", "Short-term provisions", set(), ()),
    )),
)

_SCHEDULE_III_PNL = (
    ("pnl", "Statement of profit and loss", (
        ("revenue_from_operations", "Revenue from operations", {"4100"}, ()),
        ("other_income", "Other income", {"5700"}, ()),
        ("cost_of_materials_consumed", "Cost of materials consumed", {"5100", "5110", "5400"}, ()),
        ("employee_benefits_expense", "Employee benefits expense", {"5800"}, ()),
        ("finance_costs", "Finance costs", {"5200"}, ()),
        ("depreciation_and_amortisation", "Depreciation and amortisation expense", {"5300"}, ()),
        ("other_expenses", "Other expenses", {"5150", "5250", "5450", "5500", "5600", "5900"}, ()),
    )),
)


def schedule_iii_balance(rows, surplus=None):
    """Schedule III balance sheet. ``surplus`` is the profit or loss not yet closed into equity.

    Without it the equity side holds only the capital and reserve accounts, so total assets differ
    from liabilities plus equity by the cumulative profit.
    """
    bs_rows = [
        row for row in rows
        if row.get("account_type") in (Account.Type.ASSET, Account.Type.LIABILITY, Account.Type.EQUITY)
    ]
    result = _schedule_iii_sections(
        bs_rows,
        _SCHEDULE_III_BALANCE,
        credit_normal_sections={"equity", "non_current_liabilities", "current_liabilities"},
    )
    if surplus is not None:
        amount = Decimal(str(surplus))
        for section in result["sections"]:
            if section["key"] == "equity":
                section["lines"].append({
                    "key": "surplus_in_profit_and_loss",
                    "label": "Surplus in statement of profit and loss",
                    "amount": amount,
                    "accounts": [],
                })
                section["amount"] = section["amount"] + amount
    return result


def schedule_iii_profit_and_loss(rows):
    result = _schedule_iii_sections(
        rows,
        _SCHEDULE_III_PNL,
        credit_normal_sections=set(),
        credit_normal_lines={"revenue_from_operations", "other_income"},
    )
    for section in result["sections"]:
        # The section total is profit: income lines minus expense lines. Adding them all as
        # positives produced a number that means nothing.
        income = {"revenue_from_operations", "other_income"}
        section["amount"] = sum(
            (line["amount"] if line["key"] in income else -line["amount"] for line in section["lines"]),
            Decimal("0"),
        )
    return result


def balance_sheet(company, as_of=None, cost_center=None):
    fy_from, fy_to = _indian_fy_bounds(as_of, company)
    # B1-011: `_balances` with as_of=None is all-time, but current_earnings is
    # P&L capped at fy_to — equation_holds then compares mismatched horizons.
    # Pin both to the same cut-off.
    if as_of is None:
        as_of = fy_to
    rows = _balances(company, as_of=as_of, cost_center=cost_center, exclude_fy_close_after=fy_from)
    by_type = {t: [] for t in Account.Type.values}
    for row in rows:
        if row["account_type"] in by_type:
            by_type[row["account_type"]].append(row)
    assets = sum((r["balance"] for r in by_type[Account.Type.ASSET]), Decimal("0"))
    liabilities = sum((-r["balance"] for r in by_type[Account.Type.LIABILITY]), Decimal("0"))
    equity = sum((-r["balance"] for r in by_type[Account.Type.EQUITY]), Decimal("0"))
    # BB-000433: current earnings = P&L for FY containing as_of (not all-time).
    pl = profit_and_loss(
        company, date_from=fy_from, date_to=as_of or fy_to, cost_center=cost_center,
    )["net_profit"]
    inventory_gl = Decimal("0")
    inventory_rows = []
    for row in by_type.get(Account.Type.ASSET, []):
        if row.get("account_code") == "1400":
            inventory_gl += Decimal(str(row.get("balance") or 0))
            inventory_rows.append(row)
    inventory_valuation = Decimal("0")
    inventory_method = getattr(company, "inventory_valuation_method", "WAVG") or "WAVG"
    try:
        from inventory.services import InventoryValuationService

        val_rows = InventoryValuationService.valuation(company, as_of=as_of)
        inventory_valuation = sum((Decimal(str(r.get("value") or 0)) for r in val_rows), Decimal("0"))
    except (TypeError, ValueError, ArithmeticError, AttributeError, KeyError) as exc:
        logger.warning("inventory valuation failed for company %s: %s", getattr(company, "pk", None), exc)
        inventory_valuation = inventory_gl
    inventory_source = "valuation_engine" if inventory_valuation or inventory_gl else "gl_1400_approximation"
    if not inventory_valuation and inventory_gl:
        inventory_source = "gl_1400_approximation"
    elif inventory_valuation:
        inventory_source = "valuation_engine"
    return {
        "as_of": as_of,
        "cost_center": cost_center,
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity,
        "current_earnings": pl,
        "fy_from": fy_from,
        "fy_to": fy_to,
        "equation_holds": assets == liabilities + equity + pl,
        "inventory_gl": inventory_gl,
        "inventory_valuation": inventory_valuation,
        "inventory_variance": inventory_valuation - inventory_gl,
        "inventory_method": inventory_method,
        "inventory_source": inventory_source,
        "inventory_note": (
            "Balance sheet assets use GL 1400 (document postings). "
            "inventory_valuation is the Phase 4.2 as-of replay for CA review."
            if inventory_source == "valuation_engine"
            else "No valuation replay available; inventory line is the GL 1400 approximation."
        ),
        # UXW2B-019: keep "rows" a flat list, consistent with trial_balance/profit_and_loss,
        # instead of an {ASSET: [...], LIABILITY: [...], ...} dict — the frontend's shared
        # report-table renderer expects an array here and crashed on the object shape.
        "rows": rows,
        "schedule_iii": schedule_iii_balance(rows, surplus=pl),
    }


def cash_flow(company, date_from=None, date_to=None, cost_center=None):
    """Direct cash flow statement derived from Cash (1100) & Bank (1500) movements."""
    from django.db.models import Case, DecimalField, F, Sum, Value, When

    if date_from is None and date_to is not None:
        date_from, _ = _indian_fy_bounds(date_to, company)
    elif date_from is None and date_to is None:
        date_from, date_to = _indian_fy_bounds(None, company)

    # B1-001: per-bank child ledgers are coded "1500-<bank_account.id>"
    # (accounting.services). The old code__in=["1100","1500"] filter missed
    # every real bank movement once a company had more than the parent stub,
    # understating cash. Include the children.
    cash_accounts = Account.objects.filter(company=company).filter(
        Q(code__in=["1100", "1500"]) | Q(code__startswith="1500-")
    )
    qs = JournalLine.objects.filter(
        entry__company=company,
        entry__status__in=[JournalEntry.Status.POSTED, JournalEntry.Status.REVERSED],
        account__in=cash_accounts,
    )
    if date_from:
        qs = qs.filter(entry__entry_date__gte=date_from)
    if date_to:
        qs = qs.filter(entry__entry_date__lte=date_to)
    if cost_center:
        qs = qs.filter(cost_center_id=cost_center)

    # CR-077: aggregate in SQL instead of iterating every cash journal line.
    zero = Value(Decimal("0"), output_field=DecimalField(max_digits=14, decimal_places=2))
    agg = qs.aggregate(
        financing_inflows=Sum(
            Case(
                When(debit__gt=0, entry__source_type="EQUITY", then=F("debit")),
                default=zero,
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        ),
        operating_inflows=Sum(
            Case(
                When(
                    debit__gt=0,
                    then=Case(
                        When(entry__source_type="EQUITY", then=zero),
                        default=F("debit"),
                        output_field=DecimalField(max_digits=14, decimal_places=2),
                    ),
                ),
                default=zero,
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        ),
        investing_outflows=Sum(
            Case(
                When(
                    credit__gt=0,
                    entry__source_type__in=("FIXED_ASSET", "INVESTMENT"),
                    then=F("credit"),
                ),
                default=zero,
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        ),
        operating_outflows=Sum(
            Case(
                When(
                    credit__gt=0,
                    then=Case(
                        When(
                            entry__source_type__in=("FIXED_ASSET", "INVESTMENT"),
                            then=zero,
                        ),
                        default=F("credit"),
                        output_field=DecimalField(max_digits=14, decimal_places=2),
                    ),
                ),
                default=zero,
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        ),
    )
    operating_inflows = agg["operating_inflows"] or Decimal("0")
    operating_outflows = agg["operating_outflows"] or Decimal("0")
    investing_outflows = agg["investing_outflows"] or Decimal("0")
    financing_inflows = agg["financing_inflows"] or Decimal("0")

    net_operating = operating_inflows - operating_outflows
    net_investing = -investing_outflows
    net_financing = financing_inflows
    net_change = net_operating + net_investing + net_financing

    return {
        "date_from": date_from,
        "date_to": date_to,
        "cost_center": cost_center,
        "operating_activities": {
            "inflows": operating_inflows,
            "outflows": operating_outflows,
            "net": net_operating,
        },
        "investing_activities": {
            "outflows": investing_outflows,
            "net": net_investing,
        },
        "financing_activities": {
            "inflows": financing_inflows,
            "net": net_financing,
        },
        "net_cash_flow": net_change,
        "aid_kind": "gl_cash_flow",
        "label": "GL cash-flow aid (1100/1500)",
        # CR-076: distinguish from document cash book (receipts/payments).
        "disclaimer": (
            "GL cash-movement aid from Cash (1100) and Bank (1500) journal lines — "
            "not the document cash book (posted receipts/supplier payments), and not a "
            "Schedule III / Ind AS cash-flow statement. Unclassified source types are "
            "treated as operating."
        ),
    }


def fy_bounds_for_end(company, fy_end):
    """FY start is the 1st of company.fy_start_month (default April) on or before fy_end."""
    from datetime import date

    start_month = int(getattr(company, "fy_start_month", None) or 4)
    if start_month < 1 or start_month > 12:
        logger.warning(
            "accounting.reports: company %s fy_start_month=%r out of range; using April",
            getattr(company, "pk", None), start_month,
        )
        start_month = 4
    start_year = fy_end.year if fy_end.month >= start_month else fy_end.year - 1
    return date(start_year, start_month, 1), fy_end


def _fy_close_source_id(fy_end):
    return int(fy_end.strftime("%Y%m%d"))


def close_financial_year(company, fy_end, user=None):
    """BB-000664: close income-statement accounts to 3100 Retained Earnings.

    Rules:
    - FY start is derived from company.fy_start_month (default 4) and ``fy_end``.
    - Sum posted (unreversed) journal lines on INCOME / EXPENSE accounts in the
      FY date range. Header/equity accounts such as 3200 Opening Balance Equity
      are not closed into 3100.
    - Post one balanced FY_CLOSE journal that zeros each IS account against 3100.
      Idempotent on (company, source_type=FY_CLOSE, source_id=YYYYMMDD, purpose=FY_CLOSE).
    - After success, every AccountingPeriod overlapping the FY is set to CLOSED.
    - Refuse unless ``confirm`` path already passed API checks. Service-level
      blockers (practical):
        * BooksHealthService.control_balances is unhealthy (AR/AP mismatch or
          error-severity alerts such as DOCUMENT_MISSING_POSTING), OR
        * any DRAFT sales or purchase invoice is dated inside the FY.
      Soft-closed periods with those blockers therefore cannot be year-closed.
    """
    from datetime import date as date_cls
    from decimal import Decimal

    from django.db import transaction
    from django.db.models import Sum

    from core.exceptions import BusinessRuleError
    from purchases.models import PurchaseInvoice
    from sales.models import SalesInvoice

    from .models import Account, AccountingPeriod, JournalEntry, JournalLine
    from .services import BooksHealthService, PostingService, seed_chart_of_accounts

    if isinstance(fy_end, str):
        try:
            fy_end = date_cls.fromisoformat(fy_end[:10])
        except (ValueError, TypeError):
            raise BusinessRuleError("Invalid financial year end date (expected YYYY-MM-DD).")
    fy_start, fy_end = fy_bounds_for_end(company, fy_end)
    source_id = _fy_close_source_id(fy_end)

    existing = JournalEntry.objects.filter(
        company=company,
        source_type="FY_CLOSE",
        source_id=source_id,
        purpose="FY_CLOSE",
        status=JournalEntry.Status.POSTED,
        lines__isnull=False,
    ).distinct().first()
    if existing:
        AccountingPeriod.objects.filter(
            company=company, start_date__lte=fy_end, end_date__gte=fy_start,
        ).exclude(status=AccountingPeriod.Status.CLOSED).update(
            status=AccountingPeriod.Status.CLOSED,
            updated_by=user,
            updated_at=timezone.now(),  # B1-029
        )
        from reporting.models import GstReturnPeriod

        GstReturnPeriod.objects.filter(
            company=company,
            period__gte=fy_start.strftime("%Y-%m"),
            period__lte=fy_end.strftime("%Y-%m"),
        ).exclude(status=GstReturnPeriod.Status.CLOSED).update(
            status=GstReturnPeriod.Status.CLOSED,
            closed_by=user,
            closed_at=timezone.now(),
            updated_at=timezone.now(),  # B1-029
        )
        return existing

    health = BooksHealthService.control_balances(company)
    unhealthy = (not health["ar"]["healthy"]) or (not health["ap"]["healthy"])
    error_alerts = [a for a in health.get("alerts") or [] if a.get("severity") == "error"]
    if unhealthy or error_alerts:
        codes = ", ".join(sorted({a["code"] for a in error_alerts})) or "AR/AP control mismatch"
        raise BusinessRuleError(f"Financial-year close blocked: books health is unhealthy ({codes}).")

    draft_sales = SalesInvoice.objects.filter(
        company=company, status=SalesInvoice.Status.DRAFT,
        invoice_date__gte=fy_start, invoice_date__lte=fy_end,
    ).exists()
    draft_purchases = PurchaseInvoice.objects.filter(
        company=company, status=PurchaseInvoice.Status.DRAFT,
        invoice_date__gte=fy_start, invoice_date__lte=fy_end,
    ).exists()
    if draft_sales or draft_purchases:
        raise BusinessRuleError(
            "Financial-year close blocked: draft sales or purchase invoices exist in this FY."
        )

    from manufacturing.models import WorkOrder

    if BooksHealthService.manufacturing_books_required(company) and WorkOrder.objects.filter(
        company=company,
        status=WorkOrder.Status.RELEASED,
        released_at__lte=fy_end,
    ).exists():
        raise BusinessRuleError(
            "Financial-year close blocked: OPEN_WIP — released work orders exist. Complete or cancel them first."
        )
    wip = JournalLine.objects.filter(
        entry__company=company,
        entry__status__in=[JournalEntry.Status.POSTED, JournalEntry.Status.REVERSED],
        entry__entry_date__lte=fy_end,
        account__code="1450",
    ).aggregate(d=Sum("debit"), c=Sum("credit"))
    wip_net = (wip["d"] or Decimal("0")) - (wip["c"] or Decimal("0"))
    if wip_net != 0:
        raise BusinessRuleError(
            f"Financial-year close blocked: OPEN_WIP — WIP GL 1450 net is {wip_net}."
        )

    if not company.accounting_enabled:
        raise BusinessRuleError("Accounting is not enabled for this company.")

    # B1-008: don't post an FY_CLOSE journal for a year that has no accounting
    # periods — the close would produce a journal that nothing then locks, and
    # the "set periods to CLOSED" step at the end is a no-op. Require at least
    # one period overlapping the FY.
    if not AccountingPeriod.objects.filter(
        company=company, start_date__lte=fy_end, end_date__gte=fy_start,
    ).exists():
        raise BusinessRuleError(
            "Financial-year close blocked: no accounting periods are defined for "
            f"{fy_start:%Y-%m-%d}–{fy_end:%Y-%m-%d}. Create the periods first."
        )

    seed_chart_of_accounts(company, user)
    retained = PostingService._account(company, "3100")

    qs = JournalLine.objects.filter(
        entry__company=company,
        entry__status__in=[JournalEntry.Status.POSTED, JournalEntry.Status.REVERSED],
        entry__entry_date__gte=fy_start,
        entry__entry_date__lte=fy_end,
        account__type__in=(Account.Type.INCOME, Account.Type.EXPENSE),
    ).exclude(entry__purpose="FY_CLOSE")

    lines = []
    re_debit = Decimal("0")
    re_credit = Decimal("0")
    for row in qs.values("account_id").annotate(debit=Sum("debit"), credit=Sum("credit")):
        debit = row["debit"] or Decimal("0")
        credit = row["credit"] or Decimal("0")
        net = debit - credit
        if net == 0:
            continue
        account = Account.objects.get(company=company, pk=row["account_id"])
        if net > 0:
            lines.append({"account": account, "credit": net})
            re_debit += net
        else:
            amt = -net
            lines.append({"account": account, "debit": amt})
            re_credit += amt

    entry = None
    with transaction.atomic():
        if lines:
            net_re = re_debit - re_credit
            if net_re > 0:
                lines.append({"account": retained, "debit": net_re})
            elif net_re < 0:
                lines.append({"account": retained, "credit": -net_re})
            entry = PostingService.post(
                company=company,
                source_type="FY_CLOSE",
                source_id=source_id,
                purpose="FY_CLOSE",
                entry_date=fy_end,
                user=user,
                allow_soft_closed=True,
                narration=f"FY close {fy_start.isoformat()} to {fy_end.isoformat()}",
                lines=lines,
            )
        AccountingPeriod.objects.filter(
            company=company, start_date__lte=fy_end, end_date__gte=fy_start,
        ).exclude(status=AccountingPeriod.Status.CLOSED).update(
            status=AccountingPeriod.Status.CLOSED,
            updated_by=user,
            updated_at=timezone.now(),  # B1-029
        )
        # BB-000712: align GST return periods with FY close.
        from reporting.models import GstReturnPeriod

        GstReturnPeriod.objects.filter(
            company=company,
            period__gte=fy_start.strftime("%Y-%m"),
            period__lte=fy_end.strftime("%Y-%m"),
        ).exclude(status=GstReturnPeriod.Status.CLOSED).update(
            status=GstReturnPeriod.Status.CLOSED,
            closed_by=user,
            closed_at=timezone.now(),
            updated_at=timezone.now(),  # B1-029
        )
    return entry
