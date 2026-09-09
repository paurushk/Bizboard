"""A2 — PostingService atomicity (CR-078, CR-088)."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from accounting.models import JournalEntry, JournalLine
from accounting.services import PostingService, seed_chart_of_accounts
from core.exceptions import BusinessRuleError

pytestmark = pytest.mark.django_db


@pytest.fixture
def books(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    return tenant_a


def _balanced_lines(company, amount=Decimal("100.00")):
    return [
        {"account": PostingService._account(company, "1100"), "debit": amount},
        {"account": PostingService._account(company, "3100"), "credit": amount},
    ]


def test_posting_crash_between_header_and_lines_does_not_leave_empty_posted(books):
    """CR-078: JE header + lines share one atomic — failure after create rolls back."""
    source_id = 78001

    def boom(*args, **kwargs):
        raise RuntimeError("simulated crash after JE create")

    with patch.object(JournalLine.objects, "bulk_create", side_effect=boom):
        with pytest.raises(RuntimeError, match="simulated crash"):
            PostingService.post(
                company=books.company,
                source_type="TEST",
                source_id=source_id,
                purpose="CR078",
                entry_date=date(2026, 4, 1),
                lines=_balanced_lines(books.company),
                user=books.owner,
            )

    assert not JournalEntry.objects.filter(
        company=books.company,
        source_type="TEST",
        source_id=source_id,
        purpose="CR078",
    ).exists()

    # Retry succeeds and leaves a balanced POSTED JE (no sticky empty header).
    entry = PostingService.post(
        company=books.company,
        source_type="TEST",
        source_id=source_id,
        purpose="CR078",
        entry_date=date(2026, 4, 1),
        lines=_balanced_lines(books.company),
        user=books.owner,
    )
    assert entry.status == JournalEntry.Status.POSTED
    assert entry.lines.count() == 2
    assert sum(line.debit for line in entry.lines.all()) == sum(
        line.credit for line in entry.lines.all()
    )


def test_incomplete_posted_je_repaired_on_repost(books):
    """CR-078: idempotent fast-path must not return a zero-line POSTED forever."""
    incomplete = JournalEntry.objects.create(
        company=books.company,
        number="JV-INCOMPLETE-078",
        entry_date=date(2026, 4, 1),
        status=JournalEntry.Status.POSTED,
        source_type="TEST",
        source_id=78002,
        purpose="CR078_REPAIR",
        narration="orphan header",
        posted_at=timezone.now(),
        posted_by=books.owner,
        created_by=books.owner,
        updated_by=books.owner,
    )
    assert incomplete.lines.count() == 0

    entry = PostingService.post(
        company=books.company,
        source_type="TEST",
        source_id=78002,
        purpose="CR078_REPAIR",
        entry_date=date(2026, 4, 1),
        lines=_balanced_lines(books.company, Decimal("50.00")),
        user=books.owner,
    )

    assert not JournalEntry.objects.filter(pk=incomplete.pk).exists()
    assert entry.pk != incomplete.pk
    assert entry.status == JournalEntry.Status.POSTED
    assert entry.lines.count() == 2
    # Second call is a true idempotent hit (complete JE).
    again = PostingService.post(
        company=books.company,
        source_type="TEST",
        source_id=78002,
        purpose="CR078_REPAIR",
        entry_date=date(2026, 4, 1),
        lines=_balanced_lines(books.company, Decimal("99.00")),
        user=books.owner,
    )
    assert again.pk == entry.pk
    assert again.lines.count() == 2


def test_post_rejects_subpaisa_unbalanced_after_quantize(books):
    """CR-088: amounts that balance at >2dp but not after 2dp quantize are rejected."""
    cash = PostingService._account(books.company, "1100")
    equity = PostingService._account(books.company, "3100")
    # 10.004 + 10.004 == 20.008 before quantize; after q2 → 10.00+10.00 vs 20.01.
    lines = [
        {"account": cash, "debit": Decimal("10.004")},
        {"account": cash, "debit": Decimal("10.004")},
        {"account": equity, "credit": Decimal("20.008")},
    ]
    assert sum(Decimal(str(l.get("debit", 0))) for l in lines) == sum(
        Decimal(str(l.get("credit", 0))) for l in lines
    )

    with pytest.raises(BusinessRuleError, match="balanced debit and credit"):
        PostingService.post(
            company=books.company,
            source_type="TEST",
            source_id=88001,
            purpose="CR088",
            entry_date=date(2026, 4, 1),
            lines=lines,
            user=books.owner,
        )

    assert not JournalEntry.objects.filter(
        company=books.company, source_type="TEST", source_id=88001, purpose="CR088",
    ).exists()


def test_post_quantizes_balanced_subpaisa_lines(books):
    """CR-088: symmetric sub-paisa that remains balanced after quantize still posts."""
    cash = PostingService._account(books.company, "1100")
    equity = PostingService._account(books.company, "3100")
    entry = PostingService.post(
        company=books.company,
        source_type="TEST",
        source_id=88002,
        purpose="CR088_OK",
        entry_date=date(2026, 4, 1),
        lines=[
            {"account": cash, "debit": Decimal("10.004")},
            {"account": equity, "credit": Decimal("10.004")},
        ],
        user=books.owner,
    )
    assert entry.lines.count() == 2
    assert sum(line.debit for line in entry.lines.all()) == Decimal("10.00")
    assert sum(line.credit for line in entry.lines.all()) == Decimal("10.00")
    for line in entry.lines.all():
        assert line.debit in (Decimal("0.00"), Decimal("10.00"))
        assert line.credit in (Decimal("0.00"), Decimal("10.00"))
