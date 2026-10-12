"""Quick Order Entry pilot metrics, read from the audit trail (QOE-15).

The insights event list is a database enum, so Quick Entry does not add telemetry events. Every document it creates
carries ``metadata.source = "quick_entry"`` in its CREATE audit event; this command turns that into the pilot numbers:
how many documents, order-versus-bill share, how many orders are still drafts, and per-rep volume. Read-only.
"""

from collections import Counter
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import AuditEvent
from sales.models import SalesOrder


class Command(BaseCommand):
    help = "Report Quick Entry volume, order-vs-bill share, draft orders and per-rep counts from audit events."

    def add_arguments(self, parser):
        parser.add_argument("--company", type=int, help="Limit to a company id.")
        parser.add_argument("--days", type=int, default=14, help="Look-back window (default 14).")

    def handle(self, *args, **options):
        since = timezone.now() - timedelta(days=options["days"])
        events = AuditEvent.objects.filter(
            action=AuditEvent.Action.CREATE,
            entity_type__in=("SalesOrder", "SalesInvoice"),
            created_at__gte=since,
            metadata__source="quick_entry",
        )
        if options.get("company"):
            events = events.filter(company_id=options["company"])

        orders = [e for e in events if e.entity_type == "SalesOrder"]
        bills = [e for e in events if e.entity_type == "SalesInvoice"]
        total = len(orders) + len(bills)
        self.stdout.write(f"Quick Entry documents in the last {options['days']} days: {total}")
        if total:
            self.stdout.write(f"  sales orders: {len(orders)} ({100 * len(orders) // total}%)")
            self.stdout.write(f"  draft bills:  {len(bills)} ({100 * len(bills) // total}%)")

        order_ids = [int(e.entity_id) for e in orders if str(e.entity_id).isdigit()]
        statuses = Counter(SalesOrder.objects.filter(pk__in=order_ids).values_list("status", flat=True))
        if order_ids:
            still_draft = statuses.get(SalesOrder.Status.DRAFT, 0)
            self.stdout.write(
                f"  orders still DRAFT: {still_draft} of {len(order_ids)} "
                f"(auto-confirm held back or not enabled)"
            )
            for status, count in sorted(statuses.items()):
                self.stdout.write(f"    {status}: {count}")

        per_rep = Counter(e.user_id for e in events)
        for user_id, count in per_rep.most_common(10):
            self.stdout.write(f"  user {user_id}: {count}")
