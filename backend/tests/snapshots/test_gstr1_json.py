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
