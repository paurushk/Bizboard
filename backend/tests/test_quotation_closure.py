"""Closure-plan regression tests (QUOTATIONS_CLOSURE_PLAN.md), grouped by work package."""
from __future__ import annotations

import itertools
from decimal import Decimal

import pytest

from sales.models import Quotation, QuotationConversion, SalesInvoice, SalesOrder
from tests.conftest import make_customer, make_product

pytestmark = pytest.mark.django_db

_n = itertools.count(1)


def _line(product, qty="10", price="100.00", gst="18", **extra):
    return {"product": product.id, "quantity": qty, "unit_price": price, "gst_rate": gst, **extra}


def _quote(tenant, *lines, customer=None, products=None, **extra):
    n = next(_n)
    cust = customer or make_customer(tenant.company, name=f"Cust {n}", phone=f"98765{n:05d}")
    if not lines:
        prod = make_product(tenant.company, sku=f"CL-{n}")
        lines = (_line(prod),)
    body = {
        "customer": cust.id,
        "quotation_date": "2026-03-01",
        "valid_until": "2099-03-15",
        "items": list(lines),
        **extra,
    }
    resp = tenant.client.post("/api/v1/sales/quotations/", body, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data


def _to_order(tenant, quote, *, qty, item=0):
    resp = tenant.client.post(
        f"/api/v1/sales/quotations/{quote['id']}/convert-to-order/",
        {"items": [{"id": quote["items"][item]["id"], "quantity": qty}]},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    return SalesOrder.objects.get(pk=resp.data["id"])


def _patch(tenant, qid, body):
    return tenant.client.patch(f"/api/v1/sales/quotations/{qid}/", body, format="json")


# ---------------------------------------------------------------- WP1 ------

def test_wp1_even_split_shares_header_and_sums_to_quote(tenant_a):
    q = _quote(tenant_a, additional_charges="100", invoice_discount="50")
    first = _to_order(tenant_a, q, qty=5)
    second = _to_order(tenant_a, q, qty=5)
    assert (first.additional_charges, first.invoice_discount) == (Decimal("50.00"), Decimal("25.00"))
    assert first.additional_charges + second.additional_charges == Decimal("100.00")
    assert first.invoice_discount + second.invoice_discount == Decimal("50.00")


def test_wp1_odd_split_adds_up_to_the_paisa(tenant_a):
    q = _quote(tenant_a, additional_charges="100.01", invoice_discount="33.33")
    orders = [_to_order(tenant_a, q, qty=qty) for qty in (3, 3, 4)]
    assert sum(o.additional_charges for o in orders) == Decimal("100.01")
    assert sum(o.invoice_discount for o in orders) == Decimal("33.33")


def test_wp1_release_and_reconvert_picks_the_share_up_again(tenant_a):
    from sales.quotation_conversions import QuotationConversionService

    q = _quote(tenant_a, additional_charges="100")
    first = _to_order(tenant_a, q, qty=4)
    second = _to_order(tenant_a, q, qty=3)
    quote = Quotation.objects.get(pk=q["id"])
    QuotationConversionService.release_for_order(
        first, tenant_a.owner, QuotationConversion.ReleaseReason.DRAFT_DELETED
    )
    third = _to_order(tenant_a, q, qty=4)
    assert second.additional_charges + third.additional_charges == Decimal("70.00")
    assert quote.items.get().quantity == Decimal("10")


def test_wp1_full_conversion_copies_exact_amounts(tenant_a):
    q = _quote(tenant_a, additional_charges="100", invoice_discount="50")
    resp = tenant_a.client.post(f"/api/v1/sales/quotations/{q['id']}/convert/", {}, format="json")
    assert resp.status_code == 200, resp.data
    invoice = SalesInvoice.objects.get(pk=resp.data["id"])
    assert (invoice.additional_charges, invoice.invoice_discount) == (Decimal("100.00"), Decimal("50.00"))


def test_wp1_zero_value_line_carries_no_share_and_valuable_line_does(tenant_a):
    free = make_product(tenant_a.company, sku="FREE-1")
    paid = make_product(tenant_a.company, sku="PAID-1")
    q = _quote(tenant_a, _line(free, "5", "0.00", "0"), _line(paid, "10", "100.00"), additional_charges="100")
    only_free = _to_order(tenant_a, q, qty=5, item=0)
    assert only_free.additional_charges == Decimal("0.00")
    only_paid = _to_order(tenant_a, q, qty=10, item=1)
    assert only_paid.additional_charges == Decimal("100.00")


def test_wp1_all_zero_quote_uses_quantity_weights(tenant_a):
    free = make_product(tenant_a.company, sku="FREE-2")
    q = _quote(tenant_a, _line(free, "10", "0.00", "0"), additional_charges="40")
    first = _to_order(tenant_a, q, qty=5)
    assert first.additional_charges == Decimal("20.00")


def test_wp1_weight_of_a_row_is_its_share_of_the_line_value(tenant_a):
    from sales.quotation_conversions import _converted_weight

    q = _quote(tenant_a, additional_charges="10")
    _to_order(tenant_a, q, qty=3)
    quote = Quotation.objects.get(pk=q["id"])
    assert _converted_weight(quote, list(quote.items.all()), by_quantity=False) == Decimal("300")


def test_wp1_discount_never_exceeds_converted_value(tenant_a):
    from sales.quotation_conversions import header_shares

    q = _quote(tenant_a, invoice_discount="500", invoice_discount_mode="BEFORE_TAX")
    quote = Quotation.objects.get(pk=q["id"])
    plan = [(quote.items.get(), Decimal("1"))]
    charges, discount = header_shares(quote, plan)
    assert discount <= Decimal("100.00")
    assert charges == Decimal("0.00")


def test_wp1_gst_on_split_charges_stays_within_a_paisa_per_document(tenant_a):
    q = _quote(tenant_a, additional_charges="100", charges_hsn="9965", charges_gst_rate="28")
    orders = [_to_order(tenant_a, q, qty=qty) for qty in (3, 3, 4)]
    assert sum(o.additional_charges for o in orders) == Decimal("100.00")
    quote_tax = Quotation.objects.get(pk=q["id"])
    quote_gst = quote_tax.cgst_total + quote_tax.sgst_total + quote_tax.igst_total
    doc_gst = sum(o.cgst_total + o.sgst_total + o.igst_total for o in orders)
    assert abs(doc_gst - quote_gst) <= Decimal("0.05")


# ---------------------------------------------------------------- helpers --

def _assert_ledger(quote_id):
    """The cache on every line equals the sum of its unreleased ledger rows."""
    from django.db.models import Sum

    quote = Quotation.objects.get(pk=quote_id)
    for item in quote.items.all():
        live = (
            QuotationConversion.objects.filter(quotation_item=item, released_at__isnull=True)
            .aggregate(total=Sum("quantity"))["total"]
            or Decimal("0")
        )
        assert item.converted_quantity == live, (item.id, item.converted_quantity, live)
    remaining = sum((i.quantity - i.converted_quantity for i in quote.items.all()), Decimal("0"))
    if quote.short_closed_at is None and quote.status in (Quotation.Status.CONVERTED, *Quotation.OPEN_STATUSES):
        assert (quote.status == Quotation.Status.CONVERTED) == (remaining <= 0)


# ---------------------------------------------------------------- WP2 ------

def test_wp2_wipe_works_with_conversions_and_revisions(tenant_a):
    from accounts.tenant_backup import wipe_logical_tenant_rows
    from sales.models import QuotationRevision

    q = _quote(tenant_a)
    _to_order(tenant_a, q, qty=4)
    quote = Quotation.objects.get(pk=q["id"])
    QuotationRevision.objects.create(
        company=tenant_a.company, quotation=quote, revision=0, snapshot={"n": 1}, created_by=tenant_a.owner
    )
    wipe_logical_tenant_rows(tenant_a.company)
    assert not Quotation.objects.filter(company=tenant_a.company).exists()
    assert not QuotationConversion.objects.filter(company=tenant_a.company).exists()
    assert not QuotationRevision.objects.filter(company=tenant_a.company).exists()


def _restore(tenant, payload):
    from accounts.tenant_backup import restore_destroy_in_place

    restore_destroy_in_place(
        company=tenant.company, payload=payload, owner=tenant.owner, confirm_destroy_unbacked=True
    )


def test_wp2_restore_round_trip_keeps_ledger_revisions_and_links(tenant_a):
    from accounts.tenant_backup import build_export_payload
    from sales.models import QuotationRevision

    q = _quote(tenant_a, additional_charges="20")
    _to_order(tenant_a, q, qty=4)
    _to_order(tenant_a, q, qty=3)
    quote = Quotation.objects.get(pk=q["id"])
    QuotationRevision.objects.create(
        company=tenant_a.company, quotation=quote, revision=0, snapshot={"n": 1}, created_by=tenant_a.owner
    )
    live_before = QuotationConversion.objects.filter(quotation=quote, released_at__isnull=True).count()
    payload = build_export_payload(tenant_a.company)
    assert len(payload["quotation_conversions"]) == 2 and len(payload["quotation_revisions"]) == 1

    _restore(tenant_a, payload)

    restored = Quotation.objects.get(company=tenant_a.company)
    rows = list(QuotationConversion.objects.filter(quotation=restored))
    assert len(rows) == live_before
    for row in rows:
        assert row.sales_order is not None and row.sales_order.company_id == tenant_a.company.id
        assert row.quotation_item.quotation_id == restored.id
        assert row.sales_order_item is not None
        assert row.sales_order_item.sales_order_id == row.sales_order_id
    assert restored.items.get().converted_quantity == Decimal("7")
    assert QuotationRevision.objects.filter(quotation=restored).count() == 1
    _assert_ledger(restored.id)


def test_wp2_restore_of_an_old_backup_backfills_the_ledger(tenant_a):
    from accounts.tenant_backup import build_export_payload

    q = _quote(tenant_a)
    _to_order(tenant_a, q, qty=4)
    payload = build_export_payload(tenant_a.company)
    payload.pop("quotation_conversions")
    payload.pop("quotation_revisions")

    _restore(tenant_a, payload)

    restored = Quotation.objects.get(company=tenant_a.company)
    rows = list(QuotationConversion.objects.filter(quotation=restored))
    assert len(rows) == 1 and rows[0].backfilled and rows[0].quantity == Decimal("4")
    _assert_ledger(restored.id)
    # The restored quote cannot be converted beyond what is left.
    resp = tenant_a.client.post(
        f"/api/v1/sales/quotations/{restored.id}/convert-to-order/",
        {"items": [{"id": restored.items.get().id, "quantity": 7}]},
        format="json",
    )
    assert resp.status_code == 400


def test_wp2_restore_stops_when_a_quote_disagrees_with_its_ledger(tenant_a):
    from accounts.tenant_backup import build_export_payload
    from core.exceptions import BusinessRuleError

    q = _quote(tenant_a)
    _to_order(tenant_a, q, qty=4)
    payload = build_export_payload(tenant_a.company)
    payload["quotation_items"][0]["converted_quantity"] = "9.000"
    with pytest.raises(BusinessRuleError):
        _restore(tenant_a, payload)


def test_wp2_backfill_can_be_limited_to_one_company(tenant_a, tenant_b):
    from sales.models import QuotationItem
    from sales.quotation_conversions import backfill_conversions

    quotes = []
    for tenant in (tenant_a, tenant_b):
        q = _quote(tenant)
        _to_order(tenant, q, qty=2)
        QuotationConversion.objects.filter(quotation_id=q["id"]).delete()
        quotes.append(q)
    backfill_conversions(QuotationItem, QuotationConversion, company=tenant_a.company)
    assert QuotationConversion.objects.filter(quotation_id=quotes[0]["id"]).count() == 1
    assert QuotationConversion.objects.filter(quotation_id=quotes[1]["id"]).count() == 0


# ---------------------------------------------------------------- WP3 ------

def test_wp3_create_response_has_real_totals(tenant_a):
    q = _quote(tenant_a)
    fetched = tenant_a.client.get(f"/api/v1/sales/quotations/{q['id']}/").data
    assert Decimal(q["grand_total"]) > 0
    assert q["grand_total"] == fetched["grand_total"]
    assert q["taxable_total"] == fetched["taxable_total"]
    assert q["number"]


# ---------------------------------------------------------------- WP4 ------

def test_wp4_release_is_on_by_default(tenant_a):
    q = _quote(tenant_a)
    resp = tenant_a.client.post(f"/api/v1/sales/quotations/{q['id']}/convert/", {}, format="json")
    assert resp.status_code == 200, resp.data
    assert Quotation.objects.get(pk=q["id"]).status == Quotation.Status.CONVERTED
    assert tenant_a.client.delete(f"/api/v1/sales/invoices/{resp.data['id']}/").status_code == 204
    assert Quotation.objects.get(pk=q["id"]).status == Quotation.Status.DRAFT
    _assert_ledger(q["id"])


def _flag_off(tenant):
    tenant.company.feature_flags = {**(tenant.company.feature_flags or {}), "QUOTE_CONVERSION_RELEASE": False}
    tenant.company.save(update_fields=["feature_flags"])


def test_wp4_flag_off_leaves_an_orphan_and_the_sweep_releases_it(tenant_a):
    from sales.quotation_conversions import QuotationConversionService

    _flag_off(tenant_a)
    q = _quote(tenant_a)
    resp = tenant_a.client.post(f"/api/v1/sales/quotations/{q['id']}/convert/", {}, format="json")
    tenant_a.client.delete(f"/api/v1/sales/invoices/{resp.data['id']}/")
    assert Quotation.objects.get(pk=q["id"]).status == Quotation.Status.CONVERTED
    dry = QuotationConversionService.sweep(tenant_a.company, dry_run=True)
    assert dry["released"] == 1
    assert Quotation.objects.get(pk=q["id"]).status == Quotation.Status.CONVERTED
    done = QuotationConversionService.sweep(tenant_a.company)
    assert done["released"] == 1 and done["by_reason"] == {"DRAFT_DELETED": 1}
    assert Quotation.objects.get(pk=q["id"]).status == Quotation.Status.DRAFT
    _assert_ledger(q["id"])
    assert QuotationConversionService.sweep(tenant_a.company)["released"] == 0


def test_wp4_sweep_releases_a_cancelled_order_and_leaves_unknown_rows(tenant_a):
    from sales.quotation_conversions import QuotationConversionService

    q = _quote(tenant_a)
    order = _to_order(tenant_a, q, qty=4)
    SalesOrder.objects.filter(pk=order.pk).update(status=SalesOrder.Status.CANCELLED)
    other = _quote(tenant_a)
    _to_order(tenant_a, other, qty=2)
    QuotationConversion.objects.filter(quotation_id=other["id"]).update(
        target=QuotationConversion.Target.UNKNOWN, sales_order=None
    )
    result = QuotationConversionService.sweep(tenant_a.company)
    assert result["by_reason"] == {"ORDER_CANCELLED": 1}
    assert QuotationConversion.objects.get(quotation_id=q["id"]).released_at is not None
    assert QuotationConversion.objects.get(quotation_id=other["id"]).released_at is None


def test_wp4_sweep_command_runs(tenant_a):
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    call_command("release_orphan_quotation_conversions", "--dry-run", stdout=out)
    assert "would release" in out.getvalue()


def test_wp4_invoice_from_an_order_never_releases_the_quote(tenant_a):
    q = _quote(tenant_a)
    order = _to_order(tenant_a, q, qty=4)
    invoice = SalesInvoice.objects.create(
        company=tenant_a.company, customer=order.customer, source_order=order, created_by=tenant_a.owner
    )
    assert tenant_a.client.delete(f"/api/v1/sales/invoices/{invoice.pk}/").status_code == 204
    assert QuotationConversion.objects.get(quotation_id=q["id"]).released_at is None
    _assert_ledger(q["id"])


def test_wp4_cancelling_or_deleting_the_order_releases_the_quote(tenant_a):
    from sales.notes_services import SalesNotesService

    q = _quote(tenant_a)
    cancelled = _to_order(tenant_a, q, qty=4)
    SalesNotesService.cancel_sales_order(cancelled, tenant_a.owner)
    assert QuotationConversion.objects.get(sales_order=cancelled).release_reason == "ORDER_CANCELLED"
    deleted = _to_order(tenant_a, q, qty=3)
    assert tenant_a.client.delete(f"/api/v1/sales/orders/{deleted.pk}/").status_code == 204
    row = QuotationConversion.objects.get(quotation_id=q["id"], quantity=Decimal("3"))
    assert row.release_reason == "DRAFT_DELETED" and row.released_at is not None
    _assert_ledger(q["id"])
