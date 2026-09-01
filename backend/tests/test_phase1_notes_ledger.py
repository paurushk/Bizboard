"""Phase 1: credit notes, credit limits, outstanding helper matrix."""

from datetime import date
from decimal import Decimal

import pytest

from ledgers.services import LedgerService
from purchases.models import PurchaseCreditNote
from sales.models import SalesCreditNote, SalesInvoice
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def test_credit_limit_blocks_complete(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "20")
    customer = make_customer(tenant_a.company, credit_limit=Decimal("100.00"))
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "10", "unit_price": "50", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 400
    assert "credit limit" in str(resp.data).lower()


def test_unallocated_advance_allows_complete_under_limit(tenant_a):
    from payments.models import CustomerReceipt

    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, credit_limit=Decimal("100.00"))
    CustomerReceipt.objects.create(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("500.00"),
        mode="CASH",
        number="RCT-ADV-1",
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    exposure = LedgerService.customer_exposure_for_credit_limit(tenant_a.company, customer)
    assert exposure <= 0
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "50", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 200, resp.data


def test_credit_note_reduces_outstanding_and_caps(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    assert LedgerService.sales_invoice_outstanding(invoice) == Decimal("1000.00")

    cn = tenant_a.client.post(
        "/api/v1/sales/credit-notes/",
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
    assert cn.status_code == 201, cn.data
    done = tenant_a.client.post(f"/api/v1/sales/credit-notes/{cn.data['id']}/complete/")
    assert done.status_code == 200, done.data
    invoice.refresh_from_db()
    assert LedgerService.sales_invoice_outstanding(invoice) == Decimal("600.00")

    cn2 = tenant_a.client.post(
        "/api/v1/sales/credit-notes/",
        {
            "customer": customer.id,
            "sales_invoice": invoice.id,
            "reason": "CORRECTION_OF_INVOICE",
            "items": [
                {"product": product.id, "quantity": "1", "unit_price": "700", "gst_rate": "0"}
            ],
        },
        format="json",
    )
    assert cn2.status_code == 201, cn2.data
    fail = tenant_a.client.post(f"/api/v1/sales/credit-notes/{cn2.data['id']}/complete/")
    assert fail.status_code == 400
    assert SalesCreditNote.objects.get(pk=cn2.data["id"]).status == "DRAFT"


def test_purchase_return_auto_cn_excluded_from_supplier_outstanding(tenant_a):
    """BB-000323: supplier_outstanding/bulk_supplier_outstanding/supplier_statement
    must not double-count a purchase return once an auto-generated credit note
    has relieved it (mirrors purchase_invoice_outstanding's BB-000281 fix)."""
    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a, supplier,
        [{"product": product.id, "quantity": "5", "unit_price": "100", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200

    ret = tenant_a.client.post(
        "/api/v1/purchases/returns/",
        {
            "supplier": supplier.id, "purchase_invoice": pur["id"],
            "items": [{"product": product.id, "quantity": "2", "unit_price": "100"}],
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    assert tenant_a.client.post(f"/api/v1/purchases/returns/{ret.data['id']}/complete/").status_code == 200

    auto_cn = PurchaseCreditNote.objects.get(purchase_return_id=ret.data["id"])
    assert auto_cn.status == PurchaseCreditNote.Status.COMPLETED

    # Invoice 500 - CN 200 (return relieved via auto CN) = 300 outstanding, once.
    outstanding = LedgerService.supplier_outstanding(tenant_a.company, supplier)
    assert outstanding == Decimal("300.00")

    bulk = LedgerService.bulk_supplier_outstanding(tenant_a.company)
    assert bulk.get(supplier.id) == Decimal("300.00")

    statement = LedgerService.supplier_statement(tenant_a.company, supplier)
    # The return leg must not appear as a separate debit alongside the CN credit.
    return_rows = [row for row in statement if row.get("type") == "PURCHASE_RETURN"]
    assert not return_rows


def test_purchase_return_auto_cn_maps_source_item_hsn(tenant_a):
    """BB-000364: the auto-generated credit note line must carry the HSN
    snapshotted on the originating invoice line (source_item), not the product
    master's HSN as it stands today (which may have since changed)."""
    product = make_product(tenant_a.company, hsn_code="9999")
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a, supplier,
        [{"product": product.id, "quantity": "3", "unit_price": "100", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200

    # Product master's HSN changes after the purchase was recorded.
    product.hsn_code = "1111"
    product.save(update_fields=["hsn_code"])

    ret = tenant_a.client.post(
        "/api/v1/purchases/returns/",
        {
            "supplier": supplier.id, "purchase_invoice": pur["id"],
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    assert tenant_a.client.post(f"/api/v1/purchases/returns/{ret.data['id']}/complete/").status_code == 200

    auto_cn = PurchaseCreditNote.objects.get(purchase_return_id=ret.data["id"])
    cn_item = auto_cn.items.first()
    invoice_item = auto_cn.purchase_invoice.items.get(product=product)
    assert cn_item.source_item_id == invoice_item.id
    assert cn_item.hsn_code == "9999"


def test_purchase_complete_hard_blocked_in_soft_closed_period(tenant_a):
    """BB-000337: completing a purchase invoice in a soft-closed GST period is a
    hard failure, not a soft warning."""
    from reporting.models import GstReturnPeriod

    today = date.today()
    period = f"{today.year:04d}-{today.month:02d}"
    GstReturnPeriod.objects.create(
        company=tenant_a.company, period=period, status=GstReturnPeriod.Status.SOFT_CLOSED,
    )
    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a, supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    resp = tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/")
    assert resp.status_code == 400
    assert "period" in str(resp.data).lower()


def test_purchase_credit_note_complete_hard_blocked_in_soft_closed_period(tenant_a):
    """BB-000338: completing a purchase credit note in a soft-closed period is
    a hard failure."""
    from reporting.models import GstReturnPeriod

    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a, supplier,
        [{"product": product.id, "quantity": "5", "unit_price": "100", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200

    cn = tenant_a.client.post(
        "/api/v1/purchases/credit-notes/",
        {
            "supplier": supplier.id, "purchase_invoice": pur["id"], "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data

    today = date.today()
    period = f"{today.year:04d}-{today.month:02d}"
    GstReturnPeriod.objects.create(
        company=tenant_a.company, period=period, status=GstReturnPeriod.Status.SOFT_CLOSED,
    )
    resp = tenant_a.client.post(f"/api/v1/purchases/credit-notes/{cn.data['id']}/complete/")
    assert resp.status_code == 400
    assert "period" in str(resp.data).lower()


def test_purchase_credit_note_capped_to_outstanding(tenant_a):
    """BB-000339: a manual purchase credit note cannot exceed the invoice's
    remaining outstanding, mirroring the sales-side cap."""
    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a, supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200

    cn = tenant_a.client.post(
        "/api/v1/purchases/credit-notes/",
        {
            "supplier": supplier.id, "purchase_invoice": pur["id"], "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    resp = tenant_a.client.post(f"/api/v1/purchases/credit-notes/{cn.data['id']}/complete/")
    assert resp.status_code == 400
    assert "outstanding" in str(resp.data).lower()


def test_sales_order_convert_copies_money_fields(tenant_a):
    product = make_product(tenant_a.company)
    customer = make_customer(tenant_a.company)
    order = tenant_a.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id,
            "invoice_type": "NON_GST",
            "invoice_discount": "50",
            "invoice_discount_mode": "AFTER_TAX",
            "additional_charges": "10",
            "items": [
                {"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "0"}
            ],
        },
        format="json",
    )
    assert order.status_code == 201, order.data
    conv = tenant_a.client.post(f"/api/v1/sales/orders/{order.data['id']}/convert/")
    assert conv.status_code == 200, conv.data
    discount = conv.data.get("invoiceDiscount", conv.data.get("invoice_discount"))
    assert Decimal(str(discount)) == Decimal("50")
    assert len(conv.data["items"]) == 1
