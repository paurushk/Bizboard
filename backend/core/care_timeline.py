"""Activity timeline for the care and job screens (FND-10).

Reads the audit log for one record. Nothing here is written by the timeline; each action already
logs its own event. Only whitelisted record types are readable, and the client address is never
returned.
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AuditEvent
from .permissions import (
    CanCreatePurchases,
    CanCreateSales,
    HasCompany,
    get_company_user,
)

# record type -> permission class that may read its timeline
TIMELINE_ENTITIES = {
    "Ticket": CanCreateSales,
    "Complaint": CanCreateSales,
    "SupplierComplaint": CanCreatePurchases,
    "Contract": CanCreateSales,
    "JobCard": CanCreateSales,
    "Project": CanCreateSales,
}
PAGE = 100


def timeline_rows(company, entity_type, entity_id, limit=PAGE):
    rows = (
        AuditEvent.objects.filter(company=company, entity_type=entity_type, entity_id=str(entity_id))
        .select_related("user")
        .order_by("-created_at", "-id")[:limit]
    )
    out = []
    for row in rows:
        meta = {k: v for k, v in (row.metadata or {}).items() if k != "ip"}
        user = row.user
        out.append({
            "id": row.id,
            "action": row.action,
            "description": row.description,
            "metadata": meta,
            "user_name": (getattr(user, "full_name", "") or getattr(user, "email", "") or "") if user else "",
            "created_at": row.created_at,
        })
    return out


class CareTimelineView(APIView):
    """GET /audit-timeline/?entity=Ticket&id=12"""

    permission_classes = [IsAuthenticated, HasCompany]

    def get(self, request):
        entity = (request.query_params.get("entity") or "").strip()
        raw_id = (request.query_params.get("id") or "").strip()
        permission = TIMELINE_ENTITIES.get(entity)
        if permission is None or not raw_id.isdigit():
            return Response({"detail": "Unknown record."}, status=400)
        if not permission().has_permission(request, self):
            return Response({"detail": "You do not have access to this record."}, status=403)
        company = get_company_user(request).company
        return Response(timeline_rows(company, entity, int(raw_id)))
