"""Phase 1 document completeness: DN/challan/purchase notes/PO + PDF READY."""

from decimal import Decimal

import pytest

from inventory.models import StockBalance, StockMovement
from sales.models import DeliveryChallan, SalesCreditNote, SalesDebitNote, SalesInvoice
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def _complete_invoice(tenant, qty="1", price="1000", gst="0", invoice_type="NON_GST"):
    product = make_product(tenant.company)
    add_stock(tenant, product, "20")
    customer = make_customer(tenant.company)
    inv = create_draft_invoice(
        tenant,
        customer,
        [{"product": product.id, "quantity": qty, "unit_price": price, "gst_rate": gst}],
        invoice_type=invoice_type,
    )
    assert tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    return SalesInvoice.objects.get(pk=inv["id"]), product, customer


def test_sales_debit_note_complete_and_cap(tenant_a):
    invoice, product, customer = _complete_invoice(tenant_a)
    dn = tenant_a.client.post(
        "/api/v1/sales/debit-notes/",
        {
            "customer": customer.id,
            "sales_invoice": invoice.id,
            "reason": "CORRECTION_OF_INVOICE",
            "items": [
                {"product": product.id, "quantity": "1", "unit_price": "400", "gst_rate": "0"}
            ],
        },
        format="json",
    )
    assert dn.status_code == 201, dn.data
    done = tenant_a.client.post(f"/api/v1/sales/debit-notes/{dn.data['id']}/complete/")
    assert done.status_code == 200, done.data
    assert SalesDebitNote.objects.get(pk=dn.data["id"]).status == "COMPLETED"

    over = tenant_a.client.post(
        "/api/v1/sales/debit-notes/",
        {
            "customer": customer.id,
            "sales_invoice": invoice.id,
            "reason": "CORRECTION_OF_INVOICE",
            "items": [
                {"product": product.id, "quantity": "1", "unit_price": "1500", "gst_rate": "0"}
            ],
        },
        format="json",
    )
    assert over.status_code == 201, over.data
    fail = tenant_a.client.post(f"/api/v1/sales/debit-notes/{over.data['id']}/complete/")
    assert fail.status_code == 400
    assert SalesDebitNote.objects.get(pk=over.data["id"]).status == "DRAFT"


def test_delivery_challan_complete_no_stock_movement(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    before = StockBalance.objects.get(company=tenant_a.company, product=product).on_hand
    movements_before = StockMovement.objects.filter(company=tenant_a.company).count()
    customer = make_customer(tenant_a.company)
    challan = tenant_a.client.post(
        "/api/v1/sales/delivery-challans/",
        {
            "customer": customer.id,
            "items": [{"product": product.id, "quantity": "3", "unit_price": "0", "gst_rate": "0"}],
        },
        format="json",
    )
    assert challan.status_code == 201, challan.data
    done = tenant_a.client.post(f"/api/v1/sales/delivery-challans/{challan.data['id']}/complete/")
    assert done.status_code == 200, done.data
    assert DeliveryChallan.objects.get(pk=challan.data["id"]).status == "COMPLETED"
    after = StockBalance.objects.get(company=tenant_a.company, product=product).on_hand
    assert after == before
    assert StockMovement.objects.filter(company=tenant_a.company).count() == movements_before


def test_purchase_credit_and_debit_note_complete(tenant_a):
    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "2", "unit_price": "200", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200

    cn = tenant_a.client.post(
        "/api/v1/purchases/credit-notes/",
        {
            "supplier": supplier.id,
            "purchase_invoice": pur["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [
                {"product": product.id, "quantity": "1", "unit_price": "50", "gst_rate": "0"}
            ],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    assert (
        tenant_a.client.post(f"/api/v1/purchases/credit-notes/{cn.data['id']}/complete/").status_code
        == 200
    )

    dn = tenant_a.client.post(
        "/api/v1/purchases/debit-notes/",
        {
            "supplier": supplier.id,
            "purchase_invoice": pur["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [
                {"product": product.id, "quantity": "1", "unit_price": "40", "gst_rate": "0"}
            ],
        },
        format="json",
    )
    assert dn.status_code == 201, dn.data
    assert (
        tenant_a.client.post(f"/api/v1/purchases/debit-notes/{dn.data['id']}/complete/").status_code
        == 200
    )


def test_purchase_order_convert_copies_money_fields(tenant_a):
    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    order = tenant_a.client.post(
        "/api/v1/purchases/orders/",
        {
            "supplier": supplier.id,
            "purchase_type": "NON_GST",
            "invoice_discount": "25",
            "invoice_discount_mode": "AFTER_TAX",
            "additional_charges": "5",
            "items": [
                {"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "0"}
            ],
        },
        format="json",
    )
    assert order.status_code == 201, order.data
    conv = tenant_a.client.post(f"/api/v1/purchases/orders/{order.data['id']}/convert/")
    assert conv.status_code == 200, conv.data
    discount = conv.data.get("invoiceDiscount", conv.data.get("invoice_discount"))
    assert Decimal(str(discount)) == Decimal("25")
    assert len(conv.data["items"]) == 1


def test_credit_note_pdf_ready_after_complete(tenant_a):
    invoice, product, customer = _complete_invoice(tenant_a)
    cn = tenant_a.client.post(
        "/api/v1/sales/credit-notes/",
        {
            "customer": customer.id,
            "sales_invoice": invoice.id,
            "reason": "CORRECTION_OF_INVOICE",
            "items": [
                {"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}
            ],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    done = tenant_a.client.post(f"/api/v1/sales/credit-notes/{cn.data['id']}/complete/")
    assert done.status_code == 200, done.data
    note = SalesCreditNote.objects.get(pk=cn.data["id"])
    assert note.pdf_status == "READY"
    assert note.pdf_file_id is not None
    pdf = tenant_a.client.get(f"/api/v1/sales/credit-notes/{cn.data['id']}/pdf/")
    assert pdf.status_code == 200
    content = b"".join(pdf.streaming_content)
    assert content.startswith(b"%PDF")


def test_debit_note_and_challan_pdf_ready(tenant_a):
    invoice, product, customer = _complete_invoice(tenant_a)
    dn = tenant_a.client.post(
        "/api/v1/sales/debit-notes/",
        {
            "customer": customer.id,
            "sales_invoice": invoice.id,
            "reason": "CORRECTION_OF_INVOICE",
            "items": [
                {"product": product.id, "quantity": "1", "unit_price": "50", "gst_rate": "0"}
            ],
        },
        format="json",
    )
    assert dn.status_code == 201, dn.data
    assert tenant_a.client.post(f"/api/v1/sales/debit-notes/{dn.data['id']}/complete/").status_code == 200
    assert SalesDebitNote.objects.get(pk=dn.data["id"]).pdf_status == "READY"

    challan = tenant_a.client.post(
        "/api/v1/sales/delivery-challans/",
        {
            "customer": customer.id,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "0", "gst_rate": "0"}],
        },
        format="json",
    )
    assert challan.status_code == 201, challan.data
    assert (
        tenant_a.client.post(f"/api/v1/sales/delivery-challans/{challan.data['id']}/complete/").status_code
        == 200
    )
    assert DeliveryChallan.objects.get(pk=challan.data["id"]).pdf_status == "READY"
