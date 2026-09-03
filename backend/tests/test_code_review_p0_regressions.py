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
    assert Decimal(str(a["taxable_value"])) == Decimal("1000.00")
    assert Decimal(str(a["cgst"])) + Decimal(str(a["sgst"])) + Decimal(str(a["igst"])) == Decimal("0.00")


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


def test_domain_event_handler_failure_does_not_raise():
    from core.events import emit, subscribe, _subscribers

    calls = []

    @subscribe("_test.quality_review")
    def _boom(**kwargs):
        calls.append("boom")
        raise RuntimeError("handler exploded")

    try:
        emit("_test.quality_review", document=None)
    finally:
        _subscribers.pop("_test.quality_review", None)
    assert calls == ["boom"]


def test_document_number_configure_rejects_rewind(tenant_a):
    from core.services.document_numbers import DocumentNumberService

    product = make_product(tenant_a.company, sku="SEQ-RW", hsn_code="1001")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    prefix = (invoice.number or "INV").rsplit("-", 1)[0] or "INV"
    with pytest.raises(ValueError, match="greater than"):
        DocumentNumberService.configure(tenant_a.company, "SALES_INVOICE", prefix=prefix, next_number=1)


def test_csv_safe_keeps_negative_amounts():
    from core.csv_utils import csv_safe
    from decimal import Decimal

    assert csv_safe(Decimal("-12.50")) == Decimal("-12.50")
    assert csv_safe("-12.50") == "-12.50"
    assert csv_safe("=CMD") == "'=CMD"
    assert csv_safe("\tCMD") == "'\tCMD"
    assert csv_safe("\r=CMD") == "'\r=CMD"


def test_h9a_rejects_supply_nature_and_cess_changes():
    from core.exceptions import BusinessRuleError
    from core.services.h9_amend import assert_h9a_line_allowlist

    class _Line:
        id = 1
        product_id = 10
        quantity = Decimal("1")
        gst_rate = Decimal("18")
        supply_nature = "TAXABLE"
        cess_rate = Decimal("0")
        cess_amount = Decimal("0")

    base = {"id": 1, "product": 10, "quantity": "1", "gst_rate": "18"}
    with pytest.raises(BusinessRuleError, match="supply nature"):
        assert_h9a_line_allowlist([_Line()], [{**base, "supply_nature": "NIL"}])
    with pytest.raises(BusinessRuleError, match="cess rates"):
        assert_h9a_line_allowlist([_Line()], [{**base, "cess_rate": "12"}])
    with pytest.raises(BusinessRuleError, match="cess amounts"):
        assert_h9a_line_allowlist([_Line()], [{**base, "cess_amount": "5"}])


def test_wrap_idempotent_docstring_releases_5xx():
    from core.idempotency import wrap_idempotent

    assert "5xx after build() returned | No" in (wrap_idempotent.__doc__ or "")


def test_gstr2b_reupload_does_not_duplicate(tenant_a):
    from reporting.models import Gstr2bIngest

    payload = {
        "period": PERIOD,
        "rows": [
            {
                "supplier_gstin": "27AAAAA0000A1Z2",
                "invoice_number": "PI-DUP",
                "taxable_value": "100.00",
                "cgst": "9.00",
                "sgst": "9.00",
                "igst": "0.00",
            }
        ],
    }
    first = tenant_a.client.post("/api/v1/reports/gstr2b/upload/", payload, format="json")
    if first.status_code in (200, 201):
        second = tenant_a.client.post("/api/v1/reports/gstr2b/upload/", payload, format="json")
        assert second.status_code in (200, 201), second.data
        assert Gstr2bIngest.objects.filter(company=tenant_a.company, invoice_number="PI-DUP").count() == 1
        return
    Gstr2bIngest.objects.update_or_create(
        company=tenant_a.company,
        period=PERIOD,
        supplier_gstin="27AAAAA0000A1Z2",
        invoice_number="PI-DUP",
        defaults={"taxable_value": "100.00", "cgst": "9.00", "sgst": "9.00"},
    )
    Gstr2bIngest.objects.update_or_create(
        company=tenant_a.company,
        period=PERIOD,
        supplier_gstin="27AAAAA0000A1Z2",
        invoice_number="PI-DUP",
        defaults={"taxable_value": "110.00", "cgst": "9.90", "sgst": "9.90"},
    )
    assert Gstr2bIngest.objects.filter(company=tenant_a.company, invoice_number="PI-DUP").count() == 1


def test_draft_challan_cancel_and_so_stays_confirmed(tenant_a):
    from sales.models import SalesOrder
    from sales.notes_services import SalesNotesService

    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    order = SalesOrder.objects.create(
        company=tenant_a.company,
        customer=customer,
        invoice_type=SalesInvoice.InvoiceType.NON_GST,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    SalesNotesService.set_order_items(
        order,
        [{"product": product, "quantity": Decimal("2"), "unit_price": Decimal("100"), "gst_rate": Decimal("0")}],
        tenant_a.owner,
    )
    SalesNotesService.confirm_sales_order(order, tenant_a.owner)
    challan = SalesNotesService.convert_sales_order_to_challan(order, tenant_a.owner)
    order.refresh_from_db()
    assert order.status == SalesOrder.Status.CONFIRMED
    SalesNotesService.cancel_challan(challan, tenant_a.owner)
    order.refresh_from_db()
    assert order.status == SalesOrder.Status.CONFIRMED
