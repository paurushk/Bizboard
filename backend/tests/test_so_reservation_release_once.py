"""R1 (H-01, H-02): a sales order's stock reservation is given back exactly once.

Reservations are shared per product (StockBalance.reserved) and carry no order reference, so a
second release for the same units quietly frees stock another order is holding. Every case here
builds a second order (B) on the same product and asserts B's hold is never touched.
"""

from decimal import Decimal

import pytest

from inventory.models import StockBalance
from sales.models import (
    DeliveryChallan,
    DeliveryChallanReturn,
    DeliveryRoute,
    DeliveryRouteStop,
    SalesInvoice,
    SalesOrder,
)
from sales.notes_services import SalesNotesService
from sales.order_quantities import order_still_held
from sales.route_service import RouteService
from sales.services import SalesService
from tests.conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db


def _order(tenant, product, qty, customer=None):
    customer = customer or make_customer(tenant.company, name=f"Cust {qty}-{SalesOrder.objects.count()}")
    resp = tenant.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id,
            "invoice_type": "NON_GST",
            "items": [{"product": product.id, "quantity": str(qty), "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    return SalesOrder.objects.get(pk=resp.data["id"])


def _confirmed(tenant, product, qty):
    order = _order(tenant, product, qty)
    SalesNotesService.confirm_sales_order(order, tenant.owner)
    order.refresh_from_db()
    return order


def _reserved(tenant, product):
    return StockBalance.objects.get(company=tenant.company, product=product).reserved


def _ship(order, tenant, qty):
    """Draft challan for ``qty`` of the order's only line, completed."""
    line = order.items.get()
    challan = SalesNotesService.convert_sales_order_to_challan(
        order, tenant.owner, line_quantities={line.pk: Decimal(str(qty))}
    )
    return SalesNotesService.complete_challan(challan, tenant.owner)


def _setup(tenant, a_qty=10, b_qty=5, stock="40"):
    product = make_product(tenant.company)
    add_stock(tenant, product, stock)
    order_a = _confirmed(tenant, product, a_qty)
    order_b = _confirmed(tenant, product, b_qty)
    assert _reserved(tenant, product) == Decimal(a_qty + b_qty)
    return product, order_a, order_b


# ---------------------------------------------------------------------------
# H-01 — challan complete, then the invoice made from it
# ---------------------------------------------------------------------------


def test_tc_wp1_01_partial_challan_invoice_does_not_release_twice(tenant_a):
    product, order_a, _order_b = _setup(tenant_a)
    challan = _ship(order_a, tenant_a, 4)
    # The challan gave back its 4 when it completed.
    assert _reserved(tenant_a, product) == Decimal("11")

    invoice = SalesNotesService.convert_delivery_challan(challan, tenant_a.owner)
    SalesService.complete(invoice, tenant_a.owner)

    # A's unshipped 6 plus B's 5. The pre-fix code released 4 again here (7).
    assert _reserved(tenant_a, product) == Decimal("11")
    order_a.refresh_from_db()
    assert order_a.status == SalesOrder.Status.PARTIALLY_CONVERTED


def test_tc_wp1_03_direct_order_invoice_releases_exactly_once(tenant_a):
    product, order_a, _order_b = _setup(tenant_a)
    invoice = SalesNotesService.convert_sales_order(order_a, tenant_a.owner)
    # The draft invoice still holds A's reservation until it completes.
    assert _reserved(tenant_a, product) == Decimal("15")
    SalesService.complete(invoice, tenant_a.owner)
    assert _reserved(tenant_a, product) == Decimal("5")


def test_tc_wp1_03b_partial_direct_invoice_releases_only_its_own_quantity(tenant_a):
    product, order_a, _order_b = _setup(tenant_a)
    line = order_a.items.get()
    invoice = SalesNotesService.convert_sales_order(
        order_a, tenant_a.owner, line_quantities={line.pk: Decimal("4")}
    )
    SalesService.complete(invoice, tenant_a.owner)
    assert _reserved(tenant_a, product) == Decimal("11")


def test_tc_wp1_04_full_challan_then_invoice_leaves_the_other_order_alone(tenant_a):
    product, order_a, _order_b = _setup(tenant_a)
    challan = _ship(order_a, tenant_a, 10)
    assert _reserved(tenant_a, product) == Decimal("5")
    invoice = SalesNotesService.convert_delivery_challan(challan, tenant_a.owner)
    SalesService.complete(invoice, tenant_a.owner)
    assert _reserved(tenant_a, product) == Decimal("5")
    order_a.refresh_from_db()
    assert order_a.status == SalesOrder.Status.CONVERTED


def test_tc_wp1_05_challan_from_a_draft_order_never_touches_other_holds(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "40")
    order_b = _confirmed(tenant_a, product, 5)
    draft = _order(tenant_a, product, 10)  # never confirmed: holds nothing
    assert _reserved(tenant_a, product) == Decimal("5")
    challan = _ship(draft, tenant_a, 10)
    invoice = SalesNotesService.convert_delivery_challan(challan, tenant_a.owner)
    SalesService.complete(invoice, tenant_a.owner)
    assert _reserved(tenant_a, product) == Decimal("5")
    order_b.refresh_from_db()
    assert order_b.status == SalesOrder.Status.CONFIRMED


# ---------------------------------------------------------------------------
# order_still_held — the one definition of "reserved for this order"
# ---------------------------------------------------------------------------


def test_tc_wp1_06_held_counts_completed_documents_only(tenant_a):
    product, order_a, _order_b = _setup(tenant_a)
    assert order_still_held(order_a) == {product.id: Decimal("10")}

    line = order_a.items.get()
    challan = SalesNotesService.convert_sales_order_to_challan(
        order_a, tenant_a.owner, line_quantities={line.pk: Decimal("4")}
    )
    # A draft challan has not left the godown: it still holds its 4.
    assert order_still_held(order_a) == {product.id: Decimal("10")}
    SalesNotesService.complete_challan(challan, tenant_a.owner)
    order_a.refresh_from_db()
    assert order_still_held(order_a) == {product.id: Decimal("6")}


def test_tc_wp1_07_held_after_a_direct_invoice_completes(tenant_a):
    product, order_a, _order_b = _setup(tenant_a)
    line = order_a.items.get()
    invoice = SalesNotesService.convert_sales_order(
        order_a, tenant_a.owner, line_quantities={line.pk: Decimal("3")}
    )
    assert order_still_held(order_a) == {product.id: Decimal("10")}
    SalesService.complete(invoice, tenant_a.owner)
    order_a.refresh_from_db()
    assert order_still_held(order_a) == {product.id: Decimal("7")}
    # A draft or cancelled order holds nothing.
    order_b = SalesOrder.objects.exclude(pk=order_a.pk).get()
    order_b.status = SalesOrder.Status.CANCELLED
    assert order_still_held(order_b) == {}


# ---------------------------------------------------------------------------
# H-02 — a failed stop gives back only what is still held
# ---------------------------------------------------------------------------


def _stop(tenant, order):
    route = DeliveryRoute.objects.create(
        company=tenant.company, route_date="2026-10-14", status=DeliveryRoute.Status.IN_TRANSIT,
    )
    stop = DeliveryRouteStop.objects.create(company=tenant.company, route=route, sales_order=order)
    return route, stop


def test_tc_wp2_01_failed_stop_on_a_shipped_order_does_not_release_again(tenant_a):
    product, order_a, _order_b = _setup(tenant_a)
    _ship(order_a, tenant_a, 10)
    assert _reserved(tenant_a, product) == Decimal("5")
    route, stop = _stop(tenant_a, order_a)

    RouteService.set_stop_status(route, stop, "FAILED", tenant_a.owner)

    assert _reserved(tenant_a, product) == Decimal("5")  # pre-fix: 0 (B's hold eaten)
    # The goods are coming back: a draft return is opened for the godown.
    assert DeliveryChallanReturn.objects.filter(
        company=tenant_a.company, status=DeliveryChallanReturn.Status.DRAFT
    ).count() == 1


def test_tc_wp2_02_failed_stop_on_an_untouched_confirmed_order_releases_once(tenant_a):
    product, order_a, _order_b = _setup(tenant_a)
    route, stop = _stop(tenant_a, order_a)

    RouteService.set_stop_status(route, stop, "FAILED", tenant_a.owner)

    assert _reserved(tenant_a, product) == Decimal("5")
    order_a.refresh_from_db()
    # It now holds nothing, so it must be confirmed again (which re-reserves) before it can go out.
    assert order_a.status == SalesOrder.Status.DRAFT
    assert order_still_held(order_a) == {}
    SalesNotesService.confirm_sales_order(order_a, tenant_a.owner)
    assert _reserved(tenant_a, product) == Decimal("15")


def test_tc_wp2_03_failed_delivered_failed_releases_once(tenant_a):
    product, order_a, _order_b = _setup(tenant_a)
    route, stop = _stop(tenant_a, order_a)
    RouteService.set_stop_status(route, stop, "FAILED", tenant_a.owner)
    assert _reserved(tenant_a, product) == Decimal("5")
    stop.refresh_from_db()
    RouteService.set_stop_status(
        route, stop, "DELIVERED", tenant_a.owner, received_by_name="R", completion_source="OFFICE",
        reason="Customer took it after all",
    )
    stop.refresh_from_db()
    RouteService.set_stop_status(route, stop, "FAILED", tenant_a.owner, reason="Refused on second look")
    assert _reserved(tenant_a, product) == Decimal("5")


def test_tc_wp2_04_failed_stop_on_a_draft_order_is_a_no_op_for_stock(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "40")
    order_b = _confirmed(tenant_a, product, 5)
    draft = _order(tenant_a, product, 10)
    route, stop = _stop(tenant_a, draft)
    RouteService.set_stop_status(route, stop, "FAILED", tenant_a.owner)
    assert _reserved(tenant_a, product) == Decimal("5")
    draft.refresh_from_db()
    assert draft.status == SalesOrder.Status.DRAFT
    order_b.refresh_from_db()
    assert order_b.status == SalesOrder.Status.CONFIRMED


def test_tc_wp2_05_failed_stop_on_a_partly_shipped_order_keeps_the_remainder_held(tenant_a):
    product, order_a, _order_b = _setup(tenant_a)
    _ship(order_a, tenant_a, 4)
    assert _reserved(tenant_a, product) == Decimal("11")
    order_a.refresh_from_db()
    route, stop = _stop(tenant_a, order_a)

    RouteService.set_stop_status(route, stop, "FAILED", tenant_a.owner)

    # The 4 shipped were released at challan complete; the 6 not yet shipped are still wanted.
    assert _reserved(tenant_a, product) == Decimal("11")
    order_a.refresh_from_db()
    assert order_a.status == SalesOrder.Status.PARTIALLY_CONVERTED


def test_tc_wp2_06_failed_stop_on_an_invoiced_challan_opens_no_return(tenant_a):
    """Once the challan is converted the return path is refused; the stop must not 500 or open one."""
    product, order_a, _order_b = _setup(tenant_a)
    challan = _ship(order_a, tenant_a, 10)
    SalesNotesService.convert_delivery_challan(challan, tenant_a.owner)
    order_a.refresh_from_db()
    route, stop = _stop(tenant_a, order_a)
    RouteService.set_stop_status(route, stop, "FAILED", tenant_a.owner)
    assert DeliveryChallanReturn.objects.filter(company=tenant_a.company).count() == 0
    assert _reserved(tenant_a, product) == Decimal("5")
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == 1
    assert DeliveryChallan.objects.get(pk=challan.pk).status == DeliveryChallan.Status.COMPLETED


def test_tc_wp2_07_failed_stop_on_an_order_with_only_a_draft_challan_gives_the_stock_back(tenant_a):
    """The goods have not formally left, so there is nothing to check in: release and reconfirm."""
    product, order_a, _order_b = _setup(tenant_a)
    line = order_a.items.get()
    SalesNotesService.convert_sales_order_to_challan(order_a, tenant_a.owner, line_quantities={line.pk: Decimal("4")})
    assert _reserved(tenant_a, product) == Decimal("15")
    order_a.refresh_from_db()
    route, stop = _stop(tenant_a, order_a)

    RouteService.set_stop_status(route, stop, "FAILED", tenant_a.owner)

    assert _reserved(tenant_a, product) == Decimal("5")  # the order's whole hold went back, once
    order_a.refresh_from_db()
    assert order_a.status == SalesOrder.Status.DRAFT and order_a.stock_held is False
    assert DeliveryChallanReturn.objects.filter(company=tenant_a.company).count() == 0
    # Completing that draft challan later must not release stock the order no longer holds.
    challan = DeliveryChallan.objects.get(sales_order=order_a)
    SalesNotesService.complete_challan(challan, tenant_a.owner)
    assert _reserved(tenant_a, product) == Decimal("5")


def test_tc_wp2_08_a_draft_order_never_released_anything_it_did_not_hold(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "40")
    order_b = _confirmed(tenant_a, product, 5)
    draft = _order(tenant_a, product, 10)
    line = draft.items.get()
    challan = SalesNotesService.convert_sales_order_to_challan(draft, tenant_a.owner, line_quantities={line.pk: Decimal("4")})
    SalesNotesService.complete_challan(challan, tenant_a.owner)
    draft.refresh_from_db()
    assert draft.stock_held is False
    assert _reserved(tenant_a, product) == Decimal("5")
    second = SalesNotesService.convert_sales_order_to_challan(draft, tenant_a.owner)
    SalesNotesService.complete_challan(second, tenant_a.owner)
    assert _reserved(tenant_a, product) == Decimal("5")  # B's hold survives both completions
    order_b.refresh_from_db()
    assert order_b.status == SalesOrder.Status.CONFIRMED


# ---------------------------------------------------------------------------
# Cancelling a completed direct invoice gives the order its goods back
# ---------------------------------------------------------------------------


def test_cancelling_a_completed_direct_invoice_reopens_the_order_and_holds_stock_again(tenant_a):
    product, order_a, _order_b = _setup(tenant_a)
    invoice = SalesNotesService.convert_sales_order(order_a, tenant_a.owner)
    SalesService.complete(invoice, tenant_a.owner)
    order_a.refresh_from_db()
    assert order_a.status == SalesOrder.Status.CONVERTED
    assert _reserved(tenant_a, product) == Decimal("5")

    SalesService.cancel(invoice, tenant_a.owner, reason="Wrong rate")

    order_a.refresh_from_db()
    assert order_a.status == SalesOrder.Status.CONFIRMED
    assert order_a.converted_invoice_id is None
    assert _reserved(tenant_a, product) == Decimal("15")
    assert order_a.items.get().invoiced_quantity == 0


def test_cancelling_one_of_two_direct_invoices_leaves_the_order_partly_processed(tenant_a):
    product, order_a, _order_b = _setup(tenant_a)
    line = order_a.items.get()
    first = SalesNotesService.convert_sales_order(order_a, tenant_a.owner, line_quantities={line.pk: Decimal("4")})
    SalesService.complete(first, tenant_a.owner)
    second = SalesNotesService.convert_sales_order(order_a, tenant_a.owner, line_quantities={line.pk: Decimal("6")})
    SalesService.complete(second, tenant_a.owner)
    assert _reserved(tenant_a, product) == Decimal("5")

    SalesService.cancel(second, tenant_a.owner, reason="Customer changed mind")

    order_a.refresh_from_db()
    assert order_a.status == SalesOrder.Status.PARTIALLY_CONVERTED
    assert _reserved(tenant_a, product) == Decimal("11")
