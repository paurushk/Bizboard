"""Double-submit and key-reuse behaviour on the money-moving endpoints (C3 / QOS-0053 follow-up).

A double click, a retried request and a reused Idempotency-Key must never create a second
record, and a key reused for a DIFFERENT request must be refused instead of being answered
with the first request's result (which would show "success" for data that was never saved).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from accounting.models import JournalEntry
from accounting.services import seed_chart_of_accounts
from core.idempotency import IdempotencyRecord, request_fingerprint
from inventory.models import StockMovement
from payments.models import CustomerReceipt, SupplierPayment
from purchases.models import PurchaseInvoice
from sales.models import SalesInvoice
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def _receipt_payload(customer, amount="500.00"):
    return {"customer": customer.id, "amount": amount, "mode": "CASH", "receipt_date": str(timezone.localdate())}


def _post(client, url, body, key):
    return client.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY=key)


# --- receipts ------------------------------------------------------------------------

def test_same_key_same_body_creates_exactly_one_receipt(tenant_a):
    c = make_customer(tenant_a.company)
    first = _post(tenant_a.client, "/api/v1/payments/receipts/", _receipt_payload(c), "rcpt-1")
    second = _post(tenant_a.client, "/api/v1/payments/receipts/", _receipt_payload(c), "rcpt-1")
    assert first.status_code == 201, first.content
    assert second.status_code == first.status_code
    assert second.data["id"] == first.data["id"]
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 1


def test_same_key_different_amount_is_refused_not_silently_replayed(tenant_a):
    c = make_customer(tenant_a.company)
    ok = _post(tenant_a.client, "/api/v1/payments/receipts/", _receipt_payload(c, "500.00"), "rcpt-2")
    assert ok.status_code == 201
    corrected = _post(tenant_a.client, "/api/v1/payments/receipts/", _receipt_payload(c, "5000.00"), "rcpt-2")
    assert corrected.status_code == 422, corrected.content
    assert b"idempotency_key_reused" in corrected.content
    rows = list(CustomerReceipt.objects.filter(company=tenant_a.company))
    assert len(rows) == 1 and rows[0].amount == Decimal("500.00"), "the corrected 5000 must NOT look saved"


def test_different_keys_with_the_same_body_are_two_receipts(tenant_a):
    """The key is the dedup contract: a client that wants one receipt must reuse its key."""
    c = make_customer(tenant_a.company)
    _post(tenant_a.client, "/api/v1/payments/receipts/", _receipt_payload(c), "rcpt-3a")
    _post(tenant_a.client, "/api/v1/payments/receipts/", _receipt_payload(c), "rcpt-3b")
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 2


def test_key_is_scoped_per_company(tenant_a, tenant_b):
    ca, cb = make_customer(tenant_a.company), make_customer(tenant_b.company)
    a = _post(tenant_a.client, "/api/v1/payments/receipts/", _receipt_payload(ca), "shared-key")
    b = _post(tenant_b.client, "/api/v1/payments/receipts/", _receipt_payload(cb, "999.00"), "shared-key")
    assert a.status_code == 201 and b.status_code == 201, (a.content, b.content)
    assert CustomerReceipt.objects.filter(company=tenant_b.company).count() == 1


def test_key_reuse_on_another_endpoint_family_does_not_collide(tenant_a):
    c, s = make_customer(tenant_a.company), make_supplier(tenant_a.company)
    r = _post(tenant_a.client, "/api/v1/payments/receipts/", _receipt_payload(c), "same-key")
    p = _post(
        tenant_a.client, "/api/v1/payments/supplier-payments/",
        {"supplier": s.id, "amount": "100.00", "mode": "CASH", "payment_date": str(timezone.localdate())}, "same-key",
    )
    assert r.status_code == 201 and p.status_code == 201, (r.content, p.content)


# --- supplier payments ---------------------------------------------------------------

def test_supplier_payment_same_key_one_row_and_changed_body_refused(tenant_a):
    s = make_supplier(tenant_a.company)
    body = {"supplier": s.id, "amount": "250.00", "mode": "CASH", "payment_date": str(timezone.localdate())}
    first = _post(tenant_a.client, "/api/v1/payments/supplier-payments/", body, "sp-1")
    again = _post(tenant_a.client, "/api/v1/payments/supplier-payments/", body, "sp-1")
    changed = _post(tenant_a.client, "/api/v1/payments/supplier-payments/", {**body, "amount": "2500.00"}, "sp-1")
    assert first.status_code == 201 and again.status_code == 201
    assert again.data["id"] == first.data["id"]
    assert changed.status_code == 422
    rows = list(SupplierPayment.objects.filter(company=tenant_a.company))
    assert len(rows) == 1 and rows[0].amount == Decimal("250.00")


# --- completing documents ------------------------------------------------------------

_SKU = iter(range(1, 1000))


def _draft_sale(t, amount="1000"):
    c = make_customer(t.company)
    p = make_product(t.company, gst_rate="0", sku=f"DS-{next(_SKU)}")
    add_stock(t, p, "10")
    inv = create_draft_invoice(
        t, c, [{"product": p.id, "quantity": "1", "unit_price": amount, "gst_rate": "0"}], invoice_type="NON_GST",
    )
    return inv["id"], p


def _sale_movements(t, product):
    return StockMovement.objects.filter(company=t.company, product=product, movement_type="SALE").count()


def test_double_click_complete_without_a_key_posts_stock_once(tenant_a):
    inv_id, product = _draft_sale(tenant_a)
    first = tenant_a.client.post(f"/api/v1/sales/invoices/{inv_id}/complete/")
    second = tenant_a.client.post(f"/api/v1/sales/invoices/{inv_id}/complete/")
    assert first.status_code == 200
    assert second.status_code >= 400, "a second Complete must be refused, not re-posted"
    assert _sale_movements(tenant_a, product) == 1
    assert SalesInvoice.objects.get(pk=inv_id).status == SalesInvoice.Status.COMPLETED


def test_double_click_complete_with_a_key_replays_and_posts_stock_once(tenant_a):
    inv_id, product = _draft_sale(tenant_a)
    url = f"/api/v1/sales/invoices/{inv_id}/complete/"
    first = tenant_a.client.post(url, HTTP_IDEMPOTENCY_KEY="complete-1")
    second = tenant_a.client.post(url, HTTP_IDEMPOTENCY_KEY="complete-1")
    assert first.status_code == 200 and second.status_code == 200
    assert _sale_movements(tenant_a, product) == 1


def test_double_click_complete_posts_the_same_journal_entries_as_a_single_click(tenant_a):
    """A sale posts a fixed set of entries (revenue + COGS). Extra clicks must add none."""
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)

    single_id, _ = _draft_sale(tenant_a)
    base = JournalEntry.objects.filter(company=tenant_a.company).count()
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{single_id}/complete/").status_code == 200
    per_sale = JournalEntry.objects.filter(company=tenant_a.company).count() - base
    assert per_sale >= 1

    multi_id, _ = _draft_sale(tenant_a)
    before = JournalEntry.objects.filter(company=tenant_a.company).count()
    url = f"/api/v1/sales/invoices/{multi_id}/complete/"
    tenant_a.client.post(url, HTTP_IDEMPOTENCY_KEY="je-1")
    tenant_a.client.post(url, HTTP_IDEMPOTENCY_KEY="je-1")
    tenant_a.client.post(url)  # and a keyless third click
    created = JournalEntry.objects.filter(company=tenant_a.company).count() - before
    assert created == per_sale, f"one click posts {per_sale} entries; three clicks posted {created}"


def test_purchase_complete_double_click_posts_stock_once(tenant_a):
    s = make_supplier(tenant_a.company)
    p = make_product(tenant_a.company, purchase_price="100", gst_rate="0")
    pur = create_draft_purchase(
        tenant_a, s, [{"product": p.id, "quantity": "3", "unit_price": "100", "gst_rate": "0"}], purchase_type="NON_GST",
    )
    url = f"/api/v1/purchases/invoices/{pur['id']}/complete/"
    first = tenant_a.client.post(url, HTTP_IDEMPOTENCY_KEY="pc-1")
    second = tenant_a.client.post(url, HTTP_IDEMPOTENCY_KEY="pc-1")
    third = tenant_a.client.post(url)
    assert first.status_code == 200 and second.status_code == 200 and third.status_code >= 400
    assert StockMovement.objects.filter(company=tenant_a.company, product=p, movement_type="PURCHASE").count() == 1
    assert PurchaseInvoice.objects.get(pk=pur["id"]).status == PurchaseInvoice.Status.COMPLETED


def test_complete_with_a_reused_key_on_a_different_invoice_is_refused(tenant_a):
    """Two different invoices, one key: the second must not be answered with the first's result."""
    a_id, _ = _draft_sale(tenant_a)
    b_id, _ = _draft_sale(tenant_a, "2000")
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{a_id}/complete/", HTTP_IDEMPOTENCY_KEY="shared").status_code == 200
    second = tenant_a.client.post(f"/api/v1/sales/invoices/{b_id}/complete/", HTTP_IDEMPOTENCY_KEY="shared")
    assert second.status_code == 422, second.content
    assert SalesInvoice.objects.get(pk=b_id).status != SalesInvoice.Status.COMPLETED, "B must not look completed"


# --- the mechanism itself -----------------------------------------------------------

def test_legacy_record_without_a_hash_is_still_replayed(tenant_a):
    """Rows written before request_hash existed must keep replaying (no surprise 422s on deploy)."""
    c = make_customer(tenant_a.company)
    first = _post(tenant_a.client, "/api/v1/payments/receipts/", _receipt_payload(c), "legacy-1")
    IdempotencyRecord.objects.filter(company=tenant_a.company, key="legacy-1").update(request_hash="")
    again = _post(tenant_a.client, "/api/v1/payments/receipts/", _receipt_payload(c, "999.00"), "legacy-1")
    assert again.status_code == 201 and again.data["id"] == first.data["id"]


def test_strict_fingerprint_can_be_switched_off(tenant_a, settings):
    settings.IDEMPOTENCY_STRICT_FINGERPRINT = False
    c = make_customer(tenant_a.company)
    first = _post(tenant_a.client, "/api/v1/payments/receipts/", _receipt_payload(c), "rollback-1")
    again = _post(tenant_a.client, "/api/v1/payments/receipts/", _receipt_payload(c, "999.00"), "rollback-1")
    assert again.status_code == 201 and again.data["id"] == first.data["id"]


def test_fingerprint_ignores_json_key_order_but_not_values():
    from rest_framework.test import APIRequestFactory
    from rest_framework.request import Request
    from rest_framework.parsers import JSONParser

    def fp(payload, path="/api/v1/payments/receipts/"):
        req = APIRequestFactory().post(path, payload, format="json")
        return request_fingerprint(Request(req, parsers=[JSONParser()]))

    assert fp({"a": 1, "b": 2}) == fp({"b": 2, "a": 1})
    assert fp({"a": 1, "b": 2}) != fp({"a": 1, "b": 3})
    assert fp({"a": 1}) != fp({"a": 1}, path="/api/v1/payments/supplier-payments/")
