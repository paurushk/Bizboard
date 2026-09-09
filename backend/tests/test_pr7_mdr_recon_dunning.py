"""PR 7 — R-020 MDR fee parse + ranked recon, R-042 dunning catch-up,
R-043 sort-then-cap / AA ranking, R-049 blank CSV dates.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from payments.dunning import run_dunning_for_company
from payments.gateway import CashfreeGateway, PayUGateway
from payments.models import (
    BankAccount,
    BankLineMatchStatus,
    BankStatement,
    BankStatementLine,
    BankStatementStatus,
    CustomerReceipt,
    DunningReminder,
    GatewayPayment,
    GatewayPaymentStatus,
    ReceiptStatus,
)
from payments.recon import parse_bank_csv, score_match, suggest_matches
from tests.conftest import make_customer
from tests.test_a07_dunning import _enable_dunning, _overdue_invoice

IST = ZoneInfo("Asia/Kolkata")


def test_cashfree_payu_parse_fee_2_00_mdr():
    cf = CashfreeGateway({})
    charge_body = json.dumps(
        {
            "data": {
                "payment": {
                    "cf_payment_id": "cf_pay_1",
                    "payment_amount": "100.00",
                    "payment_status": "SUCCESS",
                    "payment_service_charge": "2.00",
                }
            }
        }
    ).encode()
    ev = cf.parse_webhook(body=charge_body)
    assert ev is not None
    assert ev.fee == Decimal("2.00")

    charges_body = json.dumps(
        {
            "data": {
                "payment": {
                    "cf_payment_id": "cf_pay_2",
                    "payment_amount": "100.00",
                    "payment_status": "SUCCESS",
                    "charges": {"service_charge": "2.00"},
                }
            }
        }
    ).encode()
    ev2 = cf.parse_webhook(body=charges_body)
    assert ev2 is not None
    assert ev2.fee == Decimal("2.00")

    payu = PayUGateway({})
    ev3 = payu.parse_webhook(
        body=urlencode(
            {
                "amount": "100.00",
                "status": "success",
                "mihpayid": "403993715512345678",
                "txnid": "bb_payu_fee",
                "additionalCharges": "2.00",
            }
        ).encode()
    )
    assert ev3 is not None
    assert ev3.fee == Decimal("2.00")

    ev4 = payu.parse_webhook(
        body=json.dumps(
            {
                "amount": "100.00",
                "status": "success",
                "mihpayid": "403993715512345679",
                "txnid": "bb_payu_disc",
                "disc": "2.00",
            }
        ).encode()
    )
    assert ev4 is not None
    assert ev4.fee == Decimal("2.00")


@pytest.mark.django_db
def test_recon_prefers_net_over_gross(tenant_a):
    customer = make_customer(tenant_a.company)
    today = timezone.localdate()
    gp = GatewayPayment.objects.create(
        company=tenant_a.company,
        provider="cashfree",
        provider_payment_id="pay_mdr_net",
        amount=Decimal("100.00"),
        fee=Decimal("2.00"),
        status=GatewayPaymentStatus.CAPTURED,
    )
    net_receipt = CustomerReceipt.objects.create(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("100.00"),
        receipt_date=today,
        status=ReceiptStatus.POSTED,
        number="RCPT-NET",
        gateway_payment=gp,
    )
    gross_receipt = CustomerReceipt.objects.create(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("98.00"),
        receipt_date=today,
        status=ReceiptStatus.POSTED,
        number="RCPT-GROSS",
    )
    ba = BankAccount.objects.create(company=tenant_a.company, name="HDFC", is_default=True)
    stmt = BankStatement.objects.create(
        company=tenant_a.company,
        bank_account=ba,
        status=BankStatementStatus.COMMITTED,
        period_start=today,
        period_end=today,
    )
    line = BankStatementLine.objects.create(
        company=tenant_a.company,
        statement=stmt,
        txn_date=today,
        amount=Decimal("98.00"),
        narration="PG SETTLEMENT",
        utr="",
        line_hash="mdr-net-1",
        match_status=BankLineMatchStatus.UNMATCHED,
    )
    net_score = score_match(line, receipt=net_receipt)
    gross_score = score_match(line, receipt=gross_receipt)
    assert net_score > gross_score

    suggestions = suggest_matches(company=tenant_a.company, line=line)
    assert suggestions
    assert suggestions[0]["id"] == net_receipt.id
    assert suggestions[0]["confidence"] > next(
        s["confidence"] for s in suggestions if s["id"] == gross_receipt.id
    )


@pytest.mark.django_db
def test_day7_quiet_hours_fires_in_window(tenant_a):
    as_of = date(2026, 8, 31)
    invoice = _overdue_invoice(tenant_a, days=7, as_of=as_of)
    _enable_dunning(invoice.company)
    quiet = datetime(2026, 8, 31, 22, 0, tzinfo=IST)
    result = run_dunning_for_company(invoice.company, now=quiet)
    assert result["reason"] == "quiet_hours"
    assert result["sent"] == 0
    row = DunningReminder.objects.get(invoice=invoice)
    assert row.status == DunningReminder.Status.SKIPPED
    assert row.last_attempt_on is not None
    assert row.days_overdue == 7

    midday = datetime(2026, 9, 1, 12, 0, tzinfo=IST)
    fired = run_dunning_for_company(invoice.company, now=midday)
    assert fired["sent"] == 1
    sent = DunningReminder.objects.get(invoice=invoice, status=DunningReminder.Status.SENT)
    assert sent.days_overdue == 7
    assert sent.last_attempt_on is not None


def test_bank_csv_blank_date_goes_to_skipped():
    content = (
        "Date,Amount,Narration\n"
        ",1000.00,BLANK DATE CREDIT\n"
        "not-a-date,500.00,BAD DATE\n"
        "2026-01-15,abc,BAD AMOUNT\n"
        "2026-01-16,200.00,OK ROW\n"
    )
    rows, skipped = parse_bank_csv(content)
    assert len(rows) == 1
    assert rows[0]["amount"] == Decimal("200.00")
    assert any("blank date" in s.lower() for s in skipped)
    assert any("unparseable date" in s.lower() for s in skipped)
    assert any("invalid amount" in s.lower() for s in skipped)


@pytest.mark.django_db
def test_recon_better_amount_match_wins_over_first_row(tenant_a):
    customer = make_customer(tenant_a.company)
    today = timezone.localdate()
    for i in range(51):
        CustomerReceipt.objects.create(
            company=tenant_a.company,
            customer=customer,
            amount=Decimal("999.00"),
            receipt_date=today,
            status=ReceiptStatus.POSTED,
            number=f"DECOY-{i}",
        )
    hit = CustomerReceipt.objects.create(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("100.00"),
        receipt_date=today,
        status=ReceiptStatus.POSTED,
        number="HIT-100",
    )
    ba = BankAccount.objects.create(company=tenant_a.company, name="ICICI", is_default=True)
    stmt = BankStatement.objects.create(
        company=tenant_a.company,
        bank_account=ba,
        status=BankStatementStatus.COMMITTED,
        period_start=today,
        period_end=today,
    )
    line = BankStatementLine.objects.create(
        company=tenant_a.company,
        statement=stmt,
        txn_date=today,
        amount=Decimal("100.00"),
        narration="INWARD",
        utr="",
        line_hash="r043-cap",
        match_status=BankLineMatchStatus.UNMATCHED,
    )
    suggestions = suggest_matches(company=tenant_a.company, line=line)
    assert suggestions
    assert suggestions[0]["id"] == hit.id


@pytest.mark.django_db
def test_aa_better_amount_match_wins_over_first_fuzzy(tenant_a):
    from banking.models import AaConsent, AaTransaction
    from banking.services import match_aa_to_receipts

    cust = make_customer(tenant_a.company, name="Imp Co")
    consent = AaConsent.objects.create(company=tenant_a.company, consent_id="c-r043")
    first = CustomerReceipt.objects.create(
        company=tenant_a.company,
        customer=cust,
        amount=Decimal("100.00"),
        receipt_date=date(2026, 6, 6),
        status=ReceiptStatus.POSTED,
        number="R-FAR",
        reference="UTR123456789FAR",
        utr="UTR123456789FAR",
    )
    closer = CustomerReceipt.objects.create(
        company=tenant_a.company,
        customer=cust,
        amount=Decimal("100.00"),
        receipt_date=date(2026, 6, 12),
        status=ReceiptStatus.POSTED,
        number="R-NEAR",
        reference="UTR123456789NEAR",
        utr="UTR123456789NEAR",
    )
    AaTransaction.objects.create(
        company=tenant_a.company,
        consent=consent,
        txn_id="bankinternal-r043",
        amount=Decimal("100.00"),
        txn_date=date(2026, 6, 12),
        raw={"narration": "UPI/CR/UTR123456789/IMP CO"},
    )
    assert match_aa_to_receipts(company=tenant_a.company) == 1
    matched = AaTransaction.objects.get(txn_id="bankinternal-r043")
    assert matched.matched_payment_id == closer.id
    assert matched.matched_payment_id != first.id
