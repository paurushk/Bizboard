"""J-ROUTE-P7-BEAT. A delivered stop records who received the goods. It does not post stock."""

import pytest

from core.invariants import assert_all_invariants
from inventory.models import StockMovement
from payments.models import CustomerReceipt
from sales.models import DeliveryRoute, DeliveryRouteStop, SalesOrder, SalesOrderItem
from sales.pod_slip import render_pod_pdf
from sales.route_service import RouteService
from tests.conftest import make_customer, make_product

from core.exceptions import BusinessRuleError

pytestmark = pytest.mark.django_db


def test_j_route_p7_beat_requires_receiver_and_does_not_post(tenant_a, tenant_b):
    """J-ROUTE-P7-BEAT."""
    customer = make_customer(tenant_a.company)
    other = make_customer(tenant_a.company, name="Other shop")
    product = make_product(tenant_a.company)
    order = SalesOrder.objects.create(company=tenant_a.company, customer=customer)
    SalesOrderItem.objects.create(
        company=tenant_a.company, sales_order=order, product=product, quantity=1, unit_price=10,
    )
    route = DeliveryRoute.objects.create(
        company=tenant_a.company, route_date="2026-09-26", status=DeliveryRoute.Status.IN_TRANSIT,
    )
    stop = DeliveryRouteStop.objects.create(company=tenant_a.company, route=route, sales_order=order)
    before = StockMovement.objects.filter(company=tenant_a.company).count()
    receipts_before = CustomerReceipt.objects.filter(company=tenant_a.company).count()
    with pytest.raises(BusinessRuleError):
        RouteService.set_stop_status(route, stop, "DELIVERED", tenant_a.owner)
    RouteService.set_stop_status(route, stop, "DELIVERED", tenant_a.owner, received_by_name="R")
    stop.refresh_from_db()
    assert stop.received_by_name == "R"
    assert StockMovement.objects.filter(company=tenant_a.company).count() == before
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == receipts_before
    mismatch = CustomerReceipt.objects.create(company=tenant_a.company, customer=other, amount=10)
    fresh = DeliveryRouteStop.objects.create(
        company=tenant_a.company,
        route=route,
        sales_order=SalesOrder.objects.create(company=tenant_a.company, customer=customer),
    )
    with pytest.raises(BusinessRuleError):
        RouteService.set_stop_status(
            route, fresh, "DELIVERED", tenant_a.owner, received_by_name="R", customer_receipt=mismatch,
        )
    planned = DeliveryRoute.objects.create(company=tenant_a.company, route_date="2026-09-26")
    pending = DeliveryRouteStop.objects.create(
        company=tenant_a.company,
        route=planned,
        sales_order=SalesOrder.objects.create(company=tenant_a.company, customer=customer),
    )
    with pytest.raises(BusinessRuleError):
        RouteService.set_stop_status(planned, pending, "DELIVERED", tenant_a.owner, received_by_name="R")
    route.status = DeliveryRoute.Status.COMPLETED
    route.save(update_fields=["status"])
    stop.refresh_from_db()
    assert render_pod_pdf(stop).startswith(b"%PDF")
    resp = tenant_a.client.get(f"/api/v1/sales/delivery-routes/{route.id}/stops/{stop.id}/pod.pdf")
    assert resp.status_code == 200
    foreign = tenant_b.client.get(f"/api/v1/sales/delivery-routes/{route.id}/stops/{stop.id}/pod.pdf")
    assert foreign.status_code == 404
    assert_all_invariants(tenant_a.company)
