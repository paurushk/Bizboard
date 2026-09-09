"""Phase 2 smoke: the invariant checks run against real posted state and pass.

This is the "does the invariant code even work" test — it exercises every
registered check against a company that has a completed sale and a completed
purchase, and asserts assert_all_invariants() does not raise. Real regressions
belong in tests/workflows/ and tests/regression/.
"""

from __future__ import annotations

import pytest

from core.invariants import assert_all_invariants, registered, run_invariants
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def test_registry_is_populated():
    names = registered()
    assert len(names) >= 15
    for domain in ("gl.", "gst.", "inventory.", "money.", "tenancy."):
        assert any(n.startswith(domain) for n in names), domain


def test_all_invariants_hold_for_a_fresh_company(tenant_a):
    # A company with no documents at all must still be fully consistent.
    failures = run_invariants(tenant_a.company)
    assert failures == {}, failures


def test_all_invariants_hold_after_a_completed_sale_and_purchase(tenant_a):
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "20")
    customer = make_customer(tenant_a.company, gstin="29AAAAA0000A1ZY")
    supplier = make_supplier(tenant_a.company)

    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "3", "unit_price": "100.00", "gst_rate": "18"}],
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data

    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "10", "unit_price": "80.00", "gst_rate": "18"}],
    )
    pdone = tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/")
    assert pdone.status_code == 200, pdone.data

    # The whole point: no invariant is violated by a normal sale + purchase.
    assert_all_invariants(tenant_a.company)


def test_isolation_between_two_tenants(tenant_a, tenant_b):
    for t in (tenant_a, tenant_b):
        p = make_product(t.company)
        add_stock(t, p, "5")
    assert run_invariants(tenant_a.company) == {}
    assert run_invariants(tenant_b.company) == {}
