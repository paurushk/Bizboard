"""BB-136 (D-08, 2026-10-24): NPS prompt and CSAT on resolved support requests.

Both sit behind the company flag ENABLE_SATISFACTION_SURVEY (off by default). Answers are read by
Bizboard staff in Django admin (Support > Satisfaction responses), never shown to other tenants.
"""

from __future__ import annotations

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services.feature_flags import flag_enabled

FLAG = "ENABLE_SATISFACTION_SURVEY"
# Ask again at most every 90 days, and only once someone has used the product for two weeks.
NPS_COOLDOWN_DAYS = 90
NPS_MIN_MEMBER_DAYS = 14
COMMENT_MAX = 2000


def survey_on(company) -> bool:
    return flag_enabled(company, FLAG)


def nps_due(membership) -> bool:
    """True when this member should see the NPS prompt now."""
    from .models import SatisfactionResponse

    company = membership.company
    if not survey_on(company):
        return False
    now = timezone.now()
    if membership.created_at and membership.created_at > now - timedelta(days=NPS_MIN_MEMBER_DAYS):
        return False
    return not SatisfactionResponse.objects.filter(
        company=company,
        user=membership.user,
        kind=SatisfactionResponse.Kind.NPS,
        created_at__gte=now - timedelta(days=NPS_COOLDOWN_DAYS),
    ).exists()


def nps_score_summary(rows) -> dict:
    """NPS = % promoters (9-10) minus % detractors (0-6) over answered rows; "Not now" is left out."""
    scores = [r.score for r in rows if r.score is not None]
    if not scores:
        return {"answered": 0, "nps": None, "promoters": 0, "passives": 0, "detractors": 0}
    promoters = sum(1 for s in scores if s >= 9)
    detractors = sum(1 for s in scores if s <= 6)
    return {
        "answered": len(scores),
        "nps": round((promoters - detractors) * 100 / len(scores)),
        "promoters": promoters,
        "passives": len(scores) - promoters - detractors,
        "detractors": detractors,
    }


def record(membership, *, kind: str, score, comment: str = "", platform_ticket_id=None):
    """Save one answer. NPS: 0-10, or None for "Not now". CSAT: 1-5 on the member's own resolved request."""
    from .models import PlatformTicket, SatisfactionResponse

    company = membership.company
    if not survey_on(company):
        raise BusinessRuleError("Feedback surveys are not on for this company.", code="survey_off")
    comment = (comment or "").strip()[:COMMENT_MAX]
    ticket = None
    if kind == SatisfactionResponse.Kind.NPS:
        if score is not None and not (0 <= int(score) <= 10):
            raise BusinessRuleError("Pick a number from 0 to 10.", code="survey_score")
        if platform_ticket_id:
            raise BusinessRuleError("A recommendation score is not tied to a request.", code="survey_ticket")
    elif kind == SatisfactionResponse.Kind.CSAT:
        if score is None or not (1 <= int(score) <= 5):
            raise BusinessRuleError("Pick a rating from 1 to 5.", code="survey_score")
        ticket = PlatformTicket.objects.filter(
            pk=platform_ticket_id, company=company, raised_by=membership.user,
        ).first()
        if ticket is None:
            raise BusinessRuleError("You can rate only your own support requests.", code="survey_ticket")
        if ticket.status != PlatformTicket.Status.RESOLVED:
            raise BusinessRuleError("You can rate a request once it is resolved.", code="survey_not_resolved")
    else:
        raise BusinessRuleError("Unknown survey.", code="survey_kind")
    try:
        with transaction.atomic():
            return SatisfactionResponse.objects.create(
                company=company,
                user=membership.user,
                kind=kind,
                score=None if score is None else int(score),
                comment=comment,
                platform_ticket=ticket,
                created_by=membership.user,
                updated_by=membership.user,
            )
    except IntegrityError:
        raise BusinessRuleError("This request is already rated.", code="survey_already_rated") from None
