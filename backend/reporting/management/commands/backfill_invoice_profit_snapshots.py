"""One-off backfill: InvoiceProfitSnapshot rows for invoices completed before
this feature existed.

Re-derives COGS read-only from existing StockMovement rows via
CogsService.invoice_sale_moves — never re-runs post_sale_stock_and_cogs,
which would post new stock movements. Historical cost_basis classification
is a coarser best-effort guess since the live per-tier resolution signal
(FIFO vs valuation-fallback vs purchase-price-fallback) wasn't captured when
these invoices were originally posted; rows are marked is_backfilled=True
so the UI can badge them distinctly from live-computed ones.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from accounts.models import Company
from core.rls import rls_bypass
from reporting.invoice_profit_service import InvoiceProfitService
from sales.cogs_service import CogsService
from sales.models import SalesInvoice
from sales.status_semantics import PROFIT_SNAPSHOT_STATUSES

CHUNK = 500


def _chunked(qs, *, chunk_size=CHUNK):
    last_pk = 0
    qs = qs.order_by("pk")
    while True:
        batch = list(qs.filter(pk__gt=last_pk)[:chunk_size])
        if not batch:
            return
        last_pk = batch[-1].pk
        yield batch


def _backfill_counts(invoice) -> tuple[Decimal, dict]:
    moves = CogsService.invoice_sale_moves(invoice)
    cogs_total = Decimal("0")
    counts = {"lines": len(moves)}
    for move in moves:
        unit_cost = Decimal(str(move.unit_cost or 0))
        quantity = abs(Decimal(str(move.quantity or 0)))
        cogs_total += unit_cost * quantity
        key = "fifo" if unit_cost else "zero_cost"
        counts[key] = counts.get(key, 0) + 1
    return cogs_total, counts


class Command(BaseCommand):
    help = (
        "Backfill InvoiceProfitSnapshot rows for SalesInvoices completed before this "
        "feature existed. Read-only against inventory. Use --dry-run first, then --company=N."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--company", type=int, help="Company id (required unless --dry-run).")
        parser.add_argument(
            "--force", action="store_true",
            help="Recompute and overwrite invoices that already have a snapshot.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options["dry_run"])
        force = bool(options["force"])
        company_id = options.get("company")
        if not dry_run and not company_id:
            raise CommandError("Pass --company=N to write, or --dry-run to scan.")

        with rls_bypass():
            companies = Company.objects.all()
            if company_id:
                companies = companies.filter(pk=company_id)
            created = 0
            skipped_has_snapshot = 0
            skipped_no_moves = 0
            for company in companies.iterator():
                c, s_has, s_none = self._backfill_company(company, dry_run=dry_run, force=force)
                created += c
                skipped_has_snapshot += s_has
                skipped_no_moves += s_none
                self.stdout.write(
                    f"Company {company.id}: "
                    f"{'would_create' if dry_run else 'created'}={c} "
                    f"skipped_has_snapshot={s_has} skipped_no_moves={s_none}"
                )
        verb = "Dry-run: would create" if dry_run else "Backfill created"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {created} snapshot(s); "
            f"{skipped_has_snapshot} already had one, {skipped_no_moves} had no stock movements."
        ))

    def _backfill_company(self, company, *, dry_run: bool, force: bool) -> tuple[int, int, int]:
        created = skipped_has_snapshot = skipped_no_moves = 0
        qs = SalesInvoice.objects.filter(
            company=company,
            status__in=PROFIT_SNAPSHOT_STATUSES,
        )
        if not force:
            qs = qs.filter(profit_snapshot__isnull=True)
        for batch in _chunked(qs):
            for invoice in batch:
                # `qs` is already filtered to profit_snapshot__isnull=True
                # when not force (above), so a per-row exists() check here
                # was always False -- one redundant query per invoice on top
                # of the batched fetch, purely wasted on a backfill that's
                # already I/O heavy.
                cogs_total, counts = _backfill_counts(invoice)
                if not counts.get("lines"):
                    # No stock movements at all -- either a pure-service invoice
                    # (correctly NO_COGS) or a tally-opening import that never
                    # posted COGS in the first place. Either way there is
                    # nothing to derive, so skip rather than write a
                    # zero-everything row that looks like a real ₹0 sale.
                    skipped_no_moves += 1
                    continue
                created += 1
                if dry_run:
                    continue
                InvoiceProfitService.write_snapshot(
                    invoice, cogs_total, counts, user=None, is_backfilled=True
                )
        return created, skipped_has_snapshot, skipped_no_moves
