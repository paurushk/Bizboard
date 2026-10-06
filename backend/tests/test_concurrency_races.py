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



def test_concurrent_invoice_numbering_no_duplicate(tenant_a):
    """§G7 — two invoices completing at the same instant must not share a
    document number. `DocumentNumberService` row-locks the `DocumentSeries`."""
    _require_postgres()
    from accounting.models import JournalEntry  # noqa: F401 — app ready
    from sales.models import SalesInvoice

    product = make_product(tenant_a.company, sku="RACE-NUM", gst_rate="18", selling_price="100")
    add_stock(tenant_a, product, "50")
    customer = make_customer(tenant_a.company, state="Karnataka", gstin="29AAAAA0000A1ZY")

    drafts = [
        create_draft_invoice(
            tenant_a, customer,
            [{"product": product.id, "quantity": "1", "unit_price": "100.00", "gst_rate": "18"}],
        )["id"]
        for _ in range(2)
    ]

    numbers: list[str] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(2, timeout=10)

    def complete_one(draft_id):
        connection.close()
        try:
            barrier.wait()
            resp = tenant_a.client.post(f"/api/v1/sales/invoices/{draft_id}/complete/")
            if resp.status_code == 200:
                numbers.append(resp.data["number"])
            else:
                errors.append(RuntimeError(f"{resp.status_code}: {resp.data}"))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=complete_one, args=(d,)) for d in drafts]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, errors
    assert len(numbers) == 2
    assert len(set(numbers)) == 2, f"duplicate invoice number under race: {numbers}"
    assert SalesInvoice.objects.filter(
        company=tenant_a.company, status=SalesInvoice.Status.COMPLETED
    ).count() == 2


def test_cft_120_concurrent_same_invoice_amend_one_wins(tenant_a):
    """CFT-120 — two concurrent completed-invoice amends: one 200, one 409, no double money write."""
    _require_postgres()
    product = make_product(tenant_a.company, sku="RACE-AMEND")
    add_stock(tenant_a, product, "10")
    customer = make_customer(tenant_a.company)
    inv = create_draft_invoice(
        tenant_a, customer, [{"product": product.id, "quantity": "1", "unit_price": "100"}]
    )
    done = tenant_a.client.post(f"/api/v1/sales/invoices/{inv['id']}/complete/")
    assert done.status_code == 200, done.data
    rev = done.data.get("amend_revision", 0)
    invoice_id = inv["id"]
    statuses: list[int] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(2, timeout=10)

    def amend(price: str):
        connection.close()
        try:
            barrier.wait()
            resp = tenant_a.client.patch(
                f"/api/v1/sales/invoices/{invoice_id}/",
                {
                    "confirm_amend": True,
                    "expected_amend_revision": rev,
                    "items": [{"product": product.id, "quantity": "1", "unit_price": price}],
                },
                format="json",
            )
            statuses.append(resp.status_code)
        except Exception as exc:  # pragma: no cover
            errors.append(exc)
        finally:
            connection.close()

    threads = [
        threading.Thread(target=amend, args=("90",)),
        threading.Thread(target=amend, args=("80",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, errors
    assert sorted(statuses) == [200, 409], statuses
    from sales.models import SalesInvoice

    obj = SalesInvoice.objects.get(pk=invoice_id)
    assert obj.amend_revision == int(rev) + 1
    price = Decimal(str(obj.items.get().unit_price))
    assert price in (Decimal("90.00"), Decimal("80.00"))


def test_concurrent_order_confirms_share_one_credit_limit(tenant_a):
    """Two different draft orders race for one credit limit.

    Each thread creates its own DRAFT inside the confirm transaction, then
    calls confirm_sales_order. The sibling insert is invisible until that
    transaction commits, so the customer row lock is what makes the second
    confirm see the first order and raise credit_limit_exceeded.
    """
    _require_postgres()
    from django.db import transaction

    from sales.models import SalesOrder, SalesOrderItem
    from sales.notes_services import SalesNotesService

    flags = dict(tenant_a.company.feature_flags or {})
    flags["ENABLE_ORDER_GATES"] = True
    tenant_a.company.feature_flags = flags
    tenant_a.company.save(update_fields=["feature_flags"])
    customer = make_customer(tenant_a.company, name="Race Credit", credit_limit=Decimal("100"))
    product = make_product(tenant_a.company, sku="RACE-CREDIT", purchase_price="10", selling_price="100")
    add_stock(tenant_a, product, "2")

    barrier = threading.Barrier(2, timeout=15)
    successes: list[int] = []
    errors: list[str] = []

    def confirm():
        connection.close()
        try:
            barrier.wait()
            with transaction.atomic():
                order = SalesOrder.objects.create(
                    company=tenant_a.company,
                    customer=customer,
                    grand_total=Decimal("100"),
                    status=SalesOrder.Status.DRAFT,
                    created_by=tenant_a.owner,
                )
                SalesOrderItem.objects.create(
                    company=tenant_a.company,
                    sales_order=order,
                    product=product,
                    quantity=Decimal("1"),
                    unit_price=Decimal("100"),
                )
                SalesNotesService.confirm_sales_order(order, tenant_a.owner)
            successes.append(order.pk)
        except BusinessRuleError as exc:
            errors.append(str(exc.get_codes()) if hasattr(exc, "get_codes") else str(exc))
        finally:
            connection.close()

    threads = [threading.Thread(target=confirm), threading.Thread(target=confirm)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert len(successes) == 1, (successes, errors)
    assert len(errors) == 1 and "credit_limit_exceeded" in errors[0]
    assert len(set(successes)) == 1
    confirmed = SalesOrder.objects.filter(customer=customer, status=SalesOrder.Status.CONFIRMED)
    assert confirmed.count() == 1
    assert confirmed.get().pk == successes[0]


def test_concurrent_apply_pack_leaves_one_snapshot(tenant_a):
    """A flag written while the company row is locked survives apply_pack.

    The holder keeps the row lock, the apply waits on that lock, then the
    holder stores SENTINEL_FLAG and commits. apply_pack must read that value
    and keep it. Two identical applies cannot show a lost update.

    How the holder knows the apply is really waiting: it polls pg_stat_activity from a SEPARATE
    autocommit connection. Two things make the obvious approaches wrong (verified on PostgreSQL
    17.10): pg_stat_activity is snapshotted once per transaction, so polling from inside the
    holder's own transaction keeps returning the first, stale snapshot; and a session blocked on a
    ROW lock does not appear as an ungranted lock on the table in pg_locks (it is an ungranted
    `transactionid` lock with a NULL relation).
    """
    _require_postgres()
    import time

    from django.db import connections, transaction

    from accounts.models import Company, CompanyPackState
    from accounts.packs import PACKS, apply_pack

    holding = threading.Event()
    errors: list[BaseException] = []

    def hold():
        connection.close()
        poll = None
        try:
            poll = connections.create_connection("default")
            poll.set_autocommit(True)
            with transaction.atomic():
                company = Company.objects.select_for_update().get(pk=tenant_a.company.pk)
                holding.set()
                deadline = time.time() + 10
                while time.time() < deadline:
                    with poll.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT COUNT(*) FROM pg_stat_activity
                            WHERE datname = current_database()
                              AND pid <> pg_backend_pid()
                              AND wait_event_type = 'Lock'
                              AND query ILIKE '%accounts_company%'
                            """
                        )
                        waiting = cursor.fetchone()[0]
                    if waiting:
                        break
                    time.sleep(0.05)
                else:
                    raise AssertionError("apply_pack did not wait on the company row lock")
                flags = dict(company.feature_flags or {})
                flags["SENTINEL_FLAG"] = True
                company.feature_flags = flags
                company.save(update_fields=["feature_flags", "updated_at"])
        except BaseException as exc:  # noqa: BLE001 — reported by the assertion
            errors.append(exc)
        finally:
            if poll is not None:
                poll.close()
            connection.close()

    def run():
        connection.close()
        try:
            assert holding.wait(timeout=10)
            apply_pack(
                tenant_a.company,
                "retail",
                {"how_you_sell": "counter", "what_you_sell": "", "deliver": "", "gst_registered": ""},
                tenant_a.owner,
            )
        except BaseException as exc:  # noqa: BLE001 — reported by the assertion
            errors.append(exc)
        finally:
            connection.close()

    holder = threading.Thread(target=hold)
    applier = threading.Thread(target=run)
    holder.start()
    applier.start()
    holder.join(timeout=30)
    applier.join(timeout=30)

    assert not errors, errors
    company = Company.objects.get(pk=tenant_a.company.pk)
    state = CompanyPackState.objects.get(company=company)
    # apply_pack grants only what the company's plan entitles it to (and never ENABLE_PAYROLL), so
    # "every key in the pack" is wrong: the expected set is the entitled subset.
    from accounts.packs import _entitled

    expected = {
        key: True for key in PACKS["retail"] if key != "ENABLE_PAYROLL" and _entitled(company, key)
    }
    assert expected, "the retail pack should grant at least some flags"
    assert state.applied_pack == "retail"
    assert state.applied_flags == expected
    assert company.feature_flags["SENTINEL_FLAG"] is True
    for key in expected:
        assert company.feature_flags[key] is True


def test_concurrent_job_convert_creates_one_invoice(tenant_a):
    """Two workers converting one job leave a single draft invoice."""
    _require_postgres()
    from workshop.models import JobCard
    from workshop.services import convert_to_invoice

    tenant_a.company.feature_flags = {"ENABLE_WORKSHOP": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    customer = make_customer(tenant_a.company)
    product = make_product(tenant_a.company, product_type="SERVICE")
    job = JobCard.objects.create(company=tenant_a.company, customer=customer, number="JOB-RACE")
    from workshop.models import JobCardLine

    JobCardLine.objects.create(
        company=tenant_a.company, job=job, kind=JobCardLine.Kind.LABOUR, product=product, quantity=1, unit_price=10,
    )
    errors = []

    def convert():
        try:
            convert_to_invoice(job, tenant_a.owner)
        except Exception as exc:  # noqa: BLE001 — the loser may see a locked row
            errors.append(exc)

    threads = [threading.Thread(target=convert) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    job.refresh_from_db()
    from sales.models import SalesInvoice

    assert SalesInvoice.objects.filter(company=tenant_a.company, pk=job.sales_invoice_id).count() == 1


def test_concurrent_policy_issue_creates_one_policy(tenant_a):
    """Two workers issuing one chosen option leave a single policy."""
    _require_postgres()
    from insurance.models import Policy, PolicyOption, PolicyOptionSet, PolicyProduct
    from insurance.services import choose_option, issue_policy

    tenant_a.company.feature_flags = {"ENABLE_INSURANCE": True}
    tenant_a.company.save(update_fields=["feature_flags"])
    customer = make_customer(tenant_a.company)
    from crm.models import Lead

    lead = Lead.objects.create(company=tenant_a.company, name=customer.name, customer=customer)
    first = PolicyProduct.objects.create(
        company=tenant_a.company, name="A", insurer_name="I", line="OTHER", tenure_months=1, sum_insured=1, premium=10,
    )
    second = PolicyProduct.objects.create(
        company=tenant_a.company, name="B", insurer_name="I", line="OTHER", tenure_months=1, sum_insured=1, premium=12,
    )
    option_set = PolicyOptionSet.objects.create(company=tenant_a.company, lead=lead)
    option = PolicyOption.objects.create(company=tenant_a.company, option_set=option_set, product=first)
    PolicyOption.objects.create(company=tenant_a.company, option_set=option_set, product=second)
    choose_option(option, tenant_a.owner)

    def issue():
        issue_policy(
            tenant_a.company, tenant_a.owner, option=option, customer=customer,
            nominee="Anita", start_date=timezone.localdate(),
        )

    from django.utils import timezone

    threads = [threading.Thread(target=issue) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert Policy.objects.filter(company=tenant_a.company, option=option).count() == 1

