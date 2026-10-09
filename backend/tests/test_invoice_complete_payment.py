"""Completing a sales invoice collects the tender in the same transaction.

A receipt or allocation failure must leave the invoice a draft: no number,
no stock movement, no receipt.
"""

from decimal import Decimal

from django.utils import timezone

from accounts.models import CompanyUser
from core.exceptions import BusinessRuleError
from core.models import DocumentSeries
from inventory.models import StockMovement
from payments.models import CustomerReceipt, PaymentAllocation
from payments.services import PaymentService
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product


def _draft(tenant, price="500"):
    product = make_product(tenant.company, sku=f"WID-{price}")
    add_stock(tenant, product, "20")
    customer = make_customer(tenant.company, name=f"Buyer {price}")
    inv = create_draft_invoice(
        tenant,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": price, "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    return inv


def _series_next(company, doc_type):
    return list(
        DocumentSeries.objects.filter(company=company, doc_type=doc_type)
        .order_by("id")
        .values_list("next_number", flat=True)
    )


def _complete(tenant, invoice_id, body, key=None):
    headers = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
    return tenant.client.post(
        f"/api/v1/sales/invoices/{invoice_id}/complete/",
        body,
        format="json",
        **headers,
    )


def test_cash_tender_equal_to_total_posts_receipt_today(tenant_a):
    inv = _draft(tenant_a, "500")
    resp = _complete(tenant_a, inv["id"], {"amount_received": "500", "payment_mode": "CASH"})
    assert resp.status_code == 200, getattr(resp, "data", resp)
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    assert invoice.status == "COMPLETED"
    receipt = CustomerReceipt.objects.get(company=tenant_a.company)
    assert receipt.amount == Decimal("500.00")
    assert receipt.tendered == Decimal("500.00")
    assert receipt.change_given == Decimal("0.00")
    assert receipt.receipt_date == timezone.localdate()
    assert PaymentAllocation.objects.filter(receipt=receipt, sales_invoice=invoice).count() == 1


def test_inv_main_18_cash_above_total_posts_the_bill_amount(tenant_a):
    inv = _draft(tenant_a, "480")
    resp = _complete(tenant_a, inv["id"], {"amount_received": "500", "payment_mode": "CASH"})
    assert resp.status_code == 200, getattr(resp, "data", resp)
    receipt = CustomerReceipt.objects.get(company=tenant_a.company)
    assert receipt.amount == Decimal("480.00")
    assert receipt.tendered == Decimal("500.00")
    assert receipt.change_given == Decimal("20.00")
    alloc = PaymentAllocation.objects.get(receipt=receipt)
    assert alloc.amount == Decimal("480.00")


def test_inv_main_18_upi_above_total_rejects_and_leaves_a_draft(tenant_a):
    inv = _draft(tenant_a, "480")
    before_series = _series_next(tenant_a.company, "SALES_INVOICE")
    before_stock = StockMovement.objects.filter(company=tenant_a.company).count()
    resp = _complete(tenant_a, inv["id"], {"amount_received": "500", "payment_mode": "UPI"})
    assert resp.status_code == 400
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    assert invoice.status == "DRAFT"
    assert invoice.number in ("", None)
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0
    assert StockMovement.objects.filter(company=tenant_a.company).count() == before_stock
    assert _series_next(tenant_a.company, "SALES_INVOICE") == before_series


def test_allocation_failure_rolls_back_invoice_stock_and_series(tenant_a, monkeypatch):
    inv = _draft(tenant_a, "100")
    before_series = _series_next(tenant_a.company, "SALES_INVOICE")
    before_receipt_series = _series_next(tenant_a.company, "CUSTOMER_RECEIPT")
    before_stock = StockMovement.objects.filter(company=tenant_a.company).count()

    def boom(*args, **kwargs):
        raise BusinessRuleError("allocation failed")

    monkeypatch.setattr(PaymentService, "allocate_receipt", boom)
    from sales import handlers as sales_handlers

    pdf_enqueues = []
    real_delay = sales_handlers.safe_delay

    def spy_delay(task, *args, **kwargs):
        pdf_enqueues.append(getattr(task, "name", str(task)))
        return real_delay(task, *args, **kwargs)

    monkeypatch.setattr(sales_handlers, "safe_delay", spy_delay)
    resp = _complete(
        tenant_a, inv["id"], {"amount_received": "100", "payment_mode": "CASH"}, key="alloc-fail",
    )
    assert resp.status_code == 400, getattr(resp, "data", resp)
    assert pdf_enqueues == []
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    assert invoice.status == "DRAFT"
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0
    assert StockMovement.objects.filter(company=tenant_a.company).count() == before_stock
    assert _series_next(tenant_a.company, "SALES_INVOICE") == before_series
    assert _series_next(tenant_a.company, "CUSTOMER_RECEIPT") == before_receipt_series

    monkeypatch.undo()
    retry = _complete(
        tenant_a, inv["id"], {"amount_received": "100", "payment_mode": "CASH"}, key="alloc-fail",
    )
    assert retry.status_code == 200, getattr(retry, "data", resp)
    assert SalesInvoice.objects.get(pk=inv["id"]).status == "COMPLETED"
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 1


def test_successful_complete_replays_without_a_second_receipt(tenant_a):
    inv = _draft(tenant_a, "100")
    body = {"amount_received": "100", "payment_mode": "CASH"}
    first = _complete(tenant_a, inv["id"], body, key="paid-once")
    assert first.status_code == 200, getattr(first, "data", first)
    second = _complete(tenant_a, inv["id"], body, key="paid-once")
    assert second.status_code == 200, getattr(second, "data", second)
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 1


def test_sales_only_user_cannot_complete_a_paid_invoice(tenant_a):
    membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    membership.can_create_sales = True
    membership.can_create_payments = False
    membership.save(update_fields=["can_create_sales", "can_create_payments"])
    inv = _draft(tenant_a, "100")
    resp = tenant_a.staff_client.post(
        f"/api/v1/sales/invoices/{inv['id']}/complete/",
        {"amount_received": "100", "payment_mode": "CASH"},
        format="json",
    )
    assert resp.status_code == 400, getattr(resp, "data", resp)
    assert SalesInvoice.objects.get(pk=inv["id"]).status == "DRAFT"
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0


def test_cheque_complete_posts_cheque_fields_on_the_receipt(tenant_a):
    inv = _draft(tenant_a, "250")
    resp = _complete(tenant_a, inv["id"], {
        "amount_received": "250",
        "payment_mode": "CHEQUE",
        "cheque_number": "123456",
        "cheque_bank_name": "HDFC Bank",
        "cheque_date": "2026-10-01",
    })
    assert resp.status_code == 200, getattr(resp, "data", resp)
    receipt = CustomerReceipt.objects.get(company=tenant_a.company)
    assert receipt.mode == "CHEQUE"
    assert receipt.cheque_number == "123456"
    assert receipt.cheque_bank_name == "HDFC Bank"
    assert str(receipt.cheque_date) == "2026-10-01"
    assert receipt.amount == Decimal("250.00")
    alloc = PaymentAllocation.objects.get(receipt=receipt)
    assert alloc.amount == Decimal("250.00")


def test_act_11_receipt_log_names_the_id_and_omits_gstin_and_cheque_image(tenant_a, caplog):
    import logging

    from django.core.files.base import ContentFile

    from core.models import AuditEvent, FileAsset

    gstin = "29AABCU9603R1ZJ"
    image_name = "secret-cheque-scan.png"
    product = make_product(tenant_a.company, sku="LOG-1", gst_rate="0")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Log Buyer", gstin=gstin)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "80", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    asset = FileAsset.objects.create(
        company=tenant_a.company,
        kind=FileAsset.Kind.ATTACHMENT,
        original_name=image_name,
        content_type="image/png",
        size=8,
    )
    asset.file.save(image_name, ContentFile(b"\x89PNG\r\n"), save=True)
    with caplog.at_level(logging.INFO):
        resp = _complete(tenant_a, inv["id"], {
            "amount_received": "80",
            "payment_mode": "CHEQUE",
            "cheque_number": "998877",
            "cheque_bank_name": "SBI",
            "cheque_date": "2026-10-02",
            "cheque_image": asset.pk,
        })
    assert resp.status_code == 200, getattr(resp, "data", resp)
    receipt = CustomerReceipt.objects.get(company=tenant_a.company)
    assert f"customer_receipt.created id={receipt.pk}" in caplog.text
    assert gstin not in caplog.text
    assert image_name not in caplog.text
    event = AuditEvent.objects.get(entity_type="CustomerReceipt", entity_id=str(receipt.pk))
    stored = str(event.metadata)
    assert gstin not in stored
    assert image_name not in stored
    assert str(receipt.pk) == event.entity_id


def test_credit_mode_completes_without_a_receipt(tenant_a):
    inv = _draft(tenant_a, "100")
    resp = _complete(tenant_a, inv["id"], {"amount_received": "100", "payment_mode": "CREDIT"})
    assert resp.status_code == 200, getattr(resp, "data", resp)
    assert SalesInvoice.objects.get(pk=inv["id"]).status == "COMPLETED"
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0


def test_inv_main_18_card_bank_and_cheque_above_total_are_refused(tenant_a):
    for price, mode in (("471", "CARD"), ("472", "BANK"), ("473", "CHEQUE")):
        inv = _draft(tenant_a, price)
        resp = _complete(tenant_a, inv["id"], {"amount_received": "500", "payment_mode": mode})
        assert resp.status_code == 400, (mode, getattr(resp, "data", resp))
        invoice = SalesInvoice.objects.get(pk=inv["id"])
        assert invoice.status == "DRAFT"
        assert CustomerReceipt.objects.filter(company=tenant_a.company, customer_id=invoice.customer_id).count() == 0


def test_inv_det_03_amount_above_the_balance_does_not_reduce_it(tenant_a):
    from ledgers.services import LedgerService

    inv = _draft(tenant_a, "100")
    done = _complete(tenant_a, inv["id"], {})
    assert done.status_code == 200, getattr(done, "data", done)
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    before = LedgerService.sales_invoice_outstanding(invoice)
    resp = tenant_a.client.post(
        f"/api/v1/sales/invoices/{invoice.id}/record-payment/",
        {"amount": "150", "mode": "CASH"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="det-03-over",
    )
    assert resp.status_code == 400, getattr(resp, "data", resp)
    assert LedgerService.sales_invoice_outstanding(invoice) == before
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0
