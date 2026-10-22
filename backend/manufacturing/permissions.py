"""Who may do what in Manufacturing (MFG-00).

The module stays behind ``ENABLE_MANUFACTURING``. Inside it, access is by role, not by the
general inventory capability flags: a sales-counter user who happens to be allowed to adjust
stock still cannot raise a work order.

| Action                                    | Roles                                  |
| read                                      | owner, manager, inventory, accountant, auditor, viewer |
| BOM create / revise / activate            | owner, manager                         |
| work order create / release; issue / return / receipt | owner, manager, inventory |
| cancel a work order                       | owner, manager                         |
| reverse a posted document; reopen         | owner, manager                         |
| close a work order                        | owner, manager, accountant             |
| see costs and variance                    | owner, manager, accountant, auditor    |
"""

from django.http import Http404
from rest_framework.permissions import SAFE_METHODS, BasePermission

import logging
from decimal import InvalidOperation

from core.exceptions import BusinessRuleError
from core.permissions import get_company_user
from core.services.feature_flags import build_feature_flags

VIEW_ROLES = frozenset({"OWNER", "MANAGER", "INVENTORY_STAFF", "ACCOUNTANT", "AUDITOR", "VIEWER"})
PLAN_ROLES = frozenset({"OWNER", "MANAGER"})
WORK_ROLES = frozenset({"OWNER", "MANAGER", "INVENTORY_STAFF"})
REVERSE_ROLES = frozenset({"OWNER", "MANAGER"})
CLOSE_ROLES = frozenset({"OWNER", "MANAGER", "ACCOUNTANT"})
COST_ROLES = frozenset({"OWNER", "MANAGER", "ACCOUNTANT", "AUDITOR"})
BACKDATE_ROLES = frozenset({"OWNER", "MANAGER"})
SETTINGS_ROLES = frozenset({"OWNER", "MANAGER"})


def assert_manufacturing_enabled(company) -> None:
    flags = build_feature_flags(company=company)
    if not flags.get("ENABLE_MANUFACTURING"):
        raise Http404()


def assert_sub_flag(company, key: str) -> None:
    """A sub-module (planning, quality, job work, costing, shop floor) is off unless granted."""
    flags = build_feature_flags(company=company)
    if not flags.get(key):
        raise Http404()


def role_of(request) -> str:
    cu = get_company_user(request)
    return getattr(cu, "role", "") or ""


def can_see_costs(request) -> bool:
    return role_of(request) in COST_ROLES


def can_backdate(request) -> bool:
    return role_of(request) in BACKDATE_ROLES


class MfgRolePermission(BasePermission):
    """Roles per action, read from ``view.mfg_roles``.

    ``view.mfg_roles`` maps an action name to the set of roles allowed. Actions not named
    fall back to read roles for safe methods and ``WORK_ROLES`` for everything else.
    """

    message = "Your role cannot do this in Manufacturing."

    def has_permission(self, request, view):
        cu = get_company_user(request)
        if cu is None:
            return False
        table = getattr(view, "mfg_roles", {}) or {}
        action = getattr(view, "action", None)
        if action in table:
            return cu.role in table[action]
        if request.method in SAFE_METHODS:
            return cu.role in VIEW_ROLES
        return cu.role in WORK_ROLES


logger = logging.getLogger(__name__)


class BadInputIs400:
    """Put first in a view's bases. A number or id the screen should have sent but did not (``abc`` for a quantity or a
    filter) is the caller's mistake, so it answers 400 with a plain message, not 500."""

    def handle_exception(self, exc):
        if isinstance(exc, (ValueError, InvalidOperation)):
            logger.info("manufacturing: unreadable input: %s", exc)
            exc = BusinessRuleError(
                "One of the values sent is not valid. Check the numbers and dates.", code="MFG_BAD_INPUT",
            )
        return super().handle_exception(exc)
