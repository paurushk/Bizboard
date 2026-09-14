"""
Warehouse-scoped exact-quantity stock movement (companion to test_stock_flow.py).

test_stock_flow.py proves the *arithmetic* is correct ("qty decreases/increases
by exactly N") but every one of those tests runs against a tenant with a
single (default) warehouse, so `on_hand()` / `available_quantity()` are called
with no `warehouse=` filter at all. That is company-wide aggregation, not
per-godown verification — it would pass identically if a sale silently
decremented the *wrong* warehouse's balance, as long as there was only one
warehouse to decrement.

These tests seed two warehouses and assert:
  1. the selected warehouse's StockBalance row moves by exactly the
     transacted quantity, and
  2. the OTHER warehouse's StockBalance row is byte-for-byte unchanged.
"""

from decimal import Decimal

import pytest

from inventory.models import MovementType, StockBalance, Warehouse
from inventory.services import InventoryService
from tests.conftest import make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db


def _balance(company, warehouse, product):
    return StockBalance.objects.get(company=company, warehouse=warehouse, product=product, batch=None)


def _make_two_warehouses(company):
    default = InventoryService.default_warehouse(company)
    branch = Warehouse.objects.create(company=company, name="Branch", code="BRANCH")
    return default, branch


def test_sale_complete_decreases_exact_qty_in_selected_warehouse_only(tenant_a):
    product = make_product(tenant_a.company, sku="MW-SALE-1")
    customer = make_customer(tenant_a.company)
    default_wh, branch_wh = _make_two_warehouses(tenant_a.company)

    InventoryService.post_movement(
        company=tenant_a.company, warehouse=default_wh, product=product,
        movement_type=MovementType.OPENING_STOCK, quantity=Decimal("10"), unit_cost=Decimal("80"),
        user=tenant_a.owner,
    )
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=branch_wh, product=product,
        movement_type=MovementType.OPENING_STOCK, quantity=Decimal("10"), unit_cost=Decimal("80"),
        user=tenant_a.owner,
    )

    resp = tenant_a.client.post("/api/v1/sales/invoices/", {
        "customer": customer.id,
        "invoice_type": "GST",
        "warehouse": branch_wh.id,
        "items": [{"product": product.id, "quantity": "3", "unit_price": "100"}],
    }, format="json")
    assert resp.status_code == 201, resp.data
    complete = tenant_a.client.post(f"/api/v1/sales/invoices/{resp.data['id']}/complete/")
    assert complete.status_code == 200, complete.data

    assert _balance(tenant_a.company, branch_wh, product).on_hand == Decimal("7")
    assert _balance(tenant_a.company, default_wh, product).on_hand == Decimal("10"), (
        "selling from the branch godown must not touch the default godown's balance"
    )


def test_purchase_complete_increases_exact_qty_in_selected_warehouse_only(tenant_a):
    product = make_product(tenant_a.company, sku="MW-PUR-1")
    supplier = make_supplier(tenant_a.company)
    default_wh, branch_wh = _make_two_warehouses(tenant_a.company)

    InventoryService.post_movement(
        company=tenant_a.company, warehouse=default_wh, product=product,
        movement_type=MovementType.OPENING_STOCK, quantity=Decimal("4"), unit_cost=Decimal("80"),
        user=tenant_a.owner,
    )

    resp = tenant_a.client.post("/api/v1/purchases/invoices/", {
        "supplier": supplier.id,
        "purchase_type": "GST",
        "warehouse": branch_wh.id,
        "items": [{"product": product.id, "quantity": "5", "unit_price": "80"}],
    }, format="json")
    assert resp.status_code == 201, resp.data
    complete = tenant_a.client.post(f"/api/v1/purchases/invoices/{resp.data['id']}/complete/")
    assert complete.status_code == 200, complete.data

    assert _balance(tenant_a.company, branch_wh, product).on_hand == Decimal("5")
    assert _balance(tenant_a.company, default_wh, product).on_hand == Decimal("4"), (
        "receiving into the branch godown must not touch the default godown's balance"
    )


def test_pos_checkout_decreases_exact_qty_in_selected_warehouse_only(tenant_a):
    product = make_product(tenant_a.company, gst_rate="18", selling_price="100", sku="MW-POS-1")
    customer = make_customer(tenant_a.company, state="Karnataka", gstin="29AAAAA0000A1ZY")
    default_wh, branch_wh = _make_two_warehouses(tenant_a.company)

    InventoryService.post_movement(
        company=tenant_a.company, warehouse=default_wh, product=product,
        movement_type=MovementType.OPENING_STOCK, quantity=Decimal("20"), unit_cost=Decimal("60"),
        user=tenant_a.owner,
    )
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=branch_wh, product=product,
        movement_type=MovementType.OPENING_STOCK, quantity=Decimal("20"), unit_cost=Decimal("60"),
        user=tenant_a.owner,
    )

    checkout_payload = {
        "invoice": {
            "customer": customer.id,
            "invoice_type": "RETAIL",
            "invoice_date": "2026-03-15",
            "warehouse": branch_wh.id,
            "items": [{"product": product.id, "quantity": "2", "unit_price": "100.00", "gst_rate": "18"}],
        },
        "payment": {"mode": "CASH", "amount": "236.00", "tendered_amount": "250.00"},
    }
    res = tenant_a.client.post("/api/v1/sales/invoices/pos-checkout/", checkout_payload, format="json")
    assert res.status_code == 201, res.data

    # The POS checkout hits the exact same SalesService.complete() path a
    # regular invoice does, so — unlike test_wf19_pos_checkout, which reads
    # InventoryService.available_quantity() with no warehouse filter (i.e. a
    # company-wide aggregate that can't tell godowns apart) — assert directly
    # against the specific godown's row, plus that the OTHER godown is untouched.
    assert _balance(tenant_a.company, branch_wh, product).on_hand == Decimal("18")
    assert _balance(tenant_a.company, default_wh, product).on_hand == Decimal("20"), (
        "a POS sale from the branch godown must not touch the default godown's balance"
    )


def test_negative_stock_block_is_scoped_to_the_selected_warehouse(tenant_a):
    """A BLOCK-policy company with plenty of stock in warehouse B must still
    refuse a sale from empty warehouse A — the guard must not let stock
    sitting in another godown paper over a shortfall in the one actually
    being sold from (inventory/services.py `_stock_in_other_warehouses` exists
    only to *surface* this in the error message, never to bypass the check)."""
    tenant_a.company.negative_stock_policy = "BLOCK"
    tenant_a.company.save(update_fields=["negative_stock_policy"])
    product = make_product(tenant_a.company, sku="MW-BLOCK-1")
    customer = make_customer(tenant_a.company)
    default_wh, branch_wh = _make_two_warehouses(tenant_a.company)

    # Plenty of stock, but only in the default godown.
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=default_wh, product=product,
        movement_type=MovementType.OPENING_STOCK, quantity=Decimal("50"), unit_cost=Decimal("80"),
        user=tenant_a.owner,
    )

    resp = tenant_a.client.post("/api/v1/sales/invoices/", {
        "customer": customer.id,
        "invoice_type": "GST",
        "warehouse": branch_wh.id,
        "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
    }, format="json")
    assert resp.status_code == 201, resp.data
    complete = tenant_a.client.post(f"/api/v1/sales/invoices/{resp.data['id']}/complete/")

    assert complete.status_code == 400, complete.data
    assert _balance(tenant_a.company, default_wh, product).on_hand == Decimal("50"), (
        "a blocked sale must not silently draw down stock from a different godown"
    )
    assert not StockBalance.objects.filter(company=tenant_a.company, warehouse=branch_wh, product=product).exists()


def test_sales_return_restores_exact_qty_to_the_original_warehouse_only(tenant_a):
    product = make_product(tenant_a.company, sku="MW-RET-1")
    customer = make_customer(tenant_a.company)
    default_wh, branch_wh = _make_two_warehouses(tenant_a.company)

    InventoryService.post_movement(
        company=tenant_a.company, warehouse=default_wh, product=product,
        movement_type=MovementType.OPENING_STOCK, quantity=Decimal("10"), unit_cost=Decimal("80"),
        user=tenant_a.owner,
    )
    InventoryService.post_movement(
        company=tenant_a.company, warehouse=branch_wh, product=product,
        movement_type=MovementType.OPENING_STOCK, quantity=Decimal("10"), unit_cost=Decimal("80"),
        user=tenant_a.owner,
    )

    inv = tenant_a.client.post("/api/v1/sales/invoices/", {
        "customer": customer.id,
        "invoice_type": "GST",
        "warehouse": branch_wh.id,
        "items": [{"product": product.id, "quantity": "3", "unit_price": "100"}],
    }, format="json")
    assert inv.status_code == 201, inv.data
    tenant_a.client.post(f"/api/v1/sales/invoices/{inv.data['id']}/complete/")

    ret = tenant_a.client.post("/api/v1/sales/returns/", {
        "customer": customer.id, "sales_invoice": inv.data["id"],
        "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
    }, format="json")
    assert ret.status_code == 201, ret.data
    complete = tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/")
    assert complete.status_code == 200, complete.data

    assert _balance(tenant_a.company, branch_wh, product).on_hand == Decimal("8")
    assert _balance(tenant_a.company, default_wh, product).on_hand == Decimal("10"), (
        "a return against a branch-godown sale must restore stock to that same godown, not the default one"
    )
