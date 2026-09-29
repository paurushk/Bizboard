"""Campaign funnel and hierarchy rollup."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum

from sales.models import Quotation

from .models import Campaign, Opportunity


def _won_revenue(opportunity: Opportunity) -> tuple[Decimal, str]:
    converted = Quotation.objects.filter(
        company_id=opportunity.company_id,
        opportunity=opportunity,
        status=Quotation.Status.CONVERTED,
    )
    total = converted.aggregate(total=Sum("grand_total"))["total"]
    if total is not None:
        return Decimal(total), "quotation_total"
    return Decimal(opportunity.amount or 0), "opportunity_amount"


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
