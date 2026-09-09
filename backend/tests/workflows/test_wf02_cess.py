"""WF-02 — Sale carrying compensation cess: ad-valorem + per-unit (specific).

Full chain: line tax -> GSTR-1 cess column -> GL 2270 Output Cess -> e-invoice
CesAmt / CesNonAdvlAmt split -> trial balance = 0.  (SR-11 / D9b)
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from accounting.models import JournalEntry
from accounting.services import seed_chart_of_accounts
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def test_wf02_cess_advalorem_and_specific_full_chain(tenant_a, assert_consistent):
    company = tenant_a.company
    company.accounting_enabled = True
    company.gstin = "29ABCDE1234F1ZW"
    company.state = "Karnataka"
    company.pincode = "560001"
    company.address = "1 MG Road"
    company.city = "Bengaluru"
    company.save()
    seed_chart_of_accounts(company, tenant_a.owner)

    # HSN 7318 is not in the starter rate catalog, so the line's cess_rate /
    # cess_amount stand (no HSN-driven override).
    prod_av = make_product(company, sku="CESS-AV", hsn_code="7318", gst_rate="18", selling_price="100")
    prod_sp = make_product(company, sku="CESS-SP", hsn_code="7318", gst_rate="18", selling_price="100")
    add_stock(tenant_a, prod_av, "50", unit_cost="60")
    add_stock(tenant_a, prod_sp, "50", unit_cost="60")
    customer = make_customer(
        company, state="Karnataka", gstin="29AAAAA0000A1ZY",
        billing_address="45 Residency Road, Bengaluru 560001",
    )

    inv = create_draft_invoice(tenant_a, customer, [
        {"product": prod_av.id, "quantity": "10", "unit_price": "100", "gst_rate": "18",
         "cess_rate": "12", "cess_amount": "0"},
        {"product": prod_sp.id, "quantity": "10", "unit_price": "100", "gst_rate": "18",
         "cess_rate": "0", "cess_amount": "3"},
    ])
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data

    from sales.models import SalesInvoice

    invoice = SalesInvoice.objects.get(pk=inv["id"])
    line_av = invoice.items.get(product=prod_av)
    line_sp = invoice.items.get(product=prod_sp)

    # --- line tax: ad-valorem 12% of 1000 = 120 ; specific 10 x Rs 3 = 30 ---
    assert line_av.cess == Decimal("120.00"), line_av.cess
    assert line_sp.cess == Decimal("30.00"), line_sp.cess
    assert invoice.cess_total == Decimal("150.00")

    # --- GL: 2270 Output Cess credited by the full cess; entry balances ---
    entry = JournalEntry.objects.get(
        company=company, source_type="SALES_INVOICE", source_id=invoice.id, purpose="COMPLETE",
    )
    entry.assert_balanced()
    cess_line = entry.lines.filter(account__code="2270").first()
    assert cess_line is not None
    assert cess_line.credit == Decimal("150.00"), cess_line.credit

    # --- GSTR-1: b2b cess column foots to 150 ---
    from reporting.gst_returns import build_gstr1

    period = invoice.invoice_date.strftime("%Y-%m")
    g1 = build_gstr1(company, period)
    assert Decimal(str(g1["totals"]["b2b"]["cess"])) == Decimal("150.00"), g1["totals"]["b2b"]

    # --- e-invoice payload: the split lands in the right NIC fields ---
    from sales.einvoice_payload import build_einvoice_payload

    payload = build_einvoice_payload(invoice)
    adv = next(i for i in payload["ItemList"] if i["CesRt"] == "12.00")
    spc = next(i for i in payload["ItemList"] if i["CesNonAdvlAmt"] == "30.00")
    assert adv["CesAmt"] == "120.00" and adv["CesNonAdvlAmt"] == "0.00"
    assert spc["CesAmt"] == "0.00" and spc["CesRt"] == "0.00"
    assert payload["ValDtls"]["CesVal"] == "150.00"

    # --- trial balance = 0 + whole-chain invariants ---
    from accounting.reports import trial_balance

    tb = trial_balance(company)
    assert tb["balanced"] is True, tb
    assert_consistent(company)


def test_wf02_cess_defaults_from_product_master(tenant_a):
    """SR-12 / D9b: cess_rate + cess_amount set on the product master flow onto a
    new sales *and* purchase line with no line-level cess input."""
    company = tenant_a.company
    company.gstin = "29ABCDE1234F1ZW"
    company.state = "Karnataka"
    company.save()

    # HSN 7318 is not in the starter catalog, so the master rates are not overridden.
    product = make_product(
        company, sku="PM-CESS", hsn_code="7318", gst_rate="18",
        cess_rate="12", cess_amount="3",
    )
    product.refresh_from_db()
    assert product.cess_rate == Decimal("12.00")
    assert product.cess_amount == Decimal("3.00")
    add_stock(tenant_a, product, "100", unit_cost="60")
    customer = make_customer(company, state="Karnataka", gstin="29AAAAA0000A1ZY")

    # sales line — no cess_rate / cess_amount in the line dict
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "10", "unit_price": "100"},
    ])
    from sales.models import SalesInvoice

    s_inv = SalesInvoice.objects.get(pk=inv["id"])
    s_line = s_inv.items.first()
    assert s_line.cess_rate == Decimal("12.00"), s_line.cess_rate
    assert s_line.cess_amount == Decimal("3.00"), s_line.cess_amount
    # 12% of 1000 taxable + 10 units x Rs 3 = 120 + 30
    assert s_line.cess == Decimal("150.00"), s_line.cess

    # purchase line — no cess in the line dict either
    from tests.conftest import create_draft_purchase, make_supplier

    supplier = make_supplier(company, state="Karnataka")
    pur = create_draft_purchase(tenant_a, supplier, [
        {"product": product.id, "quantity": "20", "unit_price": "60"},
    ])
    from purchases.models import PurchaseInvoice

    p_inv = PurchaseInvoice.objects.get(pk=pur["id"])
    p_line = p_inv.items.first()
    assert p_line.cess_rate == Decimal("12.00"), p_line.cess_rate
    assert p_line.cess_amount == Decimal("3.00"), p_line.cess_amount
