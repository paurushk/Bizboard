"""R7 (PL-02, PL-04..PL-10, PL-33): the server enforces what the planning table shows.

Blocks stop an order going on a route (all or nothing), warnings need an acknowledgement with a reason
that is kept, drafts only go with an owner's reason, starting a route checks everything again, and the
candidate list, the add rule and the start rule always agree.
"""

from decimal import Decimal
from unittest import mock

import pytest

from core.exceptions import BusinessRuleError
from core.models import AuditEvent
from masters.models import Customer
from sales.models import (
    DeliveryRoute,
    DeliveryRouteStop,
    RouteStopAcknowledgement,
    SalesOrder,
    SalesOrderItem,
)
from sales.notes_services import SalesNotesService
from sales.route_planning import Viewer
from sales.route_service import RouteService
from tests.conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db

TODAY = "2026-10-14"
STAFF = Viewer(role="SALES_STAFF")
MANAGER = Viewer(role="MANAGER")


def _order(tenant, *, status=SalesOrder.Status.CONFIRMED, address="12 Market Road", customer=None, product=None, qty="2", price="100", **extra):
    customer = customer or make_customer(tenant.company, name=f"Cust {SalesOrder.objects.count()}", phone="9876543210", pincode="560001")
    product = product or make_product(tenant.company, sku=f"E-{SalesOrder.objects.count()}", track_inventory=False)
    order = SalesOrder.objects.create(
        company=tenant.company, customer=customer, status=status, delivery_address=address,
        grand_total=Decimal(qty) * Decimal(price), number=f"SO-{SalesOrder.objects.count() + 1}", **extra,
    )
    SalesOrderItem.objects.create(
        company=tenant.company, sales_order=order, product=product, quantity=Decimal(qty), unit_price=Decimal(price),
    )
    return order


def _route(tenant, **extra):
    return DeliveryRoute.objects.create(
        company=tenant.company, route_date=TODAY, number=f"RT-P{DeliveryRoute.objects.count() + 1}", **extra
    )


def _add(tenant, route, order_ids, *, acks=None, client=None):
    return (client or tenant.client).post(
        f"/api/v1/sales/delivery-routes/{route.id}/add-orders/",
        {"order_ids": list(order_ids), **({"acknowledgements": acks} if acks is not None else {})},
        format="json",
    )


def _details(resp):
    return resp.data["error"].get("details", {})


# ---------------------------------------------------------------------------
# PL-04 — Blocks refuse, all or nothing
# ---------------------------------------------------------------------------


def test_tc_pl04_01_a_blocked_order_is_refused_with_its_code_and_nothing_is_added(tenant_a):
    good = _order(tenant_a)
    cancelled = _order(tenant_a, status=SalesOrder.Status.CANCELLED)
    route = _route(tenant_a)
    resp = _add(tenant_a, route, [good.id, cancelled.id])
    assert resp.status_code == 400
    assert resp.data["error"]["code"] == "route_order_blocked"
    assert [r["code"] for r in _details(resp)["risks"]] == ["order_cancelled"]
    assert route.stops.count() == 0


def test_tc_pl04_01b_a_blocked_customer_is_refused(tenant_a):
    customer = make_customer(tenant_a.company, name="Blocked", phone="9000000000", pincode="560001", status=Customer.Status.BLOCKED)
    resp = _add(tenant_a, _route(tenant_a), [_order(tenant_a, customer=customer).id])
    assert resp.status_code == 400 and resp.data["error"]["code"] == "route_order_blocked"


def test_tc_pl04_01c_an_order_on_another_live_route_is_refused(tenant_a):
    order = _order(tenant_a)
    first = _route(tenant_a)
    assert _add(tenant_a, first, [order.id]).status_code == 200
    other = DeliveryRoute.objects.create(company=tenant_a.company, route_date=TODAY, number="RT-2")
    resp = _add(tenant_a, other, [order.id])
    assert resp.status_code == 400 and "RT-P" in str(resp.data)


# ---------------------------------------------------------------------------
# PL-04 / PL-06 — warnings need an acknowledgement, with a reason, kept on the stop
# ---------------------------------------------------------------------------


def test_tc_pl04_02_a_warning_without_acknowledgement_is_refused_and_names_what_is_needed(tenant_a):
    customer = make_customer(tenant_a.company, name="No Phone", phone="", pincode="560001")
    order = _order(tenant_a, customer=customer)
    route = _route(tenant_a)
    resp = _add(tenant_a, route, [order.id])
    assert resp.status_code == 400
    assert resp.data["error"]["code"] == "route_risk_needs_acknowledgement"
    risks = _details(resp)["risks"]
    assert risks[0]["order"] == order.id and risks[0]["code"] == "no_phone" and risks[0]["kind"] == "needs_ack"
    assert route.stops.count() == 0


def test_tc_pl04_03_with_an_acknowledgement_it_is_added_and_the_reason_is_kept(tenant_a):
    customer = make_customer(tenant_a.company, name="No Phone", phone="", pincode="560001")
    order = _order(tenant_a, customer=customer)
    route = _route(tenant_a)
    resp = _add(tenant_a, route, [order.id], acks=[{"order": order.id, "code": "no_phone", "reason": "Driver knows the shop"}])
    assert resp.status_code == 200, resp.data
    ack = RouteStopAcknowledgement.objects.get()
    assert (ack.risk_code, ack.level, ack.reason) == ("no_phone", "warn", "Driver knows the shop")
    assert ack.created_by_id == tenant_a.owner.id and ack.company_id == tenant_a.company.id
    assert ack.stop.sales_order_id == order.id
    event = AuditEvent.objects.filter(
        company=tenant_a.company, entity_type="DeliveryRoute", entity_id=str(route.pk),
        description="delivery_route.risk_acknowledged",
    ).get()
    assert event.metadata["risk"] == "no_phone" and event.metadata["reason"] == "Driver knows the shop"


def test_tc_pl06_02_an_acknowledgement_without_a_reason_is_refused(tenant_a):
    customer = make_customer(tenant_a.company, name="No Phone", phone="", pincode="560001")
    order = _order(tenant_a, customer=customer)
    for reason in ("", "  ", "ok"):
        resp = _add(tenant_a, _route(tenant_a), [order.id], acks=[{"order": order.id, "code": "no_phone", "reason": reason}])
        assert resp.status_code == 400, reason
    assert RouteStopAcknowledgement.objects.count() == 0


def test_tc_pl06_01b_an_acknowledgement_for_a_risk_the_order_does_not_have_is_not_recorded(tenant_a):
    order = _order(tenant_a)
    resp = _add(tenant_a, _route(tenant_a), [order.id], acks=[{"order": order.id, "code": "stock_short", "reason": "just in case"}])
    assert resp.status_code == 200, resp.data
    assert RouteStopAcknowledgement.objects.count() == 0


def test_tc_pl06_01c_information_and_blocks_cannot_be_acknowledged_away(tenant_a):
    order = _order(tenant_a, status=SalesOrder.Status.CANCELLED)
    resp = _add(tenant_a, _route(tenant_a), [order.id], acks=[{"order": order.id, "code": "order_cancelled", "reason": "please let it through"}])
    assert resp.status_code == 400 and resp.data["error"]["code"] == "route_order_blocked"
    assert RouteStopAcknowledgement.objects.count() == 0


def test_tc_pl04_04_a_warning_only_a_manager_may_accept_is_refused_for_staff(tenant_a):
    customer = make_customer(tenant_a.company, name="Over", phone="9000000001", pincode="560001", credit_limit=Decimal("100"))
    order = _order(tenant_a, customer=customer, qty="2", price="100")  # 200 against a limit of 100
    route = _route(tenant_a)
    acks = [{"order": order.id, "code": "over_credit_limit", "reason": "Regular customer"}]
    with pytest.raises(BusinessRuleError) as staff:
        RouteService.add_orders(route, [order.id], tenant_a.staff, acknowledgements=acks, viewer=STAFF)
    assert staff.value.extra["risks"][0]["kind"] == "not_allowed"
    RouteService.add_orders(route, [order.id], tenant_a.owner, acknowledgements=acks, viewer=MANAGER)
    assert RouteStopAcknowledgement.objects.get().risk_code == "over_credit_limit"


def test_tc_pl04_05_a_draft_never_goes_on_a_route_even_for_the_owner(tenant_a):
    draft = _order(tenant_a, status=SalesOrder.Status.DRAFT)
    route = _route(tenant_a)
    acks = [{"order": draft.id, "code": "not_ready", "reason": "Customer collecting today, confirm later"}]
    for kwargs in ({}, {"acks": acks}):
        resp = _add(tenant_a, route, [draft.id], **kwargs)  # the owner
        assert resp.status_code == 400 and resp.data["error"]["code"] == "route_order_blocked"
    assert RouteStopAcknowledgement.objects.count() == 0
    assert not route.stops.exists()


def test_tc_pl04_06_creating_a_route_with_orders_and_acknowledgements_is_one_step(tenant_a):
    customer = make_customer(tenant_a.company, name="No Phone", phone="", pincode="560001")
    order = _order(tenant_a, customer=customer)
    resp = tenant_a.client.post(
        "/api/v1/sales/delivery-routes/",
        {
            "route_date": TODAY, "order_ids": [order.id],
            "acknowledgements": [{"order": order.id, "code": "no_phone", "reason": "Driver knows the shop"}],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert len(resp.data["stops"]) == 1
    refused = tenant_a.client.post(
        "/api/v1/sales/delivery-routes/", {"route_date": TODAY, "order_ids": [order.id]}, format="json"
    )
    assert refused.status_code == 400
    assert DeliveryRoute.objects.count() == 1  # the failed attempt left no empty route behind


def test_tc_pl06_03_one_acknowledgement_per_stop_and_risk_and_it_can_be_restated(tenant_a):
    customer = make_customer(tenant_a.company, name="No Phone", phone="", pincode="560001")
    order = _order(tenant_a, customer=customer)
    route = _route(tenant_a)
    assert _add(tenant_a, route, [order.id], acks=[{"order": order.id, "code": "no_phone", "reason": "first reason"}]).status_code == 200
    stop = route.stops.get()
    RouteService._record_acknowledgements(route, stop, {"no_phone": "a better reason"}, tenant_a.owner)
    assert RouteStopAcknowledgement.objects.count() == 1
    assert RouteStopAcknowledgement.objects.get().reason == "a better reason"


# ---------------------------------------------------------------------------
# PL-05 — starting checks again
# ---------------------------------------------------------------------------


def _start(tenant, route, acks=None):
    return tenant.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/start/",
        {"acknowledgements": acks} if acks is not None else {},
        format="json",
    )


def test_tc_pl05_01_a_clean_route_starts(tenant_a):
    route = _route(tenant_a)
    assert _add(tenant_a, route, [_order(tenant_a).id]).status_code == 200
    resp = _start(tenant_a, route)
    assert resp.status_code == 200, resp.data
    assert resp.data["status"] == "IN_TRANSIT"


@pytest.mark.invariant_skip("inventory.balance_equals_movements", reason="stock balances or movements are written directly through the ORM")
def test_tc_pl05_02_a_risk_that_appears_after_planning_needs_a_new_acknowledgement(tenant_a):
    product = make_product(tenant_a.company, sku="START-1")
    add_stock(tenant_a, product, "5")
    order = _order(tenant_a, product=product, qty="5")
    route = _route(tenant_a)
    assert _add(tenant_a, route, [order.id]).status_code == 200
    # Meanwhile the stock is sold.
    from inventory.models import StockBalance

    StockBalance.objects.filter(company=tenant_a.company, product=product).update(on_hand=Decimal("1"))
    refused = _start(tenant_a, route)
    assert refused.status_code == 400
    assert refused.data["error"]["code"] == "route_risk_needs_acknowledgement"
    assert "Not enough stock" in str(refused.data)
    stop = route.stops.get()
    accepted = _start(tenant_a, route, acks=[{"stop": stop.id, "code": "stock_short", "reason": "Restock arrives this evening"}])
    assert accepted.status_code == 200, accepted.data
    assert RouteStopAcknowledgement.objects.get().risk_code == "stock_short"


def test_tc_pl05_03_a_customer_blocked_after_planning_stops_the_start(tenant_a):
    order = _order(tenant_a)
    route = _route(tenant_a)
    assert _add(tenant_a, route, [order.id]).status_code == 200
    Customer.objects.filter(pk=order.customer_id).update(status=Customer.Status.BLOCKED)
    resp = _start(tenant_a, route)
    assert resp.status_code == 400 and resp.data["error"]["code"] == "route_order_blocked"
    route.refresh_from_db()
    assert route.status == DeliveryRoute.Status.PLANNED


def test_tc_pl05_04_an_order_cancelled_after_planning_stops_the_start(tenant_a):
    order = _order(tenant_a)
    route = _route(tenant_a)
    assert _add(tenant_a, route, [order.id]).status_code == 200
    SalesOrder.objects.filter(pk=order.pk).update(status=SalesOrder.Status.CANCELLED)
    assert _start(tenant_a, route).status_code == 400


def test_tc_pl05_05_a_warning_accepted_at_planning_does_not_ask_again_for_the_same_risk(tenant_a):
    customer = make_customer(tenant_a.company, name="No Phone", phone="", pincode="560001")
    order = _order(tenant_a, customer=customer)
    route = _route(tenant_a)
    assert _add(tenant_a, route, [order.id], acks=[{"order": order.id, "code": "no_phone", "reason": "Driver knows"}]).status_code == 200
    assert _start(tenant_a, route).status_code == 200


def test_tc_pl05_06_a_stop_acknowledgement_for_another_route_is_refused(tenant_a):
    route = _route(tenant_a)
    assert _add(tenant_a, route, [_order(tenant_a).id]).status_code == 200
    other = DeliveryRoute.objects.create(company=tenant_a.company, route_date=TODAY, number="RT-O")
    stranger = DeliveryRouteStop.objects.create(company=tenant_a.company, route=other, sales_order=_order(tenant_a))
    resp = _start(tenant_a, route, acks=[{"stop": stranger.id, "code": "no_phone", "reason": "not mine"}])
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# the preflight read
# ---------------------------------------------------------------------------


def test_tc_pl05_07_preflight_lists_every_stop_with_its_risks_totals_and_whether_it_can_start(tenant_a):
    ok = _order(tenant_a, qty="2", price="100")
    sparse = _order(tenant_a, address="", qty="3", price="50")
    route = _route(tenant_a)
    _add(tenant_a, route, [ok.id])
    DeliveryRouteStop.objects.create(company=tenant_a.company, route=route, sales_order=sparse, sequence=2)
    resp = tenant_a.client.get(f"/api/v1/sales/delivery-routes/{route.id}/preflight/")
    assert resp.status_code == 200, resp.data
    assert resp.data["can_start"] is False and resp.data["open_problems"] == 1
    by_order = {row["order"]: row for row in resp.data["stops"]}
    assert by_order[ok.id]["status"] == "ok"
    assert by_order[sparse.id]["status"] == "needs_ack"
    assert [r["code"] for r in by_order[sparse.id]["risks"] if r["level"] == "warn"] == ["no_address"]
    totals = resp.data["totals"]
    assert totals["orders"] == 2 and totals["value"] == "350.00" and totals["warnings"] == 1


def test_tc_pl08_01_a_risk_that_appears_later_shows_on_the_next_read(tenant_a):
    order = _order(tenant_a)
    route = _route(tenant_a)
    _add(tenant_a, route, [order.id])
    first = tenant_a.client.get(f"/api/v1/sales/delivery-routes/{route.id}/preflight/")
    assert first.data["can_start"] is True
    Customer.objects.filter(pk=order.customer_id).update(status=Customer.Status.BLOCKED)
    again = tenant_a.client.get(f"/api/v1/sales/delivery-routes/{route.id}/preflight/")
    assert again.data["can_start"] is False and again.data["stops"][0]["status"] == "blocked"


def test_tc_pl05_08_an_empty_route_cannot_start_and_says_so(tenant_a):
    route = _route(tenant_a)
    assert _start(tenant_a, route).status_code == 400
    assert tenant_a.client.get(f"/api/v1/sales/delivery-routes/{route.id}/preflight/").data["can_start"] is False


def test_tc_pl05_09_preflight_is_company_scoped(tenant_a, tenant_b):
    route = _route(tenant_a)
    assert tenant_b.client.get(f"/api/v1/sales/delivery-routes/{route.id}/preflight/").status_code == 404


# ---------------------------------------------------------------------------
# PL-02 — the candidate list
# ---------------------------------------------------------------------------


def _candidates(tenant, query="", client=None):
    resp = (client or tenant.client).get(f"/api/v1/sales/delivery-routes/candidates/?{query}")
    assert resp.status_code == 200, resp.data
    return resp.data


def test_tc_pl02_01_default_list_offers_only_routable_orders_not_busy_ones(tenant_a):
    ready = _order(tenant_a)
    _order(tenant_a, status=SalesOrder.Status.DRAFT)
    _order(tenant_a, status=SalesOrder.Status.CANCELLED)
    busy = _order(tenant_a)
    DeliveryRouteStop.objects.create(company=tenant_a.company, route=_route(tenant_a), sales_order=busy)
    shipped = _order(tenant_a, status=SalesOrder.Status.CONVERTED)
    data = _candidates(tenant_a)
    assert {r["order"] for r in data["results"]} == {ready.id, shipped.id}
    assert data["count"] == 2 and all(r["ready"] for r in data["results"])


def test_tc_pl02_02_show_unavailable_and_drafts_appear_as_blocked_rows(tenant_a):
    draft = _order(tenant_a, status=SalesOrder.Status.DRAFT)
    busy = _order(tenant_a)
    DeliveryRouteStop.objects.create(company=tenant_a.company, route=_route(tenant_a), sales_order=busy)
    data = _candidates(tenant_a, "include_drafts=1&show_unavailable=1")
    rows = {r["order"]: r for r in data["results"]}
    assert rows[draft.id]["ready"] is False and "not_ready" in {x["code"] for x in rows[draft.id]["risks"]}
    assert rows[busy.id]["ready"] is False and "already_on_route" in {x["code"] for x in rows[busy.id]["risks"]}


def test_tc_pl02_03_filters_search_customer_pincode_and_dates(tenant_a):
    alpha = make_customer(tenant_a.company, name="Alpha Stores", phone="9000000001", pincode="560001")
    beta = make_customer(tenant_a.company, name="Beta Traders", phone="9000000002", pincode="411001")
    a = _order(tenant_a, customer=alpha, expected_delivery="2026-10-15")
    b = _order(tenant_a, customer=beta, expected_delivery="2026-10-20")
    ids = lambda q: {r["order"] for r in _candidates(tenant_a, q)["results"]}  # noqa: E731
    assert ids("q=alpha") == {a.id}
    assert ids(f"customer={beta.id}") == {b.id}
    assert ids("pincode=5600") == {a.id}
    assert ids("date_from=2026-10-18") == {b.id}
    assert ids("date_to=2026-10-16") == {a.id}
    assert tenant_a.client.get("/api/v1/sales/delivery-routes/candidates/?date_from=nope").status_code == 400
    assert tenant_a.client.get("/api/v1/sales/delivery-routes/candidates/?customer=abc").status_code == 400
    assert tenant_a.client.get("/api/v1/sales/delivery-routes/candidates/?page=x").status_code == 400


def test_tc_pl02_04_paging_and_a_stable_order(tenant_a):
    orders = [_order(tenant_a, expected_delivery=f"2026-10-{10 + i}") for i in range(5)]
    first = _candidates(tenant_a, "page_size=2&page=1")
    second = _candidates(tenant_a, "page_size=2&page=2")
    third = _candidates(tenant_a, "page_size=2&page=3")
    assert [r["order"] for r in first["results"]] == [orders[0].id, orders[1].id]
    assert [r["order"] for r in second["results"]] == [orders[2].id, orders[3].id]
    assert [r["order"] for r in third["results"]] == [orders[4].id]
    assert first["count"] == 5 and first["page_size"] == 2
    assert _candidates(tenant_a, "page_size=5000")["page_size"] == 100  # capped


def test_tc_pl02_05_another_companys_orders_never_appear(tenant_a, tenant_b):
    _order(tenant_b)
    assert _candidates(tenant_a)["count"] == 0


def test_tc_pl01_03_cost_and_customer_money_follow_what_the_viewer_may_see(tenant_a):
    from accounts.models import CompanyUser

    product = make_product(tenant_a.company, sku="PRIV-1", purchase_price="99", selling_price="100", track_inventory=False)
    _order(tenant_a, product=product, price="100")
    owner_row = _candidates(tenant_a)["results"][0]
    assert "money" in owner_row and "low_margin_products" in owner_row
    CompanyUser.objects.filter(company=tenant_a.company, user=tenant_a.staff).update(
        role=CompanyUser.Role.SALES_STAFF, can_create_sales=True, can_create_payments=False, can_view_financial_reports=False,
    )
    staff = _candidates(tenant_a, client=tenant_a.staff_client)["results"][0]
    assert "low_margin_products" not in staff
    assert "low_margin" not in {r["code"] for r in staff["risks"]}


def test_tc_pl10_01_an_order_sent_back_after_a_failed_stop_must_be_confirmed_again(tenant_a):
    product = make_product(tenant_a.company, sku="REPLAN-1")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company, name="Replan Co", phone="9000000003", pincode="560001")
    resp = tenant_a.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id, "invoice_type": "NON_GST", "delivery_address": "Gate 4",
            "items": [{"product": product.id, "quantity": "3", "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )
    order = SalesOrder.objects.get(pk=resp.data["id"])
    SalesNotesService.confirm_sales_order(order, tenant_a.owner)
    first = _route(tenant_a)
    assert _add(tenant_a, first, [order.id]).status_code == 200
    assert _start(tenant_a, first).status_code == 200
    stop = first.stops.get()
    tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{first.id}/set-stop-status/", {"stop_id": stop.id, "status": "FAILED"}, format="json"
    )
    order.refresh_from_db()
    assert order.status == SalesOrder.Status.DRAFT  # nothing held any more
    assert order.id not in {r["order"] for r in _candidates(tenant_a)["results"]}
    second = DeliveryRoute.objects.create(company=tenant_a.company, route_date=TODAY, number="RT-2")
    assert _add(tenant_a, second, [order.id]).status_code == 400
    SalesNotesService.confirm_sales_order(order, tenant_a.owner)
    assert order.id in {r["order"] for r in _candidates(tenant_a)["results"]}
    assert _add(tenant_a, second, [order.id]).status_code == 200


# ---------------------------------------------------------------------------
# PL-33 — what the table shows is what the server enforces
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "build",
    ["clean", "no_phone", "cancelled", "blocked_customer", "draft", "over_limit"],
)
def test_tc_pl33_01_candidates_preflight_add_and_start_agree(tenant_a, build):
    customer = make_customer(tenant_a.company, name=f"Agree {build}", phone="9000000009", pincode="560001")
    status = SalesOrder.Status.CONFIRMED
    if build == "no_phone":
        customer.phone = ""
        customer.save(update_fields=["phone"])
    elif build == "cancelled":
        status = SalesOrder.Status.CANCELLED
    elif build == "blocked_customer":
        customer.status = Customer.Status.BLOCKED
        customer.save(update_fields=["status"])
    elif build == "draft":
        status = SalesOrder.Status.DRAFT
    elif build == "over_limit":
        customer.credit_limit = Decimal("50")
        customer.save(update_fields=["credit_limit"])
    order = _order(tenant_a, customer=customer, status=status)

    shown = {r["order"]: r for r in _candidates(tenant_a, "show_unavailable=1&include_drafts=1")["results"]}
    summary_codes = {r["code"] for r in shown[order.id]["risks"]} if order.id in shown else {"order_cancelled"}

    route = _route(tenant_a)
    added = _add(tenant_a, route, [order.id])
    if build == "clean":
        assert added.status_code == 200 and summary_codes == set()
    else:
        assert added.status_code == 400
        refused_codes = {r["code"] for r in _details(added)["risks"]}
        assert refused_codes <= summary_codes, (refused_codes, summary_codes)
        # and once accepted (where it can be), the preflight and the start agree with the add
        accept = [
            {"order": order.id, "code": r["code"], "reason": "accepted in test"}
            for r in _details(added)["risks"] if r["kind"] == "needs_ack"
        ]
        if build in ("cancelled", "blocked_customer", "draft"):
            assert all(r["kind"] == "blocked" for r in _details(added)["risks"])
        else:
            again = _add(tenant_a, route, [order.id], acks=accept)
            assert again.status_code == 200, again.data
            pre = tenant_a.client.get(f"/api/v1/sales/delivery-routes/{route.id}/preflight/").data
            assert pre["can_start"] is True
            assert _start(tenant_a, route).status_code == 200


def test_the_service_applies_the_same_rules_without_a_request(tenant_a):
    """Internal callers get the rules too unless they say they vouch for the orders."""
    cancelled = _order(tenant_a, status=SalesOrder.Status.CANCELLED)
    route = _route(tenant_a)
    with pytest.raises(BusinessRuleError):
        RouteService.add_orders(route, [cancelled.id], tenant_a.owner)
    with mock.patch("sales.route_planning.order_summaries") as summaries:
        RouteService.add_orders(route, [_order(tenant_a).id], tenant_a.owner, enforce_risks=False)
        summaries.assert_not_called()


def test_the_route_and_the_manifest_show_the_risks_that_were_accepted(tenant_a):
    from io import BytesIO

    from pypdf import PdfReader

    customer = make_customer(tenant_a.company, name="No Phone Co", phone="", pincode="560001")
    order = _order(tenant_a, customer=customer)
    route = _route(tenant_a)
    assert _add(tenant_a, route, [order.id], acks=[{"order": order.id, "code": "no_phone", "reason": "Driver knows the shop"}]).status_code == 200
    detail = tenant_a.client.get(f"/api/v1/sales/delivery-routes/{route.id}/")
    ack = detail.data["stops"][0]["acknowledgements"][0]
    assert ack["code"] == "no_phone" and ack["level"] == "warn" and ack["reason"] == "Driver knows the shop"
    assert ack["by"] and ack["at"]
    pdf = tenant_a.client.get(f"/api/v1/sales/delivery-routes/{route.id}/manifest/")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(b"".join(pdf.streaming_content))).pages)
    assert "RISKS ACCEPTED" in text and "Driver knows the shop" in text


def test_a_summary_says_whether_the_customer_has_a_location(tenant_a):
    here = make_customer(tenant_a.company, name="Located", phone="9000000010", pincode="560001")
    Customer.objects.filter(pk=here.pk).update(latitude=Decimal("12.9716"), longitude=Decimal("77.5946"))
    placed = _order(tenant_a, customer=Customer.objects.get(pk=here.pk))
    unplaced = _order(tenant_a)
    rows = {r["order"]: r for r in _candidates(tenant_a)["results"]}
    assert rows[placed.id]["customer"]["has_location"] is True
    assert rows[unplaced.id]["customer"]["has_location"] is False


def test_candidates_can_be_limited_to_the_orders_picked_on_the_order_list(tenant_a):
    a, b, c = _order(tenant_a), _order(tenant_a), _order(tenant_a)
    assert {r["order"] for r in _candidates(tenant_a, f"ids={a.id},{c.id}")["results"]} == {a.id, c.id}
    assert tenant_a.client.get("/api/v1/sales/delivery-routes/candidates/?ids=1,x").status_code == 400
    assert b.id not in {r["order"] for r in _candidates(tenant_a, f"ids={a.id}")["results"]}
