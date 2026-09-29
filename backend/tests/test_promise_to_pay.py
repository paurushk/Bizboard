"""Promise-to-pay: create, list-open, mark-resolved, due-today, tenant isolation."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import CompanyUser, User
from core.models import AuditEvent
from payments.models import PaymentPromise
from payments.promise_to_pay import (
    create_promise,
    list_open_promises,
    promises_due_today,
    resolve_promise,
)
from sales.models import SalesInvoice
from tests.conftest import make_customer

pytestmark = pytest.mark.django_db


def _persona(tenant, role):
    """Create a fresh CompanyUser + authenticated APIClient for `tenant.company`
    with the given role, using that role's invite-time capability defaults."""
    email = f"{role.lower()}@{tenant.company.id}-promise.test"
    user = User.objects.create_user(email=email, password="StrongPass123!", full_name=role)
    cu = CompanyUser(company=tenant.company, user=user, role=role)
    for field, value in (CompanyUser.capability_defaults_for_role(role) or {}).items():
        setattr(cu, field, value)
    cu.save()
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _invoice(company, customer, number, grand="100"):
    return SalesInvoice.objects.create(
        company=company,
        customer=customer,
        number=number,
        status=SalesInvoice.Status.COMPLETED,
        invoice_date=timezone.localdate(),
        grand_total=Decimal(grand),
        taxable_total=Decimal(grand),
    )


def test_create_promise_stamps_audit_and_defaults(tenant_a):
    customer = make_customer(tenant_a.company, name="Promise Co")
    promise = create_promise(
        company=tenant_a.company,
        customer=customer,
        promised_date=date(2026, 10, 1),
        note="Will pay after harvest",
        user=tenant_a.owner,
    )
    assert promise.resolved is False
    assert promise.resolved_at is None
    assert promise.invoice_id is None
    assert AuditEvent.objects.filter(
        company=tenant_a.company, action="CREATE", entity_type="PaymentPromise", entity_id=str(promise.pk)
    ).exists()


def test_create_promise_can_attach_an_invoice(tenant_a):
    customer = make_customer(tenant_a.company, name="Invoice Promise Co")
    invoice = _invoice(tenant_a.company, customer, "PP-1")
    promise = create_promise(
        company=tenant_a.company,
        customer=customer,
        invoice=invoice,
        promised_date=date(2026, 10, 1),
        user=tenant_a.owner,
    )
    assert promise.invoice_id == invoice.id


def test_list_open_promises_excludes_resolved(tenant_a):
    customer = make_customer(tenant_a.company, name="List Co")
    open_promise = create_promise(
        company=tenant_a.company, customer=customer, promised_date=date(2026, 10, 1), user=tenant_a.owner,
    )
    resolved_promise = create_promise(
        company=tenant_a.company, customer=customer, promised_date=date(2026, 10, 2), user=tenant_a.owner,
    )
    resolve_promise(resolved_promise, user=tenant_a.owner)
    open_ids = [p.id for p in list_open_promises(tenant_a.company)]
    assert open_ids == [open_promise.id]


def test_mark_resolved_stamps_resolved_at_and_audit(tenant_a):
    customer = make_customer(tenant_a.company, name="Resolve Co")
    promise = create_promise(
        company=tenant_a.company, customer=customer, promised_date=date(2026, 10, 1), user=tenant_a.owner,
    )
    before = timezone.now()
    resolved = resolve_promise(promise, user=tenant_a.owner)
    assert resolved.resolved is True
    assert resolved.resolved_at is not None
    assert resolved.resolved_at >= before
    assert AuditEvent.objects.filter(
        company=tenant_a.company, action="UPDATE", entity_type="PaymentPromise", entity_id=str(promise.pk)
    ).exists()


def test_mark_resolved_is_idempotent(tenant_a):
    customer = make_customer(tenant_a.company, name="Idempotent Co")
    promise = create_promise(
        company=tenant_a.company, customer=customer, promised_date=date(2026, 10, 1), user=tenant_a.owner,
    )
    resolve_promise(promise, user=tenant_a.owner)
    first_resolved_at = PaymentPromise.objects.get(pk=promise.pk).resolved_at
    resolve_promise(PaymentPromise.objects.get(pk=promise.pk), user=tenant_a.owner)
    assert PaymentPromise.objects.get(pk=promise.pk).resolved_at == first_resolved_at


def test_promises_due_today_is_company_local_day_boundary(tenant_a):
    customer = make_customer(tenant_a.company, name="Due Today Co")
    today = date(2026, 6, 15)
    due_today = create_promise(
        company=tenant_a.company, customer=customer, promised_date=today, user=tenant_a.owner,
    )
    create_promise(
        company=tenant_a.company, customer=customer, promised_date=today - timedelta(days=1), user=tenant_a.owner,
    )
    create_promise(
        company=tenant_a.company, customer=customer, promised_date=today + timedelta(days=1), user=tenant_a.owner,
    )
    rows = list(promises_due_today(tenant_a.company, as_of=today))
    assert [p.id for p in rows] == [due_today.id]


def test_promises_due_today_excludes_resolved(tenant_a):
    customer = make_customer(tenant_a.company, name="Due Resolved Co")
    today = date(2026, 6, 15)
    promise = create_promise(
        company=tenant_a.company, customer=customer, promised_date=today, user=tenant_a.owner,
    )
    resolve_promise(promise, user=tenant_a.owner)
    assert list(promises_due_today(tenant_a.company, as_of=today)) == []


def test_cross_tenant_isolation(tenant_a, tenant_b):
    customer_a = make_customer(tenant_a.company, name="Alpha Co")
    customer_b = make_customer(tenant_b.company, name="Beta Co")
    create_promise(company=tenant_a.company, customer=customer_a, promised_date=date(2026, 10, 1), user=tenant_a.owner)
    create_promise(company=tenant_b.company, customer=customer_b, promised_date=date(2026, 10, 1), user=tenant_b.owner)
    assert list_open_promises(tenant_a.company).count() == 1
    assert list_open_promises(tenant_b.company).count() == 1
    assert list_open_promises(tenant_a.company).first().customer_id == customer_a.id


# --- API surface ---


def test_api_create_list_and_resolve(tenant_a):
    customer = make_customer(tenant_a.company, name="API Co")
    create_resp = tenant_a.client.post(
        "/api/v1/payments/promises/",
        {"customer": customer.id, "promised_date": "2026-10-01", "promised_amount": "250.00", "note": "Paying next week"},
        format="json",
    )
    assert create_resp.status_code == 201, create_resp.data
    promise_id = create_resp.data["id"]
    assert create_resp.data["resolved"] is False

    list_resp = tenant_a.client.get("/api/v1/payments/promises/")
    assert list_resp.status_code == 200
    ids = [row["id"] for row in list_resp.data.get("results", list_resp.data)]
    assert promise_id in ids

    resolve_resp = tenant_a.client.post(f"/api/v1/payments/promises/{promise_id}/resolve/")
    assert resolve_resp.status_code == 200, resolve_resp.data
    assert resolve_resp.data["resolved"] is True
    assert resolve_resp.data["resolved_at"] is not None

    list_after = tenant_a.client.get("/api/v1/payments/promises/")
    ids_after = [row["id"] for row in list_after.data.get("results", list_after.data)]
    assert promise_id not in ids_after


def test_api_rejects_cross_tenant_customer(tenant_a, tenant_b):
    customer_b = make_customer(tenant_b.company, name="Cross Co")
    resp = tenant_a.client.post(
        "/api/v1/payments/promises/",
        {"customer": customer_b.id, "promised_date": "2026-10-01"},
        format="json",
    )
    assert resp.status_code == 400


def test_cross_tenant_isolation_via_api(tenant_a, tenant_b):
    """API-level confirmation that tenant_b cannot see or list tenant_a's promise
    (RLS/company scoping, unaffected by the role gate below)."""
    customer = make_customer(tenant_a.company, name="Isolation Co")
    create_resp = tenant_a.client.post(
        "/api/v1/payments/promises/",
        {"customer": customer.id, "promised_date": "2026-10-01", "promised_amount": "100.00"},
        format="json",
    )
    assert create_resp.status_code == 201, create_resp.data
    promise_id = create_resp.data["id"]

    cross_get = tenant_b.client.get(f"/api/v1/payments/promises/{promise_id}/")
    assert cross_get.status_code == 404

    cross_list = tenant_b.client.get("/api/v1/payments/promises/")
    assert cross_list.status_code == 200
    ids = [row["id"] for row in cross_list.data.get("results", cross_list.data)]
    assert promise_id not in ids


# --- Role gate: create/resolve restricted to OWNER, MANAGER, ACCOUNTANT ---


ALLOWED_ROLES = [CompanyUser.Role.OWNER, CompanyUser.Role.MANAGER, CompanyUser.Role.ACCOUNTANT]
DENIED_ROLES = [
    CompanyUser.Role.SALES_STAFF,
    CompanyUser.Role.INVENTORY_STAFF,
    CompanyUser.Role.AUDITOR,
    CompanyUser.Role.VIEWER,
]


@pytest.mark.parametrize("role", ALLOWED_ROLES)
def test_allowed_roles_can_create_promise(tenant_a, role):
    customer = make_customer(tenant_a.company, name=f"Create OK {role}")
    client = _persona(tenant_a, role)
    resp = client.post(
        "/api/v1/payments/promises/",
        {"customer": customer.id, "promised_date": "2026-10-01", "promised_amount": "500.00"},
        format="json",
    )
    assert resp.status_code == 201, resp.data


@pytest.mark.parametrize("role", DENIED_ROLES)
def test_denied_roles_cannot_create_promise(tenant_a, role):
    customer = make_customer(tenant_a.company, name=f"Create Denied {role}")
    client = _persona(tenant_a, role)
    resp = client.post(
        "/api/v1/payments/promises/",
        {"customer": customer.id, "promised_date": "2026-10-01"},
        format="json",
    )
    assert resp.status_code == 403, resp.data


@pytest.mark.parametrize("role", ALLOWED_ROLES)
def test_allowed_roles_can_resolve_promise(tenant_a, role):
    customer = make_customer(tenant_a.company, name=f"Resolve OK {role}")
    promise = create_promise(
        company=tenant_a.company, customer=customer, promised_date=date(2026, 10, 1), user=tenant_a.owner,
    )
    client = _persona(tenant_a, role)
    resp = client.post(f"/api/v1/payments/promises/{promise.id}/resolve/")
    assert resp.status_code == 200, resp.data
    assert resp.data["resolved"] is True


@pytest.mark.parametrize("role", DENIED_ROLES)
def test_denied_roles_cannot_resolve_promise(tenant_a, role):
    customer = make_customer(tenant_a.company, name=f"Resolve Denied {role}")
    promise = create_promise(
        company=tenant_a.company, customer=customer, promised_date=date(2026, 10, 1), user=tenant_a.owner,
    )
    client = _persona(tenant_a, role)
    resp = client.post(f"/api/v1/payments/promises/{promise.id}/resolve/")
    assert resp.status_code == 403, resp.data
    assert PaymentPromise.objects.get(pk=promise.pk).resolved is False


@pytest.mark.parametrize("role", DENIED_ROLES)
def test_denied_role_can_still_list_and_retrieve(tenant_a, role):
    """List/retrieve stay open to any authenticated company member — only the
    mutating actions are role-gated."""
    customer = make_customer(tenant_a.company, name=f"View OK {role}")
    promise = create_promise(
        company=tenant_a.company, customer=customer, promised_date=date(2026, 10, 1), user=tenant_a.owner,
    )
    client = _persona(tenant_a, role)

    list_resp = client.get("/api/v1/payments/promises/")
    assert list_resp.status_code == 200
    ids = [row["id"] for row in list_resp.data.get("results", list_resp.data)]
    assert promise.id in ids

    detail_resp = client.get(f"/api/v1/payments/promises/{promise.id}/")
    assert detail_resp.status_code == 200
