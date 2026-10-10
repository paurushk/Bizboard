"""Campaign funnel and hierarchy rollup."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum

from sales.models import Quotation

from .models import Campaign, Opportunity


def _won_revenue(opportunity: Opportunity) -> tuple[Decimal, str]:
    """Completed-invoice taxable value, net of completed credit notes.

    Quotation totals and opportunity.amount are not revenue. grand_total
    includes GST, so it is not the basis either.

    Known limit: an order or invoice edited after conversion to add lines that were
    not on the quote counts in full.
    """
    from sales.models import (
        DeliveryChallan,
        QuotationConversion,
        SalesCreditNote,
        SalesInvoice,
        SalesOrder,
    )

    # Every path from a quote to an invoice: direct conversion, quote -> order -> invoice
    # (split invoices, the order's own link, or a challan), and pre-ledger legacy links.
    # Released conversions are ignored, and partially converted quotes count.
    company_id = opportunity.company_id
    quote_ids = list(
        Quotation.objects.filter(company_id=company_id, opportunity=opportunity).values_list("id", flat=True)
    )
    live = QuotationConversion.objects.filter(
        company_id=company_id, quotation_id__in=quote_ids, released_at__isnull=True
    )
    invoice_ids = set(
        live.filter(sales_invoice_id__isnull=False).values_list("sales_invoice_id", flat=True)
    )
    order_ids = set(live.filter(sales_order_id__isnull=False).values_list("sales_order_id", flat=True))
    if order_ids:
        invoice_ids |= set(
            SalesInvoice.objects.filter(company_id=company_id, source_order_id__in=order_ids)
            .values_list("id", flat=True)
        )
        invoice_ids |= set(
            SalesOrder.objects.filter(
                company_id=company_id, pk__in=order_ids, converted_invoice_id__isnull=False
            ).values_list("converted_invoice_id", flat=True)
        )
        invoice_ids |= set(
            DeliveryChallan.objects.filter(
                company_id=company_id, sales_order_id__in=order_ids, converted_invoice_id__isnull=False
            ).values_list("converted_invoice_id", flat=True)
        )
    # Quotes converted before the ledger existed have no rows, only the old single link.
    invoice_ids |= set(
        Quotation.objects.filter(
            company_id=company_id,
            pk__in=quote_ids,
            converted_invoice_id__isnull=False,
        )
        .exclude(pk__in=QuotationConversion.objects.filter(quotation_id__in=quote_ids).values("quotation_id"))
        .values_list("converted_invoice_id", flat=True)
    )
    invoice_ids = list(invoice_ids)
    invoices = SalesInvoice.objects.filter(
        company_id=opportunity.company_id,
        pk__in=invoice_ids or [-1],
        status=SalesInvoice.Status.COMPLETED,
    )
    if not invoices.exists():
        return Decimal("0"), "no_completed_invoice"
    taxable = invoices.aggregate(total=Sum("taxable_total"))["total"] or Decimal("0")
    credits = (
        SalesCreditNote.objects.filter(
            company_id=opportunity.company_id,
            sales_invoice_id__in=invoices.values("id"),
            status=SalesCreditNote.Status.COMPLETED,
        ).aggregate(total=Sum("taxable_total"))["total"]
        or Decimal("0")
    )
    return Decimal(taxable) - Decimal(credits), "completed_invoice_taxable_net"


def _direct_stats(company, campaign: Campaign) -> dict:
    leads = campaign.leads.filter(company=company)
    lead_ids = list(leads.values_list("id", flat=True))
    opportunities = Opportunity.objects.filter(company=company, lead_id__in=lead_ids)
    won = opportunities.filter(stage=Opportunity.Stage.WON)
    revenue = Decimal("0")
    sources = []
    for opportunity in won:
        amount, source = _won_revenue(opportunity)
        revenue += amount
        sources.append({"opportunity": opportunity.id, "revenue_source": source, "revenue": str(amount)})
    budget = Decimal(campaign.budget or 0)
    return {
        "leads": leads.count(),
        "opportunities": opportunities.count(),
        "won_opportunities": won.count(),
        "budget": str(budget),
        "revenue": str(revenue),
        "target_revenue": None if campaign.target_revenue is None else str(campaign.target_revenue),
        "roi_ratio": None if budget == 0 else str((revenue / budget).quantize(Decimal("0.0001"))),
        "variance": str(revenue - budget),
        "rows": sources,
    }


def campaign_funnel(company, campaign: Campaign) -> dict:
    return _direct_stats(company, campaign)


def campaign_rollup(company, campaign: Campaign, *, depth: int = 5) -> dict:
    stats = _direct_stats(company, campaign)
    if depth <= 0:
        return stats
    for child in campaign.children.filter(company=company):
        child_stats = campaign_rollup(company, child, depth=depth - 1)
        for key in ("leads", "opportunities", "won_opportunities"):
            stats[key] += child_stats[key]
        revenue = Decimal(stats["revenue"]) + Decimal(child_stats["revenue"])
        budget = Decimal(stats["budget"]) + Decimal(child_stats["budget"])
        stats["revenue"] = str(revenue)
        stats["budget"] = str(budget)
        stats["variance"] = str(revenue - budget)
        stats["roi_ratio"] = None if budget == 0 else str((revenue / budget).quantize(Decimal("0.0001")))
        stats["rows"] = stats["rows"] + child_stats["rows"]
    return stats
