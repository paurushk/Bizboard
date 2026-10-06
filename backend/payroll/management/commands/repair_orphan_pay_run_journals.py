"""List pay runs that are not completed but still have a posted payroll journal.

With books on and --apply, reverse those journals. Do not re-complete the run.
With books off, print the ids and exit. Reverse while books are off would mark
the journal REVERSED and store no reversal lines.
"""

from django.core.management.base import BaseCommand

from accounting.models import JournalEntry
from accounting.services import PostingService
from core.rls import rls_bypass
from payroll.models import PayRun


class Command(BaseCommand):
    help = (
        "List non-completed pay runs that still have a posted PAYROLL journal. "
        "--apply reverses them only when that company's books are on."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Reverse posted journals for companies whose books are on.",
        )

    def handle(self, *args, **options):
        apply = bool(options["apply"])
        with rls_bypass():
            posted = JournalEntry.objects.filter(
                source_type="PAY_RUN",
                purpose="PAYROLL",
                status=JournalEntry.Status.POSTED,
            ).select_related("company")
            runs = []
            for entry in posted:
                run = PayRun.objects.filter(pk=entry.source_id, company=entry.company).first()
                if run is None or run.status == PayRun.Status.COMPLETED:
                    continue
                runs.append((run, entry))
            if not runs:
                self.stdout.write("No orphan payroll journals.")
                return
            blocked = False
            for run, entry in runs:
                line_bits = []
                for line in entry.lines.select_related("account"):
                    line_bits.append(
                        f"{line.account.code} dr={line.debit} cr={line.credit}"
                    )
                self.stdout.write(
                    f"company={run.company_id} pay_run={run.pk} period={run.period} "
                    f"status={run.status} journal={entry.pk} books={run.company.accounting_enabled} "
                    f"lines=[{'; '.join(line_bits)}]"
                )
                if not run.company.accounting_enabled:
                    blocked = True
                    continue
                if apply:
                    PostingService.reverse(entry, user=None)
                    self.stdout.write(f"reversed journal={entry.pk}")
            if blocked and apply:
                self.stdout.write(
                    "Books are off for at least one company. Those journals were not reversed."
                )
