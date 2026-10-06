"""Wave 3 stock and document lifecycle regressions."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from core.exceptions import BusinessRuleError
from tests.conftest import add_stock, make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db


def _wh(company):
    from inventory.services import InventoryService

    return InventoryService.default_warehouse(company)


def _on_hand(company, product, warehouse=None):
    from inventory.models import StockBalance

    qs = StockBalance.objects.filter(company=company, product=product)
    if warehouse is not None:
        qs = qs.filter(warehouse=warehouse)
    total = qs.aggregate(s=Sum("on_hand"))["s"]
    return total or Decimal("0")


def _reserved(company, product):
    from inventory.models import StockBalance

    total = StockBalance.objects.filter(company=company, product=product).aggregate(s=Sum("reserved"))["s"]
    return total or Decimal("0")


def _grn(company, user, product, *, received, accepted, rejected, price="40", batch_no="", serials=None):
    from purchases.models import GoodsReceipt, GoodsReceiptItem

    from masters.models import Supplier

    supplier = Supplier.objects.filter(company=company, gstin="29BBBBB0000B1Z5").first()
    if supplier is None:
        supplier = make_supplier(company, state="Karnataka", gstin="29BBBBB0000B1Z5")
    grn = GoodsReceipt.objects.create(
        company=company,
        supplier=supplier,
        warehouse=_wh(company),
        created_by=user,
        updated_by=user,
    )
    GoodsReceiptItem.objects.create(
        company=company,
        goods_receipt=grn,
        product=product,
        quantity_received=Decimal(received),
        quantity_accepted=Decimal(accepted),
        quantity_rejected=Decimal(rejected),
        unit_price=Decimal(price),
        batch_no=batch_no,
        serial_numbers=list(serials or []),
        created_by=user,
        updated_by=user,
    )
    return grn


def _order(tenant, product, qty):
    from sales.models import SalesOrder
    from sales.notes_services import SalesNotesService

    customer = make_customer(tenant.company, state="Karnataka")
    order = SalesOrder.objects.create(
        company=tenant.company,
        customer=customer,
        created_by=tenant.owner,
        updated_by=tenant.owner,
    )
    SalesNotesService.set_order_items(
        order,
        [{
            "product": product,
            "quantity": Decimal(qty),
            "unit_price": Decimal("100"),
            "gst_rate": Decimal("18"),
        }],
        tenant.owner,
    )
    SalesNotesService.confirm_sales_order(order, tenant.owner)
    return order


def test_bug_pur_012_accepted_plus_rejected_must_equal_received(tenant_a):
    from purchases.grn_service import GoodsReceiptService

    product = make_product(tenant_a.company, sku="PUR012")
    grn = _grn(tenant_a.company, tenant_a.owner, product, received="10", accepted="5", rejected="0")
    with pytest.raises(BusinessRuleError, match="must equal"):
        GoodsReceiptService.complete(grn, tenant_a.owner)
    assert _on_hand(tenant_a.company, product) == Decimal("0")


def test_bug_pur_008_batch_and_serial_on_grn(tenant_a):
    from inventory.models import SerialNumber, StockMovement
    from purchases.grn_service import GoodsReceiptService

    batched = make_product(tenant_a.company, sku="PUR008B", track_batch=True)
    missing = _grn(
        tenant_a.company, tenant_a.owner, batched, received="2", accepted="2", rejected="0",
    )
    with pytest.raises(BusinessRuleError, match="batch"):
        GoodsReceiptService.complete(missing, tenant_a.owner)

    grn = _grn(
        tenant_a.company, tenant_a.owner, batched, received="2", accepted="2", rejected="0",
        batch_no="LOT-8",
    )
    GoodsReceiptService.complete(grn, tenant_a.owner)
    move = StockMovement.objects.get(
        company=tenant_a.company, product=batched, reference_type="goods_receipt",
    )
    assert move.batch_id is not None
    assert move.batch.batch_no == "LOT-8"

    serial_product = make_product(tenant_a.company, sku="PUR008S", track_serial=True)
    serial_grn = _grn(
        tenant_a.company, tenant_a.owner, serial_product,
        received="1", accepted="1", rejected="0", serials=["SN-8"],
    )
    GoodsReceiptService.complete(serial_grn, tenant_a.owner)
    row = SerialNumber.objects.get(company=tenant_a.company, serial_number="SN-8")
    assert row.status == SerialNumber.Status.AVAILABLE
    assert row.product_id == serial_product.id


def test_bug_pur_006_cancel_refused_while_bill_exists(tenant_a):
    from purchases.grn_service import GoodsReceiptService
    from purchases.services import PurchaseService

    product = make_product(tenant_a.company, sku="PUR006")
    grn = _grn(tenant_a.company, tenant_a.owner, product, received="4", accepted="4", rejected="0")
    GoodsReceiptService.complete(grn, tenant_a.owner)
    bill = GoodsReceiptService.convert_to_bill(grn, tenant_a.owner)
    PurchaseService.complete(bill, tenant_a.owner)
    before = _on_hand(tenant_a.company, product)
    with pytest.raises(BusinessRuleError, match="purchase bill"):
        GoodsReceiptService.cancel(grn, tenant_a.owner)
    assert _on_hand(tenant_a.company, product) == before


def test_bug_pur_007_bill_cancel_unwinds_grn_stock_and_serials(tenant_a):
    from inventory.models import SerialNumber, StockMovement
    from purchases.grn_service import GoodsReceiptService
    from purchases.services import PurchaseService

    product = make_product(tenant_a.company, sku="PUR007", track_serial=True)
    grn = _grn(
        tenant_a.company, tenant_a.owner, product,
        received="1", accepted="1", rejected="0", serials=["SN-7"],
    )
    GoodsReceiptService.complete(grn, tenant_a.owner)
    assert _on_hand(tenant_a.company, product) == Decimal("1")
    bill = GoodsReceiptService.convert_to_bill(grn, tenant_a.owner)
    PurchaseService.complete(bill, tenant_a.owner)
    assert SerialNumber.objects.filter(company=tenant_a.company, serial_number="SN-7").exists()
    PurchaseService.cancel(bill, tenant_a.owner)
    assert _on_hand(tenant_a.company, product) == Decimal("0")
    assert not SerialNumber.objects.filter(company=tenant_a.company, serial_number="SN-7").exists()
    assert StockMovement.objects.filter(
        company=tenant_a.company, reference_type="goods_receipt_unwind", reference_id=str(grn.pk),
    ).exists()
    GoodsReceiptService.cancel(grn, tenant_a.owner)
    assert _on_hand(tenant_a.company, product) == Decimal("0")


def test_bug_pur_009_return_costs_from_goods_receipt_layer(tenant_a):
    from inventory.models import InventoryCostLayer, MovementType, StockMovement

    tenant_a.company.inventory_valuation_method = "FIFO"
    tenant_a.company.save(update_fields=["inventory_valuation_method"])
    from purchases.models import PurchaseReturn
    from purchases.grn_service import GoodsReceiptService
    from purchases.services import PurchaseService

    product = make_product(tenant_a.company, sku="PUR009")
    grn = _grn(
        tenant_a.company, tenant_a.owner, product,
        received="2", accepted="2", rejected="0", price="40",
    )
    GoodsReceiptService.complete(grn, tenant_a.owner)
    bill = GoodsReceiptService.convert_to_bill(grn, tenant_a.owner)
    PurchaseService.set_items(
        bill,
        [{
            "product": product,
            "quantity": Decimal("2"),
            "unit_price": Decimal("100"),
            "gst_rate": Decimal("18"),
        }],
        tenant_a.owner,
    )
    # The bill is deliberately priced above the receipt, which the 3-way match refuses
    # without an owner override. The point of this test is the return's cost source.
    PurchaseService.complete(bill, tenant_a.owner, confirm_three_way_override=True)
    purchase_return = PurchaseReturn.objects.create(
        company=tenant_a.company,
        supplier=bill.supplier,
        purchase_invoice=bill,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    PurchaseService.set_return_items(
        purchase_return,
        [{
            "product": product,
            "quantity": Decimal("2"),
            "unit_price": Decimal("100"),
            "gst_rate": Decimal("18"),
        }],
        tenant_a.owner,
    )
    PurchaseService.complete_return(purchase_return, tenant_a.owner)
    move = StockMovement.objects.get(
        company=tenant_a.company,
        product=product,
        movement_type=MovementType.PURCHASE_RETURN,
    )
    assert move.unit_cost == Decimal("40")
    layer = InventoryCostLayer.objects.get(
        company=tenant_a.company, product=product, source_movement__reference_type="goods_receipt",
    )
    assert layer.qty_remaining == Decimal("0")
    assert not InventoryCostLayer.objects.filter(
        company=tenant_a.company, product=product, unit_cost=Decimal("100"), qty_remaining__gt=0,
    ).exists()


def test_bug_inv_001_transfer_holds_stock_in_transit(tenant_a):
    from inventory.models import StockTransfer, StockTransferLine, Warehouse
    from inventory.services import InventoryService, StockTransferService

    product = make_product(tenant_a.company, sku="INV001")
    add_stock(tenant_a, product, "8")
    source = _wh(tenant_a.company)
    dest = Warehouse.objects.create(
        company=tenant_a.company, name="South", code="SOUTH",
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    transfer = StockTransfer.objects.create(
        company=tenant_a.company, from_warehouse=source, to_warehouse=dest,
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    StockTransferLine.objects.create(transfer=transfer, product=product, quantity="5")
    StockTransferService.dispatch(transfer, tenant_a.owner)
    transfer.refresh_from_db()
    transit = Warehouse.objects.get(company=tenant_a.company, code="IN_TRANSIT")
    assert transfer.status == StockTransfer.Status.DISPATCHED
    assert InventoryService.available_quantity(tenant_a.company, product, dest) == Decimal("0")
    assert _on_hand(tenant_a.company, product, transit) == Decimal("5")
    StockTransferService.receive(transfer, tenant_a.owner)
    assert _on_hand(tenant_a.company, product, dest) == Decimal("5")
    assert _on_hand(tenant_a.company, product, transit) == Decimal("0")


def test_bug_inv_010_transfer_uses_transfer_date(tenant_a):
    from inventory.models import MovementType, StockMovement, StockTransfer, StockTransferLine, Warehouse
    from inventory.services import StockTransferService

    product = make_product(tenant_a.company, sku="INV010")
    add_stock(tenant_a, product, "3")
    source = _wh(tenant_a.company)
    dest = Warehouse.objects.create(
        company=tenant_a.company, name="East", code="EAST",
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    biz = timezone.localdate() - timedelta(days=1)
    transfer = StockTransfer.objects.create(
        company=tenant_a.company, from_warehouse=source, to_warehouse=dest, transfer_date=biz,
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    StockTransferLine.objects.create(transfer=transfer, product=product, quantity="1")
    StockTransferService.dispatch(transfer, tenant_a.owner)
    StockTransferService.receive(transfer, tenant_a.owner)
    dates = set(
        StockMovement.objects.filter(
            company=tenant_a.company,
            product=product,
            movement_type__in=[MovementType.TRANSFER_OUT, MovementType.TRANSFER_IN],
        ).values_list("movement_date", flat=True)
    )
    # Dispatch is dated at the transfer date. Receipt happens later and is dated at the receipt,
    # so a receipt after a month closed is neither refused nor back-dated into the closed month.
    assert dates == {biz, timezone.localdate()}


def test_bug_inv_009_adjustment_posts_on_the_given_date(tenant_a):
    from inventory.models import MovementType, StockMovement

    product = make_product(tenant_a.company, sku="INV009")
    biz = timezone.localdate() - timedelta(days=1)
    res = tenant_a.client.post(
        "/api/v1/inventory/adjustments/",
        {"product": product.id, "quantity": "2", "reason": "count", "date": biz.isoformat()},
        format="json",
    )
    assert res.status_code == 201, res.data
    move = StockMovement.objects.get(
        company=tenant_a.company, product=product, movement_type=MovementType.ADJUSTMENT,
    )
    assert move.movement_date == biz


def test_bug_inv_002_expired_reservations_are_released(tenant_a):
    from inventory.models import StockReservation
    from inventory.services import InventoryService

    product = make_product(tenant_a.company, sku="INV002")
    add_stock(tenant_a, product, "10")
    warehouse = _wh(tenant_a.company)
    # expiry is opt-in per company
    tenant_a.company.feature_flags = {**(tenant_a.company.feature_flags or {}), "reservation_ttl_hours": 24}
    tenant_a.company.save(update_fields=["feature_flags"])
    InventoryService.reserve_stock(tenant_a.company, warehouse, product, Decimal("4"), user=tenant_a.owner)
    StockReservation.objects.filter(company=tenant_a.company, product=product).update(
        expires_at=timezone.now() - timedelta(hours=1),
    )
    released = InventoryService.release_expired_reservations(tenant_a.company)
    assert released == Decimal("4")
    assert _reserved(tenant_a.company, product) == Decimal("0")
    InventoryService.reserve_stock(tenant_a.company, warehouse, product, Decimal("2"), user=tenant_a.owner)
    InventoryService.release_expired_reservations(tenant_a.company)
    assert _reserved(tenant_a.company, product) == Decimal("2")
    entry = settings.CELERY_BEAT_SCHEDULE["inventory-release-expired-reservations"]
    assert entry["task"] == "inventory.tasks.release_expired_reservations_task"
    assert set(entry["schedule"].minute) == {0, 15, 30, 45}


def test_bug_sales_002_failed_stop_releases_stock_and_opens_return(tenant_a):
    from sales.models import DeliveryChallanReturn, DeliveryRoute, DeliveryRouteStop
    from sales.notes_services import SalesNotesService
    from sales.route_service import RouteService

    product = make_product(tenant_a.company, sku="SAL002")
    add_stock(tenant_a, product, "6")
    order = _order(tenant_a, product, "2")
    SalesNotesService.convert_sales_order_to_challan(order, tenant_a.owner)
    assert _reserved(tenant_a.company, product) == Decimal("2")
    route = DeliveryRoute.objects.create(
        company=tenant_a.company, created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    stop = DeliveryRouteStop.objects.create(
        company=tenant_a.company, route=route, sales_order=order, sequence=1,
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    RouteService.start_route(route, tenant_a.owner)
    RouteService.set_stop_status(route, stop, DeliveryRouteStop.StopStatus.FAILED, tenant_a.owner)
    assert _reserved(tenant_a.company, product) == Decimal("0")
    assert DeliveryChallanReturn.objects.filter(company=tenant_a.company, reason__startswith="Stop ").exists()

    product_b = make_product(tenant_a.company, sku="SAL002B")
    add_stock(tenant_a, product_b, "4")
    order_b = _order(tenant_a, product_b, "1")
    SalesNotesService.convert_sales_order_to_challan(order_b, tenant_a.owner)
    route_b = DeliveryRoute.objects.create(
        company=tenant_a.company, created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    stop_b = DeliveryRouteStop.objects.create(
        company=tenant_a.company, route=route_b, sales_order=order_b, sequence=1,
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    RouteService.start_route(route_b, tenant_a.owner)
    RouteService.set_stop_status(route_b, stop_b, DeliveryRouteStop.StopStatus.REJECTED, tenant_a.owner)
    assert _reserved(tenant_a.company, product_b) == Decimal("0")
    assert DeliveryChallanReturn.objects.filter(
        company=tenant_a.company, challan__sales_order=order_b,
    ).exists()


def test_bug_sales_001_partial_invoice_and_challan(tenant_a):
    from sales.models import SalesOrder
    from sales.notes_services import SalesNotesService

    product = make_product(tenant_a.company, sku="SAL001")
    add_stock(tenant_a, product, "100")
    order = _order(tenant_a, product, "100")
    line = order.items.get()
    first = SalesNotesService.convert_sales_order(
        order, tenant_a.owner, line_quantities={line.id: Decimal("40")},
    )
    order.refresh_from_db()
    line.refresh_from_db()
    assert first.items.get().quantity == Decimal("40")
    assert line.invoiced_quantity == Decimal("40")
    assert order.status == SalesOrder.Status.PARTIALLY_CONVERTED
    second = SalesNotesService.convert_sales_order(
        order, tenant_a.owner, line_quantities={line.id: Decimal("60")},
    )
    line.refresh_from_db()
    assert second.items.get().quantity == Decimal("60")
    assert line.invoiced_quantity == Decimal("100")
    with pytest.raises(BusinessRuleError):
        SalesNotesService.convert_sales_order(
            order, tenant_a.owner, line_quantities={line.id: Decimal("1")},
        )

    product_c = make_product(tenant_a.company, sku="SAL001C")
    add_stock(tenant_a, product_c, "10")
    challan_order = _order(tenant_a, product_c, "10")
    challan_line = challan_order.items.get()
    draft = SalesNotesService.convert_sales_order_to_challan(
        challan_order, tenant_a.owner, line_quantities={challan_line.id: Decimal("4")},
    )
    challan_line.refresh_from_db()
    assert challan_line.shipped_quantity == Decimal("4")
    with pytest.raises(BusinessRuleError):
        SalesNotesService.convert_sales_order_to_challan(
            challan_order, tenant_a.owner, line_quantities={challan_line.id: Decimal("6")},
        )
    SalesNotesService.complete_challan(draft, tenant_a.owner)
    rest = SalesNotesService.convert_sales_order_to_challan(
        challan_order, tenant_a.owner, line_quantities={challan_line.id: Decimal("6")},
    )
    assert rest.items.get().quantity == Decimal("6")
    challan_line.refresh_from_db()
    assert challan_line.shipped_quantity == Decimal("10")


def test_bug_sales_011_pos_checkout_accepts_blank_state_confirm(tenant_a):
    product = make_product(tenant_a.company, sku="SAL011")
    add_stock(tenant_a, product, "5")
    tenant_a.company.assume_local_state_for_blank_party = False
    tenant_a.company.save(update_fields=["assume_local_state_for_blank_party"])
    customer = make_customer(tenant_a.company, name="Blank State", state="", gstin="")
    invoice = {
        "customer": customer.id,
        "invoice_type": "GST",
        "invoice_date": timezone.localdate().isoformat(),
        "items": [{
            "product": product.id,
            "quantity": "1",
            "unit_price": "100.00",
            "gst_rate": "18",
        }],
    }
    payment = {"mode": "CASH", "amount": "118.00"}
    blocked = tenant_a.client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {"invoice": invoice, "payment": payment},
        format="json",
    )
    assert blocked.status_code >= 400
    body = str(blocked.data).lower()
    assert "place of supply" in body or "confirm" in body
    done = tenant_a.client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {"invoice": invoice, "payment": payment, "confirm_blank_pos": True},
        format="json",
    )
    assert done.status_code == 201, done.data
    assert done.data["invoice"]["status"] == "COMPLETED"


def test_bug_inv_004_fefo_is_mandatory_unless_owner_overrides(tenant_a):
    from datetime import timedelta as _td

    from inventory.item_stock import get_or_create_batch
    from inventory.models import MovementType
    from inventory.services import InventoryService
    from sales.models import SalesInvoice
    from sales.services import SalesService

    product = make_product(
        tenant_a.company, sku="INV004", track_batch=True, regulated_category="DRUG",
    )
    warehouse = _wh(tenant_a.company)
    today = timezone.localdate()
    early = get_or_create_batch(
        company=tenant_a.company, product=product, batch_no="EARLY",
        expiry_date=today + _td(days=15), user=tenant_a.owner,
    )
    late = get_or_create_batch(
        company=tenant_a.company, product=product, batch_no="LATE",
        expiry_date=today + _td(days=120), user=tenant_a.owner,
    )
    for lot in (early, late):
        InventoryService.post_movement(
            company=tenant_a.company, warehouse=warehouse, product=product, batch=lot,
            movement_type=MovementType.OPENING_STOCK, quantity=Decimal("5"),
            unit_cost=Decimal("10"), user=tenant_a.owner,
        )
    customer = make_customer(tenant_a.company, state="Karnataka")
    invoice = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, warehouse=warehouse,
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    SalesService.set_items(
        invoice,
        [{
            "product": product,
            "quantity": Decimal("1"),
            "unit_price": Decimal("100"),
            "gst_rate": Decimal("18"),
            "batch": late,
            "batch_no": late.batch_no,
        }],
        tenant_a.owner,
    )
    with pytest.raises(BusinessRuleError, match="earliest"):
        SalesService.complete(
            invoice, tenant_a.staff, confirm_missing_licence=True, fefo_override=True,
        )
    SalesService.complete(
        invoice, tenant_a.owner, confirm_missing_licence=True, fefo_override=True,
    )
    invoice.refresh_from_db()
    assert invoice.status == SalesInvoice.Status.COMPLETED


def test_bug_inv_008_owner_can_store_shopify_connection(tenant_a):
    warehouse = _wh(tenant_a.company)
    customer = make_customer(tenant_a.company)
    payload = {
        "shop_domain": "alpha.myshopify.com",
        "webhook_secret": "shhh-secret-value",
        "warehouse_id": warehouse.id,
        "customer_id": customer.id,
    }
    denied = tenant_a.staff_client.put(
        "/api/v1/integrations/shopify/connection/", payload, format="json",
    )
    assert denied.status_code == 403
    saved = tenant_a.client.put(
        "/api/v1/integrations/shopify/connection/", payload, format="json",
    )
    assert saved.status_code == 200, saved.data
    assert saved.data["shop_domain"] == "alpha.myshopify.com"
    assert saved.data["warehouse_id"] == warehouse.id
    assert saved.data["customer_id"] == customer.id
    assert "shhh-secret-value" not in str(saved.data)
    shown = tenant_a.client.get("/api/v1/integrations/shopify/connection/")
    assert shown.status_code == 200
    assert "shhh-secret-value" not in str(shown.data)
    assert shown.data["warehouse_id"] == warehouse.id


def test_bug_inv_007_pending_shopify_stock_applies_inside_the_hold(tenant_a):
    from integrations.models import IntegrationConnection
    from integrations.shopify import _sync_stock
    from inventory.services import InventoryService

    product = make_product(tenant_a.company, sku="SHOP7")
    add_stock(tenant_a, product, "10")
    warehouse = _wh(tenant_a.company)
    customer = make_customer(tenant_a.company)
    saved = tenant_a.client.put(
        "/api/v1/integrations/shopify/connection/",
        {
            "shop_domain": "hold.myshopify.com",
            "webhook_secret": "another-secret",
            "warehouse_id": warehouse.id,
            "customer_id": customer.id,
        },
        format="json",
    )
    assert saved.status_code == 200, saved.data
    conn = IntegrationConnection.objects.get(
        company=tenant_a.company, provider=IntegrationConnection.Provider.SHOPIFY,
    )
    held = _sync_stock(conn, {
        "sku": "SHOP7",
        "inventory_item_id": "gid-7",
        "available": "100",
        "updated_at": "2026-10-04T10:00:00+00:00",
    })
    assert held["status"] == "held"
    assert InventoryService.available_quantity(tenant_a.company, product, warehouse) == Decimal("10")
    listing = tenant_a.client.get("/api/v1/integrations/inventory/")
    assert listing.status_code == 200
    assert listing.data["shopify_pending_count"] == 1
    applied = tenant_a.client.post("/api/v1/integrations/shopify/pending/gid-7/apply/")
    assert applied.status_code == 200, applied.data
    assert InventoryService.available_quantity(tenant_a.company, product, warehouse) == Decimal("100")
    conn.refresh_from_db()
    still = _sync_stock(conn, {
        "sku": "SHOP7",
        "inventory_item_id": "gid-8",
        "available": "400",
        "updated_at": "2026-10-04T11:00:00+00:00",
    })
    assert still["status"] == "held"
    assert InventoryService.available_quantity(tenant_a.company, product, warehouse) == Decimal("100")
    missing = tenant_a.client.post("/api/v1/integrations/shopify/pending/missing-key/apply/")
    assert missing.status_code >= 400


def test_bug_wrk_002_job_line_reserves_and_cancel_releases(tenant_a):
    from workshop.services import add_line, cancel_job, create_job

    product = make_product(tenant_a.company, sku="WRK002")
    add_stock(tenant_a, product, "6")
    customer = make_customer(tenant_a.company)
    job = create_job(tenant_a.company, tenant_a.owner, customer=customer, complaint="Noise")
    add_line(
        job, tenant_a.owner, kind="PART", product=product,
        quantity=Decimal("2"), unit_price=Decimal("50"),
    )
    assert _reserved(tenant_a.company, product) == Decimal("2")
    cancel_job(job, tenant_a.owner)
    assert _reserved(tenant_a.company, product) == Decimal("0")


def test_bug_wrk_001_invoice_copies_batch_and_rejects_expired(tenant_a):
    from inventory.item_stock import get_or_create_batch
    from inventory.models import MovementType
    from inventory.services import InventoryService
    from workshop.services import add_line, convert_to_invoice, create_job

    product = make_product(tenant_a.company, sku="WRK001", track_batch=True)
    warehouse = _wh(tenant_a.company)
    fresh = get_or_create_batch(
        company=tenant_a.company, product=product, batch_no="FRESH",
        expiry_date=timezone.localdate() + timedelta(days=30), user=tenant_a.owner,
    )
    expired = get_or_create_batch(
        company=tenant_a.company, product=product, batch_no="OLD",
        expiry_date=timezone.localdate() - timedelta(days=2), user=tenant_a.owner,
    )
    for lot in (fresh, expired):
        InventoryService.post_movement(
            company=tenant_a.company, warehouse=warehouse, product=product, batch=lot,
            movement_type=MovementType.OPENING_STOCK, quantity=Decimal("3"),
            unit_cost=Decimal("10"), user=tenant_a.owner,
        )
    customer = make_customer(tenant_a.company)
    open_job = create_job(tenant_a.company, tenant_a.owner, customer=customer, complaint="Batch")
    add_line(
        open_job, tenant_a.owner, kind="PART", product=product,
        quantity=Decimal("1"), unit_price=Decimal("80"),
    )
    with pytest.raises(BusinessRuleError, match="batch"):
        convert_to_invoice(open_job, tenant_a.owner)

    good = create_job(tenant_a.company, tenant_a.owner, customer=customer, complaint="Fresh")
    add_line(
        good, tenant_a.owner, kind="PART", product=product,
        quantity=Decimal("1"), unit_price=Decimal("80"), batch=fresh,
    )
    invoice = convert_to_invoice(good, tenant_a.owner)
    assert invoice.items.get().batch_no == "FRESH"

    stale = create_job(tenant_a.company, tenant_a.owner, customer=customer, complaint="Old")
    add_line(
        stale, tenant_a.owner, kind="PART", product=product,
        quantity=Decimal("1"), unit_price=Decimal("80"), batch=expired,
    )
    with pytest.raises(BusinessRuleError, match="expired"):
        convert_to_invoice(stale, tenant_a.owner)


def test_bug_prj_001_milestone_stays_open_until_invoice_completes(tenant_a):
    from projects.models import Project, ProjectMilestone
    from projects.services import invoice_milestone
    from sales.models import SalesInvoice
    from sales.services import SalesService

    customer = make_customer(tenant_a.company, state="Karnataka")
    product = make_product(
        tenant_a.company, sku="PRJ001", product_type="SERVICE", track_inventory=False,
    )
    project = Project.objects.create(
        company=tenant_a.company, customer=customer, name="Fit-out",
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    milestone = ProjectMilestone.objects.create(
        company=tenant_a.company, project=project, name="Phase 1",
        amount=Decimal("1000.00"), service_product=product,
        status=ProjectMilestone.Status.READY,
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    draft = invoice_milestone(milestone, tenant_a.owner)
    milestone.refresh_from_db()
    assert draft.status == SalesInvoice.Status.DRAFT
    assert milestone.status != ProjectMilestone.Status.INVOICED
    SalesService.complete(draft, tenant_a.owner)
    invoice_milestone(milestone, tenant_a.owner)
    milestone.refresh_from_db()
    assert milestone.status == ProjectMilestone.Status.INVOICED


def test_bug_ins_001_second_in_force_policy_is_refused(tenant_a):
    from crm.models import Lead
    from insurance.models import Policy, PolicyProduct
    from insurance.services import choose_option, create_option_set, issue_policy

    customer = make_customer(tenant_a.company)
    lead = Lead.objects.create(
        company=tenant_a.company, name="Prospect",
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    first = PolicyProduct.objects.create(
        company=tenant_a.company, name="Motor A", insurer_name="CoverCo", line="MOTOR",
        tenure_months=12, sum_insured=Decimal("100000"), premium=Decimal("5000"),
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    second = PolicyProduct.objects.create(
        company=tenant_a.company, name="Motor B", insurer_name="CoverCo", line="MOTOR",
        tenure_months=12, sum_insured=Decimal("80000"), premium=Decimal("4200"),
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    option_set = create_option_set(
        tenant_a.company, tenant_a.owner, lead=lead, product_ids=[first.pk, second.pk],
    )
    option_a = option_set.options.get(product=first)
    option_b = option_set.options.get(product=second)
    choose_option(option_a, tenant_a.owner)
    issue_policy(
        tenant_a.company, tenant_a.owner, option=option_a, customer=customer,
        nominee="N", start_date=timezone.localdate(),
    )
    choose_option(option_b, tenant_a.owner)
    with pytest.raises(BusinessRuleError, match="in-force"):
        issue_policy(
            tenant_a.company, tenant_a.owner, option=option_b, customer=customer,
            nominee="N", start_date=timezone.localdate(),
        )
    assert Policy.objects.filter(company=tenant_a.company).count() == 1
