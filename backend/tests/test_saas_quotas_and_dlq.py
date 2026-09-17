"""8.2 / 8.3 / 3.7 / 3.8 / 9.4 / 9.5 / 11.3 / 12.6 — SaaS quotas, freeze plans, DLQ."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from billing.entitlements import FREEZE_DARK_PLAN_MODULES
from billing.models import DeadLetterEvent, Plan, Subscription
from billing.services import company_writes_blocked
from core.exceptions import BusinessRuleError
from core.help_codes import HelpCode
from core.tracing import captured_spans, clear_spans
from tests.conftest import add_stock, create_draft_invoice, create_draft_purchase, make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db


def _subscribe(company, **plan_kwargs):
    defaults = {
        "name": "Quota",
        "slug": plan_kwargs.pop("slug", "quota-plan"),
        "seat_limit": 3,
        "monthly_complete_limit": 0,
        "storage_bytes_limit": 0,
        "api_rate_per_minute": 0,
        "modules": {key: False for key in FREEZE_DARK_PLAN_MODULES},
        "price_paise": 49900,
    }
    defaults.update(plan_kwargs)
    plan = Plan.objects.create(**defaults)
    sub = Subscription.objects.create(
        company=company,
        plan=plan,
        status=Subscription.Status.ACTIVE,
    )
    return plan, sub


def test_seed_plans_are_freeze_safe():
    """8.2 — paid plans must not enable Table B dark modules; POS only on paid."""
    call_command("seed_plans")
    by_slug = {p.slug: p for p in Plan.objects.filter(slug__in=("free", "starter", "pro", "enterprise"))}
    assert set(by_slug) == {"free", "starter", "pro", "enterprise"}
    for slug, plan in by_slug.items():
        for key in FREEZE_DARK_PLAN_MODULES:
            assert plan.modules.get(key) is False, f"{slug}.{key}"
        if slug == "free":
            assert plan.modules.get("ENABLE_POS") is False
            assert plan.monthly_complete_limit == 30
        else:
            assert plan.modules.get("ENABLE_POS") is True
    assert by_slug["enterprise"].monthly_complete_limit == 0
    assert by_slug["enterprise"].storage_bytes_limit == 0
    assert by_slug["enterprise"].api_rate_per_minute == 0


@override_settings(ENABLE_GSTR=True, ENABLE_MANUFACTURING=True, ENABLE_PAYROLL=True, ENABLE_TALLY=True)
def test_seeded_paid_plan_does_not_enable_table_b(tenant_a):
    call_command("seed_plans")
    plan = Plan.objects.get(slug="pro")
    Subscription.objects.create(
        company=tenant_a.company, plan=plan, status=Subscription.Status.ACTIVE,
    )
    flags = tenant_a.client.get("/api/v1/feature-flags/")
    assert flags.status_code == 200
    for key in FREEZE_DARK_PLAN_MODULES:
        assert flags.data.get(key) is False, key
    assert flags.data.get("ENABLE_POS") is True


def test_monthly_complete_quota_blocks_second_complete(tenant_a):
    _subscribe(tenant_a.company, slug="one-complete", monthly_complete_limit=1)
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    first = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    ok = tenant_a.client.post(f"/api/v1/sales/invoices/{first['id']}/complete/")
    assert ok.status_code == 200, ok.data

    second = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    blocked = tenant_a.client.post(f"/api/v1/sales/invoices/{second['id']}/complete/")
    assert blocked.status_code == 400, blocked.data
    assert blocked.data["error"]["code"] == HelpCode.PLAN_QUOTA_EXCEEDED


def test_monthly_complete_quota_blocks_purchase_complete(tenant_a):
    _subscribe(tenant_a.company, slug="one-purchase", monthly_complete_limit=1)
    product = make_product(tenant_a.company, sku="WID-P1")
    supplier = make_supplier(tenant_a.company)
    first = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "80", "gst_rate": "18"}],
    )
    ok = tenant_a.client.post(f"/api/v1/purchases/invoices/{first['id']}/complete/")
    assert ok.status_code == 200, ok.data
    second = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "80", "gst_rate": "18"}],
    )
    blocked = tenant_a.client.post(f"/api/v1/purchases/invoices/{second['id']}/complete/")
    assert blocked.status_code == 400, blocked.data
    assert blocked.data["error"]["code"] == HelpCode.PLAN_QUOTA_EXCEEDED


def test_complete_quota_skipped_when_billing_override(tenant_a):
    from billing.quotas import assert_complete_allowed

    _subscribe(tenant_a.company, slug="override-q", monthly_complete_limit=1)
    tenant_a.company.billing_override_active = True
    tenant_a.company.save(update_fields=["billing_override_active"])
    assert_complete_allowed(tenant_a.company)


def test_storage_quota_blocks_upload(tenant_a):
    _subscribe(tenant_a.company, slug="tiny-store", storage_bytes_limit=8)
    pdf = SimpleUploadedFile("note.pdf", b"%PDF-1.4XXXX", content_type="application/pdf")
    resp = tenant_a.client.post(
        "/api/v1/files/",
        {"kind": "ATTACHMENT", "file": pdf},
        format="multipart",
    )
    assert resp.status_code == 400, resp.data
    assert resp.data["error"]["code"] == HelpCode.PLAN_QUOTA_EXCEEDED


def test_subscription_payload_includes_quotas(tenant_a):
    _subscribe(tenant_a.company, slug="quota-snap", monthly_complete_limit=30, storage_bytes_limit=1000)
    resp = tenant_a.client.get("/api/v1/billing/subscription/")
    assert resp.status_code == 200, resp.data
    quotas = resp.data["quotas"]
    assert quotas["completes"]["limit"] == 30
    assert quotas["storage_bytes"]["limit"] == 1000
    assert "used" in quotas["completes"]
    assert quotas["api_rate_per_minute"] == 0


def test_sales_complete_emits_trace_span(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    clear_spans()
    ok = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert ok.status_code == 200, ok.data
    names = [row["name"] for row in captured_spans()]
    assert "sales.complete" in names


def test_sales_pdf_emits_trace_span(tenant_a):
    from sales.models import SalesInvoice
    from sales.tasks import generate_invoice_pdf

    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    clear_spans()
    generate_invoice_pdf.run(done.data["id"], company_id=tenant_a.company.id)
    names = [row["name"] for row in captured_spans()]
    assert "sales.pdf" in names
    SalesInvoice.objects.get(pk=done.data["id"])


def test_plan_api_rate_throttles_noisy_neighbor(tenant_a, tenant_b):
    """12.6 — tenant A's cap must not 429 tenant B."""
    _subscribe(tenant_a.company, slug="slow-api", api_rate_per_minute=1)
    _subscribe(tenant_b.company, slug="fast-api", api_rate_per_minute=0)
    first = tenant_a.client.get("/api/v1/billing/subscription/")
    assert first.status_code == 200
    second = tenant_a.client.get("/api/v1/billing/subscription/")
    assert second.status_code == 429
    other = tenant_b.client.get("/api/v1/customers/")
    assert other.status_code == 200


def test_cancelled_subscription_keeps_writes_until_paid_period_ends(tenant_a):
    """8.4 / B9-007 — cancelled SaaS keeps writes through the already-paid period."""
    _plan, sub = _subscribe(tenant_a.company, slug="cancel-grace")
    sub.status = Subscription.Status.SUSPENDED
    sub.current_period_end = timezone.now() + timedelta(days=5)
    sub.save(update_fields=["status", "current_period_end"])
    assert company_writes_blocked(tenant_a.company) is False
    sub.current_period_end = timezone.now() - timedelta(seconds=1)
    sub.save(update_fields=["current_period_end"])
    assert company_writes_blocked(tenant_a.company) is True


def test_suspended_then_reactivated_subscription_unblocks_writes(tenant_a):
    """3.8 — cancel write-blocks; active webhook restores writes."""
    plan, sub = _subscribe(tenant_a.company, slug="reactivate")
    sub.status = Subscription.Status.SUSPENDED
    sub.razorpay_subscription_id = "sub_reactivate_1"
    sub.current_period_end = timezone.now()
    sub.save(update_fields=["status", "razorpay_subscription_id", "current_period_end"])

    product = make_product(tenant_a.company)
    customer = make_customer(tenant_a.company)
    blocked = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer.id,
            "invoice_type": "NON_GST",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )
    assert blocked.status_code == 403

    client = APIClient()
    resp = client.post(
        "/api/v1/billing/razorpay/webhook/",
        {
            "event": "subscription.activated",
            "payload": {"subscription": {"entity": {"id": "sub_reactivate_1", "status": "active"}}},
        },
        format="json",
        HTTP_X_BIZBOARD_TEST_WEBHOOK="1",
    )
    assert resp.status_code == 200, resp.data
    sub.refresh_from_db()
    assert sub.status == Subscription.Status.ACTIVE

    allowed = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer.id,
            "invoice_type": "NON_GST",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )
    assert allowed.status_code == 201, allowed.data


@override_settings(BILLING_WEBHOOK_MAX_AGE_SECONDS=60)
def test_stale_billing_webhook_is_parked_not_dropped(tenant_a):
    """BB-000671 gap fix: a delayed-but-legitimate retry must be recoverable,
    not silently dropped -- it is parked to the DLQ like any other
    post-signature failure so an owner/operator can replay it."""
    plan, sub = _subscribe(tenant_a.company, slug="stale")
    sub.razorpay_subscription_id = "sub_stale"
    sub.save(update_fields=["razorpay_subscription_id"])
    client = APIClient()
    resp = client.post(
        "/api/v1/billing/razorpay/webhook/",
        {
            "event": "subscription.halted",
            "created_at": 1,
            "payload": {"subscription": {"entity": {"id": "sub_stale", "status": "halted", "created_at": 1}}},
        },
        format="json",
        HTTP_X_BIZBOARD_TEST_WEBHOOK="1",
    )
    assert resp.status_code == 200, resp.data
    assert resp.data.get("parked") is True
    dead_letter_id = resp.data["dead_letter_id"]
    event = DeadLetterEvent.objects.get(pk=dead_letter_id)
    assert event.company_id == tenant_a.company.id
    assert event.status == DeadLetterEvent.Status.PENDING
    assert "Stale" in event.error
    # The subscription itself must not have been silently updated from a
    # stale payload -- it's parked for a human to confirm and replay.
    sub.refresh_from_db()
    assert sub.status == Subscription.Status.ACTIVE


def test_out_of_order_billing_webhook_ignored(tenant_a):
    plan, sub = _subscribe(tenant_a.company, slug="ooo")
    sub.razorpay_subscription_id = "sub_ooo_1"
    sub.save(update_fields=["razorpay_subscription_id"])
    client = APIClient()
    newer = client.post(
        "/api/v1/billing/razorpay/webhook/",
        {
            "event": "subscription.activated",
            "created_at": 2_000,
            "payload": {
                "subscription": {
                    "entity": {"id": "sub_ooo_1", "status": "active", "created_at": 2_000}
                }
            },
        },
        format="json",
        HTTP_X_BIZBOARD_TEST_WEBHOOK="1",
    )
    assert newer.status_code == 200, newer.data
    older = client.post(
        "/api/v1/billing/razorpay/webhook/",
        {
            "event": "subscription.halted",
            "created_at": 1_000,
            "payload": {
                "subscription": {
                    "entity": {"id": "sub_ooo_1", "status": "halted", "created_at": 1_000}
                }
            },
        },
        format="json",
        HTTP_X_BIZBOARD_TEST_WEBHOOK="1",
    )
    assert older.status_code == 200, older.data
    assert older.data.get("reason") == "out_of_order"
    sub.refresh_from_db()
    assert sub.status == Subscription.Status.ACTIVE


def test_webhook_processing_error_parks_dlq_and_owner_replays(tenant_a):
    plan, sub = _subscribe(tenant_a.company, slug="dlq")
    sub.razorpay_subscription_id = "sub_dlq_1"
    sub.save(update_fields=["razorpay_subscription_id"])
    client = APIClient()
    with patch(
        "billing.views.apply_razorpay_subscription_status",
        side_effect=RuntimeError("simulated processor crash"),
    ):
        resp = client.post(
            "/api/v1/billing/razorpay/webhook/",
            {
                "event": "subscription.halted",
                "id": "evt_dlq_1",
                "payload": {
                    "subscription": {"entity": {"id": "sub_dlq_1", "status": "halted"}}
                },
            },
            format="json",
            HTTP_X_BIZBOARD_TEST_WEBHOOK="1",
        )
    assert resp.status_code == 200, resp.data
    assert resp.data.get("parked") is True
    parked = DeadLetterEvent.objects.get(pk=resp.data["dead_letter_id"])
    assert parked.status == DeadLetterEvent.Status.PENDING
    assert parked.company_id == tenant_a.company.id

    listed = tenant_a.client.get("/api/v1/billing/dlq/")
    assert listed.status_code == 200
    assert any(row["id"] == parked.pk for row in listed.data)

    staff = tenant_a.staff_client.get("/api/v1/billing/dlq/")
    assert staff.status_code == 403

    checkout = tenant_a.staff_client.post(
        "/api/v1/billing/checkout/", {"plan_id": plan.id}, format="json"
    )
    assert checkout.status_code == 403

    replayed = tenant_a.client.post(f"/api/v1/billing/dlq/{parked.pk}/replay/")
    assert replayed.status_code == 200, replayed.data
    parked.refresh_from_db()
    assert parked.status == DeadLetterEvent.Status.REPLAYED
    sub.refresh_from_db()
    assert sub.status == Subscription.Status.PAST_DUE


def test_replay_dead_letter_management_command(tenant_a):
    plan, sub = _subscribe(tenant_a.company, slug="dlq-cmd")
    sub.razorpay_subscription_id = "sub_dlq_cmd"
    sub.save(update_fields=["razorpay_subscription_id"])
    event = DeadLetterEvent.objects.create(
        company=tenant_a.company,
        provider="razorpay_subscription",
        event_id="evt_cmd",
        payload={"payload": {"subscription": {"entity": {"id": "sub_dlq_cmd", "status": "active"}}}},
        error="parked",
        status=DeadLetterEvent.Status.PENDING,
        attempts=1,
    )
    call_command("replay_dead_letter", event.pk, user_id=tenant_a.owner.pk)
    event.refresh_from_db()
    assert event.status == DeadLetterEvent.Status.REPLAYED
    sub.refresh_from_db()
    assert sub.status == Subscription.Status.ACTIVE


def test_assert_complete_allowed_helpcode(tenant_a):
    from billing.quotas import assert_complete_allowed
    from core.exceptions import exception_error_code
    from sales.models import SalesInvoice

    _subscribe(tenant_a.company, slug="unit-q", monthly_complete_limit=1)
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    with pytest.raises(BusinessRuleError) as exc:
        assert_complete_allowed(tenant_a.company)
    assert exception_error_code(exc.value) == HelpCode.PLAN_QUOTA_EXCEEDED
    assert SalesInvoice.objects.filter(company=tenant_a.company, status=SalesInvoice.Status.COMPLETED).count() == 1


def test_sales_complete_is_company_throttled(tenant_a):
    from unittest.mock import patch

    from core.throttles import CompanyRateThrottle

    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv1 = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}]
    )
    inv2 = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}]
    )
    with patch.object(CompanyRateThrottle, "get_rate", return_value="1/min"):
        first = tenant_a.client.post(f"/api/v1/sales/invoices/{inv1['id']}/complete/")
        second = tenant_a.client.post(f"/api/v1/sales/invoices/{inv2['id']}/complete/")
    assert first.status_code == 200, first.data
    assert second.status_code == 429, second.data


@override_settings(SANDBOX_WEBHOOK_SECRET="test-sandbox-webhook-secret", DJANGO_ENV="test")
def test_payment_webhook_parks_unexpected_error_and_replays(tenant_a):
    import json
    from decimal import Decimal
    from unittest.mock import patch

    from django.test import Client

    from billing.models import DeadLetterEvent
    from billing.services import replay_dead_letter
    from payments.models import PaymentLinkStatus
    from payments.services import PaymentService
    from tests.test_payment_webhook_adversarial import _sandbox_sig
    from tests.test_phase3_payments import _complete_invoice

    inv, customer = _complete_invoice(tenant_a)
    link = PaymentService.create_payment_link(
        company=tenant_a.company,
        amount=Decimal("1000"),
        sales_invoice=inv,
        customer=customer,
        provider="sandbox",
        public_base_url="http://testserver",
    )
    body_dict = {
        "payment_id": "pay_dlq_park",
        "amount": "100000",
        "fee": "0",
        "status": "CAPTURED",
        "payment_link_id": link.provider_link_id,
    }
    raw = json.dumps(body_dict).encode()
    sig = _sandbox_sig(raw, company_id=tenant_a.company.id)
    with patch(
        "payments.webhook_views.PaymentService.finalize_gateway_payment",
        side_effect=RuntimeError("processor crash"),
    ):
        parked = Client().post(
            f"/api/v1/webhooks/payments/sandbox/?company_id={tenant_a.company.id}",
            data=raw,
            content_type="application/json",
            HTTP_X_SANDBOX_SIGNATURE=sig,
        )
    assert parked.status_code == 202, parked.content
    event = DeadLetterEvent.objects.get(payload__kind="payment_webhook")
    assert event.status == DeadLetterEvent.Status.PENDING
    replay_dead_letter(event, user=tenant_a.owner)
    event.refresh_from_db()
    assert event.status == DeadLetterEvent.Status.REPLAYED
    link.refresh_from_db()
    assert link.status == PaymentLinkStatus.PAID
