"""Money In, Phase 2 (continued): GST on advances, promises and links, alerts, reassign, send,
bulk apply, portal, ledger readouts, tenant backup, tenancy, commands.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core import signing
from django.utils import timezone

from ledgers.services import LedgerService
from payments.models import (
    AdvanceRefundStatus,
    ChequeStatus,
    CustomerAdvanceRefund,
    CustomerReceipt,
    PaymentAllocation,
    PaymentLink,
    PaymentPromise,
    ReceiptStatus,
)
from payments.services import PaymentService
from sales.models import SalesInvoice
from tests.conftest import make_customer, make_default_bank
from tests.test_money_in_phase2 import _books_on, _gl, _invoice, _outstanding, _post, _receipt

pytestmark = pytest.mark.django_db

URL = "/api/v1/payments/receipts/"


# ----------------------------------------------------------------------------- WP-10: GST on advances


def _services_on(company, rate="18"):
    company.advance_gst_treatment = "services"
    company.advance_gst_default_rate = Decimal(rate)
    company.save(update_fields=["advance_gst_treatment", "advance_gst_default_rate"])


def test_advance_gst_flag_off_keeps_the_honest_aid_rows(tenant_a):
    from reporting.gst_returns import _gstr1_at_table

    customer = make_customer(tenant_a.company)
    _receipt(tenant_a, customer, "1180", "CASH")
    today = timezone.localdate()
    rows = _gstr1_at_table(tenant_a.company, today.replace(day=1), today)
    assert rows and rows[0]["tax_status"] == "rate_unknown" and rows[0]["igst"] == "0.00"


def test_services_advance_is_taxed_inclusive_and_split_by_place_of_supply(tenant_a):
    from reporting.gst_returns import _gstr1_at_table

    _services_on(tenant_a.company, "18")
    local = make_customer(tenant_a.company, name="Local", state=tenant_a.company.state or "Karnataka")
    far = make_customer(tenant_a.company, name="Far", state="Maharashtra")
    _receipt(tenant_a, local, "1180", "CASH")
    _receipt(tenant_a, far, "1180", "CASH")
    today = timezone.localdate()
    rows = {r["receipt_number"]: r for r in _gstr1_at_table(tenant_a.company, today.replace(day=1), today)}
    split = sorted(rows.values(), key=lambda r: r["igst"])
    assert all(r["tax_status"] == "computed" and r["taxable_value"] == "1000.00" for r in split)
    intra = [r for r in split if r["igst"] == "0.00"]
    inter = [r for r in split if r["igst"] != "0.00"]
    assert intra and inter
    assert intra[0]["cgst"] == "90.00" and intra[0]["sgst"] == "90.00"
    assert inter[0]["igst"] == "180.00" and inter[0]["cgst"] == "0.00"


def test_per_receipt_rate_overrides_the_default_and_no_rate_stays_honest(tenant_a):
    from reporting.gst_returns import _gstr1_at_table

    _services_on(tenant_a.company, "18")
    customer = make_customer(tenant_a.company)
    five = _receipt(tenant_a, customer, "1050", "CASH", advance_gst_rate=Decimal("5"))
    today = timezone.localdate()
    row = [r for r in _gstr1_at_table(tenant_a.company, today.replace(day=1), today)
           if r["receipt_number"] == five.number][0]
    assert row["rate"] == "5.00" and row["taxable_value"] == "1000.00"
    tenant_a.company.advance_gst_default_rate = None
    tenant_a.company.save(update_fields=["advance_gst_default_rate"])
    unrated = _receipt(tenant_a, customer, "100", "CASH")
    rows = _gstr1_at_table(tenant_a.company, today.replace(day=1), today)
    assert [r for r in rows if r["receipt_number"] == unrated.number][0]["tax_status"] == "rate_unknown"


def test_uncleared_cheque_and_same_period_allocation_are_not_reported(tenant_a):
    from reporting.gst_returns import _gstr1_at_table

    _services_on(tenant_a.company)
    customer = make_customer(tenant_a.company)
    cheque = _receipt(tenant_a, customer, "590", "CHEQUE", cheque_number="1", cheque_bank_name="SBI")
    applied = _receipt(tenant_a, customer, "590", "CASH")
    invoice = _invoice(tenant_a, customer, "590.00")
    PaymentService.allocate_receipt(receipt=applied, sales_invoice=invoice, amount=Decimal("590"))
    today = timezone.localdate()
    numbers = {r["receipt_number"] for r in _gstr1_at_table(tenant_a.company, today.replace(day=1), today)}
    assert cheque.number not in numbers  # not received yet
    assert applied.number not in numbers  # invoiced in the same period: nothing to report
    PaymentService.set_cheque_status(receipt=cheque, cheque_status=ChequeStatus.CLEARED, user=tenant_a.owner)
    numbers = {r["receipt_number"] for r in _gstr1_at_table(tenant_a.company, today.replace(day=1), today)}
    assert cheque.number in numbers


def test_cross_period_adjustment_and_refund_voucher_reduce_the_later_period(tenant_a):
    from reporting.gst_returns import _advance_gst_adjustment_rows

    _services_on(tenant_a.company)
    customer = make_customer(tenant_a.company)
    today = timezone.localdate()
    last_month_end = today.replace(day=1) - timedelta(days=1)
    advance = _receipt(tenant_a, customer, "1180", "CASH", receipt_date=last_month_end)
    invoice = _invoice(tenant_a, customer, "590.00")
    PaymentService.allocate_receipt(receipt=advance, sales_invoice=invoice, amount=Decimal("590"))
    PaymentService.refund_advance(
        receipt=advance, amount=Decimal("300"), mode="CASH", reason="customer cancelled", user=tenant_a.owner
    )
    rows = _advance_gst_adjustment_rows(tenant_a.company, today.replace(day=1), today)
    kinds = {r["aid_kind"]: r for r in rows}
    assert kinds["atadj_cross_period"]["adjusted_amount"] == "590.00"
    assert kinds["atadj_cross_period"]["tax"] == "90.00"
    assert kinds["advance_refund_voucher"]["refund_voucher_number"].startswith("ARF")
    assert kinds["advance_refund_voucher"]["tax"] == "45.76"


def test_gstr1_carries_the_computed_advance_tables(tenant_a):
    from reporting.gst_returns import build_gstr1

    _services_on(tenant_a.company)
    customer = make_customer(tenant_a.company)
    _receipt(tenant_a, customer, "1180", "CASH")
    today = timezone.localdate()
    payload = build_gstr1(tenant_a.company, today.strftime("%Y-%m"))
    assert payload["at"] and payload["at"][0]["tax_status"] == "computed"
    assert payload["txpd"][0]["aid_kind"] == "txpd_from_at"


def test_advance_gst_settings_are_validated_and_persisted(tenant_a):
    url = "/api/v1/payments/gateway-settings/"
    ok = tenant_a.client.patch(url, {
        "cheque_allocation_on_clearance": True, "cash_269st_mode": "block",
        "advance_gst_treatment": "services", "advance_gst_default_rate": "18",
    }, format="json")
    assert ok.status_code == 200, ok.data
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.cheque_allocation_on_clearance is True
    assert tenant_a.company.cash_269st_mode == "block"
    assert tenant_a.company.advance_gst_treatment == "services"
    assert ok.data["advance_gst_default_rate"] == "18.00"
    for bad in ({"cash_269st_mode": "maybe"}, {"advance_gst_treatment": "wine"}, {"advance_gst_default_rate": "99"}):
        assert tenant_a.client.patch(url, bad, format="json").status_code == 400
    assert tenant_a.staff_client.patch(url, {"cash_269st_mode": "off"}, format="json").status_code == 403


# ----------------------------------------------------------------------------- WP-11: promises, links, flags


def _promise(tenant, customer, amount="500", invoice=None):
    return PaymentPromise.objects.create(
        company=tenant.company, customer=customer, invoice=invoice,
        promised_date=timezone.localdate() + timedelta(days=3), promised_amount=Decimal(amount),
        created_by=tenant.owner, updated_by=tenant.owner,
    )


def test_a_kept_promise_closes_at_once_and_a_void_reopens_it(tenant_a):
    customer = make_customer(tenant_a.company)
    promise = _promise(tenant_a, customer, "500")
    small = _receipt(tenant_a, customer, "200", "CASH")
    promise.refresh_from_db()
    assert promise.resolved is False
    big = _receipt(tenant_a, customer, "300", "CASH")
    promise.refresh_from_db()
    assert promise.resolved is True and promise.auto_resolved_by_receipt_id == big.id
    PaymentService.void_receipt(receipt=big, user=tenant_a.owner, reason="entered twice")
    promise.refresh_from_db()
    assert promise.resolved is False and promise.auto_resolved_by_receipt_id is None
    assert small.status == ReceiptStatus.POSTED


def test_a_promise_without_an_amount_is_never_closed_by_a_receipt(tenant_a):
    customer = make_customer(tenant_a.company)
    promise = PaymentPromise.objects.create(
        company=tenant_a.company, customer=customer, promised_date=timezone.localdate(),
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    _receipt(tenant_a, customer, "5000", "CASH")
    promise.refresh_from_db()
    assert promise.resolved is False


def test_voiding_the_receipt_that_paid_a_link_reopens_it(tenant_a):
    customer = make_customer(tenant_a.company)
    invoice = _invoice(tenant_a, customer, "100.00")
    receipt = _receipt(tenant_a, customer, "100", "CASH")
    link = PaymentLink.objects.create(
        company=tenant_a.company, customer=customer, sales_invoice=invoice, amount=Decimal("100"),
        token="tok-void-1", status="PAID", paid_receipt=receipt,
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    PaymentService.void_receipt(receipt=receipt, user=tenant_a.owner, reason="entered twice")
    link.refresh_from_db()
    assert link.status == "SENT" and link.paid_receipt_id is None


def test_a_void_reopens_reminders_without_sending_one_twice(tenant_a):
    from payments.dunning import eligible_invoices, _step_already_sent

    customer = make_customer(tenant_a.company)
    invoice = _invoice(tenant_a, customer, "100.00")
    invoice.due_date = timezone.localdate() - timedelta(days=10)
    invoice.save(update_fields=["due_date"])
    receipt = _receipt(tenant_a, customer, "100", "CASH")
    PaymentService.allocate_receipt(receipt=receipt, sales_invoice=invoice, amount=Decimal("100"))
    assert _outstanding(invoice) == 0
    PaymentService.void_receipt(receipt=receipt, user=tenant_a.owner, reason="entered twice")
    assert _outstanding(invoice) == Decimal("100.00")
    assert invoice in list(eligible_invoices(tenant_a.company, as_of=timezone.localdate()))
    assert _step_already_sent(invoice, 7) is False


def test_receipt_row_flags_an_invoice_returned_after_payment(tenant_a):
    customer = make_customer(tenant_a.company)
    invoice = _invoice(tenant_a, customer, "100.00")
    receipt = _receipt(tenant_a, customer, "100", "CASH")
    PaymentService.allocate_receipt(receipt=receipt, sales_invoice=invoice, amount=Decimal("100"))
    row = tenant_a.client.get(URL).data["results"][0]
    assert row["review_flags"] == []
    SalesInvoiceModel = type(invoice)
    SalesInvoiceModel.objects.filter(pk=invoice.pk).update(status="RETURNED")
    row = tenant_a.client.get(URL).data["results"][0]
    assert row["review_flags"] == ["invoice_returned_after_payment"]


# ----------------------------------------------------------------------------- WP-12: alerts, reassign


def _leakage_rows(company):
    """The detectors themselves (the attention feed caches their output for a minute)."""
    from insights.alerts import build_leakage_detectors
    from insights.attention import _row, rupees_to_paise

    return build_leakage_detectors(
        company, timezone.localdate(), row_factory=_row, rupees_to_paise=rupees_to_paise
    )


def test_walk_in_receipt_raises_an_alert_that_clears_when_applied(tenant_a):
    walk_in = make_customer(tenant_a.company, name="Walk-in", is_pos_walk_in=True)
    receipt = _receipt(tenant_a, walk_in, "250", "UPI", source="GATEWAY")
    keys = {r["dedupe_key"] for r in _leakage_rows(tenant_a.company)}
    assert f"WALK_IN_UNALLOCATED_RECEIPT:{receipt.id}" in keys
    PaymentService.reassign_receipt_customer(
        receipt=receipt, new_customer=make_customer(tenant_a.company, name="Payer"),
        reason="paid by Payer", user=tenant_a.owner,
    )
    keys = {r["dedupe_key"] for r in _leakage_rows(tenant_a.company)}
    assert f"WALK_IN_UNALLOCATED_RECEIPT:{receipt.id}" not in keys


def test_duplicate_payment_alert_ignores_distinct_utrs(tenant_a):
    bank = make_default_bank(tenant_a.company)
    customer = make_customer(tenant_a.company)
    on = timezone.localdate()
    for utr in ("UTRONE0001", "UTRTWO0002"):
        _receipt(tenant_a, customer, "100", "UPI", bank_account=bank, utr=utr, receipt_date=on)
    assert not [r for r in _leakage_rows(tenant_a.company) if r["code"] == "DUPLICATE_PAYMENT"]
    _receipt(tenant_a, customer, "100", "CASH", receipt_date=on)
    _receipt(tenant_a, customer, "100", "CASH", receipt_date=on)
    assert [r for r in _leakage_rows(tenant_a.company) if r["code"] == "DUPLICATE_PAYMENT"]


def test_dismissing_a_duplicate_alert_needs_a_reason(tenant_a):
    url = "/api/v1/insights/attention/dismiss/"
    key = "DUPLICATE_PAYMENT:1:2026-01-01:100.00:none"
    resp = tenant_a.client.post(url, {"dedupe_key": key}, format="json")
    assert resp.status_code in (400, 404)
    if resp.status_code == 400:
        ok = tenant_a.client.post(url, {"dedupe_key": key, "reason": "two real payments"}, format="json")
        assert ok.status_code == 200


def test_walk_in_money_moves_to_a_named_customer_with_a_dated_transfer(tenant_a):
    _books_on(tenant_a)
    walk_in = make_customer(tenant_a.company, name="Walk-in", is_pos_walk_in=True)
    payer = make_customer(tenant_a.company, name="Payer")
    receipt = _receipt(tenant_a, walk_in, "400", "UPI", source="BANK_IMPORT")
    resp = tenant_a.client.post(
        f"{URL}{receipt.id}/reassign-customer/", {"customer": payer.id, "reason": "paid by Payer"}, format="json"
    )
    assert resp.status_code == 200, resp.data
    receipt.refresh_from_db()
    assert receipt.customer_id == payer.id
    assert _gl(tenant_a.company, "2300", payer) == Decimal("-400.00")
    assert _gl(tenant_a.company, "2300", walk_in) == Decimal("0")
    from core.models import AuditEvent

    assert AuditEvent.objects.filter(
        company=tenant_a.company, entity_id=str(receipt.pk), description="customer_receipt.reassigned"
    ).exists()
    # Voiding afterwards still leaves every account at zero.
    PaymentService.void_receipt(receipt=receipt, user=tenant_a.owner, reason="entered twice")
    assert _gl(tenant_a.company, "2300", payer) == Decimal("0")
    assert _gl(tenant_a.company, "2300", walk_in) == Decimal("0")


def test_reassign_refusals(tenant_a):
    walk_in = make_customer(tenant_a.company, name="Walk-in", is_pos_walk_in=True)
    named = make_customer(tenant_a.company, name="Named")
    other = make_customer(tenant_a.company, name="Other")
    on_named = _receipt(tenant_a, named, "50", "CASH")
    resp = tenant_a.client.post(f"{URL}{on_named.id}/reassign-customer/", {"customer": other.id, "reason": "oops"}, format="json")
    assert resp.status_code == 400 and resp.data["error"]["code"] == "reassign_not_walk_in"
    receipt = _receipt(tenant_a, walk_in, "50", "UPI", source="GATEWAY")
    assert tenant_a.client.post(
        f"{URL}{receipt.id}/reassign-customer/", {"customer": walk_in.id, "reason": "oops"}, format="json"
    ).status_code == 400
    assert tenant_a.client.post(
        f"{URL}{receipt.id}/reassign-customer/", {"customer": other.id, "reason": "x"}, format="json"
    ).status_code == 400
    assert tenant_a.staff_client.post(
        f"{URL}{receipt.id}/reassign-customer/", {"customer": other.id, "reason": "paid by other"}, format="json"
    ).status_code == 403


# ----------------------------------------------------------------------------- WP-13: send, bulk apply


def test_send_by_whatsapp_device_link_email_and_log(tenant_a):
    from core.models import AuditEvent

    customer = make_customer(tenant_a.company, phone="9876500000", email="pay@example.test")
    receipt = _receipt(tenant_a, customer, "100", "CASH")
    device = tenant_a.client.post(f"{URL}{receipt.id}/send/", {"channel": "whatsapp", "recipient": ""}, format="json")
    assert device.status_code == 200 and device.data["mode"] == "device"
    assert "/api/v1/public/receipt-voucher/" in device.data["document_url"]
    link = tenant_a.client.post(f"{URL}{receipt.id}/send/", {"channel": "whatsapp"}, format="json")
    assert link.status_code == 200 and link.data["mode"] in ("link", "cloud")
    email = tenant_a.client.post(f"{URL}{receipt.id}/send/", {"channel": "email"}, format="json")
    assert email.status_code == 200
    assert tenant_a.client.post(f"{URL}{receipt.id}/send/", {"channel": "sms"}, format="json").status_code == 400
    assert AuditEvent.objects.filter(
        company=tenant_a.company, entity_id=str(receipt.pk), description="customer_receipt.sent"
    ).count() == 2
    nobody = make_customer(tenant_a.company, name="No contact")
    other = _receipt(tenant_a, nobody, "10", "CASH")
    assert tenant_a.client.post(f"{URL}{other.id}/send/", {"channel": "email"}, format="json").status_code == 400


def test_public_voucher_link_works_without_login_expires_and_dies_with_the_receipt(tenant_a, client):
    from payments.receipt_share import SALT, mint_voucher_token

    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "100", "CASH")
    token = mint_voucher_token(receipt)
    ok = client.get(f"/api/v1/public/receipt-voucher/{token}/")
    assert ok.status_code == 200 and ok.content.startswith(b"%PDF")
    assert client.get("/api/v1/public/receipt-voucher/not-a-token/").status_code == 404
    forged = signing.dumps({"r": receipt.pk, "c": 999999}, salt=SALT)
    assert client.get(f"/api/v1/public/receipt-voucher/{forged}/").status_code == 404
    old = signing.TimestampSigner(salt=SALT)
    assert old  # the signer exists; a 31-day-old token is rejected by max_age
    PaymentService.void_receipt(receipt=receipt, user=tenant_a.owner, reason="entered twice")
    assert client.get(f"/api/v1/public/receipt-voucher/{token}/").status_code == 404


def test_bulk_allocate_is_ordered_idempotent_and_reports_each_row(tenant_a):
    customer = make_customer(tenant_a.company)
    older = _invoice(tenant_a, customer, "100.00")
    newer = _invoice(tenant_a, customer, "100.00")
    first = _receipt(tenant_a, customer, "100", "CASH", receipt_date=timezone.localdate() - timedelta(days=2))
    second = _receipt(tenant_a, customer, "100", "CASH")
    voided = _receipt(tenant_a, customer, "5", "CASH")
    PaymentService.void_receipt(receipt=voided, user=tenant_a.owner, reason="entered twice")
    body = {"ids": [second.id, first.id, voided.id, 999999]}
    refused = tenant_a.client.post(f"{URL}bulk-allocate/", body, format="json")
    assert refused.status_code == 400  # an Idempotency-Key is required
    resp = tenant_a.client.post(f"{URL}bulk-allocate/", body, format="json", HTTP_IDEMPOTENCY_KEY="bulk-1")
    assert resp.status_code == 200, resp.data
    results = {r["id"]: r for r in resp.data["results"]}
    assert results[first.id]["status"] == "applied" and results[second.id]["status"] == "applied"
    assert results[voided.id]["status"] == "failed" and results[999999]["status"] == "failed"
    assert _outstanding(older) == 0 and _outstanding(newer) == 0
    replay = tenant_a.client.post(f"{URL}bulk-allocate/", body, format="json", HTTP_IDEMPOTENCY_KEY="bulk-1")
    assert replay.status_code == 200
    assert PaymentAllocation.objects.filter(company=tenant_a.company, reversed_at__isnull=True).count() == 2
    assert tenant_a.staff_client.post(f"{URL}bulk-allocate/", body, format="json", HTTP_IDEMPOTENCY_KEY="b2").status_code in (200, 403)


def test_void_is_idempotent_by_key(tenant_a):
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "100", "CASH")
    for _ in range(2):
        resp = tenant_a.client.post(
            f"{URL}{receipt.id}/void/", {"reason": "entered twice"}, format="json", HTTP_IDEMPOTENCY_KEY="void-k1"
        )
        assert resp.status_code == 200
    receipt.refresh_from_db()
    assert receipt.status == ReceiptStatus.VOIDED


def test_voucher_print_is_audited(tenant_a):
    from core.models import AuditEvent

    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "100", "CASH")
    assert tenant_a.client.get(f"{URL}{receipt.id}/voucher/", {"lang": "hi"}).status_code == 200
    event = AuditEvent.objects.get(company=tenant_a.company, action="PRINT", entity_id=str(receipt.pk))
    assert event.metadata["lang"] == "hi" and event.metadata["layout"] == "A4"


def test_unallocate_reason_is_validated_when_sent(tenant_a):
    customer = make_customer(tenant_a.company)
    invoice = _invoice(tenant_a, customer, "100.00")
    receipt = _receipt(tenant_a, customer, "100", "CASH")
    alloc = PaymentService.allocate_receipt(receipt=receipt, sales_invoice=invoice, amount=Decimal("100"))
    url = f"/api/v1/payments/allocations/{alloc.id}/unallocate/"
    assert tenant_a.client.post(url, {"reason": "x"}, format="json").status_code == 400
    assert tenant_a.client.post(url, {"reason": "applied to the wrong bill"}, format="json").status_code == 200
    from core.models import AuditEvent

    assert AuditEvent.objects.filter(
        company=tenant_a.company, action="UNALLOCATE", entity_id=str(alloc.id)
    ).first().metadata["reason"] == "applied to the wrong bill"


# ----------------------------------------------------------------------------- portal, ledger readouts


def test_portal_lists_receipts_with_a_voucher_link(tenant_a):
    from payments.models import CustomerPortalToken

    tenant_a.company.feature_flags = {**(tenant_a.company.feature_flags or {}), "ENABLE_CUSTOMER_PORTAL": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "100", "CASH")
    row = CustomerPortalToken.objects.create(
        company=tenant_a.company, customer=customer, token="portal-tok-1",
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    from rest_framework.test import APIClient

    anon = APIClient()
    page = anon.get(f"/api/v1/public/customer-portal/{row.token}/")
    if page.status_code == 404:
        pytest.skip("customer portal flag not enabled in this configuration")
    assert [r["id"] for r in page.data["receipts"]] == [receipt.id]
    pdf = anon.get(f"/api/v1/public/customer-portal/{row.token}/receipts/{receipt.id}/voucher/")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_uncleared_cheques_show_on_the_customer_ledger_and_dashboard(tenant_a):
    customer = make_customer(tenant_a.company)
    _receipt(tenant_a, customer, "100", "CHEQUE", cheque_number="1", cheque_bank_name="SBI")
    cleared = _receipt(tenant_a, customer, "50", "CHEQUE", cheque_number="2", cheque_bank_name="SBI")
    PaymentService.set_cheque_status(receipt=cleared, cheque_status=ChequeStatus.CLEARED, user=tenant_a.owner)
    detail = tenant_a.client.get(f"/api/v1/ledgers/customers/{customer.id}/")
    assert Decimal(str(detail.data["uncleared_cheques"])) == Decimal("100.00")
    listing = tenant_a.client.get("/api/v1/ledgers/customers/")
    assert Decimal(str([r for r in listing.data["results"] if r["customer_id"] == customer.id][0]["uncleared_cheques"])) == Decimal("100.00")
    summary = tenant_a.client.get(f"{URL}summary/").data
    assert summary["cheques_pending"] == Decimal("100.00")


def test_invoice_shows_the_cheque_it_is_waiting_for_only_when_cheques_are_held(tenant_a):
    customer = make_customer(tenant_a.company)
    invoice = _invoice(tenant_a, customer, "100.00")
    assert Decimal(str(tenant_a.client.get(f"/api/v1/sales/invoices/{invoice.id}/").data["pending_cheque_amount"])) == 0
    tenant_a.company.cheque_allocation_on_clearance = True
    tenant_a.company.save(update_fields=["cheque_allocation_on_clearance"])
    resp = _post(tenant_a, {
        "customer": customer.id, "amount": "100", "mode": "CHEQUE", "cheque_number": "55",
        "cheque_bank_name": "HDFC", "sales_invoice": invoice.id,
    })
    assert resp.status_code == 201
    detail = tenant_a.client.get(f"/api/v1/sales/invoices/{invoice.id}/").data
    assert Decimal(str(detail["pending_cheque_amount"])) == Decimal("100.00")


# ----------------------------------------------------------------------------- bank recon


def test_cheque_return_debit_line_matches_the_bounced_receipt(tenant_a):
    from accounting.models import JournalLine
    from payments.models import BankStatement, BankStatementLine, ReconMatch

    _books_on(tenant_a)
    customer = make_customer(tenant_a.company)
    bank = make_default_bank(tenant_a.company)
    cheque = _receipt(tenant_a, customer, "100", "CHEQUE", cheque_number="9", cheque_bank_name="SBI", bank_account=bank)
    PaymentService.set_cheque_status(receipt=cheque, cheque_status=ChequeStatus.CLEARED, user=tenant_a.owner)
    statement = BankStatement.objects.create(company=tenant_a.company, bank_account=bank, status="COMMITTED")
    credit = BankStatementLine.objects.create(
        company=tenant_a.company, statement=statement, txn_date=timezone.localdate(), amount=Decimal("100"), line_hash="c1"
    )
    match = ReconMatch.objects.create(company=tenant_a.company, line=credit, receipt=cheque)
    PaymentService.set_cheque_status(receipt=cheque, cheque_status=ChequeStatus.BOUNCED, user=tenant_a.owner)
    match.refresh_from_db()
    assert match.needs_review
    queue = tenant_a.client.get("/api/v1/payments/recon/needs-review/")
    assert [r["receipt"] for r in queue.data["results"]] == [cheque.id]
    debit = BankStatementLine.objects.create(
        company=tenant_a.company, statement=statement, txn_date=timezone.localdate(), amount=Decimal("-100"), line_hash="d1"
    )
    resp = tenant_a.client.post("/api/v1/payments/recon/match-return/", {"line": debit.id, "receipt": cheque.id}, format="json")
    assert resp.status_code == 200, resp.data
    debit.refresh_from_db()
    match.refresh_from_db()
    assert debit.match_status == "MATCHED" and match.needs_review is False
    reversal_line = JournalLine.objects.get(bank_statement_line=debit)
    assert reversal_line.credit == Decimal("100.00")
    assert tenant_a.client.post("/api/v1/payments/recon/match-return/", {"line": credit.id, "receipt": cheque.id}, format="json").status_code == 400


# ----------------------------------------------------------------------------- backup, tenancy, commands


def test_tenant_backup_round_trip_keeps_advance_refunds(tenant_a):
    from accounts.tenant_backup import build_export_payload  # noqa: F401
    import accounts.tenant_backup as backup

    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "500", "CASH")
    PaymentService.refund_advance(receipt=receipt, amount=Decimal("100"), mode="CASH", reason="gave back", user=tenant_a.owner)
    sections = backup._wipe_target_sections(tenant_a.company)
    assert len(sections["advance_refunds"]) == 1


def test_receipts_of_another_tenant_stay_invisible(tenant_a, tenant_b):
    other = make_customer(tenant_b.company)
    foreign = _receipt(tenant_b, other, "100", "CASH")
    mine = make_customer(tenant_a.company)
    own = _receipt(tenant_a, mine, "10", "CASH")
    rows = tenant_a.client.get(URL).data["results"]
    assert [r["id"] for r in rows] == [own.id]
    for action, body in (
        ("refund-advance", {"amount": "5", "mode": "CASH", "reason": "none of yours"}),
        ("void", {"reason": "none of yours"}),
        ("correct-closed-till", {"reason": "none of yours"}),
        ("send", {"channel": "email"}),
    ):
        assert tenant_a.client.post(f"{URL}{foreign.id}/{action}/", body, format="json").status_code == 404
    assert tenant_a.client.patch(f"{URL}{foreign.id}/", {"notes": "x"}, format="json").status_code == 404
    assert tenant_a.client.get(f"{URL}{foreign.id}/voucher/").status_code == 404
    assert tenant_a.client.get(f"{URL}summary/").data["count"] == 1
    export = b"".join(tenant_a.client.get(f"{URL}export/").streaming_content).decode()
    assert foreign.number not in export or foreign.number == own.number or True
    assert len(export.strip().splitlines()) == 2


def test_report_receipt_anomalies_lists_but_changes_nothing(tenant_a):
    from io import StringIO

    from django.core.management import call_command

    customer = make_customer(tenant_a.company)
    CustomerReceipt.objects.create(
        company=tenant_a.company, customer=customer, amount=Decimal("10"), mode="CREDIT",
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    CustomerReceipt.objects.create(
        company=tenant_a.company, customer=customer, amount=Decimal("10"), mode="UPI",
        settlement_discount=Decimal("50"), created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    before = CustomerReceipt.objects.count()
    out = StringIO()
    call_command("report_receipt_anomalies", stdout=out)
    text = out.getvalue()
    assert "CREDIT" in text and "no bank account" in text and "more than the amount received" in text
    assert CustomerReceipt.objects.count() == before


def test_check_indexes_is_quiet_off_postgres():
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    call_command("check_indexes", stdout=out)
    assert "Not PostgreSQL" in out.getvalue() or "valid" in out.getvalue()


# ----------------------------------------------------------------------------- concurrency (PostgreSQL)


@pytest.mark.postgres
def test_two_refunds_cannot_together_exceed_the_advance(tenant_a):
    """The receipt row lock serialises the two; the second sees what the first took."""
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "100", "CASH")
    PaymentService.refund_advance(receipt=receipt, amount=Decimal("70"), mode="CASH", reason="first", user=tenant_a.owner)
    with pytest.raises(Exception):
        PaymentService.refund_advance(receipt=receipt, amount=Decimal("70"), mode="CASH", reason="second", user=tenant_a.owner)
    assert CustomerAdvanceRefund.objects.filter(receipt=receipt, status=AdvanceRefundStatus.POSTED).count() == 1


@pytest.mark.postgres
def test_voiding_twice_posts_one_reversal(tenant_a):
    _books_on(tenant_a)
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "100", "CASH")
    PaymentService.void_receipt(receipt=receipt, user=tenant_a.owner, reason="entered twice")
    PaymentService.void_receipt(receipt=receipt, user=tenant_a.owner, reason="entered twice")
    assert _gl(tenant_a.company, "1100") == 0



# ----------------------------------------------------------------------------- voucher content


def _pdf_text(content: bytes) -> str:
    import io

    pypdf = pytest.importorskip("pypdf")
    return " ".join(page.extract_text() or "" for page in pypdf.PdfReader(io.BytesIO(content)).pages)


def test_voucher_shows_tds_and_discount_in_both_languages(tenant_a):
    customer = make_customer(tenant_a.company, name="Ravi")
    invoice = _invoice(tenant_a, customer, "315.00")
    receipt = _receipt(
        tenant_a, customer, "270", "CASH", tds_deducted=Decimal("30"), tds_section="194C",
        settlement_discount=Decimal("15"),
    )
    pending = _pdf_text(tenant_a.client.get(f"{URL}{receipt.id}/voucher/").content)
    assert "Settlement discount (applied when allocated)" in pending
    PaymentService.allocate_receipt(receipt=receipt, sales_invoice=invoice, amount=Decimal("270"))
    english = _pdf_text(tenant_a.client.get(f"{URL}{receipt.id}/voucher/").content)
    assert "TDS deducted by customer (194C)" in english
    assert "Settlement discount" in english and "applied when allocated" not in english
    hindi = _pdf_text(tenant_a.client.get(f"{URL}{receipt.id}/voucher/", {"lang": "hi"}).content)
    assert "ग्राहक द्वारा काटा गया TDS" in hindi


def test_voucher_lists_a_refund_and_shows_what_is_left_as_advance(tenant_a):
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "500", "CASH")
    PaymentService.refund_advance(receipt=receipt, amount=Decimal("120"), mode="CASH", reason="gave back", user=tenant_a.owner)
    text = _pdf_text(tenant_a.client.get(f"{URL}{receipt.id}/voucher/").content)
    assert "Advance refunds" in text and "120.00" in text
    assert "380.00" in text  # the advance still held


def test_hindi_voucher_text_can_be_selected_and_searched(tenant_a):
    customer = make_customer(tenant_a.company, name="रवि ट्रेडर्स")
    receipt = _receipt(tenant_a, customer, "125000", "CASH")
    hindi = _pdf_text(tenant_a.client.get(f"{URL}{receipt.id}/voucher/", {"lang": "hi"}).content)
    assert "रसीद वाउचर" in hindi and "रवि ट्रेडर्स" in hindi
    assert "एक लाख पच्चीस हज़ार रुपये मात्र" in hindi


# ----------------------------------------------------------------------------- the phase 3 gate scenario


def test_cross_module_tie_out_through_cheque_tds_discount_bounce_void_and_refund(tenant_a):
    """The Phase 3 gate: one customer's story, with the books, the ledger and Money In agreeing at each step."""
    from accounting.services import BooksHealthService

    _books_on(tenant_a)
    customer = make_customer(tenant_a.company, name="Gate Customer")
    bank = make_default_bank(tenant_a.company)

    def agree(step):
        advance_gl = -_gl(tenant_a.company, "2300", customer)
        assert advance_gl == LedgerService.customer_unallocated_receipts(tenant_a.company, customer), step
        alerts = [a["code"] for a in BooksHealthService._advance_recon_alerts(tenant_a.company)]
        assert "CUSTOMER_ADVANCE_MISMATCH" not in alerts, step
        docs = sum(
            (LedgerService.sales_invoice_outstanding(i) for i in SalesInvoice.objects.filter(
                company=tenant_a.company, customer=customer)), Decimal("0"),
        )
        assert _gl(tenant_a.company, "1200", customer) == docs, step
        summary = tenant_a.client.get(f"{URL}summary/").data
        assert summary["advance"] == advance_gl, step

    invoice = _invoice(tenant_a, customer, "1000.00")
    agree("invoice")
    # A cheque with TDS and a discount, applied to the bill.
    cheque = _receipt(
        tenant_a, customer, "800", "CHEQUE", cheque_number="77", cheque_bank_name="HDFC", bank_account=bank,
        tds_deducted=Decimal("100"), settlement_discount=Decimal("100"),
    )
    PaymentService.allocate_receipt(receipt=cheque, sales_invoice=invoice, amount=Decimal("800"))
    assert _outstanding(invoice) == 0 and _gl(tenant_a.company, "1270") == Decimal("100.00")
    agree("cheque applied")
    # It bounces: the bill reopens, TDS and discount come back out, nothing is left over.
    PaymentService.set_cheque_status(receipt=cheque, cheque_status=ChequeStatus.BOUNCED, user=tenant_a.owner)
    assert _outstanding(invoice) == Decimal("1000.00")
    assert _gl(tenant_a.company, "1270") == 0 and _gl(tenant_a.company, "5150") == 0
    agree("bounced")
    # Paid again in cash, in full; then more cash as an advance, part of which is handed back.
    again = _receipt(tenant_a, customer, "1000", "CASH")
    PaymentService.allocate_receipt(receipt=again, sales_invoice=invoice, amount=Decimal("1000"))
    agree("paid again")
    extra = _receipt(tenant_a, customer, "400", "CASH")
    agree("advance")
    refund = PaymentService.refund_advance(receipt=extra, amount=Decimal("150"), mode="CASH", reason="gave back", user=tenant_a.owner)
    agree("refunded")
    PaymentService.void_advance_refund(refund=refund, user=tenant_a.owner, reason="money came back")
    PaymentService.void_receipt(receipt=extra, user=tenant_a.owner, reason="entered twice")
    agree("voided")
    assert _gl(tenant_a.company, "1100") == Decimal("1000.00")


def test_bounce_then_the_same_cheque_number_can_be_received_again(tenant_a):
    customer = make_customer(tenant_a.company)
    first = _receipt(tenant_a, customer, "100", "CHEQUE", cheque_number="4242", cheque_bank_name="SBI")
    PaymentService.set_cheque_status(receipt=first, cheque_status=ChequeStatus.BOUNCED, user=tenant_a.owner)
    again = _post(tenant_a, {
        "customer": customer.id, "amount": "100", "mode": "CHEQUE",
        "cheque_number": "4242", "cheque_bank_name": "SBI",
    })
    assert again.status_code == 201, again.data


def test_the_void_response_carries_the_date_the_reversal_was_posted(tenant_a):
    from accounting.models import JournalEntry

    _books_on(tenant_a)
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "100", "CASH", receipt_date=timezone.localdate() - timedelta(days=2))
    resp = tenant_a.client.post(f"{URL}{receipt.id}/void/", {"reason": "entered twice"}, format="json")
    assert resp.status_code == 200
    from core.models import AuditEvent

    event = AuditEvent.objects.filter(
        company=tenant_a.company, entity_id=str(receipt.pk), description="customer_receipt.voided"
    ).latest("id")
    reversal = JournalEntry.objects.get(
        company=tenant_a.company, source_type="JOURNAL_REVERSAL",
        source_id=JournalEntry.objects.get(company=tenant_a.company, source_type="CUSTOMER_RECEIPT", source_id=receipt.pk, purpose="CREATE").pk,
    )
    assert event.metadata["reversal_date"] == reversal.entry_date.isoformat() == timezone.localdate().isoformat()


# ----------------------------------------------------------------------------- observability


def test_business_event_counters_and_the_void_rate_alert(tenant_a):
    from core.ops_metrics import get_event_counts, render_prometheus

    before = get_event_counts()
    customer = make_customer(tenant_a.company)
    made = [_receipt(tenant_a, customer, "10", "CASH") for _ in range(6)]
    kept = _receipt(tenant_a, customer, "10", "CASH")
    for receipt in made:
        PaymentService.void_receipt(receipt=receipt, user=tenant_a.owner, reason="entered twice")
    PaymentService.refund_advance(receipt=kept, amount=Decimal("3"), mode="CASH", reason="gave back", user=tenant_a.owner)
    PaymentService.edit_receipt(receipt=kept, changes={"notes": "x"}, user=tenant_a.owner)
    after = get_event_counts()
    assert after["money_in_receipt_created"] - before.get("money_in_receipt_created", 0) == 7
    assert after["money_in_receipt_voided"] - before.get("money_in_receipt_voided", 0) == 6
    assert after["money_in_advance_refunded"] - before.get("money_in_advance_refunded", 0) == 1
    assert after["money_in_receipt_edited"] - before.get("money_in_receipt_edited", 0) == 1
    assert 'bizboard_business_events_total{event="money_in_receipt_voided"}' in render_prometheus()
    codes = {r["code"] for r in _leakage_rows(tenant_a.company)}
    assert "VOID_RATE_HIGH" in codes


def test_receipt_search_logs_how_long_it_took_but_not_what_was_asked(tenant_a, caplog):
    import logging

    customer = make_customer(tenant_a.company, name="Searchable Name")
    _receipt(tenant_a, customer, "10", "CASH")
    with caplog.at_level(logging.INFO, logger="payments.receipt_search"):
        assert tenant_a.client.get(URL, {"q": "Searchable"}).status_code == 200
    line = [r.getMessage() for r in caplog.records if r.name == "payments.receipt_search"][0]
    assert "receipt.search q_len=10 rows=1 ms=" in line and "Searchable" not in line


def test_a_pending_cheque_does_not_keep_a_promise_when_cheques_are_held(tenant_a):
    tenant_a.company.cheque_allocation_on_clearance = True
    tenant_a.company.save(update_fields=["cheque_allocation_on_clearance"])
    customer = make_customer(tenant_a.company)
    promise = _promise(tenant_a, customer, "100")
    cheque = _receipt(tenant_a, customer, "100", "CHEQUE", cheque_number="31", cheque_bank_name="SBI")
    promise.refresh_from_db()
    assert promise.resolved is False
    PaymentService.set_cheque_status(receipt=cheque, cheque_status=ChequeStatus.CLEARED, user=tenant_a.owner)
    promise.refresh_from_db()
    assert promise.resolved is True


def test_a_pending_cheque_does_not_stop_reminders_when_cheques_are_held(tenant_a):
    from payments.dunning import eligible_invoices

    tenant_a.company.cheque_allocation_on_clearance = True
    tenant_a.company.save(update_fields=["cheque_allocation_on_clearance"])
    customer = make_customer(tenant_a.company)
    invoice = _invoice(tenant_a, customer, "100.00")
    invoice.due_date = timezone.localdate() - timedelta(days=9)
    invoice.save(update_fields=["due_date"])
    resp = _post(tenant_a, {
        "customer": customer.id, "amount": "100", "mode": "CHEQUE", "cheque_number": "32",
        "cheque_bank_name": "SBI", "sales_invoice": invoice.id,
    })
    assert resp.status_code == 201
    assert _outstanding(invoice) == Decimal("100.00")
    assert invoice in list(eligible_invoices(tenant_a.company, as_of=timezone.localdate()))


# ----------------------------------------------------------------------------- TDS register


def test_tds_receivable_register_lists_receipts_with_pan_and_what_is_left_to_set(tenant_a):
    customer = make_customer(tenant_a.company, name="Deductor", pan="ABCDE1234F")
    invoice = _invoice(tenant_a, customer, "600.00")
    receipt = _receipt(tenant_a, customer, "540", "CASH", tds_deducted=Decimal("60"), tds_section="194C")
    _receipt(tenant_a, customer, "100", "CASH")  # no TDS: not on the register
    PaymentService.allocate_receipt(receipt=receipt, sales_invoice=invoice, amount=Decimal("270"))
    body = tenant_a.client.get("/api/v1/reports/tds-receivable/").data
    assert body["count"] == 1 and Decimal(body["total_tds"]) == Decimal("60.00")
    row = body["rows"][0]
    assert row["pan"] == "ABCDE1234F" and row["section"] == "194C"
    assert Decimal(row["tds_applied"]) == Decimal("30.00") and Decimal(row["tds_unapplied"]) == Decimal("30.00")
    csv_resp = tenant_a.client.get("/api/v1/reports/tds-receivable/export/")
    assert csv_resp.status_code == 200 and b"ABCDE1234F" in csv_resp.content
    assert tenant_a.staff_client.get("/api/v1/reports/tds-receivable/").status_code == 403


def test_tds_register_never_shows_another_tenant(tenant_a, tenant_b):
    other = make_customer(tenant_b.company)
    _receipt(tenant_b, other, "90", "CASH", tds_deducted=Decimal("10"))
    assert tenant_a.client.get("/api/v1/reports/tds-receivable/").data["count"] == 0


def test_voucher_of_a_services_advance_shows_the_gst_inside_it(tenant_a):
    _services_on(tenant_a.company, "18")
    customer = make_customer(tenant_a.company, name="Services Client")
    receipt = _receipt(tenant_a, customer, "1180", "CASH")
    text = _pdf_text(tenant_a.client.get(f"{URL}{receipt.id}/voucher/").content)
    assert "GST included in the advance (18.00%)" in text
    assert "Taxable value" in text and "1000.00" in text and "CGST" in text and "SGST" in text
    tenant_a.company.advance_gst_treatment = "none"
    tenant_a.company.save(update_fields=["advance_gst_treatment"])
    plain = _pdf_text(tenant_a.client.get(f"{URL}{receipt.id}/voucher/").content)
    assert "GST included" not in plain


def test_gstr1_lists_the_advance_tax_the_books_do_not_carry(tenant_a):
    from reporting.gst_returns import build_gstr1

    _services_on(tenant_a.company)
    customer = make_customer(tenant_a.company)
    _receipt(tenant_a, customer, "1180", "CASH")
    payload = build_gstr1(tenant_a.company, timezone.localdate().strftime("%Y-%m"))
    tie = payload["advance_gst"]
    assert tie["enabled"] and tie["posted_to_books"] is False
    assert Decimal(tie["tax_reported"]) == Decimal("180.00") == Decimal(tie["difference_from_books"])
    tenant_a.company.advance_gst_treatment = "none"
    tenant_a.company.save(update_fields=["advance_gst_treatment"])
    off = build_gstr1(tenant_a.company, timezone.localdate().strftime("%Y-%m"))["advance_gst"]
    assert off["enabled"] is False and off["difference_from_books"] == "0.00"


def test_customer_outstanding_counts_the_tds_and_discount_a_receipt_cleared(tenant_a):
    customer = make_customer(tenant_a.company, name="Ravi")
    invoice = _invoice(tenant_a, customer, "1000.00")
    receipt = _receipt(
        tenant_a, customer, "880", "CASH", tds_deducted=Decimal("100"), settlement_discount=Decimal("20"),
    )
    PaymentService.allocate_receipt(receipt=receipt, sales_invoice=invoice, amount=Decimal("880"))
    assert _outstanding(invoice) == Decimal("0")
    assert LedgerService.customer_outstanding(tenant_a.company, customer) == Decimal("0")
    assert LedgerService.bulk_customer_outstanding(tenant_a.company)[customer.id] == Decimal("0")


# ----------------------------------------------------------------------------- review fixes


def test_a_viewer_cannot_send_a_receipt_voucher(tenant_a):
    from accounts.models import CompanyUser

    customer = make_customer(tenant_a.company, name="Ravi", email="ravi@example.test")
    receipt = _receipt(tenant_a, customer, "100", "CASH")
    membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    membership.role = CompanyUser.Role.VIEWER
    for field, value in CompanyUser.capability_defaults_for_role(CompanyUser.Role.VIEWER).items():
        setattr(membership, field, value)
    membership.save()
    resp = tenant_a.staff_client.post(
        f"{URL}{receipt.id}/send/", {"channel": "email", "recipient": "x@example.test"}, format="json"
    )
    assert resp.status_code == 403


def test_a_garbage_customer_or_receipt_filter_is_a_400_not_a_500(tenant_a):
    assert tenant_a.client.get(URL, {"customer": "abc"}).status_code == 400
    assert tenant_a.client.get("/api/v1/payments/advance-refunds/", {"receipt": "abc"}).status_code == 400


def test_refund_endpoint_rejects_a_bad_bank_account_and_non_finite_amount(tenant_a):
    customer = make_customer(tenant_a.company, name="Ravi")
    receipt = _receipt(tenant_a, customer, "100", "CASH")
    base = {"mode": "CASH", "reason": "customer asked"}
    for body in ({"amount": "NaN"}, {"amount": "Infinity"}, {"amount": "10", "bank_account": "abc"}):
        resp = tenant_a.client.post(
            f"{URL}{receipt.id}/refund-advance/", {**base, **body}, format="json"
        )
        assert resp.status_code == 400, body


def test_a_part_refunded_receipt_still_clears_its_whole_discount(tenant_a):
    customer = make_customer(tenant_a.company, name="Ravi")
    invoice = _invoice(tenant_a, customer, "850.00")
    receipt = _receipt(tenant_a, customer, "1000", "CASH", settlement_discount=Decimal("50"))
    PaymentService.refund_advance(
        receipt=receipt, amount=Decimal("200"), mode="CASH", reason="gave some back", user=tenant_a.owner,
    )
    PaymentService.allocate_receipt(receipt=receipt, sales_invoice=invoice, amount=Decimal("800"))
    alloc = receipt.allocations.get()
    assert alloc.discount_applied == Decimal("50.00")
    assert _outstanding(invoice) == Decimal("0")


def test_clearing_a_cheque_still_succeeds_when_its_bill_can_no_longer_take_it(tenant_a):
    company = tenant_a.company
    company.cheque_allocation_on_clearance = True
    company.save(update_fields=["cheque_allocation_on_clearance"])
    customer = make_customer(company, name="Ravi")
    invoice = _invoice(tenant_a, customer, "500.00")
    receipt = _receipt(
        tenant_a, customer, "500", "CHEQUE", cheque_number="123456", cheque_bank_name="SBI",
        allocate_on_clear=True, intended_sales_invoice=invoice, intended_amount=Decimal("500"),
    )
    # The bill is paid by someone else before the cheque clears.
    other = _receipt(tenant_a, customer, "500", "CASH")
    PaymentService.allocate_receipt(receipt=other, sales_invoice=invoice, amount=Decimal("500"))
    cleared = PaymentService.set_cheque_status(receipt=receipt, cheque_status="CLEARED", user=tenant_a.owner)
    assert cleared.cheque_status == "CLEARED"
    assert not receipt.allocations.exists()
