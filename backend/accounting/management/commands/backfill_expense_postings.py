"""ACS-15: post the expenses that should already be in the books (dated on/after expense_gl_start_date)."""

from django.core.management.base import BaseCommand, CommandError

from accounting.expense_posting import pending_summary, post_pending_expenses
from accounts.models import Company
from core.rls import rls_bypass


class Command(BaseCommand):
    help = (
        "Post active expenses dated on or after the company's expense_gl_start_date that have no "
        "journal entry yet. Safe to run again. A closed month is reported, not forced."
    )

    def add_arguments(self, parser):
        parser.add_argument("--company", type=int, required=True, help="Company id.")
        parser.add_argument("--dry-run", action="store_true", help="Report what would post; write nothing.")

    def handle(self, *args, **options):
        with rls_bypass():
            company = Company.objects.filter(pk=options["company"]).first()
            if company is None:
                raise CommandError(f"Company {options['company']} not found.")
            if not company.accounting_enabled or not company.expense_gl_start_date:
                raise CommandError(
                    "Set the expense ledger start date (accounting on) before back-filling expenses."
                )
            summary = pending_summary(company)
            self.stdout.write(f"Pending: {summary['count']} expense(s), total {summary['total']}.")
            result = post_pending_expenses(company, user=None, dry_run=options["dry_run"])
            if not options["dry_run"]:
                from core.repair import record_repair

                record_repair(
                    command="backfill_expense_postings", company=company, stdout=self.stdout,
                    summary={"posted": result["posted"], "total": result["total"], "skipped": len(result["skipped"])},
                )
        verb = "Would post" if options["dry_run"] else "Posted"
        self.stdout.write(self.style.SUCCESS(f"{verb} {result['posted']} expense(s), total {result['total']}."))
        for row in result["skipped"]:
            self.stdout.write(self.style.WARNING(f"Skipped {row['number'] or row['id']}: {row['reason']}"))
