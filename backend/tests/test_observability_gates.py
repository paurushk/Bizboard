"""O-Gate 1 + 2 contracts: /metrics series, request_id chain, ShopFloorEvent envelope."""

from __future__ import annotations

import json
import logging

import pytest
from django.test import override_settings
from rest_framework.test import APIClient, APIRequestFactory

from insights.models import ShopFloorEvent

pytestmark = pytest.mark.django_db

_METRICS_SERIES = (
    "bizboard_http_requests_total",
    "bizboard_http_5xx_total",
    "bizboard_http_request_duration_ms_sum",
    "bizboard_http_request_duration_ms_count",
    "bizboard_celery_task_failure_total",
    "bizboard_pdf_queue_depth",
    "bizboard_dead_letter_events",
    "bizboard_circuit_open",
    "bizboard_health_db",
    "bizboard_health_redis",
    "bizboard_health_celery",
    "bizboard_health_beat",
)


@override_settings(METRICS_TOKEN="obs-metrics-token")
def test_og1_metrics_includes_gate1_series():
    c = APIClient()
    resp = c.get("/api/v1/metrics/", HTTP_AUTHORIZATION="Bearer obs-metrics-token")
    assert resp.status_code == 200
    text = resp.content.decode("utf-8")
    for name in _METRICS_SERIES:
        assert name in text, name
    assert "prometheus_client" not in text


def test_og1_owner_ready_exposes_sentry_configured_not_dsn(tenant_a):
    resp = tenant_a.client.get("/api/v1/health/?ready=1")
    assert resp.status_code in (200, 503)
    assert "sentry_configured" in resp.data
    assert isinstance(resp.data["sentry_configured"], bool)
    blob = json.dumps(resp.data)
    assert "dsn" not in blob.lower()


def test_og2_middleware_echoes_request_id(tenant_a):
    rid = "11111111-2222-4333-8444-555555555555"
    resp = tenant_a.client.get("/api/v1/health/", HTTP_X_REQUEST_ID=rid)
    assert resp.status_code in (200, 503)
    assert resp["X-Request-ID"] == rid


def test_og2_500_envelope_includes_request_id():
    from core.exceptions import api_exception_handler

    request = APIRequestFactory().get("/api/v1/health/")
    request.request_id = "rid-500-test"
    resp = api_exception_handler(RuntimeError("boom"), {"request": request, "view": object()})
    assert resp.status_code == 500
    assert resp.data["error"]["code"] == "server_error"
    assert resp.data["error"]["request_id"] == "rid-500-test"
    assert "boom" not in json.dumps(resp.data)


def test_og2_4xx_envelope_omits_request_id(tenant_a):
    resp = tenant_a.client.post(
        "/api/v1/insights/telemetry/",
        {"event": "not_a_real_event"},
        format="json",
        HTTP_X_REQUEST_ID="rid-4xx",
    )
    assert resp.status_code == 400
    err = resp.data.get("error") or {}
    assert "request_id" not in err


def test_og2e7_shopfloor_has_envelope_columns_not_company_hash():
    names = {f.name for f in ShopFloorEvent._meta.get_fields()}
    for col in (
        "journey",
        "feature",
        "role",
        "session_id",
        "request_id",
        "success",
        "failure_reason",
    ):
        assert col in names
    assert "company_hash" not in names
    idx_names = {idx.name for idx in ShopFloorEvent._meta.indexes}
    assert "insights_sfe_request_id_idx" in idx_names
    assert "insights_sfe_co_journey_on_idx" in idx_names
    row = ShopFloorEvent(
        company_id=1,
        event="invoice_complete",
        occurred_on=__import__("datetime").date.today(),
    )
    derived = row.company_hash
    assert isinstance(derived, str)
    assert len(derived) == 12


def test_og2e7_allowlist_ignores_company_hash_rejects_gstin(tenant_a):
    ok = tenant_a.client.post(
        "/api/v1/insights/telemetry/",
        {"event": "invoice_complete", "company_hash": "should-be-ignored", "company_id": 999},
        format="json",
    )
    assert ok.status_code == 201, ok.data
    row = ShopFloorEvent.objects.filter(company=tenant_a.company, event="invoice_complete").latest(
        "id"
    )
    assert row.journey == "invoice_complete"
    assert row.success is True
    assert row.role == "OWNER"
    assert not hasattr(row, "company_hash") or row.company_hash != "should-be-ignored"

    bad = tenant_a.client.post(
        "/api/v1/insights/telemetry/",
        {"event": "invoice_complete", "gstin": "29ABCDE1234F1Z5"},
        format="json",
    )
    assert bad.status_code == 400
    persona = tenant_a.client.post(
        "/api/v1/insights/telemetry/",
        {"event": "invoice_complete", "persona": "kirana"},
        format="json",
    )
    assert persona.status_code == 400


def test_og2e8_complete_funnel_no_dual_write(tenant_a):
    rid = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    started = tenant_a.client.post(
        "/api/v1/insights/telemetry/",
        {
            "event": "journey_started",
            "journey": "invoice_complete",
            "session_id": "11111111-2222-4333-8444-555555555555",
            "request_id": rid,
        },
        format="json",
        HTTP_X_REQUEST_ID=rid,
    )
    assert started.status_code == 201, started.data
    complete = tenant_a.client.post(
        "/api/v1/insights/telemetry/",
        {
            "event": "invoice_complete",
            "duration_ms": 410,
            "request_id": rid,
            "session_id": "11111111-2222-4333-8444-555555555555",
        },
        format="json",
        HTTP_X_REQUEST_ID=rid,
    )
    assert complete.status_code == 201, complete.data
    failed = tenant_a.client.post(
        "/api/v1/insights/telemetry/",
        {
            "event": "journey_failed",
            "journey": "invoice_complete",
            "failure_reason": "validation",
            "request_id": "failed-rid",
        },
        format="json",
    )
    assert failed.status_code == 201, failed.data
    missing_reason = tenant_a.client.post(
        "/api/v1/insights/telemetry/",
        {"event": "journey_failed", "journey": "invoice_complete"},
        format="json",
    )
    assert missing_reason.status_code == 400

    assert ShopFloorEvent.objects.filter(
        company=tenant_a.company, event="invoice_complete"
    ).count() == 1
    assert not ShopFloorEvent.objects.filter(
        company=tenant_a.company, event="journey_completed"
    ).exists()

    summary = tenant_a.client.get("/api/v1/insights/telemetry/")
    assert summary.status_code == 200, summary.data
    funnel = summary.data["funnel"]
    assert funnel["invoice_complete_started"] == 1
    assert funnel["invoice_complete"] == 1
    assert funnel["invoice_complete_failed"] == 1
    assert funnel["invoice_complete_failed_by_reason"]["validation"] == 1
    assert summary.data["complete_count"] == 1

    stored = ShopFloorEvent.objects.get(
        company=tenant_a.company, event="journey_failed"
    )
    assert stored.failure_reason == "validation"
    assert stored.request_id == "failed-rid"
    assert stored.success is False


def test_og2e4_celery_json_log_and_request_id_header(caplog):
    from config.celery import _inject_request_id_header, _log_celery_task
    from core.observability import bind_request_context, clear_request_context

    headers = {}
    bind_request_context(request_id="celery-rid", company_hash="abcdefabcdef")
    _inject_request_id_header(headers=headers)
    assert headers["request_id"] == "celery-rid"
    assert headers["company_hash"] == "abcdefabcdef"

    class _Req:
        retries = 2
        _bizboard_started = None

    class _Task:
        name = "sales.tasks.generate_invoice_pdf"
        request = _Req()

    caplog.set_level(logging.INFO)
    _log_celery_task(task=_Task(), task_id="task-1", state="SUCCESS", error=None)
    lines = [r.getMessage() for r in caplog.records if "celery.task" in r.getMessage()]
    assert lines, caplog.text
    payload = json.loads(lines[-1])
    assert payload["event"] == "celery.task"
    assert payload["task"] == "sales.tasks.generate_invoice_pdf"
    assert payload["task_id"] == "task-1"
    assert payload["request_id"] == "celery-rid"
    assert payload["company_hash"] == "abcdefabcdef"
    assert payload["status"] == "success"
    assert payload["retry_count"] == 2
    blob = json.dumps(payload)
    assert "gstin" not in blob.lower()
    assert "INV-" not in blob
    assert payload.get("error") is None
    clear_request_context()


def test_og2e6_trace_span_includes_request_id():
    from core.observability import bind_request_context, clear_request_context
    from core.tracing import clear_spans, captured_spans, trace_span

    clear_spans()
    bind_request_context(request_id="span-rid")
    with trace_span("complete"):
        pass
    spans = captured_spans()
    assert spans
    assert spans[-1]["attrs"]["request_id"] == "span-rid"
    clear_request_context()
    clear_spans()


def test_freeze_journeys_pdf_payment_signup_funnel(tenant_a):
    from unittest.mock import patch

    from billing.services import park_dead_letter
    from insights.models import ShopFloorEvent
    from insights.telemetry import record_pdf_failed, record_pdf_started
    from sales.tasks import generate_invoice_pdf
    from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "10.00", "gst_rate": "0"}],
    )
    with patch("sales.pdf.render_gst_tax_invoice", side_effect=RuntimeError("render down")):
        generate_invoice_pdf.run(inv["id"], company_id=tenant_a.company.id)

    record_pdf_started(tenant_a.company)
    record_pdf_failed(tenant_a.company)
    parked = park_dead_letter(
        provider="razorpay",
        event_id="evt-obs-1",
        payload={"kind": "payment_webhook"},
        error="gateway 500",
        company=tenant_a.company,
    )
    assert parked.pk
    tenant_a.client.post(
        "/api/v1/insights/telemetry/",
        {"event": "journey_failed", "journey": "signup", "failure_reason": "validation"},
        format="json",
    )

    summary = tenant_a.client.get("/api/v1/insights/telemetry/")
    assert summary.status_code == 200, summary.data
    funnel = summary.data["funnel"]
    assert funnel["pdf_started"] >= 1
    assert funnel["pdf_failed"] >= 1
    assert funnel["pdf_failed_by_reason"]["unknown"] >= 1
    assert funnel["payment_failed"] >= 1
    assert funnel["payment_failed_by_reason"]["5xx"] >= 1
    assert funnel["signup_failed"] >= 1
    assert funnel["signup_failed_by_reason"]["validation"] >= 1
    pay = ShopFloorEvent.objects.get(
        company=tenant_a.company, event="journey_failed", journey="payment"
    )
    assert pay.failure_reason == "5xx"
    assert pay.success is False
    blob = str(pay.__dict__)
    assert "gstin" not in blob.lower()


def test_observability_gate_check_command(tenant_a, settings, capsys):
    from django.core.management import call_command
    from django.utils import timezone

    from insights.models import ShopFloorEvent

    settings.SENTRY_DSN = ""
    settings.METRICS_TOKEN = "local-staging-only-metrics-token-change-me"
    ShopFloorEvent.objects.create(
        company=tenant_a.company,
        event="journey_failed",
        occurred_on=timezone.localdate(),
        journey="invoice_complete",
        request_id="walk-rid",
        failure_reason="validation",
        success=False,
    )
    call_command("observability_gate_check", request_id="walk-rid")
    out = capsys.readouterr().out
    assert "sentry_configured=False" in out
    assert "metrics_token_set=True" in out
    assert "company_hash_column=False" in out
    assert "envelope_columns_missing=none" in out
    assert "shopfloor_matches=1" in out
    assert "walk-rid" in out
    assert "gstin" not in out.lower()
    assert "OG1-H1" in out
    assert "OGATE_GREP_WALK.md" in out
