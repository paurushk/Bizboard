"""Open purchase defects: BUG-PUR-001/002/003/004/005/011/014/015 and BUG-UI-014."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from django.utils import timezone

from tests.conftest import (
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[2]


def _books(company):
    company.accounting_enabled = True
    company.gstin = company.gstin or "29AAAAA0000A1ZY"
    company.save(update_fields=["accounting_enabled", "gstin"])
    from accounting.services import seed_chart_of_accounts

    seed_chart_of_accounts(company)


def _ids(resp):
    data = resp.data
    rows = data["results"] if isinstance(data, dict) and "results" in data else data
    return {row["id"] for row in rows}


def test_bug_pur_001(tenant_a):
    """Offsetting line rates that keep the bill total flat still fail a 3-way match."""
    from purchases.models import PurchaseOrder, PurchaseOrderItem

    company = tenant_a.company
    supplier = make_supplier(company, gstin="29ZZZZZ5555Z1Z5")
    widget = make_product(company, name="Widget", sku="PUR001-A", gst_rate="0", purchase_price="100")
    gasket = make_product(company, name="Gasket", sku="PUR001-B", gst_rate="0", purchase_price="50")
    pur = create_draft_purchase(tenant_a, supplier, [
        {"product": widget.id, "quantity": "10", "unit_price": "120", "gst_rate": "0"},
        {"product": gasket.id, "quantity": "10", "unit_price": "30", "gst_rate": "0"},
    ])
    order = PurchaseOrder.objects.create(
        company=company, supplier=supplier, created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    PurchaseOrderItem.objects.create(
        company=company, purchase_order=order, product=widget,
        quantity=Decimal("10"), unit_price=Decimal("100.00"), gst_rate=Decimal("0"),
    )
    PurchaseOrderItem.objects.create(
        company=company, purchase_order=order, product=gasket,
        quantity=Decimal("10"), unit_price=Decimal("50.00"), gst_rate=Decimal("0"),
    )
    order.converted_purchase_id = pur["id"]
    order.save(update_fields=["converted_purchase"])

    blocked = tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/")
    assert blocked.status_code == 400, blocked.data
    assert blocked.data["success"] is False
    text = str(blocked.data).lower()
    assert "3-way" in text
    assert "widget" in text and "gasket" in text

    from accounts.models import CompanyUser

    membership = CompanyUser.objects.get(company=company, user=tenant_a.staff)
    membership.can_create_purchases = True
    membership.save(update_fields=["can_create_purchases"])
    staff = tenant_a.staff_client.post(
        f"/api/v1/purchases/invoices/{pur['id']}/complete/",
        {"confirm_three_way_override": True},
        format="json",
    )
    assert staff.status_code == 400, staff.data
    assert "3-way" in str(staff.data).lower()

    done = tenant_a.client.post(
        f"/api/v1/purchases/invoices/{pur['id']}/complete/",
        {"confirm_three_way_override": True},
        format="json",
    )
    assert done.status_code == 200, done.data
    assert done.data["status"] == "COMPLETED"


def test_bug_pur_002(tenant_a):
    """Rejected GRN quantity drafts a supplier debit note and does not post it."""
    from accounting.models import JournalEntry
    from inventory.services import InventoryService
    from purchases.models import PurchaseDebitNote

    company = tenant_a.company
    supplier = make_supplier(company, state="Karnataka", gstin="29ZZZZZ5555Z1Z5")
    product = make_product(company, sku="PUR002", gst_rate="18", purchase_price="100")
    warehouse = InventoryService.default_warehouse(company)
    grn = tenant_a.client.post("/api/v1/purchases/grns/", {
        "supplier": supplier.id,
        "warehouse": warehouse.id,
        "receipt_date": timezone.localdate().isoformat(),
        "items": [{
            "product": product.id,
            "quantity_received": "10",
            "quantity_accepted": "8",
            "quantity_rejected": "2",
            "unit_price": "100.00",
            "rejection_reason": "Damaged carton",
        }],
    }, format="json")
    assert grn.status_code == 201, grn.data
    done = tenant_a.client.post(f"/api/v1/purchases/grns/{grn.data['id']}/complete/")
    assert done.status_code == 200, done.data

    note = PurchaseDebitNote.objects.get(goods_receipt_id=grn.data["id"])
    assert note.status == PurchaseDebitNote.Status.DRAFT
    assert note.supplier_id == supplier.id
    assert "Damaged carton" in (note.reason_detail or "")
    line = note.items.get()
    assert line.quantity == Decimal("2.000")
    assert line.unit_price == Decimal("100.00")
    assert not JournalEntry.objects.filter(company=company, source_id=note.id).exists()

    again = PurchaseDebitNote.objects.filter(goods_receipt_id=grn.data["id"])
    assert again.count() == 1

    conv = tenant_a.client.post(f"/api/v1/purchases/grns/{grn.data['id']}/convert/")
    assert conv.status_code in (200, 201), conv.data
    note.refresh_from_db()
    assert note.purchase_invoice_id == conv.data["id"]
    assert note.status == PurchaseDebitNote.Status.DRAFT


def test_bug_pur_003(tenant_a):
    """A completed-bill price change keeps the previous lines in a revision row."""
    from purchases.models import PurchaseInvoiceRevision

    product = make_product(tenant_a.company, sku="PUR003", gst_rate="0")
    supplier = make_supplier(tenant_a.company, gstin="29ZZZZZ5555Z1Z5")
    pur = create_draft_purchase(tenant_a, supplier, [
        {"product": product.id, "quantity": "5", "unit_price": "100", "gst_rate": "0"},
    ])
    done = tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/")
    assert done.status_code == 200, done.data
    before_total = Decimal(str(done.data["grand_total"]))

    amended = tenant_a.client.patch(f"/api/v1/purchases/invoices/{pur['id']}/", {
        "confirm_amend": True,
        "items": [{"product": product.id, "quantity": "5", "unit_price": "90", "gst_rate": "0"}],
    }, format="json")
    assert amended.status_code == 200, amended.data
    assert Decimal(amended.data["items"][0]["unit_price"]) == Decimal("90.00")

    rev = PurchaseInvoiceRevision.objects.get(invoice_id=pur["id"])
    assert rev.revision == 1
    snap = rev.snapshot
    assert Decimal(snap["grand_total"]) == before_total
    assert Decimal(snap["items"][0]["unit_price"]) == Decimal("100.00")
    assert snap["items"][0]["quantity"].startswith("5")
    assert Decimal(amended.data["grand_total"]) != before_total


def test_bug_pur_004(tenant_a):
    """A non-IN supplier needs its own completed Bill of Entry even with a blank GSTIN."""
    from purchases.models import BillOfEntry

    product = make_product(tenant_a.company, sku="PUR004", gst_rate="0")
    foreign = make_supplier(
        tenant_a.company, name="US Mill", state="", gstin="", country="US",
    )
    items = [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}]

    gst_draft = create_draft_purchase(tenant_a, foreign, items, purchase_type="GST")
    gst_blocked = tenant_a.client.post(f"/api/v1/purchases/invoices/{gst_draft['id']}/complete/")
    assert gst_blocked.status_code == 400, gst_blocked.data
    assert "bill of entry" in str(gst_blocked.data).lower()

    nongst = create_draft_purchase(tenant_a, foreign, items, purchase_type="NON_GST")
    bare = tenant_a.client.post(f"/api/v1/purchases/invoices/{nongst['id']}/complete/")
    assert bare.status_code == 400, bare.data
    assert "bill of entry" in str(bare.data).lower()

    stale = BillOfEntry.objects.create(
        company=tenant_a.company, supplier=foreign, boe_number="BOE-PUR004-STALE",
        boe_date=timezone.localdate(), igst_amount=Decimal("18.00"),
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    assert tenant_a.client.post(f"/api/v1/purchases/bills-of-entry/{stale.id}/complete/").status_code == 200
    still = tenant_a.client.post(f"/api/v1/purchases/invoices/{nongst['id']}/complete/")
    assert still.status_code == 400, still.data

    this_boe = BillOfEntry.objects.create(
        company=tenant_a.company, supplier=foreign, boe_number="BOE-PUR004-THIS",
        boe_date=timezone.localdate(), igst_amount=Decimal("18.00"),
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    assert tenant_a.client.post(f"/api/v1/purchases/bills-of-entry/{this_boe.id}/complete/").status_code == 200
    linked = tenant_a.client.patch(
        f"/api/v1/purchases/invoices/{nongst['id']}/",
        {"bill_of_entry": this_boe.id},
        format="json",
    )
    assert linked.status_code == 200, linked.data
    done = tenant_a.client.post(f"/api/v1/purchases/invoices/{nongst['id']}/complete/")
    assert done.status_code == 200, done.data
    assert done.data["status"] == "COMPLETED"


def test_bug_pur_005(tenant_a):
    """WAVG price amend revalues remaining stock and journals the consumed delta."""
    from accounting.models import JournalEntry
    from inventory.models import InventoryRunningCost

    company = tenant_a.company
    assert (company.inventory_valuation_method or "WAVG") == "WAVG"
    _books(company)
    product = make_product(company, sku="PUR005", gst_rate="0", purchase_price="100", selling_price="150")
    supplier = make_supplier(company, gstin="29ZZZZZ5555Z1Z5")
    customer = make_customer(company)
    pur = create_draft_purchase(tenant_a, supplier, [
        {"product": product.id, "quantity": "10", "unit_price": "100", "gst_rate": "0"},
    ])
    bought = tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/")
    assert bought.status_code == 200, bought.data

    sale = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "4", "unit_price": "150", "gst_rate": "0"},
    ])
    sold = tenant_a.client.post(f"/api/v1/sales/invoices/{sale['id']}/complete/")
    assert sold.status_code == 200, sold.data

    amended = tenant_a.client.patch(f"/api/v1/purchases/invoices/{pur['id']}/", {
        "confirm_amend": True,
        "items": [{"product": product.id, "quantity": "10", "unit_price": "120", "gst_rate": "0"}],
    }, format="json")
    assert amended.status_code == 200, amended.data

    row = InventoryRunningCost.objects.get(company=company, product=product)
    assert Decimal(row.qty) == Decimal("6")
    assert Decimal(row.value).quantize(Decimal("0.01")) == Decimal("720.00")

    entry = JournalEntry.objects.get(
        company=company,
        source_type="PURCHASE_INVOICE",
        source_id=pur["id"],
        purpose__startswith="WAVG_PRICE_VARIANCE",
        status=JournalEntry.Status.POSTED,
    )
    entry.assert_balanced()
    lines = list(entry.lines.select_related("account"))
    by_code = {line.account.code: line for line in lines}
    assert by_code["5400"].debit == Decimal("80.00")
    assert by_code["1400"].credit == Decimal("80.00")


def test_bug_pur_011(tenant_a):
    """Help describes a live GRN screen, and the list/create API still works."""
    from inventory.services import InventoryService

    catalog = (ROOT / "web/src/contextHelp/catalog/purchases.ts").read_text(encoding="utf-8")
    faq = (ROOT / "web/src/pages/help/faqContent.tsx").read_text(encoding="utf-8")
    app = (ROOT / "web/src/App.tsx").read_text(encoding="utf-8")
    page = (ROOT / "web/src/pages/purchases/GoodsReceiptsPage.tsx").read_text(encoding="utf-8")
    routes = (ROOT / "web/src/contextHelp/routes.ts").read_text(encoding="utf-8")
    folded = (catalog + faq).lower()
    assert "there is no separate grn" not in folded
    assert "there is no separate goods-received" not in folded
    assert "where is goods received (grn)?" in faq.lower()
    assert "purchases/grns" in app
    assert "goods-receipts" in routes
    assert "batch" in catalog.lower() and "serial" in catalog.lower()
    assert "createGoodsReceipt" in page

    supplier = make_supplier(tenant_a.company, gstin="29ZZZZZ5555Z1Z5")
    product = make_product(tenant_a.company, sku="PUR011", gst_rate="0")
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    created = tenant_a.client.post("/api/v1/purchases/grns/", {
        "supplier": supplier.id,
        "warehouse": warehouse.id,
        "receipt_date": timezone.localdate().isoformat(),
        "supplier_challan_number": "CH-PUR011",
        "items": [{
            "product": product.id,
            "quantity_received": "1",
            "quantity_accepted": "1",
            "quantity_rejected": "0",
            "unit_price": "10.00",
        }],
    }, format="json")
    assert created.status_code == 201, created.data
    listed = tenant_a.client.get("/api/v1/purchases/grns/")
    assert listed.status_code == 200, listed.data
    assert created.data["id"] in _ids(listed)
    assert created.data["supplier_challan_number"] == "CH-PUR011"


def test_bug_pur_014():
    """A product-import column named rate is purchase rate, not selling price."""
    from imports.services import MASTER_COLUMN_ALIASES, _map_master_row

    assert "rate" not in MASTER_COLUMN_ALIASES["selling_price"]
    assert "rate" in MASTER_COLUMN_ALIASES["purchase_price"]

    mapped = _map_master_row({"name": "Bolt", "sku": "B1", "rate": "55"})
    assert mapped.get("purchase_price") == "55"
    assert not mapped.get("selling_price")

    both = _map_master_row({"name": "Bolt", "sku": "B1", "rate": "40", "sales price": "90"})
    assert both["purchase_price"] == "40"
    assert both["selling_price"] == "90"


def test_bug_pur_015(tenant_a):
    supplier = make_supplier(
        tenant_a.company, name="Acme Fasteners", phone="9988776655", gstin="29ZZZZZ5555Z1Z5",
    )
    other = make_supplier(tenant_a.company, name="Other Mills", phone="9000000001")
    product = make_product(tenant_a.company, sku="PUR015", gst_rate="0")
    hit = create_draft_purchase(tenant_a, supplier, [
        {"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "0"},
    ])
    miss = create_draft_purchase(tenant_a, other, [
        {"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "0"},
    ])

    by_name = tenant_a.client.get("/api/v1/purchases/invoices/", {"q": "Acme Fasteners"})
    assert by_name.status_code == 200, by_name.data
    assert _ids(by_name) == {hit["id"]}

    by_phone = tenant_a.client.get("/api/v1/purchases/invoices/", {"q": "9988776655"})
    assert by_phone.status_code == 200, by_phone.data
    assert miss["id"] not in _ids(by_phone)
    assert hit["id"] in _ids(by_phone)


def test_bug_ui_014(tenant_a):
    """TDS section is a statutory code, not a free-text label."""
    product = make_product(tenant_a.company, sku="UI014", gst_rate="0")
    supplier = make_supplier(tenant_a.company, gstin="29ZZZZZ5555Z1Z5")
    items = [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}]

    for junk in ("Sec 194-C", "194 C Contractor"):
        resp = tenant_a.client.post("/api/v1/purchases/invoices/", {
            "supplier": supplier.id,
            "purchase_type": "GST",
            "tds_section": junk,
            "tds_rate": "2",
            "items": items,
        }, format="json")
        assert resp.status_code == 400, resp.data
        assert resp.data["success"] is False
        assert "194C" in str(resp.data)

    ok = tenant_a.client.post("/api/v1/purchases/invoices/", {
        "supplier": supplier.id,
        "purchase_type": "GST",
        "tds_section": "194C",
        "tds_rate": "2",
        "items": items,
    }, format="json")
    assert ok.status_code == 201, ok.data
    assert ok.data["tds_section"] == "194C"

    page = (ROOT / "web/src/pages/purchases/NewPurchasePage.tsx").read_text(encoding="utf-8")
    rates = (ROOT / "web/src/pages/purchases/tdsSections.ts").read_text(encoding="utf-8")
    assert 'placeholder="194C"' not in page
    assert "TDS_SECTION_OPTIONS" in page
    assert "statutoryTdsRate" in page
    assert "return company ? 2 : 1" in rates
    assert "return company ? 2 : 10" in rates
    assert "return 0.1" in rates
