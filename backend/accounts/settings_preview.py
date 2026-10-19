"""SET-22: a dry run of a high-impact Settings change, before the owner saves it.

``POST /api/v1/company/settings-preview/ {"area": "...", "proposed": {...}}`` changes nothing. It
answers with a few structured lines (a key and numbers) that the screen turns into plain words, so
the owner sees what the change would touch before agreeing to it.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import BusinessRuleError
from core.permissions import HasCompany, IsOwner, get_company_user
from core.services.document_numbers import DocumentNumberService

CASH_269ST_LIMIT = Decimal("200000")


def _line(key: str, **params) -> dict:
    return {"key": key, "params": params}


def _open_drafts(company) -> int:
    from sales.models import SalesInvoice

    return SalesInvoice.objects.filter(company=company, status=SalesInvoice.Status.DRAFT).count()


def _series(company, proposed: dict) -> list[dict]:
    lines: list[dict] = []
    for entry in proposed.get("items") or []:
        doc_type = str((entry or {}).get("doc_type") or "")
        try:
            prefix = DocumentNumberService.validate_prefix(entry.get("prefix") if entry.get("prefix") is not None else "X")
        except ValueError as exc:
            raise BusinessRuleError(f"{doc_type}: {exc}") from exc
        try:
            start = int(entry.get("next_number") or 1)
            padding = int(entry.get("padding") or 5)
        except (TypeError, ValueError):
            raise BusinessRuleError(f"{doc_type}: next number and padding must be numbers.") from None
        samples = [f"{prefix}-{n:0{padding}d}" for n in range(start, start + 5)]
        lines.append(_line("series_next", doc_type=doc_type, numbers=", ".join(samples)))
        highest = DocumentNumberService._max_existing_seq(company, doc_type, prefix)
        if highest:
            lines.append(_line("series_highest", doc_type=doc_type, highest=highest))
    return lines


def _gst_registration(company, proposed: dict) -> list[dict]:
    lines: list[dict] = []
    new_type = str(proposed.get("registration_type") or company.registration_type)
    if new_type != company.registration_type:
        lines.append(_line("registration_change", old=company.registration_type, new=new_type))
        if new_type == "UNREGISTERED":
            lines.append(_line("registration_no_tax"))
        drafts = _open_drafts(company)
        if drafts:
            lines.append(_line("drafts_affected", count=drafts))
    new_gstin = str(proposed.get("gstin") or "").strip().upper()
    if new_gstin and new_gstin != (company.gstin or "").strip().upper():
        lines.append(_line("gstin_new_series", gstin=new_gstin))
    return lines


def _stock_rules(company, proposed: dict) -> list[dict]:
    lines: list[dict] = []
    drafts = _open_drafts(company)
    if "negative_stock_policy" in proposed and proposed["negative_stock_policy"] != company.negative_stock_policy:
        lines.append(_line("stock_policy_" + str(proposed["negative_stock_policy"]).lower()))
    for key, line in (
        ("valuation_business_date_order", "valuation_order"),
        ("recompute_tax_on_complete", "recompute_tax"),
    ):
        if key in proposed and bool(proposed[key]) != bool(getattr(company, key, False)):
            lines.append(_line(line, on=bool(proposed[key])))
            if drafts:
                lines.append(_line("drafts_affected", count=drafts))
    return lines


def _cash_269st(company, proposed: dict) -> list[dict]:
    from payments.models import CustomerReceipt, PaymentMode, ReceiptStatus

    mode = str(proposed.get("cash_269st_mode") or company.cash_269st_mode)
    lines = [_line("cash_mode", mode=mode)]
    if mode == "off":
        return lines
    since = timezone.localdate() - timedelta(days=90)
    days = (
        CustomerReceipt.objects.filter(company=company, mode=PaymentMode.CASH, receipt_date__gte=since)
        .exclude(status__in=(ReceiptStatus.VOIDED, ReceiptStatus.REFUNDED))
        .values("customer_id", "receipt_date")
        .annotate(total=Sum("amount"))
        .filter(total__gte=CASH_269ST_LIMIT)
        .count()
    )
    lines.append(_line("cash_days_over_limit", count=days, blocked=mode == "block"))
    return lines


_AREAS = {
    "series": _series,
    "gst_registration": _gst_registration,
    "stock_rules": _stock_rules,
    "cash_269st": _cash_269st,
}


class SettingsPreviewView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def post(self, request):
        area = str(request.data.get("area") or "")
        if area not in _AREAS:
            raise BusinessRuleError("Unknown settings area.")
        proposed = request.data.get("proposed")
        if not isinstance(proposed, dict):
            raise BusinessRuleError("Send the proposed values in 'proposed'.")
        company = get_company_user(request).company
        return Response({"area": area, "lines": _AREAS[area](company, proposed)})
