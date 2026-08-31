"""Phase 3 payments & cash ops tests."""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal

import pytest
from django.utils import timezone

from payments.models import BankAccount, CustomerReceipt, PaymentLink, PaymentLinkStatus
from payments.services import PaymentService
from payments.upi import build_upi_intent, normalize_utr
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _post_sandbox_webhook(client, company_id: int, body: dict):
    """POST sandbox webhook with valid per-company HMAC (BB-000412)."""
    from payments.gateway import sandbox_webhook_secret_for_company

    raw = json.dumps(body).encode()
    secret = sandbox_webhook_secret_for_company(company_id)
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post(
        f"/api/v1/webhooks/payments/sandbox/?company_id={company_id}",
        raw,
        content_type="application/json",
        HTTP_X_SANDBOX_SIGNATURE=sig,
    )


def _complete_invoice(tenant, qty="1", price="1000"):
    product = make_product(tenant.company)
    add_stock(tenant, product, "20")
    customer = make_customer(tenant.company)
    inv = create_draft_invoice(
        tenant,
        customer,
        [{"product": product.id, "quantity": qty, "unit_price": price, "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    return SalesInvoice.objects.get(pk=inv["id"]), customer


def test_upi_intent_amount_locked():
    url = build_upi_intent(upi_id="shop@upi", amount=Decimal("1500.50"), note="INV-1", payee_name="Demo")
    assert url.startswith("upi://pay?")
    assert "pa=shop@upi" in url or "pa=shop%40upi" in url
    assert "am=1500.50" in url
    assert "cu=INR" in url


def test_normalize_utr():
    assert normalize_utr("  abc 123 ") == "ABC123"


def test_bank_account_crud(tenant_a):
    r = tenant_a.client.post(
        "/api/v1/payments/bank-accounts/",
        {"name": "HDFC Current", "account_type": "CURRENT", "is_default": True},
        format="json",
    )
    assert r.status_code == 201, r.data
    assert BankAccount.objects.filter(company=tenant_a.company).count() == 1
    listed = tenant_a.client.get("/api/v1/payments/bank-accounts/")
    assert listed.status_code == 200


def test_company_bank_syncs_into_bank_accounts_list(tenant_a):
    company = tenant_a.company
    company.bank_name = "HDFC"
    company.bank_account = "123456789012"
    company.bank_ifsc = "HDFC0001234"
    company.save(update_fields=["bank_name", "bank_account", "bank_ifsc"])
    listed = tenant_a.client.get("/api/v1/payments/bank-accounts/")
    assert listed.status_code == 200
    rows = listed.data.get("results") if isinstance(listed.data, dict) else listed.data
    names = [row.get("name") for row in rows]
    assert "HDFC" in names
    assert BankAccount.objects.filter(company=company).exists()


def test_receipt_with_utr_and_bank_account(tenant_a):
    customer = make_customer(tenant_a.company)
    ba = BankAccount.objects.create(company=tenant_a.company, name="Cash", is_default=True)
    r = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {
            "customer": customer.id,
            "amount": "500.00",
            "mode": "UPI",
            "utr": "UTRTEST123456",
            "bank_account": ba.id,
            "receipt_date": str(timezone.localdate()),
        },
        format="json",
    )
    assert r.status_code == 201, r.data
    assert r.data["utr"] == "UTRTEST123456"
    assert r.data["source"] == "MANUAL"


def test_upi_qr_endpoint(tenant_a):
    inv, _ = _complete_invoice(tenant_a)
    tenant_a.company.upi_id = "demo@upi"
    tenant_a.company.save(update_fields=["upi_id"])
    r = tenant_a.client.post(
        "/api/v1/payments/upi-qr/",
        {"sales_invoice": inv.id},
        format="json",
    )
    assert r.status_code == 200, r.data
    assert r.data["amount_locked"] is True
    assert "intent_url" in r.data


def test_payment_link_webhook_idempotent(tenant_a):
    inv, customer = _complete_invoice(tenant_a)
    link = PaymentService.create_payment_link(
        company=tenant_a.company,
        amount=Decimal("1000"),
        sales_invoice=inv,
        customer=customer,
        provider="sandbox",
        public_base_url="http://testserver",
    )
    assert link.status == PaymentLinkStatus.CREATED

    body = {
        "payment_id": "pay_test_1",
        "amount": "1000.00",
        "fee": "0",
        "status": "CAPTURED",
        "payment_link_id": link.provider_link_id,
    }
    wh1 = _post_sandbox_webhook(tenant_a.client, tenant_a.company.id, body)
    assert wh1.status_code == 200, wh1.data
    link.refresh_from_db()
    assert link.status == PaymentLinkStatus.PAID
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 1

    wh2 = _post_sandbox_webhook(tenant_a.client, tenant_a.company.id, body)
    assert wh2.status_code == 200
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 1


def test_public_pay_page(tenant_a):
    inv, customer = _complete_invoice(tenant_a)
    tenant_a.company.upi_id = "shop@upi"
    tenant_a.company.save(update_fields=["upi_id"])
    link = PaymentService.create_payment_link(
        company=tenant_a.company,
        amount=Decimal("1000"),
        sales_invoice=inv,
        customer=customer,
        provider="sandbox",
    )
    r = tenant_a.client.get(f"/api/v1/public/pay/{link.token}/")
    assert r.status_code == 200
    assert r.data["amount"] == "1000.00"
    assert r.data["upi"]["amount_locked"] is True


def test_bank_statement_upload_and_recon(tenant_a):
    customer = make_customer(tenant_a.company)
    ba = BankAccount.objects.create(company=tenant_a.company, name="HDFC", is_default=True)
    receipt = PaymentService.create_receipt(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("2500"),
        mode="BANK",
        utr="HDFCUTR998877",
        bank_account=ba,
        receipt_date=timezone.localdate(),
    )
    csv_content = (
        "Date,Credit,Debit,Narration,Ref No\n"
        f"{timezone.localdate().strftime('%d/%m/%Y')},2500,,PAYMENT FROM CUST HDFCUTR998877,HDFCUTR998877\n"
    )
    from django.core.files.uploadedfile import SimpleUploadedFile

    upload = SimpleUploadedFile("stmt.csv", csv_content.encode(), content_type="text/csv")
    r = tenant_a.client.post(
        "/api/v1/payments/statements/upload/",
        {"bank_account": ba.id, "preset": "generic", "file": upload},
        format="multipart",
    )
    assert r.status_code == 201, r.data
    sid = r.data["id"]
    commit = tenant_a.client.post(f"/api/v1/payments/statements/{sid}/commit/")
    assert commit.status_code == 200

    suggestions = tenant_a.client.get("/api/v1/payments/recon/")
    assert suggestions.status_code == 200
    assert len(suggestions.data["results"]) >= 1
    line_id = suggestions.data["results"][0]["line"]["id"]
    confirm = tenant_a.client.post(
        "/api/v1/payments/recon/confirm/",
        {"line": line_id, "receipt": receipt.id, "confidence": 95},
        format="json",
    )
    assert confirm.status_code == 201, confirm.data


def test_cash_book_report(tenant_a):
    customer = make_customer(tenant_a.company)
    PaymentService.create_receipt(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("100"),
        mode="CASH",
    )
    r = tenant_a.client.get("/api/v1/reports/cash-book/")
    assert r.status_code == 200
    assert Decimal(str(r.data["inflow"])) >= Decimal("100")
    assert r.data["kind"] == "actuals"


def test_webhook_hmac_fail_rejected(tenant_a):
    inv, customer = _complete_invoice(tenant_a)
    link = PaymentService.create_payment_link(
        company=tenant_a.company,
        amount=Decimal("1000"),
        sales_invoice=inv,
        customer=customer,
        provider="sandbox",
    )
    body = {
        "payment_id": "pay_bad_sig",
        "amount": "1000.00",
        "status": "CAPTURED",
        "payment_link_id": link.provider_link_id,
    }
    wh = tenant_a.client.post(
        f"/api/v1/webhooks/payments/sandbox/?company_id={tenant_a.company.id}",
        body,
        format="json",
        HTTP_X_SANDBOX_SIGNATURE="nope",
    )
    assert wh.status_code in (400, 401, 403)
    link.refresh_from_db()
    assert link.status == PaymentLinkStatus.CREATED
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0


def test_outstanding_invariant_after_webhook(tenant_a):
    from ledgers.services import LedgerService

    inv, customer = _complete_invoice(tenant_a, price="2000")
    link = PaymentService.create_payment_link(
        company=tenant_a.company,
        amount=Decimal("2000"),
        sales_invoice=inv,
        customer=customer,
        provider="sandbox",
    )
    body = {
        "payment_id": "pay_full_1",
        "amount": "2000.00",
        "fee": "0",
        "status": "CAPTURED",
        "payment_link_id": link.provider_link_id,
    }
    wh = _post_sandbox_webhook(tenant_a.client, tenant_a.company.id, body)
    assert wh.status_code == 200, wh.data
    inv.refresh_from_db()
    assert LedgerService.sales_invoice_outstanding(inv) == Decimal("0")


def test_ambiguous_match_does_not_auto_apply(tenant_a):
    from payments.models import BankLineMatchStatus, BankStatement, BankStatementLine, BankStatementStatus
    from payments.recon import is_exact_unique_suggestion, suggest_matches

    customer = make_customer(tenant_a.company)
    ba = BankAccount.objects.create(company=tenant_a.company, name="HDFC", is_default=True)
    # Two receipts same amount — ambiguous
    PaymentService.create_receipt(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("1000"),
        mode="BANK",
        utr="SAMEUTR01",
        bank_account=ba,
    )
    PaymentService.create_receipt(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("1000"),
        mode="BANK",
        utr="SAMEUTR02",
        bank_account=ba,
    )
    stmt = BankStatement.objects.create(
        company=tenant_a.company,
        bank_account=ba,
        status=BankStatementStatus.COMMITTED,
        period_start=timezone.localdate(),
        period_end=timezone.localdate(),
    )
    line = BankStatementLine.objects.create(
        company=tenant_a.company,
        statement=stmt,
        txn_date=timezone.localdate(),
        amount=Decimal("1000"),
        narration="PAYMENT",
        utr="",
        line_hash="ambig1",
        match_status=BankLineMatchStatus.UNMATCHED,
    )
    suggestions = suggest_matches(company=tenant_a.company, line=line)
    assert not is_exact_unique_suggestion(suggestions, line)
    tenant_a.company.auto_match_bank_exact = True
    tenant_a.company.save(update_fields=["auto_match_bank_exact"])
    # Re-run commit path logic: line should stay unmatched
    if is_exact_unique_suggestion(suggestions, line):
        pytest.fail("ambiguous suggestions must not be exact-unique")
    line.refresh_from_db()
    assert line.match_status != BankLineMatchStatus.MATCHED


def test_require_payment_reference(tenant_a):
    customer = make_customer(tenant_a.company)
    tenant_a.company.require_payment_reference = True
    tenant_a.company.save(update_fields=["require_payment_reference"])
    r = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {
            "customer": customer.id,
            "amount": "100.00",
            "mode": "UPI",
            "receipt_date": str(timezone.localdate()),
        },
        format="json",
    )
    assert r.status_code == 400
    ok = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {
            "customer": customer.id,
            "amount": "100.00",
            "mode": "UPI",
            "utr": "REQREF123",
            "receipt_date": str(timezone.localdate()),
        },
        format="json",
    )
    assert ok.status_code == 201, ok.data


def test_auto_match_bank_exact(tenant_a):
    from payments.models import BankLineMatchStatus, BankStatementLine

    customer = make_customer(tenant_a.company)
    ba = BankAccount.objects.create(company=tenant_a.company, name="ICICI", is_default=True)
    receipt = PaymentService.create_receipt(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("3333"),
        mode="BANK",
        utr="EXACTUTR7788",
        bank_account=ba,
        receipt_date=timezone.localdate(),
    )
    tenant_a.company.auto_match_bank_exact = True
    tenant_a.company.save(update_fields=["auto_match_bank_exact"])
    csv_content = (
        "Date,Credit,Debit,Narration,Ref No\n"
        f"{timezone.localdate().strftime('%d/%m/%Y')},3333,,INWARD EXACTUTR7788,EXACTUTR7788\n"
    )
    from django.core.files.uploadedfile import SimpleUploadedFile

    upload = SimpleUploadedFile("stmt.csv", csv_content.encode(), content_type="text/csv")
    r = tenant_a.client.post(
        "/api/v1/payments/statements/upload/",
        {"bank_account": ba.id, "preset": "generic", "file": upload},
        format="multipart",
    )
    assert r.status_code == 201, r.data
    commit = tenant_a.client.post(f"/api/v1/payments/statements/{r.data['id']}/commit/")
    assert commit.status_code == 200, commit.data
    line = BankStatementLine.objects.get(statement_id=r.data["id"])
    assert line.match_status == BankLineMatchStatus.MATCHED
    assert line.recon_match.receipt_id == receipt.id


def test_payment_health_and_refund(tenant_a):
    from ledgers.services import LedgerService
    from payments.models import (
        CustomerReceipt,
        GatewayPayment,
        GatewayPaymentStatus,
        PaymentLinkStatus,
        ReceiptStatus,
    )

    inv, customer = _complete_invoice(tenant_a)
    link = PaymentService.create_payment_link(
        company=tenant_a.company,
        amount=Decimal("1000"),
        sales_invoice=inv,
        customer=customer,
        provider="sandbox",
    )
    body = {
        "payment_id": "pay_refund_1",
        "amount": "1000.00",
        "fee": "0",
        "status": "CAPTURED",
        "payment_link_id": link.provider_link_id,
    }
    wh = _post_sandbox_webhook(tenant_a.client, tenant_a.company.id, body)
    assert wh.status_code == 200
    gp = GatewayPayment.objects.get(provider_payment_id="pay_refund_1")
    refund = tenant_a.client.post(f"/api/v1/payments/gateway-payments/{gp.id}/refund/", {}, format="json")
    assert refund.status_code == 200, refund.data
    gp.refresh_from_db()
    assert gp.status == GatewayPaymentStatus.REFUNDED

    # BB-000457 / BB-000458: no phantom advance; link reopened.
    receipt = CustomerReceipt.objects.get(gateway_payment=gp)
    assert receipt.status == ReceiptStatus.REFUNDED
    assert LedgerService.customer_unallocated_receipts(tenant_a.company, customer) == Decimal("0")
    link.refresh_from_db()
    assert link.status == PaymentLinkStatus.SENT
    assert link.paid_receipt_id is None
    assert LedgerService.sales_invoice_outstanding(inv) == Decimal("1000")

    health = tenant_a.client.get("/api/v1/payments/health/")
    assert health.status_code == 200
    assert "alerts" in health.data
    assert "unmatched_aging" in health.data


def test_refund_allows_recapture_on_reopened_link(tenant_a):
    """BB-000458: after full refund, a new capture on the same link succeeds."""
    from payments.models import GatewayPayment, GatewayPaymentStatus, PaymentLinkStatus

    inv, customer = _complete_invoice(tenant_a)
    link = PaymentService.create_payment_link(
        company=tenant_a.company,
        amount=Decimal("1000"),
        sales_invoice=inv,
        customer=customer,
        provider="sandbox",
    )
    body1 = {
        "payment_id": "pay_recap_1",
        "amount": "1000.00",
        "fee": "0",
        "status": "CAPTURED",
        "payment_link_id": link.provider_link_id,
    }
    assert _post_sandbox_webhook(tenant_a.client, tenant_a.company.id, body1).status_code == 200
    gp = GatewayPayment.objects.get(provider_payment_id="pay_recap_1")
    assert tenant_a.client.post(
        f"/api/v1/payments/gateway-payments/{gp.id}/refund/", {}, format="json"
    ).status_code == 200
    link.refresh_from_db()
    assert link.status == PaymentLinkStatus.SENT

    body2 = {
        "payment_id": "pay_recap_2",
        "amount": "1000.00",
        "fee": "0",
        "status": "CAPTURED",
        "payment_link_id": link.provider_link_id,
    }
    wh2 = _post_sandbox_webhook(tenant_a.client, tenant_a.company.id, body2)
    assert wh2.status_code == 200, getattr(wh2, "data", wh2.content)
    link.refresh_from_db()
    assert link.status == PaymentLinkStatus.PAID
    assert GatewayPayment.objects.get(provider_payment_id="pay_recap_2").status == (
        GatewayPaymentStatus.CAPTURED
    )


def test_underpayment_rejected_when_partial_disallowed(tenant_a):
    from payments.models import GatewayPayment, GatewayPaymentStatus

    inv, customer = _complete_invoice(tenant_a)
    link = PaymentService.create_payment_link(
        company=tenant_a.company,
        amount=Decimal("1000"),
        sales_invoice=inv,
        customer=customer,
        provider="sandbox",
        allow_partial=False,
    )
    body = {
        "payment_id": "pay_under_1",
        "amount": "500.00",
        "fee": "0",
        "status": "CAPTURED",
        "payment_link_id": link.provider_link_id,
    }
    wh = _post_sandbox_webhook(tenant_a.client, tenant_a.company.id, body)
    # W0-03: signature-ok under-capture is parked, not 4xx'd (Razorpay would retry).
    assert wh.status_code == 200, getattr(wh, "data", wh.content)
    link.refresh_from_db()
    assert link.status == PaymentLinkStatus.CREATED
    gp = GatewayPayment.objects.get(provider_payment_id="pay_under_1")
    assert gp.status == GatewayPaymentStatus.CAPTURED_PENDING_BOOKS
    assert gp.holding_reason == "AMOUNT_MISMATCH"
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0


def test_cash_book_xlsx(tenant_a):
    customer = make_customer(tenant_a.company)
    PaymentService.create_receipt(
        company=tenant_a.company, customer=customer, amount=Decimal("50"), mode="CASH"
    )
    r = tenant_a.client.get("/api/v1/reports/cash-book/?export=xlsx")
    assert r.status_code == 200
    assert "spreadsheetml" in r["Content-Type"]
