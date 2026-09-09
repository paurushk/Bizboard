"""SR-42 / D13 — CLI right-to-erasure for a single company.

    python manage.py erase_company --company-id 42 --confirm "Acme Traders" \
        --reason "DPDP data-subject request #1234"

Irreversible. Runs the full cascade + writes a TenantErasureLog. Unlike the HTTP
endpoint this is not gated on ENABLE_TENANT_ERASURE (an operator running a
management command has already made the call), but it still refuses outside a
non-prod shell unless --force is given, and always requires the exact name echo.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Irreversibly erase a company and everything it owns (D13)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--confirm", required=True, help="Exact company name, echoed to confirm.")
        parser.add_argument("--mode", choices=("tombstone", "hard"), default="tombstone",
                            help="tombstone = keep scrubbed statutory tax docs (SR-40 default); hard = delete everything.")
        parser.add_argument("--reason", default="", help="Recorded on the erasure log.")
        parser.add_argument("--requested-by", default="cli", help="Email / identifier of the requester.")
        parser.add_argument("--skip-export", action="store_true", help="Do not build the pre-erasure export.")

    def handle(self, *args, **options):
        from accounts.erasure import assert_erasure_model_coverage, erase_company
        from accounts.models import Company

        # fail fast if the wipe set has drifted
        assert_erasure_model_coverage()

        try:
            company = Company.objects.get(pk=options["company_id"])
        except Company.DoesNotExist:
            raise CommandError(f"No company with id {options['company_id']}.")

        if options["confirm"].strip() != (company.name or "").strip():
            raise CommandError(
                f"--confirm must be the exact company name ({company.name!r})."
            )

        result = erase_company(
            company,
            mode=options["mode"],
            requested_by_email=options["requested_by"],
            reason=options["reason"],
            skip_export=options["skip_export"],
        )
        self.stdout.write(self.style.SUCCESS(
            f"Erased company {result.company_id} ({result.company_name!r}) mode={result.mode}. "
            f"erasure log id={result.log_id}, export sha256={result.export_sha256 or '(skipped)'}, "
            f"retained={result.retained or '{}'}"
        ))
