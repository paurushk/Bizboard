"""Roles for quality work. The module also needs ENABLE_MANUFACTURING and the MFG_QUALITY flag."""

from django.http import Http404
from rest_framework.permissions import SAFE_METHODS, BasePermission

from core.permissions import get_company_user
from core.services.feature_flags import build_feature_flags

VIEW_ROLES = frozenset({"OWNER", "MANAGER", "INVENTORY_STAFF", "ACCOUNTANT", "AUDITOR", "VIEWER"})
WORK_ROLES = frozenset({"OWNER", "MANAGER", "INVENTORY_STAFF"})   # inspectors
SETUP_ROLES = frozenset({"OWNER", "MANAGER"})                      # templates, defect codes, overrides


def assert_quality_enabled(company) -> None:
    flags = build_feature_flags(company=company)
    if not (flags.get("ENABLE_MANUFACTURING") and flags.get("MFG_QUALITY")):
        raise Http404()


def role_of(request) -> str:
    cu = get_company_user(request)
    return getattr(cu, "role", "") or ""


class QualityRolePermission(BasePermission):
    message = "Your role cannot do this in Quality."

    def has_permission(self, request, view):
        cu = get_company_user(request)
        if cu is None:
            return False
        table = getattr(view, "quality_roles", {}) or {}
        action = getattr(view, "action", None)
        if action in table:
            return cu.role in table[action]
        if request.method in SAFE_METHODS:
            return cu.role in VIEW_ROLES
        return cu.role in WORK_ROLES
