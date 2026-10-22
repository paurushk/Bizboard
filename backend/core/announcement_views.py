"""WP-CM3: in-app announcements (staff-written banners) and the per-user "What's new" read marker.

GET  /api/v1/announcements/    live banners for the caller's company (all / its plan / it alone)
GET  /api/v1/whats-new/seen/   {"seen": "<newest entry id the user opened>"}
POST /api/v1/whats-new/seen/   {"seen": "<entry id>"}
"""

from __future__ import annotations

import re

from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import HasCompany, get_company_user

_ENTRY_ID = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}-[a-z0-9-]{1,28}$")


def live_announcements(company):
    from billing.models import Subscription

    from .models import Announcement

    now = timezone.now()
    sub = Subscription.objects.filter(company=company).select_related("plan").first()
    plan_slug = getattr(getattr(sub, "plan", None), "slug", "") or ""
    target = Q(target=Announcement.Target.ALL) | Q(target=Announcement.Target.COMPANY, company=company)
    if plan_slug:
        target |= Q(target=Announcement.Target.PLAN, plan_code=plan_slug)
    return Announcement.objects.filter(target, starts_at__lte=now, ends_at__gt=now).order_by("-starts_at")[:5]


class AnnouncementsView(APIView):
    permission_classes = [IsAuthenticated, HasCompany]

    def get(self, request):
        cu = get_company_user(request)
        return Response([
            {"id": a.pk, "severity": a.severity, "text_en": a.text_en, "text_hi": a.text_hi, "ends_at": a.ends_at}
            for a in live_announcements(cu.company)
        ])


class WhatsNewSeenView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"seen": request.user.whats_new_seen or ""})

    def post(self, request):
        seen = str(request.data.get("seen") or "").strip()
        if not _ENTRY_ID.match(seen):
            return Response({"detail": "Unknown entry."}, status=status.HTTP_400_BAD_REQUEST)
        # Entry ids start with their date, so the newest one wins; never move the marker back.
        if seen > (request.user.whats_new_seen or ""):
            request.user.whats_new_seen = seen
            request.user.save(update_fields=["whats_new_seen"])
        return Response({"seen": request.user.whats_new_seen})
