"""GST Guard — a real pre-submission validator for GST documents.

Extends the read-time COMP-006 buyer-GSTIN check (``reporting.gst_health``)
into a write-time validator wired into document completion (sales invoices,
POS invoices, credit notes, and recurring-generated invoices once they are
completed through the normal invoice-complete path).

``validate_document(document)`` is a pure, read-only function: it makes no
writes and does its own flag-agnostic checks. The caller (``SalesService.
complete()``, ``SalesNotesService.complete_credit_note()``, ...) is
responsible for:

  * gating the call behind ``flag_enabled(company, "ENABLE_GST_GUARD")``
  * deciding what a blocking ``GuardResult`` does (raise ``GstGuardBlocked``,
    or apply an OWNER/MANAGER override via ``apply_gst_guard_override``)
  * surfacing ``GuardResult.warning`` to the caller (non-blocking)

Works for any document with ``.company``, ``.customer``, ``.items`` (a
related manager of line items with ``hsn_code`` / ``gst_rate``), and either
an ``invoice_date`` or a ``note_date`` field — currently ``SalesInvoice`` and
``SalesCreditNote``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException

from reporting.gst_health import gstin_format_and_status, hsn_digits_insufficient_for_turnover

# "Recent invoice history" window for the GST-rate-consistency check (warning
# only — see module docstring on ``_check_rate_consistency``).
RATE_HISTORY_WINDOW_DAYS = 180

GST_GUARD_OVERRIDE_REASON_MAX = 500


@dataclass(frozen=True)
class GuardIssue:
    code: str
    message: str


@dataclass
class GuardResult:
    blocking: list[GuardIssue] = field(default_factory=list)
    warning: list[GuardIssue] = field(default_factory=list)

    @property
    def has_blocking(self) -> bool:
        return bool(self.blocking)


class GstGuardBlocked(APIException):
    """Raised when a blocking GuardIssue is found and no valid override was given."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "GST Guard blocked completion."
    default_code = "gst_guard_blocked"

    def __init__(self, result: GuardResult):
        self.result = result
        message = "; ".join(issue.message for issue in result.blocking) or self.default_detail
        detail = {
            "code": "gst_guard_blocked",
            "message": message,
            "blocking": [{"code": i.code, "message": i.message} for i in result.blocking],
            "warnings": [{"code": i.code, "message": i.message} for i in result.warning],
        }
        super().__init__(detail=detail, code="gst_guard_blocked")


def _document_fields(document):
    """Normalize the bits ``validate_document`` needs across document types."""
    company = document.company
    customer = document.customer
    items = list(document.items.all())
    doc_date = (
        getattr(document, "invoice_date", None)
        or getattr(document, "note_date", None)
        or timezone.localdate()
    )
    party_gstin = (
        (getattr(document, "filing_party_gstin", "") or "").strip()
        or (customer.gstin or "").strip()
    )
    return company, customer, items, doc_date, party_gstin


def _check_buyer_gstin(party_gstin: str, lookup_cache: dict) -> list[GuardIssue]:
    """GSTIN checksum + live-status, reusing gst_health.gstin_format_and_status."""
    gstin = (party_gstin or "").strip().upper()
    if not gstin:
        return []
    result = gstin_format_and_status(gstin, lookup_cache)
    outcome = result["outcome"]
    if outcome == "format_invalid":
        return [GuardIssue(
            "GSTIN_CHECKSUM_INVALID",
            f"Buyer GSTIN '{gstin}' checksum is invalid.",
        )]
    if outcome == "inactive":
        return [GuardIssue(
            "GSTIN_STATUS_INACTIVE",
            f"Buyer GSTIN '{gstin}' status is {result['status']}.",
        )]
    return []


def _check_hsn_master(hsn: str, on_date: date) -> tuple[str, GuardIssue] | None:
    """HSN vs the HsnRate master's effective-dated window.

    Returns ``(severity, issue)`` or ``None``:
      * no row at all for this HSN in any prefix length -> ("warning", ...)
        (an incomplete master is a data gap, not the customer's fault)
      * rows exist but none cover ``on_date`` -> ("blocking", ...)
      * a row covers ``on_date`` -> None (nothing to flag)
    """
    from masters.hsn_catalog import _hsn_prefixes
    from masters.models import HsnRate

    prefixes = _hsn_prefixes(hsn)
    if not prefixes:
        return None
    matches = list(HsnRate.objects.filter(hsn_sac__in=prefixes))
    if not matches:
        return ("warning", GuardIssue(
            "HSN_NOT_IN_MASTER",
            f"HSN '{hsn}' was not found in the GST rate master — its rate could not be cross-checked.",
        ))
    covered = any(
        row.valid_from <= on_date and (row.valid_to is None or row.valid_to >= on_date)
        for row in matches
    )
    if not covered:
        return ("blocking", GuardIssue(
            "HSN_RATE_DATE_INVALID",
            f"HSN '{hsn}' has no GST rate master entry valid on {on_date.isoformat()}.",
        ))
    return None


def _check_rate_consistency(company, hsn: str, gst_rate, on_date: date) -> GuardIssue | None:
    """Warn when this HSN is billed at a GST% the company hasn't recently used
    for that same HSN. This is a RATE check (the percentage), never a price
    check — differing unit prices, discounts, price lists, or UOM are normal
    business variation and must never trigger this.
    """
    from sales.models import SalesInvoice, SalesItem

    hsn = (hsn or "").strip()
    if not hsn:
        return None
    try:
        current = Decimal(str(gst_rate or 0))
    except InvalidOperation:
        return None
    window_start = on_date - timedelta(days=RATE_HISTORY_WINDOW_DAYS)
    raw_rates = (
        SalesItem.objects.filter(
            invoice__company=company,
            invoice__status=SalesInvoice.Status.COMPLETED,
            invoice__is_opening_balance=False,
            hsn_code=hsn,
            invoice__invoice_date__gte=window_start,
            invoice__invoice_date__lte=on_date,
        )
        .exclude(rate_override=True)
        .values_list("gst_rate", flat=True)
        .distinct()
    )
    recent_rates = {Decimal(str(r)) for r in raw_rates if r is not None}
    if recent_rates and current not in recent_rates:
        shown = ", ".join(f"{r}%" for r in sorted(recent_rates))
        return GuardIssue(
            "GST_RATE_INCONSISTENT",
            f"HSN '{hsn}' is being invoiced at {current}% but recent invoices for this "
            f"HSN used {shown}.",
        )
    return None


def validate_document(document) -> GuardResult:
    """Pure pre-submission GST validator. Makes no writes.

    ``_check_hsn_master`` and ``_check_rate_consistency`` both hit the DB;
    both are cached per unique (HSN, GST rate) seen on this document so an
    invoice with many lines sharing the same HSN (a very ordinary case —
    restocking the same handful of SKUs) issues one query per distinct
    HSN, not one per line.
    """
    company, _customer, items, doc_date, party_gstin = _document_fields(document)
    blocking: list[GuardIssue] = []
    warning: list[GuardIssue] = []

    lookup_cache: dict = {}
    blocking.extend(_check_buyer_gstin(party_gstin, lookup_cache))

    is_b2b = bool(party_gstin)
    aato = getattr(company, "aato_turnover", None)

    hsn_master_cache: dict[str, tuple[str, GuardIssue] | None] = {}
    rate_cache: dict[tuple[str, str], GuardIssue | None] = {}

    for idx, item in enumerate(items, start=1):
        hsn = (getattr(item, "hsn_code", "") or "").strip()
        if not hsn:
            if is_b2b:
                blocking.append(GuardIssue(
                    "HSN_MISSING",
                    f"Line {idx}: HSN code is required on a B2B invoice line.",
                ))
            continue
        if hsn_digits_insufficient_for_turnover(hsn, aato, is_b2b=is_b2b):
            blocking.append(GuardIssue(
                "HSN_DIGITS_INSUFFICIENT",
                f"Line {idx}: HSN '{hsn}' does not have enough digits for the company's turnover tier.",
            ))
        if hsn not in hsn_master_cache:
            hsn_master_cache[hsn] = _check_hsn_master(hsn, doc_date)
        master_issue = hsn_master_cache[hsn]
        if master_issue is not None:
            severity, issue = master_issue
            (blocking if severity == "blocking" else warning).append(issue)

        gst_rate = getattr(item, "gst_rate", 0)
        # A line whose rate was itself deliberately pinned (rate_override, e.g.
        # a challan/order rate snapshotted forward on conversion) is exactly
        # the historical noise _check_rate_consistency already excludes when
        # building recent_rates — the current line deserves the same
        # exemption, or every converted document warns on its own pinned rate.
        if not getattr(item, "rate_override", False):
            rate_key = (hsn, str(gst_rate))
            if rate_key not in rate_cache:
                rate_cache[rate_key] = _check_rate_consistency(company, hsn, gst_rate, doc_date)
            rate_issue = rate_cache[rate_key]
            if rate_issue is not None:
                warning.append(rate_issue)

    return GuardResult(blocking=blocking, warning=warning)


def gst_guard_override_membership(company, acting_user):
    """The acting user's CompanyUser membership if OWNER or MANAGER, else None."""
    from accounts.models import CompanyUser

    from sales.order_gates import _owner_membership

    return _owner_membership(
        company, acting_user, roles=(CompanyUser.Role.OWNER, CompanyUser.Role.MANAGER)
    )


def apply_gst_guard_override(document, *, result: GuardResult, reason: str, acting_user) -> None:
    """Persist the override on ``document`` and write a permanent audit trail
    entry naming the specific issues overridden. Callers must have already
    confirmed a non-blank reason and an OWNER/MANAGER acting_user — this
    function does not re-check either.
    """
    from core.services.audit import AuditService

    membership = gst_guard_override_membership(document.company, acting_user)
    now = timezone.now()
    document.gst_guard_override_reason = reason
    document.gst_guard_overridden_by = membership
    document.gst_guard_overridden_at = now
    document.save(update_fields=[
        "gst_guard_override_reason", "gst_guard_overridden_by", "gst_guard_overridden_at",
    ])
    user = getattr(acting_user, "user", acting_user)  # CompanyUser -> User, or already a User
    AuditService.log(
        action="UPDATE",
        company=document.company,
        user=user,
        entity_type=document.__class__.__name__,
        entity_id=document.pk,
        description=f"GST Guard override: {reason}",
        metadata={
            "issues": [{"code": i.code, "message": i.message} for i in result.blocking],
        },
    )


def document_has_gst_guard_override(document) -> bool:
    """True only when this document itself carries an applied override."""
    reason = (getattr(document, "gst_guard_override_reason", "") or "").strip()
    return bool(
        reason
        and getattr(document, "gst_guard_overridden_by_id", None)
        and getattr(document, "gst_guard_overridden_at", None)
    )
