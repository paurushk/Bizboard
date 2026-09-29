"""Scheduled IMS reminders."""

from celery import shared_task


@shared_task
def send_itc_expiry_digests_task() -> dict:
    from reporting.ims import send_itc_expiry_digests

    return send_itc_expiry_digests()
