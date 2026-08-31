"""A-06: compose and persist invoice WhatsApp send (Cloud or wa.me)."""

from __future__ import annotations

from django.utils import timezone

from core.models import Notification
from payments.models import PaymentLinkStatus
from payments.webhook_views import public_frontend_base_url
from sales.models import SalesInvoice


def invoice_pdf_url(invoice: SalesInvoice, request=None) -> str:
    path = f"/api/v1/sales/invoices/{invoice.pk}/pdf/"
    if request is not None:
        return request.build_absolute_uri(path)
    return path


def latest_pay_link_url(invoice: SalesInvoice, request=None) -> str:
    link = (
        invoice.payment_links.exclude(
            status__in=(
                PaymentLinkStatus.CANCELLED,
                PaymentLinkStatus.EXPIRED,
                PaymentLinkStatus.PAID,
            )
        )
        .order_by("-id")
        .first()
    )
    if link is None:
        return ""
    try:
        base = public_frontend_base_url(request)
    except Exception:
        base = ""
    path = f"/pay/{link.token}"
    return f"{base.rstrip('/')}{path}" if base else path


def compose_invoice_whatsapp_body(invoice: SalesInvoice, request=None) -> str:
    pdf = invoice_pdf_url(invoice, request)
    pay = latest_pay_link_url(invoice, request)
    parts = [
        f"Invoice {invoice.number} dated {invoice.invoice_date} from {invoice.company.name}.",
        f"Amount: INR {invoice.grand_total}.",
        f"Download PDF: {pdf}",
    ]
    if pay:
        parts.append(f"Pay online: {pay}")
    return " ".join(parts)


def allow_cloud_for_customer(customer) -> bool:
    return bool(getattr(customer, "whatsapp_opt_in", False))


def persist_invoice_whatsapp(invoice: SalesInvoice, notification: Notification) -> None:
    mode = getattr(notification, "delivery_mode", None)
    now = timezone.now()
    if notification.status == Notification.Status.SENT and mode == "cloud":
        invoice.whatsapp_send_status = SalesInvoice.WhatsAppSendStatus.SENT
        invoice.whatsapp_message_id = (notification.share_link or "")[:128]
        invoice.whatsapp_share_link = ""
        invoice.whatsapp_sent_at = now
    elif notification.status == Notification.Status.FAILED:
        invoice.whatsapp_send_status = SalesInvoice.WhatsAppSendStatus.FAILED
        invoice.whatsapp_message_id = ""
        invoice.whatsapp_share_link = notification.share_link or ""
        invoice.whatsapp_sent_at = now
    elif notification.status == Notification.Status.QUEUED:
        invoice.whatsapp_send_status = SalesInvoice.WhatsAppSendStatus.QUEUED
        invoice.whatsapp_sent_at = now
    else:
        invoice.whatsapp_send_status = SalesInvoice.WhatsAppSendStatus.FALLBACK_LINK
        invoice.whatsapp_message_id = ""
        invoice.whatsapp_share_link = notification.share_link or ""
        invoice.whatsapp_sent_at = now
    invoice.save(
        update_fields=[
            "whatsapp_send_status",
            "whatsapp_message_id",
            "whatsapp_share_link",
            "whatsapp_sent_at",
            "updated_at",
        ]
    )


def whatsapp_offer_payload(invoice: SalesInvoice) -> dict:
    customer = getattr(invoice, "customer", None)
    phone = (getattr(customer, "phone", None) or "").strip()
    return {
        "phone": phone,
        "opt_in": bool(getattr(customer, "whatsapp_opt_in", False)),
        "has_phone": bool(phone),
        "send_status": invoice.whatsapp_send_status,
    }
