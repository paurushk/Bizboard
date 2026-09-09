"""A10 — period centralization (CR-015,019,023,052,079,080,081,087)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from accounting.models import AccountingPeriod, JournalEntry
from accounting.services import PostingService, seed_chart_of_accounts
from core.exceptions import BusinessRuleError
from core.models import DocumentSeries
from inventory.models import MovementType, StockMovement, StockTransfer, StockTransferLine, Warehouse
from inventory.services import InventoryService, StockTransferService
from reporting.gst_periods import reopen_period, soft_close_period
from reporting.models import GstReturnPeriod
from sales.models import DeliveryChallan, RecurringInvoiceRun, RecurringInvoiceSchedule, SalesInvoice
from sales.notes_services import SalesNotesService
from sales.recurring import period_key_for, process_due_schedules
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product
from tests.test_sprint_a_accounting_p1 import books  # noqa: F401

pytestmark = pytest.mark.django_db


def _this_period() -> str:
    d = timezone.localdate()
    return f"{d.year:04d}-{d.month:02d}"


# --- CR-015 -----------------------------------------------------------------


def test_cr015_recurring_retries_same_period_after_unlock(tenant_a):
    """Lock → process (no advance) → unlock → process → draft for same period_key."""
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company)
    now = timezone.now() - timedelta(minutes=5)
    on = timezone.localtime(now).date() if timezone.is_aware(now) else now.date()
    sched = RecurringInvoiceSchedule.objects.create(
        company=tenant_a.company,
        customer=customer,
        cadence=RecurringInvoiceSchedule.Cadence.MONTHLY,
        next_run_at=now,
        is_active=True,
        line_template={"items": [{"product": product.id, "quantity": "1", "unit_price": "50"}]},
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    expected_key = period_key_for(sched.cadence, on)
    GstReturnPeriod.objects.create(
        company=tenant_a.company,
        period=f"{on.year:04d}-{on.month:02d}",
        status=GstReturnPeriod.Status.SOFT_CLOSED,
    )

    locked = process_due_schedules(now=timezone.now())
    assert locked["created"] == 0
    assert locked["skipped_locked"] == 1
    sched.refresh_from_db()
    assert sched.next_run_at == now  # CR-015: must not advance
    assert SalesInvoice.objects.filter(company=tenant_a.company).count() == 0

    reopen_period(tenant_a.company, f"{on.year:04d}-{on.month:02d}")
    unlocked = process_due_schedules(now=timezone.now())
    assert unlocked["created"] == 1
    inv = SalesInvoice.objects.get(company=tenant_a.company)
    assert inv.status == SalesInvoice.Status.DRAFT
    assert inv.invoice_date == on
    run = RecurringInvoiceRun.objects.get(schedule=sched)
    assert run.period_key == expected_key


# --- CR-019 -----------------------------------------------------------------


def test_cr019_challan_complete_blocked_when_stock_posts_in_soft_closed(tenant_a):
    soft_close_period(tenant_a.company, _this_period(), tenant_a.owner)
    tenant_a.company.stock_on_delivery_challan = True
    tenant_a.company.save(update_fields=["stock_on_delivery_challan"])
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    resp = tenant_a.client.post(
        "/api/v1/sales/delivery-challans/",
        {
            "customer": customer.id,
            "items": [{"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "0"}],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    with pytest.raises(BusinessRuleError, match="SOFT_CLOSED|closed|amend money"):
        SalesNotesService.complete_challan(
            DeliveryChallan.objects.get(pk=resp.data["id"]), tenant_a.owner
        )
    assert not StockMovement.objects.filter(
        company=tenant_a.company, reference_type="delivery_challan"
    ).exists()


# --- CR-023 -----------------------------------------------------------------


def test_cr023_sales_complete_closed_period_no_sale_movement_or_number(tenant_a):
    from sales.services import SalesService

    soft_close_period(tenant_a.company, "2026-04", tenant_a.owner)
    product = make_product(tenant_a.company, sku="A10-023")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "50", "gst_rate": "0"}],
        invoice_type="NON_GST",
    )
    SalesInvoice.objects.filter(pk=inv["id"]).update(invoice_date=date(2026, 4, 15))
    series_before = list(
        DocumentSeries.objects.filter(company=tenant_a.company, doc_type="SALES_INVOICE").values_list(
            "next_number", flat=True
        )
    )
    invoice = SalesInvoice.objects.get(pk=inv["id"])
    with pytest.raises(BusinessRuleError, match="SOFT_CLOSED|closed|amend money"):
        SalesService.complete(invoice, tenant_a.owner)
    invoice.refresh_from_db()
    assert invoice.status == SalesInvoice.Status.DRAFT
    assert not invoice.number
    assert not StockMovement.objects.filter(
        company=tenant_a.company,
        movement_type=MovementType.SALE,
        reference_type="sales_invoice",
        reference_id=str(inv["id"]),
    ).exists()
    series_after = list(
        DocumentSeries.objects.filter(company=tenant_a.company, doc_type="SALES_INVOICE").values_list(
            "next_number", flat=True
        )
    )
    assert series_after == series_before


def test_cr023_purchase_complete_closed_period_no_purchase_movement(tenant_a):
    from tests.conftest import create_draft_purchase, make_supplier

    soft_close_period(tenant_a.company, _this_period(), tenant_a.owner)
    product = make_product(tenant_a.company, sku="A10-023P")
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "40", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    resp = tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/")
    assert resp.status_code == 400
    assert not StockMovement.objects.filter(
        company=tenant_a.company,
        movement_type=MovementType.PURCHASE,
        reference_id=str(pur["id"]),
    ).exists()


# --- CR-052 -----------------------------------------------------------------


def test_cr052_stock_count_post_blocked_in_soft_closed(tenant_a):
    soft_close_period(tenant_a.company, _this_period(), tenant_a.owner)
    product = make_product(tenant_a.company, sku="A10-CNT")
    add_stock(tenant_a, product, "10")
    warehouse = InventoryService.default_warehouse(tenant_a.company)
    session = tenant_a.client.post(
        "/api/v1/inventory/stock-counts/",
        {"warehouse": warehouse.id},
        format="json",
    )
    assert session.status_code == 201, session.data
    line = (session.data.get("lines") or [])[0]
    patch = tenant_a.client.patch(
        f"/api/v1/inventory/stock-counts/{session.data['id']}/",
        {"lines": [{"id": line["id"], "counted_qty": "7"}]},
        format="json",
    )
    assert patch.status_code == 200, patch.data
    posted = tenant_a.client.post(f"/api/v1/inventory/stock-counts/{session.data['id']}/post/")
    assert posted.status_code == 400, posted.data
    assert not StockMovement.objects.filter(
        company=tenant_a.company, reason="STOCK_COUNT"
    ).exists()


def test_cr052_stock_transfer_complete_blocked_in_soft_closed(tenant_a):
    soft_close_period(tenant_a.company, _this_period(), tenant_a.owner)
    product = make_product(tenant_a.company, sku="A10-TRF")
    add_stock(tenant_a, product, "5")
    source = InventoryService.default_warehouse(tenant_a.company)
    dest = Warehouse.objects.create(company=tenant_a.company, name="Dest", code="DEST")
    transfer = StockTransfer.objects.create(
        company=tenant_a.company, from_warehouse=source, to_warehouse=dest,
    )
    StockTransferLine.objects.create(transfer=transfer, product=product, quantity="1")
    with pytest.raises(BusinessRuleError, match="SOFT_CLOSED|closed|amend money"):
        StockTransferService.complete(transfer, tenant_a.owner)
    assert StockTransfer.objects.get(pk=transfer.pk).status == StockTransfer.Status.DRAFT


def test_cr052_stock_transfer_cancel_blocked_in_hard_closed(tenant_a):
    """Cancel of a completed transfer reverses stock; hard CLOSED still blocks."""
    product = make_product(tenant_a.company, sku="A10-TRF-C")
    add_stock(tenant_a, product, "5")
    source = InventoryService.default_warehouse(tenant_a.company)
    dest = Warehouse.objects.create(company=tenant_a.company, name="DestC", code="DESTC")
    transfer = StockTransfer.objects.create(
        company=tenant_a.company, from_warehouse=source, to_warehouse=dest,
    )
    StockTransferLine.objects.create(transfer=transfer, product=product, quantity="1")
    result = StockTransferService.complete(transfer, tenant_a.owner)
    # complete may return (transfer, warnings) after CR-050/055 work
    completed = result[0] if isinstance(result, tuple) else result
    assert completed.status == StockTransfer.Status.COMPLETED

    GstReturnPeriod.objects.update_or_create(
        company=tenant_a.company,
        period=_this_period(),
        defaults={"status": GstReturnPeriod.Status.CLOSED},
    )
    with pytest.raises(BusinessRuleError, match="CLOSED|closed|amend money"):
        StockTransferService.cancel(completed, tenant_a.owner)
    assert StockTransfer.objects.get(pk=completed.pk).status == StockTransfer.Status.COMPLETED


# --- CR-079 -----------------------------------------------------------------


def test_cr079_reverse_rolls_back_status_if_save_fails(books):  # noqa: F811
    seed_chart_of_accounts(books.company, books.owner)
    entry = PostingService.post(
        company=books.company,
        source_type="TEST",
        source_id=79001,
        purpose="OPEN",
        entry_date=timezone.localdate(),
        lines=[
            {"account": PostingService._account(books.company, "1100"), "debit": 10},
            {"account": PostingService._account(books.company, "3100"), "credit": 10},
        ],
        user=books.owner,
    )
    assert entry.status == JournalEntry.Status.POSTED

    real_save = JournalEntry.save

    def _boom(self, *args, **kwargs):
        if self.pk == entry.pk and self.status == JournalEntry.Status.REVERSED:
            raise RuntimeError("injected status flip failure")
        return real_save(self, *args, **kwargs)

    with patch.object(JournalEntry, "save", _boom):
        with pytest.raises(RuntimeError, match="injected status flip"):
            PostingService.reverse(entry, user=books.owner)

    entry.refresh_from_db()
    assert entry.status == JournalEntry.Status.POSTED
    assert entry.reversed_entry_id is None
    assert not JournalEntry.objects.filter(
        company=books.company, source_type="JOURNAL_REVERSAL", source_id=entry.id
    ).exists()


# --- CR-080 -----------------------------------------------------------------


def test_cr080_posting_service_respects_gst_soft_close(books):  # noqa: F811
    """GST soft-close alone (no AccountingPeriod row) must block PostingService.post."""
    seed_chart_of_accounts(books.company, books.owner)
    soft_close_period(books.company, _this_period(), books.owner)
    with pytest.raises(BusinessRuleError, match="GST period|SOFT_CLOSED|amend money"):
        PostingService.post(
            company=books.company,
            source_type="TEST",
            source_id=80001,
            purpose="GST_ONLY",
            entry_date=timezone.localdate(),
            lines=[
                {"account": PostingService._account(books.company, "1100"), "debit": 1},
                {"account": PostingService._account(books.company, "3100"), "credit": 1},
            ],
        )


# --- CR-081 -----------------------------------------------------------------


def test_cr081_period_soft_close_uses_row_lock(books):  # noqa: F811
    seed_chart_of_accounts(books.company, books.owner)
    books.company.gstin = "29ABCDE1234F1ZW"
    books.company.state = "Karnataka"
    books.company.save(update_fields=["gstin", "state"])
    period = AccountingPeriod.objects.create(
        company=books.company,
        name="A10 Lock",
        start_date=timezone.localdate().replace(day=1),
        end_date=timezone.localdate() + timedelta(days=20),
        status=AccountingPeriod.Status.OPEN,
        created_by=books.owner,
        updated_by=books.owner,
    )
    # CR-081: view wraps select_for_update in @transaction.atomic
    resp = books.client.post(f"/api/v1/accounting/periods/{period.id}/soft-close/")
    assert resp.status_code == 200, resp.data
    period.refresh_from_db()
    assert period.status == AccountingPeriod.Status.SOFT_CLOSED


# --- CR-087 -----------------------------------------------------------------


def test_cr087_backfill_accounting_requires_company_or_dry_run(books):  # noqa: F811
    with pytest.raises(CommandError, match="--company|--dry-run"):
        call_command("backfill_accounting_postings")

    out = StringIO()
    call_command("backfill_accounting_postings", dry_run=True, stdout=out)
    assert "Dry-run" in out.getvalue() or "would" in out.getvalue().lower()
