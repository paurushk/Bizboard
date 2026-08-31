"""W0-01: one POSTED journal per (company, source_type, source_id, purpose)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.utils import timezone

from accounting.models import JournalEntry
from accounting.services import PostingService, seed_chart_of_accounts

pytestmark = pytest.mark.django_db


@pytest.fixture
def books(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    return tenant_a


def _lines(company, amount="10"):
    return [
        {"account": PostingService._account(company, "1100"), "debit": Decimal(amount)},
        {"account": PostingService._account(company, "3100"), "credit": Decimal(amount)},
    ]


def test_second_post_returns_same_journal(books):
    kwargs = dict(
        company=books.company,
        source_type="TEST_W0_01",
        source_id=42,
        purpose="SALE",
        entry_date=timezone.localdate(),
        user=books.owner,
        lines=_lines(books.company),
    )
    first = PostingService.post(**kwargs)
    second = PostingService.post(**kwargs)
    assert first.pk == second.pk
    assert (
        JournalEntry.objects.filter(
            company=books.company,
            source_type="TEST_W0_01",
            source_id=42,
            purpose="SALE",
            status=JournalEntry.Status.POSTED,
        ).count()
        == 1
    )


def test_reverse_then_repost_allowed(books):
    kwargs = dict(
        company=books.company,
        source_type="TEST_W0_01",
        source_id=99,
        purpose="SALE",
        entry_date=timezone.localdate(),
        user=books.owner,
        lines=_lines(books.company),
    )
    first = PostingService.post(**kwargs)
    PostingService.reverse(first, user=books.owner)
    first.refresh_from_db()
    assert first.status == JournalEntry.Status.REVERSED
    second = PostingService.post(**kwargs)
    assert second.pk != first.pk
    assert second.status == JournalEntry.Status.POSTED
    assert (
        JournalEntry.objects.filter(
            company=books.company,
            source_type="TEST_W0_01",
            source_id=99,
            purpose="SALE",
            status=JournalEntry.Status.POSTED,
        ).count()
        == 1
    )


def test_unique_constraint_blocks_second_posted_row(books):
    kwargs = dict(
        company=books.company,
        number="JV-W0-A",
        entry_date=timezone.localdate(),
        status=JournalEntry.Status.POSTED,
        source_type="TEST_W0_01",
        source_id=7,
        purpose="SALE",
        posted_at=timezone.now(),
        created_by=books.owner,
        updated_by=books.owner,
    )
    JournalEntry.objects.create(**kwargs)
    with pytest.raises(IntegrityError):
        JournalEntry.objects.create(**{**kwargs, "number": "JV-W0-B"})
