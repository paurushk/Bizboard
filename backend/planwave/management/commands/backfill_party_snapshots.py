from django.core.management.base import BaseCommand

from planwave.services import stamp_document_party
from purchases.models import PurchaseCreditNote, PurchaseDebitNote, PurchaseInvoice
from sales.models import SalesCreditNote, SalesDebitNote, SalesInvoice


class Command(BaseCommand):
    help = "Stamp party details on completed documents and mark them as backfill."

    def handle(self, *args, **options):
        stamped = 0
        models = (SalesInvoice, SalesCreditNote, SalesDebitNote, PurchaseInvoice, PurchaseCreditNote, PurchaseDebitNote)
        for model in models:
            for row in model.objects.filter(status="COMPLETED").iterator():
                if stamp_document_party(row, backfill=True):
                    stamped += 1
        self.stdout.write(f"Stamped {stamped} documents.")
