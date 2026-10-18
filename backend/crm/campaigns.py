"""Campaign funnel and hierarchy rollup."""

from __future__ import annotations

from decimal import Decimal

from .models import Campaign, Opportunity
from .revenue import BASIS_LABEL, revenue_by_opportunity


def _won_revenue(opportunity: Opportunity) -> tuple[Decimal, str]:
    """Completed-invoice taxable value, net of completed credit notes (see ``crm.revenue``)."""
    return revenue_by_opportunity(opportunity.company_id, [opportunity.id])[opportunity.id]


def _direct_stats(company, campaign: Campaign) -> dict:
    leads = campaign.leads.filter(company=company)
    lead_count = leads.count()
    opportunities = Opportunity.objects.filter(company=company, lead__campaign=campaign)
    opp_count = opportunities.count()
    won = list(
        opportunities.filter(stage=Opportunity.Stage.WON).order_by("id").values("id", "title")
    )
    figures = revenue_by_opportunity(company.id, [row["id"] for row in won])
    revenue = Decimal("0")
    sources = []
    for row in won:
        amount, source = figures[row["id"]]
        revenue += amount
        sources.append({
            "opportunity": row["id"],
            "title": row["title"],
            "revenue_source": source,
            "revenue": str(amount),
        })
    budget = Decimal(campaign.budget or 0)
    return {
        "campaign_id": campaign.id,
        "campaign_name": campaign.name,
        "leads": lead_count,
        "opportunities": opp_count,
        "won_opportunities": len(won),
        "budget": str(budget),
        "revenue": str(revenue),
        "target_revenue": None if campaign.target_revenue is None else str(campaign.target_revenue),
        # Revenue divided by the planned budget, not by money actually spent.
        "roi_ratio": None if budget == 0 else str((revenue / budget).quantize(Decimal("0.0001"))),
        "roi_basis": f"{BASIS_LABEL}; budget is the planned budget",
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
