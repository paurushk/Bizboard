"""Registration-type gates for GST tax invoices (BB-000007)."""

from __future__ import annotations

from accounts.models import Company
from core.exceptions import BusinessRuleError


def assert_may_issue_gst_tax_invoice(company: Company, *, tax_enabled: bool) -> None:
    """COMPOSITION/UNREGISTERED must not issue CGST/SGST/IGST tax invoices."""
    if not tax_enabled:
        return
    rt = company.registration_type
    if rt == Company.RegistrationType.UNREGISTERED:
        raise BusinessRuleError(
            "Unregistered companies cannot issue GST/TAX invoices with CGST/SGST/IGST. "
            "Use a non-GST bill type."
        )
    if rt == Company.RegistrationType.COMPOSITION:
        raise BusinessRuleError(
            "Composition dealers cannot issue regular GST tax invoices. "
            "Use a Bill of Supply / non-GST document type. "
            "CMP-08 / GSTR-4 aids are at /api/v1/reports/cmp08/ and /api/v1/reports/gstr4/."
        )
