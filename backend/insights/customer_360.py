"""One customer page over four existing services. B2 is not an input."""

from __future__ import annotations

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


def _can_see_money(company_user) -> bool:
    if company_user is None:
        return False
    if getattr(company_user, "role", "") == "OWNER":
        return True
    return bool(getattr(company_user, "can_view_financial_reports", False))


def customer_360(company, customer, company_user=None) -> dict | None:
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
    products = list(
        SalesOrderItem.objects.filter(
            company=company,
            sales_order__customer=customer,
        )
        .order_by("-sales_order__order_date", "-id")
        .values_list("product__name", flat=True)[:12]
    )
    show_money = _can_see_money(company_user)
    return {
        "customer_id": customer.id,
        "name": customer.name,
        "sales": {
            "invoices": sales.get("invoices", 0),
            "amount": str(sales.get("amount")) if show_money else None,
        },
        "products": list(dict.fromkeys(products)),
        "pattern": risk.get("collection_status"),
        "recommended_next_step": risk.get("recommended_next_step"),
        "outstanding": risk.get("outstanding") if show_money else None,
        "aging": risk.get("ageing") if show_money else None,
        "profit": profit if show_money else None,
    }
