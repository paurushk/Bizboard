"""A4+A5 reporting fixes: CR-063/065/069 + CR-060/062."""

from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from inventory.models import StockBalance
from purchases.models import PurchaseInvoice
from reporting.gst_returns import build_gstr3b
from reporting.models import Gstr2bIngest
from reporting.services import ReportService
from sales.models import SalesInvoice
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def test_cr063_registers_exclude_cancelled_by_default(tenant_a):
    product = make_product(tenant_a.company, sku="A4-CAN")
    add_stock(tenant_a, product, "50")
    customer = make_customer(tenant_a.company)
    supplier = make_supplier(tenant_a.company)

    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}]
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    SalesInvoice.objects.filter(pk=inv["id"]).update(status=SalesInvoice.Status.CANCELLED)

    pur = create_draft_purchase(
        tenant_a, supplier, [{"product": product.id, "quantity": "1", "unit_price": "50"}]
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    PurchaseInvoice.objects.filter(pk=pur["id"]).update(status=PurchaseInvoice.Status.CANCELLED)

    sales = ReportService.sales_register(tenant_a.company)
    assert all(r.get("status") != SalesInvoice.Status.CANCELLED for r in sales["rows"])
    purchases = ReportService.purchase_register(tenant_a.company)
    assert all(r.get("status") != PurchaseInvoice.Status.CANCELLED for r in purchases["rows"])

    # Optional status filter still surfaces cancelled when asked.
    sales_c = ReportService.sales_register(tenant_a.company, status=SalesInvoice.Status.CANCELLED)
    assert any(r["id"] == inv["id"] for r in sales_c["rows"])
    purch_c = ReportService.purchase_register(
        tenant_a.company, status=PurchaseInvoice.Status.CANCELLED
    )
    assert any(r["id"] == pur["id"] for r in purch_c["rows"])


def test_cr065_dashboard_excludes_opening_balance_flag(tenant_a):
    """Opening invoices flagged is_opening_balance must not inflate sales/purchases KPIs
    even when notes are empty (not TALLY_OPENING)."""
    product = make_product(tenant_a.company, sku="A4-OB")
    add_stock(tenant_a, product, "20")
    customer = make_customer(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    today = timezone.localdate()

    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "200"}]
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    SalesInvoice.objects.filter(pk=inv["id"]).update(
        invoice_date=today, is_opening_balance=True, notes=""
    )

    pur = create_draft_purchase(
        tenant_a, supplier, [{"product": product.id, "quantity": "1", "unit_price": "100"}]
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    PurchaseInvoice.objects.filter(pk=pur["id"]).update(
        invoice_date=today, is_opening_balance=True, notes=""
    )

    dash = ReportService.dashboard(tenant_a.company)
    assert Decimal(str(dash["sales_today"]["total"])) == Decimal("0")
    assert dash["sales_today"]["count"] == 0
    assert Decimal(str(dash["purchases_this_month"]["total"])) == Decimal("0")
    assert dash["purchases_this_month"]["count"] == 0


def test_cr069_net_payable_uses_recommended_claimable(tenant_a):
    """When 2B ITC exceeds books ITC, hint must subtract min(books, 2B), not full 2B."""
    company = tenant_a.company
    company.gstin = "29ABCDE1234F1ZW"
    company.state = "Karnataka"
    company.save(update_fields=["gstin", "state"])

    product = make_product(company, sku="A4-ITC", hsn_code="3004")
    add_stock(tenant_a, product, "5")
    customer = make_customer(company, gstin="29AABCU9603R1ZJ", state="Karnataka")
    supplier = make_supplier(company, gstin="29AAAAA0000A1ZY", state="Karnataka")

    # Outward tax in period.
    sale = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
    )
    SalesInvoice.objects.filter(pk=sale["id"]).update(invoice_date=date(2026, 7, 10))
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{sale['id']}/complete/").status_code == 200

    # Books ITC: 18 on 100 taxable.
    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    inv = PurchaseInvoice.objects.get(pk=pur["id"])
    inv.invoice_date = date(2026, 7, 5)
    inv.itc_eligibility = PurchaseInvoice.ItcEligibility.CLAIMABLE
    inv.save(update_fields=["invoice_date", "itc_eligibility"])
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    inv.refresh_from_db()

    # Matched 2B with inflated tax vs books (cgst/sgst 90 each vs books 9 each).
    Gstr2bIngest.objects.create(
        company=company,
        period="2026-07",
        supplier_gstin=supplier.gstin,
        invoice_number=inv.number or "PI-A4",
        invoice_date=date(2026, 7, 5),
        taxable_value=inv.taxable_total,
        cgst=Decimal("90"),
        sgst=Decimal("90"),
        match_status=Gstr2bIngest.MatchStatus.MATCHED,
        itc_eligibility=Gstr2bIngest.ItcEligibility.CLAIMABLE,
        ims_action=Gstr2bIngest.ImsAction.ACCEPT,
        purchase_invoice=inv,
    )

    payload = build_gstr3b(company, "2026-07")
    rec = payload["itc"]["recommended_claimable"]
    books_cgst = Decimal(str(payload["itc"]["books_itc"]["cgst"]))
    books_sgst = Decimal(str(payload["itc"]["books_itc"]["sgst"]))
    assert Decimal(str(rec["cgst"])) == min(books_cgst, Decimal("90"))
    assert Decimal(str(rec["sgst"])) == min(books_sgst, Decimal("90"))
    assert Decimal(str(rec["cgst"])) < Decimal("90")

    outward = Decimal(payload["tax_payable_summary"]["outward_tax"])
    rcm = (
        Decimal(payload["inward_supplies"]["reverse_charge"]["cgst"])
        + Decimal(payload["inward_supplies"]["reverse_charge"]["sgst"])
        + Decimal(payload["inward_supplies"]["reverse_charge"]["igst"])
        + Decimal(payload["inward_supplies"]["reverse_charge"]["cess"])
    )
    claimable = (
        Decimal(str(rec["igst"]))
        + Decimal(str(rec["cgst"]))
        + Decimal(str(rec["sgst"]))
        + Decimal(str(rec.get("cess") or 0))
    )
    hint = Decimal(payload["tax_payable_summary"]["net_payable_hint"])
    assert hint == outward + rcm - claimable
    full_2b = Decimal("180")
    assert hint != outward + rcm - full_2b


def test_cr060_dashboard_receivables_equals_aging_sum(tenant_a):
    product = make_product(tenant_a.company, sku="A5-AR")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200

    dash = ReportService.dashboard(tenant_a.company)
    aging = dash["receivables_aging"]
    aging_sum = sum((Decimal(str(aging[k])) for k in aging), Decimal("0"))
    assert Decimal(str(dash["receivables"])) == aging_sum
    assert ReportService._company_receivables(tenant_a.company) == aging_sum


@pytest.mark.no_invariant_check  # deliberately builds inconsistent state to test detection/rejection
def test_cr062_inventory_summary_uses_movements_and_flags_drift(tenant_a):
    product = make_product(tenant_a.company, sku="A5-STK", purchase_price="50")
    add_stock(tenant_a, product, "4", unit_cost="80")

    summary = ReportService.inventory_summary(tenant_a.company)
    row = next(r for r in summary["rows"] if r["product_id"] == product.id)
    assert Decimal(str(row["on_hand"])) == Decimal("4")
    assert "balance_drift" not in row

    # Corrupt cache — report must still show movement sum and flag drift.
    bal = StockBalance.objects.get(company=tenant_a.company, product=product)
    bal.on_hand = Decimal("99")
    bal.save(update_fields=["on_hand"])

    summary2 = ReportService.inventory_summary(tenant_a.company)
    row2 = next(r for r in summary2["rows"] if r["product_id"] == product.id)
    assert Decimal(str(row2["on_hand"])) == Decimal("4")
    assert row2.get("balance_drift") is True
    assert Decimal(str(row2["balance_on_hand"])) == Decimal("99")
