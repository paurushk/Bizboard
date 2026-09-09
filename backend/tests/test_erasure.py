"""SR-40..45 / D13 — automated tenant right-to-erasure (tombstone + hard)."""

from __future__ import annotations

import pytest
from django.test import override_settings

from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db


def _load_company_with_data(tenant):
    company = tenant.company
    company.accounting_enabled = True
    company.gstin = "29ABCDE1234F1ZW"
    company.address = "1 MG Road"
    company.save(update_fields=["accounting_enabled", "gstin", "address"])
    product = make_product(company, gst_rate="18")
    add_stock(tenant, product, "20")
    make_supplier(company)
    customer = make_customer(company, gstin="29AAAAA0000A1ZY", phone="9876500000")
    inv = create_draft_invoice(
        tenant, customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100.00", "gst_rate": "18"}],
    )
    assert tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    r = tenant.client.post("/api/v1/payments/receipts/", {
        "customer": customer.id, "amount": "236.00", "mode": "CASH",
    }, format="json")
    tenant.client.post("/api/v1/payments/allocations/", {
        "receipt": r.data["id"], "sales_invoice": inv["id"], "amount": "236.00",
    }, format="json")
    return company


def _non_retained_leftovers(company_id: int) -> list[str]:
    from accounts.erasure import PROTECT_MODELS_HANDLED, TOMBSTONE_RETAINED, company_fk_relations
    from django.apps import apps

    hits = []
    for label, fname, _od in company_fk_relations():
        if label in TOMBSTONE_RETAINED or label in PROTECT_MODELS_HANDLED:
            continue
        model = apps.get_model(label)
        n = model.objects.filter(**{f"{fname}_id": company_id}).count()
        if n:
            hits.append(f"{label}={n}")
    return hits


# --- SR-41 -------------------------------------------------------------------

def test_erasure_model_coverage_has_not_drifted():
    from accounts.erasure import assert_erasure_model_coverage

    assert_erasure_model_coverage()


# --- SR-40 tombstone -------------------------------------------------------------

def test_tombstone_keeps_scrubbed_tax_docs_and_company(tenant_a):
    from accounts.erasure import erase_company
    from accounts.models import Company, TenantErasureLog
    from core.models import AuditEvent
    from masters.models import Customer
    from sales.models import SalesInvoice

    company = _load_company_with_data(tenant_a)
    cid = company.pk

    result = erase_company(company, mode="tombstone", requested_by_email="o@x.com", reason="req#1")

    tomb = Company.objects.get(pk=cid)  # company row survives
    assert tomb.erased_at is not None
    assert tomb.name == f"[erased tenant {cid}]"
    assert tomb.gstin == "" and tomb.address == ""

    # statutory tax documents retained
    assert SalesInvoice.objects.filter(company_id=cid).count() == 1
    # party PII scrubbed
    cust = Customer.objects.filter(company_id=cid).first()
    assert cust is not None and cust.name == "[erased]"
    assert cust.phone == "" and cust.gstin == ""

    # everything operational is gone
    assert _non_retained_leftovers(cid) == []
    assert not AuditEvent.objects.filter(company_id=cid).exists()

    log = TenantErasureLog.objects.get(pk=result.log_id)
    assert log.mode == "tombstone"
    assert log.retained_counts.get("sales.SalesInvoice") == 1
    assert len(log.export_sha256) == 64


def test_purge_hard_deletes_expired_tombstone(tenant_a):
    from datetime import timedelta

    from accounts.erasure import erase_company, purge_expired_tombstones
    from accounts.models import Company
    from django.utils import timezone
    from sales.models import SalesInvoice

    company = _load_company_with_data(tenant_a)
    cid = company.pk
    erase_company(company, mode="tombstone", requested_by_email="o@x.com", skip_export=True)

    Company.objects.filter(pk=cid).update(erased_at=timezone.now() - timedelta(days=365 * 9))
    purged = purge_expired_tombstones()

    assert purged == 1
    assert not Company.objects.filter(pk=cid).exists()
    assert not SalesInvoice.objects.filter(company_id=cid).exists()


# --- SR-42..45 hard mode ------------------------------------------------------

def test_hard_erase_removes_everything(tenant_a):
    from accounts.erasure import company_fk_relations, erase_company
    from accounts.models import Company
    from django.apps import apps

    company = _load_company_with_data(tenant_a)
    cid = company.pk
    erase_company(company, mode="hard", requested_by_email="cli", skip_export=True)

    assert not Company.objects.filter(pk=cid).exists()
    for label, fname, _od in company_fk_relations():
        model = apps.get_model(label)
        assert model.objects.filter(**{f"{fname}_id": cid}).count() == 0, label


# --- SR-42 endpoint --------------------------------------------------------------

def test_erase_endpoint_404_when_flag_off(tenant_a):
    _load_company_with_data(tenant_a)
    resp = tenant_a.client.post("/api/v1/company/erase/", {"confirm": tenant_a.company.name}, format="json")
    assert resp.status_code == 404


@override_settings(ENABLE_TENANT_ERASURE=True)
def test_erase_endpoint_defaults_to_tombstone(tenant_a):
    from accounts.models import Company
    from sales.models import SalesInvoice

    company = _load_company_with_data(tenant_a)
    cid = company.pk
    resp = tenant_a.client.post(
        "/api/v1/company/erase/", {"confirm": company.name, "reason": "dsr"}, format="json",
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["mode"] == "tombstone"
    assert resp.data["retained_counts"].get("sales.SalesInvoice") == 1
    assert Company.objects.get(pk=cid).erased_at is not None
    assert SalesInvoice.objects.filter(company_id=cid).count() == 1


@override_settings(ENABLE_TENANT_ERASURE=True)
def test_erase_endpoint_requires_exact_name(tenant_a):
    _load_company_with_data(tenant_a)
    bad = tenant_a.client.post("/api/v1/company/erase/", {"confirm": "nope"}, format="json")
    assert bad.status_code == 400


@override_settings(ENABLE_TENANT_ERASURE=True)
def test_erase_endpoint_forbidden_for_non_owner(tenant_a):
    _load_company_with_data(tenant_a)
    resp = tenant_a.staff_client.post(
        "/api/v1/company/erase/", {"confirm": tenant_a.company.name}, format="json",
    )
    assert resp.status_code in (403, 404)
    from accounts.models import Company

    assert Company.objects.filter(pk=tenant_a.company.pk).exists()
