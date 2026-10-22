"""WP-C2: every Celery beat task must do real work under FORCE RLS as the app role.

A beat task starts with no tenant. Under the NOSUPERUSER NOBYPASSRLS app role, any read of a
tenant table that is neither scoped to a company nor inside ``rls_bypass()`` finds nothing,
so the job silently does nothing in production (found: agent proposal expiry, lead
reminders, stale lead imports, ITC digests, scheduled backups, invoice-zip purge).

``test_every_beat_task_is_classified`` runs on any database and forces each new beat entry to
say how it handles tenants. The ``postgres`` tests seed data as the superuser, run the task
inside ``app_role()``, and assert the task actually acted.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.conf import settings
from django.test import override_settings
from django.utils import timezone

from core.rls import rls_bypass
from tests.rls_helpers import app_role, needs_pg

# How each beat task finds its tenants. FAN_OUT: queues one task per company with company_id.
# PER_COMPANY: visits companies (ids read under the bypass) and sets that company's RLS context
# for each. BYPASS: a deliberate cross-tenant sweep inside rls_bypass(). PLATFORM: touches no
# tenant table.
BEAT_TASKS = {
    "accounting.tasks.post_monthly_depreciation": "FAN_OUT",
    "accounts.tasks.run_scheduled_backups_task": "FAN_OUT",
    "accounts.tasks.run_settings_alerts_task": "FAN_OUT",
    "accounts.tasks.sweep_expired_sandboxes_task": "BYPASS",
    "agents.tasks.cancel_resolved": "FAN_OUT",
    "agents.tasks.dispatch_scheduled_agents": "FAN_OUT",
    "agents.tasks.expire_proposals": "FAN_OUT",
    "agents.tasks.purge_steps": "FAN_OUT",
    "billing.tasks.reconcile_saas_subscriptions_task": "BYPASS",
    "billing.tasks.run_saas_dunning_task": "BYPASS",
    "contracts.tasks.refresh_contract_statuses": "PER_COMPANY",
    "contracts.tasks.send_contract_renewal_reminders": "PER_COMPANY",
    "core.tasks.celery_beat_heartbeat": "PLATFORM",
    "core.tasks.nightly_invariants_task": "FAN_OUT",
    "core.tasks.prune_help_events_task": "BYPASS",
    "core.tasks.prune_idempotency_records_task": "BYPASS",
    "core.tasks.seal_audit_chain_task": "BYPASS",
    "crm.tasks.reap_stale_lead_ingest_jobs": "PER_COMPANY",
    "crm.tasks.remind_due_lead_activities": "PER_COMPANY",
    "insights.tasks.generate_daily_summaries_task": "FAN_OUT",
    "insights.tasks.refresh_cashflow_forecasts_task": "FAN_OUT",
    "insights.tasks.sweep_attention_state_task": "FAN_OUT",
    "inventory.tasks.record_expiry_bands_task": "FAN_OUT",
    "inventory.tasks.release_expired_reservations_task": "PER_COMPANY",
    "masters.tasks.customers_audit_task": "PER_COMPANY",
    "payments.tasks.reconcile_gateway_captures_task": "PER_COMPANY",
    "payments.tasks.retry_pending_gateway_refunds": "PER_COMPANY",
    "payments.tasks.run_ar_dunning_task": "PER_COMPANY",
    "projects.tasks.send_milestone_due_reminders": "PER_COMPANY",
    "reporting.tasks.send_itc_expiry_digests_task": "PER_COMPANY",
    "sales.tasks.generate_recurring_invoices_task": "PER_COMPANY",
    "sales.tasks.purge_old_invoice_zips_task": "BYPASS",
    "sales.tasks.requeue_stale_invoice_pdfs": "BYPASS",
    "sales.tasks.sweep_quotation_conversions": "BYPASS",
}


def test_every_beat_task_is_classified():
    scheduled = {entry["task"] for entry in settings.CELERY_BEAT_SCHEDULE.values()}
    missing = sorted(scheduled - set(BEAT_TASKS))
    assert not missing, (
        "New beat task(s) with no tenant classification. Make each one fan out per company "
        "(company_id kwarg), set RLS per company, or run inside rls_bypass(); then add it to "
        f"BEAT_TASKS with a test below: {missing}"
    )
    stale = sorted(set(BEAT_TASKS) - scheduled)
    assert not stale, f"BEAT_TASKS lists tasks no longer scheduled: {stale}"


def _rls_on():
    return override_settings(POSTGRES_RLS_ENABLED=True)


@pytest.mark.postgres
@needs_pg
@pytest.mark.django_db(transaction=True)
def test_agent_proposals_expire_under_the_app_role():
    from agents.enums import ProposalStatus
    from agents.models import AgentProposal
    from agents.tasks import expire_proposals
    from tests.agents.conftest import enable_agents, make_proposal
    from tests.conftest import make_tenant

    import agents.catalog._example as ex
    from agents import spec

    if "EXAMPLE" not in spec.AGENTS:
        spec.register(ex.AGENT)
    try:
        t = make_tenant("rlsagt")
        enable_agents(t.company, "AGENT_EXAMPLE")
        p = make_proposal(t)
        AgentProposal.objects.filter(pk=p.pk).update(expires_at=timezone.now() - timedelta(hours=1))
        with _rls_on(), app_role():
            expire_proposals()
        with rls_bypass():
            p.refresh_from_db()
        assert p.status == ProposalStatus.EXPIRED
    finally:
        spec.unregister("EXAMPLE")


@pytest.mark.postgres
@needs_pg
@pytest.mark.django_db(transaction=True)
def test_due_lead_activity_is_reminded_under_the_app_role(tenant_a):
    from crm.models import Lead, LeadActivity
    from crm.tasks import remind_due_lead_activities

    company = tenant_a.company
    company.dunning_quiet_hours_start = company.dunning_quiet_hours_end = 0  # never quiet
    company.save(update_fields=["dunning_quiet_hours_start", "dunning_quiet_hours_end"])
    lead = Lead.objects.create(company=company, name="RLS Lead")
    act = LeadActivity.objects.create(
        company=tenant_a.company, lead=lead, body="Call back", due_at=timezone.now() - timedelta(hours=1),
    )
    with _rls_on(), app_role():
        out = remind_due_lead_activities()
    with rls_bypass():
        act.refresh_from_db()
    assert out["sent"] == 1 and act.reminded_at is not None


@pytest.mark.postgres
@needs_pg
@pytest.mark.django_db(transaction=True)
def test_stale_lead_import_is_retried_under_the_app_role(tenant_a, monkeypatch):
    from crm.models import LeadIngestJob
    from crm import tasks as crm_tasks

    job = LeadIngestJob.objects.create(
        company=tenant_a.company, kind=LeadIngestJob.Kind.CSV, status=LeadIngestJob.Status.RUNNING, payload={},
    )
    LeadIngestJob.objects.filter(pk=job.pk).update(updated_at=timezone.now() - timedelta(days=2))
    queued = []
    monkeypatch.setattr(crm_tasks.process_lead_ingest, "delay", lambda *a, **k: queued.append((a, k)))
    with _rls_on(), app_role():
        out = crm_tasks.reap_stale_lead_ingest_jobs()
    assert out["retried"] == 1 and queued


@pytest.mark.postgres
@needs_pg
@pytest.mark.django_db(transaction=True)
def test_scheduled_backup_reads_the_companys_rows_under_the_app_role(tenant_a):
    from accounts.scheduled_backup import stored_backups
    from accounts.tasks import run_scheduled_backups_task

    tenant_a.company.scheduled_backup_enabled = True
    tenant_a.company.save(update_fields=["scheduled_backup_enabled"])
    with _rls_on(), app_role():
        run_scheduled_backups_task()
    with rls_bypass():
        assert stored_backups(tenant_a.company).count() == 1


@pytest.mark.postgres
@needs_pg
@pytest.mark.django_db(transaction=True)
def test_nightly_books_check_records_a_result_under_the_app_role(tenant_a):
    from core.models import TenantSweepResult
    from core.tasks import nightly_invariants_task

    with _rls_on(), app_role():
        out = nightly_invariants_task()
    with rls_bypass():
        row = TenantSweepResult.objects.get(run_id=out["run_id"], company=tenant_a.company)
    assert row.status == TenantSweepResult.Status.CLEAN


@pytest.mark.postgres
@needs_pg
@pytest.mark.django_db(transaction=True)
def test_old_invoice_zips_are_purged_under_the_app_role(tenant_a):
    from django.core.files.base import ContentFile

    from core.models import FileAsset
    from sales.tasks import purge_old_invoice_zips_task

    asset = FileAsset(company=tenant_a.company, kind=FileAsset.Kind.EXPORT, original_name="invoices.zip")
    asset.file.save("invoices.zip", ContentFile(b"PK"), save=True)
    FileAsset.objects.filter(pk=asset.pk).update(created_at=timezone.now() - timedelta(days=30))
    with _rls_on(), app_role():
        assert purge_old_invoice_zips_task() == 1
