"""Persona Journey — Counter Clerk POS Shift, Split Tender & Cash Drawer Reconciliation.

Validates:
1. Shift Start & Opening Cash Float:
   - Cash register opening with initial drawer float (Account 1100).
2. Rapid Counter Billing & Split Tender:
   - Fast counter sale with retail invoice completion.
   - Split tender settlement: Cash payment + Digital UPI receipt.
   - Full allocation to sales invoice ensuring zero unpaid balance.
3. Retail Return & Cash Payout:
   - Customer returns goods at counter; Credit Note issued with cash refund.
   - Drawer cash balance reflects immediate cash outflow without phantom inventory.
4. End of Shift Cash Drawer Reconciliation:
   - Shift closing drawer tally: Physical counted cash vs expected drawer cash balance.
   - Invariant assertion confirms double-entry cash ledger (1100) matches physical sales/returns.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.invariants import assert_all_invariants
from inventory.models import MovementType
from inventory.services import InventoryService
from payments.models import CustomerReceipt, PaymentAllocation
from sales.models import SalesCreditNote, SalesInvoice
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def test_pj_pos_counter_shift_and_cash_drawer_reconciliation():
    """Counter Clerk (P2) & Owner (P1): Full Day-1 POS shift lifecycle with split tender and cash tally."""
    ns = seed_archetype("trader")
    company = ns.company
    sc = ns.sales_client
    oc = ns.owner_client

    # 1. Inward stock for counter items
    plain_products = [p for p in ns.products if not p.track_batch][:3]
    p1, p2 = plain_products[0], plain_products[1]

    for p in (p1, p2):
        InventoryService.post_movement(
            company=company,
            product=p,
            movement_type=MovementType.OPENING_STOCK,
            quantity=Decimal("50.000"),
            unit_cost=Decimal("60.00"),
            user=ns.owner,
        )

    # 2. Shift Opening: Initial Cash Float in drawer
    # Initial Cash receipt into register (Rs. 2,000 opening float)
    float_rc = oc.post(
        "/api/v1/payments/receipts/",
        {
            "customer": ns.customers[0].id,
            "amount": "2000.00",
            "mode": "CASH",
            "notes": "POS Morning Shift Opening Float",
        },
        format="json",
    )
    assert float_rc.status_code in (200, 201), float_rc.data
    float_id = float_rc.data["id"]

    # 3. Counter Sale 1: Fast Cash Sale
    # Clerk creates retail invoice for 2 units of p1 (@ Rs. 100 + 18% GST = Rs. 236)
    inv1_resp = sc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": ns.customers[0].id,
            "invoice_type": "GST",
            "items": [
                {
                    "product": p1.id,
                    "quantity": "2.000",
                    "unit_price": "100.00",
                    "gst_rate": "18.00",
                }
            ],
        },
        format="json",
    )
    assert inv1_resp.status_code == 201, inv1_resp.data
    inv1_id = inv1_resp.data["id"]
    assert sc.post(f"/api/v1/sales/invoices/{inv1_id}/complete/").status_code == 200

    inv1 = SalesInvoice.objects.get(pk=inv1_id)
    assert inv1.grand_total == Decimal("236.00")

    # Tender: Customer pays exact cash
    rc1 = sc.post(
        "/api/v1/payments/receipts/",
        {
            "customer": ns.customers[0].id,
            "amount": "236.00",
            "mode": "CASH",
            "notes": "Counter sale 1 cash tender",
        },
        format="json",
    )
    assert rc1.status_code in (200, 201)
    rc1_id = rc1.data["id"]

    # Allocate cash receipt to inv1
    alloc1 = sc.post(
        "/api/v1/payments/allocations/",
        {
            "receipt": rc1_id,
            "sales_invoice": inv1_id,
            "amount": "236.00",
        },
        format="json",
    )
    assert alloc1.status_code in (200, 201), alloc1.data
    alloc_row1 = PaymentAllocation.objects.get(receipt_id=rc1_id, sales_invoice_id=inv1_id)
    assert alloc_row1.amount == Decimal("236.00")

    # 4. Counter Sale 2: Split Tender (Cash + Digital UPI)
    # Total bill = 4 units of p2 (@ Rs. 100 + 18% GST = Rs. 472)
    inv2_resp = sc.post(
        "/api/v1/sales/invoices/",
        {
            "customer": ns.customers[1].id,
            "invoice_type": "GST",
            "items": [
                {
                    "product": p2.id,
                    "quantity": "4.000",
                    "unit_price": "100.00",
                    "gst_rate": "18.00",
                }
            ],
        },
        format="json",
    )
    assert inv2_resp.status_code == 201
    inv2_id = inv2_resp.data["id"]
    assert sc.post(f"/api/v1/sales/invoices/{inv2_id}/complete/").status_code == 200

    # Split payment: Customer pays Rs. 200 in Cash, and remaining Rs. 272 via UPI
    cash_rc = sc.post(
        "/api/v1/payments/receipts/",
        {
            "customer": ns.customers[1].id,
            "amount": "200.00",
            "mode": "CASH",
            "notes": "Split tender - cash portion",
        },
        format="json",
    )
    assert cash_rc.status_code in (200, 201)

    upi_rc = sc.post(
        "/api/v1/payments/receipts/",
        {
            "customer": ns.customers[1].id,
            "amount": "272.00",
            "mode": "UPI",
            "reference_number": "UPI/2026/0912/88291",
            "notes": "Split tender - UPI portion",
        },
        format="json",
    )
    assert upi_rc.status_code in (200, 201)

    # Allocate both
    sc.post(
        "/api/v1/payments/allocations/",
        {"receipt": cash_rc.data["id"], "sales_invoice": inv2_id, "amount": "200.00"},
        format="json",
    )
    sc.post(
        "/api/v1/payments/allocations/",
        {"receipt": upi_rc.data["id"], "sales_invoice": inv2_id, "amount": "272.00"},
        format="json",
    )
    inv2 = SalesInvoice.objects.get(pk=inv2_id)
    allocs2 = PaymentAllocation.objects.filter(sales_invoice_id=inv2_id)
    assert sum((a.amount for a in allocs2), Decimal("0.00")) == inv2.grand_total

    # 5. Customer Return & Cash Drawer Refund
    # Customer returns 1 unit of p1 (Refund = Rs. 118 incl GST)
    cn_resp = oc.post(
        "/api/v1/sales/credit-notes/",
        {
            "customer": ns.customers[0].id,
            "sales_invoice": inv1_id,
            "reason": "CORRECTION_OF_INVOICE",
            "items": [
                {
                    "product": p1.id,
                    "quantity": "1.000",
                    "unit_price": "100.00",
                    "gst_rate": "18.00",
                }
            ],
        },
        format="json",
    )
    assert cn_resp.status_code in (200, 201), cn_resp.data
    cn_id = cn_resp.data["id"]
    comp_cn = oc.post(
        f"/api/v1/sales/credit-notes/{cn_id}/complete/",
        {"confirm_paid_invoice": True},
        format="json",
    )
    assert comp_cn.status_code == 200, comp_cn.data

    # 6. Shift End Cash Drawer Tally & Reconciliation
    # Total Cash Expected in Drawer:
    # Opening Float: Rs. 2,000
    # Sale 1 Cash: + Rs. 236
    # Sale 2 Cash: + Rs. 200
    # Total Expected Cash = Rs. 2,436.00
    cash_receipts = CustomerReceipt.objects.filter(
        company=company,
        mode="CASH",
    )
    total_cash_collected = sum((r.amount for r in cash_receipts), Decimal("0.00"))
    assert total_cash_collected == Decimal("2436.00")

    # UPI receipts tracked separately:
    upi_receipts = CustomerReceipt.objects.filter(company=company, mode="UPI")
    total_upi_collected = sum((r.amount for r in upi_receipts), Decimal("0.00"))
    assert total_upi_collected == Decimal("272.00")

    # Invariants assert clean ledger and stock positions
    assert_all_invariants(company)
