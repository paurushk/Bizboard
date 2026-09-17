"""Coverage for the backfill_invoice_profit_snapshots management command."""

from __future__ import annotations

from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from reporting.models import InvoiceProfitSnapshot
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _completed_invoice(tenant, qty="2", price="1000"):
    product = make_product(tenant.company, gst_rate="18")
    add_stock(tenant, product, "20")
    customer = make_customer(tenant.company)
    draft = create_draft_invoice(
        tenant, customer, [{"product": product.id, "quantity": qty, "unit_price": price, "gst_rate": "18"}]
    )
    resp = tenant.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert resp.status_code == 200, resp.data
    return SalesInvoice.objects.get(pk=draft["id"])


def test_backfill_recreates_snapshot_for_pre_feature_invoice(tenant_a):
    invoice = _completed_invoice(tenant_a)
    # Simulate an invoice completed before this feature existed: no snapshot row.
    InvoiceProfitSnapshot.objects.filter(sales_invoice=invoice).delete()

    out = StringIO()
    call_command("backfill_invoice_profit_snapshots", company=tenant_a.company.id, stdout=out)

    snap = InvoiceProfitSnapshot.objects.get(sales_invoice=invoice)
    assert snap.is_backfilled is True
    assert snap.revenue_pre_discount == Decimal("2000.00")
    assert snap.cogs_total > 0
    assert snap.gross_margin == snap.revenue_pre_discount - snap.cogs_total
    assert "created=1" in out.getvalue()


def test_backfill_dry_run_does_not_write(tenant_a):
    invoice = _completed_invoice(tenant_a)
    InvoiceProfitSnapshot.objects.filter(sales_invoice=invoice).delete()

    out = StringIO()
    call_command("backfill_invoice_profit_snapshots", dry_run=True, stdout=out)

    assert not InvoiceProfitSnapshot.objects.filter(sales_invoice=invoice).exists()
    assert "would_create=1" in out.getvalue()


def test_backfill_is_idempotent_on_rerun(tenant_a):
    invoice = _completed_invoice(tenant_a)
    InvoiceProfitSnapshot.objects.filter(sales_invoice=invoice).delete()

    call_command("backfill_invoice_profit_snapshots", company=tenant_a.company.id, stdout=StringIO())
    call_command("backfill_invoice_profit_snapshots", company=tenant_a.company.id, stdout=StringIO())

    assert InvoiceProfitSnapshot.objects.filter(sales_invoice=invoice).count() == 1


def test_backfill_skips_service_only_invoice_with_no_stock_movements(tenant_a):
    product = make_product(tenant_a.company, gst_rate="18", product_type="SERVICE")
    customer = make_customer(tenant_a.company)
    draft = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "500", "gst_rate": "18"}]
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert resp.status_code == 200, resp.data
    invoice = SalesInvoice.objects.get(pk=draft["id"])
    # Live-completed invoices already get a NO_COGS snapshot; delete it to
    # simulate the pre-feature state and confirm backfill correctly skips
    # (rather than writing a misleading zero-everything row) when there are
    # no stock movements to derive from.
    InvoiceProfitSnapshot.objects.filter(sales_invoice=invoice).delete()

    out = StringIO()
    call_command("backfill_invoice_profit_snapshots", company=tenant_a.company.id, stdout=out)

    assert not InvoiceProfitSnapshot.objects.filter(sales_invoice=invoice).exists()
    assert "skipped_no_moves=1" in out.getvalue()
