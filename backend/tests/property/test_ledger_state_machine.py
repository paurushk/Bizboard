"""WP-F5 / DIM6-08: random sequences of real document operations never break the books.

Hypothesis draws a sequence of operations (sales, GST sales, receipts with and without an
invoice, receipts with TDS, voided receipts, sales returns, inter-state (IGST) sales, godown
transfers, purchases, supplier payments, sales and purchase credit notes, cancellations). Each example gets a fresh
company inside a savepoint that is rolled back afterwards; every step goes through the real
API/services, and after every step every ``gl``, ``gst``, ``money``, ``inventory`` and
``projection`` invariant must hold. An operation the product refuses (a 4xx or a validation error,
e.g. returning more than was sold) is a legal outcome, not a failure; the invariants are the oracle. A failure prints the shrunk sequence; add it below as a fixed regression
case in ``REGRESSIONS`` so it stays covered.

Runs for books-on and shadow-books companies. CI: ``LEDGER_PROPERTY_EXAMPLES`` (default 15)
on the Postgres job; the nightly workflow raises it.
"""

from __future__ import annotations

import os
from decimal import Decimal
from itertools import count

import pytest
from django.db import transaction
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.invariants import run_invariants
from tests.conftest import make_customer, make_product, make_supplier, make_tenant
from tests.test_ar_ap_agreement_matrix import (
    _books,
    _purchase,
    _purchase_cn,
    _receipt,
    _sale,
    _sales_cn,
    _supplier_payment,
)

pytestmark = [pytest.mark.django_db, pytest.mark.no_invariant_check]

EXAMPLES = int(os.environ.get("LEDGER_PROPERTY_EXAMPLES", "15"))
DOMAINS = {"gl", "gst", "money", "inventory", "projection"}
OPS = (
    "sale", "gst_sale", "igst_sale", "receipt_on_invoice", "advance_receipt", "tds_receipt", "void_receipt",
    "sales_return", "transfer", "purchase", "pay_supplier", "credit_note", "purchase_credit_note", "cancel",
)
_slug = count(1)


class _Rollback(Exception):
    pass


class Books:
    """One company and the open documents the next operation can act on."""

    def __init__(self, books_on: bool):
        self.t = make_tenant(f"prop{next(_slug)}")
        _books(self.t, books_on)
        company = self.t.company
        self.customer = make_customer(company)
        self.outstate_customer = make_customer(company, name="Out of state", state="Maharashtra")
        self.supplier = make_supplier(company)
        self.product = make_product(company, sku="PROP-1")
        self.invoices: list = []
        self.bills: list = []
        self.receipts: list = []
        self.trace: list[str] = []

    def apply(self, op: str, amount: int):
        from django.core.exceptions import ValidationError as DjangoValidationError
        from rest_framework.exceptions import ValidationError

        try:
            done = self._apply(op, amount)
        except (AssertionError, ValidationError, DjangoValidationError) as exc:
            # The product refused the operation: legal. The invariants below still have to hold.
            self.trace.append(f"{op}({amount})=refused:{str(exc)[:60]}")
            return
        if done:
            self.trace.append(f"{op}({amount})")

    def _apply(self, op: str, amount: int) -> bool:
        from ledgers.services import LedgerService
        from payments.services import PaymentService
        from sales.models import SalesInvoice

        amt = str(Decimal(amount))
        if op == "sale":
            self.invoices.append(_sale(self.t, self.customer, self.product, amount=amt))
        elif op == "gst_sale":
            self.invoices.append(self._gst_sale(amt))
        elif op == "igst_sale":
            # Kept off self.invoices: receipts and notes below act on the home-state customer.
            self._gst_sale(amt, customer=self.outstate_customer)
        elif op == "transfer":
            self._transfer()
        elif op == "receipt_on_invoice" and self.invoices:
            inv = SalesInvoice.objects.get(pk=self.invoices[-1].pk)
            due = LedgerService.sales_invoice_outstanding(inv)
            if due > 0:
                self.receipts.append(_receipt(self.t, self.customer, str(min(due, Decimal(amt))), invoice=inv))
        elif op == "advance_receipt":
            self.receipts.append(_receipt(self.t, self.customer, amt))
        elif op == "tds_receipt" and self.invoices:
            inv = SalesInvoice.objects.get(pk=self.invoices[-1].pk)
            gross = min(LedgerService.sales_invoice_outstanding(inv), Decimal(amt))
            if gross < 10:
                return False
            tds = (gross / 10).quantize(Decimal("0.01"))
            r = PaymentService.create_receipt(
                company=self.t.company, customer=self.customer, amount=gross - tds, mode="CASH",
                tds_deducted=tds, tds_section="194C", user=self.t.owner,
            )
            PaymentService.allocate_receipt(receipt=r, sales_invoice=inv, amount=gross - tds, user=self.t.owner)
            self.receipts.append(r)
        elif op == "void_receipt" and self.receipts:
            PaymentService.void_receipt(receipt=self.receipts.pop(), user=self.t.owner, reason="property test")
        elif op == "sales_return" and self.invoices:
            inv = SalesInvoice.objects.get(pk=self.invoices[-1].pk)
            line = inv.items.first()
            if inv.status != "COMPLETED" or line is None:
                return False
            ret = self.t.client.post(
                "/api/v1/sales/returns/",
                {"customer": self.customer.id, "sales_invoice": inv.id,
                 "items": [{"product": line.product_id, "quantity": "1", "unit_price": str(line.unit_price)}]},
                format="json",
            )
            assert ret.status_code == 201, ret.data
            done = self.t.client.post(f"/api/v1/sales/returns/{ret.data['id']}/complete/")
            assert done.status_code == 200, done.data
        elif op == "purchase":
            self.bills.append(_purchase(self.t, self.supplier, self.product, amount=amt))
        elif op == "pay_supplier" and self.bills:
            _supplier_payment(self.t, self.supplier, "1", invoice=self.bills[-1])
        elif op == "purchase_credit_note" and self.bills:
            _purchase_cn(self.t, self.supplier, self.bills[-1], self.product, "1")
        elif op == "credit_note" and self.invoices:
            inv = self.invoices[-1]
            if inv.invoice_type == "NON_GST" and SalesInvoice.objects.get(pk=inv.pk).status == "COMPLETED":
                _sales_cn(self.t, self.customer, inv, self.product, "1")
        elif op == "cancel" and self.invoices:
            inv = self.invoices.pop()
            self.t.client.post(f"/api/v1/sales/invoices/{inv.pk}/cancel/", {"reason": "property test"}, format="json")
        else:
            return False
        return True

    def _transfer(self):
        from inventory.models import Warehouse
        from tests.conftest import add_stock

        company = self.t.company
        try:
            add_stock(self.t, self.product, "5")  # also creates the default godown on a fresh company
        except Exception:  # noqa: BLE001 - opening stock already recorded for this product
            pass
        source = Warehouse.objects.filter(company=company).order_by("id").first()
        target, _ = Warehouse.objects.get_or_create(company=company, name="Property godown 2")
        tr = self.t.client.post(
            "/api/v1/inventory/transfers/",
            {"from_warehouse": source.id, "to_warehouse": target.id, "notes": "property test",
             "lines": [{"product": self.product.id, "quantity": "1.000"}]},
            format="json",
        )
        assert tr.status_code == 201, tr.data
        done = self.t.client.post(f"/api/v1/inventory/transfers/{tr.data['id']}/complete/")
        assert done.status_code == 200, done.data
        got = self.t.client.post(f"/api/v1/inventory/transfers/{tr.data['id']}/receive/", {}, format="json")
        assert got.status_code == 200, got.data

    def _gst_sale(self, amount: str, customer=None):
        from sales.models import SalesInvoice
        from tests.conftest import add_stock, create_draft_invoice

        try:
            add_stock(self.t, self.product, "5")
        except Exception:  # noqa: BLE001 - opening stock already recorded for this product
            pass
        draft = create_draft_invoice(
            self.t, customer or self.customer,
            [{"product": self.product.id, "quantity": "1", "unit_price": amount, "gst_rate": "18"}],
        )
        done = self.t.client.post(f"/api/v1/sales/invoices/{draft['id']}/complete/")
        assert done.status_code == 200, done.data
        return SalesInvoice.objects.get(pk=draft["id"])

    def check(self):
        failures = run_invariants(self.t.company, only=DOMAINS)
        assert not failures, f"after {' -> '.join(self.trace)}: {failures}"


def _run(books_on: bool, ops: list[tuple[str, int]]):
    try:
        with transaction.atomic():
            books = Books(books_on)
            for op, amount in ops:
                books.apply(op, amount)
                books.check()
            raise _Rollback
    except _Rollback:
        pass


operations = st.lists(
    st.tuples(st.sampled_from(OPS), st.integers(min_value=1, max_value=5000)), min_size=1, max_size=8,
)


@settings(
    max_examples=EXAMPLES,
    deadline=None,
    derandomize=bool(os.environ.get("CI")),
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(ops=operations, books_on=st.booleans())
def test_random_document_sequences_keep_the_books_whole(db, ops, books_on):
    _run(books_on, ops)


# Shrunk failures found by the test above, kept as fixed cases.
REGRESSIONS: list[tuple[bool, list[tuple[str, int]]]] = [
    (True, [("gst_sale", 999), ("receipt_on_invoice", 1179), ("credit_note", 1)]),
    (False, [("sale", 1000), ("cancel", 1), ("advance_receipt", 50), ("purchase", 70), ("pay_supplier", 1)]),
    (False, [("cancel", 463), ("cancel", 1), ("tds_receipt", 1), ("transfer", 1)]),
]


@pytest.mark.parametrize(("books_on", "ops"), REGRESSIONS)
def test_known_sequences(db, books_on, ops):
    _run(books_on, ops)


@pytest.mark.parametrize("books_on", [True, False])
def test_every_operation_takes_effect_on_a_happy_path(db, books_on):
    # Guards the generator itself: if an operation were always refused, the random test above
    # would pass while exercising nothing.
    happy = [
        ("gst_sale", 1000), ("igst_sale", 400), ("transfer", 1), ("tds_receipt", 500), ("void_receipt", 1), ("sales_return", 1),
        ("sale", 800), ("receipt_on_invoice", 300), ("credit_note", 1), ("advance_receipt", 50),
        ("purchase", 700), ("pay_supplier", 1), ("purchase_credit_note", 1), ("cancel", 1),
    ]
    assert {op for op, _ in happy} == set(OPS)
    with transaction.atomic():
        books = Books(books_on)
        for op, amount in happy:
            books.apply(op, amount)
            books.check()
        refused = [step for step in books.trace if "=refused" in step]
        transaction.set_rollback(True)
    assert not refused, refused
