"""PJ-CONTRACTS-AND-FIELD-SERVICE — Archetype Commercial Service & Maintenance Contractor Journey.

Validates:
1. Commercial Equipment Maintenance Contractor Archetype:
   - Creating Warranty/AMC contracts with customer, equipment product, and financial value.
   - Deterministic status computation (ACTIVE -> EXPIRING -> EXPIRED).
   - Attention engine integration (CONTRACT_RENEWAL items in attention feed).
2. Field Service Technician Persona:
   - On-site visit logging (ContractServiceEvent) with notes and customer link.
   - Inspection timeline aggregation (/timeline/).
   - Contract report rollups by type and status (/report/).
3. Capability & Visibility Boundaries:
   - Sales Staff / Field Tech creates contracts and service events.
   - Accountant (books-only) is denied contract creation/mutation.
4. Data Integrity:
   - Clean invariant sweeps across all operations.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from contracts.models import Contract
from contracts.tasks import refresh_contract_statuses
from core.invariants import assert_all_invariants
from insights.attention import build_attention_rows
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def test_pj_commercial_contractor_amc_and_field_service_journey(boundary):
    ns = seed_archetype("contractor")
    company = ns.company
    company.feature_flags = {
        "ENABLE_CONTRACTS": True,
        "ENABLE_SUPPORT_TICKETS": True,
    }
    company.save(update_fields=["feature_flags"])

    oc = ns.owner_client
    sc = ns.sales_client
    ac = ns.acct_client
    cust = ns.customers[0]
    equipment = next(p for p in ns.products if p.product_type == "GOODS")

    today = timezone.localdate()
    start_date = (today - timedelta(days=300)).isoformat()
    end_date = (today + timedelta(days=10)).isoformat()

    # 1. P2/P3 Sales Staff / Service Manager creates AMC contract
    create_resp = sc.post(
        "/api/v1/contracts/",
        {
            "customer": cust.id,
            "product": equipment.id,
            "contract_type": Contract.Type.AMC,
            "start_date": start_date,
            "end_date": end_date,
            "renewal_reminder_days": 15,
            "value": "25000.00",
            "notes": "HVAC Annual Maintenance Contract - Year 1",
        },
        format="json",
    )
    assert create_resp.status_code == 201, create_resp.data
    contract_id = create_resp.data["id"]
    contract_number = create_resp.data["number"]
    assert contract_number.startswith("CON-")
    # Because today + 10 days <= 15 days reminder window, status is EXPIRING
    assert create_resp.data["status"] == Contract.Status.EXPIRING

    # 2. Attention Feed verifies renewal alert for business owner
    attention_items = build_attention_rows(company)
    renewal_alerts = [
        row for row in attention_items if row.get("code") == "CONTRACT_RENEWAL"
    ]
    assert len(renewal_alerts) >= 1
    assert any(f"Contract {contract_number}" in str(row.get("title") or "") for row in renewal_alerts)

    # 3. Field Service Technician visits customer site and logs service event
    event_resp = sc.post(
        f"/api/v1/contracts/{contract_id}/service-events/",
        {
            "notes": "Quarterly compressor coil cleaning and refrigerant pressure check completed.",
        },
        format="json",
    )
    assert event_resp.status_code == 201, event_resp.data
    event_id = event_resp.data["id"]
    assert event_resp.data["notes"] == "Quarterly compressor coil cleaning and refrigerant pressure check completed."

    # 4. Service Manager retrieves contract timeline
    timeline_resp = sc.get(f"/api/v1/contracts/{contract_id}/timeline/")
    assert timeline_resp.status_code == 200
    timeline_data = timeline_resp.data
    assert timeline_data["contract"]["id"] == contract_id
    assert len(timeline_data["events"]) == 1
    assert timeline_data["events"][0]["id"] == event_id

    # 5. Review Contract value report
    report_resp = oc.get("/api/v1/contracts/report/")
    assert report_resp.status_code == 200
    matching_reports = [
        r for r in report_resp.data
        if r["contract_type"] == Contract.Type.AMC and r["status"] == Contract.Status.EXPIRING
    ]
    assert len(matching_reports) == 1
    assert Decimal(matching_reports[0]["value"]) == Decimal("25000.00")

    # 6. Nightly refresh task: advance contract past end date and verify transition to EXPIRED
    contract_obj = Contract.objects.get(id=contract_id)
    contract_obj.end_date = today - timedelta(days=1)
    contract_obj.save(update_fields=["end_date"])

    refresh_contract_statuses()
    contract_obj.refresh_from_db()
    assert contract_obj.status == Contract.Status.EXPIRED

    # 7. Role boundaries: Accountant (books-only) cannot create or mutate contracts
    boundary.denied(
        ac,
        "POST",
        "/api/v1/contracts/",
        data={
            "customer": cust.id,
            "contract_type": Contract.Type.WARRANTY,
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=365)).isoformat(),
        },
        format="json",
    )

    # 8. Complete invariant verification
    assert_all_invariants(company)
