"""Point the golden API at one company as the SaaS vendor.

VENDOR_COMPANY_ID is fixed when the server starts. This writes
backend/.e2e_vendor_id, which billing.ops reads only while
E2E_GOLDEN_GRANT=1. The command itself also refuses otherwise.
"""

from __future__ import annotations

import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import CompanyUser, User


class Command(BaseCommand):
    help = "Record the company of this email as the golden-run vendor."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)

    def handle(self, *args, **options):
        if os.environ.get("E2E_GOLDEN_GRANT") != "1":
            raise CommandError("Refusing to mark a vendor unless E2E_GOLDEN_GRANT=1.")
        user = User.objects.filter(email__iexact=options["email"]).first()
        if user is None:
            raise CommandError("No user with that email.")
        membership = CompanyUser.objects.filter(user=user).select_related("company").first()
        if membership is None:
            raise CommandError("That user has no company.")
        path = Path(settings.BASE_DIR) / ".e2e_vendor_id"
        path.write_text(str(membership.company_id), encoding="utf-8")
        self.stdout.write(f"Vendor company {membership.company_id}.")
