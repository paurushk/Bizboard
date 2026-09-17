"""WF-GRN — goods-receipt-note flow (closes the 0%-covered purchases/grn_service.py).

Create a GRN against a supplier -> complete it (accepted qty flows into stock) ->
convert it to a purchase bill (AP + ITC posted, GL balanced). Cancel path
reverses the received stock.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from tests.conftest import make_product, make_supplier

pytestmark = pytest.mark.django_db


def _this_period() -> str:
    d = timezone.localdate()
    return f"{d.year:04d}-{d.month:02d}"


def _books(company):
    company.accounting_enabled = True
    company.gstin = company.gstin or "29AAAAA0000A1ZY"
    company.save(update_fields=["accounting_enabled", "gstin"])
    from accounting.services import seed_chart_of_accounts

    seed_chart_of_accounts(company)


def _grn_payload(supplier, warehouse, product, received="10", accepted="8"):
    return {
        "supplier": supplier.id,
        "warehouse": warehouse.id,
        "receipt_date": "2026-06-10",
        "supplier_challan_number": "CH-501",
        "items": [{
            "product": product.id,
            "quantity_received": received,
            "quantity_accepted": accepted,
            "quantity_rejected": str(Decimal(received) - Decimal(accepted)),
            "unit_price": "100.00",
        }],
    }


def test_wf_grn_receive_complete_convert(tenant_a, assert_consistent):
    from accounting.models import JournalEntry
    from inventory.services import InventoryService
    from purchases.models import GoodsReceipt, PurchaseInvoice

    company = tenant_a.company
    _books(company)
    supplier = make_supplier(company, state="Karnataka", gstin="29ZZZZZ5555Z1Z5")
    product = make_product(company, gst_rate="18", purchase_price="100")
    warehouse = InventoryService.default_warehouse(company)

    grn = tenant_a.client.post(
        "/api/v1/purchases/grns/", _grn_payload(supplier, warehouse, product), format="json"
    )
    assert grn.status_code == 201, grn.data
    gid = grn.data["id"]
    assert grn.data["status"] == GoodsReceipt.Status.DRAFT

    # complete -> only the ACCEPTED quantity enters stock
    done = tenant_a.client.post(f"/api/v1/purchases/grns/{gid}/complete/")
    assert done.status_code == 200, done.data
    assert done.data["status"] == GoodsReceipt.Status.COMPLETED
    assert InventoryService.available_quantity(company=company, product=product) == Decimal("8.000")

    # convert -> a purchase bill with AP + ITC, GL balanced
    conv = tenant_a.client.post(f"/api/v1/purchases/grns/{gid}/convert/")
    assert conv.status_code in (200, 201), conv.data
    pinv_id = conv.data["id"]
    pinv = PurchaseInvoice.objects.get(pk=pinv_id)
    assert GoodsReceipt.objects.get(pk=gid).converted_purchase_id == pinv_id

    # completing the converted bill (if it is still a draft) posts the GL
    if pinv.status != PurchaseInvoice.Status.COMPLETED:
        c = tenant_a.client.post(f"/api/v1/purchases/invoices/{pinv_id}/complete/")
        assert c.status_code == 200, c.data

    for e in JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED):
        e.assert_balanced()
    assert_consistent(company)


def test_wf_grn_cancel_reverses_received_stock(tenant_a, assert_consistent):
    from inventory.services import InventoryService

    company = tenant_a.company
    _books(company)
    supplier = make_supplier(company, state="Karnataka", gstin="29ZZZZZ6666Z1Z5")
    product = make_product(company, gst_rate="18", purchase_price="100")
    warehouse = InventoryService.default_warehouse(company)

    grn = tenant_a.client.post(
        "/api/v1/purchases/grns/",
        _grn_payload(supplier, warehouse, product, received="6", accepted="6"),
        format="json",
    )
    assert grn.status_code == 201, grn.data
    gid = grn.data["id"]
    assert tenant_a.client.post(f"/api/v1/purchases/grns/{gid}/complete/").status_code == 200
    assert InventoryService.available_quantity(company=company, product=product) == Decimal("6.000")

    canc = tenant_a.client.post(f"/api/v1/purchases/grns/{gid}/cancel/", {"reason": "wrong delivery"}, format="json")
    assert canc.status_code == 200, canc.data
    assert canc.data["status"] in ("CANCELLED", "CANCELED", "VOID")
    assert InventoryService.available_quantity(company=company, product=product) == Decimal("0.000")

    assert_consistent(company)


def test_wf_grn_complete_blocked_in_soft_closed_period(tenant_a):
    """G-21: GoodsReceiptService.complete() posts valuation-carrying stock
    (unit_cost) same as PurchaseInvoice.complete, so it must gate on the
    period lock the same way — previously it had no gst_periods import at all."""
    from reporting.gst_periods import soft_close_period

    company = tenant_a.company
    _books(company)
    from inventory.services import InventoryService

    supplier = make_supplier(company, state="Karnataka", gstin="29ZZZZZ7777Z1Z5")
    product = make_product(company, gst_rate="18", purchase_price="100")
    warehouse = InventoryService.default_warehouse(company)

    soft_close_period(company, _this_period(), tenant_a.owner)

    payload = _grn_payload(supplier, warehouse, product, received="4", accepted="4")
    payload["receipt_date"] = timezone.localdate().isoformat()
    grn = tenant_a.client.post("/api/v1/purchases/grns/", payload, format="json")
    assert grn.status_code == 201, grn.data
    gid = grn.data["id"]

    complete = tenant_a.client.post(f"/api/v1/purchases/grns/{gid}/complete/")
    assert complete.status_code == 400, complete.data
    from inventory.models import StockMovement

    assert not StockMovement.objects.filter(
        company=company, reference_type="goods_receipt"
    ).exists()


def test_wf_grn_cancel_blocked_in_hard_closed_period(tenant_a):
    """G-21: cancel() reverses that same stock posting and must gate too.
    Cancel uses allow_soft_closed=True like every other unwind call site, so
    a soft-close alone must NOT block it — only a hard CLOSED does, exactly
    like PurchaseInvoice.cancel / StockTransferService.cancel."""
    from reporting.models import GstReturnPeriod

    company = tenant_a.company
    _books(company)
    from inventory.services import InventoryService

    supplier = make_supplier(company, state="Karnataka", gstin="29ZZZZZ8888Z1Z5")
    product = make_product(company, gst_rate="18", purchase_price="100")
    warehouse = InventoryService.default_warehouse(company)

    payload = _grn_payload(supplier, warehouse, product, received="4", accepted="4")
    payload["receipt_date"] = timezone.localdate().isoformat()
    grn = tenant_a.client.post("/api/v1/purchases/grns/", payload, format="json")
    assert grn.status_code == 201, grn.data
    gid = grn.data["id"]
    assert tenant_a.client.post(f"/api/v1/purchases/grns/{gid}/complete/").status_code == 200
    assert InventoryService.available_quantity(company=company, product=product) == Decimal("4.000")

    GstReturnPeriod.objects.update_or_create(
        company=company, period=_this_period(),
        defaults={"status": GstReturnPeriod.Status.CLOSED},
    )

    canc = tenant_a.client.post(
        f"/api/v1/purchases/grns/{gid}/cancel/", {"reason": "wrong delivery"}, format="json"
    )
    assert canc.status_code == 400, canc.data
    assert InventoryService.available_quantity(company=company, product=product) == Decimal("4.000")
