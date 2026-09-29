"""Give one golden-run company a trial subscription.

Registration creates a trial only when REQUIRE_SUBSCRIPTION is on. The golden
server leaves that off, so suspend has nothing to update until this command
runs. It refuses unless E2E_GOLDEN_GRANT=1.
"""

from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError

from accounts.models import CompanyUser, User
from billing.services import ensure_register_trial


class Command(BaseCommand):
    help = "Create the register trial for the company that owns this email."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)

    def handle(self, *args, **options):
        if os.environ.get("E2E_GOLDEN_GRANT") != "1":
            raise CommandError("Refusing to seed a trial unless E2E_GOLDEN_GRANT=1.")
        user = User.objects.filter(email__iexact=options["email"]).first()
        if user is None:
            raise CommandError("No user with that email.")
        membership = CompanyUser.objects.filter(user=user).select_related("company").first()
        if membership is None:
            raise CommandError("That user has no company.")
        row = ensure_register_trial(membership.company)
        if row is None:
            self.stdout.write("Trial already present.")
            return
        self.stdout.write(f"Trial {row.pk} on company {membership.company_id}.")
