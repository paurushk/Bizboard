"""Checklist for a CRM-first prospect who has no books in BizBoard yet."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import HasCompany, get_company_user


STEPS = [
    {"id": "company", "title": "Confirm the company GSTIN and state"},
    {"id": "booker", "title": "Add the person who will work the pipeline"},
    {"id": "lead", "title": "Capture the first lead"},
    {"id": "stage", "title": "Move that lead once so stage activity is recorded"},
]


class CrmOnboardingView(APIView):
    permission_classes = [IsAuthenticated, HasCompany]

    def get(self, request):
        company = get_company_user(request).company
        from accounts.models import CompanyUser
        from crm.models import Lead, Opportunity

        lead_count = Lead.objects.filter(company=company).count()
        moves = Opportunity.objects.filter(company=company, stage_move_count__gt=0).count()
        booker = CompanyUser.objects.filter(
            company=company,
            role=CompanyUser.Role.SALES_STAFF,
            is_active=True,
            user__is_active=True,
        ).exists()
        done = {
            "company": bool((company.gstin or "").strip()),
            "booker": booker,
            "lead": lead_count > 0,
            "stage": moves > 0,
        }
        return Response({
            "steps": [{**step, "done": done[step["id"]]} for step in STEPS],
        })
