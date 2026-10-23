"""WP-PO2 / N9: tenant health score and the month's SaaS numbers, for Bizboard staff only.

``score_company`` gives each company 0–100 from what it actually does (setup, first invoice,
invoicing trend, recent sign-ins, seat use) minus trouble (open P0/P1 support tickets, a past-due
subscription, a failed books check). A weekly task fans out one job per company and stores a
``TenantHealthSnapshot``; Django admin → Support → Tenant health lists them, worst first.

``monthly_metrics`` is the founder's month view: sign-ups, activated (first invoice within 14 days),
trial → paid, paid churn, net revenue retention (from Bizboard's own GST invoices), tickets per 100
tenants and median days to first invoice. ``manage.py saas_metrics --month 2026-10`` prints it.
Practice/demo companies (``is_demo`` / ``is_practice`` when present) are left out.
"""

from __future__ import annotations

import statistics
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

WEIGHTS = {
    "setup": 15, "first_invoice": 15, "activity": 20, "recency": 20, "seats": 10,
    "ticket_penalty": 10, "past_due_penalty": 15, "books_penalty": 10,
}


def _real_companies():
    """Real tenants: not sandbox copies, not erased tombstones."""
    from accounts.models import Company

    return Company.objects.filter(is_sandbox=False, erased_at__isnull=True)


def score_company(company, *, now=None) -> tuple[int, dict]:
    from accounts.models import CompanyUser
    from billing.models import Subscription, TenantActivation
    from billing.quotas import seat_count
    from core.models import TenantSweepResult
    from sales.models import SalesInvoice

    from .models import PlatformTicket

    now = now or timezone.now()
    act = TenantActivation.objects.filter(company=company).first()
    recent = SalesInvoice.objects.filter(company=company, created_at__gte=now - timedelta(days=28)).count()
    before = SalesInvoice.objects.filter(
        company=company, created_at__gte=now - timedelta(days=56), created_at__lt=now - timedelta(days=28),
    ).count()
    last_login = (
        CompanyUser.objects.filter(company=company, is_active=True)
        .exclude(user__last_login__isnull=True)
        .order_by("-user__last_login")
        .values_list("user__last_login", flat=True)
        .first()
    )
    from billing.plan_change import effective_plan

    sub = Subscription.objects.filter(company=company).select_related("plan", "upgrade_plan").first()
    seats_used = seat_count(company)
    seat_limit = int(getattr(effective_plan(sub), "seat_limit", 0) or 0)
    open_urgent = PlatformTicket.objects.filter(
        company=company, severity__in=("P0", "P1"),
    ).exclude(status=PlatformTicket.Status.RESOLVED).count()
    # A SKIPPED night says nothing about the books; the last real check does.
    last_sweep = (
        TenantSweepResult.objects.filter(company=company).exclude(status="SKIPPED").order_by("-started_at").first()
    )

    inputs = {
        "setup": bool(act and act.setup_completed_at),
        "first_invoice": bool(act and act.first_invoice_at),
        "invoices_last_28d": recent,
        "invoices_prior_28d": before,
        "days_since_login": (now - last_login).days if last_login else None,
        "seats_used": seats_used,
        "seat_limit": seat_limit,
        "open_p0_p1_tickets": open_urgent,
        "past_due": bool(sub and sub.status == Subscription.Status.PAST_DUE),
        "books_check_failed": bool(last_sweep and last_sweep.status in ("FAILED", "ERROR")),
    }
    w = WEIGHTS
    score = 0.0
    score += w["setup"] if inputs["setup"] else 0
    score += w["first_invoice"] if inputs["first_invoice"] else 0
    if recent:
        score += w["activity"] * min(1.0, recent / max(before, 1))
    days = inputs["days_since_login"]
    if days is not None:
        score += w["recency"] * (1.0 if days <= 3 else 0.75 if days <= 7 else 0.4 if days <= 14 else 0)
    if seat_limit:
        score += w["seats"] * (1.0 if seats_used / seat_limit >= 0.5 else 0.5)
    elif seats_used:
        score += w["seats"] * 0.5
    score -= w["ticket_penalty"] * open_urgent
    score -= w["past_due_penalty"] if inputs["past_due"] else 0
    score -= w["books_penalty"] if inputs["books_check_failed"] else 0
    return max(0, min(100, round(score))), inputs


def band(score: int) -> str:
    return "healthy" if score >= 70 else "watch" if score >= 40 else "at_risk"


def snapshot_company(company_id: int, *, week: date | None = None):
    from accounts.models import Company

    from .models import TenantHealthSnapshot

    company = Company.objects.get(pk=company_id)
    week = week or (timezone.localdate() - timedelta(days=timezone.localdate().weekday()))
    score, inputs = score_company(company)
    row, _ = TenantHealthSnapshot.objects.update_or_create(
        company=company, week=week, defaults={"score": score, "band": band(score), "inputs": inputs},
    )
    return row


def _month_bounds(month: str) -> tuple[datetime, datetime]:
    y, m = (int(x) for x in month.split("-"))
    start = timezone.make_aware(datetime.combine(date(y, m, 1), time.min))
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return start, timezone.make_aware(datetime.combine(nxt, time.min))


def monthly_metrics(month: str) -> dict:
    """Founder's month view. ``month`` is ``YYYY-MM``. Run inside ``rls_bypass`` (cross-tenant)."""
    from billing.models import PlatformGstInvoice, Subscription, TenantActivation

    from .models import PlatformTicket

    start, end = _month_bounds(month)
    prev_start, _ = _month_bounds((start - timedelta(days=1)).strftime("%Y-%m"))
    companies = _real_companies()
    signups = list(companies.filter(created_at__gte=start, created_at__lt=end).values_list("pk", "created_at"))
    acts = {a.company_id: a for a in TenantActivation.objects.filter(company_id__in=[c for c, _ in signups])}
    activated = sum(
        1 for cid, created in signups
        if acts.get(cid) and acts[cid].first_invoice_at and acts[cid].first_invoice_at - created <= timedelta(days=14)
    )
    days_to_first = [
        (acts[cid].first_invoice_at - created).total_seconds() / 86400
        for cid, created in signups if acts.get(cid) and acts[cid].first_invoice_at
    ]
    from django.db.models import Sum

    invoices = PlatformGstInvoice.objects.filter(kind=PlatformGstInvoice.Kind.INVOICE)
    paid_now = set(invoices.filter(created_at__gte=start, created_at__lt=end).values_list("company_id", flat=True).distinct())
    paid_before = set(
        invoices.filter(created_at__gte=prev_start, created_at__lt=start).values_list("company_id", flat=True).distinct()
    )
    paid_earlier = set(
        invoices.filter(company_id__in=paid_now, created_at__lt=start).values_list("company_id", flat=True).distinct()
    )
    first_paid = paid_now - paid_earlier
    # A month still running has not had every renewal yet: churn and retention are only shown for
    # a closed month (otherwise everyone renewing later this month looks churned).
    partial = end > timezone.now()

    def _rev(qs) -> Decimal:
        return qs.aggregate(t=Sum("total"))["t"] or Decimal("0")

    base = _rev(invoices.filter(created_at__gte=prev_start, created_at__lt=start))
    kept = _rev(invoices.filter(created_at__gte=start, created_at__lt=end, company_id__in=paid_before))
    live_tenants = companies.count() or 1
    tickets = PlatformTicket.objects.filter(created_at__gte=start, created_at__lt=end).count()
    return {
        "month": month,
        "signups": len(signups),
        "activated_14d": activated,
        "trial_to_paid": len(first_paid),
        "paying_tenants": len(paid_now),
        "partial_month": partial,
        "paid_churn": None if partial else len(paid_before - paid_now),
        "net_revenue_retention_pct": None if partial or not base else round(float(kept / base * 100), 1),
        "tickets_per_100_tenants": round(tickets * 100 / live_tenants, 1),
        "median_days_to_first_invoice": round(statistics.median(days_to_first), 1) if days_to_first else None,
        "suspended_now": Subscription.objects.filter(status=Subscription.Status.SUSPENDED).count(),
    }


def time_to_first_invoice_by_week(month: str, *, weeks: int = 12) -> list[dict]:
    """WP-GR2: median days from sign-up to first invoice, by sign-up week, for the ``weeks`` weeks
    ending with ``month``. Run inside ``rls_bypass``."""
    from billing.models import TenantActivation

    _, end = _month_bounds(month)
    start = end - timedelta(weeks=weeks)
    signups = list(_real_companies().filter(created_at__gte=start, created_at__lt=end).values_list("pk", "created_at"))
    acts = {a.company_id: a for a in TenantActivation.objects.filter(company_id__in=[c for c, _ in signups])}
    buckets: dict[date, list] = {}
    for cid, created in signups:
        local = timezone.localtime(created).date()
        week = local - timedelta(days=local.weekday())
        act = acts.get(cid)
        days = (act.first_invoice_at - created).total_seconds() / 86400 if act and act.first_invoice_at else None
        buckets.setdefault(week, []).append(days)
    rows = []
    for week in sorted(buckets):
        done = [d for d in buckets[week] if d is not None]
        rows.append({
            "week": week.isoformat(),
            "signups": len(buckets[week]),
            "invoiced": len(done),
            "median_days": round(statistics.median(done), 1) if done else None,
        })
    return rows
