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


# BB-100 F2 (D-14, 2026-10-24): bills of supply of a regular taxpayer. Off until the CA agrees.
BILL_OF_SUPPLY_FLAG = "GST_BILL_OF_SUPPLY_RETURNS"
_NON_TAXABLE_NATURES = frozenset({"NIL", "EXEMPT", "NON_GST"})


def bill_of_supply_rules_on(company: Company) -> bool:
    """True when a regular company's Non-GST invoices follow the bill-of-supply rules."""
    from core.services.feature_flags import flag_enabled

    return (
        company.registration_type == Company.RegistrationType.REGULAR
        and flag_enabled(company, BILL_OF_SUPPLY_FLAG)
    )


def assert_bill_of_supply_lines(company: Company, *, invoice_type: str, items) -> None:
    """A regular company's bill of supply may carry only nil-rated, exempt or non-GST lines;
    a taxable item belongs on a GST invoice, or its tax is silently not charged."""
    if invoice_type != "NON_GST" or not bill_of_supply_rules_on(company):
        return
    taxable = [
        idx for idx, item in enumerate(items, start=1)
        if (getattr(item, "supply_nature", None) or "TAXABLE").upper() not in _NON_TAXABLE_NATURES
    ]
    if taxable:
        lines = ", ".join(str(i) for i in taxable[:10])
        raise BusinessRuleError(
            f"A bill of supply cannot include taxable items (line {lines}). Mark each line nil-rated, "
            "exempt or non-GST, or make this a GST invoice.",
            code="bill_of_supply_taxable_line",
        )

