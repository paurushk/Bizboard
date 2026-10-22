"""R7 (PL-01, PL-03, PL-31): the facts and risks a dispatcher sees about an order before it goes on a van.

One case per risk code with its boundary (exactly at the limit, exactly equal stock, the day of expiry),
who may see what, and a guard that the work grows with customers and invoices, not with orders.
"""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from inventory.models import BatchLot, StockBalance
from inventory.services import InventoryService
from masters.models import Customer
from sales.models import (
    DeliveryRoute,
    DeliveryRouteStop,
    SalesInvoice,
    SalesOrder,
    SalesOrderItem,
)
from sales.notes_services import SalesNotesService
from sales.route_planning import (
    BLOCK,
    INFO,
    RISKS,
    WARN,
    Viewer,
    order_summaries,
    route_totals,
    unresolved_risks,
)
from tests.conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db

OWNER = Viewer(role="OWNER", can_see_customer_money=True, can_see_cost=True)
STAFF = Viewer(role="SALES_STAFF", can_see_customer_money=False, can_see_cost=False)
TODAY = timezone.localdate()


def _order(
    tenant,
    *,
    status=SalesOrder.Status.CONFIRMED,
    qty="2",
    price="100",
    customer=None,
    address="12 Market Road",
    product=None,
    stock_held=False,
    **extra,
):
    customer = customer or make_customer(tenant.company, name=f"Cust {SalesOrder.objects.count()}", phone="9876543210", pincode="560001")
    product = product or make_product(tenant.company, sku=f"P-{SalesOrder.objects.count()}", track_inventory=False)
    order = SalesOrder.objects.create(
        company=tenant.company, customer=customer, status=status, delivery_address=address,
        grand_total=Decimal(qty) * Decimal(price), stock_held=stock_held, **extra,
    )
    SalesOrderItem.objects.create(
        company=tenant.company, sales_order=order, product=product, quantity=Decimal(qty), unit_price=Decimal(price),
    )
    return order


def _summary(tenant, order, viewer=OWNER, route=None):
    loaded = SalesOrder.objects.filter(pk=order.pk).select_related("customer", "warehouse").prefetch_related("items__product").get()
    return order_summaries(tenant.company, [loaded], viewer=viewer, route=route)[order.pk]


def _codes(summary, level=None):
    return {r["code"] for r in summary["risks"] if level is None or r["level"] == level}


def _route(tenant, status=DeliveryRoute.Status.PLANNED, number="RT-1"):
    return DeliveryRoute.objects.create(company=tenant.company, route_date=TODAY, number=number, status=status)


# ---------------------------------------------------------------------------
# the catalogue itself
# ---------------------------------------------------------------------------


def test_the_catalogue_levels_and_overrides_are_what_was_decided():
    assert {c for c, (lvl, _w) in RISKS.items() if lvl == BLOCK} == {
        "order_cancelled", "already_on_route", "already_delivered", "customer_blocked", "not_ready",
        "empty_order", "no_stock",
    }
    assert RISKS["not_ready"][1] == "none"  # DEC-P1 revised: no owner override for an unconfirmed order
    assert RISKS["stock_short"][0] == WARN and RISKS["over_credit_limit"][0] == WARN  # DEC-P2, DEC-P4
    assert RISKS["over_credit_limit"][1] == "manager" and RISKS["credit_hold"][1] == "manager"
    assert all(RISKS[c][1] == "none" for c, (lvl, _w) in RISKS.items() if lvl == INFO)
    for blocked in ("order_cancelled", "already_on_route", "already_delivered", "customer_blocked",
                    "not_ready", "empty_order", "no_stock"):
        assert RISKS[blocked][1] == "none"


def test_who_may_accept_what():
    assert not OWNER.may_accept("not_ready") and not STAFF.may_accept("not_ready")
    manager = Viewer(role="MANAGER")
    assert manager.may_accept("over_credit_limit") and not STAFF.may_accept("over_credit_limit")
    assert STAFF.may_accept("stock_short") and STAFF.may_accept("no_address")
    assert not OWNER.may_accept("order_cancelled") and not OWNER.may_accept("customer_blocked")
    assert not OWNER.may_accept("late")


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


def test_tc_pl03_01_cancelled(tenant_a):
    s = _summary(tenant_a, _order(tenant_a, status=SalesOrder.Status.CANCELLED))
    assert "order_cancelled" in _codes(s, BLOCK) and s["ready"] is False


def test_tc_pl03_02_on_another_active_route_or_already_delivered(tenant_a):
    order = _order(tenant_a)
    other = _route(tenant_a, number="RT-OTHER")
    DeliveryRouteStop.objects.create(company=tenant_a.company, route=other, sales_order=order)
    mine = _route(tenant_a, number="RT-MINE")
    on = _summary(tenant_a, order, route=mine)
    assert "already_on_route" in _codes(on, BLOCK) and "RT-OTHER" in str(on["risks"])
    # the route the order is on is not "another" route for itself
    assert "already_on_route" not in _codes(_summary(tenant_a, order, route=other))
    DeliveryRouteStop.objects.filter(route=other).update(status=DeliveryRouteStop.StopStatus.DELIVERED)
    assert "already_delivered" in _codes(_summary(tenant_a, order, route=mine), BLOCK)


def test_tc_pl03_02b_a_failed_stop_or_a_cancelled_route_frees_the_order(tenant_a):
    order = _order(tenant_a)
    other = _route(tenant_a, number="RT-OTHER")
    stop = DeliveryRouteStop.objects.create(company=tenant_a.company, route=other, sales_order=order)
    mine = _route(tenant_a, number="RT-MINE")
    DeliveryRouteStop.objects.filter(pk=stop.pk).update(status=DeliveryRouteStop.StopStatus.FAILED)
    assert "already_on_route" not in _codes(_summary(tenant_a, order, route=mine))
    DeliveryRouteStop.objects.filter(pk=stop.pk).update(status=DeliveryRouteStop.StopStatus.PENDING)
    DeliveryRoute.objects.filter(pk=other.pk).update(status=DeliveryRoute.Status.CANCELLED)
    assert "already_on_route" not in _codes(_summary(tenant_a, order, route=mine))


def test_tc_pl03_03_blocked_or_inactive_customer(tenant_a):
    customer = make_customer(tenant_a.company, name="Blocked Co", phone="9000000000", pincode="560001", status=Customer.Status.BLOCKED)
    s = _summary(tenant_a, _order(tenant_a, customer=customer))
    assert "customer_blocked" in _codes(s, BLOCK)


def test_tc_pl03_04_a_draft_is_not_ready_and_nobody_may_accept_it(tenant_a):
    s = _summary(tenant_a, _order(tenant_a, status=SalesOrder.Status.DRAFT))
    assert "not_ready" in _codes(s, BLOCK)
    for viewer in (OWNER, STAFF):
        result = unresolved_risks(s, {"not_ready"}, viewer)
        assert [r["code"] for r in result["blocked"]] == ["not_ready"]


def test_an_order_with_no_quantity_is_blocked(tenant_a):
    order = _order(tenant_a, qty="0")
    assert "empty_order" in _codes(_summary(tenant_a, order), BLOCK)
    order.items.all().delete()
    s = _summary(tenant_a, SalesOrder.objects.get(pk=order.pk))
    assert "empty_order" in _codes(s, BLOCK)
    assert [r["code"] for r in unresolved_risks(s, {"empty_order"}, OWNER)["blocked"]] == ["empty_order"]


def test_nothing_on_the_shelf_is_a_block_but_a_partial_shortage_stays_a_warning(tenant_a):
    product = make_product(tenant_a.company, sku="STK-0")
    s = _summary(tenant_a, _order(tenant_a, qty="3", product=product))
    assert "no_stock" in _codes(s, BLOCK) and "stock_short" not in _codes(s)
    assert [r["code"] for r in unresolved_risks(s, {"no_stock"}, OWNER)["blocked"]] == ["no_stock"]
    add_stock(tenant_a, product, "2")
    s = _summary(tenant_a, _order(tenant_a, qty="3", product=product))
    assert "stock_short" in _codes(s, WARN) and "no_stock" not in _codes(s)


@pytest.mark.parametrize("status", ["CONFIRMED", "PARTIALLY_CONVERTED", "CONVERTED"])
def test_tc_pl03_04b_routable_statuses_have_no_readiness_problem(tenant_a, status):
    assert "not_ready" not in _codes(_summary(tenant_a, _order(tenant_a, status=status)))


# ---------------------------------------------------------------------------
# Warns
# ---------------------------------------------------------------------------


def test_tc_pl03_05_stock_exactly_equal_is_fine_one_less_is_short(tenant_a):
    product = make_product(tenant_a.company, sku="STK-1")
    add_stock(tenant_a, product, "5")
    assert "stock_short" not in _codes(_summary(tenant_a, _order(tenant_a, qty="5", product=product)))
    s = _summary(tenant_a, _order(tenant_a, qty="6", product=product))
    assert "stock_short" in _codes(s, WARN)
    assert s["lines"][0]["available"] == "5" and s["lines"][0]["short"] == "1"


def test_tc_pl03_06_the_orders_own_reservation_does_not_count_against_it(tenant_a):
    product = make_product(tenant_a.company, sku="STK-2")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company, name="Own Hold", phone="9000000001", pincode="560001")
    resp = tenant_a.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id, "invoice_type": "NON_GST", "delivery_address": "Gate 1",
            "items": [{"product": product.id, "quantity": "10", "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )
    order = SalesOrder.objects.get(pk=resp.data["id"])
    SalesNotesService.confirm_sales_order(order, tenant_a.owner)
    order.refresh_from_db()
    assert StockBalance.objects.get(company=tenant_a.company, product=product).reserved == Decimal("10")
    assert "stock_short" not in _codes(_summary(tenant_a, order))


@pytest.mark.invariant_skip("inventory.balance_equals_movements", reason="stock balances or movements are written directly through the ORM")
def test_tc_pl03_06b_goods_already_shipped_need_no_stock(tenant_a):
    product = make_product(tenant_a.company, sku="STK-3")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company, name="Shipped", phone="9000000002", pincode="560001")
    resp = tenant_a.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id, "invoice_type": "NON_GST", "delivery_address": "Gate 1",
            "items": [{"product": product.id, "quantity": "10", "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )
    order = SalesOrder.objects.get(pk=resp.data["id"])
    SalesNotesService.confirm_sales_order(order, tenant_a.owner)
    SalesNotesService.complete_challan(
        SalesNotesService.convert_sales_order_to_challan(order, tenant_a.owner), tenant_a.owner
    )
    order.refresh_from_db()
    add_stock(tenant_a, make_product(tenant_a.company, sku="OTHER"), "1")
    StockBalance.objects.filter(company=tenant_a.company, product=product).update(on_hand=0, reserved=0)
    s = _summary(tenant_a, order)
    assert "stock_short" not in _codes(s)
    assert "eway_needed" not in _codes(s)


def test_tc_pl03_07_credit_hold(tenant_a):
    order = _order(tenant_a)
    with mock.patch("planwave.services.chronic_overdue", return_value=(True, Decimal("6000"))):
        s = _summary(tenant_a, order)
    hold = [r for r in s["risks"] if r["code"] == "credit_hold"][0]
    assert hold["level"] == WARN and hold["override"] == "manager" and "6000.00" in hold["message"]
    with mock.patch("planwave.services.chronic_overdue", return_value=(True, Decimal("6000"))):
        hidden = _summary(tenant_a, order, viewer=STAFF)
    assert "6000" not in [r for r in hidden["risks"] if r["code"] == "credit_hold"][0]["message"]


def test_tc_pl03_08_credit_limit_exactly_reached_is_fine_one_rupee_over_is_not(tenant_a):
    customer = make_customer(tenant_a.company, name="Limit Co", phone="9000000003", pincode="560001", credit_limit=Decimal("1000"))
    order = _order(tenant_a, customer=customer, qty="10", price="100")  # 1000
    assert "over_credit_limit" not in _codes(_summary(tenant_a, order))
    _order(tenant_a, customer=customer, qty="1", price="1")  # one rupee more
    s = _summary(tenant_a, order)
    over = [r for r in s["risks"] if r["code"] == "over_credit_limit"][0]
    assert over["level"] == WARN and "₹1.00" in over["message"]


def test_tc_pl03_08b_no_limit_never_flags(tenant_a):
    customer = make_customer(tenant_a.company, name="No Limit", phone="9000000004", pincode="560001", credit_limit=Decimal("0"))
    assert "over_credit_limit" not in _codes(_summary(tenant_a, _order(tenant_a, customer=customer, qty="1000", price="1000")))


@pytest.mark.invariant_skip("gl.ar_ties_to_documents", reason="sales documents or journals are built through the ORM, so receivables in the ledger and on documents cannot tie")
def test_tc_pl03_09_overdue_invoices(tenant_a):
    customer = make_customer(tenant_a.company, name="Late Payer", phone="9000000005", pincode="560001")
    SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, status=SalesInvoice.Status.COMPLETED, grand_total=Decimal("500"),
        invoice_date=TODAY - timedelta(days=40), due_date=TODAY - timedelta(days=10), created_by=tenant_a.owner,
    )
    s = _summary(tenant_a, _order(tenant_a, customer=customer))
    overdue = [r for r in s["risks"] if r["code"] == "customer_overdue"][0]
    assert overdue["level"] == WARN and "₹500.00 overdue" in overdue["message"]
    assert s["money"]["overdue"] == "500.00" and s["money"]["collection_status"] == "overdue"
    assert "money" not in _summary(tenant_a, _order(tenant_a, customer=customer), viewer=STAFF)


@pytest.mark.invariant_skip("inventory.balance_equals_movements", reason="stock balances or movements are written directly through the ORM")
def test_tc_pl03_10_batch_expiry_boundaries(tenant_a):
    product = make_product(tenant_a.company, sku="BATCH-1", track_batch=True)
    warehouse = InventoryService.default_warehouse(tenant_a.company)

    def with_expiry(days):
        lot = BatchLot.objects.create(
            company=tenant_a.company, product=product, batch_no=f"B{days}", expiry_date=TODAY + timedelta(days=days),
        )
        StockBalance.objects.create(company=tenant_a.company, warehouse=warehouse, product=product, batch=lot, on_hand=Decimal("20"))
        return lot

    lot = with_expiry(31)  # the day after the window
    order = _order(tenant_a, product=product, qty="1")
    assert "expired_or_near_expiry" not in _codes(_summary(tenant_a, order))
    BatchLot.objects.filter(pk=lot.pk).update(expiry_date=TODAY + timedelta(days=30))  # the last day inside
    assert "expired_or_near_expiry" in _codes(_summary(tenant_a, order), WARN)
    BatchLot.objects.filter(pk=lot.pk).update(expiry_date=TODAY - timedelta(days=1))
    s = _summary(tenant_a, order)
    assert "expired on" in [r for r in s["risks"] if r["code"] == "expired_or_near_expiry"][0]["message"]


def test_tc_pl03_11_missing_address_phone_and_pincode(tenant_a):
    customer = make_customer(tenant_a.company, name="Sparse", phone="", pincode="")
    s = _summary(tenant_a, _order(tenant_a, customer=customer, address=""))
    assert {"no_address", "no_phone"} <= _codes(s, WARN)
    assert "no_pincode" in _codes(s, INFO)
    full = _summary(tenant_a, _order(tenant_a))
    assert not ({"no_address", "no_phone", "no_pincode"} & _codes(full))


def test_tc_pl03_12_eway_bill_by_value_and_by_what_exists(tenant_a):
    big = _order(tenant_a, qty="1", price="60000")
    assert "eway_will_be_needed" in _codes(_summary(tenant_a, big), INFO)  # nothing shipped yet
    small = _order(tenant_a, qty="1", price="49999")
    assert not ({"eway_will_be_needed", "eway_needed"} & _codes(_summary(tenant_a, small)))
    exact = _order(tenant_a, qty="1", price="50000")
    assert "eway_will_be_needed" in _codes(_summary(tenant_a, exact))  # the threshold itself counts


def test_tc_pl03_12b_a_shipped_order_without_an_eway_bill_is_a_warning(tenant_a):
    product = make_product(tenant_a.company, sku="EWAY-1")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Eway Co", phone="9000000006", pincode="560001")
    resp = tenant_a.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id, "invoice_type": "NON_GST", "delivery_address": "Gate 1",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "60000", "gst_rate": "0"}],
        },
        format="json",
    )
    order = SalesOrder.objects.get(pk=resp.data["id"])
    SalesNotesService.confirm_sales_order(order, tenant_a.owner)
    challan = SalesNotesService.complete_challan(
        SalesNotesService.convert_sales_order_to_challan(order, tenant_a.owner), tenant_a.owner
    )
    order.refresh_from_db()
    assert "eway_needed" in _codes(_summary(tenant_a, order), WARN)
    type(challan).objects.filter(pk=challan.pk).update(eway_status="GENERATED")
    assert "eway_needed" not in _codes(_summary(tenant_a, order))


# ---------------------------------------------------------------------------
# Info
# ---------------------------------------------------------------------------


def test_tc_pl03_13_margin_only_for_people_who_may_see_cost(tenant_a):
    product = make_product(tenant_a.company, sku="MARG-1", purchase_price="99", selling_price="100", track_inventory=False)
    order = _order(tenant_a, product=product, price="100")
    assert "low_margin" in _codes(_summary(tenant_a, order, viewer=OWNER), INFO)
    assert "low_margin" not in _codes(_summary(tenant_a, order, viewer=STAFF))
    assert "low_margin_products" not in _summary(tenant_a, order, viewer=STAFF)


def test_tc_pl03_14_partial_late_and_unverified_gstin(tenant_a):
    customer = make_customer(tenant_a.company, name="Gst Co", phone="9000000007", pincode="560001", gstin="29ABCDE1234F1Z5")
    customer.gstin_verification_status = "UNVERIFIED"
    customer.save(update_fields=["gstin_verification_status"])
    order = _order(tenant_a, customer=customer, expected_delivery=TODAY - timedelta(days=3))
    s = _summary(tenant_a, order)
    assert {"late", "gstin_unverified"} <= _codes(s, INFO)
    assert "3 day(s) past" in [r for r in s["risks"] if r["code"] == "late"][0]["message"]
    on_time = _summary(tenant_a, _order(tenant_a, expected_delivery=TODAY))
    assert "late" not in _codes(on_time)


def test_tc_pl03_15_info_never_needs_accepting(tenant_a):
    s = _summary(tenant_a, _order(tenant_a, expected_delivery=TODAY - timedelta(days=2)))
    assert "late" in _codes(s, INFO)
    result = unresolved_risks(s, set(), OWNER)
    assert result["blocked"] == [] and result["needs_ack"] == [] and result["not_allowed"] == []


# ---------------------------------------------------------------------------
# the summary
# ---------------------------------------------------------------------------


def test_the_summary_carries_what_the_dispatcher_needs(tenant_a):
    product = make_product(tenant_a.company, sku="SUM-1", name="Sample Widget", track_inventory=False)
    order = _order(tenant_a, product=product, qty="3", price="100", expected_delivery=TODAY + timedelta(days=1))
    s = _summary(tenant_a, order)
    assert s["customer"]["phone"] == "9876543210" and s["customer"]["pincode"] == "560001"
    assert s["delivery_address"] == "12 Market Road"
    assert s["lines"][0]["name"] == "Sample Widget" and s["lines"][0]["quantity"] == "3"
    assert s["line_count"] == 1 and s["total_quantity"] == "3" and s["grand_total"] == "300.00"
    assert s["bill"]["bill_status"] == "order_only" and s["bill"]["amount_to_collect"] == "300.00"
    assert s["ready"] is True


def test_credit_terms_mean_nothing_to_collect_at_the_door(tenant_a):
    order = _order(tenant_a, payment_terms_days=30)
    s = _summary(tenant_a, order)
    assert s["bill"]["on_credit"] is True and s["bill"]["amount_to_collect"] == "0.00"


def test_route_totals(tenant_a):
    a = _summary(tenant_a, _order(tenant_a, qty="2", price="100"))
    b = _summary(tenant_a, _order(tenant_a, qty="3", price="50", address=""))
    totals = route_totals([a, b])
    assert totals["orders"] == 2 and totals["lines"] == 2 and totals["quantity"] == "5"
    assert totals["value"] == "350.00" and totals["to_collect"] == "350.00"
    assert totals["warnings"] >= 1 and totals["blocks"] == 0


# ---------------------------------------------------------------------------
# PL-31 — work grows with customers and invoices, not with orders
# ---------------------------------------------------------------------------


def _count_queries(tenant, orders):
    loaded = list(
        SalesOrder.objects.filter(pk__in=[o.pk for o in orders]).select_related("customer", "warehouse").prefetch_related("items__product")
    )
    with CaptureQueriesContext(connection) as ctx:
        order_summaries(tenant.company, loaded, viewer=OWNER)
    return len(ctx)


def test_tc_pl31_01_queries_do_not_grow_with_the_number_of_orders(tenant_a):
    customer = make_customer(tenant_a.company, name="Many Orders", phone="9000000008", pincode="560001", credit_limit=Decimal("100000"))
    product = make_product(tenant_a.company, sku="MANY-1", track_inventory=False)
    one = [_order(tenant_a, customer=customer, product=product)]
    _count_queries(tenant_a, one)  # warm per-process caches (default warehouse and the like)
    base = _count_queries(tenant_a, one)
    more = one + [_order(tenant_a, customer=customer, product=product) for _ in range(19)]
    cost = _count_queries(tenant_a, more)
    assert cost <= base + 2, f"1 order cost {base} queries, 20 orders cost {cost}"


def test_tc_pl31_02_the_customer_snapshot_is_taken_once_per_customer(tenant_a):
    customer = make_customer(tenant_a.company, name="Once", phone="9000000009", pincode="560001")
    orders = [_order(tenant_a, customer=customer) for _ in range(6)]
    loaded = list(
        SalesOrder.objects.filter(pk__in=[o.pk for o in orders]).select_related("customer").prefetch_related("items__product")
    )
    with mock.patch("payments.dunning.customer_risk_snapshot", wraps=__import__("payments.dunning", fromlist=["x"]).customer_risk_snapshot) as spy:
        order_summaries(tenant_a.company, loaded, viewer=OWNER)
    assert spy.call_count == 1
