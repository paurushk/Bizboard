"""BB-000664: financial-year close — IS accounts to 3100 Retained Earnings."""

from datetime import date
from decimal import Decimal

import pytest

from accounting.models import AccountingPeriod, JournalEntry, JournalLine
from accounting.reports import close_financial_year
from accounting.services import PostingService, seed_chart_of_accounts
from core.exceptions import BusinessRuleError
from sales.models import SalesInvoice
from tests.conftest import make_customer


pytestmark = pytest.mark.django_db


@pytest.fixture
def books(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.fy_start_month = 4
    tenant_a.company.save(update_fields=["accounting_enabled", "fy_start_month"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    AccountingPeriod.objects.create(
        company=tenant_a.company,
        name="FY26",
        start_date=date(2025, 4, 1),
        end_date=date(2026, 3, 31),
        status=AccountingPeriod.Status.OPEN,
    )
    return tenant_a


def _net(company, code):
    agg = JournalLine.objects.filter(
        entry__company=company,
        entry__status=JournalEntry.Status.POSTED,
        account__code=code,
    ).exclude(entry__source_type="JOURNAL_REVERSAL")
    debit = sum((l.debit for l in agg), Decimal("0"))
    credit = sum((l.credit for l in agg), Decimal("0"))
    return debit - credit


def _post(books, source_id, purpose, lines, entry_date=date(2025, 6, 15)):
    return PostingService.post(
        company=books.company,
        source_type="TEST",
        source_id=source_id,
        purpose=purpose,
        entry_date=entry_date,
        user=books.owner,
        lines=lines,
    )


def test_fy_close_profit_year_zeros_sales_to_retained_earnings(books):
    sales = PostingService._account(books.company, "4100")
    cash = PostingService._account(books.company, "1100")
    _post(books, 1, "SALE", [
        {"account": cash, "debit": Decimal("1000.00")},
        {"account": sales, "credit": Decimal("1000.00")},
    ])
    close_financial_year(books.company, date(2026, 3, 31), user=books.owner)
    assert _net(books.company, "4100") == Decimal("0")
    assert _net(books.company, "3100") == Decimal("-1000.00")
    period = AccountingPeriod.objects.get(company=books.company, name="FY26")
    assert period.status == AccountingPeriod.Status.CLOSED


def test_fy_close_loss_year_debits_retained_earnings(books):
    purchases = PostingService._account(books.company, "5100")
    cash = PostingService._account(books.company, "1100")
    _post(books, 2, "BUY", [
        {"account": purchases, "debit": Decimal("400.00")},
        {"account": cash, "credit": Decimal("400.00")},
    ])
    close_financial_year(books.company, date(2026, 3, 31), user=books.owner)
    assert _net(books.company, "5100") == Decimal("0")
    assert _net(books.company, "3100") == Decimal("400.00")


def test_fy_close_other_income_and_expense_mix(books):
    sales = PostingService._account(books.company, "4100")
    gain = PostingService._account(books.company, "5700")
    purchases = PostingService._account(books.company, "5100")
    salaries = PostingService._account(books.company, "5800")
    cash = PostingService._account(books.company, "1100")
    _post(books, 10, "SALE", [
        {"account": cash, "debit": Decimal("1000.00")},
        {"account": sales, "credit": Decimal("1000.00")},
    ])
    _post(books, 11, "GAIN", [
        {"account": cash, "debit": Decimal("200.00")},
        {"account": gain, "credit": Decimal("200.00")},
    ])
    _post(books, 12, "BUY", [
        {"account": purchases, "debit": Decimal("300.00")},
        {"account": cash, "credit": Decimal("300.00")},
    ])
    _post(books, 13, "PAY", [
        {"account": salaries, "debit": Decimal("400.00")},
        {"account": cash, "credit": Decimal("400.00")},
    ])
    close_financial_year(books.company, date(2026, 3, 31), user=books.owner)
    for code in ("4100", "5700", "5100", "5800"):
        assert _net(books.company, code) == Decimal("0"), code
    # Net profit 1000+200-300-400 = 500 → RE credit 500 → net debit-credit = -500
    assert _net(books.company, "3100") == Decimal("-500.00")
    assert _net(books.company, "3200") == Decimal("0")


def test_fy_close_second_call_noops(books):
    sales = PostingService._account(books.company, "4100")
    cash = PostingService._account(books.company, "1100")
    _post(books, 20, "SALE", [
        {"account": cash, "debit": Decimal("50.00")},
        {"account": sales, "credit": Decimal("50.00")},
    ])
    close_financial_year(books.company, date(2026, 3, 31), user=books.owner)
    count = JournalEntry.objects.filter(
        company=books.company, purpose="FY_CLOSE", status=JournalEntry.Status.POSTED,
    ).count()
    close_financial_year(books.company, date(2026, 3, 31), user=books.owner)
    assert JournalEntry.objects.filter(
        company=books.company, purpose="FY_CLOSE", status=JournalEntry.Status.POSTED,
    ).count() == count == 1


def test_fy_close_refuses_draft_invoices(books):
    customer = make_customer(books.company)
    SalesInvoice.objects.create(
        company=books.company,
        customer=customer,
        status=SalesInvoice.Status.DRAFT,
        invoice_date=date(2025, 8, 1),
        grand_total=Decimal("10.00"),
    )
    with pytest.raises(BusinessRuleError, match="draft"):
        close_financial_year(books.company, date(2026, 3, 31), user=books.owner)


def test_fy_close_api_owner_only(books):
    sales = PostingService._account(books.company, "4100")
    cash = PostingService._account(books.company, "1100")
    _post(books, 30, "SALE", [
        {"account": cash, "debit": Decimal("80.00")},
        {"account": sales, "credit": Decimal("80.00")},
    ])
    denied = books.staff_client.post(
        "/api/v1/accounting/fy-close/",
        {"fyEnd": "2026-03-31", "confirm": True},
        format="json",
    )
    assert denied.status_code in (403, 400)
    missing = books.client.post(
        "/api/v1/accounting/fy-close/",
        {"fyEnd": "2026-03-31"},
        format="json",
    )
    assert missing.status_code == 400
    ok = books.client.post(
        "/api/v1/accounting/fy-close/",
        {"fyEnd": "2026-03-31", "confirm": True},
        format="json",
    )
    assert ok.status_code == 200, ok.data
    assert ok.data.get("ok") is True or ok.data.get("data", {}).get("ok") is True
