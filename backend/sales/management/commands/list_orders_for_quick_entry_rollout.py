"""Read-only ops report to run before enabling the Quick Entry order-mode flags (QOE-12a / QOE-15).

Lists open sales orders that
  * have no delivery address (a delivery-route stop would be blank), and
  * belong to a customer who is now blocked/inactive (confirming them now fails with ``customer_not_active``).
Nothing is changed.
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from masters.models import Customer
from sales.models import SalesOrder


class Command(BaseCommand):
    help = "List open sales orders with no delivery address or with a blocked/inactive customer."

    def add_arguments(self, parser):
        parser.add_argument("--company", type=int, help="Limit to a company id.")

    def handle(self, *args, **options):
        open_orders = SalesOrder.objects.filter(
            status__in=(SalesOrder.Status.DRAFT, SalesOrder.Status.CONFIRMED)
        ).select_related("customer")
        if options.get("company"):
            open_orders = open_orders.filter(company_id=options["company"])

        blank = open_orders.filter(Q(delivery_address="") | Q(delivery_address__isnull=True))
        blocked = open_orders.exclude(customer__status=Customer.Status.ACTIVE)

        self.stdout.write(self.style.WARNING(f"No delivery address: {blank.count()}"))
        for order in blank.order_by("company_id", "id")[:100]:
            self.stdout.write(f"  company {order.company_id} order {order.number or order.pk} ({order.customer.name})")
        self.stdout.write(self.style.WARNING(f"Customer blocked/inactive: {blocked.count()}"))
        for order in blocked.order_by("company_id", "id")[:100]:
            self.stdout.write(
                f"  company {order.company_id} order {order.number or order.pk} "
                f"({order.customer.name}, {order.customer.status}, {order.status})"
            )
