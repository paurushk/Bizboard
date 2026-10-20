"""Remaining Needs attention checks: runtime links, scale budget, footing, attribution, telemetry, cleanup."""

import time
from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from insights import attention as attention_module
from insights.attention import _can_see, build_attention_rows, dismiss_attention_row
from insights.models import AttentionOutcome, AttentionRowState, ShopFloorEvent
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product
from tests.test_dan_phase_b_links import _normalise, _route_patterns


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _owner(tenant):
    return tenant.company.memberships.get(user=tenant.owner)


def _complete(tenant, customer, product, price):
    draft = create_draft_invoice(
        tenant, customer, [{"product": product.id, "quantity": "1", "unit_price": price}], invoice_type="NON_GST"
    )
    resp = tenant.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert resp.status_code == 200, resp.data
    return SalesInvoice.objects.get(pk=draft["id"])


# --- links built at run time -------------------------------------------------

@pytest.mark.django_db
def test_every_link_on_a_real_feed_opens_a_real_page(tenant_a):
    from reporting.models import Gstr2bIngest

    customer = make_customer(tenant_a.company)
    sold = make_product(tenant_a.company, sku="F-SOLD", purchase_price="80", selling_price="100")
    pricey = make_product(tenant_a.company, sku="F-COST", purchase_price="200", selling_price="100", reorder_level="0")
    add_stock(tenant_a, sold, "20", unit_cost="80")
    add_stock(tenant_a, pricey, "20", unit_cost="200")
    old = _complete(tenant_a, customer, sold, "120")
    _complete(tenant_a, customer, pricey, "100")
    past = timezone.localdate() - timedelta(days=100)
    SalesInvoice.objects.filter(pk=old.pk).update(invoice_date=past, due_date=past)
    Gstr2bIngest.objects.create(
        company=tenant_a.company, period=timezone.localdate().strftime("%Y-%m"), supplier_gstin="29AAAAA0000A1Z5",
        invoice_number="P-1", taxable_value=Decimal("10000"), cgst=Decimal("900"), sgst=Decimal("900"),
        match_status=Gstr2bIngest.MatchStatus.UNMATCHED,
    )
    rows = build_attention_rows(tenant_a.company, company_user=_owner(tenant_a))
    assert len({r["code"] for r in rows}) >= 4, "the scenario should produce several kinds of row"
    patterns = _route_patterns()
    bad = [
        (r["code"], r["action_href"])
        for r in rows
        if r["action_href"] == "/" or not any(p.match(_normalise(r["action_href"])) for p in patterns)
    ]
    assert bad == []


# --- D2: who handles what ------------------------------------------------------

@pytest.mark.django_db
def test_financial_reports_users_also_handle_service_and_quotation_rows(tenant_a):
    staff = tenant_a.company.memberships.get(user=tenant_a.staff)
    staff.can_create_sales = False
    staff.can_view_financial_reports = True
    staff.save(update_fields=["can_create_sales", "can_view_financial_reports"])
    for code in ("TICKET_SLA_BREACH", "CONTRACT_RENEWAL", "MILESTONE_OVERDUE", "JOB_READY_TO_INVOICE", "QUOTATION_EXPIRING"):
        assert _can_see(staff, code), code
    staff.can_view_financial_reports = False
    staff.save(update_fields=["can_view_financial_reports"])
    for code in ("TICKET_SLA_BREACH", "QUOTATION_EXPIRING"):
        assert not _can_see(staff, code), code
    staff.can_create_sales = True
    staff.save(update_fields=["can_create_sales"])
    assert _can_see(staff, "TICKET_SLA_BREACH")


# --- scale -----------------------------------------------------------------------

@pytest.mark.django_db
@pytest.mark.no_invariant_check  # bulk_create is a fixture, not a posted chain
def test_the_feed_stays_inside_its_budget_with_5000_invoices_and_500_customers(tenant_a):
    past = timezone.localdate() - timedelta(days=45)
    customers = [make_customer(tenant_a.company, name=f"Stress {i}") for i in range(500)]
    SalesInvoice.objects.bulk_create(
        [
            SalesInvoice(
                company=tenant_a.company, customer=customers[i % 500], status=SalesInvoice.Status.COMPLETED,
                invoice_type=SalesInvoice.InvoiceType.NON_GST, invoice_date=past, due_date=past,
                taxable_total=Decimal("100.00"), grand_total=Decimal("100.00"),
            )
            for i in range(5000)
        ],
        batch_size=500,
    )
    cu = _owner(tenant_a)
    with CaptureQueriesContext(connection) as ctx:
        start = time.perf_counter()
        rows = build_attention_rows(tenant_a.company, company_user=cu)
        elapsed = time.perf_counter() - start
    customer_rows = [r for r in rows if r["code"] == "AR_CUSTOMER"]
    # Only the 30 largest debtors get the expensive risk snapshot; the rest are counted as capped.
    assert 1 <= len(customer_rows) <= 30
    status = attention_module._build_raw_rows_cached(tenant_a.company, timezone.localdate())[1]
    assert "AR_COLLECTION_RISK" in status["truncated"]
    assert len(ctx.captured_queries) < 600, f"{len(ctx.captured_queries)} queries"
    assert elapsed < 45, f"feed took {elapsed:.1f}s"
    # A second read is served from the cache and is far cheaper.
    with CaptureQueriesContext(connection) as again:
        build_attention_rows(tenant_a.company, company_user=cu)
    assert len(again.captured_queries) < len(ctx.captured_queries) / 3


@pytest.mark.django_db
def test_dashboard_receivables_foot_to_the_aging_buckets(tenant_a):
    from reporting.services import ReportService

    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, sku="FOOT-1", purchase_price="50", selling_price="100")
    add_stock(tenant_a, product, "30", unit_cost="50")
    for days_overdue, price in ((0, "100"), (20, "200"), (45, "300"), (75, "400"), (120, "500")):
        inv = _complete(tenant_a, customer, product, price)
        due = timezone.localdate() - timedelta(days=days_overdue)
        SalesInvoice.objects.filter(pk=inv.pk).update(invoice_date=due, due_date=due)
    data = ReportService.dashboard(tenant_a.company)
    aging = data["receivables_aging"]
    buckets = sum((Decimal(str(v)) for k, v in aging.items() if k != "total"), Decimal("0"))
    assert Decimal(str(data["receivables"])) == buckets
    assert Decimal(str(data["receivables"])) > 0
    assert "receivables_uncleared_cheques" in data, "cheques not yet cleared are shown beside the buckets"


# --- attribution across people ----------------------------------------------------

@pytest.mark.django_db
def test_a_second_person_sees_who_set_a_row_aside_and_why(tenant_a):
    staff = tenant_a.company.memberships.get(user=tenant_a.staff)
    staff.can_view_financial_reports = True
    staff.save(update_fields=["can_view_financial_reports"])
    key = "DEAD_STOCK:product:77"
    assert tenant_a.client.post(
        "/api/v1/insights/attention/dismiss/", {"dedupe_key": key, "reason": "Stock is seasonal"}, format="json"
    ).status_code == 200
    resp = tenant_a.staff_client.get("/api/v1/insights/attention/?status=dismissed")
    assert resp.status_code == 200
    row = (resp.data.get("data") or resp.data)["rows"][0]
    assert row["dedupe_key"] == key and row["state_reason"] == "Stock is seasonal"
    assert row["state_by"]["user_id"] == tenant_a.owner.pk
    # And the second person can bring it back.
    assert tenant_a.staff_client.post("/api/v1/insights/attention/reopen/", {"dedupe_key": key}, format="json").status_code == 200


# --- telemetry and clean-up --------------------------------------------------------

@pytest.mark.django_db
def test_each_action_is_counted_as_a_telemetry_event(tenant_a):
    cu = _owner(tenant_a)
    dismiss_attention_row(tenant_a.company, cu, dedupe_key="DEAD_STOCK:product:5")
    event = ShopFloorEvent.objects.get(company=tenant_a.company, event="attention_action")
    assert event.feature == "dismissed" and event.journey == "attention" and event.success is True


@pytest.mark.django_db
def test_cleanup_command_removes_old_keys_only_when_a_merged_copy_exists(tenant_a):
    customer = make_customer(tenant_a.company)
    other = make_customer(tenant_a.company, name="No Copy")
    now = timezone.now()
    for cid in (customer.id, other.id):
        AttentionRowState.objects.create(company=tenant_a.company, dedupe_key=f"AR_COLLECTION_RISK:customer:{cid}", first_seen=now)
        AttentionOutcome.objects.create(
            company=tenant_a.company, dedupe_key=f"AR_COLLECTION_RISK:customer:{cid}", code="AR_COLLECTION_RISK",
            outcome="dismissed", recorded_at=now,
        )
    AttentionRowState.objects.create(company=tenant_a.company, dedupe_key=f"AR_CUSTOMER:{customer.id}", first_seen=now)
    AttentionOutcome.objects.create(
        company=tenant_a.company, dedupe_key=f"AR_CUSTOMER:{customer.id}", code="AR_CUSTOMER", outcome="dismissed", recorded_at=now,
    )
    out = StringIO()
    call_command("attention_cleanup_old_keys", stdout=out)
    assert "dry run" in out.getvalue()
    assert AttentionRowState.objects.filter(dedupe_key__startswith="AR_COLLECTION_RISK").count() == 2
    call_command("attention_cleanup_old_keys", "--apply", stdout=StringIO())
    left = set(AttentionRowState.objects.filter(dedupe_key__startswith="AR_COLLECTION_RISK").values_list("dedupe_key", flat=True))
    assert left == {f"AR_COLLECTION_RISK:customer:{other.id}"}
    assert AttentionOutcome.objects.filter(dedupe_key__startswith="AR_COLLECTION_RISK").count() == 1
    assert AttentionRowState.objects.filter(dedupe_key=f"AR_CUSTOMER:{customer.id}").exists()


def test_the_sweep_runs_on_the_deployed_beat_schedule():
    from pathlib import Path

    from django.conf import settings

    compose = (Path(settings.BASE_DIR).parent / "docker-compose.yml").read_text(encoding="utf-8")
    assert "celery -A config beat" in compose, "beat reads CELERY_BEAT_SCHEDULE from settings"
    entry = settings.CELERY_BEAT_SCHEDULE["insights-attention-sweep"]
    assert entry["task"] == "insights.tasks.sweep_attention_state_task"
