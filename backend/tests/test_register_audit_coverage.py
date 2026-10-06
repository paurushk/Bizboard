"""Register tasks P-0115 / X-0432 / P-0507: every posting action writes an AuditEvent.

One test per posting action. Each drives the real API and asserts a new
AuditEvent row exists for the right company, entity type and entity id.
Purchase complete with books off and journal post each write an audit event.
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from core.models import AuditEvent
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def _assert_audited(company, entity_type, entity_id, description_contains=None):
    qs = AuditEvent.objects.filter(
        company=company, entity_type=entity_type, entity_id=str(entity_id),
    )
    if description_contains:
        qs = qs.filter(description__icontains=description_contains)
    assert qs.exists(), f"no AuditEvent for {entity_type}#{entity_id} ({description_contains})"


def _sales_item(product, qty="2"):
    return [{"product": product.id, "quantity": qty, "unit_price": "100.00", "gst_rate": "18"}]


def _completed_sales_invoice(tenant, sku, qty="5", stock="20"):
    product = make_product(tenant.company, sku=sku)
    add_stock(tenant, product, stock)
    customer = make_customer(tenant.company)
    draft = create_draft_invoice(tenant, customer, _sales_item(product, qty))
    resp = tenant.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert resp.status_code == 200, resp.data
    return product, customer, draft["id"]


def _completed_purchase_invoice(tenant, sku, qty="10"):
    product = make_product(tenant.company, sku=sku)
    supplier = make_supplier(tenant.company)
    draft = create_draft_purchase(
        tenant, supplier,
        [{"product": product.id, "quantity": qty, "unit_price": "50.00", "gst_rate": "18"}],
    )
    resp = tenant.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/")
    assert resp.status_code == 200, resp.data
    return product, supplier, draft["id"]


def test_sales_invoice_complete_writes_audit_event(tenant_a):
    _, _, inv_id = _completed_sales_invoice(tenant_a, "AUD-SI")
    _assert_audited(tenant_a.company, "SalesInvoice", inv_id, "sales_invoice.completed")


def test_sales_invoice_cancel_writes_audit_event(tenant_a):
    _, _, inv_id = _completed_sales_invoice(tenant_a, "AUD-SIC")
    resp = tenant_a.client.post(
        f"/api/v1/sales/invoices/{inv_id}/cancel/", {"reason": "audit test"}, format="json",
    )
    assert resp.status_code == 200, resp.data
    _assert_audited(tenant_a.company, "SalesInvoice", inv_id, "sales_invoice.cancelled")


def test_purchase_invoice_complete_writes_audit_event(tenant_a):
    _, _, pid = _completed_purchase_invoice(tenant_a, "AUD-PI")
    _assert_audited(tenant_a.company, "PurchaseInvoice", pid, "purchase_invoice.completed")


def test_purchase_invoice_complete_with_books_on_writes_audit_event(tenant_a):
    from accounting.services import seed_chart_of_accounts

    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(company, tenant_a.owner)
    _, _, pid = _completed_purchase_invoice(tenant_a, "AUD-PIB")
    _assert_audited(company, "PurchaseInvoice", pid, "purchase_invoice.completed")


def test_customer_receipt_post_writes_audit_event(tenant_a):
    customer = make_customer(tenant_a.company)
    resp = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": "500.00", "method": "BANK"},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    _assert_audited(tenant_a.company, "CustomerReceipt", resp.data["id"], "customer_receipt.created")


def test_supplier_payment_post_writes_audit_event(tenant_a):
    supplier = make_supplier(tenant_a.company)
    resp = tenant_a.client.post(
        "/api/v1/payments/supplier-payments/",
        {"supplier": supplier.id, "amount": "500", "mode": "CASH"},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    _assert_audited(tenant_a.company, "SupplierPayment", resp.data["id"], "supplier_payment.created")


def test_journal_post_writes_audit_event(tenant_a):
    from accounting.models import Account, JournalEntry
    from accounting.services import seed_chart_of_accounts

    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(company, tenant_a.owner)
    cash = Account.objects.get(company=company, code="1100").id
    equity = Account.objects.get(company=company, code="3200").id
    created = tenant_a.client.post(
        "/api/v1/accounting/journals/",
        {
            "entry_date": timezone.localdate().isoformat(),
            "narration": "audit coverage",
            "lines": [
                {"account": cash, "debit": "100.00", "credit": "0"},
                {"account": equity, "debit": "0", "credit": "100.00"},
            ],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    jid = created.data["id"]
    posted = tenant_a.client.post(f"/api/v1/accounting/journals/{jid}/post/")
    assert posted.status_code in (200, 202), posted.data
    assert JournalEntry.objects.get(pk=jid).status == "POSTED"
    _assert_audited(company, "JournalEntry", jid)


def test_sales_return_complete_writes_audit_event(tenant_a):
    product, customer, inv_id = _completed_sales_invoice(tenant_a, "AUD-SR")
    created = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {"customer": customer.id, "sales_invoice": inv_id, "items": _sales_item(product, "1")},
        format="json",
    )
    assert created.status_code == 201, created.data
    rid = created.data["id"]
    done = tenant_a.client.post(f"/api/v1/sales/returns/{rid}/complete/")
    assert done.status_code == 200, done.data
    _assert_audited(tenant_a.company, "SalesReturn", rid, "sales_return.completed")


def test_purchase_return_complete_writes_audit_event(tenant_a):
    product, supplier, pid = _completed_purchase_invoice(tenant_a, "AUD-PR")
    created = tenant_a.client.post(
        "/api/v1/purchases/returns/",
        {
            "supplier": supplier.id, "purchase_invoice": pid,
            "items": [{"product": product.id, "quantity": "4", "unit_price": "50.00"}],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    rid = created.data["id"]
    done = tenant_a.client.post(f"/api/v1/purchases/returns/{rid}/complete/")
    assert done.status_code == 200, done.data
    _assert_audited(tenant_a.company, "PurchaseReturn", rid, "purchase_return.completed")


def test_sales_credit_note_complete_writes_audit_event(tenant_a):
    product, customer, inv_id = _completed_sales_invoice(tenant_a, "AUD-CN")
    created = tenant_a.client.post(
        "/api/v1/sales/credit-notes/",
        {
            "customer": customer.id, "sales_invoice": inv_id,
            "reason": "CORRECTION_OF_INVOICE", "items": _sales_item(product, "1"),
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    nid = created.data["id"]
    done = tenant_a.client.post(f"/api/v1/sales/credit-notes/{nid}/complete/")
    assert done.status_code == 200, done.data
    _assert_audited(tenant_a.company, "SalesCreditNote", nid, "sales_credit_note.completed")


def test_stock_adjustment_writes_audit_event(tenant_a):
    product = make_product(tenant_a.company, sku="AUD-ADJ")
    add_stock(tenant_a, product, "10")
    resp = tenant_a.client.post(
        "/api/v1/inventory/adjustments/",
        {"product": product.id, "quantity": "-1", "reason": "damaged"},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    _assert_audited(tenant_a.company, "StockMovement", resp.data["id"], "Adjustment")


def test_stock_transfer_complete_writes_audit_event(tenant_a):
    from inventory.models import MovementType, Warehouse
    from inventory.services import InventoryService

    company = tenant_a.company
    product = make_product(company, sku="AUD-TR")
    north = InventoryService.default_warehouse(company)
    south = Warehouse.objects.create(company=company, name="South", code="SOUTH")
    InventoryService.post_movement(
        company=company, product=product, warehouse=north,
        movement_type=MovementType.OPENING_STOCK, quantity=Decimal("50"),
        unit_cost=Decimal("60"), user=tenant_a.owner,
    )
    created = tenant_a.client.post(
        "/api/v1/inventory/transfers/",
        {
            "from_warehouse": north.id, "to_warehouse": south.id,
            "lines": [{"product": product.id, "quantity": "10.000"}],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    tid = created.data["id"]
    done = tenant_a.client.post(f"/api/v1/inventory/transfers/{tid}/complete/")
    assert done.status_code == 200, done.data
    _assert_audited(company, "StockTransfer", tid)


def test_goods_receipt_complete_writes_audit_event(tenant_a):
    from inventory.services import InventoryService

    company = tenant_a.company
    supplier = make_supplier(company, gstin="29ZZZZZ5555Z1Z5")
    product = make_product(company, sku="AUD-GRN", purchase_price="100")
    warehouse = InventoryService.default_warehouse(company)
    created = tenant_a.client.post(
        "/api/v1/purchases/grns/",
        {
            "supplier": supplier.id, "warehouse": warehouse.id,
            "receipt_date": "2026-06-10", "supplier_challan_number": "CH-1",
            "items": [{
                "product": product.id, "quantity_received": "10",
                "quantity_accepted": "8", "quantity_rejected": "2", "unit_price": "100.00",
            }],
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    gid = created.data["id"]
    done = tenant_a.client.post(f"/api/v1/purchases/grns/{gid}/complete/")
    assert done.status_code == 200, done.data
    _assert_audited(company, "GoodsReceipt", gid)
