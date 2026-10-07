"""Counter rules for POS checkout: tender accounts, credit, discounts, expired lots.

Cash posts to ledger 1100. UPI, card, bank, and cheque post only to the bank
account saved for that mode. Credit creates no receipt.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.services.audit import AuditService

BANK_MODES = ("UPI", "CARD", "BANK", "CHEQUE")


def _flags(company) -> dict:
    return dict(company.feature_flags or {})


def tender_accounts(company) -> dict:
    raw = _flags(company).get("pos_tender_accounts") or {}
    out = {}
    for key, value in raw.items():
        if value in (None, ""):
            continue
        out[str(key).upper()] = int(value)
    return out


def max_line_discount(company) -> Decimal:
    try:
        return Decimal(str(_flags(company).get("pos_max_line_discount", 100)))
    except Exception:
        return Decimal("100")


def expired_lot_policy(company) -> str:
    return str(_flags(company).get("pos_expired_lot_policy") or "REASON").upper()


def pin_configured(company) -> bool:
    from sales.models import PosApproverPin

    if PosApproverPin.objects.filter(company=company).exists():
        return True
    return bool(_flags(company).get("pos_owner_pin_hash"))


def set_owner_pin(company, pin: str, user=None) -> None:
    """Save a PIN for `user`, or for the company's owner when `user` is omitted."""
    from accounts.models import CompanyUser
    from sales.models import PosApproverPin

    pin = str(pin or "")
    if len(pin) < 4:
        raise BusinessRuleError("Owner PIN must be at least 4 characters.")
    target = user
    if target is None:
        owner = CompanyUser.objects.filter(company=company, role="OWNER").order_by("id").first()
        target = getattr(owner, "user", None)
    if target is None:
        raise BusinessRuleError("Choose the user this counter PIN belongs to.")
    PosApproverPin.objects.update_or_create(
        company=company,
        user=target,
        defaults={"pin_hash": make_password(pin), "set_at": timezone.now()},
    )
    flags = _flags(company)
    flags.pop("pos_owner_pin_hash", None)
    company.feature_flags = flags
    company.save(update_fields=["feature_flags", "updated_at"])


def clear_approver_pin(company, user) -> None:
    from sales.models import PosApproverPin

    PosApproverPin.objects.filter(company=company, user=user).delete()


def save_pos_settings(company, data: dict) -> None:
    flags = _flags(company)
    if "tender_accounts" in data and isinstance(data["tender_accounts"], dict):
        cleaned = {}
        from payments.models import BankAccount

        for mode in BANK_MODES:
            raw = data["tender_accounts"].get(mode)
            if raw in (None, ""):
                continue
            try:
                bank_id = int(raw)
            except (TypeError, ValueError) as exc:
                raise BusinessRuleError(f"{mode} account must be a bank account id.") from exc
            if not BankAccount.objects.filter(company=company, pk=bank_id).exists():
                raise BusinessRuleError(f"{mode} account is not a bank account of this company.")
            cleaned[mode] = bank_id
        flags["pos_tender_accounts"] = cleaned
    if "max_line_discount" in data and data["max_line_discount"] not in (None, ""):
        try:
            cap = Decimal(str(data["max_line_discount"]))
        except Exception as exc:
            raise BusinessRuleError("Max line discount must be a number.") from exc
        if cap < 0 or cap > 100:
            raise BusinessRuleError("Max line discount must be between 0 and 100.")
        flags["pos_max_line_discount"] = str(cap)
    if "expired_lot_policy" in data and data["expired_lot_policy"]:
        policy = str(data["expired_lot_policy"]).upper()
        if policy not in ("BLOCK", "REASON"):
            raise BusinessRuleError("Expired-lot policy must be BLOCK or REASON.")
        flags["pos_expired_lot_policy"] = policy
    for key in (
        "pos_require_open_shift",
        "pos_offline_credit",
        "pos_weighted_barcode",
    ):
        if key in data:
            flags[key] = bool(data[key])
    if "pos_max_price_discount_percent" in data:
        raw = data["pos_max_price_discount_percent"]
        if raw in (None, ""):
            flags.pop("pos_max_price_discount_percent", None)
        else:
            try:
                percent = Decimal(str(raw))
            except Exception as exc:
                raise BusinessRuleError("Price discount percent must be a number.") from exc
            if percent < 0 or percent > 100:
                raise BusinessRuleError("Price discount percent must be between 0 and 100.")
            flags["pos_max_price_discount_percent"] = str(percent)
    if "pos_return_window_days" in data and data["pos_return_window_days"] not in (None, ""):
        try:
            days = int(data["pos_return_window_days"])
        except (TypeError, ValueError) as exc:
            raise BusinessRuleError("Return window must be a whole number of days.") from exc
        if days < 0:
            raise BusinessRuleError("Return window cannot be negative.")
        flags["pos_return_window_days"] = days
    company.feature_flags = flags
    company.save(update_fields=["feature_flags", "updated_at"])
    if data.get("clear_approver_user"):
        from accounts.models import CompanyUser

        member = CompanyUser.objects.filter(company=company, user_id=data["clear_approver_user"]).first()
        if member is not None:
            clear_approver_pin(company, member.user)
    if data.get("owner_pin"):
        approver = None
        if data.get("approver_user"):
            from accounts.models import CompanyUser

            member = CompanyUser.objects.filter(company=company, user_id=data["approver_user"]).first()
            if member is None:
                raise BusinessRuleError("That user is not in this company.")
            approver = member.user
        set_owner_pin(company, data["owner_pin"], user=approver)


PIN_MAX_FAILURES = 5
PIN_LOCK_SECONDS = 15 * 60


def pin_ok(company, pin: str, user=None):
    """Return the approver user, True for a legacy company hash, or False.

    Repeated wrong guesses lock that submitting user out for 15 minutes.
    """
    from django.core.cache import cache

    from sales.models import PosApproverPin

    key = f"pos_pin_fail:{company.pk}:{getattr(user, 'pk', 0) or 0}"
    if not pin:
        return False
    rows = list(PosApproverPin.objects.filter(company=company).select_related("user"))
    hashed = _flags(company).get("pos_owner_pin_hash") or ""
    if not rows and not hashed:
        return False
    if (cache.get(key) or 0) >= PIN_MAX_FAILURES:
        raise BusinessRuleError(
            "Too many wrong owner PIN attempts. Try again in 15 minutes.",
            code="pos_pin_locked",
        )
    for row in rows:
        if check_password(str(pin), row.pin_hash):
            cache.delete(key)
            return row.user
    hashed = _flags(company).get("pos_owner_pin_hash") or ""
    if hashed and check_password(str(pin), hashed):
        cache.delete(key)
        return True
    try:
        cache.add(key, 0, PIN_LOCK_SECONDS)
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, PIN_LOCK_SECONDS)
    return False


def resolve_bank(company, mode: str):
    from payments.models import BankAccount

    mode = str(mode or "").upper()
    if mode not in BANK_MODES:
        return None
    raw = tender_accounts(company).get(mode)
    if not raw:
        raise BusinessRuleError(
            f"Choose the bank account for {mode} in POS settings before taking this tender.",
            code="pos_tender_account_missing",
        )
    bank = BankAccount.objects.filter(company=company, pk=raw).first()
    if bank is None:
        raise BusinessRuleError(
            f"The {mode} account saved in POS settings is not a bank account of this company."
        )
    active = getattr(bank, "is_active", True)
    if active is False:
        raise BusinessRuleError(f"The {mode} account saved in POS settings is inactive.")
    return bank


def settlement_marker(payment: dict | None, splits) -> str | Decimal:
    """How much of this bill the receipt in this request will clear.

    ``full`` means the receipt will equal the billed total. A number is a
    short tender. ``credit`` means no receipt.
    """
    if isinstance(splits, list) and len(splits) >= 2:
        # A short split must stay on the customer's balance. Returning "full"
        # told the credit check the bill was paid.
        try:
            total = sum(
                (Decimal(str((part or {}).get("amount") or 0)) for part in splits),
                Decimal("0"),
            )
        except Exception as exc:
            raise BusinessRuleError("Split amounts must be numbers.") from exc
        return total
    payment = payment or {}
    mode = str(payment.get("mode") or "CASH").upper()
    if mode == "CREDIT":
        return "credit"
    raw = payment.get("amount")
    if raw is None or raw == "":
        return "full"
    return Decimal(str(raw))


def apply_pos_invoice_rules(invoice, *, payment: dict | None, splits, owner_pin: str, expired_reason: str, user, offline: bool = False, credit_cached_at=None) -> str | Decimal:
    """Mutate the draft invoice before complete. Returns the settlement marker."""
    from payments.models import PaymentMode

    payment = payment or {}
    mode = str(payment.get("mode") or "CASH").upper()
    if isinstance(splits, list) and len(splits) >= 2:
        if any(str((part or {}).get("mode") or "").upper() == "CREDIT" for part in splits):
            raise BusinessRuleError("Credit cannot be part of a split payment.")
        for part in splits:
            part_mode = str((part or {}).get("mode") or "CASH").upper()
            if part_mode in BANK_MODES:
                resolve_bank(invoice.company, part_mode)
    elif mode in BANK_MODES:
        resolve_bank(invoice.company, mode)
    elif mode not in ("CASH", "CREDIT", ""):
        try:
            PaymentMode(mode)
        except ValueError as exc:
            raise BusinessRuleError(f"Unknown payment mode '{mode}'.") from exc

    marker = settlement_marker(payment, splits)
    invoice._pos_settlement = marker

    customer = invoice.customer
    if marker == "credit" or mode == "CREDIT":
        if getattr(customer, "is_pos_walk_in", False):
            raise BusinessRuleError(
                "Credit needs a named customer. The walk-in party cannot carry a balance.",
                code="pos_credit_walk_in",
            )
        days = int(getattr(customer, "credit_days", 0) or 0)
        invoice.payment_terms_days = days
        invoice.due_date = invoice.invoice_date + timedelta(days=days)
        invoice.save(update_fields=["payment_terms_days", "due_date", "updated_at"])

    gstin = (getattr(customer, "gstin", "") or "").strip()
    if gstin and (invoice.invoice_discount or Decimal("0")) != 0:
        from sales.models import SalesInvoice

        if invoice.invoice_discount_mode != SalesInvoice.DiscountMode.BEFORE_TAX:
            invoice.invoice_discount_mode = SalesInvoice.DiscountMode.BEFORE_TAX
            invoice.save(update_fields=["invoice_discount_mode", "updated_at"])

    items = list(invoice.items.select_related("product"))
    # Check the PIN once per request. Each wrong check counts toward the lockout.
    approver = pin_ok(invoice.company, owner_pin, user) if owner_pin else False
    pin_valid = bool(approver)
    invoice._pos_owner_pin_ok = pin_valid
    invoice._pos_approver = approver if approver is not True else None
    _assert_discounts(invoice, items, pin_valid=pin_valid, user=user, approver=invoice._pos_approver)
    _assert_price_floor(invoice, items, pin_valid=pin_valid, user=user, approver=invoice._pos_approver)
    _assert_expired(invoice, items, reason=expired_reason, user=user, approver=invoice._pos_approver)
    _assert_offline_credit(
        invoice, mode=mode, offline=bool(offline), credit_cached_at=credit_cached_at, splits=splits,
    )
    return marker


def _assert_discounts(invoice, items, *, pin_valid: bool, user, approver=None) -> None:
    cap = max_line_discount(invoice.company)
    discounted = []
    over = []
    for item in items:
        percent = Decimal(str(getattr(item, "discount_percent", 0) or 0))
        if percent <= 0:
            continue
        name = getattr(item.product, "name", "") or str(item.pk)
        discounted.append({"line": name, "percent": str(percent)})
        if percent > cap:
            over.append(name)
    if over and not pin_valid:
        raise BusinessRuleError(
            f"Line discount is above the {cap}% counter limit. An owner PIN is required.",
            code="pos_discount_cap",
        )
    if not discounted:
        return
    AuditService.log(
        company=invoice.company,
        user=user,
        action="UPDATE",
        entity_type="SalesInvoice",
        entity_id=str(invoice.pk),
        description=(
            f"POS discount above {cap}% allowed with owner PIN."
            if over
            else "POS line discount."
        ),
        metadata={
            "lines": discounted,
            "above_cap": over,
            "approver_id": getattr(approver, "pk", None),
            "approver_name": (
                (getattr(approver, "get_full_name", lambda: "")() or getattr(approver, "username", ""))
                if approver not in (None, True, False) else ""
            ),
            "scope": "discount",
        },
    )


def _baseline_price(customer, product, qty) -> Decimal:
    from masters.models import PriceListItem

    price_list_id = getattr(customer, "price_list_id", None)
    if price_list_id:
        slabs = list(
            PriceListItem.objects.filter(price_list_id=price_list_id, product=product).order_by("-min_qty")
        )
        quantity = Decimal(str(qty or 1))
        for slab in slabs:
            if quantity + Decimal("0") >= Decimal(str(slab.min_qty or 1)):
                if slab.max_qty is None or quantity <= Decimal(str(slab.max_qty)):
                    return Decimal(str(slab.unit_price))
    return Decimal(str(getattr(product, "selling_price", 0) or 0))


def _assert_price_floor(invoice, items, *, pin_valid: bool, user, approver=None) -> None:
    raw = _flags(invoice.company).get("pos_max_price_discount_percent")
    if raw in (None, ""):
        return
    cap = Decimal(str(raw))
    for item in items:
        baseline = _baseline_price(invoice.customer, item.product, item.quantity)
        if baseline <= 0:
            continue
        # An inclusive-price bill stores the tax-exclusive rate; compare the price the cashier typed.
        inclusive = getattr(item, "unit_price_inclusive", None)
        if getattr(invoice, "price_mode", "") == "INCLUSIVE" and inclusive:
            unit = Decimal(str(inclusive))
        else:
            unit = Decimal(str(item.unit_price or 0))
        if unit >= baseline:
            continue
        off = (baseline - unit) / baseline * Decimal("100")
        if off <= cap:
            continue
        reason = str(getattr(item, "rate_override_reason", "") or "").strip()
        if not pin_valid:
            raise BusinessRuleError(
                f"Price for '{item.product.name}' is more than {cap}% under the list price. An approver PIN is required.",
                code="pos_price_floor",
            )
        if not reason:
            raise BusinessRuleError(
                f"Price for '{item.product.name}' needs a reason.",
                code="pos_price_reason",
            )
        item.rate_override = True
        item.price_override_by = approver if getattr(approver, "pk", None) else None
        item.save(update_fields=["rate_override", "price_override_by", "updated_at"])
        AuditService.log(
            company=invoice.company,
            user=user,
            action="UPDATE",
            entity_type="SalesInvoice",
            entity_id=str(invoice.pk),
            description=f"POS price override on {item.product.name}: {reason}",
            metadata={
                "approver_id": getattr(approver, "pk", None),
                "approver_name": (
                    (getattr(approver, "get_full_name", lambda: "")() or getattr(approver, "username", ""))
                    if approver not in (None, True, False) else ""
                ),
                "scope": "price",
                "reason": reason[:200],
            },
        )


def _outage_filter(invoice) -> dict:
    outage = str(getattr(invoice, "pos_outage_id", "") or "")
    if outage:
        return {"pos_outage_id": outage}
    return {"invoice_date": invoice.invoice_date}


def _bill_total(invoice) -> Decimal:
    total = Decimal(str(invoice.grand_total or 0))
    if total > 0:
        return total
    amount = Decimal("0")
    for item in invoice.items.all():
        qty = Decimal(str(item.quantity or 0))
        price = Decimal(str(item.unit_price or 0))
        disc = Decimal(str(getattr(item, "discount_percent", 0) or 0))
        amount += qty * price * (Decimal("1") - disc / Decimal("100"))
    return amount.quantize(Decimal("0.01"))


def _assert_offline_credit(invoice, *, mode: str, offline: bool, credit_cached_at=None, splits=None) -> None:
    if not offline:
        return
    if isinstance(splits, list) and len(splits) >= 2:
        modes = [str((part or {}).get("mode") or "CASH").upper() for part in splits]
    else:
        modes = [str(mode or "CASH").upper()]
    if any(item not in ("CASH", "CREDIT", "") for item in modes):
        raise BusinessRuleError(
            "Card, UPI, bank, and cheque cannot be synced from an offline bill.",
            code="pos_offline_tender",
        )
    if "CREDIT" not in modes:
        return
    if not _flags(invoice.company).get("pos_offline_credit"):
        raise BusinessRuleError("Offline credit is turned off for this company.", code="pos_offline_credit_off")
    from datetime import timedelta
    from django.utils.dateparse import parse_datetime

    cached = parse_datetime(str(credit_cached_at or ""))
    if cached is not None and timezone.is_naive(cached):
        cached = timezone.make_aware(cached, timezone.get_current_timezone())
    now = timezone.now()
    if (
        cached is None
        or cached > now + timedelta(minutes=5)
        or now - cached > timedelta(hours=4)
    ):
        raise BusinessRuleError(
            "Offline credit needs a credit check from the last 4 hours.",
            code="pos_offline_credit_stale",
        )
    customer = invoice.customer
    if getattr(customer, "is_pos_walk_in", False):
        raise BusinessRuleError("Offline credit needs a named customer.", code="pos_credit_walk_in")
    if getattr(customer, "status", "") == "BLOCKED":
        raise BusinessRuleError("This customer is on stop-credit.", code="pos_offline_credit_hold")
    from payments.dunning import customer_risk_snapshot

    snap = customer_risk_snapshot(invoice.company, customer)
    if snap.get("collection_status") in ("stop_credit", "overdue_severe"):
        raise BusinessRuleError(
            "This customer is on stop-credit or severe overdue.",
            code="pos_offline_credit_hold",
        )
    bill = _bill_total(invoice)
    from django.db.models import Sum
    from ledgers.services import LedgerService
    from sales.models import SalesInvoice

    prior_total = SalesInvoice.objects.filter(
        company=invoice.company,
        customer=customer,
        pos_offline=True,
        status=SalesInvoice.Status.COMPLETED,
        **_outage_filter(invoice),
    ).exclude(pk=invoice.pk).aggregate(total=Sum("grand_total"))["total"] or Decimal("0")
    ceiling = Decimal("5000")
    limit = Decimal(str(getattr(customer, "credit_limit", 0) or 0))
    if limit > 0:
        outstanding = Decimal(str(LedgerService.customer_outstanding(invoice.company, customer) or 0))
        ceiling = min(ceiling, max(limit - outstanding, Decimal("0")))
    if Decimal(prior_total) + bill > ceiling:
        raise BusinessRuleError(
            "Offline credit is capped at ₹5,000 per customer for this outage, or the remaining limit if that is lower.",
            code="pos_offline_credit_cap",
        )
    terminal = str(getattr(invoice, "terminal_id", "") or "")
    prior_count = SalesInvoice.objects.filter(
        company=invoice.company,
        pos_offline=True,
        status=SalesInvoice.Status.COMPLETED,
        terminal_id=terminal,
        **_outage_filter(invoice),
    ).exclude(pk=invoice.pk).count()
    if prior_count >= 20:
        raise BusinessRuleError(
            "Offline credit already has 20 bills on this terminal for this outage.",
            code="pos_offline_credit_count",
        )


def today_period_blocked(company, doc_date) -> str:
    """Read-only. Same lock as a money post, without creating a period row."""
    from accounting.models import AccountingPeriod
    from reporting.models import GstReturnPeriod

    if doc_date is None:
        return ""
    period = f"{doc_date.year:04d}-{doc_date.month:02d}"
    gst = GstReturnPeriod.objects.filter(company=company, period=period).first()
    if gst is not None and gst.status in (
        GstReturnPeriod.Status.CLOSED,
        GstReturnPeriod.Status.SOFT_CLOSED,
    ):
        return f"GST period {period} is {gst.status}."
    blocking = AccountingPeriod.objects.filter(
        company=company,
        start_date__lte=doc_date,
        end_date__gte=doc_date,
        status__in=(AccountingPeriod.Status.CLOSED, AccountingPeriod.Status.SOFT_CLOSED),
    ).first()
    if blocking is not None:
        return f"Accounting period covering {doc_date} is {blocking.status}."
    return ""


def _assert_expired(invoice, items, *, reason: str, user, approver=None) -> None:
    from inventory.models import BatchLot

    today = timezone.localdate()
    policy = expired_lot_policy(invoice.company)
    for item in items:
        batch_no = (getattr(item, "batch_no", "") or "").strip()
        if not batch_no:
            continue
        lot = BatchLot.objects.filter(
            company=invoice.company, product_id=item.product_id, batch_no=batch_no,
        ).first()
        if lot is None or not lot.expiry_date or lot.expiry_date >= today:
            continue
        regulated = getattr(item.product, "regulated_category", "") or ""
        if regulated == "DRUG" or policy == "BLOCK":
            raise BusinessRuleError(
                f"Batch {batch_no} expired on {lot.expiry_date} and cannot be sold.",
                code="pos_expired_lot",
            )
        if not str(reason or "").strip():
            raise BusinessRuleError(
                f"Batch {batch_no} expired on {lot.expiry_date}. Enter a reason to sell it.",
                code="pos_expired_lot",
            )
        AuditService.log(
            company=invoice.company,
            user=user,
            action="UPDATE",
            entity_type="SalesInvoice",
            entity_id=str(invoice.pk),
            description=f"Expired batch {batch_no} sold: {reason.strip()[:200]}",
            metadata={
                "batch": batch_no,
                "expiry": str(lot.expiry_date),
                "scope": "expired_lot",
                "approver_id": getattr(approver, "pk", None),
                "approver_name": (
                    (getattr(approver, "get_full_name", lambda: "")() or getattr(approver, "username", ""))
                    if approver not in (None, True, False) else ""
                ),
            },
        )


def projected_exposure(exposure: Decimal, grand_total: Decimal, settlement) -> Decimal:
    """Exposure after the receipt this POS request will post. Non-POS passes None."""
    if settlement is None:
        return exposure + grand_total
    if settlement == "credit":
        settled = Decimal("0")
    elif settlement == "full":
        settled = grand_total
    else:
        settled = min(Decimal(str(settlement)), grand_total)
        if settled < 0:
            settled = Decimal("0")
    return exposure + grand_total - settled
