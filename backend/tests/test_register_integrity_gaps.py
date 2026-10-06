"""Register integrity gaps: admin 2FA, trial-balance invariant, late/duplicate
gateway callbacks, and output-tax tie-out to the ledger."""

from __future__ import annotations

from decimal import Decimal
from io import StringIO

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.db.models import Sum
from django.utils import timezone
from rest_framework.test import APIClient

from accounting.models import JournalEntry, JournalLine
from accounting.reports import trial_balance
from accounting.services import PostingService, seed_chart_of_accounts
from core.invariants import InvariantViolation
from payments.models import CustomerReceipt, GatewayPayment, GatewayPaymentStatus
from payments.services import PaymentService
from reporting.gst_periods import reopen_period, soft_close_period
from sales.models import SalesInvoice
from tests.conftest import add_stock, create_draft_invoice, make_customer, make_product
from tests.test_phase3_payments import _complete_invoice, _post_sandbox_webhook

pytestmark = pytest.mark.django_db

PASSWORD = "StrongPass123!"


@pytest.fixture
def books(tenant_a):
    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    return tenant_a


# --------------------------------------------------------------------------- #
# 1. Mandatory admin 2FA (SEC-0624)
# --------------------------------------------------------------------------- #
def test_owner_without_mfa_cannot_complete_login_with_password_alone(settings, tenant_a):
    settings.MFA_ENFORCE_FOR_MONEY_ROLES = True
    from accounts.models import UserMfa

    assert not UserMfa.objects.filter(user=tenant_a.owner, confirmed_at__isnull=False).exists()
    cache.clear()
    r = APIClient().post(
        "/api/v1/auth/login/",
        {"email": tenant_a.owner.email, "password": PASSWORD},
        format="json",
    )
    # Once enforced, an un-enrolled owner must not receive a session from the
    # password alone: either a second factor or forced enrolment is demanded.
    issued_session = bool(r.cookies.get("bb_access") or r.cookies.get("bb_refresh")) or (
        r.status_code == 200 and ("access" in r.data or "user" in r.data)
    )
    assert not issued_session, "owner got a full session with no second factor"


# --------------------------------------------------------------------------- #
# 2. Trial-balance invariant via check_invariants
# --------------------------------------------------------------------------- #
def _post_balanced(company):
    cash = PostingService._account(company, "1100")
    cap = PostingService._account(company, "3100")
    PostingService.post(
        company=company, source_type="TEST", source_id=1, purpose="BAL",
        entry_date=timezone.localdate(),
        lines=[{"account": cash, "debit": 500}, {"account": cap, "credit": 500}],
    )
    return cash, cap


def test_check_invariants_passes_on_balanced_postings(books):
    _post_balanced(books.company)
    assert trial_balance(books.company)["balanced"] is True
    out = StringIO()
    call_command("check_invariants", company=books.company.id, stdout=out)
    assert f"ok    company={books.company.id}" in out.getvalue()


def test_check_invariants_fails_on_unbalanced_journal_inserted_via_orm(books):
    cash, cap = _post_balanced(books.company)
    # Bypass the service: a POSTED entry whose lines do not balance.
    bad = JournalEntry.objects.create(
        company=books.company, number="JV-CORRUPT-1", entry_date=timezone.localdate(),
        status=JournalEntry.Status.POSTED, source_type="CORRUPT", source_id=9, purpose="X",
        posted_at=timezone.now(),
    )
    JournalLine.objects.create(company=books.company, entry=bad, account=cash, debit=Decimal("100.00"))
    JournalLine.objects.create(company=books.company, entry=bad, account=cap, credit=Decimal("40.00"))

    tb = trial_balance(books.company)
    assert tb["balanced"] is False
    assert tb["total_debit"] - tb["total_credit"] == Decimal("60.00")

    out = StringIO()
    with pytest.raises(InvariantViolation):  # management command => non-zero exit
        call_command("check_invariants", company=books.company.id, stdout=out)
    body = out.getvalue()
    assert f"FAIL  company={books.company.id}" in body
    assert "gl.trial_balance_zero" in body or "gl.journals_balanced" in body


# --------------------------------------------------------------------------- #
# 3. Gateway callback replay: one receipt, one set of journal entries
# --------------------------------------------------------------------------- #
def _link_and_body(tenant, payment_id):
    inv, customer = _complete_invoice(tenant)
    link = PaymentService.create_payment_link(
        company=tenant.company, amount=Decimal("1000"), sales_invoice=inv,
        customer=customer, provider="sandbox", public_base_url="http://testserver",
    )
    body = {
        "payment_id": payment_id, "amount": "1000.00", "fee": "0",
        "status": "CAPTURED", "payment_link_id": link.provider_link_id,
    }
    return inv, body


def _receipt_je_count(company):
    return JournalEntry.objects.filter(company=company, source_type="CUSTOMER_RECEIPT").count()


def test_duplicate_captured_webhook_yields_one_receipt_and_one_journal_set(books):
    _inv, body = _link_and_body(books, "pay_integrity_dup")
    assert _post_sandbox_webhook(books.client, books.company.id, body).status_code == 200
    receipts = CustomerReceipt.objects.filter(company=books.company).count()
    jes = _receipt_je_count(books.company)
    lines = JournalLine.objects.filter(entry__company=books.company).count()
    assert receipts == 1 and jes >= 1

    assert _post_sandbox_webhook(books.client, books.company.id, body).status_code == 200
    assert CustomerReceipt.objects.filter(company=books.company).count() == 1
    assert _receipt_je_count(books.company) == jes
    assert JournalLine.objects.filter(entry__company=books.company).count() == lines
    assert GatewayPayment.objects.filter(provider_payment_id="pay_integrity_dup").count() == 1


def test_late_replayed_webhook_after_parking_yields_one_receipt_and_one_journal_set(books):
    _inv, body = _link_and_body(books, "pay_integrity_late")
    today = timezone.localdate()
    period = f"{today.year:04d}-{today.month:02d}"
    soft_close_period(books.company, period, books.owner)

    assert _post_sandbox_webhook(books.client, books.company.id, body).status_code == 200
    gp = GatewayPayment.objects.get(provider_payment_id="pay_integrity_late")
    assert gp.status == GatewayPaymentStatus.CAPTURED_PENDING_BOOKS
    assert CustomerReceipt.objects.filter(company=books.company).count() == 0
    assert _receipt_je_count(books.company) == 0

    reopen_period(books.company, period)
    # Late callback arrives again AND the reconciler also runs (twice).
    assert _post_sandbox_webhook(books.client, books.company.id, body).status_code == 200
    PaymentService.reconcile_gateway_captures(older_than_minutes=0)
    PaymentService.reconcile_gateway_captures(older_than_minutes=0)
    assert _post_sandbox_webhook(books.client, books.company.id, body).status_code == 200

    gp.refresh_from_db()
    assert gp.status == GatewayPaymentStatus.CAPTURED
    assert GatewayPayment.objects.filter(provider_payment_id="pay_integrity_late").count() == 1
    receipts = CustomerReceipt.objects.filter(company=books.company)
    assert receipts.count() == 1
    receipt = receipts.get()
    entries = JournalEntry.objects.filter(
        company=books.company, source_type="CUSTOMER_RECEIPT", source_id=receipt.id,
    )
    purposes = list(entries.values_list("purpose", flat=True))
    assert len(purposes) == len(set(purposes)), f"duplicate journal purposes: {purposes}"
    assert entries.count() >= 1
    assert trial_balance(books.company)["balanced"] is True


# --------------------------------------------------------------------------- #
# 4. Tax tie-out: ledger output tax == sum of invoice tax totals
# --------------------------------------------------------------------------- #
def test_output_tax_in_ledger_equals_sum_of_completed_invoice_tax(books):
    product = make_product(books.company, gst_rate="18", selling_price="100")
    add_stock(books, product, "100", unit_cost="60")
    intra = make_customer(books.company, name="Local", state="Karnataka")
    inter = make_customer(books.company, name="Outstate", state="Maharashtra")

    for customer, qty, price in [(intra, "2", "100.00"), (intra, "3", "250.50"), (inter, "5", "199.99")]:
        inv = create_draft_invoice(
            books, customer,
            [{"product": product.id, "quantity": qty, "unit_price": price, "gst_rate": "18"}],
        )
        assert books.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/").status_code == 200

    invoices = SalesInvoice.objects.filter(company=books.company, status=SalesInvoice.Status.COMPLETED)
    assert invoices.count() == 3
    agg = invoices.aggregate(c=Sum("cgst_total"), s=Sum("sgst_total"), i=Sum("igst_total"))
    inv_cgst, inv_sgst, inv_igst = (agg[k] or Decimal("0") for k in ("c", "s", "i"))
    assert inv_igst > 0 and inv_cgst > 0

    tb = {r["account_code"]: r for r in trial_balance(books.company)["rows"]}

    def credit_balance(code):
        row = tb.get(code)
        return (row["credit"] - row["debit"]) if row else Decimal("0")

    assert credit_balance("2210") == inv_cgst
    assert credit_balance("2220") == inv_sgst
    assert credit_balance("2230") == inv_igst
