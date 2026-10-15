"""Report supplier payments the old three-call pay-at-entry flow may have left unallocated.

Before pay-at-entry became one transaction, the bill editor created the payment and then its
allocation as separate calls; a failure in between left a posted payment with an "Against <bill>"
note and nothing allocated. This command only *lists* them (read-only) so an owner can decide
whether to allocate each one on the Supplier Payments screen.

    manage.py report_orphan_purchase_payments [--company ID] [--csv path]
"""

import csv
import sys
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum

from payments.models import SupplierPayment, SupplierPaymentStatus


def orphan_payments(company_id=None):
    """Posted supplier payments noted "Against ..." that still carry an unallocated amount."""
    qs = SupplierPayment.objects.filter(
        status=SupplierPaymentStatus.POSTED, notes__startswith="Against "
    ).select_related("supplier")
    if company_id:
        qs = qs.filter(company_id=company_id)
    rows = []
    for pay in qs.order_by("company_id", "id"):
        allocated = pay.allocations.filter(reversed_at__isnull=True).aggregate(t=Sum("amount"))["t"] or Decimal("0")
        unallocated = Decimal(str(pay.amount)) + Decimal(str(pay.tds_amount or 0)) - allocated
        if unallocated > 0:
            rows.append((pay, allocated, unallocated))
    return rows


class Command(BaseCommand):
    help = "List posted 'Against <bill>' supplier payments with an unallocated remainder (read-only)."

    def add_arguments(self, parser):
        parser.add_argument("--company", type=int, default=None)
        parser.add_argument("--csv", default="", help="Write the rows to this CSV file instead of stdout.")

    def handle(self, *args, **options):
        rows = orphan_payments(options["company"])
        out = open(options["csv"], "w", newline="", encoding="utf8") if options["csv"] else sys.stdout
        try:
            writer = csv.writer(out)
            writer.writerow(["company", "payment_id", "number", "supplier", "date", "amount", "allocated", "unallocated", "notes"])
            for pay, allocated, unallocated in rows:
                writer.writerow([
                    pay.company_id, pay.pk, pay.number, pay.supplier.name, pay.payment_date,
                    pay.amount, allocated, unallocated, pay.notes,
                ])
        finally:
            if options["csv"]:
                out.close()
        self.stderr.write(f"{len(rows)} payment(s) with an unallocated remainder.")
