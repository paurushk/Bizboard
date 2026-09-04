from rest_framework.permissions import BasePermission

from core.exceptions import CompanyContextConflict, CompanyRequired


def _header_company_id(request) -> int | None:
    """BB-000055: optional X-Company-Id — never trusted without membership check."""
    raw = request.META.get("HTTP_X_COMPANY_ID") or request.headers.get("X-Company-Id")
    if not raw:
        return None
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


def get_company_user(request):
    """Resolve (and cache) the requesting user's active company membership."""
    current_uid = getattr(getattr(request, "user", None), "pk", None)
    # R1-007: the cache is keyed by the resolved-for user id. A `None` result
    # cached before authentication (e.g. PostgresRlsMiddleware / request-log
    # middleware running for a Bearer request whose user DRF authenticates
    # later) must not shadow the real membership once request.user is set.
    if hasattr(request, "_company_user") and getattr(request, "_company_user_uid", object()) == current_uid:
        return request._company_user
    company_user = None
    if request.user and request.user.is_authenticated:
        user = request.user
        qs = user.company_memberships.filter(is_active=True).select_related("company")
        header_id = _header_company_id(request)
        active_company_id = getattr(user, "active_company_id", None)
        # BB-000658: header must match active_company or 409 (no silent override).
        if header_id is not None and active_company_id and int(header_id) != int(active_company_id):
            raise CompanyContextConflict()
        if header_id is not None and (active_company_id is None or int(header_id) == int(active_company_id)):
            company_user = qs.filter(company_id=header_id).order_by("id").first()
            if company_user is not None:
                request._company_user = company_user
                request._company_user_uid = current_uid
                return company_user
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("X-Company-Id is not a company you belong to.")
        if active_company_id:
            company_user = qs.filter(company_id=active_company_id).order_by("id").first()
            if company_user is None:
                # B6-023: the stored active company is no longer a live
                # membership (revoked / deactivated). Clear it and make the user
                # re-pick explicitly — never silently switch them into another
                # company.
                try:
                    user.active_company_id = None
                    user.save(update_fields=["active_company"])
                except Exception:  # noqa: BLE001
                    pass
                raise CompanyRequired(list(qs.order_by("id")))
        if company_user is None:
            memberships = list(qs.order_by("id"))
            if len(memberships) == 1:
                company_user = memberships[0]
                if active_company_id is None:
                    try:
                        user.active_company_id = company_user.company_id
                        user.save(update_fields=["active_company"])
                    except Exception:  # noqa: BLE001 — never break the request over this
                        pass
            elif len(memberships) > 1:
                from django.conf import settings as dj_settings

                if getattr(dj_settings, "AUTO_PICK_COMPANY_ON_EMPTY", False):
                    company_user = memberships[0]
                    if company_user is not None and active_company_id is None:
                        try:
                            user.active_company_id = company_user.company_id
                            user.save(update_fields=["active_company"])
                        except Exception:  # noqa: BLE001
                            pass
                else:
                    raise CompanyRequired(memberships)
    request._company_user = company_user
    request._company_user_uid = current_uid
    return company_user


class HasCompany(BasePermission):
    """User must belong to an active company (tenant)."""

    message = "User is not associated with any company."

    def has_permission(self, request, view):
        return get_company_user(request) is not None


class IsOwner(BasePermission):
    """Owner/Admin role required (company settings, users, audit, import commit)."""

    message = "Owner role required."

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


class CanCreateSales(BasePermission):
    """Create / complete sales invoices (BB-000018)."""

    message = "Sales create permission required."

    def has_permission(self, request, view):
        cu = get_company_user(request)
        if cu is None or cu.role == "VIEWER":
            return False
        return cu.role == "OWNER" or cu.can_create_sales


class CanCreatePurchases(BasePermission):
    """Create / complete purchase invoices (BB-000018)."""

    message = "Purchases create permission required."

    def has_permission(self, request, view):
        cu = get_company_user(request)
        if cu is None or cu.role == "VIEWER":
            return False
        return cu.role == "OWNER" or cu.can_create_purchases


class CanCreatePayments(BasePermission):
    """Create receipts / supplier payments (BB-000018)."""

    message = "Payments create permission required."

    def has_permission(self, request, view):
        cu = get_company_user(request)
        if cu is None or cu.role == "VIEWER":
            return False
        return cu.role == "OWNER" or cu.can_create_payments


class CanViewSalesSurfaces(BasePermission):
    """Sales list/retrieve/pdf surfaces — not VIEWER; create-sales, financial reports, or Owner (BB-000297)."""

    message = "Sales view permission required."

    def has_permission(self, request, view):
        cu = get_company_user(request)
        if cu is None or cu.role == "VIEWER":
            return False
        return cu.role == "OWNER" or cu.can_create_sales or cu.can_view_financial_reports


class CanViewPurchaseSurfaces(BasePermission):
    """Purchase list/retrieve/pdf surfaces — not VIEWER; create-purchases, financial reports, or Owner (BB-000297)."""

    message = "Purchases view permission required."

    def has_permission(self, request, view):
        cu = get_company_user(request)
        if cu is None or cu.role == "VIEWER":
            return False
        return cu.role == "OWNER" or cu.can_create_purchases or cu.can_view_financial_reports


class CanViewPaymentSurfaces(BasePermission):
    """Payment list/retrieve surfaces — not VIEWER (BB-000297 / BB-000691)."""

    message = "Payments view permission required."

    def has_permission(self, request, view):
        cu = get_company_user(request)
        if cu is None or cu.role == "VIEWER":
            return False
        return cu.role == "OWNER" or cu.can_create_payments or cu.can_view_financial_reports


class DenyViewerWrite(BasePermission):
    """BB-000553: VIEWER cannot mutate ERP preview modules."""

    message = "Viewers cannot modify this resource."

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        cu = get_company_user(request)
        if cu is None or cu.role == "VIEWER":
            return False
        return True


class CanPostJournals(BasePermission):
    """Post / reverse journals and mutate books masters (BB-000316/200/267)."""

    message = "Journal posting permission required."

    def has_permission(self, request, view):
        cu = get_company_user(request)
        if cu is None or cu.role == "VIEWER":
            return False
        return cu.role == "OWNER" or cu.can_post_journals


class CanViewInventorySurfaces(BasePermission):
    """Stock balances / valuation — not VIEWER; inventory or financial capability (BB-000420)."""

    message = "Inventory view permission required."

    def has_permission(self, request, view):
        cu = get_company_user(request)
        if cu is None or cu.role == "VIEWER":
            return False
        return (
            cu.role == "OWNER"
            or cu.can_manage_inventory
            or cu.can_view_financial_reports
        )


class CanViewMastersCatalog(BasePermission):
    """Party/product masters — deny VIEWER catalog browsing (BB-000422)."""

    message = "Masters view permission required."

    def has_permission(self, request, view):
        cu = get_company_user(request)
        if cu is None or cu.role == "VIEWER":
            return False
        return True


class CanManageFileAssets(BasePermission):
    """File uploads / company PDF list — Owner or financial export roles (BB-000421)."""

    message = "File access permission required."

    def has_permission(self, request, view):
        cu = get_company_user(request)
        if cu is None or cu.role == "VIEWER":
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return (
                cu.role == "OWNER"
                or cu.can_view_financial_reports
                or cu.can_export
                or cu.can_create_sales
                or cu.can_create_purchases
            )
        return cu.role == "OWNER" or cu.can_export or cu.can_create_sales or cu.can_create_purchases
