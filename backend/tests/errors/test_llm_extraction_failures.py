"""SR-20 / D14 — LLM purchase-bill extraction failure paths.

Every provider failure mode (timeout, 5xx, 429, malformed JSON, hard task
timeout) must land the ImportJob in FAILED with an actionable message, never
raise a 500 to the caller, and never leave a committable partial draft.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tests.test_purchase_bill_import import _upload_bill

pytestmark = pytest.mark.django_db


FAILURE_MODES = [
    ("timeout", TimeoutError("provider request timed out")),
    ("http_5xx", Exception("503 Service Unavailable from upstream model host")),
    ("http_429", Exception("429 Too Many Requests - rate limit exceeded")),
    ("connection_reset", ConnectionError("connection reset by peer")),
]


def _no_partial_draft(company):
    from purchases.models import PurchaseInvoice
    from sales.models import SalesInvoice

    assert PurchaseInvoice.objects.filter(company=company).count() == 0
    assert SalesInvoice.objects.filter(company=company).count() == 0


@pytest.mark.parametrize("label,exc", FAILURE_MODES, ids=[m[0] for m in FAILURE_MODES])
def test_provider_failure_marks_job_failed_cleanly(label, exc, tenant_a):
    with patch("core.services.llm.extract_purchase_bill", side_effect=exc):
        resp = _upload_bill(tenant_a)

    # the upload endpoint itself never 500s on a downstream provider failure
    assert resp.status_code == 201, resp.data
    assert resp.data["status"] == "FAILED", resp.data
    assert (resp.data.get("failure_reason") or "").strip(), "FAILED job must carry a reason"
    _no_partial_draft(tenant_a.company)


def test_malformed_json_from_provider_marks_job_failed(tenant_a):
    from core.exceptions import BusinessRuleError

    with patch(
        "core.services.llm.extract_purchase_bill",
        side_effect=BusinessRuleError("LLM response was not valid JSON."),
    ):
        resp = _upload_bill(tenant_a)

    assert resp.status_code == 201, resp.data
    assert resp.data["status"] == "FAILED"
    assert "json" in (resp.data.get("failure_reason") or "").lower()
    _no_partial_draft(tenant_a.company)


def test_empty_payload_from_provider_marks_job_failed(tenant_a):
    from core.exceptions import BusinessRuleError

    with patch(
        "core.services.llm.extract_purchase_bill",
        side_effect=BusinessRuleError("LLM returned no extraction payload."),
    ):
        resp = _upload_bill(tenant_a)

    assert resp.status_code == 201, resp.data
    assert resp.data["status"] == "FAILED"
    _no_partial_draft(tenant_a.company)


def test_hard_task_timeout_marks_job_failed_with_retry_hint(tenant_a):
    from celery.exceptions import SoftTimeLimitExceeded

    with patch(
        "core.services.llm.extract_purchase_bill",
        side_effect=SoftTimeLimitExceeded(),
    ):
        resp = _upload_bill(tenant_a)

    assert resp.status_code == 201, resp.data
    assert resp.data["status"] == "FAILED"
    assert "retry" in (resp.data.get("failure_reason") or "").lower()
    _no_partial_draft(tenant_a.company)


def test_failed_extraction_is_retryable(tenant_a):
    """A FAILED job can be retried and succeed — the failure is not terminal."""
    from tests.test_purchase_bill_import import FAKE_EXTRACT

    with patch("core.services.llm.extract_purchase_bill", side_effect=TimeoutError("boom")):
        job = _upload_bill(tenant_a).data
    assert job["status"] == "FAILED"

    with patch("core.services.llm.extract_purchase_bill", return_value=FAKE_EXTRACT):
        retry = tenant_a.client.post(f"/api/v1/imports/{job['id']}/retry-extract/")
    assert retry.status_code == 200, retry.data
    assert retry.data["status"] in ("PREVIEWED", "PREVIEW", "READY")
