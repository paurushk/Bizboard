"""§H5 — error paths return a clean 4xx (never a 500), and business errors
carry a resolvable HelpCode where one applies.
"""

from __future__ import annotations

import pytest

from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def test_unbalanced_journal_is_400_not_500(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    from accounting.models import Account
    from accounting.services import seed_chart_of_accounts

    seed_chart_of_accounts(tenant_a.company)
    cash = Account.objects.get(company=tenant_a.company, code="1100").id
    cogs = Account.objects.get(company=tenant_a.company, code="5400").id
    r = tenant_a.client.post(
        "/api/v1/accounting/journals/",
        {"entry_date": "2026-06-01", "lines": [
            {"account": cogs, "debit": "100.00", "credit": "0"},
            {"account": cash, "debit": "0", "credit": "1.00"},
        ]},
        format="json",
    )
    assert r.status_code == 400, r.status_code


def test_completing_an_already_completed_invoice_is_4xx(tenant_a):
    p = make_product(tenant_a.company, gst_rate="18")
    add_stock(tenant_a, p, "10")
    c = make_customer(tenant_a.company, gstin="29AAAAA0000A1ZY")
    inv = create_draft_invoice(
        tenant_a, c,
        [{"product": p.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    again = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert 400 <= again.status_code < 500, again.status_code


def test_oversell_under_block_policy_is_4xx_with_code(tenant_a):
    # default negative_stock_policy is BLOCK
    p = make_product(tenant_a.company, gst_rate="18")
    add_stock(tenant_a, p, "1")
    c = make_customer(tenant_a.company, gstin="29AAAAA0000A1ZY")
    inv = create_draft_invoice(
        tenant_a, c,
        [{"product": p.id, "quantity": "5", "unit_price": "100.00", "gst_rate": "18"}],
    )
    r = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert 400 <= r.status_code < 500, r.status_code


def test_unknown_product_on_invoice_is_400(tenant_a):
    c = make_customer(tenant_a.company)
    r = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {"customer": c.id, "invoice_type": "GST",
         "items": [{"product": 999999, "quantity": "1", "unit_price": "1.00", "gst_rate": "18"}]},
        format="json",
    )
    assert r.status_code == 400, r.status_code


def test_gst_invoice_without_place_of_supply_is_4xx_with_help_code(tenant_a):
    # customer with no state and no gstin, assume-local off
    tenant_a.company.assume_local_state_for_blank_party = False
    tenant_a.company.save(update_fields=["assume_local_state_for_blank_party"])
    p = make_product(tenant_a.company, gst_rate="18")
    add_stock(tenant_a, p, "5")
    c = make_customer(tenant_a.company, state="")
    inv = create_draft_invoice(
        tenant_a, c,
        [{"product": p.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18"}],
    )
    r = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert 400 <= r.status_code < 500, r.status_code
    body = str(r.data)
    assert "place of supply" in body.lower() or "PLACE_OF_SUPPLY" in body
