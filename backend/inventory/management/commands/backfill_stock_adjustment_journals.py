"""Post the journals that stock adjustments, count differences, expiry write-offs and serial scrap
should have posted (INV-WP-12).

Until a company opts in (``ACCOUNTING_POST_STOCK_ADJUSTMENTS``) these stock writes change the stock
valuation but not the books, so the balance sheet's inventory (GL 1400) drifts from the stock
value. Turn the flag on, then run this to catch up the past.

Default is a dry run that lists what would be posted. Pass ``--apply`` to post. A movement in a
closed period, or dated before the books start, is reported and left alone so the rest still post.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_date

from accounting.models import JournalEntry
from accounting.services import PostingService
from accounts.models import Company
from core.exceptions import BusinessRuleError
from core.services.feature_flags import flag_enabled
from inventory.models import MovementType, StockMovement


class Command(BaseCommand):
    help = "Post missing journals for stock adjustments, counts, expiry write-offs and serial scrap."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--from", dest="date_from", help="First movement date (YYYY-MM-DD).")
        parser.add_argument("--to", dest="date_to", help="Last movement date (YYYY-MM-DD).")
        parser.add_argument("--apply", action="store_true", help="Post the journals (default is a dry run).")

    def handle(self, *args, **options):
        try:
            company = Company.objects.get(pk=options["company_id"])
        except Company.DoesNotExist as exc:
            raise CommandError("No such company.") from exc
        if not company.accounting_enabled:
            raise CommandError("Accounting is not enabled for this company.")
        if not flag_enabled(company, "ACCOUNTING_POST_STOCK_ADJUSTMENTS"):
            raise CommandError(
                "Turn on ACCOUNTING_POST_STOCK_ADJUSTMENTS for this company first. "
                "Otherwise new stock writes keep missing the books while this catches up the old ones."
            )
        apply = options["apply"]
        qs = StockMovement.objects.filter(
            company=company,
            movement_type=MovementType.ADJUSTMENT,
            reference_type__in=list(PostingService.STOCK_WRITE_PURPOSES),
        ).select_related("product").order_by("movement_date", "id")
        if options.get("date_from"):
            qs = qs.filter(movement_date__gte=parse_date(options["date_from"]))
        if options.get("date_to"):
            qs = qs.filter(movement_date__lte=parse_date(options["date_to"]))

        posted_for = set(
            JournalEntry.objects.filter(
                company=company, source_type="STOCK_MOVEMENT", status=JournalEntry.Status.POSTED,
            ).values_list("source_id", flat=True)
        )
        todo = [m for m in qs if m.pk not in posted_for]
        loss = gain = Decimal("0")
        posted = skipped = 0
        for movement in todo:
            amount = abs(Decimal(str(movement.quantity or 0))) * PostingService._stock_movement_cost(movement)
            if Decimal(str(movement.quantity)) < 0:
                loss += amount
            else:
                gain += amount
            if not apply:
                continue
            try:
                with transaction.atomic():
                    entry = PostingService.post_stock_adjustment(movement, None)
                if entry is not None:
                    posted += 1
            except BusinessRuleError as exc:
                skipped += 1
                self.stderr.write(f"  movement {movement.pk} ({movement.movement_date}): {exc}")
        self.stdout.write(
            f"{len(todo)} stock write(s) have no journal: losses {loss:.2f}, gains {gain:.2f}."
        )
        if apply:
            self.stdout.write(f"Posted {posted}; left alone {skipped}.")
        else:
            self.stdout.write("Dry run. Nothing posted. Add --apply to post.")
