from decimal import Decimal

import pytest

from accounting.models import AccountingPeriod, CostCenter, JournalEntry, JournalLine
from accounting.reports import balance_sheet, profit_and_loss, trial_balance
from accounting.services import BooksHealthService, PostingService, seed_chart_of_accounts
from core.exceptions import BusinessRuleError
from django.db.models import Sum
from payments.services import PaymentService
from purchases.models import PurchaseInvoice
from sales.models import SalesInvoice, SalesItem
from tests.conftest import create_draft_purchase, make_customer, make_product, make_supplier


def _si_with_tax_lines(company, customer, **kwargs):
    invoice = SalesInvoice.objects.create(
        company=company,
        customer=customer,
        status=SalesInvoice.Status.COMPLETED,
        invoice_date=kwargs.pop("invoice_date", "2026-04-01"),
        grand_total=kwargs.pop("grand_total", Decimal("118.00")),
        taxable_total=kwargs.pop("taxable_total", Decimal("100.00")),
        cgst_total=kwargs.pop("cgst_total", Decimal("9.00")),
        sgst_total=kwargs.pop("sgst_total", Decimal("9.00")),
        **kwargs,
    )
    product = make_product(company, sku=f"PH5-{invoice.id}")
    SalesItem.objects.create(
        company=company,
        invoice=invoice,
        product=product,
        quantity=Decimal("1"),
        unit_price=invoice.taxable_total,
        taxable_amount=invoice.taxable_total,
        cgst=invoice.cgst_total,
        sgst=invoice.sgst_total,
        igst=Decimal("0"),
        line_total=invoice.grand_total,
        gst_rate=Decimal("18"),
    )
    return invoice


@pytest.fixture
def books(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    return tenant_a


def test_balanced_entry_and_reverse(books):
    service = PostingService
    cash = service._account(books.company, "1100")
    equity = service._account(books.company, "3100")
    entry = service.post(
        company=books.company, source_type="TEST", source_id=1, purpose="OPENING",
        entry_date="2026-04-01", lines=[
            {"account": cash, "debit": Decimal("100.00")},
            {"account": equity, "credit": Decimal("100.00")},
        ], user=books.owner,
    )
    assert entry.status == JournalEntry.Status.POSTED
    assert sum(line.debit for line in entry.lines.all()) == sum(line.credit for line in entry.lines.all())
    reversal = service.reverse(entry, books.owner)
    assert entry.status == JournalEntry.Status.REVERSED
    assert reversal.lines.count() == 2


def test_ar_control_after_invoice_and_receipt(books):
    customer = make_customer(books.company)
    invoice = _si_with_tax_lines(books.company, customer)
    PostingService.post_sales_invoice(invoice, books.owner)
    receipt = PaymentService.create_receipt(
        company=books.company, customer=customer, amount=Decimal("118.00"), mode="CASH",
        receipt_date="2026-04-02", user=books.owner,
    )
    PaymentService.allocate_receipt(receipt=receipt, sales_invoice=invoice, amount=Decimal("118.00"), user=books.owner)
    health = BooksHealthService.control_balances(books.company)
    assert health["ar"] == {"gl": Decimal("0"), "ledger": Decimal("0"), "healthy": True}


def test_trial_balance_and_balance_sheet_equation(books):
    cash = PostingService._account(books.company, "1100")
    equity = PostingService._account(books.company, "3100")
    PostingService.post(
        company=books.company, source_type="TEST", source_id=2, purpose="OPENING",
        entry_date="2026-04-01", lines=[{"account": cash, "debit": 500}, {"account": equity, "credit": 500}],
    )
    tb = trial_balance(books.company, "2026-04-30")
    bs = balance_sheet(books.company, "2026-04-30")
    assert tb["balanced"] is True
    assert bs["equation_holds"] is True


def test_closed_period_blocks_posting(books):
    AccountingPeriod.objects.create(
        company=books.company, name="April", start_date="2026-04-01", end_date="2026-04-30",
        status=AccountingPeriod.Status.CLOSED,
    )
    with pytest.raises(BusinessRuleError, match="closed accounting period"):
        PostingService.post(
            company=books.company, source_type="TEST", source_id=3, purpose="CLOSED",
            entry_date="2026-04-01",
            lines=[
                {"account": PostingService._account(books.company, "1100"), "debit": 1},
                {"account": PostingService._account(books.company, "3100"), "credit": 1},
            ],
        )


def test_profit_and_loss_filters_by_cost_center(books):
    center = CostCenter.objects.create(company=books.company, code="OPS", name="Operations")
    PostingService.post(
        company=books.company, source_type="TEST", source_id=4, purpose="CC",
        entry_date="2026-04-01",
        lines=[
            {"account": PostingService._account(books.company, "5100"), "debit": 20, "cost_center": center},
            {"account": PostingService._account(books.company, "1100"), "credit": 20, "cost_center": center},
        ],
    )
    assert profit_and_loss(books.company, "2026-04-01", "2026-04-30", center.id)["expenses"] == Decimal("20")


def test_backfill_command_creates_journals(books):
    from accounting.models import JournalEntry
    from django.core.management import call_command

    customer = make_customer(books.company)
    invoice = _si_with_tax_lines(books.company, customer)
    JournalEntry.objects.filter(source_type="SALES_INVOICE", source_id=invoice.id).delete()
    assert not JournalEntry.objects.filter(source_type="SALES_INVOICE", source_id=invoice.id).exists()
    call_command("backfill_accounting_postings")
    assert JournalEntry.objects.filter(source_type="SALES_INVOICE", source_id=invoice.id).exists()


def test_accounting_bank_recon_match(books):
    from accounting.models import BankReconSession
    from payments.models import BankAccount, BankStatement, BankStatementLine, BankStatementStatus

    bank_gl = PostingService._account(books.company, "1500")
    equity = PostingService._account(books.company, "3100")
    entry = PostingService.post(
        company=books.company, source_type="TEST", source_id=99, purpose="BANK",
        entry_date="2026-04-01", user=books.owner,
        lines=[
            {"account": bank_gl, "debit": Decimal("500.00")},
            {"account": equity, "credit": Decimal("500.00")},
        ],
    )
    jl = entry.lines.filter(account=bank_gl).first()
    bank_acct = BankAccount.objects.create(company=books.company, name="HDFC")
    statement = BankStatement.objects.create(
        company=books.company, bank_account=bank_acct, status=BankStatementStatus.COMMITTED,
    )
    bs_line = BankStatementLine.objects.create(
        company=books.company, statement=statement, txn_date="2026-04-01",
        amount=Decimal("500.00"), narration="Deposit",
    )
    session = BankReconSession.objects.create(
        company=books.company, account=bank_gl, statement=statement,
        gl_balance=Decimal("500.00"), statement_balance=Decimal("500.00"),
    )
    resp = books.client.post(
        f"/api/v1/accounting/bank-recon-sessions/{session.id}/match/",
        {"journal_line": jl.id, "bank_statement_line": bs_line.id},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    jl.refresh_from_db()
    assert jl.bank_statement_line_id == bs_line.id


def test_purchase_complete_debits_inventory_not_purchases_expense(books):
    """BB-000322: perpetual inventory — purchase Complete debits 1400 Inventory,
    never the periodic 5100 Purchases expense (COGS is relieved on sale)."""
    product = make_product(books.company, sku="ACC-1400")
    supplier = make_supplier(books.company)
    pur = create_draft_purchase(
        books, supplier, [{"product": product.id, "quantity": "2", "unit_price": "100", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert books.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    entry = JournalEntry.objects.get(
        company=books.company, source_type="PURCHASE_INVOICE", source_id=pur["id"],
        purpose="COMPLETE", status=JournalEntry.Status.POSTED,
    )
    codes = set(entry.lines.values_list("account__code", flat=True))
    assert "1400" in codes
    assert "5100" not in codes
    inventory_debit = sum(
        line.debit for line in entry.lines.filter(account__code="1400")
    )
    assert inventory_debit == Decimal("200.00")


def test_purchase_round_off_posts_to_explicit_account(books):
    """BB-000322: paise round-off at Complete posts to the explicit 5500 Round
    Off account, not silently absorbed into the Inventory/tax legs."""
    product = make_product(books.company, sku="ACC-RND", gst_rate=Decimal("18"))
    supplier = make_supplier(books.company)
    pur = create_draft_purchase(
        books, supplier, [{"product": product.id, "quantity": "1", "unit_price": "99.99", "gst_rate": "18"}],
    )
    assert books.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    invoice = PurchaseInvoice.objects.get(pk=pur["id"])
    assert invoice.round_off != 0
    entry = JournalEntry.objects.get(
        company=books.company, source_type="PURCHASE_INVOICE", source_id=pur["id"],
        purpose="COMPLETE", status=JournalEntry.Status.POSTED,
    )
    round_off_lines = entry.lines.filter(account__code="5500")
    assert round_off_lines.exists()
    debit = sum(line.debit for line in entry.lines.all())
    credit = sum(line.credit for line in entry.lines.all())
    assert debit == credit


def test_books_health_missing_posting_gated_on_accounting_enabled(tenant_a):
    """BB-000322/BB-000364: with accounting OFF, PostingService.post() never
    posts anything — the missing-posting alert must not fire as false-positive
    noise for every completed document."""
    tenant_a.company.accounting_enabled = False
    tenant_a.company.save(update_fields=["accounting_enabled"])
    product = make_product(tenant_a.company, sku="ACC-GATE")
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a, supplier, [{"product": product.id, "quantity": "1", "unit_price": "100", "gst_rate": "0"}],
        purchase_type="NON_GST",
    )
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    assert not JournalEntry.objects.filter(
        company=tenant_a.company, source_type="PURCHASE_INVOICE", source_id=pur["id"],
    ).exists()
    health = BooksHealthService.control_balances(tenant_a.company)
    assert not any(a["code"] == "DOCUMENT_MISSING_POSTING" for a in health["alerts"])


def test_purchase_credit_note_rcm_reverses_rcm_liability(books):
    """BB-000336: a credit note against an RCM invoice reverses RCM payable /
    Input ITC (2240-2260 / 1310-1330), not normal Input GST/AP value legs."""
    product = make_product(books.company, sku="ACC-RCMCN", hsn_code="9983")
    supplier = make_supplier(books.company, name="URP-CN", gstin="")
    resp = books.client.post(
        "/api/v1/purchases/invoices/",
        {
            "supplier": supplier.id, "purchase_type": "GST", "is_reverse_charge": True,
            "items": [{"product": product.id, "quantity": "2", "unit_price": "1000", "gst_rate": "18"}],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert books.client.post(f"/api/v1/purchases/invoices/{resp.data['id']}/complete/").status_code == 200
    invoice = PurchaseInvoice.objects.get(pk=resp.data["id"])

    cn = books.client.post(
        "/api/v1/purchases/credit-notes/",
        {
            "supplier": supplier.id, "purchase_invoice": invoice.id, "reason": "CORRECTION_OF_INVOICE",
            "items": [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
        },
        format="json",
    )
    assert cn.status_code == 201, cn.data
    done = books.client.post(f"/api/v1/purchases/credit-notes/{cn.data['id']}/complete/")
    assert done.status_code == 200, done.data

    entry = JournalEntry.objects.get(
        company=books.company, source_type="PURCHASE_CREDIT_NOTE", source_id=cn.data["id"],
        purpose="COMPLETE", status=JournalEntry.Status.POSTED,
    )
    codes = set(entry.lines.values_list("account__code", flat=True))
    assert {"2240", "2250"}.issubset(codes)  # RCM payable reversed
    assert {"1310", "1320"}.issubset(codes)  # Input ITC reversed
    assert "2200" not in codes and "1300" not in codes


def test_fa_dispose_creates_gl_journal(books):
    """BB-000459: disposal writes NBV to 5600 Loss, never Depreciation 5300."""
    from accounting.models import FixedAsset, JournalEntry

    asset_acct = PostingService._account(books.company, "1600")
    accum_acct = PostingService._account(books.company, "1650")
    expense_acct = PostingService._account(books.company, "5300")
    asset = FixedAsset.objects.create(
        company=books.company, name="Laptop", asset_account=asset_acct,
        accumulated_depreciation_account=accum_acct, depreciation_expense_account=expense_acct,
        acquisition_date="2026-01-01", acquisition_cost=Decimal("12000.00"),
        useful_life_months=36, depreciated_amount=Decimal("2000.00"),
    )
    resp = books.client.post(f"/api/v1/accounting/fixed-assets/{asset.id}/dispose/")
    assert resp.status_code == 200, resp.data
    entry = JournalEntry.objects.get(
        company=books.company, source_type="FIXED_ASSET", source_id=asset.id, purpose="DISPOSAL",
    )
    codes = set(entry.lines.values_list("account__code", flat=True))
    assert "5600" in codes  # Loss on Disposal for NBV 10000
    assert "5300" not in codes
    loss_debit = JournalLine.objects.filter(entry=entry, account__code="5600").aggregate(
        t=Sum("debit")
    )["t"]
    assert loss_debit == Decimal("10000.00")
    asset.refresh_from_db()
    assert asset.status == FixedAsset.Status.DISPOSED


def test_fa_dispose_with_proceeds_gain(books):
    """BB-000459: proceeds > NBV credits Gain 5700."""
    from accounting.models import FixedAsset, JournalEntry

    seed_chart_of_accounts(books.company, books.owner)
    asset_acct = PostingService._account(books.company, "1600")
    accum_acct = PostingService._account(books.company, "1650")
    expense_acct = PostingService._account(books.company, "5300")
    asset = FixedAsset.objects.create(
        company=books.company, name="Desk", asset_account=asset_acct,
        accumulated_depreciation_account=accum_acct, depreciation_expense_account=expense_acct,
        acquisition_date="2026-01-01", acquisition_cost=Decimal("1000.00"),
        useful_life_months=12, depreciated_amount=Decimal("200.00"),
    )
    # NBV=800; proceeds=1000 → gain 200
    resp = books.client.post(
        f"/api/v1/accounting/fixed-assets/{asset.id}/dispose/",
        {"proceeds": "1000.00"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    entry = JournalEntry.objects.get(
        company=books.company, source_type="FIXED_ASSET", source_id=asset.id, purpose="DISPOSAL",
    )
    codes = set(entry.lines.values_list("account__code", flat=True))
    assert "5700" in codes
    assert "5300" not in codes
    assert "1100" in codes
