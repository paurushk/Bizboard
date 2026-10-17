"""R3 (H-14, DEC-5): a failed delivery on an already invoiced order warns, and creates nothing.

The invoice stands until someone records a sales return; the route says which invoice that is.
"""

import pytest

from sales.models import DeliveryChallanReturn, DeliveryRoute, DeliveryRouteStop, SalesInvoice, SalesOrder
from sales.notes_services import SalesNotesService
from sales.services import SalesService
from tests.conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db


def _invoiced_order(tenant, *, complete_invoice=True):
    product = make_product(tenant.company)
    add_stock(tenant, product, "50")
    customer = make_customer(tenant.company, name="Invoiced Co")
    resp = tenant.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id, "invoice_type": "NON_GST",
            "items": [{"product": product.id, "quantity": "3", "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )
    order = SalesOrder.objects.get(pk=resp.data["id"])
    SalesNotesService.confirm_sales_order(order, tenant.owner)
    challan = SalesNotesService.complete_challan(
        SalesNotesService.convert_sales_order_to_challan(order, tenant.owner), tenant.owner
    )
    invoice = SalesNotesService.convert_delivery_challan(challan, tenant.owner)
    if complete_invoice:
        SalesService.complete(invoice, tenant.owner)
        invoice.refresh_from_db()
    order.refresh_from_db()
    return order, invoice


def _route_with_stop(tenant, order, status=DeliveryRoute.Status.IN_TRANSIT):
    route = DeliveryRoute.objects.create(company=tenant.company, route_date="2026-10-14", status=status)
    stop = DeliveryRouteStop.objects.create(company=tenant.company, route=route, sales_order=order)
    return route, stop


def _mark(tenant, route, stop, status):
    return tenant.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/set-stop-status/",
        {"stop_id": stop.id, "status": status},
        format="json",
    )


def test_tc_wp7_01_failed_stop_names_the_live_invoice(tenant_a):
    order, invoice = _invoiced_order(tenant_a)
    route, stop = _route_with_stop(tenant_a, order)
    resp = _mark(tenant_a, route, stop, "FAILED")
    assert resp.status_code == 200, resp.data
    active = resp.data["stops"][0]["active_invoice"]
    assert active == {"id": invoice.pk, "number": invoice.number}
    # Warn only: nothing was created or reversed.
    assert DeliveryChallanReturn.objects.filter(company=tenant_a.company).count() == 0
    assert SalesInvoice.objects.get(pk=invoice.pk).status == SalesInvoice.Status.COMPLETED


@pytest.mark.parametrize("status", ["REJECTED", "RETURNED"])
def test_tc_wp7_01b_rejected_and_returned_stops_warn_too(tenant_a, status):
    order, invoice = _invoiced_order(tenant_a)
    route, stop = _route_with_stop(tenant_a, order)
    resp = _mark(tenant_a, route, stop, status)
    assert resp.status_code == 200, resp.data
    assert resp.data["stops"][0]["active_invoice"]["number"] == invoice.number


def test_tc_wp7_02_no_invoice_no_warning(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company, name="Plain Co")
    resp = tenant_a.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id, "invoice_type": "NON_GST",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )
    order = SalesOrder.objects.get(pk=resp.data["id"])
    SalesNotesService.confirm_sales_order(order, tenant_a.owner)
    route, stop = _route_with_stop(tenant_a, order)
    resp = _mark(tenant_a, route, stop, "FAILED")
    assert resp.status_code == 200, resp.data
    assert resp.data["stops"][0]["active_invoice"] is None


def test_tc_wp7_03_a_cancelled_invoice_no_longer_warns(tenant_a):
    order, invoice = _invoiced_order(tenant_a)
    SalesInvoice.objects.filter(pk=invoice.pk).update(status=SalesInvoice.Status.CANCELLED)
    route, stop = _route_with_stop(tenant_a, order)
    resp = _mark(tenant_a, route, stop, "FAILED")
    assert resp.status_code == 200, resp.data
    assert resp.data["stops"][0]["active_invoice"] is None


def test_tc_wp7_04_an_invoiced_challan_opens_no_return_and_does_not_fail(tenant_a):
    """The challan return is refused once the challan is converted: the stop must not 500 or open one."""
    order, _invoice = _invoiced_order(tenant_a, complete_invoice=False)
    route, stop = _route_with_stop(tenant_a, order)
    resp = _mark(tenant_a, route, stop, "FAILED")
    assert resp.status_code == 200, resp.data
    assert DeliveryChallanReturn.objects.filter(company=tenant_a.company).count() == 0
    # a draft invoice is not a standing sale yet: no warning for it
    assert resp.data["stops"][0]["active_invoice"] is None


def test_tc_wp7_05_a_delivered_stop_carries_no_warning(tenant_a):
    order, _invoice = _invoiced_order(tenant_a)
    route, stop = _route_with_stop(tenant_a, order)
    resp = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/set-stop-status/",
        {"stop_id": stop.id, "status": "DELIVERED", "received_by_name": "Asha"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["stops"][0]["active_invoice"] is None
