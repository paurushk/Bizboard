"""QOS-0043 — matcher eval: precision and recall of the rule engine with and without payee memory.

The memory signal is only worth keeping if it helps on lines the rules cannot settle and never
makes a wrong suggestion more likely. This harness scores labelled lines twice, once with the
rule engine alone (company=None) and once with the tenant's learned memory, then compares.

The cases are synthetic and hand-built, so the absolute numbers say nothing about real bank
data. That measurement still needs an anonymised statement. What this pins is the *relation*
between the two runs, and the amount safety rail.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from payments.models import (
    BankAccount,
    BankLineMatchStatus,
    BankStatement,
    BankStatementLine,
    BankStatementStatus,
)
from payments.recon import remember_payee, score_match
from payments.services import PaymentService
from tests.conftest import make_customer

pytestmark = pytest.mark.django_db

SUGGEST_AT = Decimal("50")  # lowest score the UI would offer as a suggestion
MARGIN = Decimal("5")  # the top candidate must clear the runner-up by this much


@dataclass
class Case:
    amount: str
    narration: str
    truth: str | None  # key of the receipt this line really settles; None = no right answer


def _line(company, statement, *, amount, narration, serial):
    return BankStatementLine.objects.create(
        company=company,
        statement=statement,
        txn_date=timezone.localdate() - timedelta(days=0),
        amount=Decimal(amount),
        narration=narration,
        utr="",
        line_hash=f"eval-{serial}",
        match_status=BankLineMatchStatus.UNMATCHED,
    )


def _suggest(line, receipts, company):
    """Top receipt key, or None when the engine would not offer a confident single answer."""
    scored = sorted(
        ((score_match(line, receipt=receipt, company=company), key) for key, receipt in receipts.items()),
        reverse=True,
    )
    top_score, top_key = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else Decimal("0")
    if top_score < SUGGEST_AT or top_score - runner_up < MARGIN:
        return None
    return top_key


def _precision_recall(cases, suggestions):
    made = [(c, s) for c, s in zip(cases, suggestions) if s is not None]
    correct = sum(1 for c, s in made if c.truth == s)
    positives = sum(1 for c in cases if c.truth is not None)
    precision = correct / len(made) if made else 1.0
    recall = correct / positives if positives else 1.0
    return precision, recall


def test_payee_memory_improves_recall_without_costing_precision(tenant_a):
    company = tenant_a.company
    account = BankAccount.objects.create(company=company, name="ICICI", is_default=True)
    statement = BankStatement.objects.create(
        company=company,
        bank_account=account,
        status=BankStatementStatus.COMMITTED,
        period_start=timezone.localdate(),
        period_end=timezone.localdate(),
    )

    sunrise = make_customer(company, name="Sunrise Enterprises")
    moonlight = make_customer(company, name="Moonlight Traders")
    orbit = make_customer(company, name="Orbit Foods")

    # The bank narrates payers differently from how they are registered, so the name rule misses.
    history = [
        (sunrise, "NEFT SUNCITY DEPT STORE INVOICE"),
        (moonlight, "IMPS MOONLT GENERAL STORES PAYMENT"),
    ]
    for serial, (customer, narration) in enumerate(history):
        remember_payee(
            company=company,
            line=_line(company, statement, amount="1", narration=narration, serial=f"hist-{serial}"),
            customer_id=customer.id,
        )

    def receipt(customer, amount):
        return PaymentService.create_receipt(company=company, customer=customer, amount=Decimal(amount), mode="BANK")

    # Two open receipts share an amount, so the rules alone cannot tell the payers apart.
    receipts = {
        "sunrise_500": receipt(sunrise, "500.00"),
        "moonlight_500": receipt(moonlight, "500.00"),
        "orbit_740": receipt(orbit, "740.00"),
    }

    cases = [
        Case("500.00", "IMPS SUNCITY DEPT STORE PAYMENT", "sunrise_500"),
        Case("500.00", "UPI MOONLT GENERAL STORES SETTLEMENT", "moonlight_500"),
        Case("740.00", "NEFT SOMEONE ELSE ENTIRELY", "orbit_740"),  # amount alone is unique
        Case("123.45", "IMPS SUNCITY DEPT STORE PAYMENT", None),  # known payer, amount matches nothing
    ]
    lines = [
        _line(company, statement, amount=c.amount, narration=c.narration, serial=f"case-{i}")
        for i, c in enumerate(cases)
    ]

    rules_only = [_suggest(line, receipts, company=None) for line in lines]
    with_memory = [_suggest(line, receipts, company=company) for line in lines]

    rule_precision, rule_recall = _precision_recall(cases, rules_only)
    mem_precision, mem_recall = _precision_recall(cases, with_memory)

    # The rules cannot separate two payers of the same amount; only the unique-amount case lands.
    assert rules_only == [None, None, "orbit_740", None]
    assert with_memory == ["sunrise_500", "moonlight_500", "orbit_740", None]

    assert mem_precision >= rule_precision, "memory must never make suggestions less precise"
    assert mem_recall > rule_recall, "memory should settle lines the rules left ambiguous"
    assert (mem_precision, mem_recall) == (1.0, 1.0)
    assert (rule_precision, rule_recall) == (1.0, pytest.approx(1 / 3))


def test_memory_never_suggests_a_receipt_whose_amount_does_not_match(tenant_a):
    """A learned payee cannot lift a candidate over the amount rail, so the eval stays honest."""
    company = tenant_a.company
    account = BankAccount.objects.create(company=company, name="ICICI", is_default=True)
    statement = BankStatement.objects.create(
        company=company,
        bank_account=account,
        status=BankStatementStatus.COMMITTED,
        period_start=timezone.localdate(),
        period_end=timezone.localdate(),
    )
    sunrise = make_customer(company, name="Sunrise Enterprises")
    remember_payee(
        company=company,
        line=_line(company, statement, amount="1", narration="NEFT SUNCITY DEPT STORE", serial="h"),
        customer_id=sunrise.id,
    )
    candidate = PaymentService.create_receipt(
        company=company, customer=sunrise, amount=Decimal("9000.00"), mode="BANK"
    )
    line = _line(company, statement, amount="250.00", narration="NEFT SUNCITY DEPT STORE", serial="x")

    assert _suggest(line, {"sunrise": candidate}, company=company) is None
