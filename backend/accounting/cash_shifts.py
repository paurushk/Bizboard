"""Daily cashier till: opening float, note count, expected cash, and day lock."""

from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.exceptions import BusinessRuleError

from .models import CashShiftRegister

Q2 = Decimal("0.01")
# Indian notes and coins a till actually counts. Unknown keys are refused.
DENOMINATIONS = (500, 200, 100, 50, 20, 10, 5, 2, 1)


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def count_denominations(denominations) -> Decimal:
    """Physical cash from a note/coin breakdown. Quantized 0.01 half-up."""
    if denominations is None:
        denominations = {}
    if not isinstance(denominations, dict):
        raise BusinessRuleError("denominations must be a map of note value to count.")
    total = Decimal("0")
    allowed = {str(note) for note in DENOMINATIONS}
    for raw_note, raw_count in denominations.items():
        note = str(raw_note).strip()
        if note not in allowed:
            raise BusinessRuleError(
                f"Unknown denomination {note}. Count {', '.join(str(n) for n in DENOMINATIONS)}."
            )
        try:
            count = int(raw_count)
        except (TypeError, ValueError) as exc:
            raise BusinessRuleError(f"Count for ₹{note} must be a whole number.") from exc
        if count < 0:
            raise BusinessRuleError(f"Count for ₹{note} cannot be negative.")
        total += Decimal(note) * Decimal(count)
    return total.quantize(Q2, rounding=ROUND_HALF_UP)


def expected_system_cash(company, cashier, business_date, opening_float) -> Decimal:
    """Opening float plus this cashier's cash receipts, minus their cash payments."""
    from payments.models import (
        CustomerReceipt,
        PaymentMode,
        ReceiptStatus,
        SupplierPayment,
        SupplierPaymentStatus,
    )

    opening = _money(opening_float)
    received = CustomerReceipt.objects.filter(
        company=company,
        created_by=cashier,
        mode=PaymentMode.CASH,
        receipt_date=business_date,
    ).exclude(
        status__in=(ReceiptStatus.VOIDED, ReceiptStatus.REFUNDED),
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    paid = SupplierPayment.objects.filter(
        company=company,
        created_by=cashier,
        mode=PaymentMode.CASH,
        payment_date=business_date,
    ).exclude(
        status=SupplierPaymentStatus.VOIDED,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return (opening + _money(received) - _money(paid)).quantize(Q2, rounding=ROUND_HALF_UP)


@transaction.atomic
def close_cash_shift(shift, denominations, user):
    """Count the drawer, store the variance, and lock the register for the day."""
    locked = CashShiftRegister.objects.select_for_update().get(pk=shift.pk, company_id=shift.company_id)
    if locked.status != CashShiftRegister.Status.OPEN or locked.locked_at is not None:
        raise BusinessRuleError("This cash register is already locked and cannot be edited.")
    counted = count_denominations(denominations)
    expected = expected_system_cash(
        locked.company, locked.cashier, locked.business_date, locked.opening_float,
    )
    variance = (counted - expected).quantize(Q2, rounding=ROUND_HALF_UP)
    normalized = {}
    for raw_note, raw_count in (denominations or {}).items():
        normalized[str(raw_note).strip()] = int(raw_count)
    locked.denominations = normalized
    locked.counted_cash = counted
    locked.expected_cash = expected
    locked.variance = variance
    locked.status = CashShiftRegister.Status.CLOSED
    locked.locked_at = timezone.now()
    locked.updated_by = user
    locked.save(update_fields=[
        "denominations", "counted_cash", "expected_cash", "variance",
        "status", "locked_at", "updated_by", "updated_at",
    ])
    return locked
