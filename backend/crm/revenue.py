"""One revenue definition for the CRM (review D3).

Revenue of a deal = taxable value of its COMPLETED invoices, minus the taxable value of
COMPLETED credit notes against them. GST is not revenue, ``Opportunity.amount`` is a
forecast, and a quotation total is neither.

An invoice belongs to a deal when ``SalesInvoice.opportunity`` says so. Invoices made before
that link existed are found through the quote -> order -> challan -> invoice chain, so old
data keeps reporting until ``backfill_invoice_opportunity`` has written the link.
Campaign ROI, referral percent rewards and won-versus-invoiced all read through here.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum

NO_INVOICE = "no_completed_invoice"
NET_TAXABLE = "completed_invoice_taxable_net"
BASIS_LABEL = "Completed invoice value before GST, net of credit notes"


def chain_invoice_ids(company_id, opportunity_ids) -> dict[int, set[int]]:
    """Invoices reached from each deal through its quotations, orders and challans."""
    from sales.models import (
        DeliveryChallan,
        Quotation,
        QuotationConversion,
        SalesInvoice,
        SalesOrder,
    )

    found: dict[int, set[int]] = defaultdict(set)
    quote_opp = dict(
        Quotation.objects.filter(company_id=company_id, opportunity_id__in=opportunity_ids)
        .values_list("id", "opportunity_id")
    )
    if not quote_opp:
        return found
    order_opps: dict[int, set[int]] = defaultdict(set)
    seen_quotes = set()
    live = QuotationConversion.objects.filter(
        company_id=company_id, quotation_id__in=list(quote_opp), released_at__isnull=True,
    )
    for quote_id, invoice_id, order_id in live.values_list("quotation_id", "sales_invoice_id", "sales_order_id"):
        opp = quote_opp[quote_id]
        if invoice_id:
            found[opp].add(invoice_id)
        if order_id:
            order_opps[order_id].add(opp)
    # Quotes converted before the ledger existed have no rows, only the old single link.
    for quote_id in QuotationConversion.objects.filter(quotation_id__in=list(quote_opp)).values_list(
        "quotation_id", flat=True,
    ):
        seen_quotes.add(quote_id)
    legacy = Quotation.objects.filter(
        company_id=company_id, pk__in=list(quote_opp), converted_invoice_id__isnull=False,
    ).exclude(pk__in=seen_quotes)
    for quote_id, invoice_id in legacy.values_list("id", "converted_invoice_id"):
        found[quote_opp[quote_id]].add(invoice_id)
    if order_opps:
        order_ids = list(order_opps)
        for invoice_id, order_id in SalesInvoice.objects.filter(
            company_id=company_id, source_order_id__in=order_ids,
        ).values_list("id", "source_order_id"):
            for opp in order_opps[order_id]:
                found[opp].add(invoice_id)
        for order_id, invoice_id in SalesOrder.objects.filter(
            company_id=company_id, pk__in=order_ids, converted_invoice_id__isnull=False,
        ).values_list("id", "converted_invoice_id"):
            for opp in order_opps[order_id]:
                found[opp].add(invoice_id)
        for order_id, invoice_id in DeliveryChallan.objects.filter(
            company_id=company_id, sales_order_id__in=order_ids, converted_invoice_id__isnull=False,
        ).values_list("sales_order_id", "converted_invoice_id"):
            for opp in order_opps[order_id]:
                found[opp].add(invoice_id)
    return found


def invoice_ids_by_opportunity(company_id, opportunity_ids) -> dict[int, set[int]]:
    from sales.models import SalesInvoice

    ids = list(opportunity_ids)
    found = chain_invoice_ids(company_id, ids)
    for invoice_id, opp in SalesInvoice.objects.filter(
        company_id=company_id, opportunity_id__in=ids,
    ).values_list("id", "opportunity_id"):
        found[opp].add(invoice_id)
    return found


def revenue_by_opportunity(company_id, opportunity_ids) -> dict[int, tuple[Decimal, str]]:
    """``{deal id: (revenue, source)}`` for every deal asked about, in a fixed number of queries."""
    from sales.models import SalesCreditNote, SalesInvoice

    ids = list(opportunity_ids)
    if not ids:
        return {}
    by_opp = invoice_ids_by_opportunity(company_id, ids)
    every = set().union(*by_opp.values()) if by_opp else set()
    taxable = dict(
        SalesInvoice.objects.filter(
            company_id=company_id, pk__in=every, status=SalesInvoice.Status.COMPLETED,
        ).values_list("id", "taxable_total")
    ) if every else {}
    credits = {}
    if taxable:
        credits = {
            row["sales_invoice_id"]: row["total"] or Decimal("0")
            for row in SalesCreditNote.objects.filter(
                company_id=company_id,
                sales_invoice_id__in=list(taxable),
                status=SalesCreditNote.Status.COMPLETED,
            ).values("sales_invoice_id").annotate(total=Sum("taxable_total"))
        }
    out: dict[int, tuple[Decimal, str]] = {}
    for opp in ids:
        completed = [inv for inv in by_opp.get(opp, ()) if inv in taxable]
        if not completed:
            out[opp] = (Decimal("0"), NO_INVOICE)
            continue
        total = sum((Decimal(taxable[inv]) - Decimal(credits.get(inv, 0)) for inv in completed), Decimal("0"))
        out[opp] = (total, NET_TAXABLE)
    return out


def opportunity_revenue(opportunity) -> Decimal:
    """Net taxable invoiced value of one deal. Never negative."""
    amount, _source = revenue_by_opportunity(opportunity.company_id, [opportunity.id])[opportunity.id]
    return amount if amount > 0 else Decimal("0")


def link_invoice_to_opportunity(invoice, opportunity) -> None:
    """Record which deal an invoice bills. Idempotent; never overwrites an existing link."""
    if opportunity is None or invoice.opportunity_id:
        return
    if opportunity.company_id != invoice.company_id:
        return
    invoice.opportunity = opportunity
    invoice.save(update_fields=["opportunity"])


def opportunity_for_order(order):
    """The deal an order came from, through the quotation conversion ledger."""
    from sales.models import QuotationConversion

    row = (
        QuotationConversion.objects.filter(
            company_id=order.company_id, sales_order_id=order.pk, released_at__isnull=True,
            quotation__opportunity__isnull=False,
        )
        .select_related("quotation__opportunity")
        .order_by("id")
        .first()
    )
    return row.quotation.opportunity if row else None
