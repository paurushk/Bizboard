"""Two completed invoices: credit and cash, stock, receipt, tax, and the PDF total.

A service line on the cash bill must not move stock. Skipping that line in the
editor grid is a frontend concern; the server only withholds the movement.
"""

from decimal import Decimal
from io import BytesIO

import pytest
from pypdf import PdfReader

from inventory.models import MovementType, StockMovement
from ledgers.services import LedgerService
from payments.models import CustomerReceipt, PaymentAllocation
from sales.models import SalesInvoice
from sales.pdf import render_gst_tax_invoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _pdf_text(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def test_credit_invoice_posts_stock_and_no_receipt(tenant_a):
    product = make_product(tenant_a.company, sku="READ-CR", name="Credit Goods", gst_rate="18", hsn_code="1001")
    add_stock(tenant_a, product, "10", unit_cost="40")
    customer = make_customer(tenant_a.company, name="Credit Buyer", state="Karnataka")
    draft = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "200", "gst_rate": "18", "hsn_code": "1001"},
    ])
    draft_row = SalesInvoice.objects.get(pk=draft["id"])
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/", {}, format="json")
    assert resp.status_code == 200, resp.data
    invoice = SalesInvoice.objects.get(pk=draft["id"])
    assert invoice.status == "COMPLETED"
    assert invoice.grand_total == Decimal(str(resp.data["grand_total"]))
    assert invoice.cgst_total == draft_row.cgst_total
    assert invoice.sgst_total == draft_row.sgst_total
    assert invoice.igst_total == draft_row.igst_total
    assert invoice.cgst_total > 0
    assert invoice.sgst_total == invoice.cgst_total
    assert invoice.igst_total == Decimal("0")
    assert StockMovement.objects.filter(
        company=tenant_a.company,
        product=product,
        movement_type=MovementType.SALE,
        reference_type="sales_invoice",
        reference_id=str(invoice.pk),
    ).exists()
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0
    text = _pdf_text(render_gst_tax_invoice(invoice))
    assert f"{invoice.grand_total:.2f}" in text


def test_cash_invoice_collects_exact_tender_and_skips_service_stock(tenant_a):
    goods = make_product(tenant_a.company, sku="READ-G", name="Cash Goods", gst_rate="18", hsn_code="1001")
    service = make_product(
        tenant_a.company, sku="READ-S", name="Fitting", gst_rate="18", hsn_code="9988",
        product_type="SERVICE",
    )
    add_stock(tenant_a, goods, "10", unit_cost="30")
    customer = make_customer(tenant_a.company, name="Cash Buyer", state="Maharashtra")
    draft = create_draft_invoice(tenant_a, customer, [
        {"product": goods.id, "quantity": "1", "unit_price": "100", "gst_rate": "18", "hsn_code": "1001"},
        {"product": service.id, "quantity": "1", "unit_price": "50", "gst_rate": "18", "hsn_code": "9988"},
    ])
    draft_row = SalesInvoice.objects.get(pk=draft["id"])
    total = draft_row.grand_total
    resp = tenant_a.client.post(
        f"/api/v1/sales/invoices/{draft['id']}/complete/",
        {"amount_received": str(total), "payment_mode": "CASH"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    invoice = SalesInvoice.objects.get(pk=draft["id"])
    assert invoice.status == "COMPLETED"
    assert invoice.grand_total == total
    assert invoice.grand_total == Decimal(str(resp.data["grand_total"]))
    assert invoice.igst_total == draft_row.igst_total
    assert invoice.igst_total > 0
    assert invoice.cgst_total == Decimal("0")
    assert invoice.sgst_total == Decimal("0")
    receipt = CustomerReceipt.objects.get(company=tenant_a.company)
    assert receipt.amount == total
    assert receipt.tendered == total
    assert receipt.change_given == Decimal("0.00")
    alloc = PaymentAllocation.objects.get(receipt=receipt, sales_invoice=invoice)
    assert alloc.amount == total
    assert LedgerService.sales_invoice_outstanding(invoice) == Decimal("0")
    assert StockMovement.objects.filter(
        company=tenant_a.company,
        product=goods,
        movement_type=MovementType.SALE,
        reference_type="sales_invoice",
        reference_id=str(invoice.pk),
    ).exists()
    assert not StockMovement.objects.filter(
        company=tenant_a.company,
        product=service,
        movement_type=MovementType.SALE,
    ).exists()
    text = _pdf_text(render_gst_tax_invoice(invoice))
    assert f"{invoice.grand_total:.2f}" in text


def test_completed_invoice_is_listed_on_history_detail_and_gstr1(tenant_a):
    from reporting.gst_returns import build_gstr1

    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save(update_fields=["gstin", "state"])
    product = make_product(tenant_a.company, sku="READ-GSTR", name="GSTR Goods", gst_rate="18", hsn_code="1001")
    add_stock(tenant_a, product, "5", unit_cost="10")
    customer = make_customer(
        tenant_a.company, name="GSTR Buyer", state="Karnataka", gstin="29AABCU9603R1ZJ",
    )
    draft = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18", "hsn_code": "1001"},
    ])
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/", {}, format="json")
    assert done.status_code == 200, done.data
    invoice = SalesInvoice.objects.get(pk=draft["id"])

    listed = tenant_a.client.get("/api/v1/sales/invoices/")
    assert listed.status_code == 200, listed.data
    rows = listed.data.get("results", listed.data)
    assert any(row["id"] == invoice.pk for row in rows)
    detail = tenant_a.client.get(f"/api/v1/sales/invoices/{invoice.pk}/")
    assert detail.status_code == 200, detail.data
    assert Decimal(str(detail.data["grand_total"])) == invoice.grand_total
    gstr = build_gstr1(tenant_a.company, invoice.invoice_date.strftime("%Y-%m"))
    assert invoice.number in str(gstr)
