"""Sprint B: CRM lead convert + activities. Still gated by ENABLE_CRM."""

import pytest
from django.test import override_settings

from crm.models import Lead, LeadActivity, Opportunity
from masters.models import Customer

pytestmark = pytest.mark.django_db


def _body(resp):
    data = resp.data
    if isinstance(data, dict) and isinstance(data.get("data"), (dict, list)):
        return data["data"]
    return data


def test_convert_lead_creates_customer_and_open_opportunity(tenant_a):
    lead_resp = tenant_a.client.post(
        "/api/v1/crm/leads/",
        {"name": "Prospect Co", "phone": "9876543210", "email": "p@example.com", "status": "NEW"},
        format="json",
    )
    assert lead_resp.status_code == 201, lead_resp.data
    lead_id = _body(lead_resp)["id"]
    converted = tenant_a.client.post(f"/api/v1/crm/leads/{lead_id}/convert/")
    assert converted.status_code == 200, converted.data
    body = _body(converted)
    lead = Lead.objects.get(pk=lead_id)
    assert lead.status == Lead.Status.QUALIFIED
    assert lead.customer_id is not None
    customer = Customer.objects.get(pk=lead.customer_id)
    assert customer.name == "Prospect Co"
    assert customer.phone == "+919876543210"
    assert customer.email == "p@example.com"
    opp = Opportunity.objects.get(pk=body["opportunity"]["id"])
    assert opp.stage == Opportunity.Stage.OPEN
    assert opp.lead_id == lead_id
    assert opp.customer_id == customer.id


def test_convert_lead_won_query_param(tenant_a):
    lead_resp = tenant_a.client.post(
        "/api/v1/crm/leads/",
        {"name": "Won Lead", "status": "CONTACTED"},
        format="json",
    )
    lead_id = _body(lead_resp)["id"]
    converted = tenant_a.client.post(f"/api/v1/crm/leads/{lead_id}/convert/?won=1")
    assert converted.status_code == 200, converted.data
    opp_id = _body(converted)["opportunity"]["id"]
    assert Opportunity.objects.get(pk=opp_id).stage == Opportunity.Stage.WON


def test_convert_reuses_existing_customer(tenant_a):
    from tests.conftest import make_customer

    customer = make_customer(tenant_a.company, name="Existing")
    lead_resp = tenant_a.client.post(
        "/api/v1/crm/leads/",
        {"name": "Linked", "status": "NEW", "customer": customer.id},
        format="json",
    )
    lead_id = _body(lead_resp)["id"]
    before = Customer.objects.filter(company=tenant_a.company).count()
    converted = tenant_a.client.post(f"/api/v1/crm/leads/{lead_id}/convert/")
    assert converted.status_code == 200, converted.data
    assert Customer.objects.filter(company=tenant_a.company).count() == before
    assert Lead.objects.get(pk=lead_id).customer_id == customer.id


def test_r077_e164_lead_matches_ten_digit_customer(tenant_a):
    """R-077: +91 lead phone matches a legacy 10-digit customer."""
    from crm.services import convert_lead

    ten = "9876512345"
    e164 = "+919876512345"

    cust_ten = Customer.objects.create(
        company=tenant_a.company,
        name="Ten Digit",
        phone=ten,
        state=tenant_a.company.state or "MH",
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    lead_e164 = Lead.objects.create(
        company=tenant_a.company,
        name="E164 Lead",
        phone=e164,
        status=Lead.Status.NEW,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    assert lead_e164.phone == e164
    _lead, _opp, matched = convert_lead(lead_e164, tenant_a.owner)
    assert matched.id == cust_ten.id


def test_r077_ten_digit_lead_matches_e164_customer(tenant_a):
    """R-077: 10-digit lead canonicalizes and matches an E.164 customer."""
    from crm.services import convert_lead

    ten = "9876512346"
    e164 = "+919876512346"

    cust_e164 = Customer.objects.create(
        company=tenant_a.company,
        name="E164 Cust",
        phone=e164,
        state=tenant_a.company.state or "MH",
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    lead_ten = Lead.objects.create(
        company=tenant_a.company,
        name="Ten Lead",
        phone=ten,
        status=Lead.Status.NEW,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    assert lead_ten.phone == e164
    _lead, _opp, matched = convert_lead(lead_ten, tenant_a.owner)
    assert matched.id == cust_e164.id


def test_r077_multiple_phone_matches_raise(tenant_a):
    """R-077: ambiguous phone twins stay a BusinessRuleError."""
    from core.exceptions import BusinessRuleError
    from crm.services import convert_lead

    phone = "9876599999"
    for name in ("Dup A", "Dup B"):
        Customer.objects.create(
            company=tenant_a.company,
            name=name,
            phone=phone,
            state=tenant_a.company.state or "MH",
            created_by=tenant_a.owner,
            updated_by=tenant_a.owner,
        )
    lead = Lead.objects.create(
        company=tenant_a.company,
        name="Ambiguous",
        phone=f"+91{phone}",
        status=Lead.Status.NEW,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    with pytest.raises(BusinessRuleError, match="Multiple customers share this phone"):
        convert_lead(lead, tenant_a.owner)


def test_lead_activities_get_post(tenant_a):
    lead_resp = tenant_a.client.post(
        "/api/v1/crm/leads/",
        {"name": "Call me", "status": "NEW"},
        format="json",
    )
    lead_id = _body(lead_resp)["id"]
    created = tenant_a.client.post(
        f"/api/v1/crm/leads/{lead_id}/activities/",
        {"kind": "CALL", "body": "Spoke to owner"},
        format="json",
    )
    assert created.status_code == 201, created.data
    listing = tenant_a.client.get(f"/api/v1/crm/leads/{lead_id}/activities/")
    assert listing.status_code == 200, listing.data
    rows = _body(listing)
    assert len(rows) == 1
    assert rows[0]["kind"] == "CALL"
    assert rows[0]["body"] == "Spoke to owner"
    assert LeadActivity.objects.filter(lead_id=lead_id, kind=LeadActivity.Kind.CALL).exists()


@override_settings(ENABLE_CRM=False)
def test_crm_convert_gated_when_flag_off(tenant_a):
    assert tenant_a.client.get("/api/v1/crm/leads/").status_code == 404
    assert tenant_a.client.post("/api/v1/crm/leads/1/convert/").status_code == 404


def test_opportunity_stage_is_terminal_once_won(tenant_a):
    """B9-039: WON/LOST are terminal -- can't flip back to OPEN or to each other."""
    opp = Opportunity.objects.create(company=tenant_a.company, title="Deal 1", amount="500")
    won = tenant_a.client.patch(
        f"/api/v1/crm/opportunities/{opp.id}/", {"stage": "WON"}, format="json",
    )
    assert won.status_code == 200, won.data
    assert won.data["stage"] == "WON"
    assert won.data["closed_at"] is not None

    reopen = tenant_a.client.patch(
        f"/api/v1/crm/opportunities/{opp.id}/", {"stage": "OPEN"}, format="json",
    )
    assert reopen.status_code == 400, reopen.data

    flip = tenant_a.client.patch(
        f"/api/v1/crm/opportunities/{opp.id}/", {"stage": "LOST"}, format="json",
    )
    assert flip.status_code == 400, flip.data


def test_opportunity_open_to_lost_stamps_closed_at_once(tenant_a):
    opp = Opportunity.objects.create(company=tenant_a.company, title="Deal 2", amount="200")
    assert opp.closed_at is None
    resp = tenant_a.client.patch(
        f"/api/v1/crm/opportunities/{opp.id}/", {"stage": "LOST"}, format="json",
    )
    assert resp.status_code == 200, resp.data
    opp.refresh_from_db()
    assert opp.stage == Opportunity.Stage.LOST
    assert opp.closed_at is not None
