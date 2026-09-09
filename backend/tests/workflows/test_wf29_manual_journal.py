"""WF-29 — manual journal entry (D5 = ON accounting core).

create draft JV -> post -> reverse. An unbalanced JV is rejected at create; a
posted JV is balanced; reversal creates a linked entry that nets the pair to
zero; the trial balance is unchanged after post + reverse.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db

J = "/api/v1/accounting/journals/"


def _books(company):
    company.accounting_enabled = True
    company.save(update_fields=["accounting_enabled"])
    from accounting.services import seed_chart_of_accounts

    seed_chart_of_accounts(company)


def _acct(company, code):
    from accounting.models import Account

    return Account.objects.get(company=company, code=code).id


def test_wf29_manual_journal_post_and_reverse(tenant_a, assert_consistent):
    company = tenant_a.company
    _books(company)
    cash = _acct(company, "1100")
    cogs = _acct(company, "5400")

    # unbalanced JV is rejected
    bad = tenant_a.client.post(
        J,
        {"entry_date": "2026-06-10", "narration": "bad", "lines": [
            {"account": cogs, "debit": "100.00", "credit": "0"},
            {"account": cash, "debit": "0", "credit": "90.00"},
        ]},
        format="json",
    )
    assert bad.status_code == 400, bad.data

    # balanced draft
    draft = tenant_a.client.post(
        J,
        {"entry_date": "2026-06-10", "narration": "expense paid in cash", "lines": [
            {"account": cogs, "debit": "500.00", "credit": "0"},
            {"account": cash, "debit": "0", "credit": "500.00"},
        ]},
        format="json",
    )
    assert draft.status_code == 201, draft.data
    jid = draft.data["id"]

    posted = tenant_a.client.post(f"{J}{jid}/post/")
    assert posted.status_code in (200, 202), posted.data

    from accounting.models import JournalEntry
    from accounting.reports import trial_balance

    je = JournalEntry.objects.get(pk=jid)
    assert je.status == JournalEntry.Status.POSTED
    je.assert_balanced()
    tb_after_post = trial_balance(company)
    assert tb_after_post["balanced"]

    rev = tenant_a.client.post(f"{J}{jid}/reverse/")
    assert rev.status_code in (200, 201, 202), rev.data

    # PostingService.reverse: original.status -> REVERSED, original.reversed_entry -> the reversal
    je.refresh_from_db()
    assert je.status == JournalEntry.Status.REVERSED
    reversal = je.reversed_entry
    assert reversal is not None, "reverse/ did not link a reversing entry"
    assert reversal.source_type == "JOURNAL_REVERSAL" and reversal.source_id == jid
    reversal.assert_balanced()

    from django.db.models import Sum

    from accounting.models import JournalLine

    for acc_id in (cash, cogs):
        agg = JournalLine.objects.filter(
            account_id=acc_id, entry_id__in=[jid, reversal.id]
        ).aggregate(d=Sum("debit"), c=Sum("credit"))
        net = (agg["d"] or Decimal("0")) - (agg["c"] or Decimal("0"))
        assert net == Decimal("0"), f"account {acc_id} net over the pair is {net}, not 0"

    assert trial_balance(company)["balanced"]
    assert_consistent(company)
