"""One customer page over four existing services. B2 is not an input."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce

from core.services.feature_flags import flag_enabled
from payments.dunning import customer_risk_snapshot
from reporting.services import ReportService


def can_open_customer_360(company_user) -> bool:
    """Same people who can see an overdue-customer row: sales, payments, or financial reports."""
    if company_user is None:
        return False
    if getattr(company_user, "role", "") == "OWNER":
        return True
    return bool(
        getattr(company_user, "can_create_sales", False)
        or getattr(company_user, "can_create_payments", False)
        or getattr(company_user, "can_view_financial_reports", False)
    )


_PATTERN_LABELS = {
    "clear": "Nothing overdue",
    "open": "Amount still open",
    "overdue": "Overdue",
    "overdue_severe": "Seriously overdue",
    "stop_credit": "Stop further credit",
}
_NEXT_STEP_LABELS = {
    "follow_up": "Follow up",
    "send_statement": "Send a statement",
    "send_link": "Send a payment link",
    "reduce_credit": "Reduce the credit limit",
    "stop_credit": "Stop further credit",
}


def _human_pattern(code) -> str:
    if not code:
        return ""
    return _PATTERN_LABELS.get(str(code), str(code).replace("_", " "))


def _human_next_step(code) -> str:
    if not code:
        return ""
    return _NEXT_STEP_LABELS.get(str(code), str(code).replace("_", " "))


def _can_see_money(company_user) -> bool:
    if company_user is None:
        return False
    if getattr(company_user, "role", "") == "OWNER":
        return True
    return bool(getattr(company_user, "can_view_financial_reports", False))


def customer_360(company, customer, company_user=None) -> dict | None:
    from ledgers.services import LedgerService

    if not flag_enabled(company, "ENABLE_CUSTOMER_360"):
        return None
    from sales.models import SalesOrderItem

    sales_body = ReportService.customer_sales(company)
    sales = next(
        (row for row in sales_body.get("rows", []) if row.get("customer_id") == customer.id),
        {"customer_id": customer.id, "customer": customer.name, "invoices": 0, "amount": "0"},
    )
    profit = ReportService.invoice_profit_report(company, customer_id=customer.id)
    risk = customer_risk_snapshot(company, customer)
    from sales.models import SalesItem

    products = list(
        SalesItem.objects.filter(company=company, invoice__customer=customer)
        .exclude(invoice__status="DRAFT")
        .order_by("-invoice__invoice_date", "-id")
        .values_list("product__name", flat=True)[:12]
    )
    if not products:
        products = list(
            SalesOrderItem.objects.filter(
                company=company,
                sales_order__customer=customer,
            )
            .order_by("-sales_order__order_date", "-id")
            .values_list("product__name", flat=True)[:12]
        )
    show_money = _can_see_money(company_user)
    from core.mail import is_suppressed

    email = (getattr(customer, "email", "") or "").strip()
    body = {
        "customer_id": customer.id,
        "name": customer.name,
        # WP-CM1: mail to this address bounced or was marked spam, so it is no longer sent.
        "email_suppressed": bool(email) and is_suppressed(email),
        "sales": {
            "invoices": sales.get("invoices", 0),
            "amount": str(sales.get("amount")) if show_money else None,
        },
        "products": list(dict.fromkeys(products)),
        "pattern": _human_pattern(risk.get("collection_status")),
        "recommended_next_step": _human_next_step(risk.get("recommended_next_step")),
        "outstanding": risk.get("outstanding") if show_money else None,
        # Cheques taken but not yet cleared: already counted as received above, so say so.
        "uncleared_cheques": (
            str(LedgerService.uncleared_cheque_total(company, customer)) if show_money else None
        ),
        "aging": risk.get("ageing") if show_money else None,
        "profit": profit if show_money else None,
    }
    if flag_enabled(company, "ENABLE_COMPLAINTS"):
        from complaints.models import Complaint

        body["complaints"] = [
            {
                "id": row.id,
                "number": row.number,
                "status": row.status,
                "category": row.category,
            }
            for row in Complaint.objects.filter(company=company, customer=customer).order_by("-id")[:20]
        ]
    if flag_enabled(company, "ENABLE_CRM"):
        from crm.models import Opportunity

        def _sum(stages):
            total = Opportunity.objects.filter(
                company=company, customer=customer, stage__in=stages,
            ).aggregate(total=Sum(Coalesce("amount", Decimal("0"))))["total"] or Decimal("0")
            return Decimal(total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        open_total = _sum(Opportunity.OPEN_STAGES)
        won_total = _sum([Opportunity.Stage.WON])
        body["open_pipeline_total"] = str(open_total)
        body["won_total"] = str(won_total)
        # Kept for one release: open plus won. Lost deals are no longer counted.
        body["opportunity_total"] = str(open_total + won_total)
    return body
