"""Regression tests for bugs found in the FMEA implementation review."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from core.models import Notification
from masters.models import Customer


def _urlopen_returning(rows):
    resp = MagicMock()
    resp.read.return_value = json.dumps({"transactions": rows}).encode()
    resp.__enter__.return_value = resp
    return resp


def test_live_fiu_fetch_skips_nan_and_bad_dates(settings):
    from banking.fiu_adapter import fetch_live_transactions_for_consent

    settings.FIU_BASE_URL = "https://fiu.example"
    rows = [
        {"txn_id": "ok", "amount": "10.50", "txn_date": "2026-10-01"},
        {"txn_id": "nan", "amount": "NaN", "txn_date": "2026-10-01"},
        {"txn_id": "inf", "amount": "Infinity", "txn_date": "2026-10-01"},
        {"txn_id": "baddate", "amount": "5", "txn_date": "2026-13-45"},
        {"txn_id": "datekey", "amount": "7", "date": "2026-09-30"},
    ]
    with patch("urllib.request.urlopen", return_value=_urlopen_returning(rows)):
        out = fetch_live_transactions_for_consent(consent_id="c1", fi_type="DEPOSIT", api_key="tok")
    by_id = {t.txn_id: t for t in out}
    assert set(by_id) == {"ok", "baddate", "datekey"}
    assert by_id["ok"].amount == Decimal("10.50")
    assert by_id["ok"].txn_date == date(2026, 10, 1)
    assert by_id["datekey"].txn_date == date(2026, 9, 30)
    assert by_id["ok"].raw["ingest_source"] == "fiu"
    assert by_id["ok"].raw["consent_id"] == "c1"


def test_client_rows_cannot_claim_fiu_source(tenant_a, settings):
    from banking.fiu_adapter import MockFiTransaction
    from banking.models import AaConsent, AaTransaction

    settings.ENABLE_ACCOUNT_AGGREGATOR = True
    tenant_a.company.feature_flags = {"ENABLE_ACCOUNT_AGGREGATOR": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    AaConsent.objects.create(
        company=tenant_a.company, consent_id="live-1", status=AaConsent.Status.ACTIVE,
        fi_type="DEPOSIT", created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    live_row = MockFiTransaction(
        txn_id="live-t1", amount=Decimal("1.00"), txn_date=date(2026, 10, 1),
        narration="", raw={"ingest_source": "fiu"},
    )
    with patch("banking.fiu_adapter.company_fiu_api_key", return_value="tok"), patch(
        "banking.views.fetch_live_transactions_for_consent", return_value=[live_row],
    ):
        resp = tenant_a.client.post(
            "/api/v1/banking/aa/ingest/",
            {
                "consent_id": "live-1",
                "use_live_fiu": True,
                "transactions": [{
                    "txn_id": "spoof-1", "amount": "2.00", "txn_date": "2026-10-01",
                    "raw": {"ingest_source": "fiu"},
                }, {
                    "txn_id": "bare-1", "amount": "3.00", "txn_date": "2026-10-01",
                }],
            },
            format="json",
        )
    assert resp.status_code == 201, resp.data
    get = lambda t: AaTransaction.objects.get(company=tenant_a.company, txn_id=t).raw  # noqa: E731
    assert get("spoof-1")["ingest_source"] == "client"
    assert get("live-t1")["ingest_source"] == "fiu"
    # A client row with no raw block keeps its own fields.
    assert get("bare-1")["amount"] == "3.00"
    assert get("bare-1")["ingest_source"] == "client"


@pytest.mark.parametrize("opted_in, customer_phone, proposed_phone, expect_cloud", [
    (True, "9876543210", "", True),
    (True, "", "9123456789", False),  # opted in, but no stored number: not a Cloud send
    (False, "9876543210", "", False),
])
def test_assistant_whatsapp_reminder_cloud_only_to_stored_opted_in_phone(
    tenant_a, opted_in, customer_phone, proposed_phone, expect_cloud,
):
    from insights.assistant import confirm_proposed_action
    from insights.models import AssistantMessage, AssistantThread

    cust = Customer.objects.create(
        company=tenant_a.company, name="Wa Cust", state="Karnataka",
        phone=customer_phone, whatsapp_opt_in=opted_in,
    )
    thread = AssistantThread.objects.create(company=tenant_a.company, created_by=tenant_a.owner)
    msg = AssistantMessage.objects.create(
        thread=thread, role=AssistantMessage.Role.ASSISTANT, content="x",
        proposed_action={
            "type": "send_reminder", "text": "Please pay", "customer_id": cust.id,
            "phone": proposed_phone,
        },
    )
    with patch("core.services.whatsapp.build_feature_flags", return_value={"ENABLE_WHATSAPP_CLOUD": True}), patch(
        "core.services.whatsapp._resolve_whatsapp_credentials", return_value=("tok", "12345"),
    ), patch("core.services.whatsapp.requests.post") as post:
        post.return_value = MagicMock(status_code=500, text="x", json=lambda: {})
        result = confirm_proposed_action(tenant_a.company, tenant_a.owner, message_id=msg.id)
    # The send must not raise (it used to TypeError on an unknown kwarg).
    assert result["requires_user_share"] is True
    assert Notification.objects.filter(company=tenant_a.company).exists()
    assert (post.called) is expect_cloud


def test_gaps_command_ignores_non_lifecycle_audit_rows(tenant_a):
    from io import StringIO

    from django.core.management import call_command

    from core.models import AuditEvent
    from core.services.audit import AuditService
    from sales.models import SalesInvoice

    customer = Customer.objects.create(company=tenant_a.company, name="Gap Cust", state="Karnataka")
    invoice = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, invoice_type="NON_GST",
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    SalesInvoice.objects.filter(pk=invoice.pk).update(status=SalesInvoice.Status.COMPLETED)
    # A CREATE row is not proof the completion was audited.
    AuditService.log(
        action="CREATE", company=tenant_a.company, user=tenant_a.owner,
        entity_type="SalesInvoice", entity_id=invoice.pk, description="created",
    )
    out = StringIO()
    call_command("fmea2_existing_gaps", stdout=out)
    assert f"company={tenant_a.company.id} count=1" in out.getvalue().split(
        "SalesInvoice_completed_without_audit"
    )[1].split("PurchaseInvoice")[0]
    call_command("fmea2_existing_gaps", "--apply", stdout=StringIO())
    assert AuditEvent.objects.filter(
        company=tenant_a.company, entity_type="SalesInvoice", entity_id=str(invoice.pk),
        description__startswith="backfill:",
    ).count() == 1
    # Idempotent.
    call_command("fmea2_existing_gaps", "--apply", stdout=StringIO())
    assert AuditEvent.objects.filter(
        company=tenant_a.company, entity_type="SalesInvoice", entity_id=str(invoice.pk),
        description__startswith="backfill:",
    ).count() == 1
