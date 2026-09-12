"""QOS-0022 — standalone invariant sweep over every company in the current DB.

Unlike the pytest-driven `INVARIANTS_STRICT=1` sweep (which asserts invariants
as tests execute, inside pytest's own fixtures), this runs `assert_all_invariants`
directly against whatever companies already exist in the connected database —
the shape a restore-drill needs: restore a real backup dump into a scratch DB,
then point this command at it, with no pytest fixtures involved.

    python manage.py check_invariants

Exits non-zero (and lists every failure) if any company fails any invariant,
so it composes as a CI/cron gate: `check_invariants || alert`.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from accounts.models import Company
from core.invariants import InvariantViolation, run_invariants
from core.rls import rls_bypass


class Command(BaseCommand):
    help = "Run the invariant sweep against every company in the connected database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--company", type=int, default=None,
            help="Check a single company id instead of every company.",
        )

    def handle(self, *args, **options):
        with rls_bypass():
            companies = (
                Company.objects.filter(pk=options["company"])
                if options["company"]
                else Company.objects.all()
            )
            companies = list(companies.only("id", "name"))

        if not companies:
            self.stdout.write(self.style.WARNING("No companies found — nothing to check."))
            return

        all_failures: dict[str, list[str]] = {}
        for company in companies:
            with rls_bypass():
                failures = run_invariants(company)
            if failures:
                self.stdout.write(self.style.ERROR(f"FAIL  company={company.id} ({company.name})"))
                for name, msgs in failures.items():
                    self.stdout.write(f"        [{name}]")
                    for m in msgs:
                        self.stdout.write(f"          - {m}")
                    all_failures[f"company {company.id} :: {name}"] = msgs
            else:
                self.stdout.write(self.style.SUCCESS(f"ok    company={company.id} ({company.name})"))

        self.stdout.write("")
        if all_failures:
            raise InvariantViolation(None, all_failures)
        self.stdout.write(self.style.SUCCESS(f"All {len(companies)} company(ies) clean."))
