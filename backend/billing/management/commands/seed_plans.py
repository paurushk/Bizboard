from django.core.management.base import BaseCommand
from billing.models import Plan


class Command(BaseCommand):
    help = "Seed standard PRD §22 SaaS subscription plans."

    def handle(self, *args, **options):
        plans_data = [
            {
                "name": "Free",
                "slug": "free",
                "seat_limit": 1,
                "price_paise": 0,
                "is_active": True,
                "modules": {
                    "ENABLE_POS": False,
                    "ENABLE_GSTR": False,
                    "ENABLE_MANUFACTURING": False,
                    "ENABLE_PAYROLL": False,
                    "ENABLE_CRM": False,
                    "ENABLE_TALLY": False,
                },
            },
            {
                "name": "Starter",
                "slug": "starter",
                "seat_limit": 2,
                "price_paise": 49900,
                "is_active": True,
                "modules": {
                    "ENABLE_POS": True,
                    "ENABLE_GSTR": True,
                    "ENABLE_MANUFACTURING": False,
                    "ENABLE_PAYROLL": False,
                    "ENABLE_CRM": False,
                    "ENABLE_TALLY": False,
                },
            },
            {
                "name": "Professional",
                "slug": "pro",
                "seat_limit": 5,
                "price_paise": 149900,
                "is_active": True,
                "modules": {
                    "ENABLE_POS": True,
                    "ENABLE_GSTR": True,
                    "ENABLE_MANUFACTURING": True,
                    "ENABLE_PAYROLL": True,
                    "ENABLE_CRM": True,
                    "ENABLE_TALLY": True,
                },
            },
            {
                "name": "Enterprise",
                "slug": "enterprise",
                "seat_limit": 999,
                "price_paise": 499900,
                "is_active": True,
                "modules": {
                    "ENABLE_POS": True,
                    "ENABLE_GSTR": True,
                    "ENABLE_MANUFACTURING": True,
                    "ENABLE_PAYROLL": True,
                    "ENABLE_CRM": True,
                    "ENABLE_TALLY": True,
                },
            },
        ]

        for p_data in plans_data:
            plan, created = Plan.objects.update_or_create(
                slug=p_data["slug"],
                defaults=p_data,
            )
            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{action} plan '{plan.name}' ({plan.slug})"))
