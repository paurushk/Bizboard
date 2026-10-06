"""GM-90 / GM-91: first growth events and admin counts."""

import pytest

from crm.pipeline import capture_lead
from insights.growth_metrics import growth_metrics
from insights.models import ShopFloorEvent
from insights.telemetry import note_once


@pytest.mark.django_db
def test_first_lead_is_recorded_once(tenant_a):
    capture_lead(tenant_a.company, tenant_a.owner, name="Asha", phone="9999990001", manual=True)
    capture_lead(tenant_a.company, tenant_a.owner, name="Bela", phone="9999990002", manual=True)
    assert ShopFloorEvent.objects.filter(company=tenant_a.company, event="first_lead").count() == 1


@pytest.mark.django_db
def test_note_once_ignores_a_repeat(tenant_a):
    note_once(tenant_a.company, "first_quote", user=tenant_a.owner, journey="growth")
    note_once(tenant_a.company, "first_quote", user=tenant_a.owner, journey="growth")
    note_once(tenant_a.company, "receipt_from_link", user=tenant_a.owner, journey="payment")
    assert ShopFloorEvent.objects.filter(company=tenant_a.company, event="first_quote").count() == 1
    assert ShopFloorEvent.objects.filter(company=tenant_a.company, event="receipt_from_link").count() == 1


@pytest.mark.django_db
def test_growth_metrics_match_the_tables(tenant_a):
    from crm.models import Lead

    capture_lead(tenant_a.company, tenant_a.owner, name="Asha", phone="9999990003", manual=True)
    numbers = growth_metrics(tenant_a.company)
    assert numbers["leads"] == Lead.objects.filter(company=tenant_a.company).count()
    assert numbers["open_tickets"] == 0
    assert numbers["referral_codes"] == 0
