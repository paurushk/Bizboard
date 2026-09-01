"""W0-03: verified gateway captures park when books cannot post."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from payments.models import (
    CustomerReceipt,
    GatewayPayment,
    GatewayPaymentStatus,
    SupplierPayment,
)
from payments.services import PaymentService
from reporting.gst_periods import reopen_period, soft_close_period
from tests.conftest import make_supplier
from tests.test_phase3_payments import _complete_invoice, _post_sandbox_webhook

pytestmark = pytest.mark.django_db


def _period_for_today() -> str:
    today = timezone.localdate()
    return f"{today.year:04d}-{today.month:02d}"


def _link_and_body(tenant, amount="1000", payment_id="pay_hold_1"):
    inv, customer = _complete_invoice(tenant)
    link = PaymentService.create_payment_link(
        company=tenant.company,
        amount=Decimal(amount),
        sales_invoice=inv,
        customer=customer,
        provider="sandbox",
        public_base_url="http://testserver",
    )
    body = {
        "payment_id": payment_id,
        "amount": f"{amount}.00" if "." not in str(amount) else str(amount),
        "fee": "0",
        "status": "CAPTURED",
        "payment_link_id": link.provider_link_id,
    }
    return inv, link, body


def test_closed_period_webhook_holds_then_reconcile_posts(tenant_a):
    inv, link, body = _link_and_body(tenant_a, payment_id="pay_period_1")
    period = _period_for_today()
    soft_close_period(tenant_a.company, period, tenant_a.owner)

    wh = _post_sandbox_webhook(tenant_a.client, tenant_a.company.id, body)
    assert wh.status_code == 200, wh.data
    gp = GatewayPayment.objects.get(provider_payment_id="pay_period_1")
    assert gp.status == GatewayPaymentStatus.CAPTURED_PENDING_BOOKS
    assert gp.holding_reason == "PERIOD_LOCKED"
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0

    retrieved = tenant_a.client.get(f"/api/v1/sales/invoices/{inv.id}/")
    assert retrieved.status_code == 200
    assert retrieved.data["payment_state"] != "UNPAID"
    assert retrieved.data["payment_state"] == "PAID_PENDING_BOOKS"

    public = tenant_a.client.get(f"/api/v1/public/pay/{link.token}/")
    assert public.status_code == 200
    assert public.data["paid"] is True
    assert public.data["payment_state"] == "PAID_PENDING_BOOKS"

    listed = tenant_a.client.get(
        "/api/v1/payments/gateway-payments/?status=CAPTURED_PENDING_BOOKS"
    )
    assert listed.status_code == 200
    rows = listed.data["results"] if isinstance(listed.data, dict) else listed.data
    assert any(str(row["id"]) == str(gp.id) for row in rows)

    health = tenant_a.client.get("/api/v1/payments/health/")
    assert health.status_code == 200
    codes = [a["code"] for a in health.data.get("alerts", [])]
    assert "GATEWAY_CAPTURE_HOLDING" in codes

    reopen_period(tenant_a.company, period)
    posted, attempted = PaymentService.reconcile_gateway_captures(older_than_minutes=0)
    assert attempted >= 1
    assert posted == 1
    gp.refresh_from_db()
    assert gp.status == GatewayPaymentStatus.CAPTURED
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 1

    retrieved2 = tenant_a.client.get(f"/api/v1/sales/invoices/{inv.id}/")
    assert retrieved2.data["payment_state"] == "PAID"


def test_duplicate_webhook_one_receipt(tenant_a):
    _inv, _link, body = _link_and_body(tenant_a, payment_id="pay_dup_1")
    wh1 = _post_sandbox_webhook(tenant_a.client, tenant_a.company.id, body)
    wh2 = _post_sandbox_webhook(tenant_a.client, tenant_a.company.id, body)
    assert wh1.status_code == 200
    assert wh2.status_code == 200
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 1
    assert GatewayPayment.objects.filter(provider_payment_id="pay_dup_1").count() == 1


def test_duplicate_webhook_while_holding_still_one_receipt(tenant_a):
    _inv, _link, body = _link_and_body(tenant_a, payment_id="pay_dup_hold")
    period = _period_for_today()
    soft_close_period(tenant_a.company, period, tenant_a.owner)
    assert _post_sandbox_webhook(tenant_a.client, tenant_a.company.id, body).status_code == 200
    assert _post_sandbox_webhook(tenant_a.client, tenant_a.company.id, body).status_code == 200
    assert (
        GatewayPayment.objects.filter(
            provider_payment_id="pay_dup_hold",
            status=GatewayPaymentStatus.CAPTURED_PENDING_BOOKS,
        ).count()
        == 1
    )
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0
    reopen_period(tenant_a.company, period)
    PaymentService.reconcile_gateway_captures(older_than_minutes=0)
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 1


def test_reconcile_auto_refunds_capture_parked_for_cancelled_invoice(tenant_a, django_capture_on_commit_callbacks):
    """Owner decision 2026-09-01: a capture parked because its invoice/link was
    cancelled can never post to books — reconcile must refund it, not retry
    finalize forever."""
    from payments.models import GatewayRefundOutbox, GatewayRefundOutboxStatus
    from sales.services import SalesService

    inv, link, body = _link_and_body(tenant_a, payment_id="pay_terminal_1")
    SalesService.cancel(inv, tenant_a.owner)

    wh = _post_sandbox_webhook(tenant_a.client, tenant_a.company.id, body)
    assert wh.status_code == 200, wh.data
    gp = GatewayPayment.objects.get(provider_payment_id="pay_terminal_1")
    assert gp.status == GatewayPaymentStatus.CAPTURED_PENDING_BOOKS
    assert gp.holding_reason in ("INVOICE_CANCELLED", "LINK_CANCELLED")

    with django_capture_on_commit_callbacks(execute=True):
        posted, attempted = PaymentService.reconcile_gateway_captures(older_than_minutes=0)
    assert attempted >= 1
    assert posted == 0  # never finalized to books
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0

    outbox = GatewayRefundOutbox.objects.get(gateway_payment=gp)
    assert outbox.status == GatewayRefundOutboxStatus.SUCCEEDED
    gp.refresh_from_db()
    assert gp.status == GatewayPaymentStatus.REFUNDED

    # Reconcile again — idempotent, no duplicate outbox row, no error.
    PaymentService.reconcile_gateway_captures(older_than_minutes=0)
    assert GatewayRefundOutbox.objects.filter(gateway_payment=gp).count() == 1

    health = tenant_a.client.get("/api/v1/payments/health/")
    codes = [a["code"] for a in health.data.get("alerts", [])]
    assert "GATEWAY_CAPTURE_HOLDING" not in codes


def test_utr_clash_does_not_drop_capture(tenant_a):
    inv, link, body = _link_and_body(tenant_a, payment_id="pay_clash_1")
    supplier = make_supplier(tenant_a.company)
    SupplierPayment.objects.create(
        company=tenant_a.company,
        supplier=supplier,
        amount=Decimal("10"),
        mode="UPI",
        utr="PAY_CLASH_1",
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    wh = _post_sandbox_webhook(tenant_a.client, tenant_a.company.id, body)
    assert wh.status_code == 200, wh.data
    gp = GatewayPayment.objects.get(provider_payment_id="pay_clash_1")
    assert gp.status in (
        GatewayPaymentStatus.CAPTURED,
        GatewayPaymentStatus.CAPTURED_PENDING_BOOKS,
    )
    assert GatewayPayment.objects.filter(provider_payment_id="pay_clash_1").exists()
    if gp.status == GatewayPaymentStatus.CAPTURED:
        assert gp.internal_utr
        assert CustomerReceipt.objects.filter(gateway_payment=gp).exists()


def test_retry_books_endpoint_after_period_open(tenant_a):
    _inv, _link, body = _link_and_body(tenant_a, payment_id="pay_retry_api")
    period = _period_for_today()
    soft_close_period(tenant_a.company, period, tenant_a.owner)
    _post_sandbox_webhook(tenant_a.client, tenant_a.company.id, body)
    gp = GatewayPayment.objects.get(provider_payment_id="pay_retry_api")
    reopen_period(tenant_a.company, period)
    retry = tenant_a.client.post(f"/api/v1/payments/gateway-payments/{gp.id}/retry-books/")
    assert retry.status_code == 200, retry.data
    gp.refresh_from_db()
    assert gp.status == GatewayPaymentStatus.CAPTURED
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 1


def test_cashfree_payu_remain_dark():
    from django.conf import settings

    assert settings.ENABLE_CASHFREE is False
    assert settings.ENABLE_PAYU is False
