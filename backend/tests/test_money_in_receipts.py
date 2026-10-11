"""Money In (customer receipts): list filters, summary, export, voucher, void audit, walk-in rule."""

import csv
import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.models import AuditEvent
from payments.models import CustomerReceipt, PaymentAllocation, ReceiptStatus
from payments.services import PaymentService
from sales.models import SalesInvoice
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    make_customer,
    make_product,
)

pytestmark = pytest.mark.django_db

URL = "/api/v1/payments/receipts/"


def _receipt(tenant, customer, amount="100", mode="CASH", on=None, **kw):
    return PaymentService.create_receipt(
        company=tenant.company,
        customer=customer,
        amount=Decimal(amount),
        mode=mode,
        receipt_date=on,
        user=tenant.owner,
        **kw,
    )


def _open_invoice(tenant, customer, price="100.00", sku="MI-1"):
    product = make_product(tenant.company, sku=sku, gst_rate="0")
    add_stock(tenant, product, "50")
    draft = create_draft_invoice(
        tenant,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": price, "gst_rate": "0"}],
    )
    assert tenant.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200
    return SalesInvoice.objects.get(pk=draft["id"])


def _results(resp):
    assert resp.status_code == 200, resp.data
    data = resp.data
    return data["results"] if isinstance(data, dict) and "results" in data else data


# ----------------------------------------------------------------------------- filters


def test_list_filters_by_mode_status_dates_and_query(tenant_a):
    ravi = make_customer(tenant_a.company, name="Ravi Traders", phone="9876501234")
    anil = make_customer(tenant_a.company, name="Anil Stores", phone="9123400000")
    old = _receipt(tenant_a, ravi, "10", "CASH", on=date(2026, 1, 5))
    upi = _receipt(tenant_a, anil, "20", "UPI", on=date(2026, 2, 5), utr="UTR998877")
    cash = _receipt(tenant_a, anil, "30", "CASH", on=date(2026, 3, 5), reference="REFABC")
    PaymentService.void_receipt(receipt=cash, user=tenant_a.owner, reason="entered twice")

    def ids(**params):
        return {row["id"] for row in _results(tenant_a.client.get(URL, params))}

    assert ids() == {old.id, upi.id, cash.id}
    assert ids(mode="upi") == {upi.id}
    assert ids(status="voided") == {cash.id}
    assert ids(status="POSTED") == {old.id, upi.id}
    assert ids(date_from="2026-02-01") == {upi.id, cash.id}
    assert ids(date_to="2026-02-28") == {old.id, upi.id}
    assert ids(date_from="2026-02-01", date_to="2026-02-28") == {upi.id}
    assert ids(q="Ravi") == {old.id}
    assert ids(q=old.number) == {old.id}
    assert ids(q="UTR9988") == {upi.id}  # UTR is a prefix match
    assert ids(q="REFA") == {cash.id}
    assert ids(q="98765") == {old.id}  # digits search the phone
    assert ids(q="Anil", mode="CASH") == {cash.id}
    assert ids(customer=anil.id) == {upi.id, cash.id}


def test_search_still_finds_receipts_of_a_deleted_customer(tenant_a):
    gone = make_customer(tenant_a.company, name="Closed Down Traders")
    receipt = _receipt(tenant_a, gone, "10")
    gone.is_deleted = True
    gone.save(update_fields=["is_deleted"])
    rows = _results(tenant_a.client.get(URL, {"q": "Closed Down"}))
    assert [row["id"] for row in rows] == [receipt.id]


@pytest.mark.postgres
def test_search_trigram_indexes_exist_on_postgres():
    from django.db import connection

    if connection.vendor != "postgresql":
        pytest.skip("Trigram indexes exist on PostgreSQL only")
    with connection.cursor() as cursor:
        cursor.execute("select indexname from pg_indexes where indexname like '%upper_trgm'")
        names = {row[0] for row in cursor.fetchall()}
    assert names >= {
        "receipt_number_upper_trgm", "receipt_utr_upper_trgm", "receipt_reference_upper_trgm",
        "customer_name_upper_trgm", "customer_phone_upper_trgm",
    }


@pytest.mark.parametrize(
    "params",
    [
        {"date_from": "not-a-date"},
        {"date_to": "2026-13-45"},
        {"date_from": "2026-05-02", "date_to": "2026-05-01"},
        {"mode": "BARTER"},
        {"status": "PENDING"},
    ],
)
def test_invalid_filter_values_are_a_400_not_a_500(tenant_a, params):
    resp = tenant_a.client.get(URL, params)
    assert resp.status_code == 400, resp.data


def test_search_text_is_capped_and_does_not_error(tenant_a):
    make_customer(tenant_a.company)
    assert tenant_a.client.get(URL, {"q": "x" * 5000}).status_code == 200


def test_filters_never_leak_another_tenants_receipts(tenant_a, tenant_b):
    mine = make_customer(tenant_a.company, name="Shared Name")
    theirs = make_customer(tenant_b.company, name="Shared Name")
    _receipt(tenant_a, mine, "10", on=date(2026, 4, 1))
    other = _receipt(tenant_b, theirs, "99", on=date(2026, 4, 1))
    rows = _results(tenant_a.client.get(URL, {"q": "Shared"}))
    assert other.id not in {row["id"] for row in rows}
    assert len(rows) == 1
    assert tenant_a.client.get(f"{URL}summary/", {"q": "Shared"}).data["collected"] == Decimal("10.00")
    assert tenant_a.client.get(f"{URL}{other.id}/voucher/").status_code == 404


def test_detail_routes_ignore_list_filters(tenant_a):
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "10", "CASH")
    assert tenant_a.client.get(f"{URL}{receipt.id}/", {"mode": "UPI"}).status_code == 200


# ----------------------------------------------------------------------------- summary


def test_summary_covers_every_page_and_excludes_dead_money(tenant_a):
    customer = make_customer(tenant_a.company)
    for _ in range(55):  # more than one 50-row page
        _receipt(tenant_a, customer, "10", "CASH")
    voided = _receipt(tenant_a, customer, "500", "CASH")
    PaymentService.void_receipt(receipt=voided, user=tenant_a.owner, reason="entered twice")
    pending = _receipt(
        tenant_a, customer, "200", "CHEQUE", cheque_number="111111", cheque_bank_name="HDFC",
    )
    bounced = _receipt(
        tenant_a, customer, "300", "CHEQUE", cheque_number="222222", cheque_bank_name="HDFC",
    )
    CustomerReceipt.objects.filter(pk=bounced.pk).update(cheque_status="BOUNCED")

    data = tenant_a.client.get(f"{URL}summary/").data
    assert data["collected"] == Decimal("550.00")  # 55 x 10; voided, bounced and pending cheque out
    assert data["cheques_pending"] == Decimal("200.00")
    assert data["allocated"] == Decimal("0.00")
    assert data["advance"] == Decimal("750.00")  # collected + pending cheque, none applied
    assert data["count"] == 56
    assert data["excluded_count"] == 2
    assert pending.id  # silence unused

    only_cash = tenant_a.client.get(f"{URL}summary/", {"mode": "CHEQUE"}).data
    assert only_cash["collected"] == Decimal("0.00")
    assert only_cash["cheques_pending"] == Decimal("200.00")


def test_summary_counts_live_allocations_only(tenant_a):
    customer = make_customer(tenant_a.company)
    invoice = _open_invoice(tenant_a, customer, "100.00", "MI-SUM")
    receipt = _receipt(tenant_a, customer, "150")
    PaymentService.allocate_receipt(
        receipt=receipt, sales_invoice=invoice, amount=Decimal("100"), user=tenant_a.owner,
    )
    data = tenant_a.client.get(f"{URL}summary/").data
    assert data["allocated"] == Decimal("100.00")
    assert data["advance"] == Decimal("50.00")
    row = PaymentAllocation.objects.get(receipt=receipt)
    PaymentService.reverse_allocation(allocation=row, user=tenant_a.owner)
    data = tenant_a.client.get(f"{URL}summary/").data
    assert data["allocated"] == Decimal("0.00")
    assert data["advance"] == Decimal("150.00")


def test_summary_requires_payment_view_permission(tenant_a):
    # SALES_STAFF can view payment surfaces in this fixture, so assert the unauthenticated gate.
    from rest_framework.test import APIClient

    assert APIClient().get(f"{URL}summary/").status_code in (401, 403)


# ----------------------------------------------------------------------------- void


def test_void_requires_a_reason_on_the_server(tenant_a):
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer)
    for body in ({}, {"reason": ""}, {"reason": "   "}, {"reason": "ab"}):
        resp = tenant_a.client.post(f"{URL}{receipt.id}/void/", body, format="json")
        assert resp.status_code == 400, body
    receipt.refresh_from_db()
    assert receipt.status == ReceiptStatus.POSTED
    resp = tenant_a.client.post(f"{URL}{receipt.id}/void/", {"reason": "x" * 501}, format="json")
    assert resp.status_code == 400


def test_void_stores_structured_audit_fields_and_event(tenant_a):
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, notes="walk-in cash")
    resp = tenant_a.client.post(
        f"{URL}{receipt.id}/void/", {"reason": "  duplicate   entry "}, format="json",
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["status"] == "VOIDED"
    assert resp.data["void_reason"] == "duplicate entry"
    assert resp.data["voided_by_name"]
    receipt.refresh_from_db()
    assert receipt.void_reason == "duplicate entry"
    assert receipt.voided_by_id == tenant_a.owner.id
    assert receipt.voided_at is not None
    assert receipt.notes == "walk-in cash"  # free-text notes are left alone
    event = AuditEvent.objects.filter(
        company=tenant_a.company, entity_type="CustomerReceipt", entity_id=str(receipt.pk),
        description="customer_receipt.voided",
    ).get()
    assert event.metadata["reason"] == "duplicate entry"
    assert event.metadata["reversal_date"] == timezone.localdate().isoformat()


def test_void_is_idempotent_and_keeps_first_reason(tenant_a):
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer)
    first = PaymentService.void_receipt(receipt=receipt, user=tenant_a.owner, reason="first reason")
    again = PaymentService.void_receipt(receipt=receipt, user=tenant_a.owner, reason="")
    assert again.void_reason == first.void_reason == "first reason"


def test_void_needs_cancel_permission(tenant_a):
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer)
    resp = tenant_a.staff_client.post(f"{URL}{receipt.id}/void/", {"reason": "mistake"}, format="json")
    assert resp.status_code == 403
    receipt.refresh_from_db()
    assert receipt.status == ReceiptStatus.POSTED


def test_void_blocked_when_matched_to_a_bank_line(tenant_a):
    from banking.models import AaConsent, AaTransaction

    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "40", "UPI", utr="UTRMATCH1")
    consent = AaConsent.objects.create(company=tenant_a.company, consent_id="c-1")
    AaTransaction.objects.create(
        company=tenant_a.company, consent=consent, txn_id="t-1", amount=Decimal("40"),
        matched_payment=receipt,
    )
    resp = tenant_a.client.post(f"{URL}{receipt.id}/void/", {"reason": "mistake"}, format="json")
    assert resp.status_code == 400
    assert "bank" in str(resp.data).lower()
    receipt.refresh_from_db()
    assert receipt.status == ReceiptStatus.POSTED


def test_a_reconciled_cheque_can_still_be_bounced(tenant_a):
    """The bank takes the money back, so the bounce must work even though the receipt is matched."""
    from banking.models import AaConsent, AaTransaction

    customer = make_customer(tenant_a.company)
    receipt = _receipt(
        tenant_a, customer, "40", "CHEQUE", cheque_number="445566", cheque_bank_name="HDFC",
    )
    consent = AaConsent.objects.create(company=tenant_a.company, consent_id="c-bounce")
    AaTransaction.objects.create(
        company=tenant_a.company, consent=consent, txn_id="t-bounce", amount=Decimal("40"),
        matched_payment=receipt,
    )
    resp = tenant_a.client.post(
        f"{URL}{receipt.id}/set-cheque-status/", {"cheque_status": "BOUNCED"}, format="json",
    )
    assert resp.status_code == 200, resp.data
    receipt.refresh_from_db()
    assert receipt.status == ReceiptStatus.VOIDED
    assert receipt.cheque_status == "BOUNCED"
    assert receipt.void_reason == "Cheque bounced"


def test_void_blocked_when_counted_in_a_closed_till(tenant_a):
    from accounting.models import CashShiftRegister

    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "40", "CASH")
    shift = CashShiftRegister.objects.create(
        company=tenant_a.company, cashier=tenant_a.owner, business_date=timezone.localdate(),
        status=CashShiftRegister.Status.CLOSED,
    )
    CustomerReceipt.objects.filter(pk=receipt.pk).update(shift=shift, paid_from_till=True)
    resp = tenant_a.client.post(f"{URL}{receipt.id}/void/", {"reason": "mistake"}, format="json")
    assert resp.status_code == 400
    assert "till" in str(resp.data).lower()


def test_void_restores_invoice_after_a_settlement_discount(tenant_a):
    customer = make_customer(tenant_a.company)
    invoice = _open_invoice(tenant_a, customer, "100.00", "MI-DISC")
    receipt = _receipt(tenant_a, customer, "95", settlement_discount=Decimal("5"))
    PaymentService.allocate_receipt(
        receipt=receipt, sales_invoice=invoice, amount=Decimal("95"), user=tenant_a.owner,
    )
    from ledgers.services import LedgerService

    invoice.refresh_from_db()
    assert LedgerService.sales_invoice_outstanding(invoice) == Decimal("0.00")
    resp = tenant_a.client.post(f"{URL}{receipt.id}/void/", {"reason": "wrong customer"}, format="json")
    assert resp.status_code == 200, resp.data
    invoice.refresh_from_db()
    assert LedgerService.sales_invoice_outstanding(invoice) == Decimal("100.00")


def test_void_of_a_partly_reallocated_receipt_reverses_every_live_allocation(tenant_a):
    customer = make_customer(tenant_a.company)
    first = _open_invoice(tenant_a, customer, "60.00", "MI-RE1")
    second = _open_invoice(tenant_a, customer, "70.00", "MI-RE2")
    receipt = _receipt(tenant_a, customer, "100")
    a = PaymentService.allocate_receipt(
        receipt=receipt, sales_invoice=first, amount=Decimal("60"), user=tenant_a.owner,
    )
    PaymentService.allocate_receipt(
        receipt=receipt, sales_invoice=second, amount=Decimal("40"), user=tenant_a.owner,
    )
    PaymentService.reverse_allocation(allocation=a, user=tenant_a.owner)
    assert tenant_a.client.post(f"{URL}{receipt.id}/void/", {"reason": "mistake"}, format="json").status_code == 200
    assert not PaymentAllocation.objects.filter(receipt=receipt, reversed_at__isnull=True).exists()


# ----------------------------------------------------------------------------- create / walk-in


def test_create_can_apply_to_one_invoice_atomically(tenant_a):
    customer = make_customer(tenant_a.company)
    invoice = _open_invoice(tenant_a, customer, "100.00", "MI-AT")
    resp = tenant_a.client.post(
        URL,
        {"customer": customer.id, "amount": "100", "mode": "CASH",
         "sales_invoice": invoice.id, "allocate_amount": "100"},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert Decimal(str(resp.data["allocated"])) == Decimal("100.00")
    assert resp.data["allocation_lines"][0]["sales_invoice"] == invoice.id


def test_create_rejects_a_future_receipt_date_but_allows_today_and_the_past(tenant_a):
    customer = make_customer(tenant_a.company)
    tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
    resp = tenant_a.client.post(
        URL, {"customer": customer.id, "amount": "10", "mode": "CASH", "receipt_date": tomorrow}, format="json",
    )
    assert resp.status_code == 400, resp.data
    assert "future" in str(resp.data).lower()
    assert CustomerReceipt.objects.filter(customer=customer).count() == 0
    for day in (timezone.localdate(), timezone.localdate() - timedelta(days=40)):
        ok = tenant_a.client.post(
            URL, {"customer": customer.id, "amount": "10", "mode": "CASH", "receipt_date": day.isoformat()},
            format="json",
        )
        assert ok.status_code == 201, ok.data


def test_failed_atomic_allocation_leaves_no_receipt_behind(tenant_a):
    customer = make_customer(tenant_a.company)
    invoice = _open_invoice(tenant_a, customer, "50.00", "MI-RB")
    before = CustomerReceipt.objects.count()
    resp = tenant_a.client.post(
        URL,
        {"customer": customer.id, "amount": "100", "mode": "CASH",
         "sales_invoice": invoice.id, "allocate_amount": "100"},
        format="json",
    )
    assert resp.status_code == 400, resp.data  # exceeds the invoice's open balance
    assert CustomerReceipt.objects.count() == before


def test_create_rejects_bad_invoice_inputs(tenant_a, tenant_b):
    customer = make_customer(tenant_a.company)
    theirs = _open_invoice(tenant_b, make_customer(tenant_b.company), "10.00", "MI-X")
    for extra in (
        {"sales_invoice": theirs.id},  # another tenant's invoice
        {"sales_invoice": "abc"},
    ):
        resp = tenant_a.client.post(
            URL, {"customer": customer.id, "amount": "10", "mode": "CASH", **extra}, format="json",
        )
        assert resp.status_code == 400, extra
    invoice = _open_invoice(tenant_a, customer, "10.00", "MI-Y")
    resp = tenant_a.client.post(
        URL,
        {"customer": customer.id, "amount": "10", "mode": "CASH", "sales_invoice": invoice.id,
         "allocate_oldest": True},
        format="json",
    )
    assert resp.status_code == 400
    resp = tenant_a.client.post(
        URL,
        {"customer": customer.id, "amount": "10", "mode": "CASH", "sales_invoice": invoice.id,
         "allocate_amount": "20"},
        format="json",
    )
    assert resp.status_code == 400
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0


def _walk_in(tenant, name="Counter Sale"):
    return make_customer(tenant.company, name=name, is_pos_walk_in=True)


def test_walk_in_receipt_without_allocation_is_refused_by_the_api(tenant_a):
    walk_in = _walk_in(tenant_a)
    resp = tenant_a.client.post(
        URL, {"customer": walk_in.id, "amount": "100", "mode": "CASH"}, format="json",
    )
    assert resp.status_code == 400, resp.data
    assert "walk-in" in str(resp.data).lower()
    assert CustomerReceipt.objects.filter(customer=walk_in).count() == 0


def test_walk_in_rule_does_not_depend_on_the_customer_name(tenant_a):
    renamed = _walk_in(tenant_a, name="Kaunter Bikri")
    resp = tenant_a.client.post(
        URL, {"customer": renamed.id, "amount": "10", "mode": "CASH"}, format="json",
    )
    assert resp.status_code == 400
    # ...and a named customer who merely has "walk-in" in the name is not caught.
    named = make_customer(tenant_a.company, name="Walk-in Wholesale Ltd")
    ok = tenant_a.client.post(
        URL, {"customer": named.id, "amount": "10", "mode": "CASH"}, format="json",
    )
    assert ok.status_code == 201, ok.data


def test_walk_in_partial_allocation_is_refused_and_full_is_accepted(tenant_a):
    walk_in = _walk_in(tenant_a)
    invoice = _open_invoice(tenant_a, walk_in, "100.00", "MI-WI")
    partial = tenant_a.client.post(
        URL,
        {"customer": walk_in.id, "amount": "100", "mode": "CASH",
         "sales_invoice": invoice.id, "allocate_amount": "60"},
        format="json",
    )
    assert partial.status_code == 400, partial.data
    assert CustomerReceipt.objects.filter(customer=walk_in).count() == 0
    full = tenant_a.client.post(
        URL,
        {"customer": walk_in.id, "amount": "100", "mode": "CASH",
         "sales_invoice": invoice.id, "allocate_amount": "100"},
        format="json",
    )
    assert full.status_code == 201, full.data
    assert full.data["customer_is_walk_in"] is True


def test_walk_in_oldest_first_must_cover_the_whole_amount(tenant_a):
    walk_in = _walk_in(tenant_a)
    _open_invoice(tenant_a, walk_in, "40.00", "MI-WO")
    short = tenant_a.client.post(
        URL, {"customer": walk_in.id, "amount": "100", "mode": "CASH", "allocate_oldest": True},
        format="json",
    )
    assert short.status_code == 400, short.data
    exact = tenant_a.client.post(
        URL, {"customer": walk_in.id, "amount": "40", "mode": "CASH", "allocate_oldest": True},
        format="json",
    )
    assert exact.status_code == 201, exact.data


def test_named_customer_can_still_hold_an_advance(tenant_a):
    customer = make_customer(tenant_a.company, name="Named Buyer")
    resp = tenant_a.client.post(
        URL, {"customer": customer.id, "amount": "250", "mode": "CASH"}, format="json",
    )
    assert resp.status_code == 201, resp.data
    assert Decimal(str(resp.data["unallocated"])) == Decimal("250.00")


# ----------------------------------------------------------------------------- voucher


def test_voucher_pdf_a4_and_thermal(tenant_a):
    customer = make_customer(tenant_a.company, name="Ravi Traders")
    invoice = _open_invoice(tenant_a, customer, "100.00", "MI-PDF")
    receipt = _receipt(tenant_a, customer, "130", "UPI", utr="UTRPDF1")
    PaymentService.allocate_receipt(
        receipt=receipt, sales_invoice=invoice, amount=Decimal("100"), user=tenant_a.owner,
    )
    for layout in ("", "thermal", "A4"):
        resp = tenant_a.client.get(f"{URL}{receipt.id}/voucher/", {"layout": layout} if layout else {})
        assert resp.status_code == 200, resp.content[:200]
        assert resp["Content-Type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")
        assert "receipt-" in resp["Content-Disposition"]
    assert tenant_a.client.get(f"{URL}{receipt.id}/voucher/", {"layout": "poster"}).status_code == 400


def test_voucher_for_a_voided_receipt_still_renders(tenant_a):
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "10")
    PaymentService.void_receipt(receipt=receipt, user=tenant_a.owner, reason="entered twice")
    resp = tenant_a.client.get(f"{URL}{receipt.id}/voucher/")
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")


# ----------------------------------------------------------------------------- export


def _csv_rows(resp):
    assert resp.status_code == 200, getattr(resp, "data", None)
    assert resp["Content-Type"].startswith("text/csv")
    # The export is streamed row by row, so read the body from the stream.
    return list(csv.DictReader(io.StringIO(b"".join(resp.streaming_content).decode("utf-8"))))


def test_export_matches_the_filtered_total_not_one_page(tenant_a):
    customer = make_customer(tenant_a.company, name="Export Co")
    for i in range(55):
        _receipt(tenant_a, customer, "10", "CASH", on=date(2026, 5, 1) + timedelta(days=i % 5))
    _receipt(tenant_a, customer, "20", "UPI", on=date(2026, 5, 2), utr="EXPUTR1")
    rows = _csv_rows(tenant_a.client.get(f"{URL}export/"))
    assert len(rows) == 56
    assert len(_csv_rows(tenant_a.client.get(f"{URL}export/", {"mode": "UPI"}))) == 1
    listed = tenant_a.client.get(URL, {"mode": "CASH"}).data["count"]
    assert len(_csv_rows(tenant_a.client.get(f"{URL}export/", {"mode": "CASH"}))) == listed == 55
    assert tenant_a.client.get(f"{URL}export/", {"date_from": "bad"}).status_code == 400


def test_export_neutralises_spreadsheet_formulas_and_shows_void_reason(tenant_a):
    customer = make_customer(tenant_a.company, name="=HYPERLINK(\"http://x\")")
    receipt = _receipt(tenant_a, customer, "10")
    PaymentService.void_receipt(receipt=receipt, user=tenant_a.owner, reason="+SUM(A1) mistake")
    row = _csv_rows(tenant_a.client.get(f"{URL}export/"))[0]
    assert row["Customer"].startswith("'=")
    assert row["Void reason"].startswith("'+")
    assert row["Status"] == "VOIDED"
    assert row["Advance"] == "0"


def test_export_is_capped(tenant_a, monkeypatch):
    import payments.views as views

    monkeypatch.setattr(views, "RECEIPT_EXPORT_MAX_ROWS", 2)
    customer = make_customer(tenant_a.company)
    for _ in range(3):
        _receipt(tenant_a, customer, "10")
    resp = tenant_a.client.get(f"{URL}export/")
    assert resp.status_code == 400
    assert "Narrow" in str(resp.data)


# ----------------------------------------------------------------------------- tie-out


def test_collected_total_ties_to_the_cash_ledger_and_customer_ledger(tenant_a):
    """OW-13: what the list calls collected equals what the books recorded."""
    from django.db.models import Sum

    from accounting.models import JournalEntry, JournalLine
    from accounting.services import seed_chart_of_accounts

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company)
    customer = make_customer(tenant_a.company)
    _receipt(tenant_a, customer, "100", "CASH")
    _receipt(tenant_a, customer, "50", "CASH")
    voided = _receipt(tenant_a, customer, "70", "CASH")
    PaymentService.void_receipt(receipt=voided, user=tenant_a.owner, reason="entered twice")

    summary = tenant_a.client.get(f"{URL}summary/").data
    assert summary["collected"] == Decimal("150.00")

    # Original and reversal entries together: the void nets to nothing on the cash ledger.
    cash = JournalLine.objects.filter(
        entry__company=tenant_a.company,
        entry__status__in=[JournalEntry.Status.POSTED, JournalEntry.Status.REVERSED],
        account__code="1100",
    ).aggregate(d=Sum("debit"), c=Sum("credit"))
    assert (cash["d"] or Decimal("0")) - (cash["c"] or Decimal("0")) == summary["collected"]
    advances = JournalLine.objects.filter(
        entry__company=tenant_a.company,
        entry__status__in=[JournalEntry.Status.POSTED, JournalEntry.Status.REVERSED],
        account__code="2300",
        customer=customer,
    ).aggregate(d=Sum("debit"), c=Sum("credit"))
    assert (advances["c"] or Decimal("0")) - (advances["d"] or Decimal("0")) == summary["collected"]


# ----------------------------------------------------------------------------- Hindi voucher


@pytest.mark.parametrize(
    "value, expected",
    [
        ("0", "शून्य रुपये मात्र"),
        ("1", "एक रुपये मात्र"),
        ("99", "निन्यानवे रुपये मात्र"),
        ("100", "एक सौ रुपये मात्र"),
        ("101.50", "एक सौ एक रुपये और पचास पैसे मात्र"),
        ("1000", "एक हज़ार रुपये मात्र"),
        ("125000", "एक लाख पच्चीस हज़ार रुपये मात्र"),
        ("2345678", "तेईस लाख पैंतालीस हज़ार छह सौ अठहत्तर रुपये मात्र"),
        ("10000000", "एक करोड़ रुपये मात्र"),
    ],
)
def test_hindi_amount_in_words(value, expected):
    from payments.hindi_numbers import amount_in_words_hi

    assert amount_in_words_hi(value) == expected


def test_hindi_number_table_has_a_distinct_word_for_every_number_below_100():
    from payments.hindi_numbers import _UNDER_100

    assert len(_UNDER_100) == 100
    assert len(set(_UNDER_100)) == 100


def _ink(content: bytes) -> float:
    """Share of the first page that is not white, rendered with PDFium."""
    pdfium = pytest.importorskip("pypdfium2")
    page = pdfium.PdfDocument(content)[0]
    image = page.render(scale=0.6).to_pil().convert("L")
    pixels = list(image.tobytes())
    return sum(1 for value in pixels if value < 200) / len(pixels)


def _selectable_text(content: bytes) -> str:
    pypdf = pytest.importorskip("pypdf")
    reader = pypdf.PdfReader(io.BytesIO(content))
    return " ".join(page.extract_text() or "" for page in reader.pages).strip()


def test_devanagari_is_shaped_not_laid_out_in_logical_order():
    """The i-matra is typed after its consonant but must be drawn before it; conjuncts must join."""
    pytest.importorskip("uharfbuzz")
    from payments.receipt_voucher import _HI_FONT_PATH
    from payments.shaped_text import load_font

    font = load_font(str(_HI_FONT_PATH), 400)
    ka = font._font.get_nominal_glyph(ord("क"))
    shaped = [gid for gid, *_ in font.shape("कि")]
    # Logical order is ka, i-matra. Drawn order puts the vowel sign (a contextual glyph) first.
    assert len(shaped) == 2 and shaped[0] != ka and shaped[1] == ka
    assert len(font.shape("क्ष")) < 3  # ka + virama + ssa joins into one conjunct
    assert font.width("किया", 10) > 0
    assert load_font(str(_HI_FONT_PATH), 700).width("किया", 10) != font.width(
        "किया", 10
    )  # a real bold weight, not a smeared regular


def test_voucher_in_hindi_renders_on_both_layouts(tenant_a):
    customer = make_customer(tenant_a.company, name="रवि ट्रेडर्स")
    receipt = _receipt(tenant_a, customer, "125000", "CASH")
    for layout in ("A4", "THERMAL"):
        resp = tenant_a.client.get(f"{URL}{receipt.id}/voucher/", {"layout": layout, "lang": "hi"})
        assert resp.status_code == 200, resp.content[:200]
        assert resp.content.startswith(b"%PDF")
        assert _ink(resp.content) > 0.01  # drawn, not blank
    english = tenant_a.client.get(f"{URL}{receipt.id}/voucher/").content
    hindi = tenant_a.client.get(f"{URL}{receipt.id}/voucher/", {"lang": "hi"}).content
    assert english != hindi
    # English is selectable text. Hindi is drawn as shaped outlines, each run tagged with its real
    # Unicode text, so it can still be selected, searched and read aloud.
    assert "RECEIPT VOUCHER" in _selectable_text(english)
    assert "रसीद वाउचर" in _selectable_text(hindi)


def test_voucher_falls_back_to_english_when_hindi_cannot_be_drawn(tenant_a, monkeypatch):
    import payments.receipt_voucher as voucher

    monkeypatch.setattr(voucher, "_hi_font_ok", False)

    def boom(*args, **kwargs):
        raise AssertionError("the shaper must not be used on the fallback path")

    monkeypatch.setattr(voucher, "load_font", boom)
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "10")
    resp = tenant_a.client.get(f"{URL}{receipt.id}/voucher/", {"lang": "hi"})
    assert resp.status_code == 200
    assert "RECEIPT VOUCHER" in _selectable_text(resp.content)


def test_voucher_rejects_an_unknown_language(tenant_a):
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "10")
    assert tenant_a.client.get(f"{URL}{receipt.id}/voucher/", {"lang": "ta"}).status_code == 400


def test_hindi_voucher_of_a_voided_receipt_is_stamped(tenant_a):
    customer = make_customer(tenant_a.company, name="Ravi")
    live = _receipt(tenant_a, customer, "10")
    gone = _receipt(tenant_a, customer, "10")
    PaymentService.void_receipt(receipt=gone, user=tenant_a.owner, reason="गलत ग्राहक")
    live_ink = _ink(tenant_a.client.get(f"{URL}{live.id}/voucher/", {"lang": "hi"}).content)
    gone_ink = _ink(tenant_a.client.get(f"{URL}{gone.id}/voucher/", {"lang": "hi"}).content)
    assert gone_ink > live_ink  # the VOIDED stamp and the reason add ink


# ----------------------------------------------------------------------------- bank line receipts


def _bank_line(tenant, amount="500.00"):
    from payments.models import BankAccount, BankStatement, BankStatementLine

    bank = BankAccount.objects.create(company=tenant.company, name="Main")
    statement = BankStatement.objects.create(company=tenant.company, bank_account=bank)
    return BankStatementLine.objects.create(
        company=tenant.company, statement=statement, txn_date=timezone.localdate(),
        amount=Decimal(amount), narration="NEFT", utr="UTRBANKLINE1",
    )


def test_bank_line_receipt_refuses_a_walk_in_customer_and_accepts_a_named_one(tenant_a):
    line = _bank_line(tenant_a)
    walk_in = _walk_in(tenant_a)
    path = "/api/v1/payments/recon/create-receipt-from-line/"
    refused = tenant_a.client.post(path, {"line": line.id, "customer": walk_in.id}, format="json")
    assert refused.status_code == 400, refused.data
    assert "walk-in" in str(refused.data).lower()
    assert not CustomerReceipt.objects.filter(customer=walk_in).exists()
    line.refresh_from_db()
    assert line.match_status != "MATCHED"

    named = make_customer(tenant_a.company, name="Real Payer")
    ok = tenant_a.client.post(path, {"line": line.id, "customer": named.id}, format="json")
    assert ok.status_code == 201, ok.data
