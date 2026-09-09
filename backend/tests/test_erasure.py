"""SR-40..45 / D13 — automated tenant right-to-erasure."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.test import override_settings

from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db


def _load_company_with_data(tenant):
    company = tenant.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    product = make_product(company, gst_rate="18")
    add_stock(tenant, product, "20")
    make_supplier(company)
    customer = make_customer(company, gstin="29AAAAA0000A1ZY")
    inv = create_draft_invoice(
        tenant, customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100.00", "gst_rate": "18"}],
    )
    assert tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    tenant.client.post("/api/v1/payments/receipts/", {
        "customer": customer.id, "amount": "236.00", "method": "CASH",
        "allocations": [{"invoice": inv["id"], "amount": "236.00"}],
    }, format="json")
    return company


def _remaining_rows_for_company(company_id: int) -> list[str]:
    from accounts.erasure import company_fk_relations
    from django.apps import apps

    hits = []
    for label, fname, _od in company_fk_relations():
        model = apps.get_model(label)
        n = model.objects.filter(**{f"{fname}_id": company_id}).count()
        if n:
            hits.append(f"{label}.{fname}={n}")
    return hits


# --- SR-41: wipe-set completeness drift guard ----------------------------------

def test_erasure_model_coverage_has_not_drifted():
    from accounts.erasure import assert_erasure_model_coverage

    assert_erasure_model_coverage()  # raises AssertionError listing any unhandled FK


# --- SR-43 + SR-45: full erasure leaves no rows, no orphaned audit -------------

def test_erase_company_removes_every_owned_row(tenant_a):
    from accounts.erasure import erase_company
    from accounts.models import Company, TenantErasureLog
    from core.models import AuditEvent, MoneyFieldAudit, StatutoryDocumentEvent

    company = _load_company_with_data(tenant_a)
    company_id = company.pk
    assert AuditEvent.objects.filter(company_id=company_id).exists()

    result = erase_company(company, requested_by_email="owner@example.com", reason="DPDP req #1")

    assert not Company.objects.filter(pk=company_id).exists()
    leftovers = _remaining_rows_for_company(company_id)
    assert leftovers == [], leftovers
    # audit trails are deleted, not orphaned (SR-45)
    assert not AuditEvent.objects.filter(company_id=company_id).exists()
    assert not MoneyFieldAudit.objects.filter(company_id=company_id).exists()
    assert not StatutoryDocumentEvent.objects.filter(company_id=company_id).exists()
    # SR-44: an export checksum was recorded on the immutable log
    log = TenantErasureLog.objects.get(pk=result.log_id)
    assert log.company_id == company_id
    assert log.requested_by_email == "owner@example.com"
    assert len(log.export_sha256) == 64


def test_erase_company_skip_export_records_no_checksum(tenant_a):
    from accounts.erasure import erase_company
    from accounts.models import TenantErasureLog

    company = _load_company_with_data(tenant_a)
    result = erase_company(company, requested_by_email="cli", skip_export=True)
    assert TenantErasureLog.objects.get(pk=result.log_id).export_sha256 == ""


# --- SR-42: owner endpoint, gated + confirm-guarded ---------------------------

def test_erase_endpoint_is_404_when_flag_off(tenant_a):
    _load_company_with_data(tenant_a)
    resp = tenant_a.client.post("/api/v1/company/erase/", {"confirm": tenant_a.company.name}, format="json")
    assert resp.status_code == 404


@override_settings(ENABLE_TENANT_ERASURE=True)
def test_erase_endpoint_requires_exact_name_confirm(tenant_a):
    _load_company_with_data(tenant_a)
    bad = tenant_a.client.post("/api/v1/company/erase/", {"confirm": "wrong name"}, format="json")
    assert bad.status_code == 400


@override_settings(ENABLE_TENANT_ERASURE=True)
def test_erase_endpoint_erases_and_returns_export(tenant_a):
    from accounts.models import Company

    company = _load_company_with_data(tenant_a)
    company_id = company.pk
    resp = tenant_a.client.post(
        "/api/v1/company/erase/",
        {"confirm": company.name, "reason": "data-subject request"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["erased"] is True
    assert len(resp.data["export_sha256"]) == 64
    assert resp.data["export_b64"]
    assert not Company.objects.filter(pk=company_id).exists()
    assert _remaining_rows_for_company(company_id) == []


@override_settings(ENABLE_TENANT_ERASURE=True)
def test_erase_endpoint_forbidden_for_non_owner(tenant_a):
    _load_company_with_data(tenant_a)
    resp = tenant_a.staff_client.post(
        "/api/v1/company/erase/", {"confirm": tenant_a.company.name}, format="json",
    )
    assert resp.status_code in (403, 404)
    from accounts.models import Company

    assert Company.objects.filter(pk=tenant_a.company.pk).exists()
