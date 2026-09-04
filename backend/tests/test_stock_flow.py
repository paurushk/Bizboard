"""Stock movement matrix — every business event posts the right typed movement (§7)."""

from datetime import date
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


def test_rebuild_balance_does_not_side_effect_other_batch_lots(tenant_a):
    """B8-023: rebuild_balance(batch=lot_A) must write ONLY lot_A's row —
    it used to also overwrite every other lot's on_hand/reserved as a side
    effect of its embedded FEFO reservation walk (order-dependent output)."""
    from inventory.models import BatchLot

    product = make_product(tenant_a.company, sku="LOT-1", track_batch=True)
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    lot_a = BatchLot.objects.create(
        company=tenant_a.company, product=product, batch_no="A", expiry_date=date(2099, 1, 1),
    )
    lot_b = BatchLot.objects.create(
        company=tenant_a.company, product=product, batch_no="B", expiry_date=date(2099, 6, 1),
    )
    InventoryService.post_opening(
        company=tenant_a.company, product=product, quantity=Decimal("10"),
        unit_cost=Decimal("50"), warehouse=warehouse, batch=lot_a, user=tenant_a.owner,
    )
    InventoryService.post_opening(
        company=tenant_a.company, product=product, quantity=Decimal("20"),
        unit_cost=Decimal("50"), warehouse=warehouse, batch=lot_b, user=tenant_a.owner,
    )
    bal_a = StockBalance.objects.get(company=tenant_a.company, product=product, batch=lot_a)
    bal_b = StockBalance.objects.get(company=tenant_a.company, product=product, batch=lot_b)
    # Simulate a stale cache on lot B's reserved that a rebuild of lot A
    # alone must not touch.
    bal_b.reserved = Decimal("999")
    bal_b.save(update_fields=["reserved"])

    InventoryService.rebuild_balance(tenant_a.company, product, warehouse=warehouse, batch=lot_a)

    bal_b.refresh_from_db()
    assert bal_b.on_hand == Decimal("20")
    assert bal_b.reserved == Decimal("999"), "rebuilding lot A's key must not have touched lot B's row"
    bal_a.refresh_from_db()
    assert bal_a.on_hand == Decimal("10")


def test_reconcile_batch_reservations_fefo_splits_across_lots(tenant_a):
    """B8-023: the FEFO reservation split is now a dedicated pass — confirm
    it still produces the right per-lot reserved qty, and that it clears a
    stale reserved on a lot it doesn't need to touch this time."""
    from inventory.models import BatchLot
    from sales.models import SalesInvoice, SalesOrder
    from sales.notes_services import SalesNotesService

    product = make_product(tenant_a.company, sku="LOT-2", track_batch=True)
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    lot_a = BatchLot.objects.create(
        company=tenant_a.company, product=product, batch_no="A2", expiry_date=date(2099, 1, 1),
    )
    lot_b = BatchLot.objects.create(
        company=tenant_a.company, product=product, batch_no="B2", expiry_date=date(2099, 6, 1),
    )
    InventoryService.post_opening(
        company=tenant_a.company, product=product, quantity=Decimal("5"),
        unit_cost=Decimal("50"), warehouse=warehouse, batch=lot_a, user=tenant_a.owner,
    )
    InventoryService.post_opening(
        company=tenant_a.company, product=product, quantity=Decimal("20"),
        unit_cost=Decimal("50"), warehouse=warehouse, batch=lot_b, user=tenant_a.owner,
    )
    customer = make_customer(tenant_a.company)
    order = SalesOrder.objects.create(
        company=tenant_a.company, customer=customer,
        invoice_type=SalesInvoice.InvoiceType.NON_GST,
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    # FEFO orders lot_a (expires first) before lot_b — a confirmed SO for 8
    # should reserve all 5 of lot_a then 3 of lot_b.
    SalesNotesService.set_order_items(
        order,
        [{"product": product, "quantity": Decimal("8"), "unit_price": Decimal("100"), "gst_rate": Decimal("0")}],
        tenant_a.owner,
    )
    SalesNotesService.confirm_sales_order(order, tenant_a.owner)

    InventoryService.rebuild_balance(tenant_a.company, product, warehouse=warehouse, batch=lot_a)
    InventoryService.rebuild_balance(tenant_a.company, product, warehouse=warehouse, batch=lot_b)
    InventoryService.reconcile_batch_reservations(tenant_a.company, product, warehouse=warehouse)

    bal_a = StockBalance.objects.get(company=tenant_a.company, product=product, batch=lot_a)
    bal_b = StockBalance.objects.get(company=tenant_a.company, product=product, batch=lot_b)
    assert bal_a.reserved == Decimal("5")
    assert bal_b.reserved == Decimal("3")


def test_rebuild_stock_balances_command_reconciles_batch_reservations(tenant_a):
    """B8-022/B8-023: the management command's two-pass rebuild (on_hand for
    every key, then one FEFO reservation reconcile per product/warehouse)
    end to end, plus the batched orphan-row cleanup."""
    from django.core.management import call_command

    from inventory.models import BatchLot

    product = make_product(tenant_a.company, sku="LOT-3", track_batch=True)
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    lot_a = BatchLot.objects.create(
        company=tenant_a.company, product=product, batch_no="A3", expiry_date=date(2099, 1, 1),
    )
    lot_b = BatchLot.objects.create(
        company=tenant_a.company, product=product, batch_no="B3", expiry_date=date(2099, 6, 1),
    )
    InventoryService.post_opening(
        company=tenant_a.company, product=product, quantity=Decimal("5"),
        unit_cost=Decimal("50"), warehouse=warehouse, batch=lot_a, user=tenant_a.owner,
    )
    InventoryService.post_opening(
        company=tenant_a.company, product=product, quantity=Decimal("20"),
        unit_cost=Decimal("50"), warehouse=warehouse, batch=lot_b, user=tenant_a.owner,
    )
    from sales.models import SalesInvoice, SalesOrder
    from sales.notes_services import SalesNotesService

    customer = make_customer(tenant_a.company)
    order = SalesOrder.objects.create(
        company=tenant_a.company, customer=customer,
        invoice_type=SalesInvoice.InvoiceType.NON_GST,
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    SalesNotesService.set_order_items(
        order,
        [{"product": product, "quantity": Decimal("8"), "unit_price": Decimal("100"), "gst_rate": Decimal("0")}],
        tenant_a.owner,
    )
    SalesNotesService.confirm_sales_order(order, tenant_a.owner)

    # Corrupt the cache (as if it had drifted) and leave an orphan row with
    # no backing movements — both must be fixed by one command run.
    StockBalance.objects.filter(product=product, batch=lot_a).update(on_hand=Decimal("999"), reserved=Decimal("0"))
    orphan_batch = BatchLot.objects.create(
        company=tenant_a.company, product=product, batch_no="ORPHAN", expiry_date=date(2099, 1, 1),
    )
    StockBalance.objects.create(
        company=tenant_a.company, warehouse=warehouse, product=product, batch=orphan_batch,
        on_hand=Decimal("7"), reserved=Decimal("0"),
    )

    call_command("rebuild_stock_balances", company=tenant_a.company.pk)

    bal_a = StockBalance.objects.get(company=tenant_a.company, product=product, batch=lot_a)
    bal_b = StockBalance.objects.get(company=tenant_a.company, product=product, batch=lot_b)
    assert bal_a.on_hand == Decimal("5")
    assert bal_a.reserved == Decimal("5")
    assert bal_b.reserved == Decimal("3")
    assert not StockBalance.objects.filter(batch=orphan_batch).exists()
