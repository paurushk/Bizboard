"""Document status machines (§4) and completed-immutability (§5)."""

from decimal import Decimal

import pytest

from inventory.models import MovementType, StockMovement
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def _completed_invoice(tenant, product=None, customer=None, qty="2"):
    product = product or make_product(tenant.company)
    add_stock(tenant, product, "10")
    customer = customer or make_customer(tenant.company)
    inv = create_draft_invoice(tenant, customer, [
        {"product": product.id, "quantity": qty, "unit_price": "100"}
    ])
    resp = tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 200, resp.data
    return resp.data, product, customer


def test_complete_assigns_number_and_status(tenant_a):
    data, _, _ = _completed_invoice(tenant_a)
    assert data["status"] == "COMPLETED"
    assert data["number"].startswith("INV-")


def test_cannot_complete_twice(tenant_a):
    data, _, _ = _completed_invoice(tenant_a)
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{data['id']}/complete/")
    assert resp.status_code == 400


def test_completed_invoice_audited_edit_allows_line_change(tenant_a):
    """H9-A: Owner may amend unit_price with confirm_amend; stock unchanged."""
    data, product, _ = _completed_invoice(tenant_a, qty="2")
    from inventory.models import StockBalance

    before_stock = StockBalance.objects.get(product=product).on_hand
    resp = tenant_a.client.patch(f"/api/v1/sales/invoices/{data['id']}/", {
        "confirm_amend": True,
        "notes": "audited amend",
        "items": [{"product": product.id, "quantity": "2", "unit_price": "90"}],
    }, format="json")
    assert resp.status_code == 200, resp.data
    assert Decimal(resp.data["items"][0]["quantity"]) == Decimal("2")
    assert Decimal(resp.data["items"][0]["unit_price"]) == Decimal("90.00")
    assert resp.data["notes"] == "audited amend"
    assert StockBalance.objects.get(product=product).on_hand == before_stock
    assert not StockMovement.objects.filter(
        movement_type=MovementType.ADJUSTMENT,
        reference_type="sales_invoice_edit",
    ).exists()

    from core.models import AuditEvent

    diff_event = AuditEvent.objects.filter(
        entity_type="SalesInvoice", entity_id=str(data["id"]),
        description="Completed document edited",
    ).latest("created_at")
    assert Decimal(diff_event.metadata["before"]["grand_total"]) == Decimal("236.00")
    assert Decimal(diff_event.metadata["after"]["grand_total"]) == Decimal("212.00")
    assert diff_event.metadata.get("amend") is True


def test_completed_invoice_amend_requires_owner_confirm(tenant_a):
    from accounts.models import CompanyUser

    data, product, _ = _completed_invoice(tenant_a, qty="2")
    # Without confirm_amend
    resp = tenant_a.client.patch(f"/api/v1/sales/invoices/{data['id']}/", {
        "items": [{"product": product.id, "quantity": "2", "unit_price": "90"}],
    }, format="json")
    assert resp.status_code == 400
    # Staff with create-sales capability (Wave 12B RBAC gate) but not Owner: still blocked.
    membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    membership.can_create_sales = True
    membership.save(update_fields=["can_create_sales"])
    resp = tenant_a.staff_client.patch(f"/api/v1/sales/invoices/{data['id']}/", {
        "confirm_amend": True,
        "items": [{"product": product.id, "quantity": "2", "unit_price": "90"}],
    }, format="json")
    assert resp.status_code == 400


def test_completed_invoice_amend_rejects_quantity_change(tenant_a):
    data, product, _ = _completed_invoice(tenant_a, qty="2")
    resp = tenant_a.client.patch(f"/api/v1/sales/invoices/{data['id']}/", {
        "confirm_amend": True,
        "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
    }, format="json")
    assert resp.status_code == 400


def test_completed_invoice_notes_only_skips_amend_confirm(tenant_a):
    """Header-only notes change must not require confirm_amend or requeue PDF."""
    data, product, _ = _completed_invoice(tenant_a, qty="2")
    from sales.models import SalesInvoice

    inv = SalesInvoice.objects.get(pk=data["id"])
    prior_pdf = inv.pdf_status
    resp = tenant_a.client.patch(f"/api/v1/sales/invoices/{data['id']}/", {
        "notes": "header only",
        "items": [{"product": product.id, "quantity": "2", "unit_price": "100"}],
    }, format="json")
    assert resp.status_code == 200, resp.data
    assert resp.data["notes"] == "header only"
    inv.refresh_from_db()
    assert inv.pdf_status == prior_pdf


def test_completed_invoice_amend_allows_reordered_lines(tenant_a):
    p1 = make_product(tenant_a.company, sku="H9-A")
    p2 = make_product(tenant_a.company, sku="H9-B")
    add_stock(tenant_a, p1, "10")
    add_stock(tenant_a, p2, "10")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": p1.id, "quantity": "1", "unit_price": "100"},
        {"product": p2.id, "quantity": "1", "unit_price": "50"},
    ])
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    detail = tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/").data
    items = detail["items"]
    # Reverse order — matcher must use id/product, not list position.
    resp = tenant_a.client.patch(f"/api/v1/sales/invoices/{inv['id']}/", {
        "confirm_amend": True,
        "items": [
            {"id": items[1]["id"], "product": p2.id, "quantity": "1", "unit_price": "55"},
            {"id": items[0]["id"], "product": p1.id, "quantity": "1", "unit_price": "110"},
        ],
    }, format="json")
    assert resp.status_code == 200, resp.data


def test_completed_purchase_h9a_amend(tenant_a):
    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(tenant_a, supplier, [
        {"product": product.id, "quantity": "5", "unit_price": "80"},
    ])
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    resp = tenant_a.client.patch(f"/api/v1/purchases/invoices/{pur['id']}/", {
        "confirm_amend": True,
        "items": [{"product": product.id, "quantity": "5", "unit_price": "75"}],
    }, format="json")
    assert resp.status_code == 200, resp.data
    assert Decimal(resp.data["items"][0]["unit_price"]) == Decimal("75.00")
    # Staff with create-purchases capability (Wave 12B RBAC gate) but not Owner: still blocked.
    from accounts.models import CompanyUser

    membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    membership.can_create_purchases = True
    membership.save(update_fields=["can_create_purchases"])
    resp = tenant_a.staff_client.patch(f"/api/v1/purchases/invoices/{pur['id']}/", {
        "confirm_amend": True,
        "items": [{"product": product.id, "quantity": "5", "unit_price": "70"}],
    }, format="json")
    assert resp.status_code == 400
    # Qty change rejected
    resp = tenant_a.client.patch(f"/api/v1/purchases/invoices/{pur['id']}/", {
        "confirm_amend": True,
        "items": [{"product": product.id, "quantity": "4", "unit_price": "75"}],
    }, format="json")
    assert resp.status_code == 400


def test_completed_invoice_cannot_change_customer(tenant_a):
    data, product, customer = _completed_invoice(tenant_a)
    other = make_customer(tenant_a.company, name="Other Party")
    resp = tenant_a.client.patch(f"/api/v1/sales/invoices/{data['id']}/", {
        "customer": other.id,
        "items": [{"product": product.id, "quantity": "2", "unit_price": "100"}],
    }, format="json")
    assert resp.status_code == 400


def test_completed_invoice_cannot_reduce_below_returned_qty(tenant_a):
    data, product, customer = _completed_invoice(tenant_a, qty="3")
    ret = tenant_a.client.post("/api/v1/sales/returns/", {
        "customer": customer.id, "sales_invoice": data["id"],
        "items": [{"product": product.id, "quantity": "2", "unit_price": "100"}],
    }, format="json")
    assert tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/").status_code == 200
    # H9-A blocks quantity changes on completed invoices entirely.
    resp = tenant_a.client.patch(f"/api/v1/sales/invoices/{data['id']}/", {
        "confirm_amend": True,
        "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
    }, format="json")
    assert resp.status_code == 400


def test_completed_invoice_edit_blocks_negative_stock(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"},
    ])
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    # H9-A: quantity increases are not an allowed amend field.
    resp = tenant_a.client.patch(f"/api/v1/sales/invoices/{inv['id']}/", {
        "confirm_amend": True,
        "items": [{"product": product.id, "quantity": "3", "unit_price": "100"}],
    }, format="json")
    assert resp.status_code == 400


def test_completed_invoice_cannot_be_deleted(tenant_a):
    data, _, _ = _completed_invoice(tenant_a)
    resp = tenant_a.client.delete(f"/api/v1/sales/invoices/{data['id']}/")
    assert resp.status_code == 400


def test_draft_can_be_edited_and_deleted(tenant_a):
    product = make_product(tenant_a.company)
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "2", "unit_price": "100"}
    ])
    resp = tenant_a.client.patch(f"/api/v1/sales/invoices/{inv['id']}/", {
        "items": [{"product": product.id, "quantity": "5", "unit_price": "90"}],
    }, format="json")
    assert resp.status_code == 200
    assert Decimal(resp.data["items"][0]["quantity"]) == Decimal("5")

    resp = tenant_a.client.delete(f"/api/v1/sales/invoices/{inv['id']}/")
    assert resp.status_code == 204


def test_cancel_completed_sale_restores_stock(tenant_a):
    data, product, _ = _completed_invoice(tenant_a, qty="3")
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{data['id']}/cancel/")
    assert resp.status_code == 200
    assert resp.data["status"] == "CANCELLED"
    # SALE movement is untouched; an ADJUSTMENT reverses it
    assert StockMovement.objects.filter(movement_type=MovementType.SALE).count() == 1
    adj = StockMovement.objects.get(movement_type=MovementType.ADJUSTMENT)
    assert adj.quantity == Decimal("3")


def test_cannot_cancel_invoice_with_completed_return(tenant_a):
    data, product, customer = _completed_invoice(tenant_a, qty="3")
    ret = tenant_a.client.post("/api/v1/sales/returns/", {
        "customer": customer.id, "sales_invoice": data["id"],
        "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
    }, format="json")
    tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/")
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{data['id']}/cancel/")
    assert resp.status_code == 400


def test_fully_returned_invoice_marked_returned(tenant_a):
    data, product, customer = _completed_invoice(tenant_a, qty="2")
    ret = tenant_a.client.post("/api/v1/sales/returns/", {
        "customer": customer.id, "sales_invoice": data["id"],
        "items": [{"product": product.id, "quantity": "2", "unit_price": "100"}],
    }, format="json")
    resp = tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/")
    assert resp.status_code == 200
    inv = tenant_a.client.get(f"/api/v1/sales/invoices/{data['id']}/")
    assert inv.data["status"] == "RETURNED"


def test_return_cannot_exceed_sold_quantity(tenant_a):
    data, product, customer = _completed_invoice(tenant_a, qty="2")
    ret = tenant_a.client.post("/api/v1/sales/returns/", {
        "customer": customer.id, "sales_invoice": data["id"],
        "items": [{"product": product.id, "quantity": "5", "unit_price": "100"}],
    }, format="json")
    resp = tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/")
    assert resp.status_code == 400


def test_quotation_convert_preserves_lines(tenant_a):
    product = make_product(tenant_a.company)
    customer = make_customer(tenant_a.company)
    quote = tenant_a.client.post("/api/v1/sales/quotations/", {
        "customer": customer.id,
        "items": [{"product": product.id, "quantity": "4", "unit_price": "150"}],
    }, format="json")
    assert quote.status_code == 201, quote.data
    assert quote.data["number"]
    assert str(quote.data["number"]).startswith("QTN")

    resp = tenant_a.client.post(f"/api/v1/sales/quotations/{quote.data['id']}/convert/")
    assert resp.status_code == 200
    assert resp.data["status"] == "DRAFT"
    assert Decimal(resp.data["items"][0]["quantity"]) == Decimal("4")

    q = tenant_a.client.get(f"/api/v1/sales/quotations/{quote.data['id']}/")
    assert q.data["status"] == "CONVERTED"
    assert q.data["converted_invoice"] == resp.data["id"]

    # Cannot convert twice
    resp = tenant_a.client.post(f"/api/v1/sales/quotations/{quote.data['id']}/convert/")
    assert resp.status_code == 400


def test_purchase_status_machine(tenant_a):
    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(tenant_a, supplier, [
        {"product": product.id, "quantity": "5", "unit_price": "80"}
    ])
    resp = tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/")
    assert resp.status_code == 200
    assert resp.data["number"].startswith("PUR-")

    # H9-A: completed purchase price amend needs confirm; qty change blocked
    resp = tenant_a.client.patch(f"/api/v1/purchases/invoices/{pur['id']}/", {
        "confirm_amend": True,
        "items": [{"product": product.id, "quantity": "5", "unit_price": "70"}],
    }, format="json")
    assert resp.status_code == 200, resp.data
    assert Decimal(resp.data["items"][0]["unit_price"]) == Decimal("70.00")

    other = make_supplier(tenant_a.company, name="Other Supplier")
    resp = tenant_a.client.patch(f"/api/v1/purchases/invoices/{pur['id']}/", {
        "supplier": other.id,
        "items": [{"product": product.id, "quantity": "5", "unit_price": "70"}],
    }, format="json")
    assert resp.status_code == 400

    # Cancel reverses stock
    resp = tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/cancel/")
    assert resp.status_code == 200
    from inventory.models import StockBalance

    assert StockBalance.objects.get(product=product).on_hand == Decimal("0")


def test_purchase_return_cannot_exceed_purchased_qty(tenant_a):
    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(tenant_a, supplier, [
        {"product": product.id, "quantity": "2", "unit_price": "80"},
    ])
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    ret = tenant_a.client.post("/api/v1/purchases/returns/", {
        "supplier": supplier.id,
        "purchase_invoice": pur["id"],
        "items": [{"product": product.id, "quantity": "5", "unit_price": "80"}],
    }, format="json")
    assert ret.status_code == 201, ret.data
    resp = tenant_a.client.post(f"/api/v1/purchases/returns/{ret.data['id']}/complete/")
    assert resp.status_code == 400


def test_invoice_create_idempotency_key(tenant_a):
    """BB-000189 — Idempotency-Key returns prior invoice id for 24h."""
    from sales.models import SalesInvoice

    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company)
    payload = {
        "customer": customer.id,
        "invoice_type": "GST",
        "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
    }
    headers = {"HTTP_IDEMPOTENCY_KEY": "wave7-invoice-key-1"}
    first = tenant_a.client.post("/api/v1/sales/invoices/", payload, format="json", **headers)
    assert first.status_code == 201, first.data
    first_id = first.data["id"]

    second = tenant_a.client.post("/api/v1/sales/invoices/", payload, format="json", **headers)
    assert second.status_code in (200, 201), second.data
    assert second.data["id"] == first_id
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == 1


def test_gst_purchase_return_requires_invoice(tenant_a):
    """BB-000020 — GST-registered company cannot complete orphan purchase return."""
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.save(update_fields=["gstin"])
    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    add_stock(tenant_a, product, "5")
    ret = tenant_a.client.post("/api/v1/purchases/returns/", {
        "supplier": supplier.id,
        "items": [{"product": product.id, "quantity": "1", "unit_price": "80"}],
    }, format="json")
    assert ret.status_code == 201, ret.data
    resp = tenant_a.client.post(f"/api/v1/purchases/returns/{ret.data['id']}/complete/")
    assert resp.status_code == 400
