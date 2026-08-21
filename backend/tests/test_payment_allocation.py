"""Payment allocation math (§5.4, §8)."""

from decimal import Decimal

import pytest

from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def _completed_sale(tenant, amount_qty="50"):
    """Invoice: 50 × 100 @18% intra = 5900 grand total."""
    product = make_product(tenant.company)
    add_stock(tenant, product, "100")
    customer = make_customer(tenant.company, state="Karnataka")
    inv = create_draft_invoice(tenant, customer, [
        {"product": product.id, "quantity": amount_qty, "unit_price": "100"}
    ])
    resp = tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 200
    return resp.data, customer, product


def _receipt(tenant, customer, amount):
    resp = tenant.client.post("/api/v1/payments/receipts/", {
        "customer": customer.id, "amount": amount, "mode": "UPI",
    }, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data


def test_receipt_requires_positive_amount(tenant_a):
    customer = make_customer(tenant_a.company)
    resp = tenant_a.client.post("/api/v1/payments/receipts/", {
        "customer": customer.id, "amount": "0", "mode": "CASH",
    }, format="json")
    assert resp.status_code == 400


def test_partial_allocation_reduces_outstanding(tenant_a):
    inv, customer, _ = _completed_sale(tenant_a)  # 5900
    receipt = _receipt(tenant_a, customer, "2000")

    resp = tenant_a.client.post("/api/v1/payments/allocations/", {
        "receipt": receipt["id"], "sales_invoice": inv["id"], "amount": "2000",
    }, format="json")
    assert resp.status_code == 201

    ledger = tenant_a.client.get(f"/api/v1/ledgers/customers/{customer.id}/")
    # Outstanding = 5900 − 2000 allocated
    assert Decimal(ledger.data["outstanding"]) == Decimal("3900.00")


def test_allocation_cannot_exceed_receipt_amount(tenant_a):
    inv, customer, _ = _completed_sale(tenant_a)
    receipt = _receipt(tenant_a, customer, "1000")
    resp = tenant_a.client.post("/api/v1/payments/allocations/", {
        "receipt": receipt["id"], "sales_invoice": inv["id"], "amount": "1500",
    }, format="json")
    assert resp.status_code == 400


def test_allocations_cannot_exceed_receipt_across_calls(tenant_a):
    inv, customer, _ = _completed_sale(tenant_a)
    receipt = _receipt(tenant_a, customer, "1000")
    ok = tenant_a.client.post("/api/v1/payments/allocations/", {
        "receipt": receipt["id"], "sales_invoice": inv["id"], "amount": "800",
    }, format="json")
    assert ok.status_code == 201
    over = tenant_a.client.post("/api/v1/payments/allocations/", {
        "receipt": receipt["id"], "sales_invoice": inv["id"], "amount": "300",
    }, format="json")
    assert over.status_code == 400


def test_allocation_cannot_exceed_invoice_outstanding(tenant_a):
    inv, customer, _ = _completed_sale(tenant_a)  # 5900
    receipt = _receipt(tenant_a, customer, "10000")
    resp = tenant_a.client.post("/api/v1/payments/allocations/", {
        "receipt": receipt["id"], "sales_invoice": inv["id"], "amount": "6000",
    }, format="json")
    assert resp.status_code == 400
    # Exactly the outstanding is fine (fully allocated)
    resp = tenant_a.client.post("/api/v1/payments/allocations/", {
        "receipt": receipt["id"], "sales_invoice": inv["id"], "amount": "5900",
    }, format="json")
    assert resp.status_code == 201


def test_allocation_to_draft_invoice_rejected(tenant_a):
    product = make_product(tenant_a.company)
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"}
    ])
    receipt = _receipt(tenant_a, customer, "100")
    resp = tenant_a.client.post("/api/v1/payments/allocations/", {
        "receipt": receipt["id"], "sales_invoice": inv["id"], "amount": "100",
    }, format="json")
    assert resp.status_code == 400


def test_receipt_customer_must_match_invoice_customer(tenant_a):
    inv, customer, _ = _completed_sale(tenant_a)
    other = make_customer(tenant_a.company, name="Other")
    receipt = _receipt(tenant_a, other, "500")
    resp = tenant_a.client.post("/api/v1/payments/allocations/", {
        "receipt": receipt["id"], "sales_invoice": inv["id"], "amount": "500",
    }, format="json")
    assert resp.status_code == 400


def test_supplier_payment_allocation_flow(tenant_a):
    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company, state="Karnataka")
    pur = create_draft_purchase(tenant_a, supplier, [
        {"product": product.id, "quantity": "10", "unit_price": "80"}
    ])  # 800 + 18% = 944
    tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/")

    payment = tenant_a.client.post("/api/v1/payments/supplier-payments/", {
        "supplier": supplier.id, "amount": "500", "mode": "BANK",
    }, format="json")
    assert payment.status_code == 201
    assert payment.data["number"].startswith("PAY-")

    resp = tenant_a.client.post("/api/v1/payments/allocations/", {
        "supplier_payment": payment.data["id"], "purchase_invoice": pur["id"], "amount": "500",
    }, format="json")
    assert resp.status_code == 201

    ledger = tenant_a.client.get(f"/api/v1/ledgers/suppliers/{supplier.id}/")
    assert Decimal(ledger.data["outstanding"]) == Decimal("444.00")


def test_allocation_needs_exactly_one_payment_source(tenant_a):
    inv, customer, _ = _completed_sale(tenant_a)
    resp = tenant_a.client.post("/api/v1/payments/allocations/", {
        "sales_invoice": inv["id"], "amount": "100",
    }, format="json")
    assert resp.status_code == 400


def test_cannot_delete_receipt_with_allocation(tenant_a):
    """BUG-311 — deleting a receipt must not silently drop its allocations
    and make a paid invoice look unpaid again."""
    inv, customer, _ = _completed_sale(tenant_a)
    receipt = _receipt(tenant_a, customer, "1000")
    alloc = tenant_a.client.post("/api/v1/payments/allocations/", {
        "receipt": receipt["id"], "sales_invoice": inv["id"], "amount": "1000",
    }, format="json")
    assert alloc.status_code == 201

    resp = tenant_a.client.delete(f"/api/v1/payments/receipts/{receipt['id']}/")
    assert resp.status_code in (400, 404, 405)
    ledger = tenant_a.client.get(f"/api/v1/ledgers/customers/{customer.id}/")
    assert Decimal(ledger.data["outstanding"]) == Decimal("4900.00")


def test_receipt_without_allocations_cannot_be_hard_deleted(tenant_a):
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "500")
    resp = tenant_a.client.delete(f"/api/v1/payments/receipts/{receipt['id']}/")
    assert resp.status_code in (404, 405)


def test_staff_without_cancel_permission_cannot_delete_allocation(tenant_a):
    """BUG-310 — un-applying an allocation needs the same permission bar as
    cancelling a completed document, not just plain company membership."""
    inv, customer, _ = _completed_sale(tenant_a)
    receipt = _receipt(tenant_a, customer, "1000")
    alloc = tenant_a.client.post("/api/v1/payments/allocations/", {
        "receipt": receipt["id"], "sales_invoice": inv["id"], "amount": "1000",
    }, format="json")

    resp = tenant_a.staff_client.delete(f"/api/v1/payments/allocations/{alloc.data['id']}/")
    assert resp.status_code in (403, 404, 405)

    owner_resp = tenant_a.client.delete(f"/api/v1/payments/allocations/{alloc.data['id']}/")
    assert owner_resp.status_code in (204, 403, 404, 405)


def test_staff_without_cancel_permission_cannot_delete_receipt(tenant_a):
    """BB-000650 — receipt hard delete is forbidden for everyone."""
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "500")
    resp = tenant_a.staff_client.delete(f"/api/v1/payments/receipts/{receipt['id']}/")
    assert resp.status_code in (403, 404, 405)


def test_receipt_and_allocation_hard_delete_forbidden(tenant_a):
    """BB-000650 / BB-000651 — money docs are not hard-deleted."""
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "500")
    receipt_id = str(receipt["id"])

    del_receipt = tenant_a.client.delete(f"/api/v1/payments/receipts/{receipt_id}/")
    assert del_receipt.status_code in (404, 405)

    inv, customer2, _ = _completed_sale(tenant_a)
    receipt2 = _receipt(tenant_a, customer2, "1000")
    alloc = tenant_a.client.post("/api/v1/payments/allocations/", {
        "receipt": receipt2["id"], "sales_invoice": inv["id"], "amount": "1000",
    }, format="json")
    assert alloc.status_code == 201
    alloc_id = str(alloc.data["id"])

    del_alloc = tenant_a.client.delete(f"/api/v1/payments/allocations/{alloc_id}/")
    assert del_alloc.status_code in (404, 405)


def test_cannot_cancel_invoice_with_payment_allocation(tenant_a):
    """BUG-722 — cancelling a paid invoice would leave a dangling
    allocation pointing at a no-longer-completed document."""
    inv, customer, _ = _completed_sale(tenant_a)
    receipt = _receipt(tenant_a, customer, "1000")
    tenant_a.client.post("/api/v1/payments/allocations/", {
        "receipt": receipt["id"], "sales_invoice": inv["id"], "amount": "1000",
    }, format="json")

    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/cancel/")
    assert resp.status_code == 400


def test_receipt_cannot_be_allocated_to_purchase_invoice(tenant_a):
    """BUG-723 — a receipt (customer money in) must not allocate against a
    purchase invoice; only a supplier_payment can pair with purchase_invoice."""
    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company, state="Karnataka")
    pur = create_draft_purchase(tenant_a, supplier, [
        {"product": product.id, "quantity": "10", "unit_price": "80"}
    ])
    tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/")
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "500")

    resp = tenant_a.client.post("/api/v1/payments/allocations/", {
        "receipt": receipt["id"], "purchase_invoice": pur["id"], "amount": "500",
    }, format="json")
    assert resp.status_code == 400


def test_supplier_payment_cannot_be_allocated_to_sales_invoice(tenant_a):
    """BUG-723 — a supplier_payment (money out) must not allocate against a
    sales invoice; only a receipt can pair with sales_invoice."""
    inv, customer, _ = _completed_sale(tenant_a)
    supplier = make_supplier(tenant_a.company, state="Karnataka")
    payment = tenant_a.client.post("/api/v1/payments/supplier-payments/", {
        "supplier": supplier.id, "amount": "500", "mode": "BANK",
    }, format="json")
    assert payment.status_code == 201

    resp = tenant_a.client.post("/api/v1/payments/allocations/", {
        "supplier_payment": payment.data["id"], "sales_invoice": inv["id"], "amount": "500",
    }, format="json")
    assert resp.status_code == 400


def test_cannot_cancel_purchase_with_payment_allocation(tenant_a):
    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company, state="Karnataka")
    pur = create_draft_purchase(tenant_a, supplier, [
        {"product": product.id, "quantity": "10", "unit_price": "80"}
    ])
    tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/")
    payment = tenant_a.client.post("/api/v1/payments/supplier-payments/", {
        "supplier": supplier.id, "amount": "500", "mode": "BANK",
    }, format="json")
    tenant_a.client.post("/api/v1/payments/allocations/", {
        "supplier_payment": payment.data["id"], "purchase_invoice": pur["id"], "amount": "500",
    }, format="json")

    resp = tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/cancel/")
    assert resp.status_code == 400
