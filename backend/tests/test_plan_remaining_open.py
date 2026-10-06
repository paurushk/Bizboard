"""End-to-end coverage for the items that were still open in code."""

import time
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from billing.platform_gst import issue_platform_gst_invoice
from crm.pipeline import DedupePrompt, capture_lead


def test_duplicate_lead_is_matched_and_not_created_silently(tenant_a):
    first = capture_lead(
        tenant_a.company, tenant_a.owner, name="Asha", phone="9999900011", manual=True,
    )
    with pytest.raises(DedupePrompt):
        capture_lead(
            tenant_a.company, tenant_a.owner, name="Asha Two", phone="9999900011", manual=True,
        )
    second = capture_lead(
        tenant_a.company, tenant_a.owner, name="Asha Two", phone="9999900011",
        manual=True, dedupe_decision="review",
    )
    assert second.dedupe_matched_lead_id == first.id
    assert second.pk != first.pk


def test_cashfree_capture_issues_one_gst_invoice_and_payu_is_idempotent(tenant_a):
    tenant_a.company.state = "Maharashtra"
    tenant_a.company.email = "owner@alpha.test"
    tenant_a.company.save(update_fields=["state", "email"])
    with override_settings(PLATFORM_STATE="Karnataka", PLATFORM_GSTIN="29AAAAA0000A1Z5"):
        first = issue_platform_gst_invoice(
            tenant_a.company, provider="cashfree", capture_id="cf_1", amount=Decimal("118.00"),
            user=tenant_a.owner,
        )
        again = issue_platform_gst_invoice(
            tenant_a.company, provider="cashfree", capture_id="cf_1", amount=Decimal("118.00"),
            user=tenant_a.owner,
        )
    assert first.pk == again.pk
    assert first.igst == Decimal("18.00")
    assert first.place_of_supply == "Maharashtra"
    assert first.platform_gstin == "29AAAAA0000A1Z5"
    assert issue_platform_gst_invoice(
        tenant_a.company, provider="razorpay", capture_id="rz_1", amount=Decimal("118.00"),
    ) is None


def test_same_state_capture_splits_cgst_and_sgst(tenant_a):
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save(update_fields=["state"])
    with override_settings(PLATFORM_STATE="Karnataka", PLATFORM_GSTIN=""):
        row = issue_platform_gst_invoice(
            tenant_a.company, provider="payu", capture_id="pu_1", amount=Decimal("118.00"),
        )
    assert row.cgst == Decimal("9.00")
    assert row.sgst == Decimal("9.00")
    assert row.igst == Decimal("0.00")


def test_twenty_signups_stay_unique_and_under_ten_seconds(db, monkeypatch):
    monkeypatch.setattr(
        "rest_framework.throttling.SimpleRateThrottle.allow_request",
        lambda self, request, view: True,
    )
    from accounts.models import Company

    client = APIClient()
    durations = []
    before = Company.objects.count()
    for i in range(20):
        email = f"load{i}@signup.test"
        started = time.perf_counter()
        otp = client.post("/api/v1/auth/register/otp/request/", {"email": email}, format="json")
        assert otp.status_code == 200, otp.data
        created = client.post("/api/v1/auth/register/", {
            "company_name": f"Load Shop {i}",
            "email": email,
            "password": "StrongPass123!",
            "state": "Karnataka",
            "otp_code": otp.data["debug_code"],
        }, format="json")
        durations.append(time.perf_counter() - started)
        assert created.status_code == 200, created.data
        assert Company.objects.filter(name=f"Load Shop {i}").count() == 1
    assert Company.objects.count() == before + 20
    durations.sort()
    p95 = durations[int(0.95 * (len(durations) - 1))]
    assert p95 <= 10


def test_cashflow_uses_settled_invoices(tenant_a):
    from payments.models import CustomerReceipt, PaymentAllocation
    from sales.models import SalesInvoice
    from tests.conftest import make_customer

    customer = make_customer(tenant_a.company, name="Payer")
    today = timezone.localdate()
    # Five invoices settled 5, 10, 12, 20 and 8 days after their due date.
    for days_late in (5, 10, 12, 20, 8):
        due = today - timedelta(days=60)
        invoice = SalesInvoice.objects.create(
            company=tenant_a.company, customer=customer, status=SalesInvoice.Status.COMPLETED,
            due_date=due, grand_total=Decimal("100"),
        )
        receipt = CustomerReceipt.objects.create(
            company=tenant_a.company, customer=customer, amount=Decimal("100"),
            receipt_date=due + timedelta(days=days_late),
        )
        PaymentAllocation.objects.create(
            company=tenant_a.company, receipt=receipt, sales_invoice=invoice, amount=Decimal("100"),
        )
    # An open invoice must not count as a settled sample.
    SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, status=SalesInvoice.Status.COMPLETED,
        due_date=today - timedelta(days=30), grand_total=Decimal("100"),
    )
    resp = tenant_a.client.get(f"/api/v1/plan/cashflow/?customer={customer.id}")
    assert resp.status_code == 200, resp.data
    assert resp.data["samples"] == 5
    assert resp.data["low_confidence"] is False


def test_pharmacy_register_pdf_names_the_patient(tenant_a):
    from masters.models import Product
    from planwave.services import assert_pharmacy_sale

    product = Product.objects.create(
        company=tenant_a.company, name="Tablet", sku="TAB-1", drug_schedule="H",
        selling_price=Decimal("10"), purchase_price=Decimal("4"),
    )
    tenant_a.company.feature_flags = {"pharmacy_enabled": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    assert_pharmacy_sale(
        company=tenant_a.company, product=product, patient_name="Meera",
        prescriber_name="Dr Iyer", prescriber_registration="TN9",
    )
    resp = tenant_a.client.get("/api/v1/plan/pharmacy/register/?layout=pdf")
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
