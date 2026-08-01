from rest_framework.permissions import BasePermission


def get_company_user(request):
    """Resolve (and cache) the requesting user's active company membership."""
    if hasattr(request, "_company_user"):
        return request._company_user
    company_user = None
    if request.user and request.user.is_authenticated:
        # .order_by("id") makes resolution deterministic; a DB-level partial
        # unique constraint (accounts migration 0006) additionally guarantees
        # at most one active membership per user, so this should never
        # actually need to pick among multiple rows (BUG-110/702).
        company_user = (
            request.user.company_memberships.filter(is_active=True)
            .select_related("company")
            .order_by("id")
            .first()
        )
    request._company_user = company_user
    return company_user


class HasCompany(BasePermission):
    """User must belong to an active company (tenant)."""

    message = "User is not associated with any company."

    def has_permission(self, request, view):
        return get_company_user(request) is not None


class IsOwner(BasePermission):
    """Owner/Admin role required (company settings, users, audit, import commit)."""

    message = "Owner/Admin role required."

    def has_permission(self, request, view):
        cu = get_company_user(request)
        return cu is not None and cu.role == "OWNER"


class CanManageInventory(BasePermission):
    """Inventory adjustment requires inventory permission (§5.5)."""

    message = "Inventory permission required."

    def has_permission(self, request, view):
        cu = get_company_user(request)
        return cu is not None and (cu.role == "OWNER" or cu.can_manage_inventory)


class CanImport(BasePermission):
    """Import commit requires Owner or explicit import permission (§5.5)."""

    message = "Import permission required."

    def has_permission(self, request, view):
        cu = get_company_user(request)
        return cu is not None and (cu.role == "OWNER" or cu.can_import)


class CanCancelDocuments(BasePermission):
    """Cancel / reverse completed documents."""

    message = "Cancel permission required."

    def has_permission(self, request, view):
        cu = get_company_user(request)
        return cu is not None and (cu.role == "OWNER" or cu.can_cancel_documents)


class CanViewFinancialReports(BasePermission):
    """Dashboard financial KPIs, ledgers, and registers."""

    message = "Financial reports permission required."

    def has_permission(self, request, view):
        cu = get_company_user(request)
        return cu is not None and (cu.role == "OWNER" or cu.can_view_financial_reports)


class CanExport(BasePermission):
    """CSV / backup exports."""

    message = "Export permission required."

    def has_permission(self, request, view):
        cu = get_company_user(request)
        return cu is not None and (cu.role == "OWNER" or cu.can_export)
