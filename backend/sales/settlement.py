"""One settlement bucket for the invoice list, the payment filter, and the stats chips."""

from decimal import Decimal

from django.db.models import Case, DecimalField, ExpressionWrapper, F, OuterRef, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce

from sales.models import SalesInvoice

OPEN = (SalesInvoice.Status.COMPLETED, SalesInvoice.Status.RETURNED)


def settlement_bucket(status, grand_total, outstanding, live_alloc, credit_notes, settlement) -> str:
    """PAID, PARTIAL, UNPAID, or NONE.

    NONE is a draft or a cancelled bill. PARTIAL means something has been
    applied (a live receipt, a credit note, or a settlement discount) and money
    is still due. Callers must pass the same outstanding the Due column shows.
    """
    if status not in OPEN:
        return "NONE"
    total = Decimal(str(grand_total or 0))
    due = Decimal(str(outstanding or 0))
    alloc = Decimal(str(live_alloc or 0))
    notes = Decimal(str(credit_notes or 0))
    discount = Decimal(str(settlement or 0))
    if due <= 0 and total > 0:
        return "PAID"
    if due > 0 and (alloc > 0 or notes > 0 or discount > 0):
        return "PARTIAL"
    if due > 0:
        return "UNPAID"
    return "NONE"


def annotate_live_settlement(qs):
    """Live paid/partial/unpaid: reversed receipts do not count, credit notes do."""
    from payments.models import PaymentAllocation
    from sales.models import SalesCreditNote, SalesDebitNote

    money = DecimalField(max_digits=14, decimal_places=2)

    def _sum(filtered, field):
        return Coalesce(
            Subquery(
                filtered.values("sales_invoice_id").annotate(s=Sum(field)).values("s")[:1],
                output_field=money,
            ),
            Value(0, output_field=money),
        )

    cn = _sum(
        SalesCreditNote.objects.filter(
            sales_invoice_id=OuterRef("pk"),
            status=SalesCreditNote.Status.COMPLETED,
        ),
        "grand_total",
    )
    dn = _sum(
        SalesDebitNote.objects.filter(
            sales_invoice_id=OuterRef("pk"),
            status=SalesDebitNote.Status.COMPLETED,
        ),
        "grand_total",
    )
    alloc = _sum(
        PaymentAllocation.objects.filter(
            sales_invoice_id=OuterRef("pk"),
            reversed_at__isnull=True,
            receipt__isnull=False,
            supplier_payment__isnull=True,
        ),
        "amount",
    )
    # Settlement (early-payment) discount counts as settled, as the ledger counts it: each
    # allocation carries its share of its receipt's discount, by share of the receipt's allocations.
    receipt_alloc_total = Subquery(
        PaymentAllocation.objects.filter(
            receipt_id=OuterRef("receipt_id"),
            receipt__isnull=False,
            supplier_payment__isnull=True,
            reversed_at__isnull=True,
        ).values("receipt_id").annotate(t=Sum("amount")).values("t")[:1],
        output_field=money,
    )
    discount_share = Coalesce(
        Subquery(
            PaymentAllocation.objects.filter(
                sales_invoice_id=OuterRef("pk"),
                reversed_at__isnull=True,
                receipt__isnull=False,
                supplier_payment__isnull=True,
            ).values("sales_invoice_id").annotate(
                d=Sum(
                    ExpressionWrapper(
                        F("receipt__settlement_discount") * F("amount") / receipt_alloc_total,
                        output_field=money,
                    )
                )
            ).values("d")[:1],
            output_field=money,
        ),
        Value(0, output_field=money),
    )
    tcs_extra = Case(
        When(tcs_in_grand_total=False, then=F("tcs_amount")),
        default=Value(0),
        output_field=money,
    )
    qs = qs.annotate(_cn=cn, _dn=dn, _live_alloc=alloc, _settle=discount_share).annotate(
        _balance_raw=ExpressionWrapper(
            F("grand_total") + tcs_extra - F("_cn") + F("_dn") - F("_live_alloc") - F("_settle"),
            output_field=money,
        )
    )
    return qs.annotate(
        _balance=Case(
            When(_balance_raw__gt=0, then=F("_balance_raw")),
            default=Value(0),
            output_field=money,
        )
    )


def live_settlement_parts(invoice):
    """(live allocations, credit notes, settlement discount) for one invoice, read fresh."""
    row = (
        annotate_live_settlement(SalesInvoice.objects.filter(pk=invoice.pk))
        .values_list("_live_alloc", "_cn", "_settle")
        .first()
    )
    return row or (0, 0, 0)


def live_settlement_parts_bulk(invoice_ids):
    """{invoice id: (live allocations, credit notes, settlement discount)} in one query."""
    rows = (
        annotate_live_settlement(SalesInvoice.objects.filter(pk__in=list(invoice_ids)))
        .values_list("pk", "_live_alloc", "_cn", "_settle")
    )
    return {pk: (alloc, notes, discount) for pk, alloc, notes, discount in rows}
