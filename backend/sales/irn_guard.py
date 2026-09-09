"""Block books-cancel while a live IRN / e-Way still exists on the portal."""

from core.exceptions import BusinessRuleError

LIVE_IRN = ("GENERATED", "MANUAL_IRN")
LIVE_EWAY = ("GENERATED", "MANUAL_EWB")


def assert_no_live_irn(doc, *, kind: str = "document") -> None:
    irn = (getattr(doc, "irn", None) or "").strip()
    status = (getattr(doc, "einvoice_status", None) or "").strip().upper()
    if status in ("QUEUED", "PENDING", "IN_PROGRESS"):
        raise BusinessRuleError(
            f"This {kind} has an in-flight e-invoice request. Wait for generation to finish or fail before proceeding."
        )
    if irn and status not in ("CANCELLED", "FAILED", "NONE", ""):
        raise BusinessRuleError(
            f"This {kind} has a live IRN. Cancel the e-invoice first, then cancel it in books."
        )


def assert_no_live_eway(doc, *, kind: str = "document") -> None:
    ewb = (getattr(doc, "eway_bill_no", None) or "").strip()
    status = (getattr(doc, "eway_status", None) or "").strip().upper()
    if status in ("QUEUED", "PENDING", "IN_PROGRESS"):
        raise BusinessRuleError(
            f"This {kind} has an in-flight e-Way bill request. Wait for generation to finish or fail before proceeding."
        )
    if ewb and status in LIVE_EWAY:
        raise BusinessRuleError(
            f"This {kind} has a live e-Way bill. Cancel the e-Way first, then cancel it in books."
        )
