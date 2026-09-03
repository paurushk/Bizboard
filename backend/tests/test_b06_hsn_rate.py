from datetime import date
from decimal import Decimal

import pytest

from core.models import AuditEvent
from core.services.billing import compute_document_totals
from masters.hsn_catalog import rate_for, seed_starter_hsn_rates
from masters.models import Customer, HsnRate
from reporting.gst_rate_scan import backscan_rate_exposure
from sales.models import SalesInvoice
from tests.conftest import add_stock, make_product


def _gst_invoice(tenant, hsn, invoice_date, gst_rate="18", sku=None, **line_extra):
    tenant.company.gstin = "29ABCDE1234F1ZW"
    tenant.company.state = "Karnataka"
    tenant.company.save(update_fields=["gstin", "state"])
    product = make_product(
        tenant.company,
        sku=sku or f"HSN-{hsn}-{invoice_date}",
        hsn_code=hsn,
        gst_rate=gst_rate,
    )
    add_stock(tenant, product, "10")
    customer, _ = Customer.objects.get_or_create(
        company=tenant.company,
        gstin="29AAAAA0000A1Z5",
        defaults={"name": "Rate Test Buyer", "state": "Karnataka"},
    )
    payload = {
        "customer": customer.id,
        "invoice_type": "GST",
        "invoice_date": invoice_date.isoformat() if hasattr(invoice_date, "isoformat") else invoice_date,
        "items": [
            {
                "product": product.id,
                "quantity": "1",
                "unit_price": "100",
                "gst_rate": gst_rate,
                **line_extra,
            }
        ],
    }
    resp = tenant.client.post("/api/v1/sales/invoices/", payload, format="json")
    assert resp.status_code == 201, resp.data
    done = tenant.client.post(f"/api/v1/sales/invoices/{resp.data['id']}/complete/")
    assert done.status_code == 200, done.data
    return SalesInvoice.objects.get(pk=resp.data["id"])


@pytest.mark.django_db
def test_invoice_date_resolves_pre_and_post_gst2(tenant_a):
    seed_starter_hsn_rates()
    pre = _gst_invoice(tenant_a, "1905", date(2025, 9, 21), gst_rate="18")
    post = _gst_invoice(tenant_a, "1905", date(2025, 9, 23), gst_rate="18")
    pre_item = pre.items.get()
    post_item = post.items.get()
    assert Decimal(pre_item.gst_rate) == Decimal("18")
    assert pre_item.applied_rate == Decimal("18")
    assert pre_item.rate_version == "pre-gst2.0"
    assert Decimal(post_item.gst_rate) == Decimal("5")
    assert post_item.applied_rate == Decimal("5")
    assert post_item.rate_version == "gst2.0-2025-09-22"


@pytest.mark.django_db
def test_editing_hsn_rate_does_not_change_completed_snapshot(tenant_a):
    seed_starter_hsn_rates()
    inv = _gst_invoice(tenant_a, "1905", date(2025, 9, 23), gst_rate="18")
    item = inv.items.get()
    assert item.applied_rate == Decimal("5")
    HsnRate.objects.filter(hsn_sac="1905", version="gst2.0-2025-09-22").update(rate=Decimal("12"))
    compute_document_totals(
        inv,
        list(inv.items.all()),
        tax_enabled=True,
        intra_state=True,
    )
    item.refresh_from_db()
    assert item.applied_rate == Decimal("5")
    assert Decimal(item.gst_rate) == Decimal("5")
    assert rate_for("1905", date(2025, 9, 23))["rate"] == Decimal("12")


@pytest.mark.django_db
def test_rate_override_requires_reason_and_is_audited(tenant_a):
    seed_starter_hsn_rates()
    inv = _gst_invoice(
        tenant_a,
        "1905",
        date(2025, 9, 23),
        gst_rate="18",
        rate_override=True,
        rate_override_reason="Classification dispute — packed namkeen",
    )
    item = inv.items.get()
    assert Decimal(item.gst_rate) == Decimal("18")
    assert item.rate_override is True
    assert AuditEvent.objects.filter(
        company=tenant_a.company,
        description__icontains="override",
    ).exists()


@pytest.mark.django_db
def test_backscan_lists_misrated_lines_with_rupee_delta(tenant_a):
    seed_starter_hsn_rates()
    inv = _gst_invoice(tenant_a, "1905", date(2025, 9, 23), gst_rate="18")
    item = inv.items.get()
    # Filed month billed 18% after the 22 Sep cutover (imported/history fixture).
    type(item).objects.filter(pk=item.pk).update(
        gst_rate=Decimal("18"),
        applied_rate=Decimal("18"),
        rate_override=False,
        rate_version="",
    )
    scan = backscan_rate_exposure(
        tenant_a.company,
        date_from=date(2025, 9, 22),
        date_to=date(2025, 9, 30),
    )
    assert scan["count"] == 1
    assert scan["rows"][0]["invoice_id"] == inv.id
    assert scan["rows"][0]["billed_rate"] == "18.00" or Decimal(scan["rows"][0]["billed_rate"]) == Decimal("18")
    assert Decimal(scan["rows"][0]["expected_rate"]) == Decimal("5")
    assert Decimal(scan["estimated_exposure"]) != Decimal("0")
    resp = tenant_a.client.get(
        "/api/v1/reports/gst-rate-exposure/",
        {"date_from": "2025-09-22", "date_to": "2025-09-30"},
    )
    assert resp.status_code == 200, resp.data


@pytest.mark.django_db
def test_preview_totals_uses_hsn_catalog_rate(tenant_a):
    seed_starter_hsn_rates()
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save(update_fields=["gstin", "state"])
    product = make_product(
        tenant_a.company, sku="HSN-PREVIEW-1905", hsn_code="1905", gst_rate="18"
    )
    add_stock(tenant_a, product, "10")
    customer, _ = Customer.objects.get_or_create(
        company=tenant_a.company,
        gstin="29AAAAA0000A1Z5",
        defaults={"name": "Rate Test Buyer", "state": "Karnataka"},
    )
    payload = {
        "customer": customer.id,
        "invoice_type": "GST",
        "invoice_date": "2025-09-23",
        "items": [
            {
                "product": product.id,
                "quantity": "1",
                "unit_price": "100",
                "gst_rate": "18",
            }
        ],
    }
    preview = tenant_a.client.post(
        "/api/v1/sales/invoices/preview-totals/", payload, format="json"
    )
    assert preview.status_code == 200, preview.data
    # Catalog cutover 22 Sep 2025: 1905 bills at 5%, not the line's 18%.
    assert Decimal(str(preview.data["cgst_total"])) + Decimal(str(preview.data["sgst_total"])) == Decimal("5.00")
