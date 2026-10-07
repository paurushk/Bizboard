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
