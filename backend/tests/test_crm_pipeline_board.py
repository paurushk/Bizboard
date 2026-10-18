"""CRM review WP-6: the board shows every open deal; stage sets a default win chance."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from crm.forecast import pipeline_forecast
from crm.models import Opportunity

from .conftest import make_customer
from .test_growth_os import _flags

pytestmark = pytest.mark.django_db


def _bulk(company, count, stage, *, closed_days_ago=None, prefix="Deal"):
    closed = timezone.now() - timedelta(days=closed_days_ago) if closed_days_ago is not None else None
    Opportunity.objects.bulk_create([
        Opportunity(
            company=company, title=f"{prefix} {stage} {i}", amount=Decimal("10"), stage=stage,
            probability=Opportunity.STAGE_DEFAULT_PROBABILITY[stage], closed_at=closed,
        )
        for i in range(count)
    ])


def test_board_never_hides_an_open_deal_behind_closed_ones(tenant_a):
    _flags(tenant_a.company)
    _bulk(tenant_a.company, 20, Opportunity.Stage.OPEN)
    _bulk(tenant_a.company, 4, Opportunity.Stage.NEGOTIATION)
    _bulk(tenant_a.company, 120, Opportunity.Stage.WON, closed_days_ago=10)
    _bulk(tenant_a.company, 7, Opportunity.Stage.LOST, closed_days_ago=400, prefix="Old")
    resp = tenant_a.client.get("/api/v1/crm/opportunities/board/")
    assert resp.status_code == 200, resp.data
    body = resp.data["data"] if "data" in resp.data and "stages" not in resp.data else resp.data
    stages = body["stages"]
    assert stages["OPEN"]["count"] == 20 and len(stages["OPEN"]["results"]) == 20
    assert stages["NEGOTIATION"]["count"] == 4
    assert stages["WON"]["count"] == 120 and len(stages["WON"]["results"]) == 25
    assert Decimal(stages["WON"]["total_amount"]) == Decimal("1200")
    # Lost deals older than the 90-day window are counted as "older", not silently dropped or shown.
    assert stages["LOST"]["count"] == 0 and stages["LOST"]["older"] == 7
    everything = tenant_a.client.get("/api/v1/crm/opportunities/board/?closed_days=0")
    all_body = everything.data["data"] if "stages" not in everything.data else everything.data
    assert all_body["stages"]["LOST"]["count"] == 7


def test_list_filters_by_stage_with_paging_and_window(tenant_a):
    _flags(tenant_a.company)
    _bulk(tenant_a.company, 30, Opportunity.Stage.WON, closed_days_ago=5)
    _bulk(tenant_a.company, 5, Opportunity.Stage.WON, closed_days_ago=300, prefix="Ancient")
    first = tenant_a.client.get("/api/v1/crm/opportunities/?stage=WON&closed_days=90&page_size=25")
    assert first.status_code == 200, first.data
    assert first.data["count"] == 30 and len(first.data["results"]) == 25 and first.data["next"]
    all_time = tenant_a.client.get("/api/v1/crm/opportunities/?stage=WON&closed_days=0&page_size=100")
    assert all_time.data["count"] == 35
    by_title = tenant_a.client.get("/api/v1/crm/opportunities/?stage=WON&q=Ancient&closed_days=0")
    assert by_title.data["count"] == 5


def test_stage_sets_a_default_win_chance_until_someone_sets_their_own(tenant_a):
    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company, name="Prob Buyer")
    created = tenant_a.client.post(
        "/api/v1/crm/opportunities/",
        {"title": "Fresh", "amount": "100", "stage": "OPEN", "customer": customer.id},
        format="json",
    )
    assert created.status_code == 201, created.data
    opp_id = created.data["id"]
    assert created.data["probability"] == 10
    moved = tenant_a.client.patch(f"/api/v1/crm/opportunities/{opp_id}/", {"stage": "QUALIFIED"}, format="json")
    assert moved.data["probability"] == 30
    custom = tenant_a.client.patch(f"/api/v1/crm/opportunities/{opp_id}/", {"probability": 45}, format="json")
    assert custom.data["probability"] == 45
    again = tenant_a.client.patch(f"/api/v1/crm/opportunities/{opp_id}/", {"stage": "NEGOTIATION"}, format="json")
    assert again.data["probability"] == 45  # a custom number is kept
    won = tenant_a.client.patch(f"/api/v1/crm/opportunities/{opp_id}/", {"stage": "WON"}, format="json")
    assert won.status_code == 200, won.data


def test_forecast_is_not_zero_for_a_deal_nobody_edited(tenant_a):
    _flags(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/crm/opportunities/", {"title": "Plain", "amount": "1000", "stage": "OPEN"}, format="json",
    )
    assert created.status_code == 201, created.data
    report = pipeline_forecast(tenant_a.company)
    assert report["unscheduled"] == "100.00"


def test_convert_starts_at_the_stage_default(tenant_a):
    _flags(tenant_a.company)
    opened = tenant_a.client.post("/api/v1/crm/leads/", {"name": "P1", "phone": "9000000551"}, format="json")
    conv = tenant_a.client.post(f"/api/v1/crm/leads/{opened.data['id']}/convert/", {}, format="json")
    assert conv.data["opportunity"]["probability"] == 10
    other = tenant_a.client.post("/api/v1/crm/leads/", {"name": "P2", "phone": "9000000552"}, format="json")
    won = tenant_a.client.post(
        f"/api/v1/crm/leads/{other.data['id']}/convert/", {"won": True, "amount": "50"}, format="json",
    )
    assert won.data["opportunity"]["probability"] == 100


def test_reopen_puts_the_default_win_chance_back(tenant_a):
    _flags(tenant_a.company)
    other = tenant_a.client.post("/api/v1/crm/leads/", {"name": "P3", "phone": "9000000553"}, format="json")
    won = tenant_a.client.post(
        f"/api/v1/crm/leads/{other.data['id']}/convert/", {"won": True, "amount": "50"}, format="json",
    )
    opp_id = won.data["opportunity"]["id"]
    reopened = tenant_a.client.post(f"/api/v1/crm/opportunities/{opp_id}/reopen/")
    assert reopened.status_code == 200, reopened.data
    assert reopened.data["probability"] == 10


def test_lists_carry_names_and_support_search_and_status_filters(tenant_a):
    from crm.models import Campaign, Lead
    from crm.pipeline import capture_lead

    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company, name="Named Buyer")
    campaign = Campaign.objects.create(
        company=tenant_a.company, name="Spring push", campaign_type=Campaign.Type.DIGITAL,
        status=Campaign.Status.ACTIVE, created_by=tenant_a.owner,
    )
    Campaign.objects.create(
        company=tenant_a.company, name="Autumn push", campaign_type=Campaign.Type.DIGITAL,
        status=Campaign.Status.ACTIVE, created_by=tenant_a.owner,
    )
    lead = capture_lead(tenant_a.company, tenant_a.owner, name="Zainab Khan", phone="9000000611", campaign=campaign.id)
    Lead.objects.filter(pk=lead.pk).update(customer=customer, status=Lead.Status.CONTACTED)
    Campaign.objects.filter(pk=campaign.pk).update(status=Campaign.Status.PAUSED)
    capture_lead(tenant_a.company, tenant_a.owner, name="Other Person", phone="9000000612")

    found = tenant_a.client.get("/api/v1/crm/leads/?q=zainab")
    assert found.status_code == 200 and found.data["count"] == 1
    row = found.data["results"][0]
    assert row["customer_name"] == "Named Buyer" and row["campaign_name"] == "Spring push"
    assert tenant_a.client.get("/api/v1/crm/leads/?q=9000000612").data["count"] == 1
    assert tenant_a.client.get("/api/v1/crm/leads/?status=CONTACTED").data["count"] == 1

    paused = tenant_a.client.get("/api/v1/crm/campaigns/?status=PAUSED")
    assert paused.data["count"] == 1 and paused.data["results"][0]["name"] == "Spring push"

    opp = Opportunity.objects.create(
        company=tenant_a.company, title="Named deal", lead=lead, customer=customer, amount="10",
    )
    detail = tenant_a.client.get(f"/api/v1/crm/opportunities/{opp.id}/")
    assert detail.data["lead_name"] == "Zainab Khan" and detail.data["customer_name"] == "Named Buyer"

    from .conftest import make_product

    product = make_product(tenant_a.company, name="Named product", sku="CRM-NAME")
    made = tenant_a.client.post(
        f"/api/v1/crm/opportunities/{opp.id}/lines/",
        {"product": product.id, "quantity": "1", "unit_price": "5"}, format="json",
    )
    assert made.status_code == 201, made.data
    lines = tenant_a.client.get(f"/api/v1/crm/opportunities/{opp.id}/lines/")
    assert lines.data["results"][0]["product_name"] == "Named product"
