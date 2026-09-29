"""PJ-CUSTOMER-SUPPORT-AND-COMPLAINTS — Customer Support & RMA Operations Journey.

Validates:
1. Customer Support & After-Sales RMA Archetype:
   - Ticketing lifecycle with SLA calculation, status progression, and internal collaboration.
   - Formal customer defect complaints linked to original sales invoices.
   - Inspection notes capture and resolution lifecycle.
2. User Personas:
   - Customer Support Agent: Ticket management, status transitions, SLA monitoring.
   - Quality / Claims Inspector: Hardware inspection, notes logging, and complaint resolution.
   - Read-only Viewer: Access boundaries and mutation denial.
3. Capability & Visibility Boundaries:
   - Viewer denied POST /tickets/ and POST /complaints/.
   - Sales staff authorized to log and progress tickets and complaints.
4. Data Integrity:
   - Clean invariant sweeps across all operations.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from complaints.models import Complaint
from core.invariants import assert_all_invariants
from support.models import Ticket
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def test_pj_support_agent_and_claims_inspector_lifecycle(boundary):
    ns = seed_archetype("trader")
    company = ns.company
    company.feature_flags = {
        "ENABLE_COMPLAINTS": True,
        "ENABLE_SUPPORT_TICKETS": True,
    }
    company.save(update_fields=["feature_flags"])

    oc = ns.owner_client
    sc = ns.sales_client
    vc = ns.viewer_client
    cust = ns.customers[0]
    product = next(p for p in ns.products if not p.track_batch)
    today_str = timezone.localdate().isoformat()

    # Step 0: Inward stock and complete a sales invoice for reference
    from inventory.models import MovementType
    from inventory.services import InventoryService

    InventoryService.post_movement(
        company=company,
        product=product,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("50.000"),
        unit_cost=Decimal("250.00"),
        user=ns.owner,
    )

    inv_resp = sc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "GST",
            "invoice_date": today_str,
            "items": [{"product": product.id, "quantity": "2.000", "unit_price": "500.00", "gst_rate": "18.00"}],
        },
        format="json",
    )
    assert inv_resp.status_code == 201, inv_resp.data
    inv_id = inv_resp.data["id"]
    assert sc.post(f"/api/v1/sales/invoices/{inv_id}/complete/").status_code == 200

    # Step 1: Customer calls in -> Support Agent creates urgent Ticket
    ticket_resp = sc.post(
        "/api/v1/support/tickets/",
        {
            "customer": cust.id,
            "subject": "Hardware unit stopped powering on",
            "description": "Customer reports smoke from power adapter upon first boot.",
            "priority": Ticket.Priority.URGENT,
        },
        format="json",
    )
    assert ticket_resp.status_code == 201, ticket_resp.data
    ticket_id = ticket_resp.data["id"]
    ticket_number = ticket_resp.data["number"]
    assert ticket_number.startswith("TKT-")
    assert ticket_resp.data["status"] == Ticket.Status.OPEN
    # URGENT priority enforces 4h SLA offset
    assert ticket_resp.data["sla_due_at"] is not None

    # Step 2: Support Agent begins investigation and logs internal comment
    trans_resp = sc.post(
        f"/api/v1/support/tickets/{ticket_id}/transition/",
        {"status": Ticket.Status.IN_PROGRESS},
        format="json",
    )
    assert trans_resp.status_code == 200
    assert trans_resp.data["status"] == Ticket.Status.IN_PROGRESS

    comment_resp = sc.post(
        f"/api/v1/support/tickets/{ticket_id}/comments/",
        {"body": "Spoke with client on phone. Requested unit return for RMA inspection."},
        format="json",
    )
    assert comment_resp.status_code == 201
    assert comment_resp.data["body"] == "Spoke with client on phone. Requested unit return for RMA inspection."

    # Step 3: Claims Inspector files defective product Complaint referencing original invoice
    comp_resp = sc.post(
        "/api/v1/complaints/",
        {
            "customer": cust.id,
            "category": "DAMAGED",
            "description": "Internal transformer blown on arrival",
            "source_invoice": inv_id,
        },
        format="json",
    )
    assert comp_resp.status_code == 201, comp_resp.data
    comp_id = comp_resp.data["id"]
    comp_number = comp_resp.data["number"]
    assert comp_number.startswith("RMA-")
    assert comp_resp.data["status"] == Complaint.Status.OPEN

    # Step 4: Claims Inspector inspects physical device and logs inspection notes
    inspect_resp = sc.post(
        f"/api/v1/complaints/{comp_id}/transition/",
        {
            "status": Complaint.Status.INSPECTING,
            "inspection_notes": "Burn marks verified near primary input coil. Defect covered under manufacturer warranty.",
        },
        format="json",
    )
    assert inspect_resp.status_code == 200
    assert inspect_resp.data["status"] == Complaint.Status.INSPECTING

    # Step 5: Claims Inspector approves complaint and resolves it
    approve_resp = sc.post(
        f"/api/v1/complaints/{comp_id}/transition/",
        {"status": Complaint.Status.APPROVED},
        format="json",
    )
    assert approve_resp.status_code == 200
    assert approve_resp.data["status"] == Complaint.Status.APPROVED

    resolve_comp = sc.post(
        f"/api/v1/complaints/{comp_id}/transition/",
        {"status": Complaint.Status.RESOLVED},
        format="json",
    )
    assert resolve_comp.status_code == 200
    assert resolve_comp.data["status"] == Complaint.Status.RESOLVED

    # Step 6: Support Agent closes customer support ticket
    resolve_ticket = sc.post(
        f"/api/v1/support/tickets/{ticket_id}/transition/",
        {"status": Ticket.Status.RESOLVED},
        format="json",
    )
    assert resolve_ticket.status_code == 200
    assert resolve_ticket.data["status"] == Ticket.Status.RESOLVED

    # Step 7: Role boundary checks — Viewer cannot mutate tickets or complaints
    boundary.denied(
        vc,
        "POST",
        "/api/v1/support/tickets/",
        data={"customer": cust.id, "subject": "Should fail", "priority": "LOW"},
        format="json",
    )
    boundary.denied(
        vc,
        "POST",
        "/api/v1/complaints/",
        data={"customer": cust.id, "category": "DAMAGED", "description": "Should fail"},
        format="json",
    )

    # Step 8: Clean invariant verification
    assert_all_invariants(company)
