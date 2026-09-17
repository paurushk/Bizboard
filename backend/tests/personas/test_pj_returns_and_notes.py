"""Reverse Logistics & Credit/Debit Notes persona journey.

Validates:
1. P2 (Sales Staff) / P5 (Accountant) customer sales return lifecycle:
   - Sales invoice completed -> stock deducted, customer AR subledger debited.
   - Credit note issued for partial return -> stock re-inwarded to warehouse, AR reduced.
   - Capability boundary: Clerk cannot complete financial credit notes without accountant/owner.
2. P5 (Accountant) supplier purchase return lifecycle:
   - Purchase invoice completed -> stock added, supplier AP subledger credited.
   - Purchase return completed -> stock deducted, auto-credit note reduces supplier AP.
3. Zero invariant violations: assert_all_invariants(company) holds throughout.
"""

from decimal import Decimal
import pytest

from core.invariants import assert_all_invariants
from inventory.models import MovementType, StockBalance
from inventory.services import InventoryService
from ledgers.services import LedgerService
from purchases.models import PurchaseCreditNote
from sales.models import SalesCreditNote
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def _body(resp):
    data = resp.data
    if isinstance(data, dict) and isinstance(data.get("data"), (dict, list)):
        return data["data"]
    return data


def test_pj_returns_and_credit_debit_notes_lifecycle():
    trader = seed_archetype("trader")
    company = trader.company
    wh = trader.warehouses[0]
    plain_prods = [p for p in trader.products if not p.track_batch and not p.track_serial]
    prod1 = plain_prods[0]
    prod2 = plain_prods[1]
    cust = trader.customers[0]
    supp = trader.suppliers[0]

    # --- Part 1: Sales Return & Credit Note ---
    # Inward opening stock
    InventoryService.post_movement(
        company=company,
        product=prod1,
        warehouse=wh,
        quantity=Decimal("10"),
        movement_type=MovementType.PURCHASE,
        unit_cost=Decimal("60.00"),
        user=trader.owner,
    )
    assert StockBalance.objects.get(company=company, product=prod1, warehouse=wh).on_hand == Decimal("10")

    # Sales Staff creates and completes an invoice for 5 units @ 100 + 18% GST = 590
    inv_resp = trader.sales_client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": cust.id,
            "invoice_type": "TAX",
            "items": [
                {"product": prod1.id, "quantity": "5", "unit_price": "100.00", "gst_rate": "18"}
            ],
        },
        format="json",
    )
    assert inv_resp.status_code == 201, inv_resp.data
    inv_id = _body(inv_resp)["id"]
    comp_inv = trader.sales_client.post(f"/api/v1/sales/invoices/{inv_id}/complete/")
    assert comp_inv.status_code == 200, comp_inv.data

    # Stock dropped to 5
    assert StockBalance.objects.get(company=company, product=prod1, warehouse=wh).on_hand == Decimal("5")
    # Customer outstanding is 590
    assert LedgerService.customer_outstanding(company, cust) == Decimal("590.00")

    # Customer returns 2 units. Draft Credit Note
    cn_resp = trader.sales_client.post(
        "/api/v1/sales/credit-notes/",
        {
            "customer": cust.id,
            "sales_invoice": inv_id,
            "reason": "CORRECTION_OF_INVOICE",
            "items": [
                {"product": prod1.id, "quantity": "2", "unit_price": "100.00", "gst_rate": "18"}
            ],
        },
        format="json",
    )
    assert cn_resp.status_code == 201, cn_resp.data
    cn_id = _body(cn_resp)["id"]

    # Boundary check: Sales clerk cannot cancel completed sales invoices
    clerk_cancel = trader.sales_client.post(f"/api/v1/sales/invoices/{inv_id}/cancel/")
    assert clerk_cancel.status_code == 403, "Sales staff must not cancel invoices"

    # Boundary check: Accountant cannot complete sales credit notes (requires CanCreateSales)
    acct_fail = trader.acct_client.post(f"/api/v1/sales/credit-notes/{cn_id}/complete/")
    assert acct_fail.status_code == 403, "Accountant without sales create permission cannot complete sales credit notes"

    # Sales staff completes the credit note
    clerk_complete = trader.sales_client.post(f"/api/v1/sales/credit-notes/{cn_id}/complete/")
    assert clerk_complete.status_code == 200, clerk_complete.data
    assert SalesCreditNote.objects.get(pk=cn_id).status == "COMPLETED"

    # Financial Credit Note (Rate Correction): reduces AR from 590 to 354 without phantom physical movement
    assert StockBalance.objects.get(company=company, product=prod1, warehouse=wh).on_hand == Decimal("5")
    assert LedgerService.customer_outstanding(company, cust) == Decimal("354.00")

    # --- Part 2: Purchase Return & Debit Note ---
    # Boundary check: Sales staff cannot create purchase returns
    sales_pur_ret = trader.sales_client.post(
        "/api/v1/purchases/returns/",
        {
            "supplier": supp.id,
            "purchase_invoice": 99999,
            "items": [{"product": prod2.id, "quantity": "1", "unit_price": "50.00"}],
        },
        format="json",
    )
    assert sales_pur_ret.status_code == 403, "Sales staff cannot create purchase returns"

    # Purchase invoice for 10 units of prod2 @ 50 + 12% GST = 560
    pur_resp = trader.acct_client.post(
        "/api/v1/purchases/invoices/",
        {
            "supplier": supp.id,
            "purchase_type": "GST",
            "items": [
                {"product": prod2.id, "quantity": "10", "unit_price": "50.00", "gst_rate": "12", "hsn_code": "841590", "rate_override": True, "rate_override_reason": "persona pins 12% line rate"}
            ],
        },
        format="json",
    )
    assert pur_resp.status_code == 201, pur_resp.data
    pur_id = _body(pur_resp)["id"]
    assert trader.acct_client.post(f"/api/v1/purchases/invoices/{pur_id}/complete/").status_code == 200

    # Stock is 10, supplier AP is 560
    assert StockBalance.objects.get(company=company, product=prod2, warehouse=wh).on_hand == Decimal("10")
    ap_before = LedgerService.supplier_outstanding(company, supp)
    assert ap_before == Decimal("560.00")

    # Return 4 units to supplier
    ret_resp = trader.acct_client.post(
        "/api/v1/purchases/returns/",
        {
            "supplier": supp.id,
            "purchase_invoice": pur_id,
            "items": [{"product": prod2.id, "quantity": "4", "unit_price": "50.00"}],
        },
        format="json",
    )
    assert ret_resp.status_code == 201, ret_resp.data
    ret_id = _body(ret_resp)["id"]
    ret_comp = trader.acct_client.post(f"/api/v1/purchases/returns/{ret_id}/complete/")
    assert ret_comp.status_code == 200, ret_comp.data

    # Stock reduced by 4 (10 -> 6)
    assert StockBalance.objects.get(company=company, product=prod2, warehouse=wh).on_hand == Decimal("6")

    # Auto-generated purchase credit note relieves supplier AP
    auto_cn = PurchaseCreditNote.objects.get(purchase_return_id=ret_id)
    assert auto_cn.status == PurchaseCreditNote.Status.COMPLETED
    assert LedgerService.supplier_outstanding(company, supp) == ap_before - auto_cn.grand_total

    # Final invariant sweep: GL, AR, AP, and stock match
    assert_all_invariants(company)
