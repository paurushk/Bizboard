"""Report (and optionally repair) customer rows that would trip the stricter master rules (CUS-22).

``--fix`` only repairs what is unambiguous: a verification status that no longer describes the stored GSTIN.
The same check runs monthly as ``masters.tasks.customers_audit_task``.
"""

from django.core.management.base import BaseCommand

from masters.audit import audit_customers
from masters.models import Customer


class Command(BaseCommand):
    help = "Audit customers for stale GSTIN verification, state/GSTIN mismatches, duplicate GSTINs and walk-in anomalies."

    def add_arguments(self, parser):
        parser.add_argument("--company", type=int, help="Limit to a company id.")
        parser.add_argument("--fix", action="store_true", help="Reset verification that no longer matches the GSTIN.")
        parser.add_argument("--fail-on-findings", action="store_true", help="Exit non-zero when anything is found.")

    def handle(self, *args, **options):
        qs = Customer.objects.all()
        if options.get("company"):
            qs = qs.filter(company_id=options["company"])
        findings, companies, fixed = audit_customers(qs, fix=options["fix"])
        total = 0
        for (company_id, check), rows in sorted(findings.items()):
            total += len(rows)
            self.stdout.write(self.style.WARNING(f"company {company_id}: {check} ({len(rows)})"))
            for pk, detail in rows[:50]:
                self.stdout.write(f"  customer {pk}: {detail}")
            if len(rows) > 50:
                self.stdout.write(f"  ... {len(rows) - 50} more")
        self.stdout.write(self.style.SUCCESS(
            f"{len(companies)} compan{'y' if len(companies) == 1 else 'ies'} checked, {total} finding(s)"
            + (f", {fixed} repaired" if options["fix"] else "")
        ))
        if options["fail_on_findings"] and total:
            raise SystemExit(1)
