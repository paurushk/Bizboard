"""FG-2f — the GL posting set for each document type is pinned.

Shape: [{account_code, debit, credit}] sorted by (account_code, debit, credit),
amounts as strings, no ids/timestamps — so the snapshot shows exactly which
accounts a change moved and by how much.

Baselines are created with SNAPSHOT_UPDATE=1 (see conftest). Until then these
skip rather than fail.
"""

from __future__ import annotations

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


def _posting_set(company):
    from accounting.models import JournalEntry, JournalLine

    rows = []
    for line in (
        JournalLine.objects.filter(
            entry__company=company, entry__status=JournalEntry.Status.POSTED
        )
        .select_related("account")
        .order_by("account__code", "debit", "credit")
    ):
        rows.append(
            {
                "account_code": line.account.code,
                "debit": str(line.debit),
                "credit": str(line.credit),
            }
        )
    return rows


def _enable_books(company):
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])


def test_sale_intrastate_gl_posting_set(tenant_a, assert_snapshot):
    company = tenant_a.company
    _enable_books(company)
    product = make_product(company, gst_rate="18")
    add_stock(tenant_a, product, "10", unit_cost="60")
    customer = make_customer(company, gstin="29AAAAA0000A1ZY")
    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100.00", "gst_rate": "18"}],
    )
    r = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert r.status_code == 200, r.data
    assert_snapshot("gl_sale_intrastate", _posting_set(company))


def test_purchase_gl_posting_set(tenant_a, assert_snapshot):
    company = tenant_a.company
    _enable_books(company)
    product = make_product(company, gst_rate="18")
    supplier = make_supplier(company)
    pur = create_draft_purchase(
        tenant_a, supplier,
        [{"product": product.id, "quantity": "5", "unit_price": "80.00", "gst_rate": "18"}],
    )
    r = tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/")
    assert r.status_code == 200, r.data
    assert_snapshot("gl_purchase", _posting_set(company))
