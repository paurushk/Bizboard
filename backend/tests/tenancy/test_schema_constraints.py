"""3.2 / 3.4 — tenant_id coverage and tenant-aware DB constraints."""

from __future__ import annotations

import pytest
from django.apps import apps
from django.db import IntegrityError, transaction
from django.db.models import ForeignKey, UniqueConstraint

pytestmark = pytest.mark.django_db

# Webhooks / DLQ may park before company is resolved.
_NULLABLE_COMPANY_OK = {
    "billing_deadletterevent",
    "payments_processedwebhookevent",
    "core_auditevent",  # login / pre-tenant actions
}

# 3.4 — money/stock documents must stay unique per company (names from models).
_REQUIRED_UNIQUES = {
    "sales.SalesInvoice": "uniq_sales_number_per_company",
    "sales.SalesCreditNote": "uniq_sales_credit_note_number_per_company",
    "sales.SalesDebitNote": "uniq_sales_debit_note_number_per_company",
    "sales.SalesReturn": "uniq_sales_return_number_per_company",
    "sales.Quotation": "uniq_quotation_number_per_company",
    "sales.SalesOrder": "uniq_sales_order_number_per_company",
    "sales.DeliveryChallan": "uniq_delivery_challan_number_per_company",
    "purchases.PurchaseInvoice": "uniq_purchase_number_per_company",
    "purchases.PurchaseCreditNote": "uniq_purchase_credit_note_number_per_company",
    "purchases.PurchaseDebitNote": "uniq_purchase_debit_note_number_per_company",
    "purchases.PurchaseOrder": "uniq_purchase_order_number_per_company",
    "masters.Product": "uniq_product_sku_per_company",
    "masters.Customer": "uniq_customer_gstin_per_company",
    "masters.Supplier": "uniq_supplier_gstin_per_company",
    "payments.CustomerReceipt": "uniq_receipt_utr_per_company",
    "payments.SupplierPayment": "uniq_supplier_payment_utr_per_company",
    "inventory.Warehouse": "uniq_warehouse_code_per_company",
    "inventory.StockTransfer": "uniq_transfer_number_per_company",
    "purchases.GoodsReceipt": "uniq_goods_receipt_number_per_company",
    "accounting.JournalEntry": "uniq_journal_number_per_company",
}


def test_company_fk_is_required_except_documented_parking_tables():
    nullable = []
    for model in apps.get_models():
        try:
            field = model._meta.get_field("company")
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(field, ForeignKey):
            continue
        if field.null and model._meta.db_table not in _NULLABLE_COMPANY_OK:
            nullable.append(model._meta.db_table)
    assert not nullable, (
        "These company FKs are nullable — add a NOT NULL constraint or document "
        "them in _NULLABLE_COMPANY_OK: " + ", ".join(sorted(nullable))
    )


def test_sales_and_purchase_numbers_are_unique_per_company():
    missing = []
    for label, expected in _REQUIRED_UNIQUES.items():
        model = apps.get_model(label)
        names = {c.name for c in model._meta.constraints if isinstance(c, UniqueConstraint)}
        if expected not in names:
            missing.append(f"{label}:{expected}")
    assert missing == [], missing


def test_duplicate_sales_number_same_company_raises(tenant_a):
    from sales.models import SalesInvoice
    from tests.conftest import make_customer

    customer = make_customer(tenant_a.company)
    SalesInvoice.objects.create(
        company=tenant_a.company,
        customer=customer,
        number="INV-CONSTRAINT-1",
        invoice_type=SalesInvoice.InvoiceType.NON_GST,
        status=SalesInvoice.Status.DRAFT,
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            SalesInvoice.objects.create(
                company=tenant_a.company,
                customer=customer,
                number="INV-CONSTRAINT-1",
                invoice_type=SalesInvoice.InvoiceType.NON_GST,
                status=SalesInvoice.Status.DRAFT,
            )


def test_same_sales_number_allowed_across_companies(tenant_a, tenant_b):
    from sales.models import SalesInvoice
    from tests.conftest import make_customer

    SalesInvoice.objects.create(
        company=tenant_a.company,
        customer=make_customer(tenant_a.company),
        number="INV-SHARED-NUM",
        invoice_type=SalesInvoice.InvoiceType.NON_GST,
        status=SalesInvoice.Status.DRAFT,
    )
    other = SalesInvoice.objects.create(
        company=tenant_b.company,
        customer=make_customer(tenant_b.company, name="Beta Customer"),
        number="INV-SHARED-NUM",
        invoice_type=SalesInvoice.InvoiceType.NON_GST,
        status=SalesInvoice.Status.DRAFT,
    )
    assert other.pk


def test_duplicate_purchase_number_same_company_raises(tenant_a):
    from purchases.models import PurchaseInvoice
    from tests.conftest import make_supplier

    supplier = make_supplier(tenant_a.company)
    PurchaseInvoice.objects.create(
        company=tenant_a.company,
        supplier=supplier,
        number="PUR-CONSTRAINT-1",
        purchase_type=PurchaseInvoice.PurchaseType.NON_GST,
        status=PurchaseInvoice.Status.DRAFT,
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PurchaseInvoice.objects.create(
                company=tenant_a.company,
                supplier=supplier,
                number="PUR-CONSTRAINT-1",
                purchase_type=PurchaseInvoice.PurchaseType.NON_GST,
                status=PurchaseInvoice.Status.DRAFT,
            )


def test_api_rejects_cross_tenant_sales_customer_and_product(tenant_a, tenant_b):
    from tests.conftest import make_customer, make_product

    customer_b = make_customer(tenant_b.company, name="Foreign Customer")
    product_a = make_product(tenant_a.company, sku="TA-FK-1")
    product_b = make_product(tenant_b.company, sku="TB-FK-1")
    customer_a = make_customer(tenant_a.company, name="Local Customer")

    bad_customer = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer_b.id,
            "invoice_type": "NON_GST",
            "items": [{"product": product_a.id, "quantity": "1", "unit_price": "10", "gst_rate": "0"}],
        },
        format="json",
    )
    assert bad_customer.status_code == 400, bad_customer.data

    bad_product = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer_a.id,
            "invoice_type": "NON_GST",
            "items": [{"product": product_b.id, "quantity": "1", "unit_price": "10", "gst_rate": "0"}],
        },
        format="json",
    )
    assert bad_product.status_code == 400, bad_product.data


def test_api_rejects_cross_tenant_purchase_supplier(tenant_a, tenant_b):
    from tests.conftest import make_product, make_supplier

    supplier_b = make_supplier(tenant_b.company, name="Foreign Supplier")
    product_a = make_product(tenant_a.company, sku="TA-PUR-FK")
    resp = tenant_a.client.post(
        "/api/v1/purchases/invoices/",
        {
            "supplier": supplier_b.id,
            "purchase_type": "NON_GST",
            "items": [{"product": product_a.id, "quantity": "1", "unit_price": "10", "gst_rate": "0"}],
        },
        format="json",
    )
    assert resp.status_code == 400, resp.data


def test_api_rejects_cross_tenant_journal_account(tenant_a, tenant_b):
    from accounting.services import PostingService

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    tenant_b.company.accounting_enabled = True
    tenant_b.company.save(update_fields=["accounting_enabled"])
    foreign = PostingService._account(tenant_b.company, "1100")
    local_equity = PostingService._account(tenant_a.company, "3100")
    resp = tenant_a.client.post(
        "/api/v1/accounting/journals/",
        {
            "entryDate": "2026-04-05",
            "narration": "cross-tenant account FK",
            "lines": [
                {"account": foreign.id, "debit": "10", "credit": "0"},
                {"account": local_equity.id, "debit": "0", "credit": "10"},
            ],
        },
        format="json",
    )
    assert resp.status_code == 400, resp.data


def test_duplicate_product_sku_and_customer_gstin_raise(tenant_a):
    from masters.models import Customer
    from tests.conftest import make_customer, make_product

    make_product(tenant_a.company, sku="SKU-CONSTRAINT-1")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_product(tenant_a.company, name="Dup SKU", sku="SKU-CONSTRAINT-1")
    make_customer(tenant_a.company, name="GSTIN One", gstin="29ABCDE1234F1Z5")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Customer.objects.create(
                company=tenant_a.company,
                name="GSTIN Two",
                gstin="29ABCDE1234F1Z5",
            )


def test_duplicate_receipt_and_supplier_utr_raise(tenant_a):
    """3.4 — UniqueConstraint is the race net behind _assert_utr_unique."""
    from payments.models import CustomerReceipt, ReceiptStatus, SupplierPayment
    from tests.conftest import make_customer, make_supplier

    customer = make_customer(tenant_a.company, name="UTR Customer")
    supplier = make_supplier(tenant_a.company, name="UTR Supplier")
    CustomerReceipt.objects.create(
        company=tenant_a.company,
        customer=customer,
        amount="10.00",
        utr="UTR-DUP-R1",
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CustomerReceipt.objects.create(
                company=tenant_a.company,
                customer=customer,
                amount="11.00",
                utr="UTR-DUP-R1",
            )
    CustomerReceipt.objects.create(
        company=tenant_a.company,
        customer=customer,
        amount="12.00",
        utr="",
    )
    CustomerReceipt.objects.create(
        company=tenant_a.company,
        customer=customer,
        amount="13.00",
        utr="",
    )
    voided = CustomerReceipt.objects.create(
        company=tenant_a.company,
        customer=customer,
        amount="14.00",
        utr="UTR-VOID-REUSE",
        status=ReceiptStatus.VOIDED,
    )
    assert voided.pk
    CustomerReceipt.objects.create(
        company=tenant_a.company,
        customer=customer,
        amount="15.00",
        utr="UTR-VOID-REUSE",
    )
    SupplierPayment.objects.create(
        company=tenant_a.company,
        supplier=supplier,
        amount="20.00",
        utr="UTR-DUP-P1",
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            SupplierPayment.objects.create(
                company=tenant_a.company,
                supplier=supplier,
                amount="21.00",
                utr="UTR-DUP-P1",
            )
