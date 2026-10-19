"""Jobs & contracts plan: job cards and service bays (JOB-*)."""

from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from contracts.models import Contract
from core.invariants import assert_all_invariants
from core.models import AuditEvent
from inventory.models import StockMovement
from masters.models import Product
from sales.models import SalesInvoice
from sales.services import SalesService
from workshop.models import JobCard, JobCardLine, ServiceBay

from .conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db

URL = "/api/v1/workshop/job-cards/"
BAYS = "/api/v1/workshop/bays/"
_SKU = {"n": 0}


def _on(tenant):
    tenant.company.feature_flags = {"ENABLE_WORKSHOP": True, "ENABLE_CONTRACTS": True}
    tenant.company.save(update_fields=["feature_flags"])


def _part(tenant, stock="20", **extra):
    _SKU["n"] += 1
    product = make_product(
        tenant.company, name=f"Part {_SKU['n']}", sku=f"PT-{_SKU['n']}", product_type=Product.ProductType.GOODS, **extra,
    )
    if stock:
        add_stock(tenant, product, stock)
    return product


def _labour(tenant):
    _SKU["n"] += 1
    return make_product(
        tenant.company, name=f"Labour {_SKU['n']}", sku=f"LB-{_SKU['n']}", product_type=Product.ProductType.SERVICE,
    )


def _job(tenant, customer=None, **extra):
    customer = customer or make_customer(tenant.company)
    resp = tenant.client.post(URL, {"customer": customer.id, "complaint": "Noise", **extra}, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data


def _line(tenant, job_id, product, kind="PART", qty="1", price="100", **extra):
    resp = tenant.client.post(
        f"{URL}{job_id}/lines/",
        {"kind": kind, "product": product.id, "quantity": qty, "unit_price": price, **extra}, format="json",
    )
    assert resp.status_code == 200, resp.data
    return resp.data


def _reserved(tenant, product):
    from django.db.models import Sum

    from inventory.models import StockBalance

    total = StockBalance.objects.filter(company=tenant.company, product=product).aggregate(n=Sum("reserved"))["n"]
    return total or 0


# ---- JOB-02: the invoice draft and the job cannot drift apart -------------------------------------------------------------

def test_reverting_to_editing_rebuilds_the_invoice_so_job_stock_and_invoice_agree(tenant_a):
    _on(tenant_a)
    part_a = _part(tenant_a)
    part_b = _part(tenant_a)
    labour = _labour(tenant_a)
    job = _job(tenant_a)
    _line(tenant_a, job["id"], part_a)
    first = tenant_a.client.post(f"{URL}{job['id']}/convert/")
    assert first.status_code == 200
    first_invoice = first.data["sales_invoice"]
    late = tenant_a.client.post(
        f"{URL}{job['id']}/lines/",
        {"kind": "PART", "product": part_b.id, "quantity": "1", "unit_price": "50"}, format="json",
    )
    assert late.status_code == 400
    reopened = tenant_a.client.post(f"{URL}{job['id']}/reopen/")
    assert reopened.status_code == 200 and reopened.data["sales_invoice"] is None
    assert SalesInvoice.objects.get(pk=first_invoice).status == SalesInvoice.Status.CANCELLED
    _line(tenant_a, job["id"], part_b, price="50")
    _line(tenant_a, job["id"], labour, kind="LABOUR", price="200")
    second = tenant_a.client.post(f"{URL}{job['id']}/convert/")
    assert second.status_code == 200 and second.data["sales_invoice"] != first_invoice
    invoice = SalesInvoice.objects.get(pk=second.data["sales_invoice"])
    assert sorted(invoice.items.values_list("product_id", flat=True)) == sorted(
        JobCardLine.objects.filter(job_id=job["id"]).values_list("product_id", flat=True),
    )
    SalesService.complete(invoice, tenant_a.owner)
    moved = StockMovement.objects.filter(company=tenant_a.company, quantity__lt=0)
    assert {m.product_id for m in moved} == {part_a.id, part_b.id}
    assert JobCard.objects.get(pk=job["id"]).status == JobCard.Status.INVOICED
    assert_all_invariants(tenant_a.company)


def test_a_completed_invoice_cannot_be_reverted_and_a_linked_draft_cannot_be_edited_in_sales(tenant_a):
    _on(tenant_a)
    part = _part(tenant_a)
    job = _job(tenant_a)
    _line(tenant_a, job["id"], part)
    invoice_id = tenant_a.client.post(f"{URL}{job['id']}/convert/").data["sales_invoice"]
    edit = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{invoice_id}/",
        {"items": [{"product": part.id, "quantity": "9", "unit_price": "1", "gst_rate": "18"}]}, format="json",
    )
    assert edit.status_code == 400 and "job card" in str(edit.data).lower()
    SalesService.complete(SalesInvoice.objects.get(pk=invoice_id), tenant_a.owner)
    assert tenant_a.client.post(f"{URL}{job['id']}/reopen/").status_code == 400
    assert tenant_a.client.post(f"{URL}{job['id']}/cancel/").status_code == 400


def test_reopen_is_harmless_when_there_is_no_draft(tenant_a):
    _on(tenant_a)
    job = _job(tenant_a)
    assert tenant_a.client.post(f"{URL}{job['id']}/reopen/").status_code == 400  # a fresh DRAFT job has nothing to revert
    tenant_a.client.post(f"{URL}{job['id']}/start/")
    assert tenant_a.client.post(f"{URL}{job['id']}/reopen/").status_code == 200


# ---- JOB-03: edit and remove lines move the stock hold -------------------------------------------------------------------

def test_changing_or_removing_a_line_moves_its_stock_hold(tenant_a):
    _on(tenant_a)
    part = _part(tenant_a, stock="10")
    job = _job(tenant_a)
    detail = _line(tenant_a, job["id"], part, qty="3")
    line_id = detail["lines"][0]["id"]
    before = _reserved(tenant_a, part)
    assert before == 3
    edit_url = f"{URL}{job['id']}/line/"
    changed = tenant_a.client.patch(edit_url, {"line": line_id, "quantity": "5", "unit_price": "120"}, format="json")
    assert changed.status_code == 200, changed.data
    assert changed.data["lines"][0]["quantity"] == "5.000"
    assert _reserved(tenant_a, part) == before + 2
    too_many = tenant_a.client.patch(edit_url, {"line": line_id, "quantity": "50"}, format="json")
    assert too_many.status_code == 400
    removed = tenant_a.client.delete(f"{edit_url}?line={line_id}")
    assert removed.status_code == 200 and removed.data["lines"] == []
    assert _reserved(tenant_a, part) == 0
    assert JobCardLine.objects.filter(job_id=job["id"]).count() == 0


def test_lines_are_locked_once_the_job_is_closed(tenant_a):
    _on(tenant_a)
    part = _part(tenant_a)
    job = _job(tenant_a)
    line_id = _line(tenant_a, job["id"], part)["lines"][0]["id"]
    tenant_a.client.post(f"{URL}{job['id']}/cancel/")
    assert tenant_a.client.patch(f"{URL}{job['id']}/line/", {"line": line_id, "quantity": "2"}, format="json").status_code == 400
    assert tenant_a.client.delete(f"{URL}{job['id']}/line/?line={line_id}").status_code == 400


# ---- JOB-04: header edits ----------------------------------------------------------------------------------------------------------

def test_the_header_can_be_edited_and_the_customer_only_while_the_job_is_empty(tenant_a):
    _on(tenant_a)
    job = _job(tenant_a)
    other = make_customer(tenant_a.company, name="Other Buyer")
    edited = tenant_a.client.patch(
        f"{URL}{job['id']}/",
        {"registration_no": "KA01AB1234", "vehicle_model": "Alto", "odometer_reading": "1200.5", "customer": other.id},
        format="json",
    )
    assert edited.status_code == 200, edited.data
    assert edited.data["customer"] == other.id and edited.data["registration_no"] == "KA01AB1234"
    _line(tenant_a, job["id"], _part(tenant_a))
    refused = tenant_a.client.patch(f"{URL}{job['id']}/", {"customer": make_customer(tenant_a.company).id}, format="json")
    assert refused.status_code == 400
    assert tenant_a.client.patch(f"{URL}{job['id']}/", {"odometer_reading": "-3"}, format="json").status_code == 400


def test_unknown_references_are_errors_not_silently_dropped(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    bad_bay = tenant_a.client.post(URL, {"customer": customer.id, "service_bay": 99999}, format="json")
    assert bad_bay.status_code == 400 and "service bay" in str(bad_bay.data).lower()
    bad_tech = tenant_a.client.post(URL, {"customer": customer.id, "technician": 99999}, format="json")
    assert bad_tech.status_code == 400
    assert tenant_a.client.post(URL, {"customer": 99999}, format="json").status_code == 400
    assert JobCard.objects.filter(company=tenant_a.company).count() == 0


# ---- JOB-06 / JOB-12: bays and bookings -----------------------------------------------------------------------------------

def test_bays_can_be_created_renamed_switched_off_and_not_deleted_while_booked(tenant_a):
    _on(tenant_a)
    made = tenant_a.client.post(BAYS, {"name": "Bay 1"}, format="json")
    assert made.status_code == 201
    assert tenant_a.client.post(BAYS, {"name": "bay 1"}, format="json").status_code == 400  # same name
    bay_id = made.data["id"]
    assert tenant_a.client.patch(f"{BAYS}{bay_id}/", {"name": "Lift A"}, format="json").status_code == 200
    start = timezone.now() + timedelta(days=1)
    job = _job(
        tenant_a, service_bay=bay_id, scheduled_start=start.isoformat(),
        scheduled_end=(start + timedelta(hours=2)).isoformat(),
    )
    assert tenant_a.client.delete(f"{BAYS}{bay_id}/").status_code == 400
    tenant_a.client.post(f"{URL}{job['id']}/cancel/")
    assert tenant_a.client.patch(f"{BAYS}{bay_id}/", {"is_active": False}, format="json").status_code == 200
    assert tenant_a.client.get(BAYS).data["count"] == 0
    assert tenant_a.client.get(BAYS, {"include_inactive": 1}).data["count"] == 1
    again = tenant_a.client.post(
        f"{URL}{_job(tenant_a)['id']}/schedule/",
        {"service_bay": bay_id, "scheduled_start": start.isoformat(),
         "scheduled_end": (start + timedelta(hours=1)).isoformat()}, format="json",
    )
    assert again.status_code == 400 and "switched off" in str(again.data)
    assert tenant_a.client.delete(f"{BAYS}{bay_id}/").status_code == 204


def test_a_double_booked_bay_and_a_busy_technician_are_refused_with_an_override(tenant_a):
    _on(tenant_a)
    bay = ServiceBay.objects.create(company=tenant_a.company, name="Bay 2")
    other_bay = ServiceBay.objects.create(company=tenant_a.company, name="Bay 3")
    start = timezone.now() + timedelta(days=2)
    window = {
        "scheduled_start": start.isoformat(), "scheduled_end": (start + timedelta(hours=2)).isoformat(),
    }
    from accounts.models import CompanyUser

    technician = CompanyUser.objects.get(user=tenant_a.staff)
    first = _job(tenant_a, service_bay=bay.id, technician=technician.id, **window)
    clash = tenant_a.client.post(URL, {"customer": first["customer"], "service_bay": bay.id, **window}, format="json")
    assert clash.status_code == 400 and "already booked" in str(clash.data)
    busy = tenant_a.client.post(
        URL, {"customer": first["customer"], "service_bay": other_bay.id, "technician": technician.id, **window},
        format="json",
    )
    assert busy.status_code == 409
    assert busy.data["error"]["details"]["code"] == "technician_busy"
    allowed = tenant_a.client.post(
        URL, {"customer": first["customer"], "service_bay": other_bay.id, "technician": technician.id,
              "allow_overlap": True, **window}, format="json",
    )
    assert allowed.status_code == 201, allowed.data
    inverted = tenant_a.client.post(
        URL, {"customer": first["customer"], "service_bay": bay.id, "scheduled_start": window["scheduled_end"],
              "scheduled_end": window["scheduled_start"]}, format="json",
    )
    assert inverted.status_code == 400


# ---- JOB-09: warranty / AMC coverage --------------------------------------------------------------------------------------

def _contract(tenant, customer, days_left=100, number="CON-W1"):
    return Contract.objects.create(
        company=tenant.company, customer=customer, contract_type="WARRANTY", number=number,
        start_date=timezone.localdate() - timedelta(days=100),
        end_date=timezone.localdate() + timedelta(days=days_left),
    )


def test_a_covered_line_is_free_and_needs_a_live_contract_of_the_same_customer(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    stranger = make_customer(tenant_a.company, name="Stranger")
    contract = _contract(tenant_a, customer)
    part = _part(tenant_a)
    job = _job(tenant_a, customer, contract=contract.id)
    assert job["contract_number"] == "CON-W1"
    covered = _line(tenant_a, job["id"], part, price="900", covered_by_contract=True)
    assert covered["lines"][0]["unit_price"] == "0.00" and covered["lines"][0]["covered_by_contract"] is True
    assert covered["total"] == "0.00"
    other = make_customer(tenant_a.company, name="Other")
    refused = tenant_a.client.post(URL, {"customer": other.id, "contract": contract.id}, format="json")
    assert refused.status_code == 400
    plain = _job(tenant_a, stranger)
    no_contract = tenant_a.client.post(
        f"{URL}{plain['id']}/lines/",
        {"kind": "PART", "product": part.id, "quantity": "1", "unit_price": "10", "covered_by_contract": True},
        format="json",
    )
    assert no_contract.status_code == 400
    expired = _contract(tenant_a, make_customer(tenant_a.company, name="Late"), days_left=-5, number="CON-W2")
    late = tenant_a.client.post(URL, {"customer": expired.customer_id, "contract": expired.id}, format="json")
    assert late.status_code == 400


def test_a_covered_line_prevents_taking_the_contract_off_the_job(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    contract = _contract(tenant_a, customer)
    job = _job(tenant_a, customer, contract=contract.id)
    _line(tenant_a, job["id"], _part(tenant_a), covered_by_contract=True)
    assert tenant_a.client.patch(f"{URL}{job['id']}/", {"contract": None}, format="json").status_code == 400


# ---- JOB-10 / JOB-13 ------------------------------------------------------------------------------------------------------------------

def test_a_job_can_name_its_ticket_and_complaint_and_a_warehouse(tenant_a):
    from complaints.models import Complaint
    from inventory.services import InventoryService
    from support.models import Ticket

    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    other = make_customer(tenant_a.company, name="Other")
    ticket = Ticket.objects.create(company=tenant_a.company, customer=customer, subject="Noise", number="T-9")
    foreign = Ticket.objects.create(company=tenant_a.company, customer=other, subject="Else", number="T-10")
    complaint = Complaint.objects.create(
        company=tenant_a.company, customer=customer, category="DAMAGED", description="Broken", number="RMA-9",
    )
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    job = _job(tenant_a, customer, ticket=ticket.id, source_complaint=complaint.id, warehouse=warehouse.id)
    assert job["ticket_number"] == "T-9" and job["complaint_number"] == "RMA-9" and job["warehouse"] == warehouse.id
    bad = tenant_a.client.post(URL, {"customer": customer.id, "ticket": foreign.id}, format="json")
    assert bad.status_code == 400
    links = tenant_a.client.get("/api/v1/links/", {"entity": "job_card", "id": job["id"]}).data
    assert {row["kind"] for row in links} == {"ticket", "complaint"}


# ---- list, search, audit, totals --------------------------------------------------------------------------------------------------

def test_the_list_is_flat_in_queries_and_carries_names_and_totals(tenant_a):
    _on(tenant_a)
    part = _part(tenant_a, stock="500")
    customer = make_customer(tenant_a.company, name="Acme Workshop")
    for _ in range(6):
        job = _job(tenant_a, customer, registration_no="KA05XY0001")
        _line(tenant_a, job["id"], part, qty="2", price="100")
    with CaptureQueriesContext(connection) as small:
        resp = tenant_a.client.get(URL)
    assert resp.status_code == 200
    row = resp.data["results"][0]
    assert "lines" not in row and "serial_history" not in row
    assert row["line_count"] == 1 and row["customer_name"] == "Acme Workshop"
    assert row["total"] == "236.00" and row["gst_total"] == "36.00" and row["subtotal"] == "200.00"
    for _ in range(6):
        _line(tenant_a, _job(tenant_a, customer)["id"], part)
    with CaptureQueriesContext(connection) as large:
        tenant_a.client.get(URL)
    assert len(large) <= len(small) + 2


def test_search_filters_and_the_audit_trail(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company, name="Zed Garage")
    job = _job(tenant_a, customer, registration_no="MH12AB9999", vehicle_model="Swift")
    _job(tenant_a)
    assert tenant_a.client.get(URL, {"q": "mh12ab"}).data["count"] == 1
    assert tenant_a.client.get(URL, {"q": "zed"}).data["count"] == 1
    assert tenant_a.client.get(URL, {"q": job["number"]}).data["count"] == 1
    assert tenant_a.client.get(URL, {"status": "DRAFT"}).data["count"] == 2
    tenant_a.client.post(f"{URL}{job['id']}/start/")
    _line(tenant_a, job["id"], _part(tenant_a))
    tenant_a.client.post(f"{URL}{job['id']}/cancel/")
    actions = set(
        AuditEvent.objects.filter(company=tenant_a.company, entity_type="JobCard", entity_id=str(job["id"]))
        .values_list("action", flat=True)
    )
    assert {"job_created", "job_started", "job_line_added", "job_cancelled"} <= actions
    shown = tenant_a.client.get(f"{URL}{job['id']}/activity/").data
    assert [row["action"] for row in shown][0] == "job_cancelled"
    report = tenant_a.client.get(f"{URL}report/").data
    assert {row["status"] for row in report["by_status"]} == {"DRAFT", "CANCELLED"}


def test_a_viewer_reads_jobs_but_cannot_change_them_and_other_companies_see_nothing(tenant_a, tenant_b):
    from accounts.models import CompanyUser, User
    from rest_framework.test import APIClient

    _on(tenant_a)
    _on(tenant_b)
    job = _job(tenant_a)
    viewer = User.objects.create_user(email="viewer@alpha.test", password="StrongPass123!", full_name="Viewer")
    CompanyUser.objects.create(company=tenant_a.company, user=viewer, role=CompanyUser.Role.VIEWER)
    client = APIClient()
    client.force_authenticate(user=viewer)
    assert client.get(f"{URL}{job['id']}/").status_code == 200
    assert client.post(f"{URL}{job['id']}/start/").status_code == 403
    assert tenant_b.client.get(f"{URL}{job['id']}/").status_code == 404
    assert tenant_b.client.get(URL, {"q": "noise"}).data["count"] == 0


def test_stock_options_list_available_serials_and_batches_for_service_staff(tenant_a):
    from inventory.models import BatchLot, SerialNumber

    _on(tenant_a)
    part = _part(tenant_a, stock="", track_serial=True)
    SerialNumber.objects.create(company=tenant_a.company, product=part, serial_number="SN-1", status="AVAILABLE")
    SerialNumber.objects.create(company=tenant_a.company, product=part, serial_number="SN-2", status="SOLD")
    other = _part(tenant_a, stock="", track_batch=True)
    lot = BatchLot.objects.create(company=tenant_a.company, product=other, batch_no="B-1")
    from decimal import Decimal

    from inventory.models import MovementType
    from inventory.services import InventoryService

    InventoryService.post_movement(
        company=tenant_a.company, product=other, movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("4"), unit_cost=Decimal("80"), user=tenant_a.owner, batch=lot,
    )
    url = f"{URL}stock-options/"
    serial_view = tenant_a.staff_client.get(url, {"product": part.id}).data
    assert [row["serial_number"] for row in serial_view["serials"]] == ["SN-1"] and serial_view["track_serial"] is True
    batch_view = tenant_a.staff_client.get(url, {"product": other.id}).data
    assert batch_view["batches"][0]["batch_no"] == "B-1" and batch_view["batches"][0]["available"] == "4.000"
    assert tenant_a.staff_client.get(url).status_code == 400
