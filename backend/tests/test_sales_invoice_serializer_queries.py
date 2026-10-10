"""The invoice response computes its outstanding once, and the numbers it reports are unchanged.

Profiled on 2026-10-02: `POST .../complete/` ran 84 queries (58 distinct). Three serializer fields
(balance, received, payment_state) each recomputed sales_invoice_outstanding(), four aggregate
queries apiece. They now share one computation per to_representation() call.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from ledgers.services import LedgerService
from payments.services import PaymentService
from sales.models import SalesInvoice
from sales.serializers import SalesInvoiceSerializer
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db

_CN_SUM = re.compile(r'SUM\("sales_salescreditnote"\."grand_total"\)')


def _invoice(t, amount="1000", gst="0"):
    c = make_customer(t.company)
    p = make_product(t.company, gst_rate=gst, sku=f"SQ-{SalesInvoice.objects.count()}")
    add_stock(t, p, "50")
    inv = create_draft_invoice(
        t, c, [{"product": p.id, "quantity": "1", "unit_price": amount, "gst_rate": gst}],
        invoice_type="GST" if gst != "0" else "NON_GST",
    )
    assert t.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    return SalesInvoice.objects.get(pk=inv["id"]), c


def _count(ctx, pattern):
    return sum(1 for q in ctx.captured_queries if pattern.search(q["sql"]))


def test_outstanding_is_computed_once_per_representation(tenant_a):
    inv, _ = _invoice(tenant_a)
    ser = SalesInvoiceSerializer(inv, context={"request": None})
    with CaptureQueriesContext(connection) as ctx:
        data = ser.data
    assert _count(ctx, _CN_SUM) == 1, "credit-note aggregate must run once, not once per field"
    assert data["balance"] == "1000.00" or Decimal(str(data["balance"])) == Decimal("1000")


def test_the_complete_response_no_longer_triples_the_outstanding_queries(tenant_a):
    c = make_customer(tenant_a.company)
    p = make_product(tenant_a.company, gst_rate="0", sku="SQ-C")
    add_stock(tenant_a, p, "5")
    inv = create_draft_invoice(tenant_a, c, [{"product": p.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}], invoice_type="NON_GST")
    from core.seed_guard import seed_load_scope

    # Test settings run Celery eagerly, which would render the PDF (and its own outstanding queries)
    # inside the request. Production queues it, so measure the response path without it.
    with seed_load_scope(), CaptureQueriesContext(connection) as ctx:
        resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 200
    assert _count(ctx, _CN_SUM) <= 1, f"expected one credit-note aggregate, saw {_count(ctx, _CN_SUM)}"


def test_balance_received_and_payment_state_stay_consistent_when_unpaid(tenant_a):
    inv, _ = _invoice(tenant_a, "1000")
    d = SalesInvoiceSerializer(inv, context={"request": None}).data
    assert Decimal(str(d["balance"])) == Decimal("1000")
    assert Decimal(str(d["received"])) == Decimal("0")
    assert d["payment_state"] == "UNPAID"


def test_balance_received_and_payment_state_stay_consistent_when_part_paid(tenant_a):
    inv, cust = _invoice(tenant_a, "1000")
    r = PaymentService.create_receipt(company=tenant_a.company, customer=cust, amount=Decimal("400"), mode="CASH", user=tenant_a.owner)
    PaymentService.allocate_receipt(receipt=r, sales_invoice=inv, amount=Decimal("400"), user=tenant_a.owner)
    d = SalesInvoiceSerializer(SalesInvoice.objects.get(pk=inv.pk), context={"request": None}).data
    assert Decimal(str(d["balance"])) == Decimal("600")
    assert Decimal(str(d["received"])) == Decimal("400")
    assert d["payment_state"] == "UNPAID"            # money still owed


def test_fully_paid_reads_paid(tenant_a):
    inv, cust = _invoice(tenant_a, "1000")
    r = PaymentService.create_receipt(company=tenant_a.company, customer=cust, amount=Decimal("1000"), mode="CASH", user=tenant_a.owner)
    PaymentService.allocate_receipt(receipt=r, sales_invoice=inv, amount=Decimal("1000"), user=tenant_a.owner)
    d = SalesInvoiceSerializer(SalesInvoice.objects.get(pk=inv.pk), context={"request": None}).data
    assert Decimal(str(d["balance"])) == 0 and d["payment_state"] == "PAID"


def test_the_memo_never_serves_a_stale_figure_across_two_representations(tenant_a):
    """Same serializer instance, same invoice, a payment lands in between: the second read must see it."""
    inv, cust = _invoice(tenant_a, "1000")
    ser = SalesInvoiceSerializer(context={"request": None})
    first = ser.to_representation(inv)
    r = PaymentService.create_receipt(company=tenant_a.company, customer=cust, amount=Decimal("250"), mode="CASH", user=tenant_a.owner)
    PaymentService.allocate_receipt(receipt=r, sales_invoice=inv, amount=Decimal("250"), user=tenant_a.owner)
    second = ser.to_representation(SalesInvoice.objects.get(pk=inv.pk))
    assert Decimal(str(first["balance"])) == Decimal("1000")
    assert Decimal(str(second["balance"])) == Decimal("750")


def test_a_credit_note_is_reflected(tenant_a):
    inv, cust = _invoice(tenant_a, "1000")
    prod = inv.items.first().product
    cn = tenant_a.client.post("/api/v1/sales/credit-notes/", {
        "customer": cust.id, "sales_invoice": inv.id, "reason": "CORRECTION_OF_INVOICE",
        "items": [{"product": prod.id, "quantity": "1", "unit_price": "300", "gst_rate": "0"}],
    }, format="json")
    assert cn.status_code == 201, cn.data
    assert tenant_a.client.post(f"/api/v1/sales/credit-notes/{cn.data['id']}/complete/", {"confirm_price_override": True}, format="json").status_code == 200
    d = SalesInvoiceSerializer(SalesInvoice.objects.get(pk=inv.pk), context={"request": None}).data
    assert Decimal(str(d["balance"])) == Decimal("700")


def test_draft_invoices_report_the_receivable_not_an_aggregate(tenant_a):
    c = make_customer(tenant_a.company)
    p = make_product(tenant_a.company, gst_rate="0", sku="SQ-D")
    inv = create_draft_invoice(tenant_a, c, [{"product": p.id, "quantity": "2", "unit_price": "50", "gst_rate": "0"}], invoice_type="NON_GST")
    draft = SalesInvoice.objects.get(pk=inv["id"])
    with CaptureQueriesContext(connection) as ctx:
        d = SalesInvoiceSerializer(draft, context={"request": None}).data
    assert Decimal(str(d["balance"])) == Decimal("100") and d["payment_state"] == "UNPAID"
    assert _count(ctx, _CN_SUM) == 0


def test_list_endpoint_values_match_detail_values(tenant_a):
    inv, _ = _invoice(tenant_a, "1000")
    detail = tenant_a.client.get(f"/api/v1/sales/invoices/{inv.id}/").data
    listing = tenant_a.client.get("/api/v1/sales/invoices/").data
    rows = listing.get("results", listing)
    row = next(r for r in rows if r["id"] == inv.id)
    for field in ("balance", "received", "payment_state"):
        assert str(row[field]) == str(detail[field]) or Decimal(str(row[field])) == Decimal(str(detail[field])), field


def test_invoice_payment_state_still_works_without_a_precomputed_value(tenant_a):
    from payments.holding import invoice_payment_state

    inv, _ = _invoice(tenant_a, "500")
    assert invoice_payment_state(inv) == "UNPAID"
    assert invoice_payment_state(inv, outstanding=Decimal("0")) == "PAID"
    assert LedgerService.sales_invoice_outstanding(inv) == Decimal("500")


def test_invoice_payment_state_uses_list_gateway_flags_without_querying(tenant_a):
    """List rows pass the gateway flags from annotations; a row must not query per field."""
    from payments.holding import invoice_payment_state

    inv, _ = _invoice(tenant_a, "500")
    with CaptureQueriesContext(connection) as ctx:
        assert invoice_payment_state(inv, outstanding=Decimal("500"), holding=False, captured=False) == "UNPAID"
        assert invoice_payment_state(inv, outstanding=Decimal("500"), holding=True, captured=False) == "PAID_PENDING_BOOKS"
        assert invoice_payment_state(inv, outstanding=Decimal("500"), holding=False, captured=True) == "PAID_PENDING_BOOKS"
    assert len(ctx.captured_queries) == 0


def test_the_list_payment_state_does_not_query_per_row(tenant_a):
    for amount in ("100", "200", "300"):
        _invoice(tenant_a, amount)
    with CaptureQueriesContext(connection) as few:
        assert tenant_a.client.get("/api/v1/sales/invoices/", {"page_size": 3}).status_code == 200
    for amount in ("400", "500", "600"):
        _invoice(tenant_a, amount)
    with CaptureQueriesContext(connection) as more:
        assert tenant_a.client.get("/api/v1/sales/invoices/", {"page_size": 6}).status_code == 200
    assert len(more.captured_queries) <= len(few.captured_queries) + 2
