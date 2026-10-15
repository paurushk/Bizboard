"""Purchase review F-01 / WP-1: pay-at-entry is one transaction, and a payment problem never un-completes a bill."""

from decimal import Decimal

import pytest

from core.exceptions import BusinessRuleError
from payments.models import PaymentAllocation, SupplierPayment
from payments.services import PaymentService
from purchases.models import PurchaseInvoice
from tests.conftest import create_draft_purchase, make_product, make_supplier

pytestmark = pytest.mark.django_db

BASE = "/api/v1/purchases/invoices"


def _draft(tenant, price="100"):
    supplier = make_supplier(tenant.company)
    product = make_product(tenant.company, sku=f"PN-{price}")
    draft = create_draft_purchase(
        tenant,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": price, "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    return supplier, draft


def _complete(tenant, draft, pay_now=None, **headers):
    body = {"pay_now": pay_now} if pay_now is not None else {}
    return tenant.client.post(f"{BASE}/{draft['id']}/complete/", body, format="json", **headers)


def test_complete_with_pay_now_creates_payment_and_allocation_together(tenant_a):
    _, draft = _draft(tenant_a)
    resp = _complete(tenant_a, draft, {"amount": "40.00", "mode": "CASH"})
    assert resp.status_code == 200, resp.data
    assert resp.data["payment_error"] is None
    assert resp.data["payment"]["amount"] == "40.00"
    assert Decimal(str(resp.data["balance"])) == Decimal("60.00")
    pay = SupplierPayment.objects.get(pk=resp.data["payment"]["id"])
    alloc = PaymentAllocation.objects.get(supplier_payment=pay, reversed_at__isnull=True)
    assert alloc.purchase_invoice_id == draft["id"] and alloc.amount == Decimal("40.00")


def test_complete_without_pay_now_has_no_payment_keys(tenant_a):
    _, draft = _draft(tenant_a)
    resp = _complete(tenant_a, draft)
    assert resp.status_code == 200
    assert "payment" not in resp.data and "payment_error" not in resp.data
    assert not SupplierPayment.objects.exists()


def test_overpay_keeps_bill_completed_and_reports_error_without_orphan_payment(tenant_a):
    _, draft = _draft(tenant_a)
    resp = _complete(tenant_a, draft, {"amount": "500.00", "mode": "CASH"})
    assert resp.status_code == 200, resp.data
    assert resp.data["payment"] is None
    assert resp.data["payment_error"]["message"]
    assert PurchaseInvoice.objects.get(pk=draft["id"]).status == "COMPLETED"
    assert not SupplierPayment.objects.exists()
    assert not PaymentAllocation.objects.exists()


def test_invalid_cheque_details_are_reported_not_raised(tenant_a):
    _, draft = _draft(tenant_a)
    resp = _complete(tenant_a, draft, {"amount": "10.00", "mode": "CHEQUE"})
    assert resp.status_code == 200, resp.data
    assert resp.data["payment"] is None and resp.data["payment_error"]
    assert PurchaseInvoice.objects.get(pk=draft["id"]).status == "COMPLETED"
    assert not SupplierPayment.objects.exists()


def test_allocation_failure_rolls_back_the_payment(tenant_a, monkeypatch):
    _, draft = _draft(tenant_a)

    def boom(**kwargs):
        raise BusinessRuleError("allocation refused")

    monkeypatch.setattr(PaymentService, "allocate_supplier_payment", staticmethod(boom))
    resp = _complete(tenant_a, draft, {"amount": "40.00", "mode": "CASH"})
    assert resp.status_code == 200, resp.data
    assert resp.data["payment"] is None
    assert "allocation refused" in resp.data["payment_error"]["message"]
    # The old three-call sequence would have left this orphan advance behind.
    assert not SupplierPayment.objects.exists()


def test_replaying_complete_with_the_same_key_pays_once(tenant_a):
    _, draft = _draft(tenant_a)
    first = _complete(tenant_a, draft, {"amount": "30.00", "mode": "CASH"}, HTTP_IDEMPOTENCY_KEY="k-complete-1")
    second = _complete(tenant_a, draft, {"amount": "30.00", "mode": "CASH"}, HTTP_IDEMPOTENCY_KEY="k-complete-1")
    assert first.status_code == 200 and second.status_code == 200
    assert SupplierPayment.objects.count() == 1


def test_record_payment_endpoint_pays_in_parts_and_blocks_overpay(tenant_a):
    _, draft = _draft(tenant_a)
    assert _complete(tenant_a, draft).status_code == 200
    one = tenant_a.client.post(f"{BASE}/{draft['id']}/record-payment/", {"amount": "70", "mode": "CASH"}, format="json")
    assert one.status_code == 201, one.data
    assert Decimal(str(one.data["balance"])) == Decimal("30.00")
    over = tenant_a.client.post(f"{BASE}/{draft['id']}/record-payment/", {"amount": "31", "mode": "CASH"}, format="json")
    assert over.status_code == 400
    assert SupplierPayment.objects.count() == 1
    rest = tenant_a.client.post(f"{BASE}/{draft['id']}/record-payment/", {"amount": "30", "mode": "CASH"}, format="json")
    assert rest.status_code == 201, rest.data
    assert Decimal(str(rest.data["balance"])) == Decimal("0.00")


def test_record_payment_is_idempotent_per_key(tenant_a):
    _, draft = _draft(tenant_a)
    assert _complete(tenant_a, draft).status_code == 200
    body = {"amount": "25", "mode": "CASH"}
    a = tenant_a.client.post(f"{BASE}/{draft['id']}/record-payment/", body, format="json", HTTP_IDEMPOTENCY_KEY="k-rp-1")
    b = tenant_a.client.post(f"{BASE}/{draft['id']}/record-payment/", body, format="json", HTTP_IDEMPOTENCY_KEY="k-rp-1")
    assert a.status_code == 201 and b.status_code in (200, 201)
    assert SupplierPayment.objects.count() == 1


def test_record_payment_refuses_a_draft_bill(tenant_a):
    _, draft = _draft(tenant_a)
    resp = tenant_a.client.post(f"{BASE}/{draft['id']}/record-payment/", {"amount": "10", "mode": "CASH"}, format="json")
    assert resp.status_code == 400
    assert not SupplierPayment.objects.exists()


def test_record_payment_does_not_cross_tenants(tenant_a, tenant_b):
    _, draft = _draft(tenant_a)
    assert _complete(tenant_a, draft).status_code == 200
    resp = tenant_b.client.post(f"{BASE}/{draft['id']}/record-payment/", {"amount": "10", "mode": "CASH"}, format="json")
    assert resp.status_code == 404
    assert not SupplierPayment.objects.exists()
