"""B4/B5 focused gates — CR-129/130 purchase notes + CR-142 serial SALE resolve."""

from datetime import timedelta
from decimal import Decimal

import pytest

from inventory.models import MovementType, SerialNumber, StockMovement
from inventory.services import InventoryService
from inventory.views import _sale_movement_for_serial
from purchases.models import PurchaseInvoice, PurchaseItem
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def _complete_purchase(tenant, supplier, product, qty="2", unit_price="100"):
    pur = create_draft_purchase(
        tenant,
        supplier,
        [{"product": product.id, "quantity": qty, "unit_price": unit_price, "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert tenant.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    src = PurchaseItem.objects.get(invoice_id=pur["id"])
    return pur, src


def test_cr129_purchase_cn_rejects_draft_source_invoice(tenant_a):
    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    # Leave DRAFT — do not complete.
    src = PurchaseItem.objects.get(invoice_id=pur["id"])
    cn = tenant_a.client.post(
        "/api/v1/purchases/credit-notes/",
        {
            "supplier": supplier.id,
            "purchase_invoice": pur["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [
                {
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "100",
                    "gst_rate": "0",
                    "source_item": src.id,
                }
            ],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    resp = tenant_a.client.post(f"/api/v1/purchases/credit-notes/{cn.data['id']}/complete/")
    assert resp.status_code == 400
    assert "completed" in str(resp.data).lower()


def test_cr129_purchase_cn_rejects_note_date_before_invoice(tenant_a):
    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    pur, src = _complete_purchase(tenant_a, supplier, product)
    inv = PurchaseInvoice.objects.get(pk=pur["id"])
    early = (inv.invoice_date - timedelta(days=1)).isoformat()
    cn = tenant_a.client.post(
        "/api/v1/purchases/credit-notes/",
        {
            "supplier": supplier.id,
            "purchase_invoice": pur["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "note_date": early,
            "items": [
                {
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "100",
                    "gst_rate": "0",
                    "source_item": src.id,
                }
            ],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    resp = tenant_a.client.post(f"/api/v1/purchases/credit-notes/{cn.data['id']}/complete/")
    assert resp.status_code == 400
    assert "before" in str(resp.data).lower()


def test_cr129_purchase_cn_source_qty_cap(tenant_a):
    product1 = make_product(tenant_a.company, sku="CR129-P1")
    product2 = make_product(tenant_a.company, sku="CR129-P2")
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [
            {"product": product1.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"},
            {"product": product2.id, "quantity": "2", "unit_price": "100", "gst_rate": "0"},
        ],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    src = PurchaseItem.objects.get(invoice_id=pur["id"], product=product1)
    cn = tenant_a.client.post(
        "/api/v1/purchases/credit-notes/",
        {
            "supplier": supplier.id,
            "purchase_invoice": pur["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [
                {
                    "product": product1.id,
                    "quantity": "2",
                    "unit_price": "100",
                    "gst_rate": "0",
                    "source_item": src.id,
                }
            ],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    resp = tenant_a.client.post(f"/api/v1/purchases/credit-notes/{cn.data['id']}/complete/")
    assert resp.status_code == 400
    assert "quantity" in str(resp.data).lower() or "qty" in str(resp.data).lower()


def test_cr129_purchase_return_reason_requires_return_fk(tenant_a):
    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    pur, src = _complete_purchase(tenant_a, supplier, product, qty="1")
    cn = tenant_a.client.post(
        "/api/v1/purchases/credit-notes/",
        {
            "supplier": supplier.id,
            "purchase_invoice": pur["id"],
            "reason": "PURCHASE_RETURN",
            "items": [
                {
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "100",
                    "gst_rate": "0",
                    "source_item": src.id,
                }
            ],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    resp = tenant_a.client.post(f"/api/v1/purchases/credit-notes/{cn.data['id']}/complete/")
    assert resp.status_code == 400
    assert "purchase return" in str(resp.data).lower()


def test_cr130_purchase_cn_rejects_supplier_invoice_mismatch(tenant_a):
    product = make_product(tenant_a.company)
    supplier_a = make_supplier(tenant_a.company, name="Supp A")
    supplier_b = make_supplier(tenant_a.company, name="Supp B")
    pur, src = _complete_purchase(tenant_a, supplier_a, product, qty="1")
    cn = tenant_a.client.post(
        "/api/v1/purchases/credit-notes/",
        {
            "supplier": supplier_b.id,
            "purchase_invoice": pur["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [
                {
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "100",
                    "gst_rate": "0",
                    "source_item": src.id,
                }
            ],
        },
        format="json",
    )
    assert cn.status_code == 400
    assert "supplier" in str(cn.data).lower()


@pytest.fixture
def fifo_company(tenant_a):
    company = tenant_a.company
    company.inventory_valuation_method = "FIFO"
    company.save(update_fields=["inventory_valuation_method"])
    return tenant_a


def test_cr142_prefers_completed_invoice_over_draft_shadow(fifo_company):
    """CR-142: a newer DRAFT listing the same SN must not win over COMPLETED SALE."""
    tenant = fifo_company
    product = make_product(tenant.company, sku="CR142-SN", track_serial=True, purchase_price="40")
    customer = make_customer(tenant.company)
    wh = InventoryService.default_warehouse(tenant.company)
    InventoryService.post_movement(
        company=tenant.company,
        warehouse=wh,
        product=product,
        movement_type=MovementType.PURCHASE,
        quantity="1",
        unit_cost="40",
        user=tenant.owner,
    )
    SerialNumber.objects.create(
        company=tenant.company,
        product=product,
        warehouse=wh,
        serial_number="CR142-SN-1",
    )
    inv = create_draft_invoice(
        tenant,
        customer,
        [
            {
                "product": product.id,
                "quantity": "1",
                "unit_price": "100",
                "serial_numbers": ["CR142-SN-1"],
            }
        ],
    )
    assert tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200
    sale_move = StockMovement.objects.get(
        company=tenant.company,
        product=product,
        movement_type=MovementType.SALE,
        reference_type="sales_invoice",
        reference_id=str(inv["id"]),
    )

    # Draft shadow that also lists the SN (no SALE moves).
    create_draft_invoice(
        tenant,
        customer,
        [
            {
                "product": product.id,
                "quantity": "1",
                "unit_price": "999",
                "serial_numbers": ["CR142-SN-1"],
            }
        ],
    )

    serial = SerialNumber.objects.get(company=tenant.company, serial_number="CR142-SN-1")
    resolved = _sale_movement_for_serial(tenant.company, serial)
    assert resolved is not None
    assert resolved.pk == sale_move.pk
    assert Decimal(str(resolved.unit_cost)) == Decimal("40")


def test_cr124_auto_return_cn_on_paid_invoice_unallocates_instead_of_failing(tenant_a):
    """CR-124: a sales return against a fully-allocated invoice must auto-move the
    receipt money to an unallocated advance and still complete the auto credit
    note — never hard-fail on the paid-invoice confirm guard."""
    from ledgers.services import LedgerService
    from sales.models import SalesCreditNote

    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "100")
    customer = make_customer(tenant_a.company, state="Karnataka")
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "10", "unit_price": "100"}]
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200

    receipt = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": "1180", "mode": "CASH"},
        format="json",
    )
    assert receipt.status_code in (200, 201), receipt.data
    alloc = tenant_a.client.post(
        "/api/v1/payments/allocations/",
        {"receipt": receipt.data["id"], "sales_invoice": inv["id"], "amount": "1180"},
        format="json",
    )
    assert alloc.status_code in (200, 201), alloc.data
    assert LedgerService.customer_unallocated_receipts(tenant_a.company, customer) == Decimal("0")

    ret = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "items": [{"product": product.id, "quantity": "2", "unit_price": "100"}],
        },
        format="json",
    )
    assert ret.status_code in (200, 201), ret.data
    done = tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/")
    assert done.status_code == 200, done.data

    # Auto CN completed, and 236 (200 + 18% GST) moved to an unallocated advance.
    cn = SalesCreditNote.objects.filter(
        sales_invoice_id=inv["id"], status=SalesCreditNote.Status.COMPLETED
    ).first()
    assert cn is not None
    assert LedgerService.customer_unallocated_receipts(tenant_a.company, customer) == Decimal("236.00")
    resp = tenant_a.client.get(f"/api/v1/ledgers/customers/{customer.id}/")
    assert Decimal(resp.data["outstanding"]) == Decimal("0.00")
