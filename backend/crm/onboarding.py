"""Checklist for a CRM-first prospect who has no books in BizBoard yet."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import HasCompany, get_company_user

from .permissions import assert_crm_enabled


STEPS = [
    {"id": "company", "title": "Confirm the company GSTIN and state (state only if unregistered)"},
    {"id": "booker", "title": "Add the person who will work the pipeline"},
    {"id": "lead", "title": "Capture the first lead"},
    {"id": "stage", "title": "Move a deal from a lead to its next stage once"},
]


class CrmOnboardingView(APIView):
    permission_classes = [IsAuthenticated, HasCompany]

    def get(self, request):
        company = get_company_user(request).company
        assert_crm_enabled(company)
        from django.db.models import Q

        from accounts.models import CompanyUser
        from crm.models import Lead, Opportunity

        lead_count = Lead.objects.filter(company=company).count()
        # A deal that came from a lead and has left OPEN counts, including one closed straight
        # from Convert-as-won (it never gets a stage move).
        moves = Opportunity.objects.filter(company=company, lead__isnull=False).filter(
            Q(stage_move_count__gt=0) | ~Q(stage=Opportunity.Stage.OPEN)
        ).count()
        booker = CompanyUser.objects.filter(
            company=company,
            # Founder decision 2026-09-30: the owner can work the pipeline, so the owner counts.
            role__in=[CompanyUser.Role.OWNER, CompanyUser.Role.SALES_STAFF],
            is_active=True,
            user__is_active=True,
        ).exists()
        done = {
            "company": bool((company.state or "").strip())
            and (
                company.registration_type == company.RegistrationType.UNREGISTERED
                or bool((company.gstin or "").strip())
            ),
            "booker": booker,
            "lead": lead_count > 0,
            "stage": moves > 0,
        }
        return Response({
            "steps": [{**step, "done": done[step["id"]]} for step in STEPS],
        })
