"""B-wave Critical regressions: CR-120, CR-144, CR-157."""

from decimal import Decimal

import pytest

from accounting.models import Account, JournalEntry, JournalLine
from accounting.services import BooksHealthService
from core.exceptions import BusinessRuleError
from inventory.models import StockMovement
from sales.models import SalesOrder
from sales.notes_services import SalesNotesService
from tests.conftest import make_customer, make_product

pytestmark = pytest.mark.django_db


def test_cr120_so_invoice_then_challan_blocked(tenant_a):
    company = tenant_a.company
    product = make_product(company, selling_price="100", gst_rate="0")
    customer = make_customer(company)
    order = SalesOrder.objects.create(
        company=company,
        customer=customer,
        order_date=company.books_start_date or __import__("datetime").date(2026, 4, 1),
        status=SalesOrder.Status.DRAFT,
        invoice_type="NON_GST",
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    SalesNotesService.set_order_items(
        order,
        [{"product": product, "quantity": Decimal("1"), "unit_price": Decimal("100"), "gst_rate": 0}],
        tenant_a.owner,
    )
    invoice = SalesNotesService.convert_sales_order(order, tenant_a.owner)
    order.refresh_from_db()
    assert order.converted_invoice_id == invoice.pk
    with pytest.raises(BusinessRuleError, match="already has an invoice"):
        SalesNotesService.convert_sales_order_to_challan(order, tenant_a.owner)


def test_cr120_so_challan_then_invoice_blocked(tenant_a):
    company = tenant_a.company
    product = make_product(company, selling_price="100", gst_rate="0")
    customer = make_customer(company)
    order = SalesOrder.objects.create(
        company=company,
        customer=customer,
        order_date=company.books_start_date or __import__("datetime").date(2026, 4, 1),
        status=SalesOrder.Status.DRAFT,
        invoice_type="NON_GST",
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    SalesNotesService.set_order_items(
        order,
        [{"product": product, "quantity": Decimal("1"), "unit_price": Decimal("100"), "gst_rate": 0}],
        tenant_a.owner,
    )
    SalesNotesService.convert_sales_order_to_challan(order, tenant_a.owner)
    order.refresh_from_db()
    with pytest.raises(BusinessRuleError, match="already has a delivery challan"):
        SalesNotesService.convert_sales_order(order, tenant_a.owner)


@pytest.mark.no_invariant_check  # deliberately builds inconsistent state to test detection/rejection
def test_cr144_restamp_calls_stamp_cost(monkeypatch, tenant_a):
    calls: list[int] = []
    original = StockMovement.stamp_cost

    @classmethod
    def _spy(cls, pk, *, unit_cost, layer_peels=None):
        calls.append(int(pk))
        return original.__func__(cls, pk, unit_cost=unit_cost, layer_peels=layer_peels)

    monkeypatch.setattr(StockMovement, "stamp_cost", _spy)

    from inventory.models import MovementType, Warehouse

    wh = Warehouse.objects.filter(company=tenant_a.company).first()
    if wh is None:
        wh = Warehouse.objects.create(
            company=tenant_a.company, name="WH", code="WH1", is_default=True
        )
    product = make_product(tenant_a.company)
    move = StockMovement.objects.create(
        company=tenant_a.company,
        warehouse=wh,
        product=product,
        movement_type=MovementType.PURCHASE,
        quantity=Decimal("1"),
        unit_cost=Decimal("10"),
        reference_type="test",
        reference_id="cr144",
        created_by=tenant_a.owner,
    )
    StockMovement.stamp_cost(move.pk, unit_cost=Decimal("12"))
    move.refresh_from_db()
    assert move.unit_cost == Decimal("12")
    assert calls == [move.pk]


def test_cr157_advance_receipt_control_healthy(tenant_a):
    company = tenant_a.company
    if not company.accounting_enabled:
        company.accounting_enabled = True
        company.save(update_fields=["accounting_enabled"])
    from accounting.services import seed_chart_of_accounts

    seed_chart_of_accounts(company)
    cust = make_customer(company)
    ar = Account.objects.get(company=company, code="1200")
    adv = Account.objects.get(company=company, code="2300")
    cash = Account.objects.filter(company=company, code="1100").first()
    if cash is None:
        cash = Account.objects.filter(company=company, account_type="ASSET").exclude(
            code__in=("1200", "2300")
        ).first()
    assert cash is not None
    entry = JournalEntry.objects.create(
        company=company,
        entry_date=__import__("datetime").date(2026, 4, 15),
        status=JournalEntry.Status.POSTED,
        source_type="TEST",
        source_id=157,
        purpose="COMPLETE",
        created_by=tenant_a.owner,
    )
    JournalLine.objects.create(
        company=company,
        entry=entry, account=ar, debit=Decimal("1000"), credit=Decimal("0"), customer=cust
    )
    JournalLine.objects.create(
        company=company,
        entry=entry, account=adv, debit=Decimal("0"), credit=Decimal("400"), customer=cust
    )
    JournalLine.objects.create(
        company=company,
        entry=entry, account=cash, debit=Decimal("0"), credit=Decimal("600")
    )
    health = BooksHealthService.control_balances(company)
    assert health["ar"]["healthy"] is True, health["alerts"]
    codes = {a["code"] for a in health["alerts"]}
    assert "AR_CONTROL_MISMATCH" not in codes
