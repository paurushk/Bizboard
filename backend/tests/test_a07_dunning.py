"""A-07: AR dunning cadence — default off, skip paid / gateway-holding."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from payments.dunning import run_dunning_for_company
from payments.models import DunningReminder, GatewayPayment, GatewayPaymentStatus, PaymentLink, PaymentLinkStatus
from sales.models import SalesInvoice
from tests.test_pdf_and_share import _complete

pytestmark = pytest.mark.django_db

IST = ZoneInfo("Asia/Kolkata")


def _overdue_invoice(tenant, *, days=3, as_of=None, **customer_kwargs):
    as_of = as_of or date(2026, 8, 31)
    data, _ = _complete(tenant, customer_kwargs=customer_kwargs)
    invoice = SalesInvoice.objects.get(pk=data["id"])
    invoice.due_date = as_of - timedelta(days=days)
    invoice.save(update_fields=["due_date"])
    return invoice


def _enable_dunning(company, **kwargs):
    company.dunning_enabled = True
    company.dunning_days = kwargs.get("days", [3, 7, 14])
    company.dunning_max_reminders = kwargs.get("max_reminders", 3)
    company.dunning_quiet_hours_start = kwargs.get("quiet_start", 21)
    company.dunning_quiet_hours_end = kwargs.get("quiet_end", 8)
    company.save(
        update_fields=[
            "dunning_enabled",
            "dunning_days",
            "dunning_max_reminders",
            "dunning_quiet_hours_start",
            "dunning_quiet_hours_end",
        ]
    )


def test_dunning_default_off(tenant_a):
    invoice = _overdue_invoice(tenant_a)
    result = run_dunning_for_company(invoice.company)
    assert result["sent"] == 0
    assert result["reason"] == "disabled"
    assert DunningReminder.objects.count() == 0


def test_due_invoice_one_reminder_per_day(tenant_a):
    invoice = _overdue_invoice(tenant_a, days=3)
    _enable_dunning(invoice.company)
    midday = datetime(2026, 8, 31, 12, 0, tzinfo=IST)
    first = run_dunning_for_company(invoice.company, now=midday)
    assert first["sent"] == 1
    assert DunningReminder.objects.filter(invoice=invoice, status="SENT").count() == 1
    second = run_dunning_for_company(invoice.company, now=midday)
    assert second["sent"] == 0
    assert DunningReminder.objects.filter(invoice=invoice).count() == 1


def test_paid_invoice_not_dunned(tenant_a):
    invoice = _overdue_invoice(tenant_a, days=3)
    _enable_dunning(invoice.company)
    receipt = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": invoice.customer_id, "amount": str(invoice.grand_total), "mode": "CASH"},
        format="json",
    )
    assert receipt.status_code in (200, 201), receipt.data
    alloc = tenant_a.client.post(
        "/api/v1/payments/allocations/",
        {
            "receipt": receipt.data["id"],
            "sales_invoice": invoice.id,
            "amount": str(invoice.grand_total),
        },
        format="json",
    )
    assert alloc.status_code in (200, 201), alloc.data
    midday = datetime(2026, 8, 31, 12, 0, tzinfo=IST)
    result = run_dunning_for_company(invoice.company, now=midday)
    assert result["sent"] == 0
    assert not DunningReminder.objects.filter(invoice=invoice, status="SENT").exists()


def test_holding_gateway_capture_not_dunned(tenant_a):
    invoice = _overdue_invoice(tenant_a, days=3)
    _enable_dunning(invoice.company)
    link = PaymentLink.objects.create(
        company=invoice.company,
        sales_invoice=invoice,
        customer=invoice.customer,
        amount=invoice.grand_total,
        token="dunning-hold-a07",
        status=PaymentLinkStatus.CREATED,
    )
    GatewayPayment.objects.create(
        company=invoice.company,
        provider="sandbox",
        provider_payment_id="pay_dunning_hold",
        amount=invoice.grand_total,
        status=GatewayPaymentStatus.CAPTURED_PENDING_BOOKS,
        payment_link=link,
    )
    midday = datetime(2026, 8, 31, 12, 0, tzinfo=IST)
    result = run_dunning_for_company(invoice.company, now=midday)
    assert result["sent"] == 0


def test_customer_opt_out_skips(tenant_a):
    invoice = _overdue_invoice(tenant_a, days=3, dunning_opt_out=True)
    _enable_dunning(invoice.company)
    midday = datetime(2026, 8, 31, 12, 0, tzinfo=IST)
    result = run_dunning_for_company(invoice.company, now=midday)
    assert result["sent"] == 0


def test_collection_risk_api(tenant_a):
    invoice = _overdue_invoice(tenant_a, days=10)
    resp = tenant_a.client.get(f"/api/v1/payments/collection-risk/{invoice.customer_id}/")
    assert resp.status_code == 200, resp.data
    assert Decimal(str(resp.data["overdue_amount"])) > 0
    assert resp.data["recommended_next_step"]
    assert resp.data["collection_status"]
