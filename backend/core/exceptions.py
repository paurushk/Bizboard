from django.db import IntegrityError
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


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


def api_exception_handler(exc, context):
    """Standard error envelope: {"success": false, "error": {...}} (E0.9)."""
    if isinstance(exc, IntegrityError):
        # A DB-level unique/foreign-key constraint firing (e.g. a duplicate
        # GSTIN/barcode conditional UniqueConstraint that DRF can't
        # auto-validate) should surface as a clean 400, not an unhandled 500.
        return Response(
            {
                "success": False,
                "error": {
                    "code": "integrity_error",
                    "message": "This conflicts with an existing record (duplicate value).",
                    "details": str(exc),
                },
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    detail = response.data
    if isinstance(detail, dict) and "detail" in detail and len(detail) == 1:
        message = str(detail["detail"])
    elif isinstance(detail, list):
        message = "; ".join(str(d) for d in detail)
    else:
        message = "Validation failed." if response.status_code == 400 else "Request failed."

    response.data = {
        "success": False,
        "error": {
            "code": getattr(exc, "default_code", "error"),
            "message": message,
            "details": detail,
        },
    }
    return response
