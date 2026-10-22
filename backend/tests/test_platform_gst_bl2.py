"""WP-BL2: every Razorpay subscription charge produces one Bizboard GST invoice."""

import hashlib
import hmac
import json
import threading
from datetime import date
from decimal import Decimal
from unittest import mock

import pytest
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from rest_framework.test import APIClient

from billing.models import Plan, PlatformGstInvoice, Subscription
from billing.platform_gst import financial_year, issue_platform_credit_note, issue_platform_gst_invoice
from core.exceptions import BusinessRuleError

_SECRET = "bl2-webhook-secret"
URL = "/api/v1/billing/razorpay/webhook/"


@pytest.fixture(autouse=True)
def _clean():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def subscribed(tenant_a):
    plan = Plan.objects.create(name="Pro BL2", slug="pro-bl2", price_paise=118000)
    Subscription.objects.update_or_create(
        company=tenant_a.company,
        defaults={"plan": plan, "status": Subscription.Status.ACTIVE, "razorpay_subscription_id": "sub_bl2"},
    )
    company = tenant_a.company
    company.state = "Maharashtra"
    company.gstin = "27AAAPL1234C1Z5"
    company.gstin_legal_name = "Alpha Traders Private Limited"
    company.save(update_fields=["state", "gstin", "gstin_legal_name"])
    return tenant_a


def _charged(payment_id="pay_1", *, created_at=1_800_000_000, amount=118000, status="active"):
    return json.dumps({
        "event": "subscription.charged",
        "created_at": created_at,
        "payload": {
            "subscription": {"entity": {"id": "sub_bl2", "status": status}},
            "payment": {"entity": {"id": payment_id, "amount": amount, "status": "captured"}},
        },
    }).encode()


def _status_event(status, *, created_at):
    return json.dumps({
        "event": f"subscription.{status}",
        "created_at": created_at,
        "payload": {"subscription": {"entity": {"id": "sub_bl2", "status": status}}},
    }).encode()


def _post(body, event_id):
    sig = hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return APIClient().post(
        URL, data=body, content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=sig, HTTP_X_RAZORPAY_EVENT_ID=event_id,
    )


@override_settings(RAZORPAY_WEBHOOK_SECRET=_SECRET, BILLING_WEBHOOK_MAX_AGE_SECONDS=0,
                   PLATFORM_STATE="Karnataka", PLATFORM_GSTIN="29AAACB0000A1Z5")
def test_a_charge_issues_one_invoice_with_buyer_details(subscribed):
    assert _post(_charged(), "evt_1").status_code == 200
    assert _post(_charged(), "evt_1").status_code == 200  # replay of the same event
    assert _post(_charged(), "evt_2").status_code == 200  # same payment, new event id
    rows = PlatformGstInvoice.objects.filter(company=subscribed.company)
    assert rows.count() == 1
    inv = rows.get()
    assert inv.provider == "razorpay" and inv.capture_id == "pay_1"
    assert inv.total == Decimal("1180.00") and inv.igst == Decimal("180.00") and inv.cgst == 0
    assert inv.buyer_gstin == "27AAAPL1234C1Z5"
    assert inv.buyer_legal_name == "Alpha Traders Private Limited"
    assert inv.place_of_supply == "Maharashtra" and inv.sac_code == "998314"
    assert inv.number.startswith("BB") and len(inv.number) <= 16


@override_settings(RAZORPAY_WEBHOOK_SECRET=_SECRET, BILLING_WEBHOOK_MAX_AGE_SECONDS=0)
def test_a_late_charge_is_still_invoiced_but_does_not_move_status_back(subscribed):
    assert _post(_status_event("halted", created_at=1_800_000_100), "evt_h").status_code == 200
    sub = Subscription.objects.get(company=subscribed.company)
    halted_status = sub.status
    # The charge happened earlier but is delivered after the halt.
    resp = _post(_charged("pay_late", created_at=1_800_000_000), "evt_late")
    assert resp.status_code == 200
    assert resp.json()["data"]["reason"] == "out_of_order"
    assert PlatformGstInvoice.objects.filter(capture_id="pay_late").count() == 1
    sub.refresh_from_db()
    assert sub.status == halted_status


@override_settings(RAZORPAY_WEBHOOK_SECRET="", DJANGO_ENV="test", BILLING_RECON_IN_TESTS=True,
                   RAZORPAY_KEY_ID="rzp_k", RAZORPAY_KEY_SECRET="rzp_s")
def test_recon_issues_invoices_for_charges_a_lost_webhook_missed(subscribed):
    from billing.recon import reconcile_saas_subscriptions

    issue_platform_gst_invoice(subscribed.company, provider="razorpay", capture_id="pay_seen", amount="1180")
    charges = [
        {"payment_id": "pay_seen", "amount": Decimal("1180")},
        {"payment_id": "pay_missed", "amount": Decimal("1180")},
    ]
    with mock.patch("billing.recon.fetch_razorpay_subscription", return_value={"status": "active"}), \
         mock.patch("billing.recon.fetch_razorpay_paid_charges", return_value=charges):
        result = reconcile_saas_subscriptions()
        again = reconcile_saas_subscriptions()
    assert result["invoiced"] == 1 and again["invoiced"] == 0
    assert set(PlatformGstInvoice.objects.values_list("capture_id", flat=True)) == {"pay_seen", "pay_missed"}


@override_settings(PLATFORM_STATE="Maharashtra")
def test_same_state_splits_cgst_sgst_and_b2c_has_no_gstin(tenant_a):
    company = tenant_a.company
    company.state = "Maharashtra"
    company.gstin = ""
    company.save(update_fields=["state", "gstin"])
    inv = issue_platform_gst_invoice(company, provider="razorpay", capture_id="pay_b2c", amount="118.00")
    assert inv.cgst == inv.sgst == Decimal("9.00") and inv.igst == 0
    assert inv.buyer_gstin == "" and inv.buyer_legal_name == company.name


def test_credit_notes_point_at_the_invoice_and_cannot_exceed_it(tenant_a):
    inv = issue_platform_gst_invoice(tenant_a.company, provider="razorpay", capture_id="pay_r", amount="1180")
    cn = issue_platform_credit_note(inv, refund_id="rfnd_1", amount="590")
    assert cn.kind == PlatformGstInvoice.Kind.CREDIT_NOTE and cn.original_id == inv.id
    assert cn.number.startswith("BC")
    assert issue_platform_credit_note(inv, refund_id="rfnd_1", amount="590").pk == cn.pk
    with pytest.raises(BusinessRuleError):
        issue_platform_credit_note(inv, refund_id="rfnd_2", amount="600")


def test_numbers_run_per_financial_year_without_gaps(tenant_a, tenant_b):
    a = issue_platform_gst_invoice(tenant_a.company, provider="razorpay", capture_id="p1", amount="118")
    b = issue_platform_gst_invoice(tenant_b.company, provider="razorpay", capture_id="p2", amount="118")
    again = issue_platform_gst_invoice(tenant_a.company, provider="razorpay", capture_id="p1", amount="118")
    seq_a, seq_b = int(a.number.split("-")[1]), int(b.number.split("-")[1])
    assert seq_b == seq_a + 1  # Bizboard-wide series across tenants
    assert again.number == a.number
    assert financial_year(date(2026, 3, 31)) == "2025-26"
    assert financial_year(date(2026, 4, 1)) == "2026-27"


def test_owner_lists_their_invoices(subscribed):
    issue_platform_gst_invoice(subscribed.company, provider="razorpay", capture_id="pay_list", amount="1180")
    resp = subscribed.client.get("/api/v1/billing/invoices/")
    assert resp.status_code == 200
    rows = resp.json()["data"]
    assert rows[0]["number"].startswith("BB") and rows[0]["buyerGstin"] == "27AAAPL1234C1Z5"


@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
def test_concurrent_captures_never_share_or_skip_a_number(tenant_a):
    if connection.vendor != "postgresql":
        pytest.skip("row locks need Postgres")
    errors = []

    def one(i):
        try:
            issue_platform_gst_invoice(tenant_a.company, provider="razorpay", capture_id=f"pc{i}", amount="118")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=one, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    nums = sorted(int(n.split("-")[1]) for n in PlatformGstInvoice.objects.values_list("number", flat=True))
    assert nums == list(range(nums[0], nums[0] + 8))


def test_owner_downloads_a_pdf_of_each_invoice_and_credit_note(tenant_a, tenant_b):
    from billing.platform_gst import issue_platform_credit_note, issue_platform_gst_invoice

    inv = issue_platform_gst_invoice(tenant_a.company, provider="razorpay", capture_id="pay_pdf1", amount="1180")
    cn = issue_platform_credit_note(inv, refund_id="rfnd_pdf1", amount="118")
    for row in (inv, cn):
        resp = tenant_a.client.get(f"/api/v1/billing/invoices/{row.pk}/pdf/")
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")
        assert row.number in resp["Content-Disposition"]
    # Another company's invoice is not reachable.
    assert tenant_b.client.get(f"/api/v1/billing/invoices/{inv.pk}/pdf/").status_code == 404
