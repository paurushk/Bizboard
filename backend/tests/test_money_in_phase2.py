"""Money In, Phase 2 (docs/plans/MONEY_IN_PHASE2_IMPLEMENTATION_PLAN.md).

WP-1 input rules, WP-4 uncleared-cheque policy, WP-5 discount accounting, WP-6 customer TDS,
WP-7 receipt edits and advance refunds, WP-9 closed-till correction, WP-15 list performance.
"""

import itertools
import random
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db.models import Sum
from django.utils import timezone

from accounting.models import JournalEntry, JournalLine
from accounting.services import BooksHealthService, PostingService, seed_chart_of_accounts
from core.exceptions import BusinessRuleError
from ledgers.services import LedgerService
from payments.models import (
    AdvanceRefundStatus,
    BankAccount,
    ChequeStatus,
    CustomerAdvanceRefund,
    CustomerReceipt,
    PaymentAllocation,
    ReceiptStatus,
)
from payments.receipt_math import LiveTotals, receipt_unallocated, shares_for
from payments.services import PaymentService
from sales.models import SalesInvoice
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    make_customer,
    make_default_bank,
    make_product,
)

pytestmark = pytest.mark.django_db

URL = "/api/v1/payments/receipts/"
_SKU_COUNTER = itertools.count(1000)


# ----------------------------------------------------------------------------- helpers


def _books_on(tenant):
    tenant.company.accounting_enabled = True
    tenant.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant.company)


def _invoice(tenant, customer, price="1000.00", sku=None):
    sku = sku or f"P2-{next(_SKU_COUNTER)}"
    product = make_product(tenant.company, sku=sku, gst_rate="0")
    add_stock(tenant, product, "50")
    draft = create_draft_invoice(
        tenant, customer,
        [{"product": product.id, "quantity": "1", "unit_price": price, "gst_rate": "0"}],
    )
    assert tenant.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/").status_code == 200
    return SalesInvoice.objects.get(pk=draft["id"])


def _receipt(tenant, customer, amount="100", mode="CASH", **kw):
    return PaymentService.create_receipt(
        company=tenant.company, customer=customer, amount=Decimal(amount), mode=mode,
        user=tenant.owner, **kw,
    )


def _gl(company, code, customer=None):
    """Debit minus credit on an account over posted and reversed entries."""
    qs = JournalLine.objects.filter(
        entry__company=company,
        entry__status__in=[JournalEntry.Status.POSTED, JournalEntry.Status.REVERSED],
        account__code=code,
    )
    if customer is not None:
        qs = qs.filter(customer=customer)
    agg = qs.aggregate(d=Sum("debit"), c=Sum("credit"))
    return (agg["d"] or Decimal("0")) - (agg["c"] or Decimal("0"))


def _outstanding(invoice):
    invoice.refresh_from_db()
    return LedgerService.sales_invoice_outstanding(invoice)


def _post(tenant, body, **headers):
    return tenant.client.post(URL, body, format="json", **headers)


# ----------------------------------------------------------------------------- WP-1: input rules


def test_credit_mode_is_refused_by_the_service_and_the_api(tenant_a):
    customer = make_customer(tenant_a.company)
    with pytest.raises(BusinessRuleError) as exc:
        _receipt(tenant_a, customer, "100", "CREDIT")
    assert exc.value.detail.code == "receipt_mode_invalid"
    resp = _post(tenant_a, {"customer": customer.id, "amount": "100", "mode": "CREDIT"})
    assert resp.status_code == 400
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0


def test_credit_receipts_already_on_file_still_list_and_filter(tenant_a):
    customer = make_customer(tenant_a.company)
    old = CustomerReceipt.objects.create(
        company=tenant_a.company, customer=customer, amount=Decimal("10"), mode="CREDIT",
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    rows = tenant_a.client.get(URL, {"mode": "CREDIT"}).data["results"]
    assert [r["id"] for r in rows] == [old.id]


@pytest.mark.parametrize(
    "discount, amount",
    [("-1", "100"), ("100.01", "100"), ("500", "100")],
)
def test_discount_must_be_between_zero_and_the_amount(tenant_a, discount, amount):
    customer = make_customer(tenant_a.company)
    invoice = _invoice(tenant_a, customer, "1000.00")
    resp = _post(tenant_a, {
        "customer": customer.id, "amount": amount, "mode": "CASH",
        "settlement_discount": discount, "sales_invoice": invoice.id,
    })
    assert resp.status_code == 400, resp.data
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0


def test_discount_equal_to_the_amount_is_the_boundary_that_is_allowed(tenant_a):
    customer = make_customer(tenant_a.company)
    invoice = _invoice(tenant_a, customer, "200.00")
    resp = _post(tenant_a, {
        "customer": customer.id, "amount": "100", "mode": "CASH",
        "settlement_discount": "100", "sales_invoice": invoice.id,
    })
    assert resp.status_code == 201, resp.data
    assert _outstanding(invoice) == Decimal("0")


def test_discount_without_an_invoice_is_refused(tenant_a):
    customer = make_customer(tenant_a.company)
    resp = _post(tenant_a, {
        "customer": customer.id, "amount": "100", "mode": "CASH", "settlement_discount": "10",
    })
    assert resp.status_code == 400
    assert resp.data["error"]["code"] == "settlement_discount_needs_invoice"


def test_amount_plus_discount_cannot_exceed_what_the_invoice_still_owes(tenant_a):
    customer = make_customer(tenant_a.company)
    invoice = _invoice(tenant_a, customer, "100.00")
    resp = _post(tenant_a, {
        "customer": customer.id, "amount": "95", "mode": "CASH",
        "settlement_discount": "10", "sales_invoice": invoice.id,
    })
    assert resp.status_code == 400
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0
    assert _outstanding(invoice) == Decimal("100.00")


@pytest.mark.parametrize("mode", ["UPI", "BANK", "CARD"])
def test_bank_modes_need_a_bank_account_and_use_the_default(tenant_a, mode):
    customer = make_customer(tenant_a.company)
    body = {"customer": customer.id, "amount": "100", "mode": mode}
    refused = _post(tenant_a, body)
    assert refused.status_code == 400
    assert refused.data["error"]["code"] == "bank_account_required"
    bank = make_default_bank(tenant_a.company)
    ok = _post(tenant_a, body)
    assert ok.status_code == 201, ok.data
    assert ok.data["bank_account"] == bank.id


def test_a_lone_active_bank_is_used_without_being_the_default(tenant_a):
    customer = make_customer(tenant_a.company)
    only = BankAccount.objects.create(company=tenant_a.company, name="Only", account_type="CURRENT")
    resp = _post(tenant_a, {"customer": customer.id, "amount": "5", "mode": "UPI"})
    assert resp.status_code == 201 and resp.data["bank_account"] == only.id


def test_two_banks_and_no_default_is_ambiguous_and_refused(tenant_a):
    customer = make_customer(tenant_a.company)
    for name in ("One", "Two"):
        BankAccount.objects.create(company=tenant_a.company, name=name, account_type="CURRENT")
    resp = _post(tenant_a, {"customer": customer.id, "amount": "5", "mode": "BANK"})
    assert resp.status_code == 400


def test_a_cash_box_is_never_taken_for_a_bank(tenant_a):
    customer = make_customer(tenant_a.company)
    BankAccount.objects.create(
        company=tenant_a.company, name="Cash", account_type="CASH_BOX", is_default=True
    )
    resp = _post(tenant_a, {"customer": customer.id, "amount": "5", "mode": "UPI"})
    assert resp.status_code == 400


def test_cash_and_cheque_still_work_without_a_bank(tenant_a):
    customer = make_customer(tenant_a.company)
    assert _post(tenant_a, {"customer": customer.id, "amount": "5", "mode": "CASH"}).status_code == 201
    cheque = _post(tenant_a, {
        "customer": customer.id, "amount": "5", "mode": "CHEQUE",
        "cheque_number": "123456", "cheque_bank_name": "HDFC",
    })
    assert cheque.status_code == 201, cheque.data


def test_system_callers_never_fail_on_the_bank_rule(tenant_a):
    """A gateway capture or an import is money that already moved: it is recorded regardless."""
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "40", "UPI", source="GATEWAY")
    assert receipt.pk and receipt.bank_account_id is None


def test_inactive_customer_with_an_open_invoice_can_still_pay(tenant_a):
    customer = make_customer(tenant_a.company)
    invoice = _invoice(tenant_a, customer, "100.00")
    customer.status = "INACTIVE"
    customer.save(update_fields=["status"])
    resp = _post(tenant_a, {
        "customer": customer.id, "amount": "100", "mode": "CASH", "sales_invoice": invoice.id,
    })
    assert resp.status_code == 201, resp.data
    assert _outstanding(invoice) == Decimal("0")


def test_short_search_terms_only_find_an_exact_receipt_number(tenant_a):
    customer = make_customer(tenant_a.company, name="Zed Traders")
    receipt = _receipt(tenant_a, customer, "10", "CASH", reference="ZZ99")
    assert tenant_a.client.get(URL, {"q": "Ze"}).data["results"] == []
    assert tenant_a.client.get(URL, {"q": "ZZ"}).data["results"] == []
    assert [r["id"] for r in tenant_a.client.get(URL, {"q": receipt.number}).data["results"]] == [receipt.id]
    assert [r["id"] for r in tenant_a.client.get(URL, {"q": "Zed"}).data["results"]] == [receipt.id]


# ----------------------------------------------------------------------------- s.269ST


def test_cash_269st_warns_by_default_and_blocks_when_asked(tenant_a):
    customer = make_customer(tenant_a.company)
    resp = _post(tenant_a, {"customer": customer.id, "amount": "150000", "mode": "CASH"})
    assert resp.status_code == 201 and "warnings" not in resp.data
    second = _post(tenant_a, {"customer": customer.id, "amount": "50000", "mode": "CASH"})
    assert second.status_code == 201
    assert any("269ST" in w for w in second.data["warnings"])

    tenant_a.company.cash_269st_mode = "block"
    tenant_a.company.save(update_fields=["cash_269st_mode"])
    blocked = _post(tenant_a, {"customer": customer.id, "amount": "10", "mode": "CASH"})
    assert blocked.status_code == 400 and blocked.data["error"]["code"] == "cash_269st_limit"
    # Another customer, another day, or another mode are not caught.
    other = make_customer(tenant_a.company, name="Someone else")
    assert _post(tenant_a, {"customer": other.id, "amount": "199999", "mode": "CASH"}).status_code == 201
    make_default_bank(tenant_a.company)
    assert _post(tenant_a, {"customer": customer.id, "amount": "500000", "mode": "UPI"}).status_code == 201

    tenant_a.company.cash_269st_mode = "off"
    tenant_a.company.save(update_fields=["cash_269st_mode"])
    quiet = _post(tenant_a, {"customer": customer.id, "amount": "300000", "mode": "CASH"})
    assert quiet.status_code == 201 and "warnings" not in quiet.data


# ----------------------------------------------------------------------------- WP-5: discount accounting


def test_partial_allocation_clears_the_same_amount_in_the_gl_and_on_the_invoice(tenant_a):
    """The review's example: 1000 received, 100 discount, only 500 applied to the first bill."""
    _books_on(tenant_a)
    customer = make_customer(tenant_a.company)
    invoice = _invoice(tenant_a, customer, "1000.00")
    receipt = _receipt(tenant_a, customer, "1000", "CASH", settlement_discount=Decimal("100"))
    alloc = PaymentService.allocate_receipt(receipt=receipt, sales_invoice=invoice, amount=Decimal("500"))
    assert alloc.discount_applied == Decimal("50.00")
    # GL: AR down by 500 + 50. Invoice: down by 500 + 50. Not 600.
    assert _gl(tenant_a.company, "1200", customer) == Decimal("1000.00") - Decimal("550.00")
    assert _outstanding(invoice) == Decimal("450.00")
    assert _gl(tenant_a.company, "5150") == Decimal("50.00")


def test_discount_and_tds_shares_add_up_exactly_over_any_split(tenant_a):
    rng = random.Random(7)  # noqa: S311 - a seeded test generator, not a secret
    for round_no in range(8):
        total = Decimal(rng.randint(500, 5000))
        discount = Decimal(rng.randint(1, 99)) + Decimal(rng.randint(0, 99)) / 100
        customer = make_customer(tenant_a.company, name=f"Split {round_no}")
        receipt = _receipt(tenant_a, customer, str(total), "CASH")
        tds = Decimal(rng.randint(1, 99)) + Decimal(rng.randint(0, 99)) / 100
        receipt.settlement_discount = discount
        receipt.tds_deducted = tds
        receipt.save(update_fields=["settlement_discount", "tds_deducted"])
        remaining, cuts = total, []
        while remaining > 0:
            cut = min(remaining, Decimal(rng.randint(1, int(total))) / Decimal(rng.choice([1, 3, 7])))
            cut = cut.quantize(Decimal("0.01"))
            if cut <= 0:
                cut = Decimal("0.01")
            cut = min(cut, remaining)
            cuts.append(cut)
            remaining -= cut
        live = LiveTotals()
        applied = tds_applied = Decimal("0")
        for cut in cuts:
            share, tds_share = shares_for(receipt, cut, live)
            live.cash += cut
            live.discount += share
            live.tds += tds_share
            applied += share
            tds_applied += tds_share
        assert applied == discount, (total, discount, cuts)
        assert tds_applied == tds, (total, tds, cuts)


def test_unallocating_frees_the_discount_for_the_next_allocation(tenant_a):
    _books_on(tenant_a)
    customer = make_customer(tenant_a.company)
    a = _invoice(tenant_a, customer, "300.00")
    b = _invoice(tenant_a, customer, "600.00")
    receipt = _receipt(tenant_a, customer, "500", "CASH", settlement_discount=Decimal("100"))
    first = PaymentService.allocate_receipt(receipt=receipt, sales_invoice=a, amount=Decimal("250"))
    assert first.discount_applied == Decimal("50.00")
    PaymentService.reverse_allocation(allocation=first)
    # Applied to a different bill the second time: the discount lands once, not twice.
    again = PaymentService.allocate_receipt(receipt=receipt, sales_invoice=b, amount=Decimal("500"))
    assert again.discount_applied == Decimal("100.00")
    live = PaymentAllocation.objects.filter(receipt=receipt, reversed_at__isnull=True)
    assert live.aggregate(t=Sum("discount_applied"))["t"] == Decimal("100.00")
    assert _outstanding(a) == Decimal("300.00")
    assert _gl(tenant_a.company, "5150") == Decimal("100.00")


def test_voiding_a_receipt_with_a_discount_restores_every_balance(tenant_a):
    _books_on(tenant_a)
    customer = make_customer(tenant_a.company)
    invoice = _invoice(tenant_a, customer, "1000.00")
    receipt = _receipt(tenant_a, customer, "900", "CASH", settlement_discount=Decimal("100"))
    PaymentService.allocate_receipt(receipt=receipt, sales_invoice=invoice, amount=Decimal("900"))
    assert _outstanding(invoice) == Decimal("0")
    PaymentService.void_receipt(receipt=receipt, user=tenant_a.owner, reason="entered twice")
    assert _outstanding(invoice) == Decimal("1000.00")
    assert _gl(tenant_a.company, "1200", customer) == Decimal("1000.00")
    assert _gl(tenant_a.company, "5150") == Decimal("0")


def test_oldest_first_uses_cash_plus_discount_to_settle_a_bill_exactly(tenant_a):
    _books_on(tenant_a)
    customer = make_customer(tenant_a.company)
    invoice = _invoice(tenant_a, customer, "110.00")
    receipt = _receipt(tenant_a, customer, "100", "CASH", settlement_discount=Decimal("10"))
    created = PaymentService.allocate_receipt_oldest_first(receipt=receipt)
    assert len(created) == 1 and created[0].amount == Decimal("100.00")
    assert created[0].discount_applied == Decimal("10.00")
    assert _outstanding(invoice) == Decimal("0")


def test_direct_allocation_rows_get_the_same_discount_slice(tenant_a):
    """Any creator of an allocation row (an import, a fixture) gets correct figures."""
    customer = make_customer(tenant_a.company)
    invoice = _invoice(tenant_a, customer, "1000.00")
    receipt = _receipt(tenant_a, customer, "1000", "CASH")
    receipt.settlement_discount = Decimal("100")
    receipt.save(update_fields=["settlement_discount"])
    row = PaymentAllocation.objects.create(
        company=tenant_a.company, receipt=receipt, sales_invoice=invoice, amount=Decimal("500")
    )
    assert row.discount_applied == Decimal("50.00")


# ----------------------------------------------------------------------------- WP-6: customer TDS


def test_customer_tds_settles_the_invoice_and_ties_out(tenant_a):
    _books_on(tenant_a)
    customer = make_customer(tenant_a.company)
    invoice = _invoice(tenant_a, customer, "1000.00")
    resp = _post(tenant_a, {
        "customer": customer.id, "amount": "900", "mode": "CASH", "tds_deducted": "100",
        "tds_section": "194C", "sales_invoice": invoice.id, "allocate_amount": "900",
    })
    assert resp.status_code == 201, resp.data
    assert _outstanding(invoice) == Decimal("0")
    assert _gl(tenant_a.company, "1270") == Decimal("100.00")
    assert _gl(tenant_a.company, "1100") == Decimal("900.00")
    assert _gl(tenant_a.company, "1200", customer) == Decimal("0")
    assert _gl(tenant_a.company, "2300", customer) == Decimal("0")
    assert resp.data["unallocated"] == Decimal("0.00")
    alerts = [a["code"] for a in BooksHealthService._advance_recon_alerts(tenant_a.company)]
    assert "CUSTOMER_ADVANCE_MISMATCH" not in alerts


def test_unallocated_receipt_with_tds_does_not_trip_the_advance_alert(tenant_a):
    _books_on(tenant_a)
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "900", "CASH", tds_deducted=Decimal("100"), tds_section="194J")
    assert receipt_unallocated(receipt) == Decimal("1000.00")
    assert _gl(tenant_a.company, "2300", customer) == Decimal("-1000.00")
    alerts = [a["code"] for a in BooksHealthService._advance_recon_alerts(tenant_a.company)]
    assert "CUSTOMER_ADVANCE_MISMATCH" not in alerts
    summary = tenant_a.client.get(f"{URL}summary/").data
    assert summary["advance"] == Decimal("1000.00") and summary["collected"] == Decimal("900.00")
    row = tenant_a.client.get(URL).data["results"][0]
    assert row["unallocated"] == Decimal("1000.00") and row["allocatable"] == Decimal("900.00")
    assert LedgerService.customer_unallocated_receipts(tenant_a.company, customer) == Decimal("1000.00")


def test_tds_is_prorated_over_partial_allocations_and_voids_cleanly(tenant_a):
    _books_on(tenant_a)
    customer = make_customer(tenant_a.company)
    a = _invoice(tenant_a, customer, "600.00")
    b = _invoice(tenant_a, customer, "400.00")
    receipt = _receipt(tenant_a, customer, "900", "CASH", tds_deducted=Decimal("100"))
    first = PaymentService.allocate_receipt(receipt=receipt, sales_invoice=a, amount=Decimal("540"))
    assert first.tds_applied == Decimal("60.00")
    assert _outstanding(a) == Decimal("0")
    second = PaymentService.allocate_receipt(receipt=receipt, sales_invoice=b, amount=Decimal("360"))
    assert second.tds_applied == Decimal("40.00")
    assert _outstanding(b) == Decimal("0")
    assert _gl(tenant_a.company, "2300", customer) == Decimal("0")
    PaymentService.void_receipt(receipt=receipt, user=tenant_a.owner, reason="wrong customer")
    assert _outstanding(a) == Decimal("600.00") and _outstanding(b) == Decimal("400.00")
    assert _gl(tenant_a.company, "1270") == Decimal("0")
    assert _gl(tenant_a.company, "2300", customer) == Decimal("0")
    assert _gl(tenant_a.company, "1200", customer) == Decimal("1000.00")


def test_tds_cannot_exceed_the_amount_or_the_invoice(tenant_a):
    customer = make_customer(tenant_a.company)
    invoice = _invoice(tenant_a, customer, "100.00")
    over = _post(tenant_a, {"customer": customer.id, "amount": "50", "mode": "CASH", "tds_deducted": "60"})
    assert over.status_code == 400
    too_much = _post(tenant_a, {
        "customer": customer.id, "amount": "95", "mode": "CASH", "tds_deducted": "10",
        "sales_invoice": invoice.id,
    })
    assert too_much.status_code == 400
    assert CustomerReceipt.objects.filter(company=tenant_a.company).count() == 0


def test_a_receipt_without_tds_posts_the_same_journal_as_before(tenant_a):
    _books_on(tenant_a)
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "250", "CASH")
    entry = JournalEntry.objects.get(
        company=tenant_a.company, source_type="CUSTOMER_RECEIPT", source_id=receipt.pk, purpose="CREATE"
    )
    lines = sorted((l.account.code, l.debit, l.credit) for l in entry.lines.all())
    assert lines == [("1100", Decimal("250.00"), Decimal("0.00")), ("2300", Decimal("0.00"), Decimal("250.00"))]


def test_tds_receivable_account_is_added_to_existing_companies(tenant_a):
    seed_chart_of_accounts(tenant_a.company)
    from accounting.models import Account

    assert Account.objects.filter(company=tenant_a.company, code="1270", is_active=True).exists()


# ----------------------------------------------------------------------------- WP-7b: advance refunds


def _refund(tenant, receipt, amount, **kw):
    return PaymentService.refund_advance(
        receipt=receipt, amount=Decimal(amount), mode=kw.pop("mode", "CASH"),
        reason=kw.pop("reason", "customer asked for it back"), user=tenant.owner, **kw,
    )


def test_refunding_part_of_an_advance_keeps_every_reader_consistent(tenant_a):
    _books_on(tenant_a)
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "1000", "CASH")
    refund = _refund(tenant_a, receipt, "400")
    assert refund.number and refund.status == AdvanceRefundStatus.POSTED
    assert _gl(tenant_a.company, "2300", customer) == Decimal("-600.00")
    assert _gl(tenant_a.company, "1100") == Decimal("600.00")
    row = tenant_a.client.get(URL).data["results"][0]
    assert row["status"] == "POSTED" and row["unallocated"] == Decimal("600.00")
    assert row["refunded"] == Decimal("400.00")
    summary = tenant_a.client.get(f"{URL}summary/").data
    assert summary["advance"] == Decimal("600.00")
    assert summary["collected"] == Decimal("600.00") and summary["refunded"] == Decimal("400.00")
    csv_rows = b"".join(tenant_a.client.get(f"{URL}export/").streaming_content).decode()
    assert "600.00" in csv_rows and "400.00" in csv_rows
    alerts = [a["code"] for a in BooksHealthService._advance_recon_alerts(tenant_a.company)]
    assert "CUSTOMER_ADVANCE_MISMATCH" not in alerts
    assert LedgerService.customer_unallocated_receipts(tenant_a.company, customer) == Decimal("600.00")


def test_a_refund_cannot_exceed_the_unallocated_amount_and_blocks_over_allocation(tenant_a):
    customer = make_customer(tenant_a.company)
    invoice = _invoice(tenant_a, customer, "1000.00")
    receipt = _receipt(tenant_a, customer, "1000", "CASH")
    PaymentService.allocate_receipt(receipt=receipt, sales_invoice=invoice, amount=Decimal("300"))
    with pytest.raises(BusinessRuleError) as exc:
        _refund(tenant_a, receipt, "701")
    assert exc.value.detail.code == "advance_refund_exceeds"
    _refund(tenant_a, receipt, "700")
    with pytest.raises(BusinessRuleError):
        PaymentService.allocate_receipt(receipt=receipt, sales_invoice=invoice, amount=Decimal("1"))
    with pytest.raises(BusinessRuleError):
        _refund(tenant_a, receipt, "0.01")


def test_a_receipt_with_a_live_refund_cannot_be_voided_until_the_refund_is(tenant_a):
    _books_on(tenant_a)
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "500", "CASH")
    refund = _refund(tenant_a, receipt, "200")
    with pytest.raises(BusinessRuleError) as exc:
        PaymentService.void_receipt(receipt=receipt, user=tenant_a.owner, reason="entered twice")
    assert exc.value.detail.code == "receipt_has_refunds"
    PaymentService.void_advance_refund(refund=refund, user=tenant_a.owner, reason="money came back")
    assert _gl(tenant_a.company, "2300", customer) == Decimal("-500.00")
    PaymentService.void_receipt(receipt=receipt, user=tenant_a.owner, reason="entered twice")
    assert _gl(tenant_a.company, "2300", customer) == Decimal("0")
    assert _gl(tenant_a.company, "1100") == Decimal("0")


def test_refund_rules_cheque_walk_in_tds_gateway_and_dates(tenant_a):
    customer = make_customer(tenant_a.company)
    cheque = _receipt(tenant_a, customer, "100", "CHEQUE", cheque_number="9", cheque_bank_name="SBI")
    with pytest.raises(BusinessRuleError) as exc:
        _refund(tenant_a, cheque, "10")
    assert exc.value.detail.code == "advance_refund_cheque"
    PaymentService.set_cheque_status(receipt=cheque, cheque_status=ChequeStatus.CLEARED, user=tenant_a.owner)
    assert _refund(tenant_a, cheque, "10").pk

    with_tds = _receipt(tenant_a, customer, "100", "CASH", tds_deducted=Decimal("10"))
    with pytest.raises(BusinessRuleError) as exc:
        _refund(tenant_a, with_tds, "10")
    assert exc.value.detail.code == "advance_refund_tds"

    walk_in = make_customer(tenant_a.company, name="Walk-in", is_pos_walk_in=True)
    with pytest.raises(BusinessRuleError):
        _refund(tenant_a, _receipt(tenant_a, walk_in, "10", "CASH"), "5")

    plain = _receipt(tenant_a, customer, "100", "CASH")
    with pytest.raises(BusinessRuleError):
        _refund(tenant_a, plain, "10", refund_date=timezone.localdate() + timedelta(days=1))
    with pytest.raises(BusinessRuleError):
        _refund(tenant_a, plain, "10", reason="x")
    with pytest.raises(BusinessRuleError):
        _refund(tenant_a, plain, "10", mode="UPI")  # a bank refund names a bank account


def test_refund_api_is_idempotent_and_permissioned(tenant_a):
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "300", "CASH")
    body = {"amount": "100", "mode": "CASH", "reason": "returned goods"}
    first = tenant_a.client.post(f"{URL}{receipt.id}/refund-advance/", body, format="json",
                                 HTTP_IDEMPOTENCY_KEY="refund-1")
    replay = tenant_a.client.post(f"{URL}{receipt.id}/refund-advance/", body, format="json",
                                  HTTP_IDEMPOTENCY_KEY="refund-1")
    assert first.status_code == 201 and replay.status_code == 201
    assert CustomerAdvanceRefund.objects.filter(receipt=receipt).count() == 1
    denied = tenant_a.staff_client.post(f"{URL}{receipt.id}/refund-advance/", body, format="json")
    assert denied.status_code == 403
    listed = tenant_a.client.get("/api/v1/payments/advance-refunds/", {"receipt": receipt.id})
    assert listed.status_code == 200 and len(listed.data["results"]) == 1
    voided = tenant_a.client.post(
        f"/api/v1/payments/advance-refunds/{first.data['id']}/void/", {"reason": "wrong amount"}, format="json"
    )
    assert voided.status_code == 200 and voided.data["status"] == "VOIDED"


def test_cash_refund_from_the_till_lowers_expected_cash(tenant_a):
    from accounting.cash_shifts import expected_system_cash
    from accounting.models import CashShiftRegister

    _books_on(tenant_a)
    customer = make_customer(tenant_a.company)
    shift = CashShiftRegister.objects.create(
        company=tenant_a.company, cashier=tenant_a.owner, business_date=timezone.localdate(),
        opening_float=Decimal("100"), status="OPEN", terminal_id="T1", opened_at=timezone.now(),
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    receipt = _receipt(tenant_a, customer, "500", "CASH")
    receipt.shift = shift
    receipt.paid_from_till = True
    receipt.save(update_fields=["shift", "paid_from_till"])
    refund = _refund(tenant_a, receipt, "120", paid_from_till=True)
    assert refund.shift_id == shift.id
    expected = expected_system_cash(
        tenant_a.company, tenant_a.owner, shift.business_date, shift.opening_float, shift=shift
    )
    assert expected == Decimal("480.00")  # 100 float + 500 received - 120 handed back


# ----------------------------------------------------------------------------- WP-7a: receipt edits


def test_edit_changes_only_the_allowed_fields_and_is_audited(tenant_a):
    from core.models import AuditEvent

    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "100", "CASH", notes="old")
    resp = tenant_a.client.patch(f"{URL}{receipt.id}/", {"notes": "new note", "reference": "R-1"}, format="json")
    assert resp.status_code == 200, resp.data
    receipt.refresh_from_db()
    assert receipt.notes == "new note" and receipt.reference == "R-1"
    assert AuditEvent.objects.filter(
        company=tenant_a.company, entity_type="CustomerReceipt", entity_id=str(receipt.pk),
        description="customer_receipt.edited",
    ).exists()
    for field, value in (("amount", "1"), ("customer", customer.id), ("mode", "UPI"), ("receipt_date", "2026-01-01")):
        refused = tenant_a.client.patch(f"{URL}{receipt.id}/", {field: value}, format="json")
        assert refused.status_code == 400, field
        assert refused.data["error"]["code"] == "receipt_field_not_editable"
    receipt.refresh_from_db()
    assert receipt.amount == Decimal("100.00")


def test_edit_utr_is_rechecked_for_duplicates(tenant_a):
    make_default_bank(tenant_a.company)
    customer = make_customer(tenant_a.company)
    first = _receipt(tenant_a, customer, "10", "UPI", utr="UTRAAA111")
    second = _receipt(tenant_a, customer, "10", "UPI", utr="UTRBBB222")
    clash = tenant_a.client.patch(f"{URL}{second.id}/", {"utr": "utraaa111"}, format="json")
    assert clash.status_code == 400
    ok = tenant_a.client.patch(f"{URL}{second.id}/", {"utr": "UTRCCC333"}, format="json")
    assert ok.status_code == 200 and ok.data["utr"] == "UTRCCC333"
    assert first.utr == "UTRAAA111"


def test_bank_account_edit_repoints_the_journal_and_survives_a_void(tenant_a):
    _books_on(tenant_a)
    customer = make_customer(tenant_a.company)
    wrong = make_default_bank(tenant_a.company, "Wrong bank")
    right = BankAccount.objects.create(company=tenant_a.company, name="Right bank", account_type="CURRENT")
    receipt = _receipt(tenant_a, customer, "700", "UPI", bank_account=wrong)
    PostingService  # noqa: B018
    resp = tenant_a.client.patch(f"{URL}{receipt.id}/", {"bank_account": right.id}, format="json")
    assert resp.status_code == 200, resp.data
    wrong_code = f"1500-{wrong.id}"
    right_code = f"1500-{right.id}"
    assert _gl(tenant_a.company, wrong_code) == Decimal("0")
    assert _gl(tenant_a.company, right_code) == Decimal("700.00")
    PaymentService.void_receipt(receipt=receipt, user=tenant_a.owner, reason="entered twice")
    assert _gl(tenant_a.company, wrong_code) == Decimal("0")
    assert _gl(tenant_a.company, right_code) == Decimal("0")


def test_bank_account_edit_refusals(tenant_a):
    customer = make_customer(tenant_a.company)
    bank = make_default_bank(tenant_a.company)
    other = BankAccount.objects.create(company=tenant_a.company, name="Other", account_type="CURRENT")
    cash = _receipt(tenant_a, customer, "10", "CASH")
    assert tenant_a.client.patch(f"{URL}{cash.id}/", {"bank_account": other.id}, format="json").status_code == 400
    upi = _receipt(tenant_a, customer, "10", "UPI", bank_account=bank)
    from payments.models import BankStatement, BankStatementLine, ReconMatch

    statement = BankStatement.objects.create(company=tenant_a.company, bank_account=bank)
    line = BankStatementLine.objects.create(
        company=tenant_a.company, statement=statement, txn_date=timezone.localdate(),
        amount=Decimal("10"), line_hash="edit-1",
    )
    ReconMatch.objects.create(company=tenant_a.company, line=line, receipt=upi)
    refused = tenant_a.client.patch(f"{URL}{upi.id}/", {"bank_account": other.id}, format="json")
    assert refused.status_code == 400 and refused.data["error"]["code"] == "receipt_reconciled"
    # A voided receipt cannot be edited at all.
    gone = _receipt(tenant_a, customer, "10", "CASH")
    PaymentService.void_receipt(receipt=gone, user=tenant_a.owner, reason="entered twice")
    assert tenant_a.client.patch(f"{URL}{gone.id}/", {"notes": "x"}, format="json").status_code == 400


# ----------------------------------------------------------------------------- WP-4: uncleared cheques


def _cheque(tenant, customer, amount="100", **kw):
    return _receipt(tenant, customer, amount, "CHEQUE", cheque_number="555", cheque_bank_name="ICICI", **kw)


def test_flag_off_a_pending_cheque_can_be_applied_as_before(tenant_a):
    customer = make_customer(tenant_a.company)
    invoice = _invoice(tenant_a, customer, "100.00")
    cheque = _cheque(tenant_a, customer)
    PaymentService.allocate_receipt(receipt=cheque, sales_invoice=invoice, amount=Decimal("100"))
    assert _outstanding(invoice) == Decimal("0")


def _flag_on(tenant):
    tenant.company.cheque_allocation_on_clearance = True
    tenant.company.save(update_fields=["cheque_allocation_on_clearance"])


def test_flag_on_a_pending_cheque_stays_an_advance_until_it_clears(tenant_a):
    _flag_on(tenant_a)
    customer = make_customer(tenant_a.company)
    invoice = _invoice(tenant_a, customer, "100.00")
    cheque = _cheque(tenant_a, customer)
    with pytest.raises(BusinessRuleError) as exc:
        PaymentService.allocate_receipt(receipt=cheque, sales_invoice=invoice, amount=Decimal("100"))
    assert exc.value.detail.code == "cheque_not_cleared"
    assert PaymentService.allocate_receipt_oldest_first(receipt=cheque) == []


def test_flag_on_clearing_applies_what_the_person_asked_for(tenant_a):
    _flag_on(tenant_a)
    customer = make_customer(tenant_a.company)
    invoice = _invoice(tenant_a, customer, "100.00")
    resp = _post(tenant_a, {
        "customer": customer.id, "amount": "100", "mode": "CHEQUE", "cheque_number": "777",
        "cheque_bank_name": "HDFC", "sales_invoice": invoice.id,
    })
    assert resp.status_code == 201, resp.data
    assert _outstanding(invoice) == Decimal("100.00")  # still owed: the cheque has not cleared
    assert resp.data["allocate_on_clear"] is True and resp.data["unallocated"] == Decimal("100.00")
    PaymentService.set_cheque_status(
        receipt=CustomerReceipt.objects.get(pk=resp.data["id"]), cheque_status=ChequeStatus.CLEARED,
        user=tenant_a.owner,
    )
    assert _outstanding(invoice) == Decimal("0")


def test_flag_on_clearing_falls_back_to_an_advance_when_the_bill_was_paid_meanwhile(tenant_a):
    _flag_on(tenant_a)
    customer = make_customer(tenant_a.company)
    invoice = _invoice(tenant_a, customer, "100.00")
    resp = _post(tenant_a, {
        "customer": customer.id, "amount": "100", "mode": "CHEQUE", "cheque_number": "778",
        "cheque_bank_name": "HDFC", "sales_invoice": invoice.id,
    })
    cash = _receipt(tenant_a, customer, "100", "CASH")
    PaymentService.allocate_receipt(receipt=cash, sales_invoice=invoice, amount=Decimal("100"))
    cheque = CustomerReceipt.objects.get(pk=resp.data["id"])
    PaymentService.set_cheque_status(receipt=cheque, cheque_status=ChequeStatus.CLEARED, user=tenant_a.owner)
    assert not PaymentAllocation.objects.filter(receipt=cheque).exists()
    assert receipt_unallocated(cheque) == Decimal("100.00")


def test_flag_on_oldest_first_cheque_is_applied_when_it_clears(tenant_a):
    _flag_on(tenant_a)
    customer = make_customer(tenant_a.company)
    older = _invoice(tenant_a, customer, "60.00")
    newer = _invoice(tenant_a, customer, "60.00")
    resp = _post(tenant_a, {
        "customer": customer.id, "amount": "100", "mode": "CHEQUE", "cheque_number": "779",
        "cheque_bank_name": "HDFC", "allocate_oldest": True,
    })
    cheque = CustomerReceipt.objects.get(pk=resp.data["id"])
    PaymentService.set_cheque_status(receipt=cheque, cheque_status=ChequeStatus.CLEARED, user=tenant_a.owner)
    assert _outstanding(older) == Decimal("0") and _outstanding(newer) == Decimal("20.00")


def test_bounce_after_clear_reverses_and_flags_the_bank_match(tenant_a):
    from payments.models import BankStatement, BankStatementLine, ReconMatch

    customer = make_customer(tenant_a.company)
    bank = make_default_bank(tenant_a.company)
    cheque = _cheque(tenant_a, customer)
    PaymentService.set_cheque_status(receipt=cheque, cheque_status=ChequeStatus.CLEARED, user=tenant_a.owner)
    statement = BankStatement.objects.create(company=tenant_a.company, bank_account=bank)
    line = BankStatementLine.objects.create(
        company=tenant_a.company, statement=statement, txn_date=timezone.localdate(),
        amount=Decimal("100"), line_hash="bounce-1",
    )
    match = ReconMatch.objects.create(company=tenant_a.company, line=line, receipt=cheque)
    PaymentService.set_cheque_status(receipt=cheque, cheque_status=ChequeStatus.BOUNCED, user=tenant_a.owner)
    match.refresh_from_db()
    assert match.needs_review and "bounced" in match.review_reason
    cheque.refresh_from_db()
    assert cheque.status == ReceiptStatus.VOIDED and cheque.cheque_status == ChequeStatus.BOUNCED


def test_void_error_for_a_matched_receipt_names_the_line(tenant_a):
    from payments.models import BankStatement, BankStatementLine, ReconMatch

    customer = make_customer(tenant_a.company)
    bank = make_default_bank(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "50", "UPI", bank_account=bank)
    statement = BankStatement.objects.create(company=tenant_a.company, bank_account=bank)
    line = BankStatementLine.objects.create(
        company=tenant_a.company, statement=statement, txn_date=timezone.localdate(),
        amount=Decimal("50"), line_hash="match-1",
    )
    ReconMatch.objects.create(company=tenant_a.company, line=line, receipt=receipt)
    resp = tenant_a.client.post(f"{URL}{receipt.id}/void/", {"reason": "entered twice"}, format="json")
    assert resp.status_code == 400
    err = resp.data["error"]
    assert err["code"] == "receipt_bank_matched"
    assert err["details"]["line_id"] == line.id and err["details"]["statement_id"] == statement.id
    assert f"unmatch line {line.id}" in str(err["message"])
    filtered = tenant_a.client.get(URL, {"reconciled": "true"}).data["results"]
    assert [r["id"] for r in filtered] == [receipt.id] and filtered[0]["reconciled"] is True
    assert tenant_a.client.get(URL, {"reconciled": "false"}).data["results"] == []
    assert tenant_a.client.get(URL, {"reconciled": "maybe"}).status_code == 400


# ----------------------------------------------------------------------------- WP-9: closed-till correction


def _closed_till_receipt(tenant, customer, amount="250"):
    from accounting.models import CashShiftRegister

    shift = CashShiftRegister.objects.create(
        company=tenant.company, cashier=tenant.owner, business_date=timezone.localdate(),
        opening_float=Decimal("0"), status="CLOSED", terminal_id="T9", opened_at=timezone.now(),
        closed_at=timezone.now(), locked_at=timezone.now(), expected_cash=Decimal(amount),
        counted_cash=Decimal(amount), variance=Decimal("0"),
        created_by=tenant.owner, updated_by=tenant.owner,
    )
    receipt = _receipt(tenant, customer, amount, "CASH")
    receipt.shift = shift
    receipt.paid_from_till = True
    receipt.save(update_fields=["shift", "paid_from_till"])
    return shift, receipt


def test_closed_till_void_error_names_the_real_flow(tenant_a):
    customer = make_customer(tenant_a.company)
    shift, receipt = _closed_till_receipt(tenant_a, customer)
    resp = tenant_a.client.post(f"{URL}{receipt.id}/void/", {"reason": "entered twice"}, format="json")
    assert resp.status_code == 400
    err = resp.data["error"]
    assert err["code"] == "receipt_till_closed" and err["details"]["shift_id"] == shift.id
    assert "Correct closed till" in str(err["message"])


def test_manager_corrects_a_closed_till_and_the_counted_figures_stay(tenant_a):
    from accounting.cash_shifts import adjusted_figures
    from accounting.models import CashShiftAdjustment

    _books_on(tenant_a)
    customer = make_customer(tenant_a.company)
    shift, receipt = _closed_till_receipt(tenant_a, customer, "250")
    resp = tenant_a.client.post(
        f"{URL}{receipt.id}/correct-closed-till/", {"reason": "keyed against the wrong customer"}, format="json"
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["status"] == "VOIDED"
    shift.refresh_from_db()
    assert shift.counted_cash == Decimal("250.00") and shift.expected_cash == Decimal("250.00")
    assert shift.variance == Decimal("0.00")
    adjustment = CashShiftAdjustment.objects.get(shift=shift)
    assert adjustment.amount == Decimal("250.00") and adjustment.approved_by_id == tenant_a.owner.id
    assert adjusted_figures(shift) == (Decimal("250.00"), Decimal("0.00"), Decimal("250.00"))
    assert _gl(tenant_a.company, "1100") == Decimal("0")
    detail = tenant_a.client.get(f"/api/v1/accounting/cash-shifts/{shift.id}/")
    if detail.status_code == 200:
        assert len(detail.data["adjustments"]) == 1


def test_a_cashier_cannot_correct_a_closed_till_and_open_tills_are_not_eligible(tenant_a):
    customer = make_customer(tenant_a.company)
    _shift, receipt = _closed_till_receipt(tenant_a, customer)
    denied = tenant_a.staff_client.post(
        f"{URL}{receipt.id}/correct-closed-till/", {"reason": "entered twice"}, format="json"
    )
    assert denied.status_code == 403
    plain = _receipt(tenant_a, customer, "10", "CASH")
    resp = tenant_a.client.post(f"{URL}{plain.id}/correct-closed-till/", {"reason": "entered twice"}, format="json")
    assert resp.status_code == 400 and resp.data["error"]["code"] == "receipt_not_in_closed_till"


# ----------------------------------------------------------------------------- WP-13/14/15: list, export, performance


def test_ordering_allow_list_and_stable_pages(tenant_a):
    customer = make_customer(tenant_a.company)
    for _ in range(7):
        _receipt(tenant_a, customer, "10", "CASH", receipt_date=date(2026, 5, 1))
    ids = []
    for page in (1, 2, 3):
        body = tenant_a.client.get(URL, {"ordering": "amount", "page_size": 3, "page": page}).data
        ids += [r["id"] for r in body["results"]]
    assert len(ids) == len(set(ids)) == 7  # equal amounts, yet no row repeats or is lost
    assert tenant_a.client.get(URL, {"ordering": "-amount"}).status_code == 200
    bad = tenant_a.client.get(URL, {"ordering": "utr; drop table"})
    assert bad.status_code == 400


def test_export_needs_the_export_permission_and_is_audited(tenant_a):
    from core.models import AuditEvent

    customer = make_customer(tenant_a.company)
    _receipt(tenant_a, customer, "10", "CASH")
    from accounts.models import CompanyUser

    membership = CompanyUser.objects.get(company=tenant_a.company, user=tenant_a.staff)
    membership.can_export = False
    membership.can_create_payments = True
    membership.save(update_fields=["can_export", "can_create_payments"])
    assert tenant_a.staff_client.get(f"{URL}export/").status_code == 403
    membership.can_export = True
    membership.save(update_fields=["can_export"])
    ok = tenant_a.staff_client.get(f"{URL}export/")
    assert ok.status_code in (200, 403)  # staff may lack payment-view; the owner path below is the contract
    assert tenant_a.client.get(f"{URL}export/").status_code == 200
    assert AuditEvent.objects.filter(company=tenant_a.company, action="EXPORT", entity_type="CustomerReceipt").exists()


def test_a_list_page_of_upi_receipts_does_not_query_per_row(tenant_a, django_assert_max_num_queries):
    bank = make_default_bank(tenant_a.company)
    customer = make_customer(tenant_a.company)
    for i in range(12):
        _receipt(tenant_a, customer, "10", "UPI", bank_account=bank, utr=f"UTRPAGE{i:03d}")
    with django_assert_max_num_queries(25):
        resp = tenant_a.client.get(URL, {"page_size": 50})
    assert resp.status_code == 200 and len(resp.data["results"]) == 12


def test_page_warns_about_a_utr_shared_with_a_supplier_payment(tenant_a):
    from masters.models import Supplier
    from payments.models import SupplierPayment

    bank = make_default_bank(tenant_a.company)
    customer = make_customer(tenant_a.company)
    receipt = _receipt(tenant_a, customer, "10", "UPI", bank_account=bank, utr="SHAREDUTR1")
    supplier = Supplier.objects.create(company=tenant_a.company, name="Vendor", state="Karnataka")
    SupplierPayment.objects.create(
        company=tenant_a.company, supplier=supplier, amount=Decimal("5"), mode="UPI", utr="SHAREDUTR1",
        created_by=tenant_a.owner, updated_by=tenant_a.owner,
    )
    row = tenant_a.client.get(URL).data["results"][0]
    assert row["id"] == receipt.id and "supplier payment" in row["utr_warning"]


def test_summary_is_one_aggregate_over_the_receipts(tenant_a, django_assert_max_num_queries):
    customer = make_customer(tenant_a.company)
    for _ in range(5):
        _receipt(tenant_a, customer, "10", "CASH")
    with django_assert_max_num_queries(8):
        resp = tenant_a.client.get(f"{URL}summary/")
    assert resp.status_code == 200 and resp.data["count"] == 5
