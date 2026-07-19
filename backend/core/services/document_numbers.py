"""Document Number Service — independent, concurrency-safe sequences (E0.13)."""

from django.db import transaction

from core.models import DocumentSeries

DEFAULT_PREFIXES = {
    "SALES_INVOICE": "INV",
    "PURCHASE_INVOICE": "PUR",
    "QUOTATION": "QTN",
    "SALES_RETURN": "SRN",
    "PURCHASE_RETURN": "PRN",
    "CUSTOMER_RECEIPT": "RCT",
    "SUPPLIER_PAYMENT": "PAY",
}


class DocumentNumberService:
    @staticmethod
    def next_number(company, doc_type: str) -> str:
        if doc_type not in DEFAULT_PREFIXES:
            raise ValueError(f"Unknown document type: {doc_type}")
        with transaction.atomic():
            DocumentSeries.objects.get_or_create(
                company=company,
                doc_type=doc_type,
                defaults={"prefix": DEFAULT_PREFIXES[doc_type]},
            )
            # Row lock guards against invoice-number races (§18).
            series = DocumentSeries.objects.select_for_update().get(
                company=company, doc_type=doc_type
            )
            number = f"{series.prefix}-{series.next_number:0{series.padding}d}"
            series.next_number += 1
            series.save(update_fields=["next_number"])
        return number
