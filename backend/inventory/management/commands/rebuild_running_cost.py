from calendar import monthrange
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Company
from inventory.services import InventoryService, InventoryValuationService


class Command(BaseCommand):
    help = (
        "Replay StockMovement into InventoryRunningCost (insert order). "
        "Fails if qty drifts from StockBalance. Optional month-end snapshots "
        "for historical as_of above 10,000 movements."
    )

    def add_arguments(self, parser):
        parser.add_argument("--company", type=int, help="Limit to a company id.")
        parser.add_argument(
            "--write-snapshots",
            action="store_true",
            help="Also write month-end InventoryValuationSnapshot rows.",
        )
        parser.add_argument(
            "--period",
            type=str,
            help="Snapshot period YYYY-MM (default: previous calendar month).",
        )

    def handle(self, *args, **options):
        companies = Company.objects.all().order_by("id")
        if options["company"]:
            companies = companies.filter(pk=options["company"])
            if not companies.exists():
                raise CommandError(f"Company {options['company']} not found.")
        period = options.get("period")
        if options["write_snapshots"] and not period:
            today = timezone.localdate()
            prev = today.replace(day=1) - timedelta(days=1)
            period = f"{prev.year:04d}-{prev.month:02d}"
        if period:
            try:
                year, month = (int(p) for p in period.split("-")[:2])
                date(year, month, 1)
                date(year, month, monthrange(year, month)[1])
            except (TypeError, ValueError):
                raise CommandError("period must be YYYY-MM.") from None

        total_rows = 0
        for company in companies.iterator():
            with transaction.atomic():
                n = InventoryService.rebuild_running_cost(company)
            total_rows += n
            self.stdout.write(f"company {company.pk}: {n} running-cost rows")
            if options["write_snapshots"]:
                snaps = InventoryValuationService.write_month_end_snapshot(company, period)
                self.stdout.write(f"company {company.pk}: {snaps} snapshot rows for {period}")

        self.stdout.write(self.style.SUCCESS(f"Rebuilt running cost for {companies.count()} company(ies)."))
