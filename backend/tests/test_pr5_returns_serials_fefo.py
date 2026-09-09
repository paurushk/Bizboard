"""PR 5 — return serials/idempotency (R-066) and purchase-return FEFO (R-039)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from core.idempotency import MONEY_IDEMPOTENCY_SCOPES, TRANSIENT_4XX_CODES
from inventory.models import BatchLot, StockBalance
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


def test_r066_return_scopes_are_money_and_serial_is_transient():
    for scope in (
        "sales_return_create",
        "sales_return_complete",
        "purchase_return_create",
        "purchase_return_complete",
    ):
        assert scope in MONEY_IDEMPOTENCY_SCOPES
    assert "serial_required" in TRANSIENT_4XX_CODES


def test_r066_sales_return_complete_replays_same_key(tenant_a):
    product = make_product(tenant_a.company, sku="SR-IDEM")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "50"}]
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    created = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "items": [{"product": product.id, "quantity": "1", "unit_price": "50"}],
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="sr-create-1",
    )
    assert created.status_code == 201, created.data
    replay_create = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "items": [{"product": product.id, "quantity": "1", "unit_price": "50"}],
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="sr-create-1",
    )
    assert replay_create.status_code == 201
    assert replay_create.data["id"] == created.data["id"]

    first = tenant_a.client.post(
        f"/api/v1/sales/returns/{created.data['id']}/complete/",
        HTTP_IDEMPOTENCY_KEY="sr-create-1-complete",
    )
    assert first.status_code == 200, first.data
    second = tenant_a.client.post(
        f"/api/v1/sales/returns/{created.data['id']}/complete/",
        HTTP_IDEMPOTENCY_KEY="sr-create-1-complete",
    )
    assert second.status_code == 200, second.data


def test_r066_purchase_return_missing_serials_releases_key(tenant_a):
    product = make_product(tenant_a.company, sku="PR-SN-KEY", track_serial=True, purchase_price="50")
    supplier = make_supplier(tenant_a.company)
    inv = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "50", "serial_numbers": ["PR-KEY-1"]}],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{inv['id']}/complete/").status_code == 200
    bad = tenant_a.client.post(
        "/api/v1/purchases/returns/",
        {
            "supplier": supplier.id,
            "purchase_invoice": inv["id"],
            "items": [{"product": product.id, "quantity": "1", "unit_price": "50"}],
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="pr-serial-1",
    )
    assert bad.status_code == 400, bad.data
    good = tenant_a.client.post(
        "/api/v1/purchases/returns/",
        {
            "supplier": supplier.id,
            "purchase_invoice": inv["id"],
            "items": [
                {
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "50",
                    "serial_numbers": ["PR-KEY-1"],
                }
            ],
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="pr-serial-1",
    )
    assert good.status_code == 201, good.data


def test_r039_purchase_return_retires_earliest_expiry_first(tenant_a):
    product = make_product(tenant_a.company, sku="PR-FEFO", track_batch=True)
    supplier = make_supplier(tenant_a.company)
    early = (date.today() + timedelta(days=10)).isoformat()
    late = (date.today() + timedelta(days=90)).isoformat()
    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [
            {
                "product": product.id,
                "quantity": "2",
                "unit_price": "10",
                "batch_no": "EARLY",
                "exp_date": early,
            },
            {
                "product": product.id,
                "quantity": "3",
                "unit_price": "10",
                "batch_no": "LATE",
                "exp_date": late,
            },
        ],
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    early_lot = BatchLot.objects.get(product=product, batch_no="EARLY")
    late_lot = BatchLot.objects.get(product=product, batch_no="LATE")
    assert StockBalance.objects.get(
        product=product, warehouse=warehouse, batch=early_lot
    ).on_hand == Decimal("2")
    assert StockBalance.objects.get(
        product=product, warehouse=warehouse, batch=late_lot
    ).on_hand == Decimal("3")

    ret = tenant_a.client.post(
        "/api/v1/purchases/returns/",
        {
            "supplier": supplier.id,
            "purchase_invoice": pur["id"],
            "items": [{"product": product.id, "quantity": "2", "unit_price": "10"}],
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    done = tenant_a.client.post(f"/api/v1/purchases/returns/{ret.data['id']}/complete/")
    assert done.status_code == 200, done.data
    assert StockBalance.objects.get(
        product=product, warehouse=warehouse, batch=early_lot
    ).on_hand == Decimal("0")
    assert StockBalance.objects.get(
        product=product, warehouse=warehouse, batch=late_lot
    ).on_hand == Decimal("3")
