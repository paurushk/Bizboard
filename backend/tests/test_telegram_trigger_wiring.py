"""The three v1 trigger sites also fan out to linked staff via Telegram:
expiry alerts, overdue-dunning reminders, and gateway payment capture.

Each of these calls ``core.services.telegram.notify_company_owners``
best-effort alongside its existing email/customer-facing send — these tests
prove the wiring fires (and stays silent when unlinked/disabled), not the
underlying alert/dunning/payment logic itself (covered elsewhere).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest import mock
from zoneinfo import ZoneInfo

import pytest
from django.test import Client, override_settings

from tests.test_a07_dunning import _enable_dunning, _overdue_invoice
from tests.test_payment_webhook_adversarial import _sandbox_sig
from tests.test_phase3_payments import _complete_invoice

pytestmark = pytest.mark.django_db

IST = ZoneInfo("Asia/Kolkata")


def _make_expiry_row(product, batch, warehouse, *, days_to_expiry=5):
    return {
        "id": batch.id,
        "product_name": product.name,
        "batch": batch.id,
        "batch_no": batch.batch_no,
        "expiry_date": batch.expiry_date,
        "manufacturing_date": None,
        "warehouse": warehouse.id,
        "warehouse_name": warehouse.name,
        "on_hand": "10",
        "days_to_expiry": days_to_expiry,
        "expired": days_to_expiry < 0,
    }


# --- expiry alert ------------------------------------------------------------


@override_settings(ENABLE_TELEGRAM=True, TELEGRAM_BOT_TOKEN="dummy-token")
def test_expiry_alert_notifies_linked_owner_via_telegram(tenant_a):
    from core.models import Notification
    from inventory.item_stock import record_expiry_bands
    from inventory.models import BatchLot, Warehouse
    from masters.models import Product

    tenant_a.owner.telegram_chat_id = "42"
    tenant_a.owner.save(update_fields=["telegram_chat_id"])

    warehouse = Warehouse.objects.create(company=tenant_a.company, name="Main", code="MAIN", is_default=True)
    product = Product.objects.create(
        company=tenant_a.company, name="Paracetamol", sku="PARA-1",
        gst_rate=Decimal("12"), purchase_price=Decimal("10"), selling_price=Decimal("20"),
    )
    batch = BatchLot.objects.create(
        company=tenant_a.company, product=product, batch_no="B1",
        expiry_date=date.today() + timedelta(days=5),
    )
    row = _make_expiry_row(product, batch, warehouse)

    with mock.patch("core.services.telegram.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        record_expiry_bands(tenant_a.company, [row], bands=(7, 30, 60, 90))

    assert mock_post.called
    assert Notification.objects.filter(
        company=tenant_a.company, channel=Notification.Channel.TELEGRAM
    ).exists()


def test_expiry_alert_skips_telegram_when_flag_disabled(tenant_a):
    from core.models import Notification
    from inventory.item_stock import record_expiry_bands
    from inventory.models import BatchLot, Warehouse
    from masters.models import Product

    tenant_a.owner.telegram_chat_id = "42"
    tenant_a.owner.save(update_fields=["telegram_chat_id"])

    warehouse = Warehouse.objects.create(company=tenant_a.company, name="Main", code="MAIN", is_default=True)
    product = Product.objects.create(
        company=tenant_a.company, name="Paracetamol", sku="PARA-2",
        gst_rate=Decimal("12"), purchase_price=Decimal("10"), selling_price=Decimal("20"),
    )
    batch = BatchLot.objects.create(
        company=tenant_a.company, product=product, batch_no="B2",
        expiry_date=date.today() + timedelta(days=5),
    )
    row = _make_expiry_row(product, batch, warehouse)

    with mock.patch("core.services.telegram.requests.post") as mock_post:
        record_expiry_bands(tenant_a.company, [row], bands=(7, 30, 60, 90))
        mock_post.assert_not_called()
    assert not Notification.objects.filter(channel=Notification.Channel.TELEGRAM).exists()


# --- overdue dunning reminder ------------------------------------------------


@override_settings(ENABLE_TELEGRAM=True, TELEGRAM_BOT_TOKEN="dummy-token")
def test_dunning_reminder_sent_notifies_owner_via_telegram(tenant_a):
    from core.models import Notification
    from payments.dunning import run_dunning_for_company

    tenant_a.owner.telegram_chat_id = "555"
    tenant_a.owner.save(update_fields=["telegram_chat_id"])

    invoice = _overdue_invoice(tenant_a, days=3)
    _enable_dunning(invoice.company)
    midday = datetime(2026, 8, 31, 12, 0, tzinfo=IST)

    with mock.patch("core.services.telegram.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        result = run_dunning_for_company(invoice.company, now=midday)

    assert result["sent"] == 1
    assert mock_post.called
    assert Notification.objects.filter(
        company=invoice.company,
        channel=Notification.Channel.TELEGRAM,
        subject="Overdue reminder sent",
    ).exists()


def test_dunning_reminder_skips_telegram_when_flag_disabled(tenant_a):
    from core.models import Notification
    from payments.dunning import run_dunning_for_company

    tenant_a.owner.telegram_chat_id = "555"
    tenant_a.owner.save(update_fields=["telegram_chat_id"])

    invoice = _overdue_invoice(tenant_a, days=3)
    _enable_dunning(invoice.company)
    midday = datetime(2026, 8, 31, 12, 0, tzinfo=IST)

    with mock.patch("core.services.telegram.requests.post") as mock_post:
        result = run_dunning_for_company(invoice.company, now=midday)
        mock_post.assert_not_called()

    assert result["sent"] == 1  # the customer-facing reminder still went out
    assert not Notification.objects.filter(channel=Notification.Channel.TELEGRAM).exists()


# --- gateway payment capture --------------------------------------------------


@override_settings(
    ENABLE_TELEGRAM=True,
    TELEGRAM_BOT_TOKEN="dummy-token",
    SANDBOX_WEBHOOK_SECRET="test-sandbox-webhook-secret",
    DJANGO_ENV="test",
)
def test_payment_captured_webhook_notifies_owner_via_telegram(tenant_a):
    from core.models import Notification
    from payments.services import PaymentService

    tenant_a.owner.telegram_chat_id = "888"
    tenant_a.owner.save(update_fields=["telegram_chat_id"])

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
        "payment_id": "pay_telegram_test",
        "amount": "100000",
        "fee": "0",
        "status": "CAPTURED",
        "payment_link_id": link.provider_link_id,
    }
    raw = json.dumps(body_dict).encode()
    sig = _sandbox_sig(raw, company_id=tenant_a.company.id)

    with mock.patch("core.services.telegram.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        resp = Client().post(
            f"/api/v1/webhooks/payments/sandbox/?company_id={tenant_a.company.id}",
            data=raw,
            content_type="application/json",
            HTTP_X_SANDBOX_SIGNATURE=sig,
        )

    assert resp.status_code == 200
    assert mock_post.called
    assert Notification.objects.filter(
        company=tenant_a.company,
        channel=Notification.Channel.TELEGRAM,
        subject="Payment received",
    ).exists()


@override_settings(SANDBOX_WEBHOOK_SECRET="test-sandbox-webhook-secret", DJANGO_ENV="test")
def test_payment_captured_webhook_skips_telegram_when_flag_disabled(tenant_a):
    from core.models import Notification
    from payments.services import PaymentService

    tenant_a.owner.telegram_chat_id = "888"
    tenant_a.owner.save(update_fields=["telegram_chat_id"])

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
        "payment_id": "pay_telegram_test_2",
        "amount": "100000",
        "fee": "0",
        "status": "CAPTURED",
        "payment_link_id": link.provider_link_id,
    }
    raw = json.dumps(body_dict).encode()
    sig = _sandbox_sig(raw, company_id=tenant_a.company.id)

    with mock.patch("core.services.telegram.requests.post") as mock_post:
        resp = Client().post(
            f"/api/v1/webhooks/payments/sandbox/?company_id={tenant_a.company.id}",
            data=raw,
            content_type="application/json",
            HTTP_X_SANDBOX_SIGNATURE=sig,
        )
        mock_post.assert_not_called()

    assert resp.status_code == 200
    assert not Notification.objects.filter(channel=Notification.Channel.TELEGRAM).exists()
