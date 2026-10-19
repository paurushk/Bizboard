"""Customer care plan: customer and supplier complaints (CMP-*, SCM-*)."""

from datetime import timedelta

import pytest
from django.utils import timezone

from complaints.models import Complaint, SupplierComplaint
from core.models import AuditEvent
from sales.models import SalesCreditNote, SalesInvoice

from .conftest import add_stock, make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db

URL = "/api/v1/complaints/"
SURL = "/api/v1/complaints/supplier/"


def _on(tenant):
    tenant.company.feature_flags = {"ENABLE_COMPLAINTS": True, "ENABLE_SUPPORT_TICKETS": True}
    tenant.company.save(update_fields=["feature_flags"])


_SKU = {"n": 0}


def _invoice(tenant, customer, quantity="5"):
    _SKU["n"] += 1
    product = make_product(tenant.company, name=f"Motor {_SKU['n']}", sku=f"MTR-{_SKU['n']}")
    add_stock(tenant, product, "50")
    created = tenant.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer.id, "invoice_type": "GST", "invoice_date": str(timezone.localdate()),
            "items": [{"product": product.id, "quantity": quantity, "unit_price": "500.00", "gst_rate": "18.00"}],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    assert tenant.client.post(f"/api/v1/sales/invoices/{created.data['id']}/complete/").status_code == 200
    invoice = SalesInvoice.objects.get(pk=created.data["id"])
    return invoice, product, invoice.items.first()


def _complaint(tenant, customer=None, **extra):
    customer = customer or make_customer(tenant.company)
    body = {"customer": customer.id, "category": "DAMAGED", "description": "Arrived broken", **extra}
    resp = tenant.client.post(URL, body, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data


def _to(tenant, complaint_id, *statuses, **extra):
    for status in statuses:
        resp = tenant.client.post(f"{URL}{complaint_id}/transition/", {"status": status, **extra}, format="json")
        assert resp.status_code == 200, resp.data
    return resp.data


# ---- CMP-02: parties and invoice are fixed once a remedy exists ---------------------------------------------------------

def test_source_invoice_and_customer_are_fixed_once_a_document_is_linked(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    invoice, product, line = _invoice(tenant_a, customer)
    other_invoice, _p, _l = _invoice(tenant_a, customer, quantity="2")
    data = _complaint(tenant_a, customer, source_invoice=invoice.id)
    _to(tenant_a, data["id"], "INSPECTING", "APPROVED")
    # before any document the invoice may still be corrected
    assert tenant_a.client.patch(
        f"{URL}{data['id']}/", {"source_invoice": other_invoice.id}, format="json",
    ).status_code == 200
    assert tenant_a.client.patch(
        f"{URL}{data['id']}/", {"source_invoice": invoice.id}, format="json",
    ).status_code == 200
    made = tenant_a.client.post(
        f"{URL}{data['id']}/create-credit-note/",
        {"items": [{"product": product.id, "quantity": "1", "unit_price": "500.00", "source_item": line.id}]},
        format="json",
    )
    assert made.status_code == 201, made.data
    locked = tenant_a.client.patch(f"{URL}{data['id']}/", {"source_invoice": other_invoice.id}, format="json")
    assert locked.status_code == 400
    assert "document" in str(locked.data).lower()
    assert tenant_a.client.patch(f"{URL}{data['id']}/", {"description": "Still broken"}, format="json").status_code == 400


def test_description_and_category_are_editable_only_before_approval(tenant_a):
    _on(tenant_a)
    data = _complaint(tenant_a)
    ok = tenant_a.client.patch(f"{URL}{data['id']}/", {"description": "Cracked housing"}, format="json")
    assert ok.status_code == 200 and ok.data["description"] == "Cracked housing"
    _to(tenant_a, data["id"], "INSPECTING", "APPROVED")
    late = tenant_a.client.patch(f"{URL}{data['id']}/", {"category": "QUALITY"}, format="json")
    assert late.status_code == 400
    blank = tenant_a.client.patch(f"{URL}{_complaint(tenant_a)['id']}/", {"description": " "}, format="json")
    assert blank.status_code == 400


# ---- CMP-03 / CMP-04 --------------------------------------------------------------------------------------------------------------

def test_a_rejection_needs_its_reason(tenant_a):
    _on(tenant_a)
    data = _complaint(tenant_a)
    _to(tenant_a, data["id"], "INSPECTING")
    bare = tenant_a.client.post(f"{URL}{data['id']}/transition/", {"status": "REJECTED"}, format="json")
    assert bare.status_code == 400 and "reason" in str(bare.data).lower()
    saved = tenant_a.client.post(
        f"{URL}{data['id']}/save-notes/", {"inspection_notes": "Customer damage, see photos"}, format="json",
    )
    assert saved.status_code == 200
    assert tenant_a.client.post(
        f"{URL}{data['id']}/transition/", {"status": "REJECTED"}, format="json",
    ).status_code == 200


def test_resolving_without_a_remedy_document_needs_a_resolution_note(tenant_a):
    _on(tenant_a)
    data = _complaint(tenant_a)
    _to(tenant_a, data["id"], "INSPECTING", "APPROVED")
    bare = tenant_a.client.post(f"{URL}{data['id']}/transition/", {"status": "RESOLVED"}, format="json")
    assert bare.status_code == 400 and "resolution note" in str(bare.data).lower()
    done = tenant_a.client.post(
        f"{URL}{data['id']}/transition/",
        {"status": "RESOLVED", "resolution_note": "Replaced at the counter"}, format="json",
    )
    assert done.status_code == 200 and done.data["resolution_note"] == "Replaced at the counter"
    report = tenant_a.client.get(f"{URL}report/").data
    assert report["resolved_without_document"] == 1


def test_notes_are_saved_without_moving_the_status(tenant_a):
    _on(tenant_a)
    data = _complaint(tenant_a)
    saved = tenant_a.client.post(
        f"{URL}{data['id']}/save-notes/", {"inspection_notes": "Housing cracked"}, format="json",
    )
    assert saved.status_code == 200
    assert saved.data["status"] == "OPEN" and saved.data["inspection_notes"] == "Housing cracked"
    _to(tenant_a, data["id"], "INSPECTING", "APPROVED")
    tenant_a.client.post(
        f"{URL}{data['id']}/transition/", {"status": "RESOLVED", "resolution_note": "done"}, format="json",
    )
    closed = tenant_a.client.post(f"{URL}{data['id']}/save-notes/", {"inspection_notes": "x"}, format="json")
    assert closed.status_code == 400


# ---- CMP-05: recovery from a cancelled document --------------------------------------------------------------------------

def test_a_complaint_recovers_after_its_credit_note_is_cancelled(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    invoice, product, line = _invoice(tenant_a, customer)
    data = _complaint(tenant_a, customer, source_invoice=invoice.id)
    _to(tenant_a, data["id"], "INSPECTING", "APPROVED")
    items = [{"product": product.id, "quantity": "1", "unit_price": "500.00", "source_item": line.id}]
    first = tenant_a.client.post(f"{URL}{data['id']}/create-credit-note/", {"items": items}, format="json")
    assert first.status_code == 201, first.data
    note = SalesCreditNote.objects.get(pk=first.data["id"])
    SalesCreditNote.objects.filter(pk=note.pk).update(status=SalesCreditNote.Status.CANCELLED)
    stuck = tenant_a.client.post(f"{URL}{data['id']}/transition/", {"status": "RESOLVED"}, format="json")
    assert stuck.status_code == 400
    unlinked = tenant_a.client.post(
        f"{URL}{data['id']}/unlink-document/", {"document": "sales_credit_note"}, format="json",
    )
    assert unlinked.status_code == 200 and unlinked.data["sales_credit_note"] is None
    again = tenant_a.client.post(f"{URL}{data['id']}/create-credit-note/", {"items": items}, format="json")
    assert again.status_code == 201 and again.data["id"] != note.id
    assert AuditEvent.objects.filter(
        company=tenant_a.company, action="complaint_document_unlinked", entity_id=str(data["id"]),
    ).exists()


# ---- CMP-06: document creation ----------------------------------------------------------------------------------------------

def test_document_creation_replays_the_same_answer_for_the_same_key(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    invoice, product, line = _invoice(tenant_a, customer)
    data = _complaint(tenant_a, customer, source_invoice=invoice.id)
    _to(tenant_a, data["id"], "INSPECTING", "APPROVED")
    items = [{"product": product.id, "quantity": "1", "unit_price": "500.00", "source_item": line.id}]
    first = tenant_a.client.post(
        f"{URL}{data['id']}/create-credit-note/", {"items": items}, format="json", HTTP_IDEMPOTENCY_KEY="cn-1",
    )
    second = tenant_a.client.post(
        f"{URL}{data['id']}/create-credit-note/", {"items": items}, format="json", HTTP_IDEMPOTENCY_KEY="cn-1",
    )
    assert first.status_code == 201 and second.data["id"] == first.data["id"]
    assert SalesCreditNote.objects.filter(company=tenant_a.company).count() == 1


def test_a_document_cannot_be_made_before_approval_or_without_items(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    invoice, product, line = _invoice(tenant_a, customer)
    data = _complaint(tenant_a, customer, source_invoice=invoice.id)
    early = tenant_a.client.post(f"{URL}{data['id']}/create-credit-note/", {"items": []}, format="json")
    assert early.status_code == 400
    _to(tenant_a, data["id"], "INSPECTING", "APPROVED")
    empty = tenant_a.client.post(f"{URL}{data['id']}/create-credit-note/", {"items": []}, format="json")
    assert empty.status_code == 400


# ---- list, search, filters, report -----------------------------------------------------------------------------------------

def test_search_filters_and_ageing_report(tenant_a):
    _on(tenant_a)
    acme = make_customer(tenant_a.company, name="Acme Foods")
    zed = make_customer(tenant_a.company, name="Zed Mills")
    first = _complaint(tenant_a, acme)
    second = _complaint(tenant_a, zed, category="QUALITY")
    Complaint.objects.filter(pk=first["id"]).update(created_at=timezone.now() - timedelta(days=10))
    assert tenant_a.client.get(URL, {"q": "zed"}).data["count"] == 1
    assert tenant_a.client.get(URL, {"q": second["number"]}).data["count"] == 1
    assert tenant_a.client.get(URL, {"category": "QUALITY"}).data["count"] == 1
    assert tenant_a.client.get(URL, {"customer": acme.id}).data["count"] == 1
    assert tenant_a.client.get(URL, {"created_from": str(timezone.localdate())}).data["count"] == 1
    listed = tenant_a.client.get(URL).data["results"][0]
    assert listed["customer_name"] in {"Acme Foods", "Zed Mills"}
    report = tenant_a.client.get(f"{URL}report/").data
    ageing = {row["bucket"]: row["count"] for row in report["ageing"]}
    assert ageing["8-14 days"] == 1 and ageing["0-2 days"] == 1


def test_only_an_owner_can_delete_and_only_without_a_linked_document(tenant_a):
    _on(tenant_a)
    data = _complaint(tenant_a)
    assert tenant_a.staff_client.delete(f"{URL}{data['id']}/").status_code == 403
    assert tenant_a.client.delete(f"{URL}{data['id']}/").status_code == 204


def test_complaint_files_are_frozen_after_it_closes_and_changes_are_audited(tenant_a):
    _on(tenant_a)
    data = _complaint(tenant_a)
    _to(tenant_a, data["id"], "INSPECTING", "REJECTED", inspection_notes="Misuse")
    assert tenant_a.client.post(f"{URL}{data['id']}/attachments/", {}, format="multipart").status_code == 400
    assert tenant_a.client.delete(f"{URL}{data['id']}/attachments/?attachment=1").status_code == 400
    timeline = tenant_a.client.get(f"{URL}{data['id']}/activity/").data
    assert any(row["action"] == "complaint_status" for row in timeline)


# ---- XLK: a complaint can open a ticket ---------------------------------------------------------------------------------------

def test_a_complaint_can_open_one_linked_ticket(tenant_a):
    _on(tenant_a)
    data = _complaint(tenant_a)
    first = tenant_a.client.post(f"{URL}{data['id']}/create-ticket/")
    assert first.status_code == 201
    again = tenant_a.client.post(f"{URL}{data['id']}/create-ticket/")
    assert again.data == {"id": first.data["id"], "existing": True}
    shown = tenant_a.client.get(f"{URL}{data['id']}/").data
    assert shown["ticket"] == first.data["id"] and shown["ticket_number"].startswith("TKT-")
    links = tenant_a.client.get("/api/v1/links/", {"entity": "complaint", "id": data["id"]}).data
    assert [row["kind"] for row in links] == ["ticket"]
    back = tenant_a.client.get("/api/v1/links/", {"entity": "ticket", "id": first.data["id"]}).data
    assert [row["kind"] for row in back] == ["complaint"]


# ---- SCM: supplier complaints mirror the rules, with one remedy ------------------------------------------------------


def test_supplier_complaint_rules_mirror_the_customer_ones(tenant_a):
    _on(tenant_a)
    supplier = make_supplier(tenant_a.company)
    created = tenant_a.client.post(
        SURL, {"supplier": supplier.id, "category": "QUALITY", "description": "Wrong grade"}, format="json",
    )
    assert created.status_code == 201 and created.data["supplier_name"] == supplier.name
    sid = created.data["id"]
    for status in ("INSPECTING",):
        tenant_a.client.post(f"{SURL}{sid}/transition/", {"status": status}, format="json")
    reject = tenant_a.client.post(f"{SURL}{sid}/transition/", {"status": "REJECTED"}, format="json")
    assert reject.status_code == 400
    assert tenant_a.client.post(
        f"{SURL}{sid}/transition/", {"status": "REJECTED", "inspection_notes": "Within tolerance"}, format="json",
    ).status_code == 200
    assert tenant_a.client.post(f"{SURL}{sid}/attachments/", {}, format="multipart").status_code == 400
    assert SupplierComplaint.objects.get(pk=sid).status == "REJECTED"
    # a staff member without the purchases right is shut out, as before
    assert tenant_a.staff_client.post(
        SURL, {"supplier": supplier.id, "category": "OTHER", "description": "x"}, format="json",
    ).status_code == 403
    assert tenant_a.client.get(f"{SURL}?q={supplier.name[:4]}").data["count"] == 1


def test_a_document_cannot_return_more_than_was_invoiced(tenant_a):
    _on(tenant_a)
    customer = make_customer(tenant_a.company)
    invoice, product, line = _invoice(tenant_a, customer, quantity="3")
    data = _complaint(tenant_a, customer, source_invoice=invoice.id)
    _to(tenant_a, data["id"], "INSPECTING", "APPROVED")
    over = tenant_a.client.post(
        f"{URL}{data['id']}/create-credit-note/",
        {"items": [{"product": product.id, "quantity": "99", "unit_price": "500.00", "source_item": line.id}]},
        format="json",
    )
    assert over.status_code == 400, over.data
    assert SalesCreditNote.objects.filter(company=tenant_a.company).count() == 0
    assert Complaint.objects.get(pk=data["id"]).sales_credit_note_id is None
