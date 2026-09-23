"""E1 spike: map existing alert and action sources onto one event shape.

This is the schema the later pipeline would consume. It does not execute
events, adjust thresholds, or call a model. Approval is assignment.
Dismiss and snooze are "not now". Learning is a report a person reads.
"""

from __future__ import annotations

OUTCOME = {
    "acted": "assigned and then resolved, or dismissed, inside the row window",
    "metric": "where measurable, whether the underlying metric improved after",
}
LEARNING = {
    "v1": "a report a person reads",
    "excluded": "automatic threshold changes",
}
APPROVAL = "assignment"
NOT_APPROVAL = ("dismiss", "snooze")

# Codes emitted by the attention feed and the alerts engine today, plus the
# rows this program adds. A test fails if a new feed code is missing here.
EVENT_SOURCES = {
    "AR_OVERDUE_CRITICAL": {"kind": "receivable", "entity": "customer"},
    "AR_OVERDUE_WARN": {"kind": "receivable", "entity": "customer"},
    "AR_OVERDUE_CUSTOMER": {"kind": "receivable", "entity": "customer"},
    "AR_COLLECTION_RISK": {"kind": "receivable", "entity": "customer"},
    "AR_RESIDUAL_AFTER_RETURN": {"kind": "receivable", "entity": "customer"},
    "AP_DUE_7D": {"kind": "payable", "entity": "supplier"},
    "CREDIT_LIMIT_NEAR": {"kind": "credit", "entity": "customer"},
    "CUSTOMER_CONCENTRATION": {"kind": "sales", "entity": "customer"},
    "MARGIN_DROP_SKU": {"kind": "margin", "entity": "product"},
    "MARGIN_COMPRESSION": {"kind": "margin", "entity": "product"},
    "SALE_BELOW_COST": {"kind": "margin", "entity": "product"},
    "DISCOUNT_OVER_THRESHOLD": {"kind": "discount", "entity": "invoice"},
    "DISCOUNT_STACKED": {"kind": "discount", "entity": "invoice"},
    "DISCOUNT_FREQUENCY": {"kind": "discount", "entity": "customer"},
    "PURCHASE_PRICE_JUMP": {"kind": "purchase", "entity": "product"},
    "PURCHASE_PRICE_CREEP": {"kind": "purchase", "entity": "product"},
    "CASH_TIGHT_14D": {"kind": "cash", "entity": "company"},
    "ITC_AT_RISK": {"kind": "gst", "entity": "company"},
    "GSTR2B_UNMATCHED": {"kind": "gst", "entity": "company"},
    "GST_HEALTH_CRITICAL_OPEN": {"kind": "gst", "entity": "company"},
    "GST_GUARDRAIL": {"kind": "gst", "entity": "invoice"},
    "GST_RATE_EXPOSURE": {"kind": "gst", "entity": "product"},
    "DUPLICATE_PAYMENT": {"kind": "payment", "entity": "payment"},
    "OVERDUE_CONCENTRATION": {"kind": "receivable", "entity": "customer"},
    "PAID_PENDING_BOOKS": {"kind": "books", "entity": "payment"},
    "LOW_STOCK_FAST_MOVER": {"kind": "stock", "entity": "product"},
    "DEAD_STOCK": {"kind": "stock", "entity": "product"},
    "EXPIRING_STOCK": {"kind": "stock", "entity": "product"},
    "ABNORMAL_STOCK_ADJUSTMENT": {"kind": "stock", "entity": "adjustment"},
    "NO_SALES_TODAY": {"kind": "sales", "entity": "company"},
    "EINVOICE_FAILED": {"kind": "gst", "entity": "invoice"},
    "EINVOICE_PENDING": {"kind": "gst", "entity": "invoice"},
    "IRN_FAILED": {"kind": "gst", "entity": "invoice"},
    "PREDICTED_LATE_PAYMENT": {"kind": "receivable", "entity": "customer"},
    "CHURN_RISK": {"kind": "sales", "entity": "customer"},
    "REPEAT_ORDER_DUE": {"kind": "sales", "entity": "product"},
}


def event_for(code: str) -> dict:
    source = EVENT_SOURCES[code]
    return {
        "code": code,
        "kind": source["kind"],
        "entity": source["entity"],
        "approval": APPROVAL,
        "not_approval": list(NOT_APPROVAL),
        "outcome": OUTCOME,
        "learning": LEARNING,
    }
