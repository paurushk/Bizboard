"""6.5 — print cutover recon counts then run check_invariants.

    python manage.py cutover_recon --company-id 42
"""

from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from accounts.models import Company
from core.rls import rls_bypass, set_rls_company
from masters.models import Customer, Product, Supplier
from purchases.models import PurchaseInvoice
from sales.models import SalesInvoice


class Command(BaseCommand):
    help = "Cutover recon: counts + invariant sweep for one company."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)

    def handle(self, *args, **options):
        pk = options["company_id"]
        with rls_bypass():
            company = Company.objects.filter(pk=pk).first()
        if company is None:
            raise CommandError(f"No company {pk}.")
        set_rls_company(company.pk)
        rows = [
            ("products", Product.objects.filter(company=company).count()),
            ("customers", Customer.objects.filter(company=company).count()),
            ("suppliers", Supplier.objects.filter(company=company).count()),
            ("sales_invoices", SalesInvoice.objects.filter(company=company).count()),
            ("purchase_invoices", PurchaseInvoice.objects.filter(company=company).count()),
        ]
        for name, n in rows:
            self.stdout.write(f"{name}={n}")
        call_command("check_invariants", company=pk)
