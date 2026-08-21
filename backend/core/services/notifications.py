"""
Notification Service — single interface with channel adapters (E0.15).
Email sends via Celery; WhatsApp is a share-link adapter for MVP;
SMS/Push are stubs for later phases.
"""

from urllib.parse import quote

from core.models import Notification


class NotificationService:
    @classmethod
    def send(cls, *, company, channel, recipient, subject="", body="", user=None):
        notification = Notification.objects.create(
            company=company,
            channel=channel,
            recipient=recipient,
            subject=subject,
            body=body,
            created_by=user,
            updated_by=user,
        )
        if channel == Notification.Channel.EMAIL:
            from django.conf import settings

            from core.tasks import send_email_notification

            backend = (getattr(settings, "EMAIL_BACKEND", "") or "").lower()
            env = (getattr(settings, "DJANGO_ENV", "") or "").lower()
            if env in ("production", "staging") and "console" in backend:
                notification.status = Notification.Status.FAILED
                notification.error = "SMTP is not configured (console email backend forbidden)."
                notification.save(update_fields=["status", "error"])
                return notification

            send_email_notification.delay(notification.id)
            # In eager mode (dev/test) the task has already updated the row.
            notification.refresh_from_db()
        elif channel == Notification.Channel.WHATSAPP:
            from core.services.whatsapp import send_whatsapp_template

            template_name = (subject or "").strip()
            if template_name not in ("invoice_ready", "payment_reminder", "invoice_share"):
                template_name = "invoice_share" if "invoice" in (subject or "").lower() else "payment_reminder"
            result = send_whatsapp_template(
                recipient,
                template_name=template_name,
                params=[body] if body else None,
                company=company,
            )
            # BB-000743: surface delivery mode for UI honesty (not persisted).
            notification.delivery_mode = result.mode  # type: ignore[attr-defined]
            if result.mode == "cloud" and result.message_id:
                notification.status = Notification.Status.SENT
                notification.share_link = result.message_id
                notification.error = ""
            else:
                # BB-000282: wa.me fallback — never claim SENT delivery.
                notification.share_link = result.share_link or (
                    f"https://wa.me/{''.join(c for c in recipient if c.isdigit())}"
                    f"?text={quote(body[:1000])}"
                )
                notification.status = Notification.Status.LINK_READY
                raw = result.raw or {}
                if raw.get("error") or raw.get("status_code"):
                    # Cloud was attempted but Graph failed — warn UI of silent fallback.
                    detail = str(raw.get("error") or "")[:500]
                    code = raw.get("status_code")
                    notification.error = (
                        f"WhatsApp Cloud delivery failed"
                        + (f" (HTTP {code})" if code else "")
                        + (f": {detail}" if detail else "")
                        + ". Opened chat-link fallback — not delivered by BizBoard."
                    )[:2000]
                else:
                    notification.error = ""
            notification.save(update_fields=["share_link", "status", "error"])
        else:
            # SMS / Push deferred to Phase 2 — record only.
            notification.status = Notification.Status.QUEUED
            notification.save(update_fields=["status"])
        return notification
