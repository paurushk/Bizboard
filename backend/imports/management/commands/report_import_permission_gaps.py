"""List users who can import but can no longer use bill import.

Bill upload now needs the Import permission AND the right to create the
document it produces (sales invoice / purchase invoice). Run this before
deploying to tell the affected people (UPLOAD_SALES_BILL_REVIEW 23.5).
"""

from django.core.management.base import BaseCommand

from accounts.models import CompanyUser


class Command(BaseCommand):
    help = "Report users with can_import who cannot create sales and/or purchase invoices."

    def handle(self, *args, **options):
        rows = 0
        for cu in CompanyUser.objects.select_related("company", "user").filter(can_import=True).exclude(
            role=CompanyUser.Role.OWNER
        ):
            missing = []
            if not cu.can_create_sales:
                missing.append("sales")
            if not cu.can_create_purchases:
                missing.append("purchases")
            if not missing:
                continue
            rows += 1
            self.stdout.write(
                f"{cu.company.name} | {cu.user.email} | role={cu.role} | cannot import bills for: {', '.join(missing)}"
            )
        self.stdout.write(self.style.SUCCESS(f"{rows} user(s) affected."))
