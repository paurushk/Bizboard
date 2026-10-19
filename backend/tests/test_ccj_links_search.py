"""Cross-module pieces of the care/jobs plan: links, timeline, search, alerts, KPIs (XLK-*, FND-*)."""

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from complaints.models import Complaint
from contracts.models import Contract
from insights.alerts import build_business_alerts
from projects.models import Project, ProjectMilestone
from support.models import Ticket
from workshop.models import JobCard, JobCardLine

from .conftest import make_customer, make_product

pytestmark = pytest.mark.django_db


def _on(tenant):
    tenant.company.feature_flags = {
        "ENABLE_SUPPORT_TICKETS": True, "ENABLE_COMPLAINTS": True, "ENABLE_CONTRACTS": True,
        "ENABLE_WORKSHOP": True, "ENABLE_PROJECTS": True,
    }
    tenant.company.save(update_fields=["feature_flags"])


def test_links_list_the_neighbours_of_a_customer_and_hide_other_companies(tenant_a, tenant_b):
    _on(tenant_a)
    _on(tenant_b)
    customer = make_customer(tenant_a.company)
    ticket = Ticket.objects.create(company=tenant_a.company, customer=customer, subject="Noise", number="T-1")
    Complaint.objects.create(
        company=tenant_a.company, customer=customer, category="OTHER", description="Late", number="RMA-1",
    )
    JobCard.objects.create(company=tenant_a.company, customer=customer, number="JOB-1", ticket=ticket)
    Contract.objects.create(
        company=tenant_a.company, customer=customer, contract_type="AMC", number="CON-1",
        start_date=timezone.localdate(), end_date=timezone.localdate() + timedelta(days=90),
    )
    Project.objects.create(company=tenant_a.company, customer=customer, name="Build", number="PRJ-1")
    rows = tenant_a.client.get("/api/v1/links/", {"entity": "customer", "id": customer.id}).data
    assert {row["kind"] for row in rows} == {"ticket", "complaint", "job_card", "contract", "project"}
    assert all(row["href"].startswith("/") for row in rows)
    assert tenant_a.client.get("/api/v1/links/", {"entity": "ticket", "id": ticket.id}).data[0]["kind"] == "job_card"
    assert tenant_b.client.get("/api/v1/links/", {"entity": "ticket", "id": ticket.id}).status_code == 404
    assert tenant_a.client.get("/api/v1/links/", {"entity": "nonsense", "id": 1}).status_code == 404
    assert tenant_a.client.get("/api/v1/links/", {"entity": "ticket"}).status_code == 400


def test_the_timeline_only_serves_known_record_types_and_respects_the_purchases_right(tenant_a, tenant_b):
    _on(tenant_a)
    assert tenant_a.client.get("/api/v1/audit-timeline/", {"entity": "Customer", "id": 1}).status_code == 400
    assert tenant_a.client.get("/api/v1/audit-timeline/", {"entity": "Ticket", "id": "x"}).status_code == 400
    # a sales-only staff member cannot read the supplier-complaint timeline
    assert tenant_a.staff_client.get(
        "/api/v1/audit-timeline/", {"entity": "SupplierComplaint", "id": 1},
    ).status_code == 403
    ticket = Ticket.objects.create(company=tenant_a.company, customer=make_customer(tenant_a.company), subject="s")
    assert tenant_b.client.get("/api/v1/audit-timeline/", {"entity": "Ticket", "id": ticket.id}).data == []


def test_global_search_reaches_jobs_projects_and_the_vendor_inbox(tenant_a, tenant_b):
    from django.utils import timezone as tz

    from support.models import VendorTicketShare

    _on(tenant_a)
    _on(tenant_b)
    customer = make_customer(tenant_a.company, name="Zed Garage")
    JobCard.objects.create(
        company=tenant_a.company, customer=customer, number="JOB-77", registration_no="MH12ZZ0007",
    )
    Project.objects.create(company=tenant_a.company, customer=customer, name="Zed expansion", number="PRJ-77")
    found = tenant_a.client.get("/api/v1/search/", {"q": "zed"}).data
    assert [row["number"] for row in found["job_cards"]] == ["JOB-77"]
    assert [row["number"] for row in found["projects"]] == ["PRJ-77"]
    assert tenant_a.client.get("/api/v1/search/", {"q": "mh12zz"}).data["job_cards"][0]["number"] == "JOB-77"
    assert tenant_b.client.get("/api/v1/search/", {"q": "zed"}).data["job_cards"] == []
    with override_settings(VENDOR_COMPANY_ID=str(tenant_b.company.id)):
        VendorTicketShare.objects.create(
            company=tenant_b.company, vendor_company=tenant_b.company, source_company=tenant_a.company,
            source_ticket_id=5, source_number="TKT-5", subject="Gearbox", status="OPEN", shared_at=tz.now(),
        )
        hit = tenant_b.client.get("/api/v1/search/", {"q": "gearbox"}).data
        assert hit["shared_tickets"][0]["number"] == "TKT-5"
        assert tenant_a.client.get("/api/v1/search/", {"q": "gearbox"}).data["shared_tickets"] == []


def test_alerts_cover_overdue_milestones_ready_jobs_and_renewals_with_detail_links(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    project = Project.objects.create(company=tenant_a.company, customer=customer, name="B", number="PRJ-2")
    service = make_product(tenant_a.company, name="Design", sku="D-1", product_type="SERVICE")
    ProjectMilestone.objects.create(
        company=tenant_a.company, project=project, name="Slab", amount=100, service_product=service,
        target_completion_date=timezone.localdate() - timedelta(days=2),
    )
    job = JobCard.objects.create(
        company=tenant_a.company, customer=customer, number="JOB-2", status=JobCard.Status.IN_PROGRESS,
    )
    part = make_product(tenant_a.company, name="Spare", sku="S-1", product_type="GOODS")
    JobCardLine.objects.create(company=tenant_a.company, job=job, kind="PART", product=part, quantity=1, unit_price=1)
    contract = Contract.objects.create(
        company=tenant_a.company, customer=customer, contract_type="AMC", number="CON-2",
        start_date=timezone.localdate() - timedelta(days=300), end_date=timezone.localdate() + timedelta(days=5),
    )
    ticket = Ticket.objects.create(
        company=tenant_a.company, customer=customer, subject="s", number="T-3",
        sla_due_at=timezone.now() - timedelta(hours=1),
    )
    alerts = {row["code"]: row for row in build_business_alerts(tenant_a.company)}
    assert alerts["MILESTONE_OVERDUE"]["cta_path"] == f"/projects/{project.id}"
    assert alerts["JOB_READY_TO_INVOICE"]["cta_path"] == f"/workshop/jobs/{job.id}"
    assert alerts["CONTRACT_RENEWAL"]["cta_path"] == f"/contracts/{contract.id}"
    assert alerts["TICKET_SLA_BREACH"]["cta_path"] == f"/support/tickets/{ticket.id}"


def test_care_kpis_summarise_the_period_and_follow_the_flags(tenant_a, tenant_b):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    now = timezone.now()
    Ticket.objects.create(
        company=tenant_a.company, customer=customer, subject="ok", number="T-4", status="RESOLVED",
        sla_due_at=now + timedelta(hours=5), resolved_at=now,
    )
    Ticket.objects.create(
        company=tenant_a.company, customer=customer, subject="late", number="T-5", status="RESOLVED",
        sla_due_at=now - timedelta(hours=5), resolved_at=now,
    )
    data = tenant_a.client.get("/api/v1/care-kpis/", {"days": 30}).data
    assert data["tickets"]["resolved"] == 2 and data["tickets"]["sla_met_percent"] == 50
    assert {"complaints", "workshop", "projects", "contracts"} <= set(data)
    tenant_b.company.feature_flags = {}
    tenant_b.company.save(update_fields=["feature_flags"])
    assert "tickets" not in tenant_b.client.get("/api/v1/care-kpis/").data
    assert tenant_a.client.get("/api/v1/care-kpis/", {"days": "abc"}).data["days"] == 90
