"""Open-pipeline forecast. Amount is the single source; lines keep it in sync."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from .models import Opportunity


def sync_opportunity_amount(opportunity: Opportunity) -> None:
    lines = list(opportunity.lines.all())
    if not lines:
        opportunity.amount = Decimal("0.00")
        opportunity.save(update_fields=["amount", "updated_at"])
        return
    total = sum((line.quantity * line.unit_price for line in lines), Decimal("0"))
    opportunity.amount = total.quantize(Decimal("0.01"))
    opportunity.save(update_fields=["amount", "updated_at"])


def won_versus_invoices(company, month) -> dict:
    """Won opportunity amounts in a month, next to completed invoices for those customers.

    These are two sums. They are not a forecast and not a model score.
    """
    from datetime import date, datetime

    from django.utils import timezone

    from sales.models import SalesInvoice

    if isinstance(month, str):
        year_text, month_text = month.split("-", 1)
        start = date(int(year_text), int(month_text), 1)
    else:
        start = month.replace(day=1)
    if start.month == 12:
        end = date(start.year + 1, 1, 1)
    else:
        end = date(start.year, start.month + 1, 1)
    tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(datetime(start.year, start.month, start.day), tz)
    end_dt = timezone.make_aware(datetime(end.year, end.month, end.day), tz)
    won = Opportunity.objects.filter(
        company=company,
        stage=Opportunity.Stage.WON,
        closed_at__gte=start_dt,
        closed_at__lt=end_dt,
    )
    won_amount = sum((Decimal(row.amount or 0) for row in won), Decimal("0"))
    customer_ids = [row.customer_id for row in won if row.customer_id]
    invoiced = Decimal("0")
    if customer_ids:
        invoices = SalesInvoice.objects.filter(
            company=company,
            customer_id__in=customer_ids,
            status=SalesInvoice.Status.COMPLETED,
            invoice_date__gte=start,
            invoice_date__lt=end,
        )
        invoiced = sum((Decimal(row.grand_total or 0) for row in invoices), Decimal("0"))
    return {
        "month": f"{start.year:04d}-{start.month:02d}",
        "won_amount": str(won_amount.quantize(Decimal("0.01"))),
        "invoiced_amount": str(invoiced.quantize(Decimal("0.01"))),
    }


def pipeline_forecast(company) -> dict:
    buckets: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    unscheduled = Decimal("0")
    qs = Opportunity.objects.filter(company=company, stage__in=Opportunity.OPEN_STAGES)
    for opportunity in qs:
        weighted = (Decimal(opportunity.amount or 0) * Decimal(opportunity.probability or 0)) / Decimal("100")
        if opportunity.expected_close_date is None:
            unscheduled += weighted
        else:
            key = opportunity.expected_close_date.strftime("%Y-%m")
            buckets[key] += weighted
    months = [
        {"month": key, "amount": str(buckets[key].quantize(Decimal("0.01")))}
        for key in sorted(buckets)
    ]
    return {
        "months": months,
        "unscheduled": str(unscheduled.quantize(Decimal("0.01"))),
    }
