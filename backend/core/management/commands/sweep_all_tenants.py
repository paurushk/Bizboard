"""WP-E1: run the books check for every company (or one), the same check the nightly job runs.

Default queues one Celery task per company. ``--sync`` runs in this process and prints a
per-company table (restore drill, cutover, CI migration gate). ``--fail-on-any`` exits
non-zero when any company FAILED or hit an ERROR.

    python manage.py sweep_all_tenants --sync --full --fail-on-any
    python manage.py sweep_all_tenants --company 42 --sync
"""

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Run the nightly books check (invariants) per company and record TenantSweepResult rows."

    def add_arguments(self, parser):
        parser.add_argument("--company", type=int, help="Only this company id.")
        parser.add_argument("--full", action="store_true", help="Check even companies with no changes.")
        parser.add_argument("--sync", action="store_true", help="Run here instead of queueing tasks.")
        parser.add_argument("--fail-on-any", action="store_true", help="Exit 1 if any company fails.")

    def handle(self, *args, **opts):
        from core import sweep
        from core.rls import set_rls_company
        from core.tasks import sweep_company_task

        ids = [opts["company"]] if opts.get("company") else sweep.all_company_ids()
        run_id = sweep.new_run_id()
        if not opts["sync"]:
            for pk in ids:
                sweep_company_task.delay(company_id=pk, run_id=run_id, force_full=opts["full"])
            self.stdout.write(f"queued {len(ids)} companies run_id={run_id}")
            return
        bad = []
        for pk in ids:
            set_rls_company(pk)
            try:
                row = sweep.sweep_company(pk, run_id, force_full=opts["full"])
            finally:
                set_rls_company(None)
            if row is None:
                continue
            detail = ", ".join(row.failing_keys) or row.error
            self.stdout.write(f"{row.status:8} company={pk} {row.duration_ms}ms {detail}".rstrip())
            if row.status in ("FAILED", "ERROR"):
                bad.append(pk)
        self.stdout.write(f"run_id={run_id} companies={len(ids)} failed={len(bad)}")
        if bad and opts["fail_on_any"]:
            raise CommandError(f"books check failed for companies: {bad}")
