"""Seed synthetic C1–C5 persona companies for Compose staging only.

Development: use seed_pilot_fixtures / seed_demo (DEBUG, DJANGO_ENV=development).
Production: seeding is forbidden.
Staging: this command — DJANGO_ENV=staging only, including DEBUG=0.
"""

from django.conf import settings
from django.core.management.base import CommandError

from accounts.models import Company, User
from accounts.management.commands.seed_pilot_fixtures import PROFILES
from accounts.management.commands.seed_pilot_fixtures import Command as PilotCommand


class Command(PilotCommand):
    help = "Seed C1–C5 synthetic companies. Allowed only when DJANGO_ENV=staging."

    def handle(self, *args, **options):
        env = getattr(settings, "DJANGO_ENV", "").strip().lower()
        if env != "staging":
            raise CommandError(
                "seed_staging only runs when DJANGO_ENV=staging "
                "(got {}). Development: seed_pilot_fixtures / seed_demo. "
                "Production: seeding is forbidden.".format(env or "unset")
            )

        if options["reset"]:
            for profile in PROFILES:
                Company.objects.filter(name=profile["name"]).delete()
                User.objects.filter(email__iexact=profile["email"]).delete()
                if profile.get("staff_email"):
                    User.objects.filter(email__iexact=profile["staff_email"]).delete()
            self.stdout.write("Reset previous staging fixtures.")

        for profile in PROFILES:
            self._seed_profile(profile)

        n = options["perf_invoices"]
        if n > 0:
            self._seed_perf_invoices(n)

        self.stdout.write(self.style.SUCCESS(
            "Staging fixtures ready. Password for all users: PilotPass123!\n"
            "Reset: python manage.py seed_staging --reset"
        ))
