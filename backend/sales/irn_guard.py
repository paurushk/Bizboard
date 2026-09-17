"""Block books-cancel / line-amend while a live IRN / e-Way still exists on the portal."""

from core.exceptions import BusinessRuleError

LIVE_IRN = ("GENERATED", "MANUAL_IRN")
LIVE_EWAY = ("GENERATED", "MANUAL_EWB")
IN_FLIGHT = ("QUEUED", "PENDING", "IN_PROGRESS")
NON_LIVE_IRN = ("CANCELLED", "FAILED", "NONE", "")


def assert_no_live_irn(doc, *, kind: str = "document", action: str = "cancel") -> None:
    irn = (getattr(doc, "irn", None) or "").strip()
    status = (getattr(doc, "einvoice_status", None) or "").strip().upper()
    if status in IN_FLIGHT:
        raise BusinessRuleError(
            f"This {kind} has an in-flight e-invoice request. Wait for generation to finish or fail before proceeding."
        )
    live = status in LIVE_IRN or (bool(irn) and status not in NON_LIVE_IRN)
    if not live:
        return
    if action == "amend":
        raise BusinessRuleError(
            f"This {kind} has a live IRN. Cancel the e-invoice first before amending lines."
        )
    raise BusinessRuleError(
        f"This {kind} has a live IRN. Cancel the e-invoice first, then cancel it in books."
    )


def assert_no_live_eway(doc, *, kind: str = "document") -> None:
    ewb = (getattr(doc, "eway_bill_no", None) or "").strip()
    status = (getattr(doc, "eway_status", None) or "").strip().upper()
    if status in IN_FLIGHT:
        raise BusinessRuleError(
            f"This {kind} has an in-flight e-Way bill request. Wait for generation to finish or fail before proceeding."
        )
    if ewb and status in LIVE_EWAY:
        raise BusinessRuleError(
            f"This {kind} has a live e-Way bill. Cancel the e-Way first, then cancel it in books."
        )
