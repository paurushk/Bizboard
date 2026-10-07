from django.core.management.base import BaseCommand
from django.db.models import Count

from accounting.models import CashShiftRegister


class Command(BaseCommand):
    help = "List cashiers who have more than one open till. The shift migration aborts on these rows."

    def handle(self, *args, **options):
        rows = (
            CashShiftRegister.objects.filter(status=CashShiftRegister.Status.OPEN)
            .values("company_id", "cashier_id")
            .annotate(open_count=Count("id"))
            .filter(open_count__gt=1)
            .order_by("company_id", "cashier_id")
        )
        found = False
        for row in rows:
            found = True
            shifts = CashShiftRegister.objects.filter(
                company_id=row["company_id"],
                cashier_id=row["cashier_id"],
                status=CashShiftRegister.Status.OPEN,
            )
            ids = ", ".join(str(shift.pk) for shift in shifts)
            self.stdout.write(
                f"company {row['company_id']} cashier {row['cashier_id']} "
                f"open shifts: {ids}"
            )
        if not found:
            self.stdout.write("No cashier has more than one open shift.")
