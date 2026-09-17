from django.core.management.base import BaseCommand

from billing.entitlements import freeze_safe_modules
from billing.models import Plan


class Command(BaseCommand):
    help = "Seed standard PRD §22 SaaS subscription plans (freeze-safe modules)."

    def handle(self, *args, **options):
        plans_data = [
            {
                "name": "Free",
                "slug": "free",
                "seat_limit": 1,
                "monthly_complete_limit": 30,
                "storage_bytes_limit": 50 * 1024 * 1024,
                "api_rate_per_minute": 60,
                "price_paise": 0,
                "is_active": True,
                "modules": freeze_safe_modules(pos=False),
            },
            {
                "name": "Starter",
                "slug": "starter",
                "seat_limit": 2,
                "monthly_complete_limit": 300,
                "storage_bytes_limit": 500 * 1024 * 1024,
                "api_rate_per_minute": 120,
                "price_paise": 49900,
                "is_active": True,
                "modules": freeze_safe_modules(pos=True),
            },
            {
                "name": "Professional",
                "slug": "pro",
                "seat_limit": 5,
                "monthly_complete_limit": 2000,
                "storage_bytes_limit": 2 * 1024 * 1024 * 1024,
                "api_rate_per_minute": 300,
                "price_paise": 149900,
                "is_active": True,
                "modules": freeze_safe_modules(pos=True),
            },
            {
                "name": "Enterprise",
                "slug": "enterprise",
                "seat_limit": 999,
                "monthly_complete_limit": 0,
                "storage_bytes_limit": 0,
                "api_rate_per_minute": 0,
                "price_paise": 499900,
                "is_active": True,
                "modules": freeze_safe_modules(pos=True),
            },
        ]

        for p_data in plans_data:
            plan, created = Plan.objects.update_or_create(
                slug=p_data["slug"],
                defaults=p_data,
            )
            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{action} plan '{plan.name}' ({plan.slug})"))
