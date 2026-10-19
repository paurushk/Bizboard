"""SET-14: stable codes for errors raised by Settings endpoints.

Each code has a plain-language cause and fix in the web catalogue (``web/src/i18n``: ``settingsErrors``),
in English and Hindi. ``web/src/utils/settingsErrors.test.ts`` fails if a code listed here has no entry,
and ``tests/test_settings_error_codes.py`` fails if a code listed here is never raised.
"""

SETTINGS_ERROR_CODES: tuple[str, ...] = (
    "SETTINGS_STALE",
    "series_invalid",
    "PRICE_LIST_IN_USE",
    "UNIT_IN_USE",
    "GATEWAY_KEYS_REFUSED",
    "GATEWAY_PROVIDER_DISABLED",
    "GATEWAY_ADDRESS_UNSUPPORTED",
    "GATEWAY_CHECK_TOO_SOON",
    "ACCOUNTING_PERIOD_CLOSED",
    "ACCOUNTING_BACKFILL_RUNNING",
    "REASON_REQUIRED",
    "ACKNOWLEDGE_REQUIRED",
    "PASSWORD_NOT_SET",
    "REAUTH_LOCKED",
    "CHURN_REASON_REQUIRED",
    "COMPANY_NAME_MISMATCH",
    "ALREADY_SUSPENDED",
    "RESTORE_LIVE_DISABLED",
    "LICENCE_LOCKED",
    "LICENCE_INACTIVE",
    "LICENCE_UNCHANGED",
)
