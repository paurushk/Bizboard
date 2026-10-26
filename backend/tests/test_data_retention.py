"""D-13 (2026-10-25): a read-only workspace is warned, then erased after the owner's retention period."""

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from accounts.models import Company
from accounts.retention import apply_retention, deletion_due_at
from billing.models import Plan, Subscription
from core.models import Notification

pytestmark = pytest.mark.django_db


def _lapse(tenant):
    plan = Plan.objects.create(name="Lapsed", slug="d13-lapsed", seat_limit=3, price_paise=0)
    return Subscription.objects.create(
        company=tenant.company, plan=plan, status=Subscription.Status.TRIAL,
        trial_ends_at=timezone.now() - timedelta(days=1),
    )


def _read_only_for(tenant, days):
    Company.objects.filter(pk=tenant.company.pk).update(read_only_since=timezone.now() - timedelta(days=days))
    tenant.company.refresh_from_db()


def test_an_active_workspace_is_left_alone(tenant_a):
    assert apply_retention(tenant_a.company) == "active"
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.read_only_since is None
    assert deletion_due_at(tenant_a.company) is None


def test_the_clock_starts_when_it_turns_read_only_and_stops_on_renewal(tenant_a):
    sub = _lapse(tenant_a)
    assert apply_retention(tenant_a.company) == "started"
    assert tenant_a.company.read_only_since is not None
    assert deletion_due_at(tenant_a.company) == tenant_a.company.read_only_since + timedelta(days=90)
    sub.status = Subscription.Status.ACTIVE
    sub.current_period_end = timezone.now() + timedelta(days=30)
    sub.save()
    assert apply_retention(tenant_a.company) == "active"
    assert tenant_a.company.read_only_since is None


def test_owners_are_warned_30_then_7_days_ahead_once_each(tenant_a):
    _lapse(tenant_a)
    _read_only_for(tenant_a, 70)  # deletion in 20 days
    assert apply_retention(tenant_a.company) == "warned"
    assert apply_retention(tenant_a.company) == "waiting"  # not twice
    owner_rows = Notification.objects.filter(company=tenant_a.company, body__contains="retention:")
    assert set(owner_rows.values_list("channel", flat=True)) == {"IN_APP", "EMAIL"}
    assert owner_rows.count() == 2
    _read_only_for(tenant_a, 85)  # deletion in 5 days
    assert apply_retention(tenant_a.company) == "warned"
    assert Notification.objects.filter(company=tenant_a.company, body__contains=":7]").count() == 2
    # Sales staff are not owners and are not told.
    assert not Notification.objects.filter(recipient=tenant_a.staff.email).exists()


def test_past_the_period_nothing_is_deleted_while_enforcement_is_off(tenant_a):
    _lapse(tenant_a)
    _read_only_for(tenant_a, 91)
    assert apply_retention(tenant_a.company) == "would_erase"
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.erased_at is None


@override_settings(DATA_RETENTION_ENFORCE=True)
def test_past_the_period_the_workspace_is_erased_when_enforced(tenant_a):
    _lapse(tenant_a)
    _read_only_for(tenant_a, 91)
    assert apply_retention(tenant_a.company) == "erased"
    assert Company.objects.get(pk=tenant_a.company.pk).erased_at is not None


@override_settings(DATA_RETENTION_ENFORCE=True)
def test_a_longer_period_set_by_the_owner_is_respected(tenant_a):
    _lapse(tenant_a)
    Company.objects.filter(pk=tenant_a.company.pk).update(data_retention_days=365)
    _read_only_for(tenant_a, 91)
    assert apply_retention(tenant_a.company) == "waiting"
    assert Company.objects.get(pk=tenant_a.company.pk).erased_at is None


def test_only_the_owner_sets_the_period_within_30_to_3650_days(tenant_a):
    res = tenant_a.client.patch("/api/v1/company/", {"data_retention_days": 180}, format="json")
    assert res.status_code == 200, res.data
    assert res.data["data_retention_days"] == 180
    assert res.data["data_deletion_due_at"] is None
    assert tenant_a.client.patch("/api/v1/company/", {"data_retention_days": 10}, format="json").status_code == 400
    assert tenant_a.client.patch("/api/v1/company/", {"data_retention_days": 4000}, format="json").status_code == 400
    assert tenant_a.staff_client.patch("/api/v1/company/", {"data_retention_days": 30}, format="json").status_code == 403
