from decimal import Decimal
import logging

from django.db.models import F, Q, Sum
from django.utils import timezone

from .models import Account, JournalEntry, JournalLine

logger = logging.getLogger(__name__)


def _balances(company, *, as_of=None, date_from=None, date_to=None, cost_center=None, exclude_fy_close=False, exclude_fy_close_after=None):
    qs = JournalLine.objects.filter(entry__company=company, entry__status=JournalEntry.Status.POSTED).select_related("account")
    if as_of:
        qs = qs.filter(entry__entry_date__lte=as_of)
    if date_from:
        qs = qs.filter(entry__entry_date__gte=date_from)
    if date_to:
        qs = qs.filter(entry__entry_date__lte=date_to)
    if cost_center:
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
            "net_profit": income - expenses, "rows": rows}


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
    }


def cash_flow(company, date_from=None, date_to=None, cost_center=None):
    """Direct cash flow statement derived from Cash (1100) & Bank (1500) movements."""
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
        entry__status=JournalEntry.Status.POSTED,
        account__in=cash_accounts,
    ).select_related("entry", "account")
    if date_from:
        qs = qs.filter(entry__entry_date__gte=date_from)
    if date_to:
        qs = qs.filter(entry__entry_date__lte=date_to)
    if cost_center:
        qs = qs.filter(cost_center_id=cost_center)

    operating_inflows = Decimal("0")
    operating_outflows = Decimal("0")
    investing_outflows = Decimal("0")
    financing_inflows = Decimal("0")

    for line in qs:
        if line.debit > 0:
            if line.entry.source_type in ("CUSTOMER_RECEIPT", "SALES_INVOICE"):
                operating_inflows += line.debit
            elif line.entry.source_type == "EQUITY":
                financing_inflows += line.debit
            else:
                operating_inflows += line.debit
        if line.credit > 0:
            if line.entry.source_type in ("SUPPLIER_PAYMENT", "PURCHASE_INVOICE", "EXPENSE"):
                operating_outflows += line.credit
            elif line.entry.source_type in ("FIXED_ASSET", "INVESTMENT"):
                investing_outflows += line.credit
            else:
                operating_outflows += line.credit

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
        "aid_kind": "cash_movement",
        "disclaimer": (
            "Cash-movement aid from Cash (1100) and Bank (1500) GL lines — "
            "not a Schedule III / Ind AS cash-flow statement. "
            "Unclassified source types are treated as operating."
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
    ).first()
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

    if WorkOrder.objects.filter(
        company=company,
        status=WorkOrder.Status.RELEASED,
    ).filter(Q(released_at__lte=fy_end) | Q(released_at__isnull=True)).exists():
        raise BusinessRuleError(
            "Financial-year close blocked: OPEN_WIP — released work orders exist. Complete or cancel them first."
        )
    wip = JournalLine.objects.filter(
        entry__company=company,
        entry__status=JournalEntry.Status.POSTED,
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
        entry__status=JournalEntry.Status.POSTED,
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
        account = Account.objects.get(pk=row["account_id"])
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
