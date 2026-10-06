"""Waves 6–10 bug fixes. One module covers the backend rows in those waves."""

from __future__ import annotations

import inspect
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.postgres.indexes import GinIndex
from django.http import HttpResponse
from django.test import RequestFactory
from rest_framework.response import Response

from tests.conftest import make_customer

pytestmark = pytest.mark.django_db


def test_bug_bil_001_dunning_restarts_after_recovery(tenant_a):
    from datetime import timedelta

    from django.utils import timezone

    from billing.dunning import run_saas_dunning
    from billing.models import Plan, Subscription
    from billing.services import apply_razorpay_subscription_status

    plan = Plan.objects.create(name="Restart", slug="bil-001", seat_limit=1, modules={}, price_paise=100)
    sub = Subscription.objects.create(
        company=tenant_a.company,
        plan=plan,
        status=Subscription.Status.PAST_DUE,
        current_period_end=timezone.now() - timedelta(days=1),
        razorpay_subscription_id="sub_bil_001",
        last_dunning_step=3,
    )
    apply_razorpay_subscription_status("sub_bil_001", "active")
    sub.refresh_from_db()
    assert sub.status == Subscription.Status.ACTIVE
    assert sub.last_dunning_step == 0

    sub.status = Subscription.Status.PAST_DUE
    sub.current_period_end = timezone.now() - timedelta(days=1)
    sub.save(update_fields=["status", "current_period_end", "updated_at"])
    result = run_saas_dunning()
    assert result["sent"] == 1
    sub.refresh_from_db()
    assert sub.last_dunning_step == 1


def test_bug_bil_002_unknown_subscription_event_is_not_deduped(tenant_a):
    from rest_framework.test import APIClient

    from billing.models import Plan, Subscription
    from payments.models import ProcessedWebhookEvent

    client = APIClient()
    payload = {
        "id": "evt_unknown_1",
        "payload": {"subscription": {"entity": {"id": "sub_late_row", "status": "active"}}},
    }
    first = client.post(
        "/api/v1/billing/razorpay/webhook/",
        payload,
        format="json",
        HTTP_X_BIZBOARD_TEST_WEBHOOK="1",
    )
    assert first.status_code == 200
    assert first.data.get("reason") == "unknown_subscription"
    assert not ProcessedWebhookEvent.objects.filter(provider="razorpay_subscription").exists()

    plan = Plan.objects.create(name="Late", slug="bil-002", seat_limit=1, modules={}, price_paise=100)
    sub = Subscription.objects.create(
        company=tenant_a.company,
        plan=plan,
        status=Subscription.Status.TRIAL,
        razorpay_subscription_id="sub_late_row",
    )
    second = client.post(
        "/api/v1/billing/razorpay/webhook/",
        {**payload, "id": "evt_unknown_2"},
        format="json",
        HTTP_X_BIZBOARD_TEST_WEBHOOK="1",
    )
    assert second.status_code == 200, second.data
    sub.refresh_from_db()
    assert sub.status == Subscription.Status.ACTIVE


def test_bug_sec_009_cancel_without_trailing_slash_is_allowed(tenant_a):
    from billing.middleware import SubscriptionWriteGateMiddleware

    def _ok(_request):
        return HttpResponse("ok", status=200)

    middleware = SubscriptionWriteGateMiddleware(_ok)
    request = RequestFactory().post("/api/v1/sales/invoices/9/cancel")
    request.user = tenant_a.owner
    with patch("billing.middleware.company_writes_blocked", return_value=True):
        response = middleware(request)
    assert response.status_code == 200


def test_bug_sec_007_plan_throttle_still_present():
    from pathlib import Path

    from rest_framework.throttling import SimpleRateThrottle

    from core.throttles import TenantPlanRateThrottle

    assert issubclass(TenantPlanRateThrottle, SimpleRateThrottle)
    assert TenantPlanRateThrottle.scope == "tenant_api"
    settings_text = (Path(__file__).resolve().parents[1] / "config" / "settings.py").read_text(encoding="utf-8")
    assert "REDIS_URL" in settings_text
    assert "TenantPlanRateThrottle" in settings_text or "core.throttles" in settings_text


def test_bug_sec_005_page_size_is_capped(tenant_a):
    from core.pagination import DefaultPagination

    assert DefaultPagination.max_page_size <= 250
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    journals = tenant_a.client.get("/api/v1/accounting/journals/", {"page_size": "100000"})
    assert journals.status_code == 200, journals.data
    assert len(journals.data.get("results", journals.data)) <= 250
    movements = tenant_a.client.get("/api/v1/inventory/movements/", {"page_size": "100000"})
    assert movements.status_code == 200, movements.data
    assert len(movements.data.get("results", movements.data)) <= 250
    register = tenant_a.client.get(
        "/api/v1/reports/sales-register/",
        {"page_size": "100000", "paginate": "1"},
    )
    assert register.status_code == 200, register.data
    assert register.data["page_size"] <= 250


def test_bug_sec_005_stock_movement_export_streams(tenant_a):
    from inventory.views import StockMovementViewSet

    assert "iterator" in inspect.getsource(StockMovementViewSet.export_csv)
    response = tenant_a.client.get("/api/v1/inventory/movements/export/")
    assert response.status_code == 200
    assert "text/csv" in response["Content-Type"]
    body = b"".join(response.streaming_content)
    assert body.startswith(b"id,product_id")


def test_bug_perf_001_stock_balance_select_related():
    from inventory.views import StockBalanceViewSet

    related = StockBalanceViewSet.queryset.query.select_related
    assert "product" in related
    assert "warehouse" in related
    assert "batch" in related


def test_bug_perf_002_task_routes_split_queues():
    from config.celery import app

    routes = app.conf.task_routes
    assert routes["core.tasks.send_otp_*"]["queue"] == "high_priority"
    assert routes["payments.tasks.process_webhook_*"]["queue"] == "high_priority"
    assert routes["sales.tasks.generate_invoice_pdf"]["queue"] == "media_heavy"
    assert routes["ocr.tasks.process_bill_image"]["queue"] == "media_heavy"
    assert routes["reporting.tasks.*"]["queue"] == "reports"


def test_bug_perf_003_gstr_walks_in_chunks():
    from reporting.gst_returns import build_gstr1
    from reporting.tasks import compile_gst_return_task

    assert "_iter_prefetched" in inspect.getsource(build_gstr1)
    assert callable(compile_gst_return_task)


def test_bug_perf_004_balances_use_company_column_and_rollup(tenant_a):
    from accounting.models import Account, JournalEntry, JournalLine
    from accounting.reports import _balances, refresh_account_monthly_balances, trial_balance

    assert "company=company" in inspect.getsource(_balances)
    company = tenant_a.company
    account = Account.objects.create(company=company, code="PERF4", name="Perf", type=Account.Type.EXPENSE)
    entry = JournalEntry.objects.create(
        company=company, status=JournalEntry.Status.POSTED, entry_date=date(2026, 1, 15), number="JV-PERF4",
    )
    JournalLine.objects.create(company=company, entry=entry, account=account, debit=Decimal("10"), credit=Decimal("0"))
    before = trial_balance(company, as_of=date(2026, 1, 31))
    refresh_account_monthly_balances(company)
    after = trial_balance(company, as_of=date(2026, 1, 31))
    assert before["total_debit"] == after["total_debit"] == Decimal("10")
    live = _balances(company, as_of=date(2026, 1, 31))
    assert sum(row["debit"] for row in live) == Decimal("10")


def test_bug_perf_005_composite_indexes_exist():
    from accounting.models import JournalLine
    from payments.models import PaymentAllocation
    from sales.models import SalesInvoice

    alloc = {idx.name for idx in PaymentAllocation._meta.indexes}
    assert "alloc_sales_inv_rev_idx" in alloc
    assert "alloc_purch_inv_rev_idx" in alloc
    sales = {idx.name for idx in SalesInvoice._meta.indexes}
    assert "sales_inv_co_cust_stat_dt_idx" in sales
    journal = {idx.name for idx in JournalLine._meta.indexes}
    assert "jl_company_account_idx" in journal
    assert "jl_company_acct_entry_idx" in journal


def test_bug_perf_006_low_stock_groups_without_loading_every_override_subquery(tenant_a):
    from inventory.models import StockBalance, Warehouse
    from inventory.views import low_stock_alert_payload
    from masters.models import Product

    company = tenant_a.company
    product = Product.objects.create(
        company=company, name="Low soap", sku="LOW-SOAP", gst_rate="18", reorder_level=Decimal("5"),
    )
    left = Warehouse.objects.create(company=company, name="Left", code="L")
    right = Warehouse.objects.create(company=company, name="Right", code="R")
    StockBalance.objects.create(company=company, product=product, warehouse=left, on_hand=Decimal("1"), reserved=0)
    StockBalance.objects.create(company=company, product=product, warehouse=right, on_hand=Decimal("2"), reserved=0)
    rows = low_stock_alert_payload(company)
    assert len(rows) == 1
    assert rows[0].on_hand == Decimal("3")
    assert rows[0].is_warehouse_specific is False
    assert "Subquery" not in inspect.getsource(low_stock_alert_payload)


def test_bug_perf_008_batch_sync_runs_each_checkout(tenant_a):
    from sales.views import SalesInvoiceViewSet

    def _fake(self, request):
        return Response({"n": request.data.get("n")})

    with patch.object(SalesInvoiceViewSet, "pos_checkout", _fake):
        empty = tenant_a.client.post("/api/v1/sales/pos/batch-sync/", {"checkouts": []}, format="json")
        assert empty.status_code == 400
        response = tenant_a.client.post(
            "/api/v1/sales/pos/batch-sync/",
            {"checkouts": [{"n": 1, "idempotency_key": "b-1"}, {"n": 2, "idempotency_key": "b-2"}]},
            format="json",
        )
    assert response.status_code == 201, response.data
    assert response.data["results"] == [{"n": 1}, {"n": 2}]
    assert response.data["errors"] == []


def test_bug_sales_009_product_trigram_index():
    from masters.models import Product

    assert any(isinstance(idx, GinIndex) and idx.name == "product_name_sku_barcode_trgm" for idx in Product._meta.indexes)


def test_bug_inv_006_zpl_label(tenant_a):
    from masters.models import Product

    product = Product.objects.create(
        company=tenant_a.company, name="Label soap", sku="LBL", barcode="890123", gst_rate="18",
    )
    response = tenant_a.client.get("/api/v1/inventory/labels.zpl", {"product": product.pk})
    assert response.status_code == 200
    body = response.content.decode()
    assert body.startswith("^XA")
    assert "890123" in body
    assert "^XZ" in body


def test_bug_ui_009_customer_name_stops_at_the_next_keyword(tenant_a):
    from insights.assistant import _extract_customer_name

    make_customer(tenant_a.company, name="Rahul")
    assert _extract_customer_name(tenant_a.company, "Draft reminder for Rahul for invoice 101") == "Rahul"
    assert _extract_customer_name(tenant_a.company, "Sales totals for March") is None


def test_bug_ui_031_search_includes_growth_documents(tenant_a):
    from support.models import Ticket

    customer = make_customer(tenant_a.company, name="Search Party")
    Ticket.objects.create(
        company=tenant_a.company, customer=customer, number="TKT-4242", subject="Pump leak",
    )
    response = tenant_a.client.get("/api/v1/search/", {"q": "TKT-4242"})
    assert response.status_code == 200, response.data
    assert any(row["number"] == "TKT-4242" for row in response.data["tickets"])


def test_bug_ui_032_time_buckets_and_product_filter():
    from datetime import date as d

    from reporting.time_buckets import group_register_rows

    rows = group_register_rows(
        [
            {"date": d(2026, 4, 2), "grand_total": "10"},
            {"date": d(2026, 5, 2), "grand_total": "5"},
            {"date": d(2026, 1, 10), "grand_total": "7"},
        ],
        bucket="fy",
    )
    keys = {row["bucket"] for row in rows}
    assert "FY2026-27" in keys
    assert "FY2025-26" in keys
    from reporting.views import SalesRegisterView

    assert "time_bucket" in inspect.getsource(SalesRegisterView.get)


def test_bug_sec_008_slow_request_is_logged(caplog):
    import logging

    from core.middleware import RequestIdMiddleware

    def _ok(_request):
        return HttpResponse("ok")

    middleware = RequestIdMiddleware(_ok)
    request = RequestFactory().get("/api/v1/health/")
    request.user = None
    calls = {"n": 0}

    def _clock():
        calls["n"] += 1
        return 0 if calls["n"] == 1 else 2

    request_logger = logging.getLogger("bizboard.request")
    request_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.WARNING, logger="bizboard.request"):
            with patch("core.middleware.time.monotonic", _clock):
                response = middleware(request)
    finally:
        request_logger.removeHandler(caplog.handler)
    assert response.status_code == 200
    assert any("slow_request" in rec.message for rec in caplog.records)


def test_bug_sec_017_stale_company_does_not_fall_through(tenant_a):
    from accounts.views import _active_membership

    user = tenant_a.owner
    user.active_company_id = 9_999_999
    user.save(update_fields=["active_company_id"])
    assert _active_membership(user) is None
    user.refresh_from_db()
    assert user.active_company_id is None


def test_bug_sec_018_viewer_cannot_hold_financial_reports():
    from rest_framework import serializers

    from accounts.models import CompanyUser
    from accounts.serializers import _assert_role_capability_invariants

    with pytest.raises(serializers.ValidationError):
        _assert_role_capability_invariants(
            CompanyUser.Role.VIEWER, {"can_view_financial_reports": True},
        )


def test_bug_acc_007_comparative_store_pnl_splits_overhead(tenant_a):
    from accounting.models import Account, CostCenter, JournalEntry, JournalLine
    from accounting.reports import comparative_store_pnl

    company = tenant_a.company
    expense = Account.objects.create(company=company, code="PERF7", name="Rent", type=Account.Type.EXPENSE)
    shop_a = CostCenter.objects.create(company=company, name="Shop A", code="A")
    CostCenter.objects.create(company=company, name="Shop B", code="B")
    tagged = JournalEntry.objects.create(
        company=company, status=JournalEntry.Status.POSTED, entry_date=date(2026, 5, 1), number="JV-A",
    )
    JournalLine.objects.create(
        company=company, entry=tagged, account=expense, debit=Decimal("100"), credit=0, cost_center=shop_a,
    )
    shared = JournalEntry.objects.create(
        company=company, status=JournalEntry.Status.POSTED, entry_date=date(2026, 5, 2), number="JV-S",
    )
    JournalLine.objects.create(
        company=company, entry=shared, account=expense, debit=Decimal("50"), credit=0,
    )
    report = comparative_store_pnl(company, date_from=date(2026, 4, 1), date_to=date(2026, 6, 30))
    by_code = {col["code"]: col for col in report["stores"]}
    assert report["shared_overhead"] == Decimal("50")
    assert by_code["A"]["allocated_overhead"] == Decimal("25.00")
    assert by_code["B"]["allocated_overhead"] == Decimal("25.00")
    assert by_code["A"]["expenses"] == Decimal("100")
