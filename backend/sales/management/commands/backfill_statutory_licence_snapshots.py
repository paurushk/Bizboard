"""SET-03: freeze the statutory licences onto invoices issued before snapshots existed.

Safe to re-run: it only touches invoices whose snapshot is still NULL, in id order, in batches, so
a stopped run resumes where it left off. It writes with ``update()``, so it does not change
``updated_at``, run signals or touch the document in any other way. Drafts are skipped; they
capture the set when they complete.

For each invoice the licences are those valid on the invoice date (see
``sales.statutory_snapshot.licences_valid_on``, historical mode). An invoice with no licence
evidence gets an empty snapshot, which is a real answer ("none then"), and is counted in the report.
"""

from django.core.management.base import BaseCommand

from sales.models import SalesInvoice
from sales.statutory_snapshot import invoice_state_code, licences_valid_on, lock_licences


class Command(BaseCommand):
    help = "Backfill statutory_licences_snapshot on completed, cancelled and returned invoices."

    def add_arguments(self, parser):
        parser.add_argument("--company", type=int, help="Only this company id.")
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--dry-run", action="store_true", help="Count and report; write nothing.")

    def handle(self, *args, company=None, batch_size=500, dry_run=False, **options):
        qs = SalesInvoice.objects.filter(statutory_licences_snapshot__isnull=True).exclude(
            status=SalesInvoice.Status.DRAFT
        )
        if company:
            qs = qs.filter(company_id=company)
        total = with_licences = empty = 0
        last_id = 0
        # (company, date, state) repeats a lot; look each combination up once per run.
        cache: dict = {}
        while True:
            batch = list(
                qs.filter(pk__gt=last_id)
                .select_related("company", "company_gstin")
                .order_by("pk")[: max(1, batch_size)]
            )
            if not batch:
                break
            for invoice in batch:
                state = invoice_state_code(invoice)
                key = (invoice.company_id, invoice.invoice_date, state)
                if key not in cache:
                    cache[key] = licences_valid_on(
                        invoice.company, invoice.invoice_date, historical=True, state_code=state
                    )
                rows = cache[key]
                total += 1
                if rows:
                    with_licences += 1
                else:
                    empty += 1
                if not dry_run:
                    SalesInvoice.objects.filter(pk=invoice.pk, statutory_licences_snapshot__isnull=True).update(
                        statutory_licences_snapshot=rows
                    )
                    lock_licences(rows)
                last_id = invoice.pk
        verb = "Would snapshot" if dry_run else "Snapshotted"
        self.stdout.write(
            f"{verb} {total} invoice(s): {with_licences} with licence(s), {empty} with none on the invoice date."
        )
