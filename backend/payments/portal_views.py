"""Customer self-service portal (COMP-003).

Magic link, 15 minutes, reusable until expiry. Read-only except starting the
existing payment-link flow. The request endpoint never says whether a
customer matched.
"""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from core.exceptions import BusinessRuleError
from core.rls import rls_bypass, set_rls_company
from core.services.feature_flags import flag_enabled
from core.throttles import CompanyRateThrottle
from ledgers.services import LedgerService
from masters.models import Customer

from .models import CustomerPortalToken, PaymentLink, PaymentLinkStatus

logger = logging.getLogger(__name__)

PORTAL_TTL = timedelta(minutes=15)
GENERIC_SENT = "If we found a matching customer, we sent a link."
OPEN_LINK_STATUSES = (
    PaymentLinkStatus.CREATED,
    PaymentLinkStatus.SENT,
    PaymentLinkStatus.PARTIALLY_PAID,
)


class CustomerPortalReadThrottle(AnonRateThrottle):
    # F1-007b: read from settings' DEFAULT_THROTTLE_RATES["customer_portal_read"]
    # via `scope`, matching CompanyRateThrottle's pattern below — a hardcoded
    # `rate` here would make the settings entry dead configuration.
    scope = "customer_portal_read"


def _portal_url(token: str) -> str:
    from payments.webhook_views import public_frontend_base_url

    return f"{public_frontend_base_url()}/portal/{token}"


def _load_token(token: str):
    with rls_bypass():
        row = (
            CustomerPortalToken.objects.select_related("company", "customer")
            .filter(token=token)
            .first()
        )
    if row is None or row.expires_at <= timezone.now():
        return None
    if not flag_enabled(row.company, "ENABLE_CUSTOMER_PORTAL"):
        return None
    from core.services.flag_observability import log_flag_event

    log_flag_event(row.company, "ENABLE_CUSTOMER_PORTAL", "portal_opened")
    set_rls_company(row.company_id)
    return row


def _touch(row):
    row.last_used_at = timezone.now()
    row.save(update_fields=["last_used_at", "updated_at"])


class CustomerPortalRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [CompanyRateThrottle]
    throttle_scope = "customer_portal_request"

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        phone = "".join(c for c in (request.data.get("phone") or "") if c.isdigit())
        if not email and not phone:
            return Response({"detail": "Email or phone is required."}, status=status.HTTP_400_BAD_REQUEST)
        with rls_bypass():
            qs = Customer.objects.select_related("company")
            if email:
                matches = list(qs.filter(email__iexact=email))
                channel = CustomerPortalToken.Channel.EMAIL
            else:
                matches = [c for c in qs.exclude(phone="") if "".join(ch for ch in c.phone if ch.isdigit()) == phone]
                channel = CustomerPortalToken.Channel.WHATSAPP
        debug_token = None
        for customer in matches:
            if not flag_enabled(customer.company, "ENABLE_CUSTOMER_PORTAL"):
                continue
            set_rls_company(customer.company_id)
            row = CustomerPortalToken.objects.create(
                company=customer.company,
                customer=customer,
                token=secrets.token_urlsafe(32)[:64],
                requested_via=channel,
                expires_at=timezone.now() + PORTAL_TTL,
            )
            # F1-007: delivery (SMTP/WhatsApp Cloud round trip) must not run
            # on the request path — an unmatched phone/email returns almost
            # immediately while a matched one would pay for a live network
            # call first, a timing side channel even though the response
            # body is identical either way.
            from payments.tasks import deliver_customer_portal_link

            deliver_customer_portal_link.delay(row.id, company_id=row.company_id)
            if settings.PORTAL_DEBUG_ECHO:
                # F1-011: same posture as OTP_DEBUG_ECHO — an explicit,
                # production-hard-rejected opt-in, not implied by DEBUG.
                debug_token = row.token
        payload = {"detail": GENERIC_SENT}
        if debug_token is not None:
            payload["debug_token"] = debug_token
        return Response(payload)


def _deliver(row: CustomerPortalToken) -> None:
    url = _portal_url(row.token)
    customer = row.customer
    if row.requested_via == CustomerPortalToken.Channel.EMAIL:
        if not customer.email:
            logger.info(
                "customer portal email skipped company=%s customer=%s reason=no_email",
                row.company_id,
                customer.id,
            )
            return
        send_mail(
            subject="Your invoices",
            message=f"View your invoices: {url}\nThis link expires in 15 minutes.",
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[customer.email],
            fail_silently=False,
        )
        logger.info(
            "customer portal link emailed company=%s customer=%s",
            row.company_id,
            customer.id,
        )
        return
    if not customer.whatsapp_opt_in:
        logger.info(
            "customer portal WhatsApp skipped company=%s customer=%s reason=no_opt_in",
            row.company_id,
            customer.id,
        )
        return
    from core.services.whatsapp import send_whatsapp_template

    result = send_whatsapp_template(
        customer.phone,
        "invoice_share",
        [url],
        company=row.company,
        allow_cloud=True,
    )
    logger.info(
        "customer portal WhatsApp company=%s customer=%s mode=%s",
        row.company_id,
        customer.id,
        result.mode,
    )


class CustomerPortalView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [CustomerPortalReadThrottle]

    def get(self, request, token):
        row = _load_token(token)
        if row is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        _touch(row)
        from sales.models import SalesInvoice
        from sales.status_semantics import OPEN_RECEIVABLE_STATUSES

        invoices = (
            SalesInvoice.objects.filter(
                company=row.company,
                customer=row.customer,
                status__in=OPEN_RECEIVABLE_STATUSES,
            )
            .order_by("-invoice_date", "-id")[:50]
        )
        payload = []
        for inv in invoices:
            outstanding = LedgerService.sales_invoice_outstanding(inv)
            link = (
                PaymentLink.objects.filter(
                    company=row.company,
                    sales_invoice=inv,
                    status__in=OPEN_LINK_STATUSES,
                )
                .order_by("-id")
                .first()
            )
            payload.append({
                "id": inv.id,
                "number": inv.number,
                "invoice_date": inv.invoice_date,
                "status": inv.status,
                "amount": inv.grand_total,
                "outstanding": outstanding,
                "pay_path": f"/pay/{link.token}" if link is not None else None,
            })
        return Response({
            "customer_name": row.customer.name,
            "expires_at": row.expires_at,
            "invoices": payload,
        })


class CustomerPortalPdfView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [CustomerPortalReadThrottle]

    def get(self, request, token, invoice_id):
        row = _load_token(token)
        if row is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        _touch(row)
        from sales.models import SalesInvoice
        from sales.pdf import render_gst_tax_invoice

        invoice = SalesInvoice.objects.filter(
            company=row.company, customer=row.customer, pk=invoice_id
        ).first()
        if invoice is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        content = render_gst_tax_invoice(invoice, copy="ORIGINAL")
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{invoice.number or invoice.id}.pdf"'
        return response


class CustomerPortalPayView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [CustomerPortalReadThrottle]

    def post(self, request, token, invoice_id):
        row = _load_token(token)
        if row is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        _touch(row)
        from sales.models import SalesInvoice

        invoice = SalesInvoice.objects.filter(
            company=row.company, customer=row.customer, pk=invoice_id
        ).first()
        if invoice is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        outstanding = LedgerService.sales_invoice_outstanding(invoice)
        if outstanding <= 0:
            return Response({"detail": "Nothing is outstanding on this invoice."}, status=status.HTTP_400_BAD_REQUEST)
        link = (
            PaymentLink.objects.filter(
                company=row.company,
                sales_invoice=invoice,
                status__in=OPEN_LINK_STATUSES,
            )
            .order_by("-id")
            .first()
        )
        if link is None:
            from .services import PaymentService

            try:
                link = PaymentService.create_payment_link(
                    company=row.company,
                    amount=outstanding,
                    sales_invoice=invoice,
                    customer=row.customer,
                )
            except BusinessRuleError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"pay_path": f"/pay/{link.token}"})
