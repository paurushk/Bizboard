"""WP-E1 / WP-D4: the nightly books check runs one company per task and records each result."""

from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from core import sweep
from core.models import TenantSweepResult
from core.tasks import nightly_invariants_task, sweep_company_task
from tests.conftest import add_stock, make_product

pytestmark = pytest.mark.django_db
S = TenantSweepResult.Status


def _corrupt_stock(tenant, sku="SWEEP-1"):
    from inventory.models import StockBalance

    product = make_product(tenant.company, sku=sku)
    add_stock(tenant, product, "10", unit_cost="60")
    StockBalance.objects.filter(company=tenant.company, product=product).update(on_hand=Decimal("999999"))


def _clean_row(company, started_at):
    return TenantSweepResult.objects.create(
        company=company, run_id="old", status=S.CLEAN, started_at=started_at, finished_at=started_at,
    )


def _not_rotation_day(company):
    """A 'now' whose weekday is not this company's rotation day."""
    now = timezone.now()
    while sweep.is_rotation_day(company.pk, now):
        now += timedelta(days=1)
    return now


def test_the_orchestrator_queues_one_task_per_company(tenant_a, tenant_b):
    with mock.patch.object(sweep_company_task, "delay") as delay:
        out = nightly_invariants_task()
    queued = {c.kwargs["company_id"] for c in delay.call_args_list}
    assert {tenant_a.company.pk, tenant_b.company.pk} <= queued
    assert out["queued"] == len(queued)
    assert {c.kwargs["run_id"] for c in delay.call_args_list} == {out["run_id"]}


def test_platform_checks_run_once_not_once_per_company(tenant_a, tenant_b):
    with mock.patch("integrations.shopify.notify_shopify_gaps") as gaps:
        nightly_invariants_task()
    assert gaps.call_count == 1


@pytest.mark.no_invariant_check
def test_one_failing_company_does_not_stop_the_others(tenant_a, tenant_b):
    _corrupt_stock(tenant_a)
    out = nightly_invariants_task()
    rows = TenantSweepResult.objects.filter(run_id=out["run_id"])
    bad = rows.get(company=tenant_a.company)
    assert bad.status == S.FAILED and "inventory.balance_equals_movements" in bad.failing_keys
    assert rows.get(company=tenant_b.company).status == S.CLEAN


def test_a_crash_is_recorded_as_error_and_never_raised(tenant_a):
    with mock.patch("core.invariants.run_invariants", side_effect=RuntimeError("boom")):
        row = sweep.sweep_company(tenant_a.company.pk, "r1")
    assert row.status == S.ERROR and "boom" in row.error


def test_an_unchanged_company_is_skipped_until_its_full_sweep_is_due(tenant_a):
    company = tenant_a.company
    now = _not_rotation_day(company)
    _clean_row(company, now - timedelta(hours=1))
    with mock.patch("core.sweep.changed_since", return_value=False):
        assert sweep.sweep_company(company.pk, "r", now=now).status == S.SKIPPED


def test_a_company_is_fully_swept_on_its_rotation_day_even_without_changes(tenant_a):
    company = tenant_a.company
    now = timezone.now()
    while not sweep.is_rotation_day(company.pk, now):
        now += timedelta(days=1)
    _clean_row(company, now - timedelta(hours=1))
    with mock.patch("core.sweep.changed_since", return_value=False):
        row = sweep.sweep_company(company.pk, "r", now=now)
    assert row.status == S.CLEAN and row.full_sweep is True


def test_a_company_not_checked_for_a_week_is_fully_swept(tenant_a):
    company = tenant_a.company
    now = _not_rotation_day(company)
    _clean_row(company, now - timedelta(days=8))
    with mock.patch("core.sweep.changed_since", return_value=False):
        row = sweep.sweep_company(company.pk, "r", now=now)
    assert row.full_sweep is True and row.status == S.CLEAN


def test_a_ledger_write_without_an_audit_event_still_counts_as_a_change(tenant_a):
    from accounting.models import JournalEntry
    from core.models import AuditEvent

    company = tenant_a.company
    since = timezone.now()
    assert not sweep.changed_since(company, since)
    JournalEntry.objects.create(company=company, entry_date=since.date(), narration="raw write")
    assert not AuditEvent.objects.filter(company=company, created_at__gt=since).exists()
    assert sweep.changed_since(company, since)


def test_failing_company_count_uses_each_companys_latest_result(tenant_a, tenant_b):
    now = timezone.now()
    TenantSweepResult.objects.create(company=tenant_a.company, run_id="1", status=S.FAILED,
                                     started_at=now - timedelta(days=1), finished_at=now)
    TenantSweepResult.objects.create(company=tenant_a.company, run_id="2", status=S.CLEAN,
                                     started_at=now, finished_at=now)
    TenantSweepResult.objects.create(company=tenant_b.company, run_id="2", status=S.ERROR,
                                     started_at=now, finished_at=now)
    TenantSweepResult.objects.create(company=tenant_b.company, run_id="3", status=S.SKIPPED,
                                     started_at=now + timedelta(minutes=1), finished_at=now)
    assert sweep.failing_company_count() == 1


def test_old_results_are_pruned(tenant_a):
    old = timezone.now() - timedelta(days=120)
    _clean_row(tenant_a.company, old)
    assert sweep.prune_old_results() == 1


@pytest.mark.no_invariant_check
def test_the_command_reports_and_fails_on_any_failure(tenant_a, tenant_b):
    _corrupt_stock(tenant_a, sku="SWEEP-CMD")
    out = StringIO()
    with pytest.raises(CommandError):
        call_command("sweep_all_tenants", "--sync", "--full", "--fail-on-any", stdout=out)
    text = out.getvalue()
    assert f"FAILED   company={tenant_a.company.pk}" in text
    assert f"CLEAN    company={tenant_b.company.pk}" in text


def test_the_command_passes_for_clean_books(tenant_a):
    out = StringIO()
    call_command("sweep_all_tenants", "--sync", "--full", "--fail-on-any",
                 "--company", str(tenant_a.company.pk), stdout=out)
    assert "failed=0" in out.getvalue()


def test_the_admin_list_is_superuser_only(tenant_a, client, django_user_model):
    _clean_row(tenant_a.company, timezone.now())
    url = "/admin/core/tenantsweepresult/"
    staff = django_user_model.objects.create_user("ops-staff@x.io", password="x", is_staff=True)
    client.force_login(staff)
    assert client.get(url).status_code == 403
    admin_user = django_user_model.objects.create_superuser("ops-root@x.io", password="x")
    client.force_login(admin_user)
    resp = client.get(url)
    assert resp.status_code == 200
    assert tenant_a.company.name in resp.content.decode()
