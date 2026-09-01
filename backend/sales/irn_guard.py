"""Block books-cancel while a live IRN / e-Way still exists on the portal."""

from core.exceptions import BusinessRuleError

LIVE_IRN = ("GENERATED", "MANUAL_IRN")
LIVE_EWAY = ("GENERATED", "MANUAL_EWB")


def assert_no_live_irn(doc, *, kind: str = "document") -> None:
    irn = (getattr(doc, "irn", None) or "").strip()
    status = getattr(doc, "einvoice_status", None) or ""
    if irn and status not in ("CANCELLED", "FAILED", "NONE", ""):
        raise BusinessRuleError(
            f"This {kind} has a live IRN. Cancel the e-invoice first, then cancel it in books."
        )


def assert_no_live_eway(doc, *, kind: str = "document") -> None:
    ewb = (getattr(doc, "eway_bill_no", None) or "").strip()
    status = getattr(doc, "eway_status", None) or ""
    if ewb and status in LIVE_EWAY:
        raise BusinessRuleError(
            f"This {kind} has a live e-Way bill. Cancel the e-Way first, then cancel it in books."
        )
