"""BB-000511: refunded receipts must not inflate credit-limit headroom."""

from decimal import Decimal

import pytest

from ledgers.services import LedgerService
from payments.models import CustomerReceipt, ReceiptStatus
from tests.conftest import make_customer

pytestmark = pytest.mark.django_db


def test_refunded_receipt_excluded_from_credit_limit_exposure(tenant_a):
    customer = make_customer(tenant_a.company, credit_limit=Decimal("100.00"))
    receipt = CustomerReceipt.objects.create(
        company=tenant_a.company,
        customer=customer,
        amount=Decimal("500.00"),
        mode="CASH",
        number="RCT-REFUND-REG",
        status=ReceiptStatus.POSTED,
        created_by=tenant_a.owner,
        updated_by=tenant_a.owner,
    )
    assert LedgerService.customer_unallocated_receipts(tenant_a.company, customer) == Decimal("500.00")
    exposure = LedgerService.customer_exposure_for_credit_limit(tenant_a.company, customer)
    assert exposure <= 0

    receipt.status = ReceiptStatus.REFUNDED
    receipt.save(update_fields=["status", "updated_at"])

    assert LedgerService.customer_unallocated_receipts(tenant_a.company, customer) == Decimal("0")
    exposure_after = LedgerService.customer_exposure_for_credit_limit(tenant_a.company, customer)
    assert exposure_after == Decimal("0")
