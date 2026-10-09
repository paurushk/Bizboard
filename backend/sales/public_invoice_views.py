"""Anonymous invoice page. Looks up the token with RLS bypass, then re-scopes."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import F
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from core.rls import rls_bypass, set_rls_company
from ledgers.services import LedgerService
from payments.portal_views import CustomerPortalReadThrottle

from .models import InvoicePublicLink, SalesInvoice


def _public_headers(response):
    response["Referrer-Policy"] = "no-referrer"
    response["Cache-Control"] = "no-store"
    response["X-Robots-Tag"] = "noindex"
    return response


def _not_found():
    return _public_headers(Response({"detail": "Not found."}, status=404))


def _load_link(token: str):
    with rls_bypass():
        row = (
            InvoicePublicLink.objects.select_related(
                "company", "invoice", "invoice__customer", "invoice__company",
            )
            .filter(token=token)
            .first()
        )
    if row is None:
        return None
    if row.expires_at is not None and row.expires_at <= timezone.now():
        return None
    invoice = row.invoice
    # A revoked token is a generic 404. Cancelling an invoice does not revoke,
    # so the public page can say Cancelled instead of pretending it never existed.
    if row.revoked_at is not None:
        return None
    set_rls_company(row.company_id)
    return row


def _open_pay_path(invoice) -> str:
    from payments.models import PaymentLink, PaymentLinkStatus

    link = (
        PaymentLink.objects.filter(
            sales_invoice=invoice,
            status__in=(
                PaymentLinkStatus.CREATED,
                PaymentLinkStatus.SENT,
                PaymentLinkStatus.PARTIALLY_PAID,
            ),
        )
        .order_by("-id")
        .first()
    )
    return f"/pay/{link.token}" if link else ""


_PREVIEW_BOTS = (
    "bot", "crawler", "spider", "preview", "whatsapp", "facebookexternalhit",
    "slack", "telegram", "skype", "linkedin", "embedly", "curl", "wget",
)


def _is_link_preview(request) -> bool:
    agent = (request.META.get("HTTP_USER_AGENT") or "").lower()
    return not agent or any(token in agent for token in _PREVIEW_BOTS)


def _touch(row, request) -> None:
    """Count a real person opening the link, not a chat app unfurling it."""
    if _is_link_preview(request):
        return
    InvoicePublicLink.objects.filter(pk=row.pk).update(view_count=F("view_count") + 1)


def _payload(invoice) -> dict:
    customer = invoice.customer
    company = invoice.company
    stamp = getattr(invoice, "company_gstin", None)
    seller_gstin = (getattr(stamp, "gstin", None) or "") if stamp is not None else (company.gstin or "")
    seller_name = ((getattr(stamp, "legal_name", None) or "") if stamp is not None else "") or company.name
    try:
        unpaid = Decimal(str(LedgerService.sales_invoice_outstanding(invoice) or 0))
    except (TypeError, ValueError, ArithmeticError):
        unpaid = Decimal(str(invoice.grand_total or 0))
    paid = max(Decimal(str(invoice.grand_total or 0)) - unpaid, Decimal("0"))
    lines = []
    for item in invoice.items.select_related("product").all():
        tax = (
            Decimal(str(item.cgst or 0))
            + Decimal(str(item.sgst or 0))
            + Decimal(str(item.igst or 0))
            + Decimal(str(getattr(item, "cess", 0) or 0))
        )
        lines.append({
            "name": (item.description or "").strip() or item.product.name,
            "hsn": item.hsn_code or "",
            "qty": item.quantity,
            "rate": item.unit_price,
            "tax": tax,
            "amount": item.line_total,
        })
    return {
        "seller_name": seller_name,
        "seller_gstin": seller_gstin,
        "number": invoice.number,
        "invoice_date": invoice.invoice_date,
        "status": invoice.status,
        "bill_to": {
            "name": customer.name,
            "address": customer.billing_address or "",
            "gstin": customer.gstin or "",
            "state": customer.state or "",
        },
        "ship_to": {
            "name": customer.name,
            "address": customer.shipping_address or customer.billing_address or "",
        },
        "place_of_supply": (invoice.filing_place_of_supply or customer.state or ""),
        "lines": lines,
        "totals": {
            "taxable_total": invoice.taxable_total,
            "cgst": invoice.cgst_total,
            "sgst": invoice.sgst_total,
            "igst": invoice.igst_total,
            "cess": getattr(invoice, "cess_total", 0),
            "round_off": invoice.round_off,
            "grand_total": invoice.grand_total,
        },
        "paid": paid,
        "unpaid": unpaid,
        "pay_path": _open_pay_path(invoice) if unpaid > Decimal("0.01") else "",
    }


class PublicInvoiceView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [CustomerPortalReadThrottle]

    def get(self, request, token):
        row = _load_link(token)
        if row is None:
            return _not_found()
        _touch(row, request)
        return _public_headers(Response(_payload(row.invoice)))


class PublicInvoicePdfView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [CustomerPortalReadThrottle]

    def get(self, request, token):
        row = _load_link(token)
        if row is None:
            return _not_found()
        _touch(row, request)
        from .pdf import render_gst_tax_invoice

        invoice = row.invoice
        # A cancelled bill must not download as a valid ORIGINAL.
        if invoice.status == SalesInvoice.Status.CANCELLED:
            return _public_headers(Response({"detail": "This invoice was cancelled."}, status=410))
        # Rendered fresh each time: the PDF prints paid/balance, and a stored file would
        # show the balance as it was when the invoice was completed.
        content = render_gst_tax_invoice(invoice, copy="ORIGINAL")
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{invoice.number or invoice.pk}.pdf"'
        return _public_headers(response)


class PublicInvoicePayThrottle(AnonRateThrottle):
    """Minting a payment link is a write; allow a sixth of the read rate."""

    scope = "public_invoice_pay"

    def get_rate(self):
        rates = self.THROTTLE_RATES
        if rates.get(self.scope):
            return rates[self.scope]
        base = rates.get("customer_portal_read")
        try:
            count, _, period = str(base).partition("/")
            return f"{max(1, int(count) // 6)}/{period}"
        except (TypeError, ValueError):
            return base


class PublicInvoicePayView(APIView):
    """Mint or reuse /pay/:token for the balance on this public invoice."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PublicInvoicePayThrottle]

    def post(self, request, token):
        from django.conf import settings

        from core.exceptions import BusinessRuleError
        from payments.services import PaymentService

        row = _load_link(token)
        if row is None:
            return _not_found()
        invoice = row.invoice
        existing = _open_pay_path(invoice)
        if existing:
            return _public_headers(Response({"path": existing}))
        if invoice.status != SalesInvoice.Status.COMPLETED:
            return _public_headers(Response({"detail": "Nothing to pay."}, status=400))
        try:
            outstanding = LedgerService.sales_invoice_outstanding(invoice)
        except (TypeError, ValueError, ArithmeticError):
            outstanding = invoice.grand_total
        if outstanding is None or Decimal(str(outstanding)) <= Decimal("0.01"):
            return _public_headers(Response({"detail": "Nothing to pay."}, status=400))
        django_env = (getattr(settings, "DJANGO_ENV", "") or "").lower()
        provider = "sandbox" if django_env in ("test", "development", "local") else None
        try:
            link = PaymentService.create_payment_link(
                company=invoice.company,
                amount=Decimal(str(outstanding)),
                sales_invoice=invoice,
                provider=provider,
                notes="Public invoice",
            )
        except BusinessRuleError as exc:
            return _public_headers(Response({"detail": str(exc.detail)}, status=400))
        return _public_headers(Response({"path": f"/pay/{link.token}"}))
