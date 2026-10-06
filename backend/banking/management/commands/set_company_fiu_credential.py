"""Store one company's FIU API token. The process FIU_API_KEY is not used."""

from django.core.management.base import BaseCommand, CommandError

from accounts.models import Company
from core.rls import rls_bypass
from core.services.gsp_secrets import encrypt_gsp_credentials
from integrations.models import IntegrationConnection


class Command(BaseCommand):
    help = "Encrypt a per-company FIU token onto an IntegrationConnection."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--token", required=True)

    def handle(self, *args, **options):
        token = (options["token"] or "").strip()
        if not token:
            raise CommandError("Pass --token.")
        with rls_bypass():
            company = Company.objects.filter(pk=options["company_id"]).first()
            if company is None:
                raise CommandError("No such company.")
            IntegrationConnection.objects.update_or_create(
                company=company,
                provider="FIU",
                defaults={
                    "status": IntegrationConnection.Status.ACTIVE,
                    "encrypted_secrets": encrypt_gsp_credentials({"fiu_api_key": token}),
                },
            )
        self.stdout.write(f"Stored FIU credential for company {company.pk}.")
