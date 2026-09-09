"""FG-2f — GSTR-3B aid structure + the outward-supply totals are pinned.

After a fixed intra-state sale and an intra-state purchase for one period,
snapshot the section key set and the 3.1(a) outward tax figures so a change to
3B assembly (or its tie to GSTR-1) shows as a diff.
"""

from __future__ import annotations

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


def _keys(node, depth=0):
    if isinstance(node, dict) and depth < 3:
        return {k: _keys(v, depth + 1) for k, v in sorted(node.items())}
    if isinstance(node, dict):
        return sorted(node.keys())
    return "<scalar>" if not isinstance(node, (list, dict)) else {"_count": len(node)}


def test_gstr3b_snapshot(tenant_a, assert_snapshot):
    company = tenant_a.company
    company.accounting_enabled = True
    company.gstin = "29AAAAA0000A1ZY"
    company.save(update_fields=["accounting_enabled", "gstin"])

    product = make_product(company, gst_rate="18", selling_price="100", purchase_price="60")
    add_stock(tenant_a, product, "20", unit_cost="60")
    cust = make_customer(company, state="Karnataka")
    sup = make_supplier(company, state="Karnataka")
    inv = create_draft_invoice(
        tenant_a, cust,
        [{"product": product.id, "quantity": "5", "unit_price": "100.00", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    pur = create_draft_purchase(
        tenant_a, sup,
        [{"product": product.id, "quantity": "10", "unit_price": "60.00", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200

    from reporting.gst_returns import build_gstr1, build_gstr3b

    g1 = build_gstr1(company, inv["invoice_date"][:7])
    g3b = build_gstr3b(company, inv["invoice_date"][:7], gstr1=g1)

    assert_snapshot(
        "gstr3b",
        {
            "section_keys": sorted(k for k in g3b.keys() if not k.startswith("_")),
            "shape": _keys(g3b),
        },
    )
