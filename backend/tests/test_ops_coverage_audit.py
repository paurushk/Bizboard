"""ops.CoverageAuditRun — the Celery task never crashes the worker: a live
repo scan / snapshot fallback and an LLM-provider error both resolve to a
clean FAILED status with a reason, matching the imports.tasks bill-
extraction task's failure-handling convention."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.conf import settings

from ops.models import CoverageAuditRun
from ops.tasks import run_coverage_audit_task, run_scheduled_coverage_audit

pytestmark = pytest.mark.django_db


def test_scheduled_beat_entry_absent_when_flag_is_off():
    """ENABLE_SCHEDULED_COVERAGE_AUDIT defaults off (config/settings.py) —
    a real, billed LLM call must never fire on a schedule without an
    explicit opt-in, and CI/local dev never sets this env var."""
    assert not settings.ENABLE_SCHEDULED_COVERAGE_AUDIT
    assert "ops-coverage-audit-weekly" not in settings.CELERY_BEAT_SCHEDULE


@patch("ops.coverage_scan.scan", return_value={"source": "unavailable", "note": "no repo tree"})
def test_run_marks_failed_when_repo_scan_unavailable(_mock_scan):
    run = CoverageAuditRun.objects.create()
    run_coverage_audit_task(run.pk)
    run.refresh_from_db()
    assert run.status == CoverageAuditRun.Status.FAILED
    assert "no repo tree" in run.failure_reason


@patch("core.services.llm.chat_with_tools", side_effect=Exception("provider down"))
@patch(
    "ops.coverage_scan.scan",
    return_value={"source": "live_scan", "routes": [], "route_coverage": {}, "open_qos_items": [], "g_register": ""},
)
def test_run_marks_failed_not_crash_on_llm_error(_mock_scan, _mock_chat):
    run = CoverageAuditRun.objects.create()
    run_coverage_audit_task(run.pk)  # must not raise
    run.refresh_from_db()
    assert run.status == CoverageAuditRun.Status.FAILED
    assert "provider down" in run.failure_reason


@patch("core.services.llm.chat_with_tools", return_value={"content": "not json at all"})
@patch(
    "ops.coverage_scan.scan",
    return_value={"source": "live_scan", "routes": [], "route_coverage": {}, "open_qos_items": [], "g_register": ""},
)
def test_run_stores_a_parse_error_item_not_a_crash_on_bad_llm_json(_mock_scan, _mock_chat):
    run = CoverageAuditRun.objects.create()
    run_coverage_audit_task(run.pk)
    run.refresh_from_db()
    assert run.status == CoverageAuditRun.Status.DONE
    assert run.result[0]["area"] == "parse-error"


@patch(
    "core.services.llm.chat_with_tools",
    return_value={"content": '[{"area": "Purchases", "gap": "no e2e", "severity": "high", "recommendation": "add specs", "related_qos_ids": []}]'},
)
@patch(
    "ops.coverage_scan.scan",
    return_value={"source": "live_scan", "routes": ["/purchases/new"], "route_coverage": {}, "open_qos_items": [], "g_register": ""},
)
def test_run_stores_parsed_result_on_success(_mock_scan, _mock_chat):
    run = CoverageAuditRun.objects.create()
    run_coverage_audit_task(run.pk)
    run.refresh_from_db()
    assert run.status == CoverageAuditRun.Status.DONE
    assert run.result == [
        {"area": "Purchases", "gap": "no e2e", "severity": "high", "recommendation": "add specs", "related_qos_ids": []}
    ]


def test_run_is_a_noop_for_a_nonpending_run():
    run = CoverageAuditRun.objects.create(status=CoverageAuditRun.Status.DONE, result=[{"already": "done"}])
    run_coverage_audit_task(run.pk)  # must not re-run or clear the result
    run.refresh_from_db()
    assert run.result == [{"already": "done"}]


@patch(
    "core.services.llm.chat_with_tools",
    return_value={"content": '[{"area": "Purchases", "gap": "no e2e", "severity": "high", "recommendation": "add specs", "related_qos_ids": []}]'},
)
@patch(
    "ops.coverage_scan.scan",
    return_value={"source": "live_scan", "routes": ["/purchases/new"], "route_coverage": {}, "open_qos_items": [], "g_register": ""},
)
def test_scheduled_run_creates_its_own_row_with_no_requester(_mock_scan, _mock_chat):
    """The weekly beat entry has no admin to attribute the run to — same
    execution path as the id-based task (_execute_coverage_audit), just a
    self-created row instead of one made by the admin action."""
    assert CoverageAuditRun.objects.count() == 0
    run_scheduled_coverage_audit()
    run = CoverageAuditRun.objects.get()
    assert run.requested_by is None
    assert run.status == CoverageAuditRun.Status.DONE
    assert run.result[0]["area"] == "Purchases"


@patch("core.services.llm.chat_with_tools", side_effect=Exception("provider down"))
@patch(
    "ops.coverage_scan.scan",
    return_value={"source": "live_scan", "routes": [], "route_coverage": {}, "open_qos_items": [], "g_register": ""},
)
def test_scheduled_run_marks_failed_not_crash_on_llm_error(_mock_scan, _mock_chat):
    run_scheduled_coverage_audit()  # must not raise
    run = CoverageAuditRun.objects.get()
    assert run.status == CoverageAuditRun.Status.FAILED
    assert "provider down" in run.failure_reason
