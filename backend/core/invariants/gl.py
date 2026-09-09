"""General-ledger invariants.

D5 = ON (at least one pilot company uses books), so these are a HARD blocking
freeze gate. Imports are lazy (inside each check) to avoid an import cycle with
the accounting app at startup.
"""

from __future__ import annotations

from decimal import Decimal

from .base import invariant

_ZERO = Decimal("0")
# Journal purposes allowed to post into a closed period (sanctioned corrections).
_CLOSED_PERIOD_ALLOWED_PURPOSES = {"FY_CLOSE", "H9_CORRECTION", "PERIOD_LOCK_CORRECTION"}


@invariant(
    "gl.journals_balanced",
    consequence="A posted journal entry has unequal debits and credits — the books do not balance.",
)
def journals_balanced(company) -> list[str]:
    from django.db.models import Sum

    from accounting.models import JournalEntry, JournalLine

    rows = (
        JournalLine.objects.filter(
            entry__company=company,
            entry__status__in=[JournalEntry.Status.POSTED, JournalEntry.Status.REVERSED],
        )
        .values("entry_id", "entry__number")
        .annotate(d=Sum("debit"), c=Sum("credit"))
    )
    out = []
    for r in rows:
        d = r["d"] or _ZERO
        c = r["c"] or _ZERO
        if d != c:
            out.append(
                f"entry #{r['entry_id']} ({r['entry__number'] or 'no number'}): "
                f"debit {d} != credit {c}"
            )
    return out


@invariant(
    "gl.trial_balance_zero",
    consequence="Company trial balance does not net to zero — a posting is missing a side or is malformed.",
)
def trial_balance_zero(company) -> list[str]:
    from accounting.reports import trial_balance

    tb = trial_balance(company)
    if not tb.get("balanced", False):
        return [
            f"trial balance unbalanced: total_debit {tb['total_debit']} != "
            f"total_credit {tb['total_credit']}"
        ]
    return []


@invariant(
    "gl.no_orphan_lines",
    consequence="A journal line's company tag disagrees with its entry — tenant/data corruption.",
)
def no_orphan_lines(company) -> list[str]:
    from django.db.models import F

    from accounting.models import JournalLine

    bad = (
        JournalLine.objects.filter(entry__company=company)
        .exclude(company_id=F("entry__company_id"))
        .count()
    )
    bad += (
        JournalLine.objects.filter(company=company)
        .exclude(account__company_id=F("entry__company_id"))
        .count()
    )
    return [f"{bad} journal line(s) with a company/account tenancy mismatch"] if bad else []


@invariant(
    "gl.party_subledger_complete",
    consequence="An account is used as a party sub-ledger on some lines but not others — its GL balance won't reconcile to the customer/supplier sub-ledger.",
)
def party_subledger_complete(company) -> list[str]:
    """Self-calibrating: an account that carries a customer/supplier tag on ANY
    posted line must carry one on EVERY posted line (otherwise the party
    sub-ledger is a partial view of the account and AR/AP won't tie out).
    Accounts never used as sub-ledgers (Cash, Sales, COGS, tax) have zero tagged
    lines and are skipped.
    """
    from django.db.models import Q, Sum

    from accounting.models import JournalEntry, JournalLine

    posted = dict(
        company=company,
        entry__status__in=[JournalEntry.Status.POSTED, JournalEntry.Status.REVERSED],
    )
    tagged_account_ids = (
        JournalLine.objects.filter(**posted)
        .filter(Q(customer__isnull=False) | Q(supplier__isnull=False))
        .values_list("account_id", flat=True)
        .distinct()
    )
    out = []
    for acc_id in tagged_account_ids:
        untagged = JournalLine.objects.filter(
            account_id=acc_id, customer__isnull=True, supplier__isnull=True, **posted
        ).aggregate(d=Sum("debit"), c=Sum("credit"))
        net = (untagged["d"] or _ZERO) - (untagged["c"] or _ZERO)
        n = JournalLine.objects.filter(
            account_id=acc_id, customer__isnull=True, supplier__isnull=True, **posted
        ).count()
        if n:
            code = JournalLine.objects.filter(account_id=acc_id).values_list(
                "account__code", "account__name"
            )[0]
            out.append(
                f"account {code[0]} ({code[1]}): {n} posted line(s) with no party tag "
                f"(net {net}) though the account is used as a party sub-ledger elsewhere"
            )
    return out


# NOT registered: a closed period legitimately contains every SALE/PURCHASE
# journal that was validly posted before it closed — closing does not un-post
# them. The real rule ("cannot post a NEW entry dated into a closed period") is
# time-of-action, not a resting-state property, and is asserted by WF-20.
# Kept as a callable for a period-close chain to use against a controlled setup.
def closed_period_not_violated(company) -> list[str]:
    from accounting.models import AccountingPeriod, JournalEntry

    out = []
    closed = AccountingPeriod.objects.filter(
        company=company,
        status__in=[AccountingPeriod.Status.CLOSED, AccountingPeriod.Status.SOFT_CLOSED],
    )
    for period in closed:
        offending = (
            JournalEntry.objects.filter(
                company=company,
                status=JournalEntry.Status.POSTED,
                entry_date__gte=period.start_date,
                entry_date__lte=period.end_date,
            )
            .exclude(purpose__in=_CLOSED_PERIOD_ALLOWED_PURPOSES)
            .exclude(reversed_entry__isnull=False)  # this entry reverses another
            .exclude(reversal_of__isnull=False)  # this entry was reversed
        )
        n = offending.count()
        if n:
            sample = list(offending.values_list("number", "purpose")[:5])
            out.append(
                f"period {period.name} ({period.status}): {n} disallowed posted "
                f"entr{'y' if n == 1 else 'ies'}, e.g. {sample}"
            )
    return out
