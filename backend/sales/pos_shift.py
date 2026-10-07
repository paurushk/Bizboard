"""Open-shift lookup and the cash-tender gate for the counter."""

from __future__ import annotations

from core.exceptions import BusinessRuleError


def _flags(company) -> dict:
    return dict(getattr(company, "feature_flags", None) or {})


def shift_required(company) -> bool:
    if not getattr(company, "accounting_enabled", False):
        return False
    return bool(_flags(company).get("pos_require_open_shift"))


def resolve_open_shift(company, user, terminal_id: str = ""):
    from accounting.models import CashShiftRegister

    terminal_id = str(terminal_id or "").strip()
    qs = CashShiftRegister.objects.filter(company=company, status=CashShiftRegister.Status.OPEN)
    if terminal_id:
        return qs.filter(terminal_id=terminal_id).first()
    if user is None:
        return None
    return qs.filter(cashier=user).order_by("-id").first()


def assert_cash_shift(company, user, terminal_id: str, modes) -> object | None:
    """Return the open shift when a cash tender needs one. None when the rule is off."""
    cash = any(str(mode or "").upper() == "CASH" for mode in modes)
    shift = resolve_open_shift(company, user, terminal_id)
    if cash and shift_required(company) and shift is None:
        raise BusinessRuleError(
            "Open the till before taking cash.",
            code="pos_shift_required",
        )
    return shift


def stamp_receipt(receipt, shift) -> None:
    if receipt is None or shift is None:
        return
    receipt.shift = shift
    receipt.paid_from_till = True
    receipt.save(update_fields=["shift", "paid_from_till", "updated_at"])


def mark_paid_from_till(row, company, user) -> None:
    """A payments-screen cash row the cashier took from the open drawer."""
    if row is None:
        return
    from accounting.models import CashShiftRegister

    opens = list(
        CashShiftRegister.objects.filter(
            company=company, cashier=user, status=CashShiftRegister.Status.OPEN,
        ).order_by("-id")
    )
    if not opens:
        opens = list(
            CashShiftRegister.objects.filter(
                company=company, status=CashShiftRegister.Status.OPEN,
            ).order_by("-id")
        )
    if len(opens) > 1:
        raise BusinessRuleError(
            "More than one till is open. Close the extra till before marking this as paid from the till.",
            code="pos_till_ambiguous",
        )
    if len(opens) == 1:
        stamp_receipt(row, opens[0])
        return
    row.paid_from_till = True
    row.save(update_fields=["paid_from_till", "updated_at"])
