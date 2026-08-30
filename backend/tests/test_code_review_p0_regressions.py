"""Regressions for P0/P1 code-review findings (CR-001, CR-004, CR-029, CR-041)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone

from billing.models import Plan, Subscription
from billing.services import company_writes_blocked, start_or_update_subscription
from reporting.gst_returns import build_gstr1, build_gstr3b
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db

PERIOD = timezone.localdate().strftime("%Y-%m")


def _gst_company(tenant):
    tenant.company.gstin = "29ABCDE1234F1ZW"
    tenant.company.state = "Karnataka"
    tenant.company.save()
    return tenant.company


def _plan(**kwargs):
    defaults = {
        "name": "Starter",
        "slug": kwargs.pop("slug", "cr-starter"),
        "seat_limit": 2,
        "modules": {},
        "price_paise": 49900,
    }
    defaults.update(kwargs)
    return Plan.objects.create(**defaults)


@override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
def test_cr001_active_checkout_stays_active(tenant_a):
    plan = _plan(slug="cr-active")
    Subscription.objects.create(
        company=tenant_a.company,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        current_period_end=timezone.now() + timedelta(days=30),
    )
    sub, _order = start_or_update_subscription(company=tenant_a.company, plan=plan)
    assert sub.status == Subscription.Status.ACTIVE
    assert company_writes_blocked(tenant_a.company) is False


def test_cr004_gstr3b_31a_excludes_sales_rcm(tenant_a):
    _gst_company(tenant_a)
    product = make_product(tenant_a.company, sku="RCM-31A", hsn_code="1001")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company, gstin="29BBBBB0000B1ZP", state="Karnataka")
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
    )
    tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv['id']}/",
        {"is_reverse_charge": True},
        format="json",
    )
    SalesInvoice.objects.filter(pk=inv["id"]).update(invoice_date=f"{PERIOD}-10")
    ok = tenant_a.client.post(
        f"/api/v1/sales/invoices/{inv['id']}/complete/",
        {"confirm_sales_rcm": True},
        format="json",
    )
    assert ok.status_code == 200, ok.data
    g1 = build_gstr1(tenant_a.company, PERIOD)
    assert any(row.get("rchrg") == "Y" for row in g1.get("b2b") or [])
    g3 = build_gstr3b(tenant_a.company, PERIOD, gstr1=g1)
    a = g3["outward_supplies"]["a_taxable_other_than_zero_rated"]
    assert Decimal(str(a["taxable_value"])) == Decimal("0.00")


def test_cr029_gstr1_doc_cancelled_counts_series(tenant_a):
    _gst_company(tenant_a)
    product = make_product(tenant_a.company, sku="DOC-CXL", hsn_code="1001")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company, gstin="29CCCCC0000C1ZQ", state="Karnataka")
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "200", "gst_rate": "18"}],
    )
    SalesInvoice.objects.filter(pk=inv["id"]).update(invoice_date=f"{PERIOD}-08")
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    prefix = "".join(ch for ch in (invoice.number or "") if not ch.isdigit()) or "INV"
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/cancel/").status_code == 200
    payload = build_gstr1(tenant_a.company, PERIOD)
    series_rows = [r for r in payload["doc"] if r.get("series") == prefix]
    assert series_rows
    assert series_rows[0]["cancelled"] >= 1


def test_cr041_login_without_membership_rejects_tokens(db):
    from accounts.models import User
    from rest_framework.test import APIClient

    User.objects.create_user(email="orphan@alpha.test", password="StrongPass123!", full_name="Orphan")
    resp = APIClient().post(
        "/api/v1/auth/login/",
        {"email": "orphan@alpha.test", "password": "StrongPass123!"},
        format="json",
    )
    assert resp.status_code == 403
    assert "refresh" not in (resp.data or {})
    assert "access" not in (resp.data or {})
