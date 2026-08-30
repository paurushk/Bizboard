import pytest
from django.test import override_settings
from rest_framework.exceptions import PermissionDenied

from core.exceptions import BusinessRuleError, api_exception_handler, exception_error_code
from core.help_codes import ALL_HELP_CODES, ERROR_CODE_TO_INTENT, HelpCode
from core.models import HelpEvent, HelpFeedback
from core.services.feature_flags import build_feature_flags

pytestmark = pytest.mark.django_db


def test_exception_error_code_uses_instance_not_default():
    exc = BusinessRuleError("no stock", code=HelpCode.INSUFFICIENT_STOCK)
    assert exception_error_code(exc) == HelpCode.INSUFFICIENT_STOCK
    assert exception_error_code(BusinessRuleError("plain")) == "business_rule_violation"


def test_handler_round_trips_all_help_codes():
    for code in ALL_HELP_CODES:
        if code == HelpCode.PERMISSION_DENIED:
            resp = api_exception_handler(PermissionDenied("Your login can't do this."), {})
        else:
            resp = api_exception_handler(BusinessRuleError("blocked", code=code), {})
        assert resp is not None
        assert resp.data["error"]["code"] == code
        assert ERROR_CODE_TO_INTENT[code]


def test_help_v2_flag_default_off(tenant_a):
    flags = build_feature_flags(company=tenant_a.company, user=tenant_a.owner)
    assert flags["helpV2"] is False
    resp = tenant_a.client.get("/api/v1/feature-flags/")
    assert resp.status_code == 200
    assert resp.data["helpV2"] is False


def test_help_v2_staff_or_json_or_kill_switch(tenant_a):
    tenant_a.owner.is_staff = True
    tenant_a.owner.save(update_fields=["is_staff"])
    flags = build_feature_flags(company=tenant_a.company, user=tenant_a.owner)
    assert flags["helpV2"] is True

    tenant_a.owner.is_staff = False
    tenant_a.owner.save(update_fields=["is_staff"])
    tenant_a.company.feature_flags = {"helpV2": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    flags = build_feature_flags(company=tenant_a.company, user=tenant_a.owner)
    assert flags["helpV2"] is True

    tenant_a.company.feature_flags = {"helpV2": False}
    tenant_a.company.save(update_fields=["feature_flags"])
    flags = build_feature_flags(company=tenant_a.company, user=tenant_a.owner)
    assert flags["helpV2"] is False


def test_help_v2_company_allowlist(tenant_a, settings):
    settings.HELP_V2_COMPANY_ALLOWLIST = str(tenant_a.company.id)
    flags = build_feature_flags(company=tenant_a.company, user=tenant_a.owner)
    assert flags["helpV2"] is True


def test_help_events_feedback_health_round_trip(tenant_a):
    post = tenant_a.client.post(
        "/api/v1/help-events/",
        {
            "events": [
                {
                    "name": "help_open",
                    "intentId": "add-gstin",
                    "source": "nav",
                    "query": "how do i add gstin",
                },
                {"name": "faq_resolved", "intentId": "add-gstin"},
                {"name": "help_search", "state": "no-match", "query": "asdfzxcv"},
                {"name": "help_search", "state": "confident", "query": "repeat-me"},
                {"name": "help_search", "state": "confident", "query": "repeat-me"},
            ]
        },
        format="json",
    )
    assert post.status_code == 200, post.data
    assert post.data["accepted"] == 5
    assert HelpEvent.objects.filter(company=tenant_a.company).count() == 5

    fb = tenant_a.client.post(
        "/api/v1/help-feedback/",
        {"query": "still stuck", "intentId": "add-gstin", "note": "GSTIN field grey"},
        format="json",
    )
    assert fb.status_code == 200, fb.data
    assert HelpFeedback.objects.filter(company=tenant_a.company).count() == 1

    health = tenant_a.client.get("/api/v1/help-health/")
    assert health.status_code == 200, health.data
    assert health.data["scope"] == "company"
    assert health.data["opens"] >= 1
    assert health.data["resolved"] >= 1
    assert health.data["time_to_resolution_seconds"] is not None
    assert health.data["repeat_query_rate"] is not None
    assert health.data["repeat_query_rate"] > 0

    listed = tenant_a.client.get("/api/v1/help-feedback/")
    assert listed.status_code == 200
    assert len(listed.data["results"]) == 1


def test_help_health_staff_only(tenant_a):
    resp = tenant_a.staff_client.get("/api/v1/help-health/")
    assert resp.status_code == 403


@override_settings(ENABLE_MANUFACTURING=True, ENABLE_PAYROLL=True, ENABLE_CRM=True)
def test_help_v2_json_does_not_disable_dark_modules(tenant_a):
    tenant_a.company.feature_flags = {"helpV2": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    flags = build_feature_flags(company=tenant_a.company, user=tenant_a.owner)
    assert flags["helpV2"] is True
    assert flags["ENABLE_MANUFACTURING"] is True
    assert flags["ENABLE_PAYROLL"] is True
    assert flags["ENABLE_CRM"] is True


def test_help_events_strip_query_from_props(tenant_a):
    resp = tenant_a.client.post(
        "/api/v1/help-events/",
        {
            "events": [
                {
                    "name": "help_search",
                    "query": "secret party GSTIN",
                    "props": {"query": "secret party GSTIN", "state": "no-match"},
                }
            ]
        },
        format="json",
    )
    assert resp.status_code == 200
    row = HelpEvent.objects.get(company=tenant_a.company, name="help_search")
    assert row.query == "secret party GSTIN"
    assert "query" not in (row.props or {})


def test_help_escalation_count_is_feedback_only(tenant_a):
    tenant_a.client.post(
        "/api/v1/help-events/",
        {"events": [{"name": "faq_unresolved", "intentId": "add-gstin"}]},
        format="json",
    )
    tenant_a.client.post(
        "/api/v1/help-feedback/",
        {"intentId": "add-gstin", "note": "still stuck"},
        format="json",
    )
    health = tenant_a.client.get("/api/v1/help-health/")
    assert health.status_code == 200
    assert health.data["escalation_count"] == 1


def test_help_latest_rating_wins(tenant_a):
    tenant_a.client.post(
        "/api/v1/help-events/",
        {
            "events": [
                {"name": "faq_resolved", "intentId": "add-gstin"},
                {"name": "faq_unresolved", "intentId": "add-gstin"},
            ]
        },
        format="json",
    )
    health = tenant_a.client.get("/api/v1/help-health/")
    assert health.status_code == 200
    assert health.data["resolved"] == 0
    assert health.data["unresolved"] == 1
    assert health.data["rated"] == 1
    assert HelpEvent.objects.filter(company=tenant_a.company, name__in=["faq_resolved", "faq_understood_pending", "faq_unresolved"]).count() == 1


def test_help_feedback_patch_resolved_at(tenant_a):
    created = tenant_a.client.post(
        "/api/v1/help-feedback/",
        {"intentId": "add-gstin", "note": "open"},
        format="json",
    )
    assert created.status_code == 200
    pk = created.data["id"]
    patched = tenant_a.client.patch(
        "/api/v1/help-feedback/",
        {"id": pk},
        format="json",
    )
    assert patched.status_code == 200, patched.data
    row = HelpFeedback.objects.get(pk=pk)
    assert row.resolved_at is not None
    listed = tenant_a.client.get("/api/v1/help-feedback/")
    assert listed.data["results"] == []


def test_prune_help_events_command(tenant_a):
    from datetime import timedelta

    from django.core.management import call_command
    from django.utils import timezone

    old = HelpEvent.objects.create(
        company=tenant_a.company,
        created_by=tenant_a.owner,
        name="help_open",
        intent_id="add-gstin",
    )
    HelpEvent.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=200))
    HelpEvent.objects.create(
        company=tenant_a.company,
        created_by=tenant_a.owner,
        name="help_open",
        intent_id="add-gstin",
    )
    call_command("prune_help_events", days=180)
    assert HelpEvent.objects.filter(company=tenant_a.company).count() == 1


def test_help_health_staff_all_aggregates(tenant_a, tenant_b):
    tenant_a.client.post(
        "/api/v1/help-events/",
        {"events": [{"name": "help_open", "intentId": "add-gstin"}]},
        format="json",
    )
    tenant_b.client.post(
        "/api/v1/help-events/",
        {"events": [{"name": "help_open", "intentId": "add-gstin"}]},
        format="json",
    )
    tenant_a.owner.is_staff = True
    tenant_a.owner.save(update_fields=["is_staff"])
    health = tenant_a.client.get("/api/v1/help-health/?all=1")
    assert health.status_code == 200, health.data
    assert health.data["scope"] == "all"
    assert health.data["opens"] >= 2


def test_help_health_staff_all_with_rls(tenant_a, tenant_b, settings):
    from django.db import connection

    if connection.vendor != "postgresql":
        pytest.skip("Postgres RLS only")
    if not getattr(settings, "POSTGRES_RLS_ENABLED", False):
        pytest.skip("POSTGRES_RLS_ENABLED is off")

    tenant_a.client.post(
        "/api/v1/help-events/",
        {"events": [{"name": "help_open", "intentId": "add-gstin"}]},
        format="json",
    )
    tenant_b.client.post(
        "/api/v1/help-events/",
        {"events": [{"name": "help_open", "intentId": "add-gstin"}]},
        format="json",
    )
    tenant_a.owner.is_staff = True
    tenant_a.owner.save(update_fields=["is_staff"])
    own = tenant_a.client.get("/api/v1/help-health/")
    assert own.status_code == 200
    assert own.data["scope"] == "company"
    assert own.data["opens"] == 1
    staff_all = tenant_a.client.get("/api/v1/help-health/?all=1")
    assert staff_all.status_code == 200, staff_all.data
    assert staff_all.data["scope"] == "all"
    assert staff_all.data["opens"] >= 2


def test_help_prune_on_celery_beat(settings):
    assert "help-prune-events" in settings.CELERY_BEAT_SCHEDULE
    assert settings.CELERY_BEAT_SCHEDULE["help-prune-events"]["task"] == "core.tasks.prune_help_events_task"

