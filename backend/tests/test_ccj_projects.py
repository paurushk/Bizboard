"""Jobs & contracts plan: projects and milestones (PRJ-*)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from contracts.models import Contract
from core.models import AuditEvent
from projects.models import Project, ProjectMilestone
from projects.tasks import send_milestone_due_reminders
from sales.models import SalesInvoice
from sales.services import SalesService

from .conftest import make_customer, make_product

pytestmark = pytest.mark.django_db

URL = "/api/v1/projects/"
_SKU = {"n": 0}


def _on(tenant):
    tenant.company.feature_flags = {"ENABLE_PROJECTS": True, "ENABLE_CONTRACTS": True}
    tenant.company.save(update_fields=["feature_flags"])


def _service(tenant, rate="18"):
    _SKU["n"] += 1
    return make_product(
        tenant.company, name=f"Design {_SKU['n']}", sku=f"SV-{_SKU['n']}", product_type="SERVICE", gst_rate=rate,
    )


def _project(tenant, customer=None, **extra):
    customer = customer or make_customer(tenant.company)
    resp = tenant.client.post(URL, {"customer": customer.id, "name": "Site build", **extra}, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data


def _milestone(tenant, project_id, name="Phase 1", amount="1000", **extra):
    resp = tenant.client.post(
        f"{URL}{project_id}/milestones/",
        {"name": name, "amount": amount, "service_product": _service(tenant).id, **extra}, format="json",
    )
    assert resp.status_code == 200, resp.data
    return resp.data["milestones"][-1]


def _act(tenant, project_id, milestone_id, step):
    return tenant.client.post(f"{URL}{project_id}/milestones/{milestone_id}/{step}/")


# ---- PRJ-01: nothing can get stuck ------------------------------------------------------------------------------------------------

def test_a_ready_milestone_can_go_back_and_be_removed_so_the_project_can_close(tenant_a):
    _on(tenant_a)
    project = _project(tenant_a)
    keep = _milestone(tenant_a, project["id"], "Keep")
    stuck = _milestone(tenant_a, project["id"], "Abandoned")
    assert _act(tenant_a, project["id"], stuck["id"], "ready").status_code == 200
    blocked = tenant_a.client.post(f"{URL}{project['id']}/close/")
    assert blocked.status_code == 400 and "Abandoned" in str(blocked.data)
    back = tenant_a.client.post(
        f"{URL}{project['id']}/milestone-unready/", {"milestone": stuck["id"]}, format="json",
    )
    assert back.status_code == 200
    assert {m["id"]: m["status"] for m in back.data["milestones"]}[stuck["id"]] == "PLANNED"
    assert _act(tenant_a, project["id"], stuck["id"], "delete").status_code == 200
    _act(tenant_a, project["id"], keep["id"], "ready")
    invoiced = _act(tenant_a, project["id"], keep["id"], "invoice")
    assert invoiced.status_code == 200
    draft_id = ProjectMilestone.objects.get(pk=keep["id"]).sales_invoice_id
    SalesService.complete(SalesInvoice.objects.get(pk=draft_id), tenant_a.owner)
    closed = tenant_a.client.post(f"{URL}{project['id']}/close/")
    assert closed.status_code == 200 and closed.data["status"] == "CLOSED"


def test_a_milestone_with_an_invoice_cannot_be_unreadied_or_deleted(tenant_a):
    _on(tenant_a)
    project = _project(tenant_a)
    milestone = _milestone(tenant_a, project["id"])
    _act(tenant_a, project["id"], milestone["id"], "ready")
    _act(tenant_a, project["id"], milestone["id"], "invoice")
    assert tenant_a.client.post(
        f"{URL}{project['id']}/milestone-unready/", {"milestone": milestone["id"]}, format="json",
    ).status_code == 400
    assert _act(tenant_a, project["id"], milestone["id"], "delete").status_code == 400


# ---- PRJ-02: cancel and close ------------------------------------------------------------------------------------------------------

def test_an_empty_project_is_cancelled_not_closed(tenant_a):
    _on(tenant_a)
    project = _project(tenant_a)
    assert tenant_a.client.post(f"{URL}{project['id']}/close/").status_code == 400
    assert tenant_a.staff_client.post(f"{URL}{project['id']}/cancel/", {"reason": "x"}, format="json").status_code == 403
    cancelled = tenant_a.client.post(f"{URL}{project['id']}/cancel/", {"reason": "Client withdrew"}, format="json")
    assert cancelled.status_code == 200 and cancelled.data["status"] == "CANCELLED"
    assert tenant_a.client.post(f"{URL}{project['id']}/cancel/").status_code == 400
    assert tenant_a.client.post(
        f"{URL}{project['id']}/milestones/", {"name": "x", "amount": "1", "service_product": 1}, format="json",
    ).status_code == 400


def test_cancelling_discards_draft_invoices_but_not_completed_ones(tenant_a):
    _on(tenant_a)
    project = _project(tenant_a)
    one = _milestone(tenant_a, project["id"], "One")
    _act(tenant_a, project["id"], one["id"], "ready")
    _act(tenant_a, project["id"], one["id"], "invoice")
    draft_id = ProjectMilestone.objects.get(pk=one["id"]).sales_invoice_id
    cancelled = tenant_a.client.post(f"{URL}{project['id']}/cancel/", {"reason": "Stopped"}, format="json")
    assert cancelled.status_code == 200
    assert SalesInvoice.objects.get(pk=draft_id).status == SalesInvoice.Status.CANCELLED
    second = _project(tenant_a)
    done = _milestone(tenant_a, second["id"], "Done")
    _act(tenant_a, second["id"], done["id"], "ready")
    _act(tenant_a, second["id"], done["id"], "invoice")
    SalesService.complete(
        SalesInvoice.objects.get(pk=ProjectMilestone.objects.get(pk=done["id"]).sales_invoice_id), tenant_a.owner,
    )
    refused = tenant_a.client.post(f"{URL}{second['id']}/cancel/", format="json")
    assert refused.status_code == 400 and "completed invoice" in str(refused.data)


# ---- PRJ-03 / PRJ-05: edit and money ------------------------------------------------------------------------------------------------

def test_a_project_can_be_edited_and_shows_where_the_money_stands(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    project = _project(tenant_a, customer, contract_value="2000.00", start_date="2026-11-01", end_date="2027-01-31")
    assert project["customer_name"] == customer.name and project["planned_total"] == "0.00"
    edited = tenant_a.client.patch(
        f"{URL}{project['id']}/", {"name": "Site build phase 2", "notes": "Rev B", "end_date": "2027-02-28"}, format="json",
    )
    assert edited.status_code == 200 and edited.data["name"] == "Site build phase 2"
    assert tenant_a.client.patch(f"{URL}{project['id']}/", {"end_date": "2026-10-01"}, format="json").status_code == 400
    assert tenant_a.client.patch(f"{URL}{project['id']}/", {"name": " "}, format="json").status_code == 400
    one = _milestone(tenant_a, project["id"], "One", amount="1500")
    _milestone(tenant_a, project["id"], "Two", amount="1000")
    shown = tenant_a.client.get(f"{URL}{project['id']}/").data
    assert shown["planned_total"] == "2500.00" and shown["remaining_total"] == "2500.00" and shown["over_budget"] is True
    assert shown["milestones"][0]["gst_amount"] == "270.00"
    assert shown["milestones"][0]["amount_incl_gst"] == "1770.00"
    _act(tenant_a, project["id"], one["id"], "ready")
    _act(tenant_a, project["id"], one["id"], "invoice")
    SalesService.complete(
        SalesInvoice.objects.get(pk=ProjectMilestone.objects.get(pk=one["id"]).sales_invoice_id), tenant_a.owner,
    )
    final = tenant_a.client.get(f"{URL}{project['id']}/").data
    assert final["invoiced_total"] == "1500.00" and final["percent_complete"] == 60 and final["remaining_total"] == "1000.00"
    row = tenant_a.client.get(URL).data["results"][0]
    assert "milestones" not in row and row["milestone_count"] == 2 and row["percent_complete"] == 60


def test_a_closed_project_cannot_be_edited(tenant_a):
    _on(tenant_a)
    project = _project(tenant_a)
    tenant_a.client.post(f"{URL}{project['id']}/cancel/")
    assert tenant_a.client.patch(f"{URL}{project['id']}/", {"name": "New"}, format="json").status_code == 400


# ---- PRJ-04: order and warning -------------------------------------------------------------------------------------------------------

def test_milestones_can_be_reordered_and_invoicing_out_of_order_warns(tenant_a):
    _on(tenant_a)
    project = _project(tenant_a)
    first = _milestone(tenant_a, project["id"], "First")
    second = _milestone(tenant_a, project["id"], "Second")
    assert [first["sequence"], second["sequence"]] == [1, 2]
    reordered = tenant_a.client.post(
        f"{URL}{project['id']}/milestones/reorder/", {"order": [second["id"], first["id"]]}, format="json",
    )
    assert reordered.status_code == 200
    assert [m["name"] for m in reordered.data["milestones"]] == ["Second", "First"]
    assert tenant_a.client.post(
        f"{URL}{project['id']}/milestones/reorder/", {"order": [first["id"]]}, format="json",
    ).status_code == 400
    _act(tenant_a, project["id"], first["id"], "ready")
    out_of_order = _act(tenant_a, project["id"], first["id"], "invoice")
    assert out_of_order.status_code == 200 and "Second" in out_of_order.data["warning"]


# ---- PRJ-06: invoices trace back to the project -----------------------------------------------------------------------------------

def test_the_invoice_line_names_the_project_and_a_linked_draft_is_read_only_in_sales(tenant_a):
    _on(tenant_a)
    project = _project(tenant_a)
    milestone = _milestone(tenant_a, project["id"], "Foundations")
    _act(tenant_a, project["id"], milestone["id"], "ready")
    _act(tenant_a, project["id"], milestone["id"], "invoice")
    invoice = SalesInvoice.objects.get(pk=ProjectMilestone.objects.get(pk=milestone["id"]).sales_invoice_id)
    assert invoice.items.first().description.startswith(project["number"])
    assert "Foundations" in invoice.items.first().description
    product = invoice.items.first().product
    edit = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{invoice.id}/",
        {"items": [{"product": product.id, "quantity": "1", "unit_price": "1", "gst_rate": "18"}]}, format="json",
    )
    assert edit.status_code == 400 and "milestone" in str(edit.data).lower()
    links = tenant_a.client.get("/api/v1/links/", {"entity": "invoice", "id": invoice.id}).data
    assert [row["kind"] for row in links] == ["project"]
    shown = tenant_a.client.get(f"{URL}{project['id']}/").data["milestones"][0]
    assert shown["invoice_status"] == "DRAFT"


# ---- PRJ-08 / PRJ-09 ---------------------------------------------------------------------------------------------------------------------

def test_a_project_can_name_a_contract_of_the_same_customer(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    other = make_customer(tenant_a.company, name="Other")
    contract = Contract.objects.create(
        company=tenant_a.company, customer=customer, contract_type="AMC", number="CON-P1",
        start_date=timezone.localdate(), end_date=timezone.localdate() + timedelta(days=200),
    )
    project = _project(tenant_a, customer, contract=contract.id)
    assert project["contract_number"] == "CON-P1"
    bad = tenant_a.client.post(URL, {"customer": other.id, "name": "x", "contract": contract.id}, format="json")
    assert bad.status_code == 400
    links = tenant_a.client.get("/api/v1/links/", {"entity": "contract", "id": contract.id}).data
    assert [row["kind"] for row in links] == ["project"]


def test_overdue_milestones_are_reminded_once(tenant_a):
    _on(tenant_a)
    project = _project(tenant_a)
    late = _milestone(tenant_a, project["id"], "Late one", target_completion_date=str(timezone.localdate() - timedelta(days=3)))
    assert send_milestone_due_reminders()["reminders"] == 1
    assert send_milestone_due_reminders()["reminders"] == 0
    ProjectMilestone.objects.filter(pk=late["id"]).update(status="INVOICED")
    assert AuditEvent.objects.filter(action="milestone_overdue_reminder", entity_id=str(project["id"])).count() == 1
    assert Decimal("0") == Decimal("0.00")


def test_search_filters_audit_and_tenancy(tenant_a, tenant_b):
    _on(tenant_a)
    _on(tenant_b)
    acme = make_customer(tenant_a.company, name="Acme Builders")
    project = _project(tenant_a, acme, name="Warehouse extension")
    _project(tenant_a, name="Other job")
    assert tenant_a.client.get(URL, {"q": "warehouse"}).data["count"] == 1
    assert tenant_a.client.get(URL, {"q": "acme"}).data["count"] == 1
    assert tenant_a.client.get(URL, {"customer": acme.id}).data["count"] == 1
    _milestone(tenant_a, project["id"])
    actions = set(
        AuditEvent.objects.filter(company=tenant_a.company, entity_type="Project", entity_id=str(project["id"]))
        .values_list("action", flat=True)
    )
    assert {"project_created", "milestone_added"} <= actions
    assert len(tenant_a.client.get(f"{URL}{project['id']}/activity/").data) >= 2
    assert tenant_b.client.get(f"{URL}{project['id']}/").status_code == 404
    assert tenant_b.client.get(URL, {"q": "warehouse"}).data["count"] == 0
    assert Project.objects.filter(company=tenant_a.company).count() == 2
    assert tenant_b.client.post(
        f"{URL}{project['id']}/milestone-unready/", {"milestone": 1}, format="json",
    ).status_code == 404
