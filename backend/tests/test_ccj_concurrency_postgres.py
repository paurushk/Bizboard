"""Care/jobs plan QA-02: races that only a real database lock can settle.

SQLite does not enforce row locks, so these skip unless the database is PostgreSQL.
"""

from __future__ import annotations

import threading
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from core.exceptions import BusinessRuleError, ConflictError
from workshop.models import JobCard, ServiceBay
from workshop.services import create_job

from .conftest import make_customer

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres]


def _require_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row-level locking (select_for_update)")


def _race(workers):
    """Run each callable in its own thread at the same moment; return (results, errors)."""
    results, errors = [], []
    barrier = threading.Barrier(len(workers), timeout=15)

    def run(work):
        connection.close()
        try:
            barrier.wait()
            results.append(work())
        except (BusinessRuleError, ConflictError) as exc:
            errors.append(exc)
        except Exception as exc:  # pragma: no cover — unexpected
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=(work,)) for work in workers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results, errors


def test_two_bookings_of_one_bay_cannot_both_win(tenant_a):
    _require_postgres()
    bay = ServiceBay.objects.create(company=tenant_a.company, name="Race bay")
    customer = make_customer(tenant_a.company)
    start = timezone.now() + timedelta(days=1)
    end = start + timedelta(hours=2)

    def book():
        return create_job(
            tenant_a.company, tenant_a.owner, customer=customer, service_bay=bay,
            scheduled_start=start, scheduled_end=end,
        )

    results, errors = _race([book, book])
    assert len(results) == 1 and len(errors) == 1
    assert JobCard.objects.filter(company=tenant_a.company, service_bay=bay).count() == 1


def test_two_moves_of_one_ticket_cannot_both_succeed(tenant_a):
    _require_postgres()
    from support.models import Ticket
    from support.tickets import transition_status

    ticket = Ticket.objects.create(
        company=tenant_a.company, customer=make_customer(tenant_a.company), subject="s", number="T-R1",
        status=Ticket.Status.IN_PROGRESS,
    )

    def move():
        return transition_status(Ticket.objects.get(pk=ticket.pk), tenant_a.owner, new_status="RESOLVED")

    results, errors = _race([move, move])
    assert len(results) == 1 and len(errors) == 1
    assert Ticket.objects.get(pk=ticket.pk).status == "RESOLVED"


def test_a_complaint_document_is_created_once_under_a_double_click(tenant_a):
    _require_postgres()
    from complaints.models import Complaint
    from sales.models import SalesCreditNote

    tenant_a.company.feature_flags = {"ENABLE_COMPLAINTS": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    customer = make_customer(tenant_a.company)
    complaint = Complaint.objects.create(
        company=tenant_a.company, customer=customer, category="OTHER", description="d", number="RMA-R1",
        status=Complaint.Status.APPROVED,
    )
    from tests.test_ccj_complaints import _invoice

    invoice, product, line = _invoice(tenant_a, customer)
    Complaint.objects.filter(pk=complaint.pk).update(source_invoice=invoice)
    body = {"items": [{"product": product.id, "quantity": "1", "unit_price": "500", "source_item": line.id}]}

    def click():
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=tenant_a.owner)
        return client.post(f"/api/v1/complaints/{complaint.id}/create-credit-note/", body, format="json").status_code

    results, _errors = _race([click, click])
    assert sorted(results) in ([200, 201], [201, 201])
    assert SalesCreditNote.objects.filter(company=tenant_a.company).count() == 1


def test_two_invoices_of_one_milestone_make_one_draft(tenant_a):
    _require_postgres()
    from masters.models import Product
    from projects.models import Project, ProjectMilestone
    from projects.services import invoice_milestone
    from sales.models import SalesInvoice

    project = Project.objects.create(
        company=tenant_a.company, customer=make_customer(tenant_a.company), name="P", number="PRJ-R1",
    )
    service = Product.objects.create(
        company=tenant_a.company, name="Design", sku="D-R1", product_type="SERVICE", gst_rate=18,
        purchase_price=0, selling_price=0,
    )
    milestone = ProjectMilestone.objects.create(
        company=tenant_a.company, project=project, name="M", amount=100, service_product=service,
        status=ProjectMilestone.Status.READY,
    )

    def invoice():
        return invoice_milestone(ProjectMilestone.objects.get(pk=milestone.pk), tenant_a.owner).pk

    results, _errors = _race([invoice, invoice])
    assert len(set(results)) == 1
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == 1


def test_two_renewals_of_one_contract_do_not_both_apply(tenant_a):
    _require_postgres()
    from contracts.models import Contract, ContractRenewal
    from contracts.ops import renew_contract

    contract = Contract.objects.create(
        company=tenant_a.company, customer=make_customer(tenant_a.company), contract_type="AMC", number="CON-R1",
        start_date=timezone.localdate() - timedelta(days=100), end_date=timezone.localdate() + timedelta(days=10),
    )
    new_end = timezone.localdate() + timedelta(days=375)

    def renew():
        return renew_contract(Contract.objects.get(pk=contract.pk), tenant_a.owner, new_end_date=new_end)

    results, errors = _race([renew, renew])
    assert len(results) == 1 and len(errors) == 1
    assert ContractRenewal.objects.filter(contract=contract).count() == 1
