"""Read-only ops report to run before enabling ``ENABLE_ORDER_GATES`` (DEC-3 / T-1.3).

Credit exposure now counts goods that have shipped on a completed delivery challan but are not yet on a counted
invoice. This lists, per customer, how much that adds and whether it takes them over their credit limit, so the
owner knows who will start seeing credit warnings. Nothing is changed.
"""

from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand

from sales.models import DeliveryChallan, SalesOrder
from sales.order_gates import _shipped_unbilled_value
from sales.status_semantics import OPEN_RECEIVABLE_STATUSES


def affected_customers(company_id=None):
    """Rows of (company_id, customer, shipped_unbilled, credit_limit), largest first."""
    challans = DeliveryChallan.objects.filter(status=DeliveryChallan.Status.COMPLETED).select_related("customer")
    if company_id:
        challans = challans.filter(company_id=company_id)
    pairs = {(c.company_id, c.customer_id): c.customer for c in challans}
    live_orders: dict[tuple[int, int], set[int]] = defaultdict(set)
    orders = SalesOrder.objects.filter(
        status__in=(SalesOrder.Status.CONFIRMED, SalesOrder.Status.PARTIALLY_CONVERTED)
    ).values_list("company_id", "customer_id", "pk")
    for company, customer, pk in orders:
        live_orders[(company, customer)].add(pk)
    rows = []
    for (company, customer_id), customer in pairs.items():
        value = _shipped_unbilled_value(company, customer, live_orders.get((company, customer_id), set()), OPEN_RECEIVABLE_STATUSES)
        if value > Decimal("0"):
            rows.append((company, customer, value, customer.credit_limit or Decimal("0")))
    return sorted(rows, key=lambda r: r[2], reverse=True)


class Command(BaseCommand):
    help = "List customers whose credit exposure rises because shipped challans are not yet invoiced."

    def add_arguments(self, parser):
        parser.add_argument("--company", type=int, help="Limit to a company id.")

    def handle(self, *args, **options):
        rows = affected_customers(options.get("company"))
        self.stdout.write(self.style.WARNING(f"Customers with shipped, uninvoiced challans: {len(rows)}"))
        for company, customer, value, limit in rows:
            note = "  (has no credit limit)" if limit <= 0 else ""
            self.stdout.write(f"  company {company} {customer.name}: +{value}  credit limit {limit}{note}")
