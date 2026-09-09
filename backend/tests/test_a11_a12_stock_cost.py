"""A11+A12 — purchase layer cost policy, WARN stock matrix, import void append-only."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from accounting.models import JournalEntry
from accounting.services import PostingService, seed_chart_of_accounts
from inventory.models import (
    BatchLot,
    InventoryCostLayer,
    InventoryRunningCost,
    MovementType,
    StockBalance,
    StockMovement,
    StockTransfer,
    StockTransferLine,
    Warehouse,
)
from inventory.services import InventoryService, InventoryValuationService, StockTransferService
from purchases.models import BillOfEntry
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def _enable_books(tenant):
    tenant.company.accounting_enabled = True
    tenant.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant.company, tenant.owner)


# --- CR-032 / CR-033 ---------------------------------------------------------


def test_cr032_additional_charges_not_in_stock_layers(tenant_a):
    """Freight stays on GL 5110; FIFO/WAVG layers use commercial line cost only."""
    _enable_books(tenant_a)
    tenant_a.company.inventory_valuation_method = "FIFO"
    tenant_a.company.save(update_fields=["inventory_valuation_method"])
    product = make_product(tenant_a.company, purchase_price="100", gst_rate="0")
    supplier = make_supplier(tenant_a.company)
    payload = {
        "supplier": supplier.id,
        "purchase_type": "NON_GST",
        "additional_charges": "50",
        "items": [{"product": product.id, "quantity": "10", "unit_price": "100", "gst_rate": "0"}],
    }
    resp = tenant_a.client.post("/api/v1/purchases/invoices/", payload, format="json")
    assert resp.status_code == 201, resp.data
    done = tenant_a.client.post(f"/api/v1/purchases/invoices/{resp.data['id']}/complete/")
    assert done.status_code == 200, done.data

    move = StockMovement.objects.get(
        company=tenant_a.company,
        product=product,
        movement_type=MovementType.PURCHASE,
        reference_type="purchase_invoice",
    )
    assert Decimal(str(move.unit_cost)) == Decimal("100")
    layer = InventoryCostLayer.objects.get(company=tenant_a.company, product=product)
    assert Decimal(str(layer.unit_cost)) == Decimal("100")

    entry = JournalEntry.objects.get(
        company=tenant_a.company,
        source_type="PURCHASE_INVOICE",
        source_id=resp.data["id"],
        purpose="COMPLETE",
    )
    lines = {
        ln.account.code: (ln.debit or Decimal("0")) - (ln.credit or Decimal("0"))
        for ln in entry.lines.all()
    }
    assert lines["1400"] == Decimal("1000.00")
    assert lines["5110"] == Decimal("50.00")


def test_cr033_boe_bcd_not_in_purchase_layers(tenant_a):
    """BoE BCD expenses to 5110; linked import purchase layers stay at invoice price."""
    _enable_books(tenant_a)
    tenant_a.company.inventory_valuation_method = "FIFO"
    tenant_a.company.save(update_fields=["inventory_valuation_method"])
    product = make_product(tenant_a.company, purchase_price="200", gst_rate="0")
    supplier = make_supplier(tenant_a.company)
    boe = BillOfEntry.objects.create(
        company=tenant_a.company,
        supplier=supplier,
        boe_number="BOE-A11",
        boe_date=date(2026, 6, 10),
        bcd_amount=Decimal("5000.00"),
        igst_amount=Decimal("0"),
        status=BillOfEntry.Status.COMPLETED,
    )
    PostingService.post_bill_of_entry(boe, tenant_a.owner)

    resp = tenant_a.client.post(
        "/api/v1/purchases/invoices/",
        {
            "supplier": supplier.id,
            "purchase_type": "NON_GST",
            "bill_of_entry": boe.id,
            "items": [{"product": product.id, "quantity": "5", "unit_price": "200", "gst_rate": "0"}],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    done = tenant_a.client.post(f"/api/v1/purchases/invoices/{resp.data['id']}/complete/")
    assert done.status_code == 200, done.data

    move = StockMovement.objects.get(
        company=tenant_a.company,
        product=product,
        movement_type=MovementType.PURCHASE,
    )
    assert Decimal(str(move.unit_cost)) == Decimal("200")
    layer = InventoryCostLayer.objects.get(company=tenant_a.company, product=product)
    assert Decimal(str(layer.unit_cost)) == Decimal("200")

    boe_entry = JournalEntry.objects.get(
        company=tenant_a.company, source_type="BILL_OF_ENTRY", source_id=boe.id, purpose="COMPLETE",
    )
    boe_lines = {
        ln.account.code: (ln.debit or Decimal("0")) - (ln.credit or Decimal("0"))
        for ln in boe_entry.lines.all()
    }
    assert boe_lines["5110"] == Decimal("5000.00")


# --- CR-043 ------------------------------------------------------------------


def test_cr043_purchase_dn_does_not_restamp_layers(tenant_a):
    from purchases.models import PurchaseDebitNote, PurchaseNoteReason
    from purchases.notes_services import PurchaseNotesService

    tenant_a.company.inventory_valuation_method = "FIFO"
    tenant_a.company.save(update_fields=["inventory_valuation_method"])
    product = make_product(tenant_a.company, purchase_price="100", gst_rate="0")
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "10", "unit_price": "100", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    before = list(
        InventoryCostLayer.objects.filter(company=tenant_a.company, product=product).values_list(
            "id", "unit_cost", "qty_remaining"
        )
    )
    assert before
    from purchases.models import PurchaseInvoice

    invoice = PurchaseInvoice.objects.get(pk=pur["id"])
    src = invoice.items.get()
    note = PurchaseDebitNote.objects.create(
        company=tenant_a.company,
        supplier=supplier,
        purchase_invoice=invoice,
        reason=PurchaseNoteReason.CORRECTION_OF_INVOICE,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    PurchaseNotesService.set_debit_note_items(
        note,
        [{"product": product, "quantity": "10", "unit_price": "20", "gst_rate": "0", "source_item": src}],
        tenant_a.owner,
    )
    PurchaseNotesService.complete_debit_note(note, tenant_a.owner, confirm_additional_debit=True)
    after = list(
        InventoryCostLayer.objects.filter(company=tenant_a.company, product=product).values_list(
            "id", "unit_cost", "qty_remaining"
        )
    )
    assert after == before
    assert not StockMovement.objects.filter(
        company=tenant_a.company, product=product, reference_type__icontains="debit"
    ).exists()


# --- CR-050 / CR-051 ---------------------------------------------------------


def test_cr050_warn_fefo_batch_allows_oversell(tenant_a):
    tenant_a.company.negative_stock_policy = "WARN"
    tenant_a.company.save(update_fields=["negative_stock_policy"])
    product = make_product(tenant_a.company, sku="FEFO-WARN", track_batch=True)
    wh = InventoryService.default_warehouse(tenant_a.company)
    lot = BatchLot.objects.create(
        company=tenant_a.company, product=product, batch_no="L1", expiry_date=date(2099, 1, 1),
    )
    InventoryService.post_movement(
        company=tenant_a.company,
        warehouse=wh,
        product=product,
        batch=lot,
        movement_type=MovementType.OPENING_STOCK,
        quantity="1",
        unit_cost="50",
        user=tenant_a.owner,
    )
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "5", "unit_price": "100"}],
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 200, resp.data
    assert resp.data.get("warnings")
    bal = StockBalance.objects.get(company=tenant_a.company, product=product, batch=lot)
    assert bal.on_hand == Decimal("-4")


def test_cr050_warn_transfer_and_adjust_surface_warnings(tenant_a):
    tenant_a.company.negative_stock_policy = "WARN"
    tenant_a.company.save(update_fields=["negative_stock_policy"])
    product = make_product(tenant_a.company, sku="TRF-WARN")
    source = InventoryService.default_warehouse(tenant_a.company)
    dest = Warehouse.objects.create(company=tenant_a.company, name="Branch", code="BR-W")
    add_stock(tenant_a, product, "2")

    transfer = StockTransfer.objects.create(
        company=tenant_a.company, from_warehouse=source, to_warehouse=dest,
    )
    StockTransferLine.objects.create(transfer=transfer, product=product, quantity="5")
    transfer, warnings = StockTransferService.complete(transfer, tenant_a.owner)
    assert warnings
    assert InventoryService.available_quantity(tenant_a.company, product, source) == Decimal("-3")

    adj = tenant_a.client.post(
        "/api/v1/inventory/adjustments/",
        {"product": product.id, "quantity": "-10", "reason": "shrinkage"},
        format="json",
    )
    assert adj.status_code == 201, adj.data
    assert adj.data.get("warnings")


def test_cr051_running_cost_tracks_negative_under_warn(tenant_a):
    tenant_a.company.negative_stock_policy = "WARN"
    tenant_a.company.save(update_fields=["negative_stock_policy"])
    product = make_product(tenant_a.company, sku="RC-WARN")
    add_stock(tenant_a, product, "1", unit_cost="100")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "5", "unit_price": "120"}],
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 200, resp.data
    bal = StockBalance.objects.get(company=tenant_a.company, product=product)
    assert bal.on_hand == Decimal("-4")
    rc = InventoryRunningCost.objects.get(company=tenant_a.company, product=product)
    assert rc.qty == Decimal("-4")
    assert rc.value == Decimal("-400")
    rows = InventoryValuationService.valuation(tenant_a.company, method="WAVG", product=product)
    assert rows
    assert rows[0]["qty"] == Decimal("-4")
    assert rows[0]["value"] == Decimal("-400")


# --- CR-053 ------------------------------------------------------------------


def test_cr053_import_void_compensating_movement_only(tenant_a):
    make_product(tenant_a.company, sku="SKU-VOID-A12")
    csv_content = b"sku,quantity,unit_cost\nSKU-VOID-A12,10,50\n"
    job = tenant_a.client.post(
        "/api/v1/imports/",
        {
            "kind": "opening_stock",
            "file": SimpleUploadedFile("open.csv", csv_content, content_type="text/csv"),
        },
        format="multipart",
    ).data
    assert tenant_a.client.post(f"/api/v1/imports/{job['id']}/commit/").status_code == 200

    opening = StockMovement.objects.get(
        company=tenant_a.company,
        reference_type="import",
        reference_id=str(job["id"]),
        movement_type=MovementType.OPENING_STOCK,
    )
    original_type = opening.reference_type

    void = tenant_a.client.post(f"/api/v1/imports/{job['id']}/void/")
    assert void.status_code == 200, void.data

    opening.refresh_from_db()
    assert opening.reference_type == original_type == "import"
    reverse = StockMovement.objects.get(
        company=tenant_a.company,
        reference_type="import_void",
        reference_id=str(job["id"]),
        movement_type=MovementType.ADJUSTMENT,
    )
    assert reverse.quantity == Decimal("-10")
    bal = StockBalance.objects.get(company=tenant_a.company, product__sku="SKU-VOID-A12")
    assert bal.on_hand == Decimal("0")


def test_cr059_verify_fifo_layers_documented():
    services = Path(__file__).resolve().parents[1] / "inventory" / "services.py"
    runbook = Path(__file__).resolve().parents[2] / "docs" / "pilot" / "RUNBOOKS.md"
    assert "CR-059" in services.read_text(encoding="utf-8")
    assert "FIFO layer verify" in runbook.read_text(encoding="utf-8")
