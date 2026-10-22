"""STG-17: sign-in audit rows must be writable under FORCE RLS without an ambient tenant.

Found on staging when the api moved to a non-superuser DB role: LOGIN / MFA_* audit writes run
before the middleware can set ``app.company_id`` and failed with "new row violates row-level
security policy for table core_auditevent". ``AuditService.log`` now scopes the write to the
event's own company (``core.rls.company_scope``).
"""

import pytest
from django.db import connection
from django.test import override_settings

from core.models import AuditEvent
from core.rls import company_scope
from core.services.audit import AuditService
from tests.rls_helpers import restricted_db_role  # noqa: F401 - pytest fixture


def test_company_scope_is_a_noop_without_rls(tenant_a):
    with company_scope(tenant_a.company.pk):
        pass
    event = AuditService.log(company=tenant_a.company, action="LOGIN", entity_type="User", entity_id=1)
    assert AuditEvent.objects.filter(pk=event.pk).exists()


needs_pg = pytest.mark.skipif(connection.vendor != "postgresql", reason="Postgres session settings (GUCs)")


def _guc(name):
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting(%s, true)", [name])
        return cursor.fetchone()[0] or ""


@needs_pg
@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
@override_settings(POSTGRES_RLS_ENABLED=True)
def test_company_scope_sets_and_restores_the_tenant_guc(tenant_a):
    cid = tenant_a.company.pk
    with company_scope(cid):
        assert _guc("app.company_id") == str(cid)
    assert _guc("app.company_id") == ""


@needs_pg
@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
@override_settings(POSTGRES_RLS_ENABLED=True)
def test_company_scope_keeps_an_enclosing_bypass(tenant_a):
    from core.rls import rls_bypass

    with rls_bypass():
        with company_scope(None):
            assert _guc("app.rls_bypass") == "1"
        assert _guc("app.rls_bypass") == "1"
    assert _guc("app.rls_bypass") == ""


@needs_pg
@pytest.mark.postgres
@pytest.mark.django_db(transaction=True)
@override_settings(POSTGRES_RLS_ENABLED=True)
def test_signup_works_under_a_non_superuser_role(restricted_db_role):  # noqa: F811 - pytest fixture
    """Sign-up creates the company and then writes tenant tables before any tenant is known."""
    from rest_framework.test import APIClient

    from accounts.models import Company
    from core.rls import rls_bypass
    from tests.conftest import register_via_api

    with override_settings(OTP_DEBUG_ECHO=True):
        resp = register_via_api(
            APIClient(),
            {
                "company_name": "RLS Signup Co",
                "email": "rls-signup@example.test",
                "password": "StrongPass123!",
                "state": "Karnataka",
            },
        )
    assert resp.status_code == 200, resp.data
    with rls_bypass():
        company = Company.objects.get(name="RLS Signup Co")
        from inventory.models import Warehouse

        assert Warehouse.objects.filter(company=company).exists()
        assert AuditEvent.objects.filter(company=company, action="CREATE", entity_type="Company").exists()
