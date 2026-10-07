"""Open accounting defects (BUG-ACC). Money amounts are Decimal, 0.01 half-up."""

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pytest
from django.test import override_settings
from accounting.models import (
    Account,
    AccountingPeriod,
    BankReconSession,
    FixedAsset,
    JournalEntry,
    JournalLine,
)
from accounting.reports import balance_sheet, close_financial_year, profit_and_loss
from accounting.services import BooksHealthService, PostingService, seed_chart_of_accounts
from accounting.tasks import (
    _charge_month_bounds,
    _depreciate_company_assets,
    backfill_depreciation_catchup,
)
from accounting.views import perform_accounting_backfill
from core.exceptions import BusinessRuleError
from core.models import AuditEvent
from core.services.audit_chain import MCA_RULE_11G_MASTERS
from payments.services import PaymentService
from tests.conftest import make_customer, make_product, make_supplier

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def books(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    return tenant_a
Q2 = Decimal("0.01")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Q2)


def _asset_accounts(company):
    return (
        PostingService._account(company, "1600"),
        PostingService._account(company, "1650"),
        PostingService._account(company, "5300"),
    )


def _labels(node):
    found = []
    if isinstance(node, dict):
        if node.get("label"):
            found.append(str(node["label"]))
        for value in node.values():
            found.extend(_labels(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_labels(item))
    return found


def _month_end_back(day: date, steps: int) -> date:
    cur = day
    for _ in range(steps):
        cur = cur.replace(day=1) - timedelta(days=1)
    return cur


def test_bug_acc_001_cash_shift_close_is_per_cashier(books):
    """Opening float plus the cash taken from this till only; a locked register cannot change."""
    customer = make_customer(books.company, name="Till Customer")
    business_date = date(2026, 6, 15)
    taken = PaymentService.create_receipt(
        company=books.company, customer=customer, amount=Decimal("40.00"), mode="CASH",
        receipt_date=business_date, user=books.owner,
    )
    # A payments-screen cash receipt counts toward the till only when it is marked as taken from it.
    taken.paid_from_till = True
    taken.save(update_fields=["paid_from_till"])
    PaymentService.create_receipt(
        company=books.company, customer=customer, amount=Decimal("25.00"), mode="CASH",
        receipt_date=business_date, user=books.staff,
    )
    opened = books.client.post(
        "/api/v1/accounting/cash-shifts/",
        {"business_date": "2026-06-15", "opening_float": "100.00"},
        format="json",
    )
    assert opened.status_code == 201, opened.data
    shift_id = opened.data["id"]
    closed = books.client.post(
        f"/api/v1/accounting/cash-shifts/{shift_id}/close/",
        {"denominations": {"100": 1, "20": 2}},
        format="json",
    )
    assert closed.status_code == 200, closed.data
    assert _money(closed.data["expected_cash"]) == Decimal("140.00")
    assert _money(closed.data["counted_cash"]) == Decimal("140.00")
    assert _money(closed.data["variance"]) == Decimal("0.00")
    assert closed.data["status"] == "CLOSED"
    again = books.client.post(
        f"/api/v1/accounting/cash-shifts/{shift_id}/close/",
        {"denominations": {"500": 1}},
        format="json",
    )
    assert again.status_code == 400, again.data
    patched = books.client.patch(
        f"/api/v1/accounting/cash-shifts/{shift_id}/",
        {"opening_float": "1.00"},
        format="json",
    )
    assert patched.status_code == 400, patched.data


def test_bug_acc_010_backfill_keeps_books_off_when_a_period_skips(books):
    """A closed-period payroll skip must not leave books switched on."""
    from accounts.models import Company
    from payroll.models import Employee, PayRun, PaySlip

    company = books.company
    AccountingPeriod.objects.create(
        company=company, name="April", start_date=date(2026, 4, 1), end_date=date(2026, 4, 30),
        status=AccountingPeriod.Status.CLOSED, created_by=books.owner,
    )
    employee = Employee.objects.create(
        company=company, name="Uma", code="UMA", salary=Decimal("1000.00"),
        tax_regime=Employee.TaxRegime.OLD, pf_applicable=False, esi_applicable=False,
    )
    run = PayRun.objects.create(company=company, period="2026-04", status=PayRun.Status.COMPLETED)
    PaySlip.objects.create(
        pay_run=run, company=company, employee=employee,
        gross=Decimal("1000.00"), net=Decimal("1000.00"),
    )
    Company.objects.filter(pk=company.pk).update(accounting_enabled=False)
    company.refresh_from_db()
    result = perform_accounting_backfill(company, books.owner, dry_run=False)
    company.refresh_from_db()
    rows = (result.get("skipped_by_period") or {}).get("2026-04") or []
    assert any(row.get("source_type") == "PAY_RUN" for row in rows), result
    assert company.accounting_enabled is False
    assert result["accounting_enabled"] is False
    assert not JournalEntry.objects.filter(
        company=company, source_type="PAY_RUN", purpose="PAYROLL",
    ).exists()


def test_bug_acc_010_backfill_posts_payroll_work_orders_and_bills_of_entry(books):
    """Modules that already have documents are posted, not skipped as out of scope."""
    from accounts.models import Company
    from inventory.models import MovementType
    from inventory.services import InventoryService
    from manufacturing.models import Bom, WorkOrder
    from payroll.models import Employee, PayRun, PaySlip
    from purchases.models import BillOfEntry

    company = books.company
    Company.objects.filter(pk=company.pk).update(accounting_enabled=False)
    company.refresh_from_db()
    product = make_product(company, name="Frame", sku="FRM-1")
    InventoryService.post_movement(
        company=company, product=product, movement_type=MovementType.OPENING_STOCK,
        quantity=Decimal("1"), unit_cost=Decimal("80"), user=books.owner,
        movement_date=date(2026, 10, 1),
    )
    bom = Bom.objects.create(company=company, product=product, name="Frame BOM", status=Bom.Status.ACTIVE)
    wo = WorkOrder.objects.create(
        company=company, bom=bom, qty=Decimal("1.000"), status=WorkOrder.Status.RELEASED,
        released_at=date(2026, 10, 1),
    )
    InventoryService.post_movement(
        company=company, product=product, movement_type=MovementType.MANUFACTURE_ISSUE,
        quantity=Decimal("1"), unit_cost=Decimal("80"), user=books.owner,
        reference_type="work_order", reference_id=str(wo.id), movement_date=date(2026, 10, 1),
    )
    employee = Employee.objects.create(
        company=company, name="Ravi", code="RAVI", salary=Decimal("1000.00"),
        tax_regime=Employee.TaxRegime.OLD, pf_applicable=False, esi_applicable=False,
    )
    run = PayRun.objects.create(company=company, period="2026-10", status=PayRun.Status.COMPLETED)
    PaySlip.objects.create(
        pay_run=run, company=company, employee=employee,
        gross=Decimal("1000.00"), net=Decimal("1000.00"),
    )
    BillOfEntry.objects.create(
        company=company, boe_number="BOE-010", boe_date=date(2026, 10, 1),
        bcd_amount=Decimal("25.00"), status=BillOfEntry.Status.COMPLETED,
    )
    result = perform_accounting_backfill(company, books.owner, dry_run=False)
    company.refresh_from_db()
    assert JournalEntry.objects.filter(
        company=company, source_type="PAY_RUN", source_id=run.id, purpose="PAYROLL",
        status=JournalEntry.Status.POSTED,
    ).exists(), result
    assert JournalEntry.objects.filter(
        company=company, source_type="WORK_ORDER", source_id=wo.id, purpose="RELEASE",
        status=JournalEntry.Status.POSTED,
    ).exists(), result
    assert JournalEntry.objects.filter(
        company=company, source_type="BILL_OF_ENTRY", purpose="COMPLETE",
        status=JournalEntry.Status.POSTED,
    ).exists(), result
    BooksHealthService.clear_gl_basis_cache(company)
    ready = bool(BooksHealthService._gl_basis_ready_uncached(company))
    assert company.accounting_enabled is ready
    assert not (result.get("skipped_by_period") or {})


def test_bug_acc_008_wdv_prorates_acquisition_and_disposal_months(books):
    """WDV uses days in service for the month the asset arrived and the month it left."""
    _key, charge_date, first_day = _charge_month_bounds()
    days = Decimal(charge_date.day)
    asset_acct, accum, expense = _asset_accounts(books.company)
    acquired = FixedAsset.objects.create(
        company=books.company, name="WDV late", asset_account=asset_acct,
        accumulated_depreciation_account=accum, depreciation_expense_account=expense,
        acquisition_date=charge_date - timedelta(days=1), acquisition_cost=Decimal("12000.00"),
        useful_life_months=60, method=FixedAsset.Method.WDV, wdv_annual_rate=Decimal("12.00"),
    )
    disposed = FixedAsset.objects.create(
        company=books.company, name="WDV sold", asset_account=asset_acct,
        accumulated_depreciation_account=accum, depreciation_expense_account=expense,
        acquisition_date=first_day, acquisition_cost=Decimal("12000.00"),
        useful_life_months=60, method=FixedAsset.Method.WDV, wdv_annual_rate=Decimal("12.00"),
        disposed_at=first_day + timedelta(days=9), status=FixedAsset.Status.ACTIVE,
    )
    monthly = (Decimal("12000") * Decimal("12") / Decimal("100") / Decimal("12")).quantize(Q2)
    late_expected = (monthly * Decimal(2) / days).quantize(Q2, rounding=ROUND_HALF_UP)
    sold_expected = (monthly * Decimal(10) / days).quantize(Q2, rounding=ROUND_HALF_UP)
    _depreciate_company_assets(books.company.id)
    purpose = f"DEPRECIATION-{charge_date:%Y-%m}"

    def debit_of(asset):
        entry = JournalEntry.objects.get(
            company=books.company, source_type="FIXED_ASSET", source_id=asset.id, purpose=purpose,
        )
        return JournalLine.objects.get(entry=entry, account=expense).debit

    assert debit_of(acquired) == late_expected
    assert debit_of(disposed) == sold_expected
    assert debit_of(acquired) != monthly


def test_bug_acc_015_depreciation_catchup_keeps_months_older_than_three(books):
    """The automatic window stays three months; older months are stored and posted on request."""
    _key, charge_date, _first = _charge_month_bounds()
    acquired_on = _month_end_back(charge_date, 4).replace(day=1)
    asset_acct, accum, expense = _asset_accounts(books.company)
    asset = FixedAsset.objects.create(
        company=books.company, name="SLM old", asset_account=asset_acct,
        accumulated_depreciation_account=accum, depreciation_expense_account=expense,
        acquisition_date=acquired_on, acquisition_cost=Decimal("12000.00"),
        useful_life_months=120, method=FixedAsset.Method.SLM,
    )
    _depreciate_company_assets(books.company.id)
    asset.refresh_from_db()
    window = {
        f"{_month_end_back(charge_date, step):%Y-%m}"
        for step in range(3)
    }
    older = [part for part in (asset.depreciation_catchup_months or "").split(",") if part]
    assert older, asset.depreciation_catchup_months
    assert set(older).isdisjoint(window)
    posted = set(JournalEntry.objects.filter(
        company=books.company, source_type="FIXED_ASSET", source_id=asset.id,
        status=JournalEntry.Status.POSTED,
    ).values_list("purpose", flat=True))
    assert {f"DEPRECIATION-{month}" for month in window} <= posted
    assert not any(f"DEPRECIATION-{month}" in posted for month in older)
    alerts = BooksHealthService.control_balances(books.company)["alerts"]
    assert any(alert["code"] == "DEPRECIATION_CATCHUP" for alert in alerts)
    backfill_depreciation_catchup(books.company.id)
    asset.refresh_from_db()
    assert asset.depreciation_catchup_months == ""
    posted_after = set(JournalEntry.objects.filter(
        company=books.company, source_type="FIXED_ASSET", source_id=asset.id,
        status=JournalEntry.Status.POSTED,
    ).values_list("purpose", flat=True))
    assert {f"DEPRECIATION-{month}" for month in older} <= posted_after


def test_bug_acc_009_ineligible_itc_and_scrap_do_not_use_disposal(books):
    """10.025 half-up is 10.03 on 5250 / 5450. Disposal 5600 and discount 5150 stay put."""
    supplier = make_supplier(books.company)
    invoice = __import__("purchases.models", fromlist=["PurchaseInvoice"]).PurchaseInvoice.objects.create(
        company=books.company, supplier=supplier, number="PI-009", invoice_date=date(2026, 10, 1),
    )
    input_gst = PostingService._account(books.company, "1310")
    payable = PostingService._account(books.company, "2100")
    PostingService.post(
        company=books.company, source_type="PURCHASE_INVOICE", source_id=invoice.id,
        purpose="COMPLETE", entry_date=invoice.invoice_date, user=books.owner,
        lines=[
            {"account": input_gst, "debit": Decimal("10.03")},
            {"account": payable, "credit": Decimal("10.03")},
        ],
    )
    invoice.cgst_total = Decimal("10.025")
    entry = PostingService.reclass_rejected_itc(invoice, user=books.owner)
    assert entry is not None
    debit_5250 = JournalLine.objects.get(entry=entry, account__code="5250").debit
    assert debit_5250 == Decimal("10.03")
    assert not entry.lines.filter(account__code="5600").exists()

    customer = make_customer(books.company, name="Scrap Buyer")
    from sales.models import SalesInvoice, SalesReturn

    sales_invoice = SalesInvoice.objects.create(
        company=books.company, customer=customer, number="SI-009", invoice_date=date(2026, 10, 1),
    )
    sales_return = SalesReturn.objects.create(
        company=books.company, customer=customer, sales_invoice=sales_invoice,
        number="SR-009", return_date=date(2026, 10, 2),
    )
    scrap = PostingService.post_sales_return_scrap(sales_return, Decimal("10.025"), user=books.owner)
    assert scrap is not None
    assert JournalLine.objects.get(entry=scrap, account__code="5450").debit == Decimal("10.03")
    assert not scrap.lines.filter(account__code="5600").exists()
    assert Account.objects.get(company=books.company, code="5150").name == "Settlement Discounts"


def test_bug_acc_003_master_edits_are_audited(books):
    """Each MCA Rule 11(g) master listed in the registry leaves an UPDATE audit event."""
    from accounts.models import CompanyUser
    from masters.models import PriceList, TaxRate, Unit
    from payments.models import BankAccount

    customer = make_customer(books.company, name="Audit Customer")
    supplier = make_supplier(books.company, name="Audit Supplier")
    product = make_product(books.company, name="Audit Product", sku="AUD-1")
    unit = Unit.objects.create(company=books.company, name="Piece", short_name="pc")
    tax = TaxRate.objects.create(company=books.company, name="GST 18", rate=Decimal("18.00"))
    prices = PriceList.objects.create(company=books.company, name="Retail")
    account = Account.objects.create(
        company=books.company, code="9991", name="Audit expense", type=Account.Type.EXPENSE,
        is_system=False,
    )
    bank = BankAccount.objects.create(company=books.company, name="Audit Bank")
    membership = CompanyUser.objects.get(company=books.company, user=books.staff)
    cases = {
        "Customer": ("/api/v1/customers/{id}/", customer.id, {"name": "Audit Customer 2"}),
        "Supplier": ("/api/v1/suppliers/{id}/", supplier.id, {"name": "Audit Supplier 2"}),
        "Product": ("/api/v1/products/{id}/", product.id, {"name": "Audit Product 2"}),
        "Unit": ("/api/v1/masters/units/{id}/", unit.id, {"name": "Pieces"}),
        "TaxRate": ("/api/v1/masters/tax-rates/{id}/", tax.id, {"name": "GST eighteen"}),
        "PriceList": ("/api/v1/masters/price-lists/{id}/", prices.id, {"name": "Retail 2"}),
        "Account": ("/api/v1/accounting/accounts/{id}/", account.id, {"name": "Audit expense 2"}),
        "BankAccount": ("/api/v1/payments/bank-accounts/{id}/", bank.id, {"name": "Audit Bank 2"}),
        "CompanyUser": ("/api/v1/company/users/{id}/", membership.id, {"role": "ACCOUNTANT"}),
    }
    missing = [name for name in MCA_RULE_11G_MASTERS if name not in cases]
    assert not missing, missing
    for name in MCA_RULE_11G_MASTERS:
        path, entity_id, payload = cases[name]
        before = AuditEvent.objects.filter(
            company=books.company, entity_type=name, entity_id=str(entity_id), action="UPDATE",
        ).count()
        resp = books.client.patch(path.format(id=entity_id), payload, format="json")
        assert resp.status_code == 200, (name, resp.status_code, resp.data)
        after = AuditEvent.objects.filter(
            company=books.company, entity_type=name, entity_id=str(entity_id), action="UPDATE",
        ).count()
        assert after == before + 1, name


def test_bug_acc_004_schedule_iii_headings_are_on_the_report(books):
    sheet = balance_sheet(books.company)
    profit = profit_and_loss(books.company)
    assert "schedule_iii" in sheet and "schedule_iii" in profit
    labels = set(_labels(sheet["schedule_iii"]))
    for heading in (
        "Non-current assets",
        "Current assets",
        "Non-current liabilities",
        "Current liabilities",
        "Tangible assets",
        "Long-term borrowings",
    ):
        assert heading in labels


def test_bug_acc_011_gl_recon_compares_signed_amounts(books):
    """A debit and a negative bank line are not the same amount. There is no match-anyway."""
    from payments.models import BankAccount, BankStatement, BankStatementLine

    cash = PostingService._account(books.company, "1100")
    equity = PostingService._account(books.company, "3100")
    out_entry = PostingService.post(
        company=books.company, source_type="TEST", source_id=11, purpose="OUT",
        entry_date=date(2026, 10, 1), user=books.owner,
        lines=[
            {"account": cash, "debit": Decimal("100.00")},
            {"account": equity, "credit": Decimal("100.00")},
        ],
    )
    in_entry = PostingService.post(
        company=books.company, source_type="TEST", source_id=12, purpose="IN",
        entry_date=date(2026, 10, 1), user=books.owner,
        lines=[
            {"account": equity, "debit": Decimal("100.00")},
            {"account": cash, "credit": Decimal("100.00")},
        ],
    )
    debit_line = out_entry.lines.get(account=cash)
    credit_line = in_entry.lines.get(account=cash)
    bank = BankAccount.objects.create(company=books.company, name="GL recon bank")
    statement = BankStatement.objects.create(company=books.company, bank_account=bank)
    opposite = BankStatementLine.objects.create(
        company=books.company, statement=statement, txn_date=date(2026, 10, 1),
        amount=Decimal("-100.00"), narration="out",
    )
    same = BankStatementLine.objects.create(
        company=books.company, statement=statement, txn_date=date(2026, 10, 1),
        amount=Decimal("-100.00"), narration="match credit",
    )
    session = BankReconSession.objects.create(
        company=books.company, account=cash, statement=statement,
    )
    detail = books.client.get(f"/api/v1/accounting/bank-recon-sessions/{session.id}/")
    assert detail.status_code == 200, detail.data
    refused = books.client.post(
        f"/api/v1/accounting/bank-recon-sessions/{session.id}/match/",
        {"journal_line": debit_line.id, "bank_statement_line": opposite.id},
        format="json",
    )
    assert refused.status_code == 400, refused.data
    debit_line.refresh_from_db()
    assert debit_line.bank_statement_line_id is None
    matched = books.client.post(
        f"/api/v1/accounting/bank-recon-sessions/{session.id}/match/",
        {"journal_line": credit_line.id, "bank_statement_line": same.id},
        format="json",
    )
    assert matched.status_code == 200, matched.data
    assert matched.data["match_kind"] == "gl_statement_line"
    page = (ROOT / "web/src/pages/phase/AccountingExtraPages.tsx").read_text(encoding="utf-8")
    assert "Match them anyway" not in page
    assert "Math.abs(toNumber(gl.debit)" not in page


def test_bug_acc_014_soft_close_requires_earlier_periods_closed(books):
    earlier = AccountingPeriod.objects.create(
        company=books.company, name="January", start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31), status=AccountingPeriod.Status.OPEN,
    )
    later = AccountingPeriod.objects.create(
        company=books.company, name="February", start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28), status=AccountingPeriod.Status.OPEN,
    )
    refused = books.client.post(f"/api/v1/accounting/periods/{later.id}/soft-close/")
    assert refused.status_code == 400, refused.data
    assert "January" in str(refused.data)
    later.refresh_from_db()
    assert later.status == AccountingPeriod.Status.OPEN
    closed = books.client.post(f"/api/v1/accounting/periods/{earlier.id}/soft-close/")
    assert closed.status_code == 200, closed.data
    earlier.refresh_from_db()
    assert earlier.status == AccountingPeriod.Status.SOFT_CLOSED


def test_bug_acc_016_books_close_control_is_company_ar(books):
    first = make_customer(books.company, name="Asha")
    second = make_customer(books.company, name="Bela")
    ar = PostingService._account(books.company, "1200")
    income = PostingService._account(books.company, "4100")
    PostingService.post(
        company=books.company, source_type="TEST", source_id=16, purpose="AR",
        entry_date=date(2026, 10, 1), user=books.owner,
        lines=[
            {"account": ar, "debit": Decimal("100.00"), "customer": first},
            {"account": ar, "debit": Decimal("50.00"), "customer": second},
            {"account": income, "credit": Decimal("150.00")},
        ],
    )
    health = BooksHealthService.control_balances(books.company)
    assert health["ar"]["gl"] == Decimal("150.00")
    page = (ROOT / "web/src/pages/phase/BooksCloseSection.tsx").read_text(encoding="utf-8")
    assert "customers[0]" not in page
    assert "books-health" in page


def test_bug_acc_012_year_close_ignores_work_orders_when_manufacturing_is_off(books):
    from manufacturing.models import Bom, WorkOrder

    company = books.company
    product = make_product(company, name="Assembly", sku="ASM-1")
    bom = Bom.objects.create(company=company, product=product, name="Assembly BOM", status=Bom.Status.ACTIVE)
    WorkOrder.objects.create(
        company=company, bom=bom, qty=Decimal("1.000"), status=WorkOrder.Status.RELEASED,
        released_at=date(2026, 6, 15),
    )
    AccountingPeriod.objects.create(
        company=company, name="FY 2026-27", start_date=date(2026, 4, 1),
        end_date=date(2027, 3, 31), status=AccountingPeriod.Status.OPEN,
    )

    def _clear():
        if hasattr(company, "_feature_flags_cache"):
            del company._feature_flags_cache

    with override_settings(ENABLE_MANUFACTURING=True):
        _clear()
        assert BooksHealthService.manufacturing_books_required(company) is True
        with pytest.raises(BusinessRuleError) as raised:
            close_financial_year(company, date(2027, 3, 31), books.owner)
        message = str(raised.value)
        assert (
            "DOCUMENT_MISSING_POSTING" in message
            or "OPEN_WIP" in message
            or "work order" in message.lower()
        )
    with override_settings(ENABLE_MANUFACTURING=False):
        _clear()
        assert BooksHealthService.manufacturing_books_required(company) is False
        health = BooksHealthService.control_balances(company)
        assert not any(alert["code"] == "DOCUMENT_MISSING_POSTING" for alert in health["alerts"])
        close_financial_year(company, date(2027, 3, 31), books.owner)


def test_bug_acc_017_gl_recon_points_at_the_other_product(books):
    from payments.models import BankAccount, BankStatement

    cash = PostingService._account(books.company, "1100")
    bank = BankAccount.objects.create(company=books.company, name="Other recon")
    statement = BankStatement.objects.create(company=books.company, bank_account=bank)
    session = BankReconSession.objects.create(
        company=books.company, account=cash, statement=statement,
    )
    detail = books.client.get(f"/api/v1/accounting/bank-recon-sessions/{session.id}/")
    assert detail.status_code == 200, detail.data
    assert detail.data["match_kind"] == "gl_statement_line"
    assert detail.data["other_recon_path"] == "/payments/reconciliation"
    page = (ROOT / "web/src/pages/phase/AccountingExtraPages.tsx").read_text(encoding="utf-8")
    assert 'to="/payments/reconciliation"' in page


def test_bug_acc_018_dispose_requires_confirm(books):
    asset_acct, accum, expense = _asset_accounts(books.company)
    asset = FixedAsset.objects.create(
        company=books.company, name="Confirm me", asset_account=asset_acct,
        accumulated_depreciation_account=accum, depreciation_expense_account=expense,
        acquisition_date=date(2026, 1, 1), acquisition_cost=Decimal("1000.00"),
        useful_life_months=12, depreciated_amount=Decimal("200.00"),
    )
    refused = books.client.post(f"/api/v1/accounting/fixed-assets/{asset.id}/dispose/", {}, format="json")
    assert refused.status_code == 400, refused.data
    assert not JournalEntry.objects.filter(
        company=books.company, source_type="FIXED_ASSET", source_id=asset.id, purpose="DISPOSAL",
    ).exists()
    before = JournalEntry.objects.filter(company=books.company).count()
    accepted = books.client.post(
        f"/api/v1/accounting/fixed-assets/{asset.id}/dispose/",
        {"confirm": True},
        format="json",
    )
    assert accepted.status_code == 200, accepted.data
    disposals = JournalEntry.objects.filter(
        company=books.company, source_type="FIXED_ASSET", source_id=asset.id, purpose="DISPOSAL",
    )
    assert disposals.count() == 1
    assert JournalEntry.objects.filter(company=books.company).count() == before + 1


def test_bug_acc_019_close_period_runs_books_then_gst(books):
    """One call hard-closes books, then soft-closes GST. It does not post a journal."""
    from reporting.models import GstReturnPeriod

    earlier = AccountingPeriod.objects.create(
        company=books.company, name="May", start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31), status=AccountingPeriod.Status.OPEN,
    )
    later = AccountingPeriod.objects.create(
        company=books.company, name="June", start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 30), status=AccountingPeriod.Status.OPEN,
    )
    journals = JournalEntry.objects.filter(company=books.company).count()
    blocked = books.client.post(f"/api/v1/accounting/periods/{later.id}/close-period/")
    assert blocked.status_code == 400, blocked.data
    assert "May" in str(blocked.data)
    later.refresh_from_db()
    assert later.status == AccountingPeriod.Status.OPEN
    june = GstReturnPeriod.objects.filter(company=books.company, period="2026-06").first()
    assert june is None or june.status != GstReturnPeriod.Status.SOFT_CLOSED
    done = books.client.post(f"/api/v1/accounting/periods/{earlier.id}/close-period/")
    assert done.status_code == 200, done.data
    earlier.refresh_from_db()
    assert earlier.status == AccountingPeriod.Status.CLOSED
    may = GstReturnPeriod.objects.get(company=books.company, period="2026-05")
    assert may.status == GstReturnPeriod.Status.SOFT_CLOSED
    assert done.data["books_closed"] is True
    assert done.data["gst_closed"] is True
    assert JournalEntry.objects.filter(company=books.company).count() == journals
    page = (ROOT / "web/src/pages/phase/PeriodsPage.tsx").read_text(encoding="utf-8")
    assert "closeAccountingAndGstPeriod" in page
    assert "softCloseGstPeriod" not in page
