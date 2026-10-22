"""WP-F2: shadow books — one ledger for every company, whatever the Books switch shows."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

import re

import pytest
from django.core.management import call_command
from django.utils import timezone

from accounting.books import is_shadow, posts_to_ledger
from accounting.models import AccountingPeriod, JournalEntry
from accounting.reports import trial_balance
from core.exceptions import BusinessRuleError
from tests.conftest import make_customer, make_product, make_supplier
from tests.test_ar_ap_agreement_matrix import _purchase, _receipt, _sale

pytestmark = pytest.mark.django_db


def test_the_switch_and_the_ledger_are_separate_questions(tenant_a):
    company = tenant_a.company
    assert company.accounting_enabled is False and company.post_ledger is True
    assert posts_to_ledger(company) and is_shadow(company)
    company.post_ledger = False
    assert not posts_to_ledger(company)
    company.accounting_enabled = True
    assert posts_to_ledger(company) and not is_shadow(company)
    assert not posts_to_ledger(None)


def test_a_books_off_company_still_gets_a_complete_ledger(tenant_a):
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company)
    inv = _sale(tenant_a, customer, product)
    _receipt(tenant_a, customer, "300", invoice=inv)
    _purchase(tenant_a, make_supplier(tenant_a.company), product)
    company = tenant_a.company
    company.refresh_from_db()
    assert company.accounting_enabled is False
    assert JournalEntry.objects.filter(company=company, source_type="SALES_INVOICE", source_id=inv.pk).exists()
    assert JournalEntry.objects.filter(company=company, source_type="CUSTOMER_RECEIPT").exists()
    assert JournalEntry.objects.filter(company=company, source_type="PURCHASE_INVOICE").exists()
    assert trial_balance(company)["balanced"]


def test_turning_books_on_later_needs_no_back_fill_and_changes_no_number(tenant_a):
    from accounting.views import _books_switch_allowed

    from accounting.services import PostingService
    from tests.conftest import add_stock

    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company)
    # Opening stock as the Opening stock screen records it (inventory/views.py posts it).
    PostingService.post_opening_stock(add_stock(tenant_a, product, "20"), tenant_a.owner)
    _sale(tenant_a, customer, product, amount="1180")
    company = tenant_a.company
    before = trial_balance(company)
    assert _books_switch_allowed(company)
    resp = tenant_a.client.post("/api/v1/accounting/settings/", {"accounting_enabled": True}, format="json")
    assert resp.status_code == 200, resp.content
    company.refresh_from_db()
    assert company.accounting_enabled
    after = trial_balance(company)
    assert (after["total_debit"], after["total_credit"]) == (before["total_debit"], before["total_credit"])


def test_switching_books_off_keeps_the_ledger_posting(tenant_a):
    company = tenant_a.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    pre = tenant_a.client.get("/api/v1/accounting/settings/disable-preflight/")
    assert pre.status_code == 200 and pre.data["post_ledger"] is True
    company.accounting_enabled = False
    company.save(update_fields=["accounting_enabled"])
    inv = _sale(tenant_a, make_customer(company), make_product(company))
    assert JournalEntry.objects.filter(company=company, source_type="SALES_INVOICE", source_id=inv.pk).exists()


def _period(company, status):
    today = timezone.localdate()
    return AccountingPeriod.objects.create(
        company=company, name="This month", start_date=today.replace(day=1),
        end_date=(today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1), status=status,
    )


def test_a_soft_closed_month_gives_a_document_message_not_an_accounting_error(tenant_a):
    """A soft close left from when the books were on stops money edits in that month with the
    same document-level message books-on companies get (code closed_period), never a 500."""
    from tests.conftest import add_stock, create_draft_invoice

    _period(tenant_a.company, AccountingPeriod.Status.SOFT_CLOSED)
    product = make_product(tenant_a.company)
    add_stock(tenant_a, product, "5")
    draft = create_draft_invoice(
        tenant_a, make_customer(tenant_a.company),
        [{"product": product.id, "quantity": "1", "unit_price": "10", "gst_rate": "0"}], invoice_type="NON_GST",
    )
    resp = tenant_a.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert resp.status_code == 400
    assert resp.data["error"]["code"] == "closed_period"


def test_shadow_posting_itself_accepts_a_soft_closed_month(tenant_a):
    from accounting.services import PostingService, seed_chart_of_accounts

    _period(tenant_a.company, AccountingPeriod.Status.SOFT_CLOSED)
    accounts = seed_chart_of_accounts(tenant_a.company)
    entry = PostingService.post(
        company=tenant_a.company, source_type="MANUAL_JOURNAL", source_id=778, purpose="POST",
        entry_date=timezone.localdate(),
        lines=[{"account": accounts["1100"], "debit": Decimal("1")}, {"account": accounts["4000"], "credit": Decimal("1")}],
    )
    assert entry is not None


def test_a_closed_period_still_refuses(tenant_a):
    from accounting.services import PostingService

    _period(tenant_a.company, AccountingPeriod.Status.CLOSED)
    from accounting.services import seed_chart_of_accounts

    accounts = seed_chart_of_accounts(tenant_a.company)
    with pytest.raises(BusinessRuleError):
        PostingService.post(
            company=tenant_a.company, source_type="MANUAL_JOURNAL", source_id=777, purpose="POST",
            entry_date=timezone.localdate(),
            lines=[{"account": accounts["1100"], "debit": Decimal("1")}, {"account": accounts["4000"], "credit": Decimal("1")}],
        )


def test_a_company_with_posting_off_posts_nothing(tenant_a):
    company = tenant_a.company
    company.post_ledger = False
    company.save(update_fields=["post_ledger"])
    inv = _sale(tenant_a, make_customer(company), make_product(company))
    assert not JournalEntry.objects.filter(company=company, source_type="SALES_INVOICE", source_id=inv.pk).exists()


def test_enable_shadow_books_catches_up_history_then_turns_posting_on(tenant_a):
    company = tenant_a.company
    company.post_ledger = False
    company.save(update_fields=["post_ledger"])
    inv = _sale(tenant_a, make_customer(company), make_product(company))
    out = StringIO()
    call_command("enable_shadow_books", "--company", str(company.pk), stdout=out)
    assert re.search(r"would post [1-9]\d* document\(s\)", out.getvalue()), out.getvalue()
    company.refresh_from_db()
    assert company.post_ledger is False  # dry run changed nothing
    out = StringIO()
    call_command("enable_shadow_books", "--company", str(company.pk), "--apply", stdout=out)
    company.refresh_from_db()
    assert company.post_ledger is True
    assert JournalEntry.objects.filter(company=company, source_type="SALES_INVOICE", source_id=inv.pk).exists()
    assert "books check CLEAN" in out.getvalue()


def test_the_migration_leaves_books_off_companies_with_history_for_the_command(tenant_a, tenant_b):
    import importlib

    from django.apps import apps

    from accounts.models import Company

    migration = importlib.import_module("accounts.migrations.0068_shadow_books_existing_companies")
    _sale(tenant_a, make_customer(tenant_a.company), make_product(tenant_a.company))
    migration.forwards(apps, None)
    assert Company.objects.get(pk=tenant_a.company.pk).post_ledger is False  # history, books off
    assert Company.objects.get(pk=tenant_b.company.pk).post_ledger is True  # nothing recorded yet
    assert date.today()  # keep the import used
