"""Regression tests for defects found in the review of the audit-P0 plan."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest

from payments.models import CustomerReceipt
from tests.conftest import add_stock, make_customer, make_product

pytestmark = pytest.mark.django_db


def _body(resp):
    data = resp.data
    return data.get("data", data) if isinstance(data, dict) else data


def _pos(tenant, customer, product, *, payments, payment_extra=None):
    payment = {"mode": "CASH", "amount": "100.00", "expected_total": "100.00"}
    payment.update(payment_extra or {})
    return tenant.client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {
            "invoice": {
                "customer": customer.id,
                "invoice_type": "NON_GST",
                "items": [{
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "100.00",
                    "gst_rate": "0",
                }],
            },
            "payment": payment,
            "payments": payments,
        },
        format="json",
    )


def _receipt_total(company):
    return sum(
        (r.amount for r in CustomerReceipt.objects.filter(company=company)), Decimal("0")
    )


# ---- split tender ---------------------------------------------------------


def test_split_tender_absorbs_paise_drift_and_foots_to_the_bill(tenant_a):
    product = make_product(tenant_a.company, sku="RV-SPLIT-1", gst_rate="0")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Split Drift")
    resp = _pos(
        tenant_a, customer, product,
        payments=[{"mode": "CASH", "amount": "40.03"}, {"mode": "UPI", "amount": "60.00"}],
    )
    assert resp.status_code == 201, resp.data
    assert _receipt_total(tenant_a.company) == Decimal("100.00")
    invoice = _body(resp)["invoice"]
    assert Decimal(str(invoice["balance"])) == Decimal("0")


def test_split_tender_short_needs_the_reconcile_confirm_then_collects_less(tenant_a):
    product = make_product(tenant_a.company, sku="RV-SPLIT-2", gst_rate="0")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Split Short")
    parts = [{"mode": "CASH", "amount": "30.00"}, {"mode": "UPI", "amount": "60.00"}]
    blocked = _pos(tenant_a, customer, product, payments=parts)
    assert blocked.status_code == 409, blocked.data
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0

    confirmed = _pos(
        tenant_a, customer, product, payments=parts,
        payment_extra={"confirm_totals_mismatch": True},
    )
    assert confirmed.status_code == 201, confirmed.data
    assert _receipt_total(tenant_a.company) == Decimal("90.00")


def test_split_tender_never_collects_more_than_the_bill(tenant_a):
    product = make_product(tenant_a.company, sku="RV-SPLIT-3", gst_rate="0")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, name="Split Over")
    resp = _pos(
        tenant_a, customer, product,
        payments=[{"mode": "CASH", "amount": "60.00"}, {"mode": "UPI", "amount": "50.00"}],
        payment_extra={"confirm_totals_mismatch": True},
    )
    assert resp.status_code == 400, resp.data
    assert "more than the bill" in str(resp.data)
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0


# ---- receipts -------------------------------------------------------------


def test_receipt_rolls_back_when_oldest_first_allocation_fails(tenant_a):
    customer = make_customer(tenant_a.company, name="Atomic Rcpt")
    from core.exceptions import BusinessRuleError

    with mock.patch(
        "payments.views.PaymentService.allocate_receipt_oldest_first",
        side_effect=BusinessRuleError("period closed"),
    ):
        resp = tenant_a.client.post(
            "/api/v1/payments/receipts/",
            {"customer": customer.id, "amount": "500.00", "mode": "CASH", "allocate_oldest": True},
            format="json",
            HTTP_IDEMPOTENCY_KEY="rv-atomic-1",
        )
    assert resp.status_code == 400, resp.data
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0


# ---- HSN slab -------------------------------------------------------------


def _line(unit_price, discount="0", gst_rate="12", reason="stale"):
    return SimpleNamespace(
        gst_rate=Decimal(gst_rate),
        hsn_code="6109",
        unit_price=Decimal(unit_price),
        discount_percent=Decimal(discount),
        rate_override=False,
        rate_override_reason=reason,
        product=None,
        applied_rate=None,
        rate_version="",
        cess_rate=Decimal("0"),
    )


def _rate(line):
    from core.services.tax_engine.india import apply_effective_gst_rate

    document = SimpleNamespace(
        status="DRAFT", _preview_rateable=True, invoice_date=date(2026, 1, 15),
    )
    apply_effective_gst_rate(document, line, tax_enabled=True)
    return line


def test_apparel_slab_tests_the_price_after_line_discount():
    # ₹2,700 shirt at 10% off is a ₹2,430 sale: 5%, not 18%.
    assert _rate(_line("2700", discount="10")).gst_rate == Decimal("5")
    assert _rate(_line("2700", discount="0")).gst_rate == Decimal("18")


def test_stale_rate_notice_is_cleared_when_the_rate_stops_changing():
    line = _rate(_line("3000", gst_rate="18", reason="rate changed 12%→18% by HSN table"))
    assert line.gst_rate == Decimal("18")
    assert "price > ₹2,500" in line.rate_override_reason
    assert "12%→18%" not in line.rate_override_reason


def test_single_rate_heading_with_matching_rate_leaves_no_notice():
    line = SimpleNamespace(
        gst_rate=Decimal("18"), hsn_code="8504", unit_price=Decimal("100"),
        discount_percent=Decimal("0"), rate_override=False,
        rate_override_reason="rate changed 12%→18% by HSN table", product=None,
        applied_rate=None, rate_version="", cess_rate=Decimal("0"),
    )
    from masters.hsn_catalog import seed_starter_hsn_rates

    seed_starter_hsn_rates()
    _rate(line)
    assert line.rate_override_reason == ""


def test_product_rejects_an_unknown_supply_form(tenant_a):
    resp = tenant_a.client.post(
        "/api/v1/products/",
        {"name": "Rice", "sku": "RV-RICE", "hsn_code": "1006", "gst_rate": "5",
         "gst_supply_form": "LOOSE-ISH"},
        format="json",
    )
    assert resp.status_code == 400, resp.data
    ok = tenant_a.client.post(
        "/api/v1/products/",
        {"name": "Rice 2", "sku": "RV-RICE2", "hsn_code": "1006", "gst_rate": "5",
         "gst_supply_form": "branded_prepacked"},
        format="json",
    )
    assert ok.status_code == 201, ok.data
    assert _body(ok)["gst_supply_form"] == "BRANDED_PREPACKED"


# ---- error envelope ---------------------------------------------------------


def test_structured_confirm_errors_show_only_their_sentence():
    from core.exceptions import BusinessRuleError, api_exception_handler

    exc = BusinessRuleError(
        {"code": "SOME_CONFIRM", "message": "Please confirm this.", "confirm_codes": ["SOME_CONFIRM"]},
        code="SOME_CONFIRM",
    )
    response = api_exception_handler(exc, {})
    assert response.data["error"]["message"] == "Please confirm this."
    assert response.data["error"]["details"]["confirm_codes"] == ["SOME_CONFIRM"]


# ---- back-fill job ---------------------------------------------------------


def test_backfill_status_endpoint_and_rerun_after_done(tenant_a):
    idle = tenant_a.client.get("/api/v1/accounting/backfill/")
    assert idle.status_code == 200
    assert _body(idle)["status"] == "idle"
    first = tenant_a.client.post("/api/v1/accounting/backfill/", {"confirm": True}, format="json")
    assert first.status_code == 200, first.data
    assert _body(first)["status"] == "done"
    # A finished run is history, not a lock: the second confirm must run again.
    second = tenant_a.client.post("/api/v1/accounting/backfill/", {"confirm": True}, format="json")
    assert second.status_code == 200, second.data
    assert _body(second)["status"] == "done"
    status = tenant_a.client.get("/api/v1/accounting/backfill/")
    assert _body(status)["status"] == "done"


def test_backfill_failure_is_reported_not_left_running(tenant_a):
    with mock.patch(
        "accounting.views.perform_accounting_backfill", side_effect=RuntimeError("boom"),
    ):
        resp = tenant_a.client.post(
            "/api/v1/accounting/backfill/", {"confirm": True}, format="json",
        )
    assert resp.status_code >= 400
    status = tenant_a.client.get("/api/v1/accounting/backfill/")
    assert _body(status)["status"] == "failed"


# ---- collections reminder link ----------------------------------------------


@pytest.mark.parametrize(
    "phone,expected",
    [
        ("9876543210", "919876543210"),
        ("09876543210", "919876543210"),
        ("+91 98765 43210", "919876543210"),
        ("919876543210", "919876543210"),
        ("12345", ""),
        ("", ""),
    ],
)
def test_whatsapp_digits_normalise_indian_numbers(phone, expected):
    from payments.collections_open import _wa_digits

    assert _wa_digits(phone) == expected
