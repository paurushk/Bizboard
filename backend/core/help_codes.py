"""Stable Help error codes (HR-1.1).

Only the listed raise sites pass `code=`. The rest of ~687 BusinessRuleError
raises keep `business_rule_violation`. Do not invent codes outside this module.
"""

from __future__ import annotations


class HelpCode:
    INSUFFICIENT_STOCK = "insufficient_stock"
    INACTIVE_PRODUCT = "inactive_product"
    BLOCKED_CUSTOMER = "blocked_customer"
    COMPLETED_IMMUTABLE = "completed_immutable"
    REGISTRATION_GATE = "registration_gate"
    PLACE_OF_SUPPLY_UNRESOLVED = "place_of_supply_unresolved"
    CREDIT_LIMIT_EXCEEDED = "credit_limit_exceeded"
    CLOSED_PERIOD = "closed_period"
    COMPANY_GSTIN_REQUIRED = "company_gstin_required"
    SALES_RCM_UNCONFIRMED = "sales_rcm_unconfirmed"
    INVALID_GST_RATE = "invalid_gst_rate"
    ALLOCATION_EXCEEDS_UNALLOCATED = "allocation_exceeds_unallocated"
    ALLOCATION_PARTY_MISMATCH = "allocation_party_mismatch"
    IMPORT_INVALID_ROWS = "import_invalid_rows"
    PDF_OR_SHARE_UNAVAILABLE = "pdf_or_share_unavailable"
    PERMISSION_DENIED = "permission_denied"


ALL_HELP_CODES: tuple[str, ...] = (
    HelpCode.INSUFFICIENT_STOCK,
    HelpCode.INACTIVE_PRODUCT,
    HelpCode.BLOCKED_CUSTOMER,
    HelpCode.COMPLETED_IMMUTABLE,
    HelpCode.REGISTRATION_GATE,
    HelpCode.PLACE_OF_SUPPLY_UNRESOLVED,
    HelpCode.CREDIT_LIMIT_EXCEEDED,
    HelpCode.CLOSED_PERIOD,
    HelpCode.COMPANY_GSTIN_REQUIRED,
    HelpCode.SALES_RCM_UNCONFIRMED,
    HelpCode.INVALID_GST_RATE,
    HelpCode.ALLOCATION_EXCEEDS_UNALLOCATED,
    HelpCode.ALLOCATION_PARTY_MISMATCH,
    HelpCode.IMPORT_INVALID_ROWS,
    HelpCode.PDF_OR_SHARE_UNAVAILABLE,
    HelpCode.PERMISSION_DENIED,
)

# intentId keyed for the FE map / CI check. permission_denied is HTTP 403.
ERROR_CODE_TO_INTENT: dict[str, str] = {
    HelpCode.INSUFFICIENT_STOCK: "stock-in-another-godown",
    HelpCode.INACTIVE_PRODUCT: "sell-blocked",
    HelpCode.BLOCKED_CUSTOMER: "sell-blocked",
    HelpCode.COMPLETED_IMMUTABLE: "edit-completed-invoice",
    HelpCode.REGISTRATION_GATE: "cannot-complete-invoice",
    HelpCode.PLACE_OF_SUPPLY_UNRESOLVED: "cannot-complete-invoice",
    HelpCode.CREDIT_LIMIT_EXCEEDED: "cannot-complete-invoice",
    HelpCode.CLOSED_PERIOD: "cannot-complete-invoice",
    HelpCode.COMPANY_GSTIN_REQUIRED: "add-gstin",
    HelpCode.SALES_RCM_UNCONFIRMED: "cannot-complete-invoice",
    HelpCode.INVALID_GST_RATE: "wrong-gst-on-invoice",
    HelpCode.ALLOCATION_EXCEEDS_UNALLOCATED: "payment-wont-allocate",
    HelpCode.ALLOCATION_PARTY_MISMATCH: "payment-wont-allocate",
    HelpCode.IMPORT_INVALID_ROWS: "import-row-errors",
    HelpCode.PDF_OR_SHARE_UNAVAILABLE: "pdf-or-share-unavailable",
    HelpCode.PERMISSION_DENIED: "login-cant-do-this",
}

# Skip the diagnosis picker when the error already names the leaf (HR-3.3).
ERROR_CODE_TO_LEAF: dict[str, str] = {
    HelpCode.INACTIVE_PRODUCT: "inactive",
    HelpCode.BLOCKED_CUSTOMER: "blocked-party",
    HelpCode.REGISTRATION_GATE: "reg",
    HelpCode.PLACE_OF_SUPPLY_UNRESOLVED: "pos",
    HelpCode.CREDIT_LIMIT_EXCEEDED: "credit",
    HelpCode.SALES_RCM_UNCONFIRMED: "rcm",
    HelpCode.CLOSED_PERIOD: "period",
    HelpCode.INVALID_GST_RATE: "rate",
    HelpCode.ALLOCATION_EXCEEDS_UNALLOCATED: "amount",
    HelpCode.ALLOCATION_PARTY_MISMATCH: "party",
    HelpCode.IMPORT_INVALID_ROWS: "one-bad-row",
}
