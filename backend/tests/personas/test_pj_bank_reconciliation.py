"""Bank Reconciliation & Account Aggregator persona journey.

Validates:
1. P5 (Munshi / Accountant) matches incoming bank credits (Account Aggregator / statements)
   against posted customer receipts.
2. Exact UTR matching via transaction narration.
3. Fallback matching via unique amount + date window.
4. Ambiguity protection (duplicate candidate amounts are left unmatched for manual review).
5. Accountant posts direct bank charges to GL (Dr 5300 Bank Charges, Cr 1100 Bank).
6. P2 (Sales Staff / Clerk) is forbidden from banking and bank reconciliation surfaces.
7. Zero invariant violations: assert_all_invariants(company) holds throughout.
"""

from datetime import date
from decimal import Decimal
import pytest

from accounting.services import PostingService
from banking.models import AaConsent, AaTransaction
from banking.services import match_aa_to_receipts
from core.invariants import assert_all_invariants
from payments.models import CustomerReceipt, ReceiptStatus
from tests.personas.fixtures import seed_archetype

pytestmark = pytest.mark.django_db


def test_pj_bank_reconciliation_aa_matching_and_journal():
    trader = seed_archetype("trader")
    company = trader.company
    acct = trader.acct
    cust1 = trader.customers[0]
    cust2 = trader.customers[1]

    # 1. Customer Receipts posted in Bizboard
    today = date.today()
    rcpt_utr = CustomerReceipt.objects.create(
        company=company,
        customer=cust1,
        amount=Decimal("5000.00"),
        receipt_date=today,
        status=ReceiptStatus.POSTED,
        utr="HDFC009283741",
        number="RCPT-UTR-1",
        created_by=acct,
        updated_by=acct,
    )
    rcpt_amt = CustomerReceipt.objects.create(
        company=company,
        customer=cust2,
        amount=Decimal("8250.00"),
        receipt_date=today,
        status=ReceiptStatus.POSTED,
        number="RCPT-AMT-1",
        created_by=acct,
        updated_by=acct,
    )
    # Ambiguous receipts (two receipts with the exact same amount)
    rcpt_ambig1 = CustomerReceipt.objects.create(
        company=company,
        customer=cust1,
        amount=Decimal("1200.00"),
        receipt_date=today,
        status=ReceiptStatus.POSTED,
        number="RCPT-AMB-1",
        created_by=acct,
        updated_by=acct,
    )
    rcpt_ambig2 = CustomerReceipt.objects.create(
        company=company,
        customer=cust2,
        amount=Decimal("1200.00"),
        receipt_date=today,
        status=ReceiptStatus.POSTED,
        number="RCPT-AMB-2",
        created_by=acct,
        updated_by=acct,
    )

    # 2. Ingest Account Aggregator transactions
    consent = AaConsent.objects.create(company=company, consent_id="consent-bank-recon-01")
    txn_utr = AaTransaction.objects.create(
        company=company,
        consent=consent,
        txn_id="BANK-TXN-001",
        amount=Decimal("5000.00"),
        txn_date=today,
        raw={"narration": "UPI/CR/HDFC009283741/CUST1 PAYMENT"},
    )
    txn_amt = AaTransaction.objects.create(
        company=company,
        consent=consent,
        txn_id="BANK-TXN-002",
        amount=Decimal("8250.00"),
        txn_date=today,
        raw={"narration": "NEFT/CR/TRANSFER FROM CLIENT"},
    )
    txn_ambig = AaTransaction.objects.create(
        company=company,
        consent=consent,
        txn_id="BANK-TXN-003",
        amount=Decimal("1200.00"),
        txn_date=today,
        raw={"narration": "IMPS/CR/QUICK TRANSFER"},
    )

    # 3. P5 (Munshi / Accountant) executes automated AA matching
    matched_count = match_aa_to_receipts(company=company)
    assert matched_count == 2, "Must match exactly the 2 non-ambiguous bank credits"

    txn_utr.refresh_from_db()
    assert txn_utr.matched_payment_id == rcpt_utr.id, "Txn 1 must match rcpt_utr via UTR in narration"
    assert txn_utr.raw.get("_match_method") == "ref"

    txn_amt.refresh_from_db()
    assert txn_amt.matched_payment_id == rcpt_amt.id, "Txn 2 must match rcpt_amt via unique amount+date"
    assert txn_amt.raw.get("_match_method") == "amount_date"

    txn_ambig.refresh_from_db()
    assert txn_ambig.matched_payment_id is None, "Ambiguous Txn 3 must be left unmatched for human review"

    # 4. Accountant posts direct bank charge journal entry
    PostingService._ensure_chart(company)
    bank_charges_acct = PostingService._account(company, "5300")
    bank_acct = PostingService._account(company, "1100")
    PostingService.post(
        company=company,
        source_type="JOURNAL",
        source_id=99901,
        purpose="GENERAL",
        entry_date=today,
        lines=[
            {"account": bank_charges_acct, "debit": Decimal("150.00"), "credit": Decimal("0.00")},
            {"account": bank_acct, "debit": Decimal("0.00"), "credit": Decimal("150.00")},
        ],
        user=acct,
    )

    # 5. Boundary check: P2 (Sales Staff) cannot access banking/AA endpoints or post journals
    sales_aa_list = trader.sales_client.get("/api/v1/banking/aa/")
    assert sales_aa_list.status_code in (403, 404), "Sales staff cannot browse AA banking"

    sales_journal = trader.sales_client.post(
        "/api/v1/accounting/journals/",
        {
            "entry_date": today.isoformat(),
            "lines": [
                {"account": bank_charges_acct.id, "debit": "100", "credit": "0"},
                {"account": bank_acct.id, "debit": "0", "credit": "100"},
            ],
        },
        format="json",
    )
    assert sales_journal.status_code in (403, 404), "Sales staff cannot post journals"

    # 6. All ledger invariants hold
    assert_all_invariants(company)
