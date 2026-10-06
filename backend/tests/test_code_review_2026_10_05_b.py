"""Second batch of regression tests for the 2026-10-05 review fixes (sales, purchases, accounts, reports)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.conftest import add_stock, make_customer, make_product


def _order(tenant, product, qty):
    from sales.models import SalesOrder
    from sales.notes_services import SalesNotesService

    customer = make_customer(tenant.company, state="Karnataka")
    order = SalesOrder.objects.create(
        company=tenant.company, customer=customer, created_by=tenant.owner, updated_by=tenant.owner,
    )
    SalesNotesService.set_order_items(
        order,
        [{"product": product, "quantity": Decimal(qty), "unit_price": Decimal("100"), "gst_rate": Decimal("18")}],
        tenant.owner,
    )
    SalesNotesService.confirm_sales_order(order, tenant.owner)
    return order


# ---- order conversion: a discarded draft gives its quantity back
def test_deleting_a_partial_draft_invoice_reopens_the_order(tenant_a):
    from sales.models import SalesOrder
    from sales.notes_services import SalesNotesService

    product = make_product(tenant_a.company, sku="CV-1")
    add_stock(tenant_a, product, "100")
    order = _order(tenant_a, product, "10")
    line = order.items.get()
    draft = SalesNotesService.convert_sales_order(order, tenant_a.owner, line_quantities={line.id: Decimal("6")})
    order.refresh_from_db()
    line.refresh_from_db()
    assert line.invoiced_quantity == Decimal("6") and order.status == SalesOrder.Status.PARTIALLY_CONVERTED

    resp = tenant_a.client.delete(f"/api/v1/sales/invoices/{draft.pk}/")
    assert resp.status_code in (200, 204), resp.content
    order.refresh_from_db()
    line.refresh_from_db()
    assert line.invoiced_quantity == Decimal("0")
    assert order.status == SalesOrder.Status.CONFIRMED and order.converted_invoice_id is None
    # The whole order can be converted again.
    again = SalesNotesService.convert_sales_order(order, tenant_a.owner)
    assert again.items.get().quantity == Decimal("10")


def test_a_partly_converted_draft_invoice_can_still_be_edited_within_its_share(tenant_a):
    from core.exceptions import BusinessRuleError
    from sales.notes_services import SalesNotesService
    from sales.services import SalesService

    product = make_product(tenant_a.company, sku="CV-2")
    add_stock(tenant_a, product, "100")
    order = _order(tenant_a, product, "10")
    line = order.items.get()
    first = SalesNotesService.convert_sales_order(order, tenant_a.owner, line_quantities={line.id: Decimal("4")})
    other = SalesNotesService.convert_sales_order(order, tenant_a.owner, line_quantities={line.id: Decimal("3")})

    def _items(qty):
        return [{"product": product, "quantity": Decimal(qty), "unit_price": Decimal("100"), "gst_rate": Decimal("18"),
                 "description": "x"}]

    # Both drafts are checked, not only the latest one the order points at.
    for draft, elsewhere in ((first, 3), (other, 7)):
        room = 10 - elsewhere
        SalesService.set_items(draft, _items(str(room)), tenant_a.owner)
        with pytest.raises(BusinessRuleError):
            SalesService.set_items(draft, _items(str(room + 1)), tenant_a.owner)


# ---- payment status counts the settlement discount and ignores cancelled invoices
def test_payment_status_filter_agrees_with_the_ledger_on_settlement_discount(tenant_a):
    from payments.models import CustomerReceipt, PaymentAllocation
    from sales.models import SalesInvoice

    customer = make_customer(tenant_a.company, name="Disc")
    inv = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, status=SalesInvoice.Status.COMPLETED, grand_total=Decimal("1000"),
    )
    receipt = CustomerReceipt.objects.create(
        company=tenant_a.company, customer=customer, amount=Decimal("950"), settlement_discount=Decimal("50"),
    )
    PaymentAllocation.objects.create(company=tenant_a.company, receipt=receipt, sales_invoice=inv, amount=Decimal("950"))
    cancelled = SalesInvoice.objects.create(
        company=tenant_a.company, customer=customer, status=SalesInvoice.Status.CANCELLED, grand_total=Decimal("400"),
    )
    paid = tenant_a.client.get("/api/v1/sales/invoices/?payment_status=PAID")
    ids = [r["id"] for r in (paid.data["results"] if isinstance(paid.data, dict) and "results" in paid.data else paid.data)]
    assert inv.pk in ids and cancelled.pk not in ids
    stats = tenant_a.client.get("/api/v1/sales/invoices/payment-stats/")
    assert stats.status_code == 200, stats.content
    body = stats.data.get("data", stats.data)
    assert body["paid"]["count"] >= 1
    assert body["unpaid"]["count"] == 0 and body["partial"]["count"] == 0


# ---- stock transfer: cancelling after a short receipt returns exactly what is there
def test_cancel_after_a_short_receipt_restores_stock_and_clears_transit(tenant_a):
    from inventory.models import StockBalance, StockTransfer, StockTransferLine, Warehouse
    from inventory.services import InventoryService, StockTransferService

    company = tenant_a.company
    product = make_product(company, sku="SHORT-1")
    add_stock(tenant_a, product, "10")
    source = InventoryService.default_warehouse(company)
    dest = Warehouse.objects.create(company=company, name="East", code="EAST-S")
    transfer = StockTransfer.objects.create(
        company=company, from_warehouse=source, to_warehouse=dest,
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    line = StockTransferLine.objects.create(transfer=transfer, product=product, quantity=Decimal("5"))
    StockTransferService.dispatch(transfer, tenant_a.owner)
    StockTransferService.receive(
        transfer, tenant_a.owner, receipts=[{"line": line.pk, "quantity": "3", "reason": "2 broken"}],
    )
    transit = StockTransferService.in_transit_warehouse(company)
    assert StockBalance.objects.get(company=company, warehouse=dest, product=product).on_hand == Decimal("3")
    assert StockBalance.objects.get(company=company, warehouse=transit, product=product).on_hand == Decimal("2")

    StockTransferService.cancel(transfer, tenant_a.owner)
    on_hand = lambda wh: (StockBalance.objects.filter(company=company, warehouse=wh, product=product).first() or
                          type("Z", (), {"on_hand": Decimal("0")})).on_hand
    assert on_hand(source) == Decimal("10")
    assert on_hand(dest) == Decimal("0")
    assert on_hand(transit) == Decimal("0")


def test_a_receipt_line_that_is_not_on_the_transfer_is_refused(tenant_a):
    from core.exceptions import BusinessRuleError
    from inventory.models import StockTransfer, StockTransferLine, Warehouse
    from inventory.services import InventoryService, StockTransferService

    company = tenant_a.company
    product = make_product(company, sku="SHORT-2")
    add_stock(tenant_a, product, "10")
    dest = Warehouse.objects.create(company=company, name="West", code="WEST-S")
    transfer = StockTransfer.objects.create(
        company=company, from_warehouse=InventoryService.default_warehouse(company), to_warehouse=dest,
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    StockTransferLine.objects.create(transfer=transfer, product=product, quantity=Decimal("5"))
    StockTransferService.dispatch(transfer, tenant_a.owner)
    with pytest.raises(BusinessRuleError):
        StockTransferService.receive(transfer, tenant_a.owner, receipts=[{"line": 999999, "quantity": "1"}])
    with pytest.raises(BusinessRuleError):
        StockTransferService.receive(transfer, tenant_a.owner, receipts=[{"quantity": "1"}])


# ---- Schedule III balance sheet balances once the unclosed profit is shown in equity
def test_schedule_iii_balance_sheet_balances_with_the_surplus_line(tenant_a):
    from django.utils import timezone

    from accounting.reports import balance_sheet, profit_and_loss
    from accounting.services import PostingService

    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    PostingService._ensure_chart(company)
    today = timezone.localdate()
    PostingService.post(
        company=company, source_type="TEST_SALE", source_id=1, purpose="T1", entry_date=today, user=tenant_a.owner,
        lines=[
            {"account": PostingService._account(company, "1100"), "debit": Decimal("1000")},
            {"account": PostingService._account(company, "4100"), "credit": Decimal("1000")},
        ],
    )
    sheet = balance_sheet(company, as_of=today)
    sections = {s["key"]: s for s in sheet["schedule_iii"]["sections"]}
    assets = sections["non_current_assets"]["amount"] + sections["current_assets"]["amount"]
    liabilities_and_equity = (
        sections["equity"]["amount"] + sections["non_current_liabilities"]["amount"]
        + sections["current_liabilities"]["amount"]
    )
    assert assets == Decimal("1000.00") == liabilities_and_equity
    assert any(line["key"] == "surplus_in_profit_and_loss" for line in sections["equity"]["lines"])
    pnl = profit_and_loss(company, date_from=today.replace(month=1, day=1), date_to=today)
    assert pnl["net_profit"] == Decimal("1000.00")


# ---- sessions: a password change or logout-all kills access tokens already issued
@pytest.mark.parametrize("endpoint,body", [
    ("/api/v1/auth/logout-all/", {}),
    ("/api/v1/auth/change-password/", {"current_password": "StrongPass123!", "new_password": "AnotherPass456!"}),
])
def test_access_token_dies_when_sessions_are_revoked(tenant_a, endpoint, body):
    from rest_framework.test import APIClient

    client = APIClient()
    login = client.post("/api/v1/auth/login/", {"email": tenant_a.owner.email, "password": "StrongPass123!"}, format="json")
    assert login.status_code == 200, login.content
    assert client.get("/api/v1/auth/me/").status_code == 200
    done = client.post(endpoint, body, format="json")
    assert done.status_code == 200, done.content
    stolen = APIClient()
    for name, morsel in login.cookies.items():
        stolen.cookies[name] = morsel.value
    assert stolen.get("/api/v1/auth/me/").status_code == 401


# ---- pruning never deletes a stale in-flight money key
def test_prune_keeps_stale_in_flight_money_keys_but_removes_other_scopes(tenant_a):
    from datetime import timedelta

    from django.utils import timezone

    from core.idempotency import IN_FLIGHT_STATUS
    from core.models import IdempotencyRecord
    from core.tasks import prune_idempotency_records_task

    old = timezone.now() - timedelta(hours=48)
    money = IdempotencyRecord.objects.create(
        company=tenant_a.company, scope="sales_invoice_complete", key="k-money", status_code=IN_FLIGHT_STATUS, body={},
    )
    other = IdempotencyRecord.objects.create(
        company=tenant_a.company, scope="customer_create", key="k-other", status_code=IN_FLIGHT_STATUS, body={},
    )
    IdempotencyRecord.objects.filter(pk__in=[money.pk, other.pk]).update(created_at=old)
    prune_idempotency_records_task()
    assert IdempotencyRecord.objects.filter(pk=money.pk).exists()
    assert not IdempotencyRecord.objects.filter(pk=other.pk).exists()


# ---- campaigns: the list is searched on the server, so a match on a later page is found
def test_campaign_search_runs_on_the_server(tenant_a):
    from crm.models import Campaign

    company = tenant_a.company
    company.feature_flags = {**(company.feature_flags or {}), "ENABLE_CRM": True, "pack_grant": "insurance"}
    company.save(update_fields=["feature_flags"])
    for name in ("Diwali push", "Summer sale", "Diwali referral"):
        Campaign.objects.create(company=company, name=name, created_by=tenant_a.owner, updated_by=tenant_a.owner)
    resp = tenant_a.client.get("/api/v1/crm/campaigns/?q=diwali")
    assert resp.status_code == 200, resp.content
    body = resp.data.get("data", resp.data)
    results = body["results"] if isinstance(body, dict) and "results" in body else body
    assert sorted(r["name"] for r in results) == ["Diwali push", "Diwali referral"]
