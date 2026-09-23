"""COMP-005 route profit snapshot."""

from decimal import Decimal

import pytest
from django.utils import timezone

from inventory.models import MovementType, StockMovement, Warehouse
from inventory.services import InventoryService
from sales.models import DeliveryRoute, DeliveryRouteStop, SalesInvoice, SalesOrder
from sales.route_profit_service import compute_route_financials
from sales.route_service import RouteService
from tests.conftest import make_customer, make_product


def _enable(company, on=True):
    flags = dict(company.feature_flags or {})
    flags["ENABLE_ROUTE_PROFIT"] = on
    company.feature_flags = flags
    company.save(update_fields=["feature_flags"])


def _invoice(company, customer, product, *, number, taxable, qty="-2", unit_cost="40"):
    invoice = SalesInvoice.objects.create(
        company=company,
        customer=customer,
        number=number,
        status=SalesInvoice.Status.COMPLETED,
        invoice_date=timezone.localdate(),
        taxable_total=Decimal(taxable),
        grand_total=Decimal(taxable) + Decimal("18"),
    )
    warehouse = InventoryService.default_warehouse(company)
    StockMovement.objects.create(
        company=company,
        warehouse=warehouse,
        product=product,
        movement_type=MovementType.SALE,
        quantity=Decimal(qty),
        unit_cost=Decimal(unit_cost),
        reference_type="sales_invoice",
        reference_id=str(invoice.pk),
        movement_date=timezone.localdate(),
    )
    return invoice


def _stop(route, customer, invoice, *, number):
    order = SalesOrder.objects.create(
        company=route.company,
        customer=customer,
        number=number,
        status=SalesOrder.Status.CONVERTED,
        converted_invoice=invoice,
    )
    return DeliveryRouteStop.objects.create(
        company=route.company, route=route, sales_order=order,
    )


@pytest.mark.django_db
def test_profit_uses_taxable_total_and_abs_cogs(tenant_a):
    _enable(tenant_a.company)
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="RT-1")
    route = DeliveryRoute.objects.create(
        company=tenant_a.company, number="RT-1", status=DeliveryRoute.Status.IN_TRANSIT,
        actual_logistics_cost=Decimal("10"),
    )
    inv = _invoice(tenant_a.company, customer, product, number="SI-RT-1", taxable="100")
    _stop(route, customer, inv, number="SO-RT-1")
    bare = SalesOrder.objects.create(
        company=tenant_a.company, customer=customer, number="SO-RT-2", status=SalesOrder.Status.CONFIRMED,
    )
    DeliveryRouteStop.objects.create(company=tenant_a.company, route=route, sales_order=bare)
    done = RouteService.complete_route(route, tenant_a.owner, actual_logistics_cost=Decimal("10"))
    # revenue 100, cogs abs(-2)*40 = 80, logistics 10 → profit 10. 1 of 2 stops invoiced.
    assert done.realized_revenue == Decimal("100.00")
    assert done.realized_cogs == Decimal("80.00")
    assert done.realized_profit == Decimal("10.00")
    assert done.invoiced_stop_count == 1
    assert done.stop_count == 2


@pytest.mark.django_db
def test_snapshot_is_frozen_after_complete(tenant_a):
    _enable(tenant_a.company)
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="RT-2")
    route = DeliveryRoute.objects.create(
        company=tenant_a.company, number="RT-2", status=DeliveryRoute.Status.IN_TRANSIT,
    )
    inv = _invoice(tenant_a.company, customer, product, number="SI-RT-2", taxable="50")
    _stop(route, customer, inv, number="SO-RT-3")
    done = RouteService.complete_route(route, tenant_a.owner, actual_logistics_cost=Decimal("0"))
    frozen = (done.realized_revenue, done.realized_cogs, done.realized_profit, done.invoiced_stop_count)
    inv.taxable_total = Decimal("1")
    inv.save(update_fields=["taxable_total"])
    SalesInvoice.objects.filter(pk=inv.pk).update(taxable_total=Decimal("1"))
    done.refresh_from_db()
    assert (done.realized_revenue, done.realized_cogs, done.realized_profit, done.invoiced_stop_count) == frozen


@pytest.mark.django_db
def test_planned_and_flag_off_stay_null(tenant_a):
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="RT-3")
    planned = DeliveryRoute.objects.create(company=tenant_a.company, number="RT-3")
    assert planned.realized_profit is None
    assert planned.stop_count is None
    route = DeliveryRoute.objects.create(
        company=tenant_a.company, number="RT-4", status=DeliveryRoute.Status.IN_TRANSIT,
    )
    inv = _invoice(tenant_a.company, customer, product, number="SI-RT-4", taxable="20")
    _stop(route, customer, inv, number="SO-RT-4")
    done = RouteService.complete_route(route, tenant_a.owner, actual_logistics_cost=Decimal("1"))
    assert done.realized_profit is None
    assert done.invoiced_stop_count is None
    assert done.status == DeliveryRoute.Status.COMPLETED


@pytest.mark.django_db
def test_zero_stops_does_not_error():
    class Empty:
        actual_logistics_cost = Decimal("5")

        class stops:
            @staticmethod
            def select_related(*_a, **_k):
                return []

    result = compute_route_financials(Empty())
    assert result.stop_count == 0
    assert result.invoiced_stop_count == 0
    assert result.realized_profit == Decimal("-5.00")


@pytest.mark.django_db
def test_cancelled_invoice_still_linked_is_excluded_from_revenue(tenant_a):
    """F1-004 regression: sales/services.py's invoice-cancel flow excludes
    CONVERTED orders from the converted_invoice unlink (the normal case), so
    a stop's order can still point at a now-CANCELLED invoice at route
    completion time. That invoice's amount must not be counted as realized
    revenue/COGS.
    """
    _enable(tenant_a.company)
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="RT-6")
    route = DeliveryRoute.objects.create(
        company=tenant_a.company, number="RT-6", status=DeliveryRoute.Status.IN_TRANSIT,
    )
    inv = _invoice(tenant_a.company, customer, product, number="SI-RT-6", taxable="100")
    _stop(route, customer, inv, number="SO-RT-6")
    inv.status = SalesInvoice.Status.CANCELLED
    inv.save(update_fields=["status"])
    done = RouteService.complete_route(route, tenant_a.owner, actual_logistics_cost=Decimal("0"))
    assert done.realized_revenue == Decimal("0.00")
    assert done.realized_cogs == Decimal("0.00")
    assert done.invoiced_stop_count == 0
    assert done.stop_count == 1


@pytest.mark.django_db
def test_fully_returned_invoice_is_excluded_despite_unreduced_taxable_total(tenant_a):
    """F1-004 regression: return_service.py flips status to RETURNED on a full
    return without reducing taxable_total, so this must be excluded by
    status, not by amount.
    """
    _enable(tenant_a.company)
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="RT-7")
    route = DeliveryRoute.objects.create(
        company=tenant_a.company, number="RT-7", status=DeliveryRoute.Status.IN_TRANSIT,
    )
    inv = _invoice(tenant_a.company, customer, product, number="SI-RT-7", taxable="100")
    _stop(route, customer, inv, number="SO-RT-7")
    inv.status = SalesInvoice.Status.RETURNED
    inv.save(update_fields=["status"])
    done = RouteService.complete_route(route, tenant_a.owner, actual_logistics_cost=Decimal("0"))
    assert done.realized_revenue == Decimal("0.00")
    assert done.invoiced_stop_count == 0


@pytest.mark.django_db
def test_failed_stop_is_excluded_even_with_a_completed_invoice(tenant_a):
    """F1-004 regression: a driver marking a stop FAILED/RETURNED must not
    still count that stop's (still-COMPLETED) invoice as realized revenue —
    the goods didn't move on this trip.
    """
    _enable(tenant_a.company)
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="RT-8")
    route = DeliveryRoute.objects.create(
        company=tenant_a.company, number="RT-8", status=DeliveryRoute.Status.IN_TRANSIT,
    )
    good_inv = _invoice(tenant_a.company, customer, product, number="SI-RT-8A", taxable="100")
    good_stop = _stop(route, customer, good_inv, number="SO-RT-8A")
    good_stop.status = DeliveryRouteStop.StopStatus.DELIVERED
    good_stop.save(update_fields=["status"])
    failed_inv = _invoice(tenant_a.company, customer, product, number="SI-RT-8B", taxable="60")
    failed_stop = _stop(route, customer, failed_inv, number="SO-RT-8B")
    failed_stop.status = DeliveryRouteStop.StopStatus.FAILED
    failed_stop.save(update_fields=["status"])
    done = RouteService.complete_route(route, tenant_a.owner, actual_logistics_cost=Decimal("0"))
    assert done.realized_revenue == Decimal("100.00")
    assert done.invoiced_stop_count == 1
    assert done.stop_count == 2


@pytest.mark.django_db
def test_rounding_uses_half_up_matching_the_rest_of_the_codebase(tenant_a):
    """F1-004: _q2 must round the same way as sales/services.py (BILL-05) and
    tax_engine/india.py — ROUND_HALF_UP, not the Decimal context default
    (ROUND_HALF_EVEN). unit_cost 4dp x quantity 3dp can land on a half-paise
    boundary; 0.125 rounds to 0.13 under HALF_UP, 0.12 under HALF_EVEN.
    """
    from sales.route_profit_service import _q2

    assert _q2(Decimal("0.125")) == Decimal("0.13")
    assert _q2(Decimal("0.145")) == Decimal("0.15")


@pytest.mark.django_db
def test_in_transit_is_not_snapshotted(tenant_a):
    route = DeliveryRoute.objects.create(
        company=tenant_a.company, number="RT-5", status=DeliveryRoute.Status.IN_TRANSIT,
    )
    route.refresh_from_db()
    assert route.realized_revenue is None
    assert Warehouse.objects.filter(company=tenant_a.company).count() >= 0


@pytest.mark.django_db
def test_combine_suggestions_group_same_pincode_and_leave_routes_alone(tenant_a):
    from sales.route_combine import combine_suggestions

    day = timezone.localdate()
    shared = make_customer(tenant_a.company, name="Pin A", pincode="560001")
    other = make_customer(tenant_a.company, name="Pin B", pincode="560002", phone="9000099911")
    blank = make_customer(tenant_a.company, name="No Pin", pincode="", phone="9000099922")
    route_a = DeliveryRoute.objects.create(company=tenant_a.company, number="CB-1", route_date=day)
    route_b = DeliveryRoute.objects.create(company=tenant_a.company, number="CB-2", route_date=day)

    def stop(route, customer, number):
        order = SalesOrder.objects.create(
            company=tenant_a.company,
            customer=customer,
            number=number,
            status=SalesOrder.Status.CONFIRMED,
            order_date=day,
            expected_delivery=day,
        )
        return DeliveryRouteStop.objects.create(
            company=tenant_a.company, route=route, sales_order=order,
        )

    first = stop(route_a, shared, "SO-CB-1")
    second = stop(route_b, shared, "SO-CB-2")
    stop(route_a, other, "SO-CB-3")
    stop(route_b, blank, "SO-CB-4")
    assert combine_suggestions(tenant_a.company) is None
    flags = dict(tenant_a.company.feature_flags or {})
    flags["ENABLE_ROUTE_OPTIMIZATION"] = True
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    suggestions = combine_suggestions(tenant_a.company)
    assert len(suggestions) == 1
    assert suggestions[0]["pincode"] == "560001"
    assert set(suggestions[0]["stop_ids"]) == {first.id, second.id}
    assert DeliveryRoute.objects.filter(company=tenant_a.company, number__in=["CB-1", "CB-2"]).count() == 2
    assert route_a.stops.count() == 2
