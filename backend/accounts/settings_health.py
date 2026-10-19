"""SET-18: the Settings health checklist.

One small read-only endpoint so the ``/settings`` hub can say what still needs attention, computed
on the server from the same data the screens use. It never changes anything.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import HasCompany, IsOwner, get_company_user

OK, TODO, WARN = "ok", "todo", "warn"
LICENCE_WARN_DAYS = 30


def _item(item_id: str, status: str, path: str, **extra) -> dict:
    return {"id": item_id, "status": status, "path": path, **extra}


def settings_health(company) -> list[dict]:
    from accounts.models import CompanyStatutoryLicence, CompanyUser, InviteJti
    from payments.gateway import decrypt_gateway_credentials, keys_accepted_for
    from payments.models import BankAccount

    items: list[dict] = []

    has_gstin = bool(company.gstin) or company.gstins.filter(is_active=True).exclude(gstin="").exists()
    items.append(_item("gstin", OK if has_gstin else TODO, "/settings/gst"))

    # The owner has ticked "I have checked my GST details" (recorded when a new GSTIN is saved).
    if has_gstin:
        confirmed = company.tax_profile_confirmed_at is not None
        items.append(_item("taxprofile", OK if confirmed else WARN, "/settings/gst"))

    has_default_bank = BankAccount.objects.filter(company=company, is_active=True, is_default=True).exists()
    items.append(_item("bank", OK if has_default_bank else TODO, "/settings/bank-accounts"))

    today = timezone.localdate()
    soon = today + timedelta(days=LICENCE_WARN_DAYS)
    licences = CompanyStatutoryLicence.objects.filter(company=company, is_active=True)
    total = licences.count()
    if total == 0:
        items.append(_item("licences", OK, "/settings/statutory-licences", count=0))
    else:
        expired = licences.filter(valid_upto__lt=today).count()
        expiring = licences.filter(valid_upto__gte=today, valid_upto__lte=soon).count()
        items.append(
            _item(
                "licences",
                WARN if expired or expiring else OK,
                "/settings/statutory-licences",
                count=total,
                expired=expired,
                expiring=expiring,
            )
        )

    if not company.payment_gateway_credentials_encrypted:
        items.append(_item("gateway", TODO, "/settings/payment-gateway", configured=False))
    else:
        provider = company.payment_gateway_provider or "razorpay"
        creds = decrypt_gateway_credentials(company.payment_gateway_credentials_encrypted)
        verified = keys_accepted_for(creds, provider)
        items.append(_item("gateway", OK if verified else WARN, "/settings/payment-gateway", configured=True))

    waiting = CompanyUser.objects.filter(company=company, is_active=False, user__last_login__isnull=True)
    live = InviteJti.objects.filter(
        membership__in=waiting, consumed_at__isnull=True, expires_at__gt=timezone.now()
    ).values_list("membership_id", flat=True)
    expired_invites = waiting.exclude(pk__in=set(live)).count()
    items.append(
        _item(
            "users",
            WARN if expired_invites else OK,
            "/settings/users",
            pending=len(set(live)),
            expired=expired_invites,
        )
    )
    # Settings problems that are easy to miss (SET-23): a failed automatic backup, a quiet gateway,
    # a plan limit about to be reached.
    from accounts.scheduled_backup import last_scheduled_result
    from accounts.settings_alerts import gateway_is_quiet, plan_pressure

    if company.scheduled_backup_enabled:
        last = last_scheduled_result(company)
        items.append(_item("backup", WARN if last and not last["ok"] else OK, "/settings/backup"))
    if gateway_is_quiet(company):
        items.append(_item("webhook", WARN, "/settings/payment-gateway"))
    pressed = plan_pressure(company)
    if pressed:
        items.append(_item("plan", WARN, "/settings/billing", metrics=pressed))
    return items


class SettingsHealthView(APIView):
    """GET /api/v1/company/settings-health/ — owner only."""

    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def get(self, request):
        company = get_company_user(request).company
        items = settings_health(company)
        return Response({"items": items, "needs_attention": sum(1 for i in items if i["status"] != OK)})
