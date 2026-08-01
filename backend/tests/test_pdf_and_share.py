"""Async PDF flow (§14) and share via Notification Service (E4.10)."""

from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

import pytest
from pypdf import PdfReader

from sales.models import SalesInvoice
from sales.pdf import render_gst_tax_invoice
from sales.pdf.helpers import amount_in_words, tax_breakup_by_rate
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _pdf_text(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _complete(tenant, *, product_kwargs=None, lines=None, customer_kwargs=None):
    product_kwargs = product_kwargs or {}
    customer_kwargs = customer_kwargs or {}
    product = make_product(
        tenant.company,
        hsn_code="3004",
        mrp=Decimal("120"),
        **product_kwargs,
    )
    add_stock(tenant, product, "100")
    customer = make_customer(
        tenant.company,
        phone="9876543210",
        email="c@x.test",
        billing_address="12 Test Street",
        **customer_kwargs,
    )
    items = lines or [{"product": product.id, "quantity": "2", "unit_price": "100"}]
    inv = create_draft_invoice(tenant, customer, items)
    resp = tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 200
    return resp.data, product


def test_amount_in_words_indian():
    assert amount_in_words(Decimal("100")) == "One Hundred Rupees Only"
    assert "Thousand" in amount_in_words(Decimal("1234.56"))
    assert "Paise" in amount_in_words(Decimal("1234.56"))


def test_tax_breakup_mixed_rates(tenant_a):
    p12 = make_product(tenant_a.company, sku="P12", gst_rate="12", hsn_code="3004")
    p18 = make_product(tenant_a.company, sku="P18", gst_rate="18", hsn_code="8471")
    add_stock(tenant_a, p12, "10")
    add_stock(tenant_a, p18, "10")
    customer = make_customer(tenant_a.company, state="Karnataka")
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": p12.id, "quantity": "1", "unit_price": "100"},
        {"product": p18.id, "quantity": "1", "unit_price": "100"},
    ])
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 200
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    rows = tax_breakup_by_rate(list(invoice.items.all()), tax_enabled=True)
    labels = {r["label"] for r in rows}
    assert "CGST@6" in labels
    assert "SGST@6" in labels
    assert "CGST@9" in labels
    assert "SGST@9" in labels


def test_pdf_generated_after_complete(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1Z5"
    tenant_a.company.upi_id = "demo@upi"
    tenant_a.company.save(update_fields=["gstin", "upi_id"])
    data, _product = _complete(tenant_a)

    resp = tenant_a.client.get(f"/api/v1/sales/invoices/{data['id']}/pdf-status/")
    assert resp.data["pdf_status"] == "READY"
    assert resp.data["pdf_file"] is not None

    download = tenant_a.client.get(f"/api/v1/sales/invoices/{data['id']}/pdf/")
    assert download.status_code == 200
    content = b"".join(download.streaming_content)
    assert content.startswith(b"%PDF")
    text = _pdf_text(content)
    assert "TAX INVOICE" in text
    assert "ORIGINAL" in text
    assert tenant_a.company.gstin in text
    assert "3004" in text  # HSN snapshot
    assert "Rupees" in text


def test_pdf_download_requires_auth(tenant_a):
    """P0-101 / BUG-703 — PDF download is JWT-gated (FileResponse via API)."""
    from rest_framework.test import APIClient

    data, _ = _complete(tenant_a)
    anon = APIClient()
    resp = anon.get(f"/api/v1/sales/invoices/{data['id']}/pdf/")
    assert resp.status_code == 401


def test_cross_tenant_pdf_download_returns_404(tenant_a, tenant_b):
    """P0-101 / BUG-703 — another tenant cannot download this invoice's PDF."""
    data, _ = _complete(tenant_a)
    resp = tenant_b.client.get(f"/api/v1/sales/invoices/{data['id']}/pdf/")
    assert resp.status_code == 404

    # Owner still can.
    own = tenant_a.client.get(f"/api/v1/sales/invoices/{data['id']}/pdf/")
    assert own.status_code == 200


def test_regenerate_pdf_endpoint(tenant_a):
    data, _ = _complete(tenant_a)
    # Force failed then regenerate
    from sales.models import SalesInvoice

    inv = SalesInvoice.objects.get(pk=data["id"])
    inv.pdf_status = SalesInvoice.PdfStatus.FAILED
    inv.save(update_fields=["pdf_status"])

    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{data['id']}/regenerate-pdf/")
    assert resp.status_code == 200, resp.data
    assert resp.data["pdf_status"] in ("QUEUED", "READY")
    status = tenant_a.client.get(f"/api/v1/sales/invoices/{data['id']}/pdf-status/")
    assert status.data["pdf_status"] == "READY"


def test_pdf_download_returns_409_when_not_ready(tenant_a):
    """P0-404 — download must not sync-call generate_invoice_pdf."""
    from unittest.mock import MagicMock

    data, _ = _complete(tenant_a)
    inv = SalesInvoice.objects.get(pk=data["id"])
    inv.pdf_status = SalesInvoice.PdfStatus.QUEUED
    inv.pdf_file = None
    inv.save(update_fields=["pdf_status", "pdf_file"])

    with patch("sales.views.generate_invoice_pdf") as mock_gen:
        mock_gen.delay = MagicMock()
        download = tenant_a.client.get(f"/api/v1/sales/invoices/{data['id']}/pdf/")
        assert download.status_code == 409, download.data
        assert "retry shortly" in download.data["detail"].lower()
        assert download.data["pdf_status"] == "QUEUED"
        mock_gen.assert_not_called()
        mock_gen.delay.assert_not_called()


def test_pdf_download_enqueues_when_failed(tenant_a):
    """P0-404 — FAILED download enqueues async task and returns 409."""
    from unittest.mock import MagicMock

    data, _ = _complete(tenant_a)
    inv = SalesInvoice.objects.get(pk=data["id"])
    inv.pdf_status = SalesInvoice.PdfStatus.FAILED
    inv.pdf_file = None
    inv.save(update_fields=["pdf_status", "pdf_file"])

    with patch("sales.views.generate_invoice_pdf") as mock_gen:
        mock_gen.delay = MagicMock()
        download = tenant_a.client.get(f"/api/v1/sales/invoices/{data['id']}/pdf/")
        assert download.status_code == 409, download.data
        assert "retry shortly" in download.data["detail"].lower()
        assert download.data["pdf_status"] == "QUEUED"
        mock_gen.assert_not_called()
        mock_gen.delay.assert_called_once_with(inv.pk)


def test_header_patch_preserves_line_snapshots(tenant_a):
    data, product = _complete(tenant_a)
    from masters.models import Product
    from sales.models import SalesItem

    item = SalesItem.objects.get(invoice_id=data["id"])
    original_hsn = item.hsn_code
    Product.objects.filter(pk=product.id).update(hsn_code="9999")

    resp = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{data['id']}/",
        {"notes": "header only"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    item = SalesItem.objects.get(invoice_id=data["id"])
    assert item.hsn_code == original_hsn
    assert resp.data["notes"] == "header only"


def test_pdf_duplicate_copy_stamp(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1Z5"
    tenant_a.company.save(update_fields=["gstin"])
    data, _ = _complete(tenant_a)

    download = tenant_a.client.get(
        f"/api/v1/sales/invoices/{data['id']}/pdf/",
        {"copy": "DUPLICATE"},
    )
    assert download.status_code == 200
    content = b"".join(download.streaming_content)
    assert content.startswith(b"%PDF")
    text = _pdf_text(content)
    assert "DUPLICATE" in text
    assert "TAX INVOICE" in text


def test_pdf_line_snapshots_stable(tenant_a):
    data, product = _complete(tenant_a)
    invoice = SalesInvoice.objects.get(pk=data["id"])
    item = invoice.items.get()
    assert item.hsn_code == "3004"
    assert item.mrp == Decimal("120")
    assert item.unit_name

    # Mutate product master — snapshots on the line must stay.
    product.hsn_code = "9999"
    product.mrp = Decimal("999")
    product.save(update_fields=["hsn_code", "mrp"])
    item.refresh_from_db()
    assert item.hsn_code == "3004"
    assert item.mrp == Decimal("120")


def test_pdf_multipage_totals(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1Z5"
    tenant_a.company.save(update_fields=["gstin"])
    products = []
    for i in range(32):
        p = make_product(
            tenant_a.company,
            name=f"Item {i}",
            sku=f"SKU-{i}",
            hsn_code="8471",
            mrp=Decimal("50"),
        )
        add_stock(tenant_a, p, "50")
        products.append(p)
    customer = make_customer(tenant_a.company, phone="9000000000")
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": p.id, "quantity": "1", "unit_price": "10"} for p in products],
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 200
    invoice = SalesInvoice.objects.select_related("company", "customer").prefetch_related(
        "items__product"
    ).get(pk=inv["id"])
    pdf = render_gst_tax_invoice(invoice, copy="ORIGINAL")
    assert pdf.startswith(b"%PDF")
    reader = PdfReader(BytesIO(pdf))
    assert len(reader.pages) >= 2
    text = _pdf_text(pdf)
    assert "TAX INVOICE" in text
    assert "TOTAL" in text


def test_draft_invoice_has_no_pdf(tenant_a):
    product = make_product(tenant_a.company)
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"}
    ])
    assert inv["pdf_status"] == "NONE"
    resp = tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/pdf/")
    assert resp.status_code == 400


def test_share_whatsapp_returns_link(tenant_a):
    data, _ = _complete(tenant_a)
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{data['id']}/share/", {
        "channel": "whatsapp",
    }, format="json")
    assert resp.status_code == 200
    assert resp.data["status"] == "SENT"
    assert resp.data["share_link"].startswith("https://wa.me/")


def test_share_email_queued_and_sent(tenant_a):
    data, _ = _complete(tenant_a)
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{data['id']}/share/", {
        "channel": "email",
    }, format="json")
    assert resp.status_code == 200
    # Console email backend + eager celery → SENT
    assert resp.data["status"] == "SENT"

    listing = tenant_a.client.get("/api/v1/notifications/")
    assert listing.data["count"] >= 1


def test_cannot_share_draft(tenant_a):
    product = make_product(tenant_a.company)
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"}
    ])
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/share/", {
        "channel": "whatsapp",
    }, format="json")
    assert resp.status_code == 400


@patch("sales.pdf.render_gst_tax_invoice", side_effect=RuntimeError("pdf boom"))
def test_complete_survives_pdf_failure(mock_pdf, tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"},
    ])
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 200, resp.data
    assert resp.data["status"] == "COMPLETED"
    assert resp.data["number"].startswith("INV-")
    status = tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/pdf-status/")
    assert status.data["pdf_status"] == "FAILED"
    mock_pdf.assert_called()


def test_retail_pdf_shows_tax_columns(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1Z5"
    tenant_a.company.save(update_fields=["gstin"])
    product = make_product(tenant_a.company, gst_rate="18", hsn_code="3004")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100"}],
        invoice_type="RETAIL",
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 200
    invoice = SalesInvoice.objects.prefetch_related("items__product").get(pk=inv["id"])
    pdf = render_gst_tax_invoice(invoice, copy="ORIGINAL")
    text = _pdf_text(pdf)
    assert "TAX" in text or "CGST" in text or "18" in text
    assert Decimal(invoice.cgst_total) + Decimal(invoice.sgst_total) > 0


def test_pdf_line_total_row_uses_sum_of_line_amounts(tenant_a):
    """Line TOTAL amount must be Σ line_total, not grand_total (charges/round-off)."""
    product = make_product(tenant_a.company, gst_rate="0")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"},
    ])
    # Header charges inflate grand_total above line totals
    tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv['id']}/",
        {"additional_charges": "25", "auto_round_off": False},
        format="json",
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 200
    invoice = SalesInvoice.objects.prefetch_related("items__product").get(pk=inv["id"])
    line_sum = sum(Decimal(i.line_total) for i in invoice.items.all())
    assert invoice.grand_total != line_sum
    pdf = render_gst_tax_invoice(invoice, copy="ORIGINAL")
    text = _pdf_text(pdf)
    # Both appear: line TOTAL (100) and footer TOTAL (125)
    assert "100.00" in text
    assert "125.00" in text
    assert "non-taxable" in text.lower()
    assert "Additional Charges" in text


def test_pdf_before_tax_discount_already_reflected(tenant_a):
    """P0-204b — BEFORE_TAX discount must not look like a post-tax deduction."""
    product = make_product(tenant_a.company, gst_rate="18")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "1", "unit_price": "100"},
    ])
    patch = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv['id']}/",
        {
            "invoice_discount": "10",
            "invoice_discount_mode": "BEFORE_TAX",
            "auto_round_off": True,
        },
        format="json",
    )
    assert patch.status_code == 200, patch.data
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 200, resp.data
    invoice = SalesInvoice.objects.prefetch_related("items__product").get(pk=inv["id"])
    assert invoice.invoice_discount_mode == "BEFORE_TAX"
    assert invoice.taxable_total == Decimal("90.00")
    pdf = render_gst_tax_invoice(invoice, copy="ORIGINAL")
    text = _pdf_text(pdf)
    compact = " ".join(text.split())
    assert "already reflected" in text.lower()
    assert "Discount (already reflected above)" in compact
    # Must not present a bare post-tax Discount row (without the already-reflected note).
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Discount") and "already reflected" not in stripped.lower():
            # Allow wrapped continuation lines that only say "above)"
            if stripped.lower() in {"above)", "above"}:
                continue
            # A lone "Discount" label without the note would imply double deduction.
            if stripped == "Discount":
                raise AssertionError("PDF implies post-tax Discount deduction")


def test_pdf_totals_match_db_odd_paise_and_before_tax(tenant_a):
    """P0-211 / F11 — render → extract TOTAL → assert vs DB (F3 + F6)."""
    from sales.pdf.helpers import format_money

    cases = [
        {
            "id": "f3_odd_paise",
            "unit_price": "10.05",
            "gst_rate": "18",
            "extra": {"auto_round_off": True},
        },
        {
            "id": "f6_before_tax",
            "unit_price": "100",
            "gst_rate": "18",
            "extra": {
                "invoice_discount": "10",
                "invoice_discount_mode": "BEFORE_TAX",
                "auto_round_off": True,
            },
        },
    ]
    for case in cases:
        product = make_product(
            tenant_a.company,
            sku=f"PDF-{case['id']}",
            gst_rate=case["gst_rate"],
        )
        add_stock(tenant_a, product, "10")
        customer = make_customer(tenant_a.company, name=f"Cust {case['id']}")
        inv = create_draft_invoice(tenant_a, customer, [
            {"product": product.id, "quantity": "1", "unit_price": case["unit_price"]},
        ])
        if case["extra"]:
            assert tenant_a.client.patch(
                f"/api/v1/sales/invoices/{inv['id']}/", case["extra"], format="json",
            ).status_code == 200
        resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
        assert resp.status_code == 200, resp.data
        invoice = SalesInvoice.objects.prefetch_related("items__product").get(pk=inv["id"])
        pdf = render_gst_tax_invoice(invoice, copy="ORIGINAL")
        text = _pdf_text(pdf)
        assert format_money(invoice.grand_total) in text, (
            f"{case['id']}: PDF missing grand_total {invoice.grand_total}"
        )
