"""Query-count ceilings for the competitive-roadmap read paths.

Price history is a single select of invoice lines plus a single select of
order lines, so more documents must not multiply the query count. The portal
invoice list calls outstanding and an open payment link per invoice, so its
count may grow, but only linearly.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from payments.models import CustomerPortalToken
from purchases.models import PurchaseInvoice, PurchaseItem
from sales.models import SalesInvoice
from tests.conftest import make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db


def _enable(company, key):
    flags = dict(company.feature_flags or {})
    flags[key] = True
    company.feature_flags = flags
    company.save(update_fields=["feature_flags"])


def _purchase(company, supplier, product, number):
    invoice = PurchaseInvoice.objects.create(
        company=company,
        supplier=supplier,
        number=number,
        status=PurchaseInvoice.Status.COMPLETED,
        invoice_date=date(2026, 1, 1),
        grand_total=Decimal("20"),
        taxable_total=Decimal("20"),
    )
    PurchaseItem.objects.create(
        company=company,
        invoice=invoice,
        product=product,
        quantity=Decimal("1"),
        unit_price=Decimal("10"),
        description="item",
    )


def test_supplier_price_history_query_count_stays_flat(tenant_a):
    _enable(tenant_a.company, "ENABLE_SUPPLIER_PRICE_HISTORY")
    supplier = make_supplier(tenant_a.company)
    product = make_product(tenant_a.company, sku="PERF-PH")
    for i in range(2):
        _purchase(tenant_a.company, supplier, product, f"PH-S-{i}")
    url = f"/api/v1/purchases/suppliers/{supplier.id}/price-history/?product={product.id}"

    with CaptureQueriesContext(connection) as small:
        assert tenant_a.client.get(url).status_code == 200

    for i in range(6):
        _purchase(tenant_a.company, supplier, product, f"PH-L-{i}")

    with CaptureQueriesContext(connection) as large:
        body = tenant_a.client.get(url)
    assert body.status_code == 200
    assert len(body.data["rows"]) == 8
    assert len(large.captured_queries) <= len(small.captured_queries) + 2


def _sales(company, customer, number):
    return SalesInvoice.objects.create(
        company=company,
        customer=customer,
        number=number,
        status=SalesInvoice.Status.COMPLETED,
        invoice_date=timezone.localdate(),
        grand_total=Decimal("100"),
        taxable_total=Decimal("100"),
    )


def test_customer_portal_list_query_growth_is_linear(tenant_a):
    cache.clear()
    _enable(tenant_a.company, "ENABLE_CUSTOMER_PORTAL")
    customer = make_customer(tenant_a.company, email="perf@example.com")
    token = CustomerPortalToken.objects.create(
        company=tenant_a.company,
        customer=customer,
        token="portaltok_perf_0001",
        requested_via=CustomerPortalToken.Channel.EMAIL,
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    client = APIClient()
    url = f"/api/v1/public/customer-portal/{token.token}/"
    for i in range(2):
        _sales(tenant_a.company, customer, f"PERF-S-{i}")
    with CaptureQueriesContext(connection) as small:
        assert client.get(url).status_code == 200
    for i in range(6):
        _sales(tenant_a.company, customer, f"PERF-L-{i}")
    with CaptureQueriesContext(connection) as large:
        body = client.get(url)
    assert body.status_code == 200
    assert len(body.data["invoices"]) == 8
    extra_invoices = 6
    assert len(large.captured_queries) - len(small.captured_queries) <= extra_invoices * 15
