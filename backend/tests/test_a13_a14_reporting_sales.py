"""Focused regressions for A13 reporting Highs + A14 money mediums."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.exceptions import BusinessRuleError
from purchases.boe_services import BillOfEntryService
from purchases.models import BillOfEntry, PurchaseInvoice
from reporting.gst_returns import _boe_eligible_for_itc_period, _rate_buckets
from reporting.gst_returns_sections import accumulate_hsn_line
from reporting.services import ReportService, assert_report_date_span
from sales.models import (
    SalesCreditNote,
    SalesDebitNote,
    SalesInvoice,
    SalesOrder,
)
from sales.notes_services import SalesNotesService
from sales.services import SalesService
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db


def _complete_si(tenant, qty="2", price="1000", gst="18"):
    product = make_product(tenant.company, gst_rate=gst)
    add_stock(tenant, product, "20")
    customer = make_customer(tenant.company)
    draft = create_draft_invoice(
        tenant,
        customer,
        [{"product": product.id, "quantity": qty, "unit_price": price, "gst_rate": gst}],
        invoice_type="NON_GST" if Decimal(gst) == 0 else "GST",
    )
    inv = SalesInvoice.objects.get(pk=draft["id"])
    SalesService.complete(inv, tenant.owner)
    inv.refresh_from_db()
    return inv, product, customer


def test_cr066_product_sales_nets_credit_note(tenant_a):
    inv, product, _ = _complete_si(tenant_a)
    note = SalesCreditNote.objects.create(
        company=tenant_a.company,
        customer=inv.customer,
        sales_invoice=inv,
        note_date=inv.invoice_date,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    src = inv.items.get()
    SalesNotesService.set_credit_note_items(
        note,
        [{"product": product, "quantity": Decimal("1"), "source_item": src}],
        tenant_a.owner,
    )
    SalesNotesService.complete_credit_note(
        note, tenant_a.owner, confirm_paid_invoice=True, confirm_price_override=True
    )
    rows = {r["product_id"]: r for r in ReportService.product_sales(tenant_a.company)["rows"]}
    assert rows[product.id]["quantity"] == Decimal("1")
    assert rows[product.id]["amount"] < Decimal(str(src.line_total))


def test_cr074_export_date_span_rejects_over_366():
    with pytest.raises(BusinessRuleError, match="366"):
        assert_report_date_span(
            date(2024, 1, 1), date(2025, 2, 1), kind="Export 'sales-register'"
        )


def test_cr070_rate_buckets_prefer_stored_rcm_header():
    class _Inv:
        is_reverse_charge = True
        rcm_igst = Decimal("180.00")
        rcm_cgst = Decimal("0")
        rcm_sgst = Decimal("0")
        is_intra_state = False

    class _Item:
        supply_nature = "TAXABLE"
        applied_rate = Decimal("18")
        gst_rate = Decimal("18")
        taxable_amount = Decimal("1000")
        cgst = sgst = igst = cess = Decimal("0")
        cess_rate = cess_amount = quantity = Decimal("0")

    buckets = _rate_buckets([_Item()], invoice=_Inv())
    assert buckets[Decimal("18")]["igst"] == Decimal("180.00")
    assert buckets[Decimal("18")]["cgst"] == Decimal("0")


def test_cr071_hsn_uses_applied_rate():
    class _Item:
        hsn_code = "1234"
        uqc_code = "NOS"
        applied_rate = Decimal("12")
        gst_rate = Decimal("18")
        quantity = Decimal("1")
        taxable_amount = Decimal("100")
        cgst = sgst = igst = cess = Decimal("0")

    buckets = defaultdict(
        lambda: {
            "quantity": Decimal("0"),
            "taxable_value": Decimal("0"),
            "cgst": Decimal("0"),
            "sgst": Decimal("0"),
            "igst": Decimal("0"),
            "cess": Decimal("0"),
        }
    )
    accumulate_hsn_line(buckets, _Item())
    assert ("1234", "12", "NOS") in buckets
    assert ("1234", "18", "NOS") not in buckets


def test_cr072_boe_period_sql_filter(tenant_a):
    BillOfEntry.objects.create(
        company=tenant_a.company,
        boe_number="IN",
        boe_date=date(2026, 6, 10),
        status=BillOfEntry.Status.COMPLETED,
        itc_eligibility=BillOfEntry.ItcEligibility.ELIGIBLE,
        igst_amount=Decimal("100"),
        itc_period="2026-06",
    )
    BillOfEntry.objects.create(
        company=tenant_a.company,
        boe_number="OUT",
        boe_date=date(2025, 1, 10),
        status=BillOfEntry.Status.COMPLETED,
        itc_eligibility=BillOfEntry.ItcEligibility.ELIGIBLE,
        igst_amount=Decimal("50"),
        itc_period="2025-01",
    )
    qs = _boe_eligible_for_itc_period(tenant_a.company, "2026-06")
    assert qs.count() == 1
    assert qs.get().boe_number == "IN"


def test_cr017_cn_on_paid_invoice_requires_confirm(tenant_a):
    from payments.models import CustomerReceipt, PaymentAllocation, ReceiptStatus

    inv, product, customer = _complete_si(tenant_a)
    receipt = CustomerReceipt.objects.create(
        company=tenant_a.company,
        customer=customer,
        amount=inv.grand_total,
        receipt_date=inv.invoice_date,
        status=ReceiptStatus.POSTED,
        mode="CASH",
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    PaymentAllocation.objects.create(
        company=tenant_a.company,
        receipt=receipt,
        sales_invoice=inv,
        amount=inv.grand_total,
    )
    note = SalesCreditNote.objects.create(
        company=tenant_a.company,
        customer=customer,
        sales_invoice=inv,
        note_date=inv.invoice_date,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    src = inv.items.get()
    SalesNotesService.set_credit_note_items(
        note,
        [{"product": product, "quantity": Decimal("1"), "source_item": src}],
        tenant_a.owner,
    )
    with pytest.raises(BusinessRuleError) as exc:
        SalesNotesService.complete_credit_note(note, tenant_a.owner)
    assert exc.value.status_code == 409
    SalesNotesService.complete_credit_note(
        note, tenant_a.owner, confirm_paid_invoice=True, confirm_price_override=True
    )
    note.refresh_from_db()
    assert note.status == SalesCreditNote.Status.COMPLETED


def test_cr018_dn_qty_cap(tenant_a):
    inv, product, _ = _complete_si(tenant_a, qty="1")
    note = SalesDebitNote.objects.create(
        company=tenant_a.company,
        customer=inv.customer,
        sales_invoice=inv,
        note_date=inv.invoice_date,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    src = inv.items.get()
    SalesNotesService.set_debit_note_items(
        note,
        [
            {
                "product": product,
                "quantity": Decimal("5"),
                "unit_price": Decimal("1"),
                "source_item": src,
            }
        ],
        tenant_a.owner,
    )
    with pytest.raises(BusinessRuleError, match="exceeds remaining qty"):
        SalesNotesService.complete_debit_note(note, tenant_a.owner, confirm_additional_debit=True)


def test_cr020_so_reservation_held_until_invoice_complete(tenant_a):
    from inventory.services import InventoryService

    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    order = SalesOrder.objects.create(
        company=tenant_a.company,
        customer=customer,
        invoice_type=SalesInvoice.InvoiceType.NON_GST,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    SalesNotesService.set_order_items(
        order,
        [{"product": product, "quantity": Decimal("3"), "unit_price": Decimal("100"), "gst_rate": 0}],
        tenant_a.owner,
    )
    SalesNotesService.confirm_sales_order(order, tenant_a.owner)
    wh = InventoryService.default_warehouse(tenant_a.company)
    reserved_after_confirm = InventoryService.available_quantity(
        tenant_a.company, product, wh
    )
    inv = SalesNotesService.convert_sales_order(order, tenant_a.owner)
    order.refresh_from_db()
    assert order.status == SalesOrder.Status.CONFIRMED
    assert order.converted_invoice_id == inv.id
    assert (
        InventoryService.available_quantity(tenant_a.company, product, wh)
        == reserved_after_confirm
    )
    SalesService.complete(inv, tenant_a.owner)
    order.refresh_from_db()
    assert order.status == SalesOrder.Status.CONVERTED


def test_cr024_completed_qty_amend_raises(tenant_a):
    inv, product, _ = _complete_si(tenant_a, qty="2", gst="0")
    with pytest.raises(BusinessRuleError, match="Cannot amend quantity"):
        SalesService.set_items(
            inv,
            [{"product": product, "quantity": Decimal("3"), "unit_price": Decimal("1000"), "gst_rate": 0}],
            tenant_a.owner,
        )


def test_cr044_boe_cancel_blocked_when_linked_completed_pi(tenant_a):
    supplier = make_supplier(tenant_a.company)
    boe = BillOfEntry.objects.create(
        company=tenant_a.company,
        supplier=supplier,
        boe_number="LINKED",
        boe_date=timezone.localdate(),
        status=BillOfEntry.Status.COMPLETED,
        igst_amount=Decimal("100"),
    )
    PurchaseInvoice.objects.create(
        company=tenant_a.company,
        supplier=supplier,
        purchase_type=PurchaseInvoice.PurchaseType.NON_GST,
        status=PurchaseInvoice.Status.COMPLETED,
        bill_of_entry=boe,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    with pytest.raises(BusinessRuleError, match="completed purchase"):
        BillOfEntryService.cancel(boe, tenant_a.owner)


def test_cr082_books_health_docs_gl_helper_wired(tenant_a):
    from accounting.services import BooksHealthService, seed_chart_of_accounts

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    health = BooksHealthService.control_balances(tenant_a.company)
    assert isinstance(health["alerts"], list)
    assert "ar" in health and "ap" in health


def test_cr025_failed_irn_treated_as_non_live(tenant_a):
    from sales.irn_guard import assert_no_live_irn

    inv, _, _ = _complete_si(tenant_a)
    inv.irn = "TEST-FAILED-IRN"
    inv.einvoice_status = "FAILED"
    # assert_no_live_irn treats FAILED as non-live (no exception)
    assert_no_live_irn(inv, kind="invoice")

    inv.einvoice_status = "GENERATED"
    with pytest.raises(BusinessRuleError, match="live IRN"):
        assert_no_live_irn(inv, kind="invoice")


def test_cr027_recurring_catchup_capped_loop(tenant_a):
    from sales.models import RecurringInvoiceSchedule
    from sales.recurring import MAX_CATCHUP_TICKS, process_due_schedules

    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company)
    # Schedule overdue by 3 months
    overdue = timezone.now() - timedelta(days=95)
    sched = RecurringInvoiceSchedule.objects.create(
        company=tenant_a.company,
        customer=customer,
        cadence=RecurringInvoiceSchedule.Cadence.MONTHLY,
        next_run_at=overdue,
        line_template=[{"product_id": product.id, "quantity": 1, "unit_price": "100"}],
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    result = process_due_schedules(now=timezone.now())
    # Should have caught up all 3 or 4 periods in a single run
    assert result["created"] >= 3
    assert result["created"] <= MAX_CATCHUP_TICKS
    sched.refresh_from_db()
    assert sched.next_run_at > timezone.now()


def test_cr028_validate_lines_cess_bounds(tenant_a):
    product = make_product(tenant_a.company)
    # Negative cess amount
    with pytest.raises(BusinessRuleError, match="Cess amount cannot be negative"):
        SalesService.set_items(
            SalesInvoice.objects.create(
                company=tenant_a.company,
                customer=make_customer(tenant_a.company),
                created_by=tenant_a.owner,
                updated_by=tenant_a.owner,
            ),
            [{"product": product, "quantity": Decimal("1"), "unit_price": Decimal("100"), "cess_amount": Decimal("-5")}],
            tenant_a.owner,
        )


def test_cr046_purchase_return_and_boe_query_validation(tenant_a):
    # Bad status on PurchaseReturnViewSet
    resp = tenant_a.client.get("/api/v1/purchases/returns/?status=INVALID")
    assert resp.status_code == 400
    assert "Unknown status" in str(resp.data)

    # Bad supplier on BillOfEntryViewSet
    boe_resp = tenant_a.client.get("/api/v1/purchases/bills-of-entry/?supplier=not-an-int")
    assert boe_resp.status_code == 400
    assert "numeric id" in str(boe_resp.data)

