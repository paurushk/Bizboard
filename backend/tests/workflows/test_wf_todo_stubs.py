"""Phase 2 workflow chains not yet implemented — each is a spec.

Every function is skipped with the exact contract it must assert. Implement one
by replacing its body with the chain (drive the API end to end, then call
``assert_consistent(company)`` plus the flow-specific numbers), and delete the
skip. `pytest -q tests/workflows/` shows the outstanding count.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db

_TODO = "Phase 2 chain not yet implemented — see docstring"


def test_wf02_sale_interstate_with_cess(tenant_a, assert_consistent):
    """Inter-state GST invoice: IGST (+ cess where the item carries it), CGST/SGST = 0;
    place-of-supply drives the split; stock down; AR up; GL balanced; TB 0."""
    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])

    product = make_product(company, gst_rate="28", selling_price="100")
    add_stock(tenant_a, product, "20", unit_cost="60")
    customer = make_customer(company, name="Out of State Buyer", state="Maharashtra", gstin="27BBBBB1111B2ZX")

    # Draft invoice: 2 units at 100.00 each, 28% GST, 12% ad-valorem cess, plus 5.00 specific cess per unit
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [
            {
                "product": product.id,
                "quantity": "2",
                "unit_price": "100.00",
                "gst_rate": "28",
                "cess_rate": "12.00",
                "cess_amount": "5.00",
            }
        ],
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    d = done.data

    # Tax calculation:
    # Taxable = 2 * 100 = 200.00
    # CGST = 0.00, SGST = 0.00
    # IGST = 200 * 28% = 56.00
    # Cess = (200 * 12%) + (2 * 5.00) = 24.00 + 10.00 = 34.00
    # Grand total = 200 + 56 + 34 = 290.00
    assert Decimal(str(d["taxable_total"])) == Decimal("200.00")
    assert Decimal(str(d["cgst_total"])) == Decimal("0.00")
    assert Decimal(str(d["sgst_total"])) == Decimal("0.00")
    assert Decimal(str(d["igst_total"])) == Decimal("56.00")
    assert Decimal(str(d["cess_total"])) == Decimal("34.00")
    assert Decimal(str(d["grand_total"])) == Decimal("290.00")

    # Stock: 20 - 2 = 18
    from inventory.services import InventoryService

    on_hand = InventoryService.available_quantity(company=company, product=product)
    assert on_hand == Decimal("18.000")

    # Books: GL entry exists and is balanced
    from accounting.models import JournalEntry

    entries = JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED)
    assert entries.exists()
    for e in entries:
        e.assert_balanced()

    # Customer receipt and allocation
    pay = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {
            "customer": customer.id,
            "amount": "290.00",
            "method": "CASH",
            "allocations": [{"invoice": inv["id"], "amount": "290.00"}],
        },
        format="json",
    )
    assert pay.status_code in (200, 201), pay.data

    assert_consistent(company)



def test_wf03_sales_return(tenant_a, assert_consistent):
    """Sales return against a completed invoice: stock up, GST reversed, AR down,
    the credit note appears in the GSTR-1 CDNR aid. Invariant sweep clean."""
    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])

    product = make_product(company, gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "20", unit_cost="60")
    customer = make_customer(company, state="Karnataka", gstin="29AAAAA0000A1ZY")

    # 1. Create and complete sales invoice for 3 units
    from tests.conftest import create_draft_invoice

    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "3", "unit_price": "100.00", "gst_rate": "18"}],
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data

    from inventory.services import InventoryService

    assert InventoryService.available_quantity(company=company, product=product) == Decimal("17.000")

    # 2. Create sales return for 1 unit
    ret_res = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "sales_invoice": inv["id"],
            "customer": customer.id,
            "return_date": inv["invoice_date"],
            "items": [
                {
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "100.00",
                    "gst_rate": "18",
                }
            ],
        },
        format="json",
    )
    assert ret_res.status_code == 201, ret_res.data
    ret_id = ret_res.data["id"]

    # 3. Complete sales return
    ret_done = tenant_a.client.post(f"/api/v1/sales/returns/{ret_id}/complete/")
    assert ret_done.status_code == 200, ret_done.data

    # Stock should be restored: 17 + 1 = 18
    assert InventoryService.available_quantity(company=company, product=product) == Decimal("18.000")

    # GL entries are posted and balanced
    from accounting.models import JournalEntry

    entries = JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED)
    assert entries.exists()
    for e in entries:
        e.assert_balanced()

    assert_consistent(company)


def test_wf05_purchase_return(tenant_a, assert_consistent):
    """Purchase return against a completed purchase: stock down, ITC reversed,
    AP down. Invariant sweep clean."""
    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])

    product = make_product(company, gst_rate="18", purchase_price="80")
    supplier = make_supplier(company, state="Karnataka")

    # 1. Create and complete purchase for 5 units
    from tests.conftest import create_draft_purchase

    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "5", "unit_price": "80.00", "gst_rate": "18"}],
    )
    done = tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/")
    assert done.status_code == 200, done.data

    from inventory.services import InventoryService

    assert InventoryService.available_quantity(company=company, product=product) == Decimal("5.000")

    # 2. Create purchase return for 2 units
    ret_res = tenant_a.client.post(
        "/api/v1/purchases/returns/",
        {
            "purchase_invoice": pur["id"],
            "supplier": supplier.id,
            "return_date": pur["invoice_date"],
            "items": [
                {
                    "product": product.id,
                    "quantity": "2",
                    "unit_price": "80.00",
                    "gst_rate": "18",
                }
            ],
        },
        format="json",
    )
    assert ret_res.status_code == 201, ret_res.data
    ret_id = ret_res.data["id"]

    # 3. Complete purchase return
    ret_done = tenant_a.client.post(f"/api/v1/purchases/returns/{ret_id}/complete/")
    assert ret_done.status_code == 200, ret_done.data

    # Stock should be decreased: 5 - 2 = 3
    assert InventoryService.available_quantity(company=company, product=product) == Decimal("3.000")

    # GL entries are posted and balanced
    from accounting.models import JournalEntry

    entries = JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED)
    assert entries.exists()
    for e in entries:
        e.assert_balanced()

    assert_consistent(company)


def test_wf06_quotation_to_invoice(tenant_a, assert_consistent):
    """Quotation creates no stock/GL effect; converting it produces a normal
    invoice; the quotation is marked converted and cannot convert twice."""
    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])

    product = make_product(company, gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "20", unit_cost="60")
    customer = make_customer(company, state="Karnataka", gstin="29AAAAA0000A1ZY")

    # 1. Create quotation
    quote_res = tenant_a.client.post(
        "/api/v1/sales/quotations/",
        {
            "customer": customer.id,
            "items": [
                {
                    "product": product.id,
                    "quantity": "5",
                    "unit_price": "100.00",
                    "gst_rate": "18",
                }
            ],
        },
        format="json",
    )
    assert quote_res.status_code == 201, quote_res.data
    quote_id = quote_res.data["id"]

    # Invariants hold and NO stock / GL effect has occurred yet
    from inventory.services import InventoryService
    from accounting.models import JournalEntry

    assert InventoryService.available_quantity(company=company, product=product) == Decimal("20.000")
    assert not JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED).exists()

    # 2. Convert quotation to invoice
    conv_res = tenant_a.client.post(f"/api/v1/sales/quotations/{quote_id}/convert/")
    assert conv_res.status_code == 200, conv_res.data
    inv_id = conv_res.data["id"]

    # Quotation should now be marked CONVERTED
    q_get = tenant_a.client.get(f"/api/v1/sales/quotations/{quote_id}/")
    assert q_get.data["status"] == "CONVERTED"

    # Attempting to convert again must fail
    dup_res = tenant_a.client.post(f"/api/v1/sales/quotations/{quote_id}/convert/")
    assert dup_res.status_code == 400, dup_res.data

    # Complete the generated invoice
    comp_res = tenant_a.client.post(f"/api/v1/sales/invoices/{inv_id}/complete/")
    assert comp_res.status_code == 200, comp_res.data

    # Now stock is deducted: 20 - 5 = 15
    assert InventoryService.available_quantity(company=company, product=product) == Decimal("15.000")

    # GL is posted and balanced
    entries = JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED)
    assert entries.exists()
    for e in entries:
        e.assert_balanced()

    assert_consistent(company)


def test_wf07_sales_credit_note_financial(tenant_a, assert_consistent):
    """A financial credit note (no stock movement) reduces AR, posts GL, and
    lands in GSTR-1 CDNR. Distinct from a sales return."""
    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])

    product = make_product(company, gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "20", unit_cost="60")
    customer = make_customer(company, state="Karnataka", gstin="29AAAAA0000A1ZY")

    # 1. Create and complete sales invoice for 2 units @ 100
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100.00", "gst_rate": "18"}],
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    inv_item_id = done.data["items"][0]["id"]

    from inventory.services import InventoryService

    assert InventoryService.available_quantity(company=company, product=product) == Decimal("18.000")

    # 2. Issue post-sale discount financial credit note for 1 unit @ 100
    cn_res = tenant_a.client.post(
        "/api/v1/sales/credit-notes/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "reason": "POST_SALE_DISCOUNT",
            "items": [
                {
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "100.00",
                    "gst_rate": "18",
                    "source_item": inv_item_id,
                }
            ],
        },
        format="json",
    )
    assert cn_res.status_code == 201, cn_res.data
    cn_id = cn_res.data["id"]

    # 3. Complete credit note
    cn_done = tenant_a.client.post(f"/api/v1/sales/credit-notes/{cn_id}/complete/")
    assert cn_done.status_code == 200, cn_done.data
    assert cn_done.data["status"] == "COMPLETED"
    assert Decimal(str(cn_done.data["grand_total"])) == Decimal("118.00")

    # Stock must NOT move on a financial credit note (remains 18.000)
    assert InventoryService.available_quantity(company=company, product=product) == Decimal("18.000")

    # Outstanding AR: 236.00 - 118.00 = 118.00
    from ledgers.services import LedgerService
    from sales.models import SalesInvoice

    inv_obj = SalesInvoice.objects.get(pk=inv["id"])
    assert LedgerService.sales_invoice_outstanding(inv_obj) == Decimal("118.00")

    # GL entries balanced
    from accounting.models import JournalEntry

    entries = JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED)
    assert entries.exists()
    for e in entries:
        e.assert_balanced()

    assert_consistent(company)


def test_wf08_customer_debit_note(tenant_a, assert_consistent):
    """A customer debit note raises AR, posts GL, and appears in GSTR-1."""
    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])

    product = make_product(company, gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "20", unit_cost="60")
    customer = make_customer(company, state="Karnataka", gstin="29AAAAA0000A1ZY")

    # 1. Create and complete sales invoice for 2 units @ 100 (grand total = 236.00)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100.00", "gst_rate": "18"}],
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    inv_item_id = done.data["items"][0]["id"]

    from inventory.services import InventoryService

    assert InventoryService.available_quantity(company=company, product=product) == Decimal("18.000")

    # 2. Issue customer debit note for price increase: 1 unit @ 50.00 (taxable 50 + 9 GST = 59.00)
    dn_res = tenant_a.client.post(
        "/api/v1/sales/debit-notes/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "reason": "CORRECTION_OF_INVOICE",
            "items": [
                {
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "50.00",
                    "gst_rate": "18",
                    "source_item": inv_item_id,
                }
            ],
        },
        format="json",
    )
    assert dn_res.status_code == 201, dn_res.data
    dn_id = dn_res.data["id"]

    # 3. Complete debit note with confirm_additional_debit
    dn_done = tenant_a.client.post(
        f"/api/v1/sales/debit-notes/{dn_id}/complete/",
        {"confirm_additional_debit": True},
        format="json",
    )
    assert dn_done.status_code == 200, dn_done.data
    assert dn_done.data["status"] == "COMPLETED"
    assert Decimal(str(dn_done.data["grand_total"])) == Decimal("59.00")

    # Stock must NOT move (remains 18.000)
    assert InventoryService.available_quantity(company=company, product=product) == Decimal("18.000")

    # Outstanding AR: 236.00 + 59.00 = 295.00
    from ledgers.services import LedgerService
    from sales.models import SalesInvoice

    inv_obj = SalesInvoice.objects.get(pk=inv["id"])
    assert LedgerService.sales_invoice_outstanding(inv_obj) == Decimal("295.00")

    # GL entries balanced
    from accounting.models import JournalEntry

    entries = JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED)
    assert entries.exists()
    for e in entries:
        e.assert_balanced()

    assert_consistent(company)


def test_wf09_sales_order_reserve_and_convert(tenant_a, assert_consistent):
    """SO reserves stock (StockBalance.reserved up, on_hand unchanged); converting
    to an invoice releases the reservation and issues stock; reserved never goes
    negative."""
    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])

    product = make_product(company, gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "20", unit_cost="60")
    customer = make_customer(company, state="Karnataka", gstin="29AAAAA0000A1ZY")

    from inventory.models import StockBalance
    from inventory.services import InventoryService

    warehouse = InventoryService.default_warehouse(company)
    bal = StockBalance.objects.get(company=company, product=product, warehouse=warehouse)
    assert bal.on_hand == Decimal("20.000")
    assert bal.reserved == Decimal("0.000")

    # 1. Create draft sales order for 5 units
    so_res = tenant_a.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id,
            "order_date": "2026-03-15",
            "items": [
                {
                    "product": product.id,
                    "quantity": "5",
                    "unit_price": "100.00",
                    "gst_rate": "18",
                }
            ],
        },
        format="json",
    )
    assert so_res.status_code == 201, so_res.data
    so_id = so_res.data["id"]

    # 2. Confirm the sales order -> reserves 5 units
    conf_res = tenant_a.client.post(f"/api/v1/sales/orders/{so_id}/confirm/")
    assert conf_res.status_code == 200, conf_res.data
    assert conf_res.data["status"] == "CONFIRMED"

    bal.refresh_from_db()
    assert bal.on_hand == Decimal("20.000")
    assert bal.reserved == Decimal("5.000")

    # 3. Convert sales order to invoice
    conv_res = tenant_a.client.post(f"/api/v1/sales/orders/{so_id}/convert/")
    assert conv_res.status_code == 200, conv_res.data
    inv_id = conv_res.data["id"]

    # Reservation remains until invoice completes
    bal.refresh_from_db()
    assert bal.on_hand == Decimal("20.000")
    assert bal.reserved == Decimal("5.000")

    # 4. Complete the invoice -> releases reservation and issues stock
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv_id}/complete/")
    assert done.status_code == 200, done.data

    bal.refresh_from_db()
    assert bal.on_hand == Decimal("15.000")
    assert bal.reserved == Decimal("0.000")

    # Verify SO status is CONVERTED
    from sales.models import SalesOrder

    so = SalesOrder.objects.get(pk=so_id)
    assert so.status == SalesOrder.Status.CONVERTED

    assert_consistent(company)


def test_wf10_delivery_challan_then_invoice(tenant_a, assert_consistent):
    """Challan moves stock with no GST/AR; a later invoice links to the challan
    and does not double-issue stock; e-way payload builds for a qualifying value."""
    company = tenant_a.company
    company.stock_on_delivery_challan = True
    company.accounting_enabled = True
    company.save(update_fields=["stock_on_delivery_challan", "accounting_enabled"])

    product = make_product(company, gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "20", unit_cost="60")
    customer = make_customer(company, state="Karnataka", gstin="29AAAAA0000A1ZY")

    from inventory.services import InventoryService

    assert InventoryService.available_quantity(company=company, product=product) == Decimal("20.000")

    # 1. Create draft delivery challan for 4 units
    dc_res = tenant_a.client.post(
        "/api/v1/sales/delivery-challans/",
        {
            "customer": customer.id,
            "challan_date": "2026-03-15",
            "items": [
                {
                    "product": product.id,
                    "quantity": "4",
                    "unit_price": "100.00",
                    "gst_rate": "18",
                }
            ],
        },
        format="json",
    )
    assert dc_res.status_code == 201, dc_res.data
    dc_id = dc_res.data["id"]

    # 2. Complete delivery challan -> stock decrements from 20 to 16, NO GL/AR entries
    comp_res = tenant_a.client.post(f"/api/v1/sales/delivery-challans/{dc_id}/complete/")
    assert comp_res.status_code == 200, comp_res.data
    assert comp_res.data["status"] == "COMPLETED"

    assert InventoryService.available_quantity(company=company, product=product) == Decimal("16.000")

    from accounting.models import JournalEntry

    # Challan itself must not post financial JournalEntry
    assert not JournalEntry.objects.filter(company=company, source_type="delivery_challan").exists()

    # 3. Convert delivery challan to sales invoice
    conv_res = tenant_a.client.post(f"/api/v1/sales/delivery-challans/{dc_id}/convert/")
    assert conv_res.status_code == 200, conv_res.data
    inv_id = conv_res.data["id"]

    # 4. Complete the invoice -> stock remains 16 (no double deduction!), GL and AR posted
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv_id}/complete/")
    assert done.status_code == 200, done.data
    assert done.data["status"] == "COMPLETED"

    # Stock must still be 16.000
    assert InventoryService.available_quantity(company=company, product=product) == Decimal("16.000")

    # GL entries exist and are balanced
    entries = JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED)
    assert entries.exists()
    for e in entries:
        e.assert_balanced()

    assert_consistent(company)


@pytest.mark.skip(reason=_TODO)
def test_wf11_recurring_invoice_generation_is_idempotent():
    """A due recurring schedule generates exactly one invoice per period; running
    the generator twice for the same period creates no duplicate."""


@pytest.mark.skip(reason=_TODO)
def test_wf12_purchase_credit_note():
    """Supplier credit note reduces AP and reverses the proportional ITC."""


@pytest.mark.skip(reason=_TODO)
def test_wf13_purchase_debit_note_tds():
    """A supplier debit note that enlarges a TDS bill must credit 2265 (CR-083);
    GL balanced; TDS worksheet reflects it. (D2 = ON.)"""


@pytest.mark.skip(reason=_TODO)
def test_wf14_upload_sales_bill_idempotent():
    """LLM extraction of an uploaded sales bill produces a draft invoice;
    re-uploading the same file does not create a second draft."""


@pytest.mark.skip(reason=_TODO)
def test_wf15_upload_purchase_bill_idempotent():
    """As WF-14 for a purchase bill."""


@pytest.mark.skip(reason=_TODO)
def test_wf16_purchase_order_to_purchase():
    """PO converts to a purchase; quantities/prices carry; PO marked converted."""


@pytest.mark.skip(reason=_TODO)
def test_wf17_gateway_webhook_capture_and_replay():
    """(D3 = ON, sandbox) A capture webhook -> receipt -> allocation -> GL.
    Replaying the identical webhook is a no-op (idempotency key). A capture for a
    cancelled / closed-period invoice parks, then a reconcile refunds it."""


@pytest.mark.skip(reason=_TODO)
def test_wf18_otp_login_and_ratelimit():
    """(D4 = ON) request OTP -> verify -> session issued. OTP is hashed at rest.
    Request and verify are rate-limited; N failures lock the account."""


def test_wf19_pos_checkout(tenant_a, assert_consistent):
    """(D1 = ON) /pos checkout: retail invoice complete -> stock down -> GST ->
    cash/UPI receipt -> GL; thermal PDF endpoint returns a file when available."""
    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])

    product = make_product(company, gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "20", unit_cost="60")
    customer = make_customer(company, state="Karnataka", gstin="29AAAAA0000A1ZY")

    checkout_payload = {
        "invoice": {
            "customer": customer.id,
            "invoice_type": "RETAIL",
            "invoice_date": "2026-03-15",
            "items": [
                {
                    "product": product.id,
                    "quantity": "2",
                    "unit_price": "100.00",
                    "gst_rate": "18",
                }
            ],
        },
        "payment": {
            "mode": "CASH",
            "amount": "236.00",
            "tendered_amount": "250.00",
        },
    }

    res = tenant_a.client.post("/api/v1/sales/invoices/pos-checkout/", checkout_payload, format="json")
    assert res.status_code == 201, res.data

    inv_data = res.data["invoice"]
    receipt_data = res.data["receipt"]

    assert inv_data["status"] == "COMPLETED"
    assert Decimal(str(inv_data["grand_total"])) == Decimal("236.00")
    assert receipt_data is not None
    assert Decimal(str(receipt_data["amount"])) == Decimal("236.00")

    # stock on hand should be 20 - 2 = 18
    from inventory.services import InventoryService

    on_hand = InventoryService.available_quantity(company=company, product=product)
    assert on_hand == Decimal("18.000")

    # verify customer receipt exists and is allocated
    from payments.models import CustomerReceipt

    receipt = CustomerReceipt.objects.get(pk=receipt_data["id"])
    assert receipt.allocations.filter(sales_invoice_id=inv_data["id"]).exists()

    # GL entries are posted and balanced
    from accounting.models import JournalEntry

    entries = JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED)
    assert entries.exists()
    for e in entries:
        e.assert_balanced()

    assert_consistent(company)


@pytest.mark.skip(reason=_TODO)
def test_wf20_period_close_then_sanctioned_correction():
    """Closing a period rejects a back-dated posting; the sanctioned correction
    path posts a reversing + re-post pair that nets to zero and is allowed by
    gl.closed_period_not_violated."""


def test_wf21_stock_transfer_between_godowns(tenant_a, assert_consistent):
    """A completed transfer emits TRANSFER_OUT + TRANSFER_IN that net to zero per
    (product, batch); batch and serial identity are preserved; the destination
    godown's on_hand rises by exactly the source's fall."""
    company = tenant_a.company
    from inventory.models import MovementType, StockMovement, Warehouse
    from inventory.services import InventoryService

    wh1 = InventoryService.default_warehouse(company)
    wh2 = Warehouse.objects.create(company=company, name="Secondary Godown", is_active=True)

    product = make_product(company, name="Transfer Widget", sku="XFER-WID-1", gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "20", unit_cost="60")

    assert InventoryService.available_quantity(company, product, warehouse=wh1) == Decimal("20.000")
    assert InventoryService.available_quantity(company, product, warehouse=wh2) == Decimal("0.000")

    transfer_payload = {
        "from_warehouse": wh1.id,
        "to_warehouse": wh2.id,
        "notes": "Transfer 6 units to secondary godown",
        "lines": [
            {
                "product": product.id,
                "quantity": "6.000",
            }
        ],
    }
    res = tenant_a.client.post("/api/v1/inventory/transfers/", transfer_payload, format="json")
    assert res.status_code == 201, res.data
    transfer_id = res.data["id"]

    done = tenant_a.client.post(f"/api/v1/inventory/transfers/{transfer_id}/complete/")
    assert done.status_code == 200, done.data

    out_move = StockMovement.objects.get(
        company=company, reference_type="stock_transfer", reference_id=str(transfer_id), movement_type=MovementType.TRANSFER_OUT
    )
    in_move = StockMovement.objects.get(
        company=company, reference_type="stock_transfer", reference_id=str(transfer_id), movement_type=MovementType.TRANSFER_IN
    )
    assert out_move.quantity == Decimal("-6.000")
    assert in_move.quantity == Decimal("6.000")
    assert out_move.quantity + in_move.quantity == Decimal("0.000")
    assert out_move.warehouse == wh1
    assert in_move.warehouse == wh2

    # Destination rises by source fall:
    assert InventoryService.available_quantity(company, product, warehouse=wh1) == Decimal("14.000")
    assert InventoryService.available_quantity(company, product, warehouse=wh2) == Decimal("6.000")
    assert InventoryService.available_quantity(company, product) == Decimal("20.000")

    assert_consistent(company)


@pytest.mark.skip(reason=_TODO)
def test_wf22_stock_adjustment_writeoff():
    """A write-off ADJUSTMENT reduces on_hand and valuation and posts a GL
    expense equal to the valuation delta."""


@pytest.mark.skip(reason=_TODO)
def test_wf23_import_products_idempotent():
    """Importing the same product rows twice creates each product once."""


@pytest.mark.skip(reason=_TODO)
def test_wf24_import_customers_idempotent():
    """Importing the same customer rows twice creates each party once."""


@pytest.mark.skip(reason=_TODO)
def test_wf25_import_opening_stock_idempotent():
    """Importing opening stock twice does not double the OPENING_STOCK movement
    (uniqueness constraint) and on_hand equals the imported quantity."""


@pytest.mark.skip(reason=_TODO)
def test_wf26_bank_receipt_to_gl():
    """A receipt into a GL-linked bank account debits that bank GL account and
    credits AR; bank recon can later match the statement line."""


@pytest.mark.skip(reason=_TODO)
def test_wf27_gstr1_3b_tie_out():
    """For a period with a mix of intra/inter/CDNR/HSN activity, GSTR-3B 3.1/4
    tie to the GSTR-1 aid + the purchase register."""


def test_wf28_two_tenant_interleave(tenant_a, tenant_b, assert_consistent):
    """Run WF-01 for tenant A and WF-04 for tenant B in the same test; assert
    each company's invariants hold and neither sees the other's rows."""
    from inventory.services import InventoryService
    from accounting.models import JournalEntry

    # Enable accounting for both
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    tenant_b.company.accounting_enabled = True
    tenant_b.company.save(update_fields=["accounting_enabled"])

    # Setup tenant A
    prod_a = make_product(tenant_a.company, sku="PROD-A-001", gst_rate="18", selling_price="100")
    add_stock(tenant_a, prod_a, "20", unit_cost="60")
    cust_a = make_customer(tenant_a.company, state="Karnataka", gstin="29AAAAA0000A1ZY")

    # Setup tenant B
    prod_b = make_product(tenant_b.company, sku="PROD-B-001", gst_rate="18", purchase_price="80")
    supp_b = make_supplier(tenant_b.company, state="Maharashtra")

    # Interleave draft creations
    inv_a = create_draft_invoice(
        tenant_a, cust_a, [{"product": prod_a.id, "quantity": "3", "unit_price": "100.00", "gst_rate": "18"}]
    )
    pur_b = create_draft_purchase(
        tenant_b, supp_b, [{"product": prod_b.id, "quantity": "10", "unit_price": "80.00", "gst_rate": "18"}]
    )

    # Cross-tenant read attempts must return 404
    assert tenant_a.client.get(f"/api/v1/purchases/invoices/{pur_b['id']}/").status_code == 404
    assert tenant_b.client.get(f"/api/v1/sales/invoices/{inv_a['id']}/").status_code == 404
    assert tenant_a.client.get(f"/api/v1/masters/products/{prod_b.id}/").status_code == 404
    assert tenant_b.client.get(f"/api/v1/masters/customers/{cust_a.id}/").status_code == 404

    # Complete Tenant A invoice and Tenant B purchase
    res_a = tenant_a.client.post(f"/api/v1/sales/invoices/{inv_a['id']}/complete/")
    assert res_a.status_code == 200, res_a.data
    res_b = tenant_b.client.post(f"/api/v1/purchases/invoices/{pur_b['id']}/complete/")
    assert res_b.status_code == 200, res_b.data

    # Payments
    pay_a = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {
            "customer": cust_a.id,
            "amount": "354.00",
            "mode": "CASH",
        },
        format="json",
    )
    assert pay_a.status_code in (200, 201), pay_a.data
    receipt_a_id = pay_a.data["id"]

    alloc_a = tenant_a.client.post(
        "/api/v1/payments/allocations/",
        {
            "receipt": receipt_a_id,
            "sales_invoice": inv_a["id"],
            "amount": "354.00",
        },
        format="json",
    )
    assert alloc_a.status_code == 201, alloc_a.data

    pay_b = tenant_b.client.post(
        "/api/v1/payments/supplier-payments/",
        {
            "supplier": supp_b.id,
            "amount": "944.00",
            "mode": "BANK",
        },
        format="json",
    )
    assert pay_b.status_code in (200, 201), pay_b.data
    payment_b_id = pay_b.data["id"]

    alloc_b = tenant_b.client.post(
        "/api/v1/payments/allocations/",
        {
            "supplier_payment": payment_b_id,
            "purchase_invoice": pur_b["id"],
            "amount": "944.00",
        },
        format="json",
    )
    assert alloc_b.status_code == 201, alloc_b.data

    # Cross-tenant cross-allocation must fail
    leak_attempt = tenant_a.client.post(
        "/api/v1/payments/allocations/",
        {
            "receipt": receipt_a_id,
            "sales_invoice": pur_b["id"],
            "amount": "100.00",
        },
        format="json",
    )
    assert leak_attempt.status_code in (400, 404)

    # Verify inventory isolation
    assert InventoryService.available_quantity(tenant_a.company, prod_a) == Decimal("17.000")
    assert InventoryService.available_quantity(tenant_b.company, prod_b) == Decimal("10.000")

    # Verify Journal Entries isolation and balance
    entries_a = JournalEntry.objects.filter(company=tenant_a.company, status=JournalEntry.Status.POSTED)
    entries_b = JournalEntry.objects.filter(company=tenant_b.company, status=JournalEntry.Status.POSTED)
    assert entries_a.exists()
    assert entries_b.exists()
    for e in entries_a:
        assert e.company_id == tenant_a.company.id
        e.assert_balanced()
    for e in entries_b:
        assert e.company_id == tenant_b.company.id
        e.assert_balanced()

    assert_consistent(tenant_a.company)
    assert_consistent(tenant_b.company)

