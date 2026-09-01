"""Public payment link + gateway webhook views (BB-000506)."""


from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from core.exceptions import BusinessRuleError

from .models import PaymentLink, PaymentLinkStatus
from .services import PaymentService


def public_frontend_base_url(request=None) -> str:
    """BB-000292: never trust Origin/Referer; require FRONTEND_URL outside DEBUG."""
    from django.conf import settings

    base = (getattr(settings, "FRONTEND_URL", "") or "").rstrip("/")
    if base:
        return base
    if getattr(settings, "DEBUG", False):
        return "http://localhost:5173"
    raise BusinessRuleError("FRONTEND_URL must be configured for payment link callbacks.")


class PublicPayThrottle(AnonRateThrottle):
    # BB-000514: public tokenized pay — keep tight vs anon default.
    rate = "20/min"


class PaymentWebhookThrottle(AnonRateThrottle):
    rate = "120/min"


@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([PublicPayThrottle])
def public_payment_link(request, token: str):
    link = (
        PaymentLink.objects.select_related("company", "customer", "sales_invoice")
        .filter(token=token)
        .first()
    )
    if not link:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    from payments.holding import link_payment_state, link_shows_paid

    received = link_shows_paid(link)
    payment_state = link_payment_state(link)
    if link.status == PaymentLinkStatus.CANCELLED and not received:
        return Response({"detail": "This payment link was cancelled."}, status=status.HTTP_410_GONE)
    if link.expires_at and link.expires_at < timezone.now() and not received:
        if link.status != PaymentLinkStatus.EXPIRED:
            link.status = PaymentLinkStatus.EXPIRED
            link.save(update_fields=["status", "updated_at"])
        return Response({"detail": "This payment link has expired."}, status=status.HTTP_410_GONE)
    company = link.company
    from payments.upi import upi_qr_fields

    upi = upi_qr_fields(
        upi_id=company.upi_id,
        amount=link.amount,
        note=link.sales_invoice.number if link.sales_invoice_id else link.token[:12],
        payee_name=company.legal_name or company.name,
    )
    return Response(
        {
            "token": link.token,
            "status": link.status,
            "amount": str(link.amount),
            "allow_partial": link.allow_partial,
            "expires_at": link.expires_at,
            "company_name": company.legal_name or company.name,
            "provider": link.provider,
            "provider_short_url": link.provider_short_url,
            "upi": upi,
            "paid": received,
            "payment_state": payment_state,
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([PaymentWebhookThrottle])
def payment_webhook(request, provider: str):
    """BB-000004/196/205/258/265: settle only via verified signature + payment_link identity."""
    from payments.gateway import (
        decrypt_gateway_credentials,
        get_adapter,
        parse_webhook_probe,
        sandbox_forbidden_env,
    )

    provider = (provider or "").lower().strip()
    body = request.body
    query_company_id = request.query_params.get("company_id")

    if provider == "sandbox" and sandbox_forbidden_env():
        return Response(
            {"detail": "Sandbox payment webhooks are disabled in production/staging."},
            status=status.HTTP_403_FORBIDDEN,
        )

    event_probe = parse_webhook_probe(provider, body)

    link = None
    if event_probe and getattr(event_probe, "payment_link_id", None):
        qs = PaymentLink.objects.filter(
            provider_link_id=event_probe.payment_link_id,
            provider=provider,
        )
        count = qs.count()
        if count > 1:
            return Response(
                {"detail": "Ambiguous payment_link_id."},
                status=status.HTTP_409_CONFLICT,
            )
        link = qs.first()

    if link is None:
        return Response(
            {"detail": "payment_link_id required in signed payload; amount-only matching is disabled."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    company = link.company
    if query_company_id and str(company.id) != str(query_company_id):
        return Response(
            {"detail": "company_id does not match payment link."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    creds = decrypt_gateway_credentials(company.payment_gateway_credentials_encrypted or "")

    if provider != "sandbox" and not creds:
        return Response(
            {"detail": "Payment gateway credentials are not configured."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        adapter = get_adapter(
            provider,
            creds if provider != "sandbox" else None,
            company_id=company.id,
        )
    except BusinessRuleError as exc:
        return Response({"detail": str(exc.detail)}, status=status.HTTP_400_BAD_REQUEST)

    headers = {k: v for k, v in request.headers.items()}
    if not adapter.verify_webhook(headers=headers, body=body):
        return Response({"detail": "Invalid signature."}, status=status.HTTP_401_UNAUTHORIZED)

    event = adapter.parse_webhook(body=body)
    if not event or not event.provider_payment_id:
        return Response({"detail": "Unrecognized payload."}, status=status.HTTP_400_BAD_REQUEST)

    if event.payment_link_id and event.payment_link_id != link.provider_link_id:
        return Response({"detail": "payment_link_id mismatch."}, status=status.HTTP_400_BAD_REQUEST)

    if event.status == "REFUNDED":
        from .models import GatewayPayment

        gp = GatewayPayment.objects.filter(
            company=company,
            provider=provider,
            provider_payment_id=event.provider_payment_id,
        ).first()
        if gp is None:
            return Response({"ok": True, "ignored": True, "status": event.status})
        try:
            gp = PaymentService.refund_gateway_payment(
                gateway_payment=gp,
                amount=getattr(event, "amount", None),
                reason="webhook",
                skip_gateway=True,
            )
        except BusinessRuleError as exc:
            return Response({"detail": str(exc.detail)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True, "gateway_payment_id": gp.id, "status": gp.status})

    if event.status != "CAPTURED":
        return Response({"ok": True, "ignored": True, "status": event.status})

    from payments.holding import (
        err_detail,
        gateway_holding_enabled,
        park_gateway_payment,
    )
    from payments.models import GatewayPayment, GatewayPaymentStatus

    try:
        gp = PaymentService.finalize_gateway_payment(
            company=company,
            provider=provider,
            provider_payment_id=event.provider_payment_id,
            amount=event.amount,
            fee=event.fee,
            payment_link=link,
            raw_payload=event.raw,
        )
    except BusinessRuleError as exc:
        gp = GatewayPayment.objects.filter(
            company=company,
            provider=provider,
            provider_payment_id=event.provider_payment_id,
        ).first()
        if gateway_holding_enabled():
            if gp is None:
                gp = GatewayPayment.objects.create(
                    company=company,
                    provider=provider,
                    provider_payment_id=event.provider_payment_id,
                    amount=event.amount,
                    fee=event.fee,
                    status=GatewayPaymentStatus.CREATED,
                    payment_link=link,
                    raw_payload=event.raw,
                )
            if gp.status != GatewayPaymentStatus.CAPTURED:
                park_gateway_payment(gp, "BOOKS_ERROR", err_detail(exc))
            return Response({"ok": True, "gateway_payment_id": gp.id, "status": gp.status})
        return Response({"detail": str(exc.detail)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"ok": True, "gateway_payment_id": gp.id, "status": gp.status})
