from django.core.management.base import BaseCommand

from core.services.uqc import normalize_uqc
from masters.models import Unit


class Command(BaseCommand):
    help = "Map existing Unit.uqc_code from name/short_name onto the GSTN UQC list (GAP-003)."

    def add_arguments(self, parser):
        parser.add_argument("--company", type=int, help="Limit to a company id.")

    def handle(self, *args, **options):
        qs = Unit.objects.all()
        if options.get("company"):
            qs = qs.filter(company_id=options["company"])
        updated = 0
        unmapped = 0
        for unit in qs.iterator():
            code = normalize_uqc(unit.uqc_code) or normalize_uqc(unit.short_name) or normalize_uqc(unit.name)
            if code and unit.uqc_code != code:
                unit.uqc_code = code
                unit.save(update_fields=["uqc_code"])
                updated += 1
            elif not code:
                unmapped += 1
        self.stdout.write(self.style.SUCCESS(f"Mapped {updated} units; {unmapped} remain UQC_UNMAPPED."))
