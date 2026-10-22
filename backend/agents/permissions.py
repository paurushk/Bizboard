"""Role checks used by specs. Each takes a CompanyUser and returns bool.

They reuse the existing capability fields and the assistant's access table; no new permission model.
The server is the authority: the web mirror in utils/permissions.ts only hides buttons.
"""

from __future__ import annotations


def _role(cu) -> str:
    return getattr(cu, "role", "") or ""


def is_owner_or_manager(cu) -> bool:
    return cu is not None and _role(cu) in ("OWNER", "MANAGER")


def owner_manager_accountant(cu) -> bool:
    return cu is not None and _role(cu) in ("OWNER", "MANAGER", "ACCOUNTANT")


def can_remind(cu) -> bool:
    """Same rule as the assistant's payment-reminder tool."""
    from insights.assistant import cu_has_access

    return cu is not None and cu_has_access(cu, "reminder")


def can_see_reports(cu) -> bool:
    from insights.assistant import cu_has_access

    return cu is not None and cu_has_access(cu, "reports")


def can_create_sales(cu) -> bool:
    return cu is not None and _role(cu) != "VIEWER" and (_role(cu) == "OWNER" or bool(getattr(cu, "can_create_sales", False)))


def can_create_purchases(cu) -> bool:
    return cu is not None and _role(cu) != "VIEWER" and (_role(cu) == "OWNER" or bool(getattr(cu, "can_create_purchases", False)))


def can_manage_inventory(cu) -> bool:
    return cu is not None and (_role(cu) == "OWNER" or bool(getattr(cu, "can_manage_inventory", False)))


def deny_all(cu) -> bool:
    return False
