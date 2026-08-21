"""Close remaining partial remediations: void/unallocate, FIFO restore, mfg FG cost, e-way."""

from decimal import Decimal

import pytest

from accounting.models import JournalEntry
from accounting.services import seed_chart_of_accounts
from inventory.models import InventoryCostLayer, MovementType, StockMovement
from inventory.services import InventoryService
from manufacturing.models import Bom, BomLine, WorkOrder, WorkOrderLine
from manufacturing.services import cancel_work_order, complete_work_order, release_work_order
from payments.models import ReceiptStatus
from payments.services import PaymentService
from purchases.models import PurchaseInvoice
from reporting.gst_returns import build_gstr9
from sales.eway_payload import EwayValidationError, build_eway_payload_from_invoice
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


def test_bb_000650_void_receipt_reverses_gl_and_keeps_row(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company)
    customer = make_customer(tenant_a.company)
    receipt = PaymentService.create_receipt(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("100"),
        mode="CASH",
        user=tenant_a.owner,
    )
    assert JournalEntry.objects.filter(
        source_type="CUSTOMER_RECEIPT", source_id=receipt.id, status=JournalEntry.Status.POSTED
    ).exists()
    resp = tenant_a.client.post(f"/api/v1/payments/receipts/{receipt.id}/void/", {"reason": "dup"}, format="json")
    assert resp.status_code == 200, resp.data
    receipt.refresh_from_db()
    assert receipt.status == ReceiptStatus.VOIDED
    assert JournalEntry.objects.filter(
        source_type="CUSTOMER_RECEIPT", source_id=receipt.id, status=JournalEntry.Status.POSTED
    ).count() == 0
    assert tenant_a.client.get(f"/api/v1/payments/receipts/{receipt.id}/").status_code == 200


def test_bb_000651_unallocate_reopens_invoice_and_reverses_je(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company)
    product = make_product(tenant_a.company, sku="UNAL-1")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    receipt = PaymentService.create_receipt(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("100"),
        mode="CASH",
        user=tenant_a.owner,
    )
    alloc = PaymentService.allocate_receipt(
        receipt=receipt,
        sales_invoice=SalesInvoice.objects.get(pk=inv["id"]),
        amount=Decimal("100"),
        user=tenant_a.owner,
    )
    assert JournalEntry.objects.filter(
        source_type="PAYMENT_ALLOCATION", source_id=alloc.id, status=JournalEntry.Status.POSTED
    ).exists()
    resp = tenant_a.client.post(f"/api/v1/payments/allocations/{alloc.id}/unallocate/", {}, format="json")
    assert resp.status_code == 200, resp.data
    alloc.refresh_from_db()
    assert alloc.reversed_at is not None
    inv_resp = tenant_a.client.get(f"/api/v1/sales/invoices/{inv['id']}/")
    assert inv_resp.status_code == 200
    assert Decimal(str(inv_resp.data["balance"])) == Decimal("100")


def test_bb_000655_allocation_je_uses_receipt_date(tenant_a):
    from datetime import date

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company)
    product = make_product(tenant_a.company, sku="JED-1")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "50", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    receipt = PaymentService.create_receipt(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("50"),
        mode="CASH",
        receipt_date=date(2026, 1, 15),
        user=tenant_a.owner,
    )
    alloc = PaymentService.allocate_receipt(
        receipt=receipt,
        sales_invoice=SalesInvoice.objects.get(pk=inv["id"]),
        amount=Decimal("50"),
        user=tenant_a.owner,
    )
    entry = JournalEntry.objects.get(
        source_type="PAYMENT_ALLOCATION", source_id=alloc.id, status=JournalEntry.Status.POSTED
    )
    assert entry.entry_date == date(2026, 1, 15)


def test_bb_000601_fifo_cancel_restores_original_layers(tenant_a):
    company = tenant_a.company
    company.inventory_valuation_method = "FIFO"
    company.save(update_fields=["inventory_valuation_method"])
    product = make_product(company, sku="FIFO-R")
    wh = InventoryService.default_warehouse(company)
    first = InventoryService.post_movement(
        company=company, product=product, warehouse=wh,
        movement_type=MovementType.PURCHASE, quantity="1", unit_cost="10", user=tenant_a.owner,
    )
    InventoryService.post_movement(
        company=company, product=product, warehouse=wh,
        movement_type=MovementType.PURCHASE, quantity="1", unit_cost="20", user=tenant_a.owner,
    )
    layer_ids = list(
        InventoryCostLayer.objects.filter(company=company, product=product).order_by("id").values_list("id", flat=True)
    )
    customer = make_customer(company)
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    sale = StockMovement.objects.filter(
        company=company, product=product, movement_type=MovementType.SALE
    ).first()
    assert sale.layer_peels
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/cancel/").status_code == 200
    restored = {
        layer.id: layer.qty_remaining
        for layer in InventoryCostLayer.objects.filter(company=company, product=product, id__in=layer_ids)
    }
    assert restored[layer_ids[0]] == Decimal("1")
    assert restored[layer_ids[1]] == Decimal("1")
    assert not InventoryCostLayer.objects.filter(
        company=company, product=product
    ).exclude(id__in=layer_ids).filter(qty_remaining__gt=0).exists()
    assert first.pk


def test_bb_000555_wo_fg_uses_issue_fifo_cost(tenant_a):
    company = tenant_a.company
    company.inventory_valuation_method = "FIFO"
    company.save(update_fields=["inventory_valuation_method"])
    fg = make_product(company, sku="FG-1", purchase_price="999")
    comp = make_product(company, sku="COMP-1", purchase_price="5")
    wh = InventoryService.default_warehouse(company)
    InventoryService.post_movement(
        company=company, product=comp, warehouse=wh,
        movement_type=MovementType.PURCHASE, quantity="2", unit_cost="40", user=tenant_a.owner,
    )
    bom = Bom.objects.create(company=company, product=fg, name="FG BOM", status=Bom.Status.ACTIVE)
    BomLine.objects.create(bom=bom, component=comp, qty=Decimal("1"))
    wo = WorkOrder.objects.create(company=company, bom=bom, qty=Decimal("1"), warehouse=wh)
    release_work_order(wo, tenant_a.owner)
    complete_work_order(wo, tenant_a.owner)
    receipt = StockMovement.objects.get(
        company=company, product=fg, movement_type=MovementType.MANUFACTURE_RECEIPT
    )
    assert receipt.unit_cost == Decimal("40")


def test_bb_000564_wo_cancel_restores_issue_layers(tenant_a):
    company = tenant_a.company
    company.inventory_valuation_method = "FIFO"
    company.save(update_fields=["inventory_valuation_method"])
    fg = make_product(company, sku="FG-C")
    comp = make_product(company, sku="COMP-C", purchase_price="5")
    wh = InventoryService.default_warehouse(company)
    InventoryService.post_movement(
        company=company, product=comp, warehouse=wh,
        movement_type=MovementType.PURCHASE, quantity="1", unit_cost="12", user=tenant_a.owner,
    )
    layer = InventoryCostLayer.objects.get(company=company, product=comp)
    bom = Bom.objects.create(company=company, product=fg, name="FG BOM", status=Bom.Status.ACTIVE)
    BomLine.objects.create(bom=bom, component=comp, qty=Decimal("1"))
    wo = WorkOrder.objects.create(company=company, bom=bom, qty=Decimal("1"), warehouse=wh)
    release_work_order(wo, tenant_a.owner)
    cancel_work_order(wo, tenant_a.owner)
    layer.refresh_from_db()
    assert layer.qty_remaining == Decimal("1")


def test_bb_000639_eway_requires_distance(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.pincode = "560001"
    tenant_a.company.address = "1 MG Road"
    tenant_a.company.city = "Bengaluru"
    tenant_a.company.save()
    customer = make_customer(
        tenant_a.company, gstin="29AABCU9603R1ZJ", state="Karnataka",
        billing_address="Blr 560002",
    )
    product = make_product(tenant_a.company, sku="EWD-1", hsn_code="1001")
    add_stock(tenant_a, product, "2")
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    with pytest.raises(EwayValidationError):
        build_eway_payload_from_invoice(invoice)
    invoice.transport_distance_km = 40
    invoice.sub_supply_type = "1"
    invoice.trans_mode = "1"
    payload = build_eway_payload_from_invoice(invoice)
    assert payload["transDistance"] == "40"
    assert payload["subSupplyType"] == "1"


def test_bb_000649_credit_note_snapshots_invoice_charges(tenant_a):
    product = make_product(tenant_a.company, sku="CN-S")
    add_stock(tenant_a, product, "2")
    customer = make_customer(tenant_a.company, gstin="29AABCU9603R1ZJ", state="Karnataka")
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    invoice.additional_charges = Decimal("25")
    invoice.filing_place_of_supply = "Karnataka"
    invoice.save(update_fields=["additional_charges", "filing_place_of_supply"])
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    cn = tenant_a.client.post(
        "/api/v1/sales/credit-notes/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "0"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    assert Decimal(str(cn.data.get("additional_charges") or 0)) == Decimal("0")
    assert cn.data["filing_place_of_supply"] == "Karnataka"


def test_bb_000650_gateway_receipt_cannot_void(tenant_a):
    from payments.models import PaymentSource

    customer = make_customer(tenant_a.company)
    receipt = PaymentService.create_receipt(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("40"),
        mode="UPI",
        source=PaymentSource.GATEWAY,
        user=tenant_a.owner,
        warn_utr_duplicate=False,
    )
    resp = tenant_a.client.post(f"/api/v1/payments/receipts/{receipt.id}/void/", {}, format="json")
    assert resp.status_code == 400


def test_bb_000650_void_releases_utr(tenant_a):
    customer = make_customer(tenant_a.company)
    first = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": "10", "mode": "UPI", "utr": "UTRVOID1"},
        format="json",
    )
    assert first.status_code == 201, first.data
    voided = tenant_a.client.post(f"/api/v1/payments/receipts/{first.data['id']}/void/", {}, format="json")
    assert voided.status_code == 200, voided.data
    second = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": "12", "mode": "UPI", "utr": "UTRVOID1"},
        format="json",
    )
    assert second.status_code == 201, second.data


def test_wo_release_snapshots_bom_and_posts_wip(tenant_a):
    company = tenant_a.company
    company.accounting_enabled = True
    company.inventory_valuation_method = "FIFO"
    company.save(update_fields=["accounting_enabled", "inventory_valuation_method"])
    seed_chart_of_accounts(company)
    fg = make_product(company, sku="FG-SNAP")
    comp = make_product(company, sku="COMP-SNAP", purchase_price="9")
    wh = InventoryService.default_warehouse(company)
    InventoryService.post_movement(
        company=company, product=comp, warehouse=wh,
        movement_type=MovementType.PURCHASE, quantity="3", unit_cost="20", user=tenant_a.owner,
    )
    bom = Bom.objects.create(company=company, product=fg, name="SNAP BOM", status=Bom.Status.ACTIVE)
    BomLine.objects.create(bom=bom, component=comp, qty=Decimal("2"))
    wo = WorkOrder.objects.create(company=company, bom=bom, qty=Decimal("1"), warehouse=wh)
    release_work_order(wo, tenant_a.owner)
    snap = WorkOrderLine.objects.get(work_order=wo)
    assert snap.qty == Decimal("2")
    BomLine.objects.filter(bom=bom).update(qty=Decimal("9"))
    complete_work_order(wo, tenant_a.owner)
    issue = StockMovement.objects.get(
        company=company, product=comp, movement_type=MovementType.MANUFACTURE_ISSUE,
    )
    assert abs(issue.quantity) == Decimal("2")
    assert JournalEntry.objects.filter(
        source_type="WORK_ORDER", source_id=wo.id, purpose="RELEASE", status=JournalEntry.Status.POSTED,
    ).exists()
    assert JournalEntry.objects.filter(
        source_type="WORK_ORDER", source_id=wo.id, purpose="COMPLETE", status=JournalEntry.Status.POSTED,
    ).exists()
    cancel_work_order(wo, tenant_a.owner)
    assert not JournalEntry.objects.filter(
        source_type="WORK_ORDER", source_id=wo.id, status=JournalEntry.Status.POSTED,
    ).exists()


def test_gstr9_table_6_from_claimable_purchase(tenant_a):
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save(update_fields=["gstin", "state"])
    supplier = make_supplier(tenant_a.company, gstin="29AABCU9603R1ZJ")
    product = make_product(tenant_a.company, sku="ITC-9")
    inv = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "18"}],
    )
    PurchaseInvoice.objects.filter(pk=inv["id"]).update(
        itc_eligibility=PurchaseInvoice.ItcEligibility.CLAIMABLE,
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{inv['id']}/complete/").status_code == 200
    pi = PurchaseInvoice.objects.get(pk=inv["id"])
    fy_start = tenant_a.company.fy_start_month or 4
    start_y = pi.invoice_date.year if pi.invoice_date.month >= fy_start else pi.invoice_date.year - 1
    fy = f"{start_y}-{str((start_y + 1) % 100).zfill(2)}"
    payload = build_gstr9(tenant_a.company, fy)
    assert payload["tables"]["6"]["status"] == "WORKSHEET"
    assert Decimal(payload["tables"]["6"]["tax"]) == Decimal("18.00")
    assert Decimal(payload["tables"]["6"]["taxable_value"]) == Decimal("100.00")


def test_h9_price_amend_keeps_sale_peel_cogs(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    product = make_product(tenant_a.company, sku="H9-COGS")
    add_stock(tenant_a, product, "10", unit_cost="40")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    before = JournalEntry.objects.get(
        company=tenant_a.company, source_type="SALES_INVOICE", source_id=inv["id"],
        purpose="COGS", status=JournalEntry.Status.POSTED,
    )
    cogs_before = before.lines.get(account__code="5400").debit
    sale_cost = sum(
        (Decimal(str(m.unit_cost or 0)) * abs(Decimal(str(m.quantity)))
         for m in StockMovement.objects.filter(
             company=tenant_a.company, movement_type=MovementType.SALE,
             reference_type="sales_invoice", reference_id=str(inv["id"]),
         )),
        Decimal("0"),
    )
    assert cogs_before == sale_cost == Decimal("80.00")
    resp = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv['id']}/",
        {
            "confirm_amend": True,
            "items": [{"product": product.id, "quantity": "2", "unit_price": "90", "gst_rate": "0"}],
        },
        format="json",
    )
    assert resp.status_code == 200, resp.data
    after = JournalEntry.objects.get(
        company=tenant_a.company, source_type="SALES_INVOICE", source_id=inv["id"],
        purpose="COGS", status=JournalEntry.Status.POSTED,
    )
    assert after.lines.get(account__code="5400").debit == Decimal("80.00")
    assert after.id != before.id
