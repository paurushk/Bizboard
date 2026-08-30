"""BB-000670: TDS/TCS MVP — 194C 1% / 206C 0.1% fixtures + worksheets."""

from decimal import Decimal

import pytest
from django.test import override_settings

from accounting.models import JournalEntry, JournalLine
from accounting.services import seed_chart_of_accounts
from tests.conftest import create_draft_invoice, create_draft_purchase, make_customer, make_product, make_supplier


pytestmark = pytest.mark.django_db


@pytest.fixture
def books(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    return tenant_a


def _lines_by_code(company, source_type, source_id, purpose="COMPLETE"):
    je = JournalEntry.objects.get(
        company=company, source_type=source_type, source_id=source_id, purpose=purpose,
        status=JournalEntry.Status.POSTED,
    )
    return {line.account.code: (line.debit, line.credit) for line in je.lines.all()}


def test_purchase_194c_1_percent_credits_tds_payable_and_reduces_ap(books):
    supplier = make_supplier(books.company)
    product = make_product(books.company, purchase_price="1000", selling_price="1200", gst_rate="18")
    # Taxable 1000 + GST 180 = 1180; TDS 194C 1% of 1000 = 10; net AP 1170
    draft = create_draft_purchase(
        books,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
    )
    patch = books.client.patch(
        f"/api/v1/purchases/invoices/{draft['id']}/",
        {"tdsSection": "194C", "tdsRate": "1", "tdsAmount": "10.00"},
        format="json",
    )
    assert patch.status_code == 200, patch.data
    done = books.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/")
    assert done.status_code == 200, done.data
    codes = _lines_by_code(books.company, "PURCHASE_INVOICE", draft["id"])
    assert codes["2265"][1] == Decimal("10.00")
    assert codes["2100"][1] == Decimal("1170.00")
    inv = done.data.get("data", done.data)
    assert Decimal(str(inv.get("tdsAmount") or inv.get("tds_amount") or 0)) == Decimal("10.00")


def test_sales_206c_0_1_percent_adds_tcs_receivable(books):
    from inventory.models import MovementType
    from inventory.services import InventoryService

    customer = make_customer(books.company)
    product = make_product(books.company, purchase_price="80", selling_price="1000", gst_rate="0")
    InventoryService.post_movement(
        company=books.company, product=product, movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("10"), unit_cost=Decimal("80"), user=books.owner,
    )
    # Taxable/grand 1000; TCS 206C 0.1% = 1.00; Dr AR 1 / Cr 2266 1 on top of invoice
    draft = create_draft_invoice(
        books,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    patch = books.client.patch(
        f"/api/v1/sales/invoices/{draft['id']}/",
        {"tcsSection": "206C", "tcsRate": "0.1", "tcsAmount": "1.00"},
        format="json",
    )
    assert patch.status_code == 200, patch.data
    done = books.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert done.status_code == 200, done.data
    je = JournalEntry.objects.get(
        company=books.company, source_type="SALES_INVOICE", source_id=draft["id"], purpose="COMPLETE",
    )
    tcs_credit = sum((l.credit for l in je.lines.filter(account__code="2266")), Decimal("0"))
    ar_debit = sum((l.debit for l in je.lines.filter(account__code="1200")), Decimal("0"))
    from sales.models import SalesInvoice
    inv = SalesInvoice.objects.get(pk=draft["id"])
    assert tcs_credit == inv.tcs_amount == Decimal("1.00")
    assert inv.tcs_in_grand_total is True
    assert ar_debit == inv.grand_total


def test_tds_tcs_worksheets_csv_and_flag_gate(books):
    supplier = make_supplier(books.company)
    product = make_product(books.company, purchase_price="1000", selling_price="1000", gst_rate="0")
    draft = create_draft_purchase(
        books,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    books.client.patch(
        f"/api/v1/purchases/invoices/{draft['id']}/",
        {"tdsSection": "194C", "tdsRate": "1", "tdsAmount": "10.00", "invoiceDate": "2026-08-05"},
        format="json",
    )
    assert books.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/").status_code == 200

    customer = make_customer(books.company, name="TCS Buyer")
    from inventory.models import MovementType
    from inventory.services import InventoryService

    sp = make_product(books.company, name="TCS Item", sku="TCS-1", purchase_price="50", selling_price="1000", gst_rate="0")
    InventoryService.post_movement(
        company=books.company, product=sp, movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("5"), unit_cost=Decimal("50"), user=books.owner,
    )
    si = create_draft_invoice(
        books, customer, [{"product": sp.id, "quantity": "1", "unit_price": "1000", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    books.client.patch(
        f"/api/v1/sales/invoices/{si['id']}/",
        {"tcsSection": "206C", "tcsRate": "0.1", "tcsAmount": "1.00", "invoiceDate": "2026-08-05"},
        format="json",
    )
    assert books.client.post(f"/api/v1/sales/invoices/{si['id']}/complete/").status_code == 200

    tds = books.client.get("/api/v1/reports/tds-worksheet/", {"period": "2026-08"})
    assert tds.status_code == 200
    assert "text/csv" in tds["Content-Type"]
    assert b"26Q" in tds.content
    assert b"194C" in tds.content
    tcs = books.client.get("/api/v1/reports/tcs-worksheet/", {"period": "2026-08"})
    assert tcs.status_code == 200
    assert b"27EQ" in tcs.content
    assert b"206C" in tcs.content
    staff = books.staff_client.get("/api/v1/reports/tds-worksheet/", {"period": "2026-08"})
    assert staff.status_code in (403, 404)

    with override_settings(ENABLE_TDS=False):
        gated = books.client.get("/api/v1/reports/tds-worksheet/", {"period": "2026-08"})
        # Owner can still export after TDS/TCS has been posted (worksheet is a CA aid).
        assert gated.status_code == 200
        gated2 = books.client.get("/api/v1/reports/tcs-worksheet/", {"period": "2026-08"})
        assert gated2.status_code == 200


def test_tcs_complete_folds_grand_posts_gl_and_einvoice_othchrg(books):
    from inventory.models import MovementType
    from inventory.services import InventoryService
    from sales.einvoice_payload import build_einvoice_payload
    from sales.models import SalesInvoice

    books.company.address = "12 MG Road"
    books.company.city = "Bengaluru"
    books.company.pincode = "560001"
    books.company.state = "Karnataka"
    books.company.gstin = "29ABCDE1234F1ZW"
    books.company.save()
    customer = make_customer(
        books.company,
        gstin="29AAAAA0000A1Z5",
        state="Karnataka",
        billing_address="14 Church Street, Bengaluru 560001",
    )
    product = make_product(books.company, purchase_price="80", selling_price="1000", gst_rate="18", hsn_code="1001")
    InventoryService.post_movement(
        company=books.company, product=product, movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("10"), unit_cost=Decimal("80"), user=books.owner,
    )
    draft = create_draft_invoice(
        books,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
    )
    books.client.patch(
        f"/api/v1/sales/invoices/{draft['id']}/",
        {"tcsSection": "206C", "tcsRate": "0.1"},
        format="json",
    )
    done = books.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert done.status_code == 200, done.data
    inv = SalesInvoice.objects.get(pk=draft["id"])
    assert inv.tcs_in_grand_total is True
    assert inv.tcs_amount > 0
    assert inv.grand_total == inv.taxable_total + inv.cgst_total + inv.sgst_total + inv.igst_total + inv.tcs_amount
    je = JournalEntry.objects.get(
        company=books.company, source_type="SALES_INVOICE", source_id=inv.id, purpose="COMPLETE",
    )
    ar = sum((l.debit for l in je.lines.filter(account__code="1200")), Decimal("0"))
    tcs_cr = sum((l.credit for l in je.lines.filter(account__code="2266")), Decimal("0"))
    assert ar == inv.grand_total
    assert tcs_cr == inv.tcs_amount
    payload = build_einvoice_payload(inv)
    assert Decimal(str(payload["ValDtls"]["OthChrg"])) == inv.tcs_amount + Decimal(str(inv.additional_charges or 0))
    assert Decimal(str(payload["ValDtls"]["TotInvVal"])) == inv.grand_total

