"""GST behaviour-settings matrix (FG-2 settings matrix)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.invariants import assert_all_invariants
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("assume_local", [True, False])
def test_assume_local_state_for_blank_party(tenant_a, assume_local):
    company = tenant_a.company
    company.assume_local_state_for_blank_party = assume_local
    company.gstin = "29AAAAA0000A1ZY"
    company.save(update_fields=["assume_local_state_for_blank_party", "gstin"])

    product = make_product(company, gst_rate="18")
    add_stock(tenant_a, product, "10")
    # customer with NO state and NO gstin
    customer = make_customer(company, state="")
    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100.00", "gst_rate": "18"}],
    )
    r = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")

    if assume_local:
        assert r.status_code == 200, r.data
        assert Decimal(str(r.data["cgst_total"])) == Decimal("18.00")
        assert Decimal(str(r.data["sgst_total"])) == Decimal("18.00")
        assert Decimal(str(r.data["igst_total"])) == Decimal("0.00")
    else:
        # place of supply cannot be resolved -> completion blocked
        assert 400 <= r.status_code < 500, r.data
        body = str(r.data).lower()
        assert "place of supply" in body or "state" in body

    assert_all_invariants(company)
