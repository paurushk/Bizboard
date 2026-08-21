from datetime import date
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone

from accounting.models import AccountingPeriod, JournalEntry, JournalLine
from accounting.services import BooksHealthService, PostingService, seed_chart_of_accounts
from core.exceptions import BusinessRuleError
from inventory.models import MovementType, StockMovement
from inventory.services import InventoryService
from ledgers.services import LedgerService
from payments.models import (
    CustomerReceipt,
    GatewayPayment,
    GatewayPaymentStatus,
    PaymentAllocation,
    PaymentMode,
    ReceiptStatus,
)
from payments.services import PaymentService
from sales.models import SalesInvoice, SalesItem
from tests.conftest import add_stock, make_customer, make_product


def _completed_invoice(company, customer, *, grand="118.00", taxable="100.00", cgst="9.00", sgst="9.00", **kwargs):
    invoice = SalesInvoice.objects.create(
        company=company,
        customer=customer,
        status=SalesInvoice.Status.COMPLETED,
        invoice_date=kwargs.pop("invoice_date", "2026-04-01"),
        grand_total=Decimal(grand),
        taxable_total=Decimal(taxable),
        cgst_total=Decimal(cgst),
        sgst_total=Decimal(sgst),
        **kwargs,
    )
    product = make_product(company, sku=f"P1-{invoice.id}", gst_rate="18")
    SalesItem.objects.create(
        company=company,
        invoice=invoice,
        product=product,
        quantity=Decimal("1"),
        unit_price=Decimal(taxable),
        taxable_amount=Decimal(taxable),
        cgst=Decimal(cgst),
        sgst=Decimal(sgst),
        igst=Decimal("0"),
        line_total=Decimal(grand),
        gst_rate=Decimal("18"),
    )
    return invoice


@pytest.fixture
def books(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    return tenant_a


def test_bulk_customer_outstanding_matches_gl(books):
    customer = make_customer(books.company)
    invoice = _completed_invoice(books.company, customer)
    PostingService.post_sales_invoice(invoice, books.owner)
    bulk = LedgerService.bulk_customer_outstanding(books.company)
    single = LedgerService.customer_outstanding(books.company, customer)
    assert bulk[customer.id] == single == Decimal("118.00")
    health = BooksHealthService.control_balances(books.company)
    assert health["ar"]["healthy"] is True


def test_soft_closed_blocks_operational_post(books):
    AccountingPeriod.objects.create(
        company=books.company,
        name="April",
        start_date="2026-04-01",
        end_date="2026-04-30",
        status=AccountingPeriod.Status.SOFT_CLOSED,
    )
    with pytest.raises(BusinessRuleError, match="closed accounting period"):
        PostingService.post(
            company=books.company,
            source_type="TEST",
            source_id=99,
            purpose="SOFT",
            entry_date=date(2026, 4, 10),
            lines=[
                {"account": PostingService._account(books.company, "1100"), "debit": 1},
                {"account": PostingService._account(books.company, "3100"), "credit": 1},
            ],
        )


def test_soft_closed_allows_reverse(books):
    entry = PostingService.post(
        company=books.company,
        source_type="TEST",
        source_id=100,
        purpose="OPEN",
        entry_date=date(2026, 4, 10),
        lines=[
            {"account": PostingService._account(books.company, "1100"), "debit": 5},
            {"account": PostingService._account(books.company, "3100"), "credit": 5},
        ],
        user=books.owner,
    )
    AccountingPeriod.objects.create(
        company=books.company,
        name="April",
        start_date="2026-04-01",
        end_date="2026-04-30",
        status=AccountingPeriod.Status.SOFT_CLOSED,
    )
    reversal = PostingService.reverse(entry, books.owner, date(2026, 4, 11))
    assert reversal is not None
    entry.refresh_from_db()
    assert entry.status == JournalEntry.Status.REVERSED


def test_opening_stock_posts_1400_3200(books):
    product = make_product(books.company)
    movement = InventoryService.post_movement(
        company=books.company,
        product=product,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("10"),
        unit_cost=Decimal("8"),
        user=books.owner,
        reference_type="opening_stock",
    )
    PostingService.post_opening_stock(movement, books.owner)
    je = JournalEntry.objects.get(
        company=books.company,
        source_type="STOCK_MOVEMENT",
        source_id=movement.id,
        purpose="OPENING_STOCK",
    )
    codes = {line.account.code: (line.debit, line.credit) for line in je.lines.all()}
    assert codes["1400"][0] == Decimal("80.00")
    assert codes["3200"][1] == Decimal("80.00")


def test_wo_issue_stamps_wavg_unit_cost(books):
    from manufacturing.models import Bom, BomLine, WorkOrder
    from manufacturing.services import release_work_order

    fg = make_product(books.company, name="FG", sku="FG-1")
    comp = make_product(books.company, name="Comp", sku="CP-1", purchase_price="10")
    add_stock(books, comp, 20, unit_cost="12")
    bom = Bom.objects.create(company=books.company, product=fg, name="FG BOM", status=Bom.Status.ACTIVE)
    BomLine.objects.create(bom=bom, component=comp, qty=Decimal("2"))
    wo = WorkOrder.objects.create(company=books.company, bom=bom, qty=Decimal("3"), status=WorkOrder.Status.DRAFT)
    release_work_order(wo, books.owner)
    move = StockMovement.objects.get(
        company=books.company,
        reference_type="work_order",
        reference_id=str(wo.id),
        movement_type=MovementType.MANUFACTURE_ISSUE,
    )
    assert Decimal(str(move.unit_cost or 0)) > 0


def test_refund_soft_reverses_allocations(books, monkeypatch):
    customer = make_customer(books.company)
    invoice = SalesInvoice.objects.create(
        company=books.company,
        customer=customer,
        status=SalesInvoice.Status.COMPLETED,
        invoice_date=timezone.localdate(),
        grand_total=Decimal("100.00"),
        taxable_total=Decimal("100.00"),
    )
    PostingService.post_sales_invoice(invoice, books.owner)
    gp = GatewayPayment.objects.create(
        company=books.company,
        provider="sandbox",
        provider_payment_id="pay_test_1",
        amount=Decimal("100.00"),
        status=GatewayPaymentStatus.CAPTURED,
    )
    receipt = PaymentService.create_receipt(
        company=books.company,
        customer=customer,
        amount=Decimal("100.00"),
        mode="UPI",
        receipt_date=timezone.localdate(),
        user=books.owner,
        gateway_payment=gp,
    )
    PaymentService.allocate_receipt(
        receipt=receipt, sales_invoice=invoice, amount=Decimal("100.00"), user=books.owner
    )
    alloc_id = PaymentAllocation.objects.get(receipt=receipt).id

    class _Adapter:
        def refund(self, **kwargs):
            return {"ok": True}

    monkeypatch.setattr("payments.services.get_adapter", lambda *a, **k: _Adapter())
    monkeypatch.setattr("payments.services.decrypt_gateway_credentials", lambda *a, **k: {})
    PaymentService.refund_gateway_payment(gateway_payment=gp, user=books.owner)
    alloc = PaymentAllocation.objects.get(pk=alloc_id)
    assert alloc.reversed_at is not None
    assert PaymentAllocation.objects.filter(pk=alloc_id).exists()


def test_backfill_skips_opening_cogs(books):
    customer = make_customer(books.company)
    invoice = SalesInvoice.objects.create(
        company=books.company,
        customer=customer,
        status=SalesInvoice.Status.COMPLETED,
        invoice_date="2026-04-01",
        grand_total=Decimal("50.00"),
        taxable_total=Decimal("50.00"),
        is_opening_balance=True,
        notes="TALLY_OPENING",
    )
    call_command("backfill_accounting_postings")
    assert JournalEntry.objects.filter(
        company=books.company, source_type="SALES_INVOICE", source_id=invoice.id, purpose="OPENING"
    ).exists()
    assert not JournalEntry.objects.filter(
        company=books.company, source_type="SALES_INVOICE", source_id=invoice.id, purpose="COGS"
    ).exists()


def test_control_balances_flags_untagged_ar(books):
    customer = make_customer(books.company)
    invoice = _completed_invoice(books.company, customer)
    PostingService.post_sales_invoice(invoice, books.owner)
    JournalLine.objects.filter(
        entry__company=books.company, account__code="1200", entry__source_id=invoice.id
    ).update(customer=None)
    health = BooksHealthService.control_balances(books.company)
    assert health["ar"]["healthy"] is False
    assert any(a["code"] == "AR_CONTROL_MISMATCH" for a in health["alerts"])


def test_assert_period_allows_soft_closed_override(books):
    from reporting.gst_periods import assert_period_allows_money_amend

    AccountingPeriod.objects.create(
        company=books.company,
        name="April",
        start_date="2026-04-01",
        end_date="2026-04-30",
        status=AccountingPeriod.Status.SOFT_CLOSED,
    )
    with pytest.raises(BusinessRuleError, match="SOFT_CLOSED"):
        assert_period_allows_money_amend(books.company, date(2026, 4, 10))
    assert_period_allows_money_amend(books.company, date(2026, 4, 10), allow_soft_closed=True)


def test_backfill_opening_stock_and_skips_voided_receipt(books):
    product = make_product(books.company, sku="OS-BF")
    movement = InventoryService.post_movement(
        company=books.company,
        product=product,
        movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("4"),
        unit_cost=Decimal("5"),
        user=books.owner,
        reference_type="opening_stock",
    )
    customer = make_customer(books.company)
    CustomerReceipt.objects.create(
        company=books.company,
        customer=customer,
        amount=Decimal("10.00"),
        mode=PaymentMode.CASH,
        receipt_date="2026-04-02",
        status=ReceiptStatus.VOIDED,
    )
    call_command("backfill_accounting_postings")
    assert JournalEntry.objects.filter(
        company=books.company,
        source_type="STOCK_MOVEMENT",
        source_id=movement.id,
        purpose="OPENING_STOCK",
    ).exists()
    assert not JournalEntry.objects.filter(
        company=books.company, source_type="CUSTOMER_RECEIPT", purpose="CREATE"
    ).exists()
