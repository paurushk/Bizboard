"""Anonymous quotation page and PDF. Looks the token up with RLS bypass, then re-scopes.

Answers (closure plan D-19): unknown, revoked, cancelled or rejected -> 404;
expired (the link or the validity date) -> 410; a converted quote stays readable
until its validity date.
"""

from __future__ import annotations

from django.db.models import F
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.rls import rls_bypass, set_rls_company
from payments.portal_views import CustomerPortalReadThrottle

from .models import Quotation, QuotationPublicLink
from .public_invoice_views import _is_link_preview, _public_headers

GONE_MESSAGE = "This quotation has expired. Please ask for a new one."


def _not_found():
    return _public_headers(Response({"detail": "Not found."}, status=404))


def _gone():
    return _public_headers(Response({"detail": GONE_MESSAGE}, status=410))


def _load(token: str):
    """Return ``(row, None)`` or ``(None, error_response)``."""
    with rls_bypass():
        row = (
            QuotationPublicLink.objects.select_related("company", "quotation", "quotation__customer")
            .filter(token=token)
            .first()
        )
    if row is None or row.revoked_at is not None:
        return None, _not_found()
    quotation = row.quotation
    if quotation.status in (Quotation.Status.CANCELLED, Quotation.Status.REJECTED):
        return None, _not_found()
    if row.expires_at is not None and row.expires_at <= timezone.now():
        return None, _gone()
    if (
        quotation.status in Quotation.OPEN_STATUSES
        and quotation.valid_until is not None
        and quotation.valid_until < timezone.localdate()
    ):
        return None, _gone()
    set_rls_company(row.company_id)
    return row, None


def _touch(row, request) -> None:
    if _is_link_preview(request):
        return
    QuotationPublicLink.objects.filter(pk=row.pk).update(view_count=F("view_count") + 1)


def _payload(quotation) -> dict:
    company = quotation.company
    customer = quotation.customer
    stamp = quotation.company_gstin
    seller_name = ((getattr(stamp, "legal_name", None) or "") if stamp is not None else "") or company.name
    lines = [
        {
            "name": (item.description or "").strip() or item.product.name,
            "hsn": item.hsn_code or "",
            "qty": item.quantity,
            "rate": item.unit_price,
            "discount_percent": item.discount_percent,
            "amount": item.line_total,
        }
        for item in quotation.items.select_related("product").order_by("id")
    ]
    return {
        "seller_name": seller_name,
        "number": quotation.number,
        "status": quotation.status,
        "quotation_date": quotation.quotation_date,
        "valid_until": quotation.valid_until,
        "bill_to": {"name": customer.name, "address": customer.billing_address or ""},
        "lines": lines,
        "notes": quotation.notes,
        "terms": quotation.terms_text,
        "totals": {
            "taxable_total": quotation.taxable_total,
            "cgst": quotation.cgst_total,
            "sgst": quotation.sgst_total,
            "igst": quotation.igst_total,
            "cess": getattr(quotation, "cess_total", 0),
            "additional_charges": quotation.additional_charges,
            "invoice_discount": quotation.invoice_discount,
            "round_off": quotation.round_off,
            "grand_total": quotation.grand_total,
        },
    }


class PublicQuotationView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [CustomerPortalReadThrottle]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, token):
        row, error = _load(token)
        if error is not None:
            return error
        _touch(row, request)
        return _public_headers(Response(_payload(row.quotation)))


class PublicQuotationPdfView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [CustomerPortalReadThrottle]

    @extend_schema(responses=OpenApiTypes.BINARY)
    def get(self, request, token):
        row, error = _load(token)
        if error is not None:
            return error
        _touch(row, request)
        from .pdf.note_documents import render_quotation

        quotation = row.quotation
        content = render_quotation(quotation)
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{quotation.number or quotation.pk}.pdf"'
        return _public_headers(response)
