"""Qualified and Negotiation stay open. Won and Lost are the only close states."""

from datetime import date
from decimal import Decimal

import pytest

from crm.forecast import pipeline_forecast
from crm.models import Opportunity


@pytest.mark.django_db
def test_forecast_includes_qualified_and_negotiation_and_not_a_won_deal(tenant_a):
    Opportunity.objects.create(
        company=tenant_a.company, title="Qualified", amount=Decimal("100"),
        probability=50, expected_close_date=date(2026, 10, 1), stage=Opportunity.Stage.QUALIFIED,
    )
    Opportunity.objects.create(
        company=tenant_a.company, title="Talking", amount=Decimal("80"),
        probability=25, expected_close_date=date(2026, 10, 1), stage=Opportunity.Stage.NEGOTIATION,
    )
    Opportunity.objects.create(
        company=tenant_a.company, title="Done", amount=Decimal("999"),
        probability=100, expected_close_date=date(2026, 10, 1), stage=Opportunity.Stage.WON,
    )
    report = pipeline_forecast(tenant_a.company)
    assert report["months"] == [{"month": "2026-10", "amount": "70.00"}]


@pytest.mark.django_db
def test_won_cannot_move_and_open_can_advance(tenant_a):
    from .test_growth_os import _flags

    from tests.conftest import make_customer

    _flags(tenant_a.company)
    # a deal needs a customer before it can be won (BUG-CRM-003)
    buyer = make_customer(tenant_a.company, name="Pipeline Buyer")
    created = tenant_a.client.post(
        "/api/v1/crm/opportunities/",
        {"title": "Deal", "amount": "10", "stage": "OPEN", "customer": buyer.id},
        format="json",
    )
    assert created.status_code == 201, created.data
    opportunity_id = created.data["id"]
    moved = tenant_a.client.patch(
        f"/api/v1/crm/opportunities/{opportunity_id}/",
        {"stage": "QUALIFIED"},
        format="json",
    )
    assert moved.status_code == 200
    assert moved.data["stage"] == "QUALIFIED"
    won = tenant_a.client.patch(
        f"/api/v1/crm/opportunities/{opportunity_id}/",
        {"stage": "WON"},
        format="json",
    )
    assert won.status_code == 200
    reopened = tenant_a.client.patch(
        f"/api/v1/crm/opportunities/{opportunity_id}/",
        {"stage": "NEGOTIATION"},
        format="json",
    )
    assert reopened.status_code == 400


@pytest.mark.django_db
def test_lost_is_closed_and_an_open_deal_without_a_date_stays_unscheduled(tenant_a):
    Opportunity.objects.create(
        company=tenant_a.company, title="Open", amount=Decimal("40"),
        probability=50, expected_close_date=None, stage=Opportunity.Stage.OPEN,
    )
    Opportunity.objects.create(
        company=tenant_a.company, title="Lost", amount=Decimal("500"),
        probability=100, expected_close_date=date(2026, 10, 1), stage=Opportunity.Stage.LOST,
    )
    report = pipeline_forecast(tenant_a.company)
    assert report["months"] == []
    assert report["unscheduled"] == "20.00"


@pytest.mark.django_db
def test_lead_conversion_starts_open_or_won_and_lost_cannot_reopen(tenant_a):
    from .test_growth_os import _flags

    _flags(tenant_a.company)
    opened = tenant_a.client.post(
        "/api/v1/crm/leads/",
        {"name": "Open lead", "phone": "9000000101"},
        format="json",
    )
    assert opened.status_code == 201, opened.data
    converted = tenant_a.client.post(
        f"/api/v1/crm/leads/{opened.data['id']}/convert/",
        {"amount": "25"},
        format="json",
    )
    assert converted.status_code == 200, converted.data
    opportunity = converted.data["opportunity"]
    assert opportunity["stage"] == "OPEN"
    negotiating = tenant_a.client.patch(
        f"/api/v1/crm/opportunities/{opportunity['id']}/",
        {"stage": "NEGOTIATION"},
        format="json",
    )
    assert negotiating.status_code == 200
    lost = tenant_a.client.patch(
        f"/api/v1/crm/opportunities/{opportunity['id']}/",
        {"stage": "LOST"},
        format="json",
    )
    assert lost.status_code == 200
    reopened = tenant_a.client.patch(
        f"/api/v1/crm/opportunities/{opportunity['id']}/",
        {"stage": "QUALIFIED"},
        format="json",
    )
    assert reopened.status_code == 400

    won_lead = tenant_a.client.post(
        "/api/v1/crm/leads/",
        {"name": "Won lead", "phone": "9000000102"},
        format="json",
    )
    won = tenant_a.client.post(
        f"/api/v1/crm/leads/{won_lead.data['id']}/convert/",
        {"won": True, "amount": "80"},
        format="json",
    )
    assert won.status_code == 200, won.data
    assert won.data["opportunity"]["stage"] == "WON"
    moved = tenant_a.client.patch(
        f"/api/v1/crm/opportunities/{won.data['opportunity']['id']}/",
        {"stage": "NEGOTIATION"},
        format="json",
    )
    assert moved.status_code == 400
