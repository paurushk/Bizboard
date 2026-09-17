"""CFT-114…CFT-120 — review-gap cross-flow cases from CROSS_FLOW_TEST_CHECKLIST.md.

Each test's docstring cites the stable CFT-NNN id. These are topology-rich:
stock reservation, convert remainder, IRN lock, credit-hold release, lot restore,
and same-document amend conflict — not isolated invariant sweeps.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from inventory.models import BatchLot, SerialNumber, StockBalance
from inventory.services import InventoryService
from payments.dunning import customer_risk_snapshot
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db


def test_cft_114_cancel_so_after_challan_does_not_orphan_reservation(tenant_a):
    """CFT-114 — cancel SO while a challan exists is blocked; after cancelling
    the draft challan, SO cancel releases reservation. Completing the challan
    then converting to an invoice must not double-issue stock."""
    company = tenant_a.company
    company.stock_on_delivery_challan = True
    company.save(update_fields=["stock_on_delivery_challan"])
    product = make_product(company, sku="CFT114")
    add_stock(tenant_a, product, "20")
    customer = make_customer(company)
    warehouse = InventoryService.default_warehouse(company)

    so = tenant_a.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id,
            "order_date": "2026-03-15",
            "items": [{"product": product.id, "quantity": "5", "unit_price": "100", "gst_rate": "18"}],
        },
        format="json",
    )
    assert so.status_code == 201, so.data
    so_id = so.data["id"]
    conf = tenant_a.client.post(f"/api/v1/sales/orders/{so_id}/confirm/")
    assert conf.status_code == 200, conf.data
    bal = StockBalance.objects.get(company=company, product=product, warehouse=warehouse)
    assert bal.reserved == Decimal("5.000")
    assert bal.on_hand == Decimal("20.000")

    ch = tenant_a.client.post(f"/api/v1/sales/orders/{so_id}/convert-to-challan/")
    assert ch.status_code == 200, ch.data
    ch_id = ch.data["id"]

    blocked = tenant_a.client.post(f"/api/v1/sales/orders/{so_id}/cancel/")
    assert blocked.status_code == 400, blocked.data
    assert "challan" in str(blocked.data).lower()
    bal.refresh_from_db()
    assert bal.reserved == Decimal("5.000")

    cancel_ch = tenant_a.client.post(f"/api/v1/sales/delivery-challans/{ch_id}/cancel/")
    assert cancel_ch.status_code == 200, cancel_ch.data
    cancel_so = tenant_a.client.post(f"/api/v1/sales/orders/{so_id}/cancel/")
    assert cancel_so.status_code == 200, cancel_so.data
    bal.refresh_from_db()
    assert bal.reserved == Decimal("0.000")
    assert bal.on_hand == Decimal("20.000")

    # Fresh SO → challan → complete (issues stock) → invoice complete (no second issue).
    so2 = tenant_a.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id,
            "order_date": "2026-03-16",
            "items": [{"product": product.id, "quantity": "5", "unit_price": "100", "gst_rate": "18"}],
        },
        format="json",
    )
    so2_id = so2.data["id"]
    assert tenant_a.client.post(f"/api/v1/sales/orders/{so2_id}/confirm/").status_code == 200
    ch2 = tenant_a.client.post(f"/api/v1/sales/orders/{so2_id}/convert-to-challan/")
    assert ch2.status_code == 200, ch2.data
    done_ch = tenant_a.client.post(f"/api/v1/sales/delivery-challans/{ch2.data['id']}/complete/")
    assert done_ch.status_code == 200, done_ch.data
    bal.refresh_from_db()
    assert bal.reserved == Decimal("0.000")
    assert bal.on_hand == Decimal("15.000")

    inv = tenant_a.client.post(f"/api/v1/sales/delivery-challans/{ch2.data['id']}/convert/")
    assert inv.status_code == 200, inv.data
    done_inv = tenant_a.client.post(f"/api/v1/sales/invoices/{inv.data['id']}/complete/")
    assert done_inv.status_code == 200, done_inv.data
    bal.refresh_from_db()
    assert bal.on_hand == Decimal("15.000"), "invoice complete must not re-issue challan stock"


def test_cft_115_partial_quotation_convert_remainder_still_convertible(tenant_a):
    """CFT-115 — converting part of a quotation leaves the remainder convertible;
    a second convert must not recreate already-converted qty."""
    company = tenant_a.company
    product = make_product(company, sku="CFT115")
    add_stock(tenant_a, product, "20")
    customer = make_customer(company)
    quote = tenant_a.client.post(
        "/api/v1/sales/quotations/",
        {
            "customer": customer.id,
            "items": [{"product": product.id, "quantity": "10", "unit_price": "100", "gst_rate": "18"}],
        },
        format="json",
    )
    assert quote.status_code == 201, quote.data
    qid = quote.data["id"]
    line_id = quote.data["items"][0]["id"]

    first = tenant_a.client.post(
        f"/api/v1/sales/quotations/{qid}/convert-to-order/",
        {"items": [{"id": line_id, "quantity": "4"}]},
        format="json",
    )
    assert first.status_code == 200, first.data
    assert Decimal(str(first.data["items"][0]["quantity"])) == Decimal("4")
    left = tenant_a.client.get(f"/api/v1/sales/quotations/{qid}/")
    assert left.status_code == 200
    assert left.data["status"] == "DRAFT"
    assert Decimal(str(left.data["items"][0]["converted_quantity"])) == Decimal("4.000")

    over = tenant_a.client.post(
        f"/api/v1/sales/quotations/{qid}/convert-to-order/",
        {"items": [{"id": line_id, "quantity": "7"}]},
        format="json",
    )
    assert over.status_code == 400
    assert "remaining" in str(over.data).lower()

    second = tenant_a.client.post(
        f"/api/v1/sales/quotations/{qid}/convert/",
        {"items": [{"id": line_id, "quantity": "6"}]},
        format="json",
    )
    assert second.status_code == 200, second.data
    assert Decimal(str(second.data["items"][0]["quantity"])) == Decimal("6")
    done = tenant_a.client.get(f"/api/v1/sales/quotations/{qid}/")
    assert done.data["status"] == "CONVERTED"
    third = tenant_a.client.post(f"/api/v1/sales/quotations/{qid}/convert/")
    assert third.status_code == 400


def test_cft_116_live_irn_blocks_line_amend(tenant_a):
    """CFT-116 — GENERATED / MANUAL_IRN blocks line amend (same predicate as cancel)."""
    product = make_product(tenant_a.company, sku="CFT116")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}]
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    obj = SalesInvoice.objects.get(pk=inv["id"])
    obj.irn = "a" * 64
    obj.einvoice_status = SalesInvoice.EInvoiceStatus.GENERATED
    obj.save(update_fields=["irn", "einvoice_status"])

    amend = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv['id']}/",
        {
            "confirm_amend": True,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "90"}],
        },
        format="json",
    )
    assert amend.status_code == 400, amend.data
    assert "live IRN" in str(amend.data)
    assert "amending" in str(amend.data).lower()

    obj.einvoice_status = SalesInvoice.EInvoiceStatus.MANUAL_IRN
    obj.save(update_fields=["einvoice_status"])
    amend2 = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv['id']}/",
        {
            "confirm_amend": True,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "80"}],
        },
        format="json",
    )
    assert amend2.status_code == 400
    obj.refresh_from_db()
    assert Decimal(str(obj.items.get().unit_price)) == Decimal("100.00")


def test_cft_118_hold_releases_after_return_or_pay_residual_dn_keeps_hold(tenant_a):
    """CFT-118 — clearing severe overdue AR releases auto credit-hold; residual DN AR keeps it.
    CFT-117 (block with no static limit) is gated by
    test_a07_dunning.test_auto_credit_hold_blocks_severe_overdue_customer_with_no_credit_limit."""
    company = tenant_a.company
    company.auto_credit_hold_on_severe_overdue = True
    company.save(update_fields=["auto_credit_hold_on_severe_overdue"])
    product = make_product(company, sku="CFT118")
    add_stock(tenant_a, product, "50")
    customer = make_customer(company)
    aged = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "50", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{aged['id']}/complete/").status_code == 200
    inv = SalesInvoice.objects.get(pk=aged["id"])
    inv.due_date = date.today() - timedelta(days=100)
    inv.save(update_fields=["due_date"])

    blocked = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "50", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    hold = tenant_a.client.post(f"/api/v1/sales/invoices/{blocked['id']}/complete/")
    assert hold.status_code == 400
    assert "collection hold" in str(hold.data).lower()

    ret = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": aged["id"],
            "items": [{"product": product.id, "quantity": "1", "unit_price": "50", "gst_rate": "0"}],
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    assert tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/").status_code == 200
    snap = customer_risk_snapshot(company, customer)
    assert snap["collection_status"] not in ("stop_credit", "overdue_severe")

    released = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "50", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    ok = tenant_a.client.post(f"/api/v1/sales/invoices/{released['id']}/complete/")
    assert ok.status_code == 200, ok.data


def test_cft_118_payment_releases_hold(tenant_a):
    """CFT-118 — paying the severe overdue invoice releases auto credit-hold."""
    company = tenant_a.company
    company.auto_credit_hold_on_severe_overdue = True
    company.save(update_fields=["auto_credit_hold_on_severe_overdue"])
    product = make_product(company, sku="CFT118-PAY")
    add_stock(tenant_a, product, "50")
    customer = make_customer(company)
    aged = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "50", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{aged['id']}/complete/")
    assert done.status_code == 200, done.data
    inv = SalesInvoice.objects.get(pk=aged["id"])
    inv.due_date = date.today() - timedelta(days=100)
    inv.save(update_fields=["due_date"])
    blocked = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "50", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    hold = tenant_a.client.post(f"/api/v1/sales/invoices/{blocked['id']}/complete/")
    assert hold.status_code == 400
    receipt = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": str(done.data["grand_total"]), "mode": "CASH"},
        format="json",
    )
    assert receipt.status_code in (200, 201), receipt.data
    alloc = tenant_a.client.post(
        "/api/v1/payments/allocations/",
        {
            "receipt": receipt.data["id"],
            "sales_invoice": aged["id"],
            "amount": str(done.data["grand_total"]),
        },
        format="json",
    )
    assert alloc.status_code in (200, 201), alloc.data
    snap = customer_risk_snapshot(company, customer)
    assert snap["collection_status"] not in ("stop_credit", "overdue_severe")
    released = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "50", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    ok = tenant_a.client.post(f"/api/v1/sales/invoices/{released['id']}/complete/")
    assert ok.status_code == 200, ok.data


def test_cft_118_residual_dn_keeps_hold(tenant_a):
    """CFT-118 — a return that leaves residual DN AR (G-23) must keep the hold."""
    company = tenant_a.company
    company.auto_credit_hold_on_severe_overdue = True
    company.save(update_fields=["auto_credit_hold_on_severe_overdue"])
    product = make_product(company, sku="CFT118-DN")
    add_stock(tenant_a, product, "50")
    customer2 = make_customer(company, name="CFT118-DN")
    base = create_draft_invoice(
        tenant_a,
        customer2,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    done_base = tenant_a.client.post(f"/api/v1/sales/invoices/{base['id']}/complete/")
    assert done_base.status_code == 200, done_base.data
    src = done_base.data["items"][0]["id"]
    dn = tenant_a.client.post(
        "/api/v1/sales/debit-notes/",
        {
            "customer": customer2.id,
            "sales_invoice": base["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [
                {
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "40",
                    "gst_rate": "0",
                    "source_item": src,
                }
            ],
        },
        format="json",
    )
    assert dn.status_code == 201, dn.data
    dn_done = tenant_a.client.post(
        f"/api/v1/sales/debit-notes/{dn.data['id']}/complete/",
        {"confirm_additional_debit": True},
        format="json",
    )
    assert dn_done.status_code == 200, dn_done.data
    base_obj = SalesInvoice.objects.get(pk=base["id"])
    base_obj.due_date = date.today() - timedelta(days=100)
    base_obj.save(update_fields=["due_date"])
    ret2 = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer2.id,
            "sales_invoice": base["id"],
            "items": [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )
    assert ret2.status_code == 201, ret2.data
    assert tenant_a.client.post(f"/api/v1/sales/returns/{ret2.data['id']}/complete/").status_code == 200
    snap2 = customer_risk_snapshot(company, customer2)
    assert snap2["collection_status"] in ("stop_credit", "overdue_severe")
    still = create_draft_invoice(
        tenant_a,
        customer2,
        [{"product": product.id, "quantity": "1", "unit_price": "50", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    keep = tenant_a.client.post(f"/api/v1/sales/invoices/{still['id']}/complete/")
    assert keep.status_code == 400
    assert "collection hold" in str(keep.data).lower()


def test_cft_119_return_restores_same_batch_and_serial(tenant_a):
    """CFT-119 — return restores the sold lot / serial, not an arbitrary FEFO lot."""
    company = tenant_a.company
    warehouse = InventoryService.default_warehouse(company)
    product = make_product(company, sku="CFT119-B")
    product.track_batch = True
    product.save(update_fields=["track_batch"])
    today = date.today()
    a = tenant_a.client.post(
        "/api/v1/inventory/opening-stock/",
        {
            "product": product.id,
            "quantity": "5",
            "batch_no": "LOT-A",
            "expiry_date": (today + timedelta(days=10)).isoformat(),
            "unit_cost": "10",
        },
        format="json",
    )
    assert a.status_code == 201, a.data
    b = tenant_a.client.post(
        "/api/v1/inventory/opening-stock/",
        {
            "product": product.id,
            "quantity": "5",
            "batch_no": "LOT-B",
            "expiry_date": (today + timedelta(days=40)).isoformat(),
            "unit_cost": "10",
        },
        format="json",
    )
    assert b.status_code == 201, b.data
    lot_a = BatchLot.objects.get(product=product, batch_no="LOT-A")
    lot_b = BatchLot.objects.get(product=product, batch_no="LOT-B")
    customer = make_customer(company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100", "batch": lot_b.id}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch=lot_b).on_hand == Decimal("3")
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch=lot_a).on_hand == Decimal("5")

    ret = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "items": [{"product": product.id, "quantity": "2", "unit_price": "100", "condition": "SELLABLE"}],
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    assert tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/").status_code == 200
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch=lot_b).on_hand == Decimal("5")
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch=lot_a).on_hand == Decimal("5")

    serial_p = make_product(company, sku="CFT119-S", track_serial=True)
    opened = tenant_a.client.post(
        "/api/v1/inventory/opening-stock/",
        {
            "product": serial_p.id,
            "quantity": "2",
            "unit_cost": "10",
            "serial_numbers": ["SN-KEEP", "SN-SOLD"],
        },
        format="json",
    )
    assert opened.status_code == 201, opened.data
    inv_s = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": serial_p.id, "quantity": "1", "unit_price": "100", "serial_numbers": ["SN-SOLD"]}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv_s['id']}/complete/").status_code == 200
    assert SerialNumber.objects.get(product=serial_p, serial_number="SN-SOLD").status == SerialNumber.Status.SOLD
    assert SerialNumber.objects.get(product=serial_p, serial_number="SN-KEEP").status == SerialNumber.Status.AVAILABLE

    wrong = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": inv_s["id"],
            "items": [
                {
                    "product": serial_p.id,
                    "quantity": "1",
                    "unit_price": "100",
                    "serial_numbers": ["SN-KEEP"],
                }
            ],
        },
        format="json",
    )
    if wrong.status_code == 201:
        bad = tenant_a.client.post(f"/api/v1/sales/returns/{wrong.data['id']}/complete/")
        assert bad.status_code >= 400
    else:
        assert wrong.status_code >= 400
    assert SerialNumber.objects.get(product=serial_p, serial_number="SN-KEEP").status == SerialNumber.Status.AVAILABLE

    good = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": inv_s["id"],
            "items": [
                {
                    "product": serial_p.id,
                    "quantity": "1",
                    "unit_price": "100",
                    "serial_numbers": ["SN-SOLD"],
                }
            ],
        },
        format="json",
    )
    assert good.status_code == 201, good.data
    assert tenant_a.client.post(f"/api/v1/sales/returns/{good.data['id']}/complete/").status_code == 200
    assert SerialNumber.objects.get(product=serial_p, serial_number="SN-SOLD").status == SerialNumber.Status.AVAILABLE
    assert SerialNumber.objects.get(product=serial_p, serial_number="SN-KEEP").status == SerialNumber.Status.AVAILABLE


def test_cft_120_stale_amend_revision_conflicts(tenant_a):
    """CFT-120 — a second amend with a stale expected_amend_revision is 409, not a silent overwrite."""
    product = make_product(tenant_a.company, sku="CFT120")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}]
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    rev = done.data.get("amend_revision", 0)
    first = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv['id']}/",
        {
            "confirm_amend": True,
            "expected_amend_revision": rev,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "90"}],
        },
        format="json",
    )
    assert first.status_code == 200, first.data
    assert Decimal(str(first.data["items"][0]["unit_price"])) == Decimal("90.00")
    stale = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv['id']}/",
        {
            "confirm_amend": True,
            "expected_amend_revision": rev,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "80"}],
        },
        format="json",
    )
    assert stale.status_code == 409, stale.data
    obj = SalesInvoice.objects.get(pk=inv["id"])
    assert Decimal(str(obj.items.get().unit_price)) == Decimal("90.00")
    assert obj.amend_revision == int(rev) + 1


def test_cft_120_amend_without_revision_is_conflict(tenant_a):
    """CFT-120 — completed money amend without expected_amend_revision is 409, not last-write-wins."""
    product = make_product(tenant_a.company, sku="CFT120-MISS")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}]
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    missing = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv['id']}/",
        {
            "confirm_amend": True,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "90"}],
        },
        format="json",
    )
    assert missing.status_code == 409, missing.data
    obj = SalesInvoice.objects.get(pk=inv["id"])
    assert Decimal(str(obj.items.get().unit_price)) == Decimal("100.00")


def test_cft_119_pos_return_restores_same_batch(tenant_a):
    """CFT-119 — POS checkout then /sales/returns restores the sold lot and serial (D15)."""
    company = tenant_a.company
    warehouse = InventoryService.default_warehouse(company)
    product = make_product(company, sku="CFT119-POS")
    product.track_batch = True
    product.save(update_fields=["track_batch"])
    today = date.today()
    a = tenant_a.client.post(
        "/api/v1/inventory/opening-stock/",
        {
            "product": product.id,
            "quantity": "5",
            "batch_no": "POS-A",
            "expiry_date": (today + timedelta(days=10)).isoformat(),
            "unit_cost": "10",
        },
        format="json",
    )
    assert a.status_code == 201, a.data
    b = tenant_a.client.post(
        "/api/v1/inventory/opening-stock/",
        {
            "product": product.id,
            "quantity": "5",
            "batch_no": "POS-B",
            "expiry_date": (today + timedelta(days=40)).isoformat(),
            "unit_cost": "10",
        },
        format="json",
    )
    assert b.status_code == 201, b.data
    lot_b = BatchLot.objects.get(product=product, batch_no="POS-B")
    lot_a = BatchLot.objects.get(product=product, batch_no="POS-A")
    customer = make_customer(company)
    pos = tenant_a.client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {
            "invoice": {
                "customer": customer.id,
                "invoice_type": "RETAIL",
                "items": [
                    {
                        "product": product.id,
                        "quantity": "2",
                        "unit_price": "100",
                        "gst_rate": "0",
                        "batch": lot_b.id,
                    }
                ],
            },
            "payment": {"mode": "CASH", "amount": "200"},
        },
        format="json",
    )
    assert pos.status_code == 201, pos.data
    invoice = pos.data.get("invoice") or pos.data
    inv_id = invoice["id"]
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch=lot_b).on_hand == Decimal("3")
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch=lot_a).on_hand == Decimal("5")
    ret = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": inv_id,
            "items": [{"product": product.id, "quantity": "2", "unit_price": "100", "condition": "SELLABLE"}],
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    assert tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/").status_code == 200
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch=lot_b).on_hand == Decimal("5")
    assert StockBalance.objects.get(product=product, warehouse=warehouse, batch=lot_a).on_hand == Decimal("5")

    serial_p = make_product(company, sku="CFT119-POS-S", track_serial=True)
    opened = tenant_a.client.post(
        "/api/v1/inventory/opening-stock/",
        {
            "product": serial_p.id,
            "quantity": "2",
            "unit_cost": "10",
            "serial_numbers": ["POS-KEEP", "POS-SOLD"],
        },
        format="json",
    )
    assert opened.status_code == 201, opened.data
    pos_s = tenant_a.client.post(
        "/api/v1/sales/invoices/pos-checkout/",
        {
            "invoice": {
                "customer": customer.id,
                "invoice_type": "RETAIL",
                "items": [
                    {
                        "product": serial_p.id,
                        "quantity": "1",
                        "unit_price": "100",
                        "gst_rate": "0",
                        "serial_numbers": ["POS-SOLD"],
                    }
                ],
            },
            "payment": {"mode": "CASH", "amount": "100"},
        },
        format="json",
    )
    assert pos_s.status_code == 201, pos_s.data
    assert SerialNumber.objects.get(product=serial_p, serial_number="POS-SOLD").status == SerialNumber.Status.SOLD
    assert SerialNumber.objects.get(product=serial_p, serial_number="POS-KEEP").status == SerialNumber.Status.AVAILABLE
    inv_s_id = (pos_s.data.get("invoice") or pos_s.data)["id"]
    ret_s = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": inv_s_id,
            "items": [
                {
                    "product": serial_p.id,
                    "quantity": "1",
                    "unit_price": "100",
                    "serial_numbers": ["POS-SOLD"],
                    "condition": "SELLABLE",
                }
            ],
        },
        format="json",
    )
    assert ret_s.status_code == 201, ret_s.data
    assert tenant_a.client.post(f"/api/v1/sales/returns/{ret_s.data['id']}/complete/").status_code == 200
    assert SerialNumber.objects.get(product=serial_p, serial_number="POS-SOLD").status == SerialNumber.Status.AVAILABLE
    assert SerialNumber.objects.get(product=serial_p, serial_number="POS-KEEP").status == SerialNumber.Status.AVAILABLE

