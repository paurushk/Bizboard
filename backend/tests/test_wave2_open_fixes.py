"""Wave 2 open-issue fixes: BB-000199/200/202/203/213/214/215/216/227."""

from decimal import Decimal
from datetime import date

import pytest

from accounting.models import JournalEntry
from accounting.services import PostingService, seed_chart_of_accounts
from accounts.models import CompanyUser
from core.models import FileAsset
from payments.models import BankAccount, BankStatement, BankStatementLine, BankStatementStatus
from reporting.gst_periods import reopen_period, soft_close_period
from reporting.gst_returns import build_gstr3b
from tests.conftest import create_draft_purchase, make_product, make_supplier

pytestmark = pytest.mark.django_db


def test_purchase_h9_period_block_and_gl_repost(tenant_a):
    """BB-000199: purchase amend asserts period + reverses/reposts COMPLETE journal."""
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)

    product = make_product(tenant_a.company, sku="H9-PUR")
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a, supplier, [{"product": product.id, "quantity": "2", "unit_price": "100"}]
    )
    # Stamp invoice into a known month for period close.
    from purchases.models import PurchaseInvoice

    inv = PurchaseInvoice.objects.get(pk=pur["id"])
    inv.invoice_date = date(2026, 6, 10)
    inv.save(update_fields=["invoice_date"])

    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200
    posted = JournalEntry.objects.get(
        company=tenant_a.company,
        source_type="PURCHASE_INVOICE",
        source_id=pur["id"],
        purpose="COMPLETE",
        status=JournalEntry.Status.POSTED,
    )
    ap_account = PostingService._account(tenant_a.company, "2100")
    old_credit = sum(line.credit for line in posted.lines.filter(account=ap_account))

    soft_close_period(tenant_a.company, "2026-06", tenant_a.owner)
    blocked = tenant_a.client.patch(
        f"/api/v1/purchases/invoices/{pur['id']}/",
        {
            "confirm_amend": True,
            "items": [{"product": product.id, "quantity": "2", "unit_price": "90"}],
        },
        format="json",
    )
    assert blocked.status_code == 400

    reopen_period(tenant_a.company, "2026-06")

    amended = tenant_a.client.patch(
        f"/api/v1/purchases/invoices/{pur['id']}/",
        {
            "confirm_amend": True,
            "items": [{"product": product.id, "quantity": "2", "unit_price": "90"}],
        },
        format="json",
    )
    assert amended.status_code == 200, amended.data
    posted.refresh_from_db()
    assert posted.status == JournalEntry.Status.REVERSED
    new_entry = JournalEntry.objects.get(
        company=tenant_a.company,
        source_type="PURCHASE_INVOICE",
        source_id=pur["id"],
        purpose="COMPLETE",
        status=JournalEntry.Status.POSTED,
    )
    # BB-000322: AP is credited for the full invoice value; any paise
    # round-off now posts to its own explicit 5500 Round Off leg rather than
    # being absorbed into the AP credit, so compare AP's own line only.
    new_credit = sum(line.credit for line in new_entry.lines.filter(account=ap_account))
    assert new_credit != old_credit
    assert new_credit == Decimal(amended.data["grand_total"])


def test_staff_cannot_create_journal(tenant_a):
    """BB-000200: SALES_STAFF cannot create journals; Owner can."""
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    cash = PostingService._account(tenant_a.company, "1100")
    equity = PostingService._account(tenant_a.company, "3100")
    payload = {
        "entry_date": "2026-04-01",
        "narration": "test",
        "lines": [
            {"account": cash.id, "debit": "50.00", "credit": "0"},
            {"account": equity.id, "debit": "0", "credit": "50.00"},
        ],
    }
    assert tenant_a.staff_client.post("/api/v1/accounting/journals/", payload, format="json").status_code == 403
    resp = tenant_a.client.post("/api/v1/accounting/journals/", payload, format="json")
    assert resp.status_code == 201, resp.data


def test_staff_without_reports_cannot_view_accounting_reports(tenant_a):
    """BB-000200/201: AccountingReportView requires CanViewFinancialReports."""
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    membership.can_view_financial_reports = False
    membership.save(update_fields=["can_view_financial_reports"])
    resp = tenant_a.staff_client.get("/api/v1/accounting/trial-balance/")
    assert resp.status_code == 403


def test_bank_recon_match_rejects_foreign_statement_line(tenant_a, tenant_b):
    """BB-000203: bank_statement_line must belong to session company."""
    for t in (tenant_a, tenant_b):
        t.company.accounting_enabled = True
        t.company.save(update_fields=["accounting_enabled"])
        seed_chart_of_accounts(t.company, t.owner)

    from accounting.models import BankReconSession

    bank_gl = PostingService._account(tenant_a.company, "1500")
    equity = PostingService._account(tenant_a.company, "3100")
    entry = PostingService.post(
        company=tenant_a.company,
        source_type="TEST",
        source_id=1,
        purpose="BANK",
        entry_date="2026-04-01",
        user=tenant_a.owner,
        lines=[
            {"account": bank_gl, "debit": Decimal("100.00")},
            {"account": equity, "credit": Decimal("100.00")},
        ],
    )
    jl = entry.lines.filter(account=bank_gl).first()
    bank_acct_a = BankAccount.objects.create(company=tenant_a.company, name="A")
    stmt_a = BankStatement.objects.create(
        company=tenant_a.company, bank_account=bank_acct_a, status=BankStatementStatus.COMMITTED
    )
    bank_acct_b = BankAccount.objects.create(company=tenant_b.company, name="B")
    stmt_b = BankStatement.objects.create(
        company=tenant_b.company, bank_account=bank_acct_b, status=BankStatementStatus.COMMITTED
    )
    foreign_line = BankStatementLine.objects.create(
        company=tenant_b.company,
        statement=stmt_b,
        txn_date="2026-04-01",
        amount=Decimal("100.00"),
        narration="Foreign",
    )
    session = BankReconSession.objects.create(
        company=tenant_a.company,
        account=bank_gl,
        statement=stmt_a,
        gl_balance=Decimal("100.00"),
        statement_balance=Decimal("0"),
    )
    resp = tenant_a.client.post(
        f"/api/v1/accounting/bank-recon-sessions/{session.id}/match/",
        {"journal_line": jl.id, "bank_statement_line": foreign_line.id},
        format="json",
    )
    assert resp.status_code == 400
    jl.refresh_from_db()
    assert jl.bank_statement_line_id is None


def test_company_logo_rejects_foreign_file_asset(tenant_a, tenant_b):
    """BB-000202: logo/signature FileAsset must belong to company."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    foreign = FileAsset.objects.create(
        company=tenant_b.company,
        kind=FileAsset.Kind.LOGO,
        original_name="x.png",
        file=SimpleUploadedFile("x.png", b"fake", content_type="image/png"),
    )
    resp = tenant_a.client.patch(
        "/api/v1/company/", {"logo": foreign.id}, format="json"
    )
    assert resp.status_code == 400
    assert "logo" in resp.data["error"]["details"]


def test_company_patch_cannot_enable_einvoice_or_accounting(tenant_a):
    """BB-000215/216: einvoice_enabled / aato_turnover / accounting_enabled read-only."""
    assert tenant_a.company.einvoice_enabled is False
    assert tenant_a.company.accounting_enabled is False
    resp = tenant_a.client.patch(
        "/api/v1/company/",
        {
            "einvoice_enabled": True,
            "aato_turnover": "6000000",
            "accounting_enabled": True,
            "name": "Alpha Renamed",
        },
        format="json",
    )
    assert resp.status_code == 200, resp.data
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.name == "Alpha Renamed"
    assert tenant_a.company.einvoice_enabled is False
    assert tenant_a.company.accounting_enabled is False
    assert tenant_a.company.aato_turnover is None
    assert resp.data["einvoice_enabled"] is False
    assert resp.data["accounting_enabled"] is False


def test_company_patch_cannot_enable_eway_or_gsp_provider(tenant_a):
    """BB-000215/286: eway_enabled and gsp_provider are read-only on CompanySerializer."""
    tenant_a.company.eway_enabled = False
    tenant_a.company.gsp_provider = ""
    tenant_a.company.save(update_fields=["eway_enabled", "gsp_provider"])
    resp = tenant_a.client.patch(
        "/api/v1/company/",
        {"eway_enabled": True, "gsp_provider": "sandbox"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    tenant_a.company.refresh_from_db()
    assert tenant_a.company.eway_enabled is False
    assert (tenant_a.company.gsp_provider or "") == ""
    assert resp.data["eway_enabled"] is False


def test_gstr3b_net_payable_excludes_provisional_itc(tenant_a):
    """BB-000213: net_payable_hint equals outward+RCM tax (no ITC subtract)."""
    product = make_product(tenant_a.company, sku="3B-ITC", hsn_code="3004")
    supplier = make_supplier(tenant_a.company, gstin="29AAAAA0000A1ZY", state="Karnataka")
    tenant_a.company.gstin = "29ABCDE1234F1ZW"
    tenant_a.company.state = "Karnataka"
    tenant_a.company.save(update_fields=["gstin", "state"])
    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "1000", "gst_rate": "18"}],
    )
    from purchases.models import PurchaseInvoice

    inv = PurchaseInvoice.objects.get(pk=pur["id"])
    inv.invoice_date = date(2026, 7, 5)
    inv.itc_eligibility = PurchaseInvoice.ItcEligibility.CLAIMABLE
    inv.save(update_fields=["invoice_date", "itc_eligibility"])
    assert tenant_a.client.post(f"/api/v1/purchases/invoices/{pur['id']}/complete/").status_code == 200

    payload = build_gstr3b(tenant_a.company, "2026-07")
    outward = Decimal(payload["tax_payable_summary"]["outward_tax"])
    rcm = (
        Decimal(payload["inward_supplies"]["reverse_charge"]["cgst"])
        + Decimal(payload["inward_supplies"]["reverse_charge"]["sgst"])
        + Decimal(payload["inward_supplies"]["reverse_charge"]["igst"])
    )
    hint = Decimal(payload["tax_payable_summary"]["net_payable_hint"])
    itc_total = Decimal(payload["tax_payable_summary"]["itc_available"])
    assert itc_total > 0
    assert hint == outward + rcm
    # BB-000279: RCM provisional ITC section present (label provisional).
    assert payload["itc"]["rcm_provisional"]["label"] == "provisional"
    assert payload["itc"]["rcm_provisional"]["provisional"] is True


def test_invite_owner_blocked(tenant_a):
    """BB-000227: cannot invite as OWNER."""
    resp = tenant_a.client.post(
        "/api/v1/company/users/",
        {
            "email": "coowner@alpha.test",
            "password": "StrongPass123!",
            "role": "OWNER",
        },
        format="json",
    )
    assert resp.status_code == 400
    assert "role" in resp.data["error"]["details"]


def test_patch_viewer_cannot_gain_create_sales(tenant_a):
    """BB-000227: PATCH VIEWER + can_create_sales rejected."""
    membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    membership.role = CompanyUser.Role.VIEWER
    for field, value in CompanyUser.capability_defaults_for_role(CompanyUser.Role.VIEWER).items():
        setattr(membership, field, value)
    membership.save()
    resp = tenant_a.client.patch(
        f"/api/v1/company/users/{membership.id}/",
        {"can_create_sales": True},
        format="json",
    )
    assert resp.status_code == 400
    assert "can_create_sales" in resp.data["error"]["details"]
