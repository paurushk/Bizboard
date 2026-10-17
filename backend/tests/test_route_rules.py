"""R4 (RT-01..04, RT-08, RT-09, RT-14, RT-15; OG-02, OG-03, OG-06..08, OG-11..13): route rules.

A route cannot be closed with stops still open, cannot be edited once it is on the road, cannot
share an order with another live route, can be cancelled with a reason, and an outcome that was
written down is not flipped without one. The office can record a delivery without the customer's
code (DEC-O1); the audit says so.
"""

import pytest

from core.models import AuditEvent as AuditLog
from sales.models import DeliveryRoute, DeliveryRouteStop, SalesOrder, SalesOrderItem
from tests.conftest import make_customer, make_product

pytestmark = pytest.mark.django_db

TODAY = "2026-10-14"


def _order(tenant, name="Shop", number=""):
    """A confirmed order with an address and a phone, so the planning rules have nothing to say about it."""
    customer = make_customer(tenant.company, name=name, phone="9876543210", pincode="560001")
    product = make_product(tenant.company, sku=f"R-{SalesOrder.objects.count()}", track_inventory=False)
    order = SalesOrder.objects.create(
        company=tenant.company, customer=customer, number=number,
        status=SalesOrder.Status.CONFIRMED, delivery_address="12 Market Road",
    )
    SalesOrderItem.objects.create(
        company=tenant.company, sales_order=order, product=product, quantity=1, unit_price=10,
    )
    return order


def _route(tenant, order_ids=(), **extra):
    resp = tenant.client.post(
        "/api/v1/sales/delivery-routes/",
        {"route_date": TODAY, "order_ids": list(order_ids), **extra},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    return DeliveryRoute.objects.get(pk=resp.data["id"])


def _start(tenant, route):
    resp = tenant.client.post(f"/api/v1/sales/delivery-routes/{route.id}/start/")
    assert resp.status_code == 200, resp.data
    return resp


def _mark(tenant, route, stop, status, **extra):
    return tenant.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/set-stop-status/",
        {"stop_id": stop.id, "status": status, **extra},
        format="json",
    )


def _complete(tenant, route):
    return tenant.client.post(f"/api/v1/sales/delivery-routes/{route.id}/complete/", {}, format="json")


# ---------------------------------------------------------------------------
# RT-01 — a route cannot close with stops still open
# ---------------------------------------------------------------------------


def test_tc_rt01_01_completing_with_a_pending_stop_is_refused_and_names_it(tenant_a):
    order = _order(tenant_a, number="SO-A")
    route = _route(tenant_a, [order.id])
    _start(tenant_a, route)
    resp = _complete(tenant_a, route)
    assert resp.status_code == 400
    assert "SO-A" in str(resp.data) and "no outcome" in str(resp.data)
    route.refresh_from_db()
    assert route.status == DeliveryRoute.Status.IN_TRANSIT


def test_tc_rt01_02_once_every_stop_has_an_outcome_the_route_closes(tenant_a):
    delivered, failed = _order(tenant_a, number="SO-1"), _order(tenant_a, number="SO-2")
    route = _route(tenant_a, [delivered.id, failed.id])
    _start(tenant_a, route)
    stops = list(route.stops.order_by("id"))
    assert _mark(tenant_a, route, stops[0], "DELIVERED", received_by_name="Asha", completion_source="OFFICE").status_code == 200
    assert _mark(tenant_a, route, stops[1], "FAILED").status_code == 200
    assert _complete(tenant_a, route).status_code == 200
    route.refresh_from_db()
    assert route.status == DeliveryRoute.Status.COMPLETED


def test_tc_rt01_03_a_route_with_no_stops_cannot_start(tenant_a):
    route = _route(tenant_a)
    resp = tenant_a.client.post(f"/api/v1/sales/delivery-routes/{route.id}/start/")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# RT-03 — a route on the road is locked
# ---------------------------------------------------------------------------


def test_tc_rt03_01_vehicle_driver_date_and_costs_are_locked_once_started(tenant_a):
    order = _order(tenant_a)
    route = _route(tenant_a, [order.id], vehicle_number="KA01AB1234", driver_name="Ramu")
    _start(tenant_a, route)
    for payload in (
        {"vehicle_number": "KA99ZZ0000"},
        {"driver_name": "Someone Else"},
        {"route_date": "2026-10-20"},
        {"estimated_logistics_cost": "500"},
        {"actual_logistics_cost": "500"},
    ):
        resp = tenant_a.client.patch(f"/api/v1/sales/delivery-routes/{route.id}/", payload, format="json")
        assert resp.status_code == 400, (payload, resp.data)
    route.refresh_from_db()
    assert route.vehicle_number == "KA01AB1234" and route.driver_name == "Ramu"


def test_tc_rt03_02_notes_can_still_be_edited_on_the_road_but_not_after_close(tenant_a):
    order = _order(tenant_a)
    route = _route(tenant_a, [order.id])
    _start(tenant_a, route)
    ok = tenant_a.client.patch(f"/api/v1/sales/delivery-routes/{route.id}/", {"notes": "gate 3"}, format="json")
    assert ok.status_code == 200, ok.data
    stop = route.stops.get()
    _mark(tenant_a, route, stop, "FAILED")
    assert _complete(tenant_a, route).status_code == 200
    bad = tenant_a.client.patch(f"/api/v1/sales/delivery-routes/{route.id}/", {"notes": "late edit"}, format="json")
    assert bad.status_code == 400


def test_tc_rt03_03_a_planned_route_can_change_everything(tenant_a):
    order = _order(tenant_a)
    route = _route(tenant_a, [order.id], vehicle_number="KA01AB1234")
    resp = tenant_a.client.patch(
        f"/api/v1/sales/delivery-routes/{route.id}/",
        {"vehicle_number": "KA02CD5678", "route_date": "2026-10-15"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["vehicle_number"] == "KA02CD5678"


def test_tc_rt03_04_a_patch_that_changes_nothing_on_a_started_route_is_accepted(tenant_a):
    order = _order(tenant_a)
    route = _route(tenant_a, [order.id], vehicle_number="KA01AB1234")
    _start(tenant_a, route)
    resp = tenant_a.client.patch(
        f"/api/v1/sales/delivery-routes/{route.id}/", {"vehicle_number": "KA01AB1234"}, format="json"
    )
    assert resp.status_code == 200, resp.data


# ---------------------------------------------------------------------------
# RT-04 — one order, one live route
# ---------------------------------------------------------------------------


def test_tc_rt04_01_an_order_on_a_planned_route_cannot_join_another(tenant_a):
    order = _order(tenant_a, number="SO-9")
    first = _route(tenant_a, [order.id])
    second = _route(tenant_a)
    resp = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{second.id}/add-orders/", {"order_ids": [order.id]}, format="json"
    )
    assert resp.status_code == 400
    assert "SO-9" in str(resp.data) and (first.number in str(resp.data))
    assert second.stops.count() == 0


def test_tc_rt04_02_an_order_already_delivered_cannot_be_routed_again(tenant_a):
    order = _order(tenant_a, number="SO-10")
    route = _route(tenant_a, [order.id])
    _start(tenant_a, route)
    stop = route.stops.get()
    assert _mark(tenant_a, route, stop, "DELIVERED", received_by_name="Asha", completion_source="OFFICE").status_code == 200
    assert _complete(tenant_a, route).status_code == 200
    other = _route(tenant_a)
    resp = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{other.id}/add-orders/", {"order_ids": [order.id]}, format="json"
    )
    assert resp.status_code == 400
    assert "Already delivered" in str(resp.data)


def test_tc_rt04_03_an_order_on_a_cancelled_route_is_free_again(tenant_a):
    order = _order(tenant_a)
    first = _route(tenant_a, [order.id])
    cancel = tenant_a.client.post(f"/api/v1/sales/delivery-routes/{first.id}/cancel/", {}, format="json")
    assert cancel.status_code == 200, cancel.data
    second = _route(tenant_a, [order.id])
    assert second.stops.count() == 1


def test_tc_rt04_03b_a_failed_stop_leaves_the_order_free_to_go_out_again(tenant_a):
    order = _order(tenant_a)
    first = _route(tenant_a, [order.id])
    _start(tenant_a, first)
    assert _mark(tenant_a, first, first.stops.get(), "FAILED").status_code == 200
    second = _route(tenant_a, [order.id])
    assert second.stops.count() == 1


def test_tc_rt04_04_one_bad_order_adds_none(tenant_a):
    good, taken = _order(tenant_a, number="SO-G"), _order(tenant_a, number="SO-T")
    _route(tenant_a, [taken.id])
    route = _route(tenant_a)
    resp = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/add-orders/", {"order_ids": [good.id, taken.id]}, format="json"
    )
    assert resp.status_code == 400
    assert route.stops.count() == 0


def test_tc_rt04_05_the_same_order_listed_twice_on_the_same_route_is_added_once(tenant_a):
    order = _order(tenant_a)
    route = _route(tenant_a)
    resp = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/add-orders/", {"order_ids": [order.id]}, format="json"
    )
    assert resp.status_code == 200
    again = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/add-orders/", {"order_ids": [order.id]}, format="json"
    )
    assert again.status_code == 200
    assert route.stops.count() == 1


# ---------------------------------------------------------------------------
# RT-09 — vehicle and driver clash, warning only
# ---------------------------------------------------------------------------


def test_tc_rt09_01_same_vehicle_or_driver_the_same_day_warns(tenant_a):
    first = _route(tenant_a, [_order(tenant_a).id], vehicle_number="KA01AB1234", driver_name="Ramu")
    second = tenant_a.client.post(
        "/api/v1/sales/delivery-routes/",
        {"route_date": TODAY, "vehicle_number": "ka01ab1234", "driver_name": "RAMU"},
        format="json",
    )
    assert second.status_code == 201, second.data
    codes = {w["code"] for w in second.data["warnings"]}
    assert codes == {"vehicle_clash", "driver_clash"}
    assert all(w["route"] == first.pk for w in second.data["warnings"])


def test_tc_rt09_02_a_different_day_or_a_cancelled_route_does_not_warn(tenant_a):
    first = _route(tenant_a, vehicle_number="KA01AB1234")
    other_day = tenant_a.client.post(
        "/api/v1/sales/delivery-routes/",
        {"route_date": "2026-10-15", "vehicle_number": "KA01AB1234"},
        format="json",
    )
    assert other_day.data["warnings"] == []
    tenant_a.client.post(f"/api/v1/sales/delivery-routes/{first.id}/cancel/", {}, format="json")
    same_day = _route(tenant_a, vehicle_number="KA01AB1234")
    detail = tenant_a.client.get(f"/api/v1/sales/delivery-routes/{same_day.id}/")
    assert detail.data["warnings"] == []


# ---------------------------------------------------------------------------
# RT-15 / RT-14 — numbers and filters
# ---------------------------------------------------------------------------


def test_tc_rt15_01_a_route_has_a_number_from_creation(tenant_a):
    first, second = _route(tenant_a), _route(tenant_a)
    assert first.number and second.number and first.number != second.number
    _start_order = _order(tenant_a)
    tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{first.id}/add-orders/", {"order_ids": [_start_order.id]}, format="json"
    )
    _start(tenant_a, first)
    first.refresh_from_db()
    assert first.number  # starting does not renumber


def test_tc_rt14_01_list_filters(tenant_a):
    a = _route(tenant_a, vehicle_number="KA01AB1234", driver_name="Ramu")
    b = tenant_a.client.post(
        "/api/v1/sales/delivery-routes/",
        {"route_date": "2026-10-20", "vehicle_number": "MH12ZZ9999", "driver_name": "Shyam"},
        format="json",
    ).data["id"]

    def ids(query):
        resp = tenant_a.client.get(f"/api/v1/sales/delivery-routes/?{query}")
        assert resp.status_code == 200, resp.data
        rows = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        return {row["id"] for row in rows}

    assert ids("vehicle=mh12") == {b}
    assert ids("driver=ramu") == {a.id}
    assert ids("q=KA01") == {a.id}
    assert ids("date_from=2026-10-18") == {b}
    assert ids("date_to=2026-10-15") == {a.id}
    assert ids("status=PLANNED,IN_TRANSIT") == {a.id, b}
    assert tenant_a.client.get("/api/v1/sales/delivery-routes/?status=BOGUS").status_code == 400
    assert tenant_a.client.get("/api/v1/sales/delivery-routes/?date_from=not-a-date").status_code == 400


# ---------------------------------------------------------------------------
# RT-02 / OG-07 — cancel a route
# ---------------------------------------------------------------------------


def test_tc_rt02_01_a_planned_route_cancels_without_a_reason(tenant_a):
    order = _order(tenant_a)
    route = _route(tenant_a, [order.id])
    resp = tenant_a.client.post(f"/api/v1/sales/delivery-routes/{route.id}/cancel/", {}, format="json")
    assert resp.status_code == 200, resp.data
    assert resp.data["status"] == "CANCELLED"


def test_tc_rt02_02_a_route_on_the_road_needs_a_reason(tenant_a):
    order = _order(tenant_a)
    route = _route(tenant_a, [order.id])
    _start(tenant_a, route)
    refused = tenant_a.client.post(f"/api/v1/sales/delivery-routes/{route.id}/cancel/", {}, format="json")
    assert refused.status_code == 400
    ok = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/cancel/", {"reason": "Van broke down"}, format="json"
    )
    assert ok.status_code == 200, ok.data
    route.refresh_from_db()
    assert "Van broke down" in route.notes
    assert AuditLog.objects.filter(
        company=tenant_a.company, entity_type="DeliveryRoute", entity_id=str(route.pk),
        description="delivery_route.cancelled",
    ).exists()


def test_tc_rt02_03_pending_stops_are_released_and_delivered_ones_block_cancel(tenant_a):
    first, second = _order(tenant_a), _order(tenant_a)
    route = _route(tenant_a, [first.id, second.id])
    _start(tenant_a, route)
    stops = list(route.stops.order_by("id"))
    _mark(tenant_a, route, stops[0], "DELIVERED", received_by_name="Asha", completion_source="OFFICE")
    refused = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/cancel/", {"reason": "changed my mind"}, format="json"
    )
    assert refused.status_code == 400
    assert "already delivered" in str(refused.data)


def test_tc_rt02_03b_pending_orders_go_back_to_being_routable(tenant_a):
    order = _order(tenant_a)
    route = _route(tenant_a, [order.id])
    _start(tenant_a, route)
    tenant_a.client.post(f"/api/v1/sales/delivery-routes/{route.id}/cancel/", {"reason": "weather"}, format="json")
    assert _route(tenant_a, [order.id]).stops.count() == 1


def test_tc_rt02_04_a_finished_route_cannot_be_cancelled(tenant_a):
    order = _order(tenant_a)
    route = _route(tenant_a, [order.id])
    _start(tenant_a, route)
    _mark(tenant_a, route, route.stops.get(), "FAILED")
    _complete(tenant_a, route)
    resp = tenant_a.client.post(f"/api/v1/sales/delivery-routes/{route.id}/cancel/", {"reason": "x y z"}, format="json")
    assert resp.status_code == 400


def test_tc_rt02_04b_money_collected_blocks_cancel(tenant_a):
    order = _order(tenant_a)
    other = _order(tenant_a)
    route = _route(tenant_a, [order.id, other.id])
    _start(tenant_a, route)
    stop = route.stops.order_by("id").first()
    DeliveryRouteStop.objects.filter(pk=stop.pk).update(collected_cash=100)
    resp = tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/cancel/", {"reason": "oops"}, format="json"
    )
    assert resp.status_code == 400
    assert "Money was collected" in str(resp.data)


def test_tc_rt02_05_cancel_needs_the_cancel_permission(tenant_a):
    order = _order(tenant_a)
    route = _route(tenant_a, [order.id])
    resp = tenant_a.staff_client.post(f"/api/v1/sales/delivery-routes/{route.id}/cancel/", {}, format="json")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# RT-08 / OG-11 — an outcome is not flipped silently
# ---------------------------------------------------------------------------


def test_tc_rt08_01_changing_a_recorded_outcome_needs_a_reason(tenant_a):
    order = _order(tenant_a)
    route = _route(tenant_a, [order.id])
    _start(tenant_a, route)
    stop = route.stops.get()
    assert _mark(tenant_a, route, stop, "DELIVERED", received_by_name="Asha", completion_source="OFFICE").status_code == 200
    refused = _mark(tenant_a, route, stop, "FAILED")
    assert refused.status_code == 400
    assert "reason" in str(refused.data)
    stop.refresh_from_db()
    assert stop.status == "DELIVERED"


def test_tc_rt08_02_with_a_reason_it_changes_and_the_audit_keeps_who_and_why(tenant_a):
    order = _order(tenant_a)
    route = _route(tenant_a, [order.id])
    _start(tenant_a, route)
    stop = route.stops.get()
    _mark(tenant_a, route, stop, "DELIVERED", received_by_name="Asha", completion_source="OFFICE")
    resp = _mark(tenant_a, route, stop, "RETURNED", reason="Customer refused at the door")
    assert resp.status_code == 200, resp.data
    stop.refresh_from_db()
    assert stop.status == "RETURNED"
    assert "Customer refused at the door" in stop.notes
    event = AuditLog.objects.filter(
        company=tenant_a.company, entity_type="DeliveryRoute", entity_id=str(route.pk),
        description="delivery_route.stop_status",
    ).order_by("-id").first()
    assert event is not None
    assert event.user_id == tenant_a.owner.id
    assert event.metadata["from"] == "DELIVERED" and event.metadata["to"] == "RETURNED"
    assert event.metadata["reason"] == "Customer refused at the door"


def test_tc_rt08_03_first_outcome_and_unchanged_status_need_no_reason(tenant_a):
    order = _order(tenant_a)
    route = _route(tenant_a, [order.id])
    _start(tenant_a, route)
    stop = route.stops.get()
    assert _mark(tenant_a, route, stop, "FAILED").status_code == 200
    assert _mark(tenant_a, route, stop, "FAILED").status_code == 200  # same status: not a change


def test_tc_rt08_04_a_stop_cannot_go_back_to_pending(tenant_a):
    order = _order(tenant_a)
    route = _route(tenant_a, [order.id])
    _start(tenant_a, route)
    stop = route.stops.get()
    _mark(tenant_a, route, stop, "FAILED")
    assert _mark(tenant_a, route, stop, "PENDING", reason="mistake here").status_code == 400


# ---------------------------------------------------------------------------
# OG-13 / DEC-O1 — the office records a delivery without the customer's code
# ---------------------------------------------------------------------------


def test_tc_og13_01_office_delivery_needs_no_code_and_is_marked_and_audited(tenant_a):
    order = _order(tenant_a)
    route = _route(tenant_a, [order.id])
    _start(tenant_a, route)
    stop = route.stops.get()
    resp = _mark(tenant_a, route, stop, "DELIVERED", received_by_name="Asha", completion_source="OFFICE")
    assert resp.status_code == 200, resp.data
    stop.refresh_from_db()
    assert stop.status == "DELIVERED" and stop.completion_source == "OFFICE"
    event = AuditLog.objects.filter(
        company=tenant_a.company, entity_type="DeliveryRoute", entity_id=str(route.pk),
        description="delivery_route.stop_status",
    ).first()
    assert event.metadata["recorded_by_office"] is True and event.user_id == tenant_a.owner.id


def test_tc_og13_02_a_code_that_was_issued_is_cleared_by_an_office_delivery(tenant_a):
    from accounts.otp_utils import hash_otp

    order = _order(tenant_a)
    route = _route(tenant_a, [order.id])
    _start(tenant_a, route)
    stop = route.stops.get()
    DeliveryRouteStop.objects.filter(pk=stop.pk).update(delivery_otp_hash=hash_otp("123456"))
    # the driver path would be locked out without the code ...
    blocked = _mark(tenant_a, route, stop, "DELIVERED", received_by_name="Asha", completion_source="PHONE")
    assert blocked.status_code == 400
    # ... and the office can still record the delivery, which spends the issued code.
    ok = _mark(tenant_a, route, stop, "DELIVERED", received_by_name="Asha", completion_source="OFFICE")
    assert ok.status_code == 200, ok.data
    stop.refresh_from_db()
    assert stop.delivery_otp_hash == ""


def test_tc_og13_03_the_phone_path_still_asks_for_a_code_when_one_was_issued(tenant_a):
    from accounts.otp_utils import hash_otp

    order = _order(tenant_a)
    route = _route(tenant_a, [order.id])
    _start(tenant_a, route)
    stop = route.stops.get()
    DeliveryRouteStop.objects.filter(pk=stop.pk).update(delivery_otp_hash=hash_otp("123456"))
    wrong = _mark(tenant_a, route, stop, "DELIVERED", received_by_name="Asha", completion_source="PHONE", otp_code="000000")
    assert wrong.status_code == 400
    right = _mark(tenant_a, route, stop, "DELIVERED", received_by_name="Asha", completion_source="PHONE", otp_code="123456")
    assert right.status_code == 200, right.data
