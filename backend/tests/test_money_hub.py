"""Money hub (docs/plans/MONEY_HUB_PLAN.md): the numbers foot to the screens they link to."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from ledgers.services import LedgerService
from payments.models import (
    BankLineMatchStatus,
    BankStatement,
    BankStatementLine,
    BankStatementStatus,
    ChequeStatus,
    GatewayPayment,
    GatewayPaymentStatus,
    PaymentLink,
    PaymentLinkStatus,
    BankAccount,
)
from accounting.services import seed_chart_of_accounts
from payments.promise_to_pay import create_promise
from payments.services import PaymentService
from reporting import money_position
from reporting.money_position import build_position, build_statutory, build_timeline
from reporting.services import ReportService
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    create_draft_purchase,
    make_customer,
    make_product,
    make_supplier,
)

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate


def _sale(tenant, customer, product, price="1000", due_in=None, invoice_days_ago=0):
    extra = {}
    if due_in is not None:
        extra["due_date"] = (TODAY() + timedelta(days=due_in)).isoformat()
    if invoice_days_ago:
        extra["invoice_date"] = (TODAY() - timedelta(days=invoice_days_ago)).isoformat()
    draft = create_draft_invoice(
        tenant, customer,
        [{"product": product.id, "quantity": "1", "unit_price": price, "gst_rate": "0"}],
        invoice_type="NON_GST", **extra,
    )
    resp = tenant.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
    assert resp.status_code == 200, resp.data
    from sales.models import SalesInvoice

    return SalesInvoice.objects.get(pk=draft["id"])


def _purchase(tenant, supplier, product, price="500", due_in=None):
    payload_items = [{"product": product.id, "quantity": "1", "unit_price": price}]
    draft = create_draft_purchase(tenant, supplier, payload_items, purchase_type="NON_GST")
    from purchases.models import PurchaseInvoice

    if due_in is not None:
        PurchaseInvoice.objects.filter(pk=draft["id"]).update(due_date=TODAY() + timedelta(days=due_in))
    resp = tenant.client.post(f"/api/v1/purchases/invoices/{draft['id']}/complete/")
    assert resp.status_code == 200, resp.data
    return PurchaseInvoice.objects.get(pk=draft["id"])


@pytest.fixture
def shop(tenant_a):
    product = make_product(tenant_a.company, gst_rate="0", purchase_price="100", selling_price="1000")
    add_stock(tenant_a, product, "100")
    return tenant_a, product


# ----------------------------------------------------------------------------- API


def test_position_requires_financial_reports_permission(tenant_a):
    assert tenant_a.staff_client.get("/api/v1/money/position/").status_code == 403
    assert tenant_a.staff_client.get("/api/v1/money/timeline/").status_code == 403
    assert tenant_a.staff_client.get("/api/v1/money/statutory/").status_code == 403


def test_kill_switch_hides_the_hub(tenant_a):
    assert tenant_a.client.get("/api/v1/money/position/").status_code == 200
    tenant_a.company.feature_flags = {"ENABLE_MONEY_HUB": False}
    tenant_a.company.save(update_fields=["feature_flags"])
    assert tenant_a.client.get("/api/v1/money/position/").status_code == 404
    assert tenant_a.client.get("/api/v1/money/timeline/").status_code == 404


def test_empty_company_is_all_zero_and_not_partial(tenant_a):
    data = tenant_a.client.get("/api/v1/money/position/").data
    assert data["partial"] == []
    assert Decimal(str(data["net"]["net"])) == 0
    assert Decimal(str(data["cash"]["cleared"])) == 0
    assert data["money_in"]["bills"]["bills"]["count"] == 0
    assert data["actions"] == []


def test_timeline_days_must_be_valid(tenant_a):
    for bad in ("0", "91", "abc", "-1"):
        assert tenant_a.client.get(f"/api/v1/money/timeline/?days={bad}").status_code == 400
    assert tenant_a.client.get("/api/v1/money/timeline/?days=90").status_code == 200


# ----------------------------------------------------------------------------- foot to other screens


def test_headline_foots_to_dashboard_ledger_and_cash_book(shop):
    tenant, product = shop
    customer = make_customer(tenant.company)
    supplier = make_supplier(tenant.company)
    _sale(tenant, customer, product, "1000", due_in=10)
    _sale(tenant, customer, product, "700", due_in=-5)
    _purchase(tenant, supplier, product, "400", due_in=3)
    PaymentService.create_receipt(company=tenant.company, customer=customer, amount=Decimal("300"), mode="CASH")

    pos = build_position(tenant.company)
    dash = ReportService.dashboard(tenant.company)
    assert pos["net"]["receivable"] == LedgerService.company_receivables(tenant.company)
    assert pos["net"]["receivable"] == dash["receivables"]
    assert pos["net"]["payable"] == dash["payables"] == LedgerService.company_payables(tenant.company)
    assert pos["net"]["net"] == pos["net"]["receivable"] - pos["net"]["payable"]
    book = ReportService.cash_book(tenant.company)
    assert pos["cash"]["cleared"] == dash["cash_position"]["closing"] == book["closing"]


def test_ageing_foots_to_the_headline(shop):
    tenant, product = shop
    customer = make_customer(tenant.company)
    _sale(tenant, customer, product, "1000", due_in=10)
    _sale(tenant, customer, product, "700", due_in=-5)
    _sale(tenant, customer, product, "200", due_in=-45)
    bills = build_position(tenant.company)["money_in"]["bills"]
    assert sum(bills["ageing"].values()) == bills["bills"]["amount"]
    assert bills["bills"]["amount"] + bills["not_on_a_bill"] == bills["outstanding"]
    assert bills["ageing"]["days_1_30"] == Decimal("700.00")
    assert bills["ageing"]["days_31_60"] == Decimal("200.00")
    assert bills["overdue"] == {"count": 2, "amount": Decimal("900.00")}


def test_overdue_matches_collections_list_and_sales_history_filter(shop):
    tenant, product = shop
    customer = make_customer(tenant.company)
    _sale(tenant, customer, product, "1000", due_in=10)
    late = _sale(tenant, customer, product, "700", due_in=-5)
    from payments.collections_open import open_invoice_rows

    rows = open_invoice_rows(tenant.company)
    collections_overdue = sum(Decimal(r["outstanding"]) for r in rows if r["days_overdue"] > 0)
    assert build_position(tenant.company)["money_in"]["bills"]["overdue"]["amount"] == collections_overdue
    listed = tenant.client.get("/api/v1/sales/invoices/?overdue=1").data
    results = listed["results"] if isinstance(listed, dict) else listed
    assert [r["id"] for r in results] == [late.id]


def test_due_soon_filter_matches_tile(shop):
    tenant, product = shop
    customer = make_customer(tenant.company)
    soon = _sale(tenant, customer, product, "1000", due_in=4)
    _sale(tenant, customer, product, "700", due_in=20)
    tile = build_position(tenant.company)["money_in"]["bills"]["due_soon"]
    assert tile == {"count": 1, "amount": Decimal("1000.00")}
    listed = tenant.client.get("/api/v1/sales/invoices/?due_soon=1").data
    results = listed["results"] if isinstance(listed, dict) else listed
    assert [r["id"] for r in results] == [soon.id]


def test_purchase_filters_match_payable_tiles(shop):
    tenant, product = shop
    supplier = make_supplier(tenant.company)
    late = _purchase(tenant, supplier, product, "400", due_in=-3)
    soon = _purchase(tenant, supplier, product, "250", due_in=5)
    _purchase(tenant, supplier, product, "100", due_in=40)
    bills = build_position(tenant.company)["money_out"]["bills"]
    assert bills["overdue"] == {"count": 1, "amount": Decimal("400.00")}
    assert bills["due_soon"] == {"count": 1, "amount": Decimal("250.00")}

    def ids(query):
        data = tenant.client.get(f"/api/v1/purchases/invoices/?{query}").data
        return sorted(r["id"] for r in (data["results"] if isinstance(data, dict) else data))

    assert ids("overdue=1") == [late.id]
    assert ids("due_soon=1") == [soon.id]
    assert len(ids("has_balance=1")) == 3


# ----------------------------------------------------------------------------- money in tiles


def test_cheque_tiles_follow_the_cheque_through_its_life(shop):
    tenant, _ = shop
    customer = make_customer(tenant.company)
    receipt = PaymentService.create_receipt(
        company=tenant.company, customer=customer, amount=Decimal("400"), mode="CHEQUE", cheque_number="000123", cheque_bank_name="HDFC",
    )
    money_in = build_position(tenant.company)["money_in"]
    assert money_in["cheques_pending"] == {"count": 1, "amount": Decimal("400.00")}
    assert build_position(tenant.company)["cash"]["cleared"] == 0

    PaymentService.set_cheque_status(receipt=receipt, cheque_status=ChequeStatus.CLEARED)
    pos = build_position(tenant.company)
    assert pos["money_in"]["cheques_pending"]["count"] == 0
    assert pos["cash"]["cleared"] == Decimal("400.00")

    other = PaymentService.create_receipt(
        company=tenant.company, customer=customer, amount=Decimal("90"), mode="CHEQUE", cheque_number="000123", cheque_bank_name="HDFC",
    )
    PaymentService.set_cheque_status(receipt=other, cheque_status=ChequeStatus.BOUNCED)
    pos = build_position(tenant.company)
    assert pos["money_in"]["cheques_bounced"]["count"] == 1
    assert pos["money_in"]["cheques_bounced"]["amount"] == Decimal("90.00")
    assert pos["cash"]["cleared"] == Decimal("400.00")


def test_pending_cheque_list_filter_matches_tile(shop):
    tenant, _ = shop
    customer = make_customer(tenant.company)
    PaymentService.create_receipt(company=tenant.company, customer=customer, amount=Decimal("400"), mode="CHEQUE", cheque_number="000123", cheque_bank_name="HDFC")
    PaymentService.create_receipt(company=tenant.company, customer=customer, amount=Decimal("100"), mode="CASH")
    data = tenant.client.get("/api/v1/payments/receipts/?cheque_status=PENDING_CLEARANCE").data
    rows = data["results"] if isinstance(data, dict) else data
    tile = build_position(tenant.company)["money_in"]["cheques_pending"]
    assert sum(Decimal(str(r["amount"])) for r in rows) == tile["amount"]
    assert len(rows) == tile["count"]
    bad = tenant.client.get("/api/v1/payments/receipts/?cheque_status=NOPE")
    assert bad.status_code == 400


def test_advances_tile_matches_advance_filter(shop):
    tenant, product = shop
    customer = make_customer(tenant.company)
    other = make_customer(tenant.company, name="Meena")
    PaymentService.create_receipt(company=tenant.company, customer=customer, amount=Decimal("500"), mode="CASH")
    PaymentService.create_receipt(company=tenant.company, customer=other, amount=Decimal("300"), mode="CASH")
    invoice = _sale(tenant, other, product, "100", due_in=5)
    receipt = PaymentService.create_receipt(
        company=tenant.company, customer=other, amount=Decimal("100"), mode="CASH"
    )
    PaymentService.allocate_receipt(receipt=receipt, sales_invoice=invoice, amount=Decimal("100"))

    tile = build_position(tenant.company)["money_in"]["advances"]
    data = tenant.client.get("/api/v1/payments/receipts/?advance=1").data
    rows = data["results"] if isinstance(data, dict) else data
    listed = sum(Decimal(str(r["unallocated"])) for r in rows)
    assert tile["amount"] == listed == Decimal("800.00")
    assert tile["count"] == 2
    assert all(Decimal(str(r["unallocated"])) > 0 for r in rows)


def test_tds_receivable_clears_when_certificate_is_recorded(shop):
    tenant, _ = shop
    customer = make_customer(tenant.company)
    receipt = PaymentService.create_receipt(
        company=tenant.company, customer=customer, amount=Decimal("900"), mode="BANK",
        tds_deducted=Decimal("100"), tds_section="194C", require_bank_account=False,
    )
    assert build_position(tenant.company)["money_in"]["tds_receivable"] == {
        "count": 1, "amount": Decimal("100.00"), "older_than_30_days": 0,
    }
    resp = tenant.client.post(
        f"/api/v1/payments/receipts/{receipt.id}/tds-certificate/", {"reference": "16A/22-23/9"}, format="json",
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["tds_certificate_ref"] == "16A/22-23/9"
    assert build_position(tenant.company)["money_in"]["tds_receivable"]["count"] == 0
    received = tenant.client.get("/api/v1/payments/receipts/?tds_certificate=received").data
    pending = tenant.client.get("/api/v1/payments/receipts/?tds_certificate=pending").data
    assert len(received["results"] if isinstance(received, dict) else received) == 1
    assert len(pending["results"] if isinstance(pending, dict) else pending) == 0

    undo = tenant.client.post(
        f"/api/v1/payments/receipts/{receipt.id}/tds-certificate/", {"received": False}, format="json",
    )
    assert undo.status_code == 200
    assert build_position(tenant.company)["money_in"]["tds_receivable"]["count"] == 1


def test_tds_certificate_rules(shop):
    tenant, _ = shop
    customer = make_customer(tenant.company)
    plain = PaymentService.create_receipt(company=tenant.company, customer=customer, amount=Decimal("50"), mode="CASH")
    assert tenant.client.post(f"/api/v1/payments/receipts/{plain.id}/tds-certificate/", {}, format="json").status_code == 400
    withheld = PaymentService.create_receipt(
        company=tenant.company, customer=customer, amount=Decimal("90"), mode="CASH", tds_deducted=Decimal("10"),
    )
    future = (TODAY() + timedelta(days=2)).isoformat()
    assert tenant.client.post(
        f"/api/v1/payments/receipts/{withheld.id}/tds-certificate/", {"received_on": future}, format="json",
    ).status_code == 400
    PaymentService.void_receipt(receipt=withheld, user=tenant.owner, reason="entered twice")
    assert tenant.client.post(f"/api/v1/payments/receipts/{withheld.id}/tds-certificate/", {}, format="json").status_code == 400


def test_promises_tile(shop):
    tenant, product = shop
    customer = make_customer(tenant.company)
    invoice = _sale(tenant, customer, product, "1000", due_in=-10)
    create_promise(
        company=tenant.company, customer=customer, invoice=invoice,
        promised_date=TODAY() + timedelta(days=2), promised_amount=Decimal("400"),
    )
    create_promise(
        company=tenant.company, customer=customer, invoice=invoice,
        promised_date=TODAY() - timedelta(days=3), promised_amount=Decimal("250"),
    )
    promises = build_position(tenant.company)["money_in"]["promises"]
    assert promises["due"] == {"count": 1, "amount": Decimal("400.00")}
    assert promises["broken"] == {"count": 1, "amount": Decimal("250.00")}
    from payments.promise_to_pay import broken_promise_total

    assert promises["broken"]["amount"] == broken_promise_total(tenant.company)
    kinds = [a["kind"] for a in build_position(tenant.company)["actions"]]
    assert "broken_promise" in kinds and "chase_customer" in kinds


def test_bank_gateway_and_link_tiles(tenant_a):
    account = BankAccount.objects.create(company=tenant_a.company, name="Main")
    statement = BankStatement.objects.create(
        company=tenant_a.company, bank_account=account, status=BankStatementStatus.COMMITTED,
    )
    for n, (amount, state) in enumerate([
        ("1000", BankLineMatchStatus.UNMATCHED),
        ("-400", BankLineMatchStatus.UNMATCHED),
        ("250", BankLineMatchStatus.SUGGESTED),
        ("700", BankLineMatchStatus.MATCHED),
        ("90", BankLineMatchStatus.IGNORED),
    ]):
        BankStatementLine.objects.create(
            company=tenant_a.company, statement=statement, txn_date=TODAY(), amount=Decimal(amount),
            match_status=state, line_hash=f"h{n}",
        )
    draft = BankStatement.objects.create(company=tenant_a.company, bank_account=account)
    BankStatementLine.objects.create(
        company=tenant_a.company, statement=draft, txn_date=TODAY(), amount=Decimal("55"), line_hash="d1",
    )
    GatewayPayment.objects.create(
        company=tenant_a.company, provider="razorpay", provider_payment_id="p1", amount=Decimal("600"),
        status=GatewayPaymentStatus.CAPTURED_PENDING_BOOKS,
    )
    PaymentLink.objects.create(company=tenant_a.company, token="t1", amount=Decimal("120"), status=PaymentLinkStatus.SENT)
    PaymentLink.objects.create(company=tenant_a.company, token="t2", amount=Decimal("80"), status=PaymentLinkStatus.PAID)
    PaymentLink.objects.create(
        company=tenant_a.company, token="t3", amount=Decimal("70"), status=PaymentLinkStatus.SENT,
        expires_at=timezone.now() - timedelta(days=1),
    )
    pos = build_position(tenant_a.company)
    assert pos["money_in"]["unmatched_bank_credits"] == {"count": 2, "amount": Decimal("1250.00")}
    assert pos["money_out"]["unmatched_bank_debits"] == {"count": 1, "amount": Decimal("400.00")}
    assert pos["money_in"]["gateway_awaiting_books"] == {"count": 1, "amount": Decimal("600.00")}
    assert pos["money_in"]["payment_links_open"] == {"count": 1, "amount": Decimal("120.00")}


# ----------------------------------------------------------------------------- money out tiles


def test_advances_paid_tile_matches_supplier_payment_filter_and_summary(shop):
    tenant, product = shop
    supplier = make_supplier(tenant.company)
    PaymentService.create_supplier_payment(company=tenant.company, supplier=supplier, amount=Decimal("500"), mode="BANK")
    bill = _purchase(tenant, supplier, product, "200", due_in=5)
    paid = PaymentService.create_supplier_payment(
        company=tenant.company, supplier=supplier, amount=Decimal("200"), mode="CASH",
    )
    PaymentService.allocate_supplier_payment(payment=paid, purchase_invoice=bill, amount=Decimal("200"))

    tile = build_position(tenant.company)["money_out"]["advances_paid"]
    assert tile["amount"] == Decimal("500.00")
    data = tenant.client.get("/api/v1/payments/supplier-payments/?advance=1").data
    rows = data["results"] if isinstance(data, dict) else data
    assert sum(Decimal(str(r["unallocated"])) for r in rows) == tile["amount"]
    summary = tenant.client.get("/api/v1/payments/supplier-payments/summary/").data
    assert Decimal(str(summary["advance"])) == tile["amount"]
    assert Decimal(str(summary["paid"])) == Decimal("700.00")
    # payables are shown beside advances, never netted (decision D-9)
    assert LedgerService.supplier_outstanding(tenant.company, supplier) == Decimal("0")


def test_issued_cheques_are_pending_until_cleared(shop):
    tenant, _ = shop
    supplier = make_supplier(tenant.company)
    payment = PaymentService.create_supplier_payment(
        company=tenant.company, supplier=supplier, amount=Decimal("300"), mode="CHEQUE", cheque_number="000123", cheque_bank_name="HDFC",
    )
    assert build_position(tenant.company)["money_out"]["cheques_issued_pending"] == {
        "count": 1, "amount": Decimal("300.00"),
    }
    data = tenant.client.get("/api/v1/payments/supplier-payments/?cheque_status=PENDING_CLEARANCE").data
    assert len(data["results"] if isinstance(data, dict) else data) == 1
    summary = tenant.client.get("/api/v1/payments/supplier-payments/summary/").data
    assert Decimal(str(summary["cheques_pending"])) == Decimal("300.00")
    assert Decimal(str(summary["paid"])) == 0
    PaymentService.set_supplier_cheque_status(payment=payment, cheque_status=ChequeStatus.CLEARED)
    assert build_position(tenant.company)["money_out"]["cheques_issued_pending"]["count"] == 0
    assert build_position(tenant.company)["cash"]["cleared"] == Decimal("-300.00")


def test_supplier_summary_payable_visible_only_with_financial_permission(shop):
    tenant, product = shop
    supplier = make_supplier(tenant.company)
    _purchase(tenant, supplier, product, "400", due_in=-2)
    owner = tenant.client.get("/api/v1/payments/supplier-payments/summary/").data
    assert Decimal(str(owner["payable"])) == Decimal("400.00")
    assert Decimal(str(owner["overdue"])) == Decimal("400.00")
    one = tenant.client.get(f"/api/v1/payments/supplier-payments/summary/?supplier={supplier.id}").data
    assert Decimal(str(one["payable"])) == Decimal("400.00")


# ----------------------------------------------------------------------------- robustness


def test_one_failing_section_is_named_not_zeroed(shop, monkeypatch):
    tenant, _ = shop

    def boom(company):
        raise RuntimeError("ledger offline")

    monkeypatch.setattr(money_position, "_advances_paid", boom)
    resp = tenant.client.get("/api/v1/money/position/")
    assert resp.status_code == 200
    data = resp.data
    assert "advances_paid" in data["partial"]
    assert data["money_out"]["advances_paid"] is None
    assert data["net"] is not None


def test_cross_tenant_data_never_leaks(shop, tenant_b):
    tenant, product = shop
    other_product = make_product(tenant_b.company, gst_rate="0", sku="B-1", selling_price="1000")
    add_stock(tenant_b, other_product, "10")
    _sale(tenant_b, make_customer(tenant_b.company), other_product, "999", due_in=-1)
    PaymentService.create_supplier_payment(
        company=tenant_b.company, supplier=make_supplier(tenant_b.company), amount=Decimal("77"), mode="BANK",
    )
    pos = build_position(tenant.company)
    assert pos["net"]["receivable"] == 0
    assert pos["money_out"]["advances_paid"]["amount"] == 0
    assert pos["actions"] == []


def test_position_query_count_does_not_grow_with_documents(shop):
    tenant, product = shop
    customer = make_customer(tenant.company)
    supplier = make_supplier(tenant.company)
    for _ in range(2):
        _sale(tenant, customer, product, "100", due_in=-1)
        _purchase(tenant, supplier, product, "50", due_in=-1)
    with CaptureQueriesContext(connection) as small:
        build_position(tenant.company)
    for _ in range(5):
        _sale(tenant, customer, product, "100", due_in=-1)
        _purchase(tenant, supplier, product, "50", due_in=-1)
    with CaptureQueriesContext(connection) as large:
        build_position(tenant.company)
    assert len(large.captured_queries) <= len(small.captured_queries) + 3


def test_no_second_outstanding_formula_outside_ledgers_and_reporting():
    """Architecture guard: the hub reads outstanding from one owner; nobody re-derives it."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parent.parent
    pattern = re.compile(r"def (customer_outstanding|supplier_outstanding|company_receivables|company_payables)\b")
    offenders = []
    for path in root.rglob("*.py"):
        parts = path.relative_to(root).parts
        if parts[0] in {"tests", "ledgers", "migrations", ".venv", "venv"} or "migrations" in parts:
            continue
        if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(str(path.relative_to(root)))
    assert offenders == []


# ----------------------------------------------------------------------------- phase B


def test_timeline_places_bills_promises_and_overdue(shop):
    tenant, product = shop
    customer = make_customer(tenant.company)
    supplier = make_supplier(tenant.company)
    PaymentService.create_receipt(company=tenant.company, customer=customer, amount=Decimal("1000"), mode="CASH")
    due_in = _sale(tenant, customer, product, "600", due_in=10)
    promised = _sale(tenant, customer, product, "300", due_in=25)
    _sale(tenant, customer, product, "50", due_in=-4)
    _sale(tenant, customer, product, "40", due_in=80)
    _purchase(tenant, supplier, product, "200", due_in=5)
    _purchase(tenant, supplier, product, "70", due_in=-2)
    create_promise(
        company=tenant.company, customer=customer, invoice=promised,
        promised_date=TODAY() + timedelta(days=6), promised_amount=Decimal("300"),
    )
    data = build_timeline(tenant.company, days=30)
    by_day = {row["date"]: row for row in data["timeline"]}
    assert by_day[(TODAY() + timedelta(days=10)).isoformat()]["inflow"] == Decimal("600.00")
    assert by_day[(TODAY() + timedelta(days=6)).isoformat()]["inflow"] == Decimal("300.00")
    assert (TODAY() + timedelta(days=25)).isoformat() not in by_day
    assert by_day[(TODAY() + timedelta(days=5)).isoformat()]["outflow"] >= Decimal("200.00")
    assert data["overdue_now"] == {"in": Decimal("50.00"), "out": Decimal("70.00")}
    assert data["beyond_horizon"]["in"] == Decimal("40.00")
    assert data["opening_cash"] == Decimal("1000.00")
    assert data["closing_cash"] == data["opening_cash"] + data["inflow"] - data["outflow"]
    assert data["timeline"][-1]["balance"] == data["closing_cash"]
    assert data["basis"] == "DUE_DATE"
    assert due_in.id


def test_timeline_ignores_resolved_and_past_promises(shop):
    tenant, product = shop
    customer = make_customer(tenant.company)
    invoice = _sale(tenant, customer, product, "300", due_in=12)
    promise = create_promise(
        company=tenant.company, customer=customer, invoice=invoice,
        promised_date=TODAY() + timedelta(days=3), promised_amount=Decimal("300"),
    )
    promise.resolved = True
    promise.save(update_fields=["resolved"])
    data = build_timeline(tenant.company, days=30)
    bill_days = [
        row["date"] for row in data["timeline"] if any(not item.get("estimate") for item in row["items"])
    ]
    assert bill_days == [(TODAY() + timedelta(days=12)).isoformat()]


def test_statutory_lists_tds_and_gst_with_due_dates(shop):
    tenant, _ = shop
    data = tenant.client.get("/api/v1/money/statutory/").data
    kinds = {item["kind"] for item in data["items"]}
    assert "tds_payable" in kinds
    for item in data["items"]:
        assert item["due_date"] > TODAY().isoformat() or item["kind"] in {"tds_payable", "gst_payable"}
    assert "CA" in data["note"]
    assert build_statutory(tenant.company)["as_of"] == TODAY().isoformat()


# ----------------------------------------------------------------------------- books on


def test_books_off_says_there_is_no_ledger_to_compare(tenant_a):
    recon = build_position(tenant_a.company)["reconciliation"]
    assert recon == {"available": False, "reason": "books_off"}


def test_books_on_compares_with_the_control_accounts_and_foots(shop):
    tenant, product = shop
    tenant.company.accounting_enabled = True
    tenant.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant.company)
    customer = make_customer(tenant.company)
    supplier = make_supplier(tenant.company)
    _sale(tenant, customer, product, "1000", due_in=10)
    _purchase(tenant, supplier, product, "400", due_in=3)

    pos = build_position(tenant.company)
    assert pos["partial"] == []
    recon = pos["reconciliation"]
    assert recon["available"] is True
    assert recon["gl_receivable"] == Decimal("1000.00")
    assert recon["gl_payable"] == Decimal("400.00")
    assert recon["difference_receivable"] == 0
    assert recon["difference_payable"] == 0
    assert pos["net"]["receivable"] == Decimal("1000.00")


def test_books_on_with_an_advance_compares_after_taking_the_advance_off(shop):
    tenant, product = shop
    tenant.company.accounting_enabled = True
    tenant.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant.company)
    customer = make_customer(tenant.company)
    _sale(tenant, customer, product, "1000", due_in=10)
    PaymentService.create_receipt(company=tenant.company, customer=customer, amount=Decimal("300"), mode="CASH")

    pos = build_position(tenant.company)
    assert pos["partial"] == []
    recon = pos["reconciliation"]
    assert recon["advances_received"] == Decimal("300.00")
    # On the GL basis the party figure is 1200 less the 2300 advance, so that is what it is compared with;
    # on bills it is compared with 1200 itself. Either way the difference is that subtraction, and the
    # page shows it rather than hiding it.
    taken_off = recon["advances_received"] if recon["basis"] == "GL" else Decimal("0")
    assert recon["difference_receivable"] == pos["net"]["receivable"] - (recon["gl_receivable"] - taken_off)
