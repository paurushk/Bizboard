"""ACS-40: find (and optionally fix) bank statement lines whose match state is inconsistent.

Default is a report only. ``--fix`` repairs what is unambiguous (a line linked but not marked
matched, or marked matched with nothing behind it). A line matched in both engines is only
settled when you choose ``--prefer gl`` or ``--prefer payments``.
"""
from django.db.models import Q
from django.core.management.base import BaseCommand

from accounting import bank_match
from accounts.models import Company


class Command(BaseCommand):
    help = "Report or repair inconsistent bank statement match state."

    def add_arguments(self, parser):
        parser.add_argument("--company", type=int, help="Company id; default all companies with accounting on.")
        parser.add_argument("--fix", action="store_true", help="Apply the unambiguous repairs.")
        parser.add_argument("--prefer", choices=["gl", "payments"], help="Which match to keep when both exist.")

    def handle(self, *args, **options):
        # WP-F2: shadow-books companies post to the ledger too.
        companies = Company.objects.filter(Q(accounting_enabled=True) | Q(post_ledger=True))
        if options.get("company"):
            companies = companies.filter(pk=options["company"])
        total = 0
        for company in companies:
            found = bank_match.inconsistent_lines(company)
            total += len(found)
            for item in found:
                self.stdout.write(f"company {company.pk} line {item['line']}: {item['problem']} ({item['fix']})")
            if options["fix"] and found:
                result = bank_match.repair(company, prefer=options.get("prefer"))
                self.stdout.write(f"company {company.pk}: {result}")
                from core.repair import record_repair

                record_repair(
                    command="repair_bank_match_state", company=company, stdout=self.stdout,
                    summary={"lines": len(found), "prefer": options.get("prefer") or "", "result": result},
                )
        self.stdout.write(f"{total} inconsistent line(s) found." + ("" if options["fix"] else " Re-run with --fix to repair."))
