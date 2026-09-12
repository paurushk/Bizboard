"""QOS-0014 — bulk-create a large SYNTHETIC dataset for the migration-rehearsal
drill (scripts/migration_rehearsal.sh).

This is explicitly NOT a substitute for a real anonymised production dump —
synthetic data can't reproduce real messy schemas, edge-case values, or the
row-count skew a real tenant accumulates. What it DOES give the rehearsal is
real row *volume* to apply `migrate` against, which is enough to catch the
concrete failure mode the item worries about: a migration that is fine on an
empty/tiny table and slow or lock-heavy on a large one.

    python manage.py seed_synthetic_bulk --invoices 5000

Requires `seed_demo` to have already created "Demo Traders" (fails loudly
otherwise, rather than silently seeding into a random company).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import Company
from masters.models import Customer, Product
from sales.models import SalesInvoice


class Command(BaseCommand):
    help = "Bulk-create a large synthetic SalesInvoice volume for the migration-rehearsal drill."

    def add_arguments(self, parser):
        parser.add_argument("--invoices", type=int, default=5000)
        parser.add_argument("--batch-size", type=int, default=2000)

    def handle(self, *args, **options):
        _env = getattr(settings, "DJANGO_ENV", "").strip().lower()
        if _env in ("production", "staging") or not getattr(settings, "DEBUG", False):
            raise CommandError(
                f"seed_synthetic_bulk refuses to run outside DEBUG / non-prod (DJANGO_ENV={_env or 'unset'})."
            )

        company = Company.objects.filter(name="Demo Traders").first()
        if not company:
            raise CommandError("Run `seed_demo` first — seed_synthetic_bulk builds on its company/customer/product.")
        customer = Customer.objects.filter(company=company).first()
        product = Product.objects.filter(company=company).first()
        if not customer or not product:
            raise CommandError("Demo Traders has no customer/product to attach synthetic invoices to.")

        n = max(1, options["invoices"])
        start = timezone.localdate() - timedelta(days=365)
        rows = [
            SalesInvoice(
                company=company,
                customer=customer,
                status=SalesInvoice.Status.COMPLETED,
                invoice_type=SalesInvoice.InvoiceType.NON_GST,
                invoice_date=start + timedelta(days=i % 365),
                taxable_total=Decimal("1000.00"),
                grand_total=Decimal("1000.00"),
            )
            for i in range(n)
        ]
        SalesInvoice.objects.bulk_create(rows, batch_size=max(1, options["batch_size"]))
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {n} synthetic SalesInvoice rows for company {company.id} ({company.name})."
        ))
