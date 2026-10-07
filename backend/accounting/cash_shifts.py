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


def _sole_open_shift(company, shift) -> bool:
    """True when this row is the only open till, so unstamped till cash belongs here."""
    if shift is None or shift.status != CashShiftRegister.Status.OPEN:
        return False
    open_ids = list(
        CashShiftRegister.objects.filter(
            company=company, status=CashShiftRegister.Status.OPEN,
        ).values_list("pk", flat=True)
    )
    return open_ids == [shift.pk]


def _shift_cash_receipts(company, cashier, business_date, shift):
    from payments.models import CustomerReceipt, PaymentMode, ReceiptStatus

    base = CustomerReceipt.objects.filter(company=company, mode=PaymentMode.CASH).exclude(
        status__in=(ReceiptStatus.VOIDED, ReceiptStatus.REFUNDED),
    )
    if shift is None:
        return base.filter(created_by=cashier, receipt_date=business_date)
    stamped = base.filter(shift=shift)
    legacy = str(getattr(shift, "terminal_id", "") or "").startswith("legacy-")
    if legacy:
        unstamped = base.filter(shift__isnull=True, created_by=cashier, receipt_date=business_date)
    elif _sole_open_shift(company, shift):
        unstamped = base.filter(shift__isnull=True, paid_from_till=True, receipt_date=business_date)
    else:
        unstamped = base.none()
    return stamped | unstamped


def _shift_cash_payments(company, cashier, business_date, shift):
    from payments.models import PaymentMode, SupplierPayment, SupplierPaymentStatus

    base = SupplierPayment.objects.filter(company=company, mode=PaymentMode.CASH).exclude(
        status=SupplierPaymentStatus.VOIDED,
    )
    if shift is None:
        return base.filter(created_by=cashier, payment_date=business_date)
    stamped = base.filter(shift=shift)
    legacy = str(getattr(shift, "terminal_id", "") or "").startswith("legacy-")
    if legacy:
        unstamped = base.filter(shift__isnull=True, created_by=cashier, payment_date=business_date)
    elif _sole_open_shift(company, shift):
        unstamped = base.filter(shift__isnull=True, paid_from_till=True, payment_date=business_date)
    else:
        unstamped = base.none()
    return stamped | unstamped


def _shift_cash_refunds(company, cashier, business_date, shift):
    from sales.models import PosCounterRefund

    base = PosCounterRefund.objects.filter(
        company=company,
        mode=PosCounterRefund.Mode.CASH,
        status=PosCounterRefund.Status.POSTED,
    )
    if shift is None:
        return base.filter(cashier=cashier, refund_date=business_date)
    stamped = base.filter(shift=shift)
    # A refund with no shift belongs to a till only when that till is the legacy
    # row or the only open one. Otherwise a second shift the same day would count it too.
    legacy = str(getattr(shift, "terminal_id", "") or "").startswith("legacy-")
    if legacy:
        return stamped | base.filter(shift__isnull=True, cashier=cashier, refund_date=business_date)
    if _sole_open_shift(company, shift):
        return stamped | base.filter(shift__isnull=True, refund_date=business_date)
    return stamped


def expected_system_cash(company, cashier, business_date, opening_float, cash_dropped=0, shift=None) -> Decimal:
    """Opening float plus this till's cash receipts, minus cash paid out, refunds, and drops."""
    opening = _money(opening_float)
    received = _shift_cash_receipts(company, cashier, business_date, shift).aggregate(
        total=Sum("amount"),
    )["total"] or Decimal("0")
    paid = _shift_cash_payments(company, cashier, business_date, shift).aggregate(
        total=Sum("amount"),
    )["total"] or Decimal("0")
    refunded = _shift_cash_refunds(company, cashier, business_date, shift).aggregate(
        total=Sum("amount"),
    )["total"] or Decimal("0")
    if shift is not None:
        from .models import CashDrop

        dropped_lines = CashDrop.objects.filter(shift=shift).aggregate(total=Sum("amount"))["total"]
        drops = _money(dropped_lines) if dropped_lines is not None else _money(getattr(shift, "cash_dropped", cash_dropped))
    else:
        drops = _money(cash_dropped)
    return (opening + _money(received) - _money(paid) - _money(refunded) - drops).quantize(Q2, rounding=ROUND_HALF_UP)


@transaction.atomic
def drop_cash(shift, amount, user, note: str = ""):
    """Remove cash from the open drawer. Expected cash falls by the same amount."""
    locked = CashShiftRegister.objects.select_for_update().get(pk=shift.pk, company_id=shift.company_id)
    if locked.status != CashShiftRegister.Status.OPEN or locked.locked_at is not None:
        raise BusinessRuleError("This cash register is already locked and cannot be edited.")
    dropped = _money(amount)
    if dropped <= 0:
        raise BusinessRuleError("Cash drop must be greater than zero.")
    from .models import CashDrop

    CashDrop.objects.create(
        company=locked.company,
        shift=locked,
        amount=dropped,
        note=str(note or "")[:200],
        created_by=user,
        updated_by=user,
    )
    locked.cash_dropped = (_money(locked.cash_dropped) + dropped).quantize(Q2, rounding=ROUND_HALF_UP)
    locked.updated_by = user
    locked.save(update_fields=["cash_dropped", "updated_by", "updated_at"])
    from core.services.audit import AuditService

    AuditService.log(
        company=locked.company,
        user=user,
        action="UPDATE",
        entity_type="CashShiftRegister",
        entity_id=str(locked.pk),
        description=f"Cash drop {dropped}",
        metadata={"amount": str(dropped), "business_date": str(locked.business_date)},
    )
    return locked


@transaction.atomic
def close_cash_shift(shift, denominations, user):
    """Count the drawer, store the variance, and lock the register for the day."""
    locked = CashShiftRegister.objects.select_for_update().get(pk=shift.pk, company_id=shift.company_id)
    if locked.status != CashShiftRegister.Status.OPEN or locked.locked_at is not None:
        raise BusinessRuleError("This cash register is already locked and cannot be edited.")
    counted = count_denominations(denominations)
    expected = expected_system_cash(
        locked.company, locked.cashier, locked.business_date, locked.opening_float,
        cash_dropped=locked.cash_dropped, shift=locked,
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
    locked.closed_at = locked.locked_at
    locked.updated_by = user
    locked.save(update_fields=[
        "denominations", "counted_cash", "expected_cash", "variance",
        "status", "locked_at", "closed_at", "updated_by", "updated_at",
    ])
    return locked
