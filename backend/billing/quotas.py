"""Plan usage metering: monthly completes, stored bytes, API rate.

Limits of 0 mean unlimited. Enforcement is fail-closed with HelpCode.PLAN_QUOTA_EXCEEDED
so Complete / upload cannot silently proceed past the plan.
"""

from __future__ import annotations

from django.core.cache import cache
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.help_codes import HelpCode

from .models import Plan
from .services import subscription_for_company

USER_STORAGE_KINDS = ("ATTACHMENT", "LOGO", "IMPORT", "EXPORT")

# Short-TTL cache for the per-request throttle hot path only (api_rate_per_minute).
# Plan limits change rarely, so a brief staleness window is fine there; the
# quota-enforcement path below (assert_complete_allowed/assert_storage_allowed)
# never uses this cache and always re-derives from the DB.
_RATE_CACHE_TTL_SECONDS = 30
_RATE_CACHE_PREFIX = "billing:api_rate_per_minute:"


def _plan_for(company, sub=None) -> Plan | None:
    if company is None:
        return None
    if getattr(company, "billing_override_active", False):
        return None
    if sub is None:
        sub = subscription_for_company(company)
    if sub is None or sub.plan_id is None:
        return None
    return sub.plan


def monthly_complete_count(company) -> int:
    from purchases.models import PurchaseInvoice
    from sales.models import SalesInvoice

    now = timezone.now()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    sales_n = SalesInvoice.objects.filter(
        company=company, status=SalesInvoice.Status.COMPLETED, completed_at__gte=start
    ).count()
    purchase_n = PurchaseInvoice.objects.filter(
        company=company, status=PurchaseInvoice.Status.COMPLETED, completed_at__gte=start
    ).count()
    return sales_n + purchase_n


def storage_bytes_used(company) -> int:
    from django.db.models import Sum

    from core.models import FileAsset

    total = (
        FileAsset.objects.filter(company=company, kind__in=USER_STORAGE_KINDS)
        .aggregate(total=Sum("size"))
        .get("total")
    )
    return int(total or 0)


def seat_count(company) -> int:
    from accounts.models import CompanyUser

    return CompanyUser.objects.filter(company=company, is_active=True).count()


def assert_complete_allowed(company) -> None:
    plan = _plan_for(company)
    if plan is None:
        return
    limit = int(getattr(plan, "monthly_complete_limit", 0) or 0)
    if limit <= 0:
        return
    # Serialize concurrent Complete calls for this company so the count-then-
    # compare below can't race: caller (sales/purchases complete()) already
    # runs inside @transaction.atomic, so this lock is held until that
    # transaction commits/rolls back, making the check-and-increment atomic
    # across concurrent requests. Only taken when a limit is actually active,
    # so unlimited-plan tenants (the common case) pay no extra lock cost.
    from accounts.models import Company

    Company.objects.select_for_update().get(pk=company.pk)
    used = monthly_complete_count(company)
    if used >= limit:
        raise BusinessRuleError(
            f"Monthly complete limit of {limit} reached for the current plan.",
            code=HelpCode.PLAN_QUOTA_EXCEEDED,
        )


def assert_storage_allowed(company, additional_bytes: int = 0) -> None:
    plan = _plan_for(company)
    if plan is None:
        return
    limit = int(getattr(plan, "storage_bytes_limit", 0) or 0)
    if limit <= 0:
        return
    used = storage_bytes_used(company) + max(0, int(additional_bytes or 0))
    if used > limit:
        raise BusinessRuleError(
            f"Storage limit of {limit} bytes reached for the current plan.",
            code=HelpCode.PLAN_QUOTA_EXCEEDED,
        )


def api_rate_per_minute(company, *, plan=None) -> int:
    if plan is not None:
        return int(getattr(plan, "api_rate_per_minute", 0) or 0)
    if company is None:
        return 0
    # Hot path: this runs on every throttled API request via
    # core.throttles.TenantPlanRateThrottle (a DEFAULT_THROTTLE_CLASSES
    # entry), so cache the resolved rate briefly instead of hitting
    # Subscription+Plan on every single call. Correctness-sensitive quota
    # checks (assert_complete_allowed/assert_storage_allowed) never call
    # through this cache.
    if getattr(company, "billing_override_active", False):
        return 0
    cache_key = f"{_RATE_CACHE_PREFIX}{company.pk}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    resolved_plan = _plan_for(company)
    rate = int(getattr(resolved_plan, "api_rate_per_minute", 0) or 0) if resolved_plan else 0
    cache.set(cache_key, rate, _RATE_CACHE_TTL_SECONDS)
    return rate


def usage_snapshot(company, *, plan=None, sub=None) -> dict:
    if plan is None:
        plan = _plan_for(company, sub=sub)
    completes_limit = int(getattr(plan, "monthly_complete_limit", 0) or 0) if plan else 0
    storage_limit = int(getattr(plan, "storage_bytes_limit", 0) or 0) if plan else 0
    seat_limit = int(getattr(plan, "seat_limit", 0) or 0) if plan else 0
    return {
        "seats": {"limit": seat_limit, "used": seat_count(company) if company else 0},
        "completes": {"limit": completes_limit, "used": monthly_complete_count(company) if company else 0},
        "storage_bytes": {"limit": storage_limit, "used": storage_bytes_used(company) if company else 0},
        "api_rate_per_minute": api_rate_per_minute(company, plan=plan) if company else 0,
    }
