"""Sales history register: one settlement bucket, due sort, and zip skips."""

from decimal import Decimal

import pytest

from sales.settlement import settlement_bucket
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def test_settlement_bucket_matches_the_due_column():
    assert settlement_bucket("DRAFT", "100", "100", 0, 0, 0) == "NONE"
    assert settlement_bucket("COMPLETED", "100", "100", 0, 0, 0) == "UNPAID"
    assert settlement_bucket("COMPLETED", "100", "40", "60", 0, 0) == "PARTIAL"
    assert settlement_bucket("COMPLETED", "100", "40", 0, "60", 0) == "PARTIAL"
    assert settlement_bucket("COMPLETED", "100", "80", 0, 0, "20") == "PARTIAL"
    assert settlement_bucket("COMPLETED", "100", "100", 0, 0, 0) == "UNPAID"
    assert settlement_bucket("COMPLETED", "100", "0", "100", 0, 0) == "PAID"
    assert settlement_bucket("RETURNED", "100", "0", 0, "100", 0) == "PAID"


def _completed(tenant, sku, price="100"):
    customer = make_customer(tenant.company)
    product = make_product(tenant.company, sku=sku)
    add_stock(tenant, product, "5")
    draft = create_draft_invoice(
        tenant, customer, [{"product": product.id, "quantity": "1", "unit_price": price}]
    )
    completed = tenant.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert completed.status_code == 200, completed.data
    return completed.data


def test_list_settlement_state_follows_the_payment_filter(tenant_a):
    invoice = _completed(tenant_a, "SH-UNPAID")
    listed = tenant_a.client.get("/api/v1/sales/invoices/", {"payment_status": "UNPAID"})
    assert listed.status_code == 200, listed.data
    row = next(item for item in listed.data["results"] if item["id"] == invoice["id"])
    assert row["settlement_state"] == "UNPAID"
    assert Decimal(str(row["balance"])) > 0

    paid = tenant_a.client.get("/api/v1/sales/invoices/", {"payment_status": "PAID"})
    assert all(item["id"] != invoice["id"] for item in paid.data["results"])

    stats = tenant_a.client.get("/api/v1/sales/invoices/payment-stats/", {"payment_status": "PAID"})
    assert stats.status_code == 200, stats.data
    assert int(stats.data["unpaid"]["count"]) >= 1


def test_due_sort_puts_drafts_after_open_balances(tenant_a):
    open_invoice = _completed(tenant_a, "SH-DUE")
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="SH-DRAFT")
    draft = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "10"}]
    )
    listed = tenant_a.client.get("/api/v1/sales/invoices/", {"sort": "due_desc"})
    assert listed.status_code == 200, listed.data
    ids = [item["id"] for item in listed.data["results"]]
    assert ids.index(open_invoice["id"]) < ids.index(draft["id"])
    unknown = tenant_a.client.get("/api/v1/sales/invoices/", {"sort": "nope"})
    assert unknown.status_code == 400
    # List-only parameters do not break the detail page.
    detail = tenant_a.client.get(f"/api/v1/sales/invoices/{open_invoice['id']}/", {"sort": "nope"})
    assert detail.status_code == 200, detail.data


def test_bulk_zip_names_are_flat_and_only_the_builder_downloads(tenant_a, tenant_b):
    import io
    import zipfile

    from core.models import FileAsset
    from sales.models import SalesInvoice

    first = _completed(tenant_a, "SH-ZIP-SLASH-1")
    second = _completed(tenant_a, "SH-ZIP-SLASH-2")
    SalesInvoice.objects.filter(pk=first["id"]).update(number="INV/24-25/001")
    SalesInvoice.objects.filter(pk=second["id"]).update(number="INV-24-25-001")
    zipped = tenant_a.client.post(
        "/api/v1/sales/invoices/bulk-pdf-zip/", {"ids": [first["id"], second["id"]]}, format="json",
    )
    assert zipped.status_code == 200, zipped.data
    file_id = zipped.data["file_id"]

    download = tenant_a.client.get(f"/api/v1/sales/invoices/bulk-pdf-zip/{file_id}/")
    assert download.status_code == 200
    body = b"".join(download.streaming_content)
    names = zipfile.ZipFile(io.BytesIO(body)).namelist()
    assert len(names) == 2
    assert all("/" not in name and "\\" not in name for name in names)
    assert len({name.lower() for name in names}) == 2

    assert tenant_b.client.get(f"/api/v1/sales/invoices/bulk-pdf-zip/{file_id}/").status_code == 404
    FileAsset.objects.filter(pk=file_id).update(created_by=tenant_a.staff)
    assert tenant_a.client.get(f"/api/v1/sales/invoices/bulk-pdf-zip/{file_id}/").status_code == 404


def test_missing_licence_confirm_can_retry_on_the_same_key():
    from core.idempotency import _is_transient_4xx

    assert _is_transient_4xx(status_code=400, code="confirm_missing_licence")


def test_bulk_zip_reports_skips_without_another_companys_number(tenant_a, tenant_b):
    invoice = _completed(tenant_a, "SH-ZIP")
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="SH-ZIP-DRAFT")
    draft = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "10"}]
    )
    other = _completed(tenant_b, "SH-OTHER")
    zipped = tenant_a.client.post(
        "/api/v1/sales/invoices/bulk-pdf-zip/",
        {"ids": [invoice["id"], draft["id"], other["id"], other["id"]]},
        format="json",
    )
    assert zipped.status_code == 200, zipped.data
    assert zipped.data["included"] == [{"id": invoice["id"], "number": invoice["number"]}]
    reasons = {row["id"]: row for row in zipped.data["skipped"]}
    assert reasons[draft["id"]]["reason"] == "not_completed"
    assert reasons[draft["id"]]["number"]
    assert reasons[other["id"]]["reason"] == "unavailable"
    assert "number" not in reasons[other["id"]]


def test_bulk_zip_of_only_drafts_does_not_create_a_file(tenant_a):
    from core.models import FileAsset

    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="SH-NONE")
    draft = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "10"}]
    )
    before = FileAsset.objects.filter(company=tenant_a.company).count()
    zipped = tenant_a.client.post(
        "/api/v1/sales/invoices/bulk-pdf-zip/",
        {"ids": [draft["id"]]},
        format="json",
    )
    assert zipped.status_code == 400
    assert FileAsset.objects.filter(company=tenant_a.company).count() == before


def _results(response):
    body = response.data
    if isinstance(body, dict) and "results" in body:
        return body["results"]
    return body


def _ids_for(client, payment_status):
    listed = client.get("/api/v1/sales/invoices/", {"payment_status": payment_status, "page_size": 100})
    assert listed.status_code == 200, listed.data
    return {row["id"]: row for row in _results(listed)}


def test_settlement_parity_uses_the_same_bucket_as_the_filter(tenant_a):
    """SH-06a: chip bucket, payment filter, and Due share one number on real rows."""
    from django.utils import timezone

    from payments.models import CustomerReceipt, PaymentAllocation
    from sales.models import SalesCreditNote, SalesDebitNote, SalesInvoice

    customer = make_customer(tenant_a.company, name="Parity")
    product = make_product(tenant_a.company, sku="SH-PARITY")
    add_stock(tenant_a, product, "5")
    unpaid = _completed(tenant_a, "SH-PARITY-U", price="200")
    unpaid_row = _ids_for(tenant_a.client, "UNPAID")[unpaid["id"]]
    assert unpaid_row["settlement_state"] == "UNPAID"
    assert unpaid["id"] not in _ids_for(tenant_a.client, "PAID")
    assert unpaid["id"] not in _ids_for(tenant_a.client, "PARTIAL")

    draft = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "10"}]
    )
    detail = tenant_a.client.get(f"/api/v1/sales/invoices/{draft['id']}/")
    assert detail.data["settlement_state"] == "NONE"
    for bucket in ("PAID", "PARTIAL", "UNPAID"):
        assert draft["id"] not in _ids_for(tenant_a.client, bucket)

    partial_pay = SalesInvoice.objects.get(pk=_completed(tenant_a, "SH-PARITY-PAY", price="200")["id"])
    receipt = CustomerReceipt.objects.create(
        company=tenant_a.company, customer=partial_pay.customer, amount=Decimal("40"),
    )
    PaymentAllocation.objects.create(
        company=tenant_a.company, receipt=receipt, sales_invoice=partial_pay, amount=Decimal("40"),
    )
    assert _ids_for(tenant_a.client, "PARTIAL")[partial_pay.pk]["settlement_state"] == "PARTIAL"

    credit = SalesInvoice.objects.get(pk=_completed(tenant_a, "SH-PARITY-CN", price="200")["id"])
    SalesCreditNote.objects.create(
        company=tenant_a.company, customer=credit.customer, sales_invoice=credit,
        status=SalesCreditNote.Status.COMPLETED, grand_total=Decimal("30"),
    )
    credit_row = _ids_for(tenant_a.client, "PARTIAL")[credit.pk]
    assert credit_row["settlement_state"] == "PARTIAL"
    assert Decimal(str(credit_row["balance"])) == credit.grand_total - Decimal("30")

    debit = SalesInvoice.objects.get(pk=_completed(tenant_a, "SH-PARITY-DN", price="200")["id"])
    SalesDebitNote.objects.create(
        company=tenant_a.company, customer=debit.customer, sales_invoice=debit,
        status=SalesDebitNote.Status.COMPLETED, grand_total=Decimal("15"),
    )
    debit_row = _ids_for(tenant_a.client, "UNPAID")[debit.pk]
    assert debit_row["settlement_state"] == "UNPAID"
    assert Decimal(str(debit_row["balance"])) == debit.grand_total + Decimal("15")

    discounted = SalesInvoice.objects.get(pk=_completed(tenant_a, "SH-PARITY-DISC", price="200")["id"])
    discount_receipt = CustomerReceipt.objects.create(
        company=tenant_a.company, customer=discounted.customer, amount=Decimal("20"),
        settlement_discount=Decimal("10"),
    )
    PaymentAllocation.objects.create(
        company=tenant_a.company, receipt=discount_receipt, sales_invoice=discounted, amount=Decimal("20"),
    )
    discount_row = _ids_for(tenant_a.client, "PARTIAL")[discounted.pk]
    assert discount_row["settlement_state"] == "PARTIAL"
    assert Decimal(str(discount_row["balance"])) == discounted.grand_total - Decimal("30")

    reversed_bill = SalesInvoice.objects.get(pk=_completed(tenant_a, "SH-PARITY-REV", price="200")["id"])
    SalesCreditNote.objects.create(
        company=tenant_a.company, customer=reversed_bill.customer, sales_invoice=reversed_bill,
        status=SalesCreditNote.Status.COMPLETED, grand_total=Decimal("25"),
    )
    dead = CustomerReceipt.objects.create(
        company=tenant_a.company, customer=reversed_bill.customer, amount=Decimal("50"),
    )
    PaymentAllocation.objects.create(
        company=tenant_a.company, receipt=dead, sales_invoice=reversed_bill, amount=Decimal("50"),
        reversed_at=timezone.now(),
    )
    reversed_row = _ids_for(tenant_a.client, "PARTIAL")[reversed_bill.pk]
    assert reversed_row["settlement_state"] == "PARTIAL"
    assert Decimal(str(reversed_row["balance"])) == reversed_bill.grand_total - Decimal("25")

    returned = SalesInvoice.objects.get(pk=_completed(tenant_a, "SH-PARITY-RET", price="80")["id"])
    returned.status = SalesInvoice.Status.RETURNED
    returned.save(update_fields=["status"])
    SalesCreditNote.objects.create(
        company=tenant_a.company, customer=returned.customer, sales_invoice=returned,
        status=SalesCreditNote.Status.COMPLETED, grand_total=returned.grand_total,
    )
    listed = tenant_a.client.get("/api/v1/sales/invoices/", {"page_size": 100})
    returned_row = next(row for row in _results(listed) if row["id"] == returned.pk)
    assert returned_row["status"] == "RETURNED"


def test_due_sort_matches_the_ledger_and_does_not_query_per_row(tenant_a):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from ledgers.services import LedgerService
    from payments.models import CustomerReceipt, PaymentAllocation
    from sales.models import SalesCreditNote, SalesDebitNote, SalesInvoice

    customer = make_customer(tenant_a.company, name="Due sort")

    def bundle(index, grand):
        invoice = SalesInvoice.objects.create(
            company=tenant_a.company, customer=customer, status=SalesInvoice.Status.COMPLETED,
            grand_total=Decimal(grand), number=f"DUE-{index}",
        )
        SalesCreditNote.objects.create(
            company=tenant_a.company, customer=customer, sales_invoice=invoice,
            status=SalesCreditNote.Status.COMPLETED, grand_total=Decimal("10"),
        )
        SalesDebitNote.objects.create(
            company=tenant_a.company, customer=customer, sales_invoice=invoice,
            status=SalesDebitNote.Status.COMPLETED, grand_total=Decimal("4"),
        )
        receipt = CustomerReceipt.objects.create(
            company=tenant_a.company, customer=customer, amount=Decimal("6"),
        )
        PaymentAllocation.objects.create(
            company=tenant_a.company, receipt=receipt, sales_invoice=invoice, amount=Decimal("6"),
        )
        return invoice

    first = [bundle(i, 100 + i) for i in range(10)]
    SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, status=SalesInvoice.Status.DRAFT, grand_total=Decimal("999"),
    )
    SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, status=SalesInvoice.Status.CANCELLED, grand_total=Decimal("888"),
    )

    def listed_queries():
        with CaptureQueriesContext(connection) as captured:
            response = tenant_a.client.get("/api/v1/sales/invoices/", {"sort": "due_desc", "page_size": 100})
        assert response.status_code == 200, response.data
        return len(captured), _results(response)

    queries_10, rows_10 = listed_queries()
    balances = [
        Decimal(str(row["balance"]))
        for row in rows_10
        if row["status"] in ("COMPLETED", "RETURNED")
    ]
    assert balances == sorted(balances, reverse=True)
    assert rows_10[-2]["status"] in ("DRAFT", "CANCELLED")
    assert rows_10[-1]["status"] in ("DRAFT", "CANCELLED")
    outstanding = LedgerService.bulk_sales_invoice_outstanding(tenant_a.company, [row.pk for row in first])
    for row in rows_10:
        if row["id"] in outstanding:
            assert Decimal(str(row["balance"])) == outstanding[row["id"]]
            assert row["settlement_state"] == "PARTIAL"

    for i in range(10, 50):
        bundle(i, 200 + i)
    queries_50, _rows_50 = listed_queries()
    assert queries_50 <= queries_10 + 2


def test_second_complete_does_not_issue_another_number(tenant_a):
    invoice = _completed(tenant_a, "SH-ONCE")
    number = invoice["number"]
    again = tenant_a.client.post(
        f"/api/v1/sales/invoices/{invoice['id']}/complete/", {}, format="json", HTTP_IDEMPOTENCY_KEY="second-complete",
    )
    assert again.status_code == 400, again.data
    detail = tenant_a.client.get(f"/api/v1/sales/invoices/{invoice['id']}/")
    assert detail.data["number"] == number


def test_same_idempotency_key_replays_one_complete(tenant_a):
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="SH-IDEM")
    add_stock(tenant_a, product, "2")
    draft = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "40"}]
    )
    url = f"/api/v1/sales/invoices/{draft['id']}/complete/"
    first = tenant_a.client.post(url, {}, format="json", HTTP_IDEMPOTENCY_KEY="one-gesture")
    assert first.status_code == 200, first.data
    second = tenant_a.client.post(
        url, {"confirmBlankPos": True, "confirm_blank_pos": True}, format="json", HTTP_IDEMPOTENCY_KEY="one-gesture",
    )
    assert second.status_code == 200, second.data
    assert second.data["id"] == first.data["id"]
    assert second.data["number"] == first.data["number"]


def test_get_after_post_matches_the_register(tenant_a):
    from accounts.models import CompanyUser, User
    from planwave.models import ApprovalRequest
    from sales.models import SalesInvoice

    completed = _completed(tenant_a, "SH-GET")
    detail = tenant_a.client.get(f"/api/v1/sales/invoices/{completed['id']}/")
    assert detail.data["status"] == "COMPLETED"
    assert detail.data["number"]
    assert detail.data["settlement_state"] == "UNPAID"
    listed = _ids_for(tenant_a.client, "UNPAID")
    assert listed[completed["id"]]["settlement_state"] == "UNPAID"

    paid = tenant_a.client.post(
        f"/api/v1/sales/invoices/{completed['id']}/record-payment/",
        {"amount": "10.00", "mode": "CASH"},
        format="json",
    )
    assert paid.status_code == 200, paid.data
    # The action's own response was built from an instance annotated before the receipt.
    assert paid.data["settlement_state"] == "PARTIAL"
    after_pay = tenant_a.client.get(f"/api/v1/sales/invoices/{completed['id']}/")
    assert after_pay.data["settlement_state"] == "PARTIAL"
    assert Decimal(str(after_pay.data["balance"])) < Decimal(str(detail.data["balance"]))

    sole = _completed(tenant_a, "SH-SOLE")
    cancelled = tenant_a.client.post(
        f"/api/v1/sales/invoices/{sole['id']}/cancel/", {"reason": "wrong bill"}, format="json",
    )
    assert cancelled.status_code == 200, cancelled.data
    assert tenant_a.client.get(f"/api/v1/sales/invoices/{sole['id']}/").data["status"] == "CANCELLED"

    second = User.objects.create_user(email="history-owner@alpha.test", password="StrongPass123!")
    CompanyUser.objects.create(company=tenant_a.company, user=second, role=CompanyUser.Role.OWNER)
    pending_invoice = _completed(tenant_a, "SH-PEND")
    waiting = tenant_a.client.post(
        f"/api/v1/sales/invoices/{pending_invoice['id']}/cancel/", {"reason": "needs approval"}, format="json",
    )
    assert waiting.status_code == 202, waiting.data
    pending_detail = tenant_a.client.get(f"/api/v1/sales/invoices/{pending_invoice['id']}/")
    assert pending_detail.data["status"] == "COMPLETED"
    assert pending_detail.data["cancel_approval_pending"] is True
    assert ApprovalRequest.objects.filter(
        company=tenant_a.company, action="invoice_cancel", status=ApprovalRequest.Status.PENDING,
        payload__invoice=pending_invoice["id"],
    ).count() == 1
    again = tenant_a.client.post(
        f"/api/v1/sales/invoices/{pending_invoice['id']}/cancel/", {"reason": "needs approval"}, format="json",
    )
    assert again.status_code == 202
    assert again.data["approval_id"] == waiting.data["approval_id"]

    from planwave.services import decide_approval

    decide_approval(ApprovalRequest.objects.get(pk=waiting.data["approval_id"]), approver=second, accept=True)
    listed_after = _ids_for(tenant_a.client, "UNPAID")
    assert listed_after[pending_invoice["id"]]["cancel_approval_pending"] is False
    # The screen does not carry the approval id; asking again spends the granted approval.
    granted = tenant_a.client.post(
        f"/api/v1/sales/invoices/{pending_invoice['id']}/cancel/", {"reason": "needs approval"}, format="json",
    )
    assert granted.status_code == 200, granted.data
    assert granted.data["status"] == "CANCELLED"
    assert ApprovalRequest.objects.get(pk=waiting.data["approval_id"]).token_used_at is not None

    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="SH-DEL")
    draft = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "10"}]
    )
    removed = tenant_a.client.delete(f"/api/v1/sales/invoices/{draft['id']}/")
    assert removed.status_code in (200, 204), removed.data
    missing = tenant_a.client.get(f"/api/v1/sales/invoices/{draft['id']}/")
    assert missing.status_code == 404
    alive = tenant_a.client.get("/api/v1/sales/invoices/", {"page_size": 200})
    assert all(row["id"] != draft["id"] for row in _results(alive))
    assert not SalesInvoice.objects.filter(pk=draft["id"]).exists()


def test_payment_status_accepts_several_buckets_and_overdue_filters(tenant_a):
    from datetime import timedelta

    from django.utils import timezone

    from sales.models import SalesInvoice

    first = _completed(tenant_a, "SH-MULTI-1", price="100")
    second = _completed(tenant_a, "SH-MULTI-2", price="100")
    tenant_a.client.post(
        f"/api/v1/sales/invoices/{second['id']}/record-payment/",
        {"amount": str(second["balance"]), "mode": "CASH"}, format="json",
    )
    open_rows = _ids_for(tenant_a.client, "UNPAID,PARTIAL")
    assert first["id"] in open_rows
    assert second["id"] not in open_rows
    assert "PAID" not in {row["settlement_state"] for row in open_rows.values()}

    SalesInvoice.objects.filter(pk=first["id"]).update(due_date=timezone.localdate() - timedelta(days=3))
    SalesInvoice.objects.filter(pk=second["id"]).update(due_date=timezone.localdate() - timedelta(days=3))
    overdue = tenant_a.client.get("/api/v1/sales/invoices/", {"overdue": "1"})
    ids = {row["id"] for row in overdue.data["results"]}
    # A paid bill is never overdue, however old its due date.
    assert first["id"] in ids and second["id"] not in ids


def test_cancel_keeps_the_reason_and_refuses_while_an_online_payment_is_held(tenant_a):
    from payments.models import GatewayPayment, GatewayPaymentStatus, PaymentLink

    plain = _completed(tenant_a, "SH-REASON")
    done = tenant_a.client.post(
        f"/api/v1/sales/invoices/{plain['id']}/cancel/", {"reason": "  wrong party  "}, format="json",
    )
    assert done.status_code == 200, done.data
    assert done.data["cancel_reason"] == "wrong party"
    assert tenant_a.client.get(f"/api/v1/sales/invoices/{plain['id']}/").data["cancel_reason"] == "wrong party"

    held = _completed(tenant_a, "SH-HELD")
    link = PaymentLink.objects.create(
        company=tenant_a.company, sales_invoice_id=held["id"], amount=Decimal("100"), token="held-token-1",
    )
    GatewayPayment.objects.create(
        company=tenant_a.company, provider="razorpay", provider_payment_id="pay_held_1",
        amount=Decimal("100"), status=GatewayPaymentStatus.CAPTURED_PENDING_BOOKS, payment_link=link,
    )
    refused = tenant_a.client.post(
        f"/api/v1/sales/invoices/{held['id']}/cancel/", {"reason": "oops"}, format="json",
    )
    assert refused.status_code == 400
    assert "online payment" in str(refused.data).lower()
    assert tenant_a.client.get(f"/api/v1/sales/invoices/{held['id']}/").data["status"] == "COMPLETED"


def test_register_csv_follows_the_filters_and_neutralises_formulas(tenant_a):
    from sales.models import SalesInvoice

    shown = _completed(tenant_a, "SH-CSV-1")
    SalesInvoice.objects.filter(pk=shown["id"]).update(number="=SUM(A1)")
    response = tenant_a.client.get("/api/v1/sales/invoices/export-csv/", {"payment_status": "UNPAID"})
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    text = response.content.decode("utf-8-sig")
    assert "Date,Number,Customer" in text
    assert "'=SUM(A1)" in text and ",=SUM(A1)" not in text
    none = tenant_a.client.get("/api/v1/sales/invoices/export-csv/", {"payment_status": "PAID"})
    assert "SUM(A1)" not in none.content.decode("utf-8-sig")


def test_search_term_is_trimmed_and_capped(tenant_a):
    _completed(tenant_a, "SH-Q")
    assert tenant_a.client.get("/api/v1/sales/invoices/", {"q": "x" * 5000}).status_code == 200
    blank = tenant_a.client.get("/api/v1/sales/invoices/", {"q": "   "})
    assert blank.status_code == 200 and blank.data["count"] >= 1


def test_old_invoice_zips_are_purged_and_new_ones_kept(tenant_a):
    from datetime import timedelta

    from django.utils import timezone

    from core.models import FileAsset
    from sales.tasks import purge_old_invoice_zips_task

    one = _completed(tenant_a, "SH-PURGE")
    zipped = tenant_a.client.post("/api/v1/sales/invoices/bulk-pdf-zip/", {"ids": [one["id"]]}, format="json")
    assert zipped.status_code == 200, zipped.data
    assert purge_old_invoice_zips_task() == 0
    FileAsset.objects.filter(pk=zipped.data["file_id"]).update(created_at=timezone.now() - timedelta(days=9))
    assert purge_old_invoice_zips_task() == 1
    assert not FileAsset.objects.filter(pk=zipped.data["file_id"]).exists()


def test_dashboard_recent_invoices_use_the_registers_partial_bucket(tenant_a):
    from reporting.services import ReportService

    part = _completed(tenant_a, "SH-DASH")
    tenant_a.client.post(
        f"/api/v1/sales/invoices/{part['id']}/record-payment/", {"amount": "10.00", "mode": "CASH"}, format="json",
    )
    rows = {row["id"]: row for row in ReportService.dashboard(tenant_a.company)["recent_invoices"]}
    assert rows[part["id"]]["settlement_state"] == "PARTIAL"
    register = _ids_for(tenant_a.client, "PARTIAL")
    assert part["id"] in register


def _approval(tenant, invoice_id, *, status="PENDING", requester=None, company=None, expires_in_days=7):
    from datetime import timedelta

    from django.utils import timezone

    from planwave.models import ApprovalRequest

    return ApprovalRequest.objects.create(
        company=company or tenant.company,
        action="invoice_cancel",
        payload={"invoice": invoice_id, "reason": "test"},
        status=status,
        requester=requester or tenant.owner,
        expires_at=timezone.now() + timedelta(days=expires_in_days),
    )


def test_list_flags_a_pending_cancel_per_row(tenant_a, tenant_b):
    """The list compares the approval's JSON invoice id with the row id. Postgres has no
    jsonb = bigint operator, so this list call used to 500 there (SQLite allowed it)."""
    pending = _completed(tenant_a, "SH-FLAG-P")
    text_id = _completed(tenant_a, "SH-FLAG-S")
    decided = _completed(tenant_a, "SH-FLAG-A")
    foreign = _completed(tenant_a, "SH-FLAG-F")
    _approval(tenant_a, pending["id"])
    _approval(tenant_a, str(text_id["id"]))
    _approval(tenant_a, decided["id"], status="APPROVED")
    _approval(tenant_b, foreign["id"], company=tenant_b.company, requester=tenant_b.owner)

    listed = tenant_a.client.get("/api/v1/sales/invoices/", {"page_size": 100})
    assert listed.status_code == 200, listed.data
    rows = {row["id"]: row for row in _results(listed)}
    assert rows[pending["id"]]["cancel_approval_pending"] is True
    assert rows[text_id["id"]]["cancel_approval_pending"] is True
    assert rows[decided["id"]]["cancel_approval_pending"] is False
    assert rows[foreign["id"]]["cancel_approval_pending"] is False


def test_live_settlement_parts_reads_receipts_notes_and_discount_fresh(tenant_a):
    from payments.models import CustomerReceipt, PaymentAllocation
    from sales.models import SalesCreditNote, SalesInvoice
    from sales.settlement import annotate_live_settlement, live_settlement_parts

    invoice = SalesInvoice.objects.get(pk=_completed(tenant_a, "SH-PARTS", price="200")["id"])
    assert [Decimal(str(v)) for v in live_settlement_parts(invoice)] == [0, 0, 0]
    stale = annotate_live_settlement(SalesInvoice.objects.filter(pk=invoice.pk)).get()

    receipt = CustomerReceipt.objects.create(
        company=tenant_a.company, customer=invoice.customer, amount=Decimal("40"), settlement_discount=Decimal("5"),
    )
    PaymentAllocation.objects.create(
        company=tenant_a.company, receipt=receipt, sales_invoice=invoice, amount=Decimal("40"),
    )
    SalesCreditNote.objects.create(
        company=tenant_a.company, customer=invoice.customer, sales_invoice=invoice,
        status=SalesCreditNote.Status.COMPLETED, grand_total=Decimal("30"),
    )
    alloc, notes, discount = live_settlement_parts(invoice)
    assert (Decimal(str(alloc)), Decimal(str(notes)), Decimal(str(discount))) == (
        Decimal("40"), Decimal("30"), Decimal("5"),
    )
    assert Decimal(str(stale._live_alloc)) == 0, "an annotation is a snapshot; detail paths must not trust it"


def test_an_expired_or_spent_approval_is_not_reused_for_cancel(tenant_a):
    from accounts.models import CompanyUser, User
    from sales.models import SalesInvoice

    second = User.objects.create_user(email="spent-owner@alpha.test", password="StrongPass123!")
    CompanyUser.objects.create(company=tenant_a.company, user=second, role=CompanyUser.Role.OWNER)
    invoice = _completed(tenant_a, "SH-EXPIRED")
    expired = _approval(tenant_a, invoice["id"], status="APPROVED", expires_in_days=-1)
    expired.approver = second
    expired.save(update_fields=["approver"])
    spent = _approval(tenant_a, invoice["id"], status="APPROVED")
    spent.approver = second
    spent.token_used_at = spent.created_at
    spent.save(update_fields=["approver", "token_used_at"])

    asked = tenant_a.client.post(
        f"/api/v1/sales/invoices/{invoice['id']}/cancel/", {"reason": "late"}, format="json",
    )
    assert asked.status_code == 202, asked.data
    assert asked.data["approval_id"] not in (expired.pk, spent.pk)
    assert SalesInvoice.objects.get(pk=invoice["id"]).status == SalesInvoice.Status.COMPLETED


def test_bulk_zip_download_only_serves_invoice_zips(tenant_a):
    from django.core.files.base import ContentFile

    from core.models import FileAsset

    other = FileAsset.objects.create(
        company=tenant_a.company, kind=FileAsset.Kind.EXPORT, original_name="backup.zip",
        content_type="application/zip", size=3, created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    other.file.save("backup.zip", ContentFile(b"zip"), save=True)
    assert tenant_a.client.get(f"/api/v1/sales/invoices/bulk-pdf-zip/{other.pk}/").status_code == 404
    assert tenant_a.client.get("/api/v1/sales/invoices/bulk-pdf-zip/999999/").status_code == 404
