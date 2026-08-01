"""Stock movement matrix — every business event posts the right typed movement (§7)."""

from decimal import Decimal

import pytest

from inventory.models import MovementType, StockBalance, StockMovement
from inventory.services import InventoryService
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def on_hand(company, product):
    balance = StockBalance.objects.get(company=company, product=product)
    return balance.on_hand


def test_opening_stock_increases_on_hand(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    assert on_hand(tenant_a.company, product) == Decimal("10")
    movement = StockMovement.objects.get(product=product)
    assert movement.movement_type == MovementType.OPENING_STOCK


def test_purchase_complete_increases_stock(tenant_a):
    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    data = create_draft_purchase(tenant_a, supplier, [
        {"product": product.id, "quantity": "5", "unit_price": "80"}
    ])
    # Draft has no stock effect
    assert not StockMovement.objects.filter(product=product).exists()

    resp = tenant_a.client.post(f"/api/v1/purchases/invoices/{data['id']}/complete/")
    assert resp.status_code == 200
    assert on_hand(tenant_a.company, product) == Decimal("5")
    movement = StockMovement.objects.get(product=product)
    assert movement.movement_type == MovementType.PURCHASE
    assert movement.unit_cost == Decimal("80.00")


def test_sale_complete_decreases_stock(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    data = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "3", "unit_price": "100"}
    ])
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{data['id']}/complete/")
    assert resp.status_code == 200
    assert on_hand(tenant_a.company, product) == Decimal("7")
    assert StockMovement.objects.filter(product=product, movement_type=MovementType.SALE).count() == 1


def test_sales_return_restores_stock(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "3", "unit_price": "100"}
    ])
    tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")

    ret = tenant_a.client.post("/api/v1/sales/returns/", {
        "customer": customer.id, "sales_invoice": inv["id"],
        "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
    }, format="json")
    assert ret.status_code == 201, ret.data
    resp = tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/")
    assert resp.status_code == 200
    assert on_hand(tenant_a.company, product) == Decimal("8")
    assert StockMovement.objects.filter(movement_type=MovementType.SALES_RETURN).count() == 1


def test_purchase_return_decreases_stock(tenant_a):
    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(tenant_a, supplier, [
        {"product": product.id, "quantity": "5", "unit_price": "80"}
    ])
    tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/")

    ret = tenant_a.client.post("/api/v1/purchases/returns/", {
        "supplier": supplier.id, "purchase_invoice": pur["id"],
        "items": [{"product": product.id, "quantity": "2", "unit_price": "80"}],
    }, format="json")
    assert ret.status_code == 201, ret.data
    resp = tenant_a.client.post(f"/api/v1/purchases/returns/{ret.data['id']}/complete/")
    assert resp.status_code == 200
    assert on_hand(tenant_a.company, product) == Decimal("3")


def test_fully_returned_purchase_marked_returned(tenant_a):
    """BUG-212 — mirrors the sales-side RETURNED status transition."""
    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(tenant_a, supplier, [
        {"product": product.id, "quantity": "5", "unit_price": "80"}
    ])
    tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/")

    ret = tenant_a.client.post("/api/v1/purchases/returns/", {
        "supplier": supplier.id, "purchase_invoice": pur["id"],
        "items": [{"product": product.id, "quantity": "5", "unit_price": "80"}],
    }, format="json")
    tenant_a.client.post(f"/api/v1/purchases/returns/{ret.data['id']}/complete/")

    detail = tenant_a.client.get(f"/api/v1/purchases/invoices/{pur['id']}/")
    assert detail.data["status"] == "RETURNED"


def test_manual_adjustment_and_permissions(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")

    # Sales staff without inventory permission is blocked (§5.5)
    resp = tenant_a.staff_client.post("/api/v1/inventory/adjustments/", {
        "product": product.id, "quantity": "-2", "reason": "damage",
    }, format="json")
    assert resp.status_code == 403

    resp = tenant_a.client.post("/api/v1/inventory/adjustments/", {
        "product": product.id, "quantity": "-2", "reason": "damage",
    }, format="json")
    assert resp.status_code == 201
    assert on_hand(tenant_a.company, product) == Decimal("8")


def test_movements_are_append_only(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    movement = StockMovement.objects.get(product=product)
    with pytest.raises(ValueError):
        movement.quantity = Decimal("99")
        movement.save()
    with pytest.raises(ValueError):
        movement.delete()


def test_balance_rebuildable_from_movements(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    InventoryService.post_movement(
        company=tenant_a.company, product=product,
        movement_type=MovementType.ADJUSTMENT, quantity=Decimal("-3"),
        reason="shrinkage", user=tenant_a.owner,
    )
    # Corrupt the cache, then rebuild
    StockBalance.objects.filter(product=product).update(on_hand=Decimal("999"))
    balance = InventoryService.rebuild_balance(tenant_a.company, product)
    assert balance.on_hand == Decimal("7")


def test_available_equals_on_hand_minus_reserved(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    resp = tenant_a.client.get("/api/v1/inventory/balances/")
    row = resp.data["results"][0]
    assert Decimal(row["on_hand"]) == Decimal("10")
    assert Decimal(row["reserved"]) == Decimal("0")
    assert Decimal(row["available"]) == Decimal("10")


def test_low_stock_alerts(tenant_a):
    product = make_product(tenant_a.company, reorder_level="5")
    add_stock(tenant_a, product, "3")
    resp = tenant_a.client.get("/api/v1/inventory/alerts/")
    assert resp.status_code == 200
    assert resp.data["count"] == 1


def test_low_stock_alert_clears_after_restock(tenant_a):
    """BUG-726 — the alert must disappear once stock is replenished."""
    product = make_product(tenant_a.company, reorder_level="5")
    add_stock(tenant_a, product, "3")
    InventoryService.post_movement(
        company=tenant_a.company, product=product,
        movement_type=MovementType.ADJUSTMENT, quantity=Decimal("10"),
        reason="restock", user=tenant_a.owner,
    )
    resp = tenant_a.client.get("/api/v1/inventory/alerts/")
    assert resp.data["count"] == 0


def test_opening_stock_cannot_be_recorded_twice(tenant_a):
    """BUG-312 — re-submitting opening stock must not additively stack."""
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    resp = tenant_a.client.post("/api/v1/inventory/opening-stock/", {
        "product": product.id, "quantity": "10", "unit_cost": "80",
    }, format="json")
    assert resp.status_code == 400
    assert on_hand(tenant_a.company, product) == Decimal("10")


def test_manual_adjustment_respects_negative_stock_policy(tenant_a):
    """BUG-322 — ADJUSTMENT movements were the one gap where the company's
    negative_stock_policy=BLOCK was never enforced at all."""
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "5")
    resp = tenant_a.client.post("/api/v1/inventory/adjustments/", {
        "product": product.id, "quantity": "-10", "reason": "shrinkage",
    }, format="json")
    assert resp.status_code == 400
    assert on_hand(tenant_a.company, product) == Decimal("5")
