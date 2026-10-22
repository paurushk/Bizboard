"""Set up a believable manufacturing demo for one development company.

Turns the manufacturing sub-modules on, adds raw materials with stock, a finished good with a recipe
and a by-product, a work centre with a routing and an operator. Refuses on staging and production.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import CompanyUser, User
from manufacturing import demo


class Command(BaseCommand):
    help = "Add demo manufacturing data to one development company. Staging and production are refused."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="Any user of the target company.")
        parser.add_argument("--company-id", type=int, help="Required when the user has several companies.")

    def handle(self, *args, **options):
        env_name = (getattr(settings, "DJANGO_ENV", "") or "").strip().lower()
        if env_name in ("production", "staging"):
            raise CommandError(f"Refusing to run when DJANGO_ENV={env_name}.")
        user = User.objects.filter(email__iexact=options["email"]).first()
        if user is None:
            raise CommandError("No user with that email.")
        memberships = list(CompanyUser.objects.filter(user=user, is_active=True).select_related("company"))
        if not memberships:
            raise CommandError("That user has no company.")
        company_id = options.get("company_id")
        if len(memberships) > 1 and not company_id:
            raise CommandError("That user has several companies. Pass --company-id.")
        membership = (
            next((m for m in memberships if m.company_id == company_id), None) if company_id else memberships[0]
        )
        if membership is None:
            raise CommandError("That company is not one of this user's memberships.")
        built = demo.build(membership.company, user)
        self.stdout.write(
            f"Company {membership.company.pk} ({membership.company.name}): demo recipe "
            f"'{built['biscuit_bom'].name}' ready. Try Quick production for {built['biscuit'].name}."
        )
