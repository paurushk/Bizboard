"""Release quotation conversion rows whose order or invoice is gone or cancelled."""

from django.core.management.base import BaseCommand

from sales.quotation_conversions import QuotationConversionService


class Command(BaseCommand):
    help = (
        "Release converted quantity held by deleted or cancelled orders and invoices. "
        "Use --dry-run first to see the counts."
    )

    def add_arguments(self, parser):
        parser.add_argument("--company", type=int, default=None, help="Limit to one company id.")
        parser.add_argument("--dry-run", action="store_true", help="Count only; change nothing.")

    def handle(self, *args, **options):
        result = QuotationConversionService.sweep(options["company"], dry_run=options["dry_run"])
        verb = "would release" if options["dry_run"] else "released"
        self.stdout.write(f"{verb} {result['released']} conversion row(s)")
        for reason, count in sorted(result["by_reason"].items()):
            self.stdout.write(f"  {reason}: {count}")
        for company_id, count in sorted(result["by_company"].items()):
            self.stdout.write(f"  company {company_id}: {count}")
