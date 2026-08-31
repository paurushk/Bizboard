"""Document Number Service — independent, concurrency-safe sequences (E0.13).

ADR-A25 / ADR-A28 (Sprint 3 / BB-000646):
- Filing identity is CompanyGstin; money-doc series are unique per GSTIN + FY.
- next_number trusts DocumentSeries.next_number (row lock) and does NOT
  full-scan historical document numbers on the hot path.
- sync_next remains an explicit repair/configure tool for imports.
"""

import re
from datetime import date

from django.db import transaction
from django.utils import timezone

from core.models import DocumentSeries

DEFAULT_PREFIXES = {
    "SALES_INVOICE": "INV",
    "PURCHASE_INVOICE": "PUR",
    "QUOTATION": "QTN",
    "SALES_RETURN": "SRN",
    "PURCHASE_RETURN": "PRN",
    "CUSTOMER_RECEIPT": "RCT",
    "SUPPLIER_PAYMENT": "PAY",
    "SALES_CREDIT_NOTE": "SCN",
    "SALES_DEBIT_NOTE": "SDN",
    "PURCHASE_CREDIT_NOTE": "PCN",
    "PURCHASE_DEBIT_NOTE": "PDN",
    "SALES_ORDER": "SO",
    "PURCHASE_ORDER": "PO",
    "DELIVERY_CHALLAN": "DC",
    "JOURNAL_ENTRY": "JV",
    "STOCK_TRANSFER": "TRF",
}


def gst_fy_label_for(on_date: date | None = None) -> str:
    """GST document series FY always starts in April (Rule 46(b))."""
    on_date = on_date or timezone.localdate()
    year = on_date.year
    if on_date.month < 4:
        year -= 1
    return f"{year}-{str(year + 1)[-2:]}"


def fy_label_for(company, on_date: date | None = None) -> str:
    # Rule 46(b): GST invoice numbering uses April–March FY regardless of
    # company.fy_start_month (books FY may differ; statutory series must not).
    return gst_fy_label_for(on_date)


def fy_compact(fy_label: str) -> str:
    parts = (fy_label or "").split("-")
    if len(parts) != 2:
        return (fy_label or "").replace("-", "")[-4:]
    return f"{parts[0][-2:]}{parts[1]}"


def _gstin_key(gstin) -> str:
    if gstin is None:
        return ""
    if hasattr(gstin, "gstin"):
        return (gstin.gstin or "").strip().upper()
    return str(gstin or "").strip().upper()


def series_identity(company, stamp=None, on_date=None):
    """Resolve (gstin_key, fy_label, on_date) for a document series.

    PD-03 / W0-04: if the company has any GSTIN (stamp, CompanyGstin, or
    company.gstin), always key by GSTIN+FY — even when a caller omitted
    ``gstin=`` and even when ``doc_number_scope`` is still COMPANY.
    No GSTIN → legacy unscoped series (empty keys).
    """
    gstin_key = resolve_series_gstin(company, stamp)
    if not gstin_key:
        scope = getattr(company, "doc_number_scope", "COMPANY") or "COMPANY"
        if scope != "GSTIN_FY":
            return "", "", None
    fy = fy_label_for(company, on_date)
    return (gstin_key or ""), fy, on_date or timezone.localdate()


def resolve_series_gstin(company, stamp=None):
    """BB-000729: document stamp, else primary CompanyGstin, else company.gstin."""
    if stamp is not None:
        return _gstin_key(stamp) or None
    from accounts.models import CompanyGstin

    primary = (
        CompanyGstin.objects.filter(company=company, is_primary=True, is_active=True)
        .order_by("-id")
        .first()
    )
    if primary is None:
        primary = (
            CompanyGstin.objects.filter(company=company, is_active=True)
            .order_by("-is_primary", "id")
            .first()
        )
    if primary is not None:
        return _gstin_key(primary.gstin) or None
    return _gstin_key(getattr(company, "gstin", None)) or None


class DocumentNumberService:
    @staticmethod
    def _series_defaults(doc_type: str, *, gstin_key: str, fy_label: str) -> dict:
        base = DEFAULT_PREFIXES[doc_type]
        if gstin_key or fy_label:
            parts = [base]
            if fy_label:
                parts.append(fy_compact(fy_label))
            if gstin_key:
                parts.append(gstin_key[-4:])
            prefix = "-".join(parts)
        else:
            prefix = base
        return {"prefix": prefix[:16], "gstin_key": gstin_key, "fy_label": fy_label}

    @staticmethod
    def _ensure_series(company, doc_type: str, *, gstin_key: str = "", fy_label: str = "") -> DocumentSeries:
        if doc_type not in DEFAULT_PREFIXES:
            raise ValueError(f"Unknown document type: {doc_type}")
        defaults = DocumentNumberService._series_defaults(
            doc_type, gstin_key=gstin_key or "", fy_label=fy_label or ""
        )
        series, _ = DocumentSeries.objects.get_or_create(
            company=company,
            doc_type=doc_type,
            gstin_key=gstin_key or "",
            fy_label=fy_label or "",
            defaults={"prefix": defaults["prefix"]},
        )
        return series

    @staticmethod
    def _queryset_for(company, doc_type: str):
        # R1-025: plain lazy imports (module-level would be circular). The two
        # accounting/inventory models get the same treatment as the rest — no
        # __import__() special-casing.
        from accounting.models import JournalEntry
        from inventory.models import StockTransfer
        from payments.models import CustomerReceipt, SupplierPayment
        from purchases.models import (
            PurchaseCreditNote,
            PurchaseDebitNote,
            PurchaseInvoice,
            PurchaseOrder,
            PurchaseReturn,
        )
        from sales.models import (
            DeliveryChallan,
            Quotation,
            SalesCreditNote,
            SalesDebitNote,
            SalesInvoice,
            SalesOrder,
            SalesReturn,
        )

        mapping = {
            "SALES_INVOICE": SalesInvoice.objects.filter(company=company).exclude(number=""),
            "PURCHASE_INVOICE": PurchaseInvoice.objects.filter(company=company).exclude(number=""),
            "QUOTATION": Quotation.objects.filter(company=company).exclude(number=""),
            "SALES_RETURN": SalesReturn.objects.filter(company=company).exclude(number=""),
            "PURCHASE_RETURN": PurchaseReturn.objects.filter(company=company).exclude(number=""),
            "CUSTOMER_RECEIPT": CustomerReceipt.objects.filter(company=company).exclude(number=""),
            "SUPPLIER_PAYMENT": SupplierPayment.objects.filter(company=company).exclude(number=""),
            "SALES_CREDIT_NOTE": SalesCreditNote.objects.filter(company=company).exclude(number=""),
            "SALES_DEBIT_NOTE": SalesDebitNote.objects.filter(company=company).exclude(number=""),
            "PURCHASE_CREDIT_NOTE": PurchaseCreditNote.objects.filter(company=company).exclude(number=""),
            "PURCHASE_DEBIT_NOTE": PurchaseDebitNote.objects.filter(company=company).exclude(number=""),
            "SALES_ORDER": SalesOrder.objects.filter(company=company).exclude(number=""),
            "PURCHASE_ORDER": PurchaseOrder.objects.filter(company=company).exclude(number=""),
            "DELIVERY_CHALLAN": DeliveryChallan.objects.filter(company=company).exclude(number=""),
            "JOURNAL_ENTRY": JournalEntry.objects.filter(company=company).exclude(number=""),
            "STOCK_TRANSFER": StockTransfer.objects.filter(company=company).exclude(number=""),
        }
        return mapping.get(doc_type)

    @staticmethod
    def _max_existing_seq(company, doc_type: str, prefix: str) -> int:
        """Repair-only: highest numeric suffix already used for this prefix.

        BB-000646: must not run on the allocate hot path.
        """
        qs = DocumentNumberService._queryset_for(company, doc_type)
        if qs is None:
            return 0

        max_n = 0
        prefix_l = (prefix or "").strip()
        for num in qs.values_list("number", flat=True).iterator(chunk_size=500):
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
    def sync_next(company, doc_type: str, *, gstin=None, on_date=None) -> DocumentSeries:
        """Ensure next_number continues after the highest existing document (import repair)."""
        gstin_key, fy_label, _on = DocumentNumberService._resolve_keys(
            company, gstin=gstin, on_date=on_date
        )
        DocumentNumberService._ensure_series(
            company, doc_type, gstin_key=gstin_key, fy_label=fy_label
        )
        with transaction.atomic():
            series = DocumentSeries.objects.select_for_update().get(
                company=company, doc_type=doc_type, gstin_key=gstin_key, fy_label=fy_label
            )
            max_n = DocumentNumberService._max_existing_seq(company, doc_type, series.prefix)
            needed = max_n + 1
            if needed > series.next_number:
                series.next_number = needed
                series.save(update_fields=["next_number"])
            return series

    @staticmethod
    def peek(company, doc_type: str, *, gstin=None, on_date=None) -> dict:
        gstin_key, fy_label, _on = DocumentNumberService._resolve_keys(
            company, gstin=gstin, on_date=on_date
        )
        with transaction.atomic():
            series = DocumentNumberService._ensure_series(
                company, doc_type, gstin_key=gstin_key, fy_label=fy_label
            )
            series = DocumentSeries.objects.select_for_update().get(pk=series.pk)
            return {
                "doc_type": series.doc_type,
                "prefix": series.prefix,
                "next_number": series.next_number,
                "padding": series.padding,
                "gstin_key": series.gstin_key,
                "fy_label": series.fy_label,
                "preview": f"{series.prefix}-{series.next_number:0{series.padding}d}",
            }

    @staticmethod
    @transaction.atomic
    def configure(company, doc_type: str, *, prefix=None, next_number=None, padding=None,
                  gstin=None, on_date=None) -> dict:
        gstin_key, fy_label, _on = DocumentNumberService._resolve_keys(
            company, gstin=gstin, on_date=on_date
        )
        DocumentNumberService._ensure_series(
            company, doc_type, gstin_key=gstin_key, fy_label=fy_label
        )
        series = DocumentSeries.objects.select_for_update().get(
            company=company, doc_type=doc_type, gstin_key=gstin_key, fy_label=fy_label
        )
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
        return DocumentNumberService.peek(
            company, doc_type, gstin=gstin_key or None, on_date=on_date
        )

    @staticmethod
    def _resolve_keys(company, *, gstin=None, on_date=None) -> tuple[str, str, date | None]:
        gstin_key = _gstin_key(gstin)
        if gstin_key:
            fy_label = fy_label_for(company, on_date) if (gstin_key or on_date is not None) else ""
            return gstin_key, fy_label, on_date
        auto_g, auto_fy, auto_on = series_identity(company, on_date=on_date)
        if auto_g or auto_fy:
            return auto_g, auto_fy, auto_on
        fy_label = fy_label_for(company, on_date) if on_date is not None else ""
        return "", fy_label, on_date

    @staticmethod
    def fy_restart_warning(company, doc_type: str, *, gstin_key: str, fy_label: str) -> str | None:
        """PD-03: FY-boundary series starting at 1 is expected — warn, not a gap."""
        if not fy_label:
            return None
        prior = (
            DocumentSeries.objects.filter(
                company=company, doc_type=doc_type, gstin_key=gstin_key or ""
            )
            .exclude(fy_label=fy_label)
            .exclude(fy_label="")
            .exists()
        )
        if not prior:
            return None
        series = DocumentSeries.objects.filter(
            company=company, doc_type=doc_type, gstin_key=gstin_key or "", fy_label=fy_label
        ).first()
        if series is not None and int(series.next_number or 1) != 1:
            return None
        return (
            f"FY series {fy_label} for {doc_type} starts at 1 "
            "(expected year-end restart, not a skipped number)."
        )

    @staticmethod
    def next_number(company, doc_type: str, *, gstin=None, on_date=None) -> str:
        """Allocate next number inside the caller's transaction (nested atomic = savepoint).

        BB-000646: do not SELECT/parse all historical numbers here.
        PD-03: allocate only inside the caller's atomic Complete — a rollback
        rolls the series row back with it.
        """
        if doc_type not in DEFAULT_PREFIXES:
            raise ValueError(f"Unknown document type: {doc_type}")
        gstin_key, fy_label, _on = DocumentNumberService._resolve_keys(
            company, gstin=gstin, on_date=on_date
        )
        with transaction.atomic():
            DocumentNumberService._ensure_series(
                company, doc_type, gstin_key=gstin_key, fy_label=fy_label
            )
            series = DocumentSeries.objects.select_for_update().get(
                company=company,
                doc_type=doc_type,
                gstin_key=gstin_key,
                fy_label=fy_label,
            )
            number = f"{series.prefix}-{series.next_number:0{series.padding}d}"
            series.next_number += 1
            series.save(update_fields=["next_number"])
            return number
