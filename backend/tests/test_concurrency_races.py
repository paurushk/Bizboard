"""P0-201 / P0-202 / CR-014 / CR-036 — concurrent stock, payment, and return races.

These exercise select_for_update paths in InventoryService / PaymentService /
ReturnService / PurchaseService. SQLite does not enforce row locks meaningfully,
so tests are marked `postgres` and skip unless the DB vendor is PostgreSQL
(CI with DATABASE_URL).
"""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest
from django.db import connection

from core.exceptions import BusinessRuleError
from inventory.models import MovementType, StockBalance
from inventory.services import InventoryService
from payments.models import PaymentAllocation
from payments.services import PaymentService
from django.db.models import Sum
from tests.conftest import (
    add_stock,
    create_draft_invoice,
    make_customer,
    make_product,
)

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgres]


def _require_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row-level locking (select_for_update)")


def test_concurrent_stock_oversell_blocked(tenant_a):
    """P0-201 — two SALE movements for qty 1 against stock 1 → one wins."""
    _require_postgres()
    tenant_a.company.negative_stock_policy = "BLOCK"
    tenant_a.company.save(update_fields=["negative_stock_policy"])
    product = make_product(tenant_a.company, sku="RACE-STOCK")
    add_stock(tenant_a, product, "1")

    successes: list[int] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(2, timeout=10)

    def sell():
        connection.close()
        try:
            barrier.wait()
            InventoryService.post_movement(
                company=tenant_a.company,
                product=product,
                movement_type=MovementType.SALE,
                quantity=Decimal("1"),
                reference_type="race_test",
                reference_id="stock",
                user=tenant_a.owner,
            )
            successes.append(1)
        except BusinessRuleError as exc:
            errors.append(exc)
        except Exception as exc:  # pragma: no cover — unexpected
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=sell) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(successes) == 1, (successes, errors)
    assert len(errors) == 1
    assert StockBalance.objects.get(product=product).on_hand == Decimal("0")


def test_concurrent_payment_over_allocation_blocked(tenant_a):
    """P0-202 — two allocations of full receipt amount → one wins."""
    _require_postgres()
    product = make_product(tenant_a.company, sku="RACE-PAY")
    add_stock(tenant_a, product, "100")
    customer = make_customer(tenant_a.company, state="Karnataka")
    inv = create_draft_invoice(tenant_a, customer, [
        {"product": product.id, "quantity": "10", "unit_price": "100"},
    ])
    assert tenant_a.client.post(
        f"/api/v1/sales/invoices/{inv['id']}/complete/"
    ).status_code == 200

    from sales.models import SalesInvoice

    invoice = SalesInvoice.objects.get(pk=inv["id"])
    receipt = PaymentService.create_receipt(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("1000"),
        mode="UPI",
        user=tenant_a.owner,
    )

    successes: list[int] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(2, timeout=10)

    def allocate():
        connection.close()
        try:
            barrier.wait()
            PaymentService.allocate_receipt(
                receipt=receipt,
                sales_invoice=invoice,
                amount=Decimal("1000"),
                user=tenant_a.owner,
            )
            successes.append(1)
        except BusinessRuleError as exc:
            errors.append(exc)
        except Exception as exc:  # pragma: no cover
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=allocate) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(successes) == 1, (successes, errors)
    assert len(errors) == 1
    allocated = (
        PaymentAllocation.objects.filter(receipt=receipt).aggregate(t=Sum("amount"))["t"]
        or Decimal("0")
    )
    assert allocated == Decimal("1000.00")


def test_concurrent_sales_complete_oversell_blocked(tenant_a):
    """P0-201 e2e — two Completes each needing qty 1 against stock 1 → one wins."""
    _require_postgres()
    from sales.models import SalesInvoice
    from sales.services import SalesService

    tenant_a.company.negative_stock_policy = "BLOCK"
    tenant_a.company.save(update_fields=["negative_stock_policy"])
    product = make_product(tenant_a.company, sku="RACE-COMPLETE")
    add_stock(tenant_a, product, "1")
    customer = make_customer(tenant_a.company, state="Karnataka")

    drafts = []
    for _ in range(2):
        inv = create_draft_invoice(tenant_a, customer, [
            {"product": product.id, "quantity": "1", "unit_price": "100"},
        ])
        drafts.append(SalesInvoice.objects.get(pk=inv["id"]))

    successes: list[int] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(2, timeout=10)

    def complete_one(invoice: SalesInvoice):
        connection.close()
        try:
            barrier.wait()
            SalesService.complete(invoice, tenant_a.owner)
            successes.append(1)
        except BusinessRuleError as exc:
            errors.append(exc)
        except Exception as exc:  # pragma: no cover
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=complete_one, args=(d,)) for d in drafts]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(successes) == 1, (successes, errors)
    assert len(errors) == 1
    assert StockBalance.objects.get(product=product).on_hand == Decimal("0")


def test_concurrent_journal_post_one_posted(tenant_a):
    """W0-01 — two PostingService.post calls for the same source → one POSTED journal."""
    _require_postgres()
    from django.utils import timezone

    from accounting.models import JournalEntry
    from accounting.services import PostingService, seed_chart_of_accounts

    tenant_a.company.accounting_enabled = True
    tenant_a.company.save(update_fields=["accounting_enabled"])
    seed_chart_of_accounts(tenant_a.company, tenant_a.owner)
    cash = PostingService._account(tenant_a.company, "1100")
    equity = PostingService._account(tenant_a.company, "3100")
    pks: list[int] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(2, timeout=10)

    def post_one():
        connection.close()
        try:
            barrier.wait()
            entry = PostingService.post(
                company=tenant_a.company,
                source_type="TEST_W0_01",
                source_id=1001,
                purpose="SALE",
                entry_date=timezone.localdate(),
                user=tenant_a.owner,
                lines=[
                    {"account": cash, "debit": Decimal("10")},
                    {"account": equity, "credit": Decimal("10")},
                ],
            )
            if entry is not None:
                pks.append(entry.pk)
        except Exception as exc:  # pragma: no cover
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=post_one) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, errors
    assert len(set(pks)) == 1
    assert (
        JournalEntry.objects.filter(
            company=tenant_a.company,
            source_type="TEST_W0_01",
            source_id=1001,
            purpose="SALE",
            status=JournalEntry.Status.POSTED,
        ).count()
        == 1
    )


def test_concurrent_sales_return_over_return_blocked(tenant_a):
    """CR-014 — two Completes each returning the last unit on one invoice → one wins."""
    _require_postgres()
    from sales.models import SalesReturn
    from sales.return_service import ReturnService

    product = make_product(tenant_a.company, sku="RACE-SR-RET")
    add_stock(tenant_a, product, "1")
    customer = make_customer(tenant_a.company, state="Karnataka")
    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100"}],
    )
    assert tenant_a.client.post(
        f"/api/v1/sales/invoices/{inv['id']}/complete/"
    ).status_code == 200

    returns = []
    for _ in range(2):
        ret = tenant_a.client.post(
            "/api/v1/sales/returns/",
            {
                "customer": customer.id,
                "sales_invoice": inv["id"],
                "items": [{"product": product.id, "quantity": "1", "unit_price": "100"}],
            },
            format="json",
        )
        assert ret.status_code == 201, ret.data
        returns.append(SalesReturn.objects.get(pk=ret.data["id"]))

    successes: list[int] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(2, timeout=10)

    def complete_one(sales_return: SalesReturn):
        connection.close()
        try:
            barrier.wait()
            ReturnService.complete_return(sales_return, tenant_a.owner)
            successes.append(1)
        except BusinessRuleError as exc:
            errors.append(exc)
        except Exception as exc:  # pragma: no cover
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=complete_one, args=(r,)) for r in returns]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(successes) == 1, (successes, errors)
    assert len(errors) == 1
    assert (
        SalesReturn.objects.filter(
            sales_invoice_id=inv["id"],
            status=SalesReturn.Status.COMPLETED,
        ).count()
        == 1
    )


def test_concurrent_purchase_return_over_return_blocked(tenant_a):
    """CR-036 — two Completes each returning the last unit on one invoice → one wins."""
    _require_postgres()
    from purchases.models import PurchaseReturn
    from purchases.services import PurchaseService
    from tests.conftest import create_draft_purchase, make_supplier

    product = make_product(tenant_a.company, sku="RACE-PR-RET")
    supplier = make_supplier(tenant_a.company)
    pur = create_draft_purchase(
        tenant_a,
        supplier,
        [{"product": product.id, "quantity": "1", "unit_price": "80"}],
    )
    assert tenant_a.client.post(
        f"/api/v1/purchases/invoices/{pur['id']}/complete/"
    ).status_code == 200

    returns = []
    for _ in range(2):
        ret = tenant_a.client.post(
            "/api/v1/purchases/returns/",
            {
                "supplier": supplier.id,
                "purchase_invoice": pur["id"],
                "items": [{"product": product.id, "quantity": "1", "unit_price": "80"}],
            },
            format="json",
        )
        assert ret.status_code == 201, ret.data
        returns.append(PurchaseReturn.objects.get(pk=ret.data["id"]))

    successes: list[int] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(2, timeout=10)

    def complete_one(purchase_return: PurchaseReturn):
        connection.close()
        try:
            barrier.wait()
            PurchaseService.complete_return(purchase_return, tenant_a.owner)
            successes.append(1)
        except BusinessRuleError as exc:
            errors.append(exc)
        except Exception as exc:  # pragma: no cover
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=complete_one, args=(r,)) for r in returns]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(successes) == 1, (successes, errors)
    assert len(errors) == 1
    assert (
        PurchaseReturn.objects.filter(
            purchase_invoice_id=pur["id"],
            status=PurchaseReturn.Status.COMPLETED,
        ).count()
        == 1
    )


def test_concurrent_gst_soft_close_and_complete_race(tenant_a):
    """CR-156 / CR-104 residual: soft_close vs Complete TOCTOU race on missing period row."""
    _require_postgres()
    from datetime import date
    from reporting.gst_periods import GstReturnPeriod, soft_close_period
    from sales.services import SalesService

    product = make_product(tenant_a.company, sku="RACE-GST-SC")
    add_stock(tenant_a, product, "5")
    customer = make_customer(tenant_a.company, state="Karnataka")

    # Pick a future period with no pre-existing GstReturnPeriod row
    target_date = date(2028, 5, 15)
    period_str = "2028-05"
    GstReturnPeriod.objects.filter(company=tenant_a.company, period=period_str).delete()

    inv = create_draft_invoice(
        tenant_a,
        customer,
        [{"product": product.id, "quantity": "1", "unit_price": "100"}],
        invoice_date=target_date,
    )
    from sales.models import SalesInvoice
    inv_obj = SalesInvoice.objects.get(pk=inv["id"])

    barrier = threading.Barrier(2, timeout=10)
    outcome: dict = {"soft_closed": False, "completed": False, "complete_error": None}

    def do_soft_close():
        connection.close()
        try:
            barrier.wait()
            soft_close_period(tenant_a.company, period_str, tenant_a.owner)
            outcome["soft_closed"] = True
        finally:
            connection.close()

    def do_complete():
        connection.close()
        try:
            barrier.wait()
            SalesService.complete(inv_obj, tenant_a.owner)
            outcome["completed"] = True
        except BusinessRuleError as exc:
            outcome["complete_error"] = exc
        finally:
            connection.close()

    t1 = threading.Thread(target=do_soft_close)
    t2 = threading.Thread(target=do_complete)
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)

    assert outcome["soft_closed"] is True
    # Either complete succeeded before soft_close, OR it was blocked because period was soft-closed.
    if outcome["completed"]:
        inv_obj.refresh_from_db()
        assert inv_obj.status == SalesInvoice.Status.COMPLETED
    else:
        assert outcome["complete_error"] is not None
        assert "closed" in str(outcome["complete_error"]).lower()

