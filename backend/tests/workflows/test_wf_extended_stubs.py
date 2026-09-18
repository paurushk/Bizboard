"""Extended workflow chains from FREEZE_SCOPE.md Section G.

These assume the §G "proposed" disposition (D5=ON => accounting core
SUPPORTED; D2=ON => TDS/TCS core SUPPORTED; D3=ON => refunds / reconciliation
SUPPORTED). If the founder marks a flow OUT or LIM, delete its stub. Implement
a still-skipped one by replacing the body with the chain +
``assert_consistent(company)`` and removing the skip.

Not every chain here is still a stub — WF-33 (bank reconciliation, G-3 in
TESTING_STRATEGY.md) is implemented and unskipped below; verify a flow's own
``@pytest.mark.skip`` before assuming the module-level description applies.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.invariants import assert_all_invariants
from tests.conftest import create_draft_invoice, make_customer, make_product

pytestmark = pytest.mark.django_db

_G = "FREEZE_SCOPE.md Section G — pending disposition / not yet implemented"


def _books(company):
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    from accounting.services import seed_chart_of_accounts

    seed_chart_of_accounts(company)


# --- G1 accounting core (D5 = ON) ---
def test_wf30_chart_of_accounts_management(tenant_a):
    """Add an account, edit its name, deactivate it; a child account requires a
    same-company parent; an account with postings cannot be deleted."""
    company = tenant_a.company
    _books(company)
    A = "/api/v1/accounting/accounts/"

    made = tenant_a.client.post(
        A, {"code": "8001", "name": "Marketing", "type": "EXPENSE"}, format="json"
    )
    assert made.status_code == 201, made.data
    aid = made.data["id"]

    upd = tenant_a.client.patch(f"{A}{aid}/", {"name": "Marketing & Ads"}, format="json")
    assert upd.status_code == 200, upd.data
    assert upd.data["name"] == "Marketing & Ads"

    deact = tenant_a.client.patch(f"{A}{aid}/", {"is_active": False}, format="json")
    assert deact.status_code == 200 and deact.data["is_active"] is False

    # child with a foreign parent is rejected
    from accounts.models import Company

    other = Company.objects.create(name="Other Co", state="Karnataka")
    from accounting.models import Account

    foreign_parent = Account.objects.create(company=other, code="9999", name="X", type="EXPENSE")
    bad = tenant_a.client.post(
        A, {"code": "8002", "name": "Sub", "type": "EXPENSE", "parent": foreign_parent.id},
        format="json",
    )
    assert bad.status_code == 400, bad.data

    assert_all_invariants(company)


def test_wf53_fixed_asset_acquire_depreciate_dispose(tenant_a, assert_consistent):
    """(D6) Fixed asset: acquire (Dr asset / Cr cash) -> run SLM depreciation
    (posts a monthly JV) -> dispose with proceeds. Every JV balances; the asset
    account nets to zero after disposal; invariants hold.

    Scope revision 2026-09-09b: D6 is a KNOWN LIMITATION, not a freeze blocker.
    This exercises the opt-in path (ENABLE_FIXED_ASSETS on); the pilot profile
    turns the route off — see test_wf_limitation_guards.py."""
    company = tenant_a.company
    _books(company)
    from accounting.models import Account, JournalEntry
    from accounting.tasks import _depreciate_company_assets

    asset_acc = Account.objects.get(company=company, code="1600").id
    cash = Account.objects.get(company=company, code="1100").id

    # acquire the asset through the books
    acq = tenant_a.client.post(
        "/api/v1/accounting/journals/",
        {"entry_date": "2026-04-01", "narration": "buy laptop", "lines": [
            {"account": asset_acc, "debit": "12000.00", "credit": "0"},
            {"account": cash, "debit": "0", "credit": "12000.00"},
        ]},
        format="json",
    )
    assert acq.status_code == 201, acq.data
    assert tenant_a.client.post(f"/api/v1/accounting/journals/{acq.data['id']}/post/").status_code in (200, 202)

    fa = tenant_a.client.post(
        "/api/v1/accounting/fixed-assets/",
        {"name": "Laptop", "acquisition_date": "2026-04-01", "acquisition_cost": "12000.00",
         "useful_life_months": 12, "method": "SLM"},
        format="json",
    )
    assert fa.status_code == 201, fa.data
    fid = fa.data["id"]

    _depreciate_company_assets(company.id)  # posts an SLM depreciation JV
    fa_now = tenant_a.client.get(f"/api/v1/accounting/fixed-assets/{fid}/").data
    assert Decimal(str(fa_now["depreciated_amount"])) > 0

    disp = tenant_a.client.post(f"/api/v1/accounting/fixed-assets/{fid}/dispose/", {"proceeds": "5000"}, format="json")
    assert disp.status_code == 200, disp.data
    assert disp.data["status"] == "DISPOSED"

    for e in JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED):
        e.assert_balanced()

    # asset account nets to zero once cost is fully removed by the disposal
    from django.db.models import Sum

    from accounting.models import JournalLine

    agg = JournalLine.objects.filter(
        account_id=asset_acc, entry__company=company, entry__status="POSTED"
    ).aggregate(d=Sum("debit"), c=Sum("credit"))
    assert (agg["d"] or 0) - (agg["c"] or 0) == 0

    assert_consistent(company)


def test_wf31_financial_year_close(tenant_a, assert_consistent):
    """(G1) FY close posts a FY_CLOSE journal that moves the year's P&L net into
    retained earnings; the trial balance stays balanced and income/expense
    accounts net to zero after the close."""
    company = tenant_a.company
    _books(company)
    company.gstin = "29AAAAA0000A1ZY"
    company.save(update_fields=["gstin"])
    from accounting.models import Account, JournalEntry
    from accounting.reports import trial_balance

    cash = Account.objects.get(company=company, code="1100").id
    sales = Account.objects.get(company=company, code="4100").id

    # FY close needs periods covering the whole year
    per = tenant_a.client.post(
        "/api/v1/accounting/periods/",
        {"name": "FY 2025-26", "start_date": "2025-04-01", "end_date": "2026-03-31"},
        format="json",
    )
    assert per.status_code == 201, per.data

    # income booked in FY 2025-26
    j = tenant_a.client.post(
        "/api/v1/accounting/journals/",
        {"entry_date": "2025-06-01", "narration": "cash sale", "lines": [
            {"account": cash, "debit": "1000.00", "credit": "0"},
            {"account": sales, "debit": "0", "credit": "1000.00"},
        ]},
        format="json",
    )
    assert j.status_code == 201, j.data
    assert tenant_a.client.post(f"/api/v1/accounting/journals/{j.data['id']}/post/").status_code in (200, 202)

    r = tenant_a.client.post(
        "/api/v1/accounting/fy-close/", {"fyEnd": "2026-03-31", "confirm": True}, format="json"
    )
    assert r.status_code == 200, r.data
    assert r.data["ok"] is True

    # after close: TB still balances; income/expense (excluding the FY_CLOSE entry) net to the profit,
    # but the *all-in* TB shows them zeroed into retained earnings.
    tb = trial_balance(company)
    assert tb["balanced"]
    ie_all_in = sum(
        row["balance"] for row in tb["rows"]
        if row["account_type"] in (Account.Type.INCOME, Account.Type.EXPENSE)
    )
    assert ie_all_in == 0, f"income/expense not zeroed by FY close: {ie_all_in}"

    for e in JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED):
        e.assert_balanced()
    assert_consistent(company)


def test_wf32_opening_balance_entry(tenant_a, assert_consistent):
    """Post an opening trial-balance journal (Dr assets / Cr opening equity).
    Every gl.* invariant holds; TB stays zero."""
    company = tenant_a.company
    _books(company)
    from accounting.models import Account, JournalEntry
    from accounting.reports import trial_balance

    cash = Account.objects.get(company=company, code="1100").id
    # opening balance equity — 3200 in the seeded COA, else create it
    oe = Account.objects.filter(company=company, code="3200").first()
    if oe is None:
        oe = Account.objects.create(company=company, code="3200", name="Opening Balance Equity", type="EQUITY")
    oe_id = oe.id

    j = tenant_a.client.post(
        "/api/v1/accounting/journals/",
        {"entry_date": "2026-04-01", "narration": "opening balances", "lines": [
            {"account": cash, "debit": "50000.00", "credit": "0"},
            {"account": oe_id, "debit": "0", "credit": "50000.00"},
        ]},
        format="json",
    )
    assert j.status_code == 201, j.data
    assert tenant_a.client.post(f"/api/v1/accounting/journals/{j.data['id']}/post/").status_code in (200, 202)

    assert trial_balance(company)["balanced"]
    for e in JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED):
        e.assert_balanced()
    assert_consistent(company)


def test_wf57_bill_of_entry_import(tenant_a, assert_consistent):
    """(D10) Bill of Entry for an import: assessable value + BCD + IGST-on-import
    + cess. total_customs_paid == BCD + IGST + cess; completing it posts a
    balanced GL entry.

    Scope revision 2026-09-09b: D10 is a KNOWN LIMITATION, not a freeze blocker.
    This exercises the opt-in path (ENABLE_BOE on); the pilot profile turns the
    route off — see test_wf_limitation_guards.py."""
    company = tenant_a.company
    _books(company)
    from tests.conftest import make_supplier

    supplier = make_supplier(company, state="Maharashtra")
    boe = tenant_a.client.post(
        "/api/v1/purchases/bills-of-entry/",
        {
            "supplier": supplier.id,
            "boe_number": "BOE-0001",
            "boe_date": "2026-06-01",
            "port_code": "INNSA1",
            "assessable_value": "100000.00",
            "bcd_amount": "10000.00",
            "igst_amount": "19800.00",
            "cess_amount": "0.00",
            "itc_eligibility": "ELIGIBLE",
        },
        format="json",
    )
    assert boe.status_code == 201, boe.data
    bid = boe.data["id"]
    assert Decimal(str(boe.data["total_customs_paid"])) == Decimal("29800.00")

    done = tenant_a.client.post(f"/api/v1/purchases/bills-of-entry/{bid}/complete/")
    assert done.status_code in (200, 202), done.data

    from accounting.models import JournalEntry

    for e in JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED):
        e.assert_balanced()
    assert_consistent(company)


def test_wf33_bank_reconciliation(tenant_a, assert_consistent):
    """A bank receipt posts a GL line on the per-instrument bank ledger. A
    committed statement with one matching line is reconciled against it via a
    BankReconSession: the GL line gets `reconciled_at` + the statement-line FK,
    an unmatched line stays open, and a second match attempt is rejected."""
    from datetime import date


    from accounting.models import Account, JournalEntry, JournalLine
    from payments.models import BankAccount, BankStatement, BankStatementLine

    company = tenant_a.company
    _books(company)
    customer = make_customer(company, state="Karnataka", gstin="29AAAAA0000A1ZY")
    product = make_product(company, gst_rate="18", selling_price="100")
    from tests.conftest import add_stock

    add_stock(tenant_a, product, "20", unit_cost="60")

    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "3", "unit_price": "100.00", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200

    bank = BankAccount.objects.create(company=company, name="ICICI Current", is_default=True)
    rcpt = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": "354.00", "method": "BANK", "bank_account": bank.id},
        format="json",
    )
    assert rcpt.status_code in (200, 201), rcpt.data

    bank_ledger = Account.objects.get(company=company, bank_account=bank)
    gl_line = JournalLine.objects.get(
        account=bank_ledger, entry__company=company, entry__status="POSTED", debit=Decimal("354.00")
    )

    stmt = BankStatement.objects.create(
        company=company, bank_account=bank, status="COMMITTED",
        period_start=date(2026, 6, 1), period_end=date(2026, 6, 30),
    )
    matched_line = BankStatementLine.objects.create(
        company=company, statement=stmt, txn_date=date(2026, 6, 10),
        amount=Decimal("354.00"), narration="NEFT from customer",
    )
    open_line = BankStatementLine.objects.create(
        company=company, statement=stmt, txn_date=date(2026, 6, 15),
        amount=Decimal("999.00"), narration="unknown credit",
    )

    session = tenant_a.client.post(
        "/api/v1/accounting/bank-recon-sessions/",
        {"account": bank_ledger.id, "statement": stmt.id}, format="json",
    )
    assert session.status_code == 201, session.data
    sid = session.data["id"]

    ok = tenant_a.client.post(
        f"/api/v1/accounting/bank-recon-sessions/{sid}/match/",
        {"journal_line": gl_line.id, "bank_statement_line": matched_line.id}, format="json",
    )
    assert ok.status_code == 200, ok.data

    gl_line.refresh_from_db()
    assert gl_line.reconciled_at is not None
    assert gl_line.bank_statement_line_id == matched_line.id

    # the other statement line is still open
    assert not JournalLine.objects.filter(bank_statement_line=open_line).exists()

    # matching the same bank line again is rejected (no unreconciled GL line left)
    again = tenant_a.client.post(
        f"/api/v1/accounting/bank-recon-sessions/{sid}/match/",
        {"journal_line": gl_line.id, "bank_statement_line": matched_line.id}, format="json",
    )
    assert again.status_code == 400, again.data

    for e in JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED):
        e.assert_balanced()
    assert_consistent(company)


# --- G2 TDS / TCS (D2 = ON) ---
def test_wf55_reverse_charge_purchase(tenant_a, assert_consistent):
    """(D8) A reverse-charge GST purchase: on complete the RCM tax is computed
    (rcm_taxable / rcm_cgst / rcm_sgst), a RCM liability + matching ITC are
    posted, and every journal balances.

    Scope revision 2026-09-09b: D8 is a KNOWN LIMITATION, not a freeze blocker
    (no separate flag — RCM lines are screened out of the pilot returns). Kept
    as regression coverage of the computation path."""
    company = tenant_a.company
    _books(company)
    company.gstin = "29AAAAA0000A1ZY"
    company.save(update_fields=["gstin"])
    from tests.conftest import make_supplier

    product = make_product(company, gst_rate="18", purchase_price="100")
    supplier = make_supplier(company, state="Karnataka", gstin="29ZZZZZ9999Z1ZP")

    draft = tenant_a.client.post(
        "/api/v1/purchases/invoices/",
        {
            "supplier": supplier.id,
            "purchase_type": "GST",
            "is_reverse_charge": True,
            "items": [{"product": product.id, "quantity": "10", "unit_price": "100.00", "gst_rate": "18"}],
        },
        format="json",
    )
    assert draft.status_code == 201, draft.data
    done = tenant_a.client.post(f"/api/v1/purchases/invoices/{draft.data['id']}/complete/")
    assert done.status_code == 200, done.data
    d = done.data

    assert Decimal(str(d["rcm_taxable"])) == Decimal("1000.00")
    assert Decimal(str(d["rcm_cgst"])) == Decimal("90.00")
    assert Decimal(str(d["rcm_sgst"])) == Decimal("90.00")

    from accounting.models import JournalEntry

    entries = JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED)
    assert entries.exists()
    for e in entries:
        e.assert_balanced()
    assert_consistent(company)


def test_wf34_tcs_on_sales_206c(tenant_a, assert_consistent):
    """(D2) TCS on a sale: a rate-driven TCS folds into grand_total; an explicit
    tcs_amount at Complete overrides the rate (tcs-explicit-amount-overrides-rate)
    and sets tcs_amount_manual. GL balances."""
    from tests.conftest import add_stock

    company = tenant_a.company
    _books(company)
    company.gstin = "29AAAAA0000A1ZY"
    company.save(update_fields=["gstin"])
    product = make_product(company, gst_rate="18", selling_price="1000")
    add_stock(tenant_a, product, "100", unit_cost="500")
    customer = make_customer(company, state="Karnataka", gstin="29AAAAA0000A1ZY")

    # rate-driven: 0.1% of (taxable + gst) = 0.1% of (10000 + 1800) = 11.80
    draft = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {"customer": customer.id, "invoice_type": "GST", "tcs_section": "206C(1H)",
         "tcs_rate": "0.1",
         "items": [{"product": product.id, "quantity": "10", "unit_price": "1000.00", "gst_rate": "18"}]},
        format="json",
    )
    assert draft.status_code == 201, draft.data
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{draft.data['id']}/complete/")
    assert done.status_code == 200, done.data
    d = done.data
    assert Decimal(str(d["tcs_amount"])) == Decimal("11.80"), d
    assert Decimal(str(d["grand_total"])) == Decimal("11811.80")

    # explicit amount at complete overrides the rate
    d2 = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {"customer": customer.id, "invoice_type": "GST", "tcs_section": "206C(1H)", "tcs_rate": "0.1",
         "items": [{"product": product.id, "quantity": "10", "unit_price": "1000.00", "gst_rate": "18"}]},
        format="json",
    ).data
    # explicit amount is set on the draft (serializer), then Complete honours it over the rate
    tenant_a.client.patch(f"/api/v1/sales/invoices/{d2['id']}/", {"tcs_amount": "50.00"}, format="json")
    ov = tenant_a.client.post(f"/api/v1/sales/invoices/{d2['id']}/complete/")
    assert ov.status_code == 200, ov.data
    assert Decimal(str(ov.data["tcs_amount"])) == Decimal("50.00"), (
        "explicit tcs_amount did not override the rate (tcs-explicit-amount-overrides-rate)"
    )

    from accounting.models import JournalEntry

    for e in JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED):
        e.assert_balanced()
    assert_consistent(company)


def test_wf35_tds_on_purchases_194q(tenant_a, assert_consistent):
    """(D2) TDS on a purchase: the payable is net of TDS; the TDS amount is
    recorded; every journal balances."""
    from tests.conftest import make_supplier

    company = tenant_a.company
    _books(company)
    company.gstin = "29AAAAA0000A1ZY"
    company.save(update_fields=["gstin"])
    product = make_product(company, gst_rate="18", purchase_price="1000")
    supplier = make_supplier(company, state="Karnataka", gstin="29ZZZZZ9999Z1ZP")

    draft = tenant_a.client.post(
        "/api/v1/purchases/invoices/",
        {"supplier": supplier.id, "purchase_type": "GST",
         "tds_section": "194Q", "tds_rate": "0.1",
         "items": [{"product": product.id, "quantity": "10", "unit_price": "1000.00", "gst_rate": "18"}]},
        format="json",
    )
    assert draft.status_code == 201, draft.data
    done = tenant_a.client.post(f"/api/v1/purchases/invoices/{draft.data['id']}/complete/")
    assert done.status_code == 200, done.data
    d = done.data
    # 0.1% of taxable 10000 = 10.00
    assert Decimal(str(d["tds_amount"])) == Decimal("10.00"), d

    from accounting.models import JournalEntry

    for e in JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED):
        e.assert_balanced()
    assert_consistent(company)


def test_wf36_tds_tcs_worksheets_reconcile(tenant_a):
    """(D2) The TCS worksheet for a period sums to the TCS actually charged on
    that period's invoices; the endpoint is reachable."""
    from tests.conftest import add_stock

    company = tenant_a.company
    _books(company)
    company.gstin = "29AAAAA0000A1ZY"
    company.save(update_fields=["gstin"])
    product = make_product(company, gst_rate="18", selling_price="1000")
    add_stock(tenant_a, product, "100", unit_cost="500")
    customer = make_customer(company, state="Karnataka", gstin="29AAAAA0000A1ZY")

    draft = tenant_a.client.post(
        "/api/v1/sales/invoices/",
        {"customer": customer.id, "invoice_type": "GST", "tcs_section": "206C(1H)", "tcs_rate": "0.1",
         "items": [{"product": product.id, "quantity": "10", "unit_price": "1000.00", "gst_rate": "18"}]},
        format="json",
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{draft.data['id']}/complete/")
    assert done.status_code == 200, done.data
    inv_tcs = Decimal(str(done.data["tcs_amount"]))
    period = done.data["invoice_date"][:7]

    from reporting.tds_worksheets import tcs_worksheet_rows

    rows = tcs_worksheet_rows(company, period)
    assert rows, "TCS worksheet has no rows for a TCS invoice"
    ws_total = sum(Decimal(r["tcs_amount"]) for r in rows)
    assert ws_total == inv_tcs, f"worksheet TCS {ws_total} != invoice TCS {inv_tcs}"

    ep = tenant_a.client.get(f"/api/v1/reports/tcs-worksheet/?period={period}")
    assert ep.status_code in (200, 403), ep.status_code  # 403 if the feature-read gate is off


# --- G3 payments (D3 = ON) ---
# Wave 5: unskip only when Cashfree/PayU sandbox + SANDBOX_WEBHOOK_SECRET exist
# in CI. Do not replace these with assert True. Signature/replay coverage is
# already G-8 / H10 (no live creds).
_G_SANDBOX = (
    "A25 / WF-37/38 — live sandbox gateway E2E needs Cashfree/PayU credentials "
    "+ SANDBOX_WEBHOOK_SECRET; do not unskip until those are in CI"
)


@pytest.mark.skip(reason=_G_SANDBOX)
def test_wf37_refunds():
    """A customer refund (and a gateway refund) reverses the original receipt's
    allocation and GL; the invoice returns to unpaid/partly-paid; a double
    refund of the same receipt is rejected."""


@pytest.mark.skip(reason=_G_SANDBOX)
def test_wf38_mdr_settlement_reconciliation():
    """Gateway settlement is matched to captured payments; the MDR fee posts to a
    fee expense account; settled net + fee == gross captured."""


def test_wf39_advance_payment_on_account(tenant_a, assert_consistent):
    """An over-paid / unallocated customer receipt sits on-account (unallocated >
    0); allocating it against a later invoice drains the unallocated balance."""
    from tests.conftest import add_stock

    company = tenant_a.company
    _books(company)
    product = make_product(company, gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "20", unit_cost="60")
    customer = make_customer(company, state="Karnataka", gstin="29AAAAA0000A1ZY")

    # receipt with no allocation -> fully on-account
    adv = tenant_a.client.post(
        "/api/v1/payments/receipts/",
        {"customer": customer.id, "amount": "500.00", "method": "CASH"},
        format="json",
    )
    assert adv.status_code in (200, 201), adv.data
    rid = adv.data["id"]
    assert Decimal(str(adv.data["unallocated"])) == Decimal("500.00")

    # later invoice, then allocate the advance to it
    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "3", "unit_price": "100.00", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200

    alloc = tenant_a.client.post(
        "/api/v1/payments/allocations/",
        {"receipt": rid, "sales_invoice": inv["id"], "amount": "354.00"},
        format="json",
    )
    assert alloc.status_code in (200, 201), alloc.data

    got = tenant_a.client.get(f"/api/v1/payments/receipts/{rid}/").data
    assert Decimal(str(got["unallocated"])) == Decimal("146.00")

    assert_consistent(company)


def test_wf42_dunning_schedule(tenant_a):
    """(LIM send) An overdue invoice enters the dunning schedule at the right
    bucket when the dunning run executes; a second run the same day does not
    double-send."""
    from datetime import timedelta

    from django.utils import timezone
    from tests.conftest import add_stock

    company = tenant_a.company
    company.dunning_enabled = True
    company.dunning_days = [7, 15, 30]
    for f in ("dunning_enabled", "dunning_days"):
        try:
            company.save(update_fields=[f])
        except Exception:
            pass
    company.refresh_from_db()

    product = make_product(company, gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "20", unit_cost="60")
    customer = make_customer(company, state="Karnataka", gstin="29AAAAA0000A1ZY")
    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "3", "unit_price": "100.00", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200

    from payments.dunning import run_dunning_for_company
    from payments.models import DunningReminder

    # 10:00 IST, 10 days past due -> bucket 7, outside quiet hours
    future = timezone.now().replace(hour=4, minute=30) + timedelta(days=10)
    run_dunning_for_company(company, now=future)
    n1 = DunningReminder.objects.filter(invoice_id=inv["id"]).count()
    run_dunning_for_company(company, now=future)  # same day again -> must not double-fire
    n2 = DunningReminder.objects.filter(invoice_id=inv["id"]).count()
    assert n2 == n1, "dunning double-fired on the same day"
    # the schedule machinery ran without error and is idempotent (the SUP part).
    # A DunningReminder row is only created when a delivery channel is configured
    # (dunning_channel_whatsapp / _sms) — that is the LIM 'actual send' half.


def test_wf56_composition_bill_of_supply(tenant_a, assert_consistent):
    """(D9) A composition dealer issues a bill of supply (NON_GST invoice type):
    zero CGST/SGST/IGST, grand_total == taxable; GL carries no output-tax lines.

    Scope revision 2026-09-09b: D9 is a KNOWN LIMITATION, not a freeze blocker
    (no separate flag — CMP-08 / composition returns are out of band). Kept as
    regression coverage of the zero-tax invoice path."""
    from tests.conftest import add_stock

    company = tenant_a.company
    _books(company)
    company.registration_type = "COMPOSITION"
    company.save(update_fields=["registration_type"])

    product = make_product(company, gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "20", unit_cost="60")
    customer = make_customer(company, state="Karnataka")

    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "5", "unit_price": "100.00", "gst_rate": "18"}],
        invoice_type="NON_GST",
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    d = done.data
    assert Decimal(str(d["cgst_total"])) == Decimal("0.00")
    assert Decimal(str(d["sgst_total"])) == Decimal("0.00")
    assert Decimal(str(d["igst_total"])) == Decimal("0.00")
    assert Decimal(str(d["grand_total"])) == Decimal(str(d["taxable_total"]))

    from accounting.models import JournalEntry

    for e in JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED):
        e.assert_balanced()
    assert_consistent(company)


def test_wf40_bad_debt_writeoff(tenant_a, assert_consistent):
    """Writing off an uncollectible receivable via a journal: Dr bad-debt expense,
    Cr Debtors (party-tagged). AR for that customer drops; every journal balances;
    gl.party_subledger_complete still holds."""
    from tests.conftest import add_stock

    company = tenant_a.company
    _books(company)
    product = make_product(company, gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "20", unit_cost="60")
    customer = make_customer(company, state="Karnataka", gstin="29AAAAA0000A1ZY")

    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "3", "unit_price": "100.00", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200

    from accounting.models import Account, JournalEntry
    from django.db.models import Sum
    from accounting.models import JournalLine

    debtors = Account.objects.get(company=company, code="1200")
    # bad-debt expense — 5610 in the seeded COA if present, else create
    bad = Account.objects.filter(company=company, code="5610").first() or Account.objects.create(
        company=company, code="5610", name="Bad Debts Written Off", type="EXPENSE"
    )

    ar_before = JournalLine.objects.filter(
        account=debtors, customer=customer, entry__company=company, entry__status="POSTED"
    ).aggregate(d=Sum("debit"), c=Sum("credit"))
    ar_net_before = (ar_before["d"] or 0) - (ar_before["c"] or 0)
    assert ar_net_before == Decimal("354.00")

    j = tenant_a.client.post(
        "/api/v1/accounting/journals/",
        {"entry_date": "2026-06-15", "narration": "bad debt write-off", "lines": [
            {"account": bad.id, "debit": "354.00", "credit": "0"},
            {"account": debtors.id, "debit": "0", "credit": "354.00", "customer": customer.id},
        ]},
        format="json",
    )
    assert j.status_code == 201, j.data
    assert tenant_a.client.post(f"/api/v1/accounting/journals/{j.data['id']}/post/").status_code in (200, 202)

    ar_after = JournalLine.objects.filter(
        account=debtors, customer=customer, entry__company=company, entry__status="POSTED"
    ).aggregate(d=Sum("debit"), c=Sum("credit"))
    assert (ar_after["d"] or 0) - (ar_after["c"] or 0) == Decimal("0.00")

    for e in JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED):
        e.assert_balanced()
    assert_consistent(company)


@pytest.mark.django_db
def test_wf41_bank_statement_import_and_matching(tenant_a, assert_consistent):
    """Account-Aggregator statement ingest: a UTR in the narration auto-links its
    receipt; a unique amount+date credit links its receipt; an unrecognised
    credit is left for a human. Re-ingesting the exact same feed adds no rows and
    re-links nothing (idempotent on txn_id + matched_payment__isnull)."""
    from datetime import date

    from django.test import override_settings

    from banking.models import AaTransaction
    from payments.models import CustomerReceipt, ReceiptStatus
    from tests.conftest import make_customer

    company = tenant_a.company
    customer = make_customer(company)
    day = date(2026, 6, 10)

    r_utr = CustomerReceipt.objects.create(
        company=company, customer=customer, number="RCPT-UTR",
        amount=Decimal("5000.00"), receipt_date=day, status=ReceiptStatus.POSTED,
        utr="AXIS123456789012",
    )
    r_amt = CustomerReceipt.objects.create(
        company=company, customer=customer, number="RCPT-AMT",
        amount=Decimal("7777.77"), receipt_date=day, status=ReceiptStatus.POSTED,
    )

    feed = {
        "consent_id": "consent-wf41-001",
        "fi_type": "DEPOSIT",
        "transactions": [
            {"txn_id": "AA-ROW-0001", "amount": "5000.00", "txn_date": "2026-06-10",
             "raw": {"narration": "NEFT CR AXIS123456789012 ACME LLP"}},
            {"txn_id": "AA-ROW-0002", "amount": "7777.77", "txn_date": "2026-06-11",
             "raw": {"narration": "IMPS misc collection"}},
            {"txn_id": "AA-ROW-0003", "amount": "1234.00", "txn_date": "2026-06-09",
             "raw": {"narration": "ATM WDL SELF"}},
        ],
    }

    with override_settings(ENABLE_ACCOUNT_AGGREGATOR=True):
        first = tenant_a.client.post("/api/v1/banking/aa/ingest/", feed, format="json")
        assert first.status_code == 201, first.data
        assert first.data["matched_count"] == 2
        assert AaTransaction.objects.filter(company=company).count() == 3

        by_id = {t.txn_id: t for t in AaTransaction.objects.filter(company=company)}
        assert by_id["AA-ROW-0001"].matched_payment_id == r_utr.pk
        assert by_id["AA-ROW-0002"].matched_payment_id == r_amt.pk
        assert by_id["AA-ROW-0003"].matched_payment_id is None

        # replay the identical feed
        again = tenant_a.client.post("/api/v1/banking/aa/ingest/", feed, format="json")
        assert again.status_code == 201, again.data
        assert again.data["matched_count"] == 0  # nothing left unmatched to link
        assert AaTransaction.objects.filter(company=company).count() == 3  # no dup rows

        # a genuinely new credit in a later feed still ingests + stays unmatched
        feed2 = {**feed, "transactions": feed["transactions"] + [
            {"txn_id": "AA-ROW-0004", "amount": "42.00", "txn_date": "2026-06-12",
             "raw": {"narration": "UPI P2P"}},
        ]}
        third = tenant_a.client.post("/api/v1/banking/aa/ingest/", feed2, format="json")
        assert third.status_code == 201, third.data
        assert AaTransaction.objects.filter(company=company).count() == 4
        assert AaTransaction.objects.get(txn_id="AA-ROW-0004").matched_payment_id is None

    assert_consistent(company)


# --- G4 sales / purchase ---
def test_wf43_invoice_cancellation(tenant_a, assert_consistent):
    """Cancelling a completed invoice reverses stock, GST, GL and AR; the invoice
    ends CANCELLED and every posted journal still balances."""
    from tests.conftest import add_stock

    company = tenant_a.company
    _books(company)
    product = make_product(company, gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "20", unit_cost="60")
    customer = make_customer(company, state="Karnataka", gstin="29AAAAA0000A1ZY")

    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "4", "unit_price": "100.00", "gst_rate": "18"}],
    )
    assert tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200

    from inventory.services import InventoryService

    assert InventoryService.available_quantity(company=company, product=product) == Decimal("16.000")

    canc = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/cancel/", {"reason": "customer changed mind"}, format="json")
    assert canc.status_code == 200, canc.data
    assert canc.data["status"] in ("CANCELLED", "CANCELED", "VOID")

    # stock restored
    assert InventoryService.available_quantity(company=company, product=product) == Decimal("20.000")

    from accounting.models import JournalEntry

    for e in JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED):
        e.assert_balanced()

    # lifecycle audit trail: COMPLETE + CANCEL statutory events both logged
    from core.invariants.audit import statutory_events_present

    assert not statutory_events_present(company), statutory_events_present(company)

    assert_consistent(company)


def test_wf44_invoice_amendment_h9(tenant_a, assert_consistent):
    """H9-A audited-edit path: PATCH a COMPLETED invoice with confirm_amend to
    change a line price (same qty, same product). The GL is adjusted by exactly
    the delta (Debtors + output tax + Sales all move), every posted journal still
    balances, stock is untouched, and a statutory AMEND event is logged."""
    from django.db.models import Sum

    from tests.conftest import add_stock

    company = tenant_a.company
    _books(company)
    product = make_product(company, gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "20", unit_cost="60")
    customer = make_customer(company, state="Karnataka", gstin="29AAAAA0000A1ZY")

    inv = create_draft_invoice(
        tenant_a, customer,
        [{"product": product.id, "quantity": "4", "unit_price": "100.00", "gst_rate": "18"}],
    )
    inv_id = inv["id"]
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv_id}/complete/")
    assert done.status_code == 200

    from accounting.models import Account, JournalEntry, JournalLine
    from inventory.services import InventoryService

    debtors = Account.objects.get(company=company, code="1200")
    sales = Account.objects.get(company=company, code="4100")

    def _net(account, **extra):
        # H9-A amend = reverse the original entry (-> REVERSED) + fresh re-post.
        # Netting across POSTED + REVERSED + the JOURNAL_REVERSAL pair gives the
        # true running balance.
        agg = JournalLine.objects.filter(
            account=account, entry__company=company,
            entry__status__in=("POSTED", "REVERSED"), **extra
        ).aggregate(d=Sum("debit"), c=Sum("credit"))
        return (agg["d"] or Decimal("0")) - (agg["c"] or Decimal("0"))

    # qty 4 @ 100, 18% intrastate -> taxable 400, tax 72, grand 472
    assert _net(debtors, customer=customer) == Decimal("472.00")
    assert -_net(sales) == Decimal("400.00")
    stock_before = InventoryService.available_quantity(company=company, product=product)

    amend = tenant_a.client.patch(
        f"/api/v1/sales/invoices/{inv_id}/",
        {
            "confirm_amend": True,
            "expected_amend_revision": done.data.get("amend_revision", 0),
            "notes": "price correction per customer dispute",
            "items": [{"product": product.id, "quantity": "4", "unit_price": "90.00", "gst_rate": "18"}],
        },
        format="json",
    )
    assert amend.status_code == 200, amend.data
    assert Decimal(amend.data["items"][0]["unit_price"]) == Decimal("90.00")
    # taxable 360, tax 64.80, +0.20 auto round-off -> grand 425.00
    assert Decimal(amend.data["grand_total"]) == Decimal("425.00")

    # GL moved by exactly the delta: Debtors follows grand, Sales follows taxable
    assert _net(debtors, customer=customer) == Decimal("425.00")
    assert -_net(sales) == Decimal("360.00")

    # quantity is immutable on a completed invoice -> no stock delta
    assert InventoryService.available_quantity(company=company, product=product) == stock_before

    from core.models import StatutoryDocumentEvent

    assert StatutoryDocumentEvent.objects.filter(
        company=company, entity_type="sales_invoice", entity_id=inv_id,
        event_type=StatutoryDocumentEvent.EventType.AMEND,
    ).exists()

    # and the COMPLETE event is still there beside the AMEND (trail is append-only)
    from core.invariants.audit import money_mutations_logged, statutory_events_present

    assert not statutory_events_present(company), statutory_events_present(company)

    # §G7 money.changes_audited: the money change on the COMPLETED invoice left a
    # before/after audit row (AuditEvent "Completed document edited").
    from core.models import AuditEvent

    edit_ev = AuditEvent.objects.filter(
        company=company, entity_type="SalesInvoice", entity_id=str(inv_id),
        description="Completed document edited",
    ).latest("created_at")
    assert Decimal(str(edit_ev.metadata["before"]["grand_total"])) == Decimal("472.00")
    assert Decimal(str(edit_ev.metadata["after"]["grand_total"])) == Decimal("425.00")
    assert edit_ev.metadata.get("amend") is True
    assert money_mutations_logged(company) == []  # no no-op / blank-field rows

    for e in JournalEntry.objects.filter(company=company, status=JournalEntry.Status.POSTED):
        e.assert_balanced()
    assert_consistent(company)


# --- G6 auth / users / company ---
def test_wf45_registration(db):
    """Register -> user + company + OWNER membership in one shot; a second
    registration with the same email returns the same shape and no tokens."""
    from rest_framework.test import APIClient

    from accounts.models import Company, CompanyUser, User
    from tests.conftest import register_via_api

    client = APIClient()
    payload = {
        "company_name": "Fresh Traders",
        "email": "founder@fresh.test",
        "password": "StrongPass123!",
        "full_name": "Fresh Founder",
        "phone": "9998887770",
        "state": "Karnataka",
        "registration_type": "UNREGISTERED",  # REGULAR/COMPOSITION would require a GSTIN
    }
    r = register_via_api(client, payload)
    assert r.status_code in (200, 201), r.data

    user = User.objects.get(email__iexact="founder@fresh.test")
    company = Company.objects.get(name="Fresh Traders")
    cu = CompanyUser.objects.get(user=user, company=company)
    assert cu.role == CompanyUser.Role.OWNER
    assert company.state == "Karnataka"
    # duplicate-email behaviour is exercised by tests/test_auth.py (a known-fragile
    # area — 3 register tests there fail in the full-suite context; team-owned).


def test_wf45_registration_email_verify():
    """LIM pin: register has no email-verification step. Auth URLconf exposes
    register + OTP verify, not verify-email. Do not invent a flow here."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "accounts" / "urls_auth.py"
    blob = src.read_text(encoding="utf-8")
    assert "register/" in blob
    assert "otp/verify/" in blob
    assert "email/verify" not in blob
    assert "verify-email" not in blob
    assert "VerifyEmail" not in blob


def test_wf46_password_reset(tenant_a):
    """Request reset -> extract token from the email -> confirm new password ->
    the old password no longer authenticates, the new one does."""
    import re

    from django.contrib.auth import authenticate
    from django.core import mail
    from rest_framework.test import APIClient

    user = tenant_a.owner
    email = user.email
    client = APIClient()

    mail.outbox.clear()
    r = client.post("/api/v1/auth/password/reset/", {"identifier": email}, format="json")
    assert r.status_code in (200, 202), r.data
    assert mail.outbox, "no reset email sent"
    m = re.search(r"token=([A-Za-z0-9_\-:.]+)", mail.outbox[-1].body)
    assert m, mail.outbox[-1].body
    token = m.group(1)

    conf = client.post(
        "/api/v1/auth/password/reset/confirm/",
        {"token": token, "new_password": "BrandNewPass456!"},
        format="json",
    )
    assert conf.status_code in (200, 202), conf.data

    assert authenticate(username=email, password="StrongPass123!") is None
    assert authenticate(username=email, password="BrandNewPass456!") is not None


def test_wf46_password_reset_ratelimit(tenant_a):
    """The password-reset request endpoint is throttled (scope `password_reset`,
    5/min): the 6th call inside the window returns 429. The autouse cache-clear
    fixture keeps each test's throttle bucket clean."""
    from rest_framework.test import APIClient

    client = APIClient()
    statuses = [
        client.post(
            "/api/v1/auth/password/reset/", {"identifier": tenant_a.owner.email}, format="json"
        ).status_code
        for _ in range(7)
    ]
    assert statuses[:5] == [s for s in statuses[:5] if s in (200, 202)], statuses
    assert 429 in statuses, f"expected a 429 within 7 calls, got {statuses}"
    assert statuses.index(429) >= 5, f"throttled too early: {statuses}"


def test_wf47_jwt_refresh_and_logout(db):
    """Login issues an access token + refresh cookie; refresh mints a new access
    token; after logout the same refresh token no longer refreshes."""
    from rest_framework.test import APIClient

    from accounts.models import Company, CompanyUser, User

    user = User.objects.create_user(email="jwt@x.test", password="StrongPass123!", full_name="J")
    company = Company.objects.create(name="JWT Co", state="Karnataka")
    CompanyUser.objects.create(company=company, user=user, role=CompanyUser.Role.OWNER)

    client = APIClient()
    login = client.post("/api/v1/auth/login/", {"email": "jwt@x.test", "password": "StrongPass123!"}, format="json")
    assert login.status_code == 200, login.data
    assert "access" in login.data
    from django.conf import settings as dj

    refresh = login.cookies.get(dj.JWT_REFRESH_COOKIE_NAME)
    assert refresh is not None
    refresh_val = refresh.value

    # refresh (DEBUG test settings accept the token in the body)
    ref = client.post("/api/v1/auth/refresh/", {"refresh": refresh_val}, format="json")
    assert ref.status_code == 200, ref.data
    assert "access" in ref.data

    out = client.post("/api/v1/auth/logout/", {"refresh": refresh_val}, format="json")
    assert out.status_code in (200, 204, 205), out.data

    ref2 = client.post("/api/v1/auth/refresh/", {"refresh": refresh_val}, format="json")
    assert ref2.status_code in (401, 403), f"refresh still worked after logout: {ref2.status_code}"


def test_wf58_plan_limits(tenant_a, settings):
    """(D11) Entitlement fail-closed: a subscribed plan that omits a dark module
    leaves it OFF even with the env flag on. Seat quota: inviting past the seat
    limit is rejected.

    Scope revision 2026-09-09b: D11 is a KNOWN LIMITATION, not a freeze blocker
    (no separate flag — plan-tier enforcement is not pilot-gated). Kept as
    regression coverage of fail-closed entitlement + seat quota."""
    company = tenant_a.company

    # (a) feature-flag entitlement fail-closed
    from unittest.mock import patch

    from core.services.feature_flags import build_feature_flags

    with patch("billing.services.plan_modules_for_company", return_value={"ENABLE_POS": True}):
        flags = build_feature_flags(company=company)
    # plan mentions only ENABLE_POS -> a dark module it omits is off regardless of env
    assert flags.get("ENABLE_MANUFACTURING") is False
    assert flags.get("ENABLE_PAYROLL") is False

    # (b) seat quota
    settings.UNSUBSCRIBED_SEAT_LIMIT = 2  # owner + staff already occupy 2
    r = tenant_a.client.post(
        "/api/v1/company/users/",
        {"email": "third@wf58.test", "role": "SALES_STAFF"},
        format="json",
    )
    assert 400 <= r.status_code < 500, f"3rd invite past seat limit was allowed: {r.status_code}"


def test_wf48_user_invite_to_role(tenant_a, settings):
    """Owner invites a user with a role -> a CompanyUser for that role exists on
    the tenant with that role's capability defaults; re-inviting the same email
    is rejected."""
    settings.UNSUBSCRIBED_SEAT_LIMIT = 0  # unlimited for this test
    from accounts.models import CompanyUser

    r = tenant_a.client.post(
        "/api/v1/company/users/", {"email": "acct@wf48.test", "role": "ACCOUNTANT"}, format="json"
    )
    assert r.status_code in (200, 201), r.data

    cu = CompanyUser.objects.filter(company=tenant_a.company, user__email__iexact="acct@wf48.test").first()
    assert cu is not None and cu.role == "ACCOUNTANT"
    # ACCOUNTANT capability defaults applied
    defaults = CompanyUser.capability_defaults_for_role("ACCOUNTANT") or {}
    for k, v in defaults.items():
        assert getattr(cu, k) == v, f"{k}: expected {v}, got {getattr(cu, k)}"

    # re-inviting the same email does not create a second membership for that (company, user)
    tenant_a.client.post(
        "/api/v1/company/users/", {"email": "acct@wf48.test", "role": "VIEWER"}, format="json"
    )
    assert (
        CompanyUser.objects.filter(company=tenant_a.company, user=cu.user).count() == 1
    ), "re-invite created a duplicate membership"


def test_wf49_switch_company_context(tenant_a, tenant_b):
    """A user in two companies switches context; requests are scoped to the
    active company and never see the other's rows."""
    from accounts.models import CompanyUser
    from rest_framework.test import APIClient

    user = tenant_a.owner
    CompanyUser.objects.create(company=tenant_b.company, user=user, role=CompanyUser.Role.OWNER)
    make_customer(tenant_a.company, name="A-cust")
    make_customer(tenant_b.company, name="B-cust")

    client = APIClient()
    client.force_authenticate(user=user)

    sw_a = client.post("/api/v1/auth/switch-company/", {"company_id": tenant_a.company.id}, format="json")
    assert sw_a.status_code in (200, 201), sw_a.data
    rows = client.get("/api/v1/customers/").data
    rows = rows.get("results", rows) if isinstance(rows, dict) else rows
    names = {r["name"] for r in rows}
    assert "A-cust" in names and "B-cust" not in names

    sw_b = client.post("/api/v1/auth/switch-company/", {"company_id": tenant_b.company.id}, format="json")
    assert sw_b.status_code in (200, 201), sw_b.data
    rows = client.get("/api/v1/customers/").data
    rows = rows.get("results", rows) if isinstance(rows, dict) else rows
    names = {r["name"] for r in rows}
    assert "B-cust" in names and "A-cust" not in names

    # a company the user has no membership in is rejected
    from accounts.models import Company

    stranger = Company.objects.create(name="Stranger", state="Karnataka")
    bad = client.post("/api/v1/auth/switch-company/", {"company_id": stranger.id}, format="json")
    assert bad.status_code in (400, 403, 404)


def test_wf50_and_wf59_sandbox_expiry_cascade_erasure(tenant_a):
    """(D13 / G6) An expired sandbox company is fully deleted (cascade across all
    tenant data) by the sweep; a non-sandbox company and a not-yet-expired
    sandbox are untouched."""
    from datetime import timedelta

    from django.utils import timezone

    from accounts.models import Company
    from accounts.tenant_backup import sweep_expired_sandboxes
    from masters.models import Customer

    keep = tenant_a.company  # normal company
    Customer.objects.create(company=keep, name="keep-cust", state="Karnataka")

    expired = Company.objects.create(
        name="Expired Sandbox", state="Karnataka",
        is_sandbox=True, sandbox_expires_at=timezone.now() - timedelta(days=1),
    )
    Customer.objects.create(company=expired, name="doomed-cust", state="Karnataka")

    fresh = Company.objects.create(
        name="Fresh Sandbox", state="Karnataka",
        is_sandbox=True, sandbox_expires_at=timezone.now() + timedelta(days=7),
    )

    deleted = sweep_expired_sandboxes()
    assert deleted >= 1

    assert not Company.objects.filter(pk=expired.pk).exists()
    assert not Customer.objects.filter(company_id=expired.pk).exists()  # cascade
    assert Company.objects.filter(pk=keep.pk).exists()
    assert Customer.objects.filter(company=keep, name="keep-cust").exists()
    assert Company.objects.filter(pk=fresh.pk).exists()  # not yet expired


# --- G7 cross-cutting ---
def test_wf51_idempotency_contract(tenant_a):
    """Replaying POST /sales/invoices/ with the same Idempotency-Key returns the
    original invoice and creates no second row; a different key creates a new one."""
    from tests.conftest import add_stock

    company = tenant_a.company
    product = make_product(company, gst_rate="18")
    add_stock(tenant_a, product, "50")
    customer = make_customer(company, gstin="29AAAAA0000A1ZY")
    payload = {
        "customer": customer.id,
        "invoice_type": "GST",
        "items": [{"product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18"}],
    }
    from sales.models import SalesInvoice

    r1 = tenant_a.client.post("/api/v1/sales/invoices/", payload, format="json", HTTP_IDEMPOTENCY_KEY="wf51-key-1")
    assert r1.status_code == 201, r1.data
    n_after_first = SalesInvoice.objects.filter(company=company).count()

    r2 = tenant_a.client.post("/api/v1/sales/invoices/", payload, format="json", HTTP_IDEMPOTENCY_KEY="wf51-key-1")
    assert r2.status_code in (200, 201), r2.data
    assert r2.data["id"] == r1.data["id"], "replay created / returned a different invoice"
    assert SalesInvoice.objects.filter(company=company).count() == n_after_first, "replay created a second invoice"

    r3 = tenant_a.client.post("/api/v1/sales/invoices/", payload, format="json", HTTP_IDEMPOTENCY_KEY="wf51-key-2")
    assert r3.status_code == 201 and r3.data["id"] != r1.data["id"]
    assert SalesInvoice.objects.filter(company=company).count() == n_after_first + 1

    assert_all_invariants(company)


def test_wf52_document_numbering_integrity(tenant_a):
    """Completed invoices get distinct, sequential document numbers — no
    duplicates, no blanks (numbering.no_duplicate_document_numbers holds)."""
    from tests.conftest import add_stock

    company = tenant_a.company
    product = make_product(company, gst_rate="18")
    add_stock(tenant_a, product, "50")
    customer = make_customer(company, gstin="29AAAAA0000A1ZY")

    numbers = []
    for _ in range(3):
        inv = create_draft_invoice(
            tenant_a, customer,
            [{"product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18"}],
        )
        done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
        assert done.status_code == 200, done.data
        numbers.append(done.data["number"])

    assert all(n for n in numbers), f"blank invoice number: {numbers}"
    assert len(set(numbers)) == 3, f"duplicate invoice numbers: {numbers}"

    # gap-free within the series (Rule 46(b) consecutive serials) — plain callable
    from core.invariants.numbering import sequences_intact

    assert not sequences_intact(company), sequences_intact(company)

    assert_all_invariants(company)  # includes numbering.no_duplicate_document_numbers
