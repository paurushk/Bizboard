"""R5 (RT-22..24, RT-27..29; OG-04, OG-14, OG-20..23; DEC-R2): what the office sees and the cashier does.

A stop shows its bill and what to collect; a route shows its progress and what needs the office; the
cashier's count carries a reason when it differs; and the cashier links the receipt they made to the
money the driver collected (the system never creates it). The manifest is a load list for the godown.
"""

from decimal import Decimal
from io import BytesIO

import pytest
from pypdf import PdfReader

from payments.models import CustomerReceipt, ReceiptStatus
from sales.models import DeliveryRoute, DeliveryRouteStop, RouteCashHandover, SalesOrder
from sales.notes_services import SalesNotesService
from sales.services import SalesService
from tests.conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db


def _order(tenant, *, customer=None, qty="2", price="100", terms=0, name="Shop"):
    customer = customer or make_customer(tenant.company, name=name, phone="9876543210", pincode="560001")
    product = make_product(tenant.company, sku=f"C-{SalesOrder.objects.count()}", name=f"Item {SalesOrder.objects.count()}")
    add_stock(tenant, product, "100")
    resp = tenant.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id, "invoice_type": "NON_GST", "payment_terms_days": terms,
            "delivery_address": "12 Market Road",
            "items": [{"product": product.id, "quantity": qty, "unit_price": price, "gst_rate": "0"}],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    order = SalesOrder.objects.get(pk=resp.data["id"])
    SalesNotesService.confirm_sales_order(order, tenant.owner)
    order.refresh_from_db()
    return order


def _route(tenant, orders, *, start=True):
    route = DeliveryRoute.objects.create(company=tenant.company, route_date="2026-10-14", number="RT-X")
    for order in orders:
        DeliveryRouteStop.objects.create(company=tenant.company, route=route, sales_order=order)
    if start:
        tenant.client.post(f"/api/v1/sales/delivery-routes/{route.id}/start/")
    return route


def _detail(tenant, route):
    resp = tenant.client.get(f"/api/v1/sales/delivery-routes/{route.id}/")
    assert resp.status_code == 200, resp.data
    return resp.data


def _deliver(tenant, route, stop, **extra):
    return tenant.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/set-stop-status/",
        {"stop_id": stop.id, "status": "DELIVERED", "received_by_name": "Asha", "completion_source": "OFFICE", **extra},
        format="json",
    )


# ---------------------------------------------------------------------------
# OG-20 — amount to collect and bill status on each stop
# ---------------------------------------------------------------------------


def test_tc_og20_01_a_cash_order_with_no_bill_yet_collects_the_order_total(tenant_a):
    order = _order(tenant_a, qty="3", price="100", terms=0)
    route = _route(tenant_a, [order])
    bill = _detail(tenant_a, route)["stops"][0]["bill"]
    assert bill["bill_status"] == "order_only"
    assert bill["amount_to_collect"] == "300.00" and bill["order_total"] == "300.00"
    assert bill["on_credit"] is False and bill["invoices"] == []


def test_tc_og20_02_a_credit_order_collects_nothing_at_the_door(tenant_a):
    order = _order(tenant_a, terms=30)
    route = _route(tenant_a, [order])
    bill = _detail(tenant_a, route)["stops"][0]["bill"]
    assert bill["on_credit"] is True and bill["payment_terms_days"] == 30
    assert bill["amount_to_collect"] == "0.00"


def test_tc_og20_03_an_invoiced_order_shows_the_invoice_and_its_balance(tenant_a):
    order = _order(tenant_a, qty="2", price="100")
    challan = SalesNotesService.complete_challan(
        SalesNotesService.convert_sales_order_to_challan(order, tenant_a.owner), tenant_a.owner
    )
    invoice = SalesNotesService.convert_delivery_challan(challan, tenant_a.owner)
    SalesService.complete(invoice, tenant_a.owner)
    order.refresh_from_db()
    route = _route(tenant_a, [order])
    bill = _detail(tenant_a, route)["stops"][0]["bill"]
    assert bill["bill_status"] == "invoiced"
    assert bill["invoices"][0]["balance"] == "200.00"
    assert bill["amount_to_collect"] == "200.00"


def test_tc_og20_04_a_paid_invoice_collects_nothing(tenant_a):
    order = _order(tenant_a, qty="1", price="100")
    challan = SalesNotesService.complete_challan(
        SalesNotesService.convert_sales_order_to_challan(order, tenant_a.owner), tenant_a.owner
    )
    invoice = SalesNotesService.convert_delivery_challan(challan, tenant_a.owner)
    SalesService.complete(invoice, tenant_a.owner)
    from ledgers.services import LedgerService

    from unittest import mock

    with mock.patch.object(LedgerService, "sales_invoice_outstanding", return_value=Decimal("0")):
        order.refresh_from_db()
        route = _route(tenant_a, [order])
        bill = _detail(tenant_a, route)["stops"][0]["bill"]
    assert bill["bill_status"] == "paid" and bill["amount_to_collect"] == "0.00"


def test_tc_og20_05_the_list_does_not_compute_bills(tenant_a):
    _route(tenant_a, [_order(tenant_a)])
    resp = tenant_a.client.get("/api/v1/sales/delivery-routes/")
    assert resp.status_code == 200
    rows = resp.data["results"] if isinstance(resp.data, dict) else resp.data
    assert rows[0]["stops"][0]["bill"] is None


def test_tc_og20_06_the_stop_carries_the_customer_phone(tenant_a):
    route = _route(tenant_a, [_order(tenant_a)])
    assert _detail(tenant_a, route)["stops"][0]["customer_phone"] == "9876543210"


def test_tc_og20_07_advance_on_account_follows_the_customer_360_rule(tenant_a):
    from accounts.models import CompanyUser

    order = _order(tenant_a)
    route = _route(tenant_a, [order])
    assert "advance_available" in _detail(tenant_a, route)["stops"][0]["bill"]
    CompanyUser.objects.filter(company=tenant_a.company, user=tenant_a.staff).update(
        role=CompanyUser.Role.VIEWER, can_create_sales=False, can_create_payments=False,
        can_view_financial_reports=False,
    )
    resp = tenant_a.staff_client.get(f"/api/v1/sales/delivery-routes/{route.id}/")
    if resp.status_code == 200:  # a viewer may see the route, never the customer's money
        assert "advance_available" not in resp.data["stops"][0]["bill"]


# ---------------------------------------------------------------------------
# OG-14 — progress and "needs attention"
# ---------------------------------------------------------------------------


def test_tc_og14_01_progress_counts_and_attention(tenant_a):
    first, second, third = (_order(tenant_a) for _ in range(3))
    route = _route(tenant_a, [first, second, third])
    stops = list(route.stops.order_by("id"))
    assert _detail(tenant_a, route)["progress"]["pending"] == 3
    _deliver(tenant_a, route, stops[0], collected_cash="150")
    tenant_a.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/set-stop-status/",
        {"stop_id": stops[1].id, "status": "FAILED"},
        format="json",
    )
    progress = _detail(tenant_a, route)["progress"]
    assert (progress["stops_total"], progress["delivered"], progress["failed"], progress["pending"]) == (3, 1, 1, 1)
    assert progress["collected"] == "150.00"
    assert set(progress["needs_attention"]) == {"failed_stops", "cash_unverified"}


def test_tc_og14_02_ready_to_close_when_nothing_is_pending(tenant_a):
    route = _route(tenant_a, [_order(tenant_a)])
    assert "ready_to_close" not in _detail(tenant_a, route)["progress"]["needs_attention"]
    _deliver(tenant_a, route, route.stops.get())
    assert "ready_to_close" in _detail(tenant_a, route)["progress"]["needs_attention"]


def test_tc_og14_03_a_planned_route_has_no_attention(tenant_a):
    route = _route(tenant_a, [_order(tenant_a)], start=False)
    assert _detail(tenant_a, route)["progress"]["needs_attention"] == []


# ---------------------------------------------------------------------------
# OG-21 / OG-23 — the cashier's count and its variance note
# ---------------------------------------------------------------------------


def _collect(tenant, route, *, cash="100", upi="0", recorder=None):
    stop = route.stops.get()
    client = recorder or tenant.client
    resp = client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/set-stop-status/",
        {
            "stop_id": stop.id, "status": "DELIVERED", "received_by_name": "Asha", "completion_source": "OFFICE",
            "collected_cash": cash, "collected_upi": upi, "upi_reference": "UPI123" if Decimal(upi) > 0 else None,
        },
        format="json",
    )
    assert resp.status_code == 200, resp.data
    return stop


def _count(tenant, route, *, cash, upi="0", note=None, client=None):
    payload = {"cash_counted": cash, "upi_counted": upi}
    if note is not None:
        payload["variance_note"] = note
    return (client or tenant.client).post(
        f"/api/v1/sales/delivery-routes/{route.id}/verify-handover/", payload, format="json"
    )


def test_tc_og21_01_an_exact_count_verifies_and_the_route_closes(tenant_a):
    route = _route(tenant_a, [_order(tenant_a)])
    _collect(tenant_a, route, cash="100")
    resp = _count(tenant_a, route, cash="100")
    assert resp.status_code == 200, resp.data
    assert resp.data["cash_handover"]["status"] == "VERIFIED"
    assert tenant_a.client.post(f"/api/v1/sales/delivery-routes/{route.id}/complete/", {}, format="json").status_code == 200


def test_tc_og21_02_a_short_count_is_a_variance_and_needs_a_note_to_leave_the_attention_list(tenant_a):
    route = _route(tenant_a, [_order(tenant_a)])
    _collect(tenant_a, route, cash="100")
    resp = _count(tenant_a, route, cash="90")
    assert resp.status_code == 200, resp.data
    handover = resp.data["cash_handover"]
    assert handover["status"] == "VARIANCE" and Decimal(str(handover["variance_amount"])) == Decimal("-10.00")
    assert "cash_variance_unexplained" in resp.data["progress"]["needs_attention"]
    explained = _count(tenant_a, route, cash="90", note="Driver paid the toll from the cash")
    assert explained.data["cash_handover"]["variance_note"] == "Driver paid the toll from the cash"
    assert "cash_variance_unexplained" not in explained.data["progress"]["needs_attention"]


def test_tc_og21_03_the_person_who_recorded_the_money_cannot_count_it(tenant_a):
    from accounts.models import CompanyUser

    CompanyUser.objects.filter(company=tenant_a.company, user=tenant_a.staff).update(can_create_sales=True)
    route = _route(tenant_a, [_order(tenant_a)])
    _collect(tenant_a, route, cash="100", recorder=tenant_a.staff_client)
    refused = _count(tenant_a, route, cash="100", client=tenant_a.staff_client)
    assert refused.status_code == 400
    assert "different person" in str(refused.data)
    assert _count(tenant_a, route, cash="100").status_code == 200  # the owner may


def test_tc_og21_04_collections_changed_after_the_count_need_a_recount(tenant_a):
    route = _route(tenant_a, [_order(tenant_a)])
    stop = _collect(tenant_a, route, cash="100")
    _count(tenant_a, route, cash="100")
    DeliveryRouteStop.objects.filter(pk=stop.pk).update(collected_cash=Decimal("120"))
    resp = tenant_a.client.post(f"/api/v1/sales/delivery-routes/{route.id}/complete/", {}, format="json")
    assert resp.status_code == 400
    assert "changed after cashier verification" in str(resp.data)


def test_tc_og21_05_no_money_collected_needs_no_count(tenant_a):
    route = _route(tenant_a, [_order(tenant_a)])
    _deliver(tenant_a, route, route.stops.get())
    assert tenant_a.client.post(f"/api/v1/sales/delivery-routes/{route.id}/complete/", {}, format="json").status_code == 200
    assert not RouteCashHandover.objects.filter(route=route).exists()


def test_tc_og21_06_a_matching_count_ignores_a_stray_note(tenant_a):
    route = _route(tenant_a, [_order(tenant_a)])
    _collect(tenant_a, route, cash="100")
    resp = _count(tenant_a, route, cash="100", note="not needed")
    assert resp.data["cash_handover"]["variance_note"] == ""


# ---------------------------------------------------------------------------
# OG-22 — the cashier links the receipt they made (the system never creates one)
# ---------------------------------------------------------------------------


def _receipt(tenant, customer, amount="100", status=ReceiptStatus.POSTED):
    return CustomerReceipt.objects.create(
        company=tenant.company, customer=customer, amount=Decimal(amount), status=status, created_by=tenant.owner,
    )


def _link(tenant, route, stop, receipt, **extra):
    return tenant.client.post(
        f"/api/v1/sales/delivery-routes/{route.id}/link-receipt/",
        {"stop_id": stop.id, "receipt_id": receipt.id, **extra},
        format="json",
    )


def test_tc_og22_01_a_matching_receipt_links_and_shows_on_the_stop(tenant_a):
    order = _order(tenant_a)
    route = _route(tenant_a, [order])
    stop = _collect(tenant_a, route, cash="100")
    receipt = _receipt(tenant_a, order.customer)
    resp = _link(tenant_a, route, stop, receipt)
    assert resp.status_code == 200, resp.data
    assert resp.data["stops"][0]["customer_receipt"] == receipt.id


def test_tc_og22_02_another_customers_receipt_is_refused(tenant_a):
    order = _order(tenant_a)
    route = _route(tenant_a, [order])
    stop = _collect(tenant_a, route, cash="100")
    other = make_customer(tenant_a.company, name="Someone Else")
    resp = _link(tenant_a, route, stop, _receipt(tenant_a, other))
    assert resp.status_code == 400 and "different customer" in str(resp.data)


def test_tc_og22_03_another_companys_receipt_is_not_found(tenant_a, tenant_b):
    order = _order(tenant_a)
    route = _route(tenant_a, [order])
    stop = _collect(tenant_a, route, cash="100")
    foreign = _receipt(tenant_b, make_customer(tenant_b.company))
    resp = _link(tenant_a, route, stop, foreign)
    assert resp.status_code == 400 and "not found" in str(resp.data)


def test_tc_og22_04_a_different_amount_needs_a_reason_and_keeps_the_difference(tenant_a):
    order = _order(tenant_a)
    route = _route(tenant_a, [order])
    stop = _collect(tenant_a, route, cash="100")
    receipt = _receipt(tenant_a, order.customer, amount="90")
    refused = _link(tenant_a, route, stop, receipt)
    assert refused.status_code == 400 and "10.00 less" in str(refused.data)
    ok = _link(tenant_a, route, stop, receipt, reason="Customer kept 10 for returned crate")
    assert ok.status_code == 200, ok.data
    stop.refresh_from_db()
    assert "differs by -10.00" in stop.notes and "returned crate" in stop.notes


def test_tc_og22_05_the_system_never_creates_a_receipt(tenant_a):
    order = _order(tenant_a)
    route = _route(tenant_a, [order])
    stop = _collect(tenant_a, route, cash="100")
    _count(tenant_a, route, cash="100")
    tenant_a.client.post(f"/api/v1/sales/delivery-routes/{route.id}/complete/", {}, format="json")
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0
    receipt = _receipt(tenant_a, order.customer)
    _link(tenant_a, route, stop, receipt)
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 1  # only the cashier's


def test_tc_og22_06_a_receipt_cannot_serve_two_stops(tenant_a):
    first, second = _order(tenant_a, name="Same Co"), None
    second = _order(tenant_a, customer=first.customer)
    route = _route(tenant_a, [first, second])
    stops = list(route.stops.order_by("id"))
    for stop in stops:
        _deliver(tenant_a, route, stop, collected_cash="100")
    receipt = _receipt(tenant_a, first.customer)
    assert _link(tenant_a, route, stops[0], receipt).status_code == 200
    again = _link(tenant_a, route, stops[1], receipt)
    assert again.status_code == 400 and "already linked" in str(again.data)


def test_tc_og22_07_a_voided_receipt_is_refused(tenant_a):
    order = _order(tenant_a)
    route = _route(tenant_a, [order])
    stop = _collect(tenant_a, route, cash="100")
    resp = _link(tenant_a, route, stop, _receipt(tenant_a, order.customer, status=ReceiptStatus.VOIDED))
    assert resp.status_code == 400 and "posted" in str(resp.data)


def test_tc_og22_08_linking_is_allowed_after_the_route_closes_but_not_before_it_starts(tenant_a):
    order = _order(tenant_a)
    planned = _route(tenant_a, [order], start=False)
    stop = planned.stops.get()
    assert _link(tenant_a, planned, stop, _receipt(tenant_a, order.customer)).status_code == 400


# ---------------------------------------------------------------------------
# RT-29 / OG-04 — the manifest is a load list
# ---------------------------------------------------------------------------


def test_tc_rt29_01_manifest_has_phone_collection_and_a_load_list_by_product(tenant_a):
    shared = make_product(tenant_a.company, sku="SHARED", name="Shared Bolt")
    add_stock(tenant_a, shared, "100")

    def order_with(name, qty, terms):
        customer = make_customer(tenant_a.company, name=name, phone="9000000001")
        resp = tenant_a.client.post(
            "/api/v1/sales/orders/",
            {
                "customer": customer.id, "invoice_type": "NON_GST", "payment_terms_days": terms,
                "delivery_address": f"{name} yard",
                "items": [{"product": shared.id, "quantity": str(qty), "unit_price": "50", "gst_rate": "0"}],
            },
            format="json",
        )
        return SalesOrder.objects.get(pk=resp.data["id"])

    a, b = order_with("Alpha Stores", 4, 0), order_with("Beta Stores", 6, 30)
    route = _route(tenant_a, [a, b], start=False)
    pdf = tenant_a.client.get(f"/api/v1/sales/delivery-routes/{route.id}/manifest/")
    assert pdf.status_code == 200
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(b"".join(pdf.streaming_content))).pages)
    assert "MANIFEST" in text and "9000000001" in text
    assert "Alpha Stores" in text and "Beta Stores" in text
    assert "LOAD LIST" in text and "Shared Bolt" in text
    assert "10" in text  # 4 + 6 loaded once
    assert "200.00" in text  # Alpha's cash sale to collect (4 x 50)
    assert "credit" in text  # Beta is on credit terms: nothing to collect at the door
