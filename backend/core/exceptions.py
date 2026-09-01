from django.db import IntegrityError
from rest_framework import status
from rest_framework.exceptions import APIException


class BusinessRuleError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Business rule violated."
    default_code = "business_rule_violation"


class OtpExpiredError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "OTP expired or not found."
    default_code = "otp_expired"


class OtpTooManyAttemptsError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Too many attempts."
    default_code = "otp_too_many_attempts"


class OtpInvalidError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid OTP."
    default_code = "otp_invalid"


class TooManyLoginAttemptsError(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = "Too many failed login attempts. Try again later."
    default_code = "login_locked_out"


class CompanyContextConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "X-Company-Id does not match the active company. Switch company first."
    default_code = "company_context_conflict"


class CompanyRequired(APIException):
    """D-01: multi-membership user must pick a company (no silent auto-pick)."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "Select a company to continue."
    default_code = "COMPANY_REQUIRED"

    def __init__(self, memberships):
        detail = {
            "code": "COMPANY_REQUIRED",
            "message": self.default_detail,
            "memberships": [
                {
                    "id": m.company_id,
                    "name": getattr(m.company, "name", ""),
                    "role": m.role,
                }
                for m in memberships
            ],
        }
        super().__init__(detail=detail, code="COMPANY_REQUIRED")


class GstinTotalChanged(APIException):
    """W0-02: Complete would change grand_total after filing-GSTIN recompute."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "Completing would change the invoice total because tax was recomputed "
        "for the filing GSTIN. Confirm to continue."
    )
    default_code = "GSTIN_TOTAL_CHANGED"

    def __init__(self, before, after, lines):
        detail = {
            "code": "GSTIN_TOTAL_CHANGED",
            "message": self.default_detail,
            "before": {k: str(v) for k, v in before.items()},
            "after": {k: str(v) for k, v in after.items()},
            "lines": lines,
        }
        super().__init__(detail=detail, code="GSTIN_TOTAL_CHANGED")


class StockCountConflict(APIException):
    """C-01: server qty drifted from the count snapshot — cashier must choose."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "Stock on the server changed since this count was started."
    default_code = "STOCK_COUNT_CONFLICT"

    def __init__(self, conflicts):
        detail = {
            "code": "STOCK_COUNT_CONFLICT",
            "message": self.default_detail,
            "conflicts": conflicts,
        }
        super().__init__(detail=detail, code="STOCK_COUNT_CONFLICT")


def exception_error_code(exc) -> str:
    """Instance code from DRF `get_codes()`, else class `default_code`.

    `BusinessRuleError("…", code=HelpCode.X)` stores the code on the detail;
    the old handler always emitted `default_code` (`business_rule_violation`).
    """
    getter = getattr(exc, "get_codes", None)
    if callable(getter):
        try:
            codes = getter()
        except Exception:  # noqa: BLE001 — never fail the error envelope
            codes = None
        if isinstance(codes, str) and codes.strip():
            return codes.strip()
        if isinstance(codes, dict):
            for value in codes.values():
                if isinstance(value, str) and value.strip():
                    return value.strip()
        if isinstance(codes, (list, tuple)) and codes:
            first = codes[0]
            if isinstance(first, str) and first.strip():
                return first.strip()
    return str(getattr(exc, "default_code", None) or "error")


def api_exception_handler(exc, context):
    """Standard error envelope: {"success": false, "error": {...}} (E0.9)."""
    from rest_framework.response import Response

    if isinstance(exc, IntegrityError):
        # A DB-level unique/foreign-key constraint firing (e.g. a duplicate
        # GSTIN/barcode conditional UniqueConstraint that DRF can't
        # auto-validate) should surface as a clean 400, not an unhandled 500.
        from django.db import transaction as db_transaction

        db_transaction.set_rollback(True)
        return Response(
            {
                "success": False,
                "error": {
                    "code": "integrity_error",
                    "message": "This conflicts with an existing record (duplicate value).",
                    "details": None,
                },
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    from rest_framework.views import exception_handler as drf_exception_handler

    response = drf_exception_handler(exc, context)
    if response is None:
        # Unhandled exception — DRF/Django would normally log this via
        # `django.request`, but returning our own Response here suppresses that.
        # Log it (with the traceback) so a production 500 is never silent.
        import logging

        _view = getattr(context.get("view", None), "__class__", None)
        logging.getLogger("django.request").exception(
            "Unhandled exception in %s", getattr(_view, "__name__", "API view")
        )
        return Response(
            {
                "success": False,
                "error": {
                    "code": "server_error",
                    "message": "An unexpected error occurred.",
                    "details": None,
                },
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    detail = response.data
    if isinstance(detail, dict) and "detail" in detail and len(detail) == 1:
        message = str(detail["detail"])
    elif isinstance(detail, list):
        message = "; ".join(str(d) for d in detail)
    elif isinstance(detail, dict):
        parts = []
        for k, v in detail.items():
            msgs = v if isinstance(v, list) else [v]
            for m in msgs:
                if isinstance(m, dict):
                    parts.append(f"{k}: {m}")
                else:
                    parts.append(f"{k}: {m}" if k != "non_field_errors" else str(m))
        message = "; ".join(parts) if parts else (
            "Validation failed." if response.status_code == 400 else "Request failed."
        )
    else:
        message = "Validation failed." if response.status_code == 400 else "Request failed."

    response.data = {
        "success": False,
        "error": {
            "code": exception_error_code(exc),
            "message": message,
            "details": detail,
        },
    }
    return response
