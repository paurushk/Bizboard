from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail


@shared_task
def send_email_notification(notification_id):
    from core.models import Notification

    notification = Notification.objects.get(pk=notification_id)
    try:
        send_mail(
            subject=notification.subject or "Bizboard",
            message=notification.body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[notification.recipient],
            fail_silently=False,
        )
        notification.status = Notification.Status.SENT
        notification.save(update_fields=["status"])
    except Exception as exc:  # pragma: no cover - depends on SMTP env
        notification.status = Notification.Status.FAILED
        notification.error = str(exc)
        notification.save(update_fields=["status", "error"])
        raise
