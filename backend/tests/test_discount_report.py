"""Coverage for the sales/purchase discount report (reporting/services.py)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from purchases.models import PurchaseInvoice
from purchases.services import PurchaseService
from reporting.services import ReportService
from sales.models import SalesInvoice
from sales.services import SalesService
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def test_sales_discount_report_derives_line_discount_and_weighted_average(tenant_a):
    product = make_product(tenant_a.company, gst_rate="18")
    add_stock(tenant_a, product, "20")
    customer = make_customer(tenant_a.company)
    draft = create_draft_invoice(
        tenant_a,
        customer,
        [
            {
                "product": product.id,
                "quantity": "2",
                "unit_price": "1000",
                "gst_rate": "18",
                "discount_percent": "10",
            }
        ],
    )
    inv = SalesInvoice.objects.get(pk=draft["id"])
    SalesService.complete(inv, tenant_a.owner)

    report = ReportService.sales_discount_report(tenant_a.company)

    assert report["totals"]["invoice_count"] == 1
    assert report["totals"]["discounted_invoice_count"] == 1
    # 2 * 1000 * 10% = 200
    assert report["totals"]["line_discount_total"] == Decimal("200.00")
    assert report["totals"]["pre_discount_revenue"] == Decimal("2000.00")
    assert report["totals"]["avg_discount_percent"] == Decimal("10.00")

    by_party = {r["id"]: r for r in report["by_party"]}
    assert by_party[customer.id]["line_discount"] == Decimal("200.00")
    assert by_party[customer.id]["invoices"] == 1

    by_product = {r["product_id"]: r for r in report["by_product"]}
    assert by_product[product.id]["line_discount"] == Decimal("200.00")

    assert len(report["by_period"]) == 1


def test_sales_discount_report_customer_filter_excludes_other_customers(tenant_a):
    product = make_product(tenant_a.company, gst_rate="18")
    add_stock(tenant_a, product, "20")
    customer_a = make_customer(tenant_a.company)
    customer_b = make_customer(tenant_a.company)
    for customer in (customer_a, customer_b):
        draft = create_draft_invoice(
            tenant_a,
            customer,
            [{"product": product.id, "quantity": "1", "unit_price": "500", "gst_rate": "18"}],
        )
        SalesService.complete(SalesInvoice.objects.get(pk=draft["id"]), tenant_a.owner)

    report = ReportService.sales_discount_report(tenant_a.company, customer_id=customer_a.id)
    assert report["totals"]["invoice_count"] == 1
    assert {r["id"] for r in report["by_party"]} == {customer_a.id}


def test_purchase_discount_report_derives_line_discount(tenant_a):
    product = make_product(tenant_a.company, gst_rate="18")
    supplier = make_supplier(tenant_a.company)
    draft = create_draft_purchase(
        tenant_a,
        supplier,
        [
            {
                "product": product.id,
                "quantity": "5",
                "unit_price": "200",
                "gst_rate": "18",
                "discount_percent": "5",
            }
        ],
    )
    inv = PurchaseInvoice.objects.get(pk=draft["id"])
    PurchaseService.complete(inv, tenant_a.owner)

    report = ReportService.purchase_discount_report(tenant_a.company)

    assert report["totals"]["invoice_count"] == 1
    # 5 * 200 * 5% = 50
    assert report["totals"]["line_discount_total"] == Decimal("50.00")
    by_party = {r["id"]: r for r in report["by_party"]}
    assert by_party[supplier.id]["line_discount"] == Decimal("50.00")


def test_discount_report_empty_company_returns_zeroed_totals(tenant_a):
    report = ReportService.sales_discount_report(tenant_a.company)
    assert report["totals"]["invoice_count"] == 0
    assert report["totals"]["line_discount_total"] == Decimal("0")
    assert report["totals"]["avg_discount_percent"] == Decimal("0")
    assert report["by_party"] == []
