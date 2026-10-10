"""Closure-plan tests for CRM, guards, close-remaining, cross-module surfaces, sharing and alerts."""
from __future__ import annotations

import itertools
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone

from accounts.models import CompanyUser
from sales.models import Quotation, QuotationConversion, SalesInvoice, SalesOrder
from tests.conftest import make_customer, make_product

pytestmark = pytest.mark.django_db

_n = itertools.count(1000)


def _line(product, qty="10", price="100.00", gst="18", **extra):
    return {"product": product.id, "quantity": qty, "unit_price": price, "gst_rate": gst, **extra}


def _quote(tenant, *lines, customer=None, product=None, **extra):
    n = next(_n)
    cust = customer or make_customer(tenant.company, name=f"Cust {n}", phone=f"97654{n:05d}")
    if not lines:
        prod = product or make_product(tenant.company, sku=f"CX-{n}")
        lines = (_line(prod),)
    body = {"customer": cust.id, "quotation_date": "2026-03-01", "valid_until": "2099-03-15",
            "items": list(lines), **extra}
    resp = tenant.client.post("/api/v1/sales/quotations/", body, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data


def _to_order(tenant, quote, *, qty, item=0):
    resp = tenant.client.post(
        f"/api/v1/sales/quotations/{quote['id']}/convert-to-order/",
        {"items": [{"id": quote["items"][item]["id"], "quantity": qty}], "confirm_expired": True},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    return SalesOrder.objects.get(pk=resp.data["id"])


def _grant(tenant, **flags):
    CompanyUser.objects.filter(user=tenant.staff).update(**flags)


def _crm_on(company):
    company.feature_flags = {**(company.feature_flags or {}), "ENABLE_CRM": True, "pack_grant": "insurance"}
    company.save(update_fields=["feature_flags"])


# ---------------------------------------------------------------- WP5 ------

def _won_opportunity(tenant, *, with_line=True, customer=None):
    from crm.models import Opportunity, OpportunityLine

    cust = customer or make_customer(tenant.company, name=f"Won {next(_n)}")
    opp = Opportunity.objects.create(
        company=tenant.company, customer=cust, title="Big deal", stage=Opportunity.Stage.WON,
        created_by=tenant.owner,
    )
    if with_line:
        OpportunityLine.objects.create(
            company=tenant.company, opportunity=opp,
            product=make_product(tenant.company, sku=f"OPP-{next(_n)}"),
            quantity=Decimal("4"), unit_price=Decimal("250.00"), created_by=tenant.owner,
        )
    return opp


@override_settings(ENABLE_CRM=True)
def test_wp5_crm_quote_gets_number_type_totals_and_address(tenant_a):
    _crm_on(tenant_a.company)
    cust = make_customer(tenant_a.company, name="Addr Co", shipping_address="7 Dock Road")
    opp = _won_opportunity(tenant_a, customer=cust)
    resp = tenant_a.client.post(f"/api/v1/crm/opportunities/{opp.id}/quotation/")
    assert resp.status_code == 201, resp.data
    body = resp.data.get("data", resp.data)
    assert body["number"] and Decimal(body["grand_total"]) > 0 and body["already_exists"] is False
    quote = Quotation.objects.get(pk=body["id"])
    assert quote.delivery_address == "7 Dock Road"
    assert quote.invoice_type == "GST"
    assert quote.notes == "Big deal"
    assert quote.salesman_id is None
    assert quote.items.get().discount_percent == 0


@override_settings(ENABLE_CRM=True)
def test_wp5_crm_repeat_returns_the_open_quote_and_blocked_customer_fails(tenant_a):
    _crm_on(tenant_a.company)
    opp = _won_opportunity(tenant_a)
    first = tenant_a.client.post(f"/api/v1/crm/opportunities/{opp.id}/quotation/")
    again = tenant_a.client.post(f"/api/v1/crm/opportunities/{opp.id}/quotation/")
    assert again.status_code == 200 and again.data.get("data", again.data)["already_exists"] is True
    assert Quotation.objects.filter(opportunity=opp).count() == 1
    Quotation.objects.filter(opportunity=opp).update(status=Quotation.Status.CONVERTED)
    third = tenant_a.client.post(f"/api/v1/crm/opportunities/{opp.id}/quotation/")
    assert third.status_code == 201, (first.data, third.data)
    blocked = make_customer(tenant_a.company, name="Blocked Co", status="BLOCKED")
    opp2 = _won_opportunity(tenant_a, customer=blocked)
    assert tenant_a.client.post(f"/api/v1/crm/opportunities/{opp2.id}/quotation/").status_code == 400


def test_wp5_company_without_gst_registration_gets_a_non_gst_default(tenant_a):
    from accounts.models import Company

    Company.objects.filter(pk=tenant_a.company.pk).update(registration_type="UNREGISTERED")
    tenant_a.company.refresh_from_db()
    q = _quote(tenant_a)
    assert q["invoice_type"] == "NON_GST"


# ---------------------------------------------------------------- WP6 ------

def _unit_guard(product):
    """Only the quotation part of the guard: the order a test converts to blocks the full guard too."""
    from inventory.item_stock import _assert_no_open_quotations

    _assert_no_open_quotations(product)


def test_wp6_sent_and_accepted_quotes_block_a_unit_change_and_the_message_names_them(tenant_a):
    from core.exceptions import BusinessRuleError

    prod = make_product(tenant_a.company, sku="UG-1")
    q = _quote(tenant_a, product=prod)
    for status in (Quotation.Status.DRAFT, Quotation.Status.SENT, Quotation.Status.ACCEPTED):
        Quotation.objects.filter(pk=q["id"]).update(status=status)
        with pytest.raises(BusinessRuleError) as info:
            _unit_guard(prod)
        assert q["number"] in str(info.value.detail)
    Quotation.objects.filter(pk=q["id"]).update(status=Quotation.Status.CANCELLED)
    _unit_guard(prod)


def test_wp6_fully_converted_quote_does_not_block(tenant_a):
    prod = make_product(tenant_a.company, sku="UG-2")
    q = _quote(tenant_a, product=prod)
    assert tenant_a.client.post(f"/api/v1/sales/quotations/{q['id']}/convert/", {}, format="json").status_code == 200
    _unit_guard(prod)


def test_wp6_partly_converted_expired_quote_deadlock_is_resolved_by_close_remaining(tenant_a):
    from core.exceptions import BusinessRuleError

    prod = make_product(tenant_a.company, sku="UG-3")
    q = _quote(tenant_a, product=prod, quotation_date="2026-01-01", valid_until="2026-01-31")
    _to_order(tenant_a, q, qty=2)
    quote_url = f"/api/v1/sales/quotations/{q['id']}"
    # The quote is expired and partly converted: it cannot be cancelled and it blocks the unit.
    refused = tenant_a.client.post(f"{quote_url}/cancel/", {}, format="json")
    assert refused.status_code == 400 and "Close remaining" in str(refused.data)
    with pytest.raises(BusinessRuleError):
        _unit_guard(prod)
    # Staff without cancel permission cannot close it; the owner can, and a reason is required.
    _grant(tenant_a, can_create_sales=True)
    assert tenant_a.staff_client.post(f"{quote_url}/close-remaining/", {"reason": "x"}, format="json").status_code == 403
    assert tenant_a.client.post(f"{quote_url}/close-remaining/", {}, format="json").status_code == 400
    closed = tenant_a.client.post(f"{quote_url}/close-remaining/", {"reason": "Customer went elsewhere"}, format="json")
    assert closed.status_code == 200, closed.data
    assert closed.data["status"] == "CONVERTED" and closed.data["conversion_state"] == "CLOSED"
    assert Decimal(closed.data["remaining_total"]) == 0
    _unit_guard(prod)
    # It can no longer be converted.
    assert tenant_a.client.post(
        f"{quote_url}/convert-to-order/", {"confirm_expired": True}, format="json"
    ).status_code == 400
    # Releasing the order later keeps the quote closed.
    order = SalesOrder.objects.get(quotation_conversions__quotation_id=q["id"])
    tenant_a.client.delete(f"/api/v1/sales/orders/{order.pk}/")
    assert Quotation.objects.get(pk=q["id"]).status == Quotation.Status.CONVERTED
    # Only an owner can undo it.
    assert tenant_a.staff_client.post(f"{quote_url}/reopen-closed/", {"reason": "x"}, format="json").status_code == 403
    reopened = tenant_a.client.post(f"{quote_url}/reopen-closed/", {"reason": "Customer is back"}, format="json")
    assert reopened.status_code == 200 and reopened.data["status"] == "DRAFT"
    assert reopened.data["short_closed_at"] is None


def test_wp6_close_remaining_needs_converted_quantity_and_an_open_quote(tenant_a):
    q = _quote(tenant_a)
    url = f"/api/v1/sales/quotations/{q['id']}/close-remaining/"
    assert tenant_a.client.post(url, {"reason": "nothing converted"}, format="json").status_code == 400
    tenant_a.client.post(f"/api/v1/sales/quotations/{q['id']}/cancel/", {}, format="json")
    assert tenant_a.client.post(url, {"reason": "cancelled"}, format="json").status_code == 400


def test_wp6_cancel_expired_cancels_only_eligible_quotes(tenant_a):
    eligible = _quote(tenant_a, quotation_date="2026-01-01", valid_until="2026-01-31")
    partly = _quote(tenant_a, quotation_date="2026-01-01", valid_until="2026-01-31")
    _to_order(tenant_a, partly, qty=2)
    live = _quote(tenant_a)
    resp = tenant_a.client.post("/api/v1/sales/quotations/cancel-expired/", {}, format="json")
    assert resp.status_code == 200, resp.data
    assert resp.data["cancelled"] == 1
    assert [row["id"] for row in resp.data["needs_close_remaining"]] == [partly["id"]]
    assert Quotation.objects.get(pk=eligible["id"]).status == Quotation.Status.CANCELLED
    assert Quotation.objects.get(pk=live["id"]).status == Quotation.Status.DRAFT
    assert tenant_a.staff_client.post("/api/v1/sales/quotations/cancel-expired/", {}, format="json").status_code == 403


def test_wp6_cancel_expired_is_company_scoped(tenant_a, tenant_b):
    other = _quote(tenant_b, quotation_date="2026-01-01", valid_until="2026-01-31")
    tenant_a.client.post("/api/v1/sales/quotations/cancel-expired/", {}, format="json")
    assert Quotation.objects.get(pk=other["id"]).status == Quotation.Status.DRAFT


# ---------------------------------------------------------------- WP7 ------

def test_wp7_list_query_count_does_not_grow_with_rows(tenant_a, django_assert_max_num_queries):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    def count():
        with CaptureQueriesContext(connection) as ctx:
            resp = tenant_a.client.get("/api/v1/sales/quotations/?page_size=100")
        assert resp.status_code == 200
        return len(ctx), len(resp.data["results"])

    for _ in range(3):
        q = _quote(tenant_a)
        _to_order(tenant_a, q, qty=2)
    small_queries, small_rows = count()
    for _ in range(12):
        _quote(tenant_a)
    large_queries, large_rows = count()
    assert large_rows > small_rows
    assert large_queries <= small_queries + 2, (small_queries, large_queries)


def test_wp7_list_omits_conversions_but_retrieve_has_them(tenant_a):
    q = _quote(tenant_a)
    _to_order(tenant_a, q, qty=2)
    row = tenant_a.client.get("/api/v1/sales/quotations/").data["results"][0]
    assert row["conversions"] == [] and row["conversion_state"] == "PARTIAL"
    assert len(tenant_a.client.get(f"/api/v1/sales/quotations/{q['id']}/").data["conversions"]) == 1


# ---------------------------------------------------------------- WP8 ------

def test_wp8_expired_is_not_a_status(tenant_a):
    assert "EXPIRED" not in Quotation.Status.values
    assert tenant_a.client.get("/api/v1/sales/quotations/?status=EXPIRED").status_code == 400


# ---------------------------------------------------------------- WP9 ------

def _quote_with_salesman(tenant, name, channel):
    from payroll.models import Employee

    emp = Employee.objects.create(
        company=tenant.company, name=name, code=f"E{next(_n)}", salary=Decimal("1000"), created_by=tenant.owner
    )
    q = _quote(tenant, salesman=emp.id, sales_channel=channel)
    return q, emp


def test_wp9_invoice_made_from_an_order_shows_the_source_quote(tenant_a):
    q, emp = _quote_with_salesman(tenant_a, "Asha", "ONLINE")
    order = _to_order(tenant_a, q, qty=4)
    invoice = SalesInvoice.objects.create(
        company=tenant_a.company, customer=order.customer, source_order=order, created_by=tenant_a.owner
    )
    body = tenant_a.client.get(f"/api/v1/sales/invoices/{invoice.pk}/").data
    sources = body["source_quotations"]
    assert [s["id"] for s in sources] == [q["id"]]
    assert sources[0]["salesman_name"] == "Asha" and sources[0]["sales_channel"] == "ONLINE"
    assert sources[0]["primary"] is True and body["source_quotations_differ"] is False


def test_wp9_order_linked_through_converted_invoice_and_challan_is_traced(tenant_a):
    from sales.models import DeliveryChallan

    q = _quote(tenant_a)
    order = _to_order(tenant_a, q, qty=4)
    via_link = SalesInvoice.objects.create(company=tenant_a.company, customer=order.customer, created_by=tenant_a.owner)
    SalesOrder.objects.filter(pk=order.pk).update(converted_invoice=via_link)
    assert [s["id"] for s in tenant_a.client.get(f"/api/v1/sales/invoices/{via_link.pk}/").data["source_quotations"]] == [q["id"]]
    via_challan = SalesInvoice.objects.create(company=tenant_a.company, customer=order.customer, created_by=tenant_a.owner)
    DeliveryChallan.objects.create(
        company=tenant_a.company, customer=order.customer, sales_order=order,
        converted_invoice=via_challan, created_by=tenant_a.owner,
    )
    assert [s["id"] for s in tenant_a.client.get(f"/api/v1/sales/invoices/{via_challan.pk}/").data["source_quotations"]] == [q["id"]]


def test_wp9_direct_conversion_and_released_rows(tenant_a):
    q = _quote(tenant_a)
    resp = tenant_a.client.post(f"/api/v1/sales/quotations/{q['id']}/convert/", {}, format="json")
    detail = tenant_a.client.get(f"/api/v1/sales/invoices/{resp.data['id']}/").data
    assert [s["id"] for s in detail["source_quotations"]] == [q["id"]]
    QuotationConversion.objects.filter(quotation_id=q["id"]).update(released_at=timezone.now())
    assert tenant_a.client.get(f"/api/v1/sales/invoices/{resp.data['id']}/").data["source_quotations"] == []


def test_wp9_several_sources_pick_the_earliest_and_flag_the_difference(tenant_a):
    first, _ = _quote_with_salesman(tenant_a, "Asha", "ONLINE")
    second, _ = _quote_with_salesman(tenant_a, "Ravi", "WALK_IN")
    order = _to_order(tenant_a, first, qty=3)
    row = QuotationConversion.objects.get(sales_order=order)
    QuotationConversion.objects.create(
        company=tenant_a.company, quotation_id=second["id"], product_id=row.product_id,
        unit_price=row.unit_price, target="ORDER", sales_order=order, quantity=Decimal("1"),
    )
    body = tenant_a.client.get(f"/api/v1/sales/orders/{order.pk}/").data
    ids = [s["id"] for s in body["source_quotations"]]
    assert ids == sorted(ids) and body["source_quotations_differ"] is True
    assert [s["primary"] for s in body["source_quotations"]] == [True, False]


def test_wp9_list_action_returns_no_sources(tenant_a):
    q = _quote(tenant_a)
    _to_order(tenant_a, q, qty=3)
    rows = tenant_a.client.get("/api/v1/sales/orders/").data["results"]
    assert rows and rows[0]["source_quotations"] == []


# ---------------------------------------------------------------- WP12 -----

def test_wp12_staff_never_sees_cost_on_quote_order_or_challan(tenant_a):
    _grant(tenant_a, can_create_sales=True)
    prod = make_product(tenant_a.company, sku="COST-1", purchase_price="60")
    q = _quote(tenant_a, product=prod)
    order = _to_order(tenant_a, q, qty=4)
    owner_order = tenant_a.client.get(f"/api/v1/sales/orders/{order.pk}/").data
    staff_order = tenant_a.staff_client.get(f"/api/v1/sales/orders/{order.pk}/")
    assert owner_order["items"][0]["expected_price"] is not None
    assert staff_order.status_code == 200 and staff_order.data["items"][0]["expected_price"] is None
    staff_quote = tenant_a.staff_client.get(f"/api/v1/sales/quotations/{q['id']}/").data
    assert staff_quote["items"][0]["expected_price"] is None
    assert staff_quote["expected_profit"] is None
    assert "expected_price" not in str(tenant_a.staff_client.get(f"/api/v1/sales/quotations/{q['id']}/revisions/").data)


def test_wp12_staff_edit_keeps_the_stored_cost_on_an_order(tenant_a):
    _grant(tenant_a, can_create_sales=True)
    prod = make_product(tenant_a.company, sku="COST-2", purchase_price="60")
    q = _quote(tenant_a, product=prod)
    order = _to_order(tenant_a, q, qty=4)
    cost = order.items.get().expected_price
    assert cost > 0
    line = {"product": prod.id, "quantity": "3", "unit_price": "100.00", "gst_rate": "18"}
    resp = tenant_a.staff_client.patch(f"/api/v1/sales/orders/{order.pk}/", {"items": [line]}, format="json")
    assert resp.status_code == 200, resp.data
    assert order.items.get().expected_price == cost


def test_wp12_revisions_need_the_create_permission(tenant_a):
    q = _quote(tenant_a)
    url = f"/api/v1/sales/quotations/{q['id']}/revisions/"
    assert tenant_a.staff_client.get(url).status_code == 403
    assert tenant_a.client.get(url).status_code == 200


def test_wp12_quotes_do_not_change_customer_totals_or_the_day_book(tenant_a):
    from reporting.transactions import day_book

    cust = make_customer(tenant_a.company, name="Ledger Co")
    before = tenant_a.client.get(f"/api/v1/reports/customer-ledger/{cust.id}/")
    assert before.status_code == 200, before.data
    _quote(tenant_a, customer=cust, quotation_date=timezone.localdate().isoformat())
    after = tenant_a.client.get(f"/api/v1/reports/customer-ledger/{cust.id}/")
    for key in ("total_sales", "total_received", "outstanding"):
        if key in before.data:
            assert before.data[key] == after.data[key], key
    book = day_book(tenant_a.company, timezone.localdate())
    assert "QUOTATION" not in str(book)


def test_wp12_update_is_audited_with_changed_fields(tenant_a):
    from core.models import AuditEvent

    q = _quote(tenant_a)
    resp = tenant_a.client.patch(
        f"/api/v1/sales/quotations/{q['id']}/", {"valid_until": "2099-05-05", "notes": "n"}, format="json"
    )
    assert resp.status_code == 200
    entry = AuditEvent.objects.filter(entity_type="Quotation", entity_id=str(q["id"]), action="QUOTATION_UPDATED").first()
    assert entry is not None
    assert set(entry.metadata["changed"]) >= {"valid_until", "notes"}
    assert entry.metadata["before"]["valid_until"] == "2099-03-15"
    assert entry.metadata["after"]["valid_until"] == "2099-05-05"


def test_wp12_error_codes_are_documented_in_the_schema():
    from django.conf import settings  # noqa: F401
    import json
    import pathlib

    snapshot = json.loads((pathlib.Path(__file__).resolve().parents[2] / "docs" / "openapi-snapshot.json").read_text("utf-8"))
    text = json.dumps(snapshot["paths"].get("/api/v1/sales/quotations/{id}/", {}))
    for code in ("quotation_lines_locked", "quotation_fields_locked", "quotation_not_editable"):
        assert code in text, code


# ---------------------------------------------------------------- WP13 -----

def test_wp13_search_finds_quotes_by_number_customer_name_and_phone(tenant_a, tenant_b):
    cust = make_customer(tenant_a.company, name="Zenith Traders", phone="9123456789")
    q = _quote(tenant_a, customer=cust)
    other_cust = make_customer(tenant_b.company, name="Zenith Traders", phone="9123456789")
    _quote(tenant_b, customer=other_cust)
    for term in (q["number"], "Zenith", "9123456"):
        body = tenant_a.client.get("/api/v1/search/", {"q": term}).data
        body = body.get("data", body)
        ids = [row["id"] for row in body.get("quotations", [])]
        assert ids == [q["id"]], (term, body.get("quotations"))
        assert body["quotations"][0]["customer_name"] == "Zenith Traders"


# ---------------------------------------------------------------- WP14b ----

def test_wp14b_share_makes_a_link_marks_sent_and_serves_the_pdf(tenant_a):
    from payments.portal_views import CustomerPortalReadThrottle  # noqa: F401
    from rest_framework.test import APIClient

    tenant_a.company.feature_flags = {**(tenant_a.company.feature_flags or {}), "QUOTE_LIFECYCLE": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    q = _quote(tenant_a)
    resp = tenant_a.client.post(f"/api/v1/sales/quotations/{q['id']}/share/", {"channel": "whatsapp"}, format="json")
    assert resp.status_code == 200, resp.data
    assert resp.data["status"] == "SENT" and resp.data["sent_at"]
    token = resp.data["url"].rsplit("/", 1)[-1]
    anon = APIClient()
    page = anon.get(f"/api/v1/public/quotations/{token}/")
    assert page.status_code == 200 and page.data["number"] == q["number"]
    pdf = anon.get(f"/api/v1/public/quotations/{token}/pdf/")
    assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf"
    again = tenant_a.client.post(f"/api/v1/sales/quotations/{q['id']}/share/", {}, format="json")
    assert again.data["url"] == resp.data["url"]


def test_wp14b_share_without_lifecycle_keeps_draft_but_stamps_sent_at(tenant_a):
    q = _quote(tenant_a)
    resp = tenant_a.client.post(f"/api/v1/sales/quotations/{q['id']}/share/", {}, format="json")
    assert resp.status_code == 200 and resp.data["status"] == "DRAFT" and resp.data["sent_at"]


def test_wp14b_link_rules_expired_revoked_cancelled_and_reopened(tenant_a):
    from rest_framework.test import APIClient

    tenant_a.company.feature_flags = {**(tenant_a.company.feature_flags or {}), "QUOTE_LIFECYCLE": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    anon = APIClient()

    def token_for(quote):
        r = tenant_a.client.post(f"/api/v1/sales/quotations/{quote['id']}/share/", {}, format="json")
        return r.data["url"].rsplit("/", 1)[-1]

    expired = _quote(tenant_a)
    tok = token_for(expired)
    Quotation.objects.filter(pk=expired["id"]).update(valid_until=timezone.localdate() - timedelta(days=1))
    assert anon.get(f"/api/v1/public/quotations/{tok}/").status_code == 410

    cancelled = _quote(tenant_a)
    tok = token_for(cancelled)
    tenant_a.client.post(f"/api/v1/sales/quotations/{cancelled['id']}/cancel/", {}, format="json")
    assert anon.get(f"/api/v1/public/quotations/{tok}/").status_code == 404

    edited = _quote(tenant_a)
    tok = token_for(edited)
    assert anon.get(f"/api/v1/public/quotations/{tok}/").status_code == 200
    patched = tenant_a.client.patch(f"/api/v1/sales/quotations/{edited['id']}/", {"notes": "new terms"}, format="json")
    assert patched.status_code == 200 and patched.data["status"] == "DRAFT"
    assert anon.get(f"/api/v1/public/quotations/{tok}/").status_code == 404
    assert token_for(edited) != tok

    revoked = _quote(tenant_a)
    tok = token_for(revoked)
    assert tenant_a.client.post(f"/api/v1/sales/quotations/{revoked['id']}/public-link/revoke/").data["revoked"] is True
    assert anon.get(f"/api/v1/public/quotations/{tok}/").status_code == 404
    assert anon.get("/api/v1/public/quotations/not-a-token/").status_code == 404


def test_wp14b_converted_quote_link_stays_readable_until_expiry(tenant_a):
    from rest_framework.test import APIClient

    q = _quote(tenant_a)
    tok = tenant_a.client.post(f"/api/v1/sales/quotations/{q['id']}/share/", {}, format="json").data["url"].rsplit("/", 1)[-1]
    tenant_a.client.post(f"/api/v1/sales/quotations/{q['id']}/convert/", {}, format="json")
    assert Quotation.objects.get(pk=q["id"]).status == Quotation.Status.CONVERTED
    assert APIClient().get(f"/api/v1/public/quotations/{tok}/").status_code == 200


def test_wp14b_other_tenant_cannot_share_a_quote(tenant_a, tenant_b):
    q = _quote(tenant_a)
    assert tenant_b.client.post(f"/api/v1/sales/quotations/{q['id']}/share/", {}, format="json").status_code == 404


def test_wp14b_duplicate_makes_a_clean_draft_with_a_new_number_and_keeps_cost(tenant_a):
    _grant(tenant_a, can_create_sales=True)
    prod = make_product(tenant_a.company, sku="DUP-1", purchase_price="60")
    q = _quote(tenant_a, product=prod, additional_charges="30", notes="keep me")
    _to_order(tenant_a, q, qty=4)
    resp = tenant_a.staff_client.post(f"/api/v1/sales/quotations/{q['id']}/duplicate/", {}, format="json")
    assert resp.status_code == 201, resp.data
    copy = Quotation.objects.get(pk=resp.data["id"])
    source = Quotation.objects.get(pk=q["id"])
    assert copy.number and copy.number != source.number
    assert copy.status == Quotation.Status.DRAFT and copy.copied_from_id == source.id
    assert copy.notes == "keep me" and copy.additional_charges == Decimal("30.00")
    assert copy.items.get().converted_quantity == 0 and copy.items.get().quantity == Decimal("10")
    assert copy.items.get().expected_price == source.items.get().expected_price > 0
    assert not QuotationConversion.objects.filter(quotation=copy).exists()
    assert source.items.get().converted_quantity == Decimal("4")
    assert resp.data["copied_from"] == source.id


def test_wp14b_duplicate_of_a_blocked_customer_is_refused(tenant_a):
    q = _quote(tenant_a)
    Quotation.objects.get(pk=q["id"]).customer.__class__.objects.filter(pk=Quotation.objects.get(pk=q["id"]).customer_id).update(status="BLOCKED")
    assert tenant_a.client.post(f"/api/v1/sales/quotations/{q['id']}/duplicate/", {}, format="json").status_code == 400


# ---------------------------------------------------------------- alerts ---

def test_wp14b_expiry_alerts_for_open_quotes_only(tenant_a):
    from insights.alerts import build_business_alerts

    today = timezone.localdate()
    soon = _quote(tenant_a, quotation_date=today.isoformat(), valid_until=(today + timedelta(days=2)).isoformat())
    recent = _quote(tenant_a, quotation_date=(today - timedelta(days=20)).isoformat(),
                    valid_until=(today - timedelta(days=3)).isoformat())
    _quote(tenant_a, quotation_date=today.isoformat(), valid_until=(today + timedelta(days=40)).isoformat())
    old = _quote(tenant_a, quotation_date=(today - timedelta(days=90)).isoformat(),
                 valid_until=(today - timedelta(days=40)).isoformat())
    cancelled = _quote(tenant_a, quotation_date=today.isoformat(), valid_until=(today + timedelta(days=1)).isoformat())
    tenant_a.client.post(f"/api/v1/sales/quotations/{cancelled['id']}/cancel/", {}, format="json")
    rows = [a for a in build_business_alerts(tenant_a.company) if a["code"].startswith("QUOTATION_")]
    by_id = {a["document_id"]: a["code"] for a in rows}
    assert by_id == {soon["id"]: "QUOTATION_EXPIRING", recent["id"]: "QUOTATION_EXPIRED"}
    assert old["id"] not in by_id


def test_salespeople_endpoint_works_for_sales_staff_without_payroll(tenant_a, tenant_b):
    from payroll.models import Employee

    Employee.objects.create(company=tenant_a.company, name="Asha Rao", code="E1", salary=Decimal("1"), created_by=tenant_a.owner)
    Employee.objects.create(company=tenant_a.company, name="Old Hand", code="E2", salary=Decimal("1"),
                            status="INACTIVE", created_by=tenant_a.owner)
    Employee.objects.create(company=tenant_b.company, name="Asha Other", code="E1", salary=Decimal("1"), created_by=tenant_b.owner)
    _grant(tenant_a, can_create_sales=True)
    body = tenant_a.staff_client.get("/api/v1/sales/salespeople/", {"q": "asha"}).data
    assert [row["name"] for row in body["results"]] == ["Asha Rao"]
    assert set(body["results"][0]) == {"id", "name", "code"}
    assert tenant_a.staff_client.get("/api/v1/sales/salespeople/").data["results"][0]["name"] == "Asha Rao"


def test_stock_hint_reports_available_quantity_in_the_default_godown(tenant_a, tenant_b):
    from tests.conftest import add_stock

    tracked = make_product(tenant_a.company, sku="HINT-1")
    add_stock(tenant_a, tracked, "12", unit_cost="50")
    other = make_product(tenant_b.company, sku="HINT-2")
    add_stock(tenant_b, other, "99", unit_cost="50")
    resp = tenant_a.client.get("/api/v1/sales/stock-hints/", {"products": f"{tracked.id},{other.id},abc"})
    assert resp.status_code == 200
    body = resp.data
    assert Decimal(body["available"][str(tracked.id)]) == Decimal("12")
    assert str(other.id) not in body["available"]
    assert tenant_a.client.get("/api/v1/sales/stock-hints/").data["available"] == {}



def test_wp16_convert_chain_answers_with_sunset_headers_then_410(tenant_a, monkeypatch):
    from datetime import date

    from sales.views import QuotationViewSet

    q = _quote(tenant_a)
    url = f"/api/v1/sales/quotations/{q['id']}/convert-chain/"
    monkeypatch.setattr(QuotationViewSet, "CONVERT_CHAIN_SUNSET_DATE", date(2099, 1, 1))
    before = tenant_a.client.post(url, {"stop_stage": "SALES_ORDER"}, format="json")
    assert before.status_code == 200, before.data
    assert before["Deprecation"] == "true" and before["Sunset"]
    monkeypatch.setattr(QuotationViewSet, "CONVERT_CHAIN_SUNSET_DATE", date(2020, 1, 1))
    gone = tenant_a.client.post(url, {"stop_stage": "SALES_ORDER"}, format="json")
    assert gone.status_code == 410 and gone.data["code"] == "convert_chain_gone"


def test_a11_deleting_a_draft_records_its_number_in_the_audit_trail(tenant_a):
    from core.models import AuditEvent

    q = _quote(tenant_a)
    assert tenant_a.client.delete(f"/api/v1/sales/quotations/{q['id']}/").status_code == 204
    entry = AuditEvent.objects.get(entity_type="Quotation", entity_id=str(q["id"]), action="DELETE")
    assert entry.metadata["number"] == q["number"]
    assert entry.metadata["customer"] == q["customer"]


def test_wp12_staff_never_sees_cost_on_a_delivery_challan_either(tenant_a):
    from sales.notes_services import SalesNotesService

    _grant(tenant_a, can_create_sales=True)
    prod = make_product(tenant_a.company, sku="COST-3", purchase_price="60")
    from tests.conftest import add_stock

    add_stock(tenant_a, prod, "20", unit_cost="50")
    q = _quote(tenant_a, product=prod)
    order = _to_order(tenant_a, q, qty=4)
    SalesNotesService.confirm_sales_order(order, tenant_a.owner)
    order.refresh_from_db()
    challan = SalesNotesService.convert_sales_order_to_challan(order, tenant_a.owner)
    owner_view = tenant_a.client.get(f"/api/v1/sales/delivery-challans/{challan.pk}/").data
    staff_view = tenant_a.staff_client.get(f"/api/v1/sales/delivery-challans/{challan.pk}/")
    assert owner_view["items"][0]["expected_price"] is not None
    assert staff_view.status_code == 200 and staff_view.data["items"][0]["expected_price"] is None



def test_wp9_sources_are_only_looked_up_on_a_detail_read(tenant_a):
    q = _quote(tenant_a)
    order = _to_order(tenant_a, q, qty=3)
    invoice = SalesInvoice.objects.create(
        company=tenant_a.company, customer=order.customer, source_order=order, created_by=tenant_a.owner
    )
    detail = tenant_a.client.get(f"/api/v1/sales/invoices/{invoice.pk}/").data
    assert [s["id"] for s in detail["source_quotations"]] == [q["id"]]
    listed = tenant_a.client.get("/api/v1/sales/invoices/").data["results"][0]
    assert listed["source_quotations"] == [] and listed["source_quotations_differ"] is False


def test_product_cost_permission_matrix_omits_the_field_and_keeps_below_cost(tenant_a):
    """QOS-0115: the permission rule now runs, through the same mask as the role rule."""
    prod = make_product(tenant_a.company, sku="PRICE-9", purchase_price="60", selling_price="50")
    url = f"/api/v1/products/{prod.id}/"
    owner = tenant_a.client.get(url).data
    assert owner["purchase_price"] is not None
    _grant(tenant_a, can_create_sales=True)
    staff = tenant_a.staff_client.get(url).data
    assert "purchase_price" not in staff and staff["below_cost"] is True
    # A role that may normally see money still loses cost when it holds no cost permission.
    CompanyUser.objects.filter(user=tenant_a.staff).update(
        role="MANAGER", can_view_financial_reports=False, can_create_purchases=False, can_manage_inventory=False
    )
    bare = tenant_a.staff_client.get(url).data
    assert "purchase_price" not in bare and bare["below_cost"] is True
    CompanyUser.objects.filter(user=tenant_a.staff).update(can_view_financial_reports=True)
    assert tenant_a.staff_client.get(url).data["purchase_price"] is not None
