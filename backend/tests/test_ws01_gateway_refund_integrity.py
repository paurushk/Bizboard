"""WS-01 / Phase 0 — gateway refund integrity (review findings B4-001/002/003).

SQLite has no real row locking, so these assert the *observable* idempotency and
transaction-boundary semantics rather than true concurrency. The concurrency
paths still need a `@pytest.mark.postgres` pass in CI.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import connection

from payments.models import (
    GatewayPayment,
    GatewayPaymentStatus,
    PaymentAllocation,
)
from payments.services import PaymentService, refund_idempotency_key
from tests.conftest import make_customer
from tests.test_sprint_a_accounting_p1 import _completed_invoice, books  # noqa: F401

pytestmark = pytest.mark.django_db


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
class _RecordingAdapter:
    """Captures every idempotency_key passed to .refund(); optionally raises."""

    def __init__(self, *, fail_times=0):
        self.keys: list[str] = []
        self.calls = 0
        self._fail_times = fail_times
        self.in_atomic_at_call: list[bool] = []

    def refund(self, *, provider_payment_id, amount, idempotency_key=""):
        self.calls += 1
        self.in_atomic_at_call.append(connection.in_atomic_block)
        self.keys.append(idempotency_key)
        if self.calls <= self._fail_times:
            raise RuntimeError("provider boom")
        return {"id": f"rfnd_{self.calls}", "amount": str(amount)}


def _captured_gp_with_alloc(tenant, *, amount="1000.00"):
    customer = make_customer(tenant.company)
    inv = _completed_invoice(
        tenant.company, customer, grand=amount, taxable=amount, cgst="0", sgst="0"
    )
    from accounting.services import PostingService

    PostingService.post_sales_invoice(inv, tenant.owner)
    gp = GatewayPayment.objects.create(
        company=tenant.company,
        provider="sandbox",
        provider_payment_id=f"pay_{inv.id}",
        amount=Decimal(amount),
        status=GatewayPaymentStatus.CAPTURED,
    )
    receipt = PaymentService.create_receipt(
        company=tenant.company,
        customer=customer,
        amount=Decimal(amount),
        mode="UPI",
        receipt_date=inv.invoice_date,
        user=tenant.owner,
        gateway_payment=gp,
    )
    PaymentService.allocate_receipt(
        receipt=receipt, sales_invoice=inv, amount=Decimal(amount), user=tenant.owner
    )
    return inv, gp, receipt


def _refund_je_total(company, receipt):
    """Sum of debits on the refund journal entries for a receipt."""
    from django.db.models import Sum

    from accounting.models import JournalEntry, JournalLine

    entries = JournalEntry.objects.filter(
        company=company,
        source_type="CUSTOMER_RECEIPT",
        source_id=receipt.id,
        purpose__startswith="REFUND",
    )
    total = JournalLine.objects.filter(entry__in=entries).aggregate(d=Sum("debit"))["d"]
    return total or Decimal("0")


# --------------------------------------------------------------------------- #
# B4-002 — distinct provider key per logical refund
# --------------------------------------------------------------------------- #
def test_refund_idempotency_key_distinct_per_seq():
    a = refund_idempotency_key(42, Decimal("100.00"), seq=1)
    b = refund_idempotency_key(42, Decimal("100.00"), seq=2)
    legacy = refund_idempotency_key(42, Decimal("100.00"))
    assert a != b
    assert a != legacy and b != legacy
    assert a == "bb-refund-42-1-100.00"
    assert legacy == "bb-refund-42-100.00"  # backwards-compatible form preserved


def test_two_equal_partial_refunds_get_distinct_provider_keys(books, monkeypatch):  # noqa: F811 (books re-imported from test_sprint_a_accounting_p1)
    _inv, gp, receipt = _captured_gp_with_alloc(books)
    rec = _RecordingAdapter()
    monkeypatch.setattr("payments.services.get_adapter", lambda *a, **k: rec)
    monkeypatch.setattr("payments.services.decrypt_gateway_credentials", lambda *a, **k: {})

    PaymentService.refund_gateway_payment(
        gateway_payment=gp, amount=Decimal("400.00"), user=books.owner
    )
    PaymentService.refund_gateway_payment(
        gateway_payment=gp, amount=Decimal("400.00"), user=books.owner
    )

    assert rec.calls == 2
    assert len(set(rec.keys)) == 2, rec.keys  # B4-002: not the same key twice
    gp.refresh_from_db()
    assert gp.status == GatewayPaymentStatus.PARTIALLY_REFUNDED
    partials = gp.raw_payload.get("partial_refunds") or []
    assert [p["amount"] for p in partials] == ["400.00", "400.00"]
    # books unwound for the real total, once each
    assert _refund_je_total(books.company, receipt) == Decimal("800.00")


# --------------------------------------------------------------------------- #
# B4-001 — partial refund unwind is idempotent on the refund key
# --------------------------------------------------------------------------- #
def test_unwind_refund_books_idempotent_on_refund_key(books):  # noqa: F811 (books re-imported from test_sprint_a_accounting_p1)
    _inv, gp, receipt = _captured_gp_with_alloc(books)
    key = refund_idempotency_key(gp.id, Decimal("300.00"), seq=1)

    PaymentService._unwind_refund_books(
        gp, user=books.owner, refund_amount=Decimal("300.00"),
        reason="t", full=False, refund_key=key,
    )
    first_je = _refund_je_total(books.company, receipt)
    reversed_after_first = PaymentAllocation.objects.filter(
        receipt=receipt, reversed_at__isnull=False
    ).count()

    # replay the *same* logical refund — must be a no-op
    PaymentService._unwind_refund_books(
        gp, user=books.owner, refund_amount=Decimal("300.00"),
        reason="t", full=False, refund_key=key,
    )
    assert _refund_je_total(books.company, receipt) == first_je
    assert PaymentAllocation.objects.filter(
        receipt=receipt, reversed_at__isnull=False
    ).count() == reversed_after_first
    assert gp.raw_payload["applied_refund_keys"].count(key) == 1


# --------------------------------------------------------------------------- #
# B4-003 — the provider HTTP call runs outside any DB transaction opened by
# refund_gateway_payment itself (the test runner wraps every test in one atomic
# block, so absolute `in_atomic_block` is always True — instead assert the call
# adds no transaction/savepoint nesting).
# --------------------------------------------------------------------------- #
def test_provider_refund_call_adds_no_transaction_nesting(books, monkeypatch):  # noqa: F811 (books re-imported from test_sprint_a_accounting_p1)
    from django.db import connection

    _inv, gp, receipt = _captured_gp_with_alloc(books)
    baseline_depth = len(connection.savepoint_ids)

    depth_at_call = []

    class _DepthAdapter:
        calls = 0

        def refund(self, *, provider_payment_id, amount, idempotency_key=""):
            self.calls += 1
            depth_at_call.append(len(connection.savepoint_ids))
            return {"id": "rfnd_x", "amount": str(amount)}

    rec = _DepthAdapter()
    monkeypatch.setattr("payments.services.get_adapter", lambda *a, **k: rec)
    monkeypatch.setattr("payments.services.decrypt_gateway_credentials", lambda *a, **k: {})

    PaymentService.refund_gateway_payment(gateway_payment=gp, user=books.owner)

    assert rec.calls == 1
    assert depth_at_call == [baseline_depth], (
        "adapter.refund ran inside an extra transaction/savepoint opened by "
        "refund_gateway_payment"
    )


def test_provider_failure_leaves_pending_outbox_and_no_book_effect(books, monkeypatch):  # noqa: F811 (books re-imported from test_sprint_a_accounting_p1)
    from payments import tasks as payment_tasks
    from payments.models import GatewayRefundOutbox, GatewayRefundOutboxStatus
    from payments.tasks import execute_gateway_refund

    _inv, gp, receipt = _captured_gp_with_alloc(books)
    rec = _RecordingAdapter(fail_times=1)  # first call raises, later calls succeed
    # execute_gateway_refund imports get_adapter from payments.services at call
    # time, so patching the services module is enough for both paths.
    monkeypatch.setattr("payments.services.get_adapter", lambda *a, **k: rec)
    monkeypatch.setattr("payments.services.decrypt_gateway_credentials", lambda *a, **k: {})
    # stop the failure path from eagerly running the retry so we can inspect the
    # intermediate PENDING state.
    monkeypatch.setattr(payment_tasks.execute_gateway_refund, "delay", lambda *a, **k: None)

    PaymentService.refund_gateway_payment(
        gateway_payment=gp, amount=Decimal("250.00"), user=books.owner
    )

    # provider failed -> a durable PENDING row exists, books untouched
    row = GatewayRefundOutbox.objects.get(gateway_payment=gp)
    assert row.status == GatewayRefundOutboxStatus.PENDING
    assert row.idempotency_key == refund_idempotency_key(gp.id, Decimal("250.00"), seq=1)
    assert _refund_je_total(books.company, receipt) == Decimal("0")
    assert not PaymentAllocation.objects.filter(
        receipt=receipt, reversed_at__isnull=False
    ).exists()
    gp.refresh_from_db()
    assert gp.status == GatewayPaymentStatus.CAPTURED

    # the retry beat finishes it -- exactly once, even if run twice
    execute_gateway_refund.apply(args=(row.id,), kwargs={"company_id": books.company.id})
    execute_gateway_refund.apply(args=(row.id,), kwargs={"company_id": books.company.id})

    row.refresh_from_db()
    assert row.status == GatewayRefundOutboxStatus.SUCCEEDED
    assert _refund_je_total(books.company, receipt) == Decimal("250.00")
    gp.refresh_from_db()
    assert gp.status == GatewayPaymentStatus.PARTIALLY_REFUNDED
    assert (gp.raw_payload.get("partial_refunds") or [])[0]["amount"] == "250.00"
