"""RPT-14: the purchase register returns its own totals, with credit notes netted off."""

from decimal import Decimal

import pytest

from tests.conftest import create_draft_purchase, make_product, make_supplier

pytestmark = pytest.mark.django_db


def test_totals_net_credit_notes_and_cover_tax(tenant_a):
    product = make_product(tenant_a.company, purchase_price="100", selling_price="120", gst_rate="18")
    supplier = make_supplier(tenant_a.company, gstin="29AABCU9603R1ZJ")
    pur = create_draft_purchase(
        tenant_a, supplier,
        [{"product": product.id, "quantity": "10", "unit_price": "100", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    cn = tenant_a.client.post(
        "/api/v1/purchases/credit-notes/",
        {
            "supplier": supplier.id, "purchase_invoice": pur["id"], "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "18"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    assert tenant_a.client.post(f"/api/v1/purchases/credit-notes/{cn.data['id']}/complete/").status_code == 200

    resp = tenant_a.client.get("/api/v1/reports/purchase-register/")
    assert resp.status_code == 200
    body = resp.json()
    body = body.get("data", body)
    totals = body["totals"]
    rows = body["rows"]
    assert totals["count"] == len(rows) == 2
    # 1000 taxable less the 200 credit note; tax 180 less 36; grand 1180 less 236
    assert Decimal(str(totals["taxable"])) == Decimal("800.00")
    assert Decimal(str(totals["tax"])) == Decimal("144.00")
    assert Decimal(str(totals["grandTotal"])) == Decimal("944.00")
