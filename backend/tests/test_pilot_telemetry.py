"""SR-52 / SR-53 — server-emitted pilot telemetry + the hypothesis scoreboard."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _completed_invoice(tenant, amount="236.00"):
    company = tenant.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    product = make_product(company, gst_rate="18")
    add_stock(tenant, product, "20")
    customer = make_customer(company, gstin="29AAAAA0000A1ZY")
    inv = create_draft_invoice(
        tenant, customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100.00", "gst_rate": "18"}],
    )
    assert tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    return inv, customer


def _receipt_and_allocate(tenant, inv, customer, amount="236.00"):
    r = tenant.client.post("/api/v1/payments/receipts/", {
        "customer": customer.id, "amount": amount, "mode": "CASH",
    }, format="json")
    assert r.status_code in (200, 201), r.data
    a = tenant.client.post("/api/v1/payments/allocations/", {
        "receipt": r.data["id"], "sales_invoice": inv["id"], "amount": amount,
    }, format="json")
    assert a.status_code in (200, 201), a.data
    return r, a


def test_allocation_emits_reconciled_telemetry_clean(tenant_a):
    from insights.models import ShopFloorEvent

    inv, customer = _completed_invoice(tenant_a)
    _receipt_and_allocate(tenant_a, inv, customer)

    ev = ShopFloorEvent.objects.filter(company=tenant_a.company, event="allocation_reconciled")
    assert ev.count() == 1
    assert ev.first().tap_count == 0  # derived outstanding stayed in band → no discrepancy


def test_soft_close_emits_period_closed_telemetry(tenant_a):
    from datetime import date

    from insights.models import ShopFloorEvent
    from reporting.gst_periods import soft_close_period

    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.save(update_fields=["gstin"])
    soft_close_period(tenant_a.company, date.today().strftime("%Y-%m"), tenant_a.owner)

    assert ShopFloorEvent.objects.filter(
        company=tenant_a.company, event="period_closed",
    ).count() == 1


def test_telemetry_scoreboard_reports_hypothesis_metrics(tenant_a):
    inv, customer = _completed_invoice(tenant_a)
    _receipt_and_allocate(tenant_a, inv, customer)

    # SR-54: FE reports a keyboard-and-scanner-only checkout as tap_count 0
    tenant_a.client.post(
        "/api/v1/insights/telemetry/",
        {"event": "invoice_complete", "duration_ms": 21000, "tap_count": 0},
        format="json",
    )
    tenant_a.client.post(
        "/api/v1/insights/telemetry/",
        {"event": "invoice_complete", "duration_ms": 40000, "tap_count": 5},
        format="json",
    )

    board = tenant_a.client.get("/api/v1/insights/telemetry/")
    assert board.status_code == 200, board.data
    d = board.data
    assert d["allocations"] == 1
    assert d["allocation_discrepancies"] == 0
    assert d["allocation_ok"] is True
    assert d["offline_ok"] is True
    assert "complete_p95_ms" in d
    assert d["checkouts_measured"] == 2
    assert d["keyboard_only_checkouts"] == 1
    assert d["keyboard_only_rate"] == 0.5
