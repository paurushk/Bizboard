"""SET-04: move each company's bill-print bank details onto a Bank Account.

Until a company has an account marked "print on invoices", its bills read the company's own bank
fields (see ``payments.services.invoice_bank_details``), so nothing is lost by skipping this. Run
it to give those companies a Bank Accounts record holding the full (sealed) number and UPI ID.

For each company that has a bank name or number on the Company row and no invoice account yet, the
details are copied onto its invoice account, or its default account, or a new default account.
That overwrites the name, IFSC and UPI ID of the account it picks, so run it once, before owners
start editing accounts. Companies that already have an invoice account are left alone, so it is safe
to re-run.
"""

from django.core.management.base import BaseCommand

from accounts.models import Company
from payments.models import BankAccount
from payments.services import sync_company_bank_account


class Command(BaseCommand):
    help = "Copy company bank details onto a Bank Account marked for invoices."

    def add_arguments(self, parser):
        parser.add_argument("--company", type=int, help="Only this company id.")
        parser.add_argument("--dry-run", action="store_true", help="Report only; write nothing.")

    def handle(self, *args, company=None, dry_run=False, **options):
        qs = Company.objects.exclude(bank_name="", bank_account="")
        if company:
            qs = qs.filter(pk=company)
        done = skipped = 0
        for row in qs.iterator():
            if BankAccount.objects.filter(company=row, print_on_invoices=True).exists():
                skipped += 1
                continue
            done += 1
            if not dry_run:
                sync_company_bank_account(row)
        verb = "Would update" if dry_run else "Updated"
        self.stdout.write(f"{verb} {done} company(ies); {skipped} already had an invoice account.")
