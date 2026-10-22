"""WP-F6: the database refuses to commit a posted journal entry that does not balance.

Constraint triggers are DEFERRED, so they fire at COMMIT: these tests need real commits
(transaction=True) and each bad write runs inside its own ``atomic()`` block.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from itertools import count

import pytest
from django.db import DatabaseError, connection, transaction

from accounting.models import Account, JournalEntry, JournalLine
from accounting.services import PostingService, seed_chart_of_accounts

pytestmark = [
    pytest.mark.skipif(connection.vendor != "postgresql", reason="Postgres constraint triggers"),
    pytest.mark.postgres,
    pytest.mark.django_db(transaction=True),
]


_ids = count(9000)


def _next_id():
    return next(_ids)


def _books(tenant):
    company = tenant.company
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(company, tenant.owner)
    return company


def _accounts(company):
    return Account.objects.get(company=company, code="1100"), Account.objects.get(company=company, code="4000")


def _entry(company, status, **kw):
    return JournalEntry.objects.create(company=company, status=status, entry_date="2026-04-01", **kw)


def test_normal_posting_still_commits(tenant_a):
    company = _books(tenant_a)
    cash, sales = _accounts(company)
    entry = PostingService.post(
        company=company, source_type="MANUAL_JOURNAL", source_id=_next_id(), purpose="POST", entry_date=date(2026, 4, 1),
        lines=[{"account": cash, "debit": Decimal("100")}, {"account": sales, "credit": Decimal("100")}],
    )
    assert entry.status == JournalEntry.Status.POSTED


def test_an_unbalanced_posted_entry_is_refused_at_commit(tenant_a):
    company = _books(tenant_a)
    cash, sales = _accounts(company)
    with pytest.raises(DatabaseError, match="unbalanced"):
        with transaction.atomic():
            entry = _entry(company, JournalEntry.Status.POSTED, number="JV-T1")
            JournalLine.objects.create(company=company, entry=entry, account=cash, debit=Decimal("100"))
            JournalLine.objects.create(company=company, entry=entry, account=sales, credit=Decimal("40"))
    assert not JournalEntry.objects.filter(number="JV-T1").exists()


def test_a_posted_entry_with_no_lines_is_refused(tenant_a):
    company = _books(tenant_a)
    with pytest.raises(DatabaseError, match="no lines"):
        with transaction.atomic():
            _entry(company, JournalEntry.Status.POSTED, number="JV-T2")


def test_flipping_an_unbalanced_draft_to_posted_is_refused(tenant_a):
    company = _books(tenant_a)
    cash, _sales = _accounts(company)
    with transaction.atomic():
        draft = _entry(company, JournalEntry.Status.DRAFT, number="JV-T3")
        JournalLine.objects.create(company=company, entry=draft, account=cash, debit=Decimal("100"))
    with pytest.raises(DatabaseError, match="unbalanced"):
        with transaction.atomic():
            JournalEntry.objects.filter(pk=draft.pk).update(status=JournalEntry.Status.POSTED)
    draft.refresh_from_db()
    assert draft.status == JournalEntry.Status.DRAFT


def test_deleting_one_line_of_a_posted_entry_is_refused(tenant_a):
    company = _books(tenant_a)
    cash, sales = _accounts(company)
    entry = PostingService.post(
        company=company, source_type="MANUAL_JOURNAL", source_id=_next_id(), purpose="POST", entry_date=date(2026, 4, 1),
        lines=[{"account": cash, "debit": Decimal("100")}, {"account": sales, "credit": Decimal("100")}],
    )
    with pytest.raises(DatabaseError, match="unbalanced"):
        with transaction.atomic():
            entry.lines.filter(account=sales).delete()
    assert entry.lines.count() == 2


def test_an_unbalanced_draft_is_allowed_until_it_is_posted(tenant_a):
    company = _books(tenant_a)
    cash, _sales = _accounts(company)
    with transaction.atomic():
        draft = _entry(company, JournalEntry.Status.DRAFT, number="JV-T4")
        JournalLine.objects.create(company=company, entry=draft, account=cash, debit=Decimal("100"))
    assert JournalEntry.objects.filter(pk=draft.pk).exists()


def test_the_trigger_reads_past_row_level_security(tenant_a):
    """SECURITY DEFINER: the check sees the lines even when the session cannot (app role, no tenant)."""
    from django.test import override_settings

    from tests.rls_helpers import app_role

    company = _books(tenant_a)
    cash, sales = _accounts(company)
    from core.rls import company_scope

    with override_settings(POSTGRES_RLS_ENABLED=True), app_role():
        with company_scope(company.pk):
            entry = PostingService.post(
                company=company, source_type="MANUAL_JOURNAL", source_id=_next_id(), purpose="POST", entry_date=date(2026, 4, 1),
                lines=[{"account": cash, "debit": Decimal("5")}, {"account": sales, "credit": Decimal("5")}],
            )
    assert entry.status == JournalEntry.Status.POSTED
