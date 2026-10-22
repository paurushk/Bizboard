"""WP-F2 / DIM6-05: switch an existing books-off company to shadow books.

Migration ``accounts/0068`` left existing books-off companies that already had history with
``post_ledger`` off, because their past documents were never posted. This command catches one
company up and turns shadow posting on:

    python manage.py enable_shadow_books --company 42           # dry run: what the back-fill would post
    python manage.py enable_shadow_books --company 42 --apply   # post it, turn posting on, check the books

``--apply`` turns ``post_ledger`` on first (so the back-fill posts), runs both back-fills for the
company, then the full books check. If the check fails the company stays on (new documents must
post) and the failing checks are printed: follow docs/ops/LEDGER_REPAIR_RUNBOOK.md.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Back-fill one books-off company's history and turn shadow posting (post_ledger) on."

    def add_arguments(self, parser):
        parser.add_argument("--company", type=int, required=True)
        parser.add_argument("--apply", action="store_true", help="Post and turn on (default is a dry run).")

    def handle(self, *args, **opts):
        from accounting.management.commands.backfill_accounting_postings import Command as Backfill
        from accounting.management.commands.backfill_missing_postings import Command as BackfillMissing
        from accounting.services import seed_chart_of_accounts
        from accounts.models import Company
        from core import sweep
        from core.rls import rls_bypass, set_rls_company

        with rls_bypass():
            company = Company.objects.filter(pk=opts["company"]).first()
        if company is None:
            raise CommandError(f"Company {opts['company']} not found.")
        if company.post_ledger:
            self.stdout.write(f"Company {company.pk} already posts to the ledger (post_ledger on). Nothing to do.")
            return
        if not opts["apply"]:
            # Count what the back-fills would post, as if posting were on, without saving anything.
            company.post_ledger = True
            with rls_bypass():
                _p, _s, would = Backfill()._backfill_company(company, dry_run=True)
                _p2, _s2, would2 = BackfillMissing()._backfill_company(company, dry_run=True)
            self.stdout.write(
                f"Dry run for company {company.pk}: the back-fill would post {would + would2} document(s). "
                "Nothing changed. Re-run with --apply."
            )
            return
        with rls_bypass():
            company.post_ledger = True
            company.save(update_fields=["post_ledger", "updated_at"])
            seed_chart_of_accounts(company)
        call_command("backfill_accounting_postings", company=company.pk, stdout=self.stdout)
        call_command("backfill_missing_postings", company=company.pk, stdout=self.stdout)
        set_rls_company(company.pk)
        try:
            row = sweep.sweep_company(company.pk, sweep.new_run_id(), force_full=True)
        finally:
            set_rls_company(None)
        status = getattr(row, "status", "UNKNOWN")
        detail = ", ".join(getattr(row, "failing_keys", []) or []) or getattr(row, "error", "")
        self.stdout.write(f"Company {company.pk}: shadow books on; books check {status} {detail}".rstrip())
        if status != "CLEAN":
            self.stdout.write("Follow docs/ops/LEDGER_REPAIR_RUNBOOK.md for the failing checks.")
