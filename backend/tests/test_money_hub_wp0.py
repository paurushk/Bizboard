"""Money Hub WP-0: the two defects the hub would otherwise expose to the owner.

P-1  cash_totals / dashboard cash counted cheques that had not cleared; cash_book did not.
P-2  no document-basis total for supplier payments not yet applied to a bill.
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from ledgers.services import LedgerService
from payments.models import ChequeStatus
from payments.services import PaymentService
from reporting.services import ReportService
from tests.conftest import make_customer, make_supplier


def _cheque_receipt(tenant, customer, amount):
    return PaymentService.create_receipt(
        company=tenant.company, customer=customer, amount=Decimal(amount), mode="CHEQUE", cheque_number="000123", cheque_bank_name="HDFC",
        reference="CHQ-1",
    )


def test_p1_pending_cheque_receipt_is_not_cash(tenant_a):
    customer = make_customer(tenant_a.company)
    PaymentService.create_receipt(
        company=tenant_a.company, customer=customer, amount=Decimal("1000"), mode="CASH",
    )
    _cheque_receipt(tenant_a, customer, "400")
    position = ReportService.cash_position(tenant_a.company)
    assert position["closing"] == Decimal("1000")
    assert position["inflow_mtd"] == Decimal("1000")


def test_p1_cleared_cheque_becomes_cash(tenant_a):
    customer = make_customer(tenant_a.company)
    receipt = _cheque_receipt(tenant_a, customer, "400")
    PaymentService.set_cheque_status(receipt=receipt, cheque_status=ChequeStatus.CLEARED)
    assert ReportService.cash_position(tenant_a.company)["closing"] == Decimal("400")


def test_p1_bounced_cheque_is_not_cash(tenant_a):
    customer = make_customer(tenant_a.company)
    receipt = _cheque_receipt(tenant_a, customer, "400")
    PaymentService.set_cheque_status(receipt=receipt, cheque_status=ChequeStatus.BOUNCED)
    assert ReportService.cash_position(tenant_a.company)["closing"] == Decimal("0")


def test_p1_pending_supplier_cheque_has_not_left_the_bank(tenant_a):
    supplier = make_supplier(tenant_a.company)
    customer = make_customer(tenant_a.company)
    PaymentService.create_receipt(
        company=tenant_a.company, customer=customer, amount=Decimal("1000"), mode="CASH",
    )
    PaymentService.create_supplier_payment(
        company=tenant_a.company, supplier=supplier, amount=Decimal("300"), mode="CHEQUE", cheque_number="000123", cheque_bank_name="HDFC",
    )
    assert ReportService.cash_position(tenant_a.company)["closing"] == Decimal("1000")


def test_p1_dashboard_cash_equals_cash_book_closing(tenant_a):
    customer = make_customer(tenant_a.company)
    supplier = make_supplier(tenant_a.company)
    PaymentService.create_receipt(
        company=tenant_a.company, customer=customer, amount=Decimal("900"), mode="BANK",
    )
    _cheque_receipt(tenant_a, customer, "250")
    PaymentService.create_supplier_payment(
        company=tenant_a.company, supplier=supplier, amount=Decimal("100"), mode="CASH",
    )
    PaymentService.create_supplier_payment(
        company=tenant_a.company, supplier=supplier, amount=Decimal("70"), mode="CHEQUE", cheque_number="000123", cheque_bank_name="HDFC",
    )
    book = ReportService.cash_book(tenant_a.company)
    assert ReportService.cash_position(tenant_a.company)["closing"] == book["closing"] == Decimal("800")


def test_p1_opening_balance_ignores_pending_supplier_cheque(tenant_a):
    """A window that starts after the cheque was written must not carry it in the opening."""
    supplier = make_supplier(tenant_a.company)
    yesterday = timezone.localdate() - timedelta(days=1)
    PaymentService.create_supplier_payment(
        company=tenant_a.company, supplier=supplier, amount=Decimal("70"), mode="CHEQUE", cheque_number="000123", cheque_bank_name="HDFC",
        payment_date=yesterday,
    )
    totals = ReportService.cash_totals(tenant_a.company, date_from=timezone.localdate())
    assert totals["opening"] == Decimal("0")


def test_p2_supplier_advance_total_counts_unapplied_payments(tenant_a):
    supplier = make_supplier(tenant_a.company)
    PaymentService.create_supplier_payment(
        company=tenant_a.company, supplier=supplier, amount=Decimal("500"), mode="BANK",
    )
    assert LedgerService.supplier_advances_total(tenant_a.company) == Decimal("500.00")
    assert LedgerService.supplier_advances_total(tenant_a.company, supplier=supplier) == Decimal("500.00")


def test_p2_supplier_advance_is_company_scoped(tenant_a, tenant_b):
    supplier = make_supplier(tenant_a.company)
    PaymentService.create_supplier_payment(
        company=tenant_a.company, supplier=supplier, amount=Decimal("500"), mode="BANK",
    )
    assert LedgerService.supplier_advances_total(tenant_b.company) == Decimal("0")


def test_p2_voided_supplier_payment_is_not_an_advance(tenant_a):
    supplier = make_supplier(tenant_a.company)
    payment = PaymentService.create_supplier_payment(
        company=tenant_a.company, supplier=supplier, amount=Decimal("500"), mode="BANK",
    )
    PaymentService.void_supplier_payment(payment=payment, reason="entered twice")
    assert LedgerService.supplier_advances_total(tenant_a.company) == Decimal("0")


def test_p2_does_not_change_supplier_outstanding(tenant_a):
    """D-9: payables are shown beside advances, never netted."""
    supplier = make_supplier(tenant_a.company)
    PaymentService.create_supplier_payment(
        company=tenant_a.company, supplier=supplier, amount=Decimal("500"), mode="BANK",
    )
    assert LedgerService.supplier_outstanding(tenant_a.company, supplier) == Decimal("0")
