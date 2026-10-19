"""SET-21: recent changes to a Settings area, read from the audit trail.

``GET /api/v1/company/settings-history/?area=series&limit=30``. Owner only. Each row says who changed
what and when, with old and new values; secrets never carry values (see ``core.settings_audit``).
"""

from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import BusinessRuleError
from core.models import AuditEvent
from core.permissions import HasCompany, IsOwner, get_company_user

#: Company fields the Company screen owns; the GST screen owns the next set.
COMPANY_FIELDS = {
    "name", "legal_name", "address", "city", "state", "pincode", "phone", "email", "logo",
}
GST_FIELDS = {
    "gstin", "pan", "udyam", "registration_type", "negative_stock_policy", "valuation_business_date_order",
    "recompute_tax_on_complete", "assume_local_state_for_blank_party", "eway_threshold_amount",
}

#: area -> (entity types, optional Company field filter). ``state`` is shared: Company and GST both list it.
AREAS: dict[str, tuple[tuple[str, ...], set[str] | None]] = {
    "company": (("Company",), COMPANY_FIELDS | {"state"}),
    "gst": (("Company", "CompanyGstin"), GST_FIELDS | {"state"}),
    "licences": (("CompanyStatutoryLicence",), None),
    "banks": (("BankAccount",), None),
    "gateway": (("PaymentGatewaySettings",), None),
    "money_in": (("MoneyInRules",), None),
    "series": (("DocumentSeries",), None),
    "units": (("Unit",), None),
    "price_lists": (("PriceList",), None),
    "users": (("CompanyUser",), None),
    "accounting": (("AccountingSettings",), None),
    "packs": (("CompanyPackState",), None),
    "items": (("Company",), {"item_custom_field_defs"}),
}


def _rows(company, area: str, limit: int) -> list[dict]:
    types, fields = AREAS[area]
    events = (
        AuditEvent.objects.filter(company=company, entity_type__in=types)
        .select_related("user")
        .order_by("-created_at", "-id")[: limit * 6 if fields else limit]
    )
    out: list[dict] = []
    for event in events:
        meta = event.metadata or {}
        diff = meta.get("changes") or {}
        if fields is not None and event.entity_type == "Company":
            diff = {k: v for k, v in diff.items() if k in fields}
            if not diff:
                continue
        out.append(
            {
                "id": event.pk,
                "at": event.created_at,
                "who": (getattr(event.user, "full_name", "") or getattr(event.user, "email", "")) if event.user else "",
                "action": event.action,
                "entity": event.entity_type,
                "what": event.description or meta.get("event") or "",
                "changes": [{"field": k, **v} for k, v in diff.items()],
            }
        )
        if len(out) >= limit:
            break
    return out


class SettingsHistoryView(APIView):
    permission_classes = [IsAuthenticated, HasCompany, IsOwner]

    def get(self, request):
        area = request.query_params.get("area", "")
        if area not in AREAS:
            raise BusinessRuleError("Unknown settings area.")
        try:
            limit = max(1, min(100, int(request.query_params.get("limit", 30))))
        except ValueError:
            raise BusinessRuleError("limit must be a number.") from None
        company = get_company_user(request).company
        return Response({"area": area, "items": _rows(company, area, limit)})
