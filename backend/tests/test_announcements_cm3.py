"""WP-CM3: in-app announcements (window + targeting) and the What's new read marker."""

from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import Announcement

pytestmark = pytest.mark.django_db


def _ann(**kw):
    now = timezone.now()
    base = {"text_en": "Maintenance tonight", "text_hi": "आज रात रखरखाव", "starts_at": now - timedelta(hours=1),
            "ends_at": now + timedelta(hours=1)}
    base.update(kw)
    return Announcement.objects.create(**base)


def test_only_live_and_targeted_banners_are_shown(tenant_a, tenant_b):
    live = _ann()
    _ann(text_en="Over", starts_at=timezone.now() - timedelta(days=2), ends_at=timezone.now() - timedelta(days=1))
    _ann(text_en="Later", starts_at=timezone.now() + timedelta(hours=2), ends_at=timezone.now() + timedelta(hours=3))
    mine = _ann(text_en="Just A", target=Announcement.Target.COMPANY, company=tenant_a.company)
    _ann(text_en="Just B", target=Announcement.Target.COMPANY, company=tenant_b.company)
    _ann(text_en="Pro plan only", target=Announcement.Target.PLAN, plan_code="no-such-plan")
    body = tenant_a.client.get("/api/v1/announcements/").json()["data"]
    assert {row["id"] for row in body} == {live.pk, mine.pk}
    assert body[0]["textHi"]


def test_whats_new_marker_only_moves_forward(tenant_a):
    assert tenant_a.client.get("/api/v1/whats-new/seen/").json()["data"]["seen"] == ""
    assert tenant_a.client.post("/api/v1/whats-new/seen/", {"seen": "2026-10-22-tds-credit"}, format="json").status_code == 200
    tenant_a.client.post("/api/v1/whats-new/seen/", {"seen": "2026-09-01-older"}, format="json")
    assert tenant_a.client.get("/api/v1/whats-new/seen/").json()["data"]["seen"] == "2026-10-22-tds-credit"
    assert tenant_a.client.post("/api/v1/whats-new/seen/", {"seen": "../etc"}, format="json").status_code == 400
