"""Turn one rollout flag on for one company during golden browser runs.

Company PATCH leaves ``feature_flags`` read-only. The golden API process sets
``E2E_GOLDEN_GRANT=1``. Any other process is refused, so this command is not
a production grant path.
"""

from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError

from accounts.models import CompanyUser, User
from core.services.feature_flags import ROLLOUT_GRANTABLE_KEYS


class Command(BaseCommand):
    help = "Set one rollout flag true on the company of the given user email."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--flag", required=True)

    def handle(self, *args, **options):
        if os.environ.get("E2E_GOLDEN_GRANT") != "1":
            raise CommandError("Refusing to grant a flag unless E2E_GOLDEN_GRANT=1.")
        flag = options["flag"]
        if flag not in ROLLOUT_GRANTABLE_KEYS:
            raise CommandError(f"{flag} is not a rollout flag.")
        user = User.objects.filter(email__iexact=options["email"]).first()
        if user is None:
            raise CommandError("No user with that email.")
        membership = CompanyUser.objects.filter(user=user).select_related("company").first()
        if membership is None:
            raise CommandError("That user has no company.")
        company = membership.company
        flags = dict(company.feature_flags or {})
        flags[flag] = True
        company.feature_flags = flags
        company.save(update_fields=["feature_flags", "updated_at"])
        self.stdout.write(f"Granted {flag} on company {company.pk}.")
