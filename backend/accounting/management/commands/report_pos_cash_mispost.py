"""List POS receipts that debited cash 1100 even though the tender was not cash.

Read-only. Correcting journals are not posted: non-cash reclasses and credit
reversals need an accountant. Run after the tender-account mapping is in use
so new sales do not add to this list.
"""

from django.core.management.base import BaseCommand

from accounting.models import JournalLine
from payments.models import CustomerReceipt, PaymentMode


class Command(BaseCommand):
    help = "Report non-cash POS receipts posted to cash account 1100."

    def handle(self, *args, **options):
        receipts = CustomerReceipt.objects.filter(
            bank_account__isnull=True,
        ).exclude(mode=PaymentMode.CASH).select_related("company", "customer")
        found = 0
        for receipt in receipts.iterator():
            notes = (receipt.notes or "")
            if "POS" not in notes.upper() and receipt.mode != PaymentMode.CREDIT:
                continue
            debit_1100 = JournalLine.objects.filter(
                entry__company_id=receipt.company_id,
                entry__source_type="CUSTOMER_RECEIPT",
                entry__source_id=receipt.id,
                entry__purpose="CREATE",
                account__code="1100",
                debit__gt=0,
            ).exists()
            if not debit_1100:
                continue
            found += 1
            self.stdout.write(
                f"company={receipt.company_id} receipt={receipt.id} mode={receipt.mode} "
                f"amount={receipt.amount} customer={receipt.customer_id} number={receipt.number}"
            )
        self.stdout.write(self.style.WARNING(
            f"{found} receipt(s). Do not auto-post a correction. "
            "Reclass non-cash off 1100 onto the mapped bank, and review CREDIT receipts per customer."
        ))
