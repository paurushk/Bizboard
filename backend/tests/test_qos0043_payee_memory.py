"""QOS-0043 — a learned bank-recon signal bootstrapped from the tenant's own
confirmed matches (not a trained ML model, no external corpus). Every
confirmed match teaches payments.recon a payee's narration tokens; a later,
differently-worded line for the same payee gets a small confidence bonus on
top of the existing rule engine — never enough to bypass its amount-match
safety rail on its own.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from payments.models import BankAccount, BankLineMatchStatus, BankStatementLine, PayeeMemory
from payments.recon import narration_tokens, payee_memory_bonus, remember_payee, score_match
from payments.services import PaymentService
from tests.conftest import make_customer

pytestmark = pytest.mark.django_db


def _line(company, ba, *, amount, narration, days_ago=0):
    return BankStatementLine.objects.create(
        company=company,
        statement=_statement(company, ba),
        txn_date=timezone.localdate() - timedelta(days=days_ago),
        amount=Decimal(str(amount)),
        narration=narration,
        utr="",
        line_hash=f"h-{narration}-{amount}",
        match_status=BankLineMatchStatus.UNMATCHED,
    )


def _statement(company, ba):
    from payments.models import BankStatement, BankStatementStatus

    return BankStatement.objects.create(
        company=company, bank_account=ba, status=BankStatementStatus.COMMITTED,
        period_start=timezone.localdate(), period_end=timezone.localdate(),
    )


def test_narration_tokens_drops_short_words_and_banking_stopwords():
    tokens = narration_tokens("NEFT Ravi Traders Invoice Mar")
    assert tokens == {"RAVI", "INVOICE"}


def test_remember_payee_then_bonus_applies_to_a_differently_worded_line(tenant_a):
    customer = make_customer(tenant_a.company, name="Sunrise Enterprises")
    ba = BankAccount.objects.create(company=tenant_a.company, name="ICICI", is_default=True)

    confirmed_line = _line(tenant_a.company, ba, amount="1000", narration="NEFT SUNCITY DEPT STORE INVOICE")
    remember_payee(company=tenant_a.company, line=confirmed_line, customer_id=customer.id)

    assert PayeeMemory.objects.filter(
        company=tenant_a.company, target_type=PayeeMemory.TargetType.CUSTOMER, target_id=customer.id,
    ).count() == 4  # SUNCITY, DEPT, STORE, INVOICE (NEFT is a stopword)

    new_line = _line(tenant_a.company, ba, amount="500", narration="IMPS SUNCITY DEPT STORE PAYMENT")
    bonus = payee_memory_bonus(company=tenant_a.company, line=new_line, customer_id=customer.id)
    assert bonus > 0, "3-token overlap (SUNCITY, DEPT, STORE) must produce a nonzero bonus"

    # The customer's own registered name ("Sunrise Enterprises") shares no
    # token with either narration — this bonus is coming from memory, not
    # the pre-existing target_name rule.
    assert "SUNRISE" not in narration_tokens("NEFT SUNCITY DEPT STORE INVOICE")


def test_repeat_confirmation_raises_hit_count_not_duplicate_rows(tenant_a):
    customer = make_customer(tenant_a.company, name="Sunrise Enterprises")
    ba = BankAccount.objects.create(company=tenant_a.company, name="ICICI", is_default=True)
    line = _line(tenant_a.company, ba, amount="1000", narration="SUNCITY DEPT STORE")

    remember_payee(company=tenant_a.company, line=line, customer_id=customer.id)
    remember_payee(company=tenant_a.company, line=line, customer_id=customer.id)

    row = PayeeMemory.objects.get(
        company=tenant_a.company, token="SUNCITY", target_type=PayeeMemory.TargetType.CUSTOMER,
        target_id=customer.id,
    )
    assert row.hit_count == 2
    assert PayeeMemory.objects.filter(company=tenant_a.company, token="SUNCITY").count() == 1


def test_memory_bonus_alone_cannot_bypass_the_amount_hit_safety_rail(tenant_a):
    """Full token overlap but the line amount matches nothing — score_match's
    own `if not amount_hit: score = min(score, 35)` must still cap it."""
    customer = make_customer(tenant_a.company, name="Sunrise Enterprises")
    ba = BankAccount.objects.create(company=tenant_a.company, name="ICICI", is_default=True)
    confirmed_line = _line(tenant_a.company, ba, amount="1000", narration="SUNCITY DEPT STORE INVOICE")
    remember_payee(company=tenant_a.company, line=confirmed_line, customer_id=customer.id)

    receipt = PaymentService.create_receipt(
        company=tenant_a.company, customer=customer, amount=Decimal("9999.00"), mode="BANK",
    )
    mismatched_line = _line(tenant_a.company, ba, amount="123.45", narration="SUNCITY DEPT STORE INVOICE")
    score = score_match(mismatched_line, receipt=receipt, company=tenant_a.company)
    assert score <= Decimal("35")


def test_confirming_a_match_via_the_api_records_payee_memory(tenant_a):
    """End-to-end: ReconViewSet.confirm -> _confirm_match -> remember_payee,
    not just the standalone helper."""
    customer = make_customer(tenant_a.company, name="Sunrise Enterprises")
    ba = BankAccount.objects.create(company=tenant_a.company, name="ICICI", is_default=True)
    receipt = PaymentService.create_receipt(
        company=tenant_a.company, customer=customer, amount=Decimal("777.00"), mode="BANK",
    )
    line = _line(tenant_a.company, ba, amount="777", narration="SUNCITY DEPT STORE INVOICE")

    resp = tenant_a.client.post(
        "/api/v1/payments/recon/confirm/",
        {"line": line.id, "receipt": receipt.id, "confidence": 90},
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert PayeeMemory.objects.filter(
        company=tenant_a.company, target_type=PayeeMemory.TargetType.CUSTOMER, target_id=customer.id,
        token="SUNCITY",
    ).exists()
