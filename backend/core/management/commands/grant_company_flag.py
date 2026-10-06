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
        parser.add_argument(
            "--company-id", type=int, default=None,
            help="Required when the user belongs to more than one company.",
        )
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--on", action="store_true")
        group.add_argument("--off", action="store_true")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Required when DJANGO_ENV is production or staging.",
        )

    def handle(self, *args, **options):
        from django.conf import settings

        from core.services.audit import AuditService

        if settings.DJANGO_ENV in ("production", "staging") and not options["force"]:
            raise CommandError(
                "grant_company_flag refuses to run when DJANGO_ENV is "
                f"{settings.DJANGO_ENV} unless --force is passed."
            )
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
        memberships = CompanyUser.objects.filter(user=user).select_related("company").order_by("id")
        if options["company_id"] is not None:
            memberships = memberships.filter(company_id=options["company_id"])
        elif memberships.count() > 1:
            # Picking one at random would change the wrong tenant's flags.
            raise CommandError("That user belongs to several companies. Pass --company-id.")
        membership = memberships.first()
        if membership is None:
            raise CommandError("That user has no such company.")
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
        AuditService.log(
            company=company,
            user=user,
            action="FEATURE_FLAG_GRANT",
            entity_type="Company",
            entity_id=company.id,
            description=f"{flag} {state} (run by {os.environ.get('USERNAME') or os.environ.get('USER') or 'unknown operator'})",
        )
        self.stdout.write(f"Set {flag} {state} on company {company.pk}.")
