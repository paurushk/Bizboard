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
