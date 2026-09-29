"""SAAS-1 through SAAS-5. Vendor copies use rls_bypass only around that write."""

import os
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Max
from django.utils import timezone

from core.rls import rls_bypass
from crm.models import Campaign

from .models import Subscription, TenantActivation, VendorTenantSnapshot
from .quotas import usage_snapshot


def _vendor_id():
    raw = str(getattr(settings, "VENDOR_COMPANY_ID", "") or "").strip()
    if not raw and os.environ.get("E2E_GOLDEN_GRANT") == "1":
        pointer = Path(settings.BASE_DIR) / ".e2e_vendor_id"
        if pointer.is_file():
            raw = pointer.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _activation(company):
    row, _ = TenantActivation.objects.get_or_create(company=company)
    return row


def note_setup_completed(company):
    row = _activation(company)
    if row.setup_completed_at is None:
        row.setup_completed_at = timezone.now()
        row.save(update_fields=["setup_completed_at", "updated_at"])
    publish_vendor_snapshot(company)
    return row


def note_first_invoice(company_id):
    from accounts.models import Company

    company = Company.objects.filter(pk=company_id).first()
    if company is None:
        return None
    row = _activation(company)
    now = timezone.now()
    if row.first_invoice_at is None:
        row.first_invoice_at = now
        row.save(update_fields=["first_invoice_at", "updated_at"])
    publish_vendor_snapshot(company)
    return row


def publish_vendor_snapshot(company):
    vendor_id = _vendor_id()
    if vendor_id is None:
        return None
    activation = TenantActivation.objects.filter(company=company).first()
    sub = Subscription.objects.filter(company=company).select_related("plan").first()
    usage = usage_snapshot(company, sub=sub)
    User = get_user_model()
    last_login = User.objects.filter(company_memberships__company=company).aggregate(v=Max("last_login"))["v"]
    from sales.models import SalesInvoice

    last_invoice = SalesInvoice.objects.filter(
        company=company, status=SalesInvoice.Status.COMPLETED,
    ).aggregate(v=Max("completed_at"))["v"]
    payload = {
        "source_company_name": company.name,
        "setup_completed_at": getattr(activation, "setup_completed_at", None),
        "first_invoice_at": getattr(activation, "first_invoice_at", None),
        "last_invoice_at": last_invoice,
        "last_login_at": last_login,
        "seats_used": usage["seats"]["used"],
        "seats_limit": usage["seats"]["limit"],
        "documents_used": usage["completes"]["used"],
        "documents_limit": usage["completes"]["limit"],
        "churn_reason": getattr(sub, "churn_reason", "") or "",
    }
    with rls_bypass():
        row, _ = VendorTenantSnapshot.objects.update_or_create(
            company_id=vendor_id,
            source_company_id=company.id,
            defaults=payload,
        )
    return row


def upgrade_prompt(company):
    sub = Subscription.objects.filter(company=company).select_related("plan", "pending_plan").first()
    usage = usage_snapshot(company, sub=sub)
    reason = None
    seats = usage["seats"]
    docs = usage["completes"]
    if seats["limit"] and seats["used"] >= seats["limit"]:
        reason = "seats"
    elif docs["limit"] and docs["used"] >= docs["limit"]:
        reason = "documents"
    return {
        "show": reason is not None,
        "reason": reason,
        "pending_plan_id": getattr(sub, "pending_plan_id", None),
        "quotas": usage,
    }


def trial_ending_notice(company):
    """Distinct from past-due dunning. Only a live trial inside the notice window."""
    sub = Subscription.objects.filter(company=company).first()
    if sub is None or sub.status != Subscription.Status.TRIAL or not sub.trial_ends_at:
        return {"show": False, "trial_ends_at": None, "days_left": None}
    if sub.last_dunning_at is not None:
        # Dunning has already started stepping for this subscription --
        # don't also show the separate trial-ending notice.
        return {"show": False, "trial_ends_at": None, "days_left": None}
    now = timezone.now()
    if sub.trial_ends_at <= now:
        return {"show": False, "trial_ends_at": sub.trial_ends_at, "days_left": 0}
    days_left = (sub.trial_ends_at - now).days
    show = sub.trial_ends_at <= now + timedelta(days=7)
    return {"show": show, "trial_ends_at": sub.trial_ends_at, "days_left": days_left}


def suspend_for_churn(company, user, *, reason):
    reason = (reason or "").strip()
    if not reason:
        from core.exceptions import BusinessRuleError

        raise BusinessRuleError("A churn reason is required to suspend.")
    sub = Subscription.objects.select_for_update().filter(company=company).first()
    if sub is None:
        from core.exceptions import BusinessRuleError

        raise BusinessRuleError("This company has no subscription.")
    sub.status = Subscription.Status.SUSPENDED
    sub.churn_reason = reason[:255]
    sub.suspended_at = timezone.now()
    remote_id = (sub.razorpay_subscription_id or "").strip()
    pending_remote_id = (sub.pending_razorpay_subscription_id or "").strip()
    sub.pending_razorpay_subscription_id = ""
    sub.pending_plan = None
    sub.save(update_fields=[
        "status", "churn_reason", "suspended_at", "pending_plan",
        "pending_razorpay_subscription_id", "updated_at",
    ])
    from billing.services import _cancel_razorpay_subscription

    if remote_id:
        _cancel_razorpay_subscription(remote_id, at_cycle_end=True)
    if pending_remote_id and pending_remote_id != remote_id:
        _cancel_razorpay_subscription(pending_remote_id, at_cycle_end=False)
    vendor_id = _vendor_id()
    win_back_name = ""
    if vendor_id is not None:
        win_back_name = f"Win-back {company.name}"[:200]
        with rls_bypass():
            exists = Campaign.objects.filter(company_id=vendor_id, name=win_back_name).exists()
            if not exists:
                Campaign.objects.create(
                    company_id=vendor_id,
                    name=win_back_name,
                    campaign_type=Campaign.Type.DIGITAL,
                    status=Campaign.Status.DRAFT,
                    expected_outcome=reason[:255],
                    created_by=user,
                    updated_by=user,
                )
    publish_vendor_snapshot(company)
    return sub, win_back_name
