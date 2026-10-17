"""R3 (H-12, H-13, H-04, H-08; DEC-1): one order ships in several challans, one invoice for each.

A challan and a direct invoice draw on one remainder, so no unit is shipped or billed twice and no
unit is lost. The line counters are a cache of the live documents and follow every change.
"""

from decimal import Decimal

import pytest

from core.exceptions import BusinessRuleError
from inventory.models import MovementType, StockBalance, StockMovement
from inventory.services import InventoryService
from sales.models import (
    DeliveryChallan,
    DeliveryRoute,
    DeliveryRouteStop,
    SalesOrder,
)
from sales.notes_services import SalesNotesService
from sales.order_quantities import invoices_for_order, order_remaining, order_still_held
from sales.route_profit_service import compute_route_financials
from sales.services import SalesService
from tests.conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db


def _order(tenant, product, qty):
    customer = make_customer(tenant.company, name=f"Cust {SalesOrder.objects.count()}")
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
    order = SalesOrder.objects.get(pk=resp.data["id"])
    SalesNotesService.confirm_sales_order(order, tenant.owner)
    order.refresh_from_db()
    return order


def _reserved(tenant, product):
    return StockBalance.objects.get(company=tenant.company, product=product).reserved


def _challan(tenant, order, qty):
    line = order.items.get()
    return SalesNotesService.convert_sales_order_to_challan(
        order, tenant.owner, line_quantities={line.pk: Decimal(str(qty))}
    )


def _direct_invoice(tenant, order, qty):
    line = order.items.get()
    return SalesNotesService.convert_sales_order(
        order, tenant.owner, line_quantities={line.pk: Decimal(str(qty))}
    )


@pytest.fixture
def setup(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "100")
    order_a = _order(tenant_a, product, 10)
    order_b = _order(tenant_a, product, 5)
    return product, order_a, order_b


# ---------------------------------------------------------------------------
# H-12 — several challans, an invoice for each
# ---------------------------------------------------------------------------


def test_tc_wp6_01_two_challans_two_invoices_close_the_order(tenant_a, setup):
    product, order_a, _b = setup
    for qty in (4, 6):
        challan = SalesNotesService.complete_challan(_challan(tenant_a, order_a, qty), tenant_a.owner)
        invoice = SalesNotesService.convert_delivery_challan(challan, tenant_a.owner)
        SalesService.complete(invoice, tenant_a.owner)
        order_a.refresh_from_db()

    assert order_a.status == SalesOrder.Status.CONVERTED
    # Only the other order's hold is left (pre-fix the second release took it as well).
    assert _reserved(tenant_a, product) == Decimal("5")
    sold = sum(
        abs(m.quantity)
        for m in StockMovement.objects.filter(
            company=tenant_a.company, product=product, movement_type=MovementType.SALE
        )
    )
    assert sold == Decimal("10")  # every unit left stock exactly once
    assert invoices_for_order(order_a).count() == 2
    line = order_a.items.get()
    assert (line.shipped_quantity, line.invoiced_quantity) == (Decimal("10"), Decimal("0"))


def test_tc_wp6_01b_second_challan_may_complete_after_the_first_was_invoiced(tenant_a, setup):
    """The old CR-120 guard refused this: the order already pointed at an invoice."""
    _p, order_a, _b = setup
    first = SalesNotesService.complete_challan(_challan(tenant_a, order_a, 4), tenant_a.owner)
    second = _challan(tenant_a, order_a, 6)  # drafted while the first is still open
    SalesNotesService.convert_delivery_challan(first, tenant_a.owner)
    SalesNotesService.complete_challan(second, tenant_a.owner)
    second.refresh_from_db()
    assert second.status == DeliveryChallan.Status.COMPLETED
    SalesNotesService.convert_delivery_challan(second, tenant_a.owner)


def test_tc_wp6_02_direct_invoice_cannot_take_units_a_challan_holds(tenant_a, setup):
    _p, order_a, _b = setup
    _challan(tenant_a, order_a, 4)
    with pytest.raises(BusinessRuleError, match="only 6 is still open"):
        _direct_invoice(tenant_a, order_a, 7)
    _direct_invoice(tenant_a, order_a, 6)  # exactly the remainder is fine
    assert order_remaining(order_a) == {order_a.items.get().product_id: Decimal("0")}


def test_tc_wp6_03_challan_cannot_take_units_a_direct_invoice_holds(tenant_a, setup):
    _p, order_a, _b = setup
    _direct_invoice(tenant_a, order_a, 6)
    with pytest.raises(BusinessRuleError, match="only 4 is still open"):
        _challan(tenant_a, order_a, 5)
    _challan(tenant_a, order_a, 4)


def test_tc_wp6_03b_everything_taken_names_what_holds_it(tenant_a, setup):
    _p, order_a, order_b = setup
    _direct_invoice(tenant_a, order_a, 10)
    with pytest.raises(BusinessRuleError, match="already has an invoice"):
        SalesNotesService.convert_sales_order_to_challan(order_a, tenant_a.owner)
    _challan(tenant_a, order_b, 5)
    with pytest.raises(BusinessRuleError, match="already has a delivery challan"):
        SalesNotesService.convert_sales_order(order_b, tenant_a.owner)


# ---------------------------------------------------------------------------
# H-13 — several invoices per order
# ---------------------------------------------------------------------------


def test_tc_wp6_04_converted_invoice_is_the_latest_and_the_helper_returns_all(tenant_a, setup):
    _p, order_a, _b = setup
    one = _direct_invoice(tenant_a, order_a, 4)
    two = _direct_invoice(tenant_a, order_a, 6)
    order_a.refresh_from_db()
    assert order_a.converted_invoice_id == two.pk
    assert set(invoices_for_order(order_a).values_list("pk", flat=True)) == {one.pk, two.pk}


def test_tc_wp6_04b_a_challan_invoice_and_a_direct_invoice_are_both_found(tenant_a, setup):
    _p, order_a, _b = setup
    challan = SalesNotesService.complete_challan(_challan(tenant_a, order_a, 4), tenant_a.owner)
    from_challan = SalesNotesService.convert_delivery_challan(challan, tenant_a.owner)
    direct = _direct_invoice(tenant_a, order_a, 6)
    assert set(invoices_for_order(order_a).values_list("pk", flat=True)) == {from_challan.pk, direct.pk}


def test_tc_wp6_05_an_order_with_a_live_invoice_cannot_be_cancelled(tenant_a, setup):
    _p, order_a, _b = setup
    invoice = _direct_invoice(tenant_a, order_a, 10)  # whole order: stays CONFIRMED until it completes
    order_a.refresh_from_db()
    assert order_a.status == SalesOrder.Status.CONFIRMED
    with pytest.raises(BusinessRuleError, match=f"draft #{invoice.pk}"):
        SalesNotesService.cancel_sales_order(order_a, tenant_a.owner)


def test_tc_wp6_06_deleting_the_draft_gives_the_quantity_back_and_lets_the_order_cancel(tenant_a, setup):
    product, order_a, _b = setup
    invoice = _direct_invoice(tenant_a, order_a, 10)
    resp = tenant_a.client.delete(f"/api/v1/sales/invoices/{invoice.pk}/")
    assert resp.status_code == 204, resp.data
    order_a.refresh_from_db()
    line = order_a.items.get()
    assert line.invoiced_quantity == Decimal("0")
    assert order_a.converted_invoice_id is None
    SalesNotesService.cancel_sales_order(order_a, tenant_a.owner)
    assert _reserved(tenant_a, product) == Decimal("5")


def test_tc_wp6_06b_deleting_the_latest_draft_repoints_to_the_earlier_invoice(tenant_a, setup):
    _p, order_a, _b = setup
    one = _direct_invoice(tenant_a, order_a, 4)
    two = _direct_invoice(tenant_a, order_a, 6)
    resp = tenant_a.client.delete(f"/api/v1/sales/invoices/{two.pk}/")
    assert resp.status_code == 204, resp.data
    order_a.refresh_from_db()
    assert order_a.converted_invoice_id == one.pk
    assert order_a.items.get().invoiced_quantity == Decimal("4")
    assert order_a.status == SalesOrder.Status.PARTIALLY_CONVERTED


def test_tc_wp6_06c_deleting_a_draft_challan_gives_its_quantity_back(tenant_a, setup):
    _p, order_a, _b = setup
    challan = _challan(tenant_a, order_a, 4)
    assert order_a.items.get().shipped_quantity == Decimal("4")
    resp = tenant_a.client.delete(f"/api/v1/sales/delivery-challans/{challan.pk}/")
    assert resp.status_code == 204, resp.data
    order_a.refresh_from_db()
    assert order_a.items.get().shipped_quantity == Decimal("0")
    assert order_a.status == SalesOrder.Status.CONFIRMED
    _challan(tenant_a, order_a, 10)  # the whole order can go out now


def test_tc_wp6_10_trip_profit_counts_every_invoice_of_the_order(tenant_a, setup):
    _p, order_a, _b = setup
    for qty in (4, 6):
        challan = SalesNotesService.complete_challan(_challan(tenant_a, order_a, qty), tenant_a.owner)
        invoice = SalesNotesService.convert_delivery_challan(challan, tenant_a.owner)
        SalesService.complete(invoice, tenant_a.owner)
    route = DeliveryRoute.objects.create(
        company=tenant_a.company, route_date="2026-10-14", status=DeliveryRoute.Status.IN_TRANSIT,
    )
    order_a.refresh_from_db()
    DeliveryRouteStop.objects.create(
        company=tenant_a.company, route=route, sales_order=order_a, status=DeliveryRouteStop.StopStatus.DELIVERED,
    )
    financials = compute_route_financials(route)
    assert financials.invoiced_stop_count == 1
    assert financials.realized_revenue == Decimal("1000.00")  # 4 x 100 + 6 x 100, not just the latest 600
    assert financials.realized_cogs > Decimal("0")


def test_tc_wp6_11_cancelling_one_completed_challan_reopens_only_its_quantity(tenant_a, setup):
    product, order_a, _b = setup
    first = SalesNotesService.complete_challan(_challan(tenant_a, order_a, 4), tenant_a.owner)
    SalesNotesService.complete_challan(_challan(tenant_a, order_a, 6), tenant_a.owner)
    order_a.refresh_from_db()
    assert order_a.status == SalesOrder.Status.CONVERTED
    assert _reserved(tenant_a, product) == Decimal("5")

    SalesNotesService.cancel_challan(first, tenant_a.owner)

    order_a.refresh_from_db()
    assert order_a.status == SalesOrder.Status.PARTIALLY_CONVERTED
    assert order_a.items.get().shipped_quantity == Decimal("6")
    # Its 4 are owed (and held) again; the other order's 5 are untouched.
    assert _reserved(tenant_a, product) == Decimal("9")
    assert order_still_held(order_a) == {product.id: Decimal("4")}


def test_tc_wp6_11b_cancelling_the_only_challan_returns_the_order_to_confirmed(tenant_a, setup):
    product, order_a, _b = setup
    only = SalesNotesService.complete_challan(_challan(tenant_a, order_a, 10), tenant_a.owner)
    assert _reserved(tenant_a, product) == Decimal("5")
    SalesNotesService.cancel_challan(only, tenant_a.owner)
    order_a.refresh_from_db()
    assert order_a.status == SalesOrder.Status.CONFIRMED
    assert order_a.items.get().shipped_quantity == Decimal("0")
    assert _reserved(tenant_a, product) == Decimal("15")


def test_tc_wp6_14_status_waits_while_a_draft_is_still_open(tenant_a, setup):
    """All units taken but one challan still a draft: the order is not closed yet."""
    _p, order_a, _b = setup
    SalesNotesService.complete_challan(_challan(tenant_a, order_a, 4), tenant_a.owner)
    pending = _challan(tenant_a, order_a, 6)
    order_a.refresh_from_db()
    assert order_a.status == SalesOrder.Status.PARTIALLY_CONVERTED
    SalesNotesService.complete_challan(pending, tenant_a.owner)
    order_a.refresh_from_db()
    assert order_a.status == SalesOrder.Status.CONVERTED


# ---------------------------------------------------------------------------
# H-04 — the stock rebuild and the unit-change guard know about partly processed orders
# ---------------------------------------------------------------------------


def test_tc_wp6_h04_01_rebuild_keeps_a_partly_shipped_orders_remainder_reserved(tenant_a, setup):
    product, order_a, _b = setup
    SalesNotesService.complete_challan(_challan(tenant_a, order_a, 4), tenant_a.owner)
    assert _reserved(tenant_a, product) == Decimal("11")
    InventoryService.rebuild_balance(tenant_a.company, product)
    # A's unshipped 6 plus B's 5. Counting only CONFIRMED orders gave 5.
    assert _reserved(tenant_a, product) == Decimal("11")


def test_tc_wp6_h04_02_unit_change_is_blocked_by_a_partly_processed_order(tenant_a, setup):
    from inventory.item_stock import assert_no_open_documents_for_unit_change

    product, order_a, order_b = setup
    SalesNotesService.cancel_sales_order(order_b, tenant_a.owner)
    SalesNotesService.complete_challan(_challan(tenant_a, order_a, 4), tenant_a.owner)
    order_a.refresh_from_db()
    assert order_a.status == SalesOrder.Status.PARTIALLY_CONVERTED
    with pytest.raises(BusinessRuleError, match="open sales order"):
        assert_no_open_documents_for_unit_change(product)


def test_tc_wp6_h04_03_unit_change_is_allowed_once_the_order_is_fully_delivered(tenant_a, setup):
    from inventory.item_stock import assert_no_open_documents_for_unit_change

    product, order_a, order_b = setup
    SalesNotesService.cancel_sales_order(order_b, tenant_a.owner)
    challan = SalesNotesService.complete_challan(_challan(tenant_a, order_a, 10), tenant_a.owner)
    invoice = SalesNotesService.convert_delivery_challan(challan, tenant_a.owner)
    SalesService.complete(invoice, tenant_a.owner)
    order_a.refresh_from_db()
    assert order_a.status == SalesOrder.Status.CONVERTED
    assert_no_open_documents_for_unit_change(product)  # nothing open: no error


# ---------------------------------------------------------------------------
# H-08 — a challan built by hand and linked to an order
# ---------------------------------------------------------------------------


def _post_challan(tenant, order, product, qty):
    return tenant.client.post(
        "/api/v1/sales/delivery-challans/",
        {
            "customer": order.customer_id,
            "sales_order": order.id,
            "items": [{"product": product.id, "quantity": str(qty), "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )


def test_tc_wp9_01_a_hand_linked_challan_within_the_remainder_counts_against_the_order(tenant_a, setup):
    product, order_a, _b = setup
    resp = _post_challan(tenant_a, order_a, product, 4)
    assert resp.status_code == 201, resp.data
    assert order_a.items.get().shipped_quantity == Decimal("4")
    assert order_remaining(order_a) == {product.id: Decimal("6")}


def test_tc_wp9_02_above_the_remainder_is_refused_with_the_number(tenant_a, setup):
    product, order_a, _b = setup
    _challan(tenant_a, order_a, 4)
    resp = _post_challan(tenant_a, order_a, product, 7)
    assert resp.status_code == 400
    assert "only 6 is still open" in str(resp.data)


def test_tc_wp9_02b_a_product_not_on_the_order_is_refused(tenant_a, setup):
    _p, order_a, _b = setup
    other = make_product(tenant_a.company, name="Other", sku="OTH-1")
    add_stock(tenant_a, other, "10")
    resp = _post_challan(tenant_a, order_a, other, 1)
    assert resp.status_code == 400
    assert "is not on sales order" in str(resp.data)


def test_tc_wp9_02c_editing_a_draft_does_not_compete_with_itself(tenant_a, setup):
    product, order_a, _b = setup
    resp = _post_challan(tenant_a, order_a, product, 10)  # the whole order, as a draft
    assert resp.status_code == 201, resp.data
    edit = tenant_a.client.patch(
        f"/api/v1/sales/delivery-challans/{resp.data['id']}/",
        {"items": [{"product": product.id, "quantity": "9", "unit_price": "100", "gst_rate": "0"}]},
        format="json",
    )
    assert edit.status_code == 200, edit.data
    assert order_a.items.get().shipped_quantity == Decimal("9")


def test_tc_wp9_03_deleting_the_draft_gives_the_quantity_back(tenant_a, setup):
    product, order_a, _b = setup
    resp = _post_challan(tenant_a, order_a, product, 4)
    tenant_a.client.delete(f"/api/v1/sales/delivery-challans/{resp.data['id']}/")
    assert order_a.items.get().shipped_quantity == Decimal("0")


def test_tc_wp9_04_a_hand_linked_challan_completes_like_any_other(tenant_a, setup):
    product, order_a, _b = setup
    resp = _post_challan(tenant_a, order_a, product, 4)
    done = tenant_a.client.post(f"/api/v1/sales/delivery-challans/{resp.data['id']}/complete/")
    assert done.status_code == 200, done.data
    order_a.refresh_from_db()
    assert order_a.status == SalesOrder.Status.PARTIALLY_CONVERTED  # was CONVERTED whatever the quantity
    assert _reserved(tenant_a, product) == Decimal("11")
