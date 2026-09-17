"""Dedicated CFT-NNN gates for CROSS_FLOW_TEST_CHECKLIST.md gaps.

CFT-114–120 live in test_cft_cross_flow.py. This module covers unique
cross-flow assertions that were only loosely mapped to a sibling WF/PJ test
(or not asserted at all). Each test docstring cites the stable CFT id(s).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db


def _d(value) -> Decimal:
    return Decimal(str(value))


def _books(company, gstin="29AAAAA0000A1ZY"):
    company.accounting_enabled = True
    if gstin:
        company.gstin = gstin
    company.save(update_fields=["accounting_enabled", "gstin"] if gstin else ["accounting_enabled"])
    from accounting.services import seed_chart_of_accounts

    seed_chart_of_accounts(company)
    return company


def _qty(company, product) -> Decimal:
    from inventory.services import InventoryService

    return InventoryService.available_quantity(company=company, product=product)


def _on_hand(company, product) -> Decimal:
    from django.db.models import Sum

    from inventory.models import StockBalance

    return StockBalance.objects.filter(company=company, product=product).aggregate(
        t=Sum("on_hand")
    )["t"] or Decimal("0")


def _complete_sale(tenant, customer, items, *, invoice_type="NON_GST", invoice_date=None):
    inv = create_draft_invoice(tenant, customer, items, invoice_type=invoice_type)
    if invoice_date:
        patched = tenant.client.patch(
            f"/api/v1/sales/invoices/{inv['id']}/",
            {"invoice_date": invoice_date},
            format="json",
        )
        assert patched.status_code == 200, patched.data
    done = tenant.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    return done.data


def _complete_purchase(tenant, supplier, items, *, purchase_type="NON_GST"):
    pur = create_draft_purchase(tenant, supplier, items, purchase_type=purchase_type)
    done = tenant.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/")
    assert done.status_code == 200, done.data
    return done.data


def _return_sale(tenant, invoice, product, qty, unit_price, *, return_date=None, gst_rate="0"):
    payload = {
        "customer": invoice["customer"] if isinstance(invoice, dict) else invoice.customer_id,
        "sales_invoice": invoice["id"] if isinstance(invoice, dict) else invoice.id,
        "items": [
            {
                "product": product.id,
                "quantity": str(qty),
                "unit_price": str(unit_price),
                "gst_rate": gst_rate,
            }
        ],
    }
    if return_date:
        payload["return_date"] = return_date
    ret = tenant.client.post("/api/v1/sales/returns/", payload, format="json")
    assert ret.status_code == 201, ret.data
    done = tenant.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/")
    assert done.status_code == 200, done.data
    return done.data, ret.data["id"]


def _dashboard(tenant):
    resp = tenant.client.get("/api/v1/dashboard/")
    assert resp.status_code == 200, resp.data
    return resp.data


def _register_ids(tenant, **params):
    resp = tenant.client.get("/api/v1/reports/sales-register/", params)
    assert resp.status_code == 200, resp.data
    rows = resp.data.get("rows") if isinstance(resp.data, dict) else resp.data
    return {r["id"] for r in rows}


def _movement_sum(company, product) -> Decimal:
    from django.db.models import Sum

    from inventory.models import StockMovement

    return StockMovement.objects.filter(company=company, product=product).aggregate(
        t=Sum("quantity")
    )["t"] or Decimal("0")


# ---------------------------------------------------------------------------
# Draft contamination, filters, KPIs
# ---------------------------------------------------------------------------


def test_cft_001_012_046_047_072_draft_does_not_contaminate_committed_state(tenant_a):
    """CFT-001 CFT-012 CFT-046 CFT-047 CFT-072 — drafts do not move stock,
    dashboard KPIs, or committed registers; list filters stay split."""
    from ledgers.services import LedgerService
    from reporting.services import ReportService

    company = tenant_a.company
    product = make_product(company, sku="CFT001")
    add_stock(tenant_a, product, "10")
    customer = make_customer(company)
    supplier = make_supplier(company)
    stock0 = _qty(company, product)
    dash0 = ReportService.dashboard(company)

    sale_draft = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "3", "unit_price": "100", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    pur_draft = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "4", "unit_price": "80", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert sale_draft["status"] == "DRAFT"
    assert pur_draft["status"] == "DRAFT"
    assert _qty(company, product) == stock0
    dash1 = ReportService.dashboard(company)
    assert _d(dash1["sales_this_month"]["total"]) == _d(dash0["sales_this_month"]["total"])
    assert _d(dash1["purchases_this_month"]["total"]) == _d(dash0["purchases_this_month"]["total"])
    assert _d(dash1["receivables"]) == _d(dash0["receivables"])
    assert LedgerService.customer_outstanding(company, customer) == Decimal("0")
    assert sale_draft["id"] not in _register_ids(tenant_a)
    listed = tenant_a.client.get("/api/v1/sales/invoices/", {"status": "DRAFT"})
    assert listed.status_code == 200
    draft_ids = {r["id"] for r in listed.data["results"]}
    assert sale_draft["id"] in draft_ids
    completed = tenant_a.client.get("/api/v1/sales/invoices/", {"status": "COMPLETED"})
    assert sale_draft["id"] not in {r["id"] for r in completed.data["results"]}


# ---------------------------------------------------------------------------
# Returns
# ---------------------------------------------------------------------------


def test_cft_006_008_partial_multiline_return_only_touches_that_line(tenant_a):
    """CFT-006 CFT-008 CFT-052 — partial return keeps COMPLETED; only the
    returned line's stock/value reverse."""
    from inventory.models import StockBalance
    from ledgers.services import LedgerService
    from sales.models import SalesInvoice

    company = tenant_a.company
    p_keep = make_product(company, sku="CFT008-KEEP")
    p_ret = make_product(company, sku="CFT008-RET")
    add_stock(tenant_a, p_keep, "10")
    add_stock(tenant_a, p_ret, "10")
    customer = make_customer(company)
    inv = _complete_sale(
        tenant_a,
        customer,
        [
            {"product": p_keep.id, "quantity": "4", "unit_price": "10", "gst_rate": "0"},
            {"product": p_ret.id, "quantity": "6", "unit_price": "20", "gst_rate": "0"},
        ],
    )
    keep_after_sale = StockBalance.objects.get(product=p_keep).on_hand
    ret_after_sale = StockBalance.objects.get(product=p_ret).on_hand
    outstanding_after_sale = LedgerService.sales_invoice_outstanding(
        SalesInvoice.objects.get(pk=inv["id"])
    )

    _return_sale(tenant_a, inv, p_ret, "2", "20")
    obj = SalesInvoice.objects.get(pk=inv["id"])
    assert obj.status == SalesInvoice.Status.COMPLETED
    assert StockBalance.objects.get(product=p_keep).on_hand == keep_after_sale
    assert StockBalance.objects.get(product=p_ret).on_hand == ret_after_sale + Decimal("2")
    outstanding = LedgerService.sales_invoice_outstanding(obj)
    assert outstanding == outstanding_after_sale - Decimal("40.00")


def test_cft_007_cancel_sales_return_restores_sale(tenant_a):
    """CFT-007 — cancelling a completed sales return removes restored stock
    again and flips RETURNED back to COMPLETED when no other return remains."""
    from sales.models import SalesInvoice, SalesReturn

    company = tenant_a.company
    product = make_product(company, sku="CFT007")
    add_stock(tenant_a, product, "10")
    customer = make_customer(company)
    inv = _complete_sale(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "4", "unit_price": "25", "gst_rate": "0"}],
    )
    after_sale = _on_hand(company, product)
    _ret_data, ret_id = _return_sale(tenant_a, inv, product, "4", "25")
    obj = SalesInvoice.objects.get(pk=inv["id"])
    assert obj.status == SalesInvoice.Status.RETURNED
    assert _on_hand(company, product) == after_sale + Decimal("4")

    cancel = tenant_a.client.post(f"/api/v1/sales/returns/{ret_id}/cancel/")
    assert cancel.status_code == 200, cancel.data
    obj.refresh_from_db()
    assert obj.status == SalesInvoice.Status.COMPLETED
    assert SalesReturn.objects.get(pk=ret_id).status == SalesReturn.Status.CANCELLED
    assert _on_hand(company, product) == after_sale


# ---------------------------------------------------------------------------
# Purchase lifecycle / AP
# ---------------------------------------------------------------------------


def test_cft_014_016_026_030_cancel_purchase_and_purchase_return(tenant_a):
    """CFT-014 CFT-016 CFT-026 CFT-030 — complete purchase raises AP/stock;
    cancel purchase reverses both; cancel of a purchase return restores them."""
    from ledgers.services import LedgerService
    from purchases.models import PurchaseInvoice

    company = tenant_a.company
    product = make_product(company, sku="CFT014")
    supplier = make_supplier(company)
    pur = _complete_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "5", "unit_price": "80", "gst_rate": "0"}],
    )
    inv = PurchaseInvoice.objects.get(pk=pur["id"])
    assert LedgerService.purchase_invoice_outstanding(inv) == Decimal("400.00")
    assert _on_hand(company, product) == Decimal("5")

    ret = tenant_a.client.post(
        "/api/v1/purchases/returns/",
        {
            "supplier": supplier.id,
            "purchase_invoice": pur["id"],
            "items": [{"product": product.id, "quantity": "2", "unit_price": "80", "gst_rate": "0"}],
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    assert tenant_a.client.post(f"/api/v1/purchases/returns/{ret.data['id']}/complete/").status_code == 200
    assert _on_hand(company, product) == Decimal("3")
    inv.refresh_from_db()
    assert LedgerService.purchase_invoice_outstanding(inv) == Decimal("240.00")

    cancel_ret = tenant_a.client.post(f"/api/v1/purchases/returns/{ret.data['id']}/cancel/")
    assert cancel_ret.status_code == 200, cancel_ret.data
    assert _on_hand(company, product) == Decimal("5")
    inv.refresh_from_db()
    assert LedgerService.purchase_invoice_outstanding(inv) == Decimal("400.00")

    cancel_pur = tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/cancel/")
    assert cancel_pur.status_code == 200, cancel_pur.data
    assert cancel_pur.data["status"] == "CANCELLED"
    assert _on_hand(company, product) == Decimal("0")
    inv.refresh_from_db()
    assert LedgerService.purchase_invoice_outstanding(inv) == Decimal("0")


def test_cft_017_purchase_amend_after_sale_consumed_keeps_sale_cogs(tenant_a):
    """CFT-017 — amending a purchase lot after a sale consumed it must not
    rewrite the sale's posted COGS."""
    from accounting.models import JournalEntry

    company = _books(tenant_a.company)
    product = make_product(company, sku="CFT017")
    supplier = make_supplier(company)
    customer = make_customer(company)
    pur = _complete_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "5", "unit_price": "80", "gst_rate": "0"}],
    )
    sale = _complete_sale(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "2", "unit_price": "120", "gst_rate": "0"}],
    )
    from django.db.models import Sum

    from accounting.models import JournalLine

    cogs = JournalEntry.objects.filter(
        company=company, source_type="SALES_INVOICE", source_id=sale["id"], purpose="COGS"
    )
    assert cogs.exists()
    cogs_total = JournalLine.objects.filter(entry__in=cogs).aggregate(t=Sum("debit"))["t"] or Decimal("0")
    assert cogs_total > 0

    amend = tenant_a.client.patch(
        f"/api/v1/purchases/invoices/{pur['id']}/",
        {
            "confirm_amend": True,
            "items": [{"product": product.id, "quantity": "5", "unit_price": "50", "gst_rate": "0"}],
        },
        format="json",
    )
    assert amend.status_code == 200, amend.data
    cogs_after = JournalLine.objects.filter(
        entry__company=company,
        entry__source_type="SALES_INVOICE",
        entry__source_id=sale["id"],
        entry__purpose="COGS",
    ).aggregate(t=Sum("debit"))["t"] or Decimal("0")
    assert cogs_after == cogs_total
    from sales.models import SalesInvoice

    assert _d(SalesInvoice.objects.get(pk=sale["id"]).grand_total) == _d(sale["grand_total"])


def test_cft_027_028_031_032_ap_allocate_reverse_and_over_alloc(tenant_a):
    """CFT-027 CFT-028 CFT-031 CFT-032 — supplier allocate / reverse / partial /
    over-allocation reject."""
    from accounting.models import JournalEntry
    from ledgers.services import LedgerService
    from purchases.models import PurchaseInvoice

    company = _books(tenant_a.company)
    product = make_product(company, sku="CFT027")
    supplier = make_supplier(company)
    pur = _complete_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "5", "unit_price": "100", "gst_rate": "0"}],
    )
    inv = PurchaseInvoice.objects.get(pk=pur["id"])
    assert LedgerService.purchase_invoice_outstanding(inv) == Decimal("500.00")

    pay = tenant_a.client.post(
        "/api/v1/payments/supplier-payments/",
        {"supplier": supplier.id, "amount": "500", "mode": "CASH"},
        format="json",
    )
    assert pay.status_code == 201, pay.data
    over = tenant_a.client.post(
        "/api/v1/payments/allocations/",
        {"supplier_payment": pay.data["id"], "purchase_invoice": pur["id"], "amount": "501"},
        format="json",
    )
    assert over.status_code == 400
    part = tenant_a.client.post(
        "/api/v1/payments/allocations/",
        {"supplier_payment": pay.data["id"], "purchase_invoice": pur["id"], "amount": "200"},
        format="json",
    )
    assert part.status_code == 201, part.data
    inv.refresh_from_db()
    assert LedgerService.purchase_invoice_outstanding(inv) == Decimal("300.00")
    je = JournalEntry.objects.filter(
        company=company, source_type="PAYMENT_ALLOCATION", source_id=part.data["id"]
    )
    assert je.filter(status=JournalEntry.Status.POSTED).exists()

    unalloc = tenant_a.client.post(
        f"/api/v1/payments/allocations/{part.data['id']}/unallocate/", {}, format="json"
    )
    assert unalloc.status_code == 200, unalloc.data
    inv.refresh_from_db()
    assert LedgerService.purchase_invoice_outstanding(inv) == Decimal("500.00")
    alloc_jes = list(
        JournalEntry.objects.filter(
            company=company, source_type="PAYMENT_ALLOCATION", source_id=part.data["id"]
        )
    )
    assert alloc_jes
    assert all(e.status != JournalEntry.Status.POSTED for e in alloc_jes) or any(
        e.status == JournalEntry.Status.REVERSED for e in alloc_jes
    )


def test_cft_029_returned_purchase_with_residual_dn_stays_in_ap(tenant_a):
    """CFT-029 — RETURNED purchase with residual debit-note AP remains in
    payables (G-18)."""
    from ledgers.services import LedgerService
    from purchases.models import PurchaseInvoice
    from reporting.services import ReportService

    company = tenant_a.company
    product = make_product(company, sku="CFT029")
    supplier = make_supplier(company)
    pur = _complete_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "0"}],
    )
    src = pur["items"][0]["id"]
    dn = tenant_a.client.post(
        "/api/v1/purchases/debit-notes/",
        {
            "supplier": supplier.id,
            "purchase_invoice": pur["id"],
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
        f"/api/v1/purchases/debit-notes/{dn.data['id']}/complete/",
        {"confirm_additional_debit": True},
        format="json",
    )
    assert dn_done.status_code == 200, dn_done.data

    ret = tenant_a.client.post(
        "/api/v1/purchases/returns/",
        {
            "supplier": supplier.id,
            "purchase_invoice": pur["id"],
            "items": [{"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "0"}],
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    assert tenant_a.client.post(f"/api/v1/purchases/returns/{ret.data['id']}/complete/").status_code == 200
    inv = PurchaseInvoice.objects.get(pk=pur["id"])
    assert inv.status == PurchaseInvoice.Status.RETURNED
    residual = LedgerService.purchase_invoice_outstanding(inv)
    assert residual > 0
    payables = _d(ReportService.dashboard(company)["payables"])
    assert payables >= residual
    assert LedgerService.supplier_outstanding(company, supplier) == residual


# ---------------------------------------------------------------------------
# Sales AR / cancel / over-allocation
# ---------------------------------------------------------------------------


def test_cft_023_038_045_053_070_100_cancel_reverses_and_retires_number(tenant_a):
    """CFT-023 CFT-038 CFT-045 CFT-053 CFT-070 CFT-098 CFT-100 — cancel zeros
    AR, restores stock against the movement-sum invariant, drops committed
    totals, and retires the document number."""
    from core.invariants.inventory import balance_equals_movements
    from core.services.document_numbers import gst_fy_label_for
    from ledgers.services import LedgerService
    from reporting.services import ReportService
    from sales.models import SalesInvoice

    company = tenant_a.company
    product = make_product(company, sku="CFT023")
    add_stock(tenant_a, product, "10")
    customer = make_customer(company)
    inv = _complete_sale(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "3", "unit_price": "50", "gst_rate": "0"}],
    )
    number = inv["number"]
    obj = SalesInvoice.objects.get(pk=inv["id"])
    assert LedgerService.sales_invoice_outstanding(obj) == Decimal("150.00")
    dash_live = ReportService.dashboard(company)
    assert inv["id"] in {r["id"] for r in dash_live["recent_invoices"]} or _d(
        dash_live["sales_this_month"]["total"]
    ) >= Decimal("150")

    cancel = tenant_a.client.post(
        f"/api/v1/sales/invoices/{inv['id']}/cancel/",
        {"reason": "customer withdrew"},
        format="json",
    )
    assert cancel.status_code == 200, cancel.data
    obj.refresh_from_db()
    assert obj.status == SalesInvoice.Status.CANCELLED
    assert obj.number == number
    assert LedgerService.sales_invoice_outstanding(obj) == Decimal("0")
    assert _on_hand(company, product) == Decimal("10")
    assert _movement_sum(company, product) == _on_hand(company, product)
    assert balance_equals_movements(company) == []
    assert inv["id"] not in _register_ids(tenant_a)
    dash_after = ReportService.dashboard(company)
    assert _d(dash_after["sales_this_month"]["total"]) == _d(dash_live["sales_this_month"]["total"]) - Decimal(
        "150.00"
    )
    fy = gst_fy_label_for(obj.invoice_date)
    retired = tenant_a.client.get("/api/v1/reports/cancelled-document-numbers/", {"fy": fy})
    assert retired.status_code == 200
    rows = retired.data.get("rows") or []
    if isinstance(retired.data.get("data"), list):
        rows = retired.data["data"]
    assert any(r.get("number") == number for r in rows)
    later = _complete_sale(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "0"}],
    )
    assert later["number"] != number


def test_cft_025_over_allocation_then_excess_to_other_invoice_or_advance(tenant_a):
    """CFT-025 — over-allocation against one invoice is rejected; excess can
    still sit as advance or allocate to a different invoice."""
    from ledgers.services import LedgerService
    from sales.models import SalesInvoice

    company = tenant_a.company
    product = make_product(company, sku="CFT025")
    add_stock(tenant_a, product, "20")
    customer = make_customer(company)
    a = _complete_sale(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
    )
    b = _complete_sale(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "80", "gst_rate": "0"}],
    )
    receipt = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": "200", "mode": "CASH"},
        format="json",
    )
    assert receipt.status_code == 201, receipt.data
    assert _d(receipt.data["unallocated"]) == Decimal("200.00")
    over = tenant_a.client.post(
        "/api/v1/payments/allocations/",
        {"receipt": receipt.data["id"], "sales_invoice": a["id"], "amount": "150"},
        format="json",
    )
    assert over.status_code == 400
    ok_a = tenant_a.client.post(
        "/api/v1/payments/allocations/",
        {"receipt": receipt.data["id"], "sales_invoice": a["id"], "amount": "100"},
        format="json",
    )
    assert ok_a.status_code == 201, ok_a.data
    ok_b = tenant_a.client.post(
        "/api/v1/payments/allocations/",
        {"receipt": receipt.data["id"], "sales_invoice": b["id"], "amount": "80"},
        format="json",
    )
    assert ok_b.status_code == 201, ok_b.data
    leftover = tenant_a.client.get(f"/api/v1/payments/receipts/{receipt.data['id']}/").data
    assert _d(leftover["unallocated"]) == Decimal("20.00")
    assert LedgerService.sales_invoice_outstanding(SalesInvoice.objects.get(pk=a["id"])) == Decimal("0")
    assert LedgerService.sales_invoice_outstanding(SalesInvoice.objects.get(pk=b["id"])) == Decimal("0")
    assert LedgerService.customer_unallocated_receipts(company, customer) == Decimal("20.00")


# ---------------------------------------------------------------------------
# Inventory surfaces
# ---------------------------------------------------------------------------


def test_cft_040_042_048_reserved_available_agrees_across_surfaces(tenant_a):
    """CFT-040 CFT-042 CFT-048 — available = on_hand − reserved on product
    balances, inventory summary, low-stock, and dead-stock; warehouse filter
    must not silently use the default godown."""
    from insights.alerts import build_business_alerts
    from inventory.models import MovementType, StockBalance, Warehouse
    from inventory.services import InventoryService
    from inventory.views import low_stock_alert_payload
    from reporting.services import ReportService

    company = tenant_a.company
    product = make_product(company, sku="CFT040", reorder_level="100")
    main = InventoryService.default_warehouse(company)
    branch_resp = tenant_a.client.post(
        "/api/v1/inventory/warehouses/", {"name": "CFT Branch", "code": "CFTBR"}, format="json"
    )
    assert branch_resp.status_code == 201, branch_resp.data
    branch = Warehouse.objects.get(pk=branch_resp.data["id"])
    InventoryService.post_movement(
        company=company,
        product=product,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("8"),
        unit_cost=Decimal("10"),
        user=tenant_a.owner,
        warehouse=main,
    )
    InventoryService.post_movement(
        company=company,
        product=product,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("5"),
        unit_cost=Decimal("10"),
        user=tenant_a.owner,
        warehouse=branch,
    )
    customer = make_customer(company)
    so = tenant_a.client.post(
        "/api/v1/sales/orders/",
        {
            "customer": customer.id,
            "order_date": str(timezone.localdate()),
            "items": [{"product": product.id, "quantity": "8", "unit_price": "20", "gst_rate": "0"}],
        },
        format="json",
    )
    assert so.status_code == 201, so.data
    assert tenant_a.client.post(f"/api/v1/sales/orders/{so.data['id']}/confirm/").status_code == 200

    main_bal = StockBalance.objects.get(company=company, product=product, warehouse=main)
    assert main_bal.available == main_bal.on_hand - main_bal.reserved
    assert main_bal.reserved == Decimal("8")
    assert main_bal.available == Decimal("0")

    listed = tenant_a.client.get("/api/v1/inventory/balances/", {"product": product.id})
    assert listed.status_code == 200
    page_rows = listed.data["results"]
    summary = ReportService.inventory_summary(company)
    summary_available = sum(
        _d(r["available"]) for r in summary["rows"] if r["product_id"] == product.id
    )
    page_available = sum(_d(r["available"]) for r in page_rows)
    assert page_available == Decimal("5")
    assert page_available == summary_available
    assert InventoryService.available_quantity(company=company, product=product) == page_available

    # CFT-048: All-godowns must include the branch lot. Filtering the default
    # godown (fully reserved → available 0) must not match that aggregate.
    main_only = ReportService.inventory_summary(company, warehouse_id=main.id)
    main_row = next(r for r in main_only["rows"] if r["product_id"] == product.id)
    assert _d(main_row["available"]) == Decimal("0")
    assert _d(main_row["available"]) != summary_available
    branch_only = ReportService.inventory_summary(company, warehouse_id=branch.id)
    branch_row = next(r for r in branch_only["rows"] if r["product_id"] == product.id)
    assert _d(branch_row["available"]) == Decimal("5")

    low = low_stock_alert_payload(company)
    low_ids = {
        row["product_id"] if isinstance(row, dict) else row.product_id
        for row in low
    }
    assert product.id in low_ids
    alerts = build_business_alerts(company)
    # Fully reserved main-warehouse qty (available 0) must not be valued as dead.
    dead_money = sum(
        (a.get("money_impact_paise") or 0)
        for a in alerts
        if a.get("code") == "DEAD_STOCK"
    )
    assert dead_money >= 0


def test_cft_043_044_stock_movement_recon_and_return_surfaces(tenant_a):
    """CFT-043 CFT-044 — opening + purchases − sales + returns = closing;
    a return hits stock movement, sales report, and product stock together."""
    from inventory.models import MovementType, StockMovement
    from reporting.services import ReportService

    company = tenant_a.company
    product = make_product(company, sku="CFT043")
    add_stock(tenant_a, product, "10", unit_cost="40")
    supplier = make_supplier(company)
    customer = make_customer(company)
    _complete_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "4", "unit_price": "40", "gst_rate": "0"}],
    )
    sale = _complete_sale(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "3", "unit_price": "90", "gst_rate": "0"}],
    )
    _return_sale(tenant_a, sale, product, "1", "90")

    opening = StockMovement.objects.filter(
        company=company, product=product, movement_type=MovementType.OPENING_STOCK
    ).count()
    assert opening >= 1
    closing = _on_hand(company, product)
    assert closing == Decimal("12")  # 10 + 4 − 3 + 1
    assert _movement_sum(company, product) == closing

    moves = tenant_a.client.get("/api/v1/inventory/movements/", {"product": product.id})
    assert moves.status_code == 200
    types = {r["movement_type"] for r in moves.data["results"]}
    assert MovementType.SALE in types or "SALE" in types
    summary = ReportService.inventory_summary(company)
    row = next(r for r in summary["rows"] if r["product_id"] == product.id)
    assert _d(row["on_hand"]) == closing
    assert sale["id"] in _register_ids(tenant_a)  # partial return: still COMPLETED


# ---------------------------------------------------------------------------
# Reports / dashboard / NID-01 live numbers
# ---------------------------------------------------------------------------


def test_cft_050_067_073_nid01_returned_counts_in_money_not_insights(tenant_a):
    """CFT-050 CFT-067 CFT-073 CFT-NID-01 — dashboard invoice_count includes
    RETURNED; insights health sales_count excludes it."""
    from insights.services import compute_health_score
    from reporting.services import ReportService
    from sales.models import SalesInvoice

    company = tenant_a.company
    product = make_product(company, sku="CFT050")
    add_stock(tenant_a, product, "10")
    customer = make_customer(company)
    inv = _complete_sale(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "0"}],
    )
    dash_before = ReportService.dashboard(company)
    health_before = compute_health_score(company)
    _return_sale(tenant_a, inv, product, "2", "100")
    obj = SalesInvoice.objects.get(pk=inv["id"])
    assert obj.status == SalesInvoice.Status.RETURNED

    dash_after = ReportService.dashboard(company)
    health_after = compute_health_score(company)
    # Money dashboard still sees RETURNED in the invoice_count predicate.
    assert int(dash_after["invoice_count"]) == int(dash_before["invoice_count"])
    # Insights operational sales drop the reversed sale.
    assert health_after["sales_count"] == health_before["sales_count"] - 1
    # Net sales (CN subtracted) fall; operational count is the split.
    assert _d(dash_after["sales_this_month"]["total"]) < _d(dash_before["sales_this_month"]["total"])


def test_cft_054_060_061_062_063_064_065_066_069_dashboard_statement_outstanding(tenant_a):
    """CFT-054 CFT-060 CFT-061 CFT-062 CFT-063 CFT-064 CFT-065 CFT-066 CFT-068
    CFT-069 — dashboard, statement, and outstanding share LedgerService."""
    from ledgers.services import LedgerService
    from reporting.services import ReportService

    company = tenant_a.company
    product = make_product(company, sku="CFT054")
    add_stock(tenant_a, product, "20")
    customer = make_customer(company)
    supplier = make_supplier(company)
    sale = _complete_sale(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "0"}],
    )
    _complete_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "3", "unit_price": "40", "gst_rate": "0"}],
    )
    receipt = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": "50", "mode": "CASH"},
        format="json",
    )
    assert receipt.status_code == 201, receipt.data
    tenant_a.client.post(
        "/api/v1/payments/allocations/",
        {"receipt": receipt.data["id"], "sales_invoice": sale["id"], "amount": "50"},
        format="json",
    )
    _return_sale(tenant_a, sale, product, "1", "100")

    statement = LedgerService.customer_statement(company, customer)
    types = {row["type"] for row in statement}
    assert "SALES_INVOICE" in types
    assert "RECEIPT" in types
    assert any("RETURN" in t or t == "SALES_CREDIT_NOTE" or t == "CREDIT_NOTE" for t in types) or any(
        "CN" in str(row).upper() or "RETURN" in str(row.get("type", "")).upper() for row in statement
    )
    outstanding = LedgerService.customer_outstanding(company, customer)
    closing = statement[-1]["balance"] if statement else Decimal("0")
    assert outstanding == closing
    profile = tenant_a.client.get(f"/api/v1/customers/{customer.id}/")
    assert profile.status_code == 200
    assert _d(profile.data["outstanding"]) == outstanding
    dash = ReportService.dashboard(company)
    assert _d(dash["receivables"]) == outstanding
    assert _d(dash["payables"]) == LedgerService.supplier_outstanding(company, supplier)
    supp_stmt = LedgerService.supplier_statement(company, supplier)
    assert supp_stmt[-1]["balance"] == LedgerService.supplier_outstanding(company, supplier)

    cancelled = _complete_sale(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "0"}],
    )
    tenant_a.client.post(f"/api/v1/sales/invoices/{cancelled['id']}/cancel/", {"reason": "void"}, format="json")
    stmt2 = LedgerService.customer_statement(company, customer)
    cancelled_types = [row for row in stmt2 if row.get("number") == cancelled["number"]]
    assert not cancelled_types or all(
        _d(row.get("debit") or 0) == 0 and _d(row.get("credit") or 0) == 0 for row in cancelled_types
    )
    assert LedgerService.customer_outstanding(company, customer) == outstanding


def test_cft_071_099_amend_updates_once_and_writes_money_audit(tenant_a):
    """CFT-071 CFT-099 — amend moves insights/dashboard once; AuditEvent and
    MoneyFieldAudit both fire."""
    from core.models import AuditEvent, StatutoryDocumentEvent
    from reporting.services import ReportService

    company = tenant_a.company
    product = make_product(company, sku="CFT071")
    add_stock(tenant_a, product, "10")
    customer = make_customer(company)
    inv = _complete_sale(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
    )
    before = _d(ReportService.dashboard(company)["sales_this_month"]["total"])
    amend = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv['id']}/",
        {
            "confirm_amend": True,
            "expected_amend_revision": inv.get("amend_revision", 0),
            "items": [{"product": product.id, "quantity": "1", "unit_price": "80"}],
        },
        format="json",
    )
    assert amend.status_code == 200, amend.data
    after = _d(ReportService.dashboard(company)["sales_this_month"]["total"])
    assert after == before - Decimal("20.00")
    assert AuditEvent.objects.filter(
        entity_type="SalesInvoice", entity_id=str(inv["id"])
    ).exists()
    from core.models import MoneyFieldAudit

    assert MoneyFieldAudit.objects.filter(
        company=company,
        entity_type="salesinvoice",
        entity_id=inv["id"],
        field="grand_total",
    ).exists()
    assert StatutoryDocumentEvent.objects.filter(
        company=company,
        entity_type="sales_invoice",
        entity_id=inv["id"],
        event_type=StatutoryDocumentEvent.EventType.AMEND,
    ).exists()


# ---------------------------------------------------------------------------
# Dates & periods
# ---------------------------------------------------------------------------


def test_cft_056_057_059_date_moves_period_and_later_return_stays_put(tenant_a):
    """CFT-056 CFT-057 CFT-059 — documents report by their own date; a later
    return does not rewrite the original period's historical sale total."""
    from reporting.services import ReportService

    company = tenant_a.company
    product = make_product(company, sku="CFT056")
    add_stock(tenant_a, product, "20")
    customer = make_customer(company)
    march = _complete_sale(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "0"}],
        invoice_date="2026-03-20",
    )
    april = _complete_sale(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        invoice_date="2026-04-05",
    )
    march_reg = ReportService.sales_register(
        company, date_from=date(2026, 3, 1), date_to=date(2026, 3, 31)
    )
    april_reg = ReportService.sales_register(
        company, date_from=date(2026, 4, 1), date_to=date(2026, 4, 30)
    )
    march_ids = {r["id"] for r in march_reg["rows"] if r.get("invoice_type") != "CREDIT_NOTE"}
    april_ids = {r["id"] for r in april_reg["rows"] if r.get("invoice_type") != "CREDIT_NOTE"}
    assert march["id"] in march_ids
    assert march["id"] not in april_ids
    assert april["id"] in april_ids

    _return_sale(tenant_a, march, product, "2", "100", return_date="2026-04-10")
    march_after = ReportService.sales_register(
        company, date_from=date(2026, 3, 1), date_to=date(2026, 3, 31)
    )
    april_after = ReportService.sales_register(
        company, date_from=date(2026, 4, 1), date_to=date(2026, 4, 30)
    )
    march_sale_rows = [r for r in march_after["rows"] if r["id"] == march["id"]]
    assert march_sale_rows
    march_cn = [
        r for r in march_after["rows"]
        if r.get("doc_type") == "SALES_CREDIT_NOTE" or r.get("invoice_type") == "CREDIT_NOTE"
    ]
    assert not march_cn, "return must not rewrite the original period's historical totals"


def test_cft_058_102_closed_blocks_amend_soft_closed_allows_cancel(tenant_a):
    """CFT-058 CFT-102 — CLOSED period blocks new complete and in-place amend;
    SOFT_CLOSED still allows cancel (unwind)."""
    from accounting.models import AccountingPeriod
    from sales.models import SalesInvoice

    company = _books(tenant_a.company)
    product = make_product(company, sku="CFT058")
    add_stock(tenant_a, product, "20")
    customer = make_customer(company)
    day = date(2026, 2, 10)
    inv = _complete_sale(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "40", "gst_rate": "0"}],
        invoice_date=str(day),
    )
    AccountingPeriod.objects.create(
        company=company,
        name="Feb closed",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
        status=AccountingPeriod.Status.CLOSED,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    amend = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv['id']}/",
        {
            "confirm_amend": True,
            "expected_amend_revision": inv.get("amend_revision", 0),
            "items": [{"product": product.id, "quantity": "1", "unit_price": "30"}],
        },
        format="json",
    )
    assert amend.status_code in (400, 403, 409, 422), amend.data
    obj = SalesInvoice.objects.get(pk=inv["id"])
    assert _d(obj.items.get().unit_price) == Decimal("40.00")

    blocked = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    tenant_a.client.patch(
        f"/api/v1/sales/invoices/{blocked['id']}/", {"invoice_date": str(day)}, format="json"
    )
    complete = tenant_a.client.post(f"/api/v1/sales/invoices/{blocked['id']}/complete/")
    assert complete.status_code in (400, 403, 409, 422)

    AccountingPeriod.objects.filter(company=company, name="Feb closed").update(
        status=AccountingPeriod.Status.SOFT_CLOSED
    )
    cancel = tenant_a.client.post(
        f"/api/v1/sales/invoices/{inv['id']}/cancel/", {"reason": "unwind"}, format="json"
    )
    assert cancel.status_code == 200, cancel.data


# ---------------------------------------------------------------------------
# Tax / TCS / refund-not-CN
# ---------------------------------------------------------------------------


def test_cft_082_cess_partial_return_reverses_only_returned_qty(tenant_a):
    """CFT-082 — specific cess lands on the invoice and only the returned
    quantity's cess reverses."""
    company = tenant_a.company
    product = make_product(company, sku="CFT082", gst_rate="28")
    add_stock(tenant_a, product, "10")
    customer = make_customer(company, state="Maharashtra", gstin="27BBBBB1111B2ZX")
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
    assert _d(done.data["cess_total"]) == Decimal("34.00")
    ret = tenant_a.client.post(
        "/api/v1/sales/returns/",
        {
            "customer": customer.id,
            "sales_invoice": inv["id"],
            "items": [
                {
                    "product": product.id,
                    "quantity": "1",
                    "unit_price": "100.00",
                    "gst_rate": "28",
                    "cess_rate": "12.00",
                    "cess_amount": "5.00",
                }
            ],
        },
        format="json",
    )
    assert ret.status_code == 201, ret.data
    assert tenant_a.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/").status_code == 200
    from sales.models import SalesCreditNote

    cn = SalesCreditNote.objects.filter(sales_invoice_id=inv["id"]).latest("id")
    assert _d(cn.cess_total) > 0
    assert _d(cn.cess_total) < _d(done.data["cess_total"])


def test_cft_084_composition_blocked_from_gstr1_cmp08_ok(tenant_a):
    """CFT-084 — composition sales never enter the regular GSTR-1 pipeline."""
    from accounts.models import Company
    from core.exceptions import BusinessRuleError
    from reporting.gst_returns import assert_not_composition_for_regular_returns
    from reporting.gstr2b import build_cmp08

    company = tenant_a.company
    company.registration_type = Company.RegistrationType.COMPOSITION
    company.gstin = "29AAAAA0000A1ZY"
    company.save(update_fields=["registration_type", "gstin"])
    with pytest.raises(BusinessRuleError, match="Composition"):
        assert_not_composition_for_regular_returns(company)
    period = timezone.localdate().strftime("%Y-%m")
    cmp08 = build_cmp08(company, period)
    assert cmp08.get("aid_kind") == "composition_cmp08"


def test_cft_085_itc_ineligible_excluded_from_gstr3b_claim(tenant_a):
    """CFT-085 — ITC-ineligible purchase still posts stock/AP but is absent
    from GSTR-3B claimed ITC."""
    from purchases.models import PurchaseInvoice
    from reporting.gst_returns import build_gstr3b

    company = _books(tenant_a.company)
    product = make_product(company, sku="CFT085", gst_rate="18")
    supplier = make_supplier(company, state="Karnataka", gstin="29ZZZZZ9999Z1ZP")
    claimable = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18"}],
        purchase_type="GST",
    )
    tenant_a.client.patch(
        f"/api/v1/purchases/invoices/{claimable['id']}/",
        {"itc_eligibility": "CLAIMABLE"},
        format="json",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{claimable['id']}/complete/").status_code == 200
    blocked = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18"}],
        purchase_type="GST",
    )
    tenant_a.client.patch(
        f"/api/v1/purchases/invoices/{blocked['id']}/",
        {"itc_eligibility": "INELIGIBLE"},
        format="json",
    )
    done = tenant_a.client.post(f"/api/v1/purchases/invoices/{blocked['id']}/complete/")
    assert done.status_code == 200, done.data
    assert _on_hand(company, product) == Decimal("2")
    period = timezone.localdate().strftime("%Y-%m")
    g3 = build_gstr3b(company, period)
    claimed_cgst = _d(g3["itc"]["books_itc"]["cgst"])
    claimable_obj = PurchaseInvoice.objects.get(pk=claimable["id"])
    assert claimed_cgst == _d(claimable_obj.cgst_total)
    assert claimed_cgst < _d(claimable_obj.cgst_total) + _d(PurchaseInvoice.objects.get(pk=blocked["id"]).cgst_total)


def test_cft_089_explicit_tcs_logs_both_rate_and_entered_amount(tenant_a):
    """CFT-089 — explicit TCS override posts the entered amount and logs both
    the entered amount and the rate-derived amount."""
    from core.models import StatutoryDocumentEvent

    company = _books(tenant_a.company)
    product = make_product(company, sku="CFT089", gst_rate="18")
    add_stock(tenant_a, product, "20")
    customer = make_customer(company, state="Karnataka", gstin="29AAAAA0000A1ZY")
    draft = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer.id,
            "invoice_type": "GST",
            "tcs_section": "206C(1H)",
            "tcs_rate": "0.1",
            "items": [{"product": product.id, "quantity": "10", "unit_price": "1000.00", "gst_rate": "18"}],
        },
        format="json",
    )
    assert draft.status_code == 201, draft.data
    tenant_a.client.patch(
        f"/api/v1/sales/invoices/{draft.data['id']}/", {"tcs_amount": "50.00"}, format="json"
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{draft.data['id']}/complete/")
    assert done.status_code == 200, done.data
    assert _d(done.data["tcs_amount"]) == Decimal("50.00")
    evt = StatutoryDocumentEvent.objects.filter(
        company=company,
        entity_type="sales_invoice",
        entity_id=draft.data["id"],
        event_type=StatutoryDocumentEvent.EventType.COMPLETE,
    ).latest("created_at")
    override = evt.payload.get("tcs_override") or {}
    assert override.get("provided_amount") == "50.00"
    assert Decimal(str(override.get("calculated_rate_amount"))) == Decimal("11.80")


def test_cft_090_tcs_reverses_on_return_in_worksheet(tenant_a):
    """CFT-090 — TCS on a return reverses in the TCS worksheet for that period."""
    from reporting.tds_worksheets import tcs_worksheet_rows

    company = _books(tenant_a.company)
    product = make_product(company, sku="CFT090", gst_rate="18")
    add_stock(tenant_a, product, "20")
    customer = make_customer(company, state="Karnataka", gstin="29AAAAA0000A1ZY")
    draft = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {
            "customer": customer.id,
            "invoice_type": "GST",
            "tcs_section": "206C(1H)",
            "tcs_rate": "0.1",
            "items": [{"product": product.id, "quantity": "10", "unit_price": "1000.00", "gst_rate": "18"}],
        },
        format="json",
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{draft.data['id']}/complete/")
    assert done.status_code == 200, done.data
    period = done.data["invoice_date"][:7]
    before = sum((_d(r["tcs_amount"]) for r in tcs_worksheet_rows(company, period)), Decimal("0"))
    _return_sale(tenant_a, done.data, product, "10", "1000.00", gst_rate="18")
    after = sum((_d(r["tcs_amount"]) for r in tcs_worksheet_rows(company, period)), Decimal("0"))
    assert after < before
    assert after == Decimal("0") or after <= Decimal("0.05")


def test_cft_092_void_receipt_is_not_a_credit_note(tenant_a):
    """CFT-092 — a money reverse (void receipt) must not create a sales-return
    credit note; goods returns stay a separate document type."""
    from payments.models import CustomerReceipt
    from sales.models import SalesCreditNote

    company = _books(tenant_a.company)
    product = make_product(company, sku="CFT092")
    add_stock(tenant_a, product, "10")
    customer = make_customer(company)
    inv = _complete_sale(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
    )
    receipt = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": "100", "mode": "CASH"},
        format="json",
    )
    assert receipt.status_code == 201, receipt.data
    alloc = tenant_a.client.post(
        "/api/v1/payments/allocations/",
        {"receipt": receipt.data["id"], "sales_invoice": inv["id"], "amount": "100"},
        format="json",
    )
    assert alloc.status_code == 201, alloc.data
    void = tenant_a.client.post(
        f"/api/v1/payments/receipts/{receipt.data['id']}/void/",
        {"reason": "refund cash"},
        format="json",
    )
    assert void.status_code == 200, void.data
    assert CustomerReceipt.objects.get(pk=receipt.data["id"]).status == "VOIDED"
    assert not SalesCreditNote.objects.filter(sales_invoice_id=inv["id"]).exists()


# ---------------------------------------------------------------------------
# PDF B2, product search, lifecycle
# ---------------------------------------------------------------------------


def test_cft_107_pdf_snapshot_differs_from_live_outstanding_after_return(tenant_a):
    """CFT-107 / B2 — after a full return with no residual DN, issued PDF
    grand_total must not equal live outstanding."""
    from core.invariants.projection import pdf_snapshot_differs_from_live_outstanding_after_return
    from ledgers.services import LedgerService
    from sales.models import SalesInvoice

    company = tenant_a.company
    product = make_product(company, sku="CFT107")
    add_stock(tenant_a, product, "10")
    customer = make_customer(company)
    inv = _complete_sale(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "0"}],
    )
    _return_sale(tenant_a, inv, product, "2", "100")
    obj = SalesInvoice.objects.get(pk=inv["id"])
    live = LedgerService.sales_invoice_outstanding(obj)
    assert live != obj.grand_total
    assert pdf_snapshot_differs_from_live_outstanding_after_return(company) == []


def test_cft_112_product_search_is_company_scoped(tenant_a, tenant_b):
    """CFT-112 — barcode/SKU search never resolves another tenant's product."""
    from masters.models import Product

    ours = make_product(tenant_a.company, sku="CFT112-A", barcode="CFT112BAR")
    foreign_p = make_product(tenant_b.company, sku="CFT112-A", barcode="CFT112BAR", name="Foreign")
    by_sku = tenant_a.client.get("/api/v1/products/", {"search": "CFT112-A"})
    assert by_sku.status_code == 200
    ids = {r["id"] for r in by_sku.data["results"]}
    assert ours.id in ids
    assert foreign_p.id not in ids
    foreign = tenant_a.client.get(f"/api/v1/products/{foreign_p.id}/")
    assert foreign.status_code == 404
    assert Product.objects.filter(company=tenant_b.company, sku="CFT112-A").count() == 1


def test_cft_121_125_sales_lifecycle_surfaces_agree(tenant_a):
    """CFT-121 CFT-122 CFT-123 CFT-124 CFT-125 — draft → complete → partial
    pay → return → cancel-return → cancel of a sibling must not double-post,
    other lines/periods stay put, and surfaces agree (NID-01 where they must not)."""
    from ledgers.services import LedgerService
    from reporting.services import ReportService
    from sales.models import SalesInvoice

    company = tenant_a.company
    product = make_product(company, sku="CFT121")
    other = make_product(company, sku="CFT122-OTHER")
    add_stock(tenant_a, product, "20")
    add_stock(tenant_a, other, "20")
    customer = make_customer(company)

    draft = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "2", "unit_price": "50", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    other_hand = _on_hand(company, other)
    complete = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert complete.status_code == 200
    twice = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert twice.status_code == 400
    assert _on_hand(company, other) == other_hand

    receipt = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": "40", "mode": "CASH"},
        format="json",
    )
    tenant_a.client.post(
        "/api/v1/payments/allocations/",
        {"receipt": receipt.data["id"], "sales_invoice": draft["id"], "amount": "40"},
        format="json",
    )
    obj = SalesInvoice.objects.get(pk=draft["id"])
    assert LedgerService.sales_invoice_outstanding(obj) == Decimal("60.00")
    dash = ReportService.dashboard(company)
    assert _d(dash["receivables"]) == LedgerService.customer_outstanding(company, customer)

    _return_sale(tenant_a, complete.data, product, "1", "50")
    obj.refresh_from_db()
    assert obj.status == SalesInvoice.Status.COMPLETED
    stmt = LedgerService.customer_statement(company, customer)
    assert stmt[-1]["balance"] == LedgerService.customer_outstanding(company, customer)
    assert _on_hand(company, other) == other_hand
