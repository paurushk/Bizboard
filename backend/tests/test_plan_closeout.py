"""Closes the remaining plan walks: books, counter timing, first invoice, Tally, offline flush."""

import json
import time
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db.backends.utils import CursorWrapper
from rest_framework.test import APIClient

from accounting.models import AccountingPeriod
from accounting.reports import profit_and_loss, trial_balance
from accounting.services import seed_chart_of_accounts
from billing.services import ensure_register_trial
from core.services.feature_flags import flag_enabled
from integrations.tally.adapter import DISCLAIMER
from ledgers.services import LedgerService
from payments.models import CustomerReceipt
from sales.models import SalesInvoice
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
    register_via_api,
)

STEP_CEILING_MS = 20_000
SIGNUP_CEILING_MS = 60_000
VALID_GSTIN = "29AAAAA0000A1ZY"


def _ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


def _clear_flag_cache(company):
    if hasattr(company, "_feature_flags_cache"):
        del company._feature_flags_cache


@pytest.mark.django_db
def test_books_walk_balances_and_a_closed_period_rejects_the_next_invoice(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    customer = make_customer(tenant_a.company, state="Karnataka")
    supplier = make_supplier(tenant_a.company, state="Karnataka")
    product = make_product(tenant_a.company, sku="BOOKS-WALK-1", hsn_code="190500", gst_rate="18")
    add_stock(tenant_a, product, "10", unit_cost="80")

    draft = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
        invoice_date="2026-09-01",
    )
    completed = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert completed.status_code == 200, completed.data
    invoice = SalesInvoice.objects.get(pk=draft["id"])
    assert invoice.status == SalesInvoice.Status.COMPLETED
    grand = Decimal(str(invoice.grand_total))
    half = (grand / 2).quantize(Decimal("0.01"))

    receipt = tenant_a.client.post("/api/v1/payments/receipts/", {
        "customer": customer.id, "amount": str(half), "mode": "CASH", "receipt_date": "2026-09-02",
    }, format="json")
    assert receipt.status_code == 201, receipt.data
    allocated = tenant_a.client.post("/api/v1/payments/allocations/", {
        "receipt": receipt.data["id"], "sales_invoice": invoice.id, "amount": str(half),
    }, format="json")
    assert allocated.status_code == 201, allocated.data

    purchase = create_draft_purchase(tenant_a, supplier, [
        {"product": product.id, "quantity": "2", "unit_price": "80"},
    ])
    purchased = tenant_a.client.post(f"/api/v1/purchases/invoices/{purchase['id']}/complete/")
    assert purchased.status_code == 200, purchased.data

    invoice.refresh_from_db()
    open_balance = LedgerService.sales_invoice_outstanding(invoice)
    outstanding = LedgerService.customer_outstanding(tenant_a.company, customer)
    statement = LedgerService.customer_statement(tenant_a.company, customer)
    tb = trial_balance(tenant_a.company, "2026-09-30")
    pnl = profit_and_loss(tenant_a.company, "2026-09-01", "2026-09-30")
    closing = statement[-1]["balance"] if statement else None
    numbers = {
        "trial_debit": str(tb["total_debit"]),
        "trial_credit": str(tb["total_credit"]),
        "open_balance": str(open_balance),
        "customer_ledger": str(outstanding),
        "statement_close": str(closing),
        "pnl_income": str(pnl["income"]),
    }
    assert tb["balanced"] is True, numbers
    assert tb["total_debit"] == tb["total_credit"], numbers
    assert tb["total_debit"] > 0, numbers
    assert outstanding == open_balance, numbers
    assert closing == outstanding, numbers
    assert pnl["income"] > 0, numbers

    AccountingPeriod.objects.create(
        company=tenant_a.company,
        name="September 2026",
        start_date="2026-09-01",
        end_date="2026-09-30",
        status=AccountingPeriod.Status.CLOSED,
    )
    second = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
        invoice_date="2026-09-15",
    )
    rejected = tenant_a.client.post(f"/api/v1/sales/invoices/{second['id']}/complete/")
    assert rejected.status_code == 400, rejected.data
    assert SalesInvoice.objects.get(pk=second["id"]).status == SalesInvoice.Status.DRAFT


@pytest.mark.django_db
def test_counter_steps_stay_under_the_ceiling_when_the_database_is_slow(tenant_a):
    customer = make_customer(tenant_a.company, state="Karnataka")
    product = make_product(
        tenant_a.company, name="Counter Soap", sku="COUNTER-1",
        barcode="8901234567890", hsn_code="190500", gst_rate="18",
    )
    add_stock(tenant_a, product, "10")
    payload = {
        "invoice": {
            "customer": customer.id,
            "invoice_type": "GST",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
        },
        "payment": {"mode": "CASH"},
    }

    def rows(payload):
        if isinstance(payload, dict) and "results" in payload:
            return payload["results"]
        return payload

    def run_pass():
        started = time.perf_counter()
        barcode = tenant_a.client.get("/api/v1/products/", {"search": "8901234567890"})
        barcode_ms = _ms(started)
        assert barcode.status_code == 200, barcode.data
        assert any(row["id"] == product.id for row in rows(barcode.data))

        started = time.perf_counter()
        named = tenant_a.client.get("/api/v1/products/", {"search": "Counter Soap"})
        name_ms = _ms(started)
        assert named.status_code == 200, named.data
        assert any(row["id"] == product.id for row in rows(named.data))

        started = time.perf_counter()
        checkout = tenant_a.client.post("/api/v1/sales/invoices/pos-checkout/", payload, format="json")
        complete_ms = _ms(started)
        assert checkout.status_code == 201, checkout.data
        invoice = checkout.data["invoice"]
        assert invoice["status"] == SalesInvoice.Status.COMPLETED

        started = time.perf_counter()
        printed = tenant_a.client.get(f"/api/v1/sales/invoices/{invoice['id']}/thermal-pdf/")
        print_ms = _ms(started)
        assert printed.status_code == 200, getattr(printed, "data", printed.status_code)
        assert "pdf" in printed["Content-Type"]
        return {
            "barcode_ms": barcode_ms,
            "name_ms": name_ms,
            "complete_ms": complete_ms,
            "print_ms": print_ms,
        }

    normal = run_pass()
    real_execute = CursorWrapper.execute

    def slowed(self, sql, params=None):
        time.sleep(0.002)
        return real_execute(self, sql, params)

    with patch.object(CursorWrapper, "execute", slowed):
        throttled = run_pass()

    measured = {f"normal_{key}": value for key, value in normal.items()}
    measured.update({f"throttled_{key}": value for key, value in throttled.items()})
    assert len(measured) == 8, measured
    slow = {key: value for key, value in measured.items() if value >= STEP_CEILING_MS}
    assert slow == {}, measured


@pytest.mark.django_db
def test_first_invoice_after_register_finishes_under_a_minute():
    client = APIClient()
    started = time.perf_counter()
    registered = register_via_api(client, {
        "company_name": "First Invoice Mart",
        "email": "first-invoice@closeout.test",
        "password": "StrongPass123!",
        "state": "Karnataka",
        "registration_type": "REGULAR",
        "gstin": VALID_GSTIN,
    })
    assert registered.status_code == 200, registered.data
    login = client.post("/api/v1/auth/login/", {
        "email": "first-invoice@closeout.test",
        "password": "StrongPass123!",
    }, format="json")
    assert login.status_code == 200, login.data
    client.cookies = login.cookies

    company = client.get("/api/v1/company/")
    assert company.status_code == 200, company.data
    assert company.data.get("gstin") == VALID_GSTIN
    series = client.patch("/api/v1/sales/invoices/number-series/", {
        "prefix": "INV", "next_number": 1, "padding": 5,
    }, format="json")
    assert series.status_code == 200, series.data

    customer = client.post("/api/v1/customers/", {
        "name": "Walk-in Buyer", "state": "Karnataka",
    }, format="json")
    assert customer.status_code == 201, customer.data
    product = client.post("/api/v1/products/", {
        "name": "First Soap", "sku": "FIRST-1", "gst_rate": "18",
        "selling_price": "100", "purchase_price": "80", "hsn_code": "190500",
    }, format="json")
    assert product.status_code == 201, product.data
    stock = client.post("/api/v1/inventory/opening-stock/", {
        "product": product.data["id"], "quantity": "5", "unit_cost": "80",
    }, format="json")
    assert stock.status_code in (200, 201), getattr(stock, "data", stock.status_code)
    draft = client.post("/api/v1/sales/invoices/", {
        "customer": customer.data["id"],
        "invoice_type": "GST",
        "items": [{
            "product": product.data["id"], "quantity": "1",
            "unit_price": "100", "gst_rate": "18",
        }],
    }, format="json")
    assert draft.status_code == 201, draft.data
    completed = client.post(f"/api/v1/sales/invoices/{draft.data['id']}/complete/")
    elapsed_ms = _ms(started)
    wizard_blocked = completed.status_code != 200
    assert completed.status_code == 200, {
        "wizard_blocked": wizard_blocked,
        "elapsed_ms": elapsed_ms,
        "body": completed.data,
    }
    assert completed.data["status"] == SalesInvoice.Status.COMPLETED
    assert elapsed_ms < SIGNUP_CEILING_MS, {"elapsed_ms": elapsed_ms, "wizard_blocked": False}


@pytest.mark.django_db
def test_granted_company_can_import_tally_and_a_trial_company_cannot(tenant_a, tenant_b):
    raw = (
        b"entity_type,name,sku,hsn_code,gst_rate,purchase_price,selling_price,opening_qty\n"
        b"customer,Closeout Cust,,,,,,\n"
        b"product,Closeout Prod,SKU-CLOSE,8471,18,10,20,1\n"
    )
    ensure_register_trial(tenant_a.company)
    ensure_register_trial(tenant_b.company)
    tenant_a.company.feature_flags = {}
    tenant_b.company.feature_flags = {}
    tenant_a.company.save(update_fields=["feature_flags"])
    tenant_b.company.save(update_fields=["feature_flags"])
    _clear_flag_cache(tenant_a.company)
    _clear_flag_cache(tenant_b.company)
    assert flag_enabled(tenant_a.company, "ENABLE_TALLY") is False

    denied = tenant_a.client.post(
        "/api/v1/integrations/tally/upload/",
        {"file": SimpleUploadedFile("masters.csv", raw, content_type="text/csv")},
        format="multipart",
    )
    assert denied.status_code == 404

    call_command("grant_company_flag", email=tenant_a.owner.email, flag="ENABLE_TALLY", on=True)
    tenant_a.company.refresh_from_db()
    _clear_flag_cache(tenant_a.company)
    assert flag_enabled(tenant_a.company, "ENABLE_TALLY") is True

    uploaded = tenant_a.client.post(
        "/api/v1/integrations/tally/upload/",
        {"file": SimpleUploadedFile("masters.csv", raw, content_type="text/csv")},
        format="multipart",
    )
    assert uploaded.status_code == 201, uploaded.data
    run_id = uploaded.data["sync_run_id"]
    preview = tenant_a.client.post("/api/v1/integrations/tally/preview/", {
        "sync_run_id": run_id,
    }, format="json")
    assert preview.status_code == 200, preview.data
    committed = tenant_a.client.post("/api/v1/integrations/tally/commit/", {
        "sync_run_id": run_id,
    }, format="json")
    assert committed.status_code == 200, committed.data
    diff = tenant_a.client.post("/api/v1/integrations/tally/migrate-diff/", {
        "batch_id": "closeout", "tally_total": "20.00",
    }, format="json")
    assert diff.status_code == 200, diff.data
    assert "diff" in diff.data
    blob = json.dumps({
        "upload": uploaded.data,
        "preview": preview.data,
        "commit": committed.data,
        "diff": diff.data,
    })
    assert "synced" not in blob.lower()
    assert "synced" not in DISCLAIMER.lower()

    still_denied = tenant_b.client.post(
        "/api/v1/integrations/tally/upload/",
        {"file": SimpleUploadedFile("masters.csv", raw, content_type="text/csv")},
        format="multipart",
    )
    assert still_denied.status_code == 404
    _clear_flag_cache(tenant_b.company)
    assert flag_enabled(tenant_b.company, "ENABLE_TALLY") is False


@pytest.mark.django_db
def test_same_flush_keys_twice_leave_one_completed_invoice_and_one_receipt(tenant_a):
    customer = make_customer(tenant_a.company, state="Karnataka")
    product = make_product(tenant_a.company, sku="FLUSH-1", hsn_code="190500", gst_rate="18")
    add_stock(tenant_a, product, "5")
    key = "pos-flush-once"
    invoice_payload = {
        "customer": customer.id,
        "invoice_type": "GST",
        "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    }

    def flush():
        created = tenant_a.client.post(
            "/api/v1/sales/invoices/", invoice_payload, format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )
        assert created.status_code in (200, 201), created.data
        invoice_id = created.data["id"]
        completed = tenant_a.client.post(
            f"/api/v1/sales/invoices/{invoice_id}/complete/", {},
            format="json", HTTP_IDEMPOTENCY_KEY=f"{key}-complete",
        )
        assert completed.status_code == 200, completed.data
        grand = completed.data["grand_total"]
        receipt = tenant_a.client.post(
            "/api/v1/payments/receipts/",
            {"customer": customer.id, "amount": grand, "mode": "CASH"},
            format="json", HTTP_IDEMPOTENCY_KEY=f"{key}-receipt",
        )
        assert receipt.status_code in (200, 201), receipt.data
        allocation = tenant_a.client.post(
            "/api/v1/payments/allocations/",
            {"receipt": receipt.data["id"], "sales_invoice": invoice_id, "amount": grand},
            format="json", HTTP_IDEMPOTENCY_KEY=f"{key}-alloc",
        )
        assert allocation.status_code in (200, 201), allocation.data
        return invoice_id, receipt.data["id"]

    first_invoice, first_receipt = flush()
    second_invoice, second_receipt = flush()
    assert second_invoice == first_invoice
    assert second_receipt == first_receipt
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == 1
    invoice = SalesInvoice.objects.get(pk=first_invoice)
    assert invoice.status == SalesInvoice.Status.COMPLETED
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 1
