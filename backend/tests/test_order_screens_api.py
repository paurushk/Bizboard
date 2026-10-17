"""R2 (H-05, H-06, H-07, H-16): the order list, cancel, fulfilment label and search.

Backend half of the order-screen hardening: a multi-status list filter, cancelling a confirmed order,
the read-only ``fulfilment_state`` that drives the "Shipped" label, and global search finding orders,
challans and delivery routes.
"""

from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from inventory.models import StockBalance
from sales.models import DeliveryChallan, DeliveryRoute, SalesOrder
from sales.notes_services import SalesNotesService
from tests.conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db


def _order(tenant, product, qty=2, customer=None, **extra):
    customer = customer or make_customer(tenant.company, name=f"Cust {SalesOrder.objects.count()}")
    resp = tenant.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id,
            "invoice_type": "NON_GST",
            "items": [{"product": product.id, "quantity": str(qty), "unit_price": "100", "gst_rate": "0"}],
            **extra,
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    return SalesOrder.objects.get(pk=resp.data["id"])


@pytest.fixture
def product(tenant_a):
    p = make_product(tenant_a.company)
    add_stock(tenant_a, p, "100")
    return p


def _results(resp):
    data = resp.data
    return data["results"] if isinstance(data, dict) and "results" in data else data


# ---------------------------------------------------------------------------
# list filter
# ---------------------------------------------------------------------------


def test_tc_wp4_b01_list_accepts_several_statuses(tenant_a, product):
    draft = _order(tenant_a, product)
    confirmed = _order(tenant_a, product)
    SalesNotesService.confirm_sales_order(confirmed, tenant_a.owner)
    cancelled = _order(tenant_a, product)
    SalesNotesService.cancel_sales_order(cancelled, tenant_a.owner)

    resp = tenant_a.client.get("/api/v1/sales/orders/?status=DRAFT,CONFIRMED,PARTIALLY_CONVERTED")
    assert resp.status_code == 200, resp.data
    assert {row["id"] for row in _results(resp)} == {draft.id, confirmed.id}

    resp = tenant_a.client.get("/api/v1/sales/orders/?status=CONVERTED,CANCELLED")
    assert {row["id"] for row in _results(resp)} == {cancelled.id}

    resp = tenant_a.client.get("/api/v1/sales/orders/?status=confirmed")
    assert {row["id"] for row in _results(resp)} == {confirmed.id}


def test_tc_wp4_b01b_unknown_status_is_refused_not_ignored(tenant_a, product):
    _order(tenant_a, product)
    resp = tenant_a.client.get("/api/v1/sales/orders/?status=COMPLETED")
    assert resp.status_code == 400
    assert "COMPLETED" in str(resp.data)


# ---------------------------------------------------------------------------
# cancel a confirmed order (DEC-4)
# ---------------------------------------------------------------------------


def test_tc_wp4_b02_cancelling_a_confirmed_order_releases_its_stock(tenant_a, product):
    order = _order(tenant_a, product, qty=4)
    SalesNotesService.confirm_sales_order(order, tenant_a.owner)
    assert StockBalance.objects.get(company=tenant_a.company, product=product).reserved == Decimal("4")
    resp = tenant_a.client.post(f"/api/v1/sales/orders/{order.id}/cancel/")
    assert resp.status_code == 200, resp.data
    assert resp.data["status"] == "CANCELLED"
    assert StockBalance.objects.get(company=tenant_a.company, product=product).reserved == Decimal("0")


def test_tc_wp4_b03_cancel_needs_the_cancel_permission(tenant_a, product):
    order = _order(tenant_a, product)
    SalesNotesService.confirm_sales_order(order, tenant_a.owner)
    resp = tenant_a.staff_client.post(f"/api/v1/sales/orders/{order.id}/cancel/")
    assert resp.status_code == 403
    order.refresh_from_db()
    assert order.status == SalesOrder.Status.CONFIRMED


def test_tc_wp4_b04_a_partly_processed_order_cannot_be_cancelled(tenant_a, product):
    order = _order(tenant_a, product, qty=10)
    SalesNotesService.confirm_sales_order(order, tenant_a.owner)
    line = order.items.get()
    challan = SalesNotesService.convert_sales_order_to_challan(
        order, tenant_a.owner, line_quantities={line.pk: Decimal("4")}
    )
    SalesNotesService.complete_challan(challan, tenant_a.owner)
    resp = tenant_a.client.post(f"/api/v1/sales/orders/{order.id}/cancel/")
    assert resp.status_code == 400
    order.refresh_from_db()
    assert order.status == SalesOrder.Status.PARTIALLY_CONVERTED


def test_tc_wp4_b05_a_retried_confirm_reserves_once(tenant_a, product):
    order = _order(tenant_a, product, qty=3)
    headers = {"HTTP_IDEMPOTENCY_KEY": "confirm-once-0001"}
    first = tenant_a.client.post(f"/api/v1/sales/orders/{order.id}/confirm/", **headers)
    assert first.status_code == 200, first.data
    second = tenant_a.client.post(f"/api/v1/sales/orders/{order.id}/confirm/", **headers)
    assert second.status_code == 200, second.data
    assert StockBalance.objects.get(company=tenant_a.company, product=product).reserved == Decimal("3")


# ---------------------------------------------------------------------------
# fulfilment_state — the "Shipped" label
# ---------------------------------------------------------------------------


def _detail(tenant, order):
    resp = tenant.client.get(f"/api/v1/sales/orders/{order.id}/")
    assert resp.status_code == 200, resp.data
    return resp.data


def test_tc_wp8_b01_fulfilment_state_tracks_challan_and_invoice(tenant_a, product):
    order = _order(tenant_a, product, qty=2)
    SalesNotesService.confirm_sales_order(order, tenant_a.owner)
    assert _detail(tenant_a, order)["fulfilment_state"] == "none"

    challan = SalesNotesService.convert_sales_order_to_challan(order, tenant_a.owner)
    # A draft challan has not shipped anything yet.
    assert _detail(tenant_a, order)["fulfilment_state"] == "none"

    SalesNotesService.complete_challan(challan, tenant_a.owner)
    detail = _detail(tenant_a, order)
    assert detail["status"] == "CONVERTED"
    assert detail["fulfilment_state"] == "shipped_not_invoiced"

    SalesNotesService.convert_delivery_challan(challan, tenant_a.owner)
    assert _detail(tenant_a, order)["fulfilment_state"] == "invoiced"


def test_tc_wp8_b01b_a_direct_invoice_counts_as_invoiced(tenant_a, product):
    order = _order(tenant_a, product, qty=2)
    SalesNotesService.confirm_sales_order(order, tenant_a.owner)
    SalesNotesService.convert_sales_order(order, tenant_a.owner)
    assert _detail(tenant_a, order)["fulfilment_state"] == "invoiced"


def test_tc_wp8_b02_a_page_of_orders_costs_the_same_number_of_queries(tenant_a, product):
    def list_query_count():
        with CaptureQueriesContext(connection) as ctx:
            resp = tenant_a.client.get("/api/v1/sales/orders/?page_size=50")
            assert resp.status_code == 200
        return len(ctx)

    first = _order(tenant_a, product)
    SalesNotesService.confirm_sales_order(first, tenant_a.owner)
    one = list_query_count()
    for _ in range(8):
        extra = _order(tenant_a, product)
        SalesNotesService.confirm_sales_order(extra, tenant_a.owner)
        challan = SalesNotesService.convert_sales_order_to_challan(extra, tenant_a.owner)
        SalesNotesService.complete_challan(challan, tenant_a.owner)
    nine = list_query_count()
    assert nine == one, f"list cost {one} queries for 1 order and {nine} for 9"


# ---------------------------------------------------------------------------
# global search (H-16)
# ---------------------------------------------------------------------------


def _search(client, q):
    resp = client.get("/api/v1/search/", {"q": q})
    assert resp.status_code == 200, resp.data
    return resp.data


def test_tc_wp10_01_search_finds_orders_challans_and_routes(tenant_a, product):
    customer = make_customer(tenant_a.company, name="Zebra Stores")
    order = _order(tenant_a, product, customer=customer)
    SalesNotesService.confirm_sales_order(order, tenant_a.owner)
    order.refresh_from_db()
    challan = SalesNotesService.convert_sales_order_to_challan(order, tenant_a.owner)
    SalesNotesService.complete_challan(challan, tenant_a.owner)
    challan.refresh_from_db()
    route = DeliveryRoute.objects.create(
        company=tenant_a.company, number="RT-0099", vehicle_number="KA01XY9876", driver_name="Ganesh Rao",
        created_by=tenant_a.owner,
    )

    by_order = _search(tenant_a.client, order.number)
    assert [row["id"] for row in by_order["sales_orders"]] == [order.id]
    assert by_order["sales_orders"][0]["customer_name"] == "Zebra Stores"

    by_customer = _search(tenant_a.client, "Zebra")
    assert order.id in [row["id"] for row in by_customer["sales_orders"]]
    assert challan.id in [row["id"] for row in by_customer["delivery_challans"]]

    by_challan = _search(tenant_a.client, challan.number)
    assert [row["id"] for row in by_challan["delivery_challans"]] == [challan.id]

    for term in ("RT-0099", "KA01XY9876", "Ganesh"):
        found = _search(tenant_a.client, term)["delivery_routes"]
        assert [row["id"] for row in found] == [route.id], term


def test_tc_wp10_02_a_viewer_gets_no_sales_rows(tenant_a, product):
    from accounts.models import CompanyUser

    CompanyUser.objects.filter(company=tenant_a.company, user=tenant_a.staff).update(
        role=CompanyUser.Role.VIEWER, can_create_sales=False
    )
    order = _order(tenant_a, product)
    SalesNotesService.confirm_sales_order(order, tenant_a.owner)
    order.refresh_from_db()
    body = _search(tenant_a.staff_client, order.number)
    assert body["sales_orders"] == []
    assert body["delivery_challans"] == []
    assert body["delivery_routes"] == []


def test_tc_wp10_03_another_companys_documents_never_appear(tenant_a, tenant_b):
    other_product = make_product(tenant_b.company)
    add_stock(tenant_b, other_product, "10")
    foreign = _order(tenant_b, other_product)
    SalesNotesService.confirm_sales_order(foreign, tenant_b.owner)
    foreign.refresh_from_db()
    DeliveryRoute.objects.create(company=tenant_b.company, number="RT-FOREIGN", vehicle_number="MH12ZZ1111")
    body = _search(tenant_a.client, foreign.number)
    assert body["sales_orders"] == []
    assert _search(tenant_a.client, "RT-FOREIGN")["delivery_routes"] == []
    assert _search(tenant_a.client, "MH12ZZ1111")["delivery_routes"] == []


def test_tc_wp10_04_a_short_query_returns_every_key(tenant_a):
    body = _search(tenant_a.client, "a")
    for key in ("sales_orders", "delivery_challans", "delivery_routes"):
        assert body[key] == []
    assert DeliveryChallan.objects.count() == 0
