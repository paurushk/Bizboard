"""Behaviour for the 2026-10-04 implementation plan that the rest of the apps call."""

from __future__ import annotations

import csv
import hashlib
import io
import math
import secrets
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.exceptions import BusinessRuleError

from .crypto import SealError, open_secret, seal
from .models import (
    AnomalyReview,
    ApprovalRequest,
    BlockedCreditRule,
    BulkImportBatch,
    CreditUnlock,
    EwayStubAction,
    IntegrityQuarantine,
    ItcBillCheck,
    LoggingWindow,
    PartySnapshot,
    PharmacyDispense,
    TallyImportJob,
)

MONEY_VISIBLE_ROLES = {"OWNER", "ACCOUNTANT", "MANAGER"}
PLAIN_TEXT_FIELDS = (
    "notes", "description", "name", "address", "billing_address", "shipping_address",
    "remarks", "reason",
)


def open_quarantine(company, failures: dict) -> IntegrityQuarantine:
    """One open row per company. The partial unique constraint makes concurrent runs converge."""
    keys = sorted(failures.keys())
    with transaction.atomic():
        row = (
            IntegrityQuarantine.objects.select_for_update()
            .filter(company=company, cleared_at__isnull=True)
            .first()
        )
        if row is None:
            try:
                with transaction.atomic():
                    return IntegrityQuarantine.objects.create(company=company, keys=keys, detail=failures)
            except IntegrityError:
                row = IntegrityQuarantine.objects.select_for_update().get(company=company, cleared_at__isnull=True)
        row.keys = keys
        row.detail = failures
        row.save(update_fields=["keys", "detail", "updated_at"])
        return row


def quarantine_is_open(company) -> bool:
    return IntegrityQuarantine.objects.filter(company=company, cleared_at__isnull=True).exists()


def assert_books_clear(company) -> None:
    if quarantine_is_open(company):
        raise BusinessRuleError(
            "Books are quarantined. Period close and GST export stay blocked until the quarantine is cleared. Billing can continue.",
        )


def clear_quarantine(company, user) -> int:
    now = timezone.now()
    return IntegrityQuarantine.objects.filter(company=company, cleared_at__isnull=True).update(
        cleared_at=now, cleared_by=user,
    )


def cost_visible(role: str) -> bool:
    return (role or "") in MONEY_VISIBLE_ROLES


def mask_commercial(data: dict, role: str) -> dict:
    """Omit purchase price and margin. Never replace them with blank or zero."""
    out = dict(data)
    if cost_visible(role):
        return out
    out.pop("purchase_price", None)
    out.pop("margin", None)
    selling = data.get("selling_price")
    cost = data.get("purchase_price")
    try:
        below = Decimal(str(selling)) < Decimal(str(cost))
    except Exception:
        below = False
    out["below_cost"] = bool(below and cost not in (None, ""))
    return out


def chronic_overdue(company, customer, *, today: date | None = None, floor: Decimal = Decimal("5000")):
    from sales.models import SalesInvoice

    today = today or timezone.localdate()
    cutoff = today - timedelta(days=60)
    from ledgers.services import LedgerService

    rows = SalesInvoice.objects.filter(
        company=company,
        customer=customer,
        status=SalesInvoice.Status.COMPLETED,
        due_date__lt=cutoff,
    )
    # Only what is still owed counts: a paid or credited invoice must not hold credit.
    total = Decimal("0")
    any_old = False
    for row in rows:
        owed = LedgerService.sales_invoice_outstanding(row)
        if owed > 0:
            any_old = True
            total += owed
    return any_old and total >= floor, total


def assert_chronic_credit_allowed(invoice, *, unlock_code: str | None = None, force: bool = False) -> None:
    """Block credit completion, not cash or prepaid (payment terms of zero days).

    Delivery challans pass force=True: a challan is a credit delivery.
    """
    if not force and int(getattr(invoice, "payment_terms_days", 0) or 0) <= 0:
        return
    blocked, total = chronic_overdue(invoice.company, invoice.customer)
    if not blocked:
        return
    if unlock_code and consume_unlock(invoice.company, invoice.customer, unlock_code):
        return
    raise BusinessRuleError(
        f"Credit is held: invoices over 60 days overdue total {total}. Cash or prepaid can still be billed.",
    )


def issue_unlock(company, customer, user, reason: str):
    if not (reason or "").strip():
        raise BusinessRuleError("An unlock needs a reason.")
    code = secrets.token_hex(4)
    return CreditUnlock.objects.create(
        company=company,
        customer=customer,
        code=code,
        reason=reason.strip(),
        expires_at=timezone.now() + timedelta(hours=24),
        created_by=user if getattr(user, "pk", None) else None,
    )


def consume_unlock(company, customer, code: str) -> bool:
    row = (
        CreditUnlock.objects.select_for_update()
        .filter(company=company, customer=customer, code=code)
        .first()
    )
    if row is None or row.used_at is not None or row.expires_at <= timezone.now():
        return False
    row.used_at = timezone.now()
    row.save(update_fields=["used_at", "updated_at"])
    return True


def stamp_document_party(document, *, backfill=False) -> PartySnapshot | None:
    party = getattr(document, "customer", None) or getattr(document, "supplier", None)
    if party is None:
        return None
    return stamp_party(document, party, backfill=backfill)


def stamp_party(document, party, *, backfill=False) -> PartySnapshot:
    payload = {
        "legal_name": getattr(party, "gstin_legal_name", "") or getattr(party, "name", ""),
        "trade_name": getattr(party, "name", ""),
        "billing_address": getattr(party, "billing_address", "") or getattr(party, "address", ""),
        "shipping_address": getattr(party, "shipping_address", ""),
        "gstin": getattr(party, "gstin", ""),
    }
    lookup = dict(company=document.company, entity_type=type(document).__name__, entity_id=str(document.pk))
    row = PartySnapshot.objects.filter(**lookup).first()
    if row is None:
        return PartySnapshot.objects.create(payload=payload, backfill_from_master=backfill, **lookup)
    # As-issued snapshots are write-once. A backfill never replaces any snapshot, and a live
    # stamp only replaces one that was itself copied from the master.
    if backfill or not row.backfill_from_master:
        return row
    row.payload = payload
    row.backfill_from_master = False
    row.save(update_fields=["payload", "backfill_from_master", "updated_at"])
    return row


SECTION_17_RULES = (
    ("9963", "food", "Food and beverages"),
    ("8703", "motor", "Motor vehicles"),
    ("", "club", "Membership of a club"),
    ("", "works_contract", "Works contract for immovable property"),
    ("", "personal", "Personal consumption"),
    ("", "exempt_supply", "Goods or services used for exempt supplies"),
)


def ensure_blocked_rules() -> None:
    if BlockedCreditRule.objects.exists():
        return
    start = date(2017, 7, 1)
    BlockedCreditRule.objects.bulk_create([
        BlockedCreditRule(
            hsn_prefix=hsn, expense_category=cat, effective_from=start, description=desc,
        )
        for hsn, cat, desc in SECTION_17_RULES
    ])


def blocked_credit_match(*, hsn: str, expense_category: str, on: date) -> BlockedCreditRule | None:
    ensure_blocked_rules()
    hsn = (hsn or "").strip()
    cat = (expense_category or "").strip().lower()
    for rule in BlockedCreditRule.objects.filter(effective_from__lte=on).order_by("-effective_from"):
        if rule.effective_to and rule.effective_to < on:
            continue
        if rule.hsn_prefix and hsn.startswith(rule.hsn_prefix):
            return rule
        if rule.expense_category and rule.expense_category == cat:
            return rule
    return None


def itc_claimable(check: ItcBillCheck) -> bool:
    proven = check.invoice_held and check.goods_received and check.paid_within_180
    attested = check.supplier_tax_attested and check.return_filed_attested
    return bool(proven and attested)


def save_itc_check(company, source_type, source_id, **flags) -> ItcBillCheck:
    row, _ = ItcBillCheck.objects.update_or_create(
        company=company, source_type=source_type, source_id=str(source_id), defaults=flags,
    )
    return row


def section_16_4_deadline(invoice_date: date, annual_return: date | None = None) -> date:
    """30 November following the financial year, or the annual return if earlier."""
    if invoice_date.month >= 4:
        fy_end_year = invoice_date.year + 1
    else:
        fy_end_year = invoice_date.year
    deadline = date(fy_end_year, 11, 30)
    if annual_return and annual_return < deadline:
        return annual_return
    return deadline


def section_16_4_status(invoice_date: date, *, claimed: bool, today: date, annual_return: date | None = None) -> str:
    deadline = section_16_4_deadline(invoice_date, annual_return)
    if today > deadline:
        return "CLAIMED_REVIEW" if claimed else "TIME_BARRED"
    days = (deadline - today).days
    if days <= 7:
        return "DUE_7"
    if days <= 60:
        return "DUE_60"
    return "OPEN"


# Section 50 rates. A date outside the table is refused. No journal is posted.
SECTION_50_RATES = (
    (date(2017, 7, 1), None, Decimal("0.18"), Decimal("0.24")),
)


def section_50_interest(*, tax: Decimal, excess_itc: Decimal, days: int, on: date) -> dict:
    if days < 0:
        raise BusinessRuleError("Interest days cannot be negative.")
    rate = None
    for start, end, late, excess in SECTION_50_RATES:
        if on < start:
            continue
        if end and on > end:
            continue
        rate = (late, excess)
    if rate is None:
        raise BusinessRuleError("No Section 50 rate covers this date.")
    late_rate, excess_rate = rate

    def _interest(amount, yearly):
        raw = (Decimal(amount) * yearly * Decimal(days)) / Decimal(365)
        return raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "late_tax_interest": _interest(tax, late_rate),
        "excess_itc_interest": _interest(excess_itc, excess_rate),
        "journal_posted": False,
    }


def eway_validity_days(distance_km: Decimal | int) -> int:
    distance = Decimal(str(distance_km))
    if distance <= 0:
        raise BusinessRuleError("Distance must be greater than zero.")
    return max(1, math.ceil(float(distance) / 100))


def record_eway_stub(*, company, document_type, document_id, action, payload, bill_status="ACTIVE", user=None):
    if bill_status in ("CANCELLED", "EXPIRED") and action == EwayStubAction.Action.PART_B:
        raise BusinessRuleError("Part B cannot be updated on a cancelled or expired bill.")
    if action == EwayStubAction.Action.EXTEND:
        distance = payload.get("distance_km")
        days = eway_validity_days(distance if distance is not None else 0)
        if int(payload.get("extend_by_days") or 0) > days:
            raise BusinessRuleError("Extension is outside the validity window.")
    if action == EwayStubAction.Action.SPLIT:
        total = Decimal(str(payload.get("consignment_qty") or 0))
        parts = payload.get("parts") or []
        used = sum(Decimal(str(p)) for p in parts)
        if used > total:
            raise BusinessRuleError("Split quantities are above the consignment.")
    if action == EwayStubAction.Action.TRANSFER_PART_B and bill_status == "COMPLETED":
        raise BusinessRuleError("Part B cannot be updated on a completed transfer.")
    row = EwayStubAction.objects.create(
        company=company,
        document_type=document_type,
        document_id=str(document_id),
        action=action,
        payload=payload,
        bill_status=bill_status,
        history=[{"at": timezone.now().isoformat(), "payload": payload}],
        created_by=user if getattr(user, "pk", None) else None,
    )
    return row


def pharmacy_required(company) -> bool:
    flags = getattr(company, "feature_flags", None) or {}
    return bool(flags.get("pharmacy_enabled"))


def assert_pharmacy_sale(*, company, product, patient_name="", prescriber_name="", prescriber_registration="",
                         prescription_note="", quantity=None, record=True, invoice_number="", batch_no=""):
    """Check a Schedule H/H1/X sale has its details. ``record=False`` only checks.

    The invoice completion path checks first and records once, after the invoice has a number,
    so a refused or retried completion never leaves unnumbered register rows behind.
    """
    if not pharmacy_required(company):
        return None
    schedule = (getattr(product, "drug_schedule", "") or "").upper()
    if schedule not in ("H", "H1", "X"):
        return None
    if not (patient_name and prescriber_name and prescriber_registration):
        raise BusinessRuleError("Schedule H, H1 and X sales need the patient and the prescriber.")
    if schedule == "X" and not (prescription_note or "").strip():
        raise BusinessRuleError("Schedule X needs a prescription copy.")
    if not record:
        return schedule
    return PharmacyDispense.objects.create(
        company=company,
        product=product,
        schedule=schedule,
        invoice_number=invoice_number,
        batch_no=batch_no,
        patient_name=patient_name,
        prescriber_name=prescriber_name,
        prescriber_registration=prescriber_registration,
        quantity=Decimal(str(quantity or "1")),
        prescription_note=prescription_note,
    )


def submit_approval(*, company, action, requester, payload, hours=72) -> ApprovalRequest:
    return ApprovalRequest.objects.create(
        company=company,
        action=action,
        requester=requester,
        payload=payload or {},
        expires_at=timezone.now() + timedelta(hours=hours),
    )


def decide_approval(row: ApprovalRequest, *, approver, accept: bool, owner_exception=False) -> ApprovalRequest:
    with transaction.atomic():
        locked = ApprovalRequest.objects.select_for_update().get(pk=row.pk)
        expired = _decide_locked(locked, approver=approver, accept=accept, owner_exception=owner_exception)
    # Callers keep using the object they passed in: bring it up to date with what was saved.
    row.refresh_from_db()
    if expired:
        # Raised after the transaction so the EXPIRED status it recorded is kept.
        raise BusinessRuleError("The request expired and counts as rejected.")
    return row


def _decide_locked(row: ApprovalRequest, *, approver, accept: bool, owner_exception=False) -> bool:
    """Apply a decision to a locked row. Returns True when the request had already expired."""
    if row.expires_at <= timezone.now() and row.status == ApprovalRequest.Status.PENDING:
        row.status = ApprovalRequest.Status.EXPIRED
        row.decided_at = timezone.now()
        row.save(update_fields=["status", "decided_at", "updated_at"])
        return True
    if row.status != ApprovalRequest.Status.PENDING:
        raise BusinessRuleError("This request is already decided.")
    if approver is not None and row.requester_id == getattr(approver, "pk", None) and not owner_exception:
        raise BusinessRuleError("The requester cannot approve their own request.")
    row.status = ApprovalRequest.Status.APPROVED if accept else ApprovalRequest.Status.REJECTED
    row.approver = approver
    row.decided_at = timezone.now()
    row.save(update_fields=["status", "approver", "decided_at", "updated_at"])
    from core.services.audit import AuditService

    AuditService.log(
        company=row.company, user=approver, action="APPROVE" if accept else "REJECT",
        entity_type="ApprovalRequest", entity_id=str(row.pk),
        description=f"{row.action} {row.status}",
    )
    return False


def issue_credit_token(*, company, requester, invoice_batch: str) -> ApprovalRequest:
    row = submit_approval(
        company=company,
        action="credit_token",
        requester=requester,
        payload={"invoice_batch": invoice_batch},
        hours=0,
    )
    row.expires_at = timezone.now() + timedelta(minutes=15)
    row.token = secrets.token_hex(8)
    row.save(update_fields=["expires_at", "token", "updated_at"])
    return row


def redeem_credit_token(company, token: str, invoice_batch: str) -> ApprovalRequest:
    if not (token or "").strip():
        raise BusinessRuleError("The token is missing, used, or expired. The invoice stays held.")
    with transaction.atomic():
        row = (
            ApprovalRequest.objects.select_for_update()
            .filter(company=company, action="credit_token", token=token)
            .first()
        )
        if row is None or row.token_used_at is not None or row.expires_at <= timezone.now():
            raise BusinessRuleError("The token is missing, used, or expired. The invoice stays held.")
        if (row.payload or {}).get("invoice_batch") != invoice_batch:
            raise BusinessRuleError("The token is for a different invoice batch.")
        row.token_used_at = timezone.now()
        row.status = ApprovalRequest.Status.APPROVED
        row.decided_at = timezone.now()
        row.save(update_fields=["token_used_at", "status", "decided_at", "updated_at"])
        return row


def owner_is_sole_approver(company, user) -> bool:
    from accounts.models import CompanyUser

    membership = CompanyUser.objects.filter(
        company=company, user=user, is_active=True, role=CompanyUser.Role.OWNER,
    ).first()
    if membership is None:
        return False
    return not CompanyUser.objects.filter(
        company=company, is_active=True, role=CompanyUser.Role.OWNER,
    ).exclude(user_id=getattr(user, "pk", None)).exists()


def _same_value(left, right) -> bool:
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except Exception:  # noqa: BLE001 - not numeric, compare as text
        return str(left) == str(right)


def _consume_approval(company, approval_id, user, action, **subject):
    """Spend one approved request, once.

    The request must be approved by someone other than the caller, raised by the caller,
    unexpired, not already spent, and granted for this exact subject (``subject`` keys
    are matched against the stored payload). Without these checks one approval could
    cancel any invoice or post any adjustment, any number of times.
    """
    if not approval_id:
        return None
    try:
        approval_pk = int(approval_id)
    except (TypeError, ValueError):
        return None
    uid = getattr(user, "pk", None)
    with transaction.atomic():
        row = (
            ApprovalRequest.objects.select_for_update()
            .filter(pk=approval_pk, company=company, action=action, status=ApprovalRequest.Status.APPROVED)
            .first()
        )
        if row is None or row.approver_id is None or row.approver_id == uid:
            return None
        if row.token_used_at is not None or row.expires_at <= timezone.now():
            return None
        if row.requester_id is not None and row.requester_id != uid:
            return None
        payload = row.payload or {}
        for key, value in subject.items():
            if key not in payload or not _same_value(payload[key], value):
                return None
        row.token_used_at = timezone.now()
        row.save(update_fields=["token_used_at", "updated_at"])
    return row


def consume_action_approval(company, approval_id, user, action, **subject):
    return _consume_approval(company, approval_id, user, action, **subject)


def consume_stock_approval(company, approval_id, user, **subject):
    return _consume_approval(company, approval_id, user, "stock_adjustment", **subject)


def stock_adjustment_needs_second(company, *, value: Decimal, quantity: Decimal, on_hand: Decimal) -> bool:
    flags = getattr(company, "feature_flags", None) or {}
    value_floor = Decimal(str(flags.get("stock_adjust_value") or "10000"))
    qty_pct = Decimal(str(flags.get("stock_adjust_qty_pct") or "10"))
    if value >= value_floor:
        return True
    if on_hand <= 0:
        # No stock to measure against (or an unknown cost): a second person must approve.
        return quantity != 0
    return (abs(quantity) / on_hand) * Decimal(100) >= qty_pct


def provision_buckets(company) -> list[tuple[int, int | None, Decimal]]:
    flags = getattr(company, "feature_flags", None) or {}
    custom = flags.get("bad_debt_buckets")
    if custom:
        return [(int(b["from"]), b.get("to"), Decimal(str(b["rate"]))) for b in custom]
    return [
        (0, 60, Decimal("0")),
        (61, 90, Decimal("0.05")),
        (91, 180, Decimal("0.25")),
        (181, 365, Decimal("0.50")),
        (366, None, Decimal("1")),
    ]


def suggest_provision(company, *, days_overdue: int, amount: Decimal) -> Decimal:
    rate = Decimal("0")
    for start, end, bucket_rate in provision_buckets(company):
        if days_overdue < start:
            continue
        if end is not None and days_overdue > end:
            continue
        rate = bucket_rate
        break
    return (Decimal(amount) * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def interest_exposure(company, *, amount: Decimal, days: int) -> Decimal:
    flags = getattr(company, "feature_flags", None) or {}
    yearly = Decimal(str(flags.get("interest_rate") or "0.18"))
    raw = (Decimal(amount) * yearly * Decimal(days)) / Decimal(365)
    return raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def flag_anomaly(*, company, kind, subject_id, discount=None, median_discount=None, bill=None, median_bill=None, floor=Decimal("1000")):
    unusual = False
    if discount is not None and median_discount not in (None, 0, Decimal("0")):
        unusual = Decimal(str(discount)) > Decimal(str(median_discount)) * 3
    if bill is not None and median_bill not in (None, 0, Decimal("0")):
        unusual = unusual or (
            Decimal(str(bill)) >= floor and Decimal(str(bill)) > Decimal(str(median_bill)) * 3
        )
    if not unusual:
        return None
    row, _created = AnomalyReview.objects.get_or_create(
        company=company,
        kind=kind,
        subject_id=str(subject_id),
        defaults={"detail": {"discount": str(discount or ""), "bill": str(bill or "")}},
    )
    return row


def cashflow_forecast(delays: list[int], *, segment_average: float, runs: int = 1000) -> dict:
    sample = list(delays)
    low_confidence = len(sample) < 5
    if low_confidence:
        sample = [int(segment_average)]
    else:
        # Shrink toward the segment average.
        sample = [int(round((d + segment_average) / 2)) for d in sample]
    if not sample:
        sample = [int(segment_average)]
    outcomes = []
    for n in range(runs):
        outcomes.append(sample[n % len(sample)])
    outcomes.sort()
    def pct(p):
        idx = min(len(outcomes) - 1, max(0, int(round(p * (len(outcomes) - 1)))))
        return outcomes[idx]
    return {"p10": pct(0.10), "p50": pct(0.50), "p90": pct(0.90), "low_confidence": low_confidence}


def gstr2b_score(*, books_gstin: str, return_gstin: str, books_tax: Decimal, return_tax: Decimal, tolerance=Decimal("1")) -> str:
    gstin_match = (books_gstin or "").strip().upper() == (return_gstin or "").strip().upper() and bool(books_gstin)
    tax_close = abs(Decimal(books_tax) - Decimal(return_tax)) <= tolerance
    if gstin_match and tax_close:
        return "AUTO"
    if gstin_match or tax_close:
        return "SUGGEST"
    return "NONE"


AUDIT_COVERAGE = {
    "sales_invoice.complete": "sales_invoice.completed",
    "sales_invoice.cancel": "sales_invoice.cancelled",
    "sales_invoice.amend": "sales_invoice.amended",
    "sales_return": "sales_return.completed",
    "sales_credit_note": "sales_credit_note.completed",
    "sales_debit_note": "sales_debit_note.completed",
    "purchase_invoice.complete": "purchase_invoice.completed",
    "purchase_return": "purchase_return.completed",
    "customer_receipt": "customer_receipt.created",
    "supplier_payment": "supplier_payment.created",
    "journal.post": "journal.posted",
    "journal.reverse": "journal.reversed",
    "stock_adjustment": "stock.adjusted",
    "stock_transfer": "stock_transfer.completed",
    "goods_receipt": "goods_receipt.completed",
    "payroll.finalise": "payroll.finalised",
    "period.lock": "period.locked",
    "period.reopen": "period.reopened",
}


def certification_export(company, *, year_start: date, year_end: date, chain_ok: bool) -> dict:
    if not chain_ok:
        raise BusinessRuleError("The audit chain has a gap. This year cannot be certified.")
    dark = LoggingWindow.objects.filter(
        company=company, logging_enabled=False, starts_on__lte=year_end,
    ).exclude(ends_on__lt=year_start)
    if dark.exists():
        raise BusinessRuleError("Logging was off during this financial year.")
    return {
        "company_id": company.pk,
        "year_start": year_start.isoformat(),
        "year_end": year_end.isoformat(),
        "coverage": AUDIT_COVERAGE,
        "logging_on": True,
        "certified": True,
    }


def parse_bulk_invoices(company, text: str) -> dict:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    existing = BulkImportBatch.objects.filter(company=company, file_hash=digest).first()
    if existing and existing.status == "COMMITTED":
        return {"idempotent": True, "report": existing.report}
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if len(rows) > 2000:
        raise BusinessRuleError("The file is above the 2,000 row cap.")
    good, bad = [], []
    required = {"invoice_ref", "customer", "sku", "quantity", "rate"}
    for idx, row in enumerate(rows, start=2):
        missing = [k for k in required if not (row.get(k) or "").strip()]
        if missing:
            bad.append({"row": idx, "error": "missing " + ",".join(missing), "invoice_ref": row.get("invoice_ref")})
        else:
            good.append(row)
    report = {"accepted": len(good), "rejected": bad}
    BulkImportBatch.objects.update_or_create(
        company=company, file_hash=digest, defaults={"status": "DRY_RUN", "report": report},
    )
    return {"idempotent": False, "report": report, "file_hash": digest}


def map_tally_import(company, *, financial_year: str, ledgers: dict, stock_items: dict, vouchers: list) -> TallyImportJob:
    if not ledgers or not stock_items:
        raise BusinessRuleError("Ledger and stock-item mapping is required before vouchers are stored.")
    return TallyImportJob.objects.create(
        company=company,
        financial_year=financial_year,
        ledger_map=ledgers,
        stock_map=stock_items,
        voucher_count=len(vouchers),
        status="MAPPED",
    )


def section_138_dates(*, memo: date, demand: date) -> dict:
    if demand < memo or demand > memo + timedelta(days=30):
        raise BusinessRuleError("The written demand must fall within 30 days of the bank memo.")
    pay_by = demand + timedelta(days=15)
    return {"memo": memo.isoformat(), "demand": demand.isoformat(), "pay_by": pay_by.isoformat(),
            "disclaimer": "An advocate must review this draft before it is sent."}


def alert_purchase_team(company, subject: str, body: str) -> None:
    from django.db.models import Q

    from accounts.models import CompanyUser
    from core.models import Notification
    from core.services.notifications import NotificationService

    members = CompanyUser.objects.filter(company=company, is_active=True).filter(
        Q(role__in=[CompanyUser.Role.OWNER, CompanyUser.Role.ACCOUNTANT]) | Q(can_create_purchases=True)
    ).select_related("user")
    for membership in members:
        NotificationService.send(
            company=company,
            channel=Notification.Channel.IN_APP,
            recipient=membership.user.email or str(membership.user_id),
            subject=subject,
            body=body,
            user=membership.user,
        )


def assert_gstin_override(company, user, reason: str) -> None:
    from accounts.models import CompanyUser

    if not (reason or "").strip():
        raise BusinessRuleError("An override needs a reason.")
    membership = CompanyUser.objects.filter(company=company, user=user, is_active=True).first()
    if membership is None or membership.role not in (CompanyUser.Role.OWNER, CompanyUser.Role.ACCOUNTANT):
        raise BusinessRuleError("Only an Owner or Accountant can release a cancelled-GSTIN hold.")
    from core.services.audit import AuditService

    AuditService.log(
        company=company, user=user, action="UPDATE", entity_type="Supplier",
        description="Cancelled-GSTIN hold released.", metadata={"reason": reason.strip()},
    )


def supplier_itc_blocked(invoice_date: date, cancelled_on: date | None) -> bool:
    if cancelled_on is None:
        return False
    return invoice_date >= cancelled_on


def reseal_fernet_blob(ciphertext: str) -> str:
    """Read a Fernet blob and return AES-GCM. Empty stays empty."""
    from core.services.gsp_secrets import decrypt_gsp_credentials

    if not (ciphertext or "").strip() or str(ciphertext).startswith("gcm1."):
        return ciphertext or ""
    payload = decrypt_gsp_credentials(ciphertext)
    if not payload:
        raise SealError("Fernet blob could not be read.")
    import json
    return seal(json.dumps(payload, sort_keys=True))


def open_credential_blob(ciphertext: str) -> dict:
    import json

    if not (ciphertext or "").strip():
        return {}
    if str(ciphertext).startswith("gcm1."):
        return json.loads(open_secret(ciphertext))
    from core.services.gsp_secrets import decrypt_gsp_credentials
    return decrypt_gsp_credentials(ciphertext)
