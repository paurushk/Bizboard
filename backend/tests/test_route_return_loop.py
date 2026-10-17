"""R6 (OG-30..34, RT-07; DEC-O3): goods that come back reopen the order.

A failed or refused delivery opens a draft return for the godown to check the goods in. Completing it
restocks them, puts the order back to ready, and holds stock for it again, so the order can go out a
second time without overselling. Only what actually came back is returned (a partial refusal), and
returned goods are never billed or restocked twice.
"""

from decimal import Decimal

import pytest

from core.exceptions import BusinessRuleError
from inventory.models import MovementType, StockBalance, StockMovement
from sales.challan_return import ChallanReturnService
from sales.models import (
    DeliveryChallan,
    DeliveryChallanReturn,
    DeliveryRoute,
    DeliveryRouteStop,
    SalesOrder,
)
from sales.notes_services import SalesNotesService
from sales.order_quantities import order_remaining, order_still_held, shipped_by_product
from sales.route_service import RouteService
from tests.conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db


def _order(tenant, product, qty):
    customer = make_customer(tenant.company, name=f"Cust {SalesOrder.objects.count()}")
    resp = tenant.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id, "invoice_type": "NON_GST",
            "items": [{"product": product.id, "quantity": str(qty), "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )
    order = SalesOrder.objects.get(pk=resp.data["id"])
    SalesNotesService.confirm_sales_order(order, tenant.owner)
    order.refresh_from_db()
    return order


def _reserved(tenant, product):
    return StockBalance.objects.get(company=tenant.company, product=product).reserved


def _on_hand(tenant, product):
    return StockBalance.objects.get(company=tenant.company, product=product).on_hand


@pytest.fixture
def setup(tenant_a):
    """Stock posts on challan, so a return really puts goods back."""
    tenant_a.company.stock_on_delivery_challan = True
    tenant_a.company.save(update_fields=["stock_on_delivery_challan"])
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "100")
    order = _order(tenant_a, product, 10)
    other = _order(tenant_a, product, 5)
    return product, order, other


def _shipped(tenant, order, qty=10):
    line = order.items.get()
    challan = SalesNotesService.convert_sales_order_to_challan(
        order, tenant.owner, line_quantities={line.pk: Decimal(str(qty))}
    )
    return SalesNotesService.complete_challan(challan, tenant.owner)


def _stop(tenant, order, status="IN_TRANSIT"):
    route = DeliveryRoute.objects.create(
        company=tenant.company, route_date="2026-10-14", number="RT-9", status=status,
    )
    return route, DeliveryRouteStop.objects.create(company=tenant.company, route=route, sales_order=order)


def _fail(tenant, order, outcome="FAILED", **extra):
    route, stop = _stop(tenant, order)
    RouteService.set_stop_status(route, stop, outcome, tenant.owner, **extra)
    return route, stop


# ---------------------------------------------------------------------------
# OG-31 — the godown's queue
# ---------------------------------------------------------------------------


def test_tc_og31_01_a_failed_stop_opens_one_draft_return_the_godown_can_find(tenant_a, setup):
    _product, order, _other = setup
    _shipped(tenant_a, order)
    _fail(tenant_a, order)
    returns = DeliveryChallanReturn.objects.filter(company=tenant_a.company)
    assert returns.count() == 1
    ret = returns.get()
    assert ret.status == DeliveryChallanReturn.Status.DRAFT
    assert ret.reason.startswith("Stop FAILED on route RT-9")
    resp = tenant_a.client.get("/api/v1/sales/challan-returns/?status=DRAFT&from_route=true")
    assert resp.status_code == 200, resp.data
    rows = resp.data["results"] if isinstance(resp.data, dict) else resp.data
    assert [r["id"] for r in rows] == [ret.id]


def test_tc_og31_02_the_queue_leaves_out_returns_not_from_a_route_and_completed_ones(tenant_a, setup):
    _product, order, _other = setup
    challan = _shipped(tenant_a, order)
    manual = DeliveryChallanReturn.objects.create(
        company=tenant_a.company, customer=order.customer, challan=challan, reason="Customer changed mind",
        created_by=tenant_a.owner,
    )
    resp = tenant_a.client.get("/api/v1/sales/challan-returns/?status=DRAFT&from_route=true")
    rows = resp.data["results"] if isinstance(resp.data, dict) else resp.data
    assert manual.id not in [r["id"] for r in rows]
    assert tenant_a.client.get("/api/v1/sales/challan-returns/?status=NOPE").status_code == 400


# ---------------------------------------------------------------------------
# OG-32 — only what came back
# ---------------------------------------------------------------------------


def test_tc_og32_01_a_partial_refusal_returns_only_that_quantity(tenant_a, setup):
    product, order, _other = setup
    _shipped(tenant_a, order)
    _fail(tenant_a, order, "REJECTED", returned_lines=[{"product": product.id, "quantity": 3}])
    ret = DeliveryChallanReturn.objects.get(company=tenant_a.company)
    assert [(i.product_id, i.quantity) for i in ret.items.all()] == [(product.id, Decimal("3"))]


def test_tc_og32_02_more_than_went_out_is_refused_and_nothing_is_left_half_done(tenant_a, setup):
    product, order, _other = setup
    _shipped(tenant_a, order)
    route, stop = _stop(tenant_a, order)
    with pytest.raises(BusinessRuleError, match="More was marked as returned"):
        RouteService.set_stop_status(
            route, stop, "FAILED", tenant_a.owner, returned_lines=[{"product": product.id, "quantity": 11}]
        )
    stop.refresh_from_db()
    assert stop.status == "PENDING" and stop.stock_released_at is None
    assert DeliveryChallanReturn.objects.filter(company=tenant_a.company).count() == 0


def test_tc_og32_03_a_delivered_stop_can_still_send_part_of_it_back(tenant_a, setup):
    product, order, _other = setup
    _shipped(tenant_a, order)
    route, stop = _stop(tenant_a, order)
    RouteService.set_stop_status(
        route, stop, "DELIVERED", tenant_a.owner, received_by_name="Asha", completion_source="OFFICE",
        returned_lines=[{"product": product.id, "quantity": 2}],
    )
    stop.refresh_from_db()
    assert stop.status == "DELIVERED"
    ret = DeliveryChallanReturn.objects.get(company=tenant_a.company)
    assert [(i.product_id, i.quantity) for i in ret.items.all()] == [(product.id, Decimal("2"))]


def test_tc_og32_04_a_negative_or_malformed_line_is_refused(tenant_a, setup):
    product, order, _other = setup
    _shipped(tenant_a, order)
    route, stop = _stop(tenant_a, order)
    for bad in ([{"product": product.id, "quantity": -1}], ["x"], [{"quantity": 1}]):
        with pytest.raises(BusinessRuleError):
            RouteService.set_stop_status(route, stop, "FAILED", tenant_a.owner, returned_lines=bad)


def test_tc_og32_05_the_stop_lists_what_can_come_back(tenant_a, setup):
    product, order, _other = setup
    _shipped(tenant_a, order)
    route, stop = _stop(tenant_a, order)
    resp = tenant_a.client.get(f"/api/v1/sales/delivery-routes/{route.id}/")
    assert resp.status_code == 200, resp.data
    lines = resp.data["stops"][0]["returnable_lines"]
    assert lines == [{"product": product.id, "product_name": product.name, "quantity": "10.000"}]


# ---------------------------------------------------------------------------
# OG-33 — completing the return reopens the order
# ---------------------------------------------------------------------------


def test_tc_og33_01_completing_the_return_restocks_reopens_and_holds_stock_again(tenant_a, setup):
    product, order, _other = setup
    _shipped(tenant_a, order)
    assert _on_hand(tenant_a, product) == Decimal("90") and _reserved(tenant_a, product) == Decimal("5")
    _fail(tenant_a, order)

    ret = DeliveryChallanReturn.objects.get(company=tenant_a.company)
    ChallanReturnService.complete(ret, tenant_a.owner)

    assert _on_hand(tenant_a, product) == Decimal("100")  # the goods are back on the shelf
    assert _reserved(tenant_a, product) == Decimal("15")  # held for the order again, plus the other's 5
    order.refresh_from_db()
    assert order.status == SalesOrder.Status.CONFIRMED
    assert order.items.get().shipped_quantity == Decimal("0")
    assert order_still_held(order) == {product.id: Decimal("10")}
    assert order_remaining(order) == {product.id: Decimal("10")}


def test_tc_og33_02_the_reopened_order_can_go_out_again_and_deliver_once(tenant_a, setup):
    product, order, _other = setup
    _shipped(tenant_a, order)
    _fail(tenant_a, order)
    ChallanReturnService.complete(DeliveryChallanReturn.objects.get(company=tenant_a.company), tenant_a.owner)
    order.refresh_from_db()

    second = SalesNotesService.complete_challan(
        SalesNotesService.convert_sales_order_to_challan(order, tenant_a.owner), tenant_a.owner
    )
    order.refresh_from_db()
    assert second.status == DeliveryChallan.Status.COMPLETED
    assert order.status == SalesOrder.Status.CONVERTED
    assert _on_hand(tenant_a, product) == Decimal("90")  # out once, not twice
    assert _reserved(tenant_a, product) == Decimal("5")  # only the other order's hold remains
    sales = StockMovement.objects.filter(
        company=tenant_a.company, product=product, movement_type=MovementType.SALE
    )
    restores = StockMovement.objects.filter(
        company=tenant_a.company, product=product, movement_type=MovementType.SALES_RETURN,
        reference_type="DeliveryChallanReturn",
    )
    assert sum(abs(m.quantity) for m in sales) - sum(abs(m.quantity) for m in restores) == Decimal("10")


def test_tc_og33_03_without_stock_posting_on_challan_the_order_still_reopens(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "100")
    order = _order(tenant_a, product, 10)
    _order(tenant_a, product, 5)
    _shipped(tenant_a, order)  # stock_on_delivery_challan is off: nothing left stock
    _fail(tenant_a, order)
    ChallanReturnService.complete(DeliveryChallanReturn.objects.get(company=tenant_a.company), tenant_a.owner)
    order.refresh_from_db()
    assert _on_hand(tenant_a, product) == Decimal("100")
    assert order.status == SalesOrder.Status.CONFIRMED
    assert _reserved(tenant_a, product) == Decimal("15")


def test_tc_og33_04_completing_the_same_return_twice_restocks_once(tenant_a, setup):
    product, order, _other = setup
    _shipped(tenant_a, order)
    _fail(tenant_a, order)
    ret = DeliveryChallanReturn.objects.get(company=tenant_a.company)
    ChallanReturnService.complete(ret, tenant_a.owner)
    with pytest.raises(BusinessRuleError):
        ChallanReturnService.complete(ret, tenant_a.owner)
    assert _on_hand(tenant_a, product) == Decimal("100")


def test_tc_og33_05_the_other_orders_hold_is_untouched_throughout(tenant_a, setup):
    product, order, other = setup
    _shipped(tenant_a, order)
    _fail(tenant_a, order)
    ChallanReturnService.complete(DeliveryChallanReturn.objects.get(company=tenant_a.company), tenant_a.owner)
    other.refresh_from_db()
    assert other.status == SalesOrder.Status.CONFIRMED
    assert order_still_held(other) == {product.id: Decimal("5")}


def test_tc_og33_06_a_partial_return_leaves_the_rest_shipped(tenant_a, setup):
    product, order, _other = setup
    _shipped(tenant_a, order)
    _fail(tenant_a, order, "REJECTED", returned_lines=[{"product": product.id, "quantity": 4}])
    ChallanReturnService.complete(DeliveryChallanReturn.objects.get(company=tenant_a.company), tenant_a.owner)
    order.refresh_from_db()
    assert shipped_by_product(order) == {product.id: Decimal("6")}
    assert order.status == SalesOrder.Status.PARTIALLY_CONVERTED
    assert _on_hand(tenant_a, product) == Decimal("94")
    assert order_still_held(order) == {product.id: Decimal("4")}


def test_tc_og33_07_a_draft_order_that_never_held_stock_is_not_given_a_reservation(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "100")
    customer = make_customer(tenant_a.company, name="Draft Co")
    resp = tenant_a.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id, "invoice_type": "NON_GST",
            "items": [{"product": product.id, "quantity": "4", "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )
    order = SalesOrder.objects.get(pk=resp.data["id"])
    challan = SalesNotesService.complete_challan(
        SalesNotesService.convert_sales_order_to_challan(order, tenant_a.owner), tenant_a.owner
    )
    ret = DeliveryChallanReturn.objects.create(
        company=tenant_a.company, customer=customer, challan=challan, reason="Stop FAILED manual", created_by=tenant_a.owner,
    )
    ChallanReturnService.set_items(
        ret, [{"product": product, "quantity": Decimal("4"), "unit_price": Decimal("100"), "gst_rate": Decimal("0")}],
        tenant_a.owner,
    )
    ChallanReturnService.complete(ret, tenant_a.owner)
    order.refresh_from_db()
    assert order.stock_held is False
    assert order.status == SalesOrder.Status.DRAFT
    assert _reserved(tenant_a, product) == Decimal("0")


# ---------------------------------------------------------------------------
# returned goods are never billed or restocked a second time
# ---------------------------------------------------------------------------


def test_tc_og33_08_a_challan_with_goods_back_cannot_be_cancelled(tenant_a, setup):
    _product, order, _other = setup
    challan = _shipped(tenant_a, order)
    _fail(tenant_a, order)
    ChallanReturnService.complete(DeliveryChallanReturn.objects.get(company=tenant_a.company), tenant_a.owner)
    with pytest.raises(BusinessRuleError, match="already come back"):
        SalesNotesService.cancel_challan(challan, tenant_a.owner)


def test_tc_og33_09_invoicing_a_challan_bills_only_what_stayed(tenant_a, setup):
    product, order, _other = setup
    challan = _shipped(tenant_a, order)
    _fail(tenant_a, order, "REJECTED", returned_lines=[{"product": product.id, "quantity": 4}])
    ChallanReturnService.complete(DeliveryChallanReturn.objects.get(company=tenant_a.company), tenant_a.owner)
    invoice = SalesNotesService.convert_delivery_challan(challan, tenant_a.owner)
    assert invoice.items.get().quantity == Decimal("6")
    assert invoice.grand_total == Decimal("600.00")


def test_tc_og33_10_a_challan_where_everything_came_back_has_nothing_to_invoice(tenant_a, setup):
    _product, order, _other = setup
    challan = _shipped(tenant_a, order)
    _fail(tenant_a, order)
    ChallanReturnService.complete(DeliveryChallanReturn.objects.get(company=tenant_a.company), tenant_a.owner)
    with pytest.raises(BusinessRuleError, match="nothing to invoice"):
        SalesNotesService.convert_delivery_challan(challan, tenant_a.owner)


# ---------------------------------------------------------------------------
# OG-34 / OG-30 — an invoiced order, and delivered-not-invoiced
# ---------------------------------------------------------------------------


def test_tc_og34_01_an_invoiced_challan_opens_no_return_and_the_stop_names_the_invoice(tenant_a, setup):
    from sales.services import SalesService

    _product, order, _other = setup
    challan = _shipped(tenant_a, order)
    invoice = SalesNotesService.convert_delivery_challan(challan, tenant_a.owner)
    SalesService.complete(invoice, tenant_a.owner)
    invoice.refresh_from_db()
    order.refresh_from_db()
    route, stop = _stop(tenant_a, order)
    resp = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/set-stop-status/",
        {"stop_id": stop.id, "status": "FAILED"}, format="json",
    )
    assert resp.status_code == 200, resp.data
    assert DeliveryChallanReturn.objects.filter(company=tenant_a.company).count() == 0
    assert resp.data["stops"][0]["active_invoice"]["number"] == invoice.number


def test_tc_og30_01_a_delivered_stop_with_no_invoice_says_so(tenant_a, setup):
    _product, order, _other = setup
    _shipped(tenant_a, order)
    route, stop = _stop(tenant_a, order)
    RouteService.set_stop_status(
        route, stop, "DELIVERED", tenant_a.owner, received_by_name="Asha", completion_source="OFFICE"
    )
    resp = tenant_a.client.get(f"/api/v1/sales/delivery-routes/{route.id}/")
    assert resp.data["stops"][0]["bill"]["bill_status"] == "challan"
