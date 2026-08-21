"""Sprint D BB-000668: tenant export / sandbox restore preserves AR/AP/GST totals."""

import base64
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.db.models import Sum

from accounts.models import Company
from core.models import AuditEvent
from ledgers.services import LedgerService
from masters.models import Customer, Supplier
from purchases.models import PurchaseInvoice
from sales.models import SalesInvoice
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def _money(value) -> Decimal:
    return Decimal(str(value or 0))


def _gst_totals(company):
    sales = SalesInvoice.objects.filter(company=company, status=SalesInvoice.Status.COMPLETED).aggregate(
        cgst=Sum("cgst_total"),
        sgst=Sum("sgst_total"),
        igst=Sum("igst_total"),
        grand=Sum("grand_total"),
    )
    purchases = PurchaseInvoice.objects.filter(
        company=company, status=PurchaseInvoice.Status.COMPLETED
    ).aggregate(
        cgst=Sum("cgst_total"),
        sgst=Sum("sgst_total"),
        igst=Sum("igst_total"),
        grand=Sum("grand_total"),
    )
    return {
        "sales_gst": _money(sales["cgst"]) + _money(sales["sgst"]) + _money(sales["igst"]),
        "purchase_gst": _money(purchases["cgst"]) + _money(purchases["sgst"]) + _money(purchases["igst"]),
        "sales_grand": _money(sales["grand"]),
        "purchase_grand": _money(purchases["grand"]),
    }


def _ar_ap(company):
    ar = sum(
        (
            LedgerService.customer_outstanding(company, c)
            for c in Customer.objects.filter(company=company)
        ),
        Decimal("0"),
    )
    ap = sum(
        (
            LedgerService.supplier_outstanding(company, s)
            for s in Supplier.objects.filter(company=company)
        ),
        Decimal("0"),
    )
    return ar, ap


def _seed_completed_books(tenant):
    product = make_product(tenant.company, gst_rate="18")
    add_stock(tenant, product, "50", unit_cost="80")
    customer = make_customer(tenant.company, state="Karnataka")
    supplier = make_supplier(tenant.company, state="Karnataka")
    inv = create_draft_invoice(
        tenant,
        customer,
        [{"product": product.id, "quantity": "2", "unit_price": "1000", "gst_rate": "18"}],
        invoice_type="GST",
    )
    assert tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    pur = create_draft_purchase(
        tenant,
        supplier,
        [{"product": product.id, "quantity": "3", "unit_price": "800", "gst_rate": "18"}],
        purchase_type="GST",
    )
    assert tenant.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    return product, customer, supplier


def test_bb_000668_export_restore_sandbox_totals_match(tenant_a):
    cache.clear()
    _seed_completed_books(tenant_a)
    before_gst = _gst_totals(tenant_a.company)
    before_ar, before_ap = _ar_ap(tenant_a.company)
    assert before_gst["sales_grand"] > 0
    assert before_gst["purchase_grand"] > 0

    export = tenant_a.client.post("/api/v1/company/export/")
    assert export.status_code == 200, export.content[:500]
    blob = export.content
    assert blob
    assert AuditEvent.objects.filter(company=tenant_a.company, action="tenant.export").exists()

    restore = tenant_a.client.post(
        "/api/v1/company/restore/",
        {"payload": base64.b64encode(blob).decode("ascii")},
        format="json",
    )
    assert restore.status_code == 201, restore.data
    sandbox_id = restore.data["company_id"]
    assert sandbox_id != tenant_a.company.id
    sandbox = Company.objects.get(pk=sandbox_id)
    assert sandbox.name == f"{tenant_a.company.name} (sandbox restore)"

    after_gst = _gst_totals(sandbox)
    after_ar, after_ap = _ar_ap(sandbox)
    assert after_gst == before_gst
    assert after_ar == before_ar
    assert after_ap == before_ap


def test_bb_000668_export_rate_limited(tenant_a):
    cache.clear()
    first = tenant_a.client.post("/api/v1/company/export/")
    assert first.status_code == 200
    second = tenant_a.client.post("/api/v1/company/export/")
    assert second.status_code == 429


def test_bb_000668_destroy_in_place_requires_typed_name(tenant_a):
    cache.clear()
    _seed_completed_books(tenant_a)
    export = tenant_a.client.post("/api/v1/company/export/")
    assert export.status_code == 200
    denied = tenant_a.client.post(
        "/api/v1/company/restore/",
        {
            "payload": base64.b64encode(export.content).decode("ascii"),
            "confirm_destroy": True,
            "typed_name": "wrong-name",
        },
        format="json",
    )
    assert denied.status_code == 400
    assert SalesInvoice.objects.filter(company=tenant_a.company).exists()
