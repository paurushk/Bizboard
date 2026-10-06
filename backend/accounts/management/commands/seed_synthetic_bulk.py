"""QOS-0014 — bulk-create a large SYNTHETIC dataset for the migration-rehearsal
drill (scripts/migration_rehearsal.sh).

This is explicitly NOT a substitute for a real anonymised production dump —
synthetic data can't reproduce real messy schemas, edge-case values, or the
row-count skew a real tenant accumulates. What it DOES give the rehearsal is
real row *volume* to apply `migrate` against, which is enough to catch the
concrete failure mode the item worries about: a migration that is fine on an
empty/tiny table and slow or lock-heavy on a large one.

    python manage.py seed_synthetic_bulk --invoices 5000
    python manage.py seed_synthetic_bulk --history --company "UX Audit Traders"

The volume drill requires `seed_demo` ("Demo Traders"). ``--history`` is the
six-month UX audit set and refuses Demo Traders.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Company
from crm.models import Lead
from inventory.models import StockCountSession, Warehouse
from masters.models import Customer, Product, Supplier
from payments.models import CustomerReceipt
from payroll.models import Employee
from purchases.models import PurchaseInvoice
from sales.models import SalesInvoice

AUDIT_COMPANY = "UX Audit Traders"


class Command(BaseCommand):
    help = "Bulk-create synthetic sales volume, or six months of UX-audit history."

    def add_arguments(self, parser):
        parser.add_argument("--invoices", type=int, default=5000)
        parser.add_argument("--batch-size", type=int, default=2000)
        parser.add_argument("--company", default="", help="Company name. Volume drill defaults to Demo Traders.")
        parser.add_argument(
            "--history",
            action="store_true",
            help="Six months of draft documents for the UX audit company. Refuses Demo Traders.",
        )

    def handle(self, *args, **options):
        _env = getattr(settings, "DJANGO_ENV", "").strip().lower()
        # Explicit DJANGO_ENV=development counts as dev: the dockerised dev stack runs DEBUG=0.
        if _env in ("production", "staging") or not (_env == "development" or getattr(settings, "DEBUG", False)):
            raise CommandError(
                f"seed_synthetic_bulk refuses to run outside DEBUG / non-prod (DJANGO_ENV={_env or 'unset'})."
            )
        if options["history"]:
            self._history(options["company"] or AUDIT_COMPANY)
            return
        self._volume(options["company"] or "Demo Traders", options["invoices"], options["batch_size"])

    def _volume(self, company_name: str, invoices: int, batch_size: int) -> None:
        company = Company.objects.filter(name=company_name).first()
        if not company:
            raise CommandError("Run `seed_demo` first — seed_synthetic_bulk builds on its company/customer/product.")
        customer = Customer.objects.filter(company=company).first()
        product = Product.objects.filter(company=company).first()
        if not customer or not product:
            raise CommandError(f"{company_name} has no customer/product to attach synthetic invoices to.")

        n = max(1, invoices)
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
        SalesInvoice.objects.bulk_create(rows, batch_size=max(1, batch_size))
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {n} synthetic SalesInvoice rows for company {company.id} ({company.name})."
        ))

    @transaction.atomic
    def _history(self, company_name: str) -> None:
        # All-or-nothing: the idempotency guard below keys on the invoices, so a partial
        # run would otherwise be skipped forever and leave an incomplete audit set.
        if company_name == "Demo Traders":
            raise CommandError("Refusing --history on Demo Traders. Use the UX audit company.")
        company = Company.objects.filter(name=company_name).first()
        if company is None:
            raise CommandError(f"No company named {company_name}. Run provision_ux_audit first.")
        if SalesInvoice.objects.filter(company=company, number__startswith="UXH-S-").exists():
            self.stdout.write(f"History already present for {company.name}.")
            return
        customer = Customer.objects.filter(company=company).first()
        supplier = Supplier.objects.filter(company=company).first()
        warehouse = Warehouse.objects.filter(company=company, is_default=True).first()
        if not customer or not supplier or not warehouse:
            raise CommandError(f"{company.name} is missing a customer, supplier, or default warehouse.")

        start = timezone.localdate() - timedelta(days=180)
        SalesInvoice.objects.bulk_create([
            SalesInvoice(
                company=company,
                customer=customer,
                number=f"UXH-S-{i:03d}",
                status=SalesInvoice.Status.DRAFT,
                invoice_type=SalesInvoice.InvoiceType.NON_GST,
                invoice_date=start + timedelta(days=(i * 7) % 180),
                taxable_total=Decimal("1000.00"),
                grand_total=Decimal("1000.00"),
            )
            for i in range(1, 25)
        ])
        PurchaseInvoice.objects.bulk_create([
            PurchaseInvoice(
                company=company,
                supplier=supplier,
                warehouse=warehouse,
                number=f"UXH-P-{i:03d}",
                status=PurchaseInvoice.Status.DRAFT,
                purchase_type=PurchaseInvoice.PurchaseType.NON_GST,
                invoice_date=start + timedelta(days=(i * 11) % 180),
                taxable_total=Decimal("800.00"),
                grand_total=Decimal("800.00"),
            )
            for i in range(1, 13)
        ])
        CustomerReceipt.objects.bulk_create([
            CustomerReceipt(
                company=company,
                customer=customer,
                number=f"UXH-R-{i:03d}",
                amount=Decimal("500.00"),
                receipt_date=start + timedelta(days=(i * 13) % 180),
                notes="ux-history",
                utr="",
            )
            for i in range(1, 13)
        ])
        StockCountSession.objects.bulk_create([
            StockCountSession(
                company=company,
                warehouse=warehouse,
                status=StockCountSession.Status.DRAFT,
                counted_on=start + timedelta(days=i * 30),
                notes="ux-history",
            )
            for i in range(6)
        ])
        Employee.objects.bulk_create([
            Employee(
                company=company,
                name=f"UX Employee {i}",
                code=f"UXH-E{i}",
                salary=Decimal("25000.00"),
            )
            for i in range(1, 5)
        ])
        Lead.objects.bulk_create([
            Lead(company=company, name=f"UXH Lead {i}", phone=f"90000004{i:02d}", status=Lead.Status.NEW)
            for i in range(1, 9)
        ])
        self.stdout.write(self.style.SUCCESS(
            f"Seeded six-month history for {company.name}: "
            "24 draft invoices, 12 draft purchases, 12 receipts, 6 stock counts, 4 employees, 8 leads."
        ))
