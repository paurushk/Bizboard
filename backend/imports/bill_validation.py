"""Single source of truth for bill-import validation.

The preview endpoint returns these errors per line / for the header so the UI
renders them instead of re-implementing the rules, and commit raises them all
at once (never silently unchecking a line the user included).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from core.exceptions import BusinessRuleError

FUTURE_DATE_WINDOW_DAYS = int(getattr(settings, "BILL_IMPORT_FUTURE_DATE_DAYS", 7) or 7)


def _err(field: str, code: str, message: str, severity: str = "error") -> dict:
    return {"field": field, "code": code, "message": message, "severity": severity}


def line_errors(line: dict, *, kind: str | None = None) -> list[dict]:
    """Structured validation of one preview line (only meaningful when included)."""
    from imports import services as svc

    errors: list[dict] = []
    if not str(line.get("name") or "").strip():
        errors.append(_err("name", "NAME_REQUIRED", "name is required"))
    try:
        if svc._as_decimal(line.get("quantity"), "0") <= 0:
            errors.append(_err("quantity", "QTY_POSITIVE", "quantity must be > 0"))
    except BusinessRuleError:
        errors.append(_err("quantity", "QTY_NUMBER", "quantity must be a number"))
    try:
        if svc._as_decimal(line.get("unit_price"), "0") < 0:
            errors.append(_err("unit_price", "PRICE_NEGATIVE", "unit_price cannot be negative"))
    except BusinessRuleError:
        errors.append(_err("unit_price", "PRICE_NUMBER", "unit_price must be a number"))

    raw_gst = line.get("gst_rate")
    if raw_gst in (None, ""):
        errors.append(_err("gst_rate", "GST_REQUIRED", "GST rate is required"))
    else:
        try:
            rate = svc._as_decimal(str(raw_gst).strip().rstrip("%").strip())
            if rate not in svc.ALLOWED_GST:
                errors.append(
                    _err("gst_rate", "GST_SLAB", f"GST rate {rate} is not an allowed slab")
                )
        except BusinessRuleError:
            errors.append(_err("gst_rate", "GST_NUMBER", "GST rate must be a number"))

    hsn = str(line.get("hsn_code") or "").strip()
    if hsn and not svc.HSN_RE.match(hsn):
        errors.append(_err("hsn_code", "HSN_FORMAT", "invalid HSN code"))

    disc = line.get("discount_percent")
    if disc not in (None, ""):
        try:
            d = svc._as_decimal(disc)
            if d < 0 or d > 100:
                errors.append(
                    _err("discount_percent", "DISCOUNT_RANGE", "discount must be between 0 and 100")
                )
        except BusinessRuleError:
            errors.append(_err("discount_percent", "DISCOUNT_NUMBER", "discount must be a number"))
    return errors


def line_error_messages(line: dict) -> list[str]:
    return [e["message"] for e in line_errors(line)]


def _period_issue(company, doc_date) -> tuple[str, str] | None:
    """Read-only check of locked GST / accounting periods (no row creation)."""
    from reporting.models import GstReturnPeriod

    period = f"{doc_date.year:04d}-{doc_date.month:02d}"
    gst = GstReturnPeriod.objects.filter(company=company, period=period).first()
    if gst is not None and gst.status == GstReturnPeriod.Status.CLOSED:
        return "error", f"GST period {period} is closed."
    if gst is not None and gst.status == GstReturnPeriod.Status.SOFT_CLOSED:
        return "warning", f"GST period {period} is soft-closed; completing this invoice will be blocked."
    try:
        from accounting.models import AccountingPeriod
    except Exception:  # pragma: no cover
        return None
    acct = AccountingPeriod.objects.filter(
        company=company, start_date__lte=doc_date, end_date__gte=doc_date,
    ).exclude(status=AccountingPeriod.Status.OPEN).first()
    if acct is not None:
        status = str(acct.status)
        if status == AccountingPeriod.Status.CLOSED:
            return "error", f"Accounting period covering {doc_date} is closed."
        return "warning", f"Accounting period covering {doc_date} is {status.lower()}."
    return None


def header_errors(job, preview: dict, included: list[dict]) -> list[dict]:
    """Header-level problems (date, party, confidence, company GSTIN, duplicates)."""
    from imports import services as svc
    from imports.models import ImportJob

    errors: list[dict] = []
    is_sales = job.kind == ImportJob.Kind.SALES_BILL

    bill_date = None
    try:
        bill_date = svc.BillImportService._parse_bill_date(
            str(preview.get("bill_date") or ""), required=True
        )
    except BusinessRuleError as exc:
        errors.append(_err("bill_date", "BILL_DATE", str(exc.detail)))
    if bill_date is not None:
        today = timezone.localdate()
        if bill_date > today + timedelta(days=FUTURE_DATE_WINDOW_DAYS):
            errors.append(
                _err("bill_date", "BILL_DATE_FUTURE", f"Bill date {bill_date} is in the future.", "warning")
            )
        issue = _period_issue(job.company, bill_date)
        if issue:
            errors.append(_err("bill_date", "PERIOD_LOCKED", issue[1], issue[0]))

    if is_sales:
        has_party = bool(
            job.customer_id
            or str(preview.get("customer_name") or "").strip()
            or str(preview.get("buyer_name") or "").strip()
        )
        if not has_party:
            errors.append(
                _err("customer", "PARTY_REQUIRED", "Select a customer or enter the customer name from the bill.")
            )
    else:
        has_party = bool(job.supplier_id or str(preview.get("supplier_name") or "").strip())
        if not has_party:
            errors.append(
                _err("supplier", "PARTY_REQUIRED", "Select a supplier or enter the supplier name from the bill.")
            )

    confidence = svc._parse_extraction_confidence(preview.get("extraction_confidence", 1))
    if confidence < svc.OCR_BILL_MIN_CONFIDENCE and not preview.get("low_confidence_accepted"):
        errors.append(
            _err(
                "low_confidence_accepted",
                "LOW_CONFIDENCE",
                f"OCR confidence ({confidence:.2f}) is below {svc.OCR_BILL_MIN_CONFIDENCE:.2f}. "
                "Check every value, then tick the confirmation.",
            )
        )

    status = svc.company_gstin_status(job.company, preview, kind=job.kind)
    if status["status"] == "unresolved":
        errors.append(
            _err(
                "company_gstin_id",
                "COMPANY_GSTIN_UNRESOLVED",
                "Your company has several GSTINs and the one on the bill was not recognised. "
                "Choose which GSTIN issued this bill.",
            )
        )

    if is_sales and included and bill_date is not None:
        ref = str(preview.get("bill_number") or "").strip()[:64]
        if ref and not preview.get("confirm_duplicate"):
            from sales.models import SalesInvoice

            dup = SalesInvoice.objects.filter(
                company=job.company, external_reference=ref, invoice_date=bill_date,
            ).exclude(status=SalesInvoice.Status.CANCELLED)
            if job.customer_id:
                dup = dup.filter(customer_id=job.customer_id)
            if dup.exists():
                errors.append(
                    _err(
                        "bill_number",
                        "DUPLICATE_BILL",
                        f"A sales invoice from bill {ref} dated {bill_date} already exists. "
                        "Tick 'This is not a duplicate' to continue.",
                    )
                )
    if not is_sales and included and bill_date is not None and job.supplier_id:
        ref = str(preview.get("bill_number") or "").strip()[:64]
        if ref and not preview.get("confirm_duplicate"):
            from purchases.models import PurchaseInvoice

            if PurchaseInvoice.objects.filter(
                company=job.company, supplier_id=job.supplier_id,
                supplier_bill_number=ref, invoice_date=bill_date,
            ).exclude(status=PurchaseInvoice.Status.CANCELLED).exists():
                errors.append(
                    _err(
                        "bill_number",
                        "DUPLICATE_BILL",
                        f"A purchase from bill {ref} dated {bill_date} already exists for this supplier. "
                        "Tick 'This is not a duplicate' to continue.",
                    )
                )
    if job.file_sha256:
        same = (
            ImportJob.objects.filter(
                company=job.company, kind=job.kind, file_sha256=job.file_sha256,
                status=ImportJob.Status.COMMITTED,
            )
            .exclude(pk=job.pk)
            .exists()
        )
        if same:
            errors.append(
                _err(
                    "file",
                    "DUPLICATE_FILE",
                    "This exact file was already imported and committed.",
                    "warning",
                )
            )
    return errors


def _v2(job) -> bool:
    from core.services.feature_flags import flag_enabled

    return flag_enabled(job.company, "BILL_IMPORT_REVIEW_V2")


# Roles that may keep a reviewed price below the customer's price list.
PRICE_OVERRIDE_ROLES = {"OWNER", "MANAGER"}


def line_policy_errors(job, line: dict, *, user=None) -> list[dict]:
    """Rules that depend on company/user context (product choice, price list)."""
    from imports import services as svc
    from imports.models import ImportJob

    errors: list[dict] = []
    if _v2(job):
        pm = line.get("product_match") or {}
        if not line.get("product_id") and not line.get("create_new") and pm.get("status") == "candidates":
            errors.append(
                _err(
                    "product",
                    "PRODUCT_CHOICE_REQUIRED",
                    "Similar products exist. Pick the matching product or mark this as a new product.",
                )
            )
    if job.kind == ImportJob.Kind.SALES_BILL and line.get("below_price_list") and user is not None:
        role = svc.BillImportService._import_role(job, user)
        if role not in PRICE_OVERRIDE_ROLES:
            errors.append(
                _err(
                    "unit_price",
                    "PRICE_BELOW_LIST",
                    f"Price {line.get('unit_price')} is below the customer's price list "
                    f"({line.get('price_list_price')}). Ask an owner or manager to approve this bill.",
                )
            )
    return errors


def policy_header_errors(job, preview: dict, included: list[dict]) -> list[dict]:
    errors: list[dict] = []
    if _v2(job):
        new_lines = [
            ln for ln in included
            if not ln.get("product_id") and (ln.get("product_match") or {}).get("status") == "none"
        ]
        if new_lines and not preview.get("confirm_new_products"):
            errors.append(
                _err(
                    "confirm_new_products",
                    "NEW_PRODUCTS_UNCONFIRMED",
                    f"{len(new_lines)} line(s) will create new products. Confirm to continue, "
                    "or map them to existing products.",
                )
            )
    return errors


def raise_if_invalid(job, preview: dict, lines: list[dict], *, user=None) -> None:
    """Strict commit-time gate: every included line + the header, all at once."""
    included = [(i, ln) for i, ln in enumerate(lines, start=1) if ln.get("include")]
    line_problems = []
    for index, ln in included:
        errs = line_errors(ln, kind=job.kind) + line_policy_errors(job, ln, user=user)
        if errs:
            line_problems.append(
                {
                    "row": index,
                    "lineId": ln.get("line_id"),
                    "name": ln.get("name") or "",
                    "errors": errs,
                }
            )
    included_lines = [ln for _, ln in included]
    head = [
        e for e in header_errors(job, preview, included_lines) + policy_header_errors(job, preview, included_lines)
        if e["severity"] == "error"
    ]
    if not included:
        head.append(_err("lines", "NO_LINES", "Select at least one valid line to commit."))
    if line_problems or head:
        parts = []
        if line_problems:
            parts.append(f"{len(line_problems)} line(s) need fixing")
        if head:
            parts.append("; ".join(e["message"] for e in head))
        raise BusinessRuleError(
            "Fix the highlighted rows before creating the draft: " + " · ".join(parts),
            code="BILL_VALIDATION",
            extra={"lineErrors": line_problems, "headerErrors": head},
        )


def to_decimal_or_none(value) -> Decimal | None:
    try:
        text = str(value if value not in (None, "") else "").strip()
        return Decimal(text) if text else None
    except Exception:  # noqa: BLE001
        return None
