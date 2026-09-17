"""Coverage for the persisted per-invoice margin snapshot (reporting.models.InvoiceProfitSnapshot)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from reporting.invoice_profit_service import InvoiceProfitService
from reporting.models import InvoiceProfitSnapshot
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _complete(tenant, *, qty="2", price="1000", discount_percent="0", product=None, customer=None):
    product = product or make_product(tenant.company, gst_rate="18")
    if getattr(product, "product_type", "GOODS") != "SERVICE":
        add_stock(tenant, product, "20")
    customer = customer or make_customer(tenant.company)
    draft = create_draft_invoice(
        tenant,
        customer,
        [
            {
                "product": product.id,
                "quantity": qty,
                "unit_price": price,
                "gst_rate": "18",
                "discount_percent": discount_percent,
            }
        ],
    )
    resp = tenant.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert resp.status_code == 200, resp.data
    invoice = SalesInvoice.objects.get(pk=draft["id"])
    return invoice, product, customer


class TestClassifyCostBasis:
    def test_no_lines_is_no_cogs(self):
        assert InvoiceProfitService.classify_cost_basis({}) == InvoiceProfitSnapshot.CostBasis.NO_COGS
        assert (
            InvoiceProfitService.classify_cost_basis({"lines": 0})
            == InvoiceProfitSnapshot.CostBasis.NO_COGS
        )

    def test_purchase_price_fallback_wins_over_everything(self):
        counts = {"lines": 3, "fifo": 1, "valuation_fallback": 1, "purchase_price_fallback": 1}
        assert (
            InvoiceProfitService.classify_cost_basis(counts)
            == InvoiceProfitSnapshot.CostBasis.PURCHASE_PRICE_FALLBACK
        )

    def test_valuation_fallback_wins_over_zero_cost_and_fifo(self):
        counts = {"lines": 2, "fifo": 1, "valuation_fallback": 1}
        assert (
            InvoiceProfitService.classify_cost_basis(counts)
            == InvoiceProfitSnapshot.CostBasis.VALUATION_FALLBACK
        )

    def test_zero_cost_wins_over_fifo(self):
        counts = {"lines": 2, "fifo": 1, "zero_cost": 1}
        assert InvoiceProfitService.classify_cost_basis(counts) == InvoiceProfitSnapshot.CostBasis.ZERO_COST

    def test_all_fifo_is_fifo(self):
        counts = {"lines": 2, "fifo": 2}
        assert InvoiceProfitService.classify_cost_basis(counts) == InvoiceProfitSnapshot.CostBasis.FIFO


def test_snapshot_created_on_complete_with_correct_margin(tenant_a):
    invoice, product, customer = _complete(tenant_a, qty="2", price="1000", discount_percent="10")

    snap = InvoiceProfitSnapshot.objects.get(sales_invoice=invoice)
    assert snap.invoice_number == invoice.number
    assert snap.invoice_status == "COMPLETED"
    assert snap.customer_id == customer.id
    # 2 * 1000 = 2000 pre-discount revenue; margin stays pre-discount (decision #2).
    assert snap.revenue_pre_discount == Decimal("2000.00")
    assert snap.line_discount_total == Decimal("200.00")
    # product.purchase_price defaults to 80 in make_product -> COGS should be FIFO-costed
    # from the stock that was added at cost 80/unit (see conftest.add_stock).
    assert snap.cogs_total > 0
    assert snap.gross_margin == snap.revenue_pre_discount - snap.cogs_total
    assert snap.has_cogs_lines is True
    assert snap.is_backfilled is False


def test_service_only_invoice_has_no_cogs_and_full_margin(tenant_a):
    product = make_product(tenant_a.company, gst_rate="18", product_type="SERVICE")
    invoice, _, _ = _complete(tenant_a, qty="1", price="500", product=product)

    snap = InvoiceProfitSnapshot.objects.get(sales_invoice=invoice)
    assert snap.cost_basis == InvoiceProfitSnapshot.CostBasis.NO_COGS
    assert snap.has_cogs_lines is False
    assert snap.cogs_total == Decimal("0")
    assert snap.gross_margin == snap.revenue_pre_discount


def test_snapshot_status_syncs_on_cancel(tenant_a):
    invoice, _, _ = _complete(tenant_a)
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{invoice.pk}/cancel/")
    assert resp.status_code == 200, resp.data

    snap = InvoiceProfitSnapshot.objects.get(sales_invoice_id=invoice.pk)
    assert snap.invoice_status == "CANCELLED"


def test_snapshot_untouched_on_full_return_except_status(tenant_a):
    invoice, product, customer = _complete(tenant_a, qty="2", price="1000")
    before = InvoiceProfitSnapshot.objects.get(sales_invoice=invoice)

    ret = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": invoice.pk,
            "items": [{"product": product.id, "quantity": "2", "unit_price": "1000"}],
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    resp = tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/")
    assert resp.status_code == 200, resp.data

    after = InvoiceProfitSnapshot.objects.get(sales_invoice=invoice)
    assert after.invoice_status == "RETURNED"
    assert after.revenue_pre_discount == before.revenue_pre_discount
    assert after.cogs_total == before.cogs_total
    assert after.gross_margin == before.gross_margin
