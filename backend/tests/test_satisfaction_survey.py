"""BB-136 (D-08, 2026-10-24): NPS prompt and support CSAT, behind ENABLE_SATISFACTION_SURVEY."""

from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.models import CompanyUser
from support.models import PlatformTicket, SatisfactionResponse
from support.satisfaction import nps_score_summary

pytestmark = pytest.mark.django_db

DUE = "/api/v1/support/satisfaction/nps-due/"
ANSWER = "/api/v1/support/satisfaction/"


def _turn_on(tenant):
    flags = dict(tenant.company.feature_flags or {})
    flags["ENABLE_SATISFACTION_SURVEY"] = True
    tenant.company.feature_flags = flags
    tenant.company.save(update_fields=["feature_flags"])


def _age_memberships(tenant, days=30):
    CompanyUser.objects.filter(company=tenant.company).update(created_at=timezone.now() - timedelta(days=days))


def test_off_by_default_never_prompts_and_refuses_answers(tenant_a):
    _age_memberships(tenant_a)
    assert tenant_a.client.get(DUE).data == {"due": False, "enabled": False}
    res = tenant_a.client.post(ANSWER, {"kind": "NPS", "score": 9}, format="json")
    assert res.status_code == 400


def test_new_members_are_not_asked_for_two_weeks(tenant_a):
    _turn_on(tenant_a)
    assert tenant_a.client.get(DUE).data["due"] is False
    _age_memberships(tenant_a)
    assert tenant_a.client.get(DUE).data["due"] is True


def test_an_answer_or_not_now_stops_the_prompt_for_90_days(tenant_a):
    _turn_on(tenant_a)
    _age_memberships(tenant_a)
    assert tenant_a.client.post(ANSWER, {"kind": "NPS", "score": 9, "comment": "Fast billing"}, format="json").status_code == 201
    assert tenant_a.client.get(DUE).data["due"] is False
    # Another member who says "Not now" is also left alone, and the answer is recorded without a score.
    assert tenant_a.staff_client.post(ANSWER, {"kind": "NPS", "score": None}, format="json").status_code == 201
    assert tenant_a.staff_client.get(DUE).data["due"] is False
    assert SatisfactionResponse.objects.filter(score__isnull=True, kind="NPS").count() == 1
    SatisfactionResponse.objects.update(created_at=timezone.now() - timedelta(days=91))
    assert tenant_a.client.get(DUE).data["due"] is True


def test_nps_score_must_be_0_to_10(tenant_a):
    _turn_on(tenant_a)
    assert tenant_a.client.post(ANSWER, {"kind": "NPS", "score": 11}, format="json").status_code == 400


def _ticket(tenant, user, status=PlatformTicket.Status.RESOLVED):
    return PlatformTicket.objects.create(
        company=tenant.company, raised_by=user, subject="Help", status=status,
        created_by=user, updated_by=user,
    )


def test_csat_only_on_your_own_resolved_request_and_once(tenant_a):
    _turn_on(tenant_a)
    open_ticket = _ticket(tenant_a, tenant_a.owner, PlatformTicket.Status.OPEN)
    res = tenant_a.client.post(ANSWER, {"kind": "CSAT", "score": 5, "platform_ticket": open_ticket.id}, format="json")
    assert res.status_code == 400
    theirs = _ticket(tenant_a, tenant_a.staff)
    res = tenant_a.client.post(ANSWER, {"kind": "CSAT", "score": 5, "platform_ticket": theirs.id}, format="json")
    assert res.status_code == 400
    mine = _ticket(tenant_a, tenant_a.owner)
    assert tenant_a.client.post(ANSWER, {"kind": "CSAT", "score": 6, "platform_ticket": mine.id}, format="json").status_code == 400
    assert tenant_a.client.post(ANSWER, {"kind": "CSAT", "score": 4, "platform_ticket": mine.id}, format="json").status_code == 201
    again = tenant_a.client.post(ANSWER, {"kind": "CSAT", "score": 5, "platform_ticket": mine.id}, format="json")
    assert again.status_code == 400
    listed = tenant_a.client.get("/api/v1/support/platform-tickets/").data
    assert next(row for row in listed if row["id"] == mine.id)["satisfaction_score"] == 4


def test_another_company_cannot_rate_your_request(tenant_a, tenant_b):
    _turn_on(tenant_a)
    _turn_on(tenant_b)
    mine = _ticket(tenant_a, tenant_a.owner)
    res = tenant_b.client.post(ANSWER, {"kind": "CSAT", "score": 1, "platform_ticket": mine.id}, format="json")
    assert res.status_code == 400
    assert not SatisfactionResponse.objects.filter(platform_ticket=mine).exists()


def test_nps_summary_counts_only_answered_rows():
    class Row:
        def __init__(self, score):
            self.score = score

    rows = [Row(10), Row(9), Row(8), Row(3), Row(None)]
    assert nps_score_summary(rows) == {"answered": 4, "nps": 25, "promoters": 2, "passives": 1, "detractors": 1}
    assert nps_score_summary([])["nps"] is None
