"""Weekly per-tenant pilot counters. Staff tooling: run from manage.py or admin.

Prints a markdown table. A blank cell means the source is not instrumented.
It is not a zero.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef
from django.db.models.functions import TruncDate
from django.utils import timezone

from accounts.models import Company
from insights.models import ShopFloorEvent
from sales.models import SalesInvoice
from support.models import Ticket


class Command(BaseCommand):
    help = "Print the weekly pilot metric table. Does not invent missing sources."

    def handle(self, *args, **options):
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        lines = [
            "| Tenant | First invoice (h) | Active days (7d) | Invoices without a prior ticket | Tickets (7d) | Mismatch tickets (7d) | 5xx per 1k |",
            "|---|---|---|---|---|---|---|",
        ]
        for company in Company.objects.order_by("id"):
            first = (
                SalesInvoice.objects.filter(company=company, status=SalesInvoice.Status.COMPLETED)
                .order_by("completed_at")
                .values_list("completed_at", flat=True)
                .first()
            )
            if first and company.created_at:
                hours = f"{(first - company.created_at).total_seconds() / 3600:.1f}"
            else:
                hours = "—"
            active_days = (
                SalesInvoice.objects.filter(
                    company=company,
                    status=SalesInvoice.Status.COMPLETED,
                    completed_at__gte=week_ago,
                )
                .annotate(day=TruncDate("completed_at"))
                .values("day")
                .distinct()
                .count()
            )
            prior_ticket = Ticket.objects.filter(
                company_id=OuterRef("company_id"),
                created_at__gte=OuterRef("completed_at") - timedelta(hours=24),
                created_at__lt=OuterRef("completed_at"),
            )
            unaided = (
                SalesInvoice.objects.filter(
                    company=company,
                    status=SalesInvoice.Status.COMPLETED,
                    completed_at__gte=week_ago,
                )
                .annotate(had_ticket=Exists(prior_ticket))
                .filter(had_ticket=False)
                .count()
            )
            tickets = Ticket.objects.filter(company=company, created_at__gte=week_ago).count()
            mismatches = Ticket.objects.filter(
                company=company,
                created_at__gte=week_ago,
                category=Ticket.Category.NUMBER_MISMATCH,
            ).count()
            lines.append(
                f"| {company.name} | {hours} | {active_days} | {unaided} | {tickets} | {mismatches} | not instrumented |"
            )
        lines.append("")
        lines.append(
            "5xx per 1k requests is not instrumented (no request log). Do not read the blank as zero."
        )
        event_count = ShopFloorEvent.objects.filter(created_at__gte=week_ago).count()
        lines.append(f"Shop-floor events in the last 7 days: {event_count}.")
        self.stdout.write("\n".join(lines))
