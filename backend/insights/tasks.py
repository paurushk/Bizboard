from celery import shared_task
from django.utils import timezone


def _iter_ai_company_ids():
    from accounts.models import Company

    return Company.objects.filter(ai_features_enabled=True).values_list("pk", flat=True).iterator()


@shared_task
def generate_daily_summaries_task():
    """Thin orchestrator: fan out one task per AI-enabled company."""
    today = timezone.localdate()
    n = 0
    for company_id in _iter_ai_company_ids():
        generate_daily_summary_for_company.delay(str(company_id), today.isoformat())
        n += 1
    return {"ok": True, "date": today.isoformat(), "queued": n}


@shared_task
def generate_daily_summary_for_company(company_id, for_date=None):
    from datetime import date

    from accounts.models import Company
    from insights.services import generate_daily_summary, snapshot_health

    company = Company.objects.get(pk=company_id)
    day = date.fromisoformat(for_date) if for_date else timezone.localdate()
    generate_daily_summary(company, for_date=day, send_email=True)
    snapshot_health(company, as_of=day)
    return {"ok": True, "company_id": str(company.pk), "date": day.isoformat()}


@shared_task
def snapshot_health_scores_task():
    """Thin orchestrator: fan out one health snapshot task per AI-enabled company."""
    today = timezone.localdate()
    n = 0
    for company_id in _iter_ai_company_ids():
        snapshot_health_for_company.delay(str(company_id), today.isoformat())
        n += 1
    return {"ok": True, "date": today.isoformat(), "queued": n}


@shared_task
def snapshot_health_for_company(company_id, as_of=None):
    from datetime import date

    from accounts.models import Company
    from insights.services import snapshot_health

    company = Company.objects.get(pk=company_id)
    day = date.fromisoformat(as_of) if as_of else timezone.localdate()
    snapshot_health(company, as_of=day)
    return {"ok": True, "company_id": str(company.pk), "date": day.isoformat()}


@shared_task
def refresh_cashflow_forecasts_task():
    """Thin orchestrator: fan out one cashflow forecast task per AI-enabled company."""
    n = 0
    for company_id in _iter_ai_company_ids():
        refresh_cashflow_forecast_for_company.delay(str(company_id))
        n += 1
    return {"ok": True, "queued": n}


@shared_task
def refresh_cashflow_forecast_for_company(company_id, horizon=14):
    from accounts.models import Company
    from insights.services import forecast_cashflow

    company = Company.objects.get(pk=company_id)
    forecast_cashflow(company, horizon=int(horizon), persist=True)
    return {"ok": True, "company_id": str(company.pk), "horizon": int(horizon)}
