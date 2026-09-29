"""Turn one rollout flag on or off for one company.

Writes company JSON only. Does not touch the shared trial plan. Refuses dark
modules and refuses when E2E_GOLDEN_GRANT is set (that switch belongs to the
golden-browser command, not to operators).
"""

from __future__ import annotations

import os

from django.core.management.base import BaseCommand, CommandError

from accounts.models import CompanyUser, User
from core.services.feature_flags import DARK_MODULE_KEYS, ROLLOUT_GRANTABLE_KEYS


class Command(BaseCommand):
    help = (
        "Turn one grantable rollout flag on for the company of the given user, "
        "or remove that company override with --off."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--flag", required=True)
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--on", action="store_true")
        group.add_argument("--off", action="store_true")

    def handle(self, *args, **options):
        if os.environ.get("E2E_GOLDEN_GRANT") == "1":
            raise CommandError("Refusing to grant a flag while E2E_GOLDEN_GRANT=1.")
        flag = options["flag"]
        if flag in DARK_MODULE_KEYS:
            raise CommandError(f"{flag} is a dark module. This command cannot turn it on.")
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
        if options["on"]:
            flags[flag] = True
            state = "on"
        else:
            flags.pop(flag, None)
            state = "off"
        company.feature_flags = flags
        company.save(update_fields=["feature_flags", "updated_at"])
        self.stdout.write(f"Set {flag} {state} on company {company.pk}.")
