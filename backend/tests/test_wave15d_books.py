"""Wave 15D: BooksHealth period close, depreciation alerts, cost-center reports."""

from decimal import Decimal
from datetime import date

import pytest

from accounting.models import AccountingPeriod, CostCenter, FixedAsset, JournalEntry, JournalLine
from accounting.reports import balance_sheet, profit_and_loss
from accounting.services import BooksHealthService, PostingService, seed_chart_of_accounts
from core.exceptions import BusinessRuleError
from core.models import AuditEvent
from sales.models import SalesInvoice
from tests.conftest import create_draft_invoice, make_customer, make_product


pytestmark = pytest.mark.django_db


@pytest.fixture
def books(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save(update_fields=["accounting_enabled", "gstin", "state"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    return tenant_a


def test_assert_period_close_allowed_blocks_ar_mismatch(books):
    ar = PostingService._account(books.company, "1200")
    equity = PostingService._account(books.company, "3100")
    PostingService.post(
        company=books.company,
        source_type="TEST",
        source_id=1,
        purpose="SKEW",
        entry_date="2026-04-01",
        user=books.owner,
        lines=[
            {"account": ar, "debit": Decimal("100.00")},
            {"account": equity, "credit": Decimal("100.00")},
        ],
    )
    health = BooksHealthService.control_balances(books.company)
    ar_alert = next(a for a in health["alerts"] if a["code"] == "AR_CONTROL_MISMATCH")
    assert ar_alert["severity"] == "error"
    with pytest.raises(BusinessRuleError, match="AR_CONTROL_MISMATCH"):
        BooksHealthService.assert_period_close_allowed(books.company)


def test_period_close_endpoint_blocks_on_health(books):
    period = AccountingPeriod.objects.create(
        company=books.company,
        name="Apr 2026",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        status=AccountingPeriod.Status.OPEN,
    )
    customer = make_customer(books.company)
    invoice = SalesInvoice.objects.create(
        company=books.company,
        customer=customer,
        status=SalesInvoice.Status.COMPLETED,
        invoice_date="2026-04-01",
        grand_total=Decimal("100.00"),
        taxable_total=Decimal("100.00"),
    )
    # Completed invoice with no GL posting → DOCUMENT_MISSING_POSTING (error).
    resp = books.client.post(f"/api/v1/accounting/periods/{period.id}/close/")
    assert resp.status_code == 400
    assert "DOCUMENT_MISSING_POSTING" in str(resp.data)


def test_depreciation_failed_surfaces_on_books_health(books):
    asset_acct = PostingService._account(books.company, "1600")
    accum_acct = PostingService._account(books.company, "1650")
    expense_acct = PostingService._account(books.company, "5300")
    FixedAsset.objects.create(
        company=books.company,
        name="Laptop",
        asset_account=asset_acct,
        accumulated_depreciation_account=accum_acct,
        depreciation_expense_account=expense_acct,
        acquisition_date=date(2026, 1, 1),
        acquisition_cost=Decimal("12000.00"),
        useful_life_months=36,
        last_depreciation_error="Cannot post to a closed accounting period.",
    )
    health = BooksHealthService.control_balances(books.company)
    assert any(a["code"] == "DEPRECIATION_FAILED" for a in health["alerts"])


def test_pl_and_bs_filter_by_cost_center(books):
    cc_a = CostCenter.objects.create(company=books.company, code="CC-A", name="Alpha")
    cc_b = CostCenter.objects.create(company=books.company, code="CC-B", name="Beta")
    cash = PostingService._account(books.company, "1100")
    sales = PostingService._account(books.company, "4100")
    rent = PostingService._account(books.company, "5400")
    equity = PostingService._account(books.company, "3100")

    PostingService.post(
        company=books.company,
        source_type="TEST",
        source_id=1,
        purpose="CC-A-SALES",
        entry_date="2026-04-05",
        user=books.owner,
        lines=[
            {"account": cash, "debit": Decimal("200.00"), "cost_center": cc_a},
            {"account": sales, "credit": Decimal("200.00"), "cost_center": cc_a},
        ],
    )
    PostingService.post(
        company=books.company,
        source_type="TEST",
        source_id=2,
        purpose="CC-B-RENT",
        entry_date="2026-04-06",
        user=books.owner,
        lines=[
            {"account": rent, "debit": Decimal("50.00"), "cost_center": cc_b},
            {"account": cash, "credit": Decimal("50.00"), "cost_center": cc_b},
        ],
    )
    PostingService.post(
        company=books.company,
        source_type="TEST",
        source_id=3,
        purpose="OPEN",
        entry_date="2026-04-01",
        user=books.owner,
        lines=[
            {"account": cash, "debit": Decimal("1000.00")},
            {"account": equity, "credit": Decimal("1000.00")},
        ],
    )

    pl_a = profit_and_loss(books.company, "2026-04-01", "2026-04-30", cc_a.id)
    pl_b = profit_and_loss(books.company, "2026-04-01", "2026-04-30", cc_b.id)
    assert pl_a["income"] == Decimal("200.00")
    assert pl_a["expenses"] == Decimal("0")
    assert pl_b["expenses"] == Decimal("50.00")

    bs_a = balance_sheet(books.company, date(2026, 4, 30), cc_a.id)
    assert bs_a["cost_center"] == cc_a.id


def test_manual_irn_requires_reason(books):
    product = make_product(books.company, hsn_code="3004")
    customer = make_customer(books.company, state="Karnataka", gstin="29AABCU9603R1ZJ")
    inv = create_draft_invoice(
        books,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100"}],
    )
    books.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    books.company.einvoice_enabled = True
    books.company.save(update_fields=["einvoice_enabled"])

    missing = books.client.post(
        f"/api/v1/sales/invoices/{inv['id']}/mark-einvoice-generated/",
        {"irn": "abc123irn", "ack_no": "ACK001"},
        format="json",
    )
    assert missing.status_code == 400
    assert "reason" in str(missing.data).lower()

    ok = books.client.post(
        f"/api/v1/sales/invoices/{inv['id']}/mark-einvoice-generated/",
        {"irn": "abc123irn", "ack_no": "ACK001", "reason": "Filed manually on portal"},
        format="json",
    )
    assert ok.status_code == 200, ok.data
    audit = AuditEvent.objects.filter(
        company=books.company,
        entity_type="salesinvoice",
        entity_id=str(inv["id"]),
        description="einvoice.manual_irn_attested",
    ).latest("id")
    assert audit.metadata.get("reason") == "Filed manually on portal"
