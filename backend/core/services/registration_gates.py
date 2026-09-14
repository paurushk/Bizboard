"""Registration-type gates for GST tax invoices (BB-000007)."""

from __future__ import annotations

from accounts.models import Company
from core.exceptions import BusinessRuleError
from core.help_codes import HelpCode


def assert_may_issue_gst_tax_invoice(company: Company, *, tax_enabled: bool) -> None:
    """COMPOSITION/UNREGISTERED must not issue CGST/SGST/IGST tax invoices.

    B14: REGULAR + GST invoice also requires a company GSTIN so skip-wizard
    tenants cannot Complete a tax invoice and only discover the hole at period close.
    """
    if not tax_enabled:
        return
    rt = company.registration_type
    if rt == Company.RegistrationType.REGULAR:
        gstin = (getattr(company, "gstin", None) or "").strip()
        if not gstin:
            from accounts.models import CompanyGstin

            gstin = (
                CompanyGstin.objects.filter(company=company, is_active=True)
                .exclude(gstin="")
                .values_list("gstin", flat=True)
                .first()
                or ""
            )
        if not (gstin or "").strip():
            raise BusinessRuleError(
                "Save the company GSTIN in GST settings before completing a GST invoice.",
                code=HelpCode.COMPANY_GSTIN_REQUIRED,
            )
    if rt == Company.RegistrationType.UNREGISTERED:
        raise BusinessRuleError(
            "Unregistered companies cannot issue GST/TAX invoices with CGST/SGST/IGST. "
            "Use a non-GST bill type.",
            code=HelpCode.REGISTRATION_GATE,
        )
    if rt == Company.RegistrationType.COMPOSITION:
        raise BusinessRuleError(
            "Composition dealers cannot issue regular GST tax invoices. "
            "Use a Bill of Supply / non-GST document type. "
            "CMP-08 / GSTR-4 aids are at /api/v1/reports/cmp08/ and /api/v1/reports/gstr4/.",
            code=HelpCode.REGISTRATION_GATE,
        )
