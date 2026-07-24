"""Document Number Service — independent, concurrency-safe sequences (E0.13)."""

import re
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
    def _ensure_series(company, doc_type: str) -> DocumentSeries:
        if doc_type not in DEFAULT_PREFIXES:
            raise ValueError(f"Unknown document type: {doc_type}")
        series, _ = DocumentSeries.objects.get_or_create(
            company=company,
            doc_type=doc_type,
            defaults={"prefix": DEFAULT_PREFIXES[doc_type]},
        )
        return series

    @staticmethod
    def _max_existing_seq(company, doc_type: str, prefix: str) -> int:
        """Highest numeric suffix already used for this doc type / prefix."""
        from payments.models import CustomerReceipt, SupplierPayment
        from purchases.models import PurchaseInvoice, PurchaseReturn
        from sales.models import Quotation, SalesInvoice, SalesReturn

        qs = None
        if doc_type == "SALES_INVOICE":
            qs = SalesInvoice.objects.filter(company=company).exclude(number="")
        elif doc_type == "PURCHASE_INVOICE":
            qs = PurchaseInvoice.objects.filter(company=company).exclude(number="")
        elif doc_type == "QUOTATION":
            qs = Quotation.objects.filter(company=company).exclude(number="")
        elif doc_type == "SALES_RETURN":
            qs = SalesReturn.objects.filter(company=company).exclude(number="")
        elif doc_type == "PURCHASE_RETURN":
            qs = PurchaseReturn.objects.filter(company=company).exclude(number="")
        elif doc_type == "CUSTOMER_RECEIPT":
            qs = CustomerReceipt.objects.filter(company=company).exclude(number="")
        elif doc_type == "SUPPLIER_PAYMENT":
            qs = SupplierPayment.objects.filter(company=company).exclude(number="")
        else:
            return 0

        max_n = 0
        prefix_l = (prefix or "").strip()
        for num in qs.values_list("number", flat=True):
            raw = (num or "").strip()
            if not raw:
                continue
            if prefix_l and raw.upper().startswith(prefix_l.upper()):
                suffix = raw[len(prefix_l) :].lstrip("-/ _")
            else:
                suffix = raw
            m = re.search(r"(\d+)\s*$", suffix)
            if m:
                max_n = max(max_n, int(m.group(1)))
        return max_n

    @staticmethod
    def sync_next(company, doc_type: str) -> DocumentSeries:
        """Ensure next_number continues after the highest existing document."""
        series = DocumentNumberService._ensure_series(company, doc_type)
        max_n = DocumentNumberService._max_existing_seq(company, doc_type, series.prefix)
        needed = max_n + 1
        if needed > series.next_number:
            series.next_number = needed
            series.save(update_fields=["next_number"])
        return series

    @staticmethod
    def peek(company, doc_type: str) -> dict:
        series = DocumentNumberService.sync_next(company, doc_type)
        return {
            "doc_type": series.doc_type,
            "prefix": series.prefix,
            "next_number": series.next_number,
            "padding": series.padding,
            "preview": f"{series.prefix}-{series.next_number:0{series.padding}d}",
        }

    @staticmethod
    @transaction.atomic
    def configure(company, doc_type: str, *, prefix=None, next_number=None, padding=None) -> dict:
        DocumentNumberService._ensure_series(company, doc_type)
        series = DocumentSeries.objects.select_for_update().get(company=company, doc_type=doc_type)
        if prefix is not None:
            cleaned = str(prefix).strip()
            if not cleaned:
                raise ValueError("Prefix cannot be empty.")
            series.prefix = cleaned[:16]
        if next_number is not None:
            n = int(next_number)
            if n < 1:
                raise ValueError("Next number must be at least 1.")
            series.next_number = n
        if padding is not None:
            p = int(padding)
            if p < 1 or p > 10:
                raise ValueError("Padding must be between 1 and 10.")
            series.padding = p
        series.save()
        # After manual configure, still never go below existing docs for this prefix.
        DocumentNumberService.sync_next(company, doc_type)
        return DocumentNumberService.peek(company, doc_type)

    @staticmethod
    def next_number(company, doc_type: str) -> str:
        """Allocate next number inside the caller's transaction (nested atomic = savepoint)."""
        if doc_type not in DEFAULT_PREFIXES:
            raise ValueError(f"Unknown document type: {doc_type}")
        with transaction.atomic():
            DocumentNumberService.sync_next(company, doc_type)
            series = DocumentSeries.objects.select_for_update().get(
                company=company, doc_type=doc_type
            )
            max_n = DocumentNumberService._max_existing_seq(company, doc_type, series.prefix)
            if max_n >= series.next_number:
                series.next_number = max_n + 1
            number = f"{series.prefix}-{series.next_number:0{series.padding}d}"
            series.next_number += 1
            series.save(update_fields=["next_number"])
            return number
