"""Human labels and app links for the document that posted a journal entry.

ACS-10: the Journals screen shows where each entry came from and sends the user to
that document, instead of letting them reverse a system entry on its own.
"""
from __future__ import annotations

MANUAL_SOURCE = "MANUAL_JOURNAL"

# source_type -> (label, app path template or None)
_SOURCES: dict[str, tuple[str, str | None]] = {
    "MANUAL_JOURNAL": ("a manual journal", None),
    "SALES_INVOICE": ("a sales invoice", "/sales/history/{id}"),
    "SALES_RETURN": ("a sales return", "/sales/returns"),
    "SALES_CREDIT_NOTE": ("a sales credit note", "/sales/credit-notes"),
    "SALES_DEBIT_NOTE": ("a sales debit note", "/sales/debit-notes"),
    "PURCHASE_INVOICE": ("a purchase bill", "/purchases/history/{id}"),
    "PURCHASE_RETURN": ("a purchase return", "/purchases/returns"),
    "PURCHASE_CREDIT_NOTE": ("a purchase credit note", "/purchases/credit-notes"),
    "PURCHASE_DEBIT_NOTE": ("a purchase debit note", "/purchases/debit-notes"),
    "CUSTOMER_RECEIPT": ("a customer receipt", "/sales/receipts"),
    "CUSTOMER_ADVANCE_REFUND": ("a customer advance refund", "/sales/receipts"),
    "SUPPLIER_PAYMENT": ("a supplier payment", "/purchases/payments"),
    "PAYMENT_ALLOCATION": ("a payment allocation", "/purchases/payments"),
    "PAY_RUN": ("a payroll run", "/payroll"),
    "FIXED_ASSET": ("a fixed asset", "/accounting/fixed-assets"),
    "WORK_ORDER": ("a work order", None),
    "STOCK_MOVEMENT": ("a stock movement", None),
    "BILL_OF_ENTRY": ("a bill of entry", None),
    "FY_CLOSE": ("the financial-year close", "/accounting/periods"),
    "JOURNAL_REVERSAL": ("the reversal of another journal", None),
    "POS_REFUND": ("a point-of-sale refund", None),
    "CHEQUE_DISHONOUR": ("a bounced cheque", "/sales/receipts"),
    "EXPENSE": ("an expense", "/accounting/expenses"),
}


def source_label(source_type: str | None) -> str:
    if not source_type:
        return "the system"
    known = _SOURCES.get(source_type)
    if known:
        return known[0]
    return "the " + source_type.replace("_", " ").lower() + " document"


def source_path(source_type: str | None, source_id: int | None) -> str | None:
    known = _SOURCES.get(source_type or "")
    if not known or not known[1]:
        return None
    template = known[1]
    if "{id}" in template:
        return template.format(id=source_id) if source_id else None
    return template


def is_manual(source_type: str | None) -> bool:
    return source_type == MANUAL_SOURCE
