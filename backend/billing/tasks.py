"""Celery tasks for SaaS dunning and Razorpay subscription recon."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def run_saas_dunning_task():
    from billing.dunning import run_saas_dunning
    from core.rls import rls_bypass

    with rls_bypass():
        result = run_saas_dunning()
    logger.info("SaaS dunning sent=%s skipped=%s", result.get("sent"), result.get("skipped"))
    return result


@shared_task
def reconcile_saas_subscriptions_task():
    from billing.recon import reconcile_saas_subscriptions
    from core.rls import rls_bypass

    with rls_bypass():
        result = reconcile_saas_subscriptions()
    logger.info(
        "SaaS billing recon skipped=%s checked=%s mismatches=%s",
        result.get("skipped"),
        result.get("checked"),
        result.get("mismatches"),
    )
    return result


def _run_parts(parts: dict) -> dict:
    """Run each part of a combined beat task on its own: one part's error must not skip the others."""
    result = {}
    for name, fn in parts.items():
        try:
            result[name] = fn()
        except Exception:  # noqa: BLE001 - logged; the other parts still run
            logger.exception("Beat task part %s failed", name)
            result[name] = "error"
    return result


@shared_task
def tds_credits_and_reminders_task():
    """WP-BL1: apply verified TDS credit to renewals the webhook path missed, and on the 16th of
    Aug/Nov/Feb/Jun remind owners to claim last quarter's TDS (Form 16A)."""
    from billing.tds_claims import apply_pending_credits, send_form16a_reminders

    result = _run_parts({"credited": apply_pending_credits, "reminded": send_form16a_reminders})
    logger.info("TDS credits/reminders %s", result)
    return result


@shared_task
def plan_change_and_renewal_task():
    """WP-BL3: undo upgrades whose prorated charge was not paid in 3 days. WP-BL4: email the
    renewal reminder 3 days before an automatic debit (once per cycle, never SMS)."""
    from billing.autopay import send_renewal_reminders
    from billing.plan_change import revert_unpaid_upgrades

    result = _run_parts({"reverted": revert_unpaid_upgrades, "reminded": send_renewal_reminders})
    logger.info("Plan change / renewal reminders %s", result)
    return result


@shared_task
def qualify_saas_referrals_task():
    """D-19 (BB-139): mark referred businesses that now pay as qualified (billing/referrals.py)."""
    from billing.referrals import qualify_referrals

    return qualify_referrals()
