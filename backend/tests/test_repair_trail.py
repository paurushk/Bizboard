"""WP-F7: a repair that writes leaves an audit row and a books check; a dry run leaves nothing."""

from io import StringIO

import pytest
from django.core.management import call_command

from core.models import AuditEvent
from tests.test_ar_ap_agreement_matrix import _books, _sale
from tests.conftest import make_customer, make_product

pytestmark = pytest.mark.django_db


def _books_off_sale_then_on(tenant):
    """A sale made while books were off has no journal until the back-fill posts it (a legacy
    company: shadow posting off too, WP-F2)."""
    tenant.company.post_ledger = False
    tenant.company.save(update_fields=["post_ledger"])
    _sale(tenant, make_customer(tenant.company), make_product(tenant.company, sku="REP-1"))
    _books(tenant, True)


def _repairs(company):
    return AuditEvent.objects.filter(company=company, action="REPAIR")


@pytest.mark.invariant_skip("gl.ar_ties_to_documents", reason="sales documents or journals are built through the ORM, so receivables in the ledger and on documents cannot tie")
def test_a_dry_run_writes_no_trail(tenant_a):
    _books_off_sale_then_on(tenant_a)
    call_command("backfill_missing_postings", "--dry-run", "--company", str(tenant_a.company.pk), stdout=StringIO())
    assert not _repairs(tenant_a.company).exists()


# backfill_accounting_postings covers invoices, receipts and payments; backfill_missing_postings
# covers notes, returns and bills of entry, so it has nothing to post for a lone invoice.
# So after the wrong one the invoice is still missing and the books check says so.
@pytest.mark.parametrize(
    ("command", "posts", "verdict"),
    [
        ("backfill_accounting_postings", 1, "clean"),
        pytest.param(
            "backfill_missing_postings", 0, "FAILED ['gl.ar_ties_to_documents']",
            marks=pytest.mark.invariant_skip(
                "gl.ar_ties_to_documents", reason="this back-fill leaves the old sale unposted, and the test asserts the check says so",
            ),
        ),
    ],
)
def test_an_applied_back_fill_is_audited_and_checked(tenant_a, command, posts, verdict):
    _books_off_sale_then_on(tenant_a)
    out = StringIO()
    call_command(command, "--company", str(tenant_a.company.pk), stdout=out)
    event = _repairs(tenant_a.company).get()
    assert event.description == command
    assert event.metadata["posted"] >= posts
    assert f"books check after {command} for company {tenant_a.company.pk}: {verdict}" in out.getvalue()


def test_running_a_back_fill_twice_posts_once(tenant_a):
    from accounting.models import JournalEntry

    _books_off_sale_then_on(tenant_a)
    call_command("backfill_accounting_postings", "--company", str(tenant_a.company.pk), stdout=StringIO())
    first = JournalEntry.objects.filter(company=tenant_a.company).count()
    assert JournalEntry.objects.filter(company=tenant_a.company, source_type="SALES_INVOICE").exists()
    call_command("backfill_accounting_postings", "--company", str(tenant_a.company.pk), stdout=StringIO())
    # The second run finds every document already posted (PostingService.post returns the existing entry).
    assert JournalEntry.objects.filter(company=tenant_a.company).count() == first
    assert _repairs(tenant_a.company).count() == 2


def test_the_bank_match_repair_is_audited_only_when_it_fixes(tenant_a):
    _books(tenant_a, True)
    call_command("repair_bank_match_state", "--company", str(tenant_a.company.pk), "--fix", stdout=StringIO())
    assert not _repairs(tenant_a.company).exists()  # nothing inconsistent, nothing repaired


def test_the_payroll_repair_takes_a_company(tenant_a):
    out = StringIO()
    call_command("repair_orphan_pay_run_journals", "--company", str(tenant_a.company.pk), stdout=out)
    assert "No orphan payroll journals." in out.getvalue()
