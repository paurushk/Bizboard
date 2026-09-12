"""Golden snapshots for GSTR-2B reconciliation and the GST tax-invoice PDF.

- GSTR-2B: after ingesting 2B rows for a period (one that matches a books
  purchase, one that does not), pin the match-summary shape + the claimable-ITC
  figures so a change to the 2B matcher / ITC rule shows as a diff.
- Invoice PDF: render the reportlab GST tax invoice and pin the extracted text
  (volatile lines stripped) so a layout / label / figure regression shows as a
  diff. Text is extracted with pypdf (already a dependency).

Baselines: ``SNAPSHOT_UPDATE=1 pytest tests/snapshots/`` — the diff MUST appear
in the PR. Missing baseline -> the test skips (CI stays green until baselined).
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def _shape(node, depth=0):
    if isinstance(node, dict):
        return {k: _shape(v, depth + 1) for k, v in sorted(node.items())}
    if isinstance(node, list):
        return {"_list_of": _shape(node[0], depth + 1) if node else "<empty>"}
    return "<scalar>"


def test_gstr2b_reconciliation_snapshot(tenant_a, assert_snapshot):
    company = tenant_a.company
    company.accounting_enabled = True
    company.gstin = "29AAAAA0000A1ZY"
    company.save(update_fields=["accounting_enabled", "gstin"])

    product = make_product(company, gst_rate="18", purchase_price="60")
    add_stock(tenant_a, product, "5", unit_cost="60")
    supplier = make_supplier(company, state="Karnataka", gstin="29BBBBB1111B1Z5")

    pur = create_draft_purchase(
        tenant_a, supplier,
        [{"product": product.id, "quantity": "10", "unit_price": "60.00", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(
        f"/api/v1/purchases/invoices/{pur['id']}/complete/"
    ).status_code == 200

    from purchases.models import PurchaseInvoice
    from reporting.gstr2b import claimable_itc_from_2b, match_gstr2b_to_purchases
    from reporting.models import Gstr2bIngest

    pi = PurchaseInvoice.objects.get(pk=pur["id"])
    period = pi.invoice_date.strftime("%Y-%m")

    # row 1 — an exact counterpart of the books purchase (should MATCH)
    Gstr2bIngest.objects.create(
        company=company, period=period, supplier_gstin="29BBBBB1111B1Z5",
        invoice_number=pi.number, invoice_date=pi.invoice_date,
        taxable_value=Decimal("600.00"), cgst=Decimal("54.00"), sgst=Decimal("54.00"),
        match_status=Gstr2bIngest.MatchStatus.UNMATCHED,
        itc_eligibility=Gstr2bIngest.ItcEligibility.CLAIMABLE,
        ims_action=Gstr2bIngest.ImsAction.ACCEPT,
    )
    # row 2 — a supplier invoice not in the books (stays UNMATCHED)
    Gstr2bIngest.objects.create(
        company=company, period=period, supplier_gstin="29CCCCC2222C1Z5",
        invoice_number="MISSING-1", invoice_date=pi.invoice_date,
        taxable_value=Decimal("1000.00"), cgst=Decimal("90.00"), sgst=Decimal("90.00"),
        match_status=Gstr2bIngest.MatchStatus.UNMATCHED,
    )

    summary = match_gstr2b_to_purchases(company, period, persist=True)
    itc = claimable_itc_from_2b(company, period)

    assert summary["rows"] == 2 and summary["matched"] == 1, summary

    assert_snapshot(
        "gstr2b_reconciliation",
        {
            "summary": {k: summary[k] for k in ("rows", "matched", "persisted")},
            "itc_shape": _shape(itc),
            "itc_figures": {
                "cgst": str(itc["cgst"]), "sgst": str(itc["sgst"]),
                "igst": str(itc["igst"]), "taxable": str(itc["taxable"]),
                "claimable": itc["claimable"], "claimable_rows": itc["claimable_rows"],
                "source": itc["source"],
            },
        },
    )


_VOLATILE = re.compile(
    r"(\d{1,2}[-/ ][A-Za-z]{3,9}[-/ ]\d{2,4})"      # 10 Sep 2026 / 10-Sep-26
    r"|(\d{4}-\d{2}-\d{2})"                          # 2026-09-10
    r"|(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})"             # 10/09/2026 / 10-09-26
    r"|([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})"         # September 10, 2026
    r"|(Generated.*)"                                # "Generated on ..." footer
    r"|(Page \d+ of \d+)"
)


def _pdf_lines(pdf_bytes: bytes, *, redact: dict[str, str] | None = None) -> list[str]:
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    out = []
    for raw in text.splitlines():
        line = _VOLATILE.sub("", raw)
        for needle, token in (redact or {}).items():
            if needle:
                line = line.replace(needle, token)
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            out.append(line)
    return out


def test_gst_tax_invoice_pdf_text_snapshot(tenant_a, assert_snapshot):
    company = tenant_a.company
    company.gstin = "29AAAAA0000A1ZY"
    company.save(update_fields=["gstin"])

    product = make_product(company, name="Nirma Soap", sku="SOAP-1", gst_rate="18",
                           selling_price="100")
    add_stock(tenant_a, product, "20")
    customer = make_customer(company, name="Ravi Stores", state="Karnataka",
                             gstin="29AABBC1234D1Z5")
    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100.00", "gst_rate": "18"}],
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data

    from sales.models import SalesInvoice
    from sales.pdf.gst_tax_invoice import render_gst_tax_invoice

    invoice = SalesInvoice.objects.get(pk=inv["id"])
    raw_lines = _pdf_lines(render_gst_tax_invoice(invoice))

    joined = "\n".join(raw_lines)
    # sanity anchors before we pin the whole thing
    for must in ("TAX INVOICE", invoice.number, "Ravi Stores", "Nirma Soap",
                 "29AAAAA0000A1ZY", "236.00"):
        assert must in joined, f"missing {must!r} in PDF text:\n{joined}"

    # the number carries an FY code (INV-2627-...); redact it so the baseline
    # doesn't expire at the next financial year.
    lines = _pdf_lines(render_gst_tax_invoice(invoice), redact={invoice.number: "<INV-NO>"})
    assert_snapshot("gst_tax_invoice_pdf_text", {"lines": lines})


def test_gst_purchase_bill_pdf_text_snapshot(tenant_a, assert_snapshot):
    from tests.conftest import create_draft_purchase, make_supplier

    company = tenant_a.company
    company.gstin = "29AAAAA0000A1ZY"
    company.save(update_fields=["gstin"])

    product = make_product(company, name="Rin Bar", sku="RIN-1", gst_rate="18", purchase_price="80")
    add_stock(tenant_a, product, "5", unit_cost="80")
    supplier = make_supplier(company, name="Wholesale Depot", state="Karnataka",
                             gstin="29ZZZZZ7777Z1Z5")
    pur = create_draft_purchase(
        tenant_a, supplier,
        [{"product": product.id, "quantity": "10", "unit_price": "80.00", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(
        f"/api/v1/purchases/invoices/{pur['id']}/complete/"
    ).status_code == 200

    from purchases.models import PurchaseInvoice
    from purchases.pdf import render_gst_purchase_bill

    inv = PurchaseInvoice.objects.get(pk=pur["id"])
    joined = "\n".join(_pdf_lines(render_gst_purchase_bill(inv)))
    for must in ("Wholesale Depot", "Rin Bar", "29AAAAA0000A1ZY", "29ZZZZZ7777Z1Z5", "944.00"):
        assert must in joined, f"missing {must!r} in purchase-bill PDF:\n{joined}"

    lines = _pdf_lines(render_gst_purchase_bill(inv), redact={inv.number: "<BILL-NO>"})
    assert_snapshot("gst_purchase_bill_pdf_text", {"lines": lines})
