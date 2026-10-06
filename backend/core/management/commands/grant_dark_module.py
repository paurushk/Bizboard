"""Dry-run pack grants for CRM and manufacturing. Payroll is refused.

The company-JSON fallback for dark modules stays until an operator attaches
this command's dry-run output to the follow-up that removes it. This command
does not remove that fallback.
"""

from django.core.management.base import BaseCommand, CommandError

from accounts.models import Company
from core.rls import rls_bypass
from core.services.feature_flags import build_feature_flags


class Command(BaseCommand):
    help = (
        "Print effective flags before and after a pack grant. "
        "--apply writes insurance or manufacturing. Payroll is refused. "
        "Does not turn off the JSON fallback."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--company-id", action="append", type=int, default=[])
        parser.add_argument("--pack", required=True, choices=["insurance", "manufacturing", "payroll"])

    def handle(self, *args, **options):
        pack = options["pack"]
        if pack == "payroll":
            raise CommandError("Payroll has no pack grant. Refusing.")
        company_ids = options["company_id"] or []
        if not company_ids:
            raise CommandError("Pass --company-id at least once.")
        apply = bool(options["apply"]) and not bool(options["dry_run"])
        with rls_bypass():
            for company_id in company_ids:
                company = Company.objects.filter(pk=company_id).first()
                if company is None:
                    raise CommandError(f"No company {company_id}.")
                before = build_feature_flags(company=company)
                flags = dict(company.feature_flags or {})
                if pack == "insurance":
                    flags["pack_grant"] = "insurance"
                else:
                    flags["manufacturing_pack_grant"] = True
                company.feature_flags = flags
                after = build_feature_flags(company=company)
                self.stdout.write(f"company={company.pk} pack={pack}")
                self.stdout.write(f"  before ENABLE_CRM={before.get('ENABLE_CRM')} ENABLE_MANUFACTURING={before.get('ENABLE_MANUFACTURING')} ENABLE_PAYROLL={before.get('ENABLE_PAYROLL')}")
                self.stdout.write(f"  after ENABLE_CRM={after.get('ENABLE_CRM')} ENABLE_MANUFACTURING={after.get('ENABLE_MANUFACTURING')} ENABLE_PAYROLL={after.get('ENABLE_PAYROLL')}")
                if apply:
                    company.save(update_fields=["feature_flags", "updated_at"])
                    self.stdout.write("  applied")
                else:
                    company.refresh_from_db()
                    self.stdout.write("  dry-run")
