"""SET-07: switching accounting off has a pre-flight, refusal rules, a reason and an audit entry."""

from datetime import date

import pytest
from django.core.cache import cache

from accounting.models import AccountingPeriod, JournalEntry
from accounting.tasks import backfill_cache_key
from core.models import AuditEvent

SETTINGS = "/api/v1/accounting/settings/"
PREFLIGHT = "/api/v1/accounting/settings/disable-preflight/"


@pytest.fixture(autouse=True)
def _fresh_cache():
    cache.clear()
    yield
    cache.clear()


def _enable(tenant):
    r = tenant.client.post(SETTINGS, {"accounting_enabled": True}, format="json")
    assert r.status_code == 200, r.data
    return r


def _disable(tenant, **body):
    return tenant.client.post(SETTINGS, {"accounting_enabled": False, **body}, format="json")


def _posted_entry(tenant, entry_date=date(2026, 5, 1)):
    count = JournalEntry.objects.filter(company=tenant.company).count()
    return JournalEntry.objects.create(
        company=tenant.company, status=JournalEntry.Status.POSTED, entry_date=entry_date, number=f"JV-{count + 1}"
    )


def _events(tenant, action):
    return AuditEvent.objects.filter(company=tenant.company, action=action)


def test_enabling_is_audited(tenant_a):
    _enable(tenant_a)
    assert _events(tenant_a, "accounting.enable").count() == 1


def test_disabling_needs_a_reason(tenant_a):
    _enable(tenant_a)
    r = _disable(tenant_a)
    assert r.status_code == 400 and "why" in str(r.data).lower()
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.accounting_enabled is True
    assert _events(tenant_a, "accounting.disable").count() == 0


def test_disabling_an_empty_set_of_books_works_and_is_audited_with_the_reason(tenant_a):
    _enable(tenant_a)
    r = _disable(tenant_a, reason="Switched on by mistake")
    assert r.status_code == 200, r.data
    assert r.data["accounting_enabled"] is False
    event = _events(tenant_a, "accounting.disable").get()
    assert event.description == "Switched on by mistake"
    assert event.metadata["posted_journals"] == 0 and event.user_id == tenant_a.owner.id


# Builds ledger rows straight through the ORM with no documents behind them, so the
# docs-vs-ledger and empty-entry invariants (WP-F4 / WP-F6) are expected to flag it.
@pytest.mark.no_invariant_check
def test_posted_entries_need_an_explicit_acknowledgement(tenant_a):
    _enable(tenant_a)
    _posted_entry(tenant_a)
    refused = _disable(tenant_a, reason="Moving to another tool")
    assert refused.status_code == 400 and "posted entries" in str(refused.data)
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.accounting_enabled is True
    ok = _disable(tenant_a, reason="Moving to another tool", acknowledge=True)
    assert ok.status_code == 200, ok.data
    event = _events(tenant_a, "accounting.disable").get()
    assert event.metadata["posted_journals"] == 1 and event.metadata["last_entry_date"] == "2026-05-01"


def test_a_closed_period_blocks_switching_off_even_with_a_reason(tenant_a):
    _enable(tenant_a)
    AccountingPeriod.objects.create(
        company=tenant_a.company, name="FY 25-26", start_date=date(2025, 4, 1), end_date=date(2026, 3, 31),
        status=AccountingPeriod.Status.CLOSED,
    )
    r = _disable(tenant_a, reason="Because", acknowledge=True)
    assert r.status_code == 400 and "closed" in str(r.data).lower()
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.accounting_enabled is True
    assert _events(tenant_a, "accounting.disable").count() == 0


def test_a_soft_closed_period_does_not_block(tenant_a):
    _enable(tenant_a)
    AccountingPeriod.objects.create(
        company=tenant_a.company, name="Apr", start_date=date(2026, 4, 1), end_date=date(2026, 4, 30),
        status=AccountingPeriod.Status.SOFT_CLOSED,
    )
    assert _disable(tenant_a, reason="Testing").status_code == 200


def test_a_running_backfill_blocks_switching_off(tenant_a):
    _enable(tenant_a)
    cache.set(backfill_cache_key(tenant_a.company.id), {"status": "running"}, 60)
    r = _disable(tenant_a, reason="Because")
    assert r.status_code == 400 and "back-fill" in str(r.data).lower()


def test_repeating_a_change_that_is_already_in_place_records_nothing(tenant_a):
    _enable(tenant_a)
    _enable(tenant_a)
    assert _events(tenant_a, "accounting.enable").count() == 1
    assert _disable(tenant_a, reason="x").status_code == 200
    assert _disable(tenant_a, reason="x").status_code == 200
    assert _events(tenant_a, "accounting.disable").count() == 1


# Builds ledger rows straight through the ORM with no documents behind them, so the
# docs-vs-ledger and empty-entry invariants (WP-F4 / WP-F6) are expected to flag it.
@pytest.mark.no_invariant_check
def test_preflight_reports_what_switching_off_would_do(tenant_a):
    _enable(tenant_a)
    _posted_entry(tenant_a, date(2026, 4, 2))
    _posted_entry(tenant_a, date(2026, 6, 9))
    JournalEntry.objects.create(company=tenant_a.company, status=JournalEntry.Status.DRAFT, number="JV-D")
    AccountingPeriod.objects.create(
        company=tenant_a.company, name="Apr", start_date=date(2026, 4, 1), end_date=date(2026, 4, 30),
        status=AccountingPeriod.Status.SOFT_CLOSED,
    )
    r = tenant_a.client.get(PREFLIGHT)
    assert r.status_code == 200, r.data
    assert r.data["posted_journals"] == 2  # the draft is not counted
    assert r.data["first_entry_date"] == "2026-04-02" and r.data["last_entry_date"] == "2026-06-09"
    assert r.data["soft_closed_periods"] == 1 and r.data["closed_periods"] == 0
    assert r.data["blockers"] == [] and r.data["can_disable"] is True


def test_preflight_lists_blockers_and_is_owner_only(tenant_a):
    _enable(tenant_a)
    AccountingPeriod.objects.create(
        company=tenant_a.company, name="FY", start_date=date(2025, 4, 1), end_date=date(2026, 3, 31),
        status=AccountingPeriod.Status.CLOSED,
    )
    cache.set(backfill_cache_key(tenant_a.company.id), {"status": "running"}, 60)
    r = tenant_a.client.get(PREFLIGHT)
    assert r.data["blockers"] == ["closed_period", "backfill_running"] and r.data["can_disable"] is False
    assert r.data["latest_closed_period_end"] == "2026-03-31"
    assert tenant_a.staff_client.get(PREFLIGHT).status_code == 403


def test_preflight_says_nothing_to_disable_when_books_are_already_off(tenant_a):
    r = tenant_a.client.get(PREFLIGHT)
    assert r.data["accounting_enabled"] is False and r.data["can_disable"] is False
