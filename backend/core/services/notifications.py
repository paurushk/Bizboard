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
            from core.tasks import send_email_notification

            send_email_notification.delay(notification.id)
            # In eager mode (dev/test) the task has already updated the row.
            notification.refresh_from_db()
        elif channel == Notification.Channel.WHATSAPP:
            phone = "".join(c for c in recipient if c.isdigit())
            notification.share_link = f"https://wa.me/{phone}?text={quote(body[:1000])}"
            notification.status = Notification.Status.SENT
            notification.save(update_fields=["share_link", "status"])
        else:
            # SMS / Push deferred to Phase 2 — record only.
            notification.status = Notification.Status.QUEUED
            notification.save(update_fields=["status"])
        return notification
