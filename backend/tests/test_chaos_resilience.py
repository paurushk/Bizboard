"""Chaos experiments CH-01..CH-15. A failing assertion is a resilience defect.

Experiments already locked by Phase 0 are not repeated:
CH-06 tests/test_w0_webhook_holding.py
CH-09 tests/test_fmea_mitigations.py::test_tc_fmea_007
CH-11 tests/test_fmea_mitigations.py::test_tc_fmea_004
CH-12 tests/test_fmea_mitigations.py::test_tc_fmea_013
CH-14 tests/test_fmea_mitigations.py::test_tc_fmea_010
CH-15 tests/test_imports.py::test_opening_stock_flags_already_recorded_opening
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import Client, override_settings
from django.utils import timezone

from billing.models import DeadLetterEvent
from core.idempotency import IN_FLIGHT_STATUS, IdempotencyRecord
from inventory.models import StockBalance, StockMovement
from payments.models import CustomerReceipt, PaymentLinkStatus, ProcessedWebhookEvent
from sales.models import SalesCreditNote, SalesInvoice

from .conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _draft(tenant, *, sku, price="100.00", gst="18"):
    product = make_product(tenant.company, sku=sku, gst_rate=gst, selling_price=price)
    add_stock(tenant, product, "5")
    customer = make_customer(tenant.company, phone=f"9{sku[-6:].zfill(6)}"[:10] or "9000000099")
    inv = create_draft_invoice(
        tenant, customer,
        [{"product": product.id, "quantity": "1", "unit_price": price, "gst_rate": gst}],
    )
    return inv, product


def test_ch_01_cache_flush_replays_one_complete_and_refuses_a_different_body(tenant_a):
    inv, product = _draft(tenant_a, sku="CH-01")
    url = f"/api/v1/sales/invoices/{inv['id']}/complete/"
    first = tenant_a.client.post(url, {}, format="json", HTTP_IDEMPOTENCY_KEY="ch-01")
    assert first.status_code == 200, first.data
    cache.clear()
    again = tenant_a.client.post(url, {}, format="json", HTTP_IDEMPOTENCY_KEY="ch-01")
    assert again.status_code == 200, again.data
    assert StockMovement.objects.filter(
        company=tenant_a.company, product=product, movement_type="SALE",
    ).count() == 1
    changed = tenant_a.client.post(
        url, {"unit_price": "1.00"}, format="json", HTTP_IDEMPOTENCY_KEY="ch-01",
    )
    assert changed.status_code == 422, changed.data
    assert SalesInvoice.objects.get(pk=inv["id"]).grand_total == Decimal(str(first.data["grand_total"]))


def test_ch_02_crash_during_stock_post_rolls_the_complete_back(tenant_a):
    inv, product = _draft(tenant_a, sku="CH-02", gst="0", price="50.00")
    row = SalesInvoice.objects.get(pk=inv["id"])
    before = StockBalance.objects.get(company=tenant_a.company, product=product).on_hand
    from sales.services import SalesService

    with patch(
        "sales.cogs_service.CogsService.post_sale_stock_and_cogs",
        side_effect=RuntimeError("disk vanished"),
    ):
        with pytest.raises(RuntimeError):
            SalesService.complete(row, tenant_a.owner)
    row.refresh_from_db()
    assert row.status == SalesInvoice.Status.DRAFT
    assert not (row.number or "").strip()
    assert StockBalance.objects.get(company=tenant_a.company, product=product).on_hand == before
    assert StockMovement.objects.filter(
        company=tenant_a.company, product=product, movement_type="SALE",
    ).count() == 0


def test_ch_03_a_fault_on_one_company_is_invisible_to_the_other(tenant_a, tenant_b):
    inv, product = _draft(tenant_a, sku="CH-03")
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    assert tenant_b.client.get(f"/api/v1/sales/invoices/{inv['id']}/").status_code == 404
    assert not StockBalance.objects.filter(company=tenant_b.company, product=product).exists()


@override_settings(SANDBOX_WEBHOOK_SECRET="test-sandbox-webhook-secret", DJANGO_ENV="test")
def test_ch_04_provider_retry_posts_once_and_the_dead_letter_does_not_post_again(tenant_a):
    from billing.services import replay_dead_letter
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
    body = {
        "payment_id": "pay_ch04",
        "amount": "100000",
        "fee": "0",
        "status": "CAPTURED",
        "payment_link_id": link.provider_link_id,
    }
    raw = json.dumps(body).encode()
    sig = _sandbox_sig(raw, company_id=tenant_a.company.id)
    url = f"/api/v1/webhooks/payments/sandbox/?company_id={tenant_a.company.id}"

    def _post():
        return Client().post(url, data=raw, content_type="application/json", HTTP_X_SANDBOX_SIGNATURE=sig)

    with patch(
        "payments.webhook_views.PaymentService.finalize_gateway_payment",
        side_effect=RuntimeError("processor crash"),
    ):
        parked = _post()
    assert parked.status_code == 202, parked.content
    assert ProcessedWebhookEvent.objects.count() == 0
    posted = _post()
    assert posted.status_code == 200, posted.content
    assert b'"duplicate"' not in posted.content
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 1
    letter = DeadLetterEvent.objects.get(payload__kind="payment_webhook")
    replay_dead_letter(letter, user=tenant_a.owner)
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 1
    link.refresh_from_db()
    assert link.status == PaymentLinkStatus.PAID
    duplicate = _post()
    assert b'"duplicate"' in duplicate.content or duplicate.status_code == 200
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 1


def test_ch_05_one_failed_replay_counts_as_one_attempt_and_five_discards(tenant_a):
    """The sweep may discard only after five failed replays. One failure is one attempt."""
    from payments.tasks import _replay_pending_payment_dead_letters

    event = DeadLetterEvent.objects.create(
        company=tenant_a.company,
        provider="sandbox",
        event_id="pay_ch05",
        payload={
            "kind": "payment_webhook",
            "provider": "sandbox",
            "provider_payment_id": "pay_ch05",
            "amount": "100",
            "fee": "0",
        },
        error="crash",
        status=DeadLetterEvent.Status.PENDING,
        attempts=1,
    )
    with patch(
        "payments.services.PaymentService.finalize_gateway_payment",
        side_effect=RuntimeError("still down"),
    ):
        _replay_pending_payment_dead_letters()
    event.refresh_from_db()
    assert event.status == DeadLetterEvent.Status.PENDING
    assert event.attempts == 2

    with patch(
        "payments.services.PaymentService.finalize_gateway_payment",
        side_effect=RuntimeError("still down"),
    ):
        for _ in range(3):
            _replay_pending_payment_dead_letters()
    event.refresh_from_db()
    assert event.status == DeadLetterEvent.Status.PENDING
    assert event.attempts == 5

    with patch(
        "payments.services.PaymentService.finalize_gateway_payment",
        side_effect=RuntimeError("still down"),
    ):
        _replay_pending_payment_dead_letters()
    event.refresh_from_db()
    assert event.status == DeadLetterEvent.Status.DISCARDED
    assert event.attempts == 6


def test_ch_07_only_a_stale_queued_pdf_is_requeued(tenant_a):
    from sales.tasks import requeue_stale_invoice_pdfs

    queued, _ = _draft(tenant_a, sku="CH-07Q", gst="0", price="40")
    failed, _ = _draft(tenant_a, sku="CH-07F", gst="0", price="40")
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{queued['id']}/complete/").status_code == 200
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{failed['id']}/complete/").status_code == 200
    old = timezone.now() - timedelta(minutes=20)
    SalesInvoice.objects.filter(pk=queued["id"]).update(
        pdf_status=SalesInvoice.PdfStatus.QUEUED, updated_at=old,
    )
    SalesInvoice.objects.filter(pk=failed["id"]).update(
        pdf_status=SalesInvoice.PdfStatus.FAILED, updated_at=old,
    )
    cache.delete(f"pdf-stale-notified:{queued['id']}")
    with patch("sales.tasks.generate_invoice_pdf.delay") as delay, patch(
        "core.services.telegram.notify_company_owners",
    ) as notify:
        requeue_stale_invoice_pdfs()
        requeue_stale_invoice_pdfs()
    assert [call.args[0] for call in delay.call_args_list] == [queued["id"], queued["id"]]
    assert notify.call_count == 1


def test_ch_07b_a_transient_pdf_render_error_stays_retryable(tenant_a):
    """Retries stay queued. The last attempt marks FAILED and tells the owner."""
    from core.models import Notification
    from sales.tasks import generate_invoice_pdf

    inv, _ = _draft(tenant_a, sku="CH-07B", gst="0", price="40")
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    SalesInvoice.objects.filter(pk=inv["id"]).update(pdf_status=SalesInvoice.PdfStatus.QUEUED)
    with patch("sales.pdf.render_gst_tax_invoice", side_effect=RuntimeError("font missing")):
        with pytest.raises(RuntimeError):
            generate_invoice_pdf.run(inv["id"], company_id=tenant_a.company.id)
    row = SalesInvoice.objects.get(pk=inv["id"])
    assert row.pdf_status == SalesInvoice.PdfStatus.QUEUED

    generate_invoice_pdf.push_request(retries=generate_invoice_pdf.max_retries)
    try:
        with patch("sales.pdf.render_gst_tax_invoice", side_effect=RuntimeError("font missing")):
            with pytest.raises(RuntimeError):
                generate_invoice_pdf.run(inv["id"], company_id=tenant_a.company.id)
    finally:
        generate_invoice_pdf.pop_request()
    row.refresh_from_db()
    assert row.pdf_status == SalesInvoice.PdfStatus.FAILED
    assert Notification.objects.filter(
        company=tenant_a.company, channel=Notification.Channel.IN_APP, subject="PDF failed",
    ).exists()


def test_ch_08_a_locked_period_does_not_spawn_or_complete_a_recurring_invoice(tenant_a):
    from reporting.gst_periods import soft_close_period
    from sales.models import RecurringInvoiceSchedule
    from sales.tasks import generate_recurring_invoices_task

    product = make_product(tenant_a.company, sku="CH-08", gst_rate="0")
    customer = make_customer(tenant_a.company, phone="9000000808")
    when = timezone.now() - timedelta(minutes=5)
    RecurringInvoiceSchedule.objects.create(
        company=tenant_a.company,
        customer=customer,
        cadence=RecurringInvoiceSchedule.Cadence.MONTHLY,
        next_run_at=when,
        line_template={"items": [{"product": product.id, "quantity": "1", "unit_price": "25"}]},
        auto_complete=False,
    )
    period = timezone.localtime(when).strftime("%Y-%m")
    soft_close_period(tenant_a.company, period, tenant_a.owner)
    before = SalesInvoice.objects.filter(company=tenant_a.company).count()
    generate_recurring_invoices_task.apply()
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == before
    assert SalesInvoice.objects.filter(
        company=tenant_a.company, status=SalesInvoice.Status.COMPLETED,
    ).count() == 0


def test_ch_10_complaints_hide_when_the_flag_drops_and_approve_once(tenant_a):
    from tests.test_growth_os import _flags

    _flags(tenant_a.company)
    customer = make_customer(tenant_a.company, phone="9000001010")
    product = make_product(tenant_a.company, sku="CH-10")
    created = tenant_a.client.post(
        "/api/v1/complaints/",
        {"customer": customer.id, "category": "QUALITY", "description": "Leak"},
        format="json",
    )
    assert created.status_code == 201, created.data
    complaint_id = created.data["id"]
    tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/transition/", {"status": "INSPECTING"}, format="json",
    )
    invoice = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "18"}],
    )
    tenant_a.client.patch(
        f"/api/v1/complaints/{complaint_id}/", {"source_invoice": invoice["id"]}, format="json",
    )
    tenant_a.company.feature_flags = {}
    tenant_a.company.save(update_fields=["feature_flags"])
    hidden = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/create-credit-note/",
        {"items": [{"product": product.id, "quantity": "1", "unit_price": "10"}]},
        format="json",
    )
    assert hidden.status_code == 404
    assert SalesCreditNote.objects.filter(company=tenant_a.company).count() == 0
    _flags(tenant_a.company)
    tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/transition/", {"status": "APPROVED"}, format="json",
    )
    body = {
        "items": [{
            "product": product.id,
            "quantity": "1",
            "unit_price": "10",
            "source_item": invoice["items"][0]["id"],
        }],
    }
    first = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/create-credit-note/", body, format="json",
    )
    second = tenant_a.client.post(
        f"/api/v1/complaints/{complaint_id}/create-credit-note/", body, format="json",
    )
    assert first.status_code == 201, first.data
    assert second.status_code == 200, second.data
    assert SalesCreditNote.objects.filter(company=tenant_a.company).count() == 1


def test_ch_13_whatsapp_cloud_outage_returns_a_result_instead_of_raising():
    import requests

    from core.services import whatsapp

    with patch.object(whatsapp, "build_feature_flags", return_value={"ENABLE_WHATSAPP_CLOUD": True}), patch.object(
        whatsapp, "_resolve_whatsapp_credentials", return_value=("tok", "12345"),
    ), patch.object(whatsapp.requests, "post", side_effect=requests.ConnectionError("reset")):
        result = whatsapp.send_whatsapp_template(
            "919876543210", "invoice_ready", ["INV-1"], company=object(), allow_cloud=True, opt_in=True,
        )
    assert result.mode in ("failed", "link")


def test_ch_16_a_stale_in_flight_complete_key_can_finish_a_still_draft_invoice(tenant_a):
    """A killed request leaves the key in-flight and the invoice draft.

    After the in-flight window, the same key must be able to Complete.
    A retry inside the window may still be told to wait.
    """
    inv, product = _draft(tenant_a, sku="CH-16", gst="0", price="30")
    IdempotencyRecord.objects.create(
        company=tenant_a.company,
        scope="sales_invoice_complete",
        key="ch-16",
        status_code=IN_FLIGHT_STATUS,
        body={},
        resource_id="",
        request_hash="",
    )
    IdempotencyRecord.objects.filter(key="ch-16").update(
        created_at=timezone.now() - timedelta(minutes=16),
    )
    url = f"/api/v1/sales/invoices/{inv['id']}/complete/"
    resumed = tenant_a.client.post(url, {}, format="json", HTTP_IDEMPOTENCY_KEY="ch-16")
    assert resumed.status_code == 200, resumed.data
    row = SalesInvoice.objects.get(pk=inv["id"])
    assert row.status == SalesInvoice.Status.COMPLETED
    assert StockMovement.objects.filter(
        company=tenant_a.company, product=product, movement_type="SALE",
    ).count() == 1
