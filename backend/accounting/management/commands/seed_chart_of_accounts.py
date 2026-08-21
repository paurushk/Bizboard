from django.core.management.base import BaseCommand, CommandError

from accounts.models import Company
from accounting.services import seed_chart_of_accounts


class Command(BaseCommand):
    help = "Seed the standard Indian SME chart of accounts for one company."

    def add_arguments(self, parser):
        parser.add_argument("company_id", type=int)

    def handle(self, *args, **options):
        company = Company.objects.filter(pk=options["company_id"]).first()
        if not company:
            raise CommandError("Company not found.")
        accounts = seed_chart_of_accounts(company)
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(accounts)} chart-of-accounts records."))
