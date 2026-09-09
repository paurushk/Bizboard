"""Regression tests for the 2026-09 functional review findings (CR-001..CR-004).

See ``FUNCTIONAL_CODE_REVIEW_2026-09-08_CLAUDE.md`` at the repo root.
"""

from decimal import Decimal

import pytest

from core.exceptions import BusinessRuleError
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def _complete_purchase(tenant, supplier, product, qty="10", unit_price="80"):
    pur = create_draft_purchase(tenant, supplier, [
        {"product": product.id, "quantity": qty, "unit_price": unit_price},
    ])
    resp = tenant.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/")
    assert resp.status_code == 200, resp.data
    return pur


def _complete_sale(tenant, customer, product, qty="6", unit_price="100"):
    inv = create_draft_invoice(tenant, customer, [
        {"product": product.id, "quantity": qty, "unit_price": unit_price},
    ])
    resp = tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert resp.status_code == 200, resp.data
    return inv


# --------------------------------------------------------------------------- #
# CR-001 — completed purchase quantities are immutable via set_items          #
# --------------------------------------------------------------------------- #

def test_cr001_completed_purchase_qty_amend_rejected_at_service_level(tenant_a):
    """PurchaseService.set_items must refuse a quantity change on a COMPLETED
    invoice (twin of SalesService.set_items CR-024/CR-128). The former qty-delta
    branch posted a `purchase_invoice_edit` ADJUSTMENT that cancel() never
    reversed, leaving the bill un-cancellable and stock/FIFO drifted."""
    from purchases.models import PurchaseInvoice
    from purchases.services import PurchaseService

    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    pur = _complete_purchase(tenant_a, supplier, product, qty="10")
    inv = PurchaseInvoice.objects.get(pk=pur["id"])

    with pytest.raises(BusinessRuleError, match="[Cc]annot amend quantity"):
        PurchaseService.set_items(
            inv,
            [{"product": product, "quantity": Decimal("6"), "unit_price": Decimal("80")}],
            tenant_a.owner,
        )

    # A price-only amend on the same completed invoice is still allowed.
    PurchaseService.set_items(
        inv,
        [{"product": product, "quantity": Decimal("10"), "unit_price": Decimal("70")}],
        tenant_a.owner,
    )
    inv.refresh_from_db()
    assert inv.items.first().unit_price == Decimal("70.00")

    # And the bill remains cancellable, netting stock back to zero.
    resp = tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/cancel/")
    assert resp.status_code == 200, resp.data
    from inventory.models import StockBalance

    assert StockBalance.objects.get(product=product).on_hand == Decimal("0")


def test_cr001_completed_purchase_qty_amend_rejected_via_api(tenant_a):
    """The REST amend path (H9-A allowlist) also rejects the qty change."""
    product = make_product(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    pur = _complete_purchase(tenant_a, supplier, product, qty="10")

    resp = tenant_a.client.patch(
        f"/api/v1/purchases/invoices/{pur['id']}/",
        {
            "confirm_amend": True,
            "items": [{"product": product.id, "quantity": "6", "unit_price": "80"}],
        },
        format="json",
    )
    assert resp.status_code == 400, resp.data


# --------------------------------------------------------------------------- #
# CR-002 — purchase-cancel headroom guard honours negative_stock_policy       #
# --------------------------------------------------------------------------- #

def test_cr002_warn_policy_allows_cancel_of_partly_consumed_purchase(tenant_a):
    """Under negative_stock_policy=WARN a completed purchase whose stock has
    since been sold can still be cancelled (the old guard keyed on a
    non-existent Company.allow_negative_stock and blocked it unconditionally)."""
    company = tenant_a.company
    company.negative_stock_policy = "WARN"
    company.save(update_fields=["negative_stock_policy"])

    product = make_product(company)
    supplier = make_supplier(company)
    customer = make_customer(company)

    pur = _complete_purchase(tenant_a, supplier, product, qty="10")
    _complete_sale(tenant_a, customer, product, qty="6")

    resp = tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/cancel/")
    assert resp.status_code == 200, resp.data

    from purchases.models import PurchaseInvoice

    assert PurchaseInvoice.objects.get(pk=pur["id"]).status == "CANCELLED"


def test_cr002_block_policy_still_blocks_cancel_of_partly_consumed_purchase(tenant_a):
    """Under the default BLOCK policy the guard is unchanged: a purchase whose
    goods have moved cannot be cancelled (reversal would drive stock negative)."""
    company = tenant_a.company
    assert company.negative_stock_policy == "BLOCK"

    product = make_product(company)
    supplier = make_supplier(company)
    customer = make_customer(company)

    pur = _complete_purchase(tenant_a, supplier, product, qty="10")
    _complete_sale(tenant_a, customer, product, qty="6")

    resp = tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/cancel/")
    assert resp.status_code == 400
    assert "less than the purchase quantity" in str(resp.data)


# --------------------------------------------------------------------------- #
# CR-003 — POS overpayment is change, not a silent unallocated advance        #
# --------------------------------------------------------------------------- #

def test_cr003_pos_overpayment_books_receipt_equal_to_invoice_total(tenant_a):
    company = tenant_a.company
    product = make_product(company, gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "20", unit_cost="60")
    customer = make_customer(company, state="Karnataka")

    payload = {
        "invoice": {
            "customer": customer.id,
            "invoice_type": "RETAIL",
            "items": [
                {"product": product.id, "quantity": "2", "unit_price": "100.00", "gst_rate": "18"}
            ],
        },
        # Operator keys ₹300 against a ₹236 bill (over-tender / fat finger).
        "payment": {"mode": "CASH", "amount": "300.00", "tendered_amount": "300.00"},
    }
    res = tenant_a.client.post("/api/v1/sales/invoices/pos-checkout/", payload, format="json")
    assert res.status_code == 201, res.data

    grand_total = Decimal(str(res.data["invoice"]["grand_total"]))
    assert grand_total == Decimal("236.00")

    from payments.models import CustomerReceipt

    receipt = CustomerReceipt.objects.get(pk=res.data["receipt"]["id"])
    # Receipt is capped at the invoice total — the ₹64 excess is change, not an advance.
    assert receipt.amount == grand_total

    from ledgers.services import LedgerService

    assert LedgerService.customer_unallocated_receipts(company, customer) == Decimal("0")
    assert "Change" in (receipt.notes or "")


def test_cr003_pos_partial_payment_still_allowed(tenant_a):
    """A smaller `amount` is a legitimate part-payment and is preserved."""
    company = tenant_a.company
    product = make_product(company, gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "20", unit_cost="60")
    customer = make_customer(company, state="Karnataka")

    payload = {
        "invoice": {
            "customer": customer.id,
            "invoice_type": "RETAIL",
            "items": [
                {"product": product.id, "quantity": "2", "unit_price": "100.00", "gst_rate": "18"}
            ],
        },
        "payment": {"mode": "CASH", "amount": "100.00"},
    }
    res = tenant_a.client.post("/api/v1/sales/invoices/pos-checkout/", payload, format="json")
    assert res.status_code == 201, res.data

    from payments.models import CustomerReceipt

    receipt = CustomerReceipt.objects.get(pk=res.data["receipt"]["id"])
    assert receipt.amount == Decimal("100.00")


# --------------------------------------------------------------------------- #
# CR-004 — a deterministic 4xx on complete is STORED against the key (by       #
# design, W0-05). Reviewed and left as-is: the key must be rotated to retry    #
# after the condition clears; the offline POS flush already does exactly that  #
# (flushPosCheckout.ts probes status then rotates `<key>-complete`).           #
# --------------------------------------------------------------------------- #

def test_cr004_deterministic_4xx_on_complete_is_stored_and_needs_a_fresh_key(tenant_a):
    company = tenant_a.company
    assert company.negative_stock_policy == "BLOCK"

    product = make_product(company)
    add_stock(tenant_a, product, "2", unit_cost="80")
    customer = make_customer(company)

    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "5", "unit_price": "100"},
    ])
    stale_key = "cr004-complete-key"

    r1 = tenant_a.client.post(
        f"/api/v1/sales/invoices/{inv['id']}/complete/",
        HTTP_IDEMPOTENCY_KEY=stale_key,
    )
    assert r1.status_code == 400
    assert "insufficient_stock" in str(r1.data).lower()

    # Restock (OPENING_STOCK is one-shot per product, so top up via ADJUSTMENT).
    from inventory.models import MovementType
    from inventory.services import InventoryService

    InventoryService.post_movement(
        company=company, product=product,
        movement_type=MovementType.ADJUSTMENT, quantity=Decimal("10"),
        unit_cost=Decimal("80"), reason="restock", user=tenant_a.owner,
    )

    # W0-05: the stale key replays the stored 400 even though stock is now available.
    r2 = tenant_a.client.post(
        f"/api/v1/sales/invoices/{inv['id']}/complete/",
        HTTP_IDEMPOTENCY_KEY=stale_key,
    )
    assert r2.status_code == 400

    # A fresh key re-executes and succeeds — this is the required retry contract.
    r3 = tenant_a.client.post(
        f"/api/v1/sales/invoices/{inv['id']}/complete/",
        HTTP_IDEMPOTENCY_KEY="cr004-complete-key-rotated",
    )
    assert r3.status_code == 200, r3.data
    assert r3.data["status"] == "COMPLETED"
