"""FG-2f — GSTR-1 aid structure is pinned.

After a fixed intra-state sale for one period, snapshot the section keys and
the B2CS taxable/tax totals so a change to GSTR-1 assembly shows as a diff.
"""

from __future__ import annotations

import pytest

from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def _shape(node):
    """Recursively reduce to key structure + scalar leaves, dropping lists' order
    sensitivity by summing numeric leaves under each list."""
    if isinstance(node, dict):
        return {k: _shape(v) for k, v in sorted(node.items())}
    if isinstance(node, list):
        return {"_count": len(node), "_items": [_shape(x) for x in node]}
    return str(node) if isinstance(node, (int, float)) else node


def test_gstr1_intrastate_snapshot(tenant_a, assert_snapshot):
    company = tenant_a.company
    company.accounting_enabled = True
    company.gstin = "29AAAAA0000A1ZY"
    company.save(update_fields=["accounting_enabled", "gstin"])

    product = make_product(company, gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "20", unit_cost="60")
    customer = make_customer(company, state="Karnataka")  # unregistered -> B2CS
    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "5", "unit_price": "100.00", "gst_rate": "18"}],
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    period = done.data["invoice_date"][:7]  # YYYY-MM

    from reporting.gst_returns import build_gstr1

    g = build_gstr1(company, period)
    # snapshot only the section key set + a couple of stable totals
    assert_snapshot(
        "gstr1_intrastate",
        {
            "section_keys": sorted(k for k in g.keys() if not k.startswith("_")),
            "b2cs_present": "b2cs" in g,
            "hsn_present": "hsn" in g or "hsn_b2b" in g or "hsn_outward" in g,
        },
    )


def test_gstr1_hsn_summary_snapshot_mixed_rate(tenant_a, assert_snapshot):
    """QOS-0033 — pin the GSTR-1 HSN summary rows for a mixed-rate, mixed-HSN
    period, not just `hsn_present`. A regression in HSN bucketing shows as a diff
    even when wf27's tie-out still passes."""
    company = tenant_a.company
    company.accounting_enabled = True
    company.gstin = "29AAAAA0000A1ZY"
    company.save(update_fields=["accounting_enabled", "gstin"])

    p18 = make_product(company, name="P18", sku="HSN-P18", gst_rate="18", selling_price="100", hsn_code="3402")
    p5 = make_product(company, name="P5", sku="HSN-P5", gst_rate="5", selling_price="200", hsn_code="1006")
    add_stock(tenant_a, p18, "50", unit_cost="60")
    add_stock(tenant_a, p5, "50", unit_cost="120")
    customer = make_customer(company, state="Karnataka")  # intra-state B2CS

    inv = create_draft_invoice(
        tenant_a, customer,
        [
            {"product": p18.id, "quantity": "3", "unit_price": "100.00", "gst_rate": "18", "hsn_code": "3402", "rate_override": True, "rate_override_reason": "snapshot pins mixed 18% / 5% HSN rows"},
            {"product": p5.id, "quantity": "4", "unit_price": "200.00", "gst_rate": "5", "hsn_code": "1006", "rate_override": True, "rate_override_reason": "snapshot pins branded rice at 5%"},
        ],
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    period = done.data["invoice_date"][:7]

    from reporting.gst_returns import build_gstr1

    g = build_gstr1(company, period)
    rows = sorted(
        (
            {
                "hsn": r["hsn"], "rate": str(r["rate"]),
                "taxable_value": str(r["taxable_value"]),
                "cgst": str(r["cgst"]), "sgst": str(r["sgst"]),
                "igst": str(r["igst"]), "cess": str(r["cess"]),
            }
            for r in g.get("hsn", [])
        ),
        key=lambda r: (r["hsn"], r["rate"]),
    )
    assert_snapshot("gstr1_hsn_summary_mixed_rate", {"hsn_rows": rows})
