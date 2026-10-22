"""Stable AGT_E_* codes for the API and UI. The UI maps each to a t() key."""

AGT_E_DISABLED = "AGT_E_DISABLED"
AGT_E_NO_CONSENT = "AGT_E_NO_CONSENT"
AGT_E_BUDGET = "AGT_E_BUDGET"
AGT_E_ROLE = "AGT_E_ROLE"
AGT_E_BAD_TRANSITION = "AGT_E_BAD_TRANSITION"
AGT_E_STALE = "AGT_E_STALE"
AGT_E_EXPIRED = "AGT_E_EXPIRED"
AGT_E_DUPLICATE_RUN = "AGT_E_DUPLICATE_RUN"
AGT_E_VALIDATION = "AGT_E_VALIDATION"
AGT_E_PROVIDER = "AGT_E_PROVIDER"
AGT_E_STEP_LIMIT = "AGT_E_STEP_LIMIT"
AGT_E_TIMEOUT = "AGT_E_TIMEOUT"
AGT_E_REVISION = "AGT_E_REVISION"
AGT_E_ATTEMPTS = "AGT_E_ATTEMPTS"
AGT_E_UNKNOWN_TOOL = "AGT_E_UNKNOWN_TOOL"
AGT_E_UNKNOWN_AGENT = "AGT_E_UNKNOWN_AGENT"
AGT_E_UNKNOWN_KIND = "AGT_E_UNKNOWN_KIND"
AGT_E_DAILY_CAP = "AGT_E_DAILY_CAP"
AGT_E_GLOBAL_KILL = "AGT_E_GLOBAL_KILL"

# Failures that may succeed on a retry. Registered in core.idempotency.TRANSIENT_4XX_CODES.
TRANSIENT_CODES = frozenset({AGT_E_PROVIDER, AGT_E_TIMEOUT})


CONFLICT_CODES = frozenset({AGT_E_BAD_TRANSITION, AGT_E_REVISION, AGT_E_EXPIRED, AGT_E_STALE, AGT_E_ATTEMPTS})


def conflict(message: str, code: str):
    """BusinessRuleError that the API returns as 409 (state changed under the caller)."""
    from core.exceptions import BusinessRuleError

    exc = BusinessRuleError(message, code=code)
    exc.status_code = 409
    return exc
