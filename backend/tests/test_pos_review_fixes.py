"""Review fixes for the counter: collect replay, catalogue scope, salesperson, cash refund shift."""

from decimal import Decimal

import pytest
from django.utils import timezone

from masters.models import Product
from payments.models import CustomerReceipt
from sales.models import SalesInvoice
from tests.conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db


def _checkout(tenant, customer, product, payment, **extra):
    body = {
        "invoice": {
            "customer": customer.id,
            "invoice_type": "NON_GST",
            "invoice_date": "2026-10-07",
            "items": [{
                "product": product.id,
                "quantity": "1",
                "unit_price": "100.00",
                "gst_rate": "0",
            }],
        },
        "payment": payment,
    }
    body.update(extra)
    return tenant.client.post("/api/v1/sales/invoices/pos-checkout/", body, format="json")


def test_collect_replay_with_the_same_key_takes_the_money_once(tenant_a):
    product = make_product(tenant_a.company, sku="RV-COLLECT", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "3")
    customer = make_customer(tenant_a.company, name="Udhaar")
    sale = _checkout(tenant_a, customer, product, {"mode": "CREDIT"})
    assert sale.status_code == 201, sale.data
    body = {"invoice": sale.data["invoice"]["id"], "mode": "CASH", "amount": "40.00"}
    first = tenant_a.client.post("/api/v1/sales/pos/collect/", body, format="json", HTTP_IDEMPOTENCY_KEY="collect-1")
    again = tenant_a.client.post("/api/v1/sales/pos/collect/", body, format="json", HTTP_IDEMPOTENCY_KEY="collect-1")
    assert first.status_code == 201, first.data
    assert again.status_code == 201, again.data
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 1


def test_catalogue_leaves_out_inactive_products_and_lists_them_as_removed(tenant_a):
    live = make_product(tenant_a.company, sku="CAT-LIVE", selling_price="10")
    gone = make_product(tenant_a.company, sku="CAT-OFF", selling_price="10")
    full = tenant_a.client.get("/api/v1/products/pos-catalog/")
    assert {row["sku"] for row in full.data["results"]} >= {"CAT-LIVE", "CAT-OFF"}
    since = timezone.now()
    Product.objects.filter(pk=gone.pk).update(status=Product.Status.INACTIVE, updated_at=timezone.now())
    full = tenant_a.client.get("/api/v1/products/pos-catalog/")
    assert "CAT-OFF" not in {row["sku"] for row in full.data["results"]}
    delta = tenant_a.client.get("/api/v1/products/pos-catalog/", {"updated_after": since.isoformat()})
    assert gone.id in delta.data["deleted_ids"]
    assert live.id not in delta.data["deleted_ids"]


def test_salesperson_from_another_company_is_refused(tenant_a, tenant_b):
    product = make_product(tenant_a.company, sku="RV-SALES", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company)
    refused = _checkout(
        tenant_a, customer, product, {"mode": "CASH", "amount": "100.00"},
        salesperson=tenant_b.owner.id,
    )
    assert refused.status_code == 400, refused.data
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == 0
    refused = _checkout(
        tenant_a, customer, product, {"mode": "CASH", "amount": "100.00"},
        salesperson="not-a-number",
    )
    assert refused.status_code == 400, refused.data


def test_cash_refund_needs_an_open_till_when_the_company_requires_one(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    product = make_product(tenant_a.company, sku="RV-REFUND-SHIFT", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "3")
    customer = make_customer(tenant_a.company, name="Shift refund")
    sale = _checkout(tenant_a, customer, product, {"mode": "CASH", "amount": "100.00"})
    assert sale.status_code == 201, sale.data
    flags = dict(tenant_a.company.feature_flags or {})
    flags["pos_require_open_shift"] = True
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    refused = tenant_a.client.post(
        "/api/v1/sales/pos/return/",
        {"invoice": sale.data["invoice"]["id"], "refund_mode": "CASH"},
        format="json",
    )
    assert refused.status_code == 400, refused.data
    assert "pos_shift_required" in str(refused.data)
    # Nothing was left half-done: the bill can still be returned once a till is open.
    from sales.models import PosCounterRefund, SalesReturn

    assert PosCounterRefund.objects.filter(company=tenant_a.company).count() == 0
    assert SalesReturn.objects.filter(company=tenant_a.company).count() == 0


def test_counter_event_refuses_a_till_from_another_company(tenant_a, tenant_b):
    from accounting.models import CashShiftRegister

    other = CashShiftRegister.objects.create(
        company=tenant_b.company,
        cashier=tenant_b.owner,
        business_date=timezone.localdate(),
        opening_float=Decimal("0"),
    )
    refused = tenant_a.client.post(
        "/api/v1/sales/pos/events/",
        {"kind": "drawer_open", "shift_id": other.id},
        format="json",
    )
    assert refused.status_code == 400, refused.data


def test_a_refund_key_reused_on_another_bill_is_refused_not_replayed(tenant_a):
    first_product = make_product(tenant_a.company, sku="RV-KEY-1", gst_rate="0", selling_price="100")
    second_product = make_product(tenant_a.company, sku="RV-KEY-2", gst_rate="0", selling_price="100")
    add_stock(tenant_a, first_product, "3")
    add_stock(tenant_a, second_product, "3")
    one = make_customer(tenant_a.company, name="Key one")
    two = make_customer(tenant_a.company, name="Key two")
    sale_one = _checkout(tenant_a, one, first_product, {"mode": "CASH", "amount": "100.00"})
    sale_two = _checkout(tenant_a, two, second_product, {"mode": "CASH", "amount": "100.00"})
    assert sale_one.status_code == 201 and sale_two.status_code == 201
    from sales.models import PosCounterRefund, SalesReturn

    body = {"refund_mode": "CASH"}
    first = tenant_a.client.post(
        "/api/v1/sales/pos/return/", {**body, "invoice": sale_one.data["invoice"]["id"]},
        format="json", HTTP_IDEMPOTENCY_KEY="shared-key",
    )
    assert first.status_code == 201, first.data
    # The same key and bill is a replay of the same return.
    replay = tenant_a.client.post(
        "/api/v1/sales/pos/return/", {**body, "invoice": sale_one.data["invoice"]["id"]},
        format="json", HTTP_IDEMPOTENCY_KEY="shared-key",
    )
    assert replay.status_code == 200 and replay.data["replayed"] is True
    assert replay.data["id"] == first.data["id"]
    # The same key for another bill is neither a replay nor a second return.
    other = tenant_a.client.post(
        "/api/v1/sales/pos/return/", {**body, "invoice": sale_two.data["invoice"]["id"]},
        format="json", HTTP_IDEMPOTENCY_KEY="shared-key",
    )
    assert other.status_code == 400, other.data
    assert "idempotency_key_reused" in str(other.data)
    assert PosCounterRefund.objects.filter(company=tenant_a.company).count() == 1
    assert SalesReturn.objects.filter(company=tenant_a.company).count() == 1


def test_an_unstamped_cash_refund_counts_only_on_the_sole_open_till(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    product = make_product(tenant_a.company, sku="RV-UNSTAMPED", gst_rate="0", selling_price="100")
    add_stock(tenant_a, product, "3")
    customer = make_customer(tenant_a.company, name="No till then")
    sale = _checkout(tenant_a, customer, product, {"mode": "CASH", "amount": "100.00"})
    assert sale.status_code == 201, sale.data
    refunded = tenant_a.client.post(
        "/api/v1/sales/pos/return/",
        {"invoice": sale.data["invoice"]["id"], "refund_mode": "CASH"},
        format="json",
    )
    assert refunded.status_code == 201, refunded.data
    today = timezone.localdate().isoformat()
    ids = {}
    for terminal in ("drawer-a", "drawer-b"):
        opened = tenant_a.client.post(
            "/api/v1/accounting/cash-shifts/",
            {"opening_float": "100.00", "business_date": today, "terminal_id": terminal},
            format="json",
        )
        assert opened.status_code == 201, opened.data
        ids[terminal] = opened.data["id"]
    # Two drawers are open, so it is unclear whose refund it was. Neither counts it.
    for terminal in ids:
        body = tenant_a.client.get(f"/api/v1/accounting/cash-shifts/today/?terminal_id={terminal}")
        assert Decimal(str(body.data["shift"]["expected_cash"])) == Decimal("100.00")
    closed = tenant_a.client.post(
        f"/api/v1/accounting/cash-shifts/{ids['drawer-a']}/close/",
        {"denominations": {"100": 1}},
        format="json",
    )
    assert closed.status_code == 200, closed.data
    # One drawer left: the refund must have come out of it.
    left = tenant_a.client.get("/api/v1/accounting/cash-shifts/today/?terminal_id=drawer-b")
    assert Decimal(str(left.data["shift"]["expected_cash"])) == Decimal("0.00")


def test_walk_in_get_or_create_returns_the_same_party(tenant_a):
    first = tenant_a.client.post("/api/v1/customers/pos-walk-in/", {}, format="json")
    second = tenant_a.client.post("/api/v1/customers/pos-walk-in/", {"name": "Another name"}, format="json")
    assert first.status_code == 201, first.data
    assert second.status_code == 200, second.data
    assert first.data["id"] == second.data["id"]
    assert first.data["is_pos_walk_in"] is True


def test_the_walk_in_flag_cannot_move_to_a_party_with_a_gstin(tenant_a):
    walk_in = make_customer(tenant_a.company, name="Counter", is_pos_walk_in=True)
    b2b = make_customer(tenant_a.company, name="B2B Traders", gstin="29ABCDE1234F1Z5")
    refused = tenant_a.client.post("/api/v1/customers/set-pos-walk-in/", {"customer": b2b.id}, format="json")
    assert refused.status_code == 400, refused.data
    assert "pos_walk_in_target" in str(refused.data)
    walk_in.refresh_from_db()
    assert walk_in.is_pos_walk_in is True
    plain = make_customer(tenant_a.company, name="Plain buyer")
    moved = tenant_a.client.post("/api/v1/customers/set-pos-walk-in/", {"customer": plain.id}, format="json")
    assert moved.status_code == 200, moved.data
    walk_in.refresh_from_db()
    plain.refresh_from_db()
    assert walk_in.is_pos_walk_in is False and plain.is_pos_walk_in is True


def test_price_floor_compares_the_inclusive_price_the_cashier_typed(tenant_a):
    flags = dict(tenant_a.company.feature_flags or {})
    flags["pos_max_price_discount_percent"] = "10"
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    product = make_product(tenant_a.company, sku="RV-INCL", gst_rate="18", selling_price="118")
    add_stock(tenant_a, product, "3")
    customer = make_customer(tenant_a.company, name="Inclusive buyer")
    resp = tenant_a.client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {
            "invoice": {
                "customer": customer.id,
                "invoice_type": "RETAIL",
                "price_mode": "INCLUSIVE",
                "invoice_date": "2026-10-07",
                "items": [{
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "100.00",
                    "unit_price_inclusive": "118.00",
                    "gst_rate": "18",
                }],
            },
            "payment": {"mode": "CASH", "amount": "118.00"},
        },
        format="json",
    )
    assert "pos_price_floor" not in str(resp.data), resp.data
