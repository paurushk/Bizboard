"""Record a GSTR-1/3B attempt against the period, not against one invoice."""

from __future__ import annotations

import uuid

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import HasCompany, get_company_user
from core.services.audit import AuditService

from .models import GstPeriodFiling


class GstPeriodFilingView(APIView):
    """CA-facing list of period filing attempts. Bookers do not see these on invoices."""

    permission_classes = [IsAuthenticated, HasCompany]

    def get(self, request):
        company = get_company_user(request).company
        rows = GstPeriodFiling.objects.filter(company=company).order_by("-id")[:100]
        return Response({
            "results": [
                {
                    "id": row.id,
                    "return_type": row.return_type,
                    "period": row.period,
                    "status": row.status,
                    "error_message": row.error_message,
                    "reference": row.reference,
                }
                for row in rows
            ]
        })


def record_period_filing(
    *,
    company,
    return_type: str,
    period: str,
    status: str,
    error_message: str = "",
    reference: str = "",
    user=None,
) -> GstPeriodFiling:
    row = GstPeriodFiling.objects.create(
        company=company,
        return_type=(return_type or "").upper(),
        period=period,
        status=status,
        error_message=(error_message or "")[:4000],
        reference=reference or uuid.uuid4().hex[:16],
        created_by=user,
        updated_by=user,
    )
    AuditService.log(
        company=company,
        user=user,
        action="CREATE",
        entity_type="gstperiodfiling",
        entity_id=row.pk,
        description=f"gstr.filing.{row.status.lower()}",
        metadata={"return_type": row.return_type, "period": row.period},
    )
    return row
