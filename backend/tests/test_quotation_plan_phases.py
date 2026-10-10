"""Regression tests for the quotation remediation plan (phases 2, 4, 6, 8, 9, 10)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from sales.models import Quotation, QuotationConversion
from tests.conftest import make_customer, make_product

pytestmark = pytest.mark.django_db

LINE = {"quantity": "10", "unit_price": "100.00", "gst_rate": "18"}


def _make_quote(tenant, customer, product, **extra):
    body = {
        "customer": customer.id,
        "quotation_date": "2026-03-01",
        "valid_until": "2099-03-15",
        "items": [{"product": product.id, **LINE}],
        **extra,
    }
    resp = tenant.client.post("/api/v1/sales/quotations/", body, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data


def _partial_quote(tenant, qty=4):
    cust = make_customer(tenant.company, name="Partial Co")
    prod = make_product(tenant.company, selling_price="100.00", purchase_price="60")
    quote = _make_quote(tenant, cust, prod)
    conv = tenant.client.post(
        f"/api/v1/sales/quotations/{quote['id']}/convert-to-order/",
        {"items": [{"id": quote["items"][0]["id"], "quantity": qty}]},
        format="json",
    )
    assert conv.status_code == 200, conv.data
    return Quotation.objects.get(pk=quote["id"]), cust, prod, conv.data


def _patch(tenant, qid, body):
    return tenant.client.patch(f"/api/v1/sales/quotations/{qid}/", body, format="json")


# ---- Phase 2: safe updates ------------------------------------------------

def test_partial_quote_rejected_patch_writes_nothing(tenant_a):
    q, _c, prod, _ = _partial_quote(tenant_a)
    resp = _patch(tenant_a, q.id, {"notes": "should not stick", "items": [{"product": prod.id, **LINE}]})
    assert resp.status_code == 400
    q.refresh_from_db()
    assert q.notes != "should not stick"


def test_partial_quote_rejects_items_even_if_identical(tenant_a):
    q, _c, prod, _ = _partial_quote(tenant_a)
    assert _patch(tenant_a, q.id, {"items": [{"product": prod.id, **LINE}]}).status_code == 400


def test_partial_quote_rejects_price_change(tenant_a):
    q, _c, prod, _ = _partial_quote(tenant_a)
    price = q.items.get().unit_price
    resp = _patch(tenant_a, q.id, {"items": [{"product": prod.id, **{**LINE, "unit_price": "250.00"}}]})
    assert resp.status_code == 400
    assert q.items.get().unit_price == price


def test_partial_quote_rejects_customer_and_discount(tenant_a):
    q, cust, _p, _ = _partial_quote(tenant_a)
    other = make_customer(tenant_a.company, name="Someone Else")
    total = q.grand_total
    resp = _patch(tenant_a, q.id, {"customer": other.id, "invoice_discount": "100"})
    assert resp.status_code == 400
    assert "customer" in str(resp.data) and "invoice_discount" in str(resp.data)
    q.refresh_from_db()
    assert q.customer_id == cust.id and q.grand_total == total


def test_partial_quote_allows_whitelisted_header(tenant_a):
    q, *_ = _partial_quote(tenant_a)
    resp = _patch(tenant_a, q.id, {
        "valid_until": "2099-04-01", "delivery_address": "Dock 4", "notes": "n", "terms_text": "t",
    })
    assert resp.status_code == 200, resp.data
    q.refresh_from_db()
    assert (q.valid_until, q.delivery_address, q.notes, q.terms_text) == (date(2099, 4, 1), "Dock 4", "n", "t")


def test_unconverted_header_change_recomputes_totals_and_keeps_cost(tenant_a):
    cust = make_customer(tenant_a.company)
    prod = make_product(tenant_a.company, purchase_price="60")
    q = Quotation.objects.get(pk=_make_quote(tenant_a, cust, prod)["id"])
    before, cost = q.grand_total, q.items.get().expected_price
    resp = _patch(tenant_a, q.id, {"invoice_discount": "100"})
    assert resp.status_code == 200, resp.data
    q.refresh_from_db()
    assert q.grand_total < before
    assert q.items.get().expected_price == cost


def test_unconverted_items_patch_still_replaces_lines(tenant_a):
    cust = make_customer(tenant_a.company)
    prod = make_product(tenant_a.company)
    quote = _make_quote(tenant_a, cust, prod)
    resp = _patch(tenant_a, quote["id"], {"items": [{"product": prod.id, **{**LINE, "quantity": "3"}}]})
    assert resp.status_code == 200, resp.data
    assert Quotation.objects.get(pk=quote["id"]).items.get().quantity == Decimal("3")


def test_edit_with_mixed_line_ids_upserts_in_place(tenant_a):
    cust = make_customer(tenant_a.company)
    prod = make_product(tenant_a.company)
    quote = _make_quote(tenant_a, cust, prod)
    line_id = quote["items"][0]["id"]
    resp = _patch(tenant_a, quote["id"], {"items": [
        {"id": line_id, "product": prod.id, **{**LINE, "quantity": "5"}},
        {"product": prod.id, **{**LINE, "quantity": "2"}},
    ]})
    assert resp.status_code == 200, resp.data
    items = Quotation.objects.get(pk=quote["id"]).items
    assert items.filter(pk=line_id).exists()
    assert sorted(items.values_list("quantity", flat=True)) == [Decimal("2"), Decimal("5")]


def test_non_draft_quote_cannot_be_edited(tenant_a):
    cust = make_customer(tenant_a.company)
    prod = make_product(tenant_a.company)
    quote = _make_quote(tenant_a, cust, prod)
    assert tenant_a.client.post(f"/api/v1/sales/quotations/{quote['id']}/cancel/").status_code == 200
    assert _patch(tenant_a, quote["id"], {"notes": "x"}).status_code == 400


def test_convert_expired_requires_confirmation(tenant_a):
    cust = make_customer(tenant_a.company)
    prod = make_product(tenant_a.company)
    quote = _make_quote(tenant_a, cust, prod, quotation_date="2026-01-01", valid_until="2026-01-02")
    url = f"/api/v1/sales/quotations/{quote['id']}/convert/"
    assert tenant_a.client.post(url, {}, format="json").status_code == 400
    assert tenant_a.client.post(url, {"confirm_expired": True}, format="json").status_code == 200


# ---- Phase 4: filters -----------------------------------------------------

def test_quotation_filter_by_customer_and_search(tenant_a):
    c1 = make_customer(tenant_a.company, name="One", phone="9876500001")
    c2 = make_customer(tenant_a.company, name="Two", phone="9876500002")
    prod = make_product(tenant_a.company)
    q1 = _make_quote(tenant_a, c1, prod)
    q2 = _make_quote(tenant_a, c2, prod)

    def ids(qs):
        return {r["id"] for r in tenant_a.client.get(f"/api/v1/sales/quotations/?{qs}").data["results"]}

    assert ids(f"customer={c1.id}") == {q1["id"]}
    assert ids(f"q={q2['number']}") == {q2["id"]}
    assert ids("q=9876500002") == {q2["id"]}


@pytest.mark.parametrize("qs", ["status=BOGUS", "customer=abc", "date_from=notadate", "ordering=bogus"])
def test_quotation_invalid_filters_return_400(tenant_a, qs):
    assert tenant_a.client.get(f"/api/v1/sales/quotations/?{qs}").status_code == 400


def test_quotation_list_is_company_scoped(tenant_a, tenant_b):
    cb = make_customer(tenant_b.company, name="Shared Name")
    _make_quote(tenant_b, cb, make_product(tenant_b.company))
    ca = make_customer(tenant_a.company, name="Shared Name")
    qa = _make_quote(tenant_a, ca, make_product(tenant_a.company))
    rows = tenant_a.client.get("/api/v1/sales/quotations/?q=Shared").data["results"]
    assert [r["id"] for r in rows] == [qa["id"]]


def test_quotation_ordering_by_total(tenant_a):
    cust = make_customer(tenant_a.company)
    prod = make_product(tenant_a.company)
    small = _make_quote(tenant_a, cust, prod, items=[{"product": prod.id, **{**LINE, "quantity": "1"}}])
    big = _make_quote(tenant_a, cust, prod)
    rows = tenant_a.client.get("/api/v1/sales/quotations/?ordering=-grand_total").data["results"]
    assert [r["id"] for r in rows] == [big["id"], small["id"]]


# ---- Cancel permission and reason ----------------------------------------

def test_staff_without_cancel_permission_gets_403(tenant_a):
    cust = make_customer(tenant_a.company)
    quote = _make_quote(tenant_a, cust, make_product(tenant_a.company))
    assert tenant_a.staff_client.post(f"/api/v1/sales/quotations/{quote['id']}/cancel/").status_code == 403


def test_cancel_stores_reason(tenant_a):
    cust = make_customer(tenant_a.company)
    quote = _make_quote(tenant_a, cust, make_product(tenant_a.company))
    resp = tenant_a.client.post(
        f"/api/v1/sales/quotations/{quote['id']}/cancel/", {"reason": "Customer left"}, format="json"
    )
    assert resp.status_code == 200
    assert resp.data["cancel_reason"] == "Customer left"


# ---- Phase 8: delete lock-down and cost masking ---------------------------

def test_delete_blocked_for_partial_and_cancelled(tenant_a):
    q, *_ = _partial_quote(tenant_a)
    assert tenant_a.client.delete(f"/api/v1/sales/quotations/{q.id}/").status_code == 400
    assert Quotation.objects.filter(pk=q.id).exists()
    cust = make_customer(tenant_a.company, name="Cx")
    other = _make_quote(tenant_a, cust, make_product(tenant_a.company, sku="CX-1"))
    tenant_a.client.post(f"/api/v1/sales/quotations/{other['id']}/cancel/")
    assert tenant_a.client.delete(f"/api/v1/sales/quotations/{other['id']}/").status_code == 400


def test_delete_allowed_for_unconverted_draft(tenant_a):
    cust = make_customer(tenant_a.company)
    quote = _make_quote(tenant_a, cust, make_product(tenant_a.company))
    assert tenant_a.client.delete(f"/api/v1/sales/quotations/{quote['id']}/").status_code == 204


def test_internal_cost_hidden_from_sales_staff_and_preserved(tenant_a):
    cust = make_customer(tenant_a.company)
    prod = make_product(tenant_a.company, purchase_price="60")
    quote = _make_quote(tenant_a, cust, prod)
    from accounts.models import CompanyUser

    CompanyUser.objects.filter(user=tenant_a.staff).update(can_create_sales=True)
    owner_view = tenant_a.client.get(f"/api/v1/sales/quotations/{quote['id']}/").data
    assert owner_view["items"][0]["expected_price"] is not None
    staff_view = tenant_a.staff_client.get(f"/api/v1/sales/quotations/{quote['id']}/")
    assert staff_view.status_code == 200
    assert staff_view.data["items"][0]["expected_price"] is None
    cost = Quotation.objects.get(pk=quote["id"]).items.get().expected_price
    line = {"id": quote["items"][0]["id"], "product": prod.id, **{**LINE, "quantity": "7"}}
    resp = tenant_a.staff_client.patch(f"/api/v1/sales/quotations/{quote['id']}/", {"items": [line]}, format="json")
    assert resp.status_code == 200, resp.data
    assert Quotation.objects.get(pk=quote["id"]).items.get().expected_price == cost


# ---- Phase 9: conversion ledger -------------------------------------------

def test_two_partial_orders_create_two_ledger_rows(tenant_a):
    cust = make_customer(tenant_a.company)
    prod = make_product(tenant_a.company)
    quote = _make_quote(tenant_a, cust, prod)
    item_id = quote["items"][0]["id"]
    for qty in (4, 3):
        r = tenant_a.client.post(
            f"/api/v1/sales/quotations/{quote['id']}/convert-to-order/",
            {"items": [{"id": item_id, "quantity": qty}]}, format="json",
        )
        assert r.status_code == 200, r.data
    assert QuotationConversion.objects.filter(quotation_id=quote["id"], target="ORDER").count() == 2
    assert Quotation.objects.get(pk=quote["id"]).items.get().converted_quantity == Decimal("7")
    data = tenant_a.client.get(f"/api/v1/sales/quotations/{quote['id']}/").data
    assert len(data["conversions"]) == 2
    assert data["conversion_state"] == "PARTIAL"


def test_deleted_draft_invoice_releases_quote_when_flag_on(tenant_a):
    company = tenant_a.company
    company.feature_flags = {**(company.feature_flags or {}), "QUOTE_CONVERSION_RELEASE": True}
    company.save(update_fields=["feature_flags"])
    cust = make_customer(company)
    prod = make_product(company)
    quote = _make_quote(tenant_a, cust, prod)
    r = tenant_a.client.post(f"/api/v1/sales/quotations/{quote['id']}/convert/", {}, format="json")
    assert r.status_code == 200, r.data
    assert Quotation.objects.get(pk=quote["id"]).status == Quotation.Status.CONVERTED
    assert tenant_a.client.delete(f"/api/v1/sales/invoices/{r.data['id']}/").status_code == 204
    q = Quotation.objects.get(pk=quote["id"])
    assert q.status == Quotation.Status.DRAFT
    assert q.items.get().converted_quantity == 0
    # Released history keeps the quote undeletable, but its line can still be edited in place.
    assert tenant_a.client.delete(f"/api/v1/sales/quotations/{q.id}/").status_code == 400
    ok = _patch(tenant_a, q.id, {"items": [{"id": quote["items"][0]["id"], "product": prod.id, **LINE}]})
    assert ok.status_code == 200, ok.data


def test_reopen_requires_owner_and_reason_and_keeps_ledger_invariant(tenant_a):
    q, *_ = _partial_quote(tenant_a)
    url = f"/api/v1/sales/quotations/{q.id}/reopen/"
    assert tenant_a.staff_client.post(url, {"reason": "x"}, format="json").status_code == 403
    assert tenant_a.client.post(url, {}, format="json").status_code == 400
    assert tenant_a.client.post(url, {"reason": "mistake"}, format="json").status_code == 200
    for item in q.items.all():
        live = sum(
            (c.quantity for c in QuotationConversion.objects.filter(quotation_item=item, released_at__isnull=True)),
            Decimal("0"),
        )
        assert item.converted_quantity == live == 0


# ---- Phase 6: server-decided expiry ---------------------------------------

def test_is_expired_is_decided_by_server(tenant_a):
    cust = make_customer(tenant_a.company)
    prod = make_product(tenant_a.company)
    old = _make_quote(tenant_a, cust, prod, quotation_date="2026-01-01", valid_until="2026-01-02")
    fresh = _make_quote(tenant_a, cust, prod)
    assert tenant_a.client.get(f"/api/v1/sales/quotations/{old['id']}/").data["is_expired"] is True
    assert tenant_a.client.get(f"/api/v1/sales/quotations/{fresh['id']}/").data["is_expired"] is False


# ---- Phase 10: create consistency ----------------------------------------

def test_valid_until_before_date_and_blocked_customer_rejected(tenant_a):
    cust = make_customer(tenant_a.company)
    prod = make_product(tenant_a.company)
    body = {"customer": cust.id, "quotation_date": "2026-03-10", "valid_until": "2026-03-01",
            "items": [{"product": prod.id, **LINE}]}
    assert tenant_a.client.post("/api/v1/sales/quotations/", body, format="json").status_code == 400
    blocked = make_customer(tenant_a.company, name="Blocked", status="BLOCKED")
    body = {"customer": blocked.id, "items": [{"product": prod.id, **LINE}]}
    assert tenant_a.client.post("/api/v1/sales/quotations/", body, format="json").status_code == 400


def test_create_gets_number_and_default_address(tenant_a):
    cust = make_customer(tenant_a.company, shipping_address="12 Market Rd")
    quote = _make_quote(tenant_a, cust, make_product(tenant_a.company))
    assert quote["number"]
    assert quote["delivery_address"] == "12 Market Rd"


# ---- Phase 12: lifecycle is flag-gated ------------------------------------

def test_lifecycle_actions_are_forbidden_while_flag_is_off(tenant_a):
    cust = make_customer(tenant_a.company)
    quote = _make_quote(tenant_a, cust, make_product(tenant_a.company))
    resp = tenant_a.client.post(f"/api/v1/sales/quotations/{quote['id']}/mark-sent/")
    assert resp.status_code == 403


def test_lifecycle_sent_edit_snapshots_revision_when_flag_on(tenant_a):
    company = tenant_a.company
    company.feature_flags = {**(company.feature_flags or {}), "QUOTE_LIFECYCLE": True}
    company.save(update_fields=["feature_flags"])
    cust = make_customer(company)
    quote = _make_quote(tenant_a, cust, make_product(company))
    base = f"/api/v1/sales/quotations/{quote['id']}"
    assert tenant_a.client.post(f"{base}/mark-sent/").status_code == 200
    resp = _patch(tenant_a, quote["id"], {"notes": "changed after sending"})
    assert resp.status_code == 200, resp.data
    assert resp.data["status"] == "DRAFT"
    revisions = tenant_a.client.get(f"{base}/revisions/").data
    assert len(revisions) == 1
    assert "expected_price" not in str(revisions[0]["snapshot"])


# ---- Phase 9: campaign revenue follows every conversion path ---------------

def _won_opportunity(tenant, customer):
    from crm.models import Opportunity

    return Opportunity.objects.create(
        company=tenant.company, customer=customer, title="Deal", amount=Decimal("0"),
        stage=Opportunity.Stage.WON, created_by=tenant.owner,
    )


def _complete(model, pk, taxable="1000.00"):
    model.objects.filter(pk=pk).update(status="COMPLETED", taxable_total=Decimal(taxable))


def test_campaign_revenue_counts_partial_quote_to_order_to_invoice(tenant_a):
    from crm.campaigns import _won_revenue
    from sales.models import SalesInvoice, SalesOrder

    company = tenant_a.company
    cust = make_customer(company)
    opp = _won_opportunity(tenant_a, cust)
    quote = _make_quote(tenant_a, cust, make_product(company), opportunity=opp.id)
    Quotation.objects.filter(pk=quote["id"]).update(opportunity=opp)
    assert _won_revenue(opp)[1] == "no_completed_invoice"

    r = tenant_a.client.post(
        f"/api/v1/sales/quotations/{quote['id']}/convert-to-order/",
        {"items": [{"id": quote["items"][0]["id"], "quantity": 4}]}, format="json",
    )
    assert r.status_code == 200, r.data
    order = SalesOrder.objects.get(pk=r.data["id"])
    invoice = SalesInvoice.objects.create(
        company=company, customer=cust, source_order=order, created_by=tenant_a.owner,
    )
    _complete(SalesInvoice, invoice.pk)
    amount, source = _won_revenue(opp)
    assert (amount, source) == (Decimal("1000.00"), "completed_invoice_taxable_net")


def test_campaign_revenue_ignores_released_conversions(tenant_a):
    from crm.campaigns import _won_revenue
    from sales.models import SalesInvoice
    from sales.quotation_conversions import QuotationConversionService

    company = tenant_a.company
    cust = make_customer(company)
    opp = _won_opportunity(tenant_a, cust)
    quote = _make_quote(tenant_a, cust, make_product(company))
    Quotation.objects.filter(pk=quote["id"]).update(opportunity=opp)
    r = tenant_a.client.post(f"/api/v1/sales/quotations/{quote['id']}/convert/", {}, format="json")
    assert r.status_code == 200, r.data
    _complete(SalesInvoice, r.data["id"])
    assert _won_revenue(opp)[0] == Decimal("1000.00")
    QuotationConversionService.reopen(Quotation.objects.get(pk=quote["id"]), tenant_a.owner, "undo")
    assert _won_revenue(opp)[1] == "no_completed_invoice"


# ---- Phase 13: PDF status/terms and report links ---------------------------

def _pdf_text(content: bytes) -> str:
    from io import BytesIO

    from pypdf import PdfReader

    return "\n".join((page.extract_text() or "") for page in PdfReader(BytesIO(content)).pages)


def test_cancelled_quotation_pdf_shows_watermark_reason_and_terms(tenant_a):
    cust = make_customer(tenant_a.company)
    quote = _make_quote(tenant_a, cust, make_product(tenant_a.company), terms_text="Payment within 15 days")
    tenant_a.client.post(f"/api/v1/sales/quotations/{quote['id']}/cancel/", {"reason": "Lost the deal"}, format="json")
    pdf = tenant_a.client.get(f"/api/v1/sales/quotations/{quote['id']}/pdf/")
    assert pdf.status_code == 200
    text = _pdf_text(b"".join(pdf.streaming_content))
    assert "CANCELLED" in text
    assert "Lost the deal" in text
    assert "Payment within 15 days" in text


def test_open_quotation_pdf_has_no_watermark(tenant_a):
    cust = make_customer(tenant_a.company)
    quote = _make_quote(tenant_a, cust, make_product(tenant_a.company))
    pdf = tenant_a.client.get(f"/api/v1/sales/quotations/{quote['id']}/pdf/")
    text = _pdf_text(b"".join(pdf.streaming_content))
    assert "CANCELLED" not in text and "EXPIRED" not in text


def test_day_book_links_to_the_quotation_itself(tenant_a):
    from reporting.transactions import sales_side_transactions

    cust = make_customer(tenant_a.company)
    quote = _make_quote(tenant_a, cust, make_product(tenant_a.company))
    rows = [r for r in sales_side_transactions(tenant_a.company, txn_types=["QUOTATION"]) if r["txn_type"] == "QUOTATION"]
    assert rows and rows[0]["source_path"] == f"/sales/quotations/{quote['id']}"
