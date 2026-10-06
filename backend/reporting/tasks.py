"""Scheduled IMS reminders."""

from celery import shared_task


@shared_task
def send_itc_expiry_digests_task() -> dict:
    from reporting.ims import send_itc_expiry_digests

    return send_itc_expiry_digests()


@shared_task
def compile_gst_return_task(company_id: int, period: str, return_type: str = "GSTR1") -> dict:
    """Build a GST worksheet off the request worker and cache it (BUG-PERF-003)."""
    from accounts.models import Company
    from reporting.gst_returns import build_gstr1, build_gstr3b, persist_snapshot

    company = Company.objects.get(pk=company_id)
    kind = (return_type or "GSTR1").upper().replace("-", "")
    if kind == "GSTR3B":
        payload = build_gstr3b(company, period)
        label = "GSTR3B"
    else:
        payload = build_gstr1(company, period)
        label = "GSTR1"
    snap = persist_snapshot(company, label, period, payload)
    return {"snapshot_id": snap.pk, "return_type": label, "period": period}
