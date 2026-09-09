"""FG-2d — role x capability -> permission truth table.

The EXPECTED table below IS the spec. Every permission class is exercised for
all four roles with that role's invite-time capability defaults applied; drift
between ``CompanyUser.capability_defaults_for_role`` and the permission classes
fails here.

Pure and fast: mocks ``core.permissions.get_company_user``; one DB company, one
loop, no per-case fixture.
"""

from __future__ import annotations

import pytest

from accounts.models import Company, CompanyUser, User
from core import permissions as perms

pytestmark = pytest.mark.django_db

ROLES = ["OWNER", "ACCOUNTANT", "SALES_STAFF", "VIEWER"]

# permission class -> {role: expected has_permission for a write (POST) request}
EXPECTED = {
    "IsOwner":                 {"OWNER": True, "ACCOUNTANT": False, "SALES_STAFF": False, "VIEWER": False},
    "CanManageInventory":      {"OWNER": True, "ACCOUNTANT": False, "SALES_STAFF": False, "VIEWER": False},
    "CanImport":               {"OWNER": True, "ACCOUNTANT": False, "SALES_STAFF": False, "VIEWER": False},
    "CanCancelDocuments":      {"OWNER": True, "ACCOUNTANT": False, "SALES_STAFF": False, "VIEWER": False},
    "CanViewFinancialReports": {"OWNER": True, "ACCOUNTANT": True,  "SALES_STAFF": False, "VIEWER": False},
    "CanExport":               {"OWNER": True, "ACCOUNTANT": True,  "SALES_STAFF": False, "VIEWER": False},
    "CanCreatePurchases":      {"OWNER": True, "ACCOUNTANT": True,  "SALES_STAFF": False, "VIEWER": False},
    # SALES_STAFF can record payments (incl. supplier payments) by default —
    # capability_defaults_for_role("SALES_STAFF")["can_create_payments"] is True.
    # Intentional per the model; flagged for founder awareness.
    "CanCreatePayments":       {"OWNER": True, "ACCOUNTANT": True,  "SALES_STAFF": True,  "VIEWER": False},
    "CanPostJournals":         {"OWNER": True, "ACCOUNTANT": True,  "SALES_STAFF": False, "VIEWER": False},
    "CanCreateSales":          {"OWNER": True, "ACCOUNTANT": False, "SALES_STAFF": True,  "VIEWER": False},
}


class _Req:
    method = "POST"


def _cu_for(company, user, role):
    cu = CompanyUser(company=company, user=user, role=role)
    for k, v in (CompanyUser.capability_defaults_for_role(role) or {}).items():
        setattr(cu, k, v)
    return cu


def test_role_capability_permission_truth_table(db, monkeypatch):
    company = Company.objects.create(name="RBAC Co", state="Karnataka")
    user = User.objects.create_user(email="rbac@x.test", password="StrongPass123!", full_name="rbac")

    failures = []
    for perm_name, per_role in EXPECTED.items():
        perm_cls = getattr(perms, perm_name)
        for role, want in per_role.items():
            cu = _cu_for(company, user, role)
            monkeypatch.setattr(perms, "get_company_user", lambda request, _cu=cu: _cu)
            got = bool(perm_cls().has_permission(_Req(), view=None))
            if got is not want:
                failures.append(f"{perm_name}[{role}]: expected {want}, got {got}")
    assert not failures, "RBAC truth-table drift:\n  " + "\n  ".join(failures)


def test_read_requests_are_not_gated_by_write_only_denies(db, monkeypatch):
    company = Company.objects.create(name="RBAC Co2", state="Karnataka")
    user = User.objects.create_user(email="rbac2@x.test", password="StrongPass123!", full_name="r2")
    cu = _cu_for(company, user, "VIEWER")
    monkeypatch.setattr(perms, "get_company_user", lambda request: cu)

    class _Get:
        method = "GET"

    # DenyViewerWrite lets reads through; a hard role gate (IsOwner) still doesn't.
    assert perms.DenyViewerWrite().has_permission(_Get(), None) is True
    assert perms.IsOwner().has_permission(_Get(), None) is False
