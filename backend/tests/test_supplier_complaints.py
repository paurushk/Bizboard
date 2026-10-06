"""Supplier complaints mirror customer complaints onto a purchase bill and a debit note."""

from decimal import Decimal

import pytest

from payments.models import CustomerReceipt, SupplierPayment
from purchases.models import PurchaseDebitNote, PurchaseInvoice

from .conftest import make_product, make_supplier


def _flags(company):
    company.feature_flags = {"ENABLE_COMPLAINTS": True}
    company.save(update_fields=["feature_flags"])


@pytest.mark.django_db
def test_supplier_complaint_debit_note_is_a_draft_and_staff_cannot_open_it(tenant_a, tenant_b):
    _flags(tenant_a.company)
    _flags(tenant_b.company)
    supplier = make_supplier(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/complaints/supplier/",
        {"supplier": supplier.id, "category": "DAMAGED", "description": "Short delivery"},
        format="json",
    )
    assert created.status_code == 201, created.data
    complaint_id = created.data["id"]
    assert created.data["number"].startswith("SCN-")

    assert tenant_a.staff_client.post(
        "/api/v1/complaints/supplier/",
        {"supplier": supplier.id, "category": "OTHER", "description": "no"},
        format="json",
    ).status_code == 403
    assert tenant_b.client.get(f"/api/v1/complaints/supplier/{complaint_id}/").status_code == 404

    illegal = tenant_a.client.post(
        f"/api/v1/complaints/supplier/{complaint_id}/transition/",
        {"status": "RESOLVED"},
        format="json",
    )
    assert illegal.status_code == 400
    tenant_a.client.post(
        f"/api/v1/complaints/supplier/{complaint_id}/transition/",
        {"status": "INSPECTING"},
        format="json",
    )
    missing = tenant_a.client.post(
        f"/api/v1/complaints/supplier/{complaint_id}/create-debit-note/",
        {"items": []},
        format="json",
    )
    assert missing.status_code == 400

    other = make_supplier(tenant_a.company, name="Other Mill")
    wrong_bill = PurchaseInvoice.objects.create(company=tenant_a.company, supplier=other)
    mismatch = tenant_a.client.patch(
        f"/api/v1/complaints/supplier/{complaint_id}/",
        {"source_invoice": wrong_bill.id},
        format="json",
    )
    assert mismatch.status_code == 400

    bill = PurchaseInvoice.objects.create(company=tenant_a.company, supplier=supplier)
    linked = tenant_a.client.patch(
        f"/api/v1/complaints/supplier/{complaint_id}/",
        {"source_invoice": bill.id},
        format="json",
    )
    assert linked.status_code == 200
    product = make_product(tenant_a.company, sku="SCN-1")
    receipts_before = CustomerReceipt.objects.count()
    payments_before = SupplierPayment.objects.count()
    tenant_a.client.post(
        f"/api/v1/complaints/supplier/{complaint_id}/transition/",
        {"status": "APPROVED"},
        format="json",
    )
    made = tenant_a.client.post(
        f"/api/v1/complaints/supplier/{complaint_id}/create-debit-note/",
        {"items": [{"product": product.id, "quantity": "1", "unit_price": "10"}]},
        format="json",
    )
    assert made.status_code == 201, made.data
    note = PurchaseDebitNote.objects.get(pk=made.data["id"])
    assert note.status == PurchaseDebitNote.Status.DRAFT
    assert note.supplier_id == supplier.id
    assert note.purchase_invoice_id == bill.id
    assert CustomerReceipt.objects.count() == receipts_before
    assert SupplierPayment.objects.count() == payments_before
    again = tenant_a.client.post(
        f"/api/v1/complaints/supplier/{complaint_id}/create-debit-note/",
        {"items": [{"product": product.id, "quantity": "1", "unit_price": "10"}]},
        format="json",
    )
    assert again.status_code == 200
    assert again.data["id"] == made.data["id"]
    assert PurchaseDebitNote.objects.filter(company=tenant_a.company).count() == 1

    blocked = tenant_a.client.post(
        f"/api/v1/complaints/supplier/{complaint_id}/transition/",
        {"status": "RESOLVED"},
        format="json",
    )
    assert blocked.status_code == 400
    note.status = PurchaseDebitNote.Status.COMPLETED
    note.save(update_fields=["status"])
    resolved = tenant_a.client.post(
        f"/api/v1/complaints/supplier/{complaint_id}/transition/",
        {"status": "RESOLVED"},
        format="json",
    )
    assert resolved.status_code == 200
    report = tenant_a.client.get("/api/v1/complaints/supplier/report/")
    assert report.data["resolved_with_document"] == 1
    assert Decimal(note.items.first().quantity) == Decimal("1")


@pytest.mark.django_db
def test_supplier_complaints_stay_hidden_when_the_flag_is_off(tenant_a):
    supplier = make_supplier(tenant_a.company)
    hidden = tenant_a.client.post(
        "/api/v1/complaints/supplier/",
        {"supplier": supplier.id, "category": "QUALITY", "description": "off"},
        format="json",
    )
    assert hidden.status_code == 404


@pytest.mark.django_db
def test_rejected_supplier_complaint_stays_closed_and_a_bare_resolve_is_separate(tenant_a, tenant_b):
    _flags(tenant_a.company)
    _flags(tenant_b.company)
    supplier = make_supplier(tenant_a.company)
    created = tenant_a.client.post(
        "/api/v1/complaints/supplier/",
        {"supplier": supplier.id, "category": "WRONG_DELIVERY", "description": "Wrong grade"},
        format="json",
    )
    assert created.status_code == 201, created.data
    complaint_id = created.data["id"]
    assert tenant_a.staff_client.post(
        f"/api/v1/complaints/supplier/{complaint_id}/transition/",
        {"status": "INSPECTING"},
        format="json",
    ).status_code == 403

    skipped = tenant_a.client.post(
        f"/api/v1/complaints/supplier/{complaint_id}/transition/",
        {"status": "APPROVED"},
        format="json",
    )
    assert skipped.status_code == 400
    bill = PurchaseInvoice.objects.create(company=tenant_a.company, supplier=supplier)
    tenant_a.client.patch(
        f"/api/v1/complaints/supplier/{complaint_id}/",
        {"source_invoice": bill.id},
        format="json",
    )
    too_early = tenant_a.client.post(
        f"/api/v1/complaints/supplier/{complaint_id}/create-debit-note/",
        {"items": [{"product": make_product(tenant_a.company, sku="SCN-2").id, "quantity": "1", "unit_price": "5"}]},
        format="json",
    )
    assert too_early.status_code == 400
    assert PurchaseDebitNote.objects.filter(company=tenant_a.company).count() == 0

    tenant_a.client.post(
        f"/api/v1/complaints/supplier/{complaint_id}/transition/",
        {"status": "INSPECTING"},
        format="json",
    )
    rejected = tenant_a.client.post(
        f"/api/v1/complaints/supplier/{complaint_id}/transition/",
        {"status": "REJECTED", "inspection_notes": "Not our shipment"},
        format="json",
    )
    assert rejected.status_code == 200
    assert rejected.data["status"] == "REJECTED"
    reopened = tenant_a.client.post(
        f"/api/v1/complaints/supplier/{complaint_id}/transition/",
        {"status": "INSPECTING"},
        format="json",
    )
    assert reopened.status_code == 400
    listed = tenant_a.client.get("/api/v1/complaints/supplier/?status=REJECTED")
    assert listed.status_code == 200
    rows = listed.data.get("results", listed.data)
    assert [row["id"] for row in rows] == [complaint_id]

    bare = tenant_a.client.post(
        "/api/v1/complaints/supplier/",
        {"supplier": supplier.id, "category": "QUALITY", "description": "No note"},
        format="json",
    )
    bare_id = bare.data["id"]
    for status_name in ("INSPECTING", "APPROVED", "RESOLVED"):
        moved = tenant_a.client.post(
            f"/api/v1/complaints/supplier/{bare_id}/transition/",
            {"status": status_name},
            format="json",
        )
        assert moved.status_code == 200, moved.data
    report = tenant_a.client.get("/api/v1/complaints/supplier/report/")
    assert report.data["resolved"] == 1
    assert report.data["resolved_with_document"] == 0
    assert report.data["resolved_without_document"] == 1
    other = tenant_b.client.get("/api/v1/complaints/supplier/report/")
    assert other.status_code == 200
    assert other.data["resolved"] == 0
